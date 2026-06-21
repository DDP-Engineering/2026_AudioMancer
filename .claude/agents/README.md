<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Claude Code Subagents

No default Claude Code subagent is required for this template. The workflow is
defined by `AGENTS.md`, `.agentic/workflow.toml`, and the skills under
`.claude/skills/`.

Add project-specific subagents here only when a target repository needs a
specialized role. Keep each subagent thin and reference the shared workflow
documents instead of copying their contents.
