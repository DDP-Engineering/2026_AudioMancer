<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# AI Translation

## 1. Purpose

AI Translation converts canonical chunks into one strictly validated,
operator-reviewable translation document.

## 2. Responsibilities

- Own the authoritative translated-chunk document, strict status/chunk schema,
  atomic writes, summaries, synchronization after chunk changes, and resets.
- Translate/retranslate chunks with AI Runtime budgets, prompts, usage,
  cancellation, resumable checkpoints, and explicit approval state.
- Project document/state notes into the translation workflow and invalidate
only permitted downstream work.
- Present profile selection, chunk review/edit/debouncing, retranslation,
approval, localization, and busy-state controls.

## 3. Public Interface

- `ai_translation_service` loads, validates, starts/resumes, retranslates,
  edits, approves, summarizes, synchronizes, and resets the authoritative
  translation document.
- `build_ai_translation_state(...)` and
  `build_ai_translation_profile_state(...)` project persistence, manifest,
  settings, and an optional live profile selection into page state.
- `AiTranslationPage` exposes start, reset, edit, approve, and selected-chunk
  retranslation signals; `MainWindow._refresh_ai_translation_page_state(...)`
  supplies the session-local profile selection across state rebuilds.

## 4. Key Behaviors

- `REQ-UX-7e8fb80a` - identical refresh content leaves both Qt editor documents
  untouched so editing context survives.
- `REQ-UX-31620904` - genuinely different authoritative content replaces stale
  editor text under the programmatic-loading guard.
- `REQ-UX-1373b3b5` - chunk-list rebuilds restore selection by stable chunk ID.
- `REQ-FUNC-9a7e98c9` - pending manual text persists before worker dispatch and
  cannot fire later from the debounce timer.
- `REQ-UX-eb55be5b` - a live enabled profile survives refresh, with configured
  default then first-enabled fallback.
- `REQ-UX-3dae2eb0` - selected retranslation is unavailable before translation
  starts and while the page is busy.
- `REQ-FUNC-ee95beb7` - the controller rejects a pre-start retranslation request
  without worker, prompt, error, document, or manifest side effects.

## 5. Implementation Overview

The service validates `translated_text.json`, aligns it to canonical chunk IDs,
and progresses status from running through review/completed. The state service
builds page state and notes, including enabled-profile fallback from a live page
selection. The main window captures that session-local selection before each
refresh. Controller methods route valid page actions through the shared runner
and reject selected retranslation before translation exists. The page merges
source/translated chunks by stable ID, leaves identical editor documents
untouched, flushes edits before worker dispatch and review actions, and gates
retranslation on a started idle state.

## 6. Dependencies

Text Chunking provides canonical chunks. AI Runtime supplies budget, prompts,
provider calls, token usage, and logs. Operation Orchestration handles
cancellation/reset; Project Lifecycle owns the manifest; PySide6 supports the
review surface.

## 7. Inputs And Outputs

Inputs are project/manifest, canonical chunks, target language, enabled profile,
optional instructions, cancellation/progress callbacks, and operator edits.
Outputs are one translated document, summaries/status notes, AI logs/usage,
approval state, and page display data. `translated_text.json` is the sole
durable translation source; separate translation report/state files are not a
parallel contract.

## 8. Data Contracts

Canonical source chunks are loaded through `chunking_document_service`; an
incompatible Chunking document is rejected.

The document contains target language, status, usage/budget/instructions, and
ordered `{chunk_id, translated_text, approved}` records. Chunk IDs must match
canonical source; completed means every source chunk is nonempty and approved.
Manual/retranslated text clears approval; malformed/incompatible documents
raise a translation-document error rather than silently merging data.
Generation checkpoints only complete chunks: an interrupted chunk's partial
segments are not persisted. A failed selected retranslation keeps the prior
text and approval state rather than replacing it with a partial result.

## 9. Workflow Integration

The component consumes Text Chunking and provides approved target-language
content to Character Discovery and Speech Blocks. Chunk changes synchronize or
invalidate only affected translations; reset preserves configured narrator work.

## 10. Usage

Operators choose an AI profile and use Start/Resume, edit/retranslate, then
approve individual or all chunks. The live enabled profile and selected chunk
survive ordinary state refreshes; same-content edit persistence does not reset
the editor cursor, selection, undo history, or scroll positions. Start/Resume
persists any pending edit before the worker can read the document, and selected
retranslation is unavailable until translation has started. Controllers call
start/continue and refresh state after each operation. Direct callers must use
the authoritative document helpers, never separate report/state files.

## 11. Validation And Tests

Primary automated coverage:

- `tests/test_ai_translation_service.py`
- `tests/test_ai_translation_state_service.py`
- `tests/test_ai_translation_ui_controller.py`
- `tests/test_ai_translation_page.py`
- `tests/test_main_window_ai_profiles.py`

These cover document schema/authority, resume/retranslation/approval/reset,
state summaries/notes, controller dispatch, and page editing/busy controls.
Minimum validation after a change: run the focused modules above with
`uv run pytest`, plus `uv run python -m py_compile` and `uv run ruff check` on
changed files.

## 12. Limitations And Future Work

Translation quality and target-language fluency require operator review; the
component validates structural, not semantic, correctness. No live provider
integration test replaces controlled manual verification of a chosen model.

## Files

From the adopted component map:

- `04_Software/AudioMancer/prompts/text_translation_*.txt`
- `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ai_translation_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/ai_translation_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/main_window.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/ai_translation_page.py`
- `04_Software/AudioMancer/tests/test_ai_translation_page.py`
- `04_Software/AudioMancer/tests/test_ai_translation_service.py`
- `04_Software/AudioMancer/tests/test_ai_translation_state_service.py`
- `04_Software/AudioMancer/tests/test_ai_translation_ui_controller.py`
- `04_Software/AudioMancer/tests/test_main_window_ai_profiles.py`
