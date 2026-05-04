<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Speech Blocks State Service

## 1. Purpose

`speech_blocks_state_service.py` builds the state payload consumed by the
`Speech Blocks` page. It keeps UI state assembly separate from Speech Blocks
generation, manual block editing, and Audio Blocks generation.

## 2. Responsibilities

- build the enabled AI-profile selector state for Speech Blocks
- load persisted Speech Blocks output, report, and operation state
- resolve the active source chunks from canonical chunking or approved
  translation output
- build operator notes, including token-usage summaries and resumable-state
  warnings
- provide speaker catalog and content-kind selector values for the page
- merge selected-audio preview flags from `audio_blocks.json` so the Speech
  Blocks page can enable per-block `Generate Audio` and `Play`/`Stop`
  shortcuts

It does not:

- generate, edit, approve, or reset Speech Blocks
- generate audio or mutate Audio Blocks artifacts
- own confirmation dialogs or manifest synchronization

## 3. Implementation Overview

The component lives in
`04_Software/AudioMancer/src/audiomancer/services/speech_blocks_state_service.py`.

Main entrypoints:

- `build_speech_blocks_profile_state(...)`
- `build_speech_blocks_state(...)`
- `build_speech_blocks_notes(...)`

`build_speech_blocks_state(...)` loads Speech Blocks artifacts, enriches each
block with audio preview flags, resolves source chunks when prerequisites are
available, and returns one dictionary passed directly to
`SpeechBlocksPage.set_speech_blocks_state(...)`.

The selected-audio merge is read-only. It matches Audio Blocks by stable
`speech_block_id`, checks the generated file path from `audio_relative_path`,
and marks metadata-only content kinds so the Speech Blocks page does not expose
audio generation for pause, indication, or background-noise rows.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config`
- `audiomancer.services.speech_blocks_service`
- `audiomancer.services.audio_blocks_service`
- `audiomancer.services.deterministic_chunking_service`
- `audiomancer.services.ai_translation_service`
- `audiomancer.services.character_voices_service`
- `audiomancer.services.narrator_definition_service`
- `audiomancer.services.home_presenter_service`
- `audiomancer.services.ai_state_note_service`
- `audiomancer.services.ui_state_service`

External dependencies:

- Python `pathlib.Path`

## 5. Inputs And Outputs

Inputs:

- active `project_root`
- active `project.json` manifest payload
- runtime UI language code
- persisted application settings payload with enabled AI profiles
- root-level workflow artifacts such as `chunks_text.json`,
  `translated_text.json`, `speech_blocks.json`, `speech_blocks_report.json`,
  `speech_blocks_state.json`, and `audio_blocks.json`

Outputs:

- dictionaries consumed by `SpeechBlocksPage`
- localized operator notes
- selector entries for AI profile, speaker, and content kind
- read-only per-block flags:
  `audio_generated`, `audio_approved`, `audio_metadata_only`, and
  `audio_can_play`

## 6. Data Contracts

`build_speech_blocks_state(...)` returns keys matching
`SpeechBlocksPage.set_speech_blocks_state(...)`, including:

- `source_chunks`
- `speech_blocks`
- `notes`
- `selected_profile_id`
- `stage_status`
- `selected_source_language`
- `processed_chunk_count`
- `total_chunk_count`
- `approved_block_count`
- `total_block_count`
- `voice_assignment_mode`
- `speaker_catalog`
- `content_kind_options`
- `can_reset`
- `can_approve_all`
- `can_resplit_selected`

Audio preview fields are derived without changing persisted Speech Blocks:

- `audio_generated` is true when the matching Audio Block is marked generated
- `audio_approved` mirrors the matching Audio Block approval flag
- `audio_metadata_only` is true for Audio Blocks metadata-only rows or Speech
  Block content kinds `background_noise`, `pause`, and `indication`
- `audio_can_play` is true only when the matching Audio Block is generated and
  its `audio_relative_path` points to an existing project-local file

## 7. Workflow Integration

The service is called by `MainWindow._refresh_speech_blocks_page_state(...)`
when the `Speech Blocks` page is active. Its output lets the page show current
Speech Blocks review state and expose selected audio preview controls without
making the page a separate audio workflow.

Downstream actions remain delegated:

- `SpeechBlocksPage.generate_audio_selected_requested` is wired to
  `audio_blocks_ui_controller.handle_regenerate_selected_requested(...)`
- `SpeechBlocksPage.selected_audio_playback_toggle_requested` is wired to
  `audio_blocks_ui_controller.handle_selected_playback_toggle_requested(...)`

## 8. Usage

Typical call from the main window:

```python
speech_blocks_state = speech_blocks_state_service.build_speech_blocks_state(
    project_root,
    manifest,
    current_language,
    settings_payload,
)
speech_blocks_page.set_speech_blocks_state(**speech_blocks_state)
```

## 9. Validation And Tests

Focused automated coverage:

- `04_Software/AudioMancer/tests/test_speech_blocks_state_service.py`
- selected UI behavior in
  `04_Software/AudioMancer/tests/test_speech_blocks_page.py`
- controller wiring behavior in
  `04_Software/AudioMancer/tests/test_audio_blocks_ui_controller.py`

Minimum validation after changing this component:

```powershell
uv run python -m py_compile src/audiomancer/services/speech_blocks_state_service.py
uv run ruff check src/audiomancer/services/speech_blocks_state_service.py --fix
uv run ruff format src/audiomancer/services/speech_blocks_state_service.py
uv run pytest tests/test_speech_blocks_state_service.py
uv run pytest tests/test_speech_blocks_page.py
```

## 10. Limitations And Future Work

- The service only reports whether an audio file exists; it does not inspect WAV
  validity or duration.
- Audio preview state is refreshed when the page state is rebuilt, not through a
  file watcher.
- Metadata-only handling is intentionally aligned with current Audio Blocks
  behavior and should be updated if richer sound-design blocks are introduced.
