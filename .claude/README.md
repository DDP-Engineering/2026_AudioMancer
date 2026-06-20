<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Claude Code Adapter

This directory adapts the shared agentic workflow template for Claude Code.

Do not duplicate the workflow contract here. `AGENTS.md` remains the canonical
source for gate order, requirements, documentation rules, safety rules, and stop
format.

Contents:

- `settings.json` - Claude Code project settings and hook bindings.
- `skills/` - thin Claude Code skill wrappers that reference the shared
  workflow instructions.
- `agents/` - optional Claude Code subagent notes for workflow roles.

The hook configuration calls the generic scripts under `.agentic/hooks/`.
Hook execution depends on the target machine having a compatible `python`
command on `PATH`. If that is not true, adjust `.claude/settings.json` locally
or install Python 3.11+.
