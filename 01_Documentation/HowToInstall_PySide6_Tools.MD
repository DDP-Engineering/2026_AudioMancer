<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE and LICENSE_NC.txt files for full license details.
-->

# How To Install PySide6 Tools

## Purpose

This document explains how to install `PySide6` and the related Qt for Python
command-line tools used for UI development in `DDP_Audiomancer`.

The expected toolset includes:

- `pyside6-designer`
- `pyside6-uic`
- `pyside6-rcc`
- `pyside6-project`
- `pyside6-deploy`

In the standard installation flow, these tools are installed together with the
`pyside6` Python package.

## Recommended Approach

Use a dedicated Python virtual environment for the project or for UI
experiments. This keeps the Qt tooling isolated from the rest of the system.

## Windows Installation

### Command Prompt

```bat
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install pyside6
```

### PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install pyside6
```

## Linux Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install pyside6
```

## Verify The Installation

Run the following commands after activating the virtual environment:

```bash
pyside6-designer --help
pyside6-uic --help
pyside6-rcc --help
pyside6-project --help
pyside6-deploy --help
```

If the commands print help output, the tools are available.

## Launch Qt Designer

After installation, start the visual designer with:

```bash
pyside6-designer
```

This tool can be used to create `.ui` files for Qt Widgets interfaces.

## Generate Python Code From A `.ui` File

Convert a designer file into Python code with:

```bash
pyside6-uic input.ui -o ui_input.py
```

This is useful when the project chooses a generated-code workflow instead of
loading `.ui` files dynamically at runtime.

## Update The Tools

Inside the active virtual environment:

```bash
pip install --upgrade pyside6
```

## Notes

- `PySide6` is the recommended long-term UI toolkit for `DDP_Audiomancer`.
- The toolkit is suitable for both Windows and Linux desktop deployment.
- Use the `pyside6-*` wrapper commands instead of generic Qt command names.
- For reproducible project work, prefer a project-local virtual environment.
