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

Before repository work, run the project-local `config validate --json` and
`config show --json` commands. Report write, protected-read/path,
scope, secret, gate, coverage, and delivery modes and active rule counts, plus
the selected worktree run or explicit `--run`. AEGIS policy comes only from
the validated file; Qwen trust and host controls remain separate.

## Contents

- `settings.json` - Qwen Code project settings. Wires the shared `.agentic/hooks/`
  guards to Qwen tool events and points the context at `AGENTS.md`. Repository
  policy remains in `workflow.toml`, not adapter permission lists.
- `skills/` - thin Qwen Code skill wrappers that reference the shared, neutral
  procedures under `.agentic/skills/` (single source of truth, same as the Codex,
  Claude Code, and OpenCode adapters).
- `commands/` - `/workflow-status`, `/workflow-preflight`, and `/workflow-report`
  prompt commands that run the project-local `.agentic` runner.

## How it works

Qwen Code has a native command-hook system (`PreToolUse` / `PostToolUse` in
`settings.json`) whose JSON-on-stdin protocol and `hookSpecificOutput` deny signal
match what the `.agentic/hooks/*.py` guards already emit. The adapter reuses
the Python hooks **byte-for-byte** - no bridge code, the same design as the Codex
and Claude Code adapters:

| Qwen tool event | Python hook(s) | Effect on deny |
|---|---|---|
| `Read` / `ReadFile` / `read_file` (PreToolUse) | `guard_read_path.py` | block with reason |
| `WriteFile` / `Edit` / `write_file` / `replace` (PreToolUse) | `guard_write_zone.py`, then `secret_scan.py` (full input) | block with reason |
| `Bash` / `run_shell_command` (PreToolUse) | `secret_scan.py`, then `delivery_preflight.py` | block with reason |
| any edit/shell (PostToolUse) | `post_tool_evidence.py` | fire-and-forget journal entry |

Qwen settings contain no repository path or outward-command denylist. The
shared hooks apply only modes and rules validated from `.agentic/workflow.toml`;
Qwen host safety controls remain independent.

## Tool-name compatibility

The current Qwen Code hook contract states that tool events carry runtime ids
in `tool_name`, including `edit`, `write_file`, and `run_shell_command`, while
built-in display names remain accepted matcher aliases. Its settings reference
maps `Edit` to `edit`, `WriteFile` to `write_file`, and `Bash` to
`run_shell_command`. Some earlier builds and compatible event producers expose
`replace` for editing. The adapter therefore uses harmless unions:

- `Edit|WriteFile|write_file|replace` for edit pre-hooks;
- `Read|ReadFile|read_file` for read pre-hooks;
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
  runtime, then the first system launcher that actually resolves on `PATH`
  (`py -3` then `python` on Windows, `python3` then `python` elsewhere) â€” the
  same ordered list the Codex and Claude Code adapters use. If no interpreter
  can be run, the guard **blocks** with an actionable reason rather than
  allowing the call: the shared hooks always exit 0 and answer on stdout, so
  silence is never an allow. Install Python, set `AEGIS_PYTHON`, or run a
  packaged WAEGIS command to register a runtime.
- **Project trust.** Qwen loads project-local settings, skills, and commands only
  after the workspace is trusted. Trust the project on first start.
- **Launch directory.** Qwen resolves `.qwen/settings.json` against the
  directory it was started in and does not search parent directories. Starting
  it in a subdirectory means the settings file is not found, so **no hooks are
  registered and every guard is silently absent** for that session. Always start
  Qwen Code from the repository root. See
  [`../.agentic/hooks/README.md`](../.agentic/hooks/README.md) for why this
  cannot be fixed by changing the hook commands.

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
