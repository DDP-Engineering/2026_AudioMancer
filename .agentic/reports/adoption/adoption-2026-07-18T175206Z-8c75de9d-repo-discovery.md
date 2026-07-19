<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Text Cleanup Repository Discovery

Run: `adoption-2026-07-18T175206Z-8c75de9d`

Discovery date: 2026-07-18

## Scope And Method

This report records read-only discovery of the approved `text-cleanup`
component in `04_Software/AudioMancer`. Current implementation is treated as
authoritative; existing tests and the three legacy implementation documents
are corroborating evidence. No application source, prompts, tests, or runtime
behavior were changed.

Evidence reviewed:

- The 8 mapped production modules and 2 matched prompt resources.
- The 8 mapped focused test modules, containing 98 `test_*` functions.
- `AudioMancer_Text_Extraction_Service.md`,
  `AudioMancer_Deterministic_Cleanup_Service.md`, and
  `AudioMancer_AI_Cleanup_Service.md` under `05_SoftwareDocu`.
- Cross-component integration evidence in `test_atomic_io_contracts.py` and
  `test_main_window_project_flow.py`.
- The approved component manifest, current adoption baseline, and AEGIS
  traceability, coverage, and registry audits.

## Confirmed Boundary

The approved boundary is coherent and requires no production-path additions or
removals at the next gate:

| Layer | Owned paths | Observed responsibility |
| --- | --- | --- |
| Extraction | `services/text_extraction_service.py` | Extract and normalize TXT, Markdown, PDF, RTF, DOCX, ODT, and EPUB sources; checkpoint supported formats; persist extraction artifacts; reset extraction and downstream state. |
| Deterministic cleanup | `services/deterministic_cleanup_service.py`, `services/cleanup_text_analysis_service.py` | Remove conservative page artifacts, heal page-boundary text, preserve dialogue and paragraph structure, detect language/script/chapter cues, checkpoint progress, and persist cleanup artifacts. |
| AI cleanup | `services/ai_cleanup_service.py`, `prompts/text_cleanup_system.txt`, `prompts/text_cleanup_user.txt` | Partition canonical source windows through an AI provider, validate exact forward source coverage, render artifact types deterministically, resume compatible prefixes, and reapply spacing selections without another provider call. |
| Metadata and state | `services/cleanup_metadata_service.py`, `services/text_cleanup_state_service.py` | Persist non-duplicating paragraph metadata; build Cleanup page state and notes; save manual edits; apply AI spacing; derive manifest state; reset cleanup and downstream stages. |
| UI integration | `ui/controllers/text_cleanup_ui_controller.py`, `ui/pages/text_cleanup_page.py` | Present extraction and cleanup actions, profile and spacing controls, side-by-side previews, manual-edit/find flows, progress/cancellation, confirmation dialogs, and manifest refresh. |

The two prompts belong to AI cleanup because their strict block schema and
artifact rendering contract are consumed only by `ai_cleanup_service.py`.
Shared project, operation, AI-provider, persistence, settings, logging, and UI
helpers remain dependencies owned by other mapped components.

## Entry Points And Data Contracts

The UI entry point is `TextCleanupPage`, whose signals are handled by
`TextCleanupUiController`. The controller starts extraction, deterministic
cleanup, or AI cleanup through the shared operation runner and refreshes page
state through `text_cleanup_state_service`.

Service entry points include:

- `text_extraction_service.extract_text`, `load_operation_state`,
  `load_extraction_report`, and `reset_extraction_and_downstream`.
- `deterministic_cleanup_service.clean_text`, `load_operation_state`, and
  `load_cleanup_report`.
- `ai_cleanup_service.clean_text`, cleanup-document/state loaders, spacing
  selection helpers, and cleanup profile helpers.
- Metadata builders/loaders and the state service's edit, spacing, reset,
  manifest, note, and preview helpers.

Observed project artifacts are:

- Extraction: `extracted_text.txt`, `extraction_report.json`, and
  `extraction_state.json`.
- Cleanup: `clean_text.txt`, `clean_text_metadata.json`,
  `cleanup_report.json`, and `cleanup_state.json`.
- AI cleanup: the cleanup document JSON plus cleanup transaction logs, using
  names resolved from `audiomancer.config`.

All production persistence paths use shared operation-path resolution and
atomic persistence helpers except for the known manual-edit integration
mismatch recorded below. Operation summaries are mirrored into the project
manifest through `project_workspace_service`.

## Dependencies

Internal dependency edges:

- `project-lifecycle`: project-root containment, project manifest reads and
  operation-summary synchronization.
- `operation-orchestration`: operation paths/state payloads, progress,
  cancellation, downstream resets, and the threaded UI operation runner.
- `ai-runtime`: provider/profile selection, prompt loading, context budgeting,
  token accounting, and transaction logging for AI cleanup.
- `platform-settings-ui`: configuration constants, localization, UI state,
  logging, and timestamps.
- Downstream workflow components: cleanup reset/manual-edit impact can clear or
  preserve later-stage artifacts through the shared workflow-impact contract.

External runtime dependencies are PySide6, PyMuPDF (`fitz`), python-docx,
EbookLib, odfpy, striprtf, and langdetect, in addition to the Python standard
library. AI cleanup also depends on a separately configured provider endpoint;
this component does not own provider credentials or endpoint settings.

## Focused Test Inventory

The mapped focused suite contains 98 tests:

| Test module | Tests | Principal evidence |
| --- | ---: | --- |
| `test_text_extraction_service.py` | 9 | Supported formats, normalization/artifacts, PDF warnings/no-OCR policy, progress units, DOCX resume, reset behavior. |
| `test_deterministic_cleanup_service.py` | 22 | Artifact removal, paragraph/dialogue repair, multilingual/script handling, cancellation/failure/restart/resume, metadata and manifest artifacts. |
| `test_ai_cleanup_service.py` | 15 | Artifacts/logs, prompt context, schema handling, transformations, warnings, budgets/windows, resume and changed-source restart. |
| `test_ai_cleanup_contract.py` | 25 | Exact source ordering/coverage, bounded story edits, schema/budget contract, reconstruction, resume offsets, spacing reapplication without provider access. |
| `test_cleanup_metadata_service.py` | 1 | Metadata omits duplicated text and reconstructs paragraphs from canonical clean text. |
| `test_text_cleanup_state_service.py` | 8 | Page state/notes, manual edit, cleanup/downstream resets, metadata removal, manifest transitions. |
| `test_text_cleanup_ui_controller.py` | 7 | Operation dispatch, profiles/instructions, resume confirmations, edits, spacing, project-state refresh. |
| `test_text_cleanup_page.py` | 11 | Action enablement, previews/status, edit/save, find, profile/spacing signals, layout. |

`cleanup_text_analysis_service.py` has no dedicated mapped test module; its
current behavior is exercised transitively by deterministic cleanup tests.
Cross-component integration tests remain assigned to their existing primary
component owners to preserve non-overlapping map paths.

## Documentation And Ownership

The three legacy documents accurately describe the broad current extraction,
deterministic cleanup, and AI cleanup contracts, but they are outside the AEGIS
component-documentation root and cite historical requirement identifiers that
are not present in the current durable registers. Component adoption should
summarize reconciled current behavior in
`.agentic/knowledge/components/Text_Cleanup.md` rather than copy historical
traceability claims.

Source and test headers consistently identify Eng. Dan Dumitru Pasare, and the
repository copyright identifies DDP Engineering. Continued alignment uses the
recommended owner response: `DDP Engineering / Eng. Dan Dumitru Pasare`.

## Current Baseline And Gaps

- Adoption baseline: `text-cleanup` is `discovered` with high criticality.
- Traceability audit: passes structurally; no current durable requirement rows
  cover `text-cleanup` yet.
- Coverage audit: 80 repository source gaps remain, including all 8 production
  files in this component.
- Registry audit: passes.
- Component documentation: no current AEGIS `Text_Cleanup.md` exists.
- Focused evidence is substantial, but it has not yet been executed within this
  adoption run; execution belongs to `component-adoption` and
  `baseline-review`.

Two previously observed cross-component tests expose baseline mismatches and
must remain characterized rather than repaired during adoption:

1. `test_atomic_io_contracts.py::test_manual_cleaned_text_edit_uses_atomic_writers`
   expects `text_cleanup_state_service.write_json_atomic`; the current module
   imports only `write_text_atomic` and delegates other persisted state changes.
2. `test_main_window_project_flow.py::test_main_window_initializes_step_state_only_when_page_is_opened`
   expects `cleanup_state.json` on opening Text Cleanup; current initialization
   creates extraction state while cleanup state is created by cleanup work.

Any decision to change either behavior must start a separate
`agentic-development` run.

## Component-Map Recommendation

At the next gate:

1. Retain all current `text-cleanup` paths, representative tests, high
   criticality, and `discovered` status.
2. Replace the provisional owner text with the aligned owner,
   `DDP Engineering / Eng. Dan Dumitru Pasare`.
3. Add dependency and gap context to the component-map gate report without
   introducing overlapping paths or a component bundle.
4. Keep promotion to `characterized` for component adoption after current
   documentation, durable requirements, and focused evidence exist.

