<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Voice Profiles

## 1. Purpose

Maintains reviewed narrator and character voice definitions, canonical sample
audio, language/assignment choices, and resumable AI narrator suggestions
required before speech generation.

## 2. Responsibilities

- Own the strict Narrator Voice document and profile-owned WAV contract.
- Persist Character Voices targets and target-specific sample metadata.
- Generate resumable AI narrator suggestions without exposing partial profiles.
- Preserve the enabled narrator-generation AI profile across page refreshes and
  apply configured-default then first-enabled fallback when it becomes invalid
  (`REQ-UX-f6f92026`, `REQ-UX-850b356e`, `REQ-UX-cbed137b`).
- Restore truthful count and instruction defaults for every narrator-generation
  retry while leaving compatibility decisions to the full service fingerprint.
- Validate narrator preview duration and sample budgets with shared script-aware spoken units.
- Migrate profile languages without replacing authored previews or writing an
  unchanged narrator document (`REQ-FUNC-4f57d7ae`, `REQ-FUNC-0fff5848`,
  `REQ-FUNC-206af389`).
- Report stale narrator edit targets and release preview playback before
  profile mutation (`REQ-UX-08439166`, `REQ-REL-c45c0ecb`).
- Treat sample WAV removal as best-effort while keeping authoritative metadata
  updates strict (`REQ-REL-870d0b6a`).
- Resolve explicit narrator selection for Character Voices and Audio Blocks.
- Drive the existing narrator and character review/edit/generate/import flows.
- Keep Narrator Voice selection application controller-owned through the full
  page-state payload while exposing `current_profile_id()` for live reads
  (`REQ-NFR-b3fb9944`).

It does not synthesize Speech Blocks or final TTS Audio Blocks.

## 3. Implementation Overview

`narrator_definition_service` is the sole owner of `narrator_voice.json`.
Profile/sample/selection mutations validate and atomically replace that
document; language application compares the fully validated profile list and
writes only when migration changes it. Exact prior-language canonical defaults
localize, while authored previews and sample metadata remain intact. WAV writes
are atomic and use immutable profile IDs. Sample deletion suppresses only WAV
filesystem errors before performing the normal strict document update, and the
controller releases preview playback plus its source before deleting a profile.
AI generation stores compact checkpoints in the same document and appends
profiles only after complete validation. The main window passes the page-owned
live narrator-generation AI selection back through the enabled-profile resolver.
Character-voice services keep their independent target contract and resolve the
selected narrator through the narrator service.

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
an inspected profile disappears before editing, the controller reports a
localized project error. Edit and delete mutations release active preview media
before sample cleanup.

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

## Files

From the adopted component map:

- `04_Software/AudioMancer/prompts/narrator_profile_*.txt`
- `04_Software/AudioMancer/src/audiomancer/services/character_voices_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/character_voices_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/narrator_profile_generation_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/tts_budget_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/voice_sample_import_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/character_voices_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/character_voices_page.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/narator_voice_page.py`
- `04_Software/AudioMancer/tests/test_character_voices_page.py`
- `04_Software/AudioMancer/tests/test_character_voices_service.py`
- `04_Software/AudioMancer/tests/test_character_voices_state_service.py`
- `04_Software/AudioMancer/tests/test_character_voices_ui_controller.py`
- `04_Software/AudioMancer/tests/test_narator_voice_page.py`
- `04_Software/AudioMancer/tests/test_narator_voice_ui_controller.py`
- `04_Software/AudioMancer/tests/test_narrator_definition_service.py`
- `04_Software/AudioMancer/tests/test_narrator_definition_state_service.py`
- `04_Software/AudioMancer/tests/test_narrator_profile_generation_service.py`
- `04_Software/AudioMancer/tests/test_narrator_voice_single_document_contract.py`
- `04_Software/AudioMancer/tests/test_tts_budget_service.py`
- `04_Software/AudioMancer/tests/test_voice_sample_import_service.py`
- `05_SoftwareDocu/UserGuide/index.html`
- `05_SoftwareDocu/UserGuide_ro/index.html`
