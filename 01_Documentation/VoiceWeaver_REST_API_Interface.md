<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# VoiceWeaver REST API Interface

## 1. Purpose

This document describes the public REST API exposed by the local
`VoiceWeaver` runtime.

It is intended for:

- external developers building applications that connect to VoiceWeaver
- UI developers building a separate browser, desktop, or CLI interface
- AI coding agents that need enough contract detail to generate a working
  client integration

The current runtime API is model-first and operation-based:

- discover local models
- load one model
- query runtime status and loaded-model capabilities
- run one voice or sound generation operation at a time
- poll status until completion
- download the latest generated audio

The currently implemented adapter set includes Qwen voice models and Stable
Audio Open prompt-to-sound generation. The API remains shaped so future local
adapters can be added without changing the top-level workflow.

There are no job ids, queues, artifact ids, or background-worker contracts in
the simplified API.

## 2. Base URL

Default local runtime:

```text
http://127.0.0.1:8059
```

Versioned API prefix:

```text
/v1
```

Example:

```text
http://127.0.0.1:8059/v1/status
```

The runtime no longer serves a built-in browser page. For local smoke testing
without HTTP, operators can run:

```powershell
uv run voiceweaver test-voice --output outputs\local_voice_test.wav
```

Packaged deliveries also include offline operator controls beside the headless
API server. Windows packages provide `VoiceWeaver Control Panel.cmd`,
`Start VoiceWeaver.cmd`, `Stop VoiceWeaver.cmd`, `VoiceWeaver Status.cmd`, and
`Generate Test Voice.cmd`. Ubuntu packages provide matching `.sh` scripts. The
control scripts do not add REST endpoints; they start, stop, status-check, or
run local CLI generation against the same packaged runtime.

## 3. Authentication

Authentication is host-aware.

Default configuration:

```text
API_AUTH_MODE = "auto"
DEFAULT_RUNTIME_HOST = "127.0.0.1"
DEFAULT_API_KEY = "voiceweaver-dev-key"
```

Effective behavior:

- if the runtime host is `127.0.0.1` or `localhost` and auth mode is `auto`,
  auth is disabled
- if the runtime host is `0.0.0.0` and auth mode is `auto`, auth is enabled
- if auth mode is `enabled`, protected routes require a Bearer token
- if auth mode is `disabled`, protected routes skip auth

When auth is enabled, send:

```http
Authorization: Bearer voiceweaver-dev-key
```

`voiceweaver-dev-key` is a shared default intended for trusted
internal-network use. Operators can override it by setting the
`VOICEWEAVER_API_KEY` environment variable before starting the runtime; when
set, only that value is accepted. The effective auth decision is resolved from
the host the runtime actually binds, so starting with `--host 0.0.0.0` enforces
authorization in `auto` mode.

Health is public. Versioned runtime routes under `/v1`, including `/v1/server`,
are protected only when effective auth is enabled. The shipped runtime is
headless and does not serve a browser UI at `/`.

For `POST /v1/voice/clone`, the multipart form fields `sample_text`,
`language`, and `text` are required and must be non-empty strings.

For `POST /v1/voice/clone-prompt`, the multipart form fields `sample_text`
and `language` are required and must be non-empty strings.

For `POST /v1/voice/clone` and `POST /v1/voice/clone-prompt`, the uploaded
`voice_sample` file is limited to 64 MiB. Larger uploads are rejected with
HTTP `413` and error code `payload_too_large` before generation starts.

## 4. Endpoint Summary

```text
GET  /v1/health
GET  /v1/server
GET  /v1/models
POST /v1/models/load
POST /v1/models/unload
POST /v1/models/rescan
GET  /v1/status
POST /v1/voice/design
POST /v1/voice/clone-prompt
POST /v1/voice/clone
POST /v1/voice/clone-from-prompt
POST /v1/voice/custom
POST /v1/voice/preset
POST /v1/sound/prompt
GET  /v1/voice
GET  /v1/audio
```

Primary integration flow:

```text
GET /v1/models
POST /v1/models/load
GET /v1/status
POST /v1/voice/<mode> or POST /v1/sound/prompt
GET /v1/status until operation.status is completed or failed
GET /v1/voice or GET /v1/audio
```

## 5. Runtime Model

VoiceWeaver runs one model and one operation at a time.

Rules:

- only one model can be loaded at once
- loading a new model unloads the previously loaded model first
- only one load, unload, or generation operation can run at a time
- concurrent mutating requests return `busy`
- `GET /v1/status` is the single polling endpoint
- `GET /v1/voice` downloads the latest completed generated voice audio for
  backward compatibility
- `GET /v1/audio` downloads the latest completed generated audio regardless
  of whether the operation was voice or sound generation
- reusable `voice_clone_prompt` artifacts are returned to the client and are
  never assigned runtime-owned profile ids
- clone-prompt creation stores its terminal artifact in
  `/v1/status.operation.result`
- `/v1/status.result` remains the latest generated audio metadata only, even
  after clone-prompt creation
- loading, unloading, startup, and new generation delete any previous
  generated `voice.wav`
- `operation_history.jsonl` is a session log: it is recreated at runtime
  startup and is not preserved across restarts
- runtime state files are written atomically, so an interrupted runtime never
  leaves a truncated `current_operation.json`, `models_available.json`, or
  `voice.wav`
- model unload performs Python garbage collection and clears CUDA cache when
  the Qwen runtime has `torch` available
- `GET /v1/status` includes `device_diagnostics` so clients can distinguish
  CUDA active, CUDA package with CPU fallback, CPU-only Torch, and missing or
  unloadable Torch

Runtime state files are visible under:

```text
04_Software/VoiceWeaver/outputs/
```

Important files:

```text
models_available.json
current_operation.json
operation_history.jsonl
voice.wav
```

External clients should use the REST API, not these files, unless the
integration is explicitly operator/debug tooling.

## 6. Model Capability Rules

Clients must not hardcode that every model supports every generation mode.
Always inspect:

```json
status.capabilities.supported_generation_modes
```

Known Qwen mapping:

```text
Qwen3-TTS-*-Base        -> clone
Qwen3-TTS-*-CustomVoice -> custom_voice
Qwen3-TTS-*-VoiceDesign -> definition
```

A model folder may also include an optional `voiceweaver_model.json` manifest.
When that file declares a `supported_generation_modes` list, the runtime uses
those modes instead of the folder-name heuristic above. Only modes the adapter
implements are accepted; unknown entries are ignored:

```json
{
  "supported_generation_modes": ["clone"]
}
```

Generic supported modes:

```text
definition
clone
custom_voice
preset
sound_prompt
```

`preset` is retained for future non-Qwen adapters. Qwen CustomVoice uses
`custom_voice`, not `preset`.

Stable Audio Open uses `sound_prompt`. It is sound generation, not TTS, and
does not require `language`.

Today the Qwen and Stable Audio adapters are registered in the runtime.
`OmniVoice` and `VoxCPM2` remain future adapter targets, not active
REST-backed backends.

## 7. Shared Response Models

### 7.1 Error Response

All runtime API errors use this stable shape:

```json
{
  "error_code": "model_not_found",
  "message": "Model 'missing-model' was not found.",
  "details": null,
  "unsupported_capability": null
}
```

Common error codes:

```text
missing_credentials
invalid_credentials
invalid_request
model_not_found
model_unhealthy
model_load_failed
no_model_loaded
unsupported_generation_mode
unsupported_language
missing_runtime_dependencies
adapter_method_missing
synthesis_failed
audio_serialization_failed
payload_too_large
busy
not_found
unexpected_error
```

HTTP status behavior:

- `400` for most request, model, adapter, and capability errors
- `401` for auth errors
- `404` for unavailable generated audio
- `409` for `busy`
- `413` for an uploaded `voice_sample` that exceeds the runtime size limit
- `200` for successful runtime operations, including failed operation objects
  returned by an operation that started and then failed internally

### 7.2 Model Summary

Used in `/v1/models`, `/v1/status.active_model`, and discovery audit payloads.

```json
{
  "model_id": "Qwen3-TTS-12Hz-0.6B-Base",
  "backend_name": "qwen",
  "status": "healthy",
  "supported_generation_modes": ["clone"],
  "supported_languages": ["de", "en", "es", "fr", "it", "ja", "ko", "pt", "ru", "zh"],
  "supported_presets": [],
  "default_model_parameters": {
    "do_sample": true,
    "top_k": 50,
    "top_p": 1.0,
    "temperature": 0.9,
    "repetition_penalty": 1.05,
    "max_new_tokens": 512
  },
  "generation_parameter_ranges": {
    "max_new_tokens": {
      "default": 512,
      "minimum": 128,
      "recommended_maximum": 2048,
      "hard_maximum": 8192,
      "unit": "codec_tokens",
      "approx_audio_seconds_per_token": 0.08333333333333333,
      "approx_default_audio_seconds": 42.666666666666664,
      "approx_recommended_audio_seconds": 170.66666666666666,
      "notes": "Higher values allow longer output but increase generation time, GPU memory use, and the chance of truncated or degenerate output near the model limit."
    }
  },
  "device_mode": "cpu",
  "issues": null
}
```

Notes:

- `supported_presets` is also used today to report Qwen CustomVoice speakers.
- `generation_parameter_ranges` reports client-facing override guidance for
  generated-output budgets such as Qwen `max_new_tokens` and Stable Audio
  `duration_seconds`, `guidance_scale`, `num_inference_steps`, and `seed`.
- `status` is `healthy` or `unhealthy` for discovered models.
- unhealthy models may have empty capabilities and an `issues` array.
- Stable Audio Open models report `backend_name = "stable_audio"`,
  `supported_generation_modes = ["sound_prompt"]`, and no supported
  languages.

### 7.3 Runtime Device Diagnostics

Used in `/v1/status.device_diagnostics`.

```json
{
  "package_flavor": "cuda",
  "torch_installed": true,
  "torch_version": "2.11.0+cu128",
  "torch_cuda_build": "12.8",
  "torch_cuda_available": true,
  "torch_cuda_device_count": 1,
  "torch_cuda_device_name": "NVIDIA GeForce RTX 5060 Ti",
  "device_mode": "cuda",
  "status_message": "CUDA active: NVIDIA GeForce RTX 5060 Ti."
}
```

Notes:

- `torch_cuda_build = null` means CPU-only Torch is installed.
- `torch_cuda_build != null` and `torch_cuda_available = false` means the
  package contains CUDA-capable Torch, but no compatible NVIDIA GPU/driver was
  detected, so the runtime falls back to CPU.
- The CUDA Toolkit does not need to be installed on the target computer. A
  compatible NVIDIA driver is still required for GPU execution.

### 7.4 Current Operation

Used in operation responses and in `/v1/status.operation`.

```json
{
  "operation_id": "19da053e-5c93-4e14-ae24-bae68f70d2ef",
  "kind": "generate_voice_clone",
  "status": "running",
  "target_model_id": "Qwen3-TTS-12Hz-0.6B-Base",
  "progress_percent": 35,
  "stage": "Running Qwen voice clone.",
  "started_at": "2026-04-15T10:00:00.000000+00:00",
  "updated_at": "2026-04-15T10:00:03.000000+00:00",
  "inputs": {
    "mode": "clone",
    "text": "Hello from VoiceWeaver.",
    "language": "en",
    "model_id": "Qwen3-TTS-12Hz-0.6B-Base",
    "backend_name": "qwen",
    "mode_inputs": {
      "sample_text": "Reference transcript.",
      "sample_file_name": "sample.wav"
    },
    "model_parameters": {},
    "effective_model_parameters": {
      "temperature": 0.9,
      "top_k": 50
    }
  },
  "result": null,
  "error": null
}
```

Operation statuses:

```text
idle
running
completed
failed
```

Operation kinds:

```text
idle
load_model
unload_model
create_voice_clone_prompt
generate_voice_design
generate_voice_clone
generate_voice_clone_from_prompt
generate_custom_voice
generate_voice_preset
generate_sound_prompt
```

For `sound_prompt` operations, `inputs.language` is `null`.

## 8. Endpoint Details

### 8.1 GET /v1/health

Health endpoint.

Request:

```http
GET /v1/health
```

Response:

```json
{
  "service": "VoiceWeaver",
  "status": "ok",
  "host": "127.0.0.1",
  "port": 8059,
  "api_version": "v1"
}
```

### 8.3 GET /v1/models

Discovers local model folders under `models/`.

Side effects:

- runtime startup rebuilds `outputs/models_available.json`
- `GET /v1/models` rewrites `outputs/models_available.json`

Model inventory is local-only. The runtime does not search online, download
models, or delete model folders. To add a model after delivery, copy a valid
model folder into `04_Software/VoiceWeaver/models/` and call `GET /v1/models`
or `POST /v1/models/rescan`.

Request:

```http
GET /v1/models
```

Response:

```json
{
  "service": "VoiceWeaver",
  "runtime_version": "1.5.0",
  "models": [
    {
      "model_id": "Qwen3-TTS-12Hz-0.6B-Base",
      "backend_name": "qwen",
      "status": "healthy",
      "supported_generation_modes": ["clone"],
      "supported_languages": ["en", "de"],
      "supported_presets": [],
      "default_model_parameters": {
        "temperature": 0.9,
        "top_k": 50,
        "max_new_tokens": 512
      },
      "generation_parameter_ranges": {
        "max_new_tokens": {
          "default": 512,
          "minimum": 128,
          "recommended_maximum": 2048,
          "hard_maximum": 8192,
          "unit": "codec_tokens",
          "approx_audio_seconds_per_token": 0.08333333333333333,
          "approx_default_audio_seconds": 42.666666666666664,
          "approx_recommended_audio_seconds": 170.66666666666666,
          "notes": "Higher values allow longer output but increase generation time, GPU memory use, and the chance of truncated or degenerate output near the model limit."
        }
      },
      "device_mode": "cpu",
      "issues": null
    }
  ]
}
```

PowerShell:

```powershell
(iwr http://127.0.0.1:8059/v1/models -UseBasicParsing).Content
```

curl:

```bash
curl http://127.0.0.1:8059/v1/models
```

Python:

```python
import requests

base_url = "http://127.0.0.1:8059"
models = requests.get(f"{base_url}/v1/models", timeout=30).json()
print(models["models"])
```

### 8.4 POST /v1/models/load

Loads one discovered model.

Request body:

```json
{
  "model_id": "Qwen3-TTS-12Hz-0.6B-Base"
}
```

Behavior:

- validates `model_id` against `outputs/models_available.json`
- if another model is loaded, unloads it first
- deletes previous `outputs/voice.wav`
- loads the requested model
- writes load operation progress to `/v1/status`

Response:

```json
{
  "operation_id": "d4f2b058-59d7-4f92-85aa-bab607f26696",
  "kind": "load_model",
  "status": "completed",
  "target_model_id": "Qwen3-TTS-12Hz-0.6B-Base",
  "progress_percent": 100,
  "stage": "Completed.",
  "started_at": "2026-04-15T10:00:00.000000+00:00",
  "updated_at": "2026-04-15T10:00:05.000000+00:00",
  "inputs": null,
  "result": {
    "active_model": "Qwen3-TTS-12Hz-0.6B-Base",
    "backend_name": "qwen",
    "supported_generation_modes": ["clone"],
    "supported_languages": ["en"],
    "supported_presets": [],
    "default_model_parameters": {
      "temperature": 0.9,
      "top_k": 50
    },
    "device_mode": "cpu",
    "device_diagnostics": {
      "package_flavor": "cuda",
      "torch_installed": true,
      "torch_version": "2.11.0+cu128",
      "torch_cuda_build": "12.8",
      "torch_cuda_available": false,
      "torch_cuda_device_count": 0,
      "torch_cuda_device_name": null,
      "device_mode": "cpu",
      "status_message": "CPU fallback: CUDA-capable Torch is installed, but no compatible GPU/driver was detected."
    }
  },
  "error": null
}
```

PowerShell:

```powershell
(iwr http://127.0.0.1:8059/v1/models/load `
  -UseBasicParsing `
  -Method Post `
  -Headers @{ "Content-Type" = "application/json" } `
  -Body '{"model_id":"Qwen3-TTS-12Hz-0.6B-Base"}').Content
```

curl:

```bash
curl -X POST http://127.0.0.1:8059/v1/models/load \
  -H "Content-Type: application/json" \
  -d '{"model_id":"Qwen3-TTS-12Hz-0.6B-Base"}'
```

### 8.5 POST /v1/models/unload

Unloads the active model.

Request:

```http
POST /v1/models/unload
```

Behavior:

- if no model is loaded, returns JSON `null`
- if a model is loaded, runs an unload operation
- deletes `outputs/voice.wav`
- does not delete `outputs/operation_history.jsonl`

No-op response:

```json
null
```

Successful unload response:

```json
{
  "operation_id": "8f3eac84-dabd-4146-b242-a608b13c3aa6",
  "kind": "unload_model",
  "status": "completed",
  "target_model_id": "Qwen3-TTS-12Hz-0.6B-Base",
  "progress_percent": 100,
  "stage": "Completed.",
  "started_at": "2026-04-15T10:05:00.000000+00:00",
  "updated_at": "2026-04-15T10:05:01.000000+00:00",
  "inputs": null,
  "result": {
    "active_model": null
  },
  "error": null
}
```

### 8.6 GET /v1/status

Returns complete runtime state.

This is the single endpoint clients should poll.

Request:

```http
GET /v1/status
```

Response when idle and no model is loaded:

```json
{
  "service": "VoiceWeaver",
  "runtime_version": "1.5.0",
  "active_model": null,
  "capabilities": {
    "service": "VoiceWeaver",
    "runtime_name": "VoiceWeaver",
    "runtime_version": "1.5.0",
    "api_version": "v1",
    "active_model": null,
    "status": "idle",
    "backend_name": null,
    "device_mode": null,
    "supported_languages": [],
    "supported_generation_modes": [],
    "supported_presets": null,
    "default_model_parameters": null,
    "generation_parameter_ranges": null,
    "accepts_reference_audio": false,
    "readiness_issues": null
  },
  "device_diagnostics": {
    "package_flavor": null,
    "torch_installed": true,
    "torch_version": "2.11.0+cpu",
    "torch_cuda_build": null,
    "torch_cuda_available": false,
    "torch_cuda_device_count": 0,
    "torch_cuda_device_name": null,
    "device_mode": "cpu",
    "status_message": "CPU only: package contains CPU-only Torch."
  },
  "operation": {
    "operation_id": null,
    "kind": "idle",
    "status": "idle",
    "target_model_id": null,
    "progress_percent": 0,
    "stage": "Idle.",
    "started_at": null,
    "updated_at": null,
    "inputs": null,
    "result": null,
    "error": null
  },
  "result": {
    "available": false,
    "mode": null,
    "model_id": null,
    "file_name": null,
    "content_type": null,
    "size_bytes": null,
    "created_at": null,
    "download_url": null,
    "summary": null,
    "inputs": null
  }
}
```

Response after completed generation:

```json
{
  "service": "VoiceWeaver",
  "runtime_version": "1.5.0",
  "active_model": {
    "model_id": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "backend_name": "qwen",
    "status": "ready",
    "supported_generation_modes": ["custom_voice"],
    "supported_languages": ["en"],
    "supported_presets": ["vivian", "serena"],
    "default_model_parameters": {
      "temperature": 0.9,
      "top_k": 50,
      "max_new_tokens": 8192
    },
    "generation_parameter_ranges": {
      "max_new_tokens": {
        "default": 8192,
        "minimum": 128,
        "recommended_maximum": 8192,
        "hard_maximum": 8192,
        "unit": "codec_tokens",
        "approx_audio_seconds_per_token": 0.08333333333333333,
        "approx_default_audio_seconds": 682.6666666666666,
        "approx_recommended_audio_seconds": 682.6666666666666,
        "notes": "Higher values allow longer output but increase generation time, GPU memory use, and the chance of truncated or degenerate output near the model limit."
      }
    },
    "device_mode": "cpu",
    "issues": null
  },
  "capabilities": {
    "service": "VoiceWeaver",
    "runtime_name": "VoiceWeaver",
    "runtime_version": "1.5.0",
    "api_version": "v1",
    "active_model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "status": "ready",
    "backend_name": "qwen",
    "device_mode": "cpu",
    "supported_languages": ["en"],
    "supported_generation_modes": ["custom_voice"],
    "supported_presets": ["vivian", "serena"],
    "default_model_parameters": {
      "temperature": 0.9,
      "top_k": 50,
      "max_new_tokens": 8192
    },
    "generation_parameter_ranges": {
      "max_new_tokens": {
        "default": 8192,
        "minimum": 128,
        "recommended_maximum": 8192,
        "hard_maximum": 8192,
        "unit": "codec_tokens",
        "approx_audio_seconds_per_token": 0.08333333333333333,
        "approx_default_audio_seconds": 682.6666666666666,
        "approx_recommended_audio_seconds": 682.6666666666666,
        "notes": "Higher values allow longer output but increase generation time, GPU memory use, and the chance of truncated or degenerate output near the model limit."
      }
    },
    "accepts_reference_audio": false,
    "readiness_issues": null
  },
  "device_diagnostics": {
    "package_flavor": "cuda",
    "torch_installed": true,
    "torch_version": "2.11.0+cu128",
    "torch_cuda_build": "12.8",
    "torch_cuda_available": true,
    "torch_cuda_device_count": 1,
    "torch_cuda_device_name": "NVIDIA GeForce RTX 5060 Ti",
    "device_mode": "cuda",
    "status_message": "CUDA active: NVIDIA GeForce RTX 5060 Ti."
  },
  "operation": {
    "operation_id": "fb81c875-8452-4d27-a2e2-f6e2391c8cf3",
    "kind": "generate_custom_voice",
    "status": "completed",
    "target_model_id": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "progress_percent": 100,
    "stage": "Completed.",
    "started_at": "2026-04-15T10:15:00.000000+00:00",
    "updated_at": "2026-04-15T10:15:10.000000+00:00",
    "inputs": {
      "mode": "custom_voice",
      "text": "Hello from VoiceWeaver.",
      "language": "en",
      "model_id": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
      "backend_name": "qwen",
      "mode_inputs": {
        "speaker": "vivian",
        "instruct": "Speak warmly."
      },
      "model_parameters": {},
      "effective_model_parameters": {
        "temperature": 0.9,
        "top_k": 50
      }
    },
    "result": {
      "available": true,
      "mode": "custom_voice",
      "model_id": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
      "file_name": "voice.wav",
      "content_type": "audio/wav",
      "size_bytes": 123456,
      "created_at": "2026-04-15T10:15:10.000000+00:00",
      "download_url": "/v1/voice",
      "summary": "Qwen3-TTS-12Hz-1.7B-CustomVoice | custom_voice:vivian | en",
      "inputs": {
        "mode": "custom_voice",
        "text": "Hello from VoiceWeaver.",
        "language": "en",
        "model_id": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "backend_name": "qwen",
        "mode_inputs": {
          "speaker": "vivian",
          "instruct": "Speak warmly."
        },
        "model_parameters": {},
        "effective_model_parameters": {
          "temperature": 0.9,
          "top_k": 50
        }
      }
    },
    "error": null
  },
  "result": {
    "available": true,
    "mode": "custom_voice",
    "model_id": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "file_name": "voice.wav",
    "content_type": "audio/wav",
    "size_bytes": 123456,
    "created_at": "2026-04-15T10:15:10.000000+00:00",
    "download_url": "/v1/voice",
    "summary": "Qwen3-TTS-12Hz-1.7B-CustomVoice | custom_voice:vivian | en",
    "inputs": {
      "mode": "custom_voice",
      "text": "Hello from VoiceWeaver.",
      "language": "en",
      "model_id": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
      "backend_name": "qwen",
      "mode_inputs": {
        "speaker": "vivian",
        "instruct": "Speak warmly."
      },
      "model_parameters": {},
      "effective_model_parameters": {
        "temperature": 0.9,
        "top_k": 50
      }
    }
  }
}
```

Client guidance:

- poll every 0.5 to 2 seconds during running operations
- stop polling when `operation.status` is `completed` or `failed`
- download audio only when `result.available` is `true`; new clients should
  use the route advertised by `result.download_url`
- inspect `operation.error` when status is `failed`

### 8.7 POST /v1/voice/design

Runs voice-design generation.

Use when the loaded model supports:

```json
["definition"]
```

Qwen model family:

```text
Qwen3-TTS-*-VoiceDesign
```

Request body:

```json
{
  "text": "Hello from VoiceWeaver.",
  "language": "en",
  "voice_description": "Warm narrator with steady pacing.",
  "model_parameters": {
    "temperature": 0.8
  }
}
```

Required fields:

- `text`
- `language`
- `voice_description`

Optional:

- `model_parameters`

Behavior note:

- `model_parameters` overrides are merged with the loaded model defaults and
  the effective values are forwarded to the adapter generation call
- `text` must be non-empty

Response:

- `CurrentOperationResponse`
- status may be `completed` or `failed`

PowerShell:

```powershell
(iwr http://127.0.0.1:8059/v1/voice/design `
  -UseBasicParsing `
  -Method Post `
  -Headers @{ "Content-Type" = "application/json" } `
  -Body '{"text":"Hello","language":"en","voice_description":"Warm narrator"}').Content
```

curl:

```bash
curl -X POST http://127.0.0.1:8059/v1/voice/design \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello","language":"en","voice_description":"Warm narrator"}'
```

### 8.8 POST /v1/voice/clone-prompt

Creates one reusable voice clone prompt.

Use when the loaded model supports:

```json
["clone"]
```

Qwen model family:

```text
Qwen3-TTS-*-Base
```

Content type:

```text
multipart/form-data
```

Form fields:

```text
voice_sample: file, required
sample_text: string, required
language: string, required
model_parameters_json: JSON object string, optional
```

Behavior notes:

- VoiceWeaver calls the official Qwen `create_voice_clone_prompt(...)` API
- the uploaded `voice_sample` file is limited to 64 MiB; larger uploads return
  HTTP `413` with error code `payload_too_large`
- the reusable `voice_clone_prompt` artifact is returned to the client
- VoiceWeaver does not create a server-owned profile id, prompt id, or delete
  API for reusable prompts
- `operation.result.voice_clone_prompt` is JSON-serializable and can be stored
  externally by the client
- `/v1/status.result` is not replaced by clone-prompt creation because it
  remains reserved for the latest generated audio metadata

Result shape inside `CurrentOperationResponse.result`:

```json
{
  "created_at": "2026-04-23T10:00:00.000000+00:00",
  "model_id": "Qwen3-TTS-12Hz-0.6B-Base",
  "backend_name": "qwen",
  "summary": "Qwen3-TTS-12Hz-0.6B-Base | clone_prompt | en",
  "voice_clone_prompt": {
    "format": "qwen_voice_clone_prompt_v1",
    "backend_name": "qwen",
    "model_id": "Qwen3-TTS-12Hz-0.6B-Base",
    "tokenizer_type": "qwen3_tts_tokenizer_12hz",
    "tts_model_type": "base",
    "prompt": {
      "ref_text": "This is the transcript of the reference sample.",
      "ref_code": {
        "encoding": "base64",
        "dtype": "int64",
        "shape": [128],
        "data": "..."
      },
      "ref_spk_embedding": {
        "encoding": "base64",
        "dtype": "float32",
        "shape": [256],
        "data": "..."
      },
      "x_vector_only_mode": false,
      "icl_mode": true
    }
  }
}
```

### 8.9 POST /v1/voice/clone

Runs voice-clone generation.

Use when the loaded model supports:

```json
["clone"]
```

Qwen model family:

```text
Qwen3-TTS-*-Base
```

Content type:

```text
multipart/form-data
```

Form fields:

```text
voice_sample: file, required
sample_text: string, required
language: string, required
text: string, required
model_parameters_json: JSON object string, optional
```

Behavior note:

- when provided, `model_parameters_json` is merged with the loaded model
  defaults and the effective values are forwarded to the adapter generation call
- `text` must be non-empty
- the uploaded `voice_sample` file is limited to 64 MiB; larger uploads return
  HTTP `413` with error code `payload_too_large`

PowerShell:

```powershell
$form = @{
  voice_sample = Get-Item ".\sample.wav"
  sample_text = "This is the transcript of the reference sample."
  language = "en"
  text = "This is the text to synthesize in the cloned voice."
  model_parameters_json = '{"temperature":0.8}'
}

(iwr http://127.0.0.1:8059/v1/voice/clone `
  -UseBasicParsing `
  -Method Post `
  -Form $form).Content
```

curl:

```bash
curl -X POST http://127.0.0.1:8059/v1/voice/clone \
  -F "voice_sample=@sample.wav" \
  -F "sample_text=This is the transcript of the reference sample." \
  -F "language=en" \
  -F "text=This is the text to synthesize in the cloned voice." \
  -F 'model_parameters_json={"temperature":0.8}'
```

Python:

```python
import requests

base_url = "http://127.0.0.1:8059"
with open("sample.wav", "rb") as sample_file:
    response = requests.post(
        f"{base_url}/v1/voice/clone",
        files={"voice_sample": ("sample.wav", sample_file, "audio/wav")},
        data={
            "sample_text": "This is the transcript of the reference sample.",
            "language": "en",
            "text": "This is the text to synthesize in the cloned voice.",
            "model_parameters_json": '{"temperature":0.8}',
        },
        timeout=300,
    )
response.raise_for_status()
print(response.json())
```

Implementation note:

- the runtime writes the uploaded sample to a private operating-system
  temporary file during generation, not the operator-visible `outputs/` folder
- the temp file is deleted after Qwen completes or fails
- clients do not need to manage this temp file

### 8.10 POST /v1/voice/clone-from-prompt

Runs reusable voice-clone generation from a previously returned prompt.

Request body:

```json
{
  "voice_clone_prompt": {
    "format": "qwen_voice_clone_prompt_v1",
    "backend_name": "qwen",
    "model_id": "Qwen3-TTS-12Hz-0.6B-Base",
    "tokenizer_type": "qwen3_tts_tokenizer_12hz",
    "tts_model_type": "base",
    "prompt": {
      "ref_text": "This is the transcript of the reference sample.",
      "ref_code": {
        "encoding": "base64",
        "dtype": "int64",
        "shape": [128],
        "data": "..."
      },
      "ref_spk_embedding": {
        "encoding": "base64",
        "dtype": "float32",
        "shape": [256],
        "data": "..."
      },
      "x_vector_only_mode": false,
      "icl_mode": true
    }
  },
  "language": "en",
  "text": "This line reuses the stored voice clone prompt.",
  "model_parameters": {
    "temperature": 0.8
  }
}
```

Request notes:

- `voice_clone_prompt` may be sent either as the JSON object above or as a
  JSON string containing the same object
- VoiceWeaver decodes the prompt artifact and calls the official Qwen
  `generate_voice_clone(..., voice_clone_prompt=...)` API
- the reusable prompt artifact retains the original reference transcript so
  VoiceWeaver can rebuild the Qwen reference token ids during replay
- the original reference sample audio is not required in this request

Validation rules:

- malformed prompt payload returns `invalid_voice_clone_prompt`
- model/backend/tokenizer/type mismatches return
  `incompatible_voice_clone_prompt`
- unsupported loaded models still return `unsupported_generation_mode`

### 8.11 POST /v1/voice/custom

Runs custom-voice generation.

Use when the loaded model supports:

```json
["custom_voice"]
```

Qwen model family:

```text
Qwen3-TTS-*-CustomVoice
```

Request body:

```json
{
  "speaker": "vivian",
  "language": "en",
  "text": "Hello from VoiceWeaver.",
  "instruct": "Speak naturally with a calm, expressive tone.",
  "model_parameters": {
    "temperature": 0.8
  }
}
```

Required fields:

- `speaker`
- `language`
- `text`

Optional fields:

- `instruct`
- `model_parameters`

Behavior note:

- `model_parameters` overrides are merged with the loaded model defaults and
  the effective values are forwarded to the adapter generation call
- `text` must be non-empty

Speaker values:

- read from `GET /v1/status` at `capabilities.supported_presets`
- read from `GET /v1/models` for discovered models

PowerShell:

```powershell
(iwr http://127.0.0.1:8059/v1/voice/custom `
  -UseBasicParsing `
  -Method Post `
  -Headers @{ "Content-Type" = "application/json" } `
  -Body '{"speaker":"vivian","language":"en","text":"Hello","instruct":"Speak warmly."}').Content
```

curl:

```bash
curl -X POST http://127.0.0.1:8059/v1/voice/custom \
  -H "Content-Type: application/json" \
  -d '{"speaker":"vivian","language":"en","text":"Hello","instruct":"Speak warmly."}'
```

Python:

```python
import requests

base_url = "http://127.0.0.1:8059"
payload = {
    "speaker": "vivian",
    "language": "en",
    "text": "Hello from VoiceWeaver.",
    "instruct": "Speak warmly.",
}
response = requests.post(f"{base_url}/v1/voice/custom", json=payload, timeout=300)
response.raise_for_status()
print(response.json())
```

### 8.12 POST /v1/voice/preset

Runs generic preset-voice generation.

This endpoint is retained for future non-Qwen adapters. Current Qwen
CustomVoice integrations should use:

```text
POST /v1/voice/custom
```

Use only when the loaded model reports:

```json
["preset"]
```

Request body:

```json
{
  "preset_voice_id": "default",
  "language": "en",
  "text": "Hello from VoiceWeaver.",
  "model_parameters": {}
}
```

Current implementation note:

- the route exists in the API surface
- clients may call the route directly when a loaded model reports `preset`
  capability
- the registered Qwen adapter does not currently report `preset` capability

### 8.13 POST /v1/sound/prompt

Runs Stable Audio Open prompt-to-sound generation.

Use when the loaded model supports:

```json
["sound_prompt"]
```

Stable Audio model family:

```text
stable-audio-open-1.0
```

Request body:

```json
{
  "prompt": "A hammer hitting a wooden surface.",
  "negative_prompt": "low quality, distorted",
  "duration_seconds": 10.0,
  "seed": 123,
  "guidance_scale": 7.0,
  "num_inference_steps": 100
}
```

Required fields:

- `prompt`

Optional fields:

- `negative_prompt`
- `duration_seconds`, default `10.0`
- `seed`
- `guidance_scale`, default `7.0`
- `num_inference_steps`, default `100`

Behavior notes:

- `prompt` must be non-empty.
- `language` is not part of this request; the stored operation input uses
  `language = null`.
- the adapter forwards `duration_seconds` to Stable Audio as
  `audio_end_in_s`.
- when `seed` is provided, the adapter creates a seeded `torch.Generator`.
- v1 generates one WAV output per request.
- completed results use `result.file_name = "audio.wav"` and
  `result.download_url = "/v1/audio"`.

PowerShell:

```powershell
(iwr http://127.0.0.1:8059/v1/sound/prompt `
  -UseBasicParsing `
  -Method Post `
  -Headers @{ "Content-Type" = "application/json" } `
  -Body '{"prompt":"A hammer hitting a wooden surface","negative_prompt":"low quality, distorted","duration_seconds":5,"guidance_scale":7,"num_inference_steps":50,"seed":123}').Content
```

curl:

```bash
curl -X POST http://127.0.0.1:8059/v1/sound/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt":"A hammer hitting a wooden surface","duration_seconds":5,"guidance_scale":7,"num_inference_steps":50,"seed":123}'
```

Python:

```python
import requests

base_url = "http://127.0.0.1:8059"
payload = {
    "prompt": "A hammer hitting a wooden surface.",
    "negative_prompt": "low quality, distorted",
    "duration_seconds": 5,
    "guidance_scale": 7,
    "num_inference_steps": 50,
    "seed": 123,
}
response = requests.post(f"{base_url}/v1/sound/prompt", json=payload, timeout=600)
response.raise_for_status()
print(response.json())
```

### 8.14 GET /v1/voice

Downloads the latest generated WAV file through the backward-compatible voice
artifact route.

Request:

```http
GET /v1/voice
```

Success:

```text
HTTP 200
Content-Type: audio/wav
Content-Disposition: attachment; filename="voice.wav"
```

Failure when no audio is available:

```json
{
  "error_code": "not_found",
  "message": "No generated audio is available yet.",
  "details": null,
  "unsupported_capability": null
}
```

PowerShell:

```powershell
iwr http://127.0.0.1:8059/v1/voice -UseBasicParsing -OutFile .\voice.wav
```

curl:

```bash
curl -o voice.wav http://127.0.0.1:8059/v1/voice
```

Python:

```python
import requests

base_url = "http://127.0.0.1:8059"
response = requests.get(f"{base_url}/v1/voice", timeout=60)
response.raise_for_status()
with open("voice.wav", "wb") as output_file:
    output_file.write(response.content)
```

### 8.15 GET /v1/audio

Downloads the latest generated audio file through the generic artifact route.

This is the preferred route for new clients. For voice generation it returns
the same latest audio payload as `/v1/voice`. For Stable Audio prompt-to-sound
generation it returns the latest generated sound as `audio.wav`.

Request:

```http
GET /v1/audio
```

Success after Stable Audio generation:

```text
HTTP 200
Content-Type: audio/wav
Content-Disposition: attachment; filename="audio.wav"
```

Failure when no audio is available:

```json
{
  "error_code": "not_found",
  "message": "No generated audio is available yet.",
  "details": null,
  "unsupported_capability": null
}
```

PowerShell:

```powershell
iwr http://127.0.0.1:8059/v1/audio -UseBasicParsing -OutFile .\audio.wav
```

curl:

```bash
curl -o audio.wav http://127.0.0.1:8059/v1/audio
```

Python:

```python
import requests

base_url = "http://127.0.0.1:8059"
response = requests.get(f"{base_url}/v1/audio", timeout=60)
response.raise_for_status()
with open("audio.wav", "wb") as output_file:
    output_file.write(response.content)
```

### 8.16 GET /v1/server

Returns runtime identity and API configuration details.

Request:

```http
GET /v1/server
```

Response:

```json
{
  "service": "VoiceWeaver",
  "runtime_version": "1.5.0",
  "api_version": "v1",
  "host": "127.0.0.1",
  "port": 8059,
  "base_url": "http://127.0.0.1:8059",
  "auth_mode": "auto",
  "auth_enabled": false,
  "models_root": "models",
  "outputs_root": "outputs",
  "logs_root": "logs"
}
```

### 8.17 POST /v1/models/rescan

Forces the runtime to rescan the local `models/` directory immediately.

Request:

```http
POST /v1/models/rescan
```

Response:

- returns the same list shape as `GET /v1/models`
- rewrites `outputs/models_available.json` with the refreshed discovery result
- does not search online and does not download or delete model files

## 9. Full Integration Examples

### 9.1 Python: Discover, Load, Generate Custom Voice, Download

```python
import time
import requests

BASE_URL = "http://127.0.0.1:8059"


def request_json(method, path, **kwargs):
    response = requests.request(method, f"{BASE_URL}{path}", timeout=300, **kwargs)
    if not response.ok:
        raise RuntimeError(response.json())
    return response.json()


models = request_json("GET", "/v1/models")
custom_model = next(
    model for model in models["models"]
    if "custom_voice" in model["supported_generation_modes"]
)

request_json("POST", "/v1/models/load", json={"model_id": custom_model["model_id"]})

status = request_json("GET", "/v1/status")
speaker = status["capabilities"]["supported_presets"][0]

request_json(
    "POST",
    "/v1/voice/custom",
    json={
        "speaker": speaker,
        "language": "en",
        "text": "Hello from VoiceWeaver.",
        "instruct": "Speak warmly with a natural rhythm.",
    },
)

while True:
    status = request_json("GET", "/v1/status")
    operation = status["operation"]
    print(operation["status"], operation["progress_percent"], operation["stage"])
    if operation["status"] in {"completed", "failed"}:
        break
    time.sleep(1)

if status["operation"]["status"] == "failed":
    raise RuntimeError(status["operation"]["error"])

if status["result"]["available"]:
    audio = requests.get(f"{BASE_URL}/v1/voice", timeout=60)
    audio.raise_for_status()
    with open("voice.wav", "wb") as output_file:
        output_file.write(audio.content)
```

### 9.2 Python: Discover, Load Base Model, Clone Voice, Download

```python
import time
import requests

BASE_URL = "http://127.0.0.1:8059"


def request_json(method, path, **kwargs):
    response = requests.request(method, f"{BASE_URL}{path}", timeout=300, **kwargs)
    if not response.ok:
        raise RuntimeError(response.json())
    return response.json()


models = request_json("GET", "/v1/models")
clone_model = next(
    model for model in models["models"]
    if "clone" in model["supported_generation_modes"]
)

request_json("POST", "/v1/models/load", json={"model_id": clone_model["model_id"]})

with open("sample.wav", "rb") as sample_file:
    request_json(
        "POST",
        "/v1/voice/clone",
        files={"voice_sample": ("sample.wav", sample_file, "audio/wav")},
        data={
            "sample_text": "Transcript of the sample voice.",
            "language": "en",
            "text": "This line will be synthesized using the cloned voice.",
        },
    )

while True:
    status = request_json("GET", "/v1/status")
    if status["operation"]["status"] in {"completed", "failed"}:
        break
    time.sleep(1)

if status["operation"]["status"] == "failed":
    raise RuntimeError(status["operation"]["error"])

audio = requests.get(f"{BASE_URL}/v1/voice", timeout=60)
audio.raise_for_status()
with open("voice.wav", "wb") as output_file:
    output_file.write(audio.content)
```

### 9.3 Python: Discover, Load Stable Audio, Generate Sound, Download

```python
import time
import requests

BASE_URL = "http://127.0.0.1:8059"


def request_json(method, path, **kwargs):
    response = requests.request(method, f"{BASE_URL}{path}", timeout=600, **kwargs)
    if not response.ok:
        raise RuntimeError(response.json())
    return response.json()


models = request_json("GET", "/v1/models")
sound_model = next(
    model for model in models["models"]
    if "sound_prompt" in model["supported_generation_modes"]
)

request_json("POST", "/v1/models/load", json={"model_id": sound_model["model_id"]})

request_json(
    "POST",
    "/v1/sound/prompt",
    json={
        "prompt": "A hammer hitting a wooden surface.",
        "negative_prompt": "low quality, distorted",
        "duration_seconds": 5,
        "guidance_scale": 7,
        "num_inference_steps": 50,
        "seed": 123,
    },
)

while True:
    status = request_json("GET", "/v1/status")
    if status["operation"]["status"] in {"completed", "failed"}:
        break
    time.sleep(1)

if status["operation"]["status"] == "failed":
    raise RuntimeError(status["operation"]["error"])

audio = requests.get(f"{BASE_URL}/v1/audio", timeout=60)
audio.raise_for_status()
with open("audio.wav", "wb") as output_file:
    output_file.write(audio.content)
```

## 10. AI Agent Integration Instructions

An AI agent building a client should follow these rules:

- Use `GET /v1/models` before loading any model.
- Select a model by `supported_generation_modes`, not by hardcoded name.
- Use `POST /v1/models/load` before generation.
- After load, call `GET /v1/status` and inspect `capabilities`.
- Only call a voice endpoint if its mode is present in
  `capabilities.supported_generation_modes`.
- Use `/v1/voice/design` for `definition`.
- Use `/v1/voice/clone-prompt` to initialize reusable clone prompts at
  session start when you want client-owned prompt reuse.
- Use `/v1/voice/clone` for `clone`.
- Use `/v1/voice/clone-from-prompt` to generate later clone outputs from a
  stored reusable prompt artifact.
- Use `/v1/voice/custom` for `custom_voice`.
- Use `/v1/voice/preset` only for `preset`.
- Use `/v1/sound/prompt` for `sound_prompt`.
- Poll `GET /v1/status` until `operation.status` is `completed` or `failed`.
- If status is `failed`, surface `operation.error.message` to the user.
- Download `GET /v1/audio` only when `result.available` is `true`.
- Existing voice clients may keep using `GET /v1/voice` for generated voice
  output.
- Do not invent job ids, artifact ids, queues, or separate result endpoints.
- Do not treat `voice_clone_prompt` as a server-owned profile or assume the
  runtime persists it between restarts.
- Do not call removed endpoints such as `/v1/results/latest`,
  `/v1/operations/current`, `/v1/models/active`, or `/v1/models/capabilities`.
- Expect generation operations to take time and keep client interfaces
  non-blocking.
- Treat `busy` as retryable after the current operation reaches a terminal
  state.

Recommended client state machine:

```text
startup
  -> get models
  -> choose model
  -> load model
  -> poll status until load completed
  -> inspect capabilities
  -> render only supported generation forms
  -> submit generation request
  -> poll status until completed or failed
  -> if completed and result.available, download /v1/audio
```

## 11. Validation Checklist For Client Developers

Minimum manual validation:

- `GET /v1/health` returns `status = ok`
- `GET /v1/models` returns at least one model
- loading a missing model returns `model_not_found`
- `POST /v1/models/unload` with no model loaded returns `null`
- `GET /v1/status` reports idle state before loading
- loading a model updates status and capabilities
- unsupported mode requests return `unsupported_generation_mode`
- a supported generation request completes or returns a clear failure
- `GET /v1/voice` returns `404` before generation
- `GET /v1/voice` downloads `voice.wav` after successful generation
- `GET /v1/audio` downloads the latest generated audio after successful
  generation
- loading Stable Audio Open reports `sound_prompt`
- `POST /v1/sound/prompt` rejects an empty prompt

## 12. Limitations

- Only one model can be loaded at a time.
- Only one mutating operation can run at a time.
- There is no queue.
- Generation/load/unload operation cancellation is not exposed.
- Generation result history is not exposed through REST; only the current or
  most recent operation is exposed.
- `supported_presets` currently also carries Qwen CustomVoice speaker ids.
  Future versions may add a clearer `supported_speakers` field.
- Model-specific parameter validation is adapter-dependent. Clients may send
  `model_parameters`, but unsupported parameters may be ignored by the adapter
  until stricter validation is added.
- Stable Audio Open v1 exposes one output per request. `num_outputs` is not
  part of the REST contract.
- Stable Audio Open can be slow and memory-intensive on CPU; CUDA-capable
  Torch is recommended for real generation.
