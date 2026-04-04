<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Application

This folder contains the initial Python application scaffold for `AudioMancer`.

## Structure

- `pyproject.toml` defines the package metadata and dependencies.
- `settings.json` provides the current persisted app-settings scaffold.
- `src/audiomancer/` contains the Python package.
- `src/audiomancer/config.py` defines the current developer-owned defaults and file names.
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