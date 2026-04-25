<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer App Shell

## 1. Purpose

Defines the runnable desktop application shell for `AudioMancer`.

It hosts the project-aware main window, toolbar, sidebar navigation, workflow
pages, settings dialogs, runtime language switching, Home workflow progress,
and the current end-to-end workflow surfaces through Audio Assembly.

## 2. Responsibilities

- start the Qt application
- create and show the main window
- provide the operator-facing application shell
- create and open persisted project workspaces through the toolbar
- host Home workflow progress and export controls
- host current workflow pages from Text Cleanup through Audio Assembly
- apply runtime UI language and text-size changes

It initializes the shared settings and logging services at startup and shuts
down logging on exit. Domain processing remains owned by the service modules
and page controllers documented in their own component pages.

## 3. Implementation Overview

The initial shell consists of:

- `audiomancer.app.main()` as the thin startup entrypoint
- `audiomancer.services.settings_service` as the settings bootstrap
- `audiomancer.services.ai_backend_service` as the backend probe and model-discovery service for AI profiles
- `audiomancer.services.project_workspace_service` as the minimal project creation, validation, and loading service
- `audiomancer.services.home_presenter_service` as the Home workflow-progress
  and source-summary presenter
- `audiomancer.services.logging_service` as the per-run logging bootstrap
- `audiomancer.ui.main_window.MainWindow` as the first UI root
- copied sidebar, status-bar, and page widgets under `audiomancer.ui`
- a main window layout with toolbar, navigation sidebar, stacked workflow pages,
  and dialogs
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
- Home workflow-progress rows built from `project.json.current_stage` plus
  persisted operation summaries, so completed ready stages and unfinished
  downstream work are shown consistently
- real localized workflow pages for Speech Blocks, Audio Blocks, and Audio
  Assembly, including local playback surfaces for generated audio
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
- a project-aware workflow layout
- the ability to create or open one persisted project workspace
- a validated app settings payload loaded from `settings.json`
- persisted updates from both the `Settings` and `AI Settings` dialogs
- immediate runtime application of saved UI language and text-size changes
- Home-page workflow status and export readiness state
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
- `audiomancer.services.home_presenter_service.build_stage_statuses(...)`
- `audiomancer.ui.main_window.MainWindow`

## 7. Workflow Integration

This component is the top-level application entry boundary.

It hosts project activation, page navigation, workflow-page refresh, and the
Home summary surface. Long-running and domain-specific behavior is delegated to
page controllers and services such as Audio Blocks and Audio Assembly.

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
- Home presenter and Home page tests for workflow progress and exports

Minimum validation after changes:

- `python -m py_compile` for changed files
- focused `pytest` run for affected scaffold tests

## 10. Limitations And Future Work

- the shell coordinates workflow-page refreshes but does not own domain logic
- Home workflow status is intentionally summary-level; detailed operation state
  remains in workflow-specific report and state files
- Windows portable packaging now exists through `02_Tools/package_windows_release.ps1`
  and `02_Tools/audiomancer_windows.spec`
- logging configuration is still developer-owned through `config.py`
