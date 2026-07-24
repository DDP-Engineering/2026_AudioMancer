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
wording, rationale, priority, status, verification, affected paths, or linked
tests of the same behavioral contract.

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

An Active automated requirement needs resolvable exact test selectors. A
manual-only Active requirement uses `Manual: <method>` or
`Inspection: <method>`. Current snapshots do not contain revision history,
parent IDs, supersession chains, or previous wording.

Use requirement create/show/list/update/activate commands instead of inventing
IDs or editing a shared index. Traceability, coverage, and impact read these
files directly and build reverse mappings only in memory. Concurrent changes
to the same TOML file are a semantic conflict that must be reconciled.
