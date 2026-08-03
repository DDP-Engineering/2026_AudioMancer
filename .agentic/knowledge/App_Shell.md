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
- Initialize logging, settings, scroll filtering, application-wide theme, and the application icon before constructing the main window, tolerating logging that degraded to console output only.
- Compose the toolbar, left navigation sidebar, pages, dialogs, project summaries, and lifecycle cleanup in `MainWindow`.
- Provide shared user-facing help, about/license, message, progress, and title helpers.
- Reapply the active locale to app-owned persistent surfaces and rebuild the
  current project page when runtime language settings change.

The component coordinates page integration; it does not own the behavior,
state, or persistence contracts of individual workflow domains.

## 3. Implementation Overview

`app.main` loads settings, creates `QApplication`, applies the persisted theme,
installs global scrolling, shows `MainWindow`, and always shuts down logging.
`__main__.py` delegates module invocation to that entry point, while
`__init__.py` exposes `main` and the release version.

`initialize_logging()` runs before the bootstrap `try/except` and therefore never
raises: when the log file cannot be created it installs a console-only root
logger and returns `None`, and `main` reports the log file as unavailable instead
of aborting. This is what keeps a read-only installation directory from crashing
startup with no diagnostic. See `.agentic/specs/user_data_location.spec.md`.

`MainWindow` creates the fixed left `NavigationSidebar`, page stack, shared
toolbar and settings dialogs. It routes selection to a current page, refreshes
only that page's derived state, applies language/theme changes, and stops
active audio playback when it closes. `misc_ui_controller` resolves localized
help and license resources and builds common dialogs; packaged icons supply the
window identity.

Settings application first reapplies theme and catalog-backed captions to the
shell and all persistent pages. If a project is open, the shell then invokes
its current-page refresh path with the new language, rebuilding derived notes
and rows without eagerly loading every hidden workflow page. Common popup and
operation-progress text is supplied already translated by the owning
controller.

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
to avoid unrelated state work, including after a runtime language change.
App-owned dialog text comes from the same English/Romanian catalog as persistent
page text. `initialize_logging()` returns `Path | None`, and
`None` means logging degraded to console output only rather than that startup
failed.

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
- `tests/test_ui_localization_coverage.py`

Minimum validation after a change: run the focused modules above with
`uv run pytest`, plus `uv run python -m py_compile` and `uv run ruff check` on
changed files.

## 10. Limitations And Future Work

`MainWindow` is necessarily a broad integration seam. Changes that alter a
domain page's lifecycle, state, or persistence behavior require corresponding
work in the owning component as well.

## Files

From the adopted component map:

- `04_Software/AudioMancer/pyproject.toml`
- `04_Software/AudioMancer/src/audiomancer/__init__.py`
- `04_Software/AudioMancer/src/audiomancer/__main__.py`
- `04_Software/AudioMancer/src/audiomancer/app.py`
- `04_Software/AudioMancer/src/audiomancer/assets/**`
- `04_Software/AudioMancer/src/audiomancer/services/__init__.py`
- `04_Software/AudioMancer/src/audiomancer/ui/__init__.py`
- `04_Software/AudioMancer/src/audiomancer/ui/main_window.py`
- `04_Software/AudioMancer/src/audiomancer/ui/navigation_sidebar.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/__init__.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/misc_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/__init__.py`
- `04_Software/AudioMancer/tests/conftest.py`
- `04_Software/AudioMancer/tests/test_app_entrypoint.py`
- `04_Software/AudioMancer/tests/test_main_window_lifecycle.py`
- `04_Software/AudioMancer/tests/test_package_import.py`
- `04_Software/AudioMancer/tests/test_ui_localization_coverage.py`
