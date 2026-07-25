<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: Requirement

Load this module only while in the `requirement` stage.

## Procedure

- Decompose the feature first. Before drafting, enumerate the complete behavior
  set the request implies: the primary success path, each distinct input or
  branch, each rejection or error, boundary/empty/limit cases, and state effects
  such as persistence, idempotency, and concurrency. Also scan the cross-cutting
  categories (`ux`, `security`, `data_privacy`, `non_functional`, `platform`)
  and list every one that applies. Aim to fully cover and define the
  functionality, not the minimum that makes it work.
- Create or update minimal spec items: one testable sentence, `behavior` or
  `property`, examples or thresholds.
- One requirement, one behavior. Each requirement and each spec item states a
  single, independently verifiable behavior with one precise purpose. When a
  request spans several distinct behaviors, create one requirement per behavior
  rather than one combined requirement. If a statement needs "and", "or", a
  list, or a semicolon to join *distinct* behaviors, split it. A shared input,
  actor, or component is not a reason to merge; each behavior that can pass or
  fail on its own is its own requirement.
- Cover failure modes as requirements, not only as tests. For each happy-path
  functional requirement, create the sibling rejection and boundary requirements
  the behavior implies — invalid input, empty or at-limit values, and the
  specific error or refusal — or record explicitly that none apply. A behavior
  that lives only in a test is a durable-contract gap: a later change can drop it
  without any requirement going untraced.
- Trace every acceptance criterion. Each `--acceptance` item recorded at
  alignment maps to at least one requirement, and each new requirement traces
  back to an acceptance criterion or to a gap found while decomposing. Record any
  acceptance item still without a requirement as an open question rather than
  dropping it.
- Run `<workflow> requirement list --json` and inspect matching contracts before
  creating a requirement.
- Capture concrete detail in a companion spec so implementation cannot drift.
  For `feature` and `change` work, author a spec file from
  `.agentic/requirements/spec_template.md` holding the data structures,
  interface/message formats, exact dialog and copy text, example payloads, and
  worked acceptance examples the behavior depends on, then pass its path as
  `--spec-ref <path>`. Keep the `requirement` sentence itself atomic. A small
  `fix` may omit `spec_ref` when the sentence is already complete.
- Create a durable snapshot with `<workflow> requirement create ...` and use the
  returned UUID-backed ID, or update the existing snapshot with
  `<workflow> requirement update --id <requirement-id> ...`.
- If the work creates or materially changes a component, include the expected
  component documentation update in the scope and acceptance notes.
- New snapshots start as `Planned`; activate only after linked checks pass.
- Record each item with `<workflow> add-spec`.
- Run `<workflow> invariants`.
- Stop and ask the human to review the spec.

## Requirement Stage Review

Before stopping at the requirement gate, report this checklist for the proposed
set so the human approves on evidence, not trust. Answer each item and name any
gap rather than omitting it:

- Independent — each requirement states one behavior; none bundle distinct
  behaviors with "and", "or", or a list.
- Testable — each requirement admits a concrete check that can pass or fail on it
  alone.
- Concrete — every `feature`/`change` requirement names a `spec_ref` whose file
  exists and carries the data structures, formats, dialog text, and examples that
  pin the implementation, or states why the sentence needs no companion spec.
- Failure modes — the rejection, boundary, and empty/at-limit behaviors exist as
  their own requirements, or are explicitly marked not applicable.
- Acceptance traced — every alignment acceptance criterion maps to at least one
  requirement, and every requirement traces back to a criterion or a recorded
  gap.
- Dimensions — every applicable coverage dimension (`functional`, `ux`,
  `non_functional`, `security`, `data_privacy`, `platform`, `release`,
  `testing`) has a requirement or a stated reason it does not apply.
- Category and priority — each requirement is filed under the correct category
  and its priority reflects its real importance.
