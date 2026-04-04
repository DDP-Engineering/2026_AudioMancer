<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Repository Setup

## Purpose

This document describes the initial local setup for working on
`2026_AudioMancer`.

Current application subtree:

- `04_Software/AudioMancer/`

Current environment and dependency workflow:

- `Python 3.12`
- `uv`

## Prerequisites

Before syncing the project environment, make sure these are available:

- `Python 3.12`
- `git`
- internet access for the first dependency installation

## 1. Clone The Repository

### Windows PowerShell

```powershell
git clone <repo-url> 2026_AudioMancer
Set-Location 2026_AudioMancer
```

### Windows CMD

```cmd
git clone <repo-url> 2026_AudioMancer
cd 2026_AudioMancer
```

### Linux Bash

```bash
git clone <repo-url> 2026_AudioMancer
cd 2026_AudioMancer
```

## 2. Install uv

For restricted or corporate environments, prefer the method already approved in
your environment.

### Windows PowerShell

Direct installer script:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Package manager alternative:

```powershell
winget install --id=astral-sh.uv -e
```

Python/pip fallback:

```powershell
py -m pip install --user uv
```

Additional controlled-environment alternatives:

- use Chocolatey if it is the approved package manager in your environment
- use a company-approved internal package mirror or binary repository
- use a manually downloaded installer or binary if direct installation is restricted

Restart PowerShell after installation.

### Windows CMD

Direct installer script:

```cmd
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Package manager alternative:

```cmd
winget install --id=astral-sh.uv -e
```

Python/pip fallback:

```cmd
py -m pip install --user uv
```

Additional controlled-environment alternatives:

- use Chocolatey if it is the approved package manager in your environment
- use a company-approved internal package mirror or binary repository
- use a manually downloaded installer or binary if direct installation is restricted

Restart the terminal after installation.

### Linux Bash

Direct installer script:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Python/pip fallback:

```bash
python3 -m pip install --user uv
```

Manual or controlled-environment alternative:

- use a company-approved internal package mirror if one exists
- use a manually downloaded prebuilt `uv` binary if direct internet install is restricted
- use a distro package source only if your environment already provides an approved `uv` package

Restart the shell after installation, or load the shell profile if needed.

If `uv` is installed with `pip --user`, make sure the user scripts directory is
available on `PATH` before continuing.

## 3. Go To The Application Folder

### Windows PowerShell

```powershell
Set-Location 04_Software/AudioMancer
```

### Windows CMD

```cmd
cd 04_Software\AudioMancer
```

### Linux Bash

```bash
cd 04_Software/AudioMancer
```

## 4. Create And Sync The Environment

The current project setup uses the application `pyproject.toml` and installs the
runtime and development tools together through the `dev` extra.

### Windows PowerShell

```powershell
uv sync --extra dev
```

### Windows CMD

```cmd
uv sync --extra dev
```

### Linux Bash

```bash
uv sync --extra dev
```

This installs the currently declared dependencies, including:

- `PySide6`
- `PyMuPDF`
- `langdetect`
- `pytest`
- `pytest-qt`
- `PyInstaller`

## 5. Run The Application

### Windows PowerShell

```powershell
uv run audiomancer
```

### Windows CMD

```cmd
uv run audiomancer
```

### Linux Bash

```bash
uv run audiomancer
```

Alternative module form:

### Windows PowerShell

```powershell
uv run python -m audiomancer
```

### Windows CMD

```cmd
uv run python -m audiomancer
```

### Linux Bash

```bash
uv run python -m audiomancer
```

## 6. Run Tests

### Windows PowerShell

```powershell
uv run pytest
```

### Windows CMD

```cmd
uv run pytest
```

### Linux Bash

```bash
uv run pytest
```

## 7. Useful Validation Commands

### Windows PowerShell

```powershell
uv run python -m py_compile src/audiomancer/app.py
```

### Windows CMD

```cmd
uv run python -m py_compile src\audiomancer\app.py
```

### Linux Bash

```bash
uv run python -m py_compile src/audiomancer/app.py
```

## Notes

- The project currently uses `uv` as the environment and dependency workflow.
- The initial application scaffold is under `04_Software/AudioMancer/`.
- Packaging placeholders are under `02_Tools/AudioMancer/`.
- `PyInstaller` is declared as a dependency for future packaging work, but the
  release build flow is still a placeholder.
