# Text Cleanup

## Routing

For Cleanup structure, page transitions, AI boundary adjudication, resumable
replacement or manual corrections, start at `text_cleanup_service.clean_text`
and `tests/test_cleanup_refinement.py`. Format parsing belongs to
`audiomancer.extraction`; provider transport and schema enforcement belong to
AI Runtime; downstream segmentation belongs to Text Chunking.

## Purpose and boundaries

Cleanup turns canonical extracted text and its source ledger into narration-ready
text using source slices and typed decisions. The isolated `cleanup` package owns
structural analysis, text helpers, rendering and edit metadata matching. Application
services own project IO, checkpoints, model requests, publication and UI state.

Extraction supports TXT, Markdown, PDF, RTF, DOCX, ODT, EPUB, local HTML/XHTML
and FB2 through its format registry. Cleanup consumes their common ledger without
format-specific parsers. OCR and free-form AI text rewriting are outside Cleanup.

## Public interface

- `cleanup.analysis.analyze_cleanup(text, ledger)` returns unit roles, decisions,
  bounded AI questions, a document profile and warnings.
- `cleanup.render.render_cleanup(text, ledger, operations, boundaries,
  check_cancelled=...)` returns text and derived paragraph/quality metadata.
  The optional callback raises the caller's cancellation exception.
- `cleanup.editing.realign_paragraph_roles(previous, current, exact=...)` carries
  metadata across unique paragraph matches in caller-supplied runtime records.
- `text_cleanup_service.clean_text(root, manifest, ai_profile_payload=None,
  progress_callback=None, cancel_requested=None, force=False)` starts/resumes work.
  Confirmed completed reruns use `force=True`; default calls resume compatible
  pending work or return the valid completed result.
- `load_cleanup_document(root)` strictly loads the published `cleanup.json`.
- `save_user_cleaned_text(root, text)` validates and publishes an operator edit.
- `cleanup_metadata_service.load_completed_paragraph_records` supplies verified
  offsets and paragraph-local provenance to Chunking.
- `cleanup_text_analysis_service` exposes the shared pure text-helper API to
  other workflow services; Cleanup itself imports `cleanup.text` directly.

## Invariants

- Canonical text and ledger intervals partition source content with no gaps or
  overlaps. The renderer validates this contract before using exact source slices.
- Every unit has one resolved role and every boundary one typed choice. Roles
  include body, heading, list_item, verse, preformatted, footnote, scene_separator
  and page_artifact. Boundaries support space joins, paragraph/semantic breaks,
  dehyphenation, preserved-hyphen joins and document end.
- Native paragraphs/line breaks, protected roles and terminal hyphenation precede
  generic page-continuation rules. TXT verse uses recorded leading_spaces; PDF
  verse uses line geometry. Dropped-artifact bridges carry one effective decision;
  filler decisions preserve complete provenance and never add separators. Bounded
  AI questions describe the nearest surviving right text.
- Artifact removal requires repeated-edge or sequential-number evidence and never
  empties an entire page. Recognized artifacts on otherwise empty pages remain
  present. Retained same-page artifacts preserve a safe space separator.
- Rendering rejects unknown/duplicate operations, unsafe adjacency, oversized
  artifact removal and empty output. Authorized dehyphenation is the sole allowed
  source-span alphanumeric fusion. Paragraph metadata traverses ordered records
  with cursors rather than scanning the full ledger for every paragraph.
- AI can choose only listed boundary operations. It requires structured output
  and >=16K context. Context tiers use 4/8/16 homogeneous questions; budget failures
  split recursively. A failed request retries once before that batch falls back.
  Only primary disagreements receive a blind verifier using the same profile;
  an override needs agreement. No unconstrained fallback or model repair is used.
- The output reservation is local planning data within the 70% context ceiling;
  provider output-limit fields are omitted. No prompts, excerpts or credentials
  enter durable Cleanup metadata; hosted fragment submissions and normalized
  token usage are recorded separately from completed resumable responses.
- `cleanup.json` is the authoritative completed metadata with `clean_text.txt`.
  A first-run checkpoint uses cleanup.json; a replacement preserves those files
  and uses cleanup_pending.json. Successful publication removes pending state.
  Explicit Reset Cleanup clears both through the operation ownership registry.
- Strict validation covers the exact root, typed decisions, progress fields,
  non-boolean non-negative counters, batch membership and zero blocking metrics.
  Corrupt checkpoints start fresh analysis; strict public loading raises
  CleanupDocumentError. Compatible resumes preserve completed AI passes; changed
  profile/prompt policy resets AI answers while retaining valid analysis.
- Finalizing recovery rerenders persisted decisions without a provider call.
  Cancellation is checked on entry, during rendering and before publication.
  First-run AI cancellation persists paused state; replacement cancellation
  preserves the previous published manifest and downstream data.
- Publication stages validated text, metadata and a single reset manifest before
  moving originals into a relative-path backup. Handled IO failures restore all
  moved files. Recovery failures retain originals in a named folder and raise.
  Process termination/power-loss atomicity is not promised. Only full success
  reports 100 percent and invalidates Chunking and later results.
- Whitespace edits retain metadata only across normalized unique matches in both
  paragraph sets; lexical edits require exact unique text and mark the whole
  document user_edited. Modified/duplicate paragraphs receive conservative roles
  and unavailable provenance. Explicit scene separators remain recognized.
  Unlocatable whitespace source units emit user_whitespace_realign_incomplete.
- Runtime quality counters describe permitted transformations and uncertainty,
  not semantic accuracy or oracle F1. Paragraph reason_codes preserve provenance;
  downstream warning_flags contain only deterministic_fallback,
  unknown_line_boundary and page_transition_repaired.
- Latin/Cyrillic are supported; predominantly CJK/Hangul sources are rejected.
  Rules are tuned for en/ro/de/fr/ru/pt/es/it; other detected languages receive one
  warning. Language detection is diagnostic and does not rewrite the source.
- The existing page retains profile selection, previews, Reset and Edit/Save/Cancel.
  Active edits disable workflow replacement. Confirmed reruns defer reset until
  publication; pending replacements resume without a second destructive prompt.
  Progress remains monotonic across completed-request checkpoint resume.

## Change map

| Change requested | Start with | Focused verification |
| --- | --- | --- |
| Roles, page semantics, indentation | cleanup/analysis.py | test_cleanup_refinement.py, test_cleanup_quality_contract.py, test_cleanup_acceptance_corpus.py |
| Rendering, fusion and metadata cost | cleanup/render.py | test_cleanup_refinement.py, test_cleanup_quality_contract.py |
| AI budget, strict responses, retry/resume | cleanup_ai_adjudication_service.py, text_cleanup_service.py | test_cleanup_adjudication_contract.py, test_cleanup_quality_contract.py |
| Safe rerun, cancellation, IO recovery | cleanup_publication_service.py, text_cleanup_service.py | test_cleanup_refinement.py, test_cleanup_service.py |
| Manual metadata retention | cleanup/editing.py, cleanup_metadata_service.py | test_cleanup_service.py, test_cleanup_refinement.py, test_cleanup_chunking_contract.py |
| Page actions and state | text_cleanup_ui_controller.py, text_cleanup_state_service.py | test_text_cleanup_ui_controller.py, test_text_cleanup_page.py |

## Key behaviors

- REQ-REL-8421d5d4: preserve completed results during reruns and restore on IO failure.
- REQ-FUNC-5f6bace8: protect structural roles and hyphens across page/artifact gaps.
- REQ-FUNC-d3d0f343: recorded TXT indentation constrains inferred verse.
- REQ-NFR-5940b263: processing runs without project services, config or Qt imports.
- REQ-NFR-8b7ba0b8: paragraph provenance traversal has a linear work bound.
- REQ-FUNC-9883c613: lexical edits retain only exact unique paragraph metadata.
- REQ-REL-ab1ad6e4: cancellation through finalization preserves published results.
- REQ-FUNC-50c48e76 and REQ-NFR-5425de7d: completed/pending metadata and compatible resume.
- REQ-FUNC-e42171cc: inspect rendered spans to reject introduced alphanumeric fusion.
- REQ-REL-a6bddb67: validate the complete checkpoint before reuse.
- REQ-FUNC-151a9e10 and REQ-UX-bb78f412: one authoritative batch plan and request-based resume progress.
- REQ-FUNC-c30ccde3: retain only unambiguous whitespace-edit paragraph provenance.
- REQ-FUNC-0cbc8cba and REQ-FUNC-85b20482: hosted subscription fragment disclosure and strict domain schemas.
- REQ-FUNC-644ff463: output reservation belongs to local context planning.

## Files

- `05_Software/AudioMancer/src/audiomancer/cleanup/` — isolated analysis, render, text, source slices and edit matching.
- `05_Software/AudioMancer/src/audiomancer/services/cleanup_publication_service.py` — staged replacement and rollback.
- `05_Software/AudioMancer/src/audiomancer/services/text_cleanup_service.py` — runtime coordination, checkpoint validation and resume.
- `05_Software/AudioMancer/src/audiomancer/services/cleanup_ai_adjudication_service.py` — model boundary adapter.
- `05_Software/AudioMancer/src/audiomancer/services/cleanup_metadata_service.py` — completed paragraph access for consumers.
- `05_Software/AudioMancer/src/audiomancer/services/cleanup_text_analysis_service.py` — shared helper facade.
- `05_Software/AudioMancer/src/audiomancer/services/text_cleanup_state_service.py` — read-only page state.
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/text_cleanup_ui_controller.py` — workflow actions and confirmations.
- `05_Software/AudioMancer/src/audiomancer/ui/pages/text_cleanup_page.py` — existing page layout and editing controls.
- `05_Software/AudioMancer/src/audiomancer/services/ui_state_service.py` — English/Romanian confirmation messages.
- `05_Software/AudioMancer/src/audiomancer/config.py` — artifact names and supported-language UI contract.
- `05_Software/AudioMancer/src/audiomancer/services/operation_runtime_service.py` — artifact ownership and reset planning.
- `05_Software/AudioMancer/prompts/text_cleanup_adjudication_*.txt` — bounded primary/verifier prompts.
- `05_Software/AudioMancer/tests/test_cleanup_refinement.py` — isolation, semantics, rollback, cancellation, exact edits and traversal bound.
- `05_Software/AudioMancer/tests/test_cleanup_service.py` — publication, manual edits and downstream preservation/invalidation.
- `05_Software/AudioMancer/tests/test_cleanup_quality_contract.py` — strict contracts, projection guards and resume.
- `05_Software/AudioMancer/tests/test_cleanup_adjudication_contract.py` — AI requests, context and retries.
- `05_Software/AudioMancer/tests/test_cleanup_acceptance_corpus.py` and `tests/fixtures/cleanup_corpus.json` — 24 gold cases including HTML/FB2.
- `05_Software/AudioMancer/tests/test_cleanup_metadata_service.py` and `tests/test_cleanup_chunking_contract.py` — downstream offsets and roles.
- `05_Software/AudioMancer/tests/test_text_cleanup_ui_controller.py`, `tests/test_text_cleanup_state_service.py` and `tests/test_text_cleanup_page.py` — page behavior.
- `05_Software/AudioMancer/tests/test_extraction_new_formats.py` — native new-format integration including FB2 poetry through Cleanup.
