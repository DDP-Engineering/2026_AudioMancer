<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# AI Translation

## Routing

For translated chunk documents, review edits, debouncing or translation jobs,
start at `ai_translation_service`, `AiTranslationPage` and their service/page
controller tests. Home option reset policy belongs to Project Lifecycle.

## Purpose and boundaries

AI Translation converts canonical chunks into one strictly validated,
operator-reviewable translation document.

### Responsibilities

- Own the authoritative translated-chunk document, strict status/chunk schema,
  atomic writes, summaries, synchronization after chunk changes, and resets.
- Translate/retranslate chunks with AI Runtime budgets, prompts, usage,
  cancellation, resumable checkpoints, and explicit approval state.
- Restrict translation targets to English, Romanian, German, French, Russian,
  Portuguese, Spanish, and Italian while retaining the source-script guard for
  unsupported Latin/Cyrillic alternatives and CJK text (`REQ-FUNC-f04f2515`).
- Project document/state notes into the translation workflow and invalidate
only permitted downstream work.
- Present profile selection, chunk review/edit/debouncing, retranslation,
approval, localization, and busy-state controls.

## Public interface

Home option changes call `flush_pending_translation_edit` before creating a
reset plan. This persists the latest manual edit and stops its queued save,
including when the operator cancels the option change. Confirmed language resets
cannot leave a queued write targeting a removed document; mode changes preserve
the latest translation. Project Lifecycle owns this coordination.

- `ai_translation_service` loads, validates, starts/resumes, retranslates,
  edits, approves, summarizes, synchronizes, and resets the authoritative
  translation document; `manifest_target_language(...)` is the canonical
  supported-value/default resolver shared by translation and chunking state
  projections (`REQ-NFR-7fcf36ea`).
- `build_ai_translation_state(...)` and
  `build_ai_translation_profile_state(...)` project persistence, manifest,
  settings, and an optional live profile selection into page state.
- `AiTranslationPage` exposes start, reset, edit, approve, and selected-chunk
  retranslation signals; `MainWindow._refresh_ai_translation_page_state(...)`
  supplies the session-local profile selection across state rebuilds.

## Key behaviors

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
- `REQ-FUNC-a0ab9df4` - interrupted selected-chunk retranslation preserves all
  chunk text and approvals, records accrued usage, and derives review status.
- `REQ-FUNC-9889967c` - start/continue selects one instruction value by
  persisted resumability and uses it for budgets, requests, and persistence.
- `REQ-FUNC-d911e006` - interrupted main batch translation keeps its distinct
  resumable failed/cancelled status and completed chunk checkpoints.
- `REQ-FUNC-e38de6a1` - budgeted requests preserve true paragraph breaks and
  rejoin pieces of one oversized paragraph with spaces.
- `REQ-FUNC-6c7c71d9` - the source-text budget is bounded by the translation the
  profile's maximum output tokens can still return, not by the context window
  alone. Translation is the only AI operation whose reply is as long as its
  request, so this cap lives here rather than in the shared budget helper, which
  AI chunking relies on to allow a text budget far larger than its own reply.
- `REQ-FUNC-cfa5468c` - when that bound leaves less source text than one request
  needs, translation refuses and names the maximum output tokens as the setting
  to raise, rather than blaming the context window that was not the constraint.
- `REQ-UX-dc3def51` - the chunk list sits above the chunk text panes in one
  vertical splitter, so the operator sets the split between them.
- `REQ-UX-d6fc781d` - that chunk list pane stops shrinking at 150 pixels.
- `REQ-UX-3a39f53e` - it grows no further than half the shared splitter height,
  except on a window short enough that the minimum prevails.

### Implementation overview

`ai_translation_service` coordinates jobs and review. `translation/document.py`
validates the document and projects records against current source IDs and text.
`translation/planning.py` assembles bounded paragraph-aware requests.
`translation_ai_service` owns the budget, prompts, policy identity and exact
reply validation. `translation_publication_service` compares old and candidate
approved source, stages the document and manifest, and uses the same recoverable
file replacement primitive as Chunking. The controller refreshes published state
and reports errors. A failed autosave leaves the edit pending and dependent UI
actions wait for a successful retry.

Budgeting limits the assembled estimated source text by both the context input
and reply capacity. Empty canonical chunks are omitted. Oversized paragraphs
split at sentences or words and preserve leading paragraph relationships.
An unbreakable span over budget fails clearly. Each request reply must contain
exactly one nonempty `translated_text` string with the same paragraph count as
its fragment. Completed fragments of an interrupted chunk do not publish as
partial translated text.

### Dependencies

Text Chunking provides canonical chunks. AI Runtime supplies budget, prompts,
provider calls, token usage, and logs. Operation Orchestration handles
cancellation/reset; Project Lifecycle owns the manifest; PySide6 supports the
review surface.

### Inputs and outputs

Inputs are project/manifest, canonical chunks, target language, enabled profile,
optional instructions, cancellation/progress callbacks, and operator edits.
Outputs are one translated document, summaries/status notes, AI logs/usage,
approval state, and page display data. `translated_text.json` is the sole
durable translation source; separate translation report/state files are not a
parallel contract.

## Invariants

Canonical source chunks are loaded through `chunking_document_service`; an
incompatible Chunking document is rejected.

The document contains target language, status, usage, budget, instructions, an
optional nonsecret request fingerprint, and ordered translated records. Each
new translation binds its chunk ID to a SHA-256 fingerprint of the exact canonical
source text. A changed fingerprint removes the affected translation from the
current projection. A legacy record lacking a fingerprint retains its text for
review with effective approval withheld. Explicit approval binds it to the
current source. Editing or replacing translated text clears that row's approval.

Only a completed document with the current nonempty chunk coverage and verified
approval qualifies as translated input. Character Discovery, Speech Blocks,
narrator analysis and completion evidence use the same eligibility rule, with
their applicable language constraint. Publication invalidates dependent files
when this effective source changes, including projects without Character
Discovery, and preserves narrator definition. A Chunking edit that changes the
source kind retires the same dependent results inside its staged transaction.
Narrator analysis requires both the project target and the voice language to
match the approved translation. Existing translated Speech Blocks must match
the currently approved text before generating new speech or audio outputs.

A valid reply with a different paragraph count triggers one correction request
for the same fragment, with the exact expected count. The budget reserves the
correction instruction and usage includes both calls. A repeated mismatch
reports both counts and leaves the unfinished chunk unsaved.

The batch checkpoints complete chunks and records a failed or cancelled terminal
state after setup, request or final publication failure when storage permits.
Resume retains instructions and verified completed work, and warns before
requests made under a changed policy. A failed selected replacement keeps the
prior text and approvals and accounts for accrued request usage. Failed
publication restores originals or reports their named recovery location.

### Usage

Operators choose an AI profile and use Start/Resume, edit/retranslate, then
approve individual or all chunks. The chunk list and the two chunk text panes
share a vertical splitter the operator drags to favour scanning the list or
reading one translation, bounded by a 150 pixel floor and a half-height ceiling.
Invalid documents have an available confirmed Reset action.
The live enabled profile and selected chunk
survive ordinary state refreshes; same-content edit persistence does not reset
the editor cursor, selection, undo history, or scroll positions. Start/Resume
persists any pending edit before the worker can read the document, and selected
retranslation is unavailable until translation has started. Resume keeps the
document's original general instructions, while a newly supplied value applies
to a new or non-resumable start; selected-retranslation instructions apply only
to that attempt. Cancelling or failing one selected retranslation keeps the
existing review result available. Controllers call start/continue and refresh
state after each operation. Direct callers must use the authoritative document
helpers, never separate report/state files.

### Verification

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

### Operational limits

Translation quality and target-language fluency require operator review; the
component validates structural, not semantic, correctness. No live provider
integration test replaces controlled manual verification of a chosen model.

## Change map

| Change requested | Start with | Focused verification |
|---|---|---|
| Translation document, budget or generation | ai_translation_service | test_ai_translation_service.py |
| Review controls and debounce | AiTranslationPage, ai_translation_ui_controller | translation page/controller tests |
| Home option reset with pending edits | home_ui_controller | test_home_option_change_settles_pending_translation_before_planning |

## Files

From the adopted component map:

- `05_Software/AudioMancer/prompts/text_translation_*.txt`
- `05_Software/AudioMancer/src/audiomancer/translation/{document,planning}.py`
- `05_Software/AudioMancer/src/audiomancer/services/translation_ai_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/translation_publication_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/ai_translation_state_service.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/ai_translation_ui_controller.py`
- `05_Software/AudioMancer/src/audiomancer/ui/main_window.py`
- `05_Software/AudioMancer/src/audiomancer/ui/pages/ai_translation_page.py`
- `05_Software/AudioMancer/tests/test_ai_translation_page.py`
- `05_Software/AudioMancer/tests/test_ai_translation_service.py`
- `05_Software/AudioMancer/tests/test_ai_translation_state_service.py`
- `05_Software/AudioMancer/tests/test_ai_translation_ui_controller.py`
- `05_Software/AudioMancer/tests/test_main_window_ai_profiles.py`
