<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Audio Assembly Service

## 1. Purpose

Implements the final `Audio Assembly` workflow in `AudioMancer`.

It consumes approved generated `Audio Blocks` and composes local WAV audiobook
deliverables under the project-root `audiobook/` folder.

## 2. Responsibilities

- persist per-project Audio Assembly options in `project.json`
- validate that all Audio Blocks are approved and reference compatible WAV files
- compose output files for per-chunk, time-limited, or whole-book delivery
- add configurable silence gaps between blocks and between chunks or output files
- convert metadata-only pause Audio Blocks into silence inside the composed WAV
  output
- write output files through temporary paths before publishing final WAV files
- persist resumable composition state in `audio_assembly_state.json`
- persist generated-output metadata in `audio_assembly_report.json`
- support completed-output resume when inputs and settings still match
- reset generated audiobook files, report data, and operation state
- build page state, status notes, progress values, and generated-output records
  for the `Audio Assembly` page
- coordinate confirmation popups, modal progress, playback, and manifest
  synchronization through the page controller

It does not regenerate TTS, approve Audio Blocks, encode MP3, trim silence,
normalize volume, edit pitch, write chapter metadata, or embed cover art.

## 3. Implementation Overview

The workflow is split across:

- `04_Software/AudioMancer/src/audiomancer/services/audio_assembly_service.py`
  for settings normalization, WAV validation, composition, resumable state,
  report persistence, output inspection, and reset behavior
- `04_Software/AudioMancer/src/audiomancer/services/audio_assembly_state_service.py`
  for page-state shaping, notes, status lines, progress, and readiness checks
- `04_Software/AudioMancer/src/audiomancer/ui/pages/audio_assembly_page.py`
  for the operator-facing settings, generated-output list, progress bar,
  status panel, and playback controls
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/audio_assembly_ui_controller.py`
  for settings persistence, long-running confirmation, threaded composition,
  generated-output playback, reset handling, and manifest synchronization

High-level flow:

1. The page emits the selected settings when the operator changes output mode,
   duration limit, output format, or silence-gap controls.
2. The controller persists normalized settings under
   `project.json.audio_assembly_settings`.
3. Pressing `Generate Audio` shows a long-operation confirmation and starts the
   shared threaded operation runner with operation kind `audio_assembly`.
4. `audio_assembly_service.start_or_continue_composition(...)` loads approved
   Audio Blocks, validates that generated WAV files exist for playable blocks,
   checks that WAV parameters are compatible, preserves metadata-only pause
   blocks as silence, and builds an input/settings fingerprint.
5. If existing operation state belongs to different inputs or settings, the
   service rejects continuation and requires an explicit reset.
6. The service builds an output plan according to the selected mode and skips
   already completed output records when the fingerprint still matches.
7. Each output file is written as `<final_name>.tmp`, then renamed to the final
   `.wav` path after the file is complete.
8. The service updates `audio_assembly_report.json` and
   `audio_assembly_state.json` after each completed output file.
9. The controller refreshes `project.json.operations["audio_assembly"]` and
   advances `project.json.current_stage` to `audio_assembly_ready` when the
   report status is completed.

## 4. Dependencies

- Internal dependencies:
  `04_Software/AudioMancer/src/audiomancer/config.py`
  `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/operation_runtime_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/text_cleanup_state_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
  `04_Software/AudioMancer/src/audiomancer/ui/controllers/operation_runner_controller.py`
  `04_Software/AudioMancer/src/audiomancer/ui/controllers/audio_blocks_ui_controller.py`
  `04_Software/AudioMancer/src/audiomancer/ui/main_window.py`
- External dependencies:
  Python standard library `wave`, `json`, `hashlib`, `datetime`, and
  `pathlib`; `PySide6` for the UI page, modal messages, and local playback

No external encoder or signal-processing dependency is used.

## 5. Inputs And Outputs

Inputs:

- active project root and manifest
- `project.json.audio_assembly_settings`
- approved generated Audio Blocks from `audio_blocks.json`, including
  metadata-only pause blocks
- generated source WAV paths under `audio_blocks/`

Outputs:

- generated audiobook WAV files under `audiobook/`
- `audio_assembly_report.json`
- `audio_assembly_state.json`
- updated compact manifest summary for `operations["audio_assembly"]`
- updated manifest stage `audio_assembly_ready` after completed composition

## 6. Data Contracts

Persisted settings in `project.json.audio_assembly_settings`:

- `output_mode`: `per_chunk`, `time_limit`, or `whole_book`
- `max_duration_minutes`: integer, default `30`
- `output_format`: currently locked to `wav`
- `inter_block_silence_ms`: integer, default `250`
- `inter_chunk_silence_ms`: integer, default `1000`

Output modes:

- `per_chunk` writes one `chunk-000N.wav` file per source chunk
- `time_limit` writes sequential `part-000N.wav` files and places a block that
  exceeds the duration limit alone in its own part with a warning
- `whole_book` writes one `audiobook.wav` file

Persisted output records include:

- `output_key`
- `file_name`
- `audio_relative_path`
- `block_count`
- `chunk_ids`
- `duration_seconds`
- `generated`
- `generated_at`
- `output_format`

Current invariants:

- Audio Assembly uses approved, generated Audio Blocks only
- metadata-only pause Audio Blocks are included as silence using
  `pause_duration_ms`, or `1000 ms` when no valid duration exists
- an explicit pause block replaces adjacent automatic inter-block silence for
  that pause position, so the pause duration is not double-counted
- metadata-only indication and background-noise Audio Blocks are skipped by the
  current composer
- approved Audio Blocks are assembled in canonical book order: source chunk
  order, then chunk-local `sequence_index`
- all source WAV files in a run must share compatible channel count, sample
  width, frame rate, compression type, and compression name
- persisted resume requires the current input/settings fingerprint to match the
  fingerprint stored in `audio_assembly_state.json`
- mismatched fingerprints require explicit reset

## 7. Workflow Integration

This workflow sits immediately after `Audio Blocks`.

Upstream integrations:

- approved generated Audio Blocks from `audio_blocks.json`
- source WAV files under `audio_blocks/`

Downstream integrations:

- generated audiobook deliverables under `audiobook/`
- workflow completion state in `project.json.current_stage`
- Home-page workflow progress through compact manifest operation summaries

Current invalidation points:

- Audio Blocks reset or regeneration clears Audio Assembly state, report, and
  generated audiobook files
- settings or input changes detected at composition time require reset before
  continuation

## 8. Usage

Representative service calls:

```python
manifest = audio_assembly_service.save_audio_assembly_settings(
    project_root,
    manifest,
    {
        "output_mode": "time_limit",
        "max_duration_minutes": 30,
        "output_format": "wav",
        "inter_block_silence_ms": 250,
        "inter_chunk_silence_ms": 1000,
    },
)

report = audio_assembly_service.start_or_continue_composition(
    project_root,
    manifest,
    progress_callback=progress_callback,
    cancel_requested=cancel_requested,
)
```

Operator path:

- complete and approve all generated Audio Blocks
- open `Audio Assembly`
- choose `Per text chunk`, `Time limit`, or `Whole audiobook`
- adjust duration and silence-gap settings as needed
- press `Generate Audio` and confirm the long-running operation
- if interrupted, press `Generate Audio` again to continue completed-output
  resume when the inputs and settings still match
- select a generated output and use `Play Audio` or `Stop Playing` for preview

## 9. Validation And Tests

Focused automated coverage exists in:

- `04_Software/AudioMancer/tests/test_audio_assembly_service.py`
- `04_Software/AudioMancer/tests/test_audio_assembly_page.py`
- `04_Software/AudioMancer/tests/test_audio_assembly_ui_controller.py`
- adjacent manifest coverage in
  `04_Software/AudioMancer/tests/test_project_workspace_service.py`

Minimum validation after a change:

```powershell
uv run python -m py_compile <changed_python_files>
uv run pytest tests/test_audio_assembly_service.py
uv run pytest tests/test_audio_assembly_page.py
uv run pytest tests/test_audio_assembly_ui_controller.py
uv run pytest tests/test_project_workspace_service.py
uv run ruff check <changed_python_files> --fix
uv run ruff format <changed_python_files>
```

## 10. Limitations And Future Work

- WAV is the only supported output format in this implementation
- MP3 or other compressed outputs require an encoder dependency decision
- whole-book cancellation preserves operation state but does not append into a
  partially written single WAV; the whole-book output is published only after a
  complete final write
- silence trimming, volume normalization, pitch changes, chapter metadata, and
  cover-art embedding are intentionally deferred
- the page lists generated outputs, but it does not provide waveform editing or
  per-output metadata editing
