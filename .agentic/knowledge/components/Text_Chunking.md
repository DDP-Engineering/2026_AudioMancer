<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Text Chunking

## 1. Purpose

Text Chunking turns canonical cleaned text into ordered, persisted chunks that
operators can inspect and edit before translation, character discovery, and
speech generation.

## 2. Responsibilities

- Derive deterministic chapter/paragraph chunks and one canonical Chunking document.
- Run AI-assisted semantic chunking with validated paragraph descriptors,
  bounded context windows, resumable state, fallback windows, and usage logs.
- Project persisted chunks and readiness into page state; make controlled
  insert, delete, and text edits invalidate downstream work appropriately.
- Present deterministic/AI actions, profile and strategy selection, previews,
  editing, and localized find behavior through the page/controller.

It consumes cleanup output but does not own cleanup extraction rules, generic
AI transport, or downstream translation/speech semantics.

## 3. Implementation Overview

`chunking_document_service` is the strict persistence boundary for the sole authoritative
`chunks_text.json` document. `deterministic_chunking_service`
detects chapter structure, while `ai_chunking_service` turns paragraphs into
budgeted windows, requires source-aligned descriptors from the provider,
checkpoints each completed unit into that document, and falls back to a complete
window chunk when no valid internal boundary is returned.
`text_chunking_state_service` derives page state and persists operator changes
while using workflow-impact rules. The UI controller routes
page signals via shared operation orchestration; `TextChunkingPage` renders
profiles, strategy, previews, edits, and search.

## 4. Dependencies

Internal dependencies include Text Cleanup artifacts, AI Runtime budget/prompt/
provider/token services, Project Lifecycle manifest persistence, Operation
Orchestration state/impact/runtime helpers, settings/UI state, and Qt widgets.
External dependencies are PySide6 and project-local JSON/text storage.

## 5. Inputs And Outputs

Inputs are active project/manifest, `clean_text.txt`, chosen deterministic or
AI strategy, enabled profile, optional instructions/context mode, and user
chunk edit requests. The sole durable Chunking output is `chunks_text.json`;
operation summaries, progress, budget details, provider/model settings, and AI
log paths are runtime-only projections. AI transaction logs remain separate
diagnostic files. A manual edit, insert, or delete atomically rewrites the same
canonical document and the manifest;
it also synchronizes affected translations, removes only affected character
evidence, Speech Blocks, and Audio Blocks, then resets Audio Assembly outputs.

## 6. Data Contracts

The document has an exact root-object schema containing lifecycle, mode,
manual-adjustment, source fingerprint, semantic strategy, operator instructions,
cumulative token usage, warnings, resume checkpoint, fallback count, and ordered
chunks. Chunk records have an exact minimal schema with stable identifiers,
sequence, text, and cleanup-boundary provenance. Legacy root arrays and obsolete
`chunking_report.json` or `chunking_state.json` sidecars are never migrated; an
incompatible document requires the operator to use Reset Chunking.

AI descriptor ranges must align to ordered paragraph records. Resume restores
the document's strategy, instructions, committed chunks, checkpoint, usage, and
fallback count, but invokes the currently selected profile with current runtime
budget settings and creates a fresh separate AI log. Edits operate by chunk ID
rather than UI row and require downstream-impact review.
Manual operations resequence `sequence_index` without changing surviving
`chunk_id` values; deletion rejects an empty resulting set, while insertion
creates an empty `chunk-####` record next to its selected anchor. They preserve
all unrelated root metadata and set `manual_adjusted` without adding sidecars.

## 7. Workflow Integration

The component begins after Text Cleanup. Its approved chunks feed AI
Translation, Character Discovery, Speech Blocks, and later audio stages. Any
manual edit or recomputation uses Operation Orchestration to reset only
affected downstream state.

## 8. Usage

Operators select deterministic chunking or an enabled AI profile/semantic
strategy on the Text Chunking page. Controllers dispatch `chunk_text` or the
deterministic service through the shared runner, then refresh page/manifest
state. To correct one chunk, select it and use edit, insert, or delete only
after reviewing the confirmation dialog; the result preserves unrelated
chunk identities and downstream artifacts where the source change permits it.
Direct callers must provide a valid project manifest and the same profile,
cancellation, and progress contracts. Page open is read-only: it derives notes
and resumability from the document and does not create default state artifacts.

## 9. Validation And Tests

Focused re-characterization ran all six mapped modules: 69 passed. They cover
deterministic artifacts/chapter behavior, AI descriptor validation/resume/
fallback contracts, state edits/invalidation, controller dispatch, and page
controls, previews, localization, search, and profile/strategy behavior.

## 10. Limitations And Future Work

AI boundaries remain advisory: invalid or empty model splits deliberately fall
back to larger deterministic windows. Token budgeting is estimated by AI
Runtime. Direct unit coverage for a few page visual layout details does not
replace operator review of semantic boundaries on a real document.
