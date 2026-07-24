<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Speech Blocks

## 1. Purpose

Converts approved text and voice context into an ordered, operator-reviewable speech-block plan for TTS.

## 2. Responsibilities

- Select compatible source chunks and derive narration, dialogue, pause, indication, and scene-ambience blocks.
- Normalize stable IDs, speakers, text, durations, warnings, approvals, and TTS-budget-safe splits.
- Persist block/report/state artifacts and provide manual edit, approval, reset, and downstream invalidation behavior.
- Present the review workflow through the Speech Blocks controller and page; it does not synthesize WAV files.

## 3. Implementation Overview

The orchestration service resolves source chunks and voice assignments, builds block documents and report artifacts, and coordinates reset/approval transitions. Normalization and text-split services provide deterministic content/speaker/identifier handling and size-aware splits. State/report services project persisted artifacts into UI data. The controller and page route operations, guarded edits, selection, warnings, and review actions through the shared runner.

## 4. Dependencies

- Internal: canonical/translated chunk artifacts, Character Discovery/Voice Profiles, TTS budget service, operation/workflow-impact runtime, persistence/logging services, and Qt/shared operation runner.
- External: no provider is required to review stored blocks; later VoiceWeaver TTS consumes approved outputs.

## 5. Inputs And Outputs

- Inputs: project state, source/translation chunks, selected narrator/character voice plan, operator edits/approvals, and configured TTS limits.
- Outputs: ordered speech-block document, reports/state summaries, normalized warnings/operation rows, approval state, and exact downstream invalidation targets.

## 6. Data Contracts

When untranslated source is selected, source order and text come only from the
strict authoritative Chunking document through its shared reader.

- Each block has a stable `speech_block_id`, content/speaker kind and identifiers, text or ambience prompt, duration, warning flags, and approval state.
- Source selection preserves canonical ordering; normalization and splits preserve usable text while keeping blocks within configured TTS limits.
- Report/state summaries derive from persisted document data rather than creating competing block records.
- IDs use a chunk-local `CCCC-BBBBBB` form. Manual insertion creates an
  unapproved narrator narration row; deletion can remove the final row for a
  chunk without removing that source chunk. Generated output remains
  `review_pending` until every persisted block is approved, and resumptions
  require a compatible source snapshot and response-contract marker.

## 7. Workflow Integration

Speech Blocks follows Voice Profiles and is the review gate before TTS Audio Blocks. An operator must resolve warnings and approve the block plan; material edits reset only affected generated audio and assembly work.

## 8. Usage

Open Speech Blocks after selecting voices, generate or resume the block plan, inspect list rows and warnings, edit the selected block deliberately, then approve the plan before TTS. Use reset when upstream character, language, or voice changes make the current plan incompatible.

## 9. Validation And Tests

Primary automated coverage:

- `tests/test_speech_blocks_service.py`
- `tests/test_speech_blocks_normalization_service.py`
- `tests/test_speech_blocks_text_split_service.py`
- `tests/test_speech_blocks_report_state_service.py`
- `tests/test_speech_blocks_state_service.py`
- `tests/test_speech_blocks_ui_controller.py`
- `tests/test_speech_blocks_page.py`

These cover source resolution, normalization, splitting, artifact/report/state
recovery, warning/approval transitions, controller operations, and page
editing/selection. Minimum validation after a change: run the focused modules
above with `uv run pytest`, plus `uv run python -m py_compile` and
`uv run ruff check` on changed files. Operators must manually review semantic
speaker assignment, ambience suitability, and pause interpretation.

## 10. Limitations And Future Work

Automated tests establish deterministic structural and invalidation contracts, but cannot decide whether a dialogue attribution, ambience prompt, pause, or pronunciation-oriented split is artistically correct. The operator remains responsible for reviewing the speech plan before audio is generated.
