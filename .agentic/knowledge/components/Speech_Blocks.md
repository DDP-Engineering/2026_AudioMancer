<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Speech Blocks

## 1. Purpose

Converts approved text and voice context into an ordered, operator-reviewable speech-block plan for TTS.

## 2. Responsibilities

- Select compatible source chunks and derive narration, dialogue, pause, indication, and scene-ambience blocks.
- Normalize stable IDs, speakers, text, durations, warnings, approvals, and TTS-budget-safe splits.
- Persist a single authoritative `speech_blocks.json` document and provide manual edit, approval, reset, and downstream invalidation behavior.
- Present the review workflow through the Speech Blocks controller and page; it does not synthesize WAV files.

## 3. Implementation Overview

The orchestration service resolves source chunks and voice assignments, assembles one authoritative `speech_blocks.json` document (source identity, AI/budget metadata, resume checkpoint, and blocks), and coordinates reset/approval transitions. Normalization and text-split services provide deterministic content/speaker/identifier handling and size-aware splits. The legacy report and operation-state shapes are compatibility projections recomputed from that single document, so `load_speech_blocks_report()` and `load_operation_state()` keep their signatures. The controller and page route operations, guarded edits, selection, warnings, and review actions through the shared runner.

The two narration modes take different paths. `narrator_and_characters` sends
budgeted source segments to the model under the `direct_blocks` contract and
realigns the returned text to the source, so uncovered spans become narrator
review rows. `same_narrator` calls no model at all: because every block gets the
narrator voice, the only remaining decision is structural, and
`speech_blocks_narrator_split_service` makes it by packing whole sentences into
evenly sized blocks under the `deterministic_narrator_blocks` contract.

## 4. Dependencies

- Internal: canonical/translated chunk artifacts, Character Discovery/Voice Profiles, TTS budget service, operation/workflow-impact runtime, persistence/logging services, and Qt/shared operation runner.
- External: no provider is required to review stored blocks; later VoiceWeaver TTS consumes approved outputs.

## 5. Inputs And Outputs

- Inputs: project state, source/translation chunks, selected narrator/character voice plan, operator edits/approvals, and configured TTS limits.
- Outputs: ordered speech-block document, reports/state summaries, normalized warnings/operation rows, approval state, and exact downstream invalidation targets.

## 6. Data Contracts

Source selection matches Character Discovery: when a translation exists, is
complete, and every chunk is approved, Speech Blocks uses the translated
(repair-normalized) text regardless of the selected Character Voices language;
otherwise it uses the original Chunking document text through its shared reader.

- Each block has a stable `speech_block_id`, content/speaker kind and identifiers, text or ambience prompt, duration, warning flags, and approval state.
- Source selection preserves canonical ordering; normalization and splits preserve usable text while keeping blocks within configured TTS limits.
- Persistence is a single authoritative `speech_blocks.json` document object with a fixed top-level field set (`status`, `source`, `ai_profile_id`, `instructions`, `scene_ambience`, `response_contract`, `token_usage`, `budget_metadata`, `checkpoint`, `failure`, `blocks`); the separate `speech_blocks_report.json` and `speech_blocks_state.json` artifacts are no longer written.
- Counts, warnings, stage status, and progress are recomputed on read; the document keeps only `source.fingerprint` (not a copy of source-chunk text) and re-resolves source chunks from upstream (`chunks_text.json` / `translated_text.json`).
- A legacy list-format artifact or a corrupt/missing document reads as not-started (`None`); reset removes the document and any residual legacy report/state files. Existing projects in the old format must re-run Speech Blocks (breaking persistence change).
- IDs use a chunk-local `CCCC-BBBBBB` form. Manual insertion creates an
  unapproved narrator narration row; deletion can remove the final row for a
  chunk without removing that source chunk. Generated output remains
  `review_pending` until every persisted block is approved, and resumptions
  require a compatible source snapshot and response-contract marker.
- `same_narrator` segmentation is deterministic and total: concatenating the
  `source_text` of a chunk's blocks reproduces that chunk character for
  character, and the service raises rather than persisting a lossy plan. A
  sentence is never cut, and a boundary is never placed while a quotation is
  open, so a multi-sentence quotation stays in one block. A single sentence that
  alone exceeds the TTS budget is kept whole and flagged `tts_budget_exceeded`,
  because TTS Audio Blocks splits it again at generation time against the real
  loaded-model budget.
- Chunking records how confident Text Cleanup was about a paragraph rebuilt
  across a page break. Speech Blocks carries that verdict through, so a chunk
  with a non-`strong` `cleanup_boundary_confidence` marks its blocks
  `weak_source_boundary` and `needs_review` instead of hiding the uncertainty.
- The retired `narrator_boundary_ids` contract still reads, so an old document
  is not lost, but it is not resumable: continuing it would leave one document
  holding two different segmentations.

## 7. Workflow Integration

Speech Blocks follows Voice Profiles and is the review gate before TTS Audio Blocks. An operator must resolve warnings and approve the block plan; material edits reset only affected generated audio and assembly work.

## 8. Usage

Open Speech Blocks after selecting voices, generate or resume the block plan, inspect list rows and warnings, edit the selected block deliberately, then approve the plan before TTS. Use reset when upstream character, language, or voice changes make the current plan incompatible.

## 9. Validation And Tests

Primary automated coverage:

- `tests/test_speech_blocks_service.py`
- `tests/test_speech_blocks_narrator_split_service.py`
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
