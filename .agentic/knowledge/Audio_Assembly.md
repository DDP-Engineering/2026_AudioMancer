<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Audio Assembly

## 1. Purpose

Validates and composes ordered generated audio blocks into project-local final audiobook WAV outputs.

## 2. Responsibilities

- Validate generated block artifacts, settings and ordering; compose resumable outputs and ambience mixes.
- Persist assembly state, reports, output metadata and project-local paths safely.
- Project assembly readiness/output state and expose generate, selection and playback actions through UI.
- It does not generate TTS blocks or alter their speech content.

## 3. Implementation Overview

The assembly service loads validated block WAVs, applies configured composition/ambience behavior, writes resumable outputs and reports, and guards project-relative paths. State service derives readiness and saved-output projections. The controller delegates long work through the shared runner; the page presents output/mix selection, settings, progress and playback.

## 4. Dependencies

- Internal: TTS Audio Blocks artifacts, Speech Blocks ordering/ambience metadata, operation runtime/persistence/project workspace, PCM Codec for sample-width/channel/rate conversion, shared runner and Qt playback widgets.
- External: Python `wave` container handling and local generated WAV artifacts. PCM sample conversion is provided by the internal codec.

## 5. Inputs And Outputs

- Inputs: approved ordered generated WAVs, assembly settings, project root, selected output/mix and cancellation request.
- Outputs: composed WAV deliverables, scene-ambience mixes, state/report/
  metadata and UI-ready output summaries. Settings support per-chunk,
  time-limited, or whole-book WAV delivery and can include or skip generated
  scene ambience.

## 6. Data Contracts

- Outputs and referenced inputs remain project-relative and ordered by block identity; state records completed outputs, durations and resumable progress.
- Every newly persisted report records one UTC ISO `started_at` for the logical
  run and a nullable `completed_at`; compact state carries the same start as
  `resume_checkpoint.run_token`. Cancelled resumes and already-completed
  re-entry preserve their original lifecycle values, while legacy report/state
  payloads without the added fields remain loadable and receive a fresh token
  only when continued (`REQ-DATA-94132a27`, `REQ-REL-3ccdf599`).
- Assembly validates readable compatible WAVs and preserves previously completed work when a later operation cannot complete.
- Final-composition preflight validates every included non-pause source as a
  safe existing regular readable supported-PCM WAV, including defensive support
  for legacy path-carrying metadata-only Scene Ambience rows. Synthesized pauses
  require no source, and disabled ambience stays outside validation and
  composition (`REQ-FUNC-7c32fd5e`).
- Accepted PCM sample widths are 2, 3 and 4 bytes. One-byte PCM is rejected on
  purpose: WAV stores 8-bit samples unsigned while this component and PCM Codec
  read every width as signed, so gap and pause silence would be written as a
  negative-rail DC offset instead of quiet. Re-admitting 8-bit requires an
  unsigned zero level of 0x80 in the silence writer and unsigned handling in PCM
  Codec, whose current signed behavior is deliberate `audioop` compatibility.
- Scene-ambience blocks group by chunk/position/anchor and share the same mixing
  helper for preview and final composition. Only a real generated ambience WAV
  carries the `audio_relative_path` that admits it to a scene group;
  metadata-only ambience rows remain pathless and are not mixed
  (`REQ-FUNC-ee6222b7`). Resume requires the current input/settings fingerprint;
  mismatched persisted state requires explicit reset. Outputs publish through
  temporary paths, and WAV remains the only supported delivery format. Before
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

## 7. Workflow Integration

Audio Assembly is the final runtime workflow after TTS Audio Blocks. It consumes approved generated audio and provides reviewable deliverables; upstream resets invalidate only affected assembly outputs.

## 8. Usage

After TTS completes, open Audio Assembly, inspect readiness/settings, generate or resume outputs, select an output or ambience mix for playback, and manually listen before export/delivery.

## 9. Validation And Tests

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

## 10. Limitations And Future Work

Automated tests cannot assess audible mixing, loudness, transitions, ambience balance, clipping or artistic sequencing. Source WAV quality and operator audition remain decisive before the final audiobook output is accepted.

## Files

From the adopted component map:

- `04_Software/AudioMancer/src/audiomancer/services/audio_assembly_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/audio_assembly_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/audio_assembly_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/audio_assembly_page.py`
- `04_Software/AudioMancer/tests/test_audio_assembly_page.py`
- `04_Software/AudioMancer/tests/test_audio_assembly_service.py`
- `04_Software/AudioMancer/tests/test_audio_assembly_state_service.py`
- `04_Software/AudioMancer/tests/test_audio_assembly_ui_controller.py`
