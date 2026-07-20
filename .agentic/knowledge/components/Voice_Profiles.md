<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Voice Profiles

## 1. Purpose

Maintains the reviewed narrator and character voice definitions, sample audio, language/assignment choices, and AI-generated narrator profiles required before speech generation.

## 2. Responsibilities

- Persist character voice targets, prompt/preview text, language, selected samples, and same-narrator assignments.
- Maintain narrator profile records, selection, sample metadata, runtime readiness, and profile-state projections.
- Generate candidate narrator profiles through the configured AI provider and validate imported WAV samples.
- Drive separate Narrator Voice and Character Voices review/edit/generate/import flows.
- It does not synthesize the project speech blocks; that belongs to TTS Audio Blocks.

## 3. Implementation Overview

Character-voice services derive safe prompts from the character inventory, preserve selected language and target samples, and synchronize the voice plan. Narrator-definition services store profile/sample metadata and derive state from project language and runtime readiness. Profile generation performs bounded, resumable AI style analysis and final profile generation, while sample import validates WAV duration/audibility. The two controller/page pairs deliberately separate narrator selection from per-character maintenance and use the shared operation runner for long generation actions.

## 4. Dependencies

- Internal: Character Discovery profiles, AI Runtime/provider/budget/prompt services, project manifest and operation runtime, VoiceWeaver runtime support, atomic persistence helpers, and shared Qt operation runner.
- External: selected AI provider for narrator profile generation; VoiceWeaver runtime for sample generation; local WAV files for imported samples.

## 5. Inputs And Outputs

- Inputs: project root/manifest, character profiles, approved language and assignment mode, narrator/character editor payloads, selected AI profile, runtime availability, generated or imported WAV samples.
- Outputs: narrator profile data and selected-sample metadata, character voice targets/plan, copied/imported sample artifacts, generated candidate profiles, page state, and workflow invalidation when a voice choice changes.

## 6. Data Contracts

- Narrator and character targets use stable IDs, selected flags, prompt/preview text, runtime language codes, sample-path metadata, and assignment mode.
- Sample imports must be readable, non-silent WAVs of adequate duration. Writes use atomic JSON/byte persistence and tolerate torn legacy metadata as absent data.
- AI profile generation retains style checkpoints, bounded preview text, operator rules, token-usage/state metadata, and does not overwrite profiles after invalid/cancelled work.
- A selected narrator is copied to `narator.wav` and `narator_sample.json` from
  the profile-owned sample. In `same_narrator` mode, character targets receive
  `copied_narrator` sample metadata; per-character prompt editing and
  generation remain disabled, while imported and generated samples retain
  their distinct source kinds.

## 7. Workflow Integration

Voice Profiles follows Character Discovery and the applicable text language decision. It supplies selected narrator/character voice assignments and validated samples to Speech Blocks and TTS Audio Blocks. Editing a voice can invalidate generated audio while preserving unrelated upstream text/character work.

## 8. Usage

Use Narrator Voice to create, generate, import, preview, and select one narrator profile. Use Character Voices to inspect the derived targets, choose a voice language/assignment mode, edit approved prompts, import or generate samples, and batch-regenerate eligible character samples. Confirm selected voice assets before starting TTS.

## 9. Validation And Tests

Focused suite E-0014 passed 96 tests across all ten mapped services, controllers, and pages. Coverage includes prompt derivation, atomic persistence, language/assignment synchronization, recovery from malformed metadata, WAV validation, bounded/cancellable AI generation, UI edit/selection behavior, sample-generation failure preservation, and redacted progress. Run all ten mapped modules after changes with temporary/cache paths outside `.agentic`. Manual listening and operator selection remain mandatory.

## 10. Limitations And Future Work

Tests verify artifact contracts and guarded flows but cannot determine that a generated or imported voice is natural, culturally appropriate, intelligible, legally usable, or suited to a character. Hardware/runtime availability and provider-generated style quality vary; operators must audition samples and approve voice assignments before speech generation.
