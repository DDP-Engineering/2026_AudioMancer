<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [1.0.6] - 2026-05-11

### Changed

- Windows and Linux packaging scripts now include `CHANGELOG.md` in portable
  release bundles.

## [1.0.5] - 2026-05-11

### Changed

- Narator Voice changes now show a synchronous modal progress dialog while
  affected Audio Blocks and Audio Assembly state is refreshed, using the same
  faster affected-audio cleanup path as Characters saves.

## [1.0.4] - 2026-05-11

### Changed

- Characters page saves now show a synchronous modal progress dialog while
  downstream Speech Blocks, Audio Blocks, and Audio Assembly state are
  refreshed, and affected Audio Blocks cleanup skips unnecessary preserved-file
  checks for faster large-project saves.

## [1.0.3] - 2026-05-10

### Changed

- Audio Blocks page opening is faster on large projects because page-state
  construction no longer opens every generated WAV to compute row durations,
  and the page batches list-row refreshes while avoiding unchanged source-text
  rewrites.

## [1.0.2] - 2026-05-10

### Fixed

- Backend workflow services now persist compact operation status summaries and
  workflow-stage transitions directly to `project.json` after operation
  completion or review updates, instead of relying on the UI shell to mirror
  backend state.
- Audio Blocks completion and approval refreshes now promote stale
  `audio_blocks_state.json` metadata to `completed` when the completed report
  and generated output artifacts prove the operation finished.
- Project-open metadata normalization now treats persisted string values such
  as `"None"` and `"null"` as missing values, preventing repeat repair prompts
  caused by stale null-like text.
- Narrator completion evidence now prefers selected-sample timestamps so valid
  narrator selections no longer require repeated summary normalization.

## [1.0.1] - 2026-05-10

### Changed

- JSON-producing AI requests now choose the structured-output
  `response_format` by backend: general OpenAI-compatible profiles use
  `json_object`, while LM Studio and Ollama profiles use permissive
  `json_schema` mode. Providers that reject `response_format` still get a
  one-time compatibility retry without the field.
- AI workflow prompts have been refreshed for literary/audiobook production,
  with stronger preservation rules for cleanup, semantic chunking, translation,
  character discovery, character voice synthesis, Speech Blocks, and
  narrator-only Speech Blocks.
- Speech Blocks prompts now preserve the improved v2 dialogue and attribution
  guidance while staying aligned with the current application JSON contract.
- Speech Blocks generation now resumes from partially generated, reviewed, or
  approved chunks instead of treating review state as a fresh run.
- AI cleanup, AI-assisted chunking, character discovery, and Speech Blocks now
  size OpenAI-compatible request text windows from 30% of the selected model
  context window, without applying the local LM Studio/Ollama request caps.
- Narrator profile selection now updates the project manifest's narrator
  operation summary immediately, avoiding a repair prompt after restarting the
  app with a valid selected narrator.
- Home workflow progress now trusts explicit operation summaries over the
  linear `current_stage`, so independently completed Narator Voice work no
  longer makes Translation, Characters, or Character Voices appear finished.

## [1.0.0] - 2026-05-06

### Added

- first AudioMancer release with the complete desktop audiobook production
  workflow, offline English and Romanian help, packaging metadata, and release
  documentation aligned to version `1.0.0`
