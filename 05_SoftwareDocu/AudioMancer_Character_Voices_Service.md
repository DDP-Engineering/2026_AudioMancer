<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Character Voices Service

## 1. Purpose

Implements the current `Character Voices` workflow in `AudioMancer`.
It prepares the narrator-plus-character voice target set for the voice language
locked on the Home page before the later `Speech Blocks`,
`Audio Blocks`, and `Audio Assembly` stages.

## 2. Responsibilities

- persist the Character Voices target list as root-level `characters_voice.json`
- prefer the character-owned `voice_definition_prompt` from `Characters` as
  the default voice-designer prompt for each character
- persist one editable per-character preview text used for sample generation
- persist per-character generated or imported samples and sample metadata in
  `narrator_and_characters` mode
- regenerate all current per-character samples as one confirmed batch operation
- mirror the selected narrator into the page as one preview-only target
- auto-copy narrator samples into all character sample slots when
  `voice_assignment_mode == "same_narrator"`
- keep `same_narrator` projects read-only for per-character voice generation
- build page state for target ordering, enablement, notes, and status lines
- keep the manifest stage and compact Character Voices operation summary aligned
  with Character Voices readiness for the Home workflow row
- apply v2 downstream impact when one voice target changes by preserving Speech
  Blocks, deleting only matching Audio Blocks and reusable clone-prompt
  metadata, and resetting Audio Assembly

It does not:

- own the selected narrator profile itself
- own the selected project voice language selector
- own global VoiceWeaver runtime settings
- implement `Speech Blocks`, `Audio Blocks`, or `Audio Assembly`

## 3. Implementation Overview

The workflow is split across:

- `04_Software/AudioMancer/src/audiomancer/services/character_voices_service.py`
  for project-local target files, synchronization, prompt persistence, sample
  persistence, and same-narrator copy behavior
- `04_Software/AudioMancer/src/audiomancer/services/character_voices_state_service.py`
  for page-state shaping from narrator selection, character discovery,
  translation readiness, and runtime capability cache
- `04_Software/AudioMancer/src/audiomancer/services/voice_sample_import_service.py`
  for WAV-only imported sample validation, minimum duration checks, and silence
  rejection
- `04_Software/AudioMancer/src/audiomancer/ui/pages/character_voices_page.py`
  for the target list, voice-language indicator, prompt editor, preview-text
  editor, and bottom status area
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/character_voices_ui_controller.py`
  for destructive edit confirmation, single and batch VoiceWeaver generation,
  preview playback, and stage plus operation-summary synchronization

High-level flow:

1. Project load refreshes read-only Character Voices indicators without
   creating `characters_voice.json`. Opening the Character Voices page
   initializes that metadata file when it does not already exist and reads the
   locked selected voice language from `project.json`.
2. The state service loads the selected narrator, discovered character
   profiles, translation report, cached VoiceWeaver models, and persisted
   Character Voices data.
3. Target synchronization keeps narrator first when selected and gives each
   discovered character one stable `character_<character_id>` target row.
4. Character default prompts use `character.voice_definition_prompt`. Target
   synchronization enforces explicit `Sex/Gender:` and `Age Domain:` sentences
   in each character prompt, using `gender_hint` and `age_hint` when available,
   a neutral non-male-default instruction when sex or gender is not specified,
   and an age-neutral adult instruction when age is not specified.
5. In `same_narrator` mode, narrator-derived character samples are copied into
   each character slot during state build and per-character editing/generation
   stays disabled.
6. `Edit Voice Prompt` confirms v2 downstream impact, deletes the stored
   character sample, removes generated Audio Blocks for that target only, resets
   Audio Assembly, and enters explicit edit mode.
7. `Import Sample` accepts one operator-selected WAV for the selected character
   target, validates that it is readable, non-silent, and at least three seconds
   long, asks for the exact spoken sample text, then stores the WAV and
   transcript in the same per-target sample slot used by generated samples.
   The read-only Narator Voice row cannot import samples from this page.
8. `Generate Sample` verifies the fixed Qwen3 capability set, waits for model
   load completion when needed, and stores one WAV plus metadata for the
   selected character target.
9. `Generate Character Samples` confirms once, selects every current character
   target, then regenerates samples sequentially in the shared modal progress
   dialog. Existing character samples are replaced by the same per-target
   storage path used by single-sample generation, and generated Audio Blocks
   tied to those targets are reset while unrelated targets are preserved.
10. When every character target plus the selected narrator sample exists, the
   controller keeps `project.json.current_stage = "character_voices_ready"` and
   writes `project.json.operations.character_voices.status = "completed"` so
   Home workflow progress reflects the generated samples.

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
- discovered character profiles from `characters_profile.json`
- translation approval report from `translation_report.json`
- cached VoiceWeaver discovery fields from `settings.json`
- Character Voices page actions:
  import sample, edit prompt, save prompt, generate one sample, regenerate all
  current character samples, preview, and stop preview

Outputs:

- `characters_voice.json`
- selected voice language read from locked `project.json.target_language` and
  mirrored `project.json.selected_voice_language`
- root-level `audio_<target_display_name>.wav` character samples
- sample metadata stored inside each `characters_voice.json` target entry
- updated manifest stage:
  `current_stage = "character_voices_ready"` when narrator plus all character
  samples exist
- updated manifest operation summary:
  `operations.character_voices.status = "completed"` with progress equal to
  narrator plus character targets when all required samples exist

## 6. Data Contracts

Character Voices target payloads use:

- `target_id`
- `target_kind`
- `display_name`
- `character_id`
- `prompt_text`
- `preview_text`
- `default_prompt_text`
- `editable`

Target rules:

- narrator target id is always `narrator`
- character target ids use `character_<character_id>`
- narrator target prompt fields are always `None` on disk
- narrator target preview text is not editable on this page
- character `default_prompt_text` is regenerated on synchronization from the
  character-owned `voice_definition_prompt`
- character `prompt_text` is preserved unless explicitly edited, except that
  synchronization backfills mandatory sex/gender and age-domain guidance when
  an existing prompt lacks it
- new character targets prefer the Character Discovery `preview_text` handoff
  when available, so samples start from source dialogue spoken by that
  character
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
- `source_file_name`
- `audio_validation`
- `runtime_result_summary`

Generated samples use `sample_source = "voice_designer"`. Imported samples use
`sample_source = "imported_sample"` and `generation_mode = "imported_sample"`;
their `source_model_id` is `None` because Audio Blocks later creates the Qwen
Base clone prompt directly from the stored WAV plus transcript.

Same-narrator copied sample metadata uses:

- `sample_source = "copied_narrator"`
- `copied_from_target_id = "narrator"`

When same-narrator mode copies from `narator_sample.json`, the source narrator
sample may use the compact Narator Voice schema (`source_kind`) or legacy
selected-sample source keys (`generation_mode`, `sample_source`). Character
Voices writes its own target metadata using the Character Voices contract above
and does not persist sample audit timestamps or `stale`; changing a character
voice prompt clears the affected sample instead.

## 7. Workflow Integration

This workflow sits immediately after `Narator Voice` in the current stage
order.

Upstream integrations:

- selected narrator state from `narator.json` and narrator sample artifacts
  from `narator.wav` plus `narator_sample.json`
- project-local `voice_assignment_mode` from `project.json`
- character discovery artifacts from `characters_profile.json`, including the
  compact sex/gender guidance, compact age-domain guidance, and final
  `voice_definition_prompt`
- translation approval state from `translation_report.json`

Downstream integrations:

- `Speech Blocks`, which reads the selected project voice language and is
  invalidated when that language changes
- `Audio Blocks` workflow data
- `Audio Assembly` workflow data

Current rules:

- the selected voice language is displayed as a read-only indicator; the
  editable project language is locked on the Home page before source import
- the supported voice-language set offers English, Romanian, Japanese, Korean,
  Chinese, German, French, Russian, Portuguese, Spanish, and Italian
- changing the selected voice language is not part of the normal workflow after
  project locking
- narrator is visible on the page but remains preview-only
- character editing and generation are enabled only in
  `narrator_and_characters` mode
- batch sample generation processes every current character target and replaces
  any existing character sample for those targets
- sample import, prompt edit, single sample regeneration, and batch character
  sample generation preserve Speech Blocks and reset only Audio Blocks whose
  `voice_target_id` matches the affected character targets
- `same_narrator` mode disables prompt editing and generation but keeps
  preview available by copying narrator-derived samples into every character
  target slot
- entering the page with a selected narrator that still lacks a generated
  sample shows one blocking warning popup per page entry

## 8. Usage

Representative service calls:

```python
voice_targets = character_voices_service.sync_voice_plan(
    project_root,
    character_profiles,
    selected_narrator_profile,
)

state = character_voices_state_service.build_character_voices_state(
    project_root,
    manifest,
    "en",
    settings_payload,
    inspected_target_id="character_elizabeth",
)

request = character_voices_service.voice_target_generation_request(
    selected_target,
    discovered_models,
    "en",
)
```

Operator path:

- open one project with a selected narrator
- enter `Character Voices`
- confirm the voice language shown from `Narator Voice`
- inspect each character
- optionally edit the derived voice prompt
- import, generate, and preview the character sample
- finish when every character row reports a sample

## 9. Validation And Tests

Documentation audit status:

- reviewed against the current implementation on 2026-05-15
- same-narrator compact narrator sample compatibility reviewed on 2026-05-18

Focused automated coverage exists in:

- `04_Software/AudioMancer/tests/test_character_voices_service.py`
- `04_Software/AudioMancer/tests/test_character_voices_state_service.py`
- `04_Software/AudioMancer/tests/test_character_voices_page.py`
- `04_Software/AudioMancer/tests/test_character_voices_ui_controller.py`
- updated workflow/config integration coverage in
  `test_config_contract.py`, `test_project_workspace_service.py`, and
  `test_main_window_project_flow.py`

Minimum validation after a change:

```powershell
uv run python -m py_compile <changed_python_files>
uv run pytest tests/test_character_voices_service.py
uv run pytest tests/test_character_voices_state_service.py
uv run pytest tests/test_character_voices_page.py
uv run pytest tests/test_character_voices_ui_controller.py
uv run ruff check <changed_python_files> --fix
uv run ruff format <changed_python_files>
```

## 10. Limitations And Future Work

- long-form audio creation is handled by Audio Blocks and Audio Assembly
- narrator prompt editing remains on the `Narator Voice` page only
- character discovery is expected to provide the current `voice_definition_prompt`
  for each persisted profile
- per-character preview text still starts from a deterministic localized
  sample text instead of automatically using real dialogue excerpts
- Character Voices does not regenerate Speech Blocks; it only invalidates the
  downstream generated audio tied to changed voice targets
