<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# App Shell

## 1. Purpose

The App Shell starts the PySide6 desktop application and composes the shared
window frame in which all AudioMancer workflow components run.

## 2. Responsibilities

- Expose the package version and `audiomancer` / `python -m audiomancer` entry points.
- Initialize logging, settings, scroll filtering, application-wide theme, and the application icon before constructing the main window.
- Compose the toolbar, left navigation sidebar, pages, dialogs, project summaries, and lifecycle cleanup in `MainWindow`.
- Provide shared user-facing help, about/license, message, progress, and title helpers.

The component coordinates page integration; it does not own the behavior,
state, or persistence contracts of individual workflow domains.

## 3. Implementation Overview

`app.main` loads settings, creates `QApplication`, applies the persisted theme,
installs global scrolling, shows `MainWindow`, and always shuts down logging.
`__main__.py` delegates module invocation to that entry point, while
`__init__.py` exposes `main` and the release version.

`MainWindow` creates the fixed left `NavigationSidebar`, page stack, shared
toolbar and settings dialogs. It routes selection to a current page, refreshes
only that page's derived state, applies language/theme changes, and stops
active audio playback when it closes. `misc_ui_controller` resolves localized
help and license resources and builds common dialogs; packaged icons supply the
window identity.

## 4. Dependencies

Internal dependencies are configuration, settings, logging, UI state/theme and
scroll services, page/controller modules, and operation/audio lifecycle
services. External dependencies are PySide6 and the host desktop event loop.

## 5. Inputs And Outputs

Inputs are persisted settings, translated resource files, user navigation and
dialog actions, and project summaries emitted by domain components. Outputs are
the visible window, active page selection, themed Qt state, dialogs, status
messages, help/about content, and a process exit code. The toolbar also emits
New Project/Open Project and Settings/AI Settings/TTS Settings requests; project
activation updates the Home summary and each page's active-project state.

## 6. Data Contracts

The package API exports `__version__` and `main`. Page identifiers must match
the sidebar and stacked-page registration. Theme is applied before widgets are
constructed at startup; page refreshes are limited to the current workflow page
to avoid unrelated state work.

## 7. Workflow Integration

This is the integration seam for project lifecycle, settings, AI, text, voice,
speech, TTS, and assembly components. Domain pages are constructed here but
retain ownership of their own service contracts and state transitions.

## 8. Usage

Launch with `uv run audiomancer` or `python -m audiomancer`. Use the toolbar to
create/open a project or open a settings dialog; the shell routes those actions
to the owning controllers. Domain code uses `MainWindow` navigation and refresh
hooks rather than recreating application or dialog infrastructure.

## 9. Validation And Tests

Primary automated coverage:

- `tests/test_app_entrypoint.py`
- `tests/test_main_window_lifecycle.py`
- `tests/test_package_import.py`

Minimum validation after a change: run the focused modules above with
`uv run pytest`, plus `uv run python -m py_compile` and `uv run ruff check` on
changed files.

## 10. Limitations And Future Work

`MainWindow` is necessarily a broad integration seam. Changes that alter a
domain page's lifecycle, state, or persistence behavior require corresponding
work in the owning component as well.
