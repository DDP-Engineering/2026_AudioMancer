---
name: agentic-delivery
description: Manual agentic delivery workflow for preparing a PR, creating a PR, publishing a branch, or finalizing an agentic development run. Use when the user asks to create PR, prepare PR, deliver the change, publish, push, merge, or produce the final report for an agentic workflow run.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Agentic Delivery

Before invoking the shared procedure, run `<workflow> config validate --json`
and `<workflow> config show --json`. Report the effective write,
protected-read/path, scope, secret, gate, coverage, and delivery modes and active
rule counts, state the selected run when graph state is used, and distinguish
AEGIS repository policy from external platform safety.

Read and follow these shared workflow rule sources:

- `AGENTS.md`
- `.agentic/skills/agentic-delivery/SKILL.md`

Codex invocation: `$agentic-delivery`.

Do not commit, push, create a PR, merge, or publish until delivery preflight
passes and the human explicitly approves the action.
