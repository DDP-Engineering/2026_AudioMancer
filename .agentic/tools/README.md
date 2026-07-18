<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Local Workflow Tools

These scripts make the bundled workflow CLI available in a copied project.

Run without installing into a virtual environment:

```powershell
.\.agentic\tools\run.ps1 --help
```

```bash
bash .agentic/tools/run.sh --help
```

Install into a project-local virtual environment:

```powershell
.\.agentic\tools\install.ps1
```

```bash
bash .agentic/tools/install.sh
```

The installer uses `uv` when available. Otherwise it falls back to Python's
standard `venv` and `pip` tooling. Python 3.11 or newer is required.
