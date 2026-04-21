<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# AudioMancer Character Voices And Audio Workflow Plan

## Implementation Target

This plan is intended for Codex GPT-5.4 with `high` reasoning effort.

The work expands the post-character-discovery audiobook workflow into explicit stages:

1. Character Voices
2. Speech Blocks
3. Audio Blocks
4. Audio Assembly

The implementation must preserve the offline-first desktop application model, reuse the existing PySide6 page/controller/service structure, and keep project artifacts under the active project workspace.

## Character Voices

Rename the previous Narration Plan concept to Character Voices. This page prepares voice samples for the narrator and for zero or more book characters.

Implementation requirements:

- rename user-facing page text, internal page ids, controller names, service names, tests, documentation, and translation keys from narration-plan wording to character-voices wording
- do not preserve compatibility names from the previous implementation unless required only for reading older persisted project data
- persist outputs under `60_character_voices`
- persist voice targets in `voice_targets.json`
- keep generated audio samples and metadata under the Character Voices output folder
- keep narrator and character target handling explicit because a project may have no discovered character speakers or many speakers
- update the project status window so this stage is visible and correctly described
- update `project.json` workflow stage handling and generation status notes

## Speech Blocks

Speech Blocks splits approved chunk text into smaller text blocks that can later be sent to a TTS model.

The page must exist after Character Voices and must persist an output folder even while the full feature is incomplete.

Implementation requirements:

- create page, controller, service, state service, prompt templates, tests, runtime translations, and software documentation
- persist outputs under `70_speech_blocks`
- create one or more speech blocks for each source chunk
- each speech block must retain the original text, source chunk id, sequence order, content kind, and assigned speaker
- split blocks on speaker changes, dialogue boundaries, narration boundaries, and TTS model token limits
- preserve quote and narration boundaries before AI attribution so dialogue such as `"Different how?" Drenthe snapped.` becomes one character dialogue block and one narrator block
- assign speaker ids from Character Discovery/Character Voices when possible
- use `narrator` as the fallback speaker for narration
- record warnings for ambiguous or missing speaker attribution instead of silently dropping text
- update the main project status window, `project.json`, and generation status

## Audio Blocks

Audio Blocks will generate audio for each Speech Blocks text block.

Only the placeholder page and project output folder are required in the current scope. The page name must reflect that this stage generates per-block audio.

Future behavior:

- persist outputs under `80_audio_blocks`
- show each Speech Blocks entry with original text, editable working text, speaker, generation status, approval status, and generated audio metadata
- preserve the original text even when the user edits the working text
- allow reverting working text back to the original text
- generate all audio blocks
- generate one selected audio block
- approve all audio blocks
- approve one selected audio block
- use the block speaker to select the narrator or character voice
- use a workflow similar to AI Translation but adapted for TTS generation and per-speaker voice selection

## Audio Assembly

Audio Assembly will assemble approved Audio Blocks into final delivery audio.

Only the placeholder page and project output folder are required in the current scope. The page name must reflect that this stage assembles generated audio into final deliverables.

Future behavior:

- persist outputs under `90_audio_assembly`
- support one continuous audio file
- support one audio file per original Text Chunking chunk
- support splitting output files by maximum duration
- generate a zip archive for final audio delivery
- generate metadata alongside the archive, including subtitle timing and speaker information
- require approved Audio Blocks before assembly

## Validation Expectations

For implementation work, run:

- `uv run python -m py_compile` for changed Python files
- `uv run ruff check <changed_python_files> --fix`
- `uv run ruff format <changed_python_files>`
- focused pytest coverage for changed services, state services, pages, controllers, settings, and project repair logic

Do not run packaging scripts as part of this workflow. Packaging is responsible only for gathering the prepared environment and creating release archives after the application has already been tested.
