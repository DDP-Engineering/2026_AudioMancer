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
- Resolve explicit narrator selection for Character Voices and Audio Blocks.
- Drive the existing narrator and character review/edit/generate/import flows.

It does not synthesize Speech Blocks or final TTS Audio Blocks.

## 3. Implementation Overview

`narrator_definition_service` is the sole owner of `narrator_voice.json`.
Profile/sample/selection mutations validate and atomically replace that
document; WAV writes are atomic and use immutable profile IDs. AI generation
stores compact checkpoints in the same document and appends profiles only after
complete validation. Character-voice services keep their independent target
contract and resolve the selected narrator through the narrator service.

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
assets before starting TTS.

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
