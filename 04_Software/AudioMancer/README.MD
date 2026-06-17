<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Application

This folder contains the Python 3.12/PySide6 desktop application package for
AudioMancer.

Component behavior, service contracts, persistence formats, UI workflows, and
runtime architecture are documented under `../../05_SoftwareDocu/`. Keep this
README focused on local setup, execution, validation, and packaging entry
points.

## Layout

- `pyproject.toml` - package metadata, dependencies, tooling configuration, and
  the `audiomancer` console entry point.
- `src/audiomancer/__init__.py` - package release metadata exposed to the app
  shell and import tests.
- `uv.lock` - locked development environment.
- `settings.example.json` - committed app-root settings scaffold. Copy it to
  `settings.json` and fill in operator-local endpoints and API keys.
- `settings.json` - operator-local settings; gitignored and never committed.
  API-key fields must remain blank in any committed example scaffold.
- `src/audiomancer/` - application package.
- `src/audiomancer/assets/` - packaged static assets such as the application
  icon.
- `prompts/` - prompt templates loaded by AI-assisted workflows.
- `tests/` - focused service, UI, and workflow regression tests.

## Component Documentation

Use `../../05_SoftwareDocu/README.md` as the component-documentation index.

Common entry points:

- `../../05_SoftwareDocu/AudioMancer_App_Shell.md`
- `../../05_SoftwareDocu/AudioMancer_Project_Workspace.md`
- `../../05_SoftwareDocu/AudioMancer_Config_And_Settings.md`
- `../../05_SoftwareDocu/AudioMancer_Speech_Blocks_Service.md`
- `../../05_SoftwareDocu/AudioMancer_Audio_Blocks_Service.md`
- `../../05_SoftwareDocu/AudioMancer_Audio_Blocks_State_Service.md`
- `../../05_SoftwareDocu/AudioMancer_Audio_Assembly_Service.md`
- `../../05_SoftwareDocu/AudioMancer_Workflow_Impact_Service.md`

Offline operator help is maintained in:

- `../../05_SoftwareDocu/UserGuide/`
- `../../05_SoftwareDocu/UserGuide_ro/`

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
- `../../02_Tools/package_linux_release.sh`
- `../../02_Tools/audiomancer_windows.spec`

Delivery archives are staged under `../../07_Delivery/` and published through
the project release flow. Generated archives must not be committed.

## Documentation Review Notes

Reviewed for the AI chunking context mode feature. When changing AI Settings or AI chunking behavior, include the focused settings, translation-catalog, settings-page, chunking-service, and text-chunking controller tests in validation.

Reviewed for the 1.5.9 release sync. Keep the package metadata, lockfile,
`audiomancer.__version__`, version smoke test, and offline help bundle versions
aligned for release bookkeeping.
