---
name: agentic-development
description: Use for feature, bug fix, or behavior-change work that should follow the shared agentic development workflow gates.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Agentic Development

Before invoking the shared procedure, run `<workflow> config validate --json`
and `<workflow> config show --effective --json`. Report the effective write,
protected-read/path, scope, secret, gate, coverage, and delivery modes and active
rule counts, state the selected run when graph state is used, and distinguish
AEGIS repository policy from external platform safety.

Read and follow these shared workflow rule sources:

- `AGENTS.md`
- `.agentic/skills/agentic-development/SKILL.md`

Claude Code invocation: `/agentic-development`.

Interpret any Codex-style `$write-component-documentation`,
`$documentation-audit`, or `$python-codestyle-audit` reference as the matching
Claude Code skill under `.claude/skills/`.
