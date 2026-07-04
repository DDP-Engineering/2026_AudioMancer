---
name: documentation-audit
description: Use after implementation changes or before delivery to review changed implementation files against relevant component knowledge under `05_SoftwareDocu`; broad docs are opt-in or scope-triggered.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Documentation Audit

Read and follow these shared workflow rule sources:

- `AGENTS.md`
- `.agentic/skills/documentation-audit/SKILL.md`

Claude Code invocation: `/documentation-audit`.

If a deterministic documentation audit exists in the target repository, run it.
Otherwise perform the manual review described by the shared skill.
