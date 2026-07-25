#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file logging_service.py
@brief Centralized application logging helpers for AudioMancer.
@details Initializes per-run logging under the resolved writable data root,
         degrading to console-only output instead of raising when no log file
         can be created, supports text and JSON formatting, applies
         per-component log-level overrides, and provides optional function
         tracing decorators for selected call sites.
@author Eng. Dan Dumitru Pasare
@date 2026-07-25
@version 0.2.0
"""

# IMPORTS

from collections.abc import Callable
from datetime import datetime, timedelta
from functools import wraps
from inspect import signature
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, TypeVar

from .. import config

# CONSTANTS

# @brief Supported textual log-level names accepted by the logging service.
_VALID_LEVEL_NAMES = set(config.LOG_LEVEL_OPTIONS)
# @brief Default human-readable log-line format used by the text formatter.
_TEXT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(func_name)s | %(event)s | %(message)s"
# @brief Maximum serialized argument/result length recorded by trace logging.
_TRACE_VALUE_MAX_LENGTH = 240


# DATA MODELS / TYPEDEFINITIONS

# @brief Generic callable type used by the trace decorator helpers.
_CallableType = TypeVar("_CallableType", bound=Callable[..., Any])


# HELPER FUNCTIONS


def _normalize_level_name(level_name: str | None) -> str:
    """
    @brief      Normalize a textual log-level name.
    @param[in]  level_name Candidate textual level name.
    @return     Supported uppercase level name.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    candidate = (level_name or config.DEFAULT_LOG_LEVEL).strip().upper()
    if candidate not in _VALID_LEVEL_NAMES:
        return config.DEFAULT_LOG_LEVEL
    return candidate


def _resolve_level(level_name: str | None) -> int:
    """
    @brief      Convert a textual log-level name into a logging level value.
    @param[in]  level_name Candidate textual level name.
    @return     Logging module numeric level.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    return getattr(logging, _normalize_level_name(level_name), logging.INFO)


def _resolve_log_format() -> str:
    """
    @brief      Resolve the configured application log output format.
    @return     Supported log format token.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    candidate = (config.DEFAULT_LOG_FORMAT or "text").strip().lower()
    if candidate == "txt":
        candidate = "text"
    if candidate not in config.LOG_FORMAT_OPTIONS:
        return "text"
    return candidate


def _safe_value(value: Any, max_length: int = _TRACE_VALUE_MAX_LENGTH) -> Any:
    """
    @brief      Convert a value into a compact log-safe representation.
    @param[in]  value Source value.
    @param[in]  max_length Maximum string length before truncation.
    @return     Sanitized summary value.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    if isinstance(value, dict):
        return f"dict(keys={list(value.keys())[:12]})"
    if isinstance(value, list):
        return f"list(len={len(value)})"
    if isinstance(value, tuple):
        return f"tuple(len={len(value)})"
    if isinstance(value, set):
        return f"set(len={len(value)})"

    text = repr(value)
    if len(text) > max_length:
        return f"{text[:max_length]}...<truncated>"
    return text


def _collect_parameters(
    function: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """
    @brief      Build a compact argument map for traced function logging.
    @param[in]  function Wrapped function.
    @param[in]  args Positional call arguments.
    @param[in]  kwargs Keyword call arguments.
    @return     Parameter-name to compact representation map.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    try:
        bound_arguments = signature(function).bind_partial(*args, **kwargs)
        return {name: _safe_value(value) for name, value in bound_arguments.arguments.items()}
    except Exception:
        return {
            "args": _safe_value(args),
            "kwargs": _safe_value(kwargs),
        }


def _resolve_component_level(component_name: str, level_name: str | None) -> int:
    """
    @brief      Resolve the effective log level for one component logger.
    @param[in]  component_name Stable component logger identifier.
    @param[in]  level_name Explicit caller-supplied level override.
    @return     Effective numeric log level for the component.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    component_override = config.DEFAULT_LOG_LEVEL_OVERRIDES.get(component_name)
    return _resolve_level(level_name or component_override or config.DEFAULT_LOG_LEVEL)


def _log_directory_path() -> Path:
    """
    @brief      Build the application log directory path.
    @details    Logs follow the resolved writable data root, not the packaged
                application root, so a read-only installation folder cannot make
                logging impossible.
    @return     Absolute application log directory path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.2.0
    """
    return config.APP_USER_DATA_ROOT / config.APP_LOG_DIRECTORY_NAME


def _build_log_file_path(timestamp: datetime | None = None) -> Path:
    """
    @brief      Build the per-run application log file path.
    @param[in]  timestamp Optional run timestamp override.
    @return     Absolute log file path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    run_timestamp = timestamp or datetime.now()
    file_name = f"{config.APP_NAME}_{run_timestamp:%Y%m%d}_{run_timestamp:%H%M%S}.log"
    return _log_directory_path() / file_name


def _cleanup_old_log_files(current_log_file: Path) -> None:
    """
    @brief      Remove expired application log files from the log directory.
    @details    Retention is best-effort. An entry that cannot be listed,
                inspected, or removed is skipped, because failing to tidy old
                logs must never stop the current run from logging.
    @param[in]  current_log_file Active run log file that must be kept.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.2.0
    """
    retention_window = timedelta(days=max(config.DEFAULT_LOG_RETENTION_DAYS, 0))
    now = datetime.now()

    try:
        candidates = list(_log_directory_path().glob("*.log"))
    except OSError:
        return

    for candidate in candidates:
        if candidate == current_log_file:
            continue
        try:
            file_age = now - datetime.fromtimestamp(candidate.stat().st_mtime)
            if file_age > retention_window:
                candidate.unlink(missing_ok=True)
        except OSError:
            continue


# FORMATTERS


class _JsonFormatter(logging.Formatter):
    """
    @brief      JSON-lines formatter for machine-readable log records.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        @brief      Render a log record as a single JSON object line.
        @param[in]  record Logging record to serialize.
        @return     JSON string representation of the log record.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-04
        @version    0.1.0
        """
        payload = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "function": getattr(record, "func_name", record.funcName),
            "event": getattr(record, "event", "log"),
            "message": record.getMessage(),
        }
        if hasattr(record, "params"):
            payload["params"] = record.params
        if hasattr(record, "result"):
            payload["result"] = record.result
        if hasattr(record, "duration_ms"):
            payload["duration_ms"] = record.duration_ms
        return json.dumps(payload, ensure_ascii=True)


class _SafeTextFormatter(logging.Formatter):
    """
    @brief      Text formatter tolerant to missing custom logging fields.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        @brief      Render a text log line with default custom field values.
        @param[in]  record Logging record to render.
        @return     Formatted text log line.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-04
        @version    0.1.0
        """
        if not hasattr(record, "func_name"):
            record.func_name = record.funcName
        if not hasattr(record, "event"):
            record.event = "log"
        return super().format(record)


def _open_run_log_file(
    formatter: logging.Formatter,
) -> tuple[Path | None, logging.FileHandler | None, str]:
    """
    @brief      Create the per-run log file handler without propagating errors.
    @param[in]  formatter Formatter applied to the created handler.
    @return     Tuple of log file path, file handler, and failure reason. The
                path and handler are `None` when creation failed, in which case
                the reason names the path and the underlying error.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    log_directory = _log_directory_path()
    try:
        log_directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return None, None, f"log directory {log_directory} could not be created ({error})"

    log_file_path = _build_log_file_path()
    _cleanup_old_log_files(log_file_path)

    try:
        file_handler = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
    except OSError as error:
        return None, None, f"log file {log_file_path} could not be opened ({error})"

    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.NOTSET)
    return log_file_path, file_handler, ""


def _build_formatter() -> logging.Formatter:
    """
    @brief      Create the configured runtime log formatter.
    @return     Formatter instance matching the configured output mode.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    if _resolve_log_format() == "json":
        return _JsonFormatter()
    return _SafeTextFormatter(fmt=_TEXT_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")


# PUBLIC API


def initialize_logging() -> Path | None:
    """
    @brief      Initialize application logging for the current app run.
    @details    This runs before the bootstrap error handler, so it must never
                raise. The console handler is installed first so a diagnostic is
                always reachable; if the log file cannot be created the run
                continues with console output only.
    @return     Absolute path to the run log file, or `None` when logging
                degraded to console output only.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.2.0
    """
    formatter = _build_formatter()
    root_logger = logging.getLogger()

    shutdown_logging()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.NOTSET)

    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.NOTSET)

    log_file_path, file_handler, failure_reason = _open_run_log_file(formatter)
    if file_handler is None:
        root_logger.warning(
            f"Application logging degraded to console output only: {failure_reason}",
            extra={"func_name": "initialize_logging", "event": "logging-degraded"},
        )
        return None

    root_logger.addHandler(file_handler)
    return log_file_path


def shutdown_logging() -> None:
    """
    @brief      Flush and close all configured root logging handlers.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    root_logger = logging.getLogger()
    handlers = list(root_logger.handlers)
    for handler in handlers:
        handler.flush()
        handler.close()
        root_logger.removeHandler(handler)


def get_component_logger(
    component_name: str,
    level_name: str | None = None,
) -> logging.Logger:
    """
    @brief      Get a configured logger for one stable application component.
    @param[in]  component_name Stable component logger identifier.
    @param[in]  level_name Optional explicit per-call log-level override.
    @return     Configured logger instance for the requested component.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    logger = logging.getLogger(component_name)
    logger.setLevel(_resolve_component_level(component_name, level_name))
    logger.propagate = True
    return logger


def trace_function(logger: logging.Logger) -> Callable[[_CallableType], _CallableType]:
    """
    @brief      Create a decorator that traces function execution with logs.
    @param[in]  logger Component logger used for trace output.
    @return     Decorator that logs call start, end, duration, and exceptions.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """

    def _decorator(function: _CallableType) -> _CallableType:
        """
        @brief      Wrap one callable with trace logging.
        @param[in]  function Callable to be wrapped.
        @return     Wrapped callable with trace logging enabled.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-04
        @version    0.1.0
        """

        @wraps(function)
        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            """
            @brief      Execute the wrapped function and emit trace logs.
            @param[in]  args Positional call arguments.
            @param[in]  kwargs Keyword call arguments.
            @return     Original wrapped function result.
            @exception  Re-raises any exception raised by the wrapped function.
            @author     Eng. Dan Dumitru Pasare
            @date       2026-04-04
            @version    0.1.0
            """
            started_at = time.perf_counter()
            parameters = _collect_parameters(function, args, kwargs)
            logger.debug(
                "Function call started",
                extra={
                    "func_name": function.__name__,
                    "event": "start",
                    "params": parameters,
                },
            )

            try:
                result = function(*args, **kwargs)
            except Exception:
                elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 3)
                logger.exception(
                    "Function call failed",
                    extra={
                        "func_name": function.__name__,
                        "event": "exception",
                        "params": parameters,
                        "duration_ms": elapsed_ms,
                    },
                )
                raise

            elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 3)
            logger.debug(
                "Function call finished",
                extra={
                    "func_name": function.__name__,
                    "event": "finish",
                    "params": parameters,
                    "result": _safe_value(result),
                    "duration_ms": elapsed_ms,
                },
            )
            return result

        return _wrapped  # type: ignore[return-value]

    return _decorator


# END OF FILE
