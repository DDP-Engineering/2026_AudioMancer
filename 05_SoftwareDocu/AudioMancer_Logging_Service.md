<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Logging Service

## 1. Purpose

Provides the shared runtime logging implementation for the `AudioMancer`
desktop application.

It gives the app one consistent logging setup for the full runtime session,
including per-run log file creation, per-component loggers, text or JSON
serialization, and optional function tracing.

## 2. Responsibilities

- initialize root logging once at app startup
- create a new run-specific log file under `Logs/`
- mirror log output to both the log file and stdout
- apply the default log level and per-component overrides from
  `audiomancer.config`
- clean up expired older log files based on retention days
- provide a reusable component logger accessor
- provide an optional decorator for function start, finish, duration, and
  exception tracing
- close and remove handlers cleanly when the application exits

It does not own settings persistence, operator-editable log configuration, or
project-local AI exchange logging.

## 3. Implementation Overview

The component is implemented in:

- `src/audiomancer/services/logging_service.py`

Main public functions:

- `initialize_logging()`
- `get_component_logger(component_name, level_name=None)`
- `shutdown_logging()`
- `trace_function(logger)`

High-level flow:

1. `audiomancer.app.main()` calls `initialize_logging()` before creating the
   Qt application.
2. The service creates `APP_ROOT / Logs` if needed.
3. A new file name is generated as
   `<APP_NAME>_<YYYYMMDD>_<HHMMSS>.log`.
4. Older `.log` files in the same directory are deleted when they exceed the
   configured retention window.
5. The root logger is rebuilt from scratch for the current run, with one file
   handler and one stdout handler.
6. Components request named loggers through `get_component_logger(...)`.
7. On application shutdown or bootstrap failure, `shutdown_logging()` flushes
   and closes all handlers.

Formatting behavior:

- `text` mode uses a readable line-based formatter with timestamp, level,
  component, function, event, and message
- `json` mode uses one JSON object per line with stable keys

Decorator tracing behavior:

- `trace_function(logger)` wraps a callable
- start and finish records are logged at `DEBUG`
- exception records are logged at `ERROR`
- parameters and results are compacted before logging
- long scalar values are truncated
- container values are summarized instead of dumped fully

## 4. Dependencies

- Internal dependencies:
  `audiomancer.config`, `audiomancer.app`, and any module that requests a
  component logger
- External dependencies:
  Python standard library only: `logging`, `json`, `pathlib`, `datetime`,
  `inspect`, `functools`, `sys`, and `time`

## 5. Inputs And Outputs

Inputs:

- logging defaults from `src/audiomancer/config.py`
- component logger names such as `app` and `main_window`
- optional explicit per-call log-level override in `get_component_logger(...)`
- optional wrapped function arguments when decorator tracing is used

Outputs:

- one new runtime log file per app launch under
  `04_Software/AudioMancer/Logs/`
- mirrored stdout log output during runtime
- structured JSON lines or formatted text lines depending on configuration
- cleaned-up old log files when retention rules apply

## 6. Data Contracts

Relevant configuration contract in `audiomancer.config`:

- `APP_ROOT`
- `APP_NAME`
- `APP_LOG_DIRECTORY_NAME`
- `DEFAULT_LOG_FORMAT`
- `LOG_FORMAT_OPTIONS`
- `DEFAULT_LOG_LEVEL`
- `DEFAULT_LOG_LEVEL_OVERRIDES`
- `LOG_LEVEL_OPTIONS`
- `DEFAULT_LOG_RETENTION_DAYS`
- `AVAILABLE_LOG_COMPONENTS`

Current log file contract:

- directory: `APP_ROOT / APP_LOG_DIRECTORY_NAME`
- file pattern: `<APP_NAME>_<YYYYMMDD>_<HHMMSS>.log`
- extension: `.log`

Current JSON log record fields:

- `timestamp`
- `level`
- `component`
- `function`
- `event`
- `message`

Optional JSON fields:

- `params`
- `result`
- `duration_ms`

Deterministic behavior assumptions:

- each app launch creates a fresh log file
- logging does not append to a previous run file
- invalid log format values fall back to `text`
- invalid log level values fall back to `DEFAULT_LOG_LEVEL`

## 7. Workflow Integration

This component sits at the top of the runtime application lifecycle.

Upstream:

- application startup in `audiomancer.app.main()`

Downstream:

- all application modules that need named component loggers
- optional service/helper functions that use decorator tracing

Current in-repo usage:

- `audiomancer.app` logs bootstrap startup, shutdown, and fatal startup errors
- `audiomancer.ui.main_window` logs shell construction and routed workflow
  operations
- principal workflow services such as AI cleanup, AI chunking, AI translation,
  character discovery, Speech Blocks, Audio Blocks, Audio Assembly,
  VoiceWeaver runtime, project export/snapshot, source import, prompt
  templates, AI backend probing, and settings use named component loggers or
  `trace_function(...)`

## 8. Usage

Startup integration:

```python
from audiomancer.services.logging_service import (
    get_component_logger,
    initialize_logging,
    shutdown_logging,
)

log_file_path = initialize_logging()
logger = get_component_logger("app")
logger.info("Application started")
```

Decorator usage:

```python
from audiomancer.services.logging_service import get_component_logger, trace_function

logger = get_component_logger("app", "DEBUG")

@trace_function(logger)
def build_payload(items: list[str]) -> dict[str, int]:
    return {"count": len(items)}
```

Required configuration:

- no environment variables are required
- current runtime behavior is developer-owned through `config.py`

## 9. Validation And Tests

Automated tests:

- `tests/test_logging_service.py`
- `tests/test_app_entrypoint.py`

Covered behaviors:

- run log file creation
- retention cleanup of expired log files
- text and JSON formatter selection
- component-level log override handling
- trace decorator start, finish, duration, exception, and truncation behavior
- bootstrap integration and shutdown handling

Minimum validation after a change:

- `python -m py_compile` for changed Python files
- focused `pytest` run for logging service and bootstrap tests

## 10. Limitations And Future Work

- logging configuration is not yet loaded from `settings.json`
- component identifiers are guided by config constants, but not currently
  enforced strictly
- log cleanup is age-based only and does not enforce file-count limits
- trace logging is synchronous and intentionally simple
- no redaction policy exists yet for sensitive payload fields beyond compact
  summarization and truncation

Documentation audit status: reviewed against the current implementation on
2026-05-06.
