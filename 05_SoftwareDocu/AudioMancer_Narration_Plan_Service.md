<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Narration Plan Service

## 1. Purpose

Implements the current `Narration Plan` workflow in `AudioMancer`.
It prepares one generation-ready voice contract for the selected narrator plus
all discovered characters by combining prompt state, sample state, language
selection, and voice-assignment rules.

## 2. Responsibilities

- persist the narration-plan target list under `60_narration_plan`
- persist one selected narration voice language
- prefer the character-owned `voice_definition_prompt` from `Characters` as
  the default voice-designer prompt for each character, with one legacy
  fallback builder for older projects
- persist one editable per-character preview text used for sample generation
- persist per-character generated samples and sample metadata
- mirror the selected narrator into the page as one preview-only target
- auto-copy narrator samples into all character sample slots when
  `voice_assignment_mode == "same_narrator"`
- build page state for target list ordering, enablement, notes, and status
  lines
- show one page-entry warning when the selected narrator sample is missing

It does not:

- own the selected narrator profile itself
- own global VoiceWeaver connection settings
- perform future long-form book generation

## 3. Implementation Overview

The workflow is split across:

- `04_Software/AudioMancer/src/audiomancer/services/narration_plan_service.py`
  for project-local narration-plan files, target synchronization, prompt
  persistence, sample persistence, and same-narrator copy behavior
- `04_Software/AudioMancer/src/audiomancer/services/narration_plan_state_service.py`
  for page-state shaping from narrator selection, character discovery,
  translation readiness, and runtime capability cache
- `04_Software/AudioMancer/src/audiomancer/ui/pages/narration_plan_page.py`
  for the target list, explicit voice-language selector, prompt editor,
  two-line preview-text editor, and bottom status area
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/narration_plan_ui_controller.py`
  for destructive edit confirmation, selected voice-language persistence,
  VoiceWeaver generation, preview playback, and stage synchronization

High-level flow:

1. Project load ensures `60_narration_plan/voice_plan.json`,
   `60_narration_plan/selected_voice_language.json`, and
   `60_narration_plan/audio_samples/` exist.
2. The state service loads:
   the selected narrator, discovered character profiles, translation report,
   cached VoiceWeaver models, and persisted narration-plan data.
3. The target list is synchronized so narrator is first when selected and each
   discovered character owns one stable `character_<character_id>` target row.
4. Character default prompts first use the stored
   `character.voice_definition_prompt`; if that field is missing, the service
   falls back to the older deterministic builder from the raw character facts.
   Any previously saved edited prompt is preserved. Each character target also
   keeps one editable preview text used as the generation input sample text.
5. In `same_narrator` mode, narrator-derived character samples are repaired or
   refreshed during state build.
6. `Edit Voice Prompt` shows a destructive confirmation, deletes the stored
   character sample, and enters explicit edit mode.
7. `Generate Sample` re-probes runtime readiness, requires the fixed Qwen3
   minimum capability set, waits for model-load completion when necessary, and
   stores one WAV plus metadata for the selected character target.
8. `Preview` plays either the selected narrator sample or the selected
   character sample locally through a dedicated page-specific player.

## 4. Dependencies

- Internal dependencies:
  `04_Software/AudioMancer/src/audiomancer/config.py`
  `04_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/character_discovery_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/settings_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/voiceweaver_runtime_service.py`
  `04_Software/AudioMancer/src/audiomancer/ui/controllers/misc_ui_controller.py`
  `04_Software/AudioMancer/src/audiomancer/ui/main_window.py`
- External dependencies:
  `PySide6`
  local `VoiceWeaver` runtime reachable over HTTP for character sample
  generation

## 5. Inputs And Outputs

Inputs:

- active project root and manifest
- selected narrator profile plus selected narrator sample
- discovered character profiles from `40_character_discovery`
- translation approval report from `30_translation`
- cached VoiceWeaver discovery fields from `settings.json`
- narration-plan page actions:
  reset prompt, edit prompt, save prompt, generate sample, preview, stop
  preview, and voice-language selection

Outputs:

- `60_narration_plan/voice_plan.json`
- `60_narration_plan/selected_voice_language.json`
- `60_narration_plan/audio_samples/<target_id>.wav`
- `60_narration_plan/audio_samples/<target_id>.json`
- updated manifest stage:
  `current_stage = "narration_plan_ready"` when narrator plus all character
  samples exist

## 6. Data Contracts

Narration-plan target payloads use:

- `target_id`
- `target_kind`
- `source_profile_id`
- `display_name`
- `character_id`
- `prompt_text`
- `preview_text`
- `default_prompt_text`
- `editable`
- `sample_mode`
- `updated_at`

Target rules:

- narrator target id is always `narrator`
- character target ids use `character_<character_id>`
- narrator target prompt fields are always `None` on disk
- narrator target preview text is not editable on this page
- character `default_prompt_text` is regenerated on synchronization
- `default_prompt_text` prefers the character-owned `voice_definition_prompt`
  and falls back to the legacy deterministic builder only when that prompt is
  missing
- character `prompt_text` is preserved until reset
- character `preview_text` is preserved until explicitly edited and saved

Selected voice-language payload uses:

- `selected_voice_language`

Character sample metadata uses:

- `target_id`
- `target_kind`
- `display_name`
- `voice_language`
- `sample_source`
- `copied_from_target_id`
- `source_model_id`
- `generation_mode`
- `prompt_text`
- `preview_text`
- `generated_at`
- `runtime_result_summary`

Same-narrator copied sample metadata uses:

- `sample_source = "copied_narrator"`
- `copied_from_target_id = "narrator"`

## 7. Workflow Integration

This workflow sits immediately after `Narrator Definition` in the current
stage order.

Upstream integrations:

- selected narrator state and narrator sample artifacts from
  `50_narrator_definition`
- project-local `voice_assignment_mode` from `project.json`
- character discovery artifacts from `40_character_discovery`, including the
  structured voice brief and final `voice_definition_prompt`
- translation approval state from `30_translation`

Downstream integrations:

- future Generation workflow that will consume the persisted narrator and
  character sample contract directly

Current rules:

- translated language becomes selectable only when all translated chunks are
  approved
- narrator is visible on the page but remains preview-only
- character editing and generation are enabled only in
  `narrator_and_characters` mode
- `same_narrator` mode disables prompt editing and generation but keeps
  preview available by copying narrator-derived samples into every character
  target slot
- entering the page with a selected narrator that still lacks a generated
  sample shows one blocking warning popup per page entry

## 8. Usage

Representative service calls:

```python
voice_targets = narration_plan_service.sync_voice_plan(
    project_root,
    character_profiles,
    selected_narrator_profile,
)

state = narration_plan_state_service.build_narration_plan_state(
    project_root,
    manifest,
    "en",
    settings_payload,
    inspected_target_id="character_elizabeth",
)

request = narration_plan_service.voice_target_generation_request(
    selected_target,
    discovered_models,
    "en",
)
```

Operator path:

- open one project with a selected narrator
- enter `Narration Plan`
- choose the voice language
- inspect each character
- optionally reset or edit the derived voice prompt
- generate and preview the character sample
- finish when every character row reports a sample

## 9. Validation And Tests

Focused automated coverage exists in:

- `04_Software/AudioMancer/tests/test_narration_plan_service.py`
- `04_Software/AudioMancer/tests/test_narration_plan_state_service.py`
- `04_Software/AudioMancer/tests/test_narration_plan_page.py`
- `04_Software/AudioMancer/tests/test_narration_plan_ui_controller.py`
- updated workflow/config integration coverage in
  `test_config_contract.py`, `test_project_workspace_service.py`, and
  `test_main_window_project_flow.py`

Minimum validation after a change:

```powershell
uv run python -m py_compile <changed_python_files>
uv run pytest tests/test_narration_plan_service.py
uv run pytest tests/test_narration_plan_state_service.py
uv run pytest tests/test_narration_plan_page.py
uv run pytest tests/test_narration_plan_ui_controller.py
uv run ruff check <changed_python_files> --fix
uv run ruff format <changed_python_files>
```

## 10. Limitations And Future Work

- long-form generation is still out of scope
- narrator prompt editing remains on the Narrator page only
- older projects without `voice_definition_prompt` still rely on the legacy
  fallback builder until Character Discovery is rerun or the character is
  edited and saved
- per-character preview text now starts from one deterministic language-based
  sample text and can be edited per character, but it is still not populated
  automatically from real book dialogue excerpts
- future Generation should consume `60_narration_plan` directly instead of
  rebuilding voice readiness heuristically
