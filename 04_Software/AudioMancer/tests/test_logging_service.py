#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_logging_service.py
@brief Focused tests for the AudioMancer logging service.
@details Verifies per-run log creation under the resolved writable data root,
         per-process log file uniqueness, graceful degradation to console-only
         output, cleanup, formatting, component-level overrides, and optional
         function-trace behavior.
"""

# IMPORTS

from datetime import datetime, timedelta
import json
import logging
import os
from pathlib import Path

import pytest

from audiomancer import config
from audiomancer.services import logging_service

# HELPER FUNCTIONS


def _read_log_lines(log_file_path: Path) -> list[str]:
    """
    @brief      Read non-empty lines from one log file.
    @param[in]  log_file_path Path to the generated log file.
    @return     Stripped non-empty log lines.
    @exception  None
    """
    return [line.strip() for line in log_file_path.read_text(encoding="utf-8").splitlines() if line.strip()]


# PUBLIC API


def test_initialize_logging_creates_per_run_log_file(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify logging initialization creates a per-run log file.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    monkeypatch.setattr(config, "APP_USER_DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DEFAULT_LOG_FORMAT", "text")

    log_file_path = logging_service.initialize_logging()
    logger = logging_service.get_component_logger("app")
    logger.info("Created test record", extra={"func_name": "test", "event": "check"})
    logging_service.shutdown_logging()

    assert log_file_path.parent == tmp_path / config.APP_LOG_DIRECTORY_NAME
    assert log_file_path.name.startswith(f"{config.APP_NAME}_")
    assert log_file_path.name.endswith(".log")
    assert log_file_path.is_file()
    assert "Created test record" in log_file_path.read_text(encoding="utf-8")


def test_log_file_name_is_unique_per_process_for_the_same_second(monkeypatch) -> None:
    """
    @brief      Verify concurrent starts in the same second cannot share one log path.
    @details    Covers REQ-FUNC-ab7ace51-daf5-4289-addf-d91cc667e42b / S-LOG-UNIQUE. The
                per-run handler opens with mode="w", so a shared path means the second
                process silently truncates the first process's log.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    run_timestamp = datetime(2026, 7, 25, 19, 46, 57)

    monkeypatch.setattr(os, "getpid", lambda: 111)
    first_path = logging_service._build_log_file_path(run_timestamp)  # noqa: SLF001
    monkeypatch.setattr(os, "getpid", lambda: 222)
    second_path = logging_service._build_log_file_path(run_timestamp)  # noqa: SLF001

    assert first_path != second_path
    for log_path in (first_path, second_path):
        assert log_path.name.startswith(f"{config.APP_NAME}_")
        assert log_path.name.endswith(".log")
        assert "20260725" in log_path.name
        assert "194657" in log_path.name


def test_initialize_logging_removes_only_expired_log_files(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify expired log files are cleaned up while recent ones remain.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    log_directory = tmp_path / config.APP_LOG_DIRECTORY_NAME
    log_directory.mkdir(parents=True, exist_ok=True)

    expired_file = log_directory / "expired.log"
    recent_file = log_directory / "recent.log"
    expired_file.write_text("expired", encoding="utf-8")
    recent_file.write_text("recent", encoding="utf-8")

    old_timestamp = (datetime.now() - timedelta(days=30)).timestamp()
    recent_timestamp = (datetime.now() - timedelta(days=1)).timestamp()
    os.utime(expired_file, (old_timestamp, old_timestamp))
    os.utime(recent_file, (recent_timestamp, recent_timestamp))

    monkeypatch.setattr(config, "APP_USER_DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DEFAULT_LOG_RETENTION_DAYS", 14)

    log_file_path = logging_service.initialize_logging()
    logging_service.shutdown_logging()

    assert not expired_file.exists()
    assert recent_file.exists()
    assert log_file_path.exists()


def test_get_component_logger_applies_component_level_override(monkeypatch) -> None:
    """
    @brief      Verify configured component-level overrides are applied.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    monkeypatch.setattr(config, "DEFAULT_LOG_LEVEL", "INFO")
    monkeypatch.setattr(config, "DEFAULT_LOG_LEVEL_OVERRIDES", {"main_window": "DEBUG"})

    logger = logging_service.get_component_logger("main_window")

    assert logger.name == "main_window"
    assert logger.level == logging.DEBUG


def test_initialize_logging_uses_json_formatter_when_configured(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify JSON mode writes structured JSON log lines.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    monkeypatch.setattr(config, "APP_USER_DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DEFAULT_LOG_FORMAT", "json")

    log_file_path = logging_service.initialize_logging()
    logger = logging_service.get_component_logger("app")
    logger.warning("Structured log line", extra={"func_name": "test", "event": "json-check"})
    logging_service.shutdown_logging()

    payload = json.loads(_read_log_lines(log_file_path)[0])
    assert payload["component"] == "app"
    assert payload["level"] == "WARNING"
    assert payload["event"] == "json-check"
    assert payload["message"] == "Structured log line"


def test_trace_function_logs_start_finish_and_duration(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify the trace decorator logs start, finish, and duration.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    monkeypatch.setattr(config, "APP_USER_DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DEFAULT_LOG_FORMAT", "json")

    log_file_path = logging_service.initialize_logging()
    logger = logging_service.get_component_logger("app", "DEBUG")

    @logging_service.trace_function(logger)
    def traced_function(value: list[int]) -> dict[str, int]:
        """
        @brief      Return a compact result payload for trace logging tests.
        @param[in]  value Input integer list.
        @return     Dictionary carrying the observed item count.
        @exception  None
        """
        return {"count": len(value)}

    result = traced_function([1, 2, 3])
    logging_service.shutdown_logging()

    payloads = [json.loads(line) for line in _read_log_lines(log_file_path)]

    assert result == {"count": 3}
    assert payloads[0]["event"] == "start"
    assert payloads[1]["event"] == "finish"
    assert payloads[0]["params"]["value"] == "list(len=3)"
    assert payloads[1]["result"] == "dict(keys=['count'])"
    assert payloads[1]["duration_ms"] >= 0


def test_trace_function_logs_exception_and_reraises(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify the trace decorator logs exceptions and re-raises them.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    monkeypatch.setattr(config, "APP_USER_DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DEFAULT_LOG_FORMAT", "json")

    log_file_path = logging_service.initialize_logging()
    logger = logging_service.get_component_logger("app", "DEBUG")

    @logging_service.trace_function(logger)
    def failing_function(payload: str) -> None:
        """
        @brief      Raise a runtime error to exercise exception tracing.
        @param[in]  payload Error message payload.
        @return     None.
        @exception  RuntimeError Always raised for this test path.
        """
        raise RuntimeError(payload)

    with pytest.raises(RuntimeError, match="boom"):
        failing_function("boom")
    logging_service.shutdown_logging()

    payloads = [json.loads(line) for line in _read_log_lines(log_file_path)]

    assert payloads[0]["event"] == "start"
    assert payloads[1]["event"] == "exception"
    assert payloads[1]["level"] == "ERROR"
    assert payloads[1]["params"]["payload"] == "'boom'"


def test_trace_function_truncates_long_values(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify traced values are compacted when they exceed the limit.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    monkeypatch.setattr(config, "APP_USER_DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DEFAULT_LOG_FORMAT", "json")

    log_file_path = logging_service.initialize_logging()
    logger = logging_service.get_component_logger("app", "DEBUG")

    @logging_service.trace_function(logger)
    def traced_function(payload: str) -> str:
        """
        @brief      Echo one payload so truncation can be asserted in the trace.
        @param[in]  payload Input string payload.
        @return     Echoed payload string.
        @exception  None
        """
        return payload

    traced_function("x" * 300)
    logging_service.shutdown_logging()

    payloads = [json.loads(line) for line in _read_log_lines(log_file_path)]
    assert payloads[0]["params"]["payload"].endswith("...<truncated>")
    assert payloads[1]["result"].endswith("...<truncated>")


def test_initialize_logging_degrades_to_console_when_log_directory_is_unusable(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """
    @brief      Verify an uncreatable log directory degrades logging instead of raising.
    @details    Covers REQ-NFR-d0afcd7a-79fd-4337-a2a9-713277e6411a / S-0004. The
                data root is placed under a regular file, so the real mkdir call
                fails the same way a read-only installation directory does.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  capsys Pytest captured-output fixture.
    @return     None.
    @exception  None
    """
    blocking_file = tmp_path / "blocking_file"
    blocking_file.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(config, "APP_USER_DATA_ROOT", blocking_file / "AudioMancer")
    monkeypatch.setattr(config, "DEFAULT_LOG_FORMAT", "text")

    log_file_path = logging_service.initialize_logging()
    logging_service.get_component_logger("app").info(
        "still reachable",
        extra={"func_name": "test", "event": "check"},
    )
    root_handlers = list(logging.getLogger().handlers)
    logging_service.shutdown_logging()
    console_output = capsys.readouterr().out

    assert log_file_path is None
    assert len(root_handlers) == 1
    assert isinstance(root_handlers[0], logging.StreamHandler)
    assert "logging-degraded" in console_output
    assert "still reachable" in console_output


def test_initialize_logging_degrades_to_console_when_log_file_cannot_be_opened(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """
    @brief      Verify a log file that cannot be opened degrades logging instead of raising.
    @details    Covers REQ-NFR-d0afcd7a-79fd-4337-a2a9-713277e6411a / S-0004. A
                directory occupies the log file path, so FileHandler raises the
                same OSError an ACL denial would.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  capsys Pytest captured-output fixture.
    @return     None.
    @exception  None
    """
    monkeypatch.setattr(config, "APP_USER_DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DEFAULT_LOG_FORMAT", "text")
    blocked_log_file = tmp_path / config.APP_LOG_DIRECTORY_NAME / "blocked.log"
    blocked_log_file.mkdir(parents=True)
    monkeypatch.setattr(logging_service, "_build_log_file_path", lambda timestamp=None: blocked_log_file)

    log_file_path = logging_service.initialize_logging()
    logging_service.shutdown_logging()
    console_output = capsys.readouterr().out

    assert log_file_path is None
    assert "logging-degraded" in console_output


def test_initialize_logging_survives_unremovable_expired_log_entries(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify retention cleanup errors do not prevent the run from logging.
    @details    Covers REQ-NFR-d0afcd7a-79fd-4337-a2a9-713277e6411a / S-0004. An
                expired entry that is a directory cannot be unlinked, which must
                not stop the new run log from being created.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    log_directory = tmp_path / config.APP_LOG_DIRECTORY_NAME
    unremovable_entry = log_directory / "expired.log"
    unremovable_entry.mkdir(parents=True)
    old_timestamp = (datetime.now() - timedelta(days=30)).timestamp()
    os.utime(unremovable_entry, (old_timestamp, old_timestamp))

    monkeypatch.setattr(config, "APP_USER_DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DEFAULT_LOG_RETENTION_DAYS", 14)

    log_file_path = logging_service.initialize_logging()
    logging_service.shutdown_logging()

    assert log_file_path is not None
    assert log_file_path.is_file()
    assert unremovable_entry.is_dir()


# END OF FILE
