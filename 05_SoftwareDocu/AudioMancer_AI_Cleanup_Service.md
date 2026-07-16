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
string. Non-story blocks remain exact forward source slices; Story blocks are
normally exact and may use a uniquely bounded normalized-edge fallback when a
model changes their interior text. The original extraction and detailed review
evidence remain available because source association does not prove that model
classifications or modifications are semantically correct.

## 2. Responsibilities

- canonicalize source newlines once from CRLF or CR to LF
- use extraction page boundaries and safe newline segments for window sizing
- concatenate each request window into one provider-visible source string
- reserve input and output capacity for source repeated in structured JSON
- validate ordered response blocks globally against the canonical window
- accept one non-exact Story only when exact neighbors or window edges provide one unique source span and sufficient normalized edge anchors match
- retain whitespace-gap coordinates and preserve an omitted internal non-whitespace gap exactly when unique exact block boundaries prove its source span
- emit each validated `story` provider text exactly, replace `separator` and `heading` with two LF characters, and remove `header`, `footer`, and `noise` without replacement whitespace
- treat confidence as review metadata that never changes deterministic output handling
- warn for entire-page, high-ratio, fragmented, inconsistent, or long removals
- checkpoint only fully validated windows, restore their canonical source-stream prefix across budget repartitioning, and reject incompatible checkpoints
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
4. Restore the longest valid checkpoint prefix against canonical source-stream
   lengths and fingerprints, then select budget-safe windows only for the
   unprocessed suffix.
5. Render that string once between `SOURCE WINDOW` markers.
6. Request the current strict JSON shape and validate identity, sequential IDs,
   exact fields, enum values, non-empty blocks, exact non-story slices, exact or
   uniquely anchored Story spans, whitespace-only gaps, and uniquely bounded
   internal non-whitespace gaps between exact blocks.
7. Reconstruct each window from validated source positions, emitting each
   accepted Story `text_block` exactly, replacing `separator` and `heading`
   slices with `\n\n`, and removing `header`, `footer`, and `noise` slices.
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

Every non-story artifact must match an exact, non-overlapping forward source
slice. An exact Story records `match_mode=exact`. A non-exact Story is accepted
only when it is not adjacent to another non-exact Story, exact neighboring
blocks or window edges produce exactly one candidate source span, and both the
source and provider text contain at least 32 alphanumeric characters. Matching
case-folds Unicode text, removes punctuation and whitespace, and compares the
first and last `min(64, floor(min(normalized lengths) / 2))` characters. The
interior has no similarity threshold. Short, changed-edge, adjacent, or
ambiguous candidates remain validation errors.

An accepted modified Story emits the provider `text_block` exactly and records
`match_mode=anchored_modified`, the original `source_text`, exact source-window
coordinates, a structured `modified_story_text_accepted` warning, and aggregate
`modified_story_block_count`. Logging records only window, block, and source
span metadata. Each exact non-story block is replaced with two LF characters
(`\n\n`) when its category belongs to the operator-selected spacing set and
contributes no output otherwise. The default set is `heading` plus `separator`;
`confidence` remains review metadata and does not affect rendering.

A whitespace-only source gap is stored in `restored_whitespace_ranges` with
canonical coordinates and emits no spacing. A non-whitespace gap is preserved
exactly only when it is internal, the immediately previous and current blocks
are exact matches, and the current block text has exactly one forward source
occurrence. Such a gap is stored in `preserved_source_gaps` with reason
`unclassified_source_gap_preserved`, emits its original source text, increments
`preserved_source_gap_count`, and adds a structured
`unclassified_source_gap_preserved` warning. Leading, trailing,
repeated-delimiter, modified-boundary, and otherwise ambiguous gaps remain
validation errors. Logging records only window coordinates, never full gap text.

`preserved_blocks`, `preserved_source_gaps`, `removed_ranges`, and
`restored_whitespace_ranges` retain complete source-window coverage.
`preserved_blocks` stores provider Story text, match mode, and source
coordinates, plus original source text for modified Story. `removed_ranges`
records exact original artifact text, current replacement, artifact type, and
confidence; whitespace gaps render as empty spacing, while preserved source
gaps remain byte-for-byte stable during spacing reapplication.
`reconstruction_contract_fingerprint` identifies reports compatible with
spacing reapplication, while `selected_spacing_categories` persists the
complete applied set. Aggregate report fields include
`artifact_replacement_count`, `spacing_replacement_count`,
`restored_whitespace_gap_count`, `restored_whitespace_character_count`, and
`preserved_source_gap_count`.

`apply_spacing_selection()` validates the selected set, reloads only a current
compatible completed AI report, rebuilds every window from retained source
ranges, and atomically rewrites `clean_text.txt`, cleanup metadata, and the
report. It performs no provider request and repeated application of the same
set is byte-identical. Reports created under an older reconstruction contract,
deterministic cleanup reports, and manual-edit state cannot be reapplied.

Interrupted or failed cleanup stores only fully validated windows. Checkpoints
contain an internal contract fingerprint plus input, instruction, window-length,
and window-fingerprint evidence. Resume verifies each saved window against the
corresponding slice of the LF-normalized provider-visible source stream and
restores the longest valid leading sequence. `source_stream_start` and
`source_stream_end` record that sequence without storing source content again.
The stream concatenates page text in source order and excludes extraction page
separators because those separators are never sent to the provider.

After restoration, current profile and budget settings repartition only the
unprocessed suffix. Restored window IDs, output, warnings, and token usage stay
unchanged; new IDs continue after the restored count, so no validated prefix is
submitted again. A different contract, input, or instruction fingerprint
restarts at window one. A malformed length, range, or window fingerprint stops
restoration at the first invalid saved item. Completed state sets
`resume_checkpoint` to null. This resume metadata extension does not change the
completed-report reconstruction fingerprint. Resume logging records only the
restored window count and source-stream offset, never the retained source text.

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
`REQ-FUNC-061`, `REQ-FUNC-062`, `REQ-FUNC-063`, `REQ-FUNC-064`, `REQ-UX-036`, `REQ-UX-037`, and
`REQ-NFR-019`.

## 10. Limitations And Future Work

- Exact forward-slice validation cannot prove semantic classification correctness.
- Normalized edge matching intentionally does not constrain a uniquely bounded Story interior; every accepted modification is warning-marked for human comparison.
- Adjacent modified Story blocks and candidates with fewer than 32 normalized alphanumeric characters are intentionally rejected.
- Preserved non-whitespace gaps require unique internal exact boundaries; edge and repeated-delimiter gaps remain errors.
- Broad and entire-page artifact removals remain warnings under the approved policy.
- Requests are sequential and cancellation is cooperative around provider calls.
- Provider JSON repair remains best effort before strict validation.
- The response-expansion factor defaults to `2.0` and should change only with
  measured evaluation evidence.
- Spacing reapplication is intentionally unavailable for reports created before
  retained complete source coordinates were introduced.
