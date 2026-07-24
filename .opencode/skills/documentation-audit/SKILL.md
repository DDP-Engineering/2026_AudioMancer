---
name: documentation-audit
description: Use to audit component documentation after implementation or workflow-contract changes.
compatibility: opencode
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Documentation Audit

Before invoking the shared procedure, run `<workflow> config validate --json`
and `<workflow> config show --effective --json`. Report the effective write,
protected-read/path, scope, secret, gate, coverage, and delivery modes and active
rule counts, state the selected run when graph state is used, and distinguish
AEGIS repository policy from external platform safety.

Read and follow these shared workflow rule sources:

- `AGENTS.md`
- `.agentic/skills/documentation-audit/SKILL.md`

OpenCode invocation: use the native `skill` tool with `documentation-audit`.

The full, platform-neutral procedure lives in
`.agentic/skills/documentation-audit/SKILL.md`. This file is only the OpenCode
adapter entry point.
