<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Narrator Definition Service

## 1. Purpose

Implements the narrator-definition persistence and state contract for the
current `Narator Voice` workflow in `AudioMancer`.
It owns the project-local narrator profile catalog, explicit selected narrator
state, locked project voice-language display, per-profile sample artifacts,
localized preview text, and the runtime-aware state shaping used by the Narator
Voice page.

## 2. Responsibilities

- seed one fixed built-in Qwen3 preset catalog (`vivian`, `serena`, `anna`)
  for new or repaired projects
- restore missing built-in Qwen3 presets automatically when one project is
  loaded
- sync additional Qwen3 CustomVoice presets reported by the current runtime
  into the stored project profile catalog without marking them as protected
  built-ins
- migrate legacy `qwen3_tts_customvoice_seed` prompt-seed entries into
  editable custom narrator profiles so they remain generatable and deletable
- persist built-in presets and custom user profiles in root-level
  `audio_profiles.json`
- persist the explicitly selected narrator profile and narrator language
  runtime code
- read the locked project voice language from `project.json.target_language`
  and expose it as a read-only indicator on the Narator Voice page
- persist one generated narrator WAV per narrator profile so multiple profiles
  can be previewed later without regenerating audio
- localize the default narrator preview text for supported voice languages
- record selected-sample state in each profile's `sample_metadata`
- derive Narator Voice page enablement for `Generate Sample`, `Select`, and
  `Preview` from the cached VoiceWeaver runtime state and stored sample
  metadata
- clear sample and selection state immediately when one profile enters edit
  mode

It does not:

- own the global VoiceWeaver connection fields in `settings.json`
- perform the HTTP calls to VoiceWeaver directly
- own the per-character prompt and sample workflow now handled by
  `Character Voices`

## 3. Implementation Overview

The workflow is split across:

- `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_service.py`
  for profile persistence, selection state, locked project-language display,
  localized preview text, and sample
  artifact helpers
- `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_state_service.py`
  for Narator Voice page state shaping, project-language display, and
  runtime-derived flags
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py`
  for Qt actions, destructive edit/sample confirmations, manifest summary sync,
  VoiceWeaver sample generation, and preview playback
- `04_Software/AudioMancer/src/audiomancer/ui/pages/narator_voice_page.py`
  for the project-aware editor, read-only original/translated/voice-language
  display, profile list, and bottom status panel

High-level flow:

1. Project load refreshes read-only Narator Voice indicators without creating
   narrator metadata. Opening the Narator Voice page initializes
   `audio_profiles.json`, `narator.json`, root-level narrator sample paths, and
   the required narrator-related `project.json` fields when they do not already
   exist.
2. The state service loads all stored profiles, the explicit selected narrator
   state, locked project options, and the cached runtime discovery models.
3. The selected voice language is resolved from the locked
   `project.json.target_language`, then applied to narrator profile generation
   requests and default preview text.
4. Each profile is enriched with `is_selected`, `has_sample`,
   `runtime_available`, `can_generate`, `can_select`, and an operator-facing
   availability note.
4.1. When the cached runtime reports additional Qwen3 CustomVoice presets,
     those presets are added to the project profile catalog as runtime preset
     entries and remain non-protected.
4.2. When one project still contains legacy `qwen3_tts_customvoice_seed`
     prompt-seed presets without a speaker id, those entries are repaired into
     editable custom narrator profiles during profile load.
5. `Edit Profile` shows a destructive confirmation, deletes the current
   per-profile sample, clears explicit selection when necessary, and only then
   unlocks the page editor.
6. `Generate Sample` re-probes runtime readiness, requires the fixed minimum
   Qwen3 capability set (`base`, `voice_designer`, `custom_voice`), waits for
   model-load completion before submitting generation, stores or replaces only
   the current profile's `audio_narator_<profile>.wav`, keeps other profile
   samples intact, uses the saved TTS preview timeout, and marks the generated
   sample metadata as selected when the regenerated profile is already selected.
7. The legacy voice-language change handler is a no-op for locked projects;
   the normal workflow changes language only by creating a new project.
8. `Select` persists `narator.json`, updates the compact manifest summary,
   and marks the chosen profile sample metadata as selected.
9. `Preview` plays the stored per-profile WAV locally through Qt media
   playback.

## 4. Dependencies

- Internal dependencies:
  `04_Software/AudioMancer/src/audiomancer/config.py`
  `04_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/home_presenter_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/settings_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/voiceweaver_runtime_service.py`
  `04_Software/AudioMancer/src/audiomancer/ui/controllers/misc_ui_controller.py`
  `04_Software/AudioMancer/src/audiomancer/ui/main_window.py`
- External dependencies:
  `PySide6`
  local `VoiceWeaver` runtime reachable over HTTP for sample generation

## 5. Inputs And Outputs

Inputs:

- active project root and manifest
- cached runtime discovery fields from `settings.json`
- locked project options from `project.json.target_language` and
  `project.json.voice_assignment_mode`
- Narator Voice page actions:
  create, edit, save, delete, generate sample, preview, and explicit select
- narrator editor fields:
  display name, prompt text, and preview text

Outputs:

- `audio_profiles.json`
- `narator.json`
- selected voice language read from `project.json.selected_voice_language`,
  which is mirrored from locked `project.json.target_language`
- `audio_narator_<profile>.wav`
- `narator.wav` and `narator_sample.json` selected-sample copies for the
  explicit narrator selection
- per-profile `sample_audio_path` and `sample_metadata` entries stored inside
  `audio_profiles.json`
- updated manifest summary fields:
  `narrator_profile_name`
  `narrator_language`
  `voice_assignment_mode`
  `current_stage = "narrator_definition_ready"`

## 6. Data Contracts

Narrator profile payloads currently use:

- `profile_id`
- `display_name`
- `language`
- `prompt_text`
- `preview_text`
- `profile_kind`
- `speaker_id`
- `source_model_id`
- `profile_origin`
- `provider_family`
- `editable`
- `protected`
- `is_selected`
- `sample_audio_path`
- `sample_metadata`
- `updated_at`

Profile rules:

- built-in seeded presets use
  `profile_kind = "preset"` and `profile_origin = "qwen_builtin_preset"`
- runtime-synced Qwen presets use
  `profile_kind = "preset"` and `profile_origin = "qwen_runtime_preset"`
- user-created profiles use
  `profile_kind = "custom"` and `profile_origin = "custom_user"`
- migrated legacy prompt-seed presets use
  `profile_kind = "custom"` and
  `profile_origin = "legacy_customvoice_seed"`
- no narrator profile is selected by default for a new project
- stored profile `language` values use VoiceWeaver language codes such as `en`
  and `ro`; legacy labels are normalized on load
- supported voice languages are English, Romanian, Japanese, Korean, Chinese,
  German, French, Russian, Portuguese, Spanish, and Italian
- the default narrator preview text is localized for every supported voice
  language

Selected narrator state uses:

- `selected_profile_id`
- `selected_language`

`selected_language` also uses the normalized runtime language-code contract.

Per-profile sample metadata uses:

- `profile_id`
- `is_selected`
- `display_name`
- `profile_kind`
- `profile_origin`
- `source_model_id`
- `speaker_id`
- `generation_mode`
- `language`
- `prompt_text`
- `preview_text`
- `generated_at`
- `runtime_result_summary`

Selected narrator metadata mirrors the per-profile metadata and
adds:

- `role = "narrator"`
- `selected_at`

## 7. Workflow Integration

This workflow sits after Character Discovery in the current stage order, but it
can already be prepared locally once a source document exists.

Upstream integrations:

- `MainWindow.show_project_state(...)`
- `TTS Settings` persistence in
  `04_Software/AudioMancer/src/audiomancer/ui/controllers/tts_settings_ui_controller.py`
- VoiceWeaver runtime discovery cached in `settings.json`

Downstream integrations:

- `Character Voices`, which consumes the explicit selected narrator state plus
  the root-level selected `narator.wav` and `narator_sample.json`
- future narration generation that will consume the same selected narrator
  contract together with `characters_voice.json`

Current runtime-aware rules:

- all stored narrator profiles remain visible in the page list
- switching the inspected profile in the page list rebuilds the Narator Voice page
  state, so operator actions always reflect the currently highlighted profile
- `Generate Sample` is enabled only when the current runtime exposes the fixed
  minimum Qwen3 capability set and the profile resolves to either
  `voice/design` or `voice/custom`
- the voice-language control on Narator Voice is a read-only locked project
  indicator
- changing the selected voice language is not part of the normal workflow after
  Home-page project locking
  state because those artifacts depend on the selected output language
- only the three fixed seeded Qwen presets are protected from deletion;
  runtime-synced presets and migrated legacy prompt-seed profiles are not
- runtime requests use VoiceWeaver language codes even when operator-facing
  labels such as `English` or `Romanian` are shown in the UI or manifest,
  except Romanian TTS requests intentionally omit the outbound `language`
  field so the runtime can infer pronunciation from the text
- the Voice Designer Prompt and Preview Text editors expose vertical scrollbars
- Preview Text is capped by the global TTS preview text limit, defaulting to
  512 characters
- `Select` requires an existing per-profile sample and is disabled for the
  already selected profile
- `Preview` requires a stored per-profile sample and plays the currently
  inspected profile's WAV, so switching profiles can preview each saved sample
  without regenerating audio
- entering edit mode clears any existing sample for that profile and also
  clears explicit selection if the edited profile had been selected

## 8. Usage

Representative service calls:

```python
profiles = narrator_definition_service.load_profiles(project_root)
selected_state = narrator_definition_service.load_selected_profile_state(project_root)
tts_plan = narrator_definition_service.load_tts_plan(project_root, discovered_models)

custom_profile = narrator_definition_service.create_custom_profile(
    project_root,
    "Warm Story Voice",
    "English",
    "Warm reflective narrator prompt.",
)

request = narrator_definition_service.profile_generation_request(
    custom_profile,
    tts_plan,
    discovered_models,
)
```

Operator path:

- open one project
- run `TTS Settings -> Test Connection`
- inspect the seeded Qwen3 presets or create additional custom profiles
- review the locked voice language chosen on the Home page
- optionally edit one profile after confirming the destructive sample reset
- generate one sample for a narrator profile
- preview the stored WAV locally
- press `Select` to make that profile the explicit narrator for the project

## 9. Validation And Tests

Focused automated coverage includes:

- `04_Software/AudioMancer/tests/test_narrator_definition_service.py`
- `04_Software/AudioMancer/tests/test_narrator_definition_state_service.py`
- `04_Software/AudioMancer/tests/test_narator_voice_page.py`
- `04_Software/AudioMancer/tests/test_narator_voice_ui_controller.py`
- narrator integration checks in
  `04_Software/AudioMancer/tests/test_main_window_project_flow.py`

Minimum validation after changes:

- `uv run python -m py_compile` for changed narrator and runtime files
- focused narrator `pytest` runs
- changed-file `ruff check` and `ruff format`

## 10. Limitations And Future Work

- sample generation uses fixed Qwen3 capability families and does not expose
  operator model-role overrides anymore
- preview playback is local only and does not stream directly from VoiceWeaver
- runtime availability depends on the last saved discovery cache, not an
  automatic background probe at page load
- selected narrator samples are referenced from profile-owned artifacts instead
  of a duplicated selected-audio copy
