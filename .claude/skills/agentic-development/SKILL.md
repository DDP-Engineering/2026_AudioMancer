---
name: agentic-development
description: Use for feature, bug fix, or behavior-change work that should follow the shared agentic development workflow gates.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Agentic Development

Read and follow these workflow rule sources:

- `AGENTS.md`
- `.agentic/workflow.toml`
- `.codex/skills/agentic-development/SKILL.md`

Use `PROMPT_CHEATSHEET.md` only as a human operator prompt reference, not as
an authoritative agent behavior contract.

Claude Code invocation: `/agentic-development`.

Interpret any Codex-style `$write-component-documentation`,
`$documentation-audit`, or `$python-codestyle-audit` reference as the matching
Claude Code skill under `.claude/skills/`.
