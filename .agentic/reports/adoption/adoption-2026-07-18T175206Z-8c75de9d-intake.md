<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Text Cleanup Adoption Intake

Run: `adoption-2026-07-18T175206Z-8c75de9d`

Intake date: 2026-07-18

## Classification

This is a single-component adoption run for the already approved
`text-cleanup` boundary. It is not a behavior-changing feature or fix run, and
no component bundle is requested.

The preceding adoption run
`adoption-2026-07-18T145821Z-782116f8` remains preserved at
`adoption-delivery`; this run continues repository adoption with a new local
slice.

## Mapped Scope

Production files:

- `04_Software/AudioMancer/src/audiomancer/services/ai_cleanup_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/cleanup_metadata_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/cleanup_text_analysis_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/deterministic_cleanup_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/text_cleanup_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/text_extraction_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/text_cleanup_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/text_cleanup_page.py`

Additional mapped scope includes
`04_Software/AudioMancer/prompts/text_cleanup_*.txt` and these focused tests:

- `04_Software/AudioMancer/tests/test_ai_cleanup_contract.py`
- `04_Software/AudioMancer/tests/test_ai_cleanup_service.py`
- `04_Software/AudioMancer/tests/test_cleanup_metadata_service.py`
- `04_Software/AudioMancer/tests/test_deterministic_cleanup_service.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_page.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_state_service.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_ui_controller.py`
- `04_Software/AudioMancer/tests/test_text_extraction_service.py`

The focused files contain 98 discovered test functions.

## Existing Knowledge

Legacy documentation is available in:

- `05_SoftwareDocu/AudioMancer_Text_Extraction_Service.md`
- `05_SoftwareDocu/AudioMancer_Deterministic_Cleanup_Service.md`
- `05_SoftwareDocu/AudioMancer_AI_Cleanup_Service.md`

Component adoption will reconcile these descriptions with current code and
create a concise current-state page under
`.agentic/knowledge/components/`.

## Baseline State

- Component status: `discovered`
- Criticality: `high`
- Configured completion threshold: `baseline-usable`
- File-level requirement coverage: missing for all eight production files
- Repository-wide coverage findings before this slice: 80
- Mapped owner: DDP Engineering / Eng. Dan Dumitru Pasare, still marked as
  discovered and requiring confirmation for this component

## Risks And Questions

Two pre-existing test/runtime contract mismatches from the preceding slice
touch this component:

1. An atomic-I/O integration test expects
   `text_cleanup_state_service.write_json_atomic`, which the current module
   does not expose.
2. A Main Window integration test expects `cleanup_state.json` when the Text
   Cleanup page opens, while current runtime behavior creates extraction state
   only.

Adoption will document and classify these mismatches. It will not alter tests
or runtime behavior. Any resolution must use `agentic-development`.

The remaining alignment question is whether DDP Engineering / Eng. Dan Dumitru
Pasare should be confirmed as the owner for `text-cleanup`. The recommended
response is to confirm the existing mapped owner, consistent with the approved
component map and repository authorship evidence.

## Intended Adoption Output

- confirm or revise the local boundary and owner
- document current extraction, deterministic cleanup, AI cleanup, metadata,
  persisted state, and UI integration
- add minimal durable requirements covering all eight production files
- link requirements to existing passing test identifiers
- run focused tests and classify any baseline gaps
- preserve application behavior and stop after every gate
