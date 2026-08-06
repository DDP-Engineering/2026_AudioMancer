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
- Decode text deterministically from signatures and declarations, including
  cp1250, cp1251, cp1252, and explicit Latin-1 fallback behavior.
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
- Publish automatic and manual canonical Cleanup changes together with a
  synchronized Chunking-and-downstream artifact and compact-summary reset.
- Stop safely after a completed model request and resume compatible work.
- Diagnose incomplete source-unit realignment when a whitespace-only operator
  edit cannot update every persisted boundary.
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
  classification and the authoritative top-level AI batch planner.
- `cleanup_renderer_service.py`: decision validation, pure rendering, paragraph
  offsets, and runtime quality metrics.
- `cleanup_metadata_service.py`: strict completed-output access for consumers.
- `text_cleanup_service.py`: persisted orchestration, stop/resume,
  finalization, and manual edits.
- `text_cleanup_state_service.py`: read-only page state projection.
- `text_cleanup_ui_controller.py` and `text_cleanup_page.py`: existing UI
  integration.

`REQ-FUNC-c7960ee8` makes undecorated text selection evidence-based rather
than first-success. BOMs and RTF code-page declarations take priority, strict
UTF-8 is tried next, and every successfully decoded cp1250/cp1251/cp1252
candidate is scored for printable text, script coherence, and code-page
evidence. Latin-1 is an explicit terminal fallback only when all three Windows
codecs reject the bytes. The selected label is persisted in the source ledger.

`REQ-FUNC-379827ff` applies the same contract per non-navigation EPUB spine
document after checking its BOM, XML encoding declaration, and applicable HTML
charset metadata. Declared decoding is strict and an unknown codec or decode
failure names the spine item and file. Uniform EPUBs record their one encoding;
mixed EPUBs record `mixed(<sorted-encodings>)` while extracted text remains in
spine order.

`REQ-FUNC-fb96f028` makes EPUB extraction omit `script`, `style`, `nav`, every
present `hidden` attribute, and `aria-hidden` values that normalize to `true`.
The parser tracks ignored non-void tags, so ordinary nested elements remain
ignored while HTML void tags and XHTML self-closing tags cannot suppress later
visible blocks. `aria-hidden="false"` remains visible; CSS and JavaScript are
not interpreted.

`REQ-FUNC-6dd114ad` makes PDF reading-order reconstruction an identity-preserving
permutation of the physical text-line records. Horizontal column classification
is exclusive: a narrow centered line that satisfies both column predicates is
treated as spanning instead of contributing to both column populations.
Spanning material is then assigned exclusively to top, bottom, or conservative
ambiguity, so no physical line can be emitted twice. Clear two-column pages keep
top-spanning, left-column, right-column, bottom-spanning order and the existing
reconstruction reason; unresolved spanning material keeps the existing
uncertainty mode and warning.

`REQ-FUNC-6c977d3b` gives every line in every `single_column` PDF result column
identity `0`, including pages with fewer than six lines and pages whose width is
unusable. Their stable top-left order is unchanged, and Cleanup therefore does
not infer a page-column transition solely from a sparse page.

Cleanup runs in four phases: deterministic analysis, optional AI adjudication,
deterministic validation/rendering, and atomic publication. It is a fixed
service pipeline, not an agent loop. Progress is monotonic: analysis occupies
0-8%, adjudication 8-88%, validation/rendering 94%, persistence 98%, and only a
validated published result reports 100%. A compatible resume reconstructs its
first displayed percentage from persisted completed and estimated AI request
counts, so cancellation followed by resume never resets the progress display.
The adjudication phase explicitly reaches 88% even when conditional verifier
requests are skipped.

`REQ-FUNC-151a9e10` makes `plan_question_batches` the only owner of top-level
AI batching. It sorts question types deterministically, preserves input order
within each type, applies the 4/8/16 context tiers, and returns no plan for an
unusable profile. Checkpoint `batch_order`, runtime `cleanup-batch-NNNN` IDs,
membership, and the primary-plus-verifier estimate are projections of this
same plan. Recursive budget splits remain runtime children and never replace
the durable top-level plan.

`REQ-UX-bb78f412` counts resumed AI progress in completed provider requests,
not answered questions. Orchestration supplies the durable checkpoint counter
to adjudication, while per-question answers only skip completed passes. One
multi-question primary or verifier pass counts once. If recursive splits make
actual requests exceed the estimate, Cleanup persists and displays the larger
total before cancellation can interrupt it; completed work is not clamped.

Automatic finalization and manual cleaned-text save share one publication
helper. It validates the completed Cleanup document before mutation, delegates
all Chunking-and-downstream file deletion to Operation Orchestration, atomically
writes `clean_text.txt` and `cleanup.json`, then reloads and atomically saves one
manifest containing the completed Cleanup summary plus default downstream
summaries at `text_chunking_ready`. Project Lifecycle owns the reusable compact
manifest reset builder; the page-state service only delegates to it.

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

The log is operational diagnostics, not Cleanup state. `cleanup.json` is the
authoritative metadata source, `clean_text.txt` is the text output, and reset
clears Cleanup-owned artifacts.

## 6. Data Contracts

`source_ledger.json` contains exact half-open codepoint intervals for every
unit and boundary. The sorted intervals partition `extracted_text.txt` without
gaps or overlaps. The ledger includes source/text hashes, adapter/encoding
metadata, structure quality, units, boundaries, page geometry, and warnings.
Text and RTF ledgers record the selected declared or evidence-based encoding.
EPUB ledgers record a normalized uniform label or a deterministic mixed token;
they no longer claim UTF-8 unconditionally.

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
non-negative integer counters, string-only batch target IDs, and a bounded
next-batch index. Completed blocking quality counters must be present as
non-boolean integer zeroes. Every violation raises `CleanupDocumentError`; persisted shape
or value corruption does not leak `TypeError`, `KeyError`, or `AttributeError`
to consumers.

`REQ-REL-a6bddb67` applies that strict contract before the run path reads any
nested checkpoint state. Persisted boundary validation covers every outer,
prior, adjudication, and final field used by policy hashing, question rebuild,
AI reset, resume, and rendering. It also verifies that question count and
`batch_order` match the authoritative plan. A readable but invalid checkpoint
is replaced through fresh deterministic analysis as one unit; the strict loader
still raises `CleanupDocumentError`, and no field-level salvage is attempted.
Online disclosure counts every submitted question fragment, including failed
retry attempts, separately from completed resumable responses.

A compatible resume reuses deterministic analysis and completed model passes.
A model, context, request-policy, or prompt change preserves deterministic
analysis but clears all AI answers and regenerates the AI batch plan.
`finalizing/rendering` recovery rerenders from persisted decisions without
calling a model. The first resume update reports the persisted request fraction
before any new model request is submitted.
A reusable completed checkpoint also verifies that `clean_text.txt` exists and
matches `output_hash`; missing or mismatched output rerenders the same persisted
decisions without a model request.

Cleanup publication does not promise cross-file rollback, but any artifact or
manifest persistence failure propagates before the service returns or reports
100% progress. Only a fully successful publication is a completed logical
transition.

Paragraph `reason_codes` remain complete decision provenance. Runtime
`warning_flags` contain only `deterministic_fallback`,
`unknown_line_boundary`, and `page_transition_repaired`, so user-edit and
LLM-override provenance does not become a downstream warning.

## 7. Workflow Integration

Extraction is mandatory before Cleanup.
`config.CLEANUP_SUPPORTED_SOURCE_LANGUAGES` defines the supported
source-content set: English, Romanian, German, French, Russian, Portuguese,
Spanish, and Italian. This set is independent of the operator interface locale.
`REQ-FUNC-8f5415b0` compares a non-empty detected language with that tuple at
deterministic analysis. An unsupported code completes normally with one
persisted warning that names the code and asks for careful review; it remains in
state notes and the manifest warning count through AI resume and finalization.
Unavailable detection is not labelled unsupported.
Predominantly CJK or Hangul input is rejected before Cleanup artifacts are
published.

Cleanup completion promotes the project to `text_chunking_ready` immediately.
When the operator confirms Cleanup on a completed document, the controller uses
the canonical Cleanup reset transition before launching the worker; Cleanup and
all downstream artifacts and compact summaries are removed, and the worker sees
the returned reset manifest. This prevents the completed-document cache from
misrepresenting a rerun. Running, paused, finalizing, and failed documents are
resumable instead: they retain their checkpoint and the service decides whether
to resume or safely rebuild. These behaviors are covered by `REQ-FUNC-75d5b274`
and `REQ-REL-43c63d8c`.

Review and manual editing are optional rather than approval gates. While a
cleaned-text edit is active, ordinary refreshes retain the draft, Cancel
baseline, writable state, and editor position where Qt preserves it; Extract,
Cleanup, Reset Cleanup, and the AI-profile selector are disabled, while Save
and Cancel remain available outside a busy operation. A modified draft prompts
for explicit discard confirmation before New Project or Open Project; accepting
the prompt alone does not discard it, and the old edit state clears only after
the new project is actually activated. These behaviors are covered by
`REQ-UX-6fb5efc7` and `REQ-UX-e1bb52ba`.

Saving an
operator edit updates the output hash, marks `user_modified`, and invalidates
Chunking and later artifacts plus their compact manifest summaries. Automatic
Cleanup finalization and rerendering apply the same invalidation. Source,
Extraction, project options, and the newly published Cleanup artifacts remain
unchanged by the downstream reset. A whitespace-only edit realigns typed
structure by unambiguous normalized paragraph content rather than list index.
The current classifier remains authoritative for explicit scene separators; a
stale prior `scene_separator` role is never carried onto classifier-negative
prose.
Unmatched or multiply matched content keeps the classifier-only role, while a
unique content match may preserve headings and other noncontradicted roles. A
lexical edit publishes minimal `user_edited` paragraph structure without
claiming source provenance. Rebuilt user-edited paragraphs conservatively
reclassify explicit marker-only scene separators while ambiguous punctuation
and lexical content remain `body`.
If an exact source unit cannot be found during whitespace realignment, the edit
still persists, the component logger emits a warning, and `cleanup.json`
records `user_whitespace_realign_incomplete`.

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

`test_text_extraction_service.py` uses public Extraction-path TXT/RTF cases for
UTF-8 with and without BOM, cp1250, cp1251, cp1252, and RTF `ansicpg`. Its EPUB
fixtures rewrite actual ZIP members with UTF-16, cp1252, and ISO-8859-1 bytes,
then verify exact text, spine order, uniform/mixed ledger labels, and actionable
declared-encoding failures. Hidden-content cases verify HTML boolean `hidden`,
normalized `aria-hidden`, nested ignored content, HTML/XHTML void tags, and
exact visible canonical-text and ledger slices. Its PDF cases cover exclusive centered and spanning
classification, identity-preserving ordering across every layout mode,
single-column identity normalization, established reason codes, and a public
Extraction regression that proves centered source text is written once.

`test_cleanup_quality_contract.py` controls language detection to verify that
all supported codes and unavailable detection remain warning-free, while one
unsupported detected code completes with exactly one persisted warning across
state projection, manifest summary, cancelled AI resume, and finalization.

`test_cleanup_service.py` specifically seeds completed downstream compact
summaries and every current downstream artifact class for both automatic and
manual publication, asserts preservation plus a clean project reopen, and
injects manifest persistence failures into both paths.

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

## Files

From the adopted component map:

- `04_Software/AudioMancer/prompts/text_cleanup_*.txt`
- `04_Software/AudioMancer/src/audiomancer/services/cleanup_ai_adjudication_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/cleanup_analysis_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/cleanup_metadata_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/cleanup_renderer_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/cleanup_text_analysis_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/source_ledger_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/text_cleanup_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/text_cleanup_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/text_extraction_adapters.py`
- `04_Software/AudioMancer/src/audiomancer/services/text_extraction_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/main_window.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/home_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/text_cleanup_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/text_cleanup_page.py`
- `04_Software/AudioMancer/tests/fixtures/cleanup_corpus.json`
- `04_Software/AudioMancer/tests/test_cleanup_acceptance_corpus.py`
- `04_Software/AudioMancer/tests/test_cleanup_adjudication_contract.py`
- `04_Software/AudioMancer/tests/test_cleanup_metadata_service.py`
- `04_Software/AudioMancer/tests/test_cleanup_quality_contract.py`
- `04_Software/AudioMancer/tests/test_cleanup_service.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_page.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_state_service.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_ui_controller.py`
- `04_Software/AudioMancer/tests/test_home_ui_controller.py`
- `04_Software/AudioMancer/tests/test_localization_parity.py`
- `04_Software/AudioMancer/tests/test_text_extraction_service.py`
