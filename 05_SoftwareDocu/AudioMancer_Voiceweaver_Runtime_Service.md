<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Voiceweaver Runtime Service

## 1. Purpose

Documents the service-only boundary for VoiceWeaver runtime probing,
endpoint normalization, model operations, voice generation, operation polling,
and generated-audio download.

The combined TTS Settings and runtime UI behavior is documented separately in
`05_SoftwareDocu/AudioMancer_TTS_Settings_And_VoiceWeaver_Runtime.md`.

## 2. Responsibilities

- build authenticated VoiceWeaver HTTP headers
- normalize endpoint URLs, including bases that already include `/v1`
- probe health, model, and status endpoints
- normalize discovered model payloads and generation-mode aliases
- expose model load, unload, rescan, catalog, download, cancel, and delete
  wrappers
- submit voice design, direct clone, clone-prompt, and clone-from-prompt
  generation requests
- submit sound-prompt generation requests for approved Scene Ambience blocks
- log sound-prompt request submission and acceptance without recording prompt
  text or runtime API keys
- poll until runtime operations reach a terminal state
- download generated voice bytes
- use the shared TTS operation timeout alias for operation polling and
  generated-audio downloads
- map runtime failures into stable result payloads for callers

It does not own Qt widgets, persisted settings validation, narrator profiles,
or generated artifact storage.

## 3. Implementation Overview

Implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/voiceweaver_runtime_service.py`

The module uses standard-library `urllib` helpers for JSON, multipart, and
binary HTTP calls. Public wrappers normalize runtime responses into dictionaries
before controllers and services consume them.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config`
- `operation_runtime_service.raise_if_cancelled`
- `url_service.join_endpoint_url`
- `logging_service`

External dependencies:

- Python standard library `urllib`, `json`, `time`, and `functools`
- a reachable VoiceWeaver REST runtime

## 5. Inputs And Outputs

Inputs:

- VoiceWeaver base URL
- optional runtime API key
- model identifiers
- language codes and preview text
- voice-description prompts
- WAV sample bytes for clone workflows
- sound prompts, negative prompts, duration, guidance, inference-step count,
  and optional seed for Scene Ambience generation
- progress/cancel callbacks for polling operations

Outputs:

- normalized probe result dictionaries
- normalized model and capability payloads
- runtime operation/status dictionaries
- generated audio bytes
- raised exceptions for invalid response shapes or failed HTTP operations when
  a wrapper is expected to be strict

## 6. Data Contracts

Normalized discovered-model payloads include:

- `model_id`
- `backend_name`
- `status`
- `supported_generation_modes`
- `supported_languages`
- `default_model_parameters`
- `device_mode`
- `issues`

Generation-mode aliases are folded into the current REST contract:

- `base` maps to `clone`
- `voice_designer` maps to `definition`

Romanian requests omit the outbound `language` field so VoiceWeaver can infer
pronunciation from the text.

`DEFAULT_TTS_OPERATION_TIMEOUT_SECONDS` aliases the current audio-generation
timeout value and is used by operation polling and generated-audio download
defaults without changing existing timeout duration.

## 7. Workflow Integration

Upstream:

- `tts_settings_ui_controller`
- `narator_voice_ui_controller`
- `character_voices_ui_controller`
- `audio_blocks_service`

Downstream:

- local VoiceWeaver runtime
- project-local narrator, character, and Audio Blocks artifact writers that
  store returned audio bytes and metadata

## 8. Usage

Representative calls:

```python
probe = voiceweaver_runtime_service.probe_runtime(base_url, runtime_api_key="")
voiceweaver_runtime_service.load_model(base_url, runtime_api_key, model_id)
status = voiceweaver_runtime_service.wait_for_terminal_operation(base_url, runtime_api_key)
audio = voiceweaver_runtime_service.download_generated_voice(base_url, runtime_api_key)
ambience = voiceweaver_runtime_service.generate_sound_prompt(
    base_url,
    runtime_api_key,
    model_id,
    prompt="low-volume room tone",
    negative_prompt="speech, music",
    duration_seconds=3.0,
)
```

## 9. Validation And Tests

Focused tests:

- `tests/test_voiceweaver_runtime_service.py`
- `tests/test_tts_settings_page.py`
- `tests/test_narator_voice_ui_controller.py`
- `tests/test_audio_blocks_service.py`

Minimum validation after changes:

- `uv run python -m py_compile src/audiomancer/services/voiceweaver_runtime_service.py`
- `uv run pytest tests/test_voiceweaver_runtime_service.py`

## 10. Limitations And Future Work

- runtime calls are synchronous and rely on controller/service-level threading
  for UI responsiveness
- cancellation is cooperative during polling, not during a blocking individual
  HTTP request
- richer runtime diagnostics remain represented as normalized dictionaries
  rather than typed models
