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
- VoiceWeaver generation diagnostics, including Scene Ambience sound-prompt
  requests and Audio Blocks checkpoints, are written through the shared runtime
  log.
- Project workflow artifacts are written inside the selected project root.
- Text chunking writes chunk artifacts, reports, and operation state atomically;
  cancelled or failed chunking runs keep resumable terminal state.
- AI Translation writes translated chunks, reports, and operation state
  atomically; unchanged page-state builds are read-only, and interrupted runs
  persist terminal cancel/failure state.
- Narrator voice preparation writes profile metadata and sample artifacts
  atomically, preserves previous samples when new VoiceWeaver generation fails
  or is cancelled, and records terminal cancel/failure state for interrupted AI
  narrator-profile generation.
- Generated Audio Blocks media is written under each project `audio_blocks/`
  folder, including generated Scene Ambience prompt audio when that path is
  enabled.
- Final Audio Assembly outputs are written under each project `audiobook/`
  folder; assembly settings decide whether generated Scene Ambience blocks are
  included in the final sequential output.

Detailed artifact contracts belong in `../../05_SoftwareDocu/`.

## Packaging

Packaging automation lives outside this application package:

- `../../02_Tools/package_windows_release.ps1`
- `../../02_Tools/package_linux_release.sh`
- `../../02_Tools/audiomancer_windows.spec`

Delivery archives are staged under `../../07_Delivery/` and published through
the project release flow. Generated archives must not be committed.
