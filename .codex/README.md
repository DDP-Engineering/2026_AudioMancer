<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Codex Adapter

This directory adapts AEGIS for [Codex](https://github.com/openai/codex).

Do not duplicate the workflow contract here. `AGENTS.md` remains the canonical
source for gate order, requirements, documentation rules, safety rules, and stop
format.

Before repository work, run the project-local `config validate --json` and
`config show --effective --json` commands. Report write, protected-read/path,
scope, secret, gate, coverage, and delivery modes and active rule counts, plus
the selected worktree run or explicit `--run-id`. AEGIS policy comes only from
the validated file; Codex trust and host approvals remain separate.

## Contents

- `config.toml` - Codex project configuration. Selects the workspace-scoped
  permission profile and keeps network access off by default. Repository policy
  remains in `workflow.toml`, not adapter permission lists.
- `hooks.json` - wires the shared `.agentic/hooks/` guards to Codex tool events.
- `skills/` - thin Codex skill wrappers that reference the shared, neutral
  procedures under `.agentic/skills/` (single source of truth, same as the
  Claude Code, Qwen Code, and OpenCode adapters).

## How it works

Codex has a native command-hook system whose JSON-on-stdin payload
(`hook_event_name`, `tool_name`, `tool_input`) and `hookSpecificOutput` deny
signal match what the `.agentic/hooks/*.py` guards already emit. The adapter
reuses the Python hooks **byte-for-byte** - no bridge code, the same design as
the Claude Code and Qwen Code adapters:

| Codex tool event | Python hook(s) | Effect on deny |
|---|---|---|
| `Read` (PreToolUse) | `guard_read_path.py` | block with reason |
| `apply_patch` / `Edit` / `Write` (PreToolUse) | `guard_write_zone.py`, then `secret_scan.py` (full input) | block with reason |
| `Bash` (PreToolUse) | `guard_shell_write.py`, `secret_scan.py`, then `delivery_preflight.py` | block with reason |
| any edit/shell (PostToolUse) | `post_tool_evidence.py` | fire-and-forget journal entry |

Codex reports its shell tool to hooks as `Bash`, and the edit matcher is a
harmless union so coverage does not depend on which identifier a given Codex
build emits for a patch application. `config.toml` contains no repository path
or outward-command denylist; the shared hooks apply only modes and rules
validated from `.agentic/workflow.toml`.

## `hooks.json` accepts exactly two top-level keys

Codex deserializes `hooks.json` strictly: the only accepted top-level keys are
`description` and `hooks`. An unknown key is not ignored - it rejects the
**whole file**, which registers no hooks at all and leaves every guard silently
absent for the session. Tool calls are not blocked; they are never inspected.

The `_legal` / `_comment*` annotation convention used in the other adapters'
JSON must therefore never appear here. Per-hook entries accept `type`,
`command`, `commandWindows`, `timeout`, `statusMessage`, and
`additionalContextLimit`; `commandWindows` is what lets one file carry both the
POSIX and Windows command forms.

`waegis doctor` reports a rejected file as the `runnability.adapter-configs`
failure, and `tests/test_scaffold.py` blocks the mistake at the source.

## Prerequisites and trust

- **Python runtime.** Hooks use `AEGIS_PYTHON`, the packaged-WAEGIS registered
  runtime, then the first system launcher that actually resolves on `PATH`
  (`py -3` then `python` on Windows, `python3` then `python` elsewhere) — the
  same ordered list the Claude Code and Qwen Code adapters use. If no
  interpreter can be run, the guard **blocks** with an actionable reason rather
  than allowing the call.
- **Node.js.** The guards are launched through
  `node .agentic/tools/run_hook.mjs`. Without `node` on `PATH` the hook command
  cannot start, which Codex reads as a non-blocking error, so the guards
  silently stop enforcing. See
  [`../.agentic/hooks/README.md`](../.agentic/hooks/README.md).
- **Project trust.** Codex loads project-local config, hooks, and exec policies
  only for a trusted project. Until the project is trusted, `.codex/` is skipped
  entirely and no guard is registered — while skills still load, so the session
  looks healthy. Trust the project when Codex prompts, or add it under
  `[projects]` in the Codex home `config.toml`.
- **Hook review.** In a trusted project a newly seen hook is registered but does
  not run until it is reviewed in the `/hooks` panel, which reports
  `N hooks need review before they can run.` Hook trust is keyed to this file's
  content hash, so any change to `hooks.json` — including an AEGIS payload
  upgrade — returns the hooks to `review required` and stops them running until
  re-reviewed.
- **Launch directory.** Start Codex from the repository root, the directory
  holding `.agentic/`. Started in a subdirectory, the project configuration is
  not found, so no hooks are registered and every guard is silently absent for
  that session. See
  [`../.agentic/hooks/README.md`](../.agentic/hooks/README.md) for why this
  cannot be fixed by changing the hook commands.

## Usage

Start Codex from the repository root so the project config, hooks, and skills
load together:

```powershell
codex
```

Then confirm the guards are actually live — the four gates above all fail open,
so a disabled session is indistinguishable from a healthy one until something
is checked. Open `/hooks` and verify the AEGIS entries are listed and trusted,
then ask the agent to read a path covered by an enforced
`guardrails.protected_paths` read policy: a correctly loaded configuration
denies it.

The shared skills are available as `agentic-development`, `agentic-adoption`,
`agentic-delivery`, `regression-traceability`, `documentation-audit`,
`python-codestyle-audit`, and `write-component-documentation`.
