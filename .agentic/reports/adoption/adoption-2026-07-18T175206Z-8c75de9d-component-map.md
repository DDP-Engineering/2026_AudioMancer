<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Text Cleanup Component Map Gate

Run: `adoption-2026-07-18T175206Z-8c75de9d`

Map review date: 2026-07-18

## Proposed Slice

The existing `text-cleanup` component boundary remains valid after repository
discovery. This gate proposes no path, representative-test, criticality,
status, or bundle changes.

| Field | Proposed value |
| --- | --- |
| Component | `text-cleanup` |
| Criticality | `high` |
| Adoption status | `discovered` |
| Owner | `DDP Engineering / Eng. Dan Dumitru Pasare` |
| Bundle | none |
| Production modules | 8 |
| Prompt resources | `prompts/text_cleanup_*.txt` (2 matched files) |
| Focused test modules | 8 modules with 98 tests |

The owner is changed from the provisional discovery label to the recommended
alignment response accepted by continuation through the prior gate.

## Boundary

The component owns:

- Source extraction and extraction reset/state/report behavior.
- Deterministic cleanup and cleanup text analysis.
- AI cleanup behavior and the two cleanup prompts.
- Cleanup paragraph metadata and page/state orchestration.
- Text Cleanup UI controller and page integration.
- The eight focused test modules already listed in `.agentic/components.toml`.

No additional production or test paths are proposed. Cross-component tests
remain assigned to their existing primary owners so the component map stays
non-overlapping.

## Dependency Context

The component depends on:

- `project-lifecycle` for project manifests, path containment, and atomic
  persistence contracts.
- `operation-orchestration` for operation state, progress, cancellation,
  downstream impact, and threaded UI execution.
- `ai-runtime` for provider/profile selection, prompt loading, budgets, token
  accounting, and AI transaction logging.
- `platform-settings-ui` for configuration constants, localization, logging,
  timestamps, and shared UI state.

These are dependency edges, not reasons to enlarge the component or create a
bundle.

## Honest Baseline Notes

- The component remains `discovered`, below the configured `baseline-usable`
  threshold.
- All 8 production modules currently lack file-level active requirement
  coverage.
- The focused test inventory exists but has not yet been run in this adoption
  slice.
- Current AEGIS component documentation is missing.
- Two known cross-component mismatches remain characterized: the manual-edit
  atomic-writer expectation and lazy cleanup-state initialization expectation.
- AI cleanup has an external provider dependency, but provider credentials and
  endpoint settings are outside this component's ownership.

Promotion is deliberately deferred to `component-adoption`, where current
documentation, durable requirements, linked test evidence, and adoption notes
can be established without runtime behavior changes.

## Approval Request

Approve this unchanged component boundary, confirmed owner, high criticality,
`discovered` status, no-bundle decision, and documented dependency/gap context
for `text-cleanup`, then continue to `component-adoption`.

