<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AEGIS CLI API Reference

This document explains the human-facing command API implemented by
`aegis/cli.py`. It is written for people who need to understand
which command to run, when it is normally used in the agentic flow, and which
workflow skills or hooks call it.

This file is the single canonical copy of the reference. It lives at
`05_Software/aegis/template/.agentic/documents/CLI_API_REFERENCE.md`
in the template repository and at `.agentic/documents/CLI_API_REFERENCE.md` in
copied target repositories.

## How To Run Commands

In a copied target repository, prefer the project-local wrapper:

```powershell
.\.agentic\tools\run.ps1 <command>
```

```bash
bash .agentic/tools/run.sh <command>
```

The wrappers call:

```text
.agentic/tools/run_aegis.py
```

That script loads the bundled CLI source from:

```text
.agentic/cli/src/aegis/cli.py
```

When the package is installed in the active Python environment, these forms are
also valid:

```powershell
aegis <command>
python -m aegis <command>
```

Examples below use `<workflow>` as a placeholder for whichever invocation form
is available in the current repository.

Commands may be run from any subdirectory of the repository: the CLI resolves
the workflow root by walking upward to the nearest directory containing
`.agentic/` (falling back to the nearest `.git`), so state is always read from
and written to the repository root — a nested `.agentic/` is never created
below an existing install.

## Runtime Requirements

- Python **3.11 or newer**, supplied by `AEGIS_PYTHON`, the packaged-WAEGIS
  registered runtime, or the system. The CLI has no third-party dependencies.
- `git` **2.30 or newer** on `PATH`. The secret scan (`INV-7`),
  `working-tree audit`, `impact`, and `delivery-preflight` shell out to `git`.
- Node **18 or newer** on `PATH` for the Claude Code, Codex, and Qwen Code
  adapters, which dispatch every guard through
  `node .agentic/tools/run_hook.mjs`. **Without it those guards cannot launch,
  and a guard that cannot launch does not block — tool calls run unchecked.**
  OpenCode runs its guard plugin in its own runtime and needs no system Node;
  Pi is installed with `npm` and therefore always has one. `waegis doctor`
  reports a missing or too-old Node as a warning rather than an error, because
  installing it afterwards makes every hook work with no repair or re-run.
- At least **1 GiB** free disk at the target, checked during deployment.
- **Start the agent from the repository root** — the directory holding
  `.agentic/`. Agent hosts locate their project configuration relative to the
  directory they were launched in; started in a subdirectory, a host finds no
  project config, registers no hooks, and runs the whole session with every
  guard silently absent. Nothing reports this: the tool calls are not blocked,
  they are simply never inspected. It happens before any hook loads, so no hook
  can detect it, and it is not fixable by changing how the hooks are addressed.
  See `.agentic/hooks/README.md`. To confirm guards are live in a session, ask
  the agent to read a path covered by an enforced
  `guardrails.protected_paths` read policy; a loaded configuration denies it.

Behavior without git:

- If the `git` executable is missing, `INV-7` (`Clean secrets`) reports
  `Could not inspect git diff for secrets` and fails closed, which blocks
  `delivery-preflight`.
- If `git status` cannot be read at all — the executable is missing, the
  directory is not a repository, or git exits non-zero for any other reason —
  `working-tree audit` records a `git-status-unavailable` blocking finding,
  which blocks `delivery-preflight`. An unreadable working tree is never
  reported as a clean one: the audit exists to prove nothing blocking is
  staged, and it cannot prove that from a status it never received.
- `impact` widens its result set from `git status` as a convenience, so an
  unreadable status simply contributes no extra paths there. The blocking
  judgement belongs to `working-tree audit` alone and is not duplicated.

Run the workflow inside a git repository. Delivery is a git operation, so
`delivery-preflight` cannot pass outside one.

## Workflow Stages

The built-in stage order is:

1. `intake`
2. `alignment`
3. `requirement`
4. `check`
5. `implementation`
6. `validation`
7. `delivery`

Adoption runs use `adoption-intake`, `adoption-alignment`, `repo-discovery`,
`component-map`, `component-adoption`, `baseline-review`, and
`adoption-delivery`.

The workflow is human-steered. Commands can be run manually, suggested by a
skill, or invoked by a hook. The CLI records state in `.agentic/`.

## Runtime Files Written By The CLI

| File | Purpose | Main writers |
| --- | --- | --- |
| `.agentic/.workspace/state/current_run` | Stores the ignored, per-worktree active run ID. | `start` |
| `.agentic/runs/<run-id>/graph.json` | Stores current stage, intent alignment, specs, checks, evidence, change units, decisions, and access mode. | `start`, `next`, `set-stage`, `set-access-mode`, `alignment`, `add-spec`, `add-check`, `record-evidence`, `record-change`, `supersede-evidence` |
| `.agentic/runs/<run-id>/journal.jsonl` | Append-only event log for workflow events and hook evidence. | `start`, `set-stage`, `set-access-mode`, `alignment`, `requirement activate`, `record-evidence`, `gates run`, `post_tool_evidence.py` |
| `.agentic/runs/<run-id>/report.md` | Human-readable delivery report. | `report` |
| `.agentic/requirements/<category>/<code>-<uuid>.toml` | One canonical current requirement snapshot. | `requirement create`, `requirement update`, `requirement activate` |

## Flow Integration Summary

| Flow step | Usual commands | Called through |
| --- | --- | --- |
| Intake | `start`, `status`, `audit traceability`, `audit coverage`, `impact` | Human prompt, `agentic-development`, `regression-traceability` |
| Intent Alignment | `alignment`, `status`, `next`, `set-stage` | `agentic-development`, `agentic-adoption`, ticket-driven orchestrators |
| Requirement | `requirement create`, `requirement show`, `requirement list`, `requirement update`, `add-spec`, `requirement activate`, `invariants`, `set-stage` | `agentic-development`, human approval |
| Check | `add-check`, `record-evidence`, `set-stage` | `agentic-development`, test authoring gate |
| Implementation | `record-evidence`, `record-change`, `gates run`, `invariants` | `agentic-development`, `write-component-documentation`, `python-codestyle-audit` |
| Validation | `gates run`, `audit traceability`, `audit coverage`, `impact`, `invariants`, `record-evidence` | `agentic-development`, `regression-traceability`, `documentation-audit`, `python-codestyle-audit` |
| Delivery | `audit traceability`, `audit coverage`, `working-tree audit`, `delivery-preflight`, `report` | `agentic-delivery`, `delivery_preflight.py` hook, human approval |
| Adoption | `start --kind adoption`, `next`, `set-stage`, `status`, `adoption component-status`, `adoption scope-check`, `adoption baseline`, `report` | `agentic-adoption`, human approval |
| Any stage | `status`, `next`, `set-stage`, `set-access-mode`, `supersede-evidence` | Human routing, skills, troubleshooting |

## Command Reference

Every CLI operation first loads and validates `.agentic/workflow.toml`. A
configuration failure exits with status `2` before the command performs its
action. `config validate --json` and `config show --effective --json` expose
the stable machine-readable configuration contract.

The graph-dependent commands below accept `--run-id <id>` on their leaf
parser: `status`, `next`, `invariants`, `report`, `delivery-preflight`,
`set-stage`, `set-access-mode`, `alignment`, `supersede-evidence`, `gates run`,
`requirement activate`, `add-spec`, `add-check`, `record-evidence`, and
`record-change`. An explicit ID wins over the per-worktree pointer and never
rewrites it. Run-resolution failures exit with status `2` and use the stable
`RUN-POINTER-*` or `RUN-ID-NOT-FOUND` contract.

Repository-wide commands reject `--run-id`: `config`, `audit`, `impact`,
`requirement create/show/list/update`, `working-tree audit`, and the read-only
`adoption` commands. `start` creates and selects a new run and also rejects an
explicit selector.

### `config validate` and `config show`

Validate the mandatory configuration or print every effective mode and active
rule collection.

```powershell
<workflow> config validate --json
<workflow> config show --effective --json
```

Both commands exit with status `2` and emit one actionable typed error when
the configuration is missing, malformed, incomplete, or inconsistent.

### `start`

Starts a new workflow run. Feature, fix, and change runs start at `intake`.
Adoption runs start at `adoption-intake`.

```powershell
<workflow> start --kind feature --statement "Add invoice export"
```

```powershell
<workflow> start --kind feature --statement "Generate client bindings" --scope-hint generated/client --scope-hint tools/codegen
```

```powershell
<workflow> start --kind change --statement "Refresh repository documentation" --access-mode repo-wide --access-reason "Human-approved broad documentation update"
```

```powershell
<workflow> start --kind adoption --statement "Adopt existing project"
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `--kind feature|fix|change|adoption` | Yes | Classifies the run intent. |
| `--statement "<text>"` | Yes | Human-readable statement of the requested work. |
| `--access-mode standard|repo-wide` | No | Defaults to `standard`. Under `stage_restricted`, `repo-wide` bypasses stage lists but not protected paths. |
| `--access-reason "<text>"` | Required for `repo-wide` | Records why broad access was approved. |
| `--scope-hint <root>` | No | Repeatable. Adds an intentional root to the INV-5 scope advisory and records it in the run intent and journal. |

Scope hints affect advisory scope evaluation only. They do not relax configured
stage write access, protected-path rules, or host filesystem permissions.

Stage: `intake` for feature, fix, and change runs; `adoption-intake` for
adoption runs.

Flow caller: human prompt, `agentic-development`, or `agentic-adoption`.

Writes:

- `.agentic/.workspace/state/current_run`
- `.agentic/runs/<run-id>/graph.json`
- `.agentic/runs/<run-id>/journal.jsonl`

### `status`

Prints the active run summary as JSON.

```powershell
<workflow> status --run-id <existing-run-id>
```

Stage: any stage.

Flow caller: human prompt, `agentic-development`, `agentic-adoption`,
`agentic-delivery`, or manual troubleshooting.

Reads:

- `.agentic/.workspace/state/current_run`
- `.agentic/runs/<run-id>/graph.json`
- configured workflow state needed for invariant checks

### `resume`

Prints a compact bootstrap brief as JSON so a fresh session continues an
existing run without prior chat context. The brief reports the current stage and
computed next stage, the intent and recorded alignment, spec items, checks,
recent active evidence, the run's cited requirements resolved with their
`spec_ref`, and a short guidance line. It is read-only and writes no state.

```powershell
<workflow> resume --run-id <existing-run-id>
```

Stage: any stage. Run it first when opening a new session on an in-progress run.

Flow caller: human prompt or `agentic-development` Stage 0 resume.

Reads:

- `.agentic/.workspace/state/current_run`
- `.agentic/runs/<run-id>/graph.json`
- cited requirement snapshots under `.agentic/requirements/` and their `spec_ref`

### `next`

Moves the active run to the next built-in stage.

```powershell
<workflow> next --run-id <existing-run-id>
```

Stage: any stage except the final stage for that run kind. When already in
`delivery`, the command keeps a normal run at `delivery`. When already in
`adoption-delivery`, the command keeps an adoption run at `adoption-delivery`.
When `[alignment].enabled = false`, `next` skips `alignment` and
`adoption-alignment`.

Flow caller: human approval or a skill after a gate summary, including
`agentic-adoption` during adoption stages.

Writes:

- `.agentic/runs/<run-id>/graph.json`
- `.agentic/runs/<run-id>/journal.jsonl`

### `set-stage`

Routes the active run to a specific stage and records the human-approved reason.

```powershell
<workflow> set-stage requirement --run-id <existing-run-id> --reason "Human requested a requirement revision"
```

```powershell
<workflow> set-stage check --run-id <existing-run-id> --reason "Human approved writing the failing tests"
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `stage` | Yes | One of `intake`, `requirement`, `check`, `implementation`, `validation`, `delivery`. |
| `--reason "<text>"` | Yes | Why the workflow is being routed. |

Stage: any stage.

Flow caller: human approval, `agentic-development`, `agentic-adoption`, or
recovery from a failed later gate.

Writes:

- `graph.json` stage
- `graph.json` decisions
- `journal.jsonl` `stage.set` event

### `set-access-mode`

Switches the active run between standard write-zone mode and repo-wide mode.

```powershell
<workflow> set-access-mode repo-wide --reason "Human approved broad maintenance across documentation and tooling"
```

```powershell
<workflow> set-access-mode standard --reason "Broad maintenance is complete"
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `access_mode` | Yes | `standard` or `repo-wide`. |
| `--reason "<text>"` | Yes | Why the access mode changed. |

Stage: any stage.

Flow caller: human approval, `agentic-development`, or `agentic-adoption`.

Used by hook: `guard_write_zone.py` reads the resulting `access_mode` from
`graph.json` before allowing or denying edits.

Writes:

- `graph.json` access mode
- `graph.json` decisions
- `journal.jsonl` `access_mode.set` event

### `alignment`

Records the agent's structured understanding before requirement/spec work or
adoption discovery proceeds.

```powershell
<workflow> alignment --source "human prompt" --understanding "Add invoice export for approved batches." --scope "in: export command; out: billing model changes" --acceptance "A CSV export can be generated from the command line." --risk low --decision proceed --reason "No open questions and low blast radius"
```

```powershell
<workflow> alignment --source "human prompt" --understanding "Add a CSV invoice export." --scope "in: export command" --acceptance "A focused export check passes." --question "Should CSV or JSON be the first format?" --recommended-response "Use CSV as the default because the prompt names spreadsheet-style export." --risk low --decision proceed --reason "Question has a recorded recommended response for automated continuation"
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `--source "<ref>"` | Yes | Human prompt, ticket id, URL, or other origin reference. |
| `--understanding "<text>"` | Yes | One-paragraph restatement of the requested work. |
| `--scope "<text>"` | Yes | Repeatable. In-scope and out-of-scope boundaries. |
| `--assumption "<text>"` | No | Repeatable. Assumptions used to disambiguate. |
| `--acceptance "<text>"` | Yes | Repeatable. Acceptance criteria the run will target. |
| `--question "<text>"` | No | Repeatable. Open questions whose answers change implementation. |
| `--recommended-response "<text>"` | No | Repeatable. Recommended answers the agent will assume for automated continuation. |
| `--risk low|medium|high` | Yes | Agent-assessed risk and blast radius. |
| `--decision proceed|pause` | Yes | Whether the run may continue from alignment. |
| `--reason "<text>"` | Yes | One-line rationale for the decision. |
| `--planned-path <path>` | No | Repeatable. Expected touched path used by protected-scope policy. |

Stage: `alignment` or `adoption-alignment`.

Flow caller: `agentic-development`, `agentic-adoption`, or a ticket-driven
orchestrator before requirement/spec work.

Policy:

- `decision proceed` is accepted only when `.agentic/workflow.toml`
  `[alignment]` allows it.
- Open questions require `pause` when `pause_on_open_questions = true` unless
  `allow_recommended_responses = true` and each question has a recorded
  recommended response.
- Risk at or above `risk_threshold` requires `pause`.
- Planned paths matching `protected_scope_patterns` require `pause`.
- The command records alignment only; it does not move the run to the next stage.

Writes:

- `graph.json` latest `alignment`
- `journal.jsonl` `alignment.recorded` event

### `add-spec`

Adds a run-local behavior or property spec item to `graph.json`.

```powershell
<workflow> add-spec --id SPEC-001 --tag behavior --statement "The export command writes one CSV file per invoice batch."
```

```powershell
<workflow> add-spec --id SPEC-002 --tag property --statement "The export is deterministic for the same input files." --example "Same input produces byte-identical output"
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `--id <id>` | Yes | Run-local spec id. |
| `--tag behavior|property` | Yes | Whether the spec is behavior-oriented or property-oriented. |
| `--statement "<text>"` | Yes | The spec statement. |
| `--status proposed|accepted|realized|retired` | No | Defaults to `accepted`. |
| `--example "<text>"` | No | Repeatable. Adds examples to the spec item. |
| `--threshold "<text>"` | No | Optional measurable threshold. |

Stage: `requirement`.

Flow caller: `agentic-development` after intake and human clarification.

Writes:

- `graph.json` `spec_items`

Exit behavior: raises `Spec id already exists: <id>` without changing the graph
when the active run already contains that spec id.

### `add-check`

Adds a run-local check or test expectation to `graph.json`.

```powershell
<workflow> add-check --id CHECK-001 --level test --cites-spec SPEC-001 --cites-requirement <requirement-id> --command "python -m pytest tests/test_export.py::test_invoice_export" --path tests/test_export.py --state red
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `--id <id>` | Yes | Run-local check id. |
| `--level <level>` | No | Defaults to `test`. |
| `--cites-spec <id>` | Yes | Repeatable. Links the check to one or more spec ids. |
| `--cites-requirement <id>` | No | Repeatable. Links to durable requirement ids. |
| `--command "<command>"` | No | Command that runs the check. |
| `--path <path>` | No | File path for the check. |
| `--state red|green|unknown` | No | Defaults to `unknown`. |

Stage: `check`.

Flow caller: `agentic-development` during the red-before-green check gate.

Writes:

- `graph.json` `checks`

Exit behavior: raises `Check id already exists: <id>` without changing the graph
when the active run already contains that check id.

### `record-evidence`

Records evidence for the active run. Evidence can represent tests, gates,
scans, diffs, decisions, or notes.

```powershell
<workflow> record-evidence --kind test-run --result fail --stage check --check-id CHECK-001 --summary "New export test fails before implementation." --command "python -m pytest tests/test_export.py::test_invoice_export"
```

```powershell
<workflow> record-evidence --kind test-run --result pass --stage implementation --check-id CHECK-001 --summary "Invoice export test passes after implementation." --command "python -m pytest tests/test_export.py::test_invoice_export"
```

```powershell
<workflow> record-evidence --kind scan --result pass --stage validation --summary "Traceability audit passed." --command "<workflow> audit traceability"
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `--kind test-run|diff|scan|gate|decision|note` | Yes | Evidence category. |
| `--result pass|fail|info` | Yes | Evidence result. |
| `--status active|superseded` | No | Defaults to `active`. |
| `--failure-kind <text>` | No | Optional failure classification. |
| `--summary "<text>"` | Yes | Human-readable evidence summary. |
| `--command "<command>"` | No | Command that produced the evidence. |
| `--path <path>` | No | Related output or artifact path. |
| `--stage <stage>` | No | Defaults to the current graph stage. |
| `--check-id <id>` | No | Links evidence to a check and updates red/green state. |

Stage: check, implementation, validation, or delivery.

Flow caller: `agentic-development`, `agentic-delivery`, or manual evidence
repair.

Writes:

- `graph.json` `evidence`
- `graph.json` linked check state when `--check-id` is provided
- `journal.jsonl` `evidence.recorded` event

Report behavior: when `--failure-kind` is set, `report` renders it after the
result, for example ``test-run/fail (env): summary``. Evidence without a failure
classification keeps the existing ``kind/result: summary`` format.

### `record-change`

Records the paths touched by an implementation change.

```powershell
<workflow> record-change --id CU-001 --path src/exporter.py --path tests/test_export.py --path .agentic/knowledge/components/Exporter.md
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `--id <id>` | Yes | Run-local change unit id. |
| `--path <path>` | Yes | Repeatable. A touched path, repository-relative or absolute inside the repository. |

Paths are normalized to repository-relative form before they are stored, and
repeated spellings of the same path are stored once, so scope and component
checks compare recorded paths against repository-relative globs consistently.
A path that resolves outside the repository is refused: the command exits
without recording anything and names the offending path.

Stage: `implementation`, sometimes `validation` if change units are recorded
after final cleanup.

Flow caller: `agentic-development`.

Writes:

- `graph.json` `change_units`

Each current change-unit record contains only its id and touched paths. The
graph loader remains compatible with older files: it ignores a legacy
`change_units[].evidence` key and the retired top-level `defects` collection.

### `supersede-evidence`

Marks older evidence as superseded by newer evidence while keeping both records
in history.

```powershell
<workflow> supersede-evidence --id E-0002 --by E-0005 --reason "The first failure was caused by a missing local dependency; the rerun passed after environment repair."
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `--id <old-evidence-id>` | Yes | Evidence to mark as superseded. |
| `--by <new-evidence-id>` | Yes | Evidence that supersedes the old record. |
| `--reason "<text>"` | Yes | Why superseding is valid. |

Stage: any stage, often validation or delivery.

Flow caller: human-approved repair, `agentic-development`, or
`agentic-delivery`.

Writes:

- `graph.json` old evidence status and supersede fields
- `graph.json` decisions
- `journal.jsonl` `evidence.superseded` event

### `requirement create`

Creates one independent `Planned` UUIDv4-backed TOML snapshot and returns its
ID, repository-relative path, and complete record as JSON.

```powershell
<workflow> requirement create --category functional --priority Must --requirement "Invoice export writes CSV." --rationale "Operators need portable exports." --verification "Inspection: inspect the exported CSV" --spec-ref .agentic/requirements/functional/invoice_export.spec.md --affected-path src/exporter.py
```

`--spec-ref` is optional and names a repository-relative companion spec file
(no globs) holding the concrete data structures, interface formats, dialog text,
and worked examples for the behavior. When supplied, the file must already exist
or the create is rejected. The command never accepts a caller-supplied ID,
status, or run selector and never edits a shared counter or register.

### `requirement show` and `requirement list`

Read canonical current snapshots without resolving a run or writing a journal.

```powershell
<workflow> requirement show --id <requirement-id> --json
<workflow> requirement list --category functional --status Planned --json
```

`--json` is required. Lists are ordered by ID.

### `requirement update`

Applies atomic partial scalar changes and complete replacement semantics for
linked tests and affected paths.

```powershell
<workflow> requirement update --id <requirement-id> --priority Should --linked-test tests/test_export.py::test_invoice_export --affected-path src/exporter.py
```

Omitted collections remain unchanged. Supplied repeatable values replace the
complete set; `--clear-linked-tests` and `--clear-affected-paths` explicitly
replace their set with empty. `--spec-ref <path>` sets the companion spec
reference (the file must exist) and `--clear-spec-ref` removes it; the two are
mutually exclusive. At least one update option is required. The ID, category,
schema version, and creation date are immutable.

### `requirement activate`

Atomically changes one current snapshot to `Active`, replaces its complete
linked-test set, updates verification, and journals the result to the selected
run.

```powershell
<workflow> requirement activate --run-id <existing-run-id> --id <requirement-id> --linked-test tests/test_export.py::test_invoice_export --verification "Automated test"
```

```powershell
<workflow> requirement activate --id <requirement-id> --verification "Inspection: inspect generated documentation"
```

Every supplied selector is resolved before the TOML file is replaced. An empty
selector set is accepted only when verification begins with `Manual:` or
`Inspection:` and contains non-empty method text. `--run-id` is optional and
uses the explicit-first selection contract.

Writes:

- `.agentic/requirements/<category>/<code>-<uuid>.toml`
- the selected run's `journal.jsonl` `requirement.activated` event

### `audit traceability`

Validates canonical requirement snapshots and their current linked-test sets.
Every non-Retired requirement (`Planned` or `Active`) must resolve at least one
linked test or declare an explicit `Manual:`/`Inspection:` verification method;
one that has neither is reported as `REQ-NO-VERIFICATION`. Unresolvable selectors
are reported as `REQ-LINK-MISSING`. Retired requirements are exempt. Delivery
preflight blocks on any of these findings.

```powershell
<workflow> audit traceability
```

Stage: intake, validation, and delivery.

Flow caller: `agentic-development`, `regression-traceability`, and
`agentic-delivery`.

Reads:

- `.agentic/workflow.toml`
- `.agentic/requirements/<category>/*.toml`
- configured test roots

Exit behavior: exits with non-zero status when audit issues exist.

### `audit coverage`

Checks whether coverable source files have requirement coverage or a waiver.

```powershell
<workflow> audit coverage
```

Stage: intake, validation, and delivery.

Flow caller: `agentic-development`, `regression-traceability`, and
`agentic-delivery`.

Reads:

- `.agentic/workflow.toml`
- `.agentic/requirements/<category>/*.toml`
- `.agentic/requirements/coverage_waivers.txt`
- configured coverable source roots

Exit behavior: exits with non-zero status when coverage issues exist.

### `impact`

Maps changed or planned files to impacted requirements and linked tests. When no
files are provided, it uses the shared Git-status parser also used by
`working-tree audit`. A rename contributes both its current and previous path;
quoted Git paths are decoded consistently by both commands.

```powershell
<workflow> impact src/exporter.py tests/test_export.py
```

```powershell
<workflow> impact --json
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `files` | No | One or more changed/planned paths. |
| `--json` | No | Prints machine-readable JSON instead of text. |

Stage: intake, validation, and delivery.

Flow caller: `agentic-development`, `regression-traceability`, and
`agentic-delivery`.

Reads:

- durable requirements
- configured coverable roots
- Git working set when no paths are passed

### `working-tree audit`

Reports working-tree findings that matter for delivery. Arbitrary untracked
human files are advisory unless they match configured protected paths,
working-tree blockers, adoption source-change policy, or secret patterns.

```powershell
<workflow> working-tree audit
```

Stage: delivery, sometimes validation.

Flow caller: `agentic-delivery`.

Reads:

- Git working tree status
- `.agentic/workflow.toml` `[guardrails.working_tree]`,
  `[guardrails.protected_paths]`, `[guardrails.secrets]`, and
  `[adoption.source_changes]` policies

Exit behavior: exits with non-zero status when blocking findings exist.

### `adoption component-status`

Prints the configured component manifest as JSON, including component and bundle
data.

```powershell
<workflow> adoption component-status
```

Stage: adoption intake, component map, component adoption, or manual adoption
review.

Flow caller: `agentic-adoption` or human adoption review.

Reads:

- `.agentic/workflow.toml` `[components]` manifest configuration
- configured component manifest, normally `.agentic/components.toml`

Exit behavior: exits zero after printing JSON.

### `adoption scope-check`

Checks one or more repository-relative paths against the configured component
baseline rules. Paths mapped to a component below the required baseline are
blocking. Unmapped paths are reported as informational and do not block.

```powershell
<workflow> adoption scope-check src/billing/invoice.py
```

```powershell
<workflow> adoption scope-check src/billing/invoice.py docs/billing.md
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `path` | Yes | First repository-relative path to check. |
| `additional-path` | No | Repeatable. Additional repository-relative paths to check. |

Stage: adoption review, intake impact review, or before behavior-changing work.

Flow caller: `agentic-adoption`, human adoption review, or feature/fix scope
review before behavior-changing work.

Reads:

- `.agentic/workflow.toml` `[components]` and `[adoption]` configuration
- configured component manifest, normally `.agentic/components.toml`

Exit behavior: exits with status `1` when a blocking component baseline issue
exists. Exits zero when all mapped paths meet the baseline or only informational
unmapped-path findings are reported.

### `adoption baseline`

Prints a concise Markdown summary of configured component and bundle baseline
status.

```powershell
<workflow> adoption baseline
```

Stage: adoption review, baseline review, or manual status reporting.

Flow caller: `agentic-adoption` or human adoption review.

Reads:

- `.agentic/workflow.toml` `[components]` manifest configuration
- configured component manifest, normally `.agentic/components.toml`

Exit behavior: exits zero after printing Markdown.

### `gates run`

Runs configured validation gate commands from `.agentic/workflow.toml`.

```powershell
<workflow> gates run --run-id <existing-run-id>
```

```powershell
<workflow> gates run --run-id <existing-run-id> --name test --name lint --timeout 600
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `run` | Yes | The only supported gates action. |
| `--run-id <id>` | No | Explicit run selection; otherwise uses the local pointer. |
| `--name <gate>` | No | Repeatable. Runs only the selected `test` or `lint` gate; any other name is rejected. |
| `--timeout <seconds>` | No | Defaults to `300`. |

Stage: validation, sometimes implementation when checking a focused change.

Flow caller: `agentic-development`, `python-codestyle-audit`, or
`agentic-delivery`.

Reads:

- `.agentic/workflow.toml` `[gates]`

Writes:

- `graph.json` gate evidence
- `journal.jsonl` `gate.output` events

Exit behavior: exits with the failing gate command status when a configured
command fails.

### `invariants`

Evaluates workflow invariants against the active run.

```powershell
<workflow> invariants --run-id <existing-run-id>
```

Stage: after every gate, especially requirement, validation, and delivery.

Flow caller: `agentic-development`, `agentic-adoption`, and
`agentic-delivery`.

Reads:

- active run graph
- durable requirements
- configured workflow roots

Exit behavior: exits with non-zero status when blocking invariant failures
exist.

### `delivery-preflight`

Runs the deterministic delivery readiness checks.

```powershell
<workflow> delivery-preflight --run-id <existing-run-id>
```

Stage: delivery.

Flow caller: `agentic-delivery`, human approval flow, and
`.agentic/hooks/delivery_preflight.py`.

Checks:

- invariants
- traceability audit
- coverage audit
- component audit
- working-tree audit

Exit behavior: exits with non-zero status if any blocking finding exists. A
passing result still requires explicit human approval before PR, push, merge,
or publish.

### `report`

Writes and prints the human-readable workflow report.

```powershell
<workflow> report --run-id <existing-run-id>
```

Stage: delivery.

Flow caller: `agentic-delivery` or `agentic-adoption` after final adoption
review, delivery preflight, or remaining risks are understood.

Writes:

- `.agentic/runs/<run-id>/report.md`

## Hook Integration

These six standalone hook scripts are the runtime source of truth and are
reused unchanged by all five agent adapters. Shell commands run the shell-write
guard (`guard_shell_write.py`), which applies the same write-zone and
protected-path policy to file writes performed through the shell, alongside the
secret scan and delivery preflight:

- **Codex** wires them through `.codex/hooks.json` (PreToolUse / PostToolUse
  command hooks); edit inputs run both the write-zone guard and secret scan,
  and shell input runs the shell-write guard, secret scan, and delivery
  preflight. Codex reads through its shell tool, so its reads are covered by the
  command guards rather than a separate read matcher.
- **Claude Code** wires them through `.claude/settings.json` (matching hook
  bindings plus the protected-read guard on `Read` / `Grep` / `Glob`); edit
  inputs run both the write-zone guard and secret scan.
- **Qwen Code** wires them through `.qwen/settings.json`; `WriteFile` / `Edit`
  inputs run both the write-zone guard and secret scan, Bash input also runs
  the shell-write guard and delivery preflight, and the read, search, glob, and
  directory-listing tools run the protected-read guard. See `.qwen/README.md`.
- **Pi** wires them through the `.pi/` bridge extension, which maps Pi
  `tool_call` / `tool_result` events onto the same JSON-on-stdin hook protocol.
  It passes full write/edit input to `secret_scan.py`, runs the shell-write
  guard on `bash` commands, and its `read`, `grep`, `find`, and `ls` tools run
  `guard_read_path.py`. See `.pi/README.md`.
- **OpenCode** wires them through `.opencode/plugins/agentic-guard.mjs`, which
  maps `tool.execute.before` / `tool.execute.after` events onto the same
  JSON-on-stdin hook protocol. The plugin also scans write/edit content for
  secrets, runs the shell-write guard on `bash` commands, and runs the
  protected-read guard on its `read`, `grep`, `glob`, and `list` tools. See
  `.opencode/README.md`.

Each adapter transport fails closed: because the shared guards always exit 0 and
signal a denial on stdout, a guard that cannot run — a missing or unlaunchable
Python interpreter, or a hook that crashed — is treated as a block, not an
allow.

### `guard_write_zone.py`

Hook path:

```text
.agentic/hooks/guard_write_zone.py
```

When it runs: before edit tools.

What it reads:

- `.agentic/.workspace/state/current_run`
- `.agentic/runs/<run-id>/graph.json`
- `.agentic/workflow.toml`

What it does: allows or denies file edits from the validated write-access and
protected-path policies. Unrestricted write access does not resolve a run;
stage-restricted access resolves stage and access mode through the shared
workspace-state API.

If stage-restricted access has no valid active run, the hook denies with the
stable `RUN-POINTER-*` code and remediation. It never guesses an intake stage
or reads the retired `.agentic/current_run` path.

Related CLI commands:

- `start`
- `next`
- `set-stage`
- `set-access-mode`

### `guard_read_path.py`

Hook path:

```text
.agentic/hooks/guard_read_path.py
```

When it runs: before the read, content-search, glob, and directory-listing
tools on every adapter that exposes them (a host's read, grep, glob, and
find/list tools).

What it reads: the validated `.agentic/workflow.toml`
`[guardrails.protected_paths]` policy, applied only when `read` is a configured
operation.

What it does: denies access to a configured protected path whether the agent
targets it through the single-file read tool or through a content-search, glob,
or listing tool — so a protected path cannot be reached by asking a host for the
same bytes through its grep, or the same file names through its glob or listing
tool, instead of its read tool. A search that names no path — a
repository-wide grep — is allowed, because no pre-tool hook can rewrite tool
output; the guard blocks a protected path from being *targeted*, not every
search that might incidentally surface a line from one. When the policy is
`disabled` or does not list `read`, it returns an explicit allow. Configuration
and path failures become actionable hook denials; there are no built-in
protected paths or permissive fallbacks.

Related CLI commands: none directly; the protected-read policy comes from
`.agentic/workflow.toml`.

### `post_tool_evidence.py`

Hook path:

```text
.agentic/hooks/post_tool_evidence.py
```

When it runs: after agent tool use when an active run exists.

What it writes:

- `.agentic/runs/<run-id>/journal.jsonl`

What it records: tool name, tool use id, timestamp, and whether a tool response
was present.

### `delivery_preflight.py`

Hook path:

```text
.agentic/hooks/delivery_preflight.py
```

When it runs: before publish-like shell commands such as `git push`,
`gh pr create`, `gh pr merge`, or `git merge`.

What it calls:

```powershell
node .agentic/tools/run_hook.mjs .agentic/tools/run_aegis.py delivery-preflight
```

What it does: denies the publish-like command when delivery preflight fails.

### `secret_scan.py`

Hook path:

```text
.agentic/hooks/secret_scan.py
```

When it runs: before shell commands and edit/write tools on every supported
adapter.

What it reads: tool input plus the validated
`.agentic/workflow.toml` `[guardrails.secrets]` policy.

What it does: when mode is `enforce`, scans tool input using only configured
regular expressions and denies the operation when a possible secret appears.
When mode is `disabled`, it returns an explicit allow result. Missing or invalid
configuration is an actionable deny with the shared `CONFIG-*` code and
remediation; there are no built-in secret rules or permissive fallbacks.

Related CLI commands: none directly, but it protects the same workflow surface.

## Typical Full Flow

```powershell
<workflow> config validate --json
<workflow> config show --effective --json
<workflow> start --kind feature --statement "Add invoice export"
<workflow> audit traceability
<workflow> audit coverage
<workflow> impact src/exporter.py tests/test_export.py
<workflow> next
<workflow> alignment --source "human prompt" --understanding "Add invoice export." --scope "in: exporter command; out: invoice model changes" --acceptance "Invoice export writes a CSV file." --risk low --decision proceed --reason "No open questions and low risk"
<workflow> requirement list --category functional --json
<workflow> requirement create --category functional --priority Must --requirement "Invoice export writes a CSV file." --rationale "Operators need portable exports." --verification "Automated test" --affected-path src/exporter.py
<workflow> add-spec --id SPEC-001 --tag behavior --statement "Invoice export writes a CSV file."
<workflow> add-check --id CHECK-001 --cites-spec SPEC-001 --cites-requirement <requirement-id> --command "python -m pytest tests/test_export.py::test_invoice_export" --path tests/test_export.py --state red
<workflow> record-evidence --kind test-run --result fail --stage check --check-id CHECK-001 --summary "Export test fails before implementation." --command "python -m pytest tests/test_export.py::test_invoice_export"
<workflow> set-stage implementation --reason "Human approved implementation after red check"
<workflow> record-evidence --kind test-run --result pass --stage implementation --check-id CHECK-001 --summary "Export test passes after implementation." --command "python -m pytest tests/test_export.py::test_invoice_export"
<workflow> record-change --id CU-001 --path src/exporter.py --path tests/test_export.py
<workflow> requirement update --id <requirement-id-returned-by-create> --linked-test tests/test_export.py::test_invoice_export --affected-path src/exporter.py
<workflow> set-stage validation --reason "Implementation is ready for validation"
<workflow> gates run --name test
<workflow> requirement activate --id <requirement-id-returned-by-create> --linked-test tests/test_export.py::test_invoice_export --verification "Automated test"
<workflow> audit traceability
<workflow> audit coverage
<workflow> set-stage delivery --reason "Validation passed and human approved delivery preparation"
<workflow> delivery-preflight
<workflow> report
```

After this sequence, the human still must explicitly approve any commit, push,
pull request, merge, or publish action.
