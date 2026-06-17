---
name: python-codestyle-audit
description: Use after Python implementation changes or before delivery to review Python style, docstrings, local conventions, and validation commands.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Python Codestyle Audit

Read and follow these workflow rule sources:

- `AGENTS.md`
- `.agentic/workflow.toml`
- `.codex/skills/python-codestyle-audit/SKILL.md`

Use `PROMPT_CHEATSHEET.md` only as a human operator prompt reference, not as
an authoritative agent behavior contract.

Claude Code invocation: `/python-codestyle-audit`.

If the target repository has deterministic Python style tooling, run it in the
smallest relevant scope. Otherwise perform the manual review described by the
shared skill.
