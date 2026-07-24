<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# OpenCode Adapter

This directory adapts OpenCode to AEGIS.
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

This is a safety requirement, not only a convenience. A host that locates its
project config relative to the launch directory finds none of the above when
started in a subdirectory, so the guard plugin is never registered and every
guard is silently absent for that session — tool calls are not blocked, they are
never inspected, and nothing reports it. See
[`../.agentic/hooks/README.md`](../.agentic/hooks/README.md) for why this cannot
be fixed by changing how the hooks are addressed.

`opencode.json` sets `default_agent` to `aegis`, so the TUI and
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

Before repository work, run `<workflow> config validate --json` and
`<workflow> config show --effective --json`. Report write,
protected-read/path, scope, secret, gate, coverage, and delivery modes and
active rule counts, plus the selected worktree run or explicit `--run-id`.
AEGIS policy comes only from the validated file; OpenCode platform permissions
remain separate.

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
- reads run `guard_read_path.py`;
- post-tool events run `post_tool_evidence.py`.

The plugin contains no repository path or command denylist. Validated
`.agentic/workflow.toml` modes and rules are the only AEGIS repository-policy
source; OpenCode platform permissions remain a separate safety layer.

Interpreter order is explicit `AEGIS_PYTHON`, the runtime registered by
packaged WAEGIS, then the first system launcher that actually resolves on
`PATH` (`py -3` then `python` on Windows, `python3` then `python` elsewhere).
This is the same ordered list used by `.agentic/tools/run_hook.mjs` and the Pi
bridge, so the same repository policy cannot resolve to a different interpreter
depending on which agent is driving. The workflow CLI and hooks do not require a
system Python when that registered runtime is present.

The guard fails **closed**. The shared hooks always exit 0 and signal a denial
on stdout, so a missing interpreter, an interpreter that cannot be launched, or
a hook that exited non-zero without a decision all block the tool call with an
actionable reason. Silence is never treated as an allow.

Delivery commands configured in `guardrails.delivery.command_patterns` require
a passing shared preflight. External OpenCode approval controls are independent
of that AEGIS decision.
