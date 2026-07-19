<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Text Cleanup Component Adoption

Run: `adoption-2026-07-18T175206Z-8c75de9d`

Adoption date: 2026-07-18

## Approved Scope

The human approved the `text-cleanup` component map and selected it as a
single-component adoption slice. The approved owner is DDP Engineering / Eng.
Dan Dumitru Pasare. No bundle exception or coverage waiver is used.

The production boundary contains eight files:

- `04_Software/AudioMancer/src/audiomancer/services/ai_cleanup_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/cleanup_metadata_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/cleanup_text_analysis_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/deterministic_cleanup_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/text_cleanup_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/text_extraction_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/text_cleanup_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/text_cleanup_page.py`

The component also owns `prompts/text_cleanup_*.txt` and the eight focused test
modules listed in `.agentic/components.toml`.

## Characterized Behavior

The component extracts supported source documents into canonical text,
performs deterministic or AI-assisted cleanup, persists resumable operation
state and non-duplicating paragraph metadata, manages cleanup edits/resets and
manifest transitions, and presents the Text Cleanup page/controller workflow.

Its exact responsibilities, dependencies, artifacts, AI block schema,
deterministic rendering rules, workflow integration, validation expectations,
and limitations are documented in
`.agentic/knowledge/components/Text_Cleanup.md` and indexed under Component
Knowledge.

## Durable Requirements

Six current-behavior requirements were added as `Planned`, proven through
their exact linked tests, and activated with the workflow CLI:

| Requirement | Behavior |
| --- | --- |
| `REQ-FUNC-005` | Supported source extraction, canonical artifacts, no-OCR policy, and source-preserving reset |
| `REQ-FUNC-006` | Conservative deterministic cleanup, multilingual analysis, and non-duplicating metadata |
| `REQ-FUNC-007` | Strict AI source coverage, deterministic artifact rendering, review artifacts, and provider-free spacing reapplication |
| `REQ-FUNC-008` | Cleanup page-state projection, manual edits, manifest transitions, spacing, and downstream reset behavior |
| `REQ-UX-001` | Text Cleanup page/controller readiness, review, edit, AI controls, operation routing, and refresh flow |
| `REQ-NFR-002` | Resumable extraction/cleanup, compatible output reproduction, and safe incompatible-state restart |

Every production file in the approved component is named by at least one
Active, test-linked requirement. Coverage findings fell from 80 to 72; all
remaining findings belong to other mapped components.

## Validation Evidence

- Scope check: all eight production files resolve only to `text-cleanup` and
  correctly reported the pre-adoption baseline gap.
- Exact linked tests: 37 passed, with one existing Python 3.13 `audioop`
  deprecation warning.
- Complete mapped component suite: 111 passed, with the same warning.
- Requirement traceability audit: pass, no issues.
- Post-activation impact: every production file covered; no full regression
  recommendation remains for this component.
- Registry sync: 12 requirements, 57 checks, 1 feature, 13 components, and no
  bundles; registry audit passes.
- Application behavior-change check: no source, prompt, or test file was
  modified by this adoption gate.

The repository-wide suite finished with 917 passed, 1 skipped, and 5 failures.
Those failures are retained as baseline evidence rather than repaired during
adoption.

## Known Baseline Gaps

1. `test_atomic_io_contracts.py::test_manual_cleaned_text_edit_uses_atomic_writers`
   expects an atomic JSON writer on `text_cleanup_state_service`; the current
   module exposes only the atomic text writer.
2. `test_main_window_project_flow.py::test_main_window_initializes_step_state_only_when_page_is_opened`
   expects `cleanup_state.json` when Text Cleanup opens; current initialization
   creates extraction state only.
3. Two `test_config_hygiene.py` cases report a populated credential field in
   `04_Software/AudioMancer/settings.json`. The value was neither copied into
   adoption artifacts nor modified. It requires prompt credential rotation and
   sanitization in a separately authorized configuration/security change.
4. `test_traceability.py::test_services_and_controllers_have_test_coverage`
   remains red because 72 source files in the other discovered components do
   not yet have Active linked requirements.

The first two gaps require a behavior decision in `agentic-development`; the
third is an out-of-scope security/configuration issue; the fourth is expected
incremental adoption work.

## Component Status

`text-cleanup` is now `characterized`: its approved boundary, owner, current
behavior, dependencies, requirements, focused tests, and remaining gaps are
explicit. It is not promoted to `baseline-usable`; classification belongs to
the next `baseline-review` gate.

