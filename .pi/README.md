<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Pi Adapter

This directory adapts AEGIS for
[Pi](https://pi.dev) (`@earendil-works/pi-coding-agent`). It is **also a Pi
package** (`package.json` carries the `pi` key), so a copied template project
gets Pi support automatically, and a standalone repo can `pi install ./.pi`.

Do not duplicate the workflow contract here. `AGENTS.md` remains the canonical
source for gate order, requirements, documentation rules, safety rules, and stop
format. Pi reads `AGENTS.md` natively.

Before repository work, run the project-local `config validate --json` and
`config show --effective --json` commands. Report write, protected-read/path,
scope, secret, gate, coverage, and delivery modes and active rule counts, plus
the selected worktree run or explicit `--run-id`. AEGIS policy comes only from
the validated file; Pi trust and host controls remain separate.

## Contents

- `package.json` - Pi package manifest. Declares the `agentic-guard` extension
  and points `pi.skills` at `../.agentic/skills` so the shared neutral skills are
  reused with **no duplication** (single source of truth, same as the Codex and
  Claude adapters).
- `settings.json` - project-local Pi settings. Loads this directory as a package
  so the skills manifest is honored.
- `extensions/agentic-guard/` - the bridge extension (the only new logic):
  - `index.ts` - subscribes to `tool_call` / `tool_result` and wires the bridge.
  - `bridge.ts` - maps Pi tool events onto the Python guard hooks.
  - `hook-bridge.ts` - spawns the `.agentic/hooks/*.py` scripts and parses their
    deny signal without interpreting repository policy.
- `tests/hook-bridge.test.ts` - vitest specs for the mapping and decision logic.

## How it works

Pi's hooks are in-process TypeScript, but the shared guard hooks under
`.agentic/hooks/` already speak a clean JSON-on-stdin protocol. The extension
translates Pi tool events into the existing hook payloads and reuses the Python
**byte-for-byte**:

| Pi event (`tool_call`) | Python hook(s) | Effect on deny |
|---|---|---|
| `write` / `edit` | `guard_write_zone.py`, then `secret_scan.py` (full input) | block with reason |
| `bash` | `secret_scan.py`, then `delivery_preflight.py` | block with reason |
| `read` | `guard_read_path.py` | block with reason |
| `tool_result` (any) | `post_tool_evidence.py` | fire-and-forget journal entry |

`block` is returned as `{ block: true, reason }`. Pi enforces this in every mode
(TUI, RPC, JSON, print) because blocking is a return value, not a UI prompt.
Read, write, secret, and delivery rules come only from the validated
`.agentic/workflow.toml`; the TypeScript bridge contains no repository denylist.

> **Transport note:** Pi's `pi.exec()` cannot pass stdin (its options are only
> `{ signal, timeout }`, with no `cwd` option either), so the hooks are spawned
> via Node's `child_process` instead, which also gives explicit control over
> the working directory. The Python is unchanged; only the transport differs
> from a plain `pi.exec`.

## Prerequisites and trust

- **Python runtime.** Set `AEGIS_PYTHON` to pin an interpreter. Otherwise the
  bridge uses the runtime registered by packaged WAEGIS, then the first system
  launcher that actually resolves on `PATH` (`py -3` then `python` on Windows,
  `python3` then `python` elsewhere) — the same ordered list the Codex, Claude
  Code, and Qwen Code launcher uses. If no interpreter can be run, the guard
  **blocks** with an actionable reason rather than allowing the call: the
  shared hooks always exit 0 and answer on stdout, so silence is never an
  allow. Install Python, set `AEGIS_PYTHON`, or run a packaged WAEGIS command
  to register a runtime.
- **Project trust.** Project-local extensions and skills load only after the
  project is trusted (`ctx.isProjectTrusted()`). Codex and Qwen Code gate their
  project-local configuration the same way, and Codex additionally requires each
  hook to be reviewed before it runs; only Claude Code needs no trust step. Trust
  the project when Pi prompts on first start.
- **Launch directory.** Start Pi from the repository root, the directory holding
  `.agentic/`. Pi resolves project-local resources from the current working
  directory; started in a subdirectory it finds no `.pi/`, so the guard
  extension is never registered and every guard is silently absent for that
  session — tool calls are not blocked, they are never inspected. Declining
  trust has the same effect and is at least visible; this one is not. See
  [`../.agentic/hooks/README.md`](../.agentic/hooks/README.md).

## Install & usage

```powershell
pi install ./.pi          # local path (inside a repo that has the .agentic engine), or:
pi install git:github.com/<org>/<repo>@v0.2.0   # private git; PolyForm-NC stays private
# Trust the project when prompted.
pi                        # AGENTS.md gate contract + /skill:agentic-development active
```

The shared skills surface as `/skill:agentic-development`,
`/skill:agentic-adoption`, `/skill:agentic-delivery`,
`/skill:regression-traceability`, `/skill:documentation-audit`,
`/skill:python-codestyle-audit`, and `/skill:write-component-documentation`.

**Do not `npm publish`.** `private:true` and the `LicenseRef-PolyForm-Noncommercial-1.0.0`
license field keep the noncommercial posture intact. Distribute via git or local
path only.

## Running the bridge tests

```powershell
cd .pi
npm install
npm test
```

`vitest` is isolated to this directory so it never touches the Python project.
