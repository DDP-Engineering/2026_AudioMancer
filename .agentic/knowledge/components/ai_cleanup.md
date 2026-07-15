<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AI Cleanup Component Knowledge

## 1. Purpose

AI Cleanup consumes canonical extracted text and uses an explicitly selected
OpenAI-compatible provider to classify exact source slices without allowing
source text to be rewritten.

## 2. Responsibilities

- Own canonical cleanup-window prompts, strict response validation,
  operator-selected deterministic artifact spacing, exact whitespace-gap
  reconstruction, output-aware budgeting, validated-window resume, reports,
  warnings, and operator-review evidence.
- Do not own extraction, deterministic cleanup, downstream processing, profile
  editing, or proof that model-selected deletions are correct.

## 3. Implementation Overview

`ai_cleanup_service.py` is the single implementation and public application
entry point. Runtime prompts are `text_cleanup_system.txt` and
`text_cleanup_user.txt`; no compatibility module, legacy prompt fallback, or
response adapter is present.

Internal page-aware units are used only for budgeting and review warnings. Each
provider request contains one concatenated canonical source window. Returned
blocks have no version, action, page, or segment identity fields and are
validated globally as exact forward source slices. Omitted gaps must be
whitespace-only and are restored exactly from source positions.

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
`REQ-FUNC-059`, `REQ-FUNC-060`, `REQ-FUNC-061`, `REQ-UX-036`, and
`REQ-NFR-019`.

The response contains only `window_id` and sequential `text_blocks`. Each block
contains only ID, text, one of six artifact types, and confidence. Every block
must be an exact ordered source slice. `story` is retained exactly. A non-story
block emits two LF characters when its category is selected and emits nothing
otherwise; the default selection is `heading` plus `separator`. Confidence is
review metadata only. Omitted whitespace-only gaps are restored exactly,
omitted non-whitespace is rejected, and final window assembly does not trim or
collapse the reconstructed text.

Completed current-contract reports retain complete story, artifact, and
whitespace source coordinates plus the applied category selection. Apply
Spacing rebuilds from those ranges without a provider call, persists the new
selection and output, and resets non-preserved downstream work. Manual edits or
incompatible reports disable reapplication.

Checkpoints use an internal contract fingerprint. Obsolete or changed-input
state restarts at window one without legacy interpretation; changed model
settings may resume after the last fully validated matching window.

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

Exact slice validation proves source fidelity but not classification
correctness. Broad artifact removals remain warnings and require operator
comparison.
Requests remain sequential and OpenAI-compatible.
Reports from older reconstruction contracts cannot be spacing-reapplied.
