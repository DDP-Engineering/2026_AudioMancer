<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Text Cleanup

## 1. Purpose

Text Cleanup converts a supported book source into canonical extracted text and
then into reviewable text suitable for narration. Deterministic structural
analysis owns the result; an optional online or offline LLM may adjudicate only
ambiguous typed boundaries and may never generate replacement book text.

## 2. Responsibilities

- Extract `.txt`, `.md`, `.pdf`, `.rtf`, `.docx`, `.odt`, and `.epub`.
- Build `extracted_text.txt` and `source_ledger.json` simultaneously.
- Preserve native headings, lists, tables, preformatted blocks, EPUB spine
  order, and PDF geometry where the format exposes them.
- Resolve a role for every source unit before classifying every boundary.
- Remove page artifacts only with conservative repetition or sequence evidence.
- Represent every join, paragraph break, semantic line break, hyphenation
  decision, and document end as a typed decision.
- Ask an optional model bounded classification questions and independently
  verify only proposed overrides of deterministic priors.
- Render solely from source-ledger slices and typed separators while rejecting
  introduced alphanumeric fusion, projection loss, or incomplete decisions.
- Persist exactly one Cleanup metadata/checkpoint file and one text output.
- Stop safely after a completed model request and resume compatible work.
- Expose the existing Cleanup page, profile selector, Reset, previews, and
  Edit/Save/Cancel controls without adding a new layout or control.

OCR, model hosting, chunking, translation, voice generation, and audiobook
assembly are outside this component.

## 3. Implementation Overview

The production boundary is:

- `text_extraction_adapters.py`: format-specific structural adapters.
- `source_ledger_service.py`: canonical text/offset builder and strict loader.
- `text_extraction_service.py`: extraction orchestration and metadata.
- `cleanup_analysis_service.py`: deterministic roles, typed priors, and
  residual questions.
- `cleanup_text_analysis_service.py`: shared Unicode, sentence, language,
  heading, and conservative scene-separator recognition.
- `cleanup_ai_adjudication_service.py`: bounded primary/verifier
  classification.
- `cleanup_renderer_service.py`: decision validation, pure rendering, paragraph
  offsets, and runtime quality metrics.
- `cleanup_metadata_service.py`: strict completed-output access for consumers.
- `text_cleanup_service.py`: persisted orchestration, stop/resume,
  finalization, and manual edits.
- `text_cleanup_state_service.py`: read-only page state projection.
- `text_cleanup_ui_controller.py` and `text_cleanup_page.py`: existing UI
  integration.

Cleanup runs in four phases: deterministic analysis, optional AI adjudication,
deterministic validation/rendering, and atomic publication. It is a fixed
service pipeline, not an agent loop. Progress is monotonic: analysis occupies
0-8%, adjudication 8-88%, validation/rendering 94%, persistence 98%, and only a
validated published result reports 100%. A compatible resume reconstructs its
first displayed percentage from persisted completed and estimated AI request
counts, so cancellation followed by resume never resets the progress display.
The adjudication phase explicitly reaches 88% even when conditional verifier
requests are skipped.

Analysis assigns `body`, `heading`, `scene_separator`, `list_item`, `verse`,
`preformatted`, `footnote`, or `page_artifact` before boundary resolution.
Native structure wins. Non-native verse requires an isolated run of at least
three short, aligned lines, with dialogue and other structural roles excluded.
When native structure is unavailable, repeated identical marker glyphs and
known singleton book ornaments may be classified as `scene_separator`;
ambiguous punctuation and lexical text remain `body`.
PDF geometry distinguishes indentation, dedentation, enlarged gaps, full-width
sentence continuation, and column changes; uncertain terminal-line cases are
eligible for adjudication instead of becoming strong paragraph assumptions.

## 4. Dependencies

Internal dependencies include project lifecycle, operation orchestration,
source-ledger access, atomic persistence, the provider adapter, token-usage
normalization, prompt templates, localization, and workflow state.

External packages are PySide6, PyMuPDF, python-docx, EbookLib, odfpy,
striprtf, markdown-it-py, and langdetect.

## 5. Inputs And Outputs

Inputs are the active project and manifest, its registered source, optional
progress/cancellation callbacks, and an optional enabled AI profile.

Extraction writes:

- `extracted_text.txt`
- `source_ledger.json`
- `extraction_metadata.json`

Cleanup writes:

- `cleanup.json`
- `clean_text.txt`
- optional `ai_cleanup_*.log` transaction logs

The log is operational diagnostics, not Cleanup state. Cleanup has no report,
state, clean-text metadata, schema-version, compatibility, or migration
sidecar. The current unversioned contract is the only accepted contract.

`config` therefore defines no constant for `cleanup_report.json`,
`cleanup_state.json`, or `clean_text_metadata.json`. Reset still deletes those
three names as bare string literals so pre-hard-break project folders are cleaned, and
`test_retired_cleanup_artifact_config_constants_are_gone` keeps the constants
from returning.

## 6. Data Contracts

`source_ledger.json` contains exact half-open codepoint intervals for every
unit and boundary. The sorted intervals partition `extracted_text.txt` without
gaps or overlaps. The ledger includes source/text hashes, adapter/encoding
metadata, structure quality, units, boundaries, page geometry, and warnings.

Unit operations are restricted to:

- `drop_page_artifact`
- `set_role`

Boundary choices are restricted to:

- `join_with_space`
- `set_paragraph_break`
- `set_semantic_line_break`
- `dehyphenate`
- `join_preserving_hyphen`
- `document_end`

`join_without_space`, `preserve`, and replacement-text actions do not exist.
Every unit has exactly one role and every source boundary has exactly one
decision. Unknown or duplicate targets, unsupported roles/choices, oversized
artifact removals, empty output, removal of every unit on a page, and new
alphanumeric adjacency are rejected. When one or more page-artifact units are
dropped, the renderer collapses their boundary chain to one typed separator
between the nearest surviving narrative units.

AI is eligible only when a selected profile advertises structured output and
at least a 16K context window. Batches contain 4 questions at 16-31K, 8 at
32-127K, and 16 at 128K or above. Oversized requests split recursively.
Invalid/provider failures retry once and then only that batch falls back to its
priors. The verifier sees only disagreements between a primary answer and its
prior; an override is accepted only when both model passes agree. Without a
compatible model, all ambiguous cases use deterministic priors.

`cleanup.json` has an exact unversioned root containing lifecycle timestamps,
source/ledger/policy/prompt hashes, a non-secret profile fingerprint, document
profile, unit operations, boundary decisions, paragraph offsets, resumable
progress, warnings, normalized token use, runtime quality metrics, output hash,
and manual-edit/structure flags. Status is `running`, `paused`, `finalizing`,
`completed`, or `failed`; only `completed` with phase `done`, zero blocking
quality counters, and a matching `clean_text.txt` hash unlocks Chunking.
Loaded documents also require the exact Progress field set, non-boolean
non-negative integer counters, string-only batch IDs, and a bounded next-batch
index. Completed blocking quality counters must be present as non-boolean
integer zeroes. Every violation raises `CleanupDocumentError`; persisted shape
or value corruption does not leak `TypeError`, `KeyError`, or `AttributeError`
to consumers.
Online disclosure counts every submitted question fragment, including failed
retry attempts, separately from completed resumable responses.

A compatible resume reuses deterministic analysis and completed model passes.
A model, context, request-policy, or prompt change preserves deterministic
analysis but clears all AI answers and regenerates the AI batch plan.
`finalizing/rendering` recovery rerenders from persisted decisions without
calling a model. The first resume update reports the persisted request fraction
before any new model request is submitted.

## 7. Workflow Integration

Extraction is mandatory before Cleanup.
`config.CLEANUP_SUPPORTED_SOURCE_LANGUAGES` defines the supported
source-content set: English, Romanian, German, French, Russian, Portuguese,
Spanish, and Italian. This set is independent of the operator interface locale.
Predominantly CJK or Hangul input is rejected before Cleanup artifacts are
published.

Cleanup completion promotes the project to `text_chunking_ready` immediately.
Review and manual editing are optional rather than approval gates. Saving an
operator edit updates the output hash, marks `user_modified`, and invalidates
Chunking and later artifacts. A whitespace-only edit realigns typed structure
by unambiguous normalized paragraph content rather than list index. The current
classifier remains authoritative for explicit scene separators; a stale prior
`scene_separator` role is never carried onto classifier-negative prose.
Unmatched or multiply matched content keeps the classifier-only role, while a
unique content match may preserve headings and other noncontradicted roles. A
lexical edit publishes minimal `user_edited` paragraph structure without
claiming source provenance. Rebuilt user-edited paragraphs conservatively
reclassify explicit marker-only scene separators while ambiguous punctuation
and lexical content remain `body`.

The existing Cleanup page layout and controls remain unchanged. The status pane
projects running, paused, invalid, and completed state from `cleanup.json`;
progress and cancellation continue through the existing operation dialog.

## 8. Usage

```python
from audiomancer.services import text_cleanup_service, text_extraction_service

text_extraction_service.extract_text(project_root, manifest)
result = text_cleanup_service.clean_text(
    project_root,
    manifest,
    ai_profile_payload=optional_profile,
)
```

## 9. Validation And Tests

Primary coverage:

- `tests/test_text_extraction_service.py`
- `tests/test_cleanup_quality_contract.py`
- `tests/test_cleanup_adjudication_contract.py`
- `tests/test_cleanup_acceptance_corpus.py`
- `tests/test_cleanup_service.py`
- `tests/test_cleanup_metadata_service.py`
- `tests/test_text_cleanup_state_service.py`
- `tests/test_project_workspace_service.py`
- `tests/test_text_cleanup_ui_controller.py`
- `tests/test_text_cleanup_page.py`

Run `uv run ruff check src tests` and `uv run pytest`. Format-specific changes
must include exact ledger/hash/role assertions. AI changes must verify strict
output, selective verification, retry isolation, context tiers, recursive
splitting, cancellation checkpoints, and resume invalidation.

## 10. Limitations And Future Work

- Image-only PDFs fail because OCR is intentionally out of scope.
- RTF exposes text but not dependable native style/list structure.
- Ambiguous multi-column PDF reading order is preserved with warnings.
- A weak or unavailable model may leave more low-confidence deterministic
  choices; the source-ledger projection and operator edit controls remain the
  safety boundary.
