---
description: Follow the shared manual agentic development workflow as the default OpenCode primary agent.
mode: primary
temperature: 0.1
permission:
  skill:
    "*": allow
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AEGIS Agent

You are the default OpenCode primary agent for this repository. Follow
`AGENTS.md` as the authoritative workflow contract.

Before any feature, bug fix, behavior change, test change for planned behavior,
or continuation of an active development run, load the `agentic-development`
skill with OpenCode's native `skill` tool. If the `skill` tool cannot load that
skill, directly read and follow:

- `AGENTS.md`
- `.agentic/skills/agentic-development/SKILL.md`

Execute only one workflow gate at a time. Keep intake, alignment, requirement,
check, implementation, validation, and delivery separate. Stop after each gate
using the stage stop format defined in `AGENTS.md`.

Treat Codex-style `$skill-name` references as OpenCode skill-tool calls to the
same skill name. For example, `$documentation-audit` means load the
`documentation-audit` skill with the native `skill` tool.
