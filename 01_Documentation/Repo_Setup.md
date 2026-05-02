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

Current repository structure:

- `0_Planning/`
- `01_Documentation/`
- `02_Tools/`
- `04_Software/`
- `05_SoftwareDocu/`
- `07_Delivery/`
- `09_Others/`

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
- `GitHub CLI` (`gh`) when creating GitHub releases, uploading delivery
  archives, or managing repository publishing from the command line

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

## 3. Install GitHub CLI For Publishing

GitHub CLI is only required for repository publishing and release management.
Normal local development, testing, and packaging do not require it.

Use `gh` when you need to:

- authenticate this machine with GitHub
- create or manage GitHub releases
- upload large executable delivery archives as release assets
- manage repository settings and automation from the command line

Do not commit executable delivery archives directly into the Git repository.
GitHub release assets are the preferred location for packaged binaries such as
`07_Delivery/AudioMancer_Windows_x64.zip`.

### Windows PowerShell

```powershell
winget install --id GitHub.cli
gh auth login
gh auth status
```

### Windows CMD

```cmd
winget install --id GitHub.cli
gh auth login
gh auth status
```

### Linux Bash

Install through the approved package source for the target distribution, then
authenticate:

```bash
gh auth login
gh auth status
```

For restricted or corporate environments, use the package source already
approved for the organization.

## 4. Go To The Application Folder

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

## 5. Create And Sync The Environment

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
- `ruff`

## 6. Run The Application

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

## 7. Run Tests

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

## 8. Useful Validation Commands

### Windows PowerShell

```powershell
uv run python -m py_compile src/audiomancer/app.py
uv run ruff check src/audiomancer/app.py tests/test_app_entrypoint.py --fix
uv run ruff format src/audiomancer/app.py tests/test_app_entrypoint.py
```

### Windows CMD

```cmd
uv run python -m py_compile src\audiomancer\app.py
uv run ruff check src\audiomancer\app.py tests\test_app_entrypoint.py --fix
uv run ruff format src\audiomancer\app.py tests\test_app_entrypoint.py
```

### Linux Bash

```bash
uv run python -m py_compile src/audiomancer/app.py
uv run ruff check src/audiomancer/app.py tests/test_app_entrypoint.py --fix
uv run ruff format src/audiomancer/app.py tests/test_app_entrypoint.py
```

## Notes

- The project currently uses `uv` as the environment and dependency workflow.
- `ruff` is installed through the same `uv sync --extra dev` path as the other developer tools.
- The runnable desktop application lives under `04_Software/AudioMancer/`.
- Windows packaging scripts and spec files live directly under `02_Tools/`.
- `07_Delivery/` is used for packaged release artifacts.
- Windows release packaging is implemented with `PyInstaller`.
- GitHub CLI is used for publishing workflows such as release creation and
  uploading packaged executable archives to GitHub releases.
- Linux packaging has a reserved helper script under `02_Tools/`, but it is not
  fully implemented yet.
