<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer AI Translation Service

## 1. Purpose

Provides AudioMancer's AI-assisted translation and human-review workflow. It
translates canonical text chunks into the project-locked target language and
stores all durable Translation data in one authoritative project file:
`translated_text.json`.

## 2. Responsibilities

- read canonical source order and source text from `chunks_text.json`
- use `project.json.target_language` as the locked translation target
- use the currently selected enabled AI profile for every new or resumed run
- reuse saved document-level instructions when resuming an interrupted run
- translate same-language projects through the normal AI path
- checkpoint only complete chunks and never persist partial segment output
- preserve completed chunks across cancellation and provider failure
- preserve the prior text and approval when selected retranslation fails
- persist manual edits with a 750 ms debounce and flush them before selection
  changes, approvals, and application close
- derive page counts and effective review status without writing during page
  state construction
- synchronize the compact manifest operation summary in the controller
- retain the existing broad downstream invalidation when approval is lost

The component does not own source import, target-language selection, text
chunking, character discovery, narrator generation, speech generation, or the
agentic development workflow used to implement repository changes.

## 3. Implementation Overview

Primary modules:

- `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ai_translation_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/ai_translation_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/ai_translation_page.py`

Main service entrypoints:

- `load_translation_document(...)`
- `write_translation_document(...)`
- `load_translation_summary(...)`
- `sync_translation_after_chunk_change(...)`
- `start_or_continue_translation(...)`
- `retranslate_chunk(...)`
- `update_translated_text(...)`
- `approve_chunk(...)`
- `approve_all(...)`
- `reset_translation(...)`

Processing flow:

1. Text Chunking creates `chunks_text.json`.
2. A fresh translation builds the strict document, stores `running`, and sends
   the first request.
3. The service processes the first empty chunk in canonical order, using the
   current profile's context budget.
4. Each fully translated chunk is committed with one atomic document write.
5. Cancellation and failure store their terminal status without discarding
   completed chunks.
6. Successful generation ends in `review_pending` until every chunk is
   approved, then becomes `completed`.
7. The controller derives and writes only the compact Translation summary in
   `project.json`.

## 4. Dependencies

Internal dependencies include:

- `audiomancer.config`
- `ai_budget_service`
- `deterministic_chunking_service`
- `llm_provider_service`
- `operation_runtime_service`
- `prompt_template_service`
- `token_usage_service`
- `persistence_service`
- `ui_state_service`

External execution requires one enabled OpenAI-compatible AI profile. AI
transaction logs remain separate diagnostic files and are not referenced by
the authoritative document.

## 5. Inputs And Outputs

Inputs:

- active project root and manifest
- `chunks_text.json`
- locked target language
- currently selected enabled AI profile
- stable system prompt and per-request user prompt templates
- optional general translation instructions for a fresh run
- optional one-off instructions for selected retranslation

Outputs:

- authoritative `translated_text.json`
- `log_ai_translation_<timestamp>.log` diagnostic files
- compact `project.json.operations["translation"]` summary containing only
  `status`, `progress_current`, `progress_total`, `mode`, and `warning_count`

`translation_report.json` and `translation_state.json` are not created, read,
or migrated. Reset Translation may delete files with those old names as
cleanup-only behavior.

## 6. Data Contracts

`translated_text.json` has exactly these root fields:

```json
{
  "target_language": "ro",
  "status": "review_pending",
  "token_usage": {
    "input_tokens": 120,
    "output_tokens": 80,
    "total_tokens": 200,
    "usage_available": true
  },
  "budget_metadata": {
    "context_window": 8192,
    "max_output_tokens": 1024,
    "prompt_budget_tokens": 240,
    "text_budget_tokens": 4800,
    "safety_margin_tokens": 1024
  },
  "additional_translation_instructions": "Preserve formal address.",
  "chunks": [
    {
      "chunk_id": "chunk-0001",
      "translated_text": "Translated text.",
      "approved": false
    }
  ]
}
```

Persistent statuses are:

- `running`
- `in_progress`
- `cancelled`
- `failed`
- `review_pending`
- `completed`

An absent file means `not_started`; `not_started` and `invalid` are derived UI
states and are never persisted.

Contract invariants:

- the root and every chunk use exact field sets
- source text, source order, profile identifiers, timestamps, path lists,
  fingerprints, counts, and per-chunk status are not duplicated in the file
- an approved chunk must contain non-empty translated text
- incompatible JSON is rejected without overwrite and the operator is directed
  to Reset Translation
- source order and resume position come from canonical `chunks_text.json`
- counts and effective completion are derived at read time
- one-off retranslation instructions never replace the saved general document
  instructions

The AI response contract is deliberately minimal: a JSON object containing a
non-empty string field named `translated_text`.

## 7. Workflow Integration

Upstream:

- Home locks the target language
- Text Cleanup records the detected original language
- Text Chunking owns source text, stable chunk IDs, and canonical order

Downstream:

- Narrator Definition, Character Voices, Speech Blocks, Audio Blocks, project
  recovery, and export read the strict document
- translated content becomes downstream-ready only when the effective status
  is `completed`
- approval loss keeps the workflow at `translation_ready` and clears dependent
  downstream runtime data, except preserved narrator profiles

## 8. Usage

```python
summary = ai_translation_service.start_or_continue_translation(
    project_root,
    manifest,
    profile_payload,
    "ro",
    additional_translation_instructions="Preserve formal address.",
)

summary = ai_translation_service.approve_chunk(project_root, "chunk-0001")
state = ai_translation_state_service.build_ai_translation_state(
    project_root,
    manifest,
    "en",
    settings_payload,
)
```

## 9. Validation And Tests

Primary focused tests:

- `04_Software/AudioMancer/tests/test_ai_translation_service.py`
- `04_Software/AudioMancer/tests/test_ai_translation_state_service.py`
- `04_Software/AudioMancer/tests/test_ai_translation_ui_controller.py`
- `04_Software/AudioMancer/tests/test_ai_translation_page.py`

Focused integration coverage also includes Text Chunking synchronization,
project recovery, narrator/voice readiness, Speech Blocks input resolution,
Audio Blocks readiness, export, operation reset behavior, and main-window close
flush behavior.

Minimum validation after changes:

```powershell
uv run pytest tests/test_ai_translation_service.py tests/test_ai_translation_state_service.py tests/test_ai_translation_ui_controller.py tests/test_ai_translation_page.py
uv run ruff check src/audiomancer/services/ai_translation_service.py src/audiomancer/services/ai_translation_state_service.py src/audiomancer/ui/controllers/ai_translation_ui_controller.py src/audiomancer/ui/pages/ai_translation_page.py
```

## 10. Limitations And Future Work

- Segment-level resume inside one oversized chunk is intentionally unsupported;
  the durable checkpoint boundary is the complete chunk.
- Translation approval loss still uses broad downstream invalidation rather
  than chunk-scoped invalidation.
- Existing incompatible translation files require an explicit Reset
  Translation; automatic migration is intentionally unsupported.

Reviewed for the single-document Chunking contract: canonical source chunks now
come through `chunking_document_service`, with no legacy Chunking fallback.
