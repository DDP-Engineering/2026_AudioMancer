<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# 05_SoftwareDocu

Implementation-focused software documentation and component notes.

## Current Documents

- `UserGuide/` contains the English end-user help bundle for AudioMancer, including the offline HTML guide and real UI screenshots used by packaged Windows and Ubuntu releases.
- `UserGuide_ro/` contains the Romanian end-user help bundle, including the offline HTML guide and Romanian UI screenshots used when the application language is set to Romanian.
- `AudioMancer_App_Shell.md` documents the desktop application shell, Home workflow progress presenter, project navigation, settings dialogs, and page-hosting responsibilities.
- `AudioMancer_Config_And_Settings.md` documents the adapted configuration and settings scaffold.
- `AudioMancer_Settings_Service.md` documents the shared settings lifecycle implementation.
- `AudioMancer_Logging_Service.md` documents the shared runtime logging implementation.
- `AudioMancer_Project_Workspace.md` documents the new/open project workspace layer, locked Home-page project options, source import flow, and current `project.json` contract.
- `AudioMancer_Project_Export_Service.md` documents the Home-page export readiness and TXT/Markdown projection layer for cleaned text, chunks, translations, character dossiers, and Speech Blocks.
- `AudioMancer_Project_Snapshot_Service.md` documents the Home-page full-project ZIP snapshot export, external destination guard, temporary archive replacement, and long-operation blocking behavior.
- `AudioMancer_Text_Extraction_Service.md` documents the deterministic extraction workflow, artifacts, and rerun/reset behavior used by the Text Cleanup page.
- `AudioMancer_Deterministic_Cleanup_Service.md` documents the deterministic cleanup workflow, cleanup artifacts, and resumable cleanup behavior used by the Text Cleanup page.
- `AudioMancer_AI_Cleanup_Service.md` documents the AI-assisted cleanup workflow, prompt/provider dependencies, and project-local AI transaction logging used by the Text Cleanup page.
- `AudioMancer_AI_Translation_Service.md` documents the locked-target AI Translation workflow, same-language pass-through behavior, per-chunk review records, and page-state integration.
- `AudioMancer_LLM_Provider_Service.md` documents the shared OpenAI-compatible provider layer, JSON-repair behavior, transaction logging, and normalized token-usage contract used by all AI workflows.
- `AudioMancer_Character_Discovery_Service.md` documents the AI-assisted character-discovery workflow, persisted artifacts, Qwen-oriented character voice-definition fields plus final prompt, page/controller integration, and resumable discovery behavior used by the Characters page.
- `AudioMancer_Narrator_Definition_Service.md` documents the seeded and runtime-synced Qwen3 narrator preset workflow, legacy prompt-seed profile migration, explicit narrator selection, locked voice-language display, per-profile sample artifacts, destructive edit behavior, and Narator Voice page integration.
- `AudioMancer_Character_Voices_Service.md` documents the Character Voices target contract, character-owned prompt handoff from `Characters` with legacy fallback, read-only selected voice-language display, same-narrator read-only reuse behavior, and root-level page/controller integration.
- `AudioMancer_Speech_Blocks_Service.md` documents the Speech Blocks source-resolution rules, mode-aware AI-first per-chunk generation flow, quoted/guillemet/dash dialogue validation, narrator-only TTS-budget segmentation, manual insert/delete behavior, metadata-only operation blocks, root-level persisted artifacts, resumable state contract, and page/controller integration.
- `AudioMancer_Audio_Blocks_Service.md` documents the Audio Blocks reusable clone-prompt workflow, metadata-only pause/background/indication handling, root-level persisted artifact contract, approval rules, generated `audio_blocks/` media folder, and upstream invalidation behavior.
- `AudioMancer_Audio_Assembly_Service.md` documents the final WAV audiobook composition workflow, pause-to-silence handling, per-project assembly settings, resumable state/report artifacts, generated `audiobook/` deliverables, and playback/reset page integration.
- `AudioMancer_TTS_Settings_And_VoiceWeaver_Runtime.md` documents the simplified TTS Settings dialog, VoiceWeaver runtime integration, fixed Qwen3 readiness classification, generation helpers, and runtime limit settings.
- `AudioMancer_TTS_Budget_Service.md` documents the cached VoiceWeaver TTS budget resolver used by narrator-only Speech Blocks prompting and validation.
- `AudioMancer_Operation_Runner_Controller.md` documents the shared threaded modal-operation runner used by long-running UI workflows.
- The app shell document also covers the shared runtime logging bootstrap.
