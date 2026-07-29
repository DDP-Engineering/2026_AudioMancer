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
- Run AI-assisted semantic chunking with validated paragraph descriptors,
  bounded context windows, resumable state, fallback windows, and usage logs.
- Prefer heading, scene, structural, and sentence-complete cuts before applying
  size-balance costs.
- Keep recognized scene separators as structural evidence while omitting their
  text from generated chunks, splitting ranges on either side, and marking the
  following narratable chunk's leading boundary.
- Use a mid-sentence hard-limit cut only when a single sentence is itself
  oversized, and report that fallback.
- Project persisted chunks and readiness into page state; make controlled
  insert, delete, and text edits invalidate downstream work appropriately.
- Present deterministic/AI actions, profile and strategy selection, previews,
  editing, and localized find behavior through the existing page/controller.

It consumes Cleanup output but does not own extraction, Cleanup adjudication,
generic AI transport, or downstream translation/speech semantics.

## 3. Implementation Overview

`chunking_document_service` is the strict persistence boundary for the sole authoritative
`chunks_text.json` document.
`cleanup_metadata_service.load_completed_paragraph_records` gates and slices
the Cleanup input for both chunking modes. `deterministic_chunking_service`
uses typed roles and semantic cut priority, while `ai_chunking_service` turns
the same paragraph records into budgeted windows, requires source-aligned
descriptors from the provider, checkpoints each consecutive valid descriptor
prefix, and retries from the first uncommitted paragraph when a later
descriptor is invalid. If no valid prefix exists, deterministic fallback keeps
explicit headings and scene separators as structural boundaries before using
a complete-window chunk. Both modes use
`cleanup_text_analysis_service.is_scene_separator_artifact` at materialization
time. A separator ends the current narratable range but never becomes a chunk;
separator-only input is rejected before an authoritative document is written.

`text_chunking_state_service` derives page state and persists operator changes
through workflow-impact rules. The controller dispatches work through the
shared operation runner and refreshes the project state. `TextChunkingPage`
renders profiles, strategy, previews, edits, and search.

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
Reset also owns the obsolete `chunking_checkpoint.json`,
`chunking_report.json`, and `chunking_state.json` names so incompatible derived
state cannot survive explicit or automatic recovery.
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
the chunk. Inserted and edited chunks retain a valid role.
Legacy root arrays and obsolete `chunking_report.json` or
`chunking_state.json` sidecars are never migrated. Strict direct loads raise
`IncompatibleChunkingDocumentError`. During project open, Project Lifecycle
handles a content-caused incompatibility by resetting Chunking and downstream
derived artifacts, retrying validation once, and marking the open result for a
post-activation operator message; it preserves Source, Extraction, and Cleanup.
Filesystem read errors remain fatal and cause no reset.
The explicit Reset Chunking action uses the same scoped artifact ownership.

Cut candidates are ordered by semantic meaning: heading, scene separator,
other structural role (`list_item`, `verse`, `preformatted`, or `footnote`),
sentence-complete body, then incomplete body. Target-size balance is a soft
cost and cannot override that order.

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

Manual operations resequence `sequence_index` without changing surviving
`chunk_id` values. Deletion rejects an empty resulting set; insertion creates
an empty `chunk-####` next to its selected anchor with no inferred scene
boundary. Text edits preserve the selected chunk's boundary flag. Deleting a
marked chunk transfers the flag to the next surviving chunk when one exists.
They preserve unrelated root metadata and set `manual_adjusted` without adding
sidecars.

## 7. Workflow Integration

The component begins only after validated Text Cleanup completion. Paused,
running, malformed, or output-hash-mismatched Cleanup state is rejected even
when a text output happens to exist. Approved chunks feed AI Translation,
Character Discovery, Speech Blocks, and later audio stages. Any manual edit or
recomputation uses Operation Orchestration to reset only affected downstream
state.

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
- `tests/test_cleanup_v2_chunking_contract.py`
- `tests/test_project_workspace_service.py`
- `tests/test_operation_runtime_service.py`
- `tests/test_text_chunking_state_service.py`
- `tests/test_text_chunking_ui_controller.py`
- `tests/test_text_chunking_page.py`

These cover strict Cleanup gating, role propagation, semantic priority,
oversized-sentence fallback, deterministic artifacts/chapter behavior, AI
descriptor validation/resume/fallback contracts, scene-separator recognition
and omission, state edits/invalidation, controller dispatch, and page behavior.
Minimum validation after a change: run the focused modules above with
`uv run pytest`, plus `uv run ruff check` on changed files.

## 10. Limitations And Future Work

AI boundaries remain advisory. Invalid tails are retried after committed valid
prefixes; responses with no valid prefix use deterministic structural
fallback and may still produce a larger window chunk when no explicit
structure exists. Token budgeting is estimated by AI Runtime. Operator review
remains available for semantic corrections.
