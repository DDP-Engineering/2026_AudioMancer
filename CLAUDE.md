<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# CLAUDE.md

Claude Code should treat `AGENTS.md` as the authoritative workflow contract for
this repository. Read `AGENTS.md` first, then use this file only as the Claude
Code adapter note.

If this file and `AGENTS.md` disagree, follow `AGENTS.md`.

Before using repository tools, complete the mandatory workflow bootstrap in
`AGENTS.md`: validate `.agentic/workflow.toml`, inspect effective modes, report
the active restrictions and selected run, then obey both AEGIS policy and
Claude Code host safety controls.

Claude direct skill invocation uses `/skill-name`. Existing Codex-style
references such as `$documentation-audit` mean the matching Claude Code skill,
for example `/documentation-audit`.
