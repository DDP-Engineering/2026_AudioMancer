<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer App Shell

## 1. Purpose

Defines the initial runnable desktop application shell for `AudioMancer`.
It provides the first executable boundary for the future application.

## 2. Responsibilities

- start the Qt application
- create and show the main window
- provide a minimal visible UI shell for validation

It does not yet own workflow orchestration or domain processing.
It now initializes the shared settings and logging services at startup and
shuts down logging on exit.

## 3. Implementation Overview

The initial shell consists of:

- `audiomancer.app.main()` as the thin startup entrypoint
- `audiomancer.services.settings_service` as the settings bootstrap
- `audiomancer.services.logging_service` as the per-run logging bootstrap
- `audiomancer.ui.main_window.MainWindow` as the first UI root
- a placeholder central label proving the desktop shell launches correctly

## 4. Dependencies

- Internal dependencies:
  `audiomancer.services.settings_service`
  `audiomancer.services.logging_service`
  `audiomancer.ui.main_window`
- External dependencies:
  `PySide6`

## 5. Inputs And Outputs

Inputs:

- process startup through `uv run audiomancer` or `python -m audiomancer`

Outputs:

- a running Qt application instance
- a visible main window for operator validation
- a validated app settings payload loaded from `settings.json`
- one new per-run application log file under `Logs/`
- process exit code from the Qt event loop

## 6. Data Contracts

There are no business-domain data contracts yet.

Current stable interface contracts are:

- `audiomancer.app.main() -> int`
- `audiomancer.services.logging_service.initialize_logging() -> Path`
- `audiomancer.services.logging_service.get_component_logger(...) -> logging.Logger`
- `audiomancer.services.logging_service.shutdown_logging() -> None`
- `audiomancer.services.logging_service.trace_function(logger)`
- `audiomancer.ui.main_window.MainWindow`

## 7. Workflow Integration

This component is the current top-level application entry boundary.
It will later host or delegate to broader workflow modules as they are added.

## 8. Usage

From `04_Software/AudioMancer/`:

```powershell
uv run audiomancer
```

Or:

```powershell
uv run python -m audiomancer
```

## 9. Validation And Tests

Current automated checks:

- package import smoke test
- main-window Qt test
- app bootstrap smoke test with lightweight fakes
- logging service unit tests

Minimum validation after changes:

- `python -m py_compile` for changed files
- focused `pytest` run for affected scaffold tests

## 10. Limitations And Future Work

- no workflow UI exists yet
- no project persistence exists yet
- no packaging spec exists yet
- logging configuration is still developer-owned through `config.py`
