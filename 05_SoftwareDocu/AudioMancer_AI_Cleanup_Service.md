<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer AI Cleanup Service

## 1. Purpose

AI Cleanup is the optional AI-assisted branch of Text Cleanup. It sends each
bounded cleanup window to an OpenAI-compatible model as one canonical source
string and accepts retained text only as exact forward source slices. The
original extraction and detailed review evidence remain available because exact
slice validation does not prove that model-selected deletions are semantically
correct.

## 2. Responsibilities

- canonicalize source newlines once from CRLF or CR to LF
- use extraction page boundaries and safe newline segments for window sizing
- concatenate each request window into one provider-visible source string
- reserve input and output capacity for source repeated in structured JSON
- validate ordered response blocks globally against the canonical window
- accept omitted whitespace-only gaps as recorded normalization evidence
- remove only high-confidence `header`, `footer`, and `noise` ranges
- preserve `separator`, `heading`, and `story` plus every medium/low-confidence block
- warn for entire-page, high-ratio, fragmented, inconsistent, or long removals
- checkpoint only fully validated windows and reject obsolete checkpoints
- persist cleaned text, report, state, metadata, model history, and transaction logs
- keep the original extraction for operator review and manual correction

It does not own extraction, deterministic cleanup, AI profile editing, chunking,
translation, or semantic proof that removed content was unwanted.

## 3. Implementation Overview

The single implementation and application entry point is
`04_Software/AudioMancer/src/audiomancer/services/ai_cleanup_service.py`.
Runtime prompts are `04_Software/AudioMancer/prompts/text_cleanup_system.txt`
and `04_Software/AudioMancer/prompts/text_cleanup_user.txt`. There is no
secondary cleanup implementation, legacy prompt fallback, or response adapter.

High-level flow:

1. Validate the project source and selected AI profile.
2. Decode the UTF-8 extraction and canonicalize newlines.
3. Build page-aware units, splitting oversized units only at existing newlines.
4. Select budget-safe windows and concatenate each window's unit text.
5. Render that string once between `SOURCE WINDOW` markers.
6. Request the current strict JSON shape and validate identity, sequential IDs,
   exact fields, enum values, non-empty blocks, forward slices, whitespace gaps,
   and authorized non-whitespace gaps.
7. Persist each fully validated window before continuing.
8. Concatenate preserved blocks and apply deterministic final formatting.
9. Persist final artifacts, clear the checkpoint, advance to
   `text_chunking_ready`, and require human review.

## 4. Dependencies

Internal dependencies include `audiomancer.config`, prompt templates, provider
JSON transport, token usage, cleanup metadata and text analysis, operation
runtime helpers, atomic persistence, project workspace synchronization, logging,
and the Text Cleanup UI controller.

External behavior depends on the Python runtime, `langdetect`, PySide6 through
the UI, and an operator-selected OpenAI-compatible endpoint.

## 5. Inputs And Outputs

Inputs:

- active project root and manifest containing `source_document`
- root-level UTF-8 `extracted_text.txt`
- selected enabled AI profile with context and output limits
- `text_cleanup_system.txt` and `text_cleanup_user.txt`
- optional operator instructions, progress callback, and cancellation callback

Outputs:

- `clean_text.txt`
- `clean_text_metadata.json`
- `cleanup_report.json`
- `cleanup_state.json`
- `log_ai_cleanup_<timestamp>.log`
- synchronized `project.json.operations.cleanup`
- project stage `text_chunking_ready` after success

The source `extracted_text.txt` remains unchanged.

## 6. Data Contracts

The provider object contains exactly the supplied `window_id` and a non-empty
ordered `text_blocks` array. Each response block contains exactly:

- sequential `text_block_id`
- non-empty `text_block`
- `artifact_type`: `header`, `footer`, `noise`, `separator`, `heading`, or `story`
- `confidence`: `high`, `medium`, or `low`

There is no response version, action, page, or segment field. `story` includes
narration, dialogue, attribution, epigraphs, verse, and other meaningful book
text. Printed page numbers, copyright notices, and unreadable extraction/OCR
garbage are represented as `noise`.

`artifact_type` and `confidence` determine handling. High-confidence `header`,
`footer`, and `noise` are removal decisions. `separator`, `heading`, and `story`
are always preserved; every medium/low-confidence block is also preserved.
Removal-decision text is advisory, while retained text must match an exact,
non-overlapping forward source slice.

An omitted whitespace-only range is accepted and stored in
`normalized_whitespace_ranges` with canonical window coordinates. An omitted
range containing non-whitespace requires an intervening high-confidence
removal decision and is stored in `removed_ranges`.

Interrupted or failed cleanup stores only fully validated windows. Checkpoints
contain an internal contract fingerprint plus input, instruction, and window
fingerprints. A checkpoint with any other contract or changed input restarts at
window one; no obsolete state is interpreted or migrated. A changed profile may
resume at the next untouched validated window. Completed state sets
`resume_checkpoint` to null.

## 7. Workflow Integration

Text Extraction supplies canonical input. The Text Cleanup controller provides
profile selection, progress, cancellation, previews, rerun confirmation, and
manual Save. Successful cleanup advances to `text_chunking_ready`, where
chunking consumes the reviewed `clean_text.txt`.

## 8. Usage

```python
from audiomancer.services import ai_cleanup_service

report = ai_cleanup_service.clean_text(
    project_root,
    manifest,
    ai_profile_payload,
    additional_cleanup_instructions="Preserve glossary names exactly.",
)
```

The operator compares the original and cleaned previews and corrects semantic
removal mistakes before downstream use.

## 9. Validation And Tests

Primary coverage:

- `04_Software/AudioMancer/tests/test_ai_cleanup_contract.py`
- `04_Software/AudioMancer/tests/test_ai_cleanup_service.py`
- `04_Software/AudioMancer/tests/test_ai_budget_service.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_state_service.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_ui_controller.py`
- `04_Software/AudioMancer/tests/test_atomic_io_contracts.py`
- provider and prompt-template tests

Run tests and style checks through the pinned `uv` environment. Durable
behavior is tracked by `REQ-FUNC-058`, `REQ-FUNC-059`, `REQ-FUNC-060`, and
`REQ-NFR-019`.

## 10. Limitations And Future Work

- Exact forward-slice validation cannot prove semantic deletion correctness.
- Broad and entire-page removals remain warnings under the approved policy.
- Requests are sequential and cancellation is cooperative around provider calls.
- Provider JSON repair remains best effort before strict validation.
- The response-expansion factor defaults to `2.0` and should change only with
  measured evaluation evidence.
