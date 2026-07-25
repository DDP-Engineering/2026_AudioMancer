<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Spec: <REQ-ID>

Companion specification for a single requirement snapshot. Referenced from the
requirement's `spec_ref`. Keep the requirement sentence atomic; put the concrete,
drift-preventing detail here. Delete any section that does not apply — do not
leave a heading with placeholder text.

- Requirement ID: `<REQ-CATEGORY-uuid>`
- Requirement: `<the one-sentence contract this spec details>`

## Behavior

What the behavior does, precisely: the primary success path plus the branches,
rejections, boundary/empty/at-limit cases, and state effects (persistence,
idempotency, concurrency) the implementation must honor.

## Data Structures

Concrete shapes the behavior reads or writes: fields, types, required/optional,
ranges, defaults, invariants. Show the actual structure rather than describing it.

```text
# example schema / type / table
```

## Interface / Format

The exact interface contract: function/endpoint signatures, request/response or
message formats, status codes, headers, CLI flags, file formats — whatever the
behavior exposes or consumes.

```text
# example interface / message / payload
```

## Copy / Dialog Text

The exact user-visible strings the change adds or changes — labels, prompts,
error and confirmation messages — verbatim, so implementation does not paraphrase.

## Examples

Worked input → output examples, including at least one failure/rejection example.
These double as the acceptance examples the check stage turns into tests.

| Input | Expected result |
| --- | --- |
| `<input>` | `<result>` |

## Acceptance

The checkable outcomes that define "done" for this requirement, each traceable to
an alignment acceptance criterion.

- [ ] `<criterion>`
