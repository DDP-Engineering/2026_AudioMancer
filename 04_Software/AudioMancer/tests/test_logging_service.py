#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_logging_service.py
@brief Focused tests for the AudioMancer logging service.
@details Verifies per-run log creation, cleanup, formatting, component-level
         overrides, and optional function-trace behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-04
@version 0.1.0
"""

# IMPORTS

import json
import logging
import os
from datetime import datetime, timedelta
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    return [
        line.strip()
        for line in log_file_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# PUBLIC API


def test_initialize_logging_creates_per_run_log_file(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify logging initialization creates a per-run log file.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)
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


def test_initialize_logging_removes_only_expired_log_files(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify expired log files are cleaned up while recent ones remain.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
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

    monkeypatch.setattr(config, "APP_ROOT", tmp_path)
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)
    monkeypatch.setattr(config, "DEFAULT_LOG_FORMAT", "json")

    log_file_path = logging_service.initialize_logging()
    logger = logging_service.get_component_logger("app", "DEBUG")

    @logging_service.trace_function(logger)
    def traced_function(value: list[int]) -> dict[str, int]:
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)
    monkeypatch.setattr(config, "DEFAULT_LOG_FORMAT", "json")

    log_file_path = logging_service.initialize_logging()
    logger = logging_service.get_component_logger("app", "DEBUG")

    @logging_service.trace_function(logger)
    def failing_function(payload: str) -> None:
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)
    monkeypatch.setattr(config, "DEFAULT_LOG_FORMAT", "json")

    log_file_path = logging_service.initialize_logging()
    logger = logging_service.get_component_logger("app", "DEBUG")

    @logging_service.trace_function(logger)
    def traced_function(payload: str) -> str:
        return payload

    traced_function("x" * 300)
    logging_service.shutdown_logging()

    payloads = [json.loads(line) for line in _read_log_lines(log_file_path)]
    assert payloads[0]["params"]["payload"].endswith("...<truncated>")
    assert payloads[1]["result"].endswith("...<truncated>")


# END OF FILE
