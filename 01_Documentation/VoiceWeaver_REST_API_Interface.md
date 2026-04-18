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
- UI developers building a separate browser or desktop interface
- AI coding agents that need enough contract detail to generate a working
  client integration

The current runtime API is model-first and operation-based:

- discover local models
- load one model
- query runtime status and loaded-model capabilities
- run one voice generation operation at a time
- poll status until completion
- download the generated `voice.wav`

The currently implemented adapter set is Qwen-only. The API remains shaped so
future local adapters can be added without changing the top-level workflow.

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

Health and the local browser UI are public. Versioned runtime routes under
`/v1`, including `/v1/server`, `/v1/model-catalog`, and the download-control
endpoints, are protected only when effective auth is enabled.

For `POST /v1/voice/clone`, the multipart form fields `sample_text`,
`language`, and `text` are required and must be non-empty strings.

## 4. Endpoint Summary

```text
GET  /v1/health
GET  /v1/server
GET  /v1/model-catalog
GET  /v1/models
POST /v1/models/load
POST /v1/models/unload
DELETE /v1/models/{model_id}
POST /v1/models/rescan
POST /v1/models/download
GET  /v1/models/download
GET  /v1/models/download/status
POST /v1/models/download/cancel
GET  /v1/status
POST /v1/voice/design
POST /v1/voice/clone
POST /v1/voice/custom
POST /v1/voice/preset
GET  /v1/voice
```

Primary integration flow:

```text
GET /v1/models
POST /v1/models/load
GET /v1/status
POST /v1/voice/<mode>
GET /v1/status until operation.status is completed or failed
GET /v1/voice
```

## 5. Runtime Model

VoiceWeaver runs one model and one operation at a time.

Rules:

- only one model can be loaded at once
- loading a new model unloads the previously loaded model first
- only one load, unload, or generation operation can run at a time
- concurrent mutating requests return `busy`
- `GET /v1/status` is the single polling endpoint
- `GET /v1/voice` downloads the latest completed generation audio
- loading, unloading, startup, and new generation delete any previous
  generated `voice.wav`
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

Generic supported modes:

```text
definition
clone
custom_voice
preset
```

`preset` is retained for future non-Qwen adapters. Qwen CustomVoice uses
`custom_voice`, not `preset`.

Today only the Qwen adapter is registered in the runtime. `OmniVoice` and
`VoxCPM2` remain future adapter targets, not active REST-backed backends.

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
busy
not_found
unexpected_error
```

HTTP status behavior:

- `400` for most request, model, adapter, and capability errors
- `401` for auth errors
- `404` for unavailable generated audio
- `409` for `busy`
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
    "repetition_penalty": 1.05
  },
  "device_mode": "cpu",
  "issues": null
}
```

Notes:

- `supported_presets` is also used today to report Qwen CustomVoice speakers.
- `status` is `healthy` or `unhealthy` for discovered models.
- unhealthy models may have empty capabilities and an `issues` array.

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
generate_voice_design
generate_voice_clone
generate_custom_voice
generate_voice_preset
```

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

Request:

```http
GET /v1/models
```

Response:

```json
{
  "service": "VoiceWeaver",
  "runtime_version": "1.0.0",
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
        "top_k": 50
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
  "runtime_version": "1.0.0",
  "active_model": null,
  "capabilities": {
    "service": "VoiceWeaver",
    "runtime_name": "VoiceWeaver",
    "runtime_version": "1.0.0",
    "api_version": "v1",
    "active_model": null,
    "status": "idle",
    "backend_name": null,
    "device_mode": null,
    "supported_languages": [],
    "supported_generation_modes": [],
    "supported_presets": null,
    "default_model_parameters": null,
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
  "runtime_version": "1.0.0",
  "active_model": {
    "model_id": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "backend_name": "qwen",
    "status": "ready",
    "supported_generation_modes": ["custom_voice"],
    "supported_languages": ["en"],
    "supported_presets": ["vivian", "serena"],
    "default_model_parameters": {
      "temperature": 0.9,
      "top_k": 50
    },
    "device_mode": "cpu",
    "issues": null
  },
  "capabilities": {
    "service": "VoiceWeaver",
    "runtime_name": "VoiceWeaver",
    "runtime_version": "1.0.0",
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
      "top_k": 50
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
- download audio only when `result.available` is `true`
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

### 8.8 POST /v1/voice/clone

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

- the runtime writes the uploaded sample to `outputs/_temp_*_reference.wav`
  during generation
- the temp file is deleted after Qwen completes or fails
- clients do not need to manage this temp file

### 8.9 POST /v1/voice/custom

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

### 8.10 POST /v1/voice/preset

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
- the shipped browser UI does not expose a dedicated preset-generation form
- the registered Qwen adapter does not currently report `preset` capability

### 8.11 GET /v1/voice

Downloads the generated WAV file.

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

### 8.12 GET /v1/server

Returns runtime identity and API configuration details.

Request:

```http
GET /v1/server
```

Response:

```json
{
  "service": "VoiceWeaver",
  "runtime_version": "1.0.0",
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

### 8.13 GET /v1/model-catalog

Returns the static catalog of supported downloadable models.

Request:

```http
GET /v1/model-catalog
```

Response:

```json
{
  "service": "VoiceWeaver",
  "api_version": "v1",
  "catalog": [
    {
      "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
      "display_name": "Qwen 1.7B Base Model",
      "backend_name": "qwen",
      "source": "huggingface",
      "repository_id": "Qwen/Qwen3-TTS-12Hz-1.7B",
      "target_folder": "Qwen3-TTS-12Hz-1.7B-Base",
      "supported_generation_modes": ["clone"],
      "requires_auth": false,
      "size_hint": "large",
      "license_note": "Review upstream model license before use."
    }
  ]
}
```

### 8.14 POST /v1/models/download

Starts a background model download workflow.

Request body:

```json
{
  "model_id": "Qwen3-TTS-12Hz-1.7B-VoiceDesign"
}
```

Response:

```json
{
  "download_id": "b76f8f6c-8a71-4d31-a998-83e509414ef1",
  "model_id": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
  "status": "resolving",
  "progress_percent": 0,
  "stage": "Preparing download.",
  "bytes_downloaded": null,
  "bytes_total": null,
  "current_file": null,
  "started_at": "2026-04-17T09:00:00+00:00",
  "updated_at": "2026-04-17T09:00:00+00:00",
  "error": null
}
```

Current implementation note:

- the shipped implementation currently runs a simulated background download
  flow while the real Hugging Face transfer integration is still pending

### 8.15 GET /v1/models/download/status

Returns the current or most recent download status snapshot.

Request:

```http
GET /v1/models/download/status
```

Compatibility note:

- `GET /v1/models/download` remains available and returns the same payload

### 8.16 POST /v1/models/download/cancel

Cancels the active background model download command.

Request:

```http
POST /v1/models/download/cancel
```

Response:

```text
HTTP 204 No Content
```

Compatibility note:

- the legacy `DELETE /v1/models/download` alias remains available for existing
  clients

### 8.17 DELETE /v1/models/{model_id}

Deletes one installed local model directory and refreshes runtime discovery.

Request:

```http
DELETE /v1/models/Qwen3-TTS-12Hz-1.7B-Base
```

Response:

```text
HTTP 204 No Content
```

Failure cases:

- `model_not_found` when the directory does not exist
- `model_in_use` when the target model is currently loaded
- `invalid_request` when the model identifier is not path-safe

### 8.18 POST /v1/models/rescan

Forces the runtime to rescan the local `models/` directory immediately.

Request:

```http
POST /v1/models/rescan
```

Response:

- returns the same list shape as `GET /v1/models`
- rewrites `outputs/models_available.json` with the refreshed discovery result

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

## 10. AI Agent Integration Instructions

An AI agent building a client should follow these rules:

- Use `GET /v1/models` before loading any model.
- Select a model by `supported_generation_modes`, not by hardcoded name.
- Use `POST /v1/models/load` before generation.
- After load, call `GET /v1/status` and inspect `capabilities`.
- Only call a voice endpoint if its mode is present in
  `capabilities.supported_generation_modes`.
- Use `/v1/voice/design` for `definition`.
- Use `/v1/voice/clone` for `clone`.
- Use `/v1/voice/custom` for `custom_voice`.
- Use `/v1/voice/preset` only for `preset`.
- Poll `GET /v1/status` until `operation.status` is `completed` or `failed`.
- If status is `failed`, surface `operation.error.message` to the user.
- Download `GET /v1/voice` only when `result.available` is `true`.
- Do not invent job ids, artifact ids, queues, or separate result endpoints.
- Do not call removed endpoints such as `/v1/results/latest`,
  `/v1/operations/current`, `/v1/models/active`, or `/v1/models/capabilities`.
- Expect generation operations to take time and make the UI non-blocking.
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
  -> if completed and result.available, download /v1/voice
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

## 12. Limitations

- Only one model can be loaded at a time.
- Only one mutating operation can run at a time.
- There is no queue.
- Model-download cancellation is available, but generation/load/unload
  operation cancellation is not.
- Generation result history is not exposed through REST; only the current or
  most recent operation is exposed.
- `supported_presets` currently also carries Qwen CustomVoice speaker ids.
  Future versions may add a clearer `supported_speakers` field.
- Model-specific parameter validation is adapter-dependent. Clients may send
  `model_parameters`, but unsupported parameters may be ignored by the adapter
  until stricter validation is added.
