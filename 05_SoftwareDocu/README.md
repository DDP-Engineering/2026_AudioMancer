<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# 05_SoftwareDocu

Implementation-focused software documentation and component notes.

Release-sensitive version history lives in `CHANGELOG.md`, while the packaged
application version is exposed through the application package metadata and
`audiomancer.__version__`.

## Current Documents

### Operator Help

- `UserGuide/` - English offline help bundle.
- `UserGuide_ro/` - Romanian offline help bundle.

### Application Shell And Shared Services

- `AudioMancer_App_Shell.md`
- `AudioMancer_Config_And_Settings.md`
- `AudioMancer_Settings_Service.md`
- `AudioMancer_UI_State_Service.md`
- `AudioMancer_UI_Scroll_Service.md`
- `AudioMancer_UI_Theme_Service.md`
- `AudioMancer_UI_Themes.md`
- `AudioMancer_Persistence_Service.md`
- `AudioMancer_Logging_Service.md`
- `AudioMancer_Workflow_Impact_Service.md`
- `AudioMancer_Operation_Runner_Controller.md`

### Project And Runtime Support

- `AudioMancer_Project_Workspace.md`
- `AudioMancer_Project_Export_Service.md`
- `AudioMancer_Project_Snapshot_Service.md`
- `AudioMancer_Project_Runtime_Support_Services.md`

### Text And AI Pipeline

- `AudioMancer_Text_Extraction_Service.md`
- `AudioMancer_Deterministic_Cleanup_Service.md`
- `AudioMancer_AI_Cleanup_Service.md`
- `AudioMancer_Chunking_Document_Service.md`
- `AudioMancer_Text_Chunking_State_Service.md`
- `AudioMancer_AI_Translation_Service.md`
- `AudioMancer_LLM_Provider_Service.md`
- `AudioMancer_AI_Runtime_Support_Services.md`
- `AudioMancer_Page_State_Support_Services.md`
- `AudioMancer_Text_Pipeline_Support_Services.md`
- `AudioMancer_OpenAI_Online_Model_Recommendations.md`
- `AudioMancer_LMStudio_Local_Model_Recommendations.md`

### Characters, Voices, And Speech

- `AudioMancer_Character_Discovery_Service.md`
- `AudioMancer_Narrator_Definition_Service.md`
- `AudioMancer_Narrator_Profile_Generation_Service.md`
- `AudioMancer_Narrator_Definition_State_Service.md`
- `AudioMancer_Character_Voices_Service.md`
- `AudioMancer_Speech_Blocks_Service.md`
- `AudioMancer_Speech_Blocks_State_Service.md`
- `AudioMancer_Speech_Blocks_Normalization_Service.md`

### Audio Generation And Assembly

- `AudioMancer_Audio_Blocks_Service.md`
- `AudioMancer_Audio_Blocks_State_Service.md`
- `AudioMancer_Audio_Assembly_Service.md`
- `AudioMancer_TTS_Settings_And_VoiceWeaver_Runtime.md`
- `AudioMancer_Voiceweaver_Runtime_Service.md`
- `AudioMancer_Voice_Sample_Import_Service.md`
- `AudioMancer_TTS_Budget_Service.md`

## Documentation Review Notes

Reviewed for the AI chunking context mode feature. Relevant component documents are `AudioMancer_Config_And_Settings.md`, `AudioMancer_Settings_Service.md`, `AudioMancer_UI_State_Service.md`, and `AudioMancer_Text_Pipeline_Support_Services.md`.

Reviewed for the single-document Chunking contract. The dedicated document
service page and affected pipeline, lifecycle, export, and state pages now
describe `chunks_text.json` as the sole authority.

Reviewed for the 1.5.9 release sync. Offline help bundle versions are maintained
in `UserGuide/index.html` and `UserGuide_ro/index.html`.
