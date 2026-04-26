<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer AI Translation Service

## 1. Purpose

Provides the AI Translation workflow for `AudioMancer`. It translates canonical
text chunks into the project-locked target language, persists per-chunk review
records, supports approval and manual corrections, and exposes page state for
the `AI Translation` UI.

## 2. Responsibilities

- read canonical chunk text from `chunks_text.json`
- use the locked `project.json.target_language` as the only translation target
- create pass-through translation records when original and target languages
  match
- call the configured OpenAI-compatible profile for chunk translation
- split oversized chunk text into budgeted translation segments before model
  calls
- persist translated chunk records, operation state, report data, and AI logs
- support selected-chunk edit, retranslate, approve, approve-all, and reset
- shape page state with original-language and target-language indicators

It does not own source import, chunking, character discovery, voice generation,
or target-language selection. Target-language selection is locked on the Home
page before source import.

## 3. Implementation Overview

The component is implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ai_translation_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/ai_translation_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/ai_translation_page.py`

Main service entrypoints:

- `ensure_translation_records(...)`
- `ensure_pass_through_translation(...)`
- `start_or_continue_translation(...)`
- `retranslate_chunk(...)`
- `update_translated_text(...)`
- `approve_chunk(...)`
- `approve_all(...)`
- `reset_translation(...)`
- `build_ai_translation_state(...)`
- `build_ai_translation_notes(...)`

High-level flow:

1. Text Chunking creates canonical chunks.
2. The controller reads the locked target language from `project.json`.
3. The state service displays original and target language indicators.
4. If original language equals target language, the service creates
   pass-through translated chunks without an AI call.
5. Otherwise, the service translates one chunk at a time, persists progress
   after each chunk, and appends provider transaction metadata.
6. Review remains incomplete until translated chunks are approved.

## 4. Dependencies

- Internal dependencies:
  `audiomancer.config`,
  `audiomancer.services.deterministic_chunking_service`,
  `audiomancer.services.llm_provider_service`,
  `audiomancer.services.operation_runtime_service`,
  `audiomancer.services.prompt_template_service`,
  `audiomancer.services.project_workspace_service`,
  `audiomancer.services.token_usage_service`, and
  `audiomancer.services.ui_state_service`
- External dependencies:
  Python standard library and one configured OpenAI-compatible LLM backend

## 5. Inputs And Outputs

Inputs:

- active project root and manifest
- `chunks_text.json`
- locked `project.json.target_language`
- `project.json.original_language`, when detected by cleanup
- selected enabled AI Translation profile from settings
- translation prompt templates under `04_Software/AudioMancer/prompts/`

Outputs:

- `translated_text.json`
- `translation_report.json`
- `translation_state.json`
- `translation_input_snapshot.json`
- `log_ai_translation_<timestamp>.log`
- compact manifest operation summary for `operations["translation"]`

## 6. Data Contracts

Translated chunk records include:

- `chunk_id`
- `source_text`
- `translated_text`
- `target_language`
- `status`
- `approved`
- `approved_at`
- warning and metadata fields used by review state

Invariants:

- target language comes from `project.json.target_language`
- reset clears translation artifacts but does not unlock or change target
  language
- same-language pass-through uses source text as translated text and avoids AI
  rewriting
- approval is required before downstream character and voice workflows consume
  translated text

## 7. Workflow Integration

Upstream:

- Text Cleanup detects and stores `project.json.original_language`
- Text Chunking creates canonical chunks
- Home locks the target language before source import

Downstream:

- Characters, Narator Voice, Character Voices, Speech Blocks, Audio Blocks, and
  Audio Assembly consume either canonical text or approved translation state
- workflow stage advances to `character_discovery_ready` only after translation
  review is complete

## 8. Usage

Representative service calls:

```python
state = ai_translation_state_service.build_ai_translation_state(project_root, manifest, settings_payload, "en")
report = ai_translation_service.start_or_continue_translation(project_root, manifest, "ro", profile_payload)
report = ai_translation_service.approve_chunk(project_root, "chunk-0001")
```

## 9. Validation And Tests

Focused automated coverage includes:

- `04_Software/AudioMancer/tests/test_ai_translation_service.py`
- `04_Software/AudioMancer/tests/test_ai_translation_state_service.py`
- `04_Software/AudioMancer/tests/test_ai_translation_ui_controller.py`
- `04_Software/AudioMancer/tests/test_ai_translation_page.py`

Minimum validation after changes:

```powershell
uv run python -m py_compile src/audiomancer/services/ai_translation_service.py src/audiomancer/services/ai_translation_state_service.py
uv run pytest tests/test_ai_translation_service.py tests/test_ai_translation_state_service.py tests/test_ai_translation_ui_controller.py tests/test_ai_translation_page.py
```

## 10. Limitations And Future Work

- The service relies on language codes and labels already supported by
  `config.TRANSLATION_LANGUAGE_OPTIONS`.
- Pass-through translation is intentionally not an AI rewrite or proofread.
