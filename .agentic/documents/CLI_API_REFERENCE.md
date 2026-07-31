<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AEGIS 2.1 CLI Reference

AEGIS uses a file-first interface designed to remain tractable for small local
models. Commands navigate work; generated schema-3 TOML and referenced Markdown
carry detailed content.

Use `aegis`, `python -m aegis`, or the repository wrappers:

```text
.\.agentic\tools\run.ps1 <group> <action>
bash .agentic/tools/run.sh <group> <action>
```

## Global Options

Only two global options exist:

```text
--run <run-id>   select a run without changing the worktree pointer
--json           emit stable JSON
```

They may appear before or after a grouped command. Default output always begins:

```text
status: <ok|blocked|failed>
stage: <stage-or-none>
artifact: <path-or-none>
next: <exact-command-or-none>
```

## Command Inventory

The complete top-level interface is:

```text
aegis run ...
aegis stage ...
aegis requirement ...
aegis check ...
aegis evidence ...
aegis waive ...
aegis verify ...
aegis delivery ...
aegis adoption ...
aegis config ...
```

Legacy AEGIS 1.x commands and mutation flags do not exist.

## Run

```text
aegis run start <feature|fix|change|adoption> [--quick]
aegis run status
aegis run resume
aegis run select <run-id>
```

`run start` creates and selects a draft run, prepares the intake form, and
returns its path. Put the statement, scope hints, and access mode in the form.
`--quick` selects the proportional profile and is valid only for `fix` and
`change`; feature and adoption starts return a typed blocked response before
run state is created.

After quick-run intake closes, `run status` reports `run_profile="quick"`,
`bypass_status="bypassed"`, and the four bypassed stages. The intake approval
also creates one `run.stages_bypassed` journal event with the human approver,
intake revision, reason, and stage list. The validation summary and delivery
report repeat this state; no surface reports bypassed work as passed.

## Stage Lifecycle

```text
aegis stage prepare
aegis stage add
aegis stage show
aegis stage apply
aegis stage close
```

- `prepare` creates or reconstructs the current form.
- `add` creates another CLI-identified requirement/check form.
- `show` reports files, revision, readiness, and blockers.
- `apply` validates the entire stage directory before importing and does not
  advance.
- `close` is the explicit human approval action. It journals approval, advances,
  and prepares the next stage.

The standard stages are:

```text
intake → alignment → requirement → design → check → implementation → validation → delivery
```

The quick `fix`/`change` profile declares a separate four-stage sequence:

```text
intake -> implementation -> validation -> delivery
```

Alignment, requirement, design, and check are absent from the executable
sequence and are explicitly journaled as `bypassed` when intake closes. Every
remaining stage still requires prepare, apply, and explicit human close.

Adoption retains its seven specialized stages and uses the same lifecycle.
Delivery closure marks the run complete; it never pushes, publishes, merges, or
creates a pull request.

Forms live below:

```text
.agentic/runs/<run-id>/stages/<stage>/
```

Their common `[control]` table carries a requested access-mode change and
rationale, optional human-approved routing to an earlier stage and rationale,
the stage summary, and unresolved questions.

## Requirements and Design

```text
aegis requirement list
aegis requirement show <id>
```

Requirement commands are read-only. Mutations occur only through requirement
stage forms. AEGIS generates UUID-backed IDs and durable companion specs.
Successful validation closure activates eligible Planned requirements.

Quick runs have no requirement or design collection stage. INV-1, INV-2,
INV-8, and INV-10 therefore report `not-applicable` with `holds=null`; this is
an explicit quick-run state, not a pass or waiver.

The authoritative design is:

```text
.agentic/runs/<run-id>/design.md
```

`stage apply` records its digest and cited requirement snapshot digests.
`stage close` approves the proposal. Check and later stages require invariant
`INV-10`; changed design/requirement digests or earlier routing make approval
stale.

## Checks and Evidence

External mode:

```text
aegis check prepare
# run the immutable commands and complete evidence.toml
aegis check record
```

Managed mode:

```text
aegis check run
aegis check run <check-id>...
```

The captured workspace policy permits one path. The wrong path returns the
configured mode and correct command. Check closure requires red evidence;
implementation closure requires prior red and current green evidence.

Quick runs have no check collection stage. Red-before-green (INV-3) is
`not-applicable` for that profile, but implementation changed paths and linked
manual evidence remain required and are validated normally.

On entry to quick implementation, the exact next command is
`aegis evidence prepare add`. Apply that form, copy its CLI-minted active ID
into `linked_check_evidence`, then apply the implementation form. Missing,
invented, superseded, or non-implementation evidence is rejected.

External preparation and recording are valid only during check or
implementation, require a captured external mode and at least one imported
check, and require exactly one result row per immutable check ID and command.
Recording validates the complete document before graph mutation. Permitted
surrounding whitespace in `result`, `summary`, and `output_log` is trimmed, and
the persisted result is the canonical `pass` or `fail` value that was
validated. Invalid or incomplete documents leave graph, journal, and form state
unchanged.

Manual evidence:

```text
aegis evidence prepare <add|supersede>
aegis evidence apply
aegis evidence show
```

## Run-Local Waivers

```text
aegis waive add <blocker-id> --reason "<human-approved reason>"
aegis waive list
```

`waive list` reports the currently eligible exact blocker IDs, active waivers,
and the complete run-local waiver history classified as `active`, `stale`, or
`inactive`. Eligible IDs include failing invariants such as `INV-10`, enforced
gate failures such as `gate:test`, per-check red-before-green failures such as
`red-before-green:<check-id>`, and exact stage, traceability, coverage, and
working-tree findings.

For zero-waiver output compatibility, an ordinary unwaived `INV-7` retains its
legacy `non-waivable` policy label. Its failing process blocker is nevertheless
eligible in `waive list`; when covered, its effective policy is reported
`blocking` alongside `waived=true`, never as `WAIVED (non-waivable)`.

`waive add` records one explicit human approval. The reason must contain
non-whitespace text, the blocker must be currently eligible, and the ID must be
exact; wildcard, bulk, and force forms do not exist. The CLI mints a
`WVR-<uuid>` ID, appends the schema-3 waiver record to the selected run graph,
and appends a separate `waiver.added` journal event.

Every waiver is scoped to the selected run. It also stores the current blocker
state digests, so a later change to pinned content makes the record stale and
the blocker returns. For example, an `INV-10` waiver no longer applies after
the approved design or one of its cited requirement snapshots changes.

A waiver neutralizes blocking behavior without rewriting history. The
invariant still has `holds=false`, a gate still has failed evidence, and audit
findings remain present. Machine summaries and `report.md` render the item as
`WAIVED` and include its reason and timestamp; they never render it as passed.
Disabled gates remain `disabled`, not passed or waived.

The exact non-waivable integrity floor is:

- malformed, unsupported, or closed-schema workflow, graph, stage, evidence,
  requirement, or integration state, including corrupted run identity or
  selection data;
- live persistence-lock conflicts (`PERSISTENCE-LOCK-TIMEOUT`);
- stale graph mutations (`GRAPH-STALE-UPDATE`);
- stale requirement mutations (`REQUIREMENT-STALE-UPDATE`); and
- atomic-publication or journal-integrity failures.

These failures protect data rather than process and therefore never appear as
eligible blocker IDs. Correct the state or retry the operation. A waiver also
does not synthesize an applied stage or shorten the lifecycle. Only an eligible
run started explicitly with `--quick` uses the declared shorter lifecycle.

## Deterministic Verification

```text
aegis verify run
aegis verify status
aegis verify gates [build|typecheck|lint|test|security]...
aegis verify invariants
aegis verify traceability
aegis verify coverage
aegis verify impact [paths-file]
aegis verify working-tree
```

`verify run` performs impact/regression selection, all enabled gates in the
fixed order shown above, invariants, traceability, coverage, working-tree review,
and then writes a validation summary for the human diff review. Every enabled
group executes even if an earlier group fails. Disabled groups are reported
`disabled`, never `passed`. Waived failures are reported `waived` with their
original failed state, reason, and timestamp; they are never reported `passed`.

For a quick run, requirement/check traceability and coverage audits, plus
INV-1, INV-2, INV-3, INV-8, and INV-10, report `not-applicable - quick run` and
cannot become pass results or waiver targets. Impact analysis, enabled gates,
the secrets scan, remaining invariants, scope advisory, and working-tree review
still execute. The summary includes the quick profile and the explicit
bypassed-stage list.

The security group runs only explicitly configured deterministic tooling. Its
result is evidence from that tooling, not an authoritative security-assurance
claim.

## Delivery, Adoption, and Configuration

```text
aegis delivery show
aegis delivery report

aegis adoption component-status
aegis adoption scope-check <path>...
aegis adoption baseline

aegis config validate
aegis config show
```

Configuration and run graphs require schema 3. AEGIS 2.1 rejects schema 2 and
earlier legacy graphs without migration or fallback.

The schema-3 run graph has an additive `profile` field: its absence means
`full`, preserving existing graphs and full-run serialization; `quick` is valid
only with `fix` or `change`. Hand-edited kind/profile/stage mismatches return a
typed stage-operation block.

The optional proportionality policy is:

```toml
[quick.changed_paths]
mode = "advise"
max_paths = 10
```

Modes are `disabled` and `advise`; `max_paths` is a positive integer. If the
table is absent, the effective ship-open default is `disabled` with threshold
10. In `advise` mode, closing quick-run implementation with more than the
configured number of unique changed paths returns `QUICK-SCOPE-ADVISORY` and
guidance to carry the context into `aegis run start <fix|change>`. It never
blocks, routes, or mutates the current run.

`config validate` and `config show` also validate/display the optional
schema-1 `.agentic/integrations/repowise.toml`. Absence means disabled. RepoWise
execution intentionally has no AEGIS command: WAEGIS owns
`waegis repowise status|sync`, while AEGIS consumes only validated structural
artifacts during `repo-discovery`.

Expected AEGIS configuration, run-resolution, workflow, command-input,
requirement, persistence, and RepoWise integration failures produce the stable
`blocked` response and exit code 1. Argparse errors retain parser output and
exit code 2. Interrupts, explicit process exits, and unexpected programming
exceptions are not reclassified as governance blocks.
