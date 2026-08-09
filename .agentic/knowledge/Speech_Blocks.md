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

The orchestration service resolves source chunks and voice assignments, assembles one authoritative `speech_blocks.json` document (source identity, AI/budget metadata, resume checkpoint, and blocks), and coordinates reset/approval transitions. Normalization and text-split services provide deterministic content/speaker/identifier handling and size-aware splits. Report and operation-state views are recomputed as projections from that single document through `load_speech_blocks_report()` and `load_operation_state()`; one public read or mutation shares one resolved source context/count across its projections and log-path work. The controller and page route operations, guarded edits, selection, warnings, and review actions through the shared runner.

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
- Speech Block identifiers are unique within the authoritative current document, not across deleted history. A deleted identifier may be allocated again; the controller therefore removes the deleted Audio Blocks row and generated WAV before manifest refresh or any later insertion can reuse it. Service-only deletion callers must provide the same downstream cleanup.
- Source selection preserves canonical ordering; normalization and splits preserve usable spoken text while keeping blocks within configured TTS limits.
- Cached VoiceWeaver budgets use a persisted `max_new_tokens` generation-range
  default when effective/default model parameters omit it, preserving the
  runtime-reported split capacity (`REQ-FUNC-1fef6b33`).
- Dash-led paragraphs retain contiguous source-span and atomic-unit offsets even
  when the opening turn has no whitespace after its dash and later replies do;
  attribution units remain selectable instead of forcing a narrator fallback
  (REQ-FUNC-6292ab33).
- Every TTS-budget split stores exact, ordered `source_text` slices whose
  concatenation reproduces the original block character-for-character,
  including leading or trailing whitespace-only spans. When model audio text
  differs, spoken parts retain that audio wording while source provenance is
  partitioned monotonically without duplication or loss (REQ-FUNC-15a96219).
- Source parsing and spoken dialogue unwrapping share one authoritative quote
  pair table, including alternative German/Romanian low-quote closers, Polish
  low quotes, reversed guillemets, and CJK pairs (REQ-FUNC-5e94d565).
- Persistence is one authoritative `speech_blocks.json` document object with a fixed top-level field set (`status`, `source`, `ai_profile_id`, `instructions`, `scene_ambience`, `response_contract`, `token_usage`, `budget_metadata`, `checkpoint`, `failure`, `blocks`).
- Counts, warnings, stage status, and progress are recomputed on read; the document keeps only `source.fingerprint` (not a copy of source-chunk text) and re-resolves source chunks from upstream (`chunks_text.json` / `translated_text.json`).
- A non-object, corrupt, or missing document reads as not-started (`None`); reset removes the authoritative document.
- IDs use a chunk-local minimum-width `CCCC-BBBBBB` form and the complete
  numeric chunk token, so chunks above 9999 retain distinct namespaces and
  canonical book order while earlier IDs remain unchanged (REQ-FUNC-31425199).
  Manual insertion creates an unapproved narrator narration row; deletion can
  remove the final row for a chunk without removing that source chunk.
  Compatible review/completed resume locates the first uncovered source chunk
  by ordered identity, regenerates missing chunks exactly once, and skips later
  covered chunks without changing their blocks or approvals; running/failed
  checkpoints retain their active chunk and segment cursor semantics
  (REQ-REL-63e230dd). Generated output remains `review_pending` until every
  persisted block is approved, and resumptions require a compatible source
  snapshot and response-contract marker.
- Multi-segment generation assigns contiguous chunk-local order before every
  checkpoint. Resuming an active segment continues after the already persisted
  rows, so intermediate, resumed, and uninterrupted documents preserve the same
  canonical source order (REQ-REL-0e236c91).
- `same_narrator` segmentation is deterministic and total: concatenating the
  `source_text` of a chunk's blocks reproduces that chunk character for
  character, and the service raises rather than persisting a lossy plan. A
  sentence is never cut, and a boundary is never placed while a quotation is
  open, so a multi-sentence quotation stays in one block. A single sentence that
  alone exceeds the TTS budget is kept whole and flagged `tts_budget_exceeded`,
  because TTS Audio Blocks splits it again at generation time against the real
  loaded-model budget.
- Same-narrator quotation tracking tests a pending closer before treating the
  same glyph as another opener, so German `„…“` and Romanian `„…”` quotations
  close correctly and later narration can resume budget splitting
  (REQ-FUNC-c13373e7).
- Chunking records how confident Text Cleanup was about a paragraph rebuilt
  across a page break. Speech Blocks carries that verdict through, so a chunk
  with a non-`strong` `cleanup_boundary_confidence` marks its blocks
  `weak_source_boundary` and `needs_review` instead of hiding the uncertainty.
- A response contract incompatible with deterministic same-narrator
  segmentation is not resumable; generation restarts to avoid mixing two
  segmentations in one document.
- Operator edits, warning cleanup, and approval updates preserve the persisted
  `deterministic_narrator_blocks` marker for same-narrator documents
  (REQ-FUNC-10095db1).
- While a block editor is active, the page disables profile, chunk, generation,
  approval-all, reset, and re-split controls and applies language changes
  without replacing the typed speech or Scene Ambience payload, caret, or text
  selection (REQ-UX-6d27b63d).
- Entering or declining Edit performs no Speech Blocks persistence and does not
  clear warning flags; warning cleanup remains owned by a successful
  `update_speech_block` commit, while failed saves retain the warnings
  (REQ-FUNC-35098598).
- Scene-ambience insertion remaps each matched `after_speech_block_id` from the
  spoken row's old identifier to its post-insertion identifier, including when
  opener ambience shifts every spoken row (REQ-DATA-f0eb775c).

## 7. Workflow Integration

Speech Blocks follows Voice Profiles and is the review gate before TTS Audio Blocks. An operator must resolve warnings and approve the block plan; material edits reset only affected generated audio and assembly work.

## 8. Usage

Open Speech Blocks after selecting voices, generate or resume the block plan,
inspect list rows and warnings, edit the selected block deliberately, then save
to commit the edit and clear its warning flags before approval. Active editor
payloads remain intact when the interface language changes. Use reset when
upstream character, language, or voice changes make the current plan
incompatible.

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
editing/selection. Instrumented projection tests enforce at most one full source
resolution per public read or review mutation and one underlying chunking/translation
document read for original-language and approved-translated page paths, while deletion coverage proves a
recycled identifier cannot inherit the removed row or WAV. Minimum validation after a change: run the focused modules
above with `uv run pytest`, plus `uv run python -m py_compile` and
`uv run ruff check` on changed files. Operators must manually review semantic
speaker assignment, ambience suitability, and pause interpretation.

## 10. Limitations And Future Work

Automated tests establish deterministic structural and invalidation contracts, but cannot decide whether a dialogue attribution, ambience prompt, pause, or pronunciation-oriented split is artistically correct. The operator remains responsible for reviewing the speech plan before audio is generated.

## Files

From the adopted component map:

- `04_Software/AudioMancer/prompts/scene_ambience_*.txt`
- `04_Software/AudioMancer/prompts/speech_blocks_*.txt`
- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_normalization_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_narrator_split_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_report_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_text_split_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/speech_blocks_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/speech_blocks_page.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_normalization_service.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_narrator_split_service.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_page.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_report_state_service.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_service.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_single_document_contract.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_state_service.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_text_split_service.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_ui_controller.py`
