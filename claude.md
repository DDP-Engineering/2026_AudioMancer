<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# CLAUDE.md

Claude Code should treat `AGENTS.md` as the authoritative workflow contract for
this repository. Read `AGENTS.md` first, then use this file only as the Claude
Code adapter note.

Useful workflow references:

- `AGENTS.md` - canonical agentic development rules.
- `PROMPT_CHEATSHEET.md` - human operator prompt examples for each workflow
  gate.
- `WORKFLOW_CHEATSHEET.svg` - visual workflow reference.
- `.agentic/workflow.toml` - project-specific roots, gates, documentation
  roots, secret patterns, and write zones.
- `.agentic/tools/` - local Windows and Bash wrappers for `<workflow>`.
- `.claude/skills/` - Claude Code skill wrappers for the shared workflow
  skills.

If this file and `AGENTS.md` disagree, follow `AGENTS.md`.

Claude direct skill invocation uses `/skill-name`. Existing Codex-style
references such as `$documentation-audit` mean the matching Claude Code skill,
for example `/documentation-audit`.
