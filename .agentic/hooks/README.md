<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AEGIS Hooks

These scripts are installed with AEGIS and are invoked by every supported
adapter. `workflow_config_bootstrap.py` loads the delivered `aegis.config`
parser; hooks must not parse `workflow.toml` independently or carry fallback
repository policy.

- `guard_read_path.py` applies configured protected-path rules for reads.
- `guard_write_zone.py` applies configured protected paths and write access.
- `secret_scan.py` applies configured secret expressions.
- `delivery_preflight.py` recognizes configured delivery commands.
- `post_tool_evidence.py` records against the selected worktree-local run.

Missing or invalid configuration denies pre-tool actions with the canonical
configuration code and remediation. Disabled or unrestricted modes add no
implicit rules. Keep transport code stdlib-only and free of project secrets.

## Decision protocol

Every hook exits `0` and answers on stdout: an allow prints nothing, a denial
prints one `hookSpecificOutput.permissionDecision = "deny"` object. A hook must
never signal a decision through its exit status.

Because of that, a non-zero exit is always an abnormal failure and never an
allow. Each transport — `.agentic/tools/run_hook.mjs` for Claude Code, Codex,
and Qwen Code, `.opencode/plugins/agentic-guard.mjs`, and
`.pi/extensions/agentic-guard/hook-bridge.ts` — fails **closed**: a missing
interpreter, an interpreter that cannot be launched, and a hook that crashed
all block the tool call with an actionable reason. The launcher normalizes
every such failure to exit status `2`, the blocking status in all three host
hook protocols; passing a crashed hook's own status through would be read as a
*non-blocking* error and the tool call would proceed unchecked.

Keep the three transports in agreement. `tests/test_guard_transport_parity.py`
fails if one of them drifts on interpreter resolution order or on this
fail-closed contract.

## Start the agent at the repository root

A host that discovers its project configuration relative to the directory it was
launched in, without searching parent directories, registers **no hooks at all**
when started in a subdirectory: the config file is simply not found, and every
guard is silently absent for that whole session. The tool calls are not blocked;
they are never inspected.

Verified for Qwen Code (see below). Not verified either way for Codex, OpenCode,
and Pi, so assume the same for them. Claude Code resolves its own project
directory and its hook commands are anchored with `${CLAUDE_PROJECT_DIR}`, which
removes the command-path half of the problem but not the config-discovery half.

This is the one gap in the fail-closed contract above, and it is not something
this repository can configure away:

- It happens before any hook is loaded, so no hook can detect or report it — a
  `SessionStart` guard would not be registered either.
- It is not a path-resolution problem, so it is not fixed by anchoring the hook
  commands. In Qwen Code, `loadSettings(workspaceDir = process.cwd())` builds
  `<cwd>/.qwen/settings.json` with no walk-up, and hooks are then spawned with
  that same directory as their working directory. The relative command in
  `settings.json` therefore always resolves correctly whenever it runs at all —
  the repo-relative form is not a latent bug waiting on a subdirectory launch.
- Anchoring the commands to the Git root instead (`git rev-parse
  --show-toplevel`) would fail outright in a project without a `.git` directory,
  disagrees with `find_repository_root`, which resolves `.agentic/` first, and
  is not expressible in one command string across `bash`, PowerShell, and
  `cmd.exe` — the last of which has no `$(...)` substitution and is the default
  shell on a stock Windows host.

**Operational rule: launch every agent from the directory that contains
`.agentic/`.** If a session starts elsewhere, exit and restart it from the
repository root rather than continuing — the absence of guards gives no visible
signal on its own.

To confirm guards are live in a session, ask the agent to read a path covered by
an enforced `guardrails.protected_paths` read policy: a correctly loaded
configuration denies it.
