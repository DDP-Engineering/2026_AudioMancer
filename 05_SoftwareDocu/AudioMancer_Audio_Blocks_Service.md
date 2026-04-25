<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Audio Blocks Service

## 1. Purpose

Implements the current `Audio Blocks` workflow in `AudioMancer`.

It consumes approved persisted `Speech Blocks`, the selected narrator sample,
per-character samples from `Character Voices` when the project uses
narrator-plus-character assignment, and the selected voice language to generate
one reviewable WAV per approved speech block under the root-level
`audio_blocks/` generated audio folder. When the project TTS plan uses
`voice_assignment_mode == "same_narrator"`, all spoken blocks use the selected
narrator sample and reusable narrator clone prompt.

## 2. Responsibilities

- validate that `Speech Blocks`, narrator sample selection, required character
  samples, and runtime clone capability are ready before generation starts, with
  `Qwen3-TTS-12Hz-1.7B-Base` preferred when the runtime exposes multiple healthy
  Qwen base clone models
- build one reusable client-owned `voice_clone_prompt` payload per referenced
  narrator or character sample through `POST /v1/voice/clone-prompt`
- generate one final WAV plus metadata pair per approved speech block in stable
  book order, splitting long Audio Blocks internally when the loaded clone
  model's runtime `max_new_tokens` budget requires it
- persist resumable operation state, report data, reusable prompt metadata, and
  generated artifacts after each meaningful step
- support responsive cancellation and restart-safe continuation from the saved
  checkpoint, including checkpoints inside split Audio Blocks
- support per-block approval, per-block regeneration, and approve-all updates
  without regenerating missing audio
- allow incremental generation when only some Speech Blocks are approved; the
  remaining unapproved Speech Blocks stay pending until they are approved and
  generation is run again
- represent `pause`, `background_noise`, and `indication` Speech Blocks as
  metadata-only Audio Blocks that do not call VoiceWeaver
- build page state, notes, progress, and selected-block details for the
  `Audio Blocks` page
- coordinate confirmation popups, modal progress, destructive rerun or reset,
  and manifest synchronization through the page controller
- invalidate persisted Audio Blocks data when upstream narrator, character,
  language, or Speech Blocks inputs change

It does not:

- assemble approved audio blocks into final chapter or book audio outputs
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
   `Speech Blocks`, filters the generation set to approved blocks, resolves
   narrator sample metadata from `narator_sample.json`, falls back to the
   selected narrator profile sample metadata for older projects where
   `narator.json` contains only selection state, loads character samples only
   when narrator-plus-character assignment is active, and reads the selected
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
5. When an existing `audio_blocks_state.json` still matches that fingerprint, the
   service restores the saved reusable prompt checkpoint and the next
   speech-block index.
6. Voice targets are processed first. Existing persisted reusable prompt
   payloads are reused only when target id, sample fingerprint, sample text,
   selected language, and clone-model id still match.
7. Each approved speech block is then synthesized in canonical book order:
   source chunk order first, then that chunk's local `sequence_index`. The
   service calls the documented `POST /v1/voice/clone-from-prompt` endpoint
   using the persisted client-owned `voice_clone_prompt` payload and
   `model_parameters={"max_new_tokens": resolved_budget}`. Long blocks are
   split by paragraph/sentence, then clause punctuation, then word groups, and
   the completed part WAVs are stitched with Python `wave`.
8. After each generated block, and after each completed split part, the service rewrites
   `audio_blocks.json`, `audio_blocks_report.json`, `voice_clone_profiles.json`,
   and `audio_blocks_state.json`.
9. Operators can later approve one block, approve all generated blocks, or
   regenerate one selected block, which clears only that block approval.
10. If only a subset of Speech Blocks was approved, the operation state remains
    `in_progress`, generated blocks are kept, and the operator can approve more
    Speech Blocks and continue later.
11. The controller advances `project.json.current_stage` to
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
- selected voice language from `project.json`
- selected narrator sample audio in root-level `narator.wav`; selected sample
  metadata in `narator_sample.json`; older projects with only selected profile
  state in `narator.json` fall back to the profile `sample_metadata`
- character sample audio files and metadata from `characters_voice.json` when
  the project uses narrator-plus-character assignment
- ordered speech blocks in `speech_blocks.json`
- runtime connection settings and discovered models from `settings.json`

Romanian remains a valid selected voice language in AudioMancer metadata, but
VoiceWeaver TTS calls omit the outbound `language` field for `ro` so the
runtime can infer pronunciation from the Romanian text.

Outputs:

- `audio_blocks.json`
- `audio_blocks_report.json`
- `audio_blocks_state.json`
- `voice_clone_profiles.json`
- `audio_blocks/<chunk_no_4digits>_<chunk_local_no_6digits>_<character_normalized_name>.wav`
- `audio_blocks/<chunk_no_4digits>_<chunk_local_no_6digits>_<character_normalized_name>.json`
- optional split part WAVs under
  `audio_blocks/parts/<chunk_no_4digits>_<chunk_local_no_6digits>_<character_normalized_name>_partNNN.wav`
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
- `content_kind`
- `metadata_only`
- `pause_duration_ms` for pause blocks when an explicit duration was parsed
- `speech_block_approved`
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
  `<chunk_no_4digits>_<chunk_local_no_6digits>_<character_normalized_name>`
- `sequence_index` mirrors the Speech Blocks chunk-local index; it is not
  globally unique
- Audio Blocks lookup and merge operations match records by `speech_block_id`
- generated output ordering is source chunk order, then chunk-local
  `sequence_index`
- `normalized_speaker_name` is ASCII-safe and derived through
  `normalize_speaker_name(...)`
- one referenced voice target produces one reusable client-owned clone-prompt
  payload per input fingerprint
- unapproved Speech Blocks remain present in `audio_blocks.json`, but they are
  skipped by generation until `speech_block_approved` becomes true
- metadata-only `pause`, `background_noise`, and `indication` blocks are marked
  generated and approved automatically when their source Speech Block is
  approved
- pause blocks retain a millisecond duration for Audio Assembly silence
  insertion; the downstream default is `1000 ms`
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

- selected narrator sample state from root-level `narator.wav`,
  `narator_sample.json`, and selected profile state in `narator.json`
- per-character sample state from `characters_voice.json` when
  `voice_assignment_mode == "narrator_and_characters"`
- selected Character Voices language from `project.json`
- ordered speech blocks from `speech_blocks.json`

Downstream integrations:

- `project.json.current_stage = "audio_blocks_ready"` only after full approval
- `Audio Assembly`, which consumes approved generated Audio Blocks as the final
  WAV composition source
- resets from the page clear audio-block and audio-assembly runtime artifacts

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
- ensure the selected narrator sample exists; when using narrator-plus-character
  assignment, also ensure every referenced character sample exists
- open `Audio Blocks`
- confirm `Start Audio Generation`
- review generated audio per speech block
- play one selected block or use `Play Audiobook` to review generated blocks in
  sequence from the selected row
- approve one block or all generated blocks
- after selected-block approval, the page advances the speech-block list to
  the next row when one exists and keeps the final row selected at the end
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

- same-narrator mode intentionally uses the narrator voice for all spoken
  dialogue and does not preserve per-character vocal differences
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
- `Audio Assembly` is implemented as the downstream WAV composition step; MP3
  and richer mastering features remain future work there
