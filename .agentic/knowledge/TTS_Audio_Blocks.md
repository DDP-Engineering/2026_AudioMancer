<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# TTS Audio Blocks

## Routing

For WAV generation, regeneration, retry, clone prompt reuse and listening, start
with `audio_blocks_service.py` and `tests/test_audio_blocks_service.py`. For text
and speaker assignment use Speech Blocks. For combining ordered WAVs use Audio
Assembly.

## Purpose and boundaries

Generates and manages ordered WAV artifacts from approved speech blocks using the configured VoiceWeaver runtime.

- Discover, probe and configure VoiceWeaver runtime capabilities and TTS settings.
- Canonicalize discovered VoiceWeaver models once for runtime use and settings persistence.
- Budget work, build resumable generation plans, create deterministic artifact paths, validate WAVs, and preserve completed artifacts on recovery paths.
- Project generation/playback state and expose settings, progress, cancellation, and playback actions through UI controllers/pages.
- It does not author speech text or compose final assembled audio.

The generation service renders one candidate from VoiceWeaver responses.
Artifact helpers derive paths and inspect WAVs. The main service owns batch
order, resource selection, checkpoints, review and recoverable publication.

## Public interface

Call `start_or_continue_generation` for eligible missing audio,
`regenerate_audio_block` for a selected row, and `load_audio_blocks_report` or
`load_operation_state` for projections. The page and controller use
`pending_speech_blocks` to resolve eligible work from current Speech Blocks
and WAV availability.

- Inputs: project root, approved blocks/voice plan, runtime/settings/capability data, generation selection and cancellation request.
- Outputs: ordered deterministic WAV artifacts, one authoritative
  `audio_blocks.json` document, the `voice_clone_profiles.json` prompt cache,
  runtime probe results, UI status/progress and playback actions. Unapproved
  Speech Blocks remain recorded but are skipped until approval; approved pause
  rows are metadata-only timing entries, while scene-ambience rows use the
  runtime sound-prompt path.

## Invariants

Chunk-source readiness is derived through the shared strict Chunking document
reader.

All operation metadata lives in a single authoritative `audio_blocks.json`
document with a fixed root field set (`status`, `voice_language`,
`input_fingerprint`, `checkpoint`, `blocks`). `load_audio_blocks_report()` and
`load_operation_state()` are projections over that document. A missing
document reads as not-started. Every existing unreadable, non-object, or
contract-invalid document raises `AudioBlocksDocumentError` with the original
failure chained and `Reset Audio Blocks to recover` in the operator message.
State and generation boundaries disable generation, surface that recovery,
and leave explicit Audio Blocks reset as the only replacement path
(`REQ-REL-c5b666e6`, `REQ-UX-7982f351`). The
`voice_clone_profiles.json` cache stays a separate artifact because it holds
large per-voice model prompts that would otherwise be rewritten on every
per-block checkpoint. See `.agentic/specs/audio_blocks_document.spec.md`.

- Generated audio paths are a pure function of `speech_block_id`
  (`audio_blocks/<speech_block_id>.wav`, parts under `audio_blocks/parts/`).
  The name depends only on the block's stable primary key. WAV format/metadata
  must include its declared frames. Part writes use the atomic byte writer.
  Final candidates publish together with the review document, clone cache and
  project summary through the recoverable file publisher. A failed or cancelled
  regeneration preserves the prior WAV and approval
  (`REQ-REL-ee8f9ed0`, `REQ-REL-3a5d2962`).
- Runtime progress is persisted in `document.checkpoint` (`run_token`,
  `current_phase`, `current_block_id`, `next_speech_block_index`,
  `next_split_part_index`) for truthful resume rather than inferred from a
  partially generated plan. For a split block, the next-part index is the
  completed-prefix length. Resume finds the active row by ID, verifies its
  synthesis fingerprint, split plan and contiguous valid WAVs, then starts at
  the first missing part. Cancel during model loading and review of other rows
  preserve the cursor. Part files are removed from the canonical project
  directory after successful publication. A redirected directory is skipped
  (`REQ-FUNC-e9a6688e`, `REQ-FUNC-9e6c2465`).
- The shared VoiceWeaver client is the only simplified REST-contract boundary.
  It probes `GET /models` and `GET /status`, loads with `POST /models/load` and
  `device_mode=auto`, unloads with `POST /models/unload`, and accepts only the
  current `voice_design`, `clone`, and `sound_prompt` capability names. Voice,
  clone-prompt, clone-from-prompt, and sound requests use their root endpoints;
  every completed audio operation downloads from `GET /audio`. The client sends
  no authentication and exposes none of the removed versioned, rescan, delete,
  or download-management routes (`REQ-FUNC-636da15e`, `REQ-FUNC-1562fca1`,
  `REQ-FUNC-b3c6df2a`, `REQ-FUNC-6606ebfa`).
- Audio Block identity is its `speech_block_id`; each persisted entry carries
  only that id, `voice_target_id`, boolean `generated` and `approved` flags,
  cached `audio_can_play`, measured `audio_duration_seconds`, and a
  `generation_fingerprint`, optional `configured_fingerprint` and `audio_stale`,
  and `split_part_count` and
  `split_plan_fingerprint` when the block was actually split. Source text,
  speaker, prompts and per-run budgets are not duplicated here; they are read
  from the Speech Blocks document or recomputed from settings. Approval changes
  preserve WAVs but reset Audio Assembly. Cancellation is cooperative around
  polling/checkpoints and calls `POST /cancel` when VoiceWeaver reports the
  current operation as cancellable; a non-cancellable request can still finish
  remotely (`REQ-FUNC-a24e14cb`). A cancel that arrives before the first status
  poll reads the operation once so the request just submitted is still stopped,
  and a `POST /cancel` that fails, including a runtime that drops the
  connection mid-teardown, never converts the cancellation into a failure.
- Cancellation has one outcome, whichever side observed it. The polling wait
  raises the cooperative cancellation error both when the operator asks locally
  and when `/status` reports the operation as terminal `cancelled`, so the
  callers that test only for `completed` never report a deliberate cancel as a
  generation failure (`REQ-FUNC-1a06b572`).
- `generate_sound_prompt()` bounds `duration_seconds` at
  `config.MAX_SOUND_PROMPT_DURATION_SECONDS`, the Stable Audio output ceiling of
  47.55 s that `/sound/prompt` refuses rather than clamps. The bound sits at the
  request, not only at the settings form, because the duration can also come
  from a persisted Scene Ambience block; a refusal here would abort the whole
  Audio Blocks run (`REQ-FUNC-1562fca1`). The TTS Settings spinbox and settings
  validation apply the same ceiling so an unachievable duration is never offered.
- `probe_runtime()` reports a refusal through `_runtime_error_message()`, the same
  helper every other runtime call uses, so the runtime's own
  `{error_code, message, details}` explanation reaches the one dialog built for
  diagnosing the connection instead of a bare status code. A successful probe
  records the reported `runtime_version` from `/status` or `/models`
  (`REQ-FUNC-636da15e`).
- A persisted discovered-model inventory declaring a generation mode outside
  `voiceweaver_runtime_service.SUPPORTED_GENERATION_MODES` is discarded whole at
  settings validation, and the connection reverts to untested. The VoiceWeaver
  interface was a hard cut, so no legacy mode name is folded onto a current one;
  trusting such a cache would report Qwen3 capabilities as missing against a
  healthy runtime until the operator re-ran Test Connection (`REQ-FUNC-9757d967`).
- The busy gate before model loading treats every terminal operation status as
  free. `/status` reports the most recent operation and latches its terminal
  status until the next one starts, so counting `cancelled` as busy left the
  runtime permanently unusable to Audio Blocks after any cancel
  (`REQ-NFR-5bda19fd`).
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
- Cancellation rebuilds use the resolved project voice-assignment mode, so
  same-narrator dialogue rows keep the narrator target used by later voice
  invalidation (`REQ-FUNC-d53b102d`).
- Re-split reconciliation resolves the project TTS plan once and initializes
  every changed or newly projected row with that voice-assignment mode, so
  same-narrator character-speaker rows continue to target the narrator
  (`REQ-FUNC-f5c39900`).
- State publishes Play and Re-Generate eligibility per row. Pause rows can Play
  as timed silence but cannot regenerate; indication and metadata-only Scene
  Ambience rows cannot Play; real speech and ambience WAVs remain playable
  (`REQ-UX-1d1e98a7`, `REQ-UX-cc9b04c0`).
- Incremental page updates rebuild the sorted widget when an unseen block is
  inserted, preserving the selected block when present; updates for existing
  block IDs still replace only that row (`REQ-FUNC-50f45095`).
- TTS Settings intentionally shows Not connected at the start of every loaded
  dialog session without treating that display reset as a failed probe. Saving
  before Test Connection preserves the durable probe success and message
  fields exactly; once the current session applies a probe, its success or
  failure and exact message become authoritative until the next `load_state`
  (`REQ-FUNC-77fce48b`, `REQ-FUNC-8749869e`).
- The TTS Settings middle action persists changes without closing and is
  therefore labeled Apply in both supported interface languages; OK retains
  the save-and-close path (`REQ-UX-aa109e16`).
- The single generated-audio WAV download helper translates a direct
  `TimeoutError` to `Connection failed: request timed out.` with the original
  exception chained, while retaining existing HTTPError and URLError handling
  (`REQ-FUNC-6606ebfa`).
- `tts_budget_service.selected_text_character_limit()` is the shared state
  projection for selected-text limits, and Audio Blocks uses one load/wait/
  terminal-status/active-model verification tail for clone and sound models;
  clone budget selection and its runtime-effective early return remain explicit
  (`REQ-NFR-7fcf36ea`, `REQ-NFR-5bda19fd`).
- Every VoiceWeaver voice request routes its language through one private
  helper, `voiceweaver_runtime_service._add_tts_language_field()`. It maps Romanian to the Italian
  synthesis hint at the outbound boundary and preserves Romanian text,
  reference transcripts, and project metadata. When the active model reports a
  supported-language list, the helper omits a hint outside that list (`REQ-FUNC-1562fca1`).
- `voiceweaver_runtime_service.normalize_model()` owns the discovered-model
  cache contract. It normalizes status, capabilities, scalar defaults and
  `generation_parameter_ranges`, while settings calls that exact contract and
  retains no duplicate model parser (`REQ-FUNC-9757d967`). A persisted
  `max_new_tokens` range default remains available to `tts_budget_service` when
  the model has no effective or default token value, so Speech and Audio Blocks
  use the runtime-reported capacity instead of the configuration fallback
  (`REQ-FUNC-1fef6b33`).
- `tts_budget_service.model_generation_limits()` is the single reader of the
  reported `max_new_tokens` range, and both budget paths call it. It returns the
  `recommended_maximum` bounded by `hard_maximum` (`REQ-FUNC-82401294`) and the
  reported `approx_audio_seconds_per_token` (`REQ-FUNC-9029b464`), each `None`
  when unreported. `_resolve_model_budget()` consults it ahead of
  `runtime_effective`, because the loaded model reports its own default as
  effective and would otherwise mask the recommended maximum.
- `resolve_generation_token_limit()` reads the operator ceiling from settings and
  both budget paths apply it to the token count before deriving anything from it,
  so audio seconds, split seconds and the safe word count all follow from the one
  token number the runtime is asked for (`REQ-FUNC-8ee67d8f`).
- That operator ceiling is a packing target, not a cut. Both budget payloads also
  carry `hard_token_maximum` and `hard_word_count`, derived from the runtime's
  reported `hard_maximum` through `model_hard_token_maximum()` and never lowered
  by the operator, because they mark where generation fails rather than where the
  operator prefers blocks to end. `_plan_audio_block_splits()` packs sentences
  toward the target but emits an over-target sentence whole while it stays inside
  the hard count; clause and word-group cuts engage only past it
  (`REQ-FUNC-79fd5f3a`).
- `_part_generation_token_budget()` sizes `max_new_tokens` per request instead of
  sending the operator target for every part. A part inside the target keeps the
  target; a longer part gets the smallest ceiling covering its estimated spoken
  length, bounded by the hard maximum. Sending the target for a deliberately
  over-target part would truncate exactly the sentences the splitter kept intact
  (`REQ-FUNC-46959c54`).
- `_ensure_clone_model_loaded()` skips the load when the live active-model
  identity already matches. It previously also required the budget to have come
  from `runtime_effective`, which a runtime-reported budget made unreachable, so
  every run reloaded an already-loaded model (`REQ-NFR-5bda19fd`).

## Change map

| Change requested | Start with | Focused verification |
|---|---|---|
| Replacement or split resume | `start_or_continue_generation`, `regenerate_audio_block` | `test_audio_blocks_service.py` |
| Candidate and WAV integrity | `audio_blocks_generation_service.py`, `audio_blocks_artifact_service.py` | `test_audio_blocks_artifact_service.py` |
| Work eligibility and review | `pending_speech_blocks`, `audio_blocks_state_service.py` | State, page and controller tests |

## Key behaviors

- `REQ-FUNC-168e8717`. Playable audio retains its actual synthesis fingerprint.
  The page and generation compare available synthesis inputs and mark changed
  rows for review. The page uses cached model descriptions and local references.
  The configured fingerprint excludes the live effective budget. Resume uses
  the exact generation fingerprint with the effective budget and split plan.
  Configured mismatches are recomputed for review. A confirmed difference
  in live synthesis that cannot be derived from configuration can persist.
- `REQ-FUNC-880f7fda`. Clone prompt reuse requires the same sample bytes,
  transcript, sample language and clone model.
- `REQ-UX-1e583d8c`. A missing or unreadable WAV is eligible for Start.
- `REQ-FUNC-dedd5cbf`. Metadata-only work runs locally. Only selected or
  pending spoken audio needs a loaded clone model and readable references.
  An unavailable optional reference only limits comparison of existing audio.

### Workflow integration

TTS Audio Blocks follows approved Speech Blocks and Voice Profiles, and supplies validated ordered WAVs to Audio Assembly. Changing TTS settings or invalidating source blocks can reset only incompatible generated artifacts.
Start and single-block regeneration require any translated Speech Blocks source
to match the current approved translation. Existing audio can still be reviewed.

### Usage

Probe the runtime in TTS Settings, choose supported settings, then open Audio Blocks to generate/resume approved blocks. Monitor progress, cancel cooperatively when needed, review/play generated files, and proceed only when the ordered block set is complete.

### Verification

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
- `tests/test_tts_runtime_ui_support.py`
- `tests/test_blocks_performance_baseline.py`

These cover artifact paths/WAV validation, orchestration/resume, state, runtime
probing, UI, settings, main-window integration, and a performance baseline.
Minimum validation after a change: run the focused modules above with
`uv run pytest`, plus `uv run python -m py_compile` and `uv run ruff check` on
changed files. Manual listening and an installed compatible runtime remain
required.

### Verification limits

Tests cannot prove voice naturalness, pronunciation, timing, clone fidelity, GPU/runtime compatibility or audible artifact quality. Providers/models and local hardware materially affect results; an operator must audition generated audio before assembly.

## Files

From the adopted component map:

- `05_Software/AudioMancer/src/audiomancer/services/audio_blocks_artifact_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/audio_blocks_generation_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/audio_blocks_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/audio_blocks_state_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/tts_budget_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/voiceweaver_runtime_service.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/audio_blocks_ui_controller.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/tts_runtime_ui_support.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/tts_settings_ui_controller.py`
- `05_Software/AudioMancer/src/audiomancer/ui/pages/audio_blocks_page.py`
- `05_Software/AudioMancer/src/audiomancer/ui/pages/tts_settings_page.py`
- `05_Software/AudioMancer/tests/test_audio_blocks_artifact_service.py`
- `05_Software/AudioMancer/tests/test_audio_blocks_main_window.py`
- `05_Software/AudioMancer/tests/test_audio_blocks_page.py`
- `05_Software/AudioMancer/tests/test_audio_blocks_service.py`
- `05_Software/AudioMancer/tests/test_audio_blocks_single_document_contract.py`
- `05_Software/AudioMancer/tests/test_audio_blocks_state_service.py`
- `05_Software/AudioMancer/tests/test_audio_blocks_ui_controller.py`
- `05_Software/AudioMancer/tests/test_blocks_performance_baseline.py`
- `05_Software/AudioMancer/tests/test_tts_settings_page.py`
- `05_Software/AudioMancer/tests/test_tts_runtime_ui_support.py`
- `05_Software/AudioMancer/tests/test_voiceweaver_runtime_service.py`
