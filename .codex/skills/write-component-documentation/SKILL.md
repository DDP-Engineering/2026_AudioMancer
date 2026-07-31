---
name: write-component-documentation
description: Create or update component documentation under `.agentic/knowledge/components/` for a repository using AEGIS. Use when Codex needs to document a new software component, refresh an existing component document, or keep the software component knowledge index aligned with implementation changes.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Write Component Documentation

Before invoking the shared procedure, run `<workflow> config validate --json`
and `<workflow> config show --json`. Report the effective write,
protected-read/path, scope, secret, gate, coverage, and delivery modes and active
rule counts, state the selected run when graph state is used, and distinguish
AEGIS repository policy from external platform safety.

Read and follow these shared workflow rule sources:

- `AGENTS.md`
- `.agentic/skills/write-component-documentation/SKILL.md`
- `.agentic/knowledge/components/component_template.md`
- `.agentic/knowledge/components/index.md`

Codex invocation: `$write-component-documentation`.

Document current implemented behavior only. Update
`.agentic/knowledge/components/index.md` when adding a new component page.
