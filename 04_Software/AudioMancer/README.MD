<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Application

This folder contains the initial Python application scaffold for `AudioMancer`.
It now includes a static main-window shell copied from
`DDP_Audiomancer` and adapted to the local package.

## Structure

- `pyproject.toml` defines the package metadata and dependencies.
- `settings.json` provides the current persisted app-settings scaffold.
- `src/audiomancer/` contains the Python package.
- `src/audiomancer/config.py` defines the current developer-owned defaults and file names.
- `src/audiomancer/services/logging_service.py` provides per-run app logging and optional trace helpers.
- `src/audiomancer/services/settings_service.py` provides load, validate, self-heal, and save behavior for `settings.json`.
- `src/audiomancer/services/ai_backend_service.py` provides backend probe and model-discovery helpers for AI provider profiles.
- `src/audiomancer/ui/` provides the copied toolbar, sidebar, page, and status-bar shell used by the first desktop window.
- the `Settings` dialog now loads and saves `language`, `interface text size`, and `play completion beep` through the shared settings service.
- saving `Settings` now applies the selected UI language and global text size to the running shell.
- the current shell supports runtime English/Romanian UI switching through one centralized UI-state service.
- the `AI Settings` dialog now loads and saves AI profiles plus the default cleanup, chunking, and character-extraction selections through the shared settings service.
- the `AI Settings` dialog now supports backend connection probing, discovered model refresh, and popup feedback with discovered-model counts.
- the static `Narrator` page now includes a presentational Qwen3-style profile manager with profile listing, custom-profile actions, voice-source selection, language selectors, voice-designer prompt fields, and a reserved preview panel.
- `LICENSE.txt`, `LICENSE_NC.txt`, `LICENSE_ro.txt`, and `LICENSE_NC_ro.txt` are stored in the app root so the About dialog can display English or Romanian license text and the delivered app keeps the license set at the app-root level.
- the About dialog now includes the main license text and the non-commercial addendum in a scrollable read-only text area, localized to the current UI language when a companion translation file exists.
- `tests/` contains focused automated tests for the scaffold.

## Environment Setup

This project uses `uv` for environment and dependency management.

Example workflow:

```powershell
uv sync --extra dev
```

## Run The Application

From this folder:

```powershell
uv run audiomancer
```

You can also run:

```powershell
uv run python -m audiomancer
```

## Runtime Logging

- Each app launch creates a new log file under `Logs/` in the app root.
- Log files use the pattern `AudioMancer_YYYYMMDD_HHMMSS.log`.
- Runtime logging writes to both the log file and stdout.
- Supported log output formats are `text` and `json`.
- Logging defaults and per-component overrides are currently defined in `src/audiomancer/config.py`.

## Settings Lifecycle

- The app settings file is stored at `settings.json` in the app root.
- Missing `settings.json` is created automatically from service-owned defaults.
- Persisted settings are validated and self-healed at startup.
- Updated settings can be saved back through the shared settings service from both `Settings` and `AI Settings`.
- Saved language and text-size changes are applied immediately to the running UI shell.
- Saved AI provider settings now include persisted connection-discovery state for each configured profile.

## Run Tests

From this folder:

```powershell
uv run pytest
```

## Packaging Placeholders

Packaging placeholders are stored under:

- `../../02_Tools/AudioMancer/build_windows.ps1`
- `../../02_Tools/AudioMancer/build_linux.sh`
- `../../02_Tools/AudioMancer/README.MD`

They define the intended future flow for `PyInstaller`-based builds and zip
packaging.
