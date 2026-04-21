<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer TTS Settings And VoiceWeaver Runtime

## 1. Purpose

Provides the operator-facing `TTS Settings` dialog and the underlying
VoiceWeaver runtime integration used to discover local TTS capabilities and to
support narrator sample generation.

It separates:

- global runtime connection and discovery cache in `settings.json`
- project-local narrator planning under `project.json.voice_assignment_mode`

## 2. Responsibilities

- probe the local VoiceWeaver runtime through `/v1/health`, `/v1/models`, and
  `/v1/status`
- expose the current VoiceWeaver REST surface used by AudioMancer, including
  `/v1/server`, `/v1/model-catalog`, `/v1/models/unload`,
  `/v1/models/rescan`, `/v1/models/download`, `/v1/models/download/status`,
  `/v1/models/download/cancel`, and `DELETE /v1/models/{model_id}`
- normalize discovered runtime models into one capability matrix, including
  normalized generation-mode aliases and `default_model_parameters`
- persist runtime connection fields and the most recent discovery cache in
  `settings.json`
- expose one static `TTS Settings` dialog beside `AI Settings`
- persist the project-local TTS plan for one active project
- classify fixed Qwen3 narrator-generation readiness from the discovered
  runtime models
- load VoiceWeaver models on demand for narrator sample generation
- submit `voice/custom` and `voice/design` generation requests
- poll runtime status and download generated audio bytes

It does not:

- own narrator profile persistence beyond the project TTS plan contract
- own local WAV playback once the audio has been downloaded

## 3. Implementation Overview

The component is implemented in:

- `src/audiomancer/services/voiceweaver_runtime_service.py`
- `src/audiomancer/ui/pages/tts_settings_page.py`
- `src/audiomancer/ui/controllers/tts_settings_ui_controller.py`
- dialog wiring in `src/audiomancer/ui/main_window.py`
- settings persistence updates in `src/audiomancer/services/settings_service.py`

High-level flow:

1. The operator opens `TTS Settings` from the main toolbar.
2. The page loads global runtime fields from `settings.json`.
3. If a project is active, the page also loads `project.json.voice_assignment_mode`.
4. `Test Connection` probes VoiceWeaver and refreshes the cached discovered
   model list plus the fixed Qwen3 capability matrix.
5. The page rebuilds:
   - the discovered-model list
   - the capability matrix
   - the operator-facing connection status label
   - the project-local planning note
6. `Save TTS Settings` writes global runtime fields through the shared settings
   service and writes the project-local TTS plan when a project is open.
7. The Narrator workflow later reuses the same service to load models, poll
   `/v1/status` until the load reaches a terminal state, submit generation,
   poll again, and download `/v1/voice`.

## 4. Dependencies

- Internal dependencies:
  `audiomancer.config`
  `audiomancer.services.settings_service`
  `audiomancer.services.narrator_definition_service`
  `audiomancer.services.ui_state_service`
  `audiomancer.ui.controllers.settings_ui_controller`
  `audiomancer.ui.controllers.misc_ui_controller`
  `audiomancer.ui.main_window.MainWindow`
- External dependencies:
  Python standard library `urllib`
  `PySide6`
  local `VoiceWeaver` runtime reachable over HTTP

## 5. Inputs And Outputs

Inputs:

- `tts_runtime_base_url`
- `tts_runtime_api_key`
- cached runtime discovery fields in `settings.json`
- current active project root, when available

Outputs:

- updated runtime fields in `settings.json`
- updated `project.json.voice_assignment_mode` for the active project
- popup feedback for successful or failed runtime probes
- a discovered-model list rendered in the dialog
- normalized load or generation results returned to the Narrator controller
- downloaded WAV bytes for narrator sample storage

## 6. Data Contracts

Global `settings.json` fields:

- `tts_runtime_base_url`
- `tts_runtime_api_key`
- `tts_runtime_probe_succeeded`
- `tts_runtime_probe_message`
- `tts_runtime_discovered_models`
- `tts_runtime_active_model_id`
- `tts_runtime_device_diagnostics`
- `tts_audio_preview_timeout_seconds`
- `tts_audio_generation_timeout_seconds`

Normalized discovered-model payloads keep:

- `model_id`
- `backend_name`
- `status`
- `supported_generation_modes`
- `supported_languages`
- `supported_presets`
- `speaker_count`
- `default_model_parameters`
- `device_mode`
- `issues`

Project-local TTS plan contract:

- `voice_assignment_mode`

New-project default:

- `voice_assignment_mode = "narrator_and_characters"`

Current capability rules:

- `minimum_qwen_ready` is true only when at least one healthy Qwen3
  `base`, `voice_designer`, and `custom_voice` model family is available
- `missing_qwen_capabilities` lists any missing required Qwen3 families
- the older generic buckets (`custom_voice_models`, `definition_models`,
  `clone_models`) are still exposed for compatibility, but the narrator
  workflow now uses the fixed Qwen3 readiness flags

Runtime helper coverage in `voiceweaver_runtime_service.py` currently includes:

- `probe_runtime(...)`
- `read_status(...)`
- `read_server_info(...)`
- `read_model_catalog(...)`
- `load_model(...)`
- `unload_model(...)`
- `rescan_models(...)`
- `delete_model(...)`
- `start_model_download(...)`
- `read_model_download_status(...)`
- `cancel_model_download(...)`
- `generate_custom_voice(...)`
- `generate_voice_design(...)`
- `wait_for_terminal_operation(...)`
- `download_generated_voice(...)`

## 7. Workflow Integration

This component sits between the global settings layer and the project-local
narrator workflow.

Upstream:

- toolbar action in `MainWindow`
- persisted app settings loaded at startup

Downstream:

- narrator state shaping in
  `src/audiomancer/services/narrator_definition_state_service.py`
- narrator sample generation in
  `src/audiomancer/ui/controllers/narrator_ui_controller.py`
- future narration and generation work that will need concrete model ids

Current UI behavior:

- the left side of the dialog keeps `Base URL`, `API Key`, `Test Connection`,
  and the three-state connection label in one column with the same width as the
  discovered-model column
- the right side keeps only the discovered-model list and constrains its height
  to roughly the same height as the runtime controls
- the project plan now exposes `Voice Assignment Mode`, `Audio Preview Timeout`,
  and `Audio Generation Timeout`
- narrator sample generation uses the saved runtime base URL, API key,
  discovered models, fixed Qwen3 capability classification, VoiceWeaver
  language codes, and the saved preview timeout from this component

## 8. Usage

Representative runtime probe call:

```python
result = voiceweaver_runtime_service.probe_runtime(
    "http://127.0.0.1:8059",
    runtime_api_key="",
)
```

Representative model-load and generation call pattern:

```python
voiceweaver_runtime_service.load_model(base_url, runtime_api_key, model_id)
voiceweaver_runtime_service.wait_for_terminal_operation(base_url, runtime_api_key)
voiceweaver_runtime_service.generate_voice_design(
    base_url,
    runtime_api_key,
    "en",
    preview_text,
    voice_description,
)
status_payload = voiceweaver_runtime_service.wait_for_terminal_operation(base_url, runtime_api_key)
audio_bytes = voiceweaver_runtime_service.download_generated_voice(base_url, runtime_api_key)
```

Operator path:

- open `TTS Settings`
- enter `Base URL` and optional `API Key`
- press `Test Connection`
- review discovered models
- optionally choose the project `Voice Assignment Mode`
- optionally adjust `Audio Preview Timeout` and `Audio Generation Timeout`
- save the project-local TTS plan when one project is open

## 9. Validation And Tests

Focused automated coverage includes:

- `tests/test_voiceweaver_runtime_service.py`
- `tests/test_tts_settings_page.py`
- `tests/test_settings_service.py`
- `tests/test_main_window_lifecycle.py`
- `tests/test_narrator_ui_controller.py`

Minimum validation after changes:

- `python -m py_compile` for changed TTS/runtime files
- focused `pytest` runs for the runtime probe, page, settings, and shell wiring
- changed-file `ruff check` and `ruff format`

## 10. Limitations And Future Work

- the dialog stores the last discovery result, not a live background refresh
- the current model list view is compact text only and does not yet expose
  richer per-model diagnostics
- runtime operations currently follow the documented synchronous polling model
  and do not expose cancellation because the current VoiceWeaver API does not
  provide a cancel endpoint
- the current dialog assumes fixed Qwen3 narrator-generation requirements and
  does not yet expose future per-role model families for other workflows
