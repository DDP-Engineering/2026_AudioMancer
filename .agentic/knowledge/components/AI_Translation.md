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

## 3. Implementation Overview

The service validates `translated_text.json`, aligns it to canonical chunk IDs,
and progresses status from running through review/completed. The state service
builds page state and notes; controller methods route page actions through the
shared runner; the page merges source/translated chunks and flushes edits before
selection, approval, retranslation, or close.

## 4. Dependencies

Text Chunking provides canonical chunks. AI Runtime supplies budget, prompts,
provider calls, token usage, and logs. Operation Orchestration handles
cancellation/reset; Project Lifecycle owns the manifest; PySide6 supports the
review surface.

## 5. Inputs And Outputs

Inputs are project/manifest, canonical chunks, target language, enabled profile,
optional instructions, cancellation/progress callbacks, and operator edits.
Outputs are one translated document, summaries/status notes, AI logs/usage,
approval state, and page display data. `translated_text.json` is the sole
durable translation source; separate translation report/state files are not a
parallel contract.

## 6. Data Contracts

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

## 7. Workflow Integration

The component consumes Text Chunking and provides approved target-language
content to Character Discovery and Speech Blocks. Chunk changes synchronize or
invalidate only affected translations; reset preserves configured narrator work.

## 8. Usage

Operators choose an AI profile and use Start/Resume, edit/retranslate, then
approve individual or all chunks. Controllers call start/continue and refresh
state after each operation. Direct callers must use the authoritative document
helpers, never separate report/state files.

## 9. Validation And Tests

Primary automated coverage:

- `tests/test_ai_translation_service.py`
- `tests/test_ai_translation_state_service.py`
- `tests/test_ai_translation_ui_controller.py`
- `tests/test_ai_translation_page.py`

These cover document schema/authority, resume/retranslation/approval/reset,
state summaries/notes, controller dispatch, and page editing/busy controls.
Minimum validation after a change: run the focused modules above with
`uv run pytest`, plus `uv run python -m py_compile` and `uv run ruff check` on
changed files.

## 10. Limitations And Future Work

Translation quality and target-language fluency require operator review; the
component validates structural, not semantic, correctness. No live provider
integration test replaces controlled manual verification of a chosen model.
