<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# TTS Audio Blocks

## 1. Purpose

Generates and manages ordered WAV artifacts from approved speech blocks using the configured VoiceWeaver runtime.

## 2. Responsibilities

- Discover, probe and configure VoiceWeaver runtime capabilities and TTS settings.
- Budget work, build resumable generation plans, create deterministic artifact paths, validate WAVs, and preserve completed artifacts on recovery paths.
- Project generation/playback state and expose settings, progress, cancellation, and playback actions through UI controllers/pages.
- It does not author speech text or compose final assembled audio.

## 3. Implementation Overview

Artifact helpers own safe names/paths and WAV inspection. The main service coordinates ordered synthesis, retry/resume, clone prompts, persistence and runtime invocation; state/budget helpers derive UI-ready limits and progress. Runtime services probe VoiceWeaver process/capabilities. Audio-block and settings controllers/pages expose deliberate configuration and generated-artifact review.

## 4. Dependencies

- Internal: approved Speech Blocks and Voice Profiles, project/operation persistence, TTS budget, audio artifact helpers, UI operation runner and playback support.
- External: installed VoiceWeaver runtime/model resources and local WAV files.

## 5. Inputs And Outputs

- Inputs: project root, approved blocks/voice plan, runtime/settings/capability data, generation selection and cancellation request.
- Outputs: ordered deterministic WAV artifacts and metadata/state/report,
  runtime probe results, UI status/progress and playback actions. Unapproved
  Speech Blocks remain recorded but are skipped until approval; approved pause
  rows are metadata-only timing entries, while scene-ambience rows use the
  runtime sound-prompt path.

## 6. Data Contracts

Chunk-source readiness is derived through the shared strict Chunking document
reader; stale legacy sidecars cannot make Audio Blocks appear ready.

- Generated audio uses stable block ordering and project-local artifact paths; WAV format/metadata must pass validation before downstream assembly.
- Runtime capabilities, budgets, progress and completed block IDs are persisted for truthful resume rather than inferred from a partially generated plan.
- Audio Block identity is its `speech_block_id`; compact records retain source
  chunk/speaker/voice target, generated and approval timestamps, relative paths,
  duration, split-plan/budget data, and a generation fingerprint. Approval
  changes preserve WAVs but reset Audio Assembly; cancellation is cooperative
  around polling/checkpoints, so an already submitted runtime request can still
  finish remotely.

## 7. Workflow Integration

TTS Audio Blocks follows approved Speech Blocks and Voice Profiles, and supplies validated ordered WAVs to Audio Assembly. Changing TTS settings or invalidating source blocks can reset only incompatible generated artifacts.

## 8. Usage

Probe the runtime in TTS Settings, choose supported settings, then open Audio Blocks to generate/resume approved blocks. Monitor progress, cancel cooperatively when needed, review/play generated files, and proceed only when the ordered block set is complete.

## 9. Validation And Tests

Primary automated coverage:

- `tests/test_audio_blocks_service.py`
- `tests/test_audio_blocks_state_service.py`
- `tests/test_audio_blocks_artifact_service.py`
- `tests/test_audio_blocks_page.py`
- `tests/test_audio_blocks_ui_controller.py`
- `tests/test_audio_blocks_main_window.py`
- `tests/test_voiceweaver_runtime_service.py`
- `tests/test_tts_settings_page.py`
- `tests/test_blocks_performance_baseline.py`

These cover artifact paths/WAV validation, orchestration/resume, state, runtime
probing, UI, settings, main-window integration, and a performance baseline.
Minimum validation after a change: run the focused modules above with
`uv run pytest`, plus `uv run python -m py_compile` and `uv run ruff check` on
changed files. Manual listening and an installed compatible runtime remain
required.

## 10. Limitations And Future Work

Tests cannot prove voice naturalness, pronunciation, timing, clone fidelity, GPU/runtime compatibility or audible artifact quality. Providers/models and local hardware materially affect results; an operator must audition generated audio before assembly.
