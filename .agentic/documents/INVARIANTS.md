<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->

# AEGIS Invariants

`aegis verify invariants` evaluates these rules; `aegis verify run` evaluates
them with gates, traceability, coverage, impact, and working-tree review. A
full run evaluates all ten. A quick run reports INV-1, INV-2, INV-3, INV-8,
and INV-10 as `not-applicable`, because it has no requirement, check, or design
collection stage. `not-applicable` is neither passed nor waived.

For an eligible failed process rule, first run `aegis waive list`, obtain
human approval, then use the exact reported ID with
`aegis waive add <blocker-id> --reason "<reason>"`. A waiver is run-local and
digest-pinned; it leaves the failure visible as `WAIVED`. It does not repair
schema, graph, persistence, or stale-update integrity failures.

| ID | Name | Policy | Protects | Evaluates / trips when | Waivable | Primary remediation |
| --- | --- | --- | --- | --- | --- | --- |
| INV-1 | Coverage | Blocking | Every non-retired requirement has a check. | Verification; one or more non-retired snapshots have no citing check. | Yes | Add or correct checks in the requirement/check stages, then `aegis verify invariants`. |
| INV-2 | Citation | Blocking | Checks refer to real requirements. | Verification; a check has no citation or cites a missing snapshot. | Yes | Correct the check collection through `aegis stage prepare`, `aegis stage apply`, and `aegis stage close`; then verify. |
| INV-3 | Red-before-green | Blocking | A full-run fix was reproduced before it was declared fixed. | Verification; a green check lacks red evidence. | Yes | Record red evidence with `aegis check prepare` / `aegis check record` or `aegis check run`, then record green evidence and verify. |
| INV-4 | No regression | Blocking | Failed implementation, validation, or delivery test/gate evidence remains visible. | Verification; active gate or test-run evidence in those stages failed. | Yes, for the exact eligible failure | Fix and rerun the relevant `aegis verify gates` or `aegis check run`, then verify. |
| INV-5 | In scope | Blocking when scope enforces; advisory otherwise | Recorded changed paths stay inside configured scope and the repository. | Verification; paths escape the repository or violate enforced allowed roots. | Yes when scope is `enforce`; advisory findings are not waiver targets | Correct changed paths through the implementation form, or consciously revise `workflow.toml`; then `aegis verify invariants`. |
| INV-6 | Evidence | Blocking | The run has durable evidence. | Verification; no evidence is recorded. | Yes | Use `aegis check prepare` / `aegis check record`, `aegis check run`, or `aegis evidence prepare add` / `aegis evidence apply`; then verify. |
| INV-7 | Clean secrets | Non-waivable policy; explicitly waiver-eligible | Configured secret patterns do not appear in tracked, staged, or untracked changes. | Verification; scanning fails or a configured pattern matches. | Yes, only as an exact recorded process waiver | Remove or redact the secret, then `aegis verify invariants`; do not use a waiver to normalize a secret leak. |
| INV-8 | Green requirements active | Blocking | Green requirement-linked checks point to active durable contracts. | Verification; a cited snapshot is missing or not `Active`. | Yes | Restore or activate the requirement through its stage form, correct the check citation, then verify. |
| INV-9 | Component baseline scope | Blocking | Behavior-changing work is limited to baseline-ready mapped components when the guard is enabled. | Verification; changed paths fail the component baseline audit. Adoption runs and disabled guards do not block. | Yes | Complete/map the affected component or correct changed paths, then `aegis verify invariants`. |
| INV-10 | Solution design | Blocking | Check and later work use a human-approved, unchanged design and cited requirement snapshots. | From check onward and during verification; no human-approved design exists, `design.md` changed, or a cited snapshot digest changed. | Yes | Return to design with `aegis stage prepare`, update/import it with `aegis stage apply`, explicitly approve with `aegis stage close`, then verify. |

## INV-1 — Coverage

This rule prevents requirements from becoming promises with no planned
verification. Add a check that cites each non-retired requirement, import and
close the applicable forms, then run `aegis verify invariants`.

## INV-2 — Citation

This rule prevents checks from drifting into uncoupled scripts. Give every
check at least one existing requirement citation through the check-stage form,
then run `aegis verify invariants`.

## INV-3 — Red-before-green

This rule prevents a full-run fix from claiming success without a demonstrated
failure first. Record the red result before its green result using the configured
external (`aegis check prepare` then `aegis check record`) or managed
(`aegis check run`) path, then verify. It is not applicable to quick runs.

## INV-4 — No regression

This rule retains failed gate and test-run evidence from implementation onward.
Fix the failure and rerun the appropriate configured gate with
`aegis verify gates` or the check with `aegis check run`; finish with
`aegis verify invariants`.

## INV-5 — In scope

This rule compares recorded changed paths with repository containment and the
configured scope. Correct the implementation form's paths, or deliberately
change the policy in `workflow.toml`, before applying and verifying again. In
advisory scope mode it reports but does not block.

## INV-6 — Evidence

This rule ensures the run contains at least one durable evidence record. Record
check evidence through `aegis check record` or `aegis check run`, or add manual
evidence through `aegis evidence prepare add` and `aegis evidence apply`.

## INV-7 — Clean secrets

This rule scans the tracked diff, staged diff, and untracked files using the
configured patterns. Remove the matched value from the working tree and rerun
`aegis verify invariants`. The code permits an exact waiver target so a scan
failure or policy exception remains explicitly recorded, but a waiver is not a
safe substitute for removing exposed credentials.

## INV-8 — Green requirements active

This rule prevents green evidence from being linked to missing or inactive
requirements. Restore or activate the snapshot, or correct the check citation,
through the appropriate stage form; then run `aegis verify invariants`. It is
not applicable to quick runs.

## INV-9 — Component baseline scope

When the component baseline guard is enabled, this rule prevents behavior work
from silently extending into components that lack the configured baseline.
Update the component map/baseline or narrow the recorded changed paths, then
verify. It does not block adoption runs and passes when the guard is disabled.

## INV-10 — Solution design

This rule protects human design approval from becoming stale. From check onward,
the design must be human approved, its `design.md` digest must match, and every
cited requirement snapshot digest must match. Revisit design with
`aegis stage prepare`, `aegis stage apply`, and `aegis stage close`, then run
`aegis verify invariants`. It is not applicable to quick runs.
