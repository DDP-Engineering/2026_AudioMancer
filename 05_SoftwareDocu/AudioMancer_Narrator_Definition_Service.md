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
state, internal locked project voice-language use, AI-generated text-only profile
suggestions, per-profile sample artifacts, localized preview text, and the
runtime-aware state shaping used by the Narator Voice page.

## 2. Responsibilities

- persist operator-created and AI-generated custom profiles in root-level
  `audio_profiles.json`
- append AI-generated text-only narrator profiles while preserving existing
  profiles and deferring all audio/sample work to explicit operator actions
- persist the explicitly selected narrator profile and narrator language
  runtime code
- read the locked project voice language from `project.json.target_language`
  for narrator samples, generated profile suggestions, and preview defaults
- persist one generated or imported narrator WAV per narrator profile so
  multiple profiles can be previewed later without regenerating audio
- localize the default narrator preview text for supported voice languages
- store compact per-profile sample metadata in each profile's `sample` payload
- keep explicit selection state in `narator.json` and the selected-sample copy
  in `narator_sample.json`
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
  for profile persistence, selection state, internal locked project-language use,
  localized preview text, and sample
  artifact helpers
- `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_state_service.py`
  for Narator Voice page state shaping, internal project-language resolution, and
  runtime-derived flags
- `04_Software/AudioMancer/src/audiomancer/services/voice_sample_import_service.py`
  for WAV-only imported sample validation, minimum duration checks, and silence
  rejection
- `04_Software/AudioMancer/src/audiomancer/services/narrator_profile_generation_service.py`
  for AI-assisted text-only profile suggestions, report/state sidecars, and
  source-text analysis
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py`
  for Qt actions, destructive edit/sample confirmations, manifest summary sync,
  VoiceWeaver sample generation, and preview playback
- `04_Software/AudioMancer/src/audiomancer/ui/pages/narator_voice_page.py`
  for the project-aware editor, AI profile selector, profile list, and bottom
  status panel

High-level flow:

1. Project load refreshes Narator Voice state without creating
   narrator metadata. Opening the Narator Voice page initializes
   `audio_profiles.json`, `narator.json`, root-level narrator sample paths, and
   the required narrator-related `project.json` fields when they do not already
   exist.
2. The state service loads all stored profiles, the explicit selected narrator
   state, locked project options, and the cached runtime discovery models.
3. The selected voice language is resolved from the locked
   `project.json.target_language`, then applied to narrator profile generation
   requests and default preview text.
4. Each profile row is enriched for UI use with `has_sample`,
   `runtime_available`, `can_generate`, `can_select`, and an operator-facing
   availability note; persisted profiles do not store UI selection flags.
5. `Edit Profile` shows a destructive confirmation, deletes the current
   per-profile sample, clears explicit selection when necessary, and only then
   unlocks the page editor.
6. `Generate Sample` re-probes runtime readiness, requires the fixed Qwen3 TTS
   Base and Voice Designer capability set (`base`, `voice_designer`), waits for
   model-load completion before submitting Voice Designer generation, stores or
   replaces only the current profile's `audio_narator_<profile>.wav`, keeps
   other profile samples intact, and uses the saved TTS preview timeout.
7. `Import Sample` accepts one operator-selected WAV for the inspected profile,
   validates that it is readable, non-silent, and at least three seconds long,
   asks for the exact spoken sample text, then stores the WAV and transcript in
   the same per-profile sample slot. Imported samples are clone-ready without a
   Voice Designer `source_model_id` because Audio Blocks later creates Qwen Base
   clone prompts directly from the WAV plus transcript.
8. `Select` persists `narator.json`, copies the chosen profile sample to
   `narator.wav` and `narator_sample.json`, and updates the compact manifest
   summary.
9. `Preview` plays the stored per-profile WAV locally through Qt media
   playback.
10. `Generate Narator Profiles` runs the AI profile-generation service through
    the shared threaded progress dialog, resumes compatible unfinished
    style-analysis checkpoints, appends validated editable text profiles, keeps
    AI logs/report/state sidecars intact, and leaves narrator selection
    unchanged.

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
  create, edit, save, delete, generate sample, import sample, preview, and
  explicit select
- narrator editor fields:
  display name, prompt text, and preview text

Outputs:

- `audio_profiles.json`
- `narator_profile_generation_report.json`
- `narator_profile_generation_state.json`
- `narator.json`
- selected voice language read from `project.json.selected_voice_language`,
  which is mirrored from locked `project.json.target_language`
- `audio_narator_<profile>.wav`
- `narator.wav` and `narator_sample.json` selected-sample copies for the
  explicit narrator selection
- compact per-profile `sample` entries stored inside `audio_profiles.json`
- updated manifest summary fields:
  `narrator_profile_name`
  `narrator_language`
  `voice_assignment_mode`
  `current_stage = "narrator_definition_ready"`
- updated `project.json.operations.narrator_definition` summary when an
  explicit narrator profile is selected, so reopening the project does not
  require manifest repair for a valid selected narrator

## 6. Data Contracts

Narrator profile payloads currently use:

- `profile_id`
- `display_name`
- `language`
- `prompt_text`
- `preview_text`
- `sample`
- `updated_at`

Profile rules:

- user-created and AI-generated profiles share the same compact profile shape
- generated suggestions remain editable by current workflow rules and have
  `sample = null` until the operator explicitly generates or imports a sample
- no narrator profile is selected by default for a new project
- stored profile `language` values use VoiceWeaver language codes such as `en`
  and `ro`; operator-facing labels are normalized when profile actions provide
  them
- supported voice languages are English, Romanian, Japanese, Korean, Chinese,
  German, French, Russian, Portuguese, Spanish, and Italian
- the default narrator preview text is localized for every supported voice
  language

Selected narrator state uses:

- `selected_profile_id`
- `selected_language`

`selected_language` also uses the normalized runtime language-code contract.

Per-profile sample metadata uses:

- `source_kind`
- `preview_text`
- `language`
- `source_model_id`
- `created_at`
- `source_file_name`

Generated samples use `source_kind = "voice_designer"`. Imported samples use
`source_kind = "imported_sample"` and set `source_model_id = None`.
`source_file_name` is present only for imported samples.

Selected narrator metadata in `narator_sample.json` mirrors the compact
per-profile sample metadata and adds:

- `profile_id`
- `selected_at`

Legacy projects that still contain `sample_metadata`, `sample_audio_path`,
`sample_source`, `generation_mode`, `generated_at`, or `imported_at` are read
compatibly and normalized to the compact `sample` contract when profiles are
loaded. Existing display-name-based `audio_narator_<name>.wav` files remain
discoverable until a later sample replacement writes the current
profile-id-based path, and legacy selected-sample JSON remains readable by
downstream workflows through the compact selected-sample return shape.

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
  minimum Qwen3 TTS Base and Voice Designer capability set and the profile
  resolves to `voice/design`
- the Narator Voice page does not display language indicators; the project
  language remains visible on Home and is still used internally by narrator
  operations
- changing the selected voice language is not part of the normal workflow after
  Home-page project locking
  state because those artifacts depend on the selected output language
- narrator profiles are operator-created and deletable unless another workflow
  state disables editing
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
- AI-generated narrator profile suggestions can be appended repeatedly; the
  service validates the requested count and male/female allocation before
  writing profiles and adds suffixes for display-name collisions with existing
  profiles
- AI narrator generation provenance, resume checkpoints, token usage, and raw
  AI transaction logs remain in
  `narator_profile_generation_report.json`,
  `narator_profile_generation_state.json`, and the project AI log files rather
  than being duplicated into each generated profile

## 8. Usage

Representative service calls:

```python
profiles = narrator_definition_service.load_profiles(project_root)
selected_state = narrator_definition_service.load_selected_profile_state(project_root)
tts_plan = narrator_definition_service.load_tts_plan(project_root, discovered_models)

generated_report = narrator_profile_generation_service.generate_narrator_profiles(
    project_root,
    manifest,
    ai_profile_payload,
    profile_count=6,
    voice_language="en",
    preview_text_character_limit=512,
)

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
- create one custom narrator profile
- or choose an AI profile and press `Generate Narator Profiles` to append
  editable text-only suggestions
- review the locked voice language chosen on the Home page
- optionally edit one profile after confirming the destructive sample reset
- generate one sample for a narrator profile
- preview the stored WAV locally
- press `Select` to make that profile the explicit narrator for the project

## 9. Validation And Tests

Documentation audit status:

- reviewed against the current implementation on 2026-05-06
- compact narrator profile/sample metadata contract reviewed on 2026-05-18
- legacy narrator sample read-compatibility reviewed on 2026-05-18
- legacy selected-sample normalization reviewed on 2026-05-18

Focused automated coverage includes:

- `04_Software/AudioMancer/tests/test_narrator_definition_service.py`
- `04_Software/AudioMancer/tests/test_narrator_definition_state_service.py`
- `04_Software/AudioMancer/tests/test_narrator_profile_generation_service.py`
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
- selected narrator samples are still copied to `narator.wav` and
  `narator_sample.json` so downstream workflows can consume one stable selected
  narrator artifact
