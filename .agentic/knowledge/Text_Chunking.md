<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Text Chunking

## 1. Purpose

Text Chunking turns canonical cleaned text into ordered, persisted chunks that
operators can inspect and edit before translation, character discovery, and
speech generation. It consumes Cleanup's typed paragraph roles and provenance
rather than rediscovering document structure from plain text.

## 2. Responsibilities

- Accept only a completed Cleanup document whose output hash matches
  `clean_text.txt`.
- Slice exact Cleanup paragraph offsets and propagate their structural roles.
- Derive deterministic chapter/paragraph chunks and one canonical Chunking
  document.
- Count bare Roman-numeral headings only when they are valid uppercase Roman
  values; ordinary words and invalid numeral strings remain paragraph text.
- Accept only the exact current canonical project-artifact schema and reject
  incomplete or incompatible Chunking documents.
- Bound deterministic running-document checkpoints by processed-paragraph and
  monotonic-time intervals while always persisting terminal lifecycle state.
- Run AI-assisted semantic chunking with validated paragraph descriptors,
  bounded context windows, resumable state, counted and disclosed fallback
  windows, and usage logs.
- Keep recognized scene separators as structural evidence while omitting their
  text from generated chunks, splitting ranges on either side, and marking the
  following narratable chunk's leading boundary.
- Project persisted chunks and readiness into page state; accept controlled
  insert, delete, and text edits only for completed documents, while resumable
  documents retain their checkpoints unchanged.
- Present deterministic/AI actions, profile and strategy selection, previews,
  editing, and localized find behavior through the existing page/controller.

It consumes Cleanup output but does not own extraction, Cleanup adjudication,
generic AI transport, or downstream translation/speech semantics.

## 3. Implementation Overview

`chunking_document_service` is the strict persistence boundary for the sole authoritative
`chunks_text.json` document.
`cleanup_metadata_service.load_completed_paragraph_records` gates and slices
the Cleanup input for both chunking modes. `deterministic_chunking_service`
materializes each narratable paragraph while retaining Cleanup provenance. It
writes one initial running document, checkpoints after 200 additional processed
paragraphs or 2.0 elapsed monotonic seconds, throttles non-terminal progress to
0.1-second intervals, and writes terminal completion, cancellation, or failure
state before returning or propagating. `ai_chunking_service` turns the same paragraph records into
budgeted windows, requires source-aligned descriptors from the provider,
checkpoints each consecutive valid descriptor prefix, and retries from the
first uncommitted paragraph when a later descriptor is invalid. If no valid
prefix exists, every window, including the only or final window, uses the same
deterministic fallback path: it keeps explicit headings and scene separators
as structural boundaries before using a complete-window chunk, increments the
persisted fallback count once, and emits an absolute paragraph-range progress
message. Completion carries the singular or plural fallback warning into the
report and manifest summary. Both
modes use
`cleanup_text_analysis_service.is_scene_separator_artifact` at materialization
time. A separator ends the current narratable range but never becomes a chunk;
separator-only input is rejected before an authoritative document is written.

`text_chunking_state_service` derives page state and persists operator changes
through workflow-impact rules. It selects notes from the authoritative
document's lifecycle before report summaries: running states show a localized
checkpoint-based in-progress note; failed and cancelled states show the resume
note while retaining warnings and AI token usage; completed states show the
summary and rerun warning; and absent documents retain ready/profile guidance.
It never fabricates a total-progress value. Its service boundary rejects edit, insertion,
and deletion for `running`, `cancelled`, and `failed` documents before any
write or downstream invalidation, preserving the resume checkpoint and all
artifacts; completed documents retain the existing manual-mutation behavior.
The controller dispatches work through the
shared operation runner and refreshes the project state. `TextChunkingPage`
renders profiles, strategy, previews, edits, and search. Saving leaves edit
mode and reprojects the current durable page model before the synchronous
controller request; a successful request refreshes that model from persisted
state, while a rejected request cannot leave the draft in the model, list, or
read-only editor.

## 4. Dependencies

Internal dependencies include Text Cleanup artifacts, AI Runtime budget,
prompt/provider/token services, Project Lifecycle manifest persistence,
Operation Orchestration state/impact/runtime helpers, settings/UI state, and
Qt widgets. External dependencies are PySide6 and project-local JSON/text
storage.

## 5. Inputs And Outputs

Inputs are the active project and manifest, completed `cleanup.json`,
hash-matching `clean_text.txt`, chosen deterministic or AI strategy, enabled
profile, optional instructions/context mode, and user chunk-edit requests.

The sole durable Chunking output is `chunks_text.json`. Operation summaries,
progress, budget details, provider/model settings, and AI log paths are
runtime-only projections. AI transaction logs remain separate diagnostics.
Reset clears Chunking-owned derived state so incompatible data cannot survive
explicit or automatic recovery.
A manual edit, insert, or delete atomically rewrites the canonical document
and manifest, synchronizes affected translations, removes affected character
evidence, Speech Blocks, and Audio Blocks, then resets Audio Assembly.

## 6. Data Contracts

The document has an exact root-object schema containing lifecycle, mode,
manual-adjustment, source fingerprint, semantic strategy, operator
instructions, cumulative token usage, warnings, resume checkpoint, fallback
count, and ordered chunks. Every chunk has exactly:

- `chunk_id`
- `sequence_index`
- `text`
- `cleanup_boundary_confidence`
- `cleanup_joined_across_page_break`
- `cleanup_warning_flags`
- `cleanup_role`
- `starts_after_scene_separator`

`cleanup_role` is one of Cleanup's supported non-artifact roles. Generated
chunks never carry `scene_separator` because separator paragraphs are
non-narratable hard boundaries. `starts_after_scene_separator` is a required
boolean that records whether one or more omitted separators immediately precede
the chunk. Inserted and edited chunks retain a valid role. The current
Translation, Character Discovery, Speech Blocks, Audio Blocks, and Audio
Assembly pipeline does not consume this field; issue #35 retains it as required
structural metadata without adding scene-transition runtime behavior.

`cleanup_warning_flags` carries only Cleanup's explicit warning-code set:
`deterministic_fallback`, `unknown_line_boundary`, and
`page_transition_repaired`. Cleanup reason codes remain provenance and do not
change the strict Chunking field set. Bare Roman-numeral detection is shared by
Cleanup analysis, deterministic Chunking, and the canonical report projection:
it uses uppercase standard subtractive grammar and rejects lowercase or invalid
forms such as `civil`, `mix`, `did`, `IIII`, and `IC`.

Only the current canonical project-artifact schema is supported. A chunk that
omits `starts_after_scene_separator`, a non-object root, or any other invalid
shape is incompatible. Strict direct loads raise
`IncompatibleChunkingDocumentError`.
During project open, Project Lifecycle handles a content-caused incompatibility
by resetting Chunking and downstream derived artifacts, retrying validation
once, and marking the open result for a post-activation operator message. This
bounded reset preserves Source, Extraction, and Cleanup.
Filesystem read errors remain fatal and cause no reset.
The explicit Reset Chunking action uses the same scoped artifact ownership.

Every deterministic running, cancelled, or failed checkpoint stores a
resume-consistent pair: `chunks` contains exactly the narratable output from the
processed paragraph prefix and `next_paragraph` identifies the following
one-based paragraph, including when processed separators produce no chunk.
Successful completion writes exactly one terminal document with
`next_paragraph=null` and final warnings. AI-assisted window checkpoint cadence
is unchanged.

AI descriptor ranges must align to ordered Cleanup paragraph records. Resume
restores the document's strategy, instructions, committed chunks, checkpoint,
usage, and fallback count, but invokes the currently selected profile with
current runtime budget settings and creates a fresh AI log. Edits operate by
chunk ID rather than UI row and require downstream-impact review.

Descriptor anchors use normalized lexical prefixes. Punctuation-only
paragraphs such as `* * *` are accepted only by an exact complete normalized
anchor. A malformed descriptor after one or more consecutive valid
descriptors invalidates only the tail; the valid prefix is committed and the
next request begins at the first uncommitted paragraph. When no prefix is
valid, fallback recognizes stored `heading` and `scene_separator` roles plus
conservative user-edited marker-only forms. Repeated identical asterisk, dash,
underscore, tilde, number-sign, equals-sign, bullet, or diamond glyphs and
common singleton ornaments are recognized. Ambiguous punctuation and lexical
text such as `...`, a single dash, `### Title`, or `x x x` remains narratable
unless Cleanup explicitly assigned `scene_separator`.

Manual mutations are accepted only for a strictly valid completed authoritative
document. A running, cancelled, or failed document rejects text edit, insert,
and delete with operator guidance to finish, resume, or reset the run; its
checkpoint and all persisted Chunking metadata remain unchanged. Manual
operations resequence `sequence_index` without changing surviving
`chunk_id` values. Deletion rejects an empty resulting set; insertion creates
an empty `chunk-####` next to its selected anchor with no inferred scene
boundary. Text edits preserve the selected chunk's boundary flag. Deleting a
marked chunk transfers the flag to the next surviving chunk when one exists.
They preserve unrelated root metadata and set `manual_adjusted` in the
authoritative document.

## 7. Workflow Integration

The component begins only after validated Text Cleanup completion. Paused,
running, malformed, or output-hash-mismatched Cleanup state is rejected even
when a text output happens to exist. Approved chunks feed AI Translation,
Character Discovery, Speech Blocks, and later audio stages. Any manual edit or
recomputation uses Operation Orchestration to reset only affected downstream
state. Those downstream components currently consume chunk content and
provenance but do not consume `starts_after_scene_separator`.

## 8. Usage

Operators select deterministic chunking or an enabled AI profile/semantic
strategy on the Text Chunking page. Controllers dispatch the requested mode
through the shared runner, then refresh page and manifest state. To correct one
chunk, select it and use edit, insert, or delete after reviewing the
confirmation dialog. Page open is read-only and does not create state.

Direct callers must provide a valid project manifest plus the same profile,
cancellation, and progress contracts used by the UI.

## 9. Validation And Tests

Primary automated coverage:

- `tests/test_chunking_single_document_contract.py`
- `tests/test_deterministic_chunking_service.py`
- `tests/test_ai_chunking_service.py`
- `tests/test_ai_chunking_descriptor_contract.py`
- `tests/test_cleanup_chunking_contract.py`
- `tests/test_project_workspace_service.py`
- `tests/test_operation_runtime_service.py`
- `tests/test_text_chunking_state_service.py`
- `tests/test_text_chunking_ui_controller.py`
- `tests/test_text_chunking_page.py`

These cover strict Cleanup gating, role propagation, canonical-only
persistence, deterministic artifacts/chapter behavior, AI descriptor
validation/resume/fallback contracts (including single and final windows),
scene-separator recognition and omission, production-path lifecycle notes,
state edits/invalidation, controller dispatch, and page behavior.
Minimum validation after a change: run the focused modules above with
`uv run pytest`, plus `uv run ruff check` on changed files.

## 10. Limitations And Future Work

AI boundaries remain advisory. Invalid tails are retried after committed valid
prefixes; responses with no valid prefix use deterministic structural
fallback and may still produce a larger window chunk when no explicit
structure exists. Token budgeting is estimated by AI Runtime. Operator review
remains available for semantic corrections.

## Files

From the adopted component map:

- `04_Software/AudioMancer/prompts/text_chunking_*.txt`
- `04_Software/AudioMancer/src/audiomancer/services/ai_chunking_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/chunking_document_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/deterministic_chunking_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/text_chunking_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/text_chunking_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/text_chunking_page.py`
- `04_Software/AudioMancer/tests/test_ai_chunking_descriptor_contract.py`
- `04_Software/AudioMancer/tests/test_ai_chunking_service.py`
- `04_Software/AudioMancer/tests/test_chunking_single_document_contract.py`
- `04_Software/AudioMancer/tests/test_cleanup_chunking_contract.py`
- `04_Software/AudioMancer/tests/test_deterministic_chunking_service.py`
- `04_Software/AudioMancer/tests/test_text_chunking_page.py`
- `04_Software/AudioMancer/tests/test_text_chunking_state_service.py`
- `04_Software/AudioMancer/tests/test_text_chunking_ui_controller.py`
- `04_Software/AudioMancer/tests/test_localization_parity.py`

The state-service regression parameterizes every resumable status and manual
operation, and verifies that authoritative Chunking, project, and downstream
artifact byte snapshots remain unchanged after rejection.
