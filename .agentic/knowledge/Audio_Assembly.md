<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Audio Assembly

## Routing

For final audiobook WAVs, output modes, pauses, Scene Mix or assembly resume,
start in `audio_assembly_service.py` and `test_audio_assembly_service.py`.
Speech generation belongs to TTS Audio Blocks.

## Purpose and boundaries

Validates and composes ordered generated audio blocks into project-local final audiobook WAV outputs.

- Validate generated block artifacts, settings and ordering; compose resumable outputs and ambience mixes.
- Persist assembly state, reports, output metadata and project-local paths safely.
- Project assembly readiness/output state and expose generate, selection and playback actions through UI.
- It does not generate TTS blocks or alter their speech content.

The assembly service validates inputs, resolves Scene Mix groups and persists resume state. The plan module groups ordered blocks into outputs. The WAV module streams PCM and publishes candidates. Final composition and planned virtual Scene Mix preflight share one WAV-parameter selector with an explicit block-path resolver, preserving speech preference, fallback paths, and runtime monkeypatch seams. State service derives readiness and saved-output projections. The controller delegates long work through the shared runner; the page presents output/mix selection, settings, progress and playback.

Refreshing the page is the component's hot path, so its cost is bounded on
purpose. `build_audio_assembly_state()` loads the Audio Blocks document once
and hands those blocks to `list_scene_mix_groups()`, whose `audio_blocks`
argument exists for exactly that (`REQ-NFR-01d90032`); omitting the argument
still loads, for callers that hold nothing. The numeric Output Settings
controls do not track keystrokes, so an edit is reported once its value
settles rather than once per digit, and Generate Audio interprets a
still-being-typed value before reading the payload (`REQ-UX-4cf55346`). A
settings save that discards no output refreshes the page through
`MainWindow.refresh_audio_assembly_page_state()` instead of the app-wide
`show_project_state()`, which would also reread every Home export artifact
(`REQ-NFR-aed66768`).

### Dependencies

- Internal: TTS Audio Blocks artifacts, Speech Blocks ordering/ambience metadata, operation runtime/persistence/project workspace, PCM Codec for sample-width/channel/rate conversion, shared runner and Qt playback widgets.
- External: Python `wave` container handling and local generated WAV artifacts. PCM sample conversion is provided by the internal codec.

## Public interface

Call `start_or_continue_composition` to assemble and `list_scene_mix_groups`
or `generate_scene_mix_preview` for preview work. The state service uses the
same report and group records.

- Inputs: approved ordered generated WAVs, assembly settings, project root, selected output/mix and cancellation request.
- Outputs: composed WAV deliverables, scene-ambience mixes, state/report/
  metadata and UI-ready output summaries. Settings support per-chunk,
  time-limited, or whole-book WAV delivery and can include or skip generated
  scene ambience.

## Invariants

- `default_audio_assembly_settings()` and
  `normalize_audio_assembly_settings()` are the public domain-owned settings
  contract used by Audio Assembly and every project-manifest build, validation,
  save/load, and repair path; local workspace imports avoid the reverse-service
  import cycle (`REQ-FUNC-4cc6cf8c`).
- Outputs and referenced inputs remain project-relative and ordered by block identity; state records completed outputs, durations and resumable progress.
- Every newly persisted report records one UTC ISO `started_at` for the logical
  run and a nullable `completed_at`; compact state carries the same start as
  `resume_checkpoint.run_token`. Cancelled resumes and already-completed
  re-entry preserve their original lifecycle values, while legacy report/state
  payloads without the added fields remain loadable and receive a fresh token
  only when continued (`REQ-DATA-94132a27`, `REQ-REL-3ccdf599`).
- Assembly validates readable compatible WAVs and preserves previously completed work when a later operation cannot complete.
- Final-composition preflight validates every included non-pause source as a
  safe existing complete supported-PCM WAV and reports its block ID, including defensive support
  for legacy path-carrying metadata-only Scene Ambience rows. Synthesized pauses
  require no source. Preflight checks PCM layout within each Scene Mix and
  supported channel conversion for each planned output. Disabled ambience stays outside validation and
  composition (`REQ-FUNC-7c32fd5e`).
- Accepted PCM sample widths are 2, 3 and 4 bytes. One-byte PCM is rejected on
  purpose: WAV stores 8-bit samples unsigned while this component and PCM Codec
  read every width as signed, so gap and pause silence would be written as a
  negative-rail DC offset instead of quiet. Re-admitting 8-bit requires an
  unsigned zero level of 0x80 in the silence writer and unsigned handling in PCM
  Codec, whose current signed behavior is deliberate `audioop` compatibility.
- Scene-ambience blocks group by chunk/position/anchor and share the same mixing
  helper and target duration for preview and final composition. A generated
  cue whose WAV is missing is reported during final preflight when included.
  Only a real generated ambience WAV carries the `audio_relative_path` that admits it to a scene group;
  metadata-only ambience rows remain pathless and are not mixed
  (`REQ-FUNC-ee6222b7`). Resume matches the current fingerprint against both
  the saved report and state, then reuses only complete PCM WAVs for the
  canonical planned files with the recorded duration. A different persisted
  input/settings fingerprint requires explicit reset. Candidate WAVs replace
  published files after a successful close and cancellation check. Each render owns its temporary file. Before
  running-state persistence or output work, each pending file is sized from
  integer PCM frames against stdlib `wave`'s exact classic RIFF payload maximum;
  only the individual overflowing file is rejected, with Per text chunk or Time
  limit guidance (`REQ-REL-607c7bfb`). Failed final-output writes and closes
  remove their temp file without replacing an existing published output
  (`REQ-REL-f3f965de`).
- Scene Mix preview identity still includes each source WAV content digest, but
  full-file hashing uses a process-local 256-entry thread-safe LRU keyed by
  resolved path, nanosecond modification time and byte size. Unchanged and
  shared sources reuse only their digest string; mtime/size changes rehash,
  failed reads are not cached, and audio bytes or cache state are never
  persisted (`REQ-NFR-b6ffe4e8`, `REQ-REL-45ec2fa5`).

## Change map

| Change requested | Start with | Focused verification |
|---|---|---|
| Output grouping or gaps | `audio_assembly_plan.py` | Per-chunk, time limit and pause tests |
| PCM and candidate publication | `audio_assembly_wav.py` | Sample width, replace failure and cancellation tests |
| Source coverage, scene identity or resume | `audio_assembly_service.py` | Missing sources, anchored preview parity and selective resume |

## Key behaviors

- `REQ-FUNC-7c32fd5e`. Required source WAVs must contain their declared frames.
- `REQ-FUNC-f58d731e`. Preview and final assembly share anchored groups and durations.
- `REQ-REL-f3f965de`. Failed or cancelled candidate publication keeps the prior WAV.
- `REQ-REL-65c19765`. Resume reuses validated output files in plan order.
- `REQ-FUNC-51afdd49`. Pauses accept milliseconds or seconds and stream silence.

### Workflow integration

Audio Assembly is the final runtime workflow after TTS Audio Blocks. It consumes approved generated audio and provides reviewable deliverables; upstream resets invalidate only affected assembly outputs. Composition requires
any translated Speech Blocks source to match the current approved translation.
An existing assembled audiobook remains available for review.

### Usage

After TTS completes, open Audio Assembly, inspect readiness/settings, generate or resume outputs, select an output or ambience mix for playback, and manually listen before export/delivery.

### Verification

Primary automated coverage:

- `tests/test_audio_assembly_service.py`
- `tests/test_audio_assembly_state_service.py`
- `tests/test_audio_assembly_page.py`
- `tests/test_audio_assembly_ui_controller.py`

These cover WAV composition/validation, output/state recovery, controller
operation flow, lifecycle timestamp/resume consistency, bounded Scene Mix
digest reuse and invalidation, and page selection/playback behavior. Minimum validation after a
change: run the focused modules above with `uv run pytest`, plus
`uv run python -m py_compile` and `uv run ruff check` on changed files. Manual
listening remains required.

### Verification limits

Automated tests cannot assess audible mixing, loudness, transitions, ambience balance, clipping or artistic sequencing. Source WAV quality and operator audition remain decisive before the final audiobook output is accepted.

## Files

From the adopted component map:

- `05_Software/AudioMancer/src/audiomancer/services/audio_assembly_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/audio_assembly_plan.py`
- `05_Software/AudioMancer/src/audiomancer/services/audio_assembly_wav.py`
- `05_Software/AudioMancer/src/audiomancer/services/audio_assembly_state_service.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/audio_assembly_ui_controller.py`
- `05_Software/AudioMancer/src/audiomancer/ui/pages/audio_assembly_page.py`
- `05_Software/AudioMancer/src/audiomancer/ui/main_window.py` (page-scoped refresh entry point)
- `05_Software/AudioMancer/tests/test_audio_assembly_page.py`
- `05_Software/AudioMancer/tests/test_audio_assembly_service.py`
- `05_Software/AudioMancer/tests/test_audio_assembly_state_service.py`
- `05_Software/AudioMancer/tests/test_audio_assembly_ui_controller.py`
