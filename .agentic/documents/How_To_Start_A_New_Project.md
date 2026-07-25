<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# How To Start And Adapt A New Project

AEGIS adds an offline-first, human-steered engineering workflow to a repository.
The template ships explicit unrestricted policy so a new project can inspect
and validate its structure before opting into repository restrictions.

## 1. Prerequisites

| Tool | Purpose | Check |
| --- | --- | --- |
| Git 2.30+ | Working-tree analysis and delivery context | `git --version` |
| Python 3.11+ | Local CLI and hook implementation | `python --version` |
| Node.js 18+ | Cross-adapter hook launcher | `node --version` |

Packaged WAEGIS can register its bundled Python runtime, so a separately
installed system Python is not required after registration.

Node is required by the Claude Code, Codex, and Qwen Code adapters, which launch
the guards through `run_hook.mjs`; OpenCode and Pi run the guards in their own
runtimes and need no system Node. Without a usable Node those three adapters
cannot launch their guards, and an unlaunchable guard blocks the tool call
rather than allowing it — so a missing Node means unchecked tool calls, not a
missing convenience.

**Always start the agent from the repository root** — the directory that holds
`.agentic/`. Each host discovers its project configuration relative to the
directory it was launched in and does not search parent directories, so a
session started in a subdirectory loads no configuration and registers no guards
at all.

## 2. Install or Deploy

For a fresh project, copy the AEGIS template or use WAEGIS `new`. For an
existing repository, prefer WAEGIS `adopt` so configuration answers, the
install manifest, and safety checks are recorded consistently.

The deployed shape includes:

```text
AGENTS.md
CLAUDE.md
QWEN.md
.agentic/
  cli/
  documents/
  hooks/
  knowledge/
  requirements/
  runs/
  skills/
  tools/
  components.toml
  workflow.toml
.claude/
.codex/
.opencode/
.pi/
.qwen/
opencode.json
```

`.agentic/.workspace/` is intentionally absent from the payload. It is ignored
local state created on demand when a run starts.

## 3. Use the Project-Local Runner

Windows:

```powershell
.\.agentic\tools\run.ps1 --help
```

POSIX:

```bash
bash .agentic/tools/run.sh --help
```

Examples below use `<workflow>` for either wrapper. An installed `aegis` or
`python -m aegis` command is also valid when it points at the copied payload.

## 4. Validate Before Acting

Every agent and operator begins with:

```powershell
<workflow> config validate --json
<workflow> config show --effective --json
```

Report the effective write-access, protected-read/path, scope, secret, gate,
coverage, and delivery modes with their active rule counts. Do not continue
when `.agentic/workflow.toml` is missing or invalid.

AEGIS repository policy and external platform safety are separate. An
unrestricted AEGIS mode never disables a host sandbox, approval, network,
operating-system, or organization control.

## 5. Understand the Shipped Defaults

The template uses schema version 2 and is explicit:

| Concern | Default mode |
| --- | --- |
| Secrets | `disabled` |
| Protected paths | `disabled` |
| Working tree | `unrestricted` |
| Write access | `unrestricted` |
| Scope | `unrestricted` |
| Coverage | `disabled` |
| Alignment protected scope | `disabled` |
| Gates | `disabled` |
| Component baseline | `disabled` |
| Adoption source changes | `unrestricted` |
| Delivery hook | `disabled` |

Inactive rule collections are empty. These values are deliberate policy, not
fallbacks. Structural roots remain explicit and must be adapted to the project.

## 6. Adapt Repository Structure

Review at least:

```toml
schema_version = 2

[source]
roots = ["src"]

[tests]
roots = ["tests"]

[requirements]
roots = [".agentic/requirements"]

[documentation]
roots = [".agentic/knowledge/components"]
component_template = ".agentic/knowledge/components/component_template.md"

[traceability]
language = "python"
source_extensions = [".py"]
test_file_patterns = ["test_*.py", "*_test.py"]
```

Paths are repository-relative and use `/`. Absolute paths, drive prefixes,
empty entries, and `..` segments are invalid. Duplicate normalized paths are
also errors.

WAEGIS language proposals help fill structural values. They do not silently
enable secrets, protected paths, blockers, scope, write restrictions, coverage,
or gates.

## 7. Opt Into Restrictions Deliberately

### Example: test and lint gates

```toml
[gates]
mode = "enforce"
test = ["python -m pytest -q"]
lint = ["python -m ruff check ."]
```

### Example: protected reads and writes

```toml
[guardrails.protected_paths]
mode = "enforce"
patterns = ["secrets/**", ".env"]
operations = ["read", "write"]
```

### Example: enforced coverage

```toml
[traceability.coverage]
mode = "enforce"
coverable_roots = ["src"]
exclude = ["src/generated/**"]
```

### Example: stage-restricted writes

`stage_restricted` requires all standard and adoption stage keys. An empty
stage list means read-only. Copy the complete example from
`WORKFLOW_CONFIGURATION.md`; do not create a partial stage map.

After every policy edit, rerun `config validate` and `config show --effective`.

## 8. Start and Select Runs

Start a new run:

```powershell
<workflow> start --kind feature --statement "Add invoice export"
```

The graph is written under `.agentic/runs/<run-id>/`. Only after the graph is
saved does AEGIS atomically select it in:

```text
.agentic/.workspace/state/current_run
```

Rules:

- one worktree owns one local pointer;
- never copy the pointer between worktrees;
- never stage `.agentic/.workspace/`;
- use `--run-id <existing-run-id>` when automation must pin a run; and
- treat `RUN-POINTER-*` and `RUN-ID-NOT-FOUND` errors as state setup guidance,
  not permission to guess or edit a graph.

Example explicit selection:

```powershell
<workflow> status --run-id feature-2026-07-22T120000Z-1a2b3c4d
```

To continue an existing run in a fresh session (a new agent with no prior chat
context), reconstruct the full picture first:

```powershell
<workflow> resume
```

`resume` prints a read-only brief: the current stage and next stage, the intent
and recorded alignment, spec items, checks, recent evidence, and the run's cited
requirements resolved with their `spec_ref`. Open each `spec_ref` file for the
concrete detail, then continue at the reported stage.

## 9. Manage Durable Requirements

Requirements are one current TOML snapshot per UUIDv4-backed ID. They are not
Markdown registers and they keep no revision history.

Search before creating:

```powershell
<workflow> requirement list --json
```

Create and use the returned ID:

```powershell
<workflow> requirement create --category functional --priority Must --requirement "Invoice export writes a CSV file." --rationale "Operators need a portable export." --verification "Inspection: inspect the exported CSV" --spec-ref .agentic/requirements/functional/invoice_export.spec.md --affected-path src/exporter.py
```

Keep the `requirement` sentence atomic and put the concrete detail — data
structures, interface/format, exact dialog and copy text, example payloads,
worked examples — in a companion spec file authored from
`.agentic/requirements/spec_template.md` and referenced with `--spec-ref`. A
non-empty `spec_ref` must resolve to an existing file, and a later-deleted target
is reported as `REQ-SPEC-MISSING` by the traceability audit. `feature` and
`change` work should carry a `spec_ref`; a small `fix` may omit it.

Update the same behavioral contract without changing its ID:

```powershell
<workflow> requirement update --id <requirement-id> --affected-path src/exporter.py --linked-test tests/test_exporter.py::test_csv_export
```

Supplied path/test options replace the complete current set. Use
`--clear-affected-paths` or `--clear-linked-tests` for an explicit empty set.

Activate after verification:

```powershell
<workflow> requirement activate --id <requirement-id> --linked-test tests/test_exporter.py::test_csv_export --verification "Automated test"
```

Traceability, coverage, and impact read these canonical files directly. There
is no registry sync, registry audit, or generated traceability cache.

## 10. Daily Workflow

The standard run stages are:

```text
intake -> alignment -> requirement -> check -> implementation -> validation -> delivery
```

At each stage:

1. Keep intent, requirements, checks, implementation, and validation separate.
2. Record failing check evidence before passing evidence.
3. Update component documentation with material component changes.
4. Run traceability/coverage according to effective modes.
5. Run configured gates when enabled.
6. Stop with evidence and exact next options.
7. Require explicit human approval before push, PR, merge, or publication.

## 11. Adapter Checks

- Codex: verify `.codex/config.toml`, `.codex/hooks.json`, and local skills.
- Claude Code: verify `.claude/settings.json`, `CLAUDE.md`, and trust/approvals.
- Pi: trust the project and verify the `.pi` bridge package.
- OpenCode: start at the repository root and use `/workflow-status`.
- Qwen Code: trust the workspace and verify `AGENTS.md` with `/memory show`.

Adapters contain no second AEGIS repository denylist. Their hooks delegate
configured decisions to the shared Python implementation.

## 12. Troubleshooting

| Symptom | Meaning | Repair |
| --- | --- | --- |
| `CONFIG-MISSING` | No readable workflow file | Restore a complete schema-version-2 file. |
| `CONFIG-INCONSISTENT` | Mode and rules disagree | Follow the reported remediation, then validate again. |
| `RUN-POINTER-MISSING` | This worktree has no selected run | Start a run or pass `--run-id`. |
| `RUN-POINTER-STALE` | Selected graph is absent or invalid | Start/select a valid run; do not guess. |
| `gates run` reports disabled | `gates.mode` is `disabled` | Enable gates and provide complete commands if desired. |
| Coverage reports a source file | Enforced coverage found no current mapping | Update a requirement `affected_paths`/linked test or approve a legacy waiver. |
| A hook cannot start Python | Adapter transport has no usable runtime; the guarded tool call is blocked until it is resolved | Set `AEGIS_PYTHON` or register the WAEGIS runtime. |
| Guards never seem to run | The agent was started below the repository root, so no configuration loaded | Restart the agent from the directory that holds `.agentic/`. |

## 13. Further Reading

- `WORKFLOW_CONFIGURATION.md` - complete schema, modes, and validation rules.
- `POLICY_CONFIGURATION.md` - intrinsic workflow versus repository policy.
- `COMPONENTS_CONFIGURATION.md` - component map and adoption baseline configuration.
- `CLI_API_REFERENCE.md` - command and error contracts.
- `PROMPT_CHEATSHEET.md` - operator-ready prompts.
- `.agentic/requirements/README.md` - requirement snapshot format.
