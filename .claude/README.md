<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Claude Code Adapter

This directory adapts AEGIS for Claude Code.

Do not duplicate the workflow contract here. `AGENTS.md` remains the canonical
source for gate order, requirements, documentation rules, safety rules, and stop
format.

Contents:

- `settings.json` - Claude Code project settings and hook bindings.
- `skills/` - thin Claude Code skill wrappers that reference the shared
  workflow instructions.
- `agents/` - optional Claude Code subagent notes for workflow roles.

Before repository work, run the project-local `config validate --json` and
`config show --json` commands. Report write, protected-read/path,
scope, secret, gate, coverage, and delivery modes and active rule counts, plus
the selected worktree run or explicit `--run`. AEGIS policy comes only from
the validated file; Claude host approvals remain separate.

The hook configuration calls the generic scripts under `.agentic/hooks/`.
Read matchers run `guard_read_path.py`.
Edit/write matchers run `guard_write_zone.py` and then `secret_scan.py`, so
content is evaluated when configured secret scanning is enforced; Bash input
uses the same configured secret hook and delivery commands use
`delivery_preflight.py`. `settings.json` carries no repository denylist:
validated `.agentic/workflow.toml` is the sole AEGIS policy source. Claude host
approvals remain a separate external safety layer.
Hook execution depends on the target machine having a compatible `python`
command on `PATH`. If that is not true, adjust `.claude/settings.json` locally
or run a packaged WAEGIS command to register its runtime; a system Python is
only the final fallback.
