<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Narration Plan Page Implementation Plan

## Summary

Implement the placeholder `Narration Plan` page as a full workflow step that
prepares the narrator plus all discovered character voices for future book
generation.

Recommended implementation model:

- `gpt-5.4`
- reasoning level: `high`

Primary outcome:

- the page lists the selected narrator plus all discovered characters
- the operator can prepare per-character voice prompts and per-character
  samples
- the page supports explicit voice-language selection
- `same_narrator` mode auto-populates all character samples from the selected
  narrator sample
- the workflow persists enough state for a later Generation page to consume
  directly

## Implementation Scope

### Workflow model and project structure

- add `60_narration_plan`
- add `narration_plan_ready` after `narrator_definition_ready`
- preserve narration-plan data during project repair when the current stage is
  already `narration_plan_ready`
- keep `project.json.voice_assignment_mode` as the source of truth for voice
  assignment behavior

### Persistence and contracts

Persist narration-plan data under `60_narration_plan`:

- `voice_plan.json`
- `selected_voice_language.json`
- `audio_samples/<target_id>.wav`
- `audio_samples/<target_id>.json`

Narrator target rules:

- stable target id: `narrator`
- visible on the page
- preview only
- no prompt editing or sample generation on this page

Character target rules:

- stable target id format: `character_<character_id>`
- derived default prompt is rebuilt from the latest character profile
- stored prompt is preserved until explicit reset
- stored sample is deleted when the operator enters prompt edit mode

### Page behavior

The page must:

- show the selected narrator plus every discovered character
- show sample-present vs sample-missing status per row
- show original language always
- show translated language as selectable only when translation exists and all
  chunks are approved
- persist one selected voice language for character generation
- show totals and sample counts in the bottom status area
- use Narrator-style progress dialog behavior for character sample generation

### Voice assignment behavior

For `narrator_and_characters`:

- character prompts can be reset, edited, saved, and generated
- character samples can be previewed or stopped

For `same_narrator`:

- character prompts remain read-only
- reset, edit, save, and generate are disabled
- character preview remains enabled
- narrator sample is copied into each character sample slot

### Missing narrator sample behavior

When the selected narrator has no generated sample and the page is entered:

- show a warning popup once per page entry
- explain that the narrator sample must be generated on the Narrator page first

## Implementation Detail

### New service layer

- `narration_plan_service.py`
  owns `60_narration_plan` persistence, prompt derivation, selected voice
  language, target sample storage, and same-narrator copy behavior
- `narration_plan_state_service.py`
  builds page state from narrator selection, character profiles, translation
  approval state, and cached VoiceWeaver discovery results

### UI integration

- replace the placeholder page with `NarrationPlanPage`
- add `narration_plan_ui_controller.py`
- wire the page and controller into `MainWindow`
- use a dedicated local preview player for narration-plan playback

### Prompt derivation

Derived prompts are deterministic and local:

- character name
- gender hint
- age band
- role summary
- description
- temperament
- social status
- speaking style
- accent or dialect hints
- voice notes

No AI prompt-building is used in this v1.

## Validation Targets

Focused automated coverage should include:

- narration-plan persistence helpers
- narration-plan state shaping
- narration-plan page widget behavior
- narration-plan UI controller edit and warning flows
- workflow config and project repair integration
- main-window home-stage rendering for `Narration Plan`

Minimum validation after implementation:

```powershell
uv run python -m py_compile <changed_python_files>
uv run pytest tests/test_narration_plan_service.py
uv run pytest tests/test_narration_plan_state_service.py
uv run pytest tests/test_narration_plan_page.py
uv run pytest tests/test_narration_plan_ui_controller.py
uv run ruff check <changed_python_files> --fix
uv run ruff format <changed_python_files>
```

## Out Of Scope

- long-form audio generation
- generation-page consumption of narration-plan state
- export workflow

