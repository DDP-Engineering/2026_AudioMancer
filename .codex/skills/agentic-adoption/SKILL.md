---
name: agentic-adoption
description: Codex adapter for adopting an existing project into the shared agentic workflow before feature, fix, or behavior-change work.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Agentic Adoption

Before invoking the shared procedure, run `<workflow> config validate --json`
and `<workflow> config show --json`. Report the effective write,
protected-read/path, scope, secret, gate, coverage, and delivery modes and active
rule counts, state the selected run when graph state is used, and distinguish
AEGIS repository policy from external platform safety.

Read and follow this shared workflow rule source:

- `.agentic/skills/agentic-adoption/SKILL.md`

Codex invocation: `$agentic-adoption`.

The full, platform-neutral procedure lives in
`.agentic/skills/agentic-adoption/SKILL.md`. This file is only the Codex
adapter entry point.
