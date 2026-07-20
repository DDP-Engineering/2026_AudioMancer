<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Qwen Code Adapter

This directory adapts AEGIS for
[Qwen Code](https://github.com/QwenLM/qwen-code).

Do not duplicate the workflow contract here. `AGENTS.md` remains the canonical
source for gate order, requirements, documentation rules, safety rules, and stop
format. `settings.json` sets `context.fileName` to `["AGENTS.md", "QWEN.md"]` so
Qwen loads `AGENTS.md` first and treats `QWEN.md` only as the adapter note.

## Contents

- `settings.json` - Qwen Code project settings. Wires the shared `.agentic/hooks/`
  guards to Qwen tool events, points the context at `AGENTS.md`, and denies secret
  reads/writes plus outward delivery commands.
- `skills/` - thin Qwen Code skill wrappers that reference the shared, neutral
  procedures under `.agentic/skills/` (single source of truth, same as the Codex,
  Claude Code, and OpenCode adapters).
- `commands/` - `/workflow-status`, `/workflow-preflight`, and `/workflow-report`
  prompt commands that run the project-local `.agentic` runner.

## How it works

Qwen Code has a native command-hook system (`PreToolUse` / `PostToolUse` in
`settings.json`) whose JSON-on-stdin protocol and `hookSpecificOutput` deny signal
match what the four `.agentic/hooks/*.py` guards already emit. The adapter reuses
the Python hooks **byte-for-byte** - no bridge code, the same design as the Codex
and Claude Code adapters:

| Qwen tool event | Python hook(s) | Effect on deny |
|---|---|---|
| `WriteFile` / `Edit` / `write_file` / `replace` (PreToolUse) | `guard_write_zone.py`, then `secret_scan.py` (full input) | block with reason |
| `Bash` / `run_shell_command` (PreToolUse) | `secret_scan.py`, then `delivery_preflight.py` | block with reason |
| any edit/shell (PostToolUse) | `post_tool_evidence.py` | fire-and-forget journal entry |

## Tool-name compatibility

The current Qwen Code hook contract states that tool events carry runtime ids
in `tool_name`, including `edit`, `write_file`, and `run_shell_command`, while
built-in display names remain accepted matcher aliases. Its settings reference
maps `Edit` to `edit`, `WriteFile` to `write_file`, and `Bash` to
`run_shell_command`. Some earlier builds and compatible event producers expose
`replace` for editing. The adapter therefore uses harmless unions:

- `Edit|WriteFile|write_file|replace` for edit pre-hooks;
- `Bash|run_shell_command` for shell pre-hooks;
- the union of both sets for post-tool evidence.

These names are cross-checked against the current official
[hook documentation](https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/hooks.md)
and [settings reference](https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/settings.md).
Keeping both friendly and raw forms makes hook coverage independent of which
form a Qwen version reports. The shared `guard_write_zone.py` hook recognizes
the same write identifiers because it is reused byte-for-byte across adapters.

## Prerequisites and trust

- **Python runtime.** Hooks use `AEGIS_PYTHON`, the packaged-WAEGIS registered
  runtime, then a supported system Python. If
  `python` cannot be run, the guard fails open (allows) - the same "needs Python on
  PATH" caveat as the Codex and Claude Code adapters. Adjust the `command` entries
  in `settings.json` locally if your interpreter is named differently.
- **Project trust.** Qwen loads project-local settings, skills, and commands only
  after the workspace is trusted. Trust the project on first start.

## Usage

Start Qwen Code from the repository root so the project `settings.json`, skills,
and commands load together:

```powershell
qwen
```

The shared skills surface in the `/skills` picker (and are model-invoked when
relevant): `agentic-development`, `agentic-adoption`, `agentic-delivery`,
`regression-traceability`, `documentation-audit`, `python-codestyle-audit`, and
`write-component-documentation`. Verify the loaded context with `/memory show`;
`AGENTS.md` should appear at the top of the hierarchy.
