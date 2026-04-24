<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# 05_SoftwareDocu

Implementation-focused software documentation and component notes.

## Current Documents

- `AudioMancer_App_Shell.md` documents the initial desktop application shell.
- `AudioMancer_Config_And_Settings.md` documents the adapted configuration and settings scaffold.
- `AudioMancer_Settings_Service.md` documents the shared settings lifecycle implementation.
- `AudioMancer_Logging_Service.md` documents the shared runtime logging implementation.
- `AudioMancer_Project_Workspace.md` documents the new/open project workspace layer, source import flow, and current `project.json` contract.
- `AudioMancer_Text_Extraction_Service.md` documents the deterministic extraction workflow, artifacts, and rerun/reset behavior used by the Text Cleanup page.
- `AudioMancer_Deterministic_Cleanup_Service.md` documents the deterministic cleanup workflow, cleanup artifacts, and resumable cleanup behavior used by the Text Cleanup page.
- `AudioMancer_AI_Cleanup_Service.md` documents the AI-assisted cleanup workflow, prompt/provider dependencies, and project-local AI transaction logging used by the Text Cleanup page.
- `AudioMancer_LLM_Provider_Service.md` documents the shared OpenAI-compatible provider layer, JSON-repair behavior, transaction logging, and normalized token-usage contract used by all AI workflows.
- `AudioMancer_Character_Discovery_Service.md` documents the AI-assisted character-discovery workflow, persisted artifacts, Qwen-oriented character voice-definition fields plus final prompt, page/controller integration, and resumable discovery behavior used by the Characters page.
- `AudioMancer_Narrator_Definition_Service.md` documents the seeded and runtime-synced Qwen3 narrator preset workflow, legacy prompt-seed profile migration, explicit narrator selection, per-profile sample artifacts, destructive edit behavior, and Narator Voice page integration.
- `AudioMancer_Character_Voices_Service.md` documents the Character Voices target contract, character-owned prompt handoff from `Characters` with legacy fallback, selected voice-language rules, same-narrator copy behavior, and page/controller integration under `60_character_voices`.
- `AudioMancer_Speech_Blocks_Service.md` documents the Speech Blocks source-resolution rules, per-chunk AI generation flow, persisted artifacts, resumable state contract, and page/controller integration under `70_speech_blocks`.
- `AudioMancer_Audio_Blocks_Service.md` documents the Audio Blocks reusable clone-prompt workflow, persisted `80_audio_blocks` contract, approval rules, resumable state, and upstream invalidation behavior.
- `AudioMancer_TTS_Settings_And_VoiceWeaver_Runtime.md` documents the simplified TTS Settings dialog, VoiceWeaver runtime integration, fixed Qwen3 readiness classification, generation helpers, and project-local `voice_assignment_mode` contract.
- `AudioMancer_Operation_Runner_Controller.md` documents the shared threaded modal-operation runner used by long-running UI workflows.
- The app shell document also covers the shared runtime logging bootstrap.
