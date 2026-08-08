<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Application

This folder contains the Python 3.12-3.13/PySide6 desktop application package
for AudioMancer.

Component behavior, service contracts, persistence formats, UI workflows, and
runtime architecture are documented in the knowledge base under
`../../.agentic/knowledge/`. Keep this README focused on local setup,
execution, validation, and packaging entry points.

## Layout

- `pyproject.toml` - package metadata, dependencies, tooling configuration, and
  the `audiomancer` console entry point.
- `uv.lock` - locked development environment.
- `settings.example.json` - committed app-root settings scaffold. Copy it to
  `settings.json` and fill in operator-local endpoints and API keys.
- `settings.json` - operator-local settings; gitignored and never committed.
  API-key fields must remain blank in any committed example scaffold.
- `LICENSE.txt`, `LICENSE_NC.txt` and their `_ro` counterparts - license texts
  shipped with the application.
- `src/audiomancer/__init__.py` - package release metadata (`__version__`)
  exposed to the app shell and import tests.
- `src/audiomancer/app.py`, `__main__.py` - application entry points.
- `src/audiomancer/config.py` - configuration contract and defaults.
- `src/audiomancer/services/` - service layer (import, extraction, cleanup,
  chunking, speech blocks, character and narrator voices, AI runtime and
  translation, TTS audio blocks, audio assembly, persistence, logging).
- `src/audiomancer/ui/` - main window, navigation sidebar, progress dialog,
  `pages/` and `controllers/`.
- `src/audiomancer/assets/icons/` - packaged application icons.
- `prompts/` - prompt templates loaded by AI-assisted workflows.
- `tests/` - focused service, UI, and workflow regression tests.
- `Logs/` - runtime logs written per launch; not committed.

## Component Documentation

Per-component implementation documentation lives in
`../../.agentic/knowledge/`, one page per component. Common entry points:

- `../../.agentic/knowledge/App_Shell.md`
- `../../.agentic/knowledge/Project_Lifecycle.md`
- `../../.agentic/knowledge/Platform_Settings_UI.md`
- `../../.agentic/knowledge/Text_Cleanup.md`
- `../../.agentic/knowledge/Text_Chunking.md`
- `../../.agentic/knowledge/Speech_Blocks.md`
- `../../.agentic/knowledge/TTS_Audio_Blocks.md`
- `../../.agentic/knowledge/Audio_Assembly.md`
- `../../.agentic/knowledge/AI_Runtime.md`
- `../../.agentic/knowledge/Operation_Orchestration.md`

`../../05_SoftwareDocu/README.md` indexes the operator-facing material:

- `../../05_SoftwareDocu/UserGuide/` - English offline help bundle.
- `../../05_SoftwareDocu/UserGuide_ro/` - Romanian offline help bundle.
- `../../05_SoftwareDocu/AudioMancer_OpenAI_Online_Model_Recommendations.md`
- `../../05_SoftwareDocu/AudioMancer_LMStudio_Local_Model_Recommendations.md`

## Environment Setup

Install the runtime and developer tools from this folder:

```powershell
uv sync --extra dev
```

## Run

Start the application:

```powershell
uv run audiomancer
```

Alternative module entry point:

```powershell
uv run python -m audiomancer
```

## Validate

Run the full local test suite:

```powershell
uv run pytest
```

Tests carry markers so you can scope a run: `service` (fast non-Qt logic),
`ui` (Qt widget, controller, and main-window), and `performance` (large-project
responsiveness). `performance` is excluded by default; opt in explicitly:

```powershell
uv run pytest -m performance
```

Run changed-file Python hygiene during normal feature work:

```powershell
uv run python -m py_compile <changed_file.py>
uv run ruff check <changed_python_files> --fix
uv run ruff format <changed_python_files>
```

Run focused tests for the area you changed before broad regression passes. The
broader validation baseline is tracked in `../../HowToTest.md`.

## Runtime Files

- Each app launch writes a log under `Logs/` in this folder.
- Project workflow artifacts are written inside the selected project root.
- Detailed artifact and workflow contracts belong in
  `../../05_SoftwareDocu/`.

## Packaging

Packaging automation lives outside this application package:

- `../../02_Tools/package_windows_release.ps1`
- `../../02_Tools/audiomancer_windows.spec`
- `../../02_Tools/audiomancer_windows_entry.py`
- `../../02_Tools/package_linux_release.sh`
- `../../02_Tools/validate_linux_delivery.sh`

Delivery archives are staged under `../../07_Delivery/` and published through
the project release flow. Generated archives must not be committed.

Releases must keep the package metadata, lockfile, `audiomancer.__version__`,
version smoke test, and offline help bundle versions aligned - see
`../../.agentic/PROJECT.md`, *Delivery - the version workflow*.
