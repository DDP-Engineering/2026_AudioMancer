---
name: python-codestyle-audit
description: Review and update Python code style for repositories using this workflow template, including module prologues, documentation comments, public callable docstrings, and local style rules. Use after Python implementation changes or before delivery when Python files changed.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Python Code Style Audit

Read and follow these shared workflow rule sources:

- `AGENTS.md`
- `.agentic/skills/python-codestyle-audit/SKILL.md`

Codex invocation: `$python-codestyle-audit`.

If the target repository has deterministic Python style tooling, run it in the
smallest relevant scope. Otherwise perform the manual review described by the
shared skill.
