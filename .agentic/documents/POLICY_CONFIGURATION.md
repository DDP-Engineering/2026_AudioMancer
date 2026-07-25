<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AEGIS Policy Configuration

AEGIS separates intrinsic workflow contracts from repository policy. This
boundary makes the engine repository-neutral without making it workflow-free.

- Intrinsic contracts define how governed evidence and stages work.
- Repository policy defines which paths, contents, commands, and scopes are
  restricted in this repository.
- External safety is supplied by the host, operating system, organization, or
  platform and is never disabled by AEGIS configuration.

## Mandatory Policy Inspection

Before repository inspection or edits:

```powershell
<workflow> config validate --json
<workflow> config show --effective --json
```

Report write-access, protected-read/path, scope, secret, gate, coverage, and
delivery modes with active rule counts. Also report the selected run for
graph-dependent work. Do not continue when configuration is missing or invalid.

## Three Independent Control Layers

| Layer | Examples | Authority |
| --- | --- | --- |
| Intrinsic AEGIS workflow | check citations, red-before-green, evidence lifecycle, stage transitions | AEGIS code |
| AEGIS repository policy | protected paths, secret regexes, write stages, coverage roots, delivery patterns | validated `.agentic/workflow.toml` |
| External safety | sandbox, approvals, filesystem permissions, network policy, organization controls | host/platform/operator |

An unrestricted AEGIS mode means only that AEGIS applies no rule for that
policy. It never grants permission beyond the external layer.

## Intrinsic Workflow Contracts

The following remain engine behavior and are not configurable repository
opinions:

| Invariant | Contract |
| --- | --- |
| `INV-1` | Every accepted or realized spec item is covered by a check. |
| `INV-2` | Every check cites an existing spec item. |
| `INV-3` | A check records failing evidence before passing evidence. |
| `INV-4` | No active failing regression evidence remains for implementation, validation, or delivery. |
| `INV-6` | The run has recorded evidence. |
| `INV-8` | Green checks citing durable requirements cite current `Active` snapshots. |

Stage transitions, journaling, immutable evidence IDs, evidence supersession,
explicit human approval for outward actions, and the distinction between
standard and repo-wide access are also intrinsic workflow contracts.

Repository-specific path and content decisions are not intrinsic. `INV-5`,
`INV-7`, and `INV-9` consume configured scope, secret, and component policies
and return explicit pass results when their policy is unrestricted or disabled.

## Repository Policy Modes

The complete key and validation reference is in
`WORKFLOW_CONFIGURATION.md`. The policy decisions are summarized here.

| Concern | Non-restrictive mode | Restrictive mode |
| --- | --- | --- |
| Secret scanning | `disabled` | `enforce` |
| Protected paths | `disabled` | `enforce` |
| Working-tree blockers | `unrestricted` | `restricted` |
| Write access | `unrestricted` | `stage_restricted` |
| Scope | `unrestricted` | `advisory` or `enforce` |
| Coverage | `disabled` | `enforce` |
| Alignment protected scope | `disabled` | `enforce` |
| Gate execution | `disabled` | `enforce` |
| Component baseline | `disabled` | `enforce` |
| Adoption source changes | `unrestricted` | `blocked` |
| Delivery hook | `disabled` | `enforce` |

Inactive modes require empty rule collections. AEGIS rejects dormant rules so
operators cannot mistake configured-looking text for enforced behavior.

## Scope and Write Decisions

Scope and write access answer different questions:

- Scope asks whether planned or touched paths fit the repository policy.
- Write access asks whether the current workflow stage may edit a path.
- Protected paths can deny configured read and/or write operations regardless
  of stage access.
- External host safety can still deny an operation that AEGIS allows.

`scope_hint` documents or narrows a run's intended work. It never expands an
enforced configured scope root.

Under `stage_restricted`, standard access applies the configured stage list. An
empty stage list means read-only. Repo-wide access bypasses stage lists after a
human records the reason, but cannot bypass enforced protected paths.

## Secret and Delivery Decisions

Secret scanning uses only configured regular expressions in `enforce` mode.
There are no built-in secret patterns. Invalid configuration denies a pre-tool
operation rather than skipping policy.

Delivery command patterns use normalized lowercase fragments. A match invokes
the shared delivery preflight. Passing preflight does not perform the outward
action and does not replace explicit human or platform approval.

## Gates and Coverage

Disabled gates contain no commands and are reported as disabled. Enforced gates
run complete configured command strings from `gates.test` and `gates.lint`.

Disabled coverage has no coverable roots. Enforced coverage evaluates current
requirement snapshot `affected_paths`, current linked tests, and explicit
waivers. It builds any reverse mapping in memory and writes no registry or cache.

## Requirement Policy

Durable requirements are current TOML snapshots, not workflow history:

- list/search before creating to avoid semantic duplicates;
- create UUIDv4-backed IDs only through the CLI;
- preserve the ID for revisions of the same behavioral contract;
- replace complete linked-test and affected-path sets when associations change;
- activate only after automated selectors resolve or an explicit `Manual:` or
  `Inspection:` method is supplied; and
- reconcile concurrent edits to the same requirement file as a real semantic
  conflict.

Traceability, coverage, impact, reports, and delivery preflight read canonical
snapshots directly. Registry sync and registry audit do not exist.

## Run Selection Policy

The worktree-local pointer is
`.agentic/.workspace/state/current_run`. The entire `.agentic/.workspace/`
directory is ignored and must not be staged or copied to another worktree.

Graph-dependent commands accept an explicit `--run-id`. Explicit selection
wins over the pointer and does not mutate it. Missing, malformed, or stale state
produces typed `RUN-*` errors with setup instructions; agents must not guess an
ID or edit graphs to bypass resolution.

## Configuration Failure Policy

Missing, malformed, incomplete, unknown, wrong-type, or inconsistent
configuration is never a default. CLI operations fail before acting and exit
with status `2`. Pre-tool hooks deny with the same stable code and remediation.
Post-tool hooks emit a warning and skip policy-dependent evidence recording.

The guard transports also fail closed beyond configuration errors. Because the
shared guards always exit `0` and signal a denial on stdout, a guard that cannot
run at all — a missing or unlaunchable Python interpreter, or a hook that
crashed — is treated as a block, not an allow, on every adapter. An unavailable
guard therefore denies the operation it was meant to check rather than silently
permitting it.

Examples:

- `CONFIG-MISSING`: create the complete schema-version-2 file.
- `CONFIG-MODE-INVALID`: select one ratified mode for the reported key.
- `CONFIG-INCONSISTENT`: align the rule collection with its selected mode.
- `CONFIG-RULE-INVALID`: repair the exact path, glob, regex, command, or stage.

## Operator Decision Checklist

Before enabling a restriction, decide:

1. Which concrete repository risk the policy addresses.
2. Whether the policy should advise or block.
3. Which exact normalized rules are required.
4. Which CLI, hook, adapter, audit, invariant, and delivery paths consume it.
5. How an agent can repair a failure without guessing.

After editing policy:

1. Run `config validate --json`.
2. Run `config show --effective --json`.
3. Exercise both a matching and non-matching case.
4. Confirm every adapter reaches the shared configured hook decision.
5. Confirm external host safety remains unchanged.
