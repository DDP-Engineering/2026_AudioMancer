<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Voice Profiles

## Routing

For sample-model selection use narrator_definition_service and
tts_runtime_ui_support. For sample persistence and profile editing use the
narrator and character voice services.

## Purpose and boundaries

Maintains reviewed narrator and character voice definitions, canonical sample
audio, language/assignment choices, and resumable AI narrator suggestions
required before speech generation.

## 2. Responsibilities

- Own the strict Narrator Voice document and profile-owned WAV contract.
- Persist Character Voices targets and target-specific sample metadata.
- Generate resumable AI narrator suggestions and keep usable profiles from
  a partially successful response.
- Preserve the enabled narrator-generation AI profile across page refreshes and
  apply configured-default then first-enabled fallback when it becomes invalid
  (`REQ-UX-f6f92026`, `REQ-UX-850b356e`, `REQ-UX-cbed137b`).
- Restore truthful count and instruction defaults for every narrator-generation
  retry while leaving compatibility decisions to the full service fingerprint.
- Validate narrator preview duration and sample budgets with shared word-based
  spoken units for supported voice languages (`REQ-FUNC-f04f2515`).
- Govern every narrator and character preview text with one accepted spoken-word
  range sized for a ten-to-fifteen-second voice-clone reference, shared by AI
  generation, the canonical per-language defaults, and both profile editors
  (`REQ-FUNC-1202a564`, `REQ-FUNC-1c0c97a6`, `REQ-FUNC-fd4b9595`,
  `REQ-FUNC-11743b06`).
- Substitute the canonical default preview text for an unusable generated
  preview instead of failing the batch, and report each substitution
  (`REQ-FUNC-05eabf3a`).
- Block a narrator or character save whose edited preview text falls outside that
  range, naming the range and the current word count (`REQ-UX-3cdcb2a3`,
  `REQ-UX-fb5a66cb`).
- Migrate profile languages without replacing authored previews or writing an
  unchanged narrator document (`REQ-FUNC-4f57d7ae`, `REQ-FUNC-0fff5848`,
  `REQ-FUNC-206af389`).
- Report stale narrator edit targets and release preview playback before
  profile mutation (`REQ-UX-08439166`, `REQ-REL-c45c0ecb`).
- Treat sample WAV removal as best-effort while keeping authoritative metadata
  updates strict (`REQ-REL-870d0b6a`).
- Resolve explicit narrator selection for Character Voices and Audio Blocks.
- Drive the existing narrator and character review/edit/generate/import flows.
- Preview generation requires a compatible design model for the selected language.
  Imported reference WAVs with transcripts can be cloned using a clone-only runtime.
- Run narrator and character voice-design samples through one shared
  unauthenticated simplified-VoiceWeaver probe, model-load, `voice_design`
  generation, validation, cancellation, and `/audio` download sequence
  while keeping each controller's request, budget, persistence, and refresh
  behavior explicit (`REQ-FUNC-47809158`, `REQ-FUNC-7a68a78e`).
- Keep Narrator Voice selection application controller-owned through the full
  page-state payload while exposing `current_profile_id()` for live reads
  (`REQ-NFR-b3fb9944`).

It does not synthesize Speech Blocks or final TTS Audio Blocks.

## 3. Implementation Overview

`narrator_definition_service` is the sole owner of `narrator_voice.json`.
Profile/sample/selection mutations validate and atomically replace that
document; language application compares the fully validated profile list and
writes only when migration changes it. Exact prior-language canonical defaults
localize, while authored previews and sample metadata remain intact. Narrator
edits stay in a draft until Save. Cancel restores the saved fields. Changing only the name preserves the WAV and
selection. A changed prompt, preview or language retires its sample and
selection, then the controller invalidates the selected voice's dependent audio.
Generated and imported WAVs publish with their transcript metadata through
recoverable replacement. Explicit sample deletion remains best-effort for WAV
filesystem errors. The controller releases playback before replacing or deleting a sample.
`tts_budget_service.preview_word_bounds()` derives one accepted spoken-word range
from the configured minimum and target preview durations, so narrator generation,
character synthesis, the canonical defaults of both operations, and both editor
gates cannot drift apart; `narrator_preview_word_bounds()` and
`preview_text_range_error()` remain on `narrator_definition_service` as thin
delegates. Only length is judged - line breaks are spoken as pauses and are
accepted on both paths. AI generation stores compact checkpoints in the same
document, estimates serialized style windows within remaining context for each
backend, and drops ranked summary terms when
the final request would exceed the estimated input budget. It appends usable
profiles with unique names and reports a shortfall. A generated preview outside
the range takes the canonical default and is reported. The main window passes the page-owned
live narrator-generation AI selection back through the enabled-profile resolver.
Character-voice services keep their independent target contract and resolve the
selected narrator through the narrator service. `tts_runtime_ui_support`
returns only the generated request, provider summary, and WAV bytes; narrator
and character controllers remain responsible for their distinct persistence
and UI completion paths.

## 4. Dependencies

- Internal: Character Discovery, AI provider/budget/prompt services, project
  manifest and operation runtime, atomic persistence, VoiceWeaver runtime, and
  shared Qt operation orchestration.
- External: selected AI provider, local VoiceWeaver runtime, and imported WAV
  files.

## 5. Inputs And Outputs

- Inputs: project root/manifest, character profiles, language/assignment mode,
  editor payloads, selected AI profile, runtime state, and generated/imported
  WAV samples.
- Outputs: strict narrator document, canonical `audio_narator_<profile_id>.wav`
  files, character target metadata/WAVs, diagnostic narrator AI logs, page
  state, and downstream invalidation when voice choices change.

## 6. Data Contracts

`narrator_voice.json` has exactly seven root fields: `status`, `token_usage`,
`budget_metadata`, `additional_profile_instructions`, `selected_profile_id`,
`profiles`, and `resume`. Each profile has exactly ID, display name, language,
prompt, preview, and optional sample metadata. Selection stores only the ID;
selected language, metadata, and canonical WAV path are derived.

Generated samples use `source_kind = "voice_designer"`; imported narrator
samples use `source_kind = "imported"`. AI cancellation/failure retains compact
resume state and unchanged profiles. Success appends validated profiles and
clears resume atomically. AI log paths and raw responses are never persisted.
The retry UI reads `resume.requested_count` only from a validated unfinished
checkpoint, bounds it to the supported dialog range, and always passes accepted
instructions as an explicit string; it stores no duplicate resume data.
Narrator-generation AI selection remains session-local rather than adding a
duplicate document field. A voice-language migration changes each profile's
language, preserves any non-canonical preview exactly, localizes only the exact
prior canonical default, and retains the sample's recorded provenance.

Character Voices retains its own `characters_voice.json` contract, including
`copied_narrator` target samples in same-narrator mode.

## 7. Workflow Integration

Voice Profiles follows Character Discovery and supplies narrator/character
assignments and validated samples to Speech Blocks and Audio Blocks. Project
completion evidence, export, snapshot, reset, and preservation use the current
narrator document and canonical profile WAVs. Editing a voice invalidates only
the intended downstream audio.

## 8. Usage

Use Narrator Voice to create or generate profiles, import/generate samples,
audition them, and explicitly select one profile. Use Character Voices to
inspect derived targets and prepare character samples. Confirm current voice
assets before starting TTS. A cancelled or failed profile-generation retry
restores the checkpointed count and saved optional rules. Accepting both
unchanged permits a compatible resume; changing the count or editing or
clearing the rules may restart analysis, and cancelling either dialog starts
no runtime work. Selecting another enabled AI profile survives ordinary page
and narrator-list refreshes. Changing the effective voice language preserves
authored preview text; untouched canonical defaults follow the new language. If
an inspected profile disappears before editing or deletion, the controller
reports a localized project error. The narrator edit service has no read-only
profile outcome: every existing profile is editable and only a missing profile
is rejected. Edit and delete mutations release active preview media before
sample cleanup (`REQ-UX-08439166`).

## 9. Validation And Tests

Primary automated coverage:

- `tests/test_narrator_definition_service.py`
- `tests/test_narrator_voice_single_document_contract.py`
- `tests/test_narrator_definition_state_service.py`
- `tests/test_narrator_profile_generation_service.py`
- `tests/test_narator_voice_page.py`
- `tests/test_narator_voice_ui_controller.py`
- `tests/test_character_voices_service.py`
- `tests/test_character_voices_state_service.py`
- `tests/test_character_voices_page.py`
- `tests/test_character_voices_ui_controller.py`
- `tests/test_voice_sample_import_service.py`
- `tests/test_tts_budget_service.py`

Adjacent Audio Blocks, workspace, export, and snapshot suites also consume the
narrator/character voice contracts. Minimum validation after a change: run the
focused modules above with `uv run pytest`, plus `uv run python -m py_compile`
and `uv run ruff check` on changed files. Automated tests cannot judge voice
naturalness or suitability, so operators must audition and approve samples.

## 10. Limitations And Future Work

Automated tests cannot judge naturalness, cultural suitability,
intelligibility, legal usability, or character fit. Operators must audition and
approve samples. Malformed current narrator documents intentionally require
operator action.

The operator-settable preview-text character limit is removed
(`REQ-UX-571c3e2f`). It applied only to Narrator Voice, truncated silently while
the operator typed, and any value below roughly 250 characters contradicted the
accepted word range outright: the editor trimmed preview text below the accepted
minimum and generation then refused it, with nothing on screen explaining why.
The accepted word range is now the only limit on preview length, on both pages,
at save and at generation.

A narrator profile written by an earlier version keeps its shorter preview text,
which is preserved as authored text rather than migrated. Operators lengthen
those previews in the editor.

## Files

From the adopted component map:

- `05_Software/AudioMancer/prompts/narrator_profile_*.txt`
- `05_Software/AudioMancer/src/audiomancer/services/character_voices_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/character_voices_state_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/narrator_definition_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/narrator_definition_state_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/narrator_profile_generation_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/tts_budget_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/voice_sample_import_service.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/character_voices_ui_controller.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/misc_ui_controller.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/tts_runtime_ui_support.py`
- `05_Software/AudioMancer/src/audiomancer/ui/pages/character_voices_page.py`
- `05_Software/AudioMancer/src/audiomancer/ui/pages/narator_voice_page.py`
- `05_Software/AudioMancer/tests/test_character_voices_page.py`
- `05_Software/AudioMancer/tests/test_character_voices_service.py`
- `05_Software/AudioMancer/tests/test_character_voices_state_service.py`
- `05_Software/AudioMancer/tests/test_character_voices_ui_controller.py`
- `05_Software/AudioMancer/tests/test_narator_voice_page.py`
- `05_Software/AudioMancer/tests/test_narator_voice_ui_controller.py`
- `05_Software/AudioMancer/tests/test_tts_runtime_ui_support.py`
- `05_Software/AudioMancer/tests/test_narrator_definition_service.py`
- `05_Software/AudioMancer/tests/test_narrator_definition_state_service.py`
- `05_Software/AudioMancer/tests/test_narrator_profile_generation_service.py`
- `05_Software/AudioMancer/tests/test_narrator_voice_single_document_contract.py`
- `05_Software/AudioMancer/tests/test_tts_budget_service.py`
- `05_Software/AudioMancer/tests/test_voice_sample_import_service.py`
- `06_SoftwareDocu/UserGuide/index.html`
- `06_SoftwareDocu/UserGuide_ro/index.html`
