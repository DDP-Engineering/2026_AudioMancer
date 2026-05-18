<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Narrator Definition State Service

## 1. Purpose

Builds the page-state payload for the project-local `Narator Voice` page.

It combines narrator profiles, selected narrator state, locked project voice
language, translation readiness, and cached VoiceWeaver runtime capability data
into one UI-facing model.

## 2. Responsibilities

- initialize narrator definition files when the page is opened for a project
- resolve inspected and selected narrator profiles
- expose locked voice-language labels and localized preview text
- build profile rows, status lines, and operator notes
- classify Qwen3 narrator-generation readiness from discovered runtime models
- expose preview text character and safe-word limits
- derive editability from the inspected profile's existence rather than a
  persisted profile-level `editable` flag

It does not create profiles, generate samples, select profiles, or write
runtime settings.

## 3. Implementation Overview

Implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_state_service.py`

Main entrypoints:

- `build_narrator_definition_state(...)`
- `build_narrator_definition_notes(...)`
- `build_status_lines(...)`
- `voice_capability_matrix(...)`

The service reads project artifacts, resolves the selected voice language from
project state and Character Voices state, applies that language to persisted
profiles, builds profile entries, and returns the dictionary consumed by the
Narator Voice page.

## 4. Dependencies

Internal dependencies:

- `narrator_definition_service`
- `character_voices_service`
- `ai_translation_service`
- `tts_budget_service`
- `voiceweaver_runtime_service`
- `ui_state_service`
- `home_presenter_service`

External dependencies:

- Python standard library `pathlib`

## 5. Inputs And Outputs

Inputs:

- active project root
- active manifest
- runtime UI language
- settings payload with cached TTS runtime discovery fields
- optional inspected profile id

Outputs:

- page-state dictionary with profile rows, selected profile id, language
  indicators, prompt/preview text, edit/generate/select flags, notes, status
  lines, and preview budget values

## 6. Data Contracts

The state payload includes stable keys such as:

- `profiles`
- `current_profile_id`
- `selected_profile_id`
- `selected_voice_language`
- `language_entries`
- `original_language`
- `translated_language`
- `prompt_text`
- `preview_text`
- `can_generate`
- `can_select`
- `preview_available`
- `status_lines`

Profile rows are derived from `narator.json`, `audio_profiles.json`, compact
per-profile `sample` metadata, and computed per-profile WAV paths. Persisted
profiles do not carry `is_selected` or `editable`; those values are resolved
for the page state from explicit selection and current workflow context.

## 7. Workflow Integration

Upstream:

- project activation and page activation in `MainWindow`
- persisted app settings from `settings_service`

Downstream:

- `NaratorVoicePage`
- `narator_voice_ui_controller`
- Character Voices state, which consumes selected narrator sample readiness

## 8. Usage

Representative page refresh:

```python
state = narrator_definition_state_service.build_narrator_definition_state(
    project_root,
    manifest,
    language,
    settings_payload,
    inspected_profile_id,
)
```

## 9. Validation And Tests

Focused tests:

- `tests/test_narrator_definition_state_service.py`
- `tests/test_narator_voice_page.py`
- `tests/test_narator_voice_ui_controller.py`

Documentation audit status:

- compact narrator profile state contract reviewed on 2026-05-18
- profile editability and selection flags reviewed on 2026-05-18

Minimum validation after changes:

- `uv run python -m py_compile src/audiomancer/services/narrator_definition_state_service.py`
- `uv run pytest tests/test_narrator_definition_state_service.py`

## 10. Limitations And Future Work

- the returned model remains a dictionary contract shared with the Qt page
- capability readiness is intentionally tied to the current fixed Qwen3 model
  families
