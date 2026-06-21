<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Agentic Workflow CLI API Reference

This document explains the human-facing command API implemented by
`agentic_workflow/cli.py`. It is written for people who need to understand
which command to run, when it is normally used in the agentic flow, and which
workflow skills or hooks call it.

This file is the single canonical copy of the reference. It lives at
`04_Software/agentic-workflow-template/template/CLI_API_REFERENCE.md` in the
template repository and is delivered verbatim into target repositories when the
template is copied.

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
.agentic/tools/run_agentic_workflow.py
```

That script loads the bundled CLI source from:

```text
.agentic/cli/src/agentic_workflow/cli.py
```

When the package is installed in the active Python environment, these forms are
also valid:

```powershell
agentic-workflow <command>
python -m agentic_workflow <command>
```

Examples below use `<workflow>` as a placeholder for whichever invocation form
is available in the current repository.

## Runtime Requirements

- Python 3.11 or newer. The CLI has no third-party runtime dependencies.
- `git` on `PATH`. The secret scan (`INV-7`), `working-tree audit`, `impact`,
  and `delivery-preflight` shell out to `git`.

Degraded behavior without git:

- If the `git` executable is missing, `INV-7` (`Clean secrets`) reports
  `Could not inspect git diff for secrets` and fails closed, which blocks
  `delivery-preflight`.
- If the directory is not a git repository, the git-based scans see no changes:
  `impact` and `working-tree audit` return nothing and `INV-7` finds nothing to
  scan. These checks no-op rather than protect, so run the workflow inside a git
  repository.

## Workflow Stages

The built-in stage order is:

1. `intake`
2. `requirement`
3. `check`
4. `implementation`
5. `validation`
6. `delivery`

The workflow is human-steered. Commands can be run manually, suggested by a
skill, or invoked by a hook. The CLI records state in `.agentic/`.

## Runtime Files Written By The CLI

| File | Purpose | Main writers |
| --- | --- | --- |
| `.agentic/current_run` | Stores the active run id. | `start` |
| `.agentic/runs/<run-id>/graph.json` | Stores current stage, intent, specs, checks, evidence, change units, decisions, and access mode. | `start`, `next`, `set-stage`, `set-access-mode`, `add-spec`, `add-check`, `record-evidence`, `record-change`, `supersede-evidence` |
| `.agentic/runs/<run-id>/journal.jsonl` | Append-only event log for workflow events and hook evidence. | `start`, `set-stage`, `set-access-mode`, `requirement activate`, `record-evidence`, `gates run`, `post_tool_evidence.py` |
| `.agentic/runs/<run-id>/report.md` | Human-readable delivery report. | `report` |
| `.agentic/requirements/*.md` | Durable requirement registers. | Human/agent edits, `requirement activate` |
| `.agentic/registry/requirements.json` | Requirement registry cache. | `registry sync` |
| `.agentic/registry/checks.json` | Requirement-to-check registry cache. | `registry sync` |
| `.agentic/registry/features.json` | Active feature/run summary cache. | `registry sync` |

## Flow Integration Summary

| Flow step | Usual commands | Called through |
| --- | --- | --- |
| Intake | `start`, `status`, `audit traceability`, `audit coverage`, `impact` | Human prompt, `agentic-development`, `regression-traceability` |
| Requirement | `add-spec`, `requirement activate`, `invariants`, `set-stage` | `agentic-development`, human approval |
| Check | `add-check`, `record-evidence`, `set-stage` | `agentic-development`, test authoring gate |
| Implementation | `record-evidence`, `record-change`, `gates run`, `invariants` | `agentic-development`, `write-component-documentation`, `python-codestyle-audit` |
| Validation | `gates run`, `audit traceability`, `audit coverage`, `impact`, `invariants`, `record-evidence` | `agentic-development`, `regression-traceability`, `documentation-audit`, `python-codestyle-audit` |
| Delivery | `registry sync`, `registry audit`, `working-tree audit`, `delivery-preflight`, `report` | `agentic-delivery`, `delivery_preflight.py` hook, human approval |
| Any stage | `status`, `next`, `set-stage`, `set-access-mode`, `supersede-evidence` | Human routing, skills, troubleshooting |

## Command Reference

### `start`

Starts a new workflow run at the `intake` stage.

```powershell
<workflow> start --kind feature --statement "Add invoice export"
```

```powershell
<workflow> start --kind change --statement "Refresh repository documentation" --access-mode repo-wide --access-reason "Human-approved broad documentation update"
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `--kind feature|fix|change` | Yes | Classifies the run intent. |
| `--statement "<text>"` | Yes | Human-readable statement of the requested work. |
| `--access-mode standard|repo-wide` | No | Defaults to `standard`. `repo-wide` relaxes stage write zones for normal repo files. |
| `--access-reason "<text>"` | Required for `repo-wide` | Records why broad access was approved. |

Stage: `intake`.

Flow caller: human prompt or `agentic-development`.

Writes:

- `.agentic/current_run`
- `.agentic/runs/<run-id>/graph.json`
- `.agentic/runs/<run-id>/journal.jsonl`

### `status`

Prints the active run summary as JSON.

```powershell
<workflow> status
```

Stage: any stage.

Flow caller: human prompt, `agentic-development`, `agentic-delivery`, or
manual troubleshooting.

Reads:

- `.agentic/current_run`
- `.agentic/runs/<run-id>/graph.json`
- configured workflow state needed for invariant checks

### `next`

Moves the active run to the next built-in stage.

```powershell
<workflow> next
```

Stage: any stage except the final `delivery` stage. When already in `delivery`,
the command keeps the stage at `delivery`.

Flow caller: human approval or a skill after a gate summary.

Writes:

- `.agentic/runs/<run-id>/graph.json`
- `.agentic/runs/<run-id>/journal.jsonl`

### `set-stage`

Routes the active run to a specific stage and records the human-approved reason.

```powershell
<workflow> set-stage requirement --reason "Human requested a requirement revision"
```

```powershell
<workflow> set-stage check --reason "Human approved writing the failing tests"
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `stage` | Yes | One of `intake`, `requirement`, `check`, `implementation`, `validation`, `delivery`. |
| `--reason "<text>"` | Yes | Why the workflow is being routed. |

Stage: any stage.

Flow caller: human approval, `agentic-development`, or recovery from a failed
later gate.

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

Flow caller: human approval or `agentic-development`.

Used by hook: `guard_write_zone.py` reads the resulting `access_mode` from
`graph.json` before allowing or denying edits.

Writes:

- `graph.json` access mode
- `graph.json` decisions
- `journal.jsonl` `access_mode.set` event

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

### `add-check`

Adds a run-local check or test expectation to `graph.json`.

```powershell
<workflow> add-check --id CHECK-001 --level test --cites-spec SPEC-001 --cites-requirement REQ-FUNC-001 --command "python -m pytest tests/test_export.py::test_invoice_export" --path tests/test_export.py --state red
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

### `record-change`

Records the paths touched by an implementation change.

```powershell
<workflow> record-change --id CU-001 --path src/exporter.py --path tests/test_export.py --path 05_SoftwareDocu/Exporter.md
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `--id <id>` | Yes | Run-local change unit id. |
| `--path <path>` | Yes | Repeatable. A touched path. |

Stage: `implementation`, sometimes `validation` if change units are recorded
after final cleanup.

Flow caller: `agentic-development`.

Writes:

- `graph.json` `change_units`

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

### `requirement activate`

Updates a durable requirement row from `Planned` to `Active`, adds linked tests,
updates verification text, and refreshes the row timestamp.

```powershell
<workflow> requirement activate --id REQ-FUNC-001 --linked-test tests/test_export.py::test_invoice_export --verification "Automated pytest coverage"
```

```powershell
<workflow> requirement activate --id REQ-DOC-001 --verification "Manual inspection of generated documentation"
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `--id <requirement-id>` | Yes | Durable requirement id. |
| `--linked-test <test-id>` | Required unless verification is manual | Repeatable. Adds exact linked test ids. |
| `--verification "<method>"` | Yes | Verification method. Manual verification text is allowed. |

Stage: usually requirement after approval, or validation/delivery after checks
have passed and a planned requirement needs activation.

Flow caller: `agentic-development`, `regression-traceability`, or
`agentic-delivery`.

Writes:

- `.agentic/requirements/*.md`
- `journal.jsonl` `requirement.activated` event

### `audit traceability`

Validates durable requirement rows and linked tests.

```powershell
<workflow> audit traceability
```

Stage: intake, validation, and delivery.

Flow caller: `agentic-development`, `regression-traceability`, and
`agentic-delivery`.

Reads:

- `.agentic/workflow.toml`
- `.agentic/requirements/*.md`
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
- `.agentic/requirements/*.md`
- `.agentic/requirements/coverage_waivers.txt`
- configured coverable source roots

Exit behavior: exits with non-zero status when coverage issues exist.

### `impact`

Maps changed or planned files to impacted requirements and linked tests. When no
files are provided, it uses the Git working set.

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

### `registry sync`

Refreshes JSON registry caches from durable requirement registers and the active
run graph.

```powershell
<workflow> registry sync
```

Stage: delivery, sometimes validation.

Flow caller: `agentic-delivery` and `regression-traceability`.

Writes:

- `.agentic/registry/requirements.json`
- `.agentic/registry/checks.json`
- `.agentic/registry/features.json`

### `registry audit`

Validates that registry cache files exist and contain valid JSON.

```powershell
<workflow> registry audit
```

Stage: delivery.

Flow caller: `agentic-delivery`.

Reads:

- `.agentic/registry/requirements.json`
- `.agentic/registry/checks.json`
- `.agentic/registry/features.json`

Exit behavior: exits with non-zero status when registry files are missing or
invalid.

### `working-tree audit`

Reports working-tree findings that matter for delivery. Arbitrary untracked
human files are advisory by default; protected paths and configured blocked
patterns are blocking.

```powershell
<workflow> working-tree audit
```

Stage: delivery, sometimes validation.

Flow caller: `agentic-delivery`.

Reads:

- Git working tree status
- `.agentic/workflow.toml` `[working_tree]` configuration

Exit behavior: exits with non-zero status when blocking findings exist.

### `gates run`

Runs configured validation gate commands from `.agentic/workflow.toml`.

```powershell
<workflow> gates run
```

```powershell
<workflow> gates run --name test --name lint --timeout 600
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `run` | Yes | The only supported gates action. |
| `--name <gate>` | No | Repeatable. Runs selected configured gates only. |
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
<workflow> invariants
```

Stage: after every gate, especially requirement, validation, and delivery.

Flow caller: `agentic-development` and `agentic-delivery`.

Reads:

- active run graph
- durable requirements
- configured workflow roots

Exit behavior: exits with non-zero status when blocking invariant failures
exist.

### `delivery-preflight`

Runs the deterministic delivery readiness checks.

```powershell
<workflow> delivery-preflight
```

Stage: delivery.

Flow caller: `agentic-delivery`, human approval flow, and
`.agentic/hooks/delivery_preflight.py`.

Checks:

- invariants
- traceability audit
- coverage audit
- registry audit
- working-tree audit

Exit behavior: exits with non-zero status if any blocking finding exists. A
passing result still requires explicit human approval before PR, push, merge,
or publish.

### `report`

Writes and prints the human-readable workflow report.

```powershell
<workflow> report
```

Stage: delivery.

Flow caller: `agentic-delivery` after delivery preflight passes or after
remaining risks are understood.

Writes:

- `.agentic/runs/<run-id>/report.md`

## Hook Integration

These four standalone hook scripts are the runtime source of truth and are
reused unchanged by all three agent adapters:

- **Codex** wires them through `.codex/hooks.json` (PreToolUse / PostToolUse
  command hooks).
- **Claude Code** wires them through `.claude/settings.json` (matching hook
  bindings plus protected-path Read/Edit/Write denies).
- **Pi** wires them through the `.pi/` bridge extension, which maps Pi
  `tool_call` / `tool_result` events onto the same JSON-on-stdin hook protocol.
  Because Pi can pass the full write/edit input, `secret_scan.py` also catches
  secrets in file *content*, and a native check denies reads of protected
  secret/key files. See `.pi/README.md`.

### `guard_write_zone.py`

Hook path:

```text
.agentic/hooks/guard_write_zone.py
```

When it runs: before edit tools.

What it reads:

- `.agentic/current_run`
- `.agentic/runs/<run-id>/graph.json`
- `.agentic/workflow.toml`

What it does: allows or denies file edits based on the current stage, access
mode, write zones, and protected path patterns.

Related CLI commands:

- `start`
- `next`
- `set-stage`
- `set-access-mode`

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
`gh pr create`, or `git merge`.

What it calls:

```powershell
python .agentic/tools/run_agentic_workflow.py delivery-preflight
```

What it does: denies the publish-like command when delivery preflight fails.

### `secret_scan.py`

Hook path:

```text
.agentic/hooks/secret_scan.py
```

When it runs: before tool use.

What it does: scans tool input for configured secret-like patterns and denies
the operation when a possible secret appears.

Related CLI commands: none directly, but it protects the same workflow surface.

## Typical Full Flow

```powershell
<workflow> start --kind feature --statement "Add invoice export"
<workflow> audit traceability
<workflow> audit coverage
<workflow> impact src/exporter.py tests/test_export.py
<workflow> add-spec --id SPEC-001 --tag behavior --statement "Invoice export writes a CSV file."
<workflow> add-check --id CHECK-001 --cites-spec SPEC-001 --cites-requirement REQ-FUNC-001 --command "python -m pytest tests/test_export.py::test_invoice_export" --path tests/test_export.py --state red
<workflow> record-evidence --kind test-run --result fail --stage check --check-id CHECK-001 --summary "Export test fails before implementation." --command "python -m pytest tests/test_export.py::test_invoice_export"
<workflow> set-stage implementation --reason "Human approved implementation after red check"
<workflow> record-evidence --kind test-run --result pass --stage implementation --check-id CHECK-001 --summary "Export test passes after implementation." --command "python -m pytest tests/test_export.py::test_invoice_export"
<workflow> record-change --id CU-001 --path src/exporter.py --path tests/test_export.py
<workflow> set-stage validation --reason "Implementation is ready for validation"
<workflow> gates run --name test
<workflow> audit traceability
<workflow> audit coverage
<workflow> registry sync
<workflow> registry audit
<workflow> set-stage delivery --reason "Validation passed and human approved delivery preparation"
<workflow> delivery-preflight
<workflow> report
```

After this sequence, the human still must explicitly approve any commit, push,
pull request, merge, or publish action.
