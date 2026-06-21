<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Pi Adapter

This directory adapts the shared agentic workflow template for
[Pi](https://pi.dev) (`@earendil-works/pi-coding-agent`). It is **also a Pi
package** (`package.json` carries the `pi` key), so a copied template project
gets Pi support automatically, and a standalone repo can `pi install ./.pi`.

Do not duplicate the workflow contract here. `AGENTS.md` remains the canonical
source for gate order, requirements, documentation rules, safety rules, and stop
format. Pi reads `AGENTS.md` natively.

## Contents

- `package.json` - Pi package manifest. Declares the `agentic-guard` extension
  and points `pi.skills` at `../.agentic/skills` so the six neutral skills are
  reused with **no duplication** (single source of truth, same as the Codex and
  Claude adapters).
- `settings.json` - project-local Pi settings. Loads this directory as a package
  so the skills manifest is honored.
- `extensions/agentic-guard/` - the bridge extension (the only new logic):
  - `index.ts` - subscribes to `tool_call` / `tool_result` and wires the bridge.
  - `bridge.ts` - maps Pi tool events onto the Python guard hooks.
  - `hook-bridge.ts` - spawns the `.agentic/hooks/*.py` scripts and parses their
    deny signal; also the protected-path read check.
- `tests/hook-bridge.test.ts` - vitest specs for the mapping and decision logic.

## How it works

Pi's hooks are in-process TypeScript, but the four guard hooks under
`.agentic/hooks/` already speak a clean JSON-on-stdin protocol. The extension
translates Pi tool events into the existing hook payloads and reuses the Python
**byte-for-byte**:

| Pi event (`tool_call`) | Python hook(s) | Effect on deny |
|---|---|---|
| `write` / `edit` | `guard_write_zone.py`, then `secret_scan.py` (full input) | block with reason |
| `bash` | `secret_scan.py`, then `delivery_preflight.py` | block with reason |
| `read` | native protected-path check (mirrors the `.claude` Read denies) | block with reason |
| `tool_result` (any) | `post_tool_evidence.py` | fire-and-forget journal entry |

`block` is returned as `{ block: true, reason }`. Pi enforces this in every mode
(TUI, RPC, JSON, print) because blocking is a return value, not a UI prompt.

> **Transport note:** Pi's `pi.exec()` cannot pass stdin (its options are
> `{ signal, timeout, cwd }`), so the hooks are spawned via Node's
> `child_process` instead. The Python is unchanged; only the transport differs
> from a plain `pi.exec`.

## Prerequisites and trust

- **Python on PATH.** The hooks are stdlib-only and run on any Python 3.11+.
  Set `AGENTIC_WORKFLOW_PYTHON` to pin a specific interpreter; otherwise the
  bridge uses `py -3` on Windows and `python3` elsewhere. If Python cannot be
  run, the guard fails open (allows) — the same "needs Python on PATH" caveat as
  the Codex/Claude adapters.
- **Project trust.** Project-local extensions and skills load only after the
  project is trusted (`ctx.isProjectTrusted()`). This is the one behavioral
  difference from the Codex and Claude adapters, which do not require a trust
  step. Trust the project when Pi prompts on first start.

## Install & usage

```powershell
pi install ./.pi          # local path (inside a repo that has the .agentic engine), or:
pi install git:github.com/<org>/<repo>@v0.1.0   # private git; PolyForm-NC stays private
# Trust the project when prompted.
pi                        # AGENTS.md gate contract + /skill:agentic-development active
```

The six skills surface as `/skill:agentic-development`, `/skill:agentic-delivery`,
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
