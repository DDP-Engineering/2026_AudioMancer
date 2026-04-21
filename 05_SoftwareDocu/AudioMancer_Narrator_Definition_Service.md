<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Narrator Definition Service

## 1. Purpose

Implements the current Narrator workflow in `AudioMancer`.
It owns the project-local narrator profile catalog, explicit selected narrator
state, per-profile sample artifacts, and the runtime-aware state shaping used
by the Narrator page.

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
- persist built-in presets and custom user profiles under
  `50_narrator_definition`
- persist the explicitly selected narrator profile and narrator language
  runtime code
- persist per-profile WAV and JSON sample artifacts
- persist the project-root selected narrator audio copy under `audio_samples/`
- derive narrator-page enablement for `Generate Sample`, `Select`, and
  `Preview` from the cached VoiceWeaver runtime state and stored sample
  metadata
- clear sample and selection state immediately when one profile enters edit
  mode

It does not:

- own the global VoiceWeaver connection fields in `settings.json`
- perform the HTTP calls to VoiceWeaver directly
- own the per-character prompt and sample workflow now handled by
  `Narration Plan`

## 3. Implementation Overview

The workflow is split across:

- `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_service.py`
  for profile persistence, selection state, `project.json`-backed simplified
  TTS plan persistence,
  and sample artifact helpers
- `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_state_service.py`
  for Narrator page state shaping, project-language display, and runtime-derived
  flags
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/narrator_ui_controller.py`
  for Qt actions, destructive edit/sample confirmations, manifest summary sync,
  VoiceWeaver sample generation, and preview playback
- `04_Software/AudioMancer/src/audiomancer/ui/pages/narrator_page.py`
  for the project-aware editor, read-only language display, profile list, and
  bottom status panel

High-level flow:

1. Project load ensures `profiles.json`, `selected_profile.json`,
   `50_narrator_definition/audio_samples/`, the project root `audio_samples/`,
   and the required narrator-related `project.json` fields exist.
2. The state service loads all stored profiles, the explicit selected narrator
   state, the project TTS plan, and the cached runtime discovery models.
3. Each profile is enriched with `is_selected`, `has_sample`,
   `runtime_available`, `can_generate`, `can_select`, and an operator-facing
   availability note.
4.1. When the cached runtime reports additional Qwen3 CustomVoice presets,
     those presets are added to the project profile catalog as runtime preset
     entries and remain non-protected.
4.2. When one project still contains legacy `qwen3_tts_customvoice_seed`
     prompt-seed presets without a speaker id, those entries are repaired into
     editable custom narrator profiles during profile load.
4. `Edit Profile` shows a destructive confirmation, deletes the current
   per-profile sample, clears explicit selection when necessary, and only then
   unlocks the page editor.
5. `Generate Sample` re-probes runtime readiness, requires the fixed minimum
   Qwen3 capability set (`base`, `voice_designer`, `custom_voice`), waits for
   model-load completion before submitting generation, stores `<profile_id>.wav`
   and `<profile_id>.json`, uses the saved TTS preview timeout, and refreshes
   `audio_samples/narrator.wav` plus `audio_samples/narrator.json` only when
   the regenerated profile is already selected.
6. `Select` persists `selected_profile.json`, updates the compact manifest
   summary, and copies the chosen profile sample into the project-root narrator
   sample folder.
7. `Preview` plays the stored per-profile WAV locally through Qt media
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
- active project TTS plan from `project.json.voice_assignment_mode`
- narrator page actions:
  create, edit, save, delete, generate sample, preview, and explicit select
- narrator editor fields:
  display name, prompt text, and preview text

Outputs:

- `50_narrator_definition/profiles.json`
- `50_narrator_definition/selected_profile.json`
- `50_narrator_definition/audio_samples/<profile_id>.wav`
- `50_narrator_definition/audio_samples/<profile_id>.json`
- `audio_samples/narrator.wav`
- `audio_samples/narrator.json`
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

Selected narrator state uses:

- `selected_profile_id`
- `selected_language`

`selected_language` also uses the normalized runtime language-code contract.

Per-profile sample metadata uses:

- `profile_id`
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

Project-root selected narrator metadata mirrors the per-profile metadata and
adds:

- `role = "narrator"`
- `selected_profile_id`
- `copied_at`

## 7. Workflow Integration

This workflow sits after Character Discovery in the current stage order, but it
can already be prepared locally once a source document exists.

Upstream integrations:

- `MainWindow.show_project_state(...)`
- `TTS Settings` persistence in
  `04_Software/AudioMancer/src/audiomancer/ui/controllers/tts_settings_ui_controller.py`
- VoiceWeaver runtime discovery cached in `settings.json`

Downstream integrations:

- `Narration Plan`, which consumes the explicit selected narrator state plus
  `audio_samples/narrator.wav` and `audio_samples/narrator.json`
- future narration generation that will consume the same selected narrator
  contract together with `60_narration_plan`

Current runtime-aware rules:

- all stored narrator profiles remain visible in the page list
- switching the inspected profile in the page list rebuilds the Narrator page
  state, so operator actions always reflect the currently highlighted profile
- `Generate Sample` is enabled only when the current runtime exposes the fixed
  minimum Qwen3 capability set and the profile resolves to either
  `voice/design` or `voice/custom`
- only the three fixed seeded Qwen presets are protected from deletion;
  runtime-synced presets and migrated legacy prompt-seed profiles are not
- runtime requests use VoiceWeaver language codes even when operator-facing
  labels such as `English` or `Romanian` are shown in the UI or manifest
- `Select` requires an existing per-profile sample and is disabled for the
  already selected profile
- `Preview` requires a stored per-profile sample
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
- optionally edit one profile after confirming the destructive sample reset
- generate one sample for a narrator profile
- preview the stored WAV locally
- press `Select` to make that profile the explicit narrator for the project

## 9. Validation And Tests

Focused automated coverage includes:

- `04_Software/AudioMancer/tests/test_narrator_definition_service.py`
- `04_Software/AudioMancer/tests/test_narrator_definition_state_service.py`
- `04_Software/AudioMancer/tests/test_narrator_page.py`
- `04_Software/AudioMancer/tests/test_narrator_ui_controller.py`
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
- only narrator samples are copied to the project-root `audio_samples/` folder
  today; character sample routing is still future work
