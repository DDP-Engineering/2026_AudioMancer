<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AI Cleanup Component Knowledge

## 1. Purpose

AI Cleanup consumes canonical extracted text and uses an explicitly selected
OpenAI-compatible provider to classify exact artifacts and source-grounded Story
spans. The prompt forbids rewriting, while validation can retain one uniquely
bounded modified Story with explicit review evidence.

## 2. Responsibilities

- Own canonical strict-copy cleanup-window prompts, source-grounded response
  validation, operator-selected deterministic artifact spacing, exact
  whitespace-gap reconstruction, uniquely bounded omitted-source preservation,
  output-aware budgeting, source-offset validated-window resume, reports, warnings, and
  operator-review evidence.
- Do not own extraction, deterministic cleanup, downstream processing, profile
  editing, or proof that model-selected deletions are correct.

## 3. Implementation Overview

`ai_cleanup_service.py` is the single implementation and public application
entry point. Runtime prompts are `text_cleanup_system.txt` and
`text_cleanup_user.txt`; no compatibility module, legacy prompt fallback, or
response adapter is present.

Internal page-aware units are used only for budgeting and review warnings. Each
provider request contains one concatenated canonical source window. Returned
blocks have no version, action, page, or segment identity fields. Non-story
blocks are exact forward slices. A non-exact Story may be associated with one
unique span bounded by exact neighbors or window edges when normalized
alphanumeric edge anchors match. An internal non-whitespace gap between two
exact blocks is preserved only when the current delimiter has one forward
occurrence; ambiguous and edge gaps remain errors.

## 4. Dependencies

Internal dependencies include project workspace and operation-state helpers,
atomic persistence, prompt templates, provider JSON transport, token usage,
logging, language detection, cleanup metadata, and Text Cleanup UI state.
External dependencies are the Python runtime, `langdetect`, PySide6, and an
operator-selected OpenAI-compatible endpoint.

## 5. Inputs And Outputs

Inputs are the active project, canonical `extracted_text.txt`, selected profile,
neutral cleanup prompts, optional operator instructions, and progress or
cancellation callbacks. Outputs are `clean_text.txt`,
`clean_text_metadata.json`, `cleanup_report.json`, `cleanup_state.json`, an AI
transaction log, and synchronized cleanup fields in `project.json`.

## 6. Data Contracts

Relevant requirements are `REQ-FUNC-002`, `REQ-NFR-002`, `REQ-NFR-004`,
`REQ-NFR-018`, `REQ-DATA-001`, `REQ-UX-027`, `REQ-FUNC-058`,
`REQ-FUNC-059`, `REQ-FUNC-060`, `REQ-FUNC-061`, `REQ-FUNC-062`, `REQ-FUNC-063`, `REQ-FUNC-064`,
`REQ-UX-036`, and `REQ-NFR-019`.

The response contains only `window_id` and sequential `text_blocks`. Each block
contains only ID, text, one of six artifact types, and confidence. Artifacts
must be exact ordered source slices. Story uses `match_mode=exact` when copied;
otherwise one non-adjacent modified block may use `anchored_modified` when its
unique candidate and provider text each have at least 32 normalized
alphanumeric characters and matching 16-to-64-character edges. Case,
punctuation, and whitespace are ignored only for edge matching; the accepted
provider Story is emitted unchanged and its original source text and coordinates
are retained. Interior similarity is intentionally unbounded. A non-story block
emits two LF characters when selected and nothing otherwise; the default is
`heading` plus `separator`. A uniquely bounded internal omitted gap is stored in
`preserved_source_gaps`, emitted exactly from source, warning-marked, and counted
in `preserved_source_gap_count`; leading, trailing, repeated-delimiter, or
modified-boundary gaps remain rejected.

Completed current-contract reports retain complete Story, artifact, and
whitespace and preserved-gap source coordinates, `modified_story_block_count`,
`preserved_source_gap_count`, structured warnings, and the applied category
selection. Apply Spacing rebuilds from those ranges without a provider call and
preserves accepted provider Story and exact source-gap text. Manual edits or
incompatible reports disable reapplication.

Checkpoints use an internal contract fingerprint. Compatible saved windows are
verified sequentially by `source_window_length` and
`source_window_fingerprint` against the canonical provider-visible source
stream. Restored decisions gain `source_stream_start` and `source_stream_end`;
current model settings repartition only the unprocessed suffix and new IDs
continue after the restored count. Obsolete, changed-input, or
changed-instruction state restarts at window one, while invalid saved-window
evidence stops restoration at the first mismatch. Page separators are excluded
from this offset stream because they are not provider-visible.

## 7. Workflow Integration

Text Extraction supplies canonical input. Successful cleanup advances to
`text_chunking_ready`. The Text Cleanup UI retains original and cleaned
previews, manual editing, rerun confirmation, and five non-story category
checkboxes in a compact two-row selector above Apply Spacing, Edit, and Save.
Cancelling optional AI instructions restores the page action state without
starting or resetting cleanup. Story remains absent from the selector and
spacing application retains its downstream reset behavior.

## 8. Validation And Tests

Focused coverage includes `test_ai_cleanup_contract.py`,
`test_ai_cleanup_service.py`, `test_ai_budget_service.py`,
`test_text_cleanup_state_service.py`, `test_text_cleanup_ui_controller.py`,
`test_text_cleanup_page.py`, and `test_atomic_io_contracts.py`. Use the pinned
application `uv` environment plus
traceability, coverage, style, component, and documentation audits before
delivery.

## 9. Limitations And Future Work

Exact artifact validation and normalized Story edges do not prove semantic
classification or modification correctness. Modified Story interiors are not
similarity-thresholded, while adjacent, short-anchor, and ambiguous candidates
remain errors. Broad artifact removals and accepted Story modifications require
operator comparison. Preserved omitted source gaps also require operator review;
only unique internal exact boundaries are accepted.
Requests remain sequential and OpenAI-compatible.
Reports from older reconstruction contracts cannot be spacing-reapplied.
