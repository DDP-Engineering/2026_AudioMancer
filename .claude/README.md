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

The hook configuration calls the generic scripts under `.agentic/hooks/`.
Edit/write matchers run `guard_write_zone.py` and then `secret_scan.py`, so
secrets pasted into file content are denied before the write occurs; Bash input
is scanned independently by the same secret hook.
Hook execution depends on the target machine having a compatible `python`
command on `PATH`. If that is not true, adjust `.claude/settings.json` locally
or run a packaged WAEGIS command to register its runtime; a system Python is
only the final fallback.
