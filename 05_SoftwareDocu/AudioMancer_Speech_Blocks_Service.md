<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Speech Blocks Service

## 1. Purpose

Implements the current `Speech Blocks` workflow in `AudioMancer`.

It converts the chunk text selected through `Character Voices` into ordered
speaker-attributed speech blocks and persists those reviewable results under
`70_speech_blocks`.

## 2. Responsibilities

- resolve the active source language from `Character Voices`
- choose canonical chunking text or approved translated text as the source
- send one AI request per chunk using the selected AI profile
- normalize model output into persisted speech-block payloads
- preserve source wording exactly except for stripping one outer pair of
  dialogue quotes when they are delimiters
- fall back to `narrator` when speaker attribution is ambiguous or invalid
- persist resumable chunk-based operation state, report data, and AI
  transaction logs
- build page state, notes, and AI-profile selector entries for the
  `Speech Blocks` page
- coordinate confirmation popups, modal progress, cancellation, rerun reset,
  and manifest updates through the page controller

It does not:

- provide manual block editing in the current implementation
- generate audio segments from speech blocks
- own character discovery, narrator selection, or voice sample generation

## 3. Implementation Overview

The workflow is split across:

- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py`
  for source resolution, AI dispatch, normalization, persistence, and resume
  handling
- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_state_service.py`
  for page-state shaping, AI-profile selection, and operator notes
- `04_Software/AudioMancer/src/audiomancer/ui/pages/speech_blocks_page.py`
  for the review-only chunk list, source preview, generated block list, and
  read-only detail panel
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/speech_blocks_ui_controller.py`
  for prerequisite validation, confirmation popups, modal progress,
  cancellation, rerun reset, and manifest synchronization

High-level flow:

1. `Character Voices` selects the effective voice language for downstream work.
2. `speech_blocks_service.resolve_source_chunks(...)` loads canonical chunks
   from `20_chunking` or approved translated chunks from `30_translation`.
3. The controller confirms that the operator wants to start or continue one AI
   run and warns about time plus token usage.
4. `speech_blocks_service.start_or_continue_generation(...)` validates the
   prompt files, restores resumable state when the saved checkpoint still
   matches the current source snapshot and AI profile, and processes one chunk
   per model request.
5. Each response is normalized into stable speech-block payloads and appended
   to `output_speech_blocks.json`.
6. The current report, `state_operation.json`, and transaction log metadata
   are rewritten after every chunk so cancellation can resume from the next
   chunk.
7. On success, the controller writes the compact `project.json.operations`
   summary and advances `current_stage` to `speech_blocks_ready`.

## 4. Dependencies

- Internal dependencies:
  `04_Software/AudioMancer/src/audiomancer/config.py`
  `04_Software/AudioMancer/src/audiomancer/services/character_voices_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/deterministic_chunking_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/character_discovery_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/prompt_template_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/token_usage_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/text_cleanup_state_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
  `04_Software/AudioMancer/src/audiomancer/ui/controllers/misc_ui_controller.py`
  `04_Software/AudioMancer/src/audiomancer/ui/main_window.py`
- External dependencies:
  `PySide6`
  one configured OpenAI-compatible LLM backend reachable through the shared
  provider layer

## 5. Inputs And Outputs

Inputs:

- active project root and manifest
- selected voice language from `60_character_voices/selected_voice_language.json`
- canonical chunking output in `20_chunking/output_chunks.json`
- approved translated chunks and translation report in `30_translation/`
  when the selected voice language is translated
- discovered character profiles from `40_character_discovery`
- selected enabled AI profile from `settings.json`
- prompt templates:
  `04_Software/AudioMancer/prompts/speech_blocks_system.txt`
  `04_Software/AudioMancer/prompts/speech_blocks_user.txt`

Outputs:

- `70_speech_blocks/input_source_chunks.json`
- `70_speech_blocks/output_speech_blocks.json`
- `70_speech_blocks/artifact_speech_blocks_report.json`
- `70_speech_blocks/state_operation.json`
- `70_speech_blocks/log_ai_transactions_<timestamp>.log`
- updated manifest summary for `operations["speech_blocks"]`
- updated manifest stage `speech_blocks_ready` after successful completion

## 6. Data Contracts

Persisted speech-block payloads use:

- `speech_block_id`
- `sequence_index`
- `chunk_id`
- `chunk_sequence_index`
- `source_language`
- `speaker_kind`
- `speaker_id`
- `speaker_display_name`
- `content_kind`
- `text`
- `warning_flags`

Current invariants:

- one AI request is issued per source chunk
- `sequence_index` is global across the whole run
- `chunk_sequence_index` is local within a chunk
- `speaker_id` must be `narrator` or one discovered `character_id`
- unrecognized or ambiguous speakers fall back to narrator and add
  `ambiguous_speaker`
- narration text is stored unchanged
- dialogue text strips only one outer pair of straight double quotes when
  both ends are quotes
- block ordering never crosses chunk boundaries

Report and operation-state metadata currently include:

- `source_language`
- `source_kind`
- `ai_profile_id`
- `processed_chunk_count`
- `total_chunk_count`
- `speech_block_count`
- `warning_count`
- `warnings`
- normalized `token_usage`
- one resume checkpoint with `next_chunk_index`,
  `source_snapshot_fingerprint`, `source_language`, and `ai_profile_id`

## 7. Workflow Integration

This workflow sits immediately after `Character Voices`.

Upstream integrations:

- canonical chunk output from `20_chunking`
- approved translation output from `30_translation` when the selected voice
  language is translated
- discovered character speaker catalog from `40_character_discovery`
- selected Character Voices language from `60_character_voices`

Downstream integrations:

- `project.json.current_stage = "speech_blocks_ready"` on successful
  completion
- later `Audio Blocks` and `Audio Assembly` placeholder stages
- Character Voices language changes invalidate `70_speech_blocks`,
  `80_audio_blocks`, and `90_audio_assembly`

Runtime gating:

- one project must be open
- chunking output must exist
- the Character Voices language must resolve to either the original language
  or a fully approved translation target
- at least one enabled AI profile must be configured

## 8. Usage

Representative service calls:

```python
source_resolution = speech_blocks_service.resolve_source_chunks(
    project_root,
    manifest,
)

report = speech_blocks_service.start_or_continue_generation(
    project_root,
    manifest,
    selected_profile_payload,
    progress_callback=progress_callback,
    cancel_requested=cancel_requested,
)
```

Operator path:

- open one project that has completed `Character Voices`
- choose the desired source language on the `Character Voices` page
- open `Speech Blocks`
- select the AI profile
- confirm the generation popup
- inspect generated blocks per chunk
- if interrupted, start generation again to continue from the saved checkpoint

## 9. Validation And Tests

Focused automated coverage exists in:

- `04_Software/AudioMancer/tests/test_speech_blocks_service.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_state_service.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_page.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_ui_controller.py`
- related invalidation and repair coverage in
  `test_character_voices_ui_controller.py` and
  `test_project_workspace_service.py`

Minimum validation after a change:

```powershell
uv run python -m py_compile <changed_python_files>
uv run pytest tests/test_speech_blocks_service.py
uv run pytest tests/test_speech_blocks_state_service.py
uv run pytest tests/test_speech_blocks_page.py
uv run pytest tests/test_speech_blocks_ui_controller.py
uv run ruff check <changed_python_files> --fix
uv run ruff format <changed_python_files>
```

## 10. Limitations And Future Work

- the current page is review-only and does not support manual block edits
- contiguous coverage is delegated to the model output plus narrator fallback;
  the service does not currently verify exact span coverage against the source
  chunk
- speaker attribution uses only the discovered-character catalog plus narrator
- prosody, delivery hints, and downstream TTS control metadata are not stored
- `Audio Blocks` and `Audio Assembly` are still placeholder stages
