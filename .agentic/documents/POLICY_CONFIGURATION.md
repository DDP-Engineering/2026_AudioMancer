<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Agentic Policy Configuration

This document explains `.agentic/policy.toml`, the manual operating policy for
the agentic workflow. It describes how gates, human asks, and invariants should
be treated by agents and human operators.

`policy.toml` is deliberately small. The executable workflow behavior is split
between the CLI, hooks, `AGENTS.md`, and `.agentic/workflow.toml`; this file is
the compact policy map that keeps the manual workflow easy to read.

## Mental Model

`policy.toml` answers these questions:

- Does each workflow gate stop for human review?
- Should the agent ask, decide, notify, or continue for common interaction
  types?
- Which invariant failures block progress?
- Which invariant failures are advisory?
- Which invariant failures are non-waivable?

The policy is most useful as a reference when writing agent instructions,
reviewing stage summaries, or deciding whether a workflow run can move forward.

## Manual Gates

The `[manual_gates]` section controls whether each stage should stop.

```toml
[manual_gates]
intake = "stop"
requirement = "stop"
check = "stop"
implementation = "stop"
validation = "stop"
delivery = "stop"
```

`stop` means the agent should finish the current gate, summarize artifacts and
evidence, and wait for human approval before moving to the next gate.

Typical gate meanings:

| Gate | Purpose of the stop |
| --- | --- |
| `intake` | Confirm the request, current run, initial impact, and next gate. |
| `requirement` | Review spec items and durable requirement rows before tests are written. |
| `check` | Review red checks before implementation changes begin. |
| `implementation` | Review source/docs changes and passing focused evidence before validation. |
| `validation` | Review full validation evidence before delivery preparation. |
| `delivery` | Review preflight, report, and final status before commit, push, PR, merge, or publish. |

Intent alignment is configured in `.agentic/workflow.toml` because it has
additional risk and open-question settings.

## Asks

The `[asks]` section defines how the agent should handle common interaction
types.

```toml
[asks]
clarify = "ask"
review = "ask"
decide = "ask"
approve = "ask"
notify = "report"
```

Meanings:

| Ask type | Policy | Meaning |
| --- | --- | --- |
| `clarify` | `ask` | Ask the human when missing information changes scope, risk, or correctness. |
| `review` | `ask` | Ask the human to review artifacts at gate boundaries. |
| `decide` | `ask` | Ask the human to choose when tradeoffs cannot be safely assumed. |
| `approve` | `ask` | Ask before actions that require explicit approval. |
| `notify` | `report` | Report status or evidence without blocking on a response. |

The workflow can still continue automatically when the active stage policy and
alignment policy allow it, but approval-sensitive actions should remain explicit.

Examples of `approve` actions:

- moving from red checks into implementation
- accepting changed requirements after scope changes
- switching to repo-wide access mode
- committing
- pushing
- opening a pull request
- merging
- publishing or deploying

## Invariants

The `[invariants]` section maps workflow invariant ids to severity.

```toml
[invariants]
INV-1 = "blocking"
INV-2 = "blocking"
INV-3 = "blocking"
INV-4 = "blocking"
INV-5 = "advisory"
INV-6 = "blocking"
INV-7 = "non-waivable"
```

Severity meanings:

| Severity | Meaning |
| --- | --- |
| `blocking` | Must be resolved before the run can be considered ready. |
| `advisory` | Must be explained or accepted, but does not automatically block delivery. |
| `non-waivable` | Must pass; do not bypass or accept as risk. |

Common invariant meanings:

| Invariant | Name | Meaning |
| --- | --- | --- |
| `INV-1` | Coverage | Accepted or realized specs must have checks. |
| `INV-2` | Citation | Checks must cite existing spec items. |
| `INV-3` | Red-before-green | Green checks must have prior red evidence. |
| `INV-4` | No regression | Implementation, validation, and delivery evidence must not contain active failing gates or tests. |
| `INV-5` | In scope | Recorded change units should stay within source, test, documentation, or approved scope paths. |
| `INV-6` | Evidence | The run must contain recorded evidence. |
| `INV-7` | Clean secrets | Configured secret patterns must not appear in the diff. |

Some workflow versions may evaluate additional invariants beyond those listed
in the policy file. Treat new blocking or non-waivable invariant failures as
real until the workflow documentation and policy are updated together.

## Real Case Pattern: Advisory Scope Overflow

If `INV-5` reports out-of-scope paths, the run should not hide the finding.
Because `INV-5` is advisory, the human can accept the scope overflow when the
extra paths are intentional.

Example stage summary:

```text
Invariant status: INV-5 advisory finding for docs/operations.md.
Needs human: confirm whether the documentation update is intentional scope.
```

If accepted, record a decision or evidence note explaining why the extra path is
part of the approved change. If rejected, revise the diff or route back to the
proper gate.

## Real Case Pattern: Non-Waivable Secret Finding

If `INV-7` fails, do not ask the human to waive it. Remove the secret-like
content from the diff, rotate any exposed credential if needed, and rerun the
secret check or delivery preflight.

Example response:

```text
Invariant status: INV-7 failed and is non-waivable.
Next action: remove the matched credential pattern and rerun delivery preflight.
```

## Real Case Pattern: Manual Gate Stop

A manual gate stop should include enough context for the human to choose the
next step without reading the entire run graph.

Example:

```text
Stage: check
Artifacts changed: tests/export/test_report_writer.py
Evidence: E-0003 red test evidence recorded for CHECK-001
Invariant status: expected implementation evidence is still missing
Needs human: approve implementation or revise the check
Next prompt options:
- Continue to implementation
- Revise CHECK-001
- Abort or park this run
```

## Example Policy For A Strict Manual Workflow

```toml
[manual_gates]
intake = "stop"
requirement = "stop"
check = "stop"
implementation = "stop"
validation = "stop"
delivery = "stop"

[asks]
clarify = "ask"
review = "ask"
decide = "ask"
approve = "ask"
notify = "report"

[invariants]
INV-1 = "blocking"
INV-2 = "blocking"
INV-3 = "blocking"
INV-4 = "blocking"
INV-5 = "advisory"
INV-6 = "blocking"
INV-7 = "non-waivable"
```

## Example Policy For Faster Internal Maintenance

Use this only when the repository instructions allow more autonomous movement
between low-risk gates. Delivery approval should still remain explicit.

```toml
[manual_gates]
intake = "stop"
requirement = "stop"
check = "stop"
implementation = "stop"
validation = "stop"
delivery = "stop"

[asks]
clarify = "ask"
review = "ask"
decide = "ask"
approve = "ask"
notify = "report"

[invariants]
INV-1 = "blocking"
INV-2 = "blocking"
INV-3 = "blocking"
INV-4 = "blocking"
INV-5 = "advisory"
INV-6 = "blocking"
INV-7 = "non-waivable"
```

This example intentionally keeps the same gate stops. In most repositories, the
safer way to speed up maintenance is to use clear alignment recommended
responses and focused validation commands, not to remove review gates.

## Change Checklist

When editing `policy.toml`:

- Keep the file aligned with `AGENTS.md` stage rules.
- Keep delivery approval explicit.
- Do not make secret findings waivable.
- Update this document when adding or renaming invariant ids.
- Update workflow instructions when changing gate behavior.
- Validate policy-sensitive changes with a dry run or stage summary review.
