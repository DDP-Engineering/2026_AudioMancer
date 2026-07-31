---
name: regression-traceability
description: Use to audit requirements traceability, map changed files to linked tests, detect uncovered modules, and decide focused versus full regression.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Regression Traceability

Before invoking the shared procedure, run `<workflow> config validate --json`
and `<workflow> config show --json`. Report the effective write,
protected-read/path, scope, secret, gate, coverage, and delivery modes and active
rule counts, state the selected run when graph state is used, and distinguish
AEGIS repository policy from external platform safety.

Read and follow these shared workflow rule sources:

- `AGENTS.md`
- `.agentic/skills/regression-traceability/SKILL.md`

Claude Code invocation: `/regression-traceability`.

Component documentation complements requirements and tests. It does not replace
durable requirement snapshots, linked tests, or explicit manual verification.
