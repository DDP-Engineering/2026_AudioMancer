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
The shell now exposes a main window copied from `DDP_Audiomancer` and adapted
to the local package structure, including the first project new/open workflow.

## 2. Responsibilities

- start the Qt application
- create and show the main window
- provide the copied first visible operator-facing UI shell for validation
- create and open minimal persisted project workspaces through the toolbar

It does not yet own workflow orchestration or domain processing beyond project
workspace activation. It now initializes the shared settings and logging
services at startup and shuts down logging on exit.

## 3. Implementation Overview

The initial shell consists of:

- `audiomancer.app.main()` as the thin startup entrypoint
- `audiomancer.services.settings_service` as the settings bootstrap
- `audiomancer.services.ai_backend_service` as the backend probe and model-discovery service for AI profiles
- `audiomancer.services.project_workspace_service` as the minimal project creation, validation, and loading service
- `audiomancer.services.logging_service` as the per-run logging bootstrap
- `audiomancer.ui.main_window.MainWindow` as the first UI root
- copied sidebar, status-bar, and page widgets under `audiomancer.ui`
- a static DDP_Audiomancer-style main window layout with toolbar, navigation
  sidebar, stacked pages, and dialogs
- toolbar-driven `New Project` and `Open Project` actions that activate the
  first persisted project workflow
- a settings dialog that loads and saves the persisted language, text-size,
  and completion-beep controls through the shared settings service
- a runtime UI-state service that applies persisted language and text-size
  changes to the running Qt shell after startup and after `Save Settings`
- an AI settings dialog that loads and saves AI profiles plus default cleanup,
  chunking, and character-extraction selections through the shared settings
  service
- functional AI Settings connect flow with backend probing, discovered model
  refresh, and popup result feedback
- a project-aware narrator-definition page with seeded editable Qwen3 preset
  profiles, destructive edit confirmations, explicit create/edit/save/delete
  actions, runtime-backed sample generation, read-only project-language
  display, and local WAV preview playback
- an About dialog with scrollable AGPL license text and the non-commercial
  addendum, localized to the current UI language when localized companion
  files are available
- app-root `LICENSE.txt`, `LICENSE_NC.txt`, `LICENSE_ro.txt`, and
  `LICENSE_NC_ro.txt` files used for the About dialog and intended delivery
  layout

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
- a first-window layout that matches the source DDP_Audiomancer shell
- the ability to create or open one minimal persisted project workspace
- a validated app settings payload loaded from `settings.json`
- persisted updates from both the `Settings` and `AI Settings` dialogs
- immediate runtime application of saved UI language and text-size changes
- one new per-run application log file under `Logs/`
- process exit code from the Qt event loop

## 6. Data Contracts

Current stable interface contracts are:

- `audiomancer.app.main() -> int`
- `audiomancer.services.logging_service.initialize_logging() -> Path`
- `audiomancer.services.logging_service.get_component_logger(...) -> logging.Logger`
- `audiomancer.services.logging_service.shutdown_logging() -> None`
- `audiomancer.services.logging_service.trace_function(logger)`
- `audiomancer.services.project_workspace_service.create_project(...)`
- `audiomancer.services.project_workspace_service.open_project(...)`
- `audiomancer.ui.main_window.MainWindow`

## 7. Workflow Integration

This component is the current top-level application entry boundary.
It now hosts project activation and will later host or delegate to broader
workflow modules as they are added.

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

- downstream workflow pages remain largely presentational after project open
- project persistence currently uses a minimal manifest contract only
- Windows portable packaging now exists through `02_Tools/package_windows_release.ps1`
  and `02_Tools/audiomancer_windows.spec`
- logging configuration is still developer-owned through `config.py`
