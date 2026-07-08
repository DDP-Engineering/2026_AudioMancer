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

- persist per-project Audio Assembly options in `project.json` and reset only
  assembly outputs when changed settings make existing outputs stale
- validate that all Audio Blocks are approved and reference readable PCM WAV files
- compose output files for per-chunk, time-limited, or whole-book delivery
- optionally include or skip generated `scene_ambience` audio blocks in the
  final assembly
- group related generated `scene_ambience` prompt WAVs and mix them into one
  Scene Mix preview or final ambience segment
- generate on-demand Scene Mix preview WAV files for operator review before
  final assembly
- run on-demand Scene Mix preview generation through the shared modal progress
  workflow with cancellation support
- add configurable silence gaps between blocks and between chunks or output files
- convert metadata-only pause Audio Blocks into silence inside the composed WAV
  output
- write output files through temporary paths before publishing final WAV files
- persist resumable composition state in `audio_assembly_state.json` atomically
- persist generated-output metadata in `audio_assembly_report.json` atomically
- support completed-output resume when inputs and settings still match
- reset generated audiobook files, report data, and operation state
- build page state, status notes, progress values, and generated-output records
  for the `Audio Assembly` page
- coordinate confirmation popups, settings-change reset confirmation, modal
  progress, generated-output playback, double-click restart, seek controls, and
  manifest synchronization through the page controller

It does not regenerate TTS, approve Audio Blocks, encode MP3, trim silence,
normalize volume, edit pitch, write chapter metadata, or embed cover art.

## 3. Implementation Overview

The workflow is split across:

- `04_Software/AudioMancer/src/audiomancer/services/audio_assembly_service.py`
  for settings normalization, WAV validation, Scene Ambience mix grouping,
  Scene Mix preview generation, composition, resumable state, report
  persistence, output inspection, and reset behavior
- `04_Software/AudioMancer/src/audiomancer/services/audio_assembly_state_service.py`
  for page-state shaping, notes, status lines, progress, and readiness checks
- `04_Software/AudioMancer/src/audiomancer/ui/pages/audio_assembly_page.py`
  for the operator-facing settings, Scene Mix preview list, generated-output
  list, operation progress bar, playback position slider, status panel, and
  playback controls
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/audio_assembly_ui_controller.py`
  for settings persistence, long-running confirmation, threaded composition,
  threaded Scene Mix preview generation, generated-output playback,
  double-click restart, seek/skip handling, reset handling, and manifest
  synchronization

High-level flow:

1. The page emits the selected settings when the operator changes output mode,
   duration limit, output format, silence-gap controls, or the Scene Ambience
   inclusion option.
2. The controller persists normalized settings under
   `project.json.audio_assembly_settings`. If generated assembly output already
   exists and the normalized settings changed, the controller asks for
   confirmation and resets only `audiobook/`, `audio_assembly_report.json`, and
   `audio_assembly_state.json`.
3. Pressing `Generate Audio` shows a long-operation confirmation and starts the
   shared threaded operation runner with operation kind `audio_assembly`.
4. `audio_assembly_service.start_or_continue_composition(...)` loads approved
   Audio Blocks, applies the Scene Ambience inclusion policy, validates that
   generated WAV files exist for playable blocks, verifies readable PCM WAV
   sources, replaces related Scene Ambience prompt blocks with grouped mix
   segments, preserves metadata-only pause blocks as silence, and builds an
   input/settings fingerprint.
5. If existing operation state belongs to different inputs or settings, the
   service rejects continuation and requires an explicit reset.
6. The service builds an output plan according to the selected mode and skips
   already completed output records when the fingerprint still matches.
7. Each output file is written as `<final_name>.tmp`, then renamed to the final
   `.wav` path after the file is complete.
8. The service atomically updates `audio_assembly_report.json` and
   `audio_assembly_state.json` after each completed output file.
9. The controller refreshes `project.json.operations["audio_assembly"]` and
   advances `project.json.current_stage` to `audio_assembly_ready` when the
   report status is completed.
10. Reset and settings-change paths set only the compact
    `operations["audio_assembly"]` summary back to `not_started`, lowering the
    stage no further than `audio_blocks_ready`.

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
- `include_scene_ambience`: boolean, default `true`; when `false`, generated
  `scene_ambience` WAV blocks are skipped during composition

Scene Mix preview records are derived from the current Audio Blocks payload and
are not persisted in `audio_assembly_report.json`. Preview WAV files are written
under `audiobook/scene_mix_previews/` with deterministic names based on group
identity and source fingerprints. Audio Assembly reset deletes those preview
files together with final audiobook outputs.

Output modes:

- `per_chunk` writes one `chunk-000N.wav` file per source chunk
- `time_limit` writes sequential `part-000N.wav` files, accounts for automatic
  inter-block and inter-chunk silence while packing parts, and places a block
  that exceeds the duration limit alone in its own part with a warning
- `whole_book` writes one `audiobook.wav` file

Persisted output records include:

- `output_key`
- `file_name`
- `audio_relative_path`
- `block_count`
- `chunk_ids`
- `duration_seconds`
- `generated`
- `output_format`

Audio Assembly report and state payloads do not persist operation audit
timestamps. Output paths remain domain data because the generated audiobook
files are not fixed to a single canonical artifact name.
Malformed or truncated operation state loads as no usable state through the
shared operation runtime loader, logs a warning, and requires the normal
fingerprint/reset path rather than crashing the page.

Current invariants:

- Audio Assembly uses approved, generated Audio Blocks only
- metadata-only pause Audio Blocks are included as silence using
  the current `pause_duration_ms` field, or `1000 ms` when that field is
  missing or invalid; pause text is not parsed as a compatibility fallback
- generated `scene_ambience` Audio Blocks are grouped by `chunk_id`,
  `ambience_position`, and `after_speech_block_id`, then mixed into one
  composition segment per group when `include_scene_ambience` is enabled; when
  disabled, they are ignored for readiness counts, WAV validation, output
  planning, and final composition
- Scene Mix previews use the same mixing helper as final Audio Assembly, so the
  reviewed preview matches the segment inserted into final outputs
- Scene Mix preview generation runs as a cancellable threaded operation and
  reports progress while preparing, mixing, and refreshing the preview list
- an explicit pause block replaces adjacent automatic inter-block silence for
  that pause position, so the pause duration is not double-counted
- metadata-only indication Audio Blocks are skipped by the current composer
- time-limited planning uses the same automatic silence-gap rules as WAV
  composition, so published part durations do not exceed the configured limit
  except when one individual block is already longer than the limit
- approved Audio Blocks are assembled in canonical book order: source chunk
  order, then chunk-local `sequence_index`
- source WAV files must be readable uncompressed PCM; final composition chooses
  reference WAV parameters from the first non-Scene-Ambience source WAV when one
  exists, then converts mono/stereo and sample-rate differences while writing
- persisted resume requires non-default state to contain the current
  input/settings fingerprint in `audio_assembly_state.json`
- missing or mismatched fingerprints require explicit reset
- reset, settings-change reset, and upstream Audio Blocks impact delete only
  assembly state, report, and generated audiobook output files; approved Audio
  Blocks and voice data remain untouched

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
- Audio Blocks approval/unapproval clears Audio Assembly only, because assembly
  eligibility changed while generated Audio Blocks remain valid
- Audio Assembly settings changes are confirmed in the controller and clear
  only Audio Assembly outputs/state/report
- settings or input changes detected at composition time still require reset
  before continuation when stale state reaches the service directly

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
        "include_scene_ambience": True,
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
- adjust duration and silence-gap settings as needed; changing settings after
  output exists asks for confirmation and resets only the existing Audio
  Assembly output
- choose whether generated Scene Ambience sound blocks should be included in
  the final sequential audiobook output
- for each ready Scene Mix preview row, use `Generate / Refresh Scene Mix` to
  build the mixed ambience preview through the modal progress dialog, then use
  `Play Scene Mix` to review it with the Audio Assembly media controls
- press `Generate Audio` and confirm the long-running operation
- if interrupted, press `Generate Audio` again to continue completed-output
  resume when the inputs and settings still match
- select a generated output and use `Play Audio` or `Stop Playing` for preview
- double-click a generated output to stop any active Audio Assembly playback and
  restart the clicked file from the beginning
- use the playback progress slider to drag to a specific position, or the
  `-10s` and `+10s` buttons for quick review jumps

## 9. Validation And Tests

Focused automated coverage exists in:

- `04_Software/AudioMancer/tests/test_audio_assembly_service.py`
- `04_Software/AudioMancer/tests/test_audio_assembly_state_service.py`
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
- the page lists generated outputs and supports position seeking, but it does
  not provide waveform editing or per-output metadata editing
