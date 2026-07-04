---
name: python-codestyle-audit
description: Use after Python implementation changes or before delivery to review Python style, docstrings, local conventions, and validation commands.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Python Code Style Audit

Read and follow these shared workflow rule sources:

- `AGENTS.md`
- `.agentic/skills/python-codestyle-audit/SKILL.md`

Qwen Code invocation: model-invoked when relevant, or select it from `/skills`.

If the target repository has deterministic Python style tooling, run it in the
smallest relevant scope. Otherwise perform the manual review described by the
shared skill.
