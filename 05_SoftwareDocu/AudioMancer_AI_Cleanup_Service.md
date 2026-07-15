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
string and accepts every returned block only as an exact forward source
slice. The original extraction and detailed review evidence remain available
because exact-slice validation does not prove that model classifications are
semantically correct.

## 2. Responsibilities

- canonicalize source newlines once from CRLF or CR to LF
- use extraction page boundaries and safe newline segments for window sizing
- concatenate each request window into one provider-visible source string
- reserve input and output capacity for source repeated in structured JSON
- validate ordered response blocks globally against the canonical window
- restore every omitted whitespace-only gap exactly at its validated source position
- retain `story` exactly, replace `separator` and `heading` with two LF characters, and remove `header`, `footer`, and `noise` without replacement whitespace
- treat confidence as review metadata that never changes deterministic output handling
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
   exact fields, enum values, non-empty blocks, forward slices, and
   whitespace-only omitted gaps.
7. Reconstruct each window from validated source positions, restoring omitted
   whitespace exactly, replacing `separator` and `heading` slices with `\n\n`,
   and removing `header`, `footer`, and `noise` slices without replacement text.
8. Persist each fully validated reconstructed window before continuing.
9. Concatenate reconstructed windows without trimming or collapsing whitespace.
10. Persist final artifacts, clear the checkpoint, advance to
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

Every block, including a non-story artifact, must match an exact,
non-overlapping forward source slice. `story` is always retained exactly. Each
non-story block is replaced with exactly two LF characters (`\n\n`) when its
category belongs to the complete operator-selected spacing set and contributes
no output otherwise. Retained whitespace-only gaps between source blocks also
contribute no output, so deselecting every category removes all controllable
inter-block blank lines without altering Story text. The default set is
`heading` plus `separator`. `confidence` remains review metadata and does not
affect rendering.

A model may omit a source gap only when the complete gap is whitespace. The
validator stores such gaps in `restored_whitespace_ranges` with canonical
window coordinates and inserts their exact source text into the reconstructed
window. Any omitted non-whitespace rejects the response. Final assembly
concatenates each window's `reconstructed_text` without trimming, blank-line
collapse, or other formatting.

`preserved_blocks`, `removed_ranges`, and `restored_whitespace_ranges` retain
complete exact-source window coverage. `removed_ranges` records original text,
current replacement (empty or two LF), artifact type, and confidence; retained
whitespace gaps provide validation and review provenance but render as empty
spacing.
`reconstruction_contract_fingerprint` identifies reports compatible with
spacing reapplication, while `selected_spacing_categories` persists the
complete applied set. Aggregate report fields include
`artifact_replacement_count`, `spacing_replacement_count`,
`restored_whitespace_gap_count`, and `restored_whitespace_character_count`.

`apply_spacing_selection()` validates the selected set, reloads only a current
compatible completed AI report, rebuilds every window from retained source
ranges, and atomically rewrites `clean_text.txt`, cleanup metadata, and the
report. It performs no provider request and repeated application of the same
set is byte-identical. Reports created under an older reconstruction contract,
deterministic cleanup reports, and manual-edit state cannot be reapplied.

Interrupted or failed cleanup stores only fully validated windows. Checkpoints
contain an internal contract fingerprint plus input, instruction, and window
fingerprints. A checkpoint with any other contract or changed input restarts at
window one; no obsolete state is interpreted or migrated. A changed profile may
resume at the next untouched validated window. Completed state sets
`resume_checkpoint` to null.

## 7. Workflow Integration

Text Extraction supplies canonical input. The Text Cleanup controller provides
profile selection, progress, cancellation, previews, rerun confirmation, and
manual Save. Cancelling the optional AI-instructions dialog clears temporary
page busy state without starting or resetting cleanup, so the operator can
retry immediately. The Cleaned Text Preview shows the five non-story spacing
checkboxes and actions in one compact two-row grid: label, Heading, Separator,
and Edit on row one; Apply Spacing, Noise, Header, Footer, and Save on row two.
Heading and Separator start selected; Story is never selectable.
Reapplication resets non-preserved downstream outputs as a cleaned-text
revision and returns the project to `text_cleanup_ready`. Manual Save changes
cleanup mode to `manual_edit`, which disables later spacing reapplication.
Successful initial cleanup advances to `text_chunking_ready`, where chunking
consumes the reviewed `clean_text.txt`.

## 8. Usage

```python
from audiomancer.services import ai_cleanup_service

report = ai_cleanup_service.clean_text(
    project_root,
    manifest,
    ai_profile_payload,
    additional_cleanup_instructions="Preserve glossary names exactly.",
)

report = ai_cleanup_service.apply_spacing_selection(
    project_root,
    {"heading", "separator", "noise"},
)
```

The operator compares the original and cleaned previews and corrects semantic
removal mistakes before downstream use.

## 9. Validation And Tests

Implementation review: selectable retained-decision spacing behavior and UI
integration were reviewed against the final source on 2026-07-15.

Primary coverage:

- `04_Software/AudioMancer/tests/test_ai_cleanup_contract.py`
- `04_Software/AudioMancer/tests/test_ai_cleanup_service.py`
- `04_Software/AudioMancer/tests/test_ai_budget_service.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_state_service.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_ui_controller.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_page.py`
- `04_Software/AudioMancer/tests/test_atomic_io_contracts.py`
- provider and prompt-template tests

Run tests and style checks through the pinned `uv` environment. Durable
behavior is tracked by `REQ-FUNC-058`, `REQ-FUNC-059`, `REQ-FUNC-060`,
`REQ-FUNC-061`, `REQ-UX-036`, `REQ-UX-037`, and `REQ-NFR-019`.

## 10. Limitations And Future Work

- Exact forward-slice validation cannot prove semantic classification correctness.
- Broad and entire-page artifact removals remain warnings under the approved policy.
- Requests are sequential and cancellation is cooperative around provider calls.
- Provider JSON repair remains best effort before strict validation.
- The response-expansion factor defaults to `2.0` and should change only with
  measured evaluation evidence.
- Spacing reapplication is intentionally unavailable for reports created before
  retained complete source coordinates were introduced.
