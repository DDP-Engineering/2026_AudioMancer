<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
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

## Access Mode

Workflow runs start in `standard` access mode. In this mode, the write-zone
guard limits edits to the configured paths for the current stage.

Use `repo-wide` access only for human-approved broad maintenance tasks that need
normal edits across multiple repository folders:

```powershell
.\.agentic\tools\run.ps1 set-access-mode repo-wide --reason "Human-approved broad maintenance"
```

`repo-wide` access still blocks protected Git, secret, environment, and key
files. It does not override the host tool's outer filesystem permissions.
