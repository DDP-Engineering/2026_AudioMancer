<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Audio Blocks State Service

## 1. Purpose

Builds the page-state payload consumed by the `Audio Blocks` review page.

It translates persisted Speech Blocks, generated Audio Blocks, reports,
operation state, selected voice language, and TTS budget data into one
approval-aware UI model.

## 2. Responsibilities

- load and merge Speech Blocks with persisted Audio Blocks without opening
  every generated WAV during page refresh
- resolve the selected/current block and full source-text preview
- build localized notes, status lines, progress values, and button enablement,
  including disabling start/continue only when all current approved Speech
  Blocks already have generated audio
- expose generated/approved counts and resumable operation metadata
- surface selected text character limits from cached VoiceWeaver budget data
- expose whether Scene Ambience audio generation is enabled so the page can
  treat `scene_ambience` rows as generated sound targets or metadata-only
  placeholders

It does not generate audio, mutate approvals, delete artifacts, or synchronize
`project.json`; those behaviors stay in `audio_blocks_service.py` and
`audio_blocks_ui_controller.py`.

## 3. Implementation Overview

Implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_state_service.py`

Main entrypoints:

- `build_audio_blocks_state(...)`
- `build_audio_blocks_notes(...)`

The service loads current artifacts, merges block state by
`speech_block_id`, computes progress and readiness, resolves the current block
from operation state, and returns a dictionary consumed directly by
`AudioBlocksPage.set_audio_blocks_state(...)`.

Start/continue readiness is based on remaining approved source work, not only
on whether approved Speech Blocks exist or whether an older report was marked
completed. If Speech Blocks are inserted or affected Audio Blocks are removed
after a completed run, `can_start_or_continue` becomes true again only for the
current approved Speech Blocks that still lack generated audio.

## 4. Dependencies

Internal dependencies:

- `audio_blocks_service`
- `speech_blocks_service`
- `character_voices_service`
- `narrator_definition_service`
- `tts_budget_service`
- `ui_state_service`
- `home_presenter_service`

External dependencies:

- Python standard library `pathlib`

## 5. Inputs And Outputs

Inputs:

- active project root
- active manifest
- runtime UI language
- optional settings payload with cached VoiceWeaver model metadata

Outputs:

- one page-state dictionary containing source text, block rows, notes, status
  lines, progress, current phase, approval flags, reset flags, and selected
  text character budget

## 6. Data Contracts

The page-state payload includes stable keys such as:

- `full_source_text`
- `speech_blocks`
- `current_block_id`
- `notes`
- `status_lines`
- `progress_current`
- `progress_total`
- `stage_status`
- `can_start_or_continue`
- `can_approve_all`
- `can_approve_selected`
- `selected_text_character_limit`
- `scene_ambience_audio_enabled`

Merged block rows preserve generated-audio fields from `audio_blocks.json` and
derive review/source fields from `speech_blocks.json`. The page uses persisted
`audio_duration_seconds` and does not open WAV files during normal state
loading.

Scene Ambience rows are metadata-only only when Scene Ambience audio generation
is disabled. When enabled, approved `scene_ambience` Speech Blocks participate
in generated/approved counts like other Audio Blocks, while still using their
prompt, negative prompt, and per-block duration instead of spoken text.

## 7. Workflow Integration

Upstream:

- `MainWindow.show_project_state(...)`
- `audio_blocks_ui_controller` refresh paths

Downstream:

- `AudioBlocksPage`
- Home workflow progress through controller-driven manifest synchronization

## 8. Usage

Representative page refresh:

```python
state = audio_blocks_state_service.build_audio_blocks_state(
    project_root,
    manifest,
    language,
    settings_payload,
)
window._audio_blocks_page.set_audio_blocks_state(**state)
```

## 9. Validation And Tests

Focused tests:

- `tests/test_audio_blocks_state_service.py`
- `tests/test_audio_blocks_page.py`
- `tests/test_audio_blocks_ui_controller.py`

Minimum validation after changes:

- `uv run python -m py_compile src/audiomancer/services/audio_blocks_state_service.py`
- `uv run pytest tests/test_audio_blocks_state_service.py`

## 10. Limitations And Future Work

- the service intentionally mirrors the current dictionary-based page contract
  rather than introducing a separate dataclass model
- Audio Blocks row labels intentionally do not compute every generated WAV
  duration during page refresh; this keeps large projects responsive when the
  operator opens the page
