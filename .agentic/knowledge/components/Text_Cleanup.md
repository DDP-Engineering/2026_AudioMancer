<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Text Cleanup

## 1. Purpose

Text Cleanup converts a supported book source into canonical extracted text and
then into reviewable clean text. The component uses one hybrid Cleanup action:
conservative structural rules do the certain work, an optional local AI model
adjudicates only residual typed questions, and uncertainty preserves source.

## 2. Responsibilities

- Extract `.txt`, `.md`, `.pdf`, `.rtf`, `.docx`, `.odt`, and `.epub`.
- Build `extracted_text.txt` and `source_ledger.json` simultaneously.
- Preserve native headings, lists, tables, preformatted blocks, EPUB spine
  order, and PDF geometry where the format exposes them.
- Identify removable page artifacts and line-boundary repairs conservatively.
- Ask an optional AI model small classification questions without allowing the
  model to reproduce or replace story text.
- Verify AI changes independently, validate all operations deterministically,
  and render solely from source-ledger slices.
- Persist one `cleanup.json`, clean text, and derived clean-text spans.
- Expose one Cleanup button, optional AI profile, Reset, source/result
  previews, and optional Edit/Save/Cancel controls.

OCR, model hosting, chunking, translation, voice generation, and audiobook
assembly are outside this component.

## 3. Implementation Overview

The production boundary is:

- `text_extraction_adapters.py`: format-specific structural adapters.
- `source_ledger_service.py`: canonical text/offset builder and strict loader.
- `text_extraction_service.py`: extraction orchestration and metadata.
- `cleanup_analysis_service.py`: deterministic evidence and residual questions.
- `cleanup_ai_adjudication_service.py`: bounded primary/verifier classification.
- `cleanup_renderer_service.py`: operation validation and pure rendering.
- `text_cleanup_service.py`: the single persisted Cleanup V2 orchestration.
- `text_cleanup_state_service.py`: read-only page state and operator edits.
- `text_cleanup_ui_controller.py` and `text_cleanup_page.py`: UI integration.

Cleanup runs in four phases: deterministic analysis, optional AI adjudication,
deterministic validation, and pure rendering. It is not an agent loop and does
not use context compaction, tool calling, planning, or open-ended prompts.
The orchestration maps those phases to monotonic UI progress: analysis starts
at 0% and completes at 5%, primary/verifier AI requests occupy 5–90%,
validation/rendering reports 92%, persistence reports 98%, and only successful
completion reports 100%. AI progress messages identify the batch and whether
the active request is the primary or verifier pass.

## 4. Dependencies

Internal dependencies include project lifecycle, operation orchestration,
atomic persistence, the OpenAI-compatible provider adapter, token-usage
normalization, localization, and workflow state.

External packages are PySide6, PyMuPDF, python-docx, EbookLib, odfpy,
striprtf, markdown-it-py, and langdetect.

## 5. Inputs And Outputs

Inputs are the active project/manifest, its registered source, optional
progress/cancellation callbacks, and an optional enabled AI profile.

Extraction writes:

- `extracted_text.txt`
- `source_ledger.json`
- `extraction_metadata.json`

Cleanup writes:

- `cleaned_text.txt`
- `clean_text_metadata.json`
- `cleanup.json`
- optional `ai_cleanup_*.log` transaction logs

Old extraction and Cleanup sidecars are incompatible by design. There is no
migration or fallback reader; the operator must rerun Extraction/Cleanup.

## 6. Data Contracts

`source_ledger.json` contains exact half-open codepoint intervals for every
unit and boundary. The sorted intervals partition `extracted_text.txt` without
gaps or overlaps. The ledger includes source/text hashes, adapter/encoding
metadata, structure quality, units, boundaries, page geometry, and warnings.

Cleanup operations are restricted to:

- `drop_page_artifact`
- `join_with_space`
- `join_without_space`
- `set_paragraph_break`
- `preserve_line_break`
- `dehyphenate`
- `set_role`

There is no `replace_text` operation. Unknown targets, duplicate target
actions, oversized artifact removals, empty output, and removal of every text
unit on a page are rejected.

Residual question types are `running_artifact`, `block_role`,
`line_boundary`, and `hyphenation`. AI responses contain only `batch_id` and
`question_id`/`choice` pairs. They contain no story output, confidence, or
rationale.

AI is eligible only when a selected profile advertises structured output and
at least a 16K context window. Homogeneous batches contain four questions at
16K and eight at 32K or above. Each question appears once in a primary call
and once in an independent verifier call. Only identical non-preserve answers
become operations. Provider JSON-schema fallback and model-based JSON repair
are disabled; one transient retry and 512 output tokens are allowed. Prompt,
schema, evidence, and output reserve must stay within 70% of context using the
conservative UTF-8-bytes/2 estimator.

The AI adjudication progress callback receives completed request count, total
request count, and an operator message. A batch contributes two request work
units. The outer Cleanup callback preserves its existing five-argument UI
contract and derives the displayed percentage from those work-unit counts.

`cleanup.json` records hashes, profile fingerprint, prompt schema, document
profile, operations, questions, answers, warnings, token use, output hash,
uncertainty count, and whether the operator edited the result. Both `passed`
and `passed_with_warnings` are terminal successes and unlock Text Chunking.

## 7. Workflow Integration

Extraction is mandatory before Cleanup. A compatible AI profile is optional;
without one, deterministic changes are applied and uncertain cases are
preserved with warnings. A provider failure during adjudication has the same
safe fallback.

Cleanup completion promotes the project to `text_chunking_ready` immediately.
Review and manual editing are optional rather than approval gates. Saving an
operator edit updates the output hash, marks `user_modified`, and invalidates
Chunking and later generated text/audio artifacts.

## 8. Usage

```python
from audiomancer.services import text_cleanup_service, text_extraction_service

text_extraction_service.extract_text(project_root, manifest)
result = text_cleanup_service.clean_text(
    project_root,
    manifest,
    ai_profile_payload=optional_local_profile,
)
```

## 9. Validation And Tests

Primary coverage:

- `tests/test_text_extraction_service.py`
- `tests/test_cleanup_v2_service.py`
- `tests/test_text_cleanup_state_service.py`
- `tests/test_text_cleanup_ui_controller.py`
- `tests/test_text_cleanup_page.py`

Run `uv run ruff check src tests` and `uv run pytest`. Format-specific changes
must include exact ledger/hash/role assertions. AI changes must verify the
strict schema flags, two-call maximum per question, disagreement fallback, and
context budget.

## 10. Limitations And Future Work

- Image-only PDFs fail because OCR is intentionally out of scope.
- RTF exposes text but not dependable native style/list structure.
- Ambiguous multi-column PDF reading order is preserved with warnings.
- Small or weak local models may leave more uncertainties unresolved; this is
  acceptable because the source is preserved and the operator can edit.
