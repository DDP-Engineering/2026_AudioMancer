<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# 05_SoftwareDocu

Implementation-focused software documentation and component notes.

## Current Documents

- `UserGuide/` contains the English end-user help bundle for AudioMancer 1.1.2, including the offline HTML guide, runtime Settings theme notes, and real UI screenshots used by packaged Windows and Ubuntu releases.
- `UserGuide_ro/` contains the Romanian end-user help bundle for AudioMancer 1.1.2, including the offline HTML guide, runtime Settings theme notes, and Romanian UI screenshots used when the application language is set to Romanian.
- `AudioMancer_App_Shell.md` documents the desktop application shell, Home workflow progress presenter, project navigation, settings dialogs, and page-hosting responsibilities.
- `AudioMancer_Config_And_Settings.md` documents the adapted configuration and settings scaffold.
- `AudioMancer_Settings_Service.md` documents the shared settings lifecycle implementation.
- `AudioMancer_UI_State_Service.md` documents the shared runtime UI string catalog, language application, text-size scaling behavior, and compact Speech Blocks selected-audio labels.
- `AudioMancer_UI_Theme_Service.md` documents the Qt-independent theme schema helper, built-in theme catalog, custom theme validation, and import/export payload behavior.
- `AudioMancer_UI_Themes.md` documents the Settings-backed UI theme schema, built-in and custom themes, JSON import/export behavior, and runtime theme application path.
- `AudioMancer_Persistence_Service.md` documents the shared atomic text and JSON write helpers used by critical project, settings, and operation state persistence paths.
- `AudioMancer_Logging_Service.md` documents the shared runtime logging implementation.
- `AudioMancer_Workflow_Impact_Service.md` documents the v2 workflow impact foundation for selective downstream preservation, stable IDs, reset summaries, manifest refresh, and safe generated-artifact deletion.
- `AudioMancer_Project_Workspace.md` documents the new/open project workspace layer, locked Home-page project options, source import flow, and current `project.json` contract.
- `AudioMancer_Project_Export_Service.md` documents the Home-page export readiness, TXT/Markdown projection layer for text artifacts, and ZIP archive exports for voice samples plus Audio Assembly outputs.
- `AudioMancer_Project_Snapshot_Service.md` documents the Home-page full-project ZIP snapshot export, external destination guard, temporary archive replacement, and long-operation blocking behavior.
- `AudioMancer_Text_Extraction_Service.md` documents the deterministic extraction workflow, artifacts, and rerun/reset behavior used by the Text Cleanup page.
- `AudioMancer_Deterministic_Cleanup_Service.md` documents the deterministic cleanup workflow, cleanup artifacts, and resumable cleanup behavior used by the Text Cleanup page.
- `AudioMancer_AI_Cleanup_Service.md` documents the AI-assisted cleanup workflow, optional operator prompt rules, current-model resume behavior, prompt/provider dependencies, and project-local AI transaction logging used by the Text Cleanup page.
- `AudioMancer_Text_Chunking_State_Service.md` documents the Text Chunking page-state helper, stable chunk identity contract, and manual chunk edit/insert/delete selective downstream preservation behavior.
- `AudioMancer_AI_Translation_Service.md` documents the locked-target AI Translation workflow, optional operator prompt rules, same-language pass-through behavior, per-chunk review records, and page-state integration.
- `AudioMancer_LLM_Provider_Service.md` documents the shared OpenAI-compatible provider layer, JSON-repair behavior, transaction logging, and normalized token-usage contract used by all AI workflows.
- `AudioMancer_AI_Runtime_Support_Services.md` documents the grouped AI helper services for backend probing, context budgets, prompt templates, token usage, state notes, URL handling, and UTC timestamps.
- `AudioMancer_OpenAI_Online_Model_Recommendations.md` documents recommended online OpenAI model profiles and AI Settings parameters for cleanup, chunking, translation, character discovery, and Speech Blocks.
- `AudioMancer_LMStudio_Local_Model_Recommendations.md` documents recommended local LM Studio model profiles and AI Settings parameters for cleanup, chunking, translation, character discovery, and Speech Blocks on a 16 GB VRAM workstation.
- `AudioMancer_Page_State_Support_Services.md` documents grouped page-state and presenter helpers for Home, Text Cleanup, AI Translation, Characters, Character Voices, and Audio Assembly.
- `AudioMancer_Text_Pipeline_Support_Services.md` documents grouped cleanup metadata, text analysis, deterministic/AI chunking with optional operator prompt rules, Speech Blocks report shaping, and text-splitting helpers.
- `AudioMancer_Project_Runtime_Support_Services.md` documents grouped source-import, shared operation-runtime, and generated-audio artifact helpers.
- `AudioMancer_Character_Discovery_Service.md` documents the AI-assisted character-discovery workflow, optional operator prompt rules, persisted compact voice-ready profiles, final prompt handoff, page/controller integration, and resumable discovery behavior used by the Characters page.
- `AudioMancer_Narrator_Definition_Service.md` documents the custom Voice Designer narrator-profile workflow, AI-generated text profile append behavior, explicit narrator selection, internal locked voice-language use, per-profile sample artifacts, destructive edit behavior, and Narator Voice page integration.
- `AudioMancer_Narrator_Profile_Generation_Service.md` documents the AI-assisted text-only narrator-profile suggestion workflow, source resolution, optional operator prompt rules, resumable style-analysis checkpoints, prompt flow, validation rules, report/state sidecars, and Narator Voice page/controller integration.
- `AudioMancer_Narrator_Definition_State_Service.md` documents the Narator Voice page-state helper, inspected/selected profile state, locked voice-language labels, preview limits, Qwen3 readiness notes, and status lines.
- `AudioMancer_Character_Voices_Service.md` documents the Character Voices target contract, character-owned prompt handoff from `Characters`, read-only selected voice-language display, same-narrator read-only reuse behavior, full-current-target batch generation, and root-level page/controller integration.
- `AudioMancer_Speech_Blocks_Service.md` documents the Speech Blocks source-resolution rules, optional operator prompt rules, mode-aware AI-first per-chunk generation flow, quoted/guillemet/dash dialogue validation, narrator-only TTS-budget segmentation, manual insert/delete behavior, metadata-only operation blocks, root-level persisted artifacts, resumable state contract, and page/controller integration.
- `AudioMancer_Speech_Blocks_State_Service.md` documents the Speech Blocks page-state helper, source resolution, localized notes, selector state, and selected-audio preview flags used by the Speech Blocks page.
- `AudioMancer_Speech_Blocks_Normalization_Service.md` documents shared Speech Blocks normalization helpers for content kinds, operation rows, warning flags, text spans, stable block IDs, and narrator-only TTS budget lookup.
- `AudioMancer_Audio_Blocks_Service.md` documents the Audio Blocks reusable clone-prompt workflow, compact timestamp-based `audio_blocks.json` index, block-level generation fingerprints, metadata-only pause/background/indication handling, approval rules, generated `audio_blocks/` media folder, and upstream invalidation behavior.
- `AudioMancer_Audio_Blocks_State_Service.md` documents the Audio Blocks page-state helper, merged Speech/Audio Blocks rows, localized notes, progress values, approval flags, and selected text character budget.
- `AudioMancer_Audio_Assembly_Service.md` documents the final WAV audiobook composition workflow, pause-to-silence handling, per-project assembly settings, resumable state/report artifacts, generated `audiobook/` deliverables, playback seek/progress controls, and reset page integration.
- `AudioMancer_TTS_Settings_And_VoiceWeaver_Runtime.md` documents the simplified TTS Settings dialog, VoiceWeaver runtime integration, fixed Qwen3 readiness classification, generation helpers, and runtime limit settings.
- `AudioMancer_Voiceweaver_Runtime_Service.md` documents the service-only VoiceWeaver REST wrapper boundary for probing, model operations, generation calls, polling, endpoint normalization, and generated-audio downloads.
- `AudioMancer_Voice_Sample_Import_Service.md` documents the shared WAV validation helper used before importing operator-provided narrator and character reference samples.
- `AudioMancer_TTS_Budget_Service.md` documents the cached VoiceWeaver TTS budget resolver used by narrator-only Speech Blocks prompting and validation.
- `AudioMancer_Operation_Runner_Controller.md` documents the shared threaded modal-operation runner used by long-running UI workflows.
- The app shell document also covers the shared runtime logging bootstrap.

## Documentation Status

These documents describe the current v2 implementation direction. The
documented workflow contract assumes stable v2 identifiers such as `chunk_id`,
`speech_block_id`, and `voice_target_id`; compatibility with pre-v2 workflow
metadata is not a documentation requirement unless a future implementation task
explicitly reintroduces migration support.

The application-level settings documentation may describe committed
`settings.json` runtime profile definitions because the repository allows the
app baseline settings file to include runnable profile scaffolding. API-key and
VoiceWeaver secret fields must remain blank in the committed file; tests and
documentation should focus on the supported settings lifecycle while preserving
that secret-free baseline.

Implementation-review follow-ups that are not yet code or documentation
contracts are tracked in `../0_Planning/08_Implementation_Review_Followups.md`.
Do not describe those follow-ups as implemented behavior until the matching
code and tests have been completed.
