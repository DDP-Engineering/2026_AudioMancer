<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Audio Blocks Service

## 1. Purpose

Implements the current `Audio Blocks` workflow in `AudioMancer`.

It consumes persisted `Speech Blocks`, the selected narrator sample, per-character
samples from `Character Voices`, and the selected voice language to generate one
reviewable WAV per speech block under `80_audio_blocks`.

## 2. Responsibilities

- validate that `Speech Blocks`, narrator sample selection, character samples,
  and runtime clone capability are ready before generation starts, with
  `Qwen3-TTS-12Hz-1.7B-Base` preferred when the runtime exposes multiple healthy
  Qwen base clone models
- build one reusable client-owned `voice_clone_prompt` payload per referenced
  narrator or character sample through `POST /v1/voice/clone-prompt`
- generate one final WAV plus metadata pair per speech block in stable sequence
  order, splitting long Audio Blocks internally when the loaded clone model's
  runtime `max_new_tokens` budget requires it
- persist resumable operation state, report data, reusable prompt metadata, and
  generated artifacts after each meaningful step
- support responsive cancellation and restart-safe continuation from the saved
  checkpoint, including checkpoints inside split Audio Blocks
- support per-block approval, per-block regeneration, and approve-all updates
  without regenerating missing audio
- build page state, notes, progress, and selected-block details for the
  `Audio Blocks` page
- coordinate confirmation popups, modal progress, destructive rerun or reset,
  and manifest synchronization through the page controller
- invalidate persisted Audio Blocks data when upstream narrator, character,
  language, or Speech Blocks inputs change

It does not:

- assemble approved audio blocks into final chapter or book audio outputs
- provide sample fallback for missing character voices during batch generation
- own narrator sample generation, character sample generation, or Speech Blocks
  speaker attribution

## 3. Implementation Overview

The workflow is split across:

- `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_service.py`
  for validation, reusable clone-prompt preparation, ordered WAV generation, report and
  state persistence, approvals, regeneration, and resets
- `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_state_service.py`
  for page-state shaping, note rendering, current-block selection, and full
  source-text reconstruction
- `04_Software/AudioMancer/src/audiomancer/ui/pages/audio_blocks_page.py`
  for the operator-facing `Audio Blocks` surface with source text, speech-block
  list, selected-block detail, local playback controls, progress bar, and
  status window
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/audio_blocks_ui_controller.py`
  for runtime probing, confirmations, modal progress lifecycle, approval
  actions, local generated-WAV playback, reset behavior, manifest
  synchronization, and upstream invalidation
- `04_Software/AudioMancer/src/audiomancer/services/voiceweaver_runtime_service.py`
  for the documented `create_voice_clone_prompt(...)` and
  `generate_voice_clone_from_prompt(...)` runtime wrappers used by the service

High-level flow:

1. The controller probes the configured VoiceWeaver runtime and reuses the
   cached discovered-model list from `TTS Settings`.
2. `audio_blocks_service.start_or_continue_generation(...)` loads current
   `Speech Blocks`, narrator sample metadata, character samples, and selected
   Character Voices language.
3. The service selects the clone/base model from the discovered runtime catalog,
   preferring `Qwen3-TTS-12Hz-1.7B-Base` when it is available. It reads
   `/v1/status`, loads the clone model only when needed, then resolves the
   generation budget from runtime effective `max_new_tokens`, discovered
   `default_model_parameters.max_new_tokens`, or the generation-parameter range
   default.
4. The service builds one input fingerprint from the speech-block snapshot,
   source sample fingerprints, selected voice language, selected project
   language context, the chosen clone/base model identifier, and the resolved
   model budget.
5. When an existing `state_operation.json` still matches that fingerprint, the
   service restores the saved reusable prompt checkpoint and the next
   speech-block index.
6. Voice targets are processed first. Existing persisted reusable prompt
   payloads are reused only when target id, sample fingerprint, sample text,
   selected language, and clone-model id still match.
7. Each speech block is then synthesized in `sequence_index` order through the
   documented `POST /v1/voice/clone-from-prompt` endpoint using the persisted
   client-owned `voice_clone_prompt` payload and
   `model_parameters={"max_new_tokens": resolved_budget}`. Long blocks are split
   by paragraph/sentence, then clause punctuation, then word groups, and the
   completed part WAVs are stitched with Python `wave`.
8. After each generated block, and after each completed split part, the service rewrites
   `output_audio_blocks.json`, `artifact_audio_blocks_report.json`,
   `voice_clone_profiles.json`, and `state_operation.json`.
9. Operators can later approve one block, approve all generated blocks, or
   regenerate one selected block, which clears only that block approval.
10. The controller advances `project.json.current_stage` to
   `audio_blocks_ready` only when every speech block has generated audio and is
   approved.

## 4. Dependencies

- Internal dependencies:
  `04_Software/AudioMancer/src/audiomancer/config.py`
  `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/character_voices_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/voiceweaver_runtime_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/operation_runtime_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/text_cleanup_state_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/home_presenter_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
  `04_Software/AudioMancer/src/audiomancer/ui/controllers/misc_ui_controller.py`
  `04_Software/AudioMancer/src/audiomancer/ui/controllers/tts_runtime_ui_support.py`
  `04_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py`
  `04_Software/AudioMancer/src/audiomancer/ui/controllers/character_voices_ui_controller.py`
  `04_Software/AudioMancer/src/audiomancer/ui/controllers/speech_blocks_ui_controller.py`
  `04_Software/AudioMancer/src/audiomancer/ui/main_window.py`
- External dependencies:
  `PySide6`
  one reachable local VoiceWeaver runtime exposing the Qwen3 clone endpoints

## 5. Inputs And Outputs

Inputs:

- active project root and manifest
- selected voice language from `60_character_voices/selected_voice_language.json`
- selected narrator sample pair in
  `50_narrator_definition/audio_samples/`
- character sample pairs in `60_character_voices/audio_samples/`
- ordered speech blocks in `70_speech_blocks/output_speech_blocks.json`
- runtime connection settings and discovered models from `settings.json`

Romanian remains a valid selected voice language in AudioMancer metadata, but
VoiceWeaver TTS calls omit the outbound `language` field for `ro` so the
runtime can infer pronunciation from the Romanian text.

Outputs:

- `80_audio_blocks/input_speech_blocks.json`
- `80_audio_blocks/output_audio_blocks.json`
- `80_audio_blocks/artifact_audio_blocks_report.json`
- `80_audio_blocks/state_operation.json`
- `80_audio_blocks/voice_clone_profiles.json`
- `80_audio_blocks/generated_audio/<order_no_6digits>_<character_normalized_name>.wav`
- `80_audio_blocks/generated_audio/<order_no_6digits>_<character_normalized_name>.json`
- optional split part WAVs under
  `80_audio_blocks/generated_audio/parts/<order_no_6digits>_<character_normalized_name>_partNNN.wav`
- updated compact manifest summary for `operations["audio_blocks"]`
- updated manifest stage `audio_blocks_ready` after full generation plus approval

## 6. Data Contracts

Persisted audio-block payloads include at minimum:

- `speech_block_id`
- `sequence_index`
- `chunk_id`
- `speaker_id`
- `speaker_display_name`
- `normalized_speaker_name`
- `text`
- `voice_target_id`
- `voice_source_kind`
- `audio_relative_path`
- `metadata_relative_path`
- `generated`
- `approved`
- `approved_at`
- `generated_at`
- `runtime_result_summary`
- `split_part_count`
- `split_strategy`
- `model_token_budget`
- `model_audio_seconds_budget`
- `generated_part_relative_paths`
- `warning_flags`

Persisted reusable clone-prompt payloads include:

- `voice_target_id`
- `display_name`
- `source_sample_relative_path`
- `source_sample_fingerprint`
- `source_model_id`
- `voice_language`
- `sample_text`
- `voice_clone_prompt`
- `prompt_format`
- `generated_at`
- `clone_model_id`

Current invariants:

- speech-block filenames are stable and deterministic:
  `<order_no_6digits>_<character_normalized_name>`
- `normalized_speaker_name` is ASCII-safe and derived through
  `normalize_speaker_name(...)`
- one referenced voice target produces one reusable client-owned clone-prompt
  payload per input fingerprint
- all approvals are explicit; generation never auto-approves audio
- `approve_all_audio_blocks(...)` updates only already generated blocks
- `audio_blocks_stage_status` becomes `completed` only when generated and
  approved counts both match the total speech-block count
- mismatched fingerprints require an explicit reset and are never resumed

Current operation-state metadata includes:

- `voice_language`
- `input_fingerprint`
- `speech_block_count`
- `generated_block_count`
- `approved_block_count`
- `clone_profile_count`
- `prompt_count`
- `reused_prompt_count`
- `regenerated_prompt_count`
- `current_phase`
- `current_block_id`
- `model_id`
- `model_token_budget`
- `model_audio_seconds_budget`
- one resume checkpoint with `next_profile_index`, `next_speech_block_index`,
  and `next_split_part_index`

## 7. Workflow Integration

This workflow sits immediately after `Speech Blocks`.

Upstream integrations:

- selected narrator sample state from `50_narrator_definition/audio_samples/`
- per-character sample state from `60_character_voices`
- selected Character Voices language from `60_character_voices`
- ordered speech blocks from `70_speech_blocks`

Downstream integrations:

- `project.json.current_stage = "audio_blocks_ready"` only after full approval
- later `Audio Assembly` under `90_audio_assembly`
- resets from the page clear both `80_audio_blocks` and `90_audio_assembly`

Current invalidation points:

- narrator profile selection, selected-sample regeneration, selected-profile
  edit, and selected-profile deletion
- Character Voices prompt reset, prompt edit start, target sample regeneration,
  and selected voice-language change
- Speech Blocks rerun or reset through its own controller

## 8. Usage

Representative service calls:

```python
report = audio_blocks_service.start_or_continue_generation(
    project_root,
    manifest,
    runtime_settings,
    progress_callback=progress_callback,
    cancel_requested=cancel_requested,
)

audio_blocks_service.approve_audio_block(project_root, speech_block_id)
audio_blocks_service.regenerate_audio_block(
    project_root,
    manifest,
    speech_block_id,
    runtime_settings,
)
```

Operator path:

- complete `Speech Blocks`
- ensure the selected narrator sample and every referenced character sample exist
- open `Audio Blocks`
- confirm `Start Audio Generation`
- review generated audio per speech block
- play one selected block or use `Play Audiobook` to review generated blocks in
  sequence from the selected row
- approve one block or all generated blocks
- if interrupted, press `Start Audio Generation` again to continue from the
  saved checkpoint

## 9. Validation And Tests

Focused automated coverage exists in:

- `04_Software/AudioMancer/tests/test_audio_blocks_service.py`
- `04_Software/AudioMancer/tests/test_audio_blocks_state_service.py`
- `04_Software/AudioMancer/tests/test_audio_blocks_page.py`
- `04_Software/AudioMancer/tests/test_audio_blocks_ui_controller.py`
- `04_Software/AudioMancer/tests/test_audio_blocks_main_window.py`
- `04_Software/AudioMancer/tests/test_audio_blocks_upstream_invalidation.py`
- adjacent invalidation coverage in
  `04_Software/AudioMancer/tests/test_character_voices_ui_controller.py`

Minimum validation after a change:

```powershell
uv run python -m py_compile <changed_python_files>
uv run pytest tests/test_audio_blocks_service.py
uv run pytest tests/test_audio_blocks_state_service.py
uv run pytest tests/test_audio_blocks_page.py
uv run pytest tests/test_audio_blocks_ui_controller.py
uv run pytest tests/test_audio_blocks_main_window.py
uv run pytest tests/test_audio_blocks_upstream_invalidation.py
uv run ruff check <changed_python_files> --fix
uv run ruff format <changed_python_files>
```

## 10. Limitations And Future Work

- the current workflow assumes narrator plus all referenced character samples
  already exist; there is no narrator fallback for missing character samples in
  batch generation
- the current page supports review, regeneration, and approval, but not manual
  text editing or waveform editing
- status and progress text are persisted as simple summaries; there is no
  richer operator history beyond the current report and state files
- current generation uses the latest persisted sample artifacts and reusable
  prompt payloads only; there is no explicit version history for earlier prompt
  inputs
- cancellation stops AudioMancer polling and persists `cancelled`, but the
  current VoiceWeaver REST API does not cancel the already submitted runtime
  operation
- `Audio Assembly` remains the next downstream placeholder step
