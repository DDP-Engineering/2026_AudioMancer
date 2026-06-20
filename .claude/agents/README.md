<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Claude Code Subagents

No default Claude Code subagent is required for this template. The workflow is
defined by `AGENTS.md`, `.agentic/workflow.toml`, and the skills under
`.claude/skills/`.

Add project-specific subagents here only when a target repository needs a
specialized role. Keep each subagent thin and reference the shared workflow
documents instead of copying their contents.
