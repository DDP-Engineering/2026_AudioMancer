<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Speech Blocks Service

## 1. Purpose

Implements the current approval-driven `Speech Blocks` workflow in
`AudioMancer`.

It converts the chunk text selected through the Narator Voice language into ordered
speaker-attributed speech blocks, gives the operator a focused review and edit
surface, and persists the approved results as root-level Speech Blocks
artifacts.

## 2. Responsibilities

- resolve the active source language from `project.json.selected_voice_language`
- choose canonical chunking text or approved translated text as the source
- send one AI request per chunk using the selected AI profile
- normalize model output into the new persisted speech-block schema only
- assign speech block IDs in `CCCC-BBBBBB` format, for example
  `0001-000001`
- persist AI-extracted baseline speaker, content kind, and text values beside
  the current editable values
- preserve source wording exactly except for stripping one outer pair of
  dialogue quotes when they are delimiters
- fall back to `narrator` when speaker attribution is ambiguous or invalid
- expose speaker choices from `Narrator` plus discovered characters
- expose content kinds `Narration`, `Dialogue`, `Background Noise`, `Pause`,
  and `Indication`
- support selected-block edit, save, and reset-to-AI-baseline operations
- support manual selected-chunk Speech Block insertion and deletion, with
  chunk-local ID renumbering from the changed point onward
- clear warning indicators as soon as an operator starts editing a block
- approve all speech blocks and report approval counts
- regenerate one selected chunk and rebuild only that chunk's local sequence
  indexes plus block IDs
- reset Speech Blocks plus downstream Audio Blocks and Audio Assembly artifacts
- persist resumable chunk-based operation state, report data, and AI
  transaction logs
- build page state, notes, speaker catalogs, content-kind labels, and
  AI-profile selector entries for the `Speech Blocks` page
- coordinate confirmation popups, modal progress, cancellation, reset,
  re-splitting, downstream audio reconciliation, and manifest updates through
  the page controller

It does not:

- preserve compatibility with old `speech-block-0001` style artifacts
- migrate old Speech Blocks or Audio Blocks artifacts
- generate audio segments from speech blocks
- send `Pause`, `Background Noise`, or `Indication` blocks to VoiceWeaver
- own character discovery, narrator selection, or voice sample generation

## 3. Implementation Overview

The workflow is split across:

- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py`
  for source resolution, AI dispatch, normalization, persistence, approval,
  editing, reset, selected-chunk regeneration, ID rebuilding, and resume
  handling
- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_state_service.py`
  for page-state shaping, AI-profile selection, speaker/content selectors,
  approval counts, and operator notes
- `04_Software/AudioMancer/src/audiomancer/ui/pages/speech_blocks_page.py`
  for the top chunk list, selected chunk preview, speech block list, selected
  block editor, manual insert/delete buttons, approval button, reset button,
  and selected-chunk re-split action
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/speech_blocks_ui_controller.py`
  for prerequisite validation, confirmation popups, modal progress,
  cancellation, explicit reset, approve-all, selected-block edit/reset/save,
  selected-chunk re-splitting, downstream Audio Blocks reconciliation, and
  manifest synchronization

High-level flow:

1. `Narator Voice` selects the effective voice language for downstream work.
2. `speech_blocks_service.resolve_source_chunks(...)` loads canonical chunks
   from `chunks_text.json` or approved translated chunks from
   `translated_text.json`.
3. The controller confirms that the operator wants to start or continue one AI
   run and warns about time plus token usage.
4. `speech_blocks_service.start_or_continue_generation(...)` validates the
   prompt files, restores resumable state when the saved checkpoint still
   matches the current source snapshot and AI profile, and processes one chunk
   per model request.
5. Each response is normalized into new speech-block payloads, including AI
   baseline values, editable current values, warning flags, approval fields,
   chunk-local sequence indexes, and `CCCC-BBBBBB` IDs.
6. The current `speech_blocks_report.json`, `speech_blocks_state.json`, and
   transaction log metadata are rewritten after every chunk so cancellation can
   resume from the next chunk.
7. Finished generation leaves Speech Blocks in review until all blocks are
   approved.
8. `Approve All Speech Blocks` marks every block approved and advances the
   manifest to `speech_blocks_ready`.
9. Editing one block invalidates affected downstream Audio Blocks state.
10. Inserting or deleting a block rewrites `speech_blocks.json`, renumbers only
    the selected chunk, leaves inserted blocks unapproved, resets downstream
    Audio Blocks plus Audio Assembly, and rolls the manifest back until review
    is complete again.
11. Re-splitting one chunk replaces only that chunk's Speech Blocks, rebuilds
    that chunk's local sequence indexes and block IDs, marks new blocks
    unapproved, rolls Speech Blocks back from complete, and asks Audio Blocks to
    delete/remap only the affected downstream records.

## 4. Dependencies

- Internal dependencies:
  `04_Software/AudioMancer/src/audiomancer/config.py`
  `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_service.py`
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
- selected voice language from `project.json`
- canonical chunking output in `chunks_text.json`
- approved translated chunks and `translation_report.json` when the selected
  voice language is translated
- discovered character profiles from `characters_profile.json`
- selected enabled AI profile from `settings.json`
- prompt templates:
  `04_Software/AudioMancer/prompts/speech_blocks_system.txt`
  `04_Software/AudioMancer/prompts/speech_blocks_user.txt`

Outputs:

- `speech_blocks.json`
- `speech_blocks_report.json`
- `speech_blocks_state.json`
- `log_ai_speech_blocks_<timestamp>.log`
- updated manifest summary for `operations["speech_blocks"]`
- updated manifest stage `speech_blocks_ready` only after approval is complete

## 6. Data Contracts

Persisted speech-block payloads use:

- `speech_block_id`
- `sequence_index`
- `chunk_id`
- `source_language`
- `speaker_kind`
- `speaker_id`
- `speaker_display_name`
- `content_kind`
- `text`
- `ai_speaker_kind`
- `ai_speaker_id`
- `ai_speaker_display_name`
- `ai_content_kind`
- `ai_text`
- `warning_flags`
- `approved`
- `approved_at`

Current invariants:

- one AI request is issued per source chunk
- `sequence_index` is 1-based and local within the source chunk
- `speech_block_id` is always `CCCC-BBBBBB`
- `CCCC` is derived from the numeric chunk id
- `BBBBBB` is the chunk-local `sequence_index`
- canonical book order is source chunk order, then chunk-local
  `sequence_index`
- `speaker_id` must be `narrator` or one discovered `character_id`
- for metadata-only operation kinds, `speaker_kind` is `operation`,
  `speaker_id` is the content-kind token, and `speaker_display_name` is the
  operation name shown in the Speech Blocks list
- unrecognized or ambiguous speakers fall back to narrator and add
  `ambiguous_speaker`
- narration text is stored unchanged
- dialogue text strips only one outer pair of straight double quotes when both
  ends are quotes
- `background_noise`, `pause`, and `indication` are metadata-only content kinds
  for Audio Blocks
- pause text may include a millisecond duration; when no valid duration exists,
  downstream audio composition uses `1000 ms`
- block ordering never crosses chunk boundaries
- manual insert creates an unapproved narrator narration block with empty text
- manual delete removes only the selected block and leaves the source chunk in
  the chunk list even when no Speech Blocks remain for that chunk
- warning flags are cleared when the operator starts editing a block
- resetting one edited block restores only the AI baseline speaker, content
  kind, and text while preserving the current warning-cleared state
- generation creates unapproved blocks
- Speech Blocks is complete only when every block is approved

Report and operation-state metadata include:

- `source_language`
- `source_kind`
- `ai_profile_id`
- `processed_chunk_count`
- `total_chunk_count`
- `speech_block_count`
- `approved_block_count`
- `total_block_count`
- `warning_count`
- `warnings`
- normalized `token_usage`
- one resume checkpoint with `next_chunk_index`,
  `source_snapshot_fingerprint`, `source_language`, and `ai_profile_id`

## 7. Workflow Integration

This workflow sits immediately after `Character Voices`.

Upstream integrations:

- canonical chunk output from `chunks_text.json`
- approved translation output from `translated_text.json` when the selected voice
  language is translated
- discovered character speaker catalog from `characters_profile.json`
- selected project voice language from `project.json`

Downstream integrations:

- `project.json.current_stage = "speech_blocks_ready"` only after every Speech
  Block is approved
- `Audio Blocks` consumes speech blocks and skips VoiceWeaver for metadata-only
  blocks
- `Reset Speech Blocks` clears speech-block, audio-block, and audio-assembly
  runtime artifacts
- selected-block edits invalidate affected downstream Audio Blocks data
- selected-chunk re-splitting asks Audio Blocks to delete audio for the
  re-split chunk, preserve earlier chunk audio, remap later records to rebuilt
  IDs, rename order-based artifacts when needed, and rebuild report/state
- Narator Voice language changes invalidate speech-block, audio-block, and
  audio-assembly runtime artifacts

Runtime gating:

- one project must be open
- chunking output must exist
- the selected project voice language must resolve to either the original language or
  a fully approved translation target
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

report = speech_blocks_service.approve_all_speech_blocks(project_root)

report = speech_blocks_service.approve_speech_block(
    project_root,
    speech_block_id,
)

report = speech_blocks_service.update_speech_block(
    project_root,
    speech_block_id,
    speaker_id,
    content_kind,
    text,
)

report = speech_blocks_service.reset_speech_block_to_ai_baseline(
    project_root,
    speech_block_id,
)

report = speech_blocks_service.regenerate_chunk_speech_blocks(
    project_root,
    manifest,
    chunk_id,
    selected_profile_payload,
    progress_callback=progress_callback,
    cancel_requested=cancel_requested,
)
```

Operator path:

- open one project that has completed `Character Voices`
- choose the desired source language on the `Narator Voice` page
- open `Speech Blocks`
- select the AI profile
- press `Generate Speech Blocks`
- confirm the generation popup
- inspect chunks in the top list
- inspect or edit selected Speech Blocks in the lower-right editor
- press `Save` after block edits
- press `Reset` to restore a block to the AI baseline values
- press `Approve` to approve only the selected Speech Block
- after selected-block approval, the page advances the visible Speech Blocks
  list to the next row when one exists and keeps the final row selected at the
  end
- press `Re-Split Selected Chunk` when only the selected chunk needs a new AI
  split
- press `Approve All Speech Blocks` after review
- if interrupted, start generation again to continue from the saved checkpoint

## 9. Validation And Tests

Focused automated coverage exists in:

- `04_Software/AudioMancer/tests/test_speech_blocks_service.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_state_service.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_page.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_ui_controller.py`
- related invalidation, Audio Blocks, and repair coverage in
  `test_audio_blocks_service.py`, `test_audio_blocks_state_service.py`,
  `test_audio_blocks_page.py`, `test_audio_blocks_ui_controller.py`,
  `test_audio_blocks_main_window.py`,
  `test_audio_blocks_upstream_invalidation.py`,
  `test_character_voices_ui_controller.py`, and
  `test_project_workspace_service.py`

Minimum validation after a change:

```powershell
uv run python -m py_compile <changed_python_files>
uv run pytest tests/test_speech_blocks_service.py
uv run pytest tests/test_speech_blocks_state_service.py
uv run pytest tests/test_speech_blocks_page.py
uv run pytest tests/test_speech_blocks_ui_controller.py
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

- contiguous source coverage is delegated to the model output plus narrator
  fallback; the service does not currently verify exact span coverage against
  the source chunk
- speaker attribution uses only the discovered-character catalog plus narrator
- prosody and detailed delivery hints are not stored
- `Pause` and `Background Noise` are metadata-only placeholders until
  downstream audio assembly defines how to represent them in final output
- `Audio Assembly` remains the next downstream placeholder stage
