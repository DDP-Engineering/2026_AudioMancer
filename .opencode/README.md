<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# OpenCode Adapter

This directory adapts OpenCode to the shared agentic workflow template.
The workflow engine remains under `.agentic/`: CLI, hooks, requirements,
documents, and platform-neutral skills.

## Usage

Start OpenCode from the repository root so it can find:

- `opencode.json`
- `AGENTS.md`
- `.opencode/agents/`
- `.opencode/skills/`
- `.opencode/commands/`
- `.opencode/plugins/`

`opencode.json` sets `default_agent` to `agentic-workflow`, so the TUI and
plain `opencode run` start with the primary agent that loads the shared
development workflow before behavior-changing work.

OpenCode discovers skills through its native `skill` tool. The workflow agent
loads `agentic-development` before feature, bug fix, behavior-change, planned
test, or active-run continuation work. Other shared skills are available by
name:

```text
agentic-development
agentic-adoption
agentic-delivery
regression-traceability
documentation-audit
python-codestyle-audit
write-component-documentation
```

The workflow command placeholder `<workflow>` still means the project-local
runner:

```powershell
.\.agentic\tools\run.ps1 <command>
```

```bash
bash .agentic/tools/run.sh <command>
```

OpenCode command shortcuts are available from the TUI:

```text
/workflow-status
/workflow-preflight
/workflow-report
```

The same commands can be run from the CLI:

```powershell
opencode run --command workflow-status
opencode run --command workflow-preflight
opencode run --command workflow-report
```

## Guard Plugin

`.opencode/plugins/agentic-guard.mjs` is loaded by OpenCode at startup. It maps
OpenCode tool events onto the shared `.agentic/hooks/` Python scripts:

- edit/write/patch operations run `guard_write_zone.py`, then
  `secret_scan.py`;
- bash commands run `secret_scan.py`, then `delivery_preflight.py`;
- reads of protected secret/key paths are blocked natively;
- post-tool events run `post_tool_evidence.py`.

Set `AGENTIC_WORKFLOW_PYTHON` if OpenCode cannot find the desired Python
interpreter. Python 3.11 or newer is required by the workflow CLI and hooks.

Delivery actions such as push, merge, publish, and PR creation still require a
passing delivery preflight and explicit human approval.
