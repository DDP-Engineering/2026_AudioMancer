<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# QWEN.md

Qwen Code should treat `AGENTS.md` as the authoritative workflow contract for
this repository. Read `AGENTS.md` first, then use this file only as the Qwen Code
adapter note.

If this file and `AGENTS.md` disagree, follow `AGENTS.md`.

Before using repository tools, complete the mandatory workflow bootstrap in
`AGENTS.md`: validate `.agentic/workflow.toml`, inspect effective modes, report
the active restrictions and selected run, then obey both AEGIS policy and Qwen
Code host safety controls.

Shared workflow skills are model-invoked and also available from the `/skills`
picker (for example `agentic-development`). Existing Codex-style references such
as `$documentation-audit` mean the matching Qwen Code skill under `.qwen/skills/`,
for example the `documentation-audit` skill.

Project-local settings, skills, and commands under `.qwen/` load only after the
workspace is trusted; see `.qwen/README.md`.
