---
name: regression-traceability
description: Use to audit requirements traceability, map changed files to linked tests, detect uncovered modules, and decide focused versus full regression.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Regression Traceability

Read and follow these workflow rule sources:

- `AGENTS.md`
- `.agentic/requirements/README.md`
- `.agentic/workflow.toml`
- `.codex/skills/regression-traceability/SKILL.md`

Use `PROMPT_CHEATSHEET.md` only as a human operator prompt reference, not as
an authoritative agent behavior contract.

Claude Code invocation: `/regression-traceability`.

Component documentation complements requirements and tests. It does not replace
durable requirement rows, linked tests, or explicit manual verification.
