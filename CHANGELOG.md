<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

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
