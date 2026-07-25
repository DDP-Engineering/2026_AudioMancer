<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Requirement Snapshots

This directory is the canonical durable project contract. Each requirement is
one complete current TOML snapshot. Run graphs record the work performed in an
individual run; requirement files record the behavior the project currently
promises.

## Identity And Layout

Use the workflow CLI to create IDs. An ID has the form
`REQ-<CATEGORY-CODE>-<lowercase UUIDv4>` and its filename is exactly
`<id>.toml` below the matching category directory:

| Category | Directory | Code |
| --- | --- | --- |
| `functional` | `functional/` | `FUNC` |
| `ux` | `ux/` | `UX` |
| `non_functional` | `non_functional/` | `NFR` |
| `security` | `security/` | `SEC` |
| `data_privacy` | `data_privacy/` | `DATA` |
| `platform` | `platform/` | `PLAT` |
| `release` | `release/` | `REL` |
| `testing` | `testing/` | `TEST` |

Search and list existing requirements before creating one so a semantically
equivalent contract is not duplicated. Keep the same ID when revising the
wording, rationale, priority, status, verification, spec reference, affected
paths, or linked tests of the same behavioral contract.

## One Requirement, One Behavior

Each requirement captures a single, independently verifiable behavior with one
precise purpose, so it is easy to read, test, and trace. Split rather than
combine: when a contract needs "and", "or", a list, or a semicolon to join
*distinct* behaviors, write one requirement per behavior instead. A shared
input, actor, or component is not a reason to merge; each behavior that can pass
or fail on its own is its own requirement. This keeps each `affected_paths` and
`linked_tests` set narrow and lets one failing test name exactly one broken
contract.

## Coverage Dimensions

A feature is fully defined only when every category it touches has requirements,
not just the functional happy path. When decomposing a feature, consider each
dimension and record a requirement for every one that applies:

- `functional` — what the system does: inputs, outputs, branches, and the errors
  or rejections each behavior produces.
- `ux` — how the user interacts: flows, states, visible messages, and
  accessibility the behavior must present.
- `non_functional` — how well it performs: latency, throughput, resource limits,
  reliability, and other measurable qualities.
- `security` — what must be prevented: authentication, authorization, input
  containment, and abuse or escape paths.
- `data_privacy` — what data is handled: what is stored, retained, exported, or
  redacted, and what must never be persisted.
- `platform` — where it runs: operating systems, runtimes, versions, and
  environment constraints the behavior depends on.
- `release` — how it ships: packaging, migration, compatibility, and rollout or
  rollback expectations.
- `testing` — how a behavior is verified when only a process or tool can assert
  it rather than a product code path.

A category with no applicable behavior needs no requirement; silently skipping a
category that does apply is the common source of gaps and later regressions.

## Complete Record

Every file uses schema version 1 and contains all fields below in this order:

```toml
schema_version = 1
id = "REQ-FUNC-6f3a61e8-84fc-438a-9b0b-53554cd04789"
category = "functional"
status = "Planned"
priority = "Must"
requirement = "One testable current behavioral contract."
rationale = "Why the contract is required."
verification = "Automated test"
spec_ref = ".agentic/requirements/functional/REQ-FUNC-6f3a61e8-84fc-438a-9b0b-53554cd04789.spec.md"

affected_paths = [
  "src/example.py",
]

linked_tests = [
  "tests/test_example.py::test_contract",
]

created_on = "2026-07-22T10:20:00Z"
last_updated = "2026-07-22T10:20:00Z"
```

`status` is `Planned`, `Active`, or `Retired`; `priority` is `Must`, `Should`,
or `Could`. Arrays are the complete current sets and are replaced rather than
appended during updates. Empty arrays never inherit earlier values.

## Concrete Specification (`spec_ref`)

`requirement` stays a single testable sentence; the concrete detail that keeps an
implementation from drifting lives in a companion spec artifact referenced by
`spec_ref`. Use `spec_template.md` as the starting point and record there the data
structures, interface or message formats, exact dialog and copy text, example
payloads, and worked acceptance examples the behavior depends on.

- `spec_ref` is an optional repository-relative path (no globs). Empty string
  means no companion spec.
- When set, the file must exist at create/update time or the write is rejected;
  the traceability audit reports a `REQ-SPEC-MISSING` finding when a referenced
  spec is later deleted, so a stale reference cannot pass silently.
- A companion spec complements, and does not replace, the durable requirement
  snapshot, its `verification`, or its linked tests.
- Place the spec beside its requirement (for example
  `functional/<id>.spec.md`) or under a project `.agentic/specs/` area; either
  is valid as long as the path resolves.
- `feature` and `change` work should set `spec_ref`; a small `fix` may leave it
  empty when the requirement sentence is already complete.

Every non-Retired requirement (`Planned` or `Active`) needs resolvable exact
test selectors or an explicit `Manual: <method>` / `Inspection: <method>`
verification; the traceability audit reports any that have neither and delivery
preflight blocks on it. Retired requirements are exempt. Current snapshots do
not contain revision history, parent IDs, supersession chains, or previous
wording.

Use requirement create/show/list/update/activate commands instead of inventing
IDs or editing a shared index. Traceability, coverage, and impact read these
files directly and build reverse mappings only in memory. Concurrent changes
to the same TOML file are a semantic conflict that must be reconciled.
