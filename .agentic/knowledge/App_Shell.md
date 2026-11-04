<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# App Shell

## Routing

For application startup, shared dialogs, page registration or window shutdown, start at `app.main`, `MainWindow` and `tests/test_main_window_lifecycle.py`. AI Runtime owns the account controller hosted by the AI Settings dialog.

## Purpose and boundaries

The App Shell starts the PySide6 desktop application and composes the shared
window frame in which all AudioMancer workflow components run.

- Expose the package version and `audiomancer` / `python -m audiomancer` entry points.
- Initialize logging, settings, scroll filtering, application-wide theme, and the application icon before constructing the main window, tolerating logging that degraded to console output only.
- Compose the toolbar, left navigation sidebar, pages, dialogs, project summaries, and lifecycle cleanup in `MainWindow`.
- Offer each workflow page's operation status through one modeless dialog opened from a button under the sidebar, enabled only once that page's operation has a recorded run status.
- Provide shared user-facing help, about/license, message, progress, and title helpers.
- Reapply the active locale to app-owned persistent surfaces and rebuild the
  current project page when runtime language settings change.

The component coordinates page integration; it does not own the behavior,
state, or persistence contracts of individual workflow domains.

### Dependencies

Internal dependencies are configuration, settings, logging, UI state/theme and
scroll services, page/controller modules, and operation/audio lifecycle
services. External dependencies are PySide6 and the host desktop event loop.

## Public interface

Home's `project_options_change_requested` signal routes deliberate language or
narration selections to Project Lifecycle's confirmed persistence handler.
Programmatic state refresh does not request changes. New Project activates only
a published source-ready project; opening existing projects displays saved options.

Inputs are persisted settings, translated resource files, user navigation and
dialog actions, and project summaries emitted by domain components. Outputs are
the visible window, active page selection, themed Qt state, dialogs, status
messages, help/about content, and a process exit code. The toolbar also emits
New Project/Open Project and Settings/AI Settings/TTS Settings requests; project
activation updates the Home summary and each page's active-project state.

Launch with `uv run audiomancer` or `python -m audiomancer`. Use the toolbar to
create/open a project or open a settings dialog; the shell routes those actions
to the owning controllers. Domain code uses `MainWindow` navigation and refresh
hooks rather than recreating application or dialog infrastructure.

## Invariants

Account sign-in/model-test workers keep their own AI Runtime cancellation
lifecycle. Project workflow workers use Operation Orchestration's shutdown and
cancellation contracts.

The package API exports `__version__` and `main`. Page identifiers must match
the sidebar and stacked-page registration. Theme is applied before widgets are
constructed at startup; page refreshes are limited to the current workflow page
to avoid unrelated state work, including after a runtime language change.
`show_project_state()` refreshes the project summary, the current page and the
operation-status control together, and its summary half rereads every Home
export artifact. A controller that changed nothing outside its own page uses a
narrower page-scoped entry point instead: `refresh_current_page_state()`
refreshes whichever workflow page is visible, and `refresh_audio_assembly_page_state()`
refreshes only that one page (`REQ-NFR-aed66768`, `REQ-NFR-dfe9ab8a`). Saving AI
Settings uses `refresh_current_page_state()` and does not reapply the
application-wide theme, font, or language, because AI Settings owns no such
setting - only the general Settings dialog does, and only it calls
`apply_current_ui_settings()`.
App-owned dialog text comes from the same English/Romanian catalog as persistent
page text. Shared confirmations retain the caller's window as parent, translate
the exact caller-provided title and message keys, expose Yes and No, default to
No, and return true only for Yes. `initialize_logging()` returns `Path | None`, and
`None` means logging degraded to console output only rather than that startup
failed.

### Operational limits

`MainWindow` is necessarily a broad integration seam. Changes that alter a
domain page's lifecycle, state, or persistence behavior require corresponding
work in the owning component as well.

## Change map

| Change requested | Start with | Focused verification |
| --- | --- | --- |
| Startup and page composition | app.main, MainWindow | test_app_entrypoint.py, test_main_window_lifecycle.py |
| Account job shutdown | MainWindow.closeEvent | test_chatgpt_ui.py, test_main_window_operation_shutdown.py |

## Key behaviors

- `REQ-UX-3d0aeaec`: MainWindow owns ChatGPTAuthUiController for the static AI Settings dialog and asks it to cancel/finish before deleting widgets. A worker that exceeds the close budget keeps the window alive.
- `REQ-UX-3e905eaa`: The AI Settings dialog hosts its page directly. The page owns body scrolling so Cancel, Apply and OK remain outside the scroll area; other settings dialogs retain their existing page wrappers.

### Implementation behavior

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
toolbar and settings dialogs. The sidebar shares a column wrapper with the
operation-status button: the sidebar is itself the `QListWidget` whose rows are
the workflow pages, so a non-page control cannot live inside it without posing
as an eleventh page and escaping the page-enablement loop. `PAGE_OPERATION_KIND`
maps each page to the workflow operation whose persisted status drives that
button, and the button and any open dialog refresh from the same current-page
path as the page state itself. It routes selection to a current page, refreshes
only that page's derived state, applies language/theme changes, and stops
active audio playback when it closes. `misc_ui_controller` resolves localized
help and license resources, builds common dialogs, and owns the exact localized
Yes-or-No/default-No question construction used by behavior-equivalent
controller confirmations (`REQ-NFR-0eae9411`); packaged icons supply the window
identity. Composite, pretranslated, formatted, and different-default dialogs
remain with their owning controllers.

Settings application first reapplies theme and catalog-backed captions to the
shell and all persistent pages. If a project is open, the shell then invokes
its current-page refresh path with the new language, rebuilding derived notes
and rows without eagerly loading every hidden workflow page. Common popup and
operation-progress text is supplied already translated by the owning
controller. English user-facing navigation and settings use the correctly
spelled Narrator label while stable internal identifiers remain unchanged
(`REQ-UX-a6c3e152`).

### Workflow integration

This is the integration seam for project lifecycle, settings, AI, text, voice,
speech, TTS, and assembly components. Domain pages are constructed here but
retain ownership of their own service contracts and state transitions.



## Files

- `05_Software/AudioMancer/pyproject.toml`
- `05_Software/AudioMancer/src/audiomancer/__init__.py`
- `05_Software/AudioMancer/src/audiomancer/__main__.py`
- `05_Software/AudioMancer/src/audiomancer/app.py`
- `05_Software/AudioMancer/src/audiomancer/assets/**`
- `05_Software/AudioMancer/src/audiomancer/services/__init__.py`
- `05_Software/AudioMancer/src/audiomancer/ui/__init__.py`
- `05_Software/AudioMancer/src/audiomancer/ui/main_window.py`
- `05_Software/AudioMancer/src/audiomancer/ui/navigation_sidebar.py`
- `05_Software/AudioMancer/src/audiomancer/ui/operation_status_dialog.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/__init__.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/misc_ui_controller.py`
- `05_Software/AudioMancer/src/audiomancer/ui/pages/__init__.py`
- `05_Software/AudioMancer/tests/conftest.py`
- `05_Software/AudioMancer/tests/test_app_entrypoint.py`
- `05_Software/AudioMancer/tests/test_main_window_lifecycle.py`
- `05_Software/AudioMancer/tests/test_package_import.py`
- `05_Software/AudioMancer/tests/test_ui_localization_coverage.py`

### Focused verification

Primary automated coverage:

- `tests/test_app_entrypoint.py`
- `tests/test_main_window_lifecycle.py`
- `tests/test_package_import.py`
- `tests/test_ui_localization_coverage.py`

Minimum validation after a change: run the focused modules above with
`uv run pytest`, plus `uv run python -m py_compile` and `uv run ruff check` on
changed files.
