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
- Outputs: ordered deterministic WAV artifacts, one authoritative
  `audio_blocks.json` document, the `voice_clone_profiles.json` prompt cache,
  runtime probe results, UI status/progress and playback actions. Unapproved
  Speech Blocks remain recorded but are skipped until approval; approved pause
  rows are metadata-only timing entries, while scene-ambience rows use the
  runtime sound-prompt path.

## 6. Data Contracts

Chunk-source readiness is derived through the shared strict Chunking document
reader.

All operation metadata lives in a single authoritative `audio_blocks.json`
document with a fixed root field set (`status`, `voice_language`,
`input_fingerprint`, `checkpoint`, `blocks`). `load_audio_blocks_report()` and
`load_operation_state()` are projections over that document. A missing
document, a non-object payload, or any root-contract violation reads as
not-started. The
`voice_clone_profiles.json` cache stays a separate artifact because it holds
large per-voice model prompts that would otherwise be rewritten on every
per-block checkpoint. See `.agentic/specs/audio_blocks_document.spec.md`.

- Generated audio paths are a pure function of `speech_block_id`
  (`audio_blocks/<speech_block_id>.wav`, parts under `audio_blocks/parts/`).
  The name depends only on the block's stable primary key. WAV format/metadata
  must pass validation before downstream assembly.
- Runtime progress is persisted in `document.checkpoint` (`run_token`,
  `current_phase`, `current_block_id`, `next_speech_block_index`,
  `next_split_part_index`) for truthful resume rather than inferred from a
  partially generated plan.
- Audio Block identity is its `speech_block_id`; each persisted entry carries
  only that id, `voice_target_id`, boolean `generated` and `approved` flags,
  cached `audio_can_play`, measured `audio_duration_seconds`, and a
  `generation_fingerprint`, plus `split_part_count` and
  `split_plan_fingerprint` when the block was actually split. Source text,
  speaker, prompts and per-run budgets are not duplicated here; they are read
  from the Speech Blocks document or recomputed from settings. Approval changes
  preserve WAVs but reset Audio Assembly; cancellation is cooperative around
  polling/checkpoints, so an already submitted runtime request can still finish
  remotely.
- Loading rebuilds every non-persisted field the same way generation first
  derived it, so a reloaded block equals a freshly initialized one. In
  particular `content_kind`, `text`, prompts, `special_block_status` and
  `pause_duration_ms` are recomputed from the current Speech Blocks entry
  (`pause_duration_ms` by parsing the pause block's text), never read back from
  Audio Blocks storage.
- The derived `audio_relative_path` exposed to consumers stays `None` for any
  block that owns no WAV — an ungenerated block, a pause/indication block, or
  a completed metadata-only Scene Ambience row. A real generated Scene
  Ambience WAV remains non-metadata-only and keeps its derived path even when
  later generation policy is Off. A set path therefore still means "generated
  audio exists on disk", which is the condition Audio Assembly inclusion and
  reusable-audio checks rely on (`REQ-FUNC-ee6222b7`).
- Direct selected regeneration rejects metadata-only pause and indication rows
  before model or artifact work, while ordinary speech and Scene Ambience keep
  their existing regeneration paths (`REQ-FUNC-94720d7e`).
- State publishes Play and Re-Generate eligibility per row. Pause rows can Play
  as timed silence but cannot regenerate; indication and metadata-only Scene
  Ambience rows cannot Play; real speech and ambience WAVs remain playable
  (`REQ-UX-1d1e98a7`, `REQ-UX-cc9b04c0`).

## 7. Workflow Integration

TTS Audio Blocks follows approved Speech Blocks and Voice Profiles, and supplies validated ordered WAVs to Audio Assembly. Changing TTS settings or invalidating source blocks can reset only incompatible generated artifacts.

## 8. Usage

Probe the runtime in TTS Settings, choose supported settings, then open Audio Blocks to generate/resume approved blocks. Monitor progress, cancel cooperatively when needed, review/play generated files, and proceed only when the ordered block set is complete.

## 9. Validation And Tests

Primary automated coverage:

- `tests/test_audio_blocks_service.py`
- `tests/test_audio_blocks_single_document_contract.py`
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

## Files

From the adopted component map:

- `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_artifact_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/tts_budget_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/voiceweaver_runtime_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/audio_blocks_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/tts_runtime_ui_support.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/tts_settings_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/audio_blocks_page.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/tts_settings_page.py`
- `04_Software/AudioMancer/tests/test_audio_blocks_artifact_service.py`
- `04_Software/AudioMancer/tests/test_audio_blocks_main_window.py`
- `04_Software/AudioMancer/tests/test_audio_blocks_page.py`
- `04_Software/AudioMancer/tests/test_audio_blocks_service.py`
- `04_Software/AudioMancer/tests/test_audio_blocks_single_document_contract.py`
- `04_Software/AudioMancer/tests/test_audio_blocks_state_service.py`
- `04_Software/AudioMancer/tests/test_audio_blocks_ui_controller.py`
- `04_Software/AudioMancer/tests/test_blocks_performance_baseline.py`
- `04_Software/AudioMancer/tests/test_tts_settings_page.py`
- `04_Software/AudioMancer/tests/test_voiceweaver_runtime_service.py`
