# Text Chunking

## Routing

Start with `chunking/` for algorithms, `deterministic_chunking_service.chunk_text`
or `ai_chunking_service.chunk_text` for execution, `chunking_edit_service` for
manual changes, and `chunking_publication_service` for recovery. Page projections
live in `text_chunking_state_service`; controller confirmations and workers live
in `ui/controllers/text_chunking_ui_controller.py`. Shared text menus and Find
navigation belong to App Shell's `ui/text_interaction.py`.

## Purpose and boundaries

Turn verified completed Cleanup paragraphs into source-only ordered chunks for
Translation, Character Discovery and speech production. The pure core imports
no project persistence, config, provider or UI services. Source loading, AI
requests, checkpoints, manual impact and publication each have a service boundary.
Chunking chooses semantic source boundaries; TTS-size splitting belongs downstream.

## Public interface

Both `chunk_text` services accept a project root, manifest, progress callback and
cancellation callback. AI also accepts the current profile, semantic strategy,
operator instructions and context mode. `restart=True` explicitly discards an
unfinished checkpoint's prefix for a new source run. Services publish the manifest;
the success controller only reloads it.

`chunking_document_service.load_chunking_document` and `load_chunks` read public
`chunks_text.json`. `load_checkpoint` prefers `chunking_pending.json`; only runtime
resume and page notes use it. `write_checkpoint` preserves a completed canonical
result by writing its replacement separately. First-run checkpoints use the
canonical path. Derived reports, operation summaries and progress are projections.
AI logs stay separate and remain after successful generation; explicit reset owns them.

Manual edit, insertion and deletion use stable chunk IDs. Existing page-facing
entry points in the state module delegate to `chunking_edit_service`. Editing is
blocked while either the initial run or its replacement is resumable. A first
empty manual chunk is allowed when verified clean text exists.

## Invariants

- Only completed `cleanup.json` with an output hash matching `clean_text.txt` can
  supply automatic paragraphs. No rediscovery from unverified plain text.
- Generated text is joined directly from source paragraphs. Automatic chunks
  have inclusive 1-based `source_paragraph_start/end`. Exact ordered coverage,
  text and materialized metadata are validated before resume and completion.
- Headings and retained `page_artifact` paragraphs stand alone. Role transitions
  split groups. Scene separators are omitted and set the next chunk's required
  boolean `starts_after_scene_separator`; trailing separators produce no chunk.
- Group confidence is the weakest of strong/medium/low, or null if any is unknown;
  warning flags are the ordered union of Cleanup warnings. Chapter detection uses
  shared uppercase standard Roman numeral grammar and localized chapter labels.
- The strict root contains lifecycle, mode, manual flag, text fingerprint, plan
  and request fingerprints, strategy, instructions, usage, warnings, checkpoint,
  fallback count and chunks. Raw profile/model/budget/progress/log-path fields
  remain outside the persisted document. Only the current shape is supported.
- `plan_fingerprint` hashes paragraph text, roles, confidence, page-join flags and
  warnings under the core policy version. Resume rejects a changed plan or corrupt
  source prefix before checkpoint writes or provider calls.
- Resume retains strategy, instructions, cumulative usage and fallback count.
  A changed nonsecret AI request fingerprint keeps the verified prefix and emits
  a warning before the remaining source uses current prompts/profile/context.
- First-run and replacement cancellation/failure preserve committed source
  prefixes. Final publication errors checkpoint the complete processed prefix as
  failed/cancelled on the original initial/pending path. Published chunks and
  downstream files remain intact during replacement.
- Publication stages results, backs up changed owned originals under relative
  names, then replaces files. Caught failures restore originals. Failed restoration
  retains a named recovery folder. This is caught-error recovery, not crash atomicity.
  Redirected paths and source/artifact overlaps are rejected before mutation.
- Manual selective impact runs on a staged owned-artifact snapshot. Immutable audio
  is hardlinked where supported, copied otherwise. Live files change only at the
  publication boundary. Surviving IDs stay stable; edited/inserted text clears
  automatic bounds/confidence/warnings and uses conservative manual roles.
- Manual insertion defaults its scene marker to false; edits retain the existing
  marker; deleting a marked chunk transfers it to the next survivor. Deleting the
  final remaining chunk is rejected. Unchanged chunks retain their metadata.

## Change map

| Change requested | Start with | Focused verification |
|---|---|---|
| Source roles, confidence, coverage | chunking/materialization.py | test_chunking_refinement.py; test_cleanup_chunking_contract.py |
| Strict persisted shape | chunking/document.py; chunking_document_service.py | test_chunking_single_document_contract.py |
| Budget/cursor/AI policy | chunking/planning.py; chunking_ai_service.py | test_ai_chunking_service.py; test_chunking_refinement.py |
| Anchored model boundaries | chunking/descriptors.py | test_ai_chunking_descriptor_contract.py |
| Cancellation/resume | both chunk_text orchestrators | test_deterministic_chunking_service.py; test_chunking_refinement.py |
| Manual selective changes | chunking_edit_service.py | test_text_chunking_state_service.py |
| File recovery | chunking_publication_service.py | test_chunking_refinement.py |
| UI flow and page notes | state service and UI controller | test_text_chunking_ui_controller.py; test_text_chunking_page.py |

## Key behaviors

- REQ-NFR-6df93f95: pure validation, materialization, descriptors and planning.
- REQ-FUNC-6a9a707e / REQ-DATA-20f1afcf: protected roles and honest grouped metadata.
- REQ-DATA-590ff8b1: verified source plan and exact automatic prefix coverage.
- REQ-FUNC-16bd24d0 / REQ-NFR-149f8458: one cost estimate per paragraph; next-window
  cursor; oversized paragraphs remain whole with warning and no model request.
- REQ-FUNC-236b922c / REQ-REL-782398af: strict initial/pending checkpoint ownership.
- REQ-REL-0c8588a0: recoverable staged generation and manual publication.
- REQ-FUNC-978f58f7: stable IDs and conservative edited/inserted metadata.
- REQ-FUNC-d582b019: visible AI request-policy change on resume.
- REQ-FUNC-b9aba951 / REQ-FUNC-5f75bee9: strict descriptor schema and normalized
  anchors commit only the consecutive valid prefix; an invalid tail is retried.
  Empty/no-valid-prefix responses take structural fallback, including final windows.
- REQ-FUNC-8fd4bd61: deterministic checkpoints every 200 paragraphs or 2 seconds,
  throttled progress at 0.1 seconds, and complete-unit cancellation checkpoints.
- REQ-DATA-36f1bf4e: separate AI logs and explicit-reset ownership.

## Files

Application paths below are relative to `05_Software/AudioMancer/`:

- `src/audiomancer/chunking/{document,materialization,planning,descriptors}.py` — pure core.
- `src/audiomancer/services/chunking_input_service.py` — verified Cleanup source adapter.
- `src/audiomancer/services/chunking_ai_service.py` — prompt, budget and provider adapter.
- `src/audiomancer/services/{deterministic,ai}_chunking_service.py` — execution and checkpoint orchestration.
- `src/audiomancer/services/chunking_document_service.py` — canonical/pending persistence and projections.
- `src/audiomancer/services/chunking_edit_service.py` — manual stable-ID selective changes.
- `src/audiomancer/services/chunking_publication_service.py` — staging, owned-file replacement and recovery.
- `src/audiomancer/services/text_chunking_state_service.py` — page projection and mutation facade.
- `src/audiomancer/ui/controllers/text_chunking_ui_controller.py` — UI confirmation/worker/refresh flow.
- `src/audiomancer/ui/pages/text_chunking_page.py` — preview and editor controls.
- `src/audiomancer/{config.py,services/operation_runtime_service.py}` — pending artifact/reset ownership.
- `tests/test_chunking_refinement.py` — structural, performance, resume, IO recovery and thin-controller regressions.
- `tests/test_{deterministic_chunking_service,ai_chunking_service,ai_chunking_descriptor_contract}.py` — execution/AI contracts.
- `tests/test_{chunking_single_document_contract,cleanup_chunking_contract,text_chunking_state_service}.py` — schema/source/edit contracts.
- `tests/test_{text_chunking_ui_controller,text_chunking_page}.py` — desktop behavior.
