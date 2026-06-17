---
name: agentic-delivery
description: Use when preparing delivery, reports, commits, PRs, pushes, merges, or final preflight for an agentic workflow run.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Agentic Delivery

Read and follow these workflow rule sources:

- `AGENTS.md`
- `.agentic/workflow.toml`
- `.codex/skills/agentic-delivery/SKILL.md`

Use `PROMPT_CHEATSHEET.md` only as a human operator prompt reference, not as
an authoritative agent behavior contract.

Claude Code invocation: `/agentic-delivery`.

Do not commit, push, create a PR, merge, or publish until delivery preflight
passes and the human explicitly approves the action.
