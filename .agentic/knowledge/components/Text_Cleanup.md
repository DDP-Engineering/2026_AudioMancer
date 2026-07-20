<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Text Cleanup

## 1. Purpose

The Text Cleanup component turns a project source document into canonical
extracted text and then into reviewable clean text. It supports deterministic
and AI-assisted cleanup modes, persists operation state and cleanup metadata,
and presents the operator workflow through the Text Cleanup page.

## 2. Responsibilities

- Extract and normalize `.txt`, `.md`, `.pdf`, `.rtf`, `.docx`, `.odt`, and
  `.epub` sources into canonical project text.
- Persist extraction state/report artifacts and resume supported interrupted
  extraction work.
- Remove conservative page artifacts, heal page-boundary text, preserve
  dialogue and paragraph structure, and detect language/script/chapter cues.
- Partition canonical source windows through an AI provider, validate strict
  forward-source coverage, and render recognized artifact types
  deterministically.
- Persist clean text, reports, operation state, non-duplicating paragraph
  metadata, AI cleanup documents, and transaction logs.
- Build Text Cleanup page state, save confirmed manual edits, reapply supported
  AI spacing choices, and reset cleanup or downstream workflow state.
- Coordinate page actions, confirmation dialogs, progress, cancellation,
  previews, editing, search, profile selection, and spacing controls.

The component does not own project creation or atomic writer primitives,
threaded operation infrastructure, AI provider/profile configuration, or later
chunking, translation, voice, TTS, and assembly behavior.

## 3. Implementation Overview

The production boundary is:

- `04_Software/AudioMancer/src/audiomancer/services/text_extraction_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/deterministic_cleanup_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/cleanup_text_analysis_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ai_cleanup_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/cleanup_metadata_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/text_cleanup_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/text_cleanup_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/text_cleanup_page.py`

`text_extraction_service.extract_text` dispatches by source suffix, normalizes
text, checkpoints formats that support incremental work, and writes canonical
extraction artifacts. `deterministic_cleanup_service.clean_text` divides input
into pages or pseudo-segments, removes conservative artifacts, repairs
structure, checkpoints progress, finalizes paragraph metadata, and updates the
project manifest. `cleanup_text_analysis_service` supplies reusable script,
language, chapter, sentence-boundary, and dialogue decisions.

`ai_cleanup_service.clean_text` resolves cleanup prompts and AI profile
budgets, creates page-aware source windows, validates strict JSON block
responses against canonical source slices, checkpoints a cleanup document, and
reconstructs clean text using deterministic artifact rendering. Compatible
completed AI documents can be re-rendered with different spacing choices
without another provider call.

`cleanup_metadata_service` stores paragraph spans and provenance without
duplicating canonical paragraph text. `text_cleanup_state_service` composes
previews, notes, manifest transitions, edit/spacing operations, and reset
effects. `TextCleanupUiController` connects those services to
`TextCleanupPage`, while the page owns Qt signals, controls, previews, find
behavior, edit state, and localized presentation.

Opening Text Cleanup initializes only resumable extraction metadata. Cleanup
state is an execution artifact: deterministic cleanup creates it when a run
starts, while AI cleanup uses its cleanup document and manual edits retain a
manifest summary without a cleanup-state file.

## 4. Dependencies

Internal dependencies include:

- `project-lifecycle` for the project manifest, project-root containment, and
  shared atomic text/JSON persistence.
- `operation-orchestration` for operation paths and payloads, progress,
  cancellation, downstream resets, and threaded UI execution.
- `ai-runtime` for profile/provider selection, prompt loading, model-context
  budgeting, token usage, and AI transaction logging.
- `platform-settings-ui` for artifact names, localization, logging, timestamps,
  and shared UI state.

External packages are PySide6, PyMuPDF (`fitz`), python-docx, EbookLib, odfpy,
striprtf, and langdetect. AI cleanup also requires a separately configured
provider endpoint. Local project files are the durable storage boundary.

## 5. Inputs And Outputs

Inputs include the active project root and manifest, its registered source
document, optional progress/cancellation callbacks, the selected cleanup mode,
AI profile and operator instructions, and AI spacing selections.

Extraction produces `extracted_text.txt`, `extraction_report.json`, and
`extraction_state.json`. Cleanup produces `clean_text.txt`,
`clean_text_metadata.json`, `cleanup_report.json`, and `cleanup_state.json`.
AI cleanup additionally persists its cleanup document and cleanup transaction
logs using names from `audiomancer.config`. Operations update compact manifest
summaries and may remove later-stage artifacts after confirmed reruns, resets,
or manual edits.

## 6. Data Contracts

Canonical text uses normalized LF line endings and a final newline. PDF pages
retain form-feed boundaries for page-aware cleanup; extraction does not perform
OCR. Cleanup metadata stores paragraph identifiers, line spans, and provenance
without duplicating paragraph text; loaders reconstruct text from
`clean_text.txt`.

The AI prompt contract returns one object containing `window_id` and ordered
`text_blocks`. Each block contains only `text_block_id`, `text_block`,
`artifact_type`, and `confidence`. Artifact types are `header`, `footer`,
`noise`, `separator`, `heading`, and `story`. Every non-whitespace source
character must be covered exactly once in forward order. Story is retained;
header/footer/noise are removed; separator/heading render as two LF characters;
confidence is review metadata only. Whitespace-only gaps are restored from
validated source positions.

Resume state is fingerprinted against relevant source and operation inputs.
Corrupt or incompatible checkpoints restart safely; compatible prefixes may be
restored even when later AI window partitioning changes. Completed AI spacing
reapplication must not contact the provider and repeated application is
deterministic.

## 7. Workflow Integration

Project Lifecycle registers the source before this component runs. The
application shell opens `TextCleanupPage`; `TextCleanupUiController` dispatches
extraction or cleanup through the shared operation runner and refreshes the
manifest and page state after success, failure, or cancellation.

Extraction is the prerequisite for either cleanup mode. Clean text and its
metadata become inputs to Text Chunking and all later workflow stages. Reruns,
resets, and manual edits use workflow-impact rules to invalidate downstream
artifacts while preserving only explicitly compatible state. AI output remains
operator-reviewable beside the source preview.

## 8. Usage

```python
from audiomancer.services import text_extraction_service

result = text_extraction_service.extract_text(project_root, manifest)
```

```python
from audiomancer.services import deterministic_cleanup_service

report = deterministic_cleanup_service.clean_text(project_root)
```

AI cleanup is normally started by `TextCleanupUiController`, which resolves
the selected profile and optional instructions before calling
`ai_cleanup_service.clean_text`. Direct callers must supply the same operation
runtime and provider/profile contracts.

## 9. Validation And Tests

Focused automated coverage is mapped in `.agentic/components.toml`:

- `04_Software/AudioMancer/tests/test_text_extraction_service.py`
- `04_Software/AudioMancer/tests/test_deterministic_cleanup_service.py`
- `04_Software/AudioMancer/tests/test_ai_cleanup_service.py`
- `04_Software/AudioMancer/tests/test_ai_cleanup_contract.py`
- `04_Software/AudioMancer/tests/test_cleanup_metadata_service.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_state_service.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_ui_controller.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_page.py`

After changes, run all eight focused modules plus the traceability and coverage
audits. Changes to extraction formats require their format-specific cases;
deterministic rules require structure and multilingual cases; AI contract
changes require the entire AI contract module; state or UI changes require
state, controller, and page tests.

## 10. Limitations And Future Work

- PDF extraction has no OCR fallback; image-only PDFs fail with an explanatory
  error.
- AI cleanup depends on an available configured provider and requires human
  review of source versus cleaned text.
