<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Book Analysis

## Routing

For resumable book summaries, context packing or the Book Analysis page, start
at `book_analysis_service` and its scripted-provider tests. Credential-free
request changes belong to `book_analysis_document_service.safe_profile_fingerprint`.
Provider model discovery and effort enforcement belong to AI Runtime.

## Purpose and boundaries

Book Analysis is an optional supporting operation shown immediately after Text
Chunking. It reads only a completed, valid `chunks_text.json` and produces a
short reader-facing summary plus expandable literary and audiobook details in
the project's selected translation target language. It does not advance a
workflow stage, block Translation, or supply canonical character/voice data.

## Public interface

Confirmed Home language changes remove Book Analysis's document, AI logs and
compact summary through Project Lifecycle's reset plan. Narration-mode changes
preserve Book Analysis. The analysis page still owns its explicit Reset action.

The service consumes completed canonical chunks, the project target language and
one enabled AI profile. It writes `book_analysis.json`; document/state services
validate checkpoints and project operation summaries. The page/controller expose
Analyze and Reset through the shared operation runner.


`book_analysis_service` packs chunks in sequence and never splits a canonical
chunk. Every accepted provider response is semantically validated before an
atomic checkpoint replaces the previous document. Consolidation repeats in
ordered levels until one summary can drive the final report. A provider-confirmed
context overflow reduces the source budget once to 75 percent and repacks from
the first unprocessed item. An individual chunk that still cannot fit is
rejected with guidance to use Text Chunking or a wider-context profile.

The request budget requires at least 16,384 configured context tokens. Source
text uses at most 50 percent of local LM Studio/Ollama context or 30 percent of
an online OpenAI-compatible context, and is further reduced by prompt, output,
reasoning, and safety reserves. The controller and worker both require the effective profile context to meet
the minimum. This context controls the budget and its output reserve is sent on each Chat Completions request. Model names are never allowlisted. The profile's
reasoning budget summary is provider default, enabled, or disabled. API-key/local
providers may reject explicit reasoning, in which case the shared provider can
retry without it. Subscription profiles select exact model-supported effort;
the subscription adapter rejects unavailable explicit levels without changing effort.

## Invariants

`book_analysis.json` has two independent slots: `completed_report` and
`candidate_run`. A completed report remains visible while a new candidate is
incomplete or failed. Resume requires the exact canonical source descriptor,
target language, profile ID, and credential-free request-configuration
fingerprint, including subscription reasoning effort. Selecting a different profile starts a new candidate while
preserving the completed report. A completed report becomes stale only when
the chunks or target language change; current profile selection does not make
it stale.

Persisted running work is presented as interrupted after restart. Analyze
continues an exact candidate; Reset removes only Book Analysis's document and
AI logs. If Reset is pressed while the worker is active, the controller requests
cooperative cancellation and deletes only after the worker reaches a terminal
callback, preventing a late checkpoint from recreating the document.

## Key behaviors

Each leaf, consolidation and final request includes its canonical JSON Schema in
the prompt, independently of provider enforcement. A parsed response with invalid
fields or types is regenerated once from the original source, using the same
profile and language. Both responses' usage is merged on successful recovery;
each request remains in the AI exchange log. A second invalid response produces a
model-format error while accepted checkpoints and completed reports remain intact.
Cancellation and transport failures propagate without format regeneration.
Prompt budgets include the schema and retry reminder. Resuming refreshes these
reserves while retaining any smaller source allowance from an overflow reduction.

`REQ-FUNC-cfd856fa` includes subscription effort in the request fingerprint;
changing it preserves completed reports but starts a new analysis candidate.

The page contains one AI-profile selector and exactly two action buttons:
Analyze and Reset. Context size and reasoning preference remain on AI Settings.
Analyze is disabled while running and after a fresh completion; Reset is enabled
after any work starts. A stale completed report stays visible and enables
Analyze. Operation state appears through the shared left-side Operation Status
control, while active work uses the standard progress dialog/bar.

The concise layer contains book type, genres, subjects, setting/time, short
summary, main characters, and themes. The initially collapsed details layer
contains the detailed summary, supporting characters/relationships, narrative
perspective and structure, tone, pacing, diction, emotional range, audiobook
guidance, uncertainties, and source evidence. Model strings are rendered as
plain text.

## Change map

| Change | Entry point | Verification |
| --- | --- | --- |
| Request budget | book_analysis_budget_service | test_book_analysis_budget_service.py |
| Resume identity or persistence | book_analysis_document_service | test_book_analysis_document_service.py |
| Summary consolidation | book_analysis_service | test_book_analysis_service.py |
| Operator state and controls | BookAnalysisPage, book_analysis_ui_controller | Page and controller tests |

### Validation

Automated coverage uses scripted in-process provider results and an autouse
transport guard for every `test_book_analysis*` module. It reads no API keys,
opens no network connection, and starts no LM Studio, Ollama, or online model.
Live application/model acceptance belongs to the operator.

Primary coverage:

- `tests/test_book_analysis_budget_service.py`
- `tests/test_book_analysis_document_service.py`
- `tests/test_book_analysis_service.py`
- `tests/test_book_analysis_state_service.py`
- `tests/test_book_analysis_page.py`
- `tests/test_book_analysis_ui_controller.py`

## Files

- `05_Software/AudioMancer/src/audiomancer/services/book_analysis_budget_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/book_analysis_document_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/book_analysis_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/book_analysis_state_service.py`
- `05_Software/AudioMancer/src/audiomancer/ui/pages/book_analysis_page.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/book_analysis_ui_controller.py`
- `05_Software/AudioMancer/prompts/book_analysis_leaf.txt`
- `05_Software/AudioMancer/prompts/book_analysis_consolidate.txt`
- `05_Software/AudioMancer/prompts/book_analysis_report.txt`
