<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# VoiceWeaver REST API Interface

## 1. Purpose

This document describes the public REST API exposed by the local `VoiceWeaver`
runtime.

It is intended for:

- external developers building applications that connect to VoiceWeaver
- UI developers building a separate browser, desktop, or CLI interface
- AI coding agents that need enough contract detail to generate a working
  client integration

The runtime API is model-first and operation-based:

- discover local models
- load one model, choosing its execution device
- query runtime status and loaded-model capabilities
- run one voice or sound generation operation at a time
- poll status until completion, cancelling if the backend allows it
- download the latest generated audio

The implemented adapter set is Qwen voice models and Stable Audio Open
prompt-to-sound generation.

The runtime holds one operation at a time and names it itself, so a client
polls `GET /status` for the operation in flight rather than tracking
identifiers of its own.

## 2. Base URL

```text
http://127.0.0.1:8059
```

Routes sit at the root. A route named `/status` is reachable at `/status`:

```text
http://127.0.0.1:8059/status
```

Clients that need to distinguish runtime builds read `runtime_version` from
`GET /status` or `GET /models`.

The runtime is headless and serves no browser page at `/`.

Packaged deliveries include offline operator controls beside the headless API
server. Windows packages provide one `VoiceWeaver.ps1` launcher; Linux packages
provide one `voiceweaver.sh` launcher. Each offers an interactive menu and the
direct commands `start`, `stop`, `status`, and `logs`. These controls add no
REST endpoints; they manage the same packaged runtime.

## 3. Security Model

**There is no authentication.** No API key, no bearer token, no auth mode.
Any process that can reach the socket can load models, generate audio, and read
generated output.

The runtime is therefore safe to bind to loopback only. Starting it with
`--host 0.0.0.0` publishes an unauthenticated control surface to the network;
the runtime logs a warning when it detects a non-loopback bind, but it does not
refuse to start. Anything beyond a trusted local machine needs a reverse proxy
that supplies its own authentication.

## 4. Endpoint Summary

Eleven routes:

```text
GET  /status
POST /cancel

GET  /models
POST /models/load
POST /models/unload

POST /voice/design
POST /voice/clone
POST /voice/clone-prompt
POST /voice/clone-from-prompt
POST /sound/prompt

GET  /audio
```

Primary integration flow:

```text
GET /models
POST /models/load
GET /status
POST /voice/<mode> or POST /sound/prompt
GET /status until operation.status is completed, cancelled, or failed
GET /audio
```

## 5. Runtime Model

VoiceWeaver runs one model and one operation at a time.

Rules:

- only one model can be loaded at once
- loading a new model unloads the previously loaded model first
- only one load, unload, or generation operation can run at a time
- concurrent mutating requests return `busy`
- `GET /status` is the single polling endpoint
- `GET /audio` downloads the latest completed generated audio, whether the
  operation was voice or sound generation
- reusable `voice_clone_prompt` artifacts are returned to the client and are
  never assigned runtime-owned profile ids
- clone-prompt creation stores its terminal artifact in
  `status.operation.result`
- `status.result` remains the latest generated audio metadata only, even after
  clone-prompt creation
- loading, unloading, startup, and new generation delete any previous
  generated `voice.wav`
- operation state lives in memory for the life of the process, so a restart
  begins idle with no operation to report
- runtime state files are written atomically, so an interrupted runtime never
  leaves a truncated `models_available.json` or `voice.wav`
- model unload performs Python garbage collection and clears CUDA cache when
  `torch` is available
- `GET /status` includes `device_diagnostics` so clients can distinguish CUDA
  active, CUDA package with CPU fallback, CPU-only Torch, and missing or
  unloadable Torch

Runtime state files are visible under:

```text
04_Software/VoiceWeaver/outputs/
```

Important files:

```text
models_available.json
voice.wav
```

External clients should use the REST API, not these files, unless the
integration is explicitly operator or debug tooling.

## 6. Model Capability Rules

Clients must not hardcode that every model supports every generation mode.
Always inspect:

```json
status.capabilities.supported_generation_modes
```

The complete set of generation modes is:

```text
voice_design
clone
sound_prompt
```

Known model mapping:

```text
Qwen3-TTS-*-Base         -> clone
Qwen3-TTS-*-VoiceDesign  -> voice_design
stable-audio-open-1.0    -> sound_prompt
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

Stable Audio Open uses `sound_prompt`. It is sound generation, not TTS, and
does not take a `language`.

### 6.1 Languages

The runtime offers exactly seven languages:

```text
en  fr  de  it  es  pt  ru
```

A request naming any other language is refused with `unsupported_language`
before the backend is called. Read the per-model list from
`capabilities.supported_languages` rather than assuming this set.

Romanian is not available from these backends at any quality and cannot be
enabled by adding it to a request.

## 7. Shared Response Models

### 7.1 Error Response

All runtime API errors use this shape, and only this shape:

```json
{
  "error_code": "model_not_found",
  "message": "Model 'missing-model' was not found.",
  "details": null
}
```

`details` carries structured context when the runtime has any — for example,
the supported list on `unsupported_language`, or both sides of a mismatch on
`incompatible_voice_clone_prompt`.

One table maps every published code to exactly one HTTP status. A `400` means
change the request; a `409` means change runtime state and retry; a `5xx` means
the operator has to fix the installation or the model directory.

| Code | Status | Meaning |
|---|---|---|
| `invalid_request` | 400 | Schema validation failed |
| `parameter_out_of_range` | 400 | A value fell outside its reported range |
| `invalid_voice_clone_prompt` | 400 | Prompt artifact malformed or wrong format |
| `model_not_found` | 404 | No such model under `models/` |
| `no_generated_audio` | 404 | Nothing generated yet |
| `busy` | 409 | Another operation is running |
| `model_not_loaded` | 409 | No model is loaded |
| `model_unhealthy` | 409 | The model was discovered but cannot serve |
| `not_cancellable` | 409 | Nothing running, or the backend has no interruption point |
| `unsupported_mode` | 409 | The loaded model does not serve that mode |
| `unsupported_language` | 409 | Language outside the offered set |
| `unsupported_device_mode` | 409 | `cuda` requested without usable CUDA |
| `incompatible_voice_clone_prompt` | 409 | Prompt built for a different model or backend |
| `missing_runtime_dependencies` | 409 | A backend extra is not installed |
| `upload_too_large` | 413 | Reference sample above 64 MiB |
| `synthesis_failed` | 500 | The backend raised during generation |
| `empty_audio_output` | 500 | The backend returned no samples |
| `silent_audio_output` | 500 | The backend returned an all-zero waveform |
| `invalid_audio_output` | 500 | The waveform failed validation |
| `audio_serialization_failed` | 500 | The WAV could not be written |
| `model_load_failed` | 500 | Loading raised |
| `adapter_method_missing` | 500 | The adapter lacks a required method |
| `models_audit_invalid` | 500 | The discovery audit payload is malformed |
| `unexpected_error` | 500 | Unclassified failure |

An operation that starts and then fails internally still returns HTTP `200`
with `operation.status = "failed"` and the detail in `operation.error`. The
error envelope above is for requests the runtime refuses outright.

### 7.2 Model Summary

Used in `/models` and `/status.active_model`.

```json
{
  "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
  "backend_name": "qwen",
  "status": "healthy",
  "supported_generation_modes": ["clone"],
  "supported_languages": ["en", "fr", "de", "it", "es", "pt", "ru"],
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

- the fields above are the whole summary; a client reads a model's voice
  options from `supported_generation_modes` and its inputs from the mode's route
- `generation_parameter_ranges` reports client-facing override guidance such as
  Qwen `max_new_tokens` and Stable Audio `duration_seconds`, `guidance_scale`,
  `num_inference_steps`, and `seed`
- `status` is `healthy` or `unhealthy` for discovered models, `ready` or `idle`
  for the runtime view
- unhealthy models may have empty capabilities and a populated `issues` array
- Stable Audio Open models report `backend_name = "stable_audio"`,
  `supported_generation_modes = ["sound_prompt"]`, and no supported languages

### 7.3 Runtime Device Diagnostics

Used in `/status.device_diagnostics`.

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

- `torch_cuda_build = null` means CPU-only Torch is installed
- `torch_cuda_build != null` with `torch_cuda_available = false` means the
  package contains CUDA-capable Torch but no compatible NVIDIA GPU or driver
  was detected, so the runtime falls back to CPU
- these probes are cached per runtime instance, so polling `/status` does not
  repeatedly trigger CUDA test allocations
- the CUDA Toolkit does not need to be installed on the target computer; a
  compatible NVIDIA driver is still required for GPU execution

### 7.4 Current Operation

Used in operation responses and in `/status.operation`.

```json
{
  "operation_id": "19da053e-5c93-4e14-ae24-bae68f70d2ef",
  "kind": "generate_voice_clone",
  "status": "running",
  "target_model_id": "Qwen3-TTS-12Hz-1.7B-Base",
  "progress_percent": 35,
  "stage": "Running Qwen voice clone.",
  "cancellable": false,
  "started_at": "2026-04-15T10:00:00.000000+00:00",
  "updated_at": "2026-04-15T10:00:03.000000+00:00",
  "inputs": {
    "mode": "clone",
    "text": "Hello from VoiceWeaver.",
    "language": "en",
    "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
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
cancelled
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
generate_sound_prompt
```

`cancellable` is a property of the operation in flight, not of the runtime. A
client reads it rather than assuming: Stable Audio generation can stop between
denoising steps, Qwen voice generation cannot.

For `sound_prompt` operations, `inputs.language` is `null`.

## 8. Endpoint Details

### 8.1 GET /models

Discovers local model folders under `models/`.

Side effects:

- runtime startup rebuilds `outputs/models_available.json`
- `GET /models` rewrites `outputs/models_available.json`

Model inventory is the `models/` directory, and both adapters load with
`local_files_only=True`, so a staged directory is the whole source of a model's
weights. To add a model after delivery, copy a valid model folder into
`04_Software/VoiceWeaver/models/` and call `GET /models`; managing model files
is a filesystem operation.

Request:

```http
GET /models
```

Response:

```json
{
  "service": "VoiceWeaver",
  "runtime_version": "1.0.0",
  "models": [
    {
      "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
      "backend_name": "qwen",
      "status": "healthy",
      "supported_generation_modes": ["clone"],
      "supported_languages": ["en", "fr", "de", "it", "es", "pt", "ru"],
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
(iwr http://127.0.0.1:8059/models -UseBasicParsing).Content
```

curl:

```bash
curl http://127.0.0.1:8059/models
```

Python:

```python
import requests

base_url = "http://127.0.0.1:8059"
models = requests.get(f"{base_url}/models", timeout=30).json()
print(models["models"])
```

### 8.2 POST /models/load

Loads one discovered model.

Request body:

```json
{
  "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
  "device_mode": "auto"
}
```

`device_mode` accepts `auto`, `cpu`, or `cuda`, and defaults to `auto`. Only
`auto` falls back: an explicit `cuda` request on a host without usable CUDA is
refused with `unsupported_device_mode` rather than being served on CPU, because
a caller that asked for CUDA and got CPU would discover it only from timings.

Behavior:

- validates `model_id` against discovered models
- if another model is loaded, unloads it first
- deletes previous `outputs/voice.wav`
- loads the requested model
- writes load operation progress to `/status`

Response:

```json
{
  "operation_id": "d4f2b058-59d7-4f92-85aa-bab607f26696",
  "kind": "load_model",
  "status": "completed",
  "target_model_id": "Qwen3-TTS-12Hz-1.7B-Base",
  "progress_percent": 100,
  "stage": "Completed.",
  "cancellable": false,
  "started_at": "2026-04-15T10:00:00.000000+00:00",
  "updated_at": "2026-04-15T10:00:05.000000+00:00",
  "inputs": null,
  "result": {
    "active_model": "Qwen3-TTS-12Hz-1.7B-Base",
    "backend_name": "qwen",
    "supported_generation_modes": ["clone"],
    "supported_languages": ["en", "fr", "de", "it", "es", "pt", "ru"],
    "default_model_parameters": {
      "temperature": 0.9,
      "top_k": 50
    },
    "generation_parameter_ranges": {},
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

`result.device_mode` reports the device the model actually landed on.

PowerShell:

```powershell
(iwr http://127.0.0.1:8059/models/load `
  -UseBasicParsing `
  -Method Post `
  -Headers @{ "Content-Type" = "application/json" } `
  -Body '{"model_id":"Qwen3-TTS-12Hz-1.7B-Base","device_mode":"auto"}').Content
```

curl:

```bash
curl -X POST http://127.0.0.1:8059/models/load \
  -H "Content-Type: application/json" \
  -d '{"model_id":"Qwen3-TTS-12Hz-1.7B-Base","device_mode":"auto"}'
```

### 8.3 POST /models/unload

Unloads the active model.

Request:

```http
POST /models/unload
```

Behavior:

- if no model is loaded, returns JSON `null`
- if a model is loaded, runs an unload operation
- deletes `outputs/voice.wav`
- runs garbage collection and clears the CUDA cache

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
  "target_model_id": "Qwen3-TTS-12Hz-1.7B-Base",
  "progress_percent": 100,
  "stage": "Completed.",
  "cancellable": false,
  "started_at": "2026-04-15T10:05:00.000000+00:00",
  "updated_at": "2026-04-15T10:05:01.000000+00:00",
  "inputs": null,
  "result": {
    "active_model": null
  },
  "error": null
}
```

### 8.4 GET /status

Returns complete runtime state. This is the single endpoint clients should
poll.

Request:

```http
GET /status
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
    "active_model": null,
    "status": "idle",
    "backend_name": null,
    "device_mode": null,
    "supported_languages": [],
    "supported_generation_modes": [],
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
    "cancellable": false,
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

Response after a completed voice-design generation:

```json
{
  "service": "VoiceWeaver",
  "runtime_version": "1.0.0",
  "active_model": {
    "model_id": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "backend_name": "qwen",
    "status": "ready",
    "supported_generation_modes": ["voice_design"],
    "supported_languages": ["en", "fr", "de", "it", "es", "pt", "ru"],
    "default_model_parameters": {
      "temperature": 0.9,
      "top_k": 50,
      "max_new_tokens": 2048
    },
    "generation_parameter_ranges": {
      "max_new_tokens": {
        "default": 2048,
        "minimum": 128,
        "recommended_maximum": 2048,
        "hard_maximum": 8192,
        "unit": "codec_tokens",
        "approx_audio_seconds_per_token": 0.08333333333333333,
        "approx_default_audio_seconds": 170.66666666666666,
        "approx_recommended_audio_seconds": 170.66666666666666,
        "notes": "Higher values allow longer output but increase generation time, GPU memory use, and the chance of truncated or degenerate output near the model limit."
      }
    },
    "device_mode": "cuda",
    "issues": null
  },
  "capabilities": {
    "service": "VoiceWeaver",
    "runtime_name": "VoiceWeaver",
    "runtime_version": "1.0.0",
    "active_model": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "status": "ready",
    "backend_name": "qwen",
    "device_mode": "cuda",
    "supported_languages": ["en", "fr", "de", "it", "es", "pt", "ru"],
    "supported_generation_modes": ["voice_design"],
    "default_model_parameters": {
      "temperature": 0.9,
      "top_k": 50,
      "max_new_tokens": 2048
    },
    "generation_parameter_ranges": {},
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
    "kind": "generate_voice_design",
    "status": "completed",
    "target_model_id": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "progress_percent": 100,
    "stage": "Completed.",
    "cancellable": false,
    "started_at": "2026-04-15T10:15:00.000000+00:00",
    "updated_at": "2026-04-15T10:15:10.000000+00:00",
    "inputs": {
      "mode": "voice_design",
      "text": "Hello from VoiceWeaver.",
      "language": "en",
      "model_id": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
      "backend_name": "qwen",
      "mode_inputs": {
        "voice_description": "Warm narrator with steady pacing."
      },
      "model_parameters": {},
      "effective_model_parameters": {
        "temperature": 0.9,
        "top_k": 50
      }
    },
    "result": {
      "available": true,
      "mode": "voice_design",
      "model_id": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
      "file_name": "voice.wav",
      "content_type": "audio/wav",
      "size_bytes": 123456,
      "created_at": "2026-04-15T10:15:10.000000+00:00",
      "download_url": "/audio",
      "summary": "Qwen3-TTS-12Hz-1.7B-VoiceDesign | definition | en",
      "inputs": null
    },
    "error": null
  },
  "result": {
    "available": true,
    "mode": "voice_design",
    "model_id": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "file_name": "voice.wav",
    "content_type": "audio/wav",
    "size_bytes": 123456,
    "created_at": "2026-04-15T10:15:10.000000+00:00",
    "download_url": "/audio",
    "summary": "Qwen3-TTS-12Hz-1.7B-VoiceDesign | definition | en",
    "inputs": null
  }
}
```

Client guidance:

- poll every 0.5 to 2 seconds during running operations
- stop polling when `operation.status` is `completed`, `cancelled`, or `failed`
- download audio only when `result.available` is `true`, using the route
  advertised by `result.download_url`
- inspect `operation.error` when status is `failed`

### 8.5 POST /cancel

Asks the operation in progress to stop at its next interruption point.

Request:

```http
POST /cancel
```

There is one operation slot, so no identifier is needed.

Behavior:

- cancellation is cooperative and bounded, not immediate: the call returns once
  the request is recorded, and the operation stays in progress until the backend
  reaches its next check
- a cancelled operation ends with `status = "cancelled"`, not `"failed"`
- if nothing is running, or the running operation has no interruption point,
  the call fails with `not_cancellable` and HTTP `409`

Read `status.operation.cancellable` before offering a cancel control. Stable
Audio generation stops between denoising steps; Qwen voice generation has no
interruption point and always refuses.

Response:

```json
{
  "operation_id": "fb81c875-8452-4d27-a2e2-f6e2391c8cf3",
  "kind": "generate_sound_prompt",
  "status": "running",
  "target_model_id": "stable-audio-open-1.0",
  "progress_percent": 42,
  "stage": "Cancellation requested.",
  "cancellable": true,
  "started_at": "2026-04-15T10:20:00.000000+00:00",
  "updated_at": "2026-04-15T10:20:04.000000+00:00",
  "inputs": null,
  "result": null,
  "error": null
}
```

### 8.6 POST /voice/design

Runs voice-design generation.

Use when the loaded model supports:

```json
["voice_design"]
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

Behavior notes:

- `text`, `language`, and `voice_description` must all be non-empty
- unknown top-level fields are rejected with `invalid_request`
- `model_parameters` overrides are merged with the loaded model defaults, and
  the merged values are what the adapter is actually called with
- a parameter outside its reported range is refused with
  `parameter_out_of_range` rather than clamped

Response:

- `CurrentOperationResponse`
- status may be `completed` or `failed`

PowerShell:

```powershell
(iwr http://127.0.0.1:8059/voice/design `
  -UseBasicParsing `
  -Method Post `
  -Headers @{ "Content-Type" = "application/json" } `
  -Body '{"text":"Hello","language":"en","voice_description":"Warm narrator"}').Content
```

curl:

```bash
curl -X POST http://127.0.0.1:8059/voice/design \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello","language":"en","voice_description":"Warm narrator"}'
```

### 8.7 POST /voice/clone

Runs voice-clone generation from an uploaded reference sample.

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
sample_text: string, required, non-empty
language: string, required, non-empty
text: string, required, non-empty
model_parameters_json: JSON object string, optional
```

Behavior notes:

- the uploaded `voice_sample` is limited to 64 MiB; larger uploads return HTTP
  `413` with error code `upload_too_large`, checked before generation starts
- when provided, `model_parameters_json` is merged with the loaded model
  defaults and the merged values are forwarded to the adapter
- clone defaults cap `max_new_tokens` at `512` and disable `subtalker_dosample`
  whenever `do_sample` is disabled, so a request asking for deterministic output
  does not silently keep a stochastic sub-talker path enabled
- a clone request whose text is heuristically likely to approach the current
  `max_new_tokens` budget logs a warning, and generated audio logs its observed
  duration against the token-derived cap
- an all-zero output near that cap fails with a near-token-limit backend error
  rather than a generic silent-output failure

PowerShell:

```powershell
$form = @{
  voice_sample = Get-Item ".\sample.wav"
  sample_text = "This is the transcript of the reference sample."
  language = "en"
  text = "This is the text to synthesize in the cloned voice."
  model_parameters_json = '{"temperature":0.8}'
}

(iwr http://127.0.0.1:8059/voice/clone `
  -UseBasicParsing `
  -Method Post `
  -Form $form).Content
```

curl:

```bash
curl -X POST http://127.0.0.1:8059/voice/clone \
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
        f"{base_url}/voice/clone",
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
- the temp file is deleted after the backend completes or fails
- clients do not need to manage this temp file

### 8.8 POST /voice/clone-prompt

Creates one reusable voice clone prompt.

Use when the loaded model supports:

```json
["clone"]
```

Content type:

```text
multipart/form-data
```

Form fields:

```text
voice_sample: file, required
sample_text: string, required, non-empty
language: string, required, non-empty
model_parameters_json: JSON object string, optional
```

Note that `text` is **not** a field here — this route creates a reusable
artifact, it does not synthesize.

Behavior notes:

- VoiceWeaver calls the official Qwen `create_voice_clone_prompt(...)` API
- the uploaded `voice_sample` is limited to 64 MiB; larger uploads return HTTP
  `413` with error code `upload_too_large`
- the reusable `voice_clone_prompt` artifact is returned to the client
- VoiceWeaver creates no server-owned profile id, prompt id, or delete API
- `operation.result.voice_clone_prompt` is JSON-serializable and can be stored
  externally by the client
- `status.result` is not replaced by clone-prompt creation, because it remains
  reserved for the latest generated audio metadata
- `outputs/voice.wav` is untouched by this route

Result shape inside `CurrentOperationResponse.result`:

```json
{
  "created_at": "2026-04-23T10:00:00.000000+00:00",
  "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
  "backend_name": "qwen",
  "summary": "Qwen3-TTS-12Hz-1.7B-Base | clone_prompt | en",
  "voice_clone_prompt": {
    "format": "qwen_voice_clone_prompt_v1",
    "backend_name": "qwen",
    "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
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

`VoiceWeaver_Voice_Clone_Prompt_Format.md` specifies this artifact in full.

### 8.9 POST /voice/clone-from-prompt

Runs clone generation from a previously returned prompt, without re-uploading
the reference sample.

Request body:

```json
{
  "voice_clone_prompt": {
    "format": "qwen_voice_clone_prompt_v1",
    "backend_name": "qwen",
    "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
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

- `voice_clone_prompt` may be sent either as the JSON object above or as a JSON
  string containing the same object
- VoiceWeaver decodes the artifact and calls the official Qwen
  `generate_voice_clone(..., voice_clone_prompt=...)` API
- the artifact retains the original reference transcript, so VoiceWeaver can
  rebuild the Qwen reference token ids during replay
- the original reference sample audio is not required in this request

Validation rules:

- a malformed payload, or one whose `format` is unrecognized, returns
  `invalid_voice_clone_prompt` with HTTP `400`
- a `backend_name`, `tts_model_type`, `model_id`, or `tokenizer_type` mismatch
  returns `incompatible_voice_clone_prompt` with HTTP `409`, and `details`
  carries both sides of the mismatch
- submitting one with no model loaded returns `model_not_loaded`
- submitting one while a non-clone model is loaded returns `unsupported_mode`

### 8.10 POST /sound/prompt

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

- `prompt`, non-empty

Optional fields:

| Field | Default | Constraint |
|---|---|---|
| `negative_prompt` | `null` | — |
| `duration_seconds` | `10.0` | greater than 0, at most `47.55` |
| `seed` | `null` | at least 0 |
| `guidance_scale` | `7.0` | at least 0.0 |
| `num_inference_steps` | `100` | at least 1 |

Behavior notes:

- `language` is not part of this request; the stored operation input records
  `language = null`
- the adapter forwards `duration_seconds` to Stable Audio as `audio_end_in_s`;
  `47.55` is the model's own output ceiling, not a runtime choice
- when `seed` is provided, the adapter creates a seeded `torch.Generator`, and
  the same seed reproduces the same output
- one WAV output is generated per request
- completed results use `result.file_name = "audio.wav"` and
  `result.download_url = "/audio"`
- this is the one generation mode that can be cancelled

PowerShell:

```powershell
(iwr http://127.0.0.1:8059/sound/prompt `
  -UseBasicParsing `
  -Method Post `
  -Headers @{ "Content-Type" = "application/json" } `
  -Body '{"prompt":"A hammer hitting a wooden surface","negative_prompt":"low quality, distorted","duration_seconds":5,"guidance_scale":7,"num_inference_steps":50,"seed":123}').Content
```

curl:

```bash
curl -X POST http://127.0.0.1:8059/sound/prompt \
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
response = requests.post(f"{base_url}/sound/prompt", json=payload, timeout=600)
response.raise_for_status()
print(response.json())
```

### 8.11 GET /audio

Downloads the latest generated audio file.

One route serves both voice and sound operations; the response filename is what
distinguishes them.

Request:

```http
GET /audio
```

Success:

```text
HTTP 200
Content-Type: audio/wav
Content-Disposition: attachment; filename="voice.wav"
```

After Stable Audio generation the filename is `audio.wav` instead.

Failure when no audio is available:

```json
{
  "error_code": "no_generated_audio",
  "message": "No generated audio is available yet.",
  "details": null
}
```

That failure arrives with HTTP `404`.

PowerShell:

```powershell
iwr http://127.0.0.1:8059/audio -UseBasicParsing -OutFile .\voice.wav
```

curl:

```bash
curl -o voice.wav http://127.0.0.1:8059/audio
```

Python:

```python
import requests

base_url = "http://127.0.0.1:8059"
response = requests.get(f"{base_url}/audio", timeout=60)
response.raise_for_status()
with open("voice.wav", "wb") as output_file:
    output_file.write(response.content)
```

## 9. Full Integration Examples

### 9.1 Python: Discover, Load, Generate Voice Design, Download

```python
import time
import requests

BASE_URL = "http://127.0.0.1:8059"


def request_json(method, path, **kwargs):
    response = requests.request(method, f"{BASE_URL}{path}", timeout=300, **kwargs)
    if not response.ok:
        raise RuntimeError(response.json())
    return response.json()


models = request_json("GET", "/models")
design_model = next(
    model for model in models["models"]
    if "voice_design" in model["supported_generation_modes"]
)

request_json(
    "POST",
    "/models/load",
    json={"model_id": design_model["model_id"], "device_mode": "auto"},
)

request_json(
    "POST",
    "/voice/design",
    json={
        "text": "Hello from VoiceWeaver.",
        "language": "en",
        "voice_description": "Warm narrator with steady pacing.",
    },
)

while True:
    status = request_json("GET", "/status")
    operation = status["operation"]
    print(operation["status"], operation["progress_percent"], operation["stage"])
    if operation["status"] in {"completed", "cancelled", "failed"}:
        break
    time.sleep(1)

if status["operation"]["status"] == "failed":
    raise RuntimeError(status["operation"]["error"])

if status["result"]["available"]:
    audio = requests.get(f"{BASE_URL}{status['result']['download_url']}", timeout=60)
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


models = request_json("GET", "/models")
clone_model = next(
    model for model in models["models"]
    if "clone" in model["supported_generation_modes"]
)

request_json("POST", "/models/load", json={"model_id": clone_model["model_id"]})

with open("sample.wav", "rb") as sample_file:
    request_json(
        "POST",
        "/voice/clone",
        files={"voice_sample": ("sample.wav", sample_file, "audio/wav")},
        data={
            "sample_text": "Transcript of the sample voice.",
            "language": "en",
            "text": "This line will be synthesized using the cloned voice.",
        },
    )

while True:
    status = request_json("GET", "/status")
    if status["operation"]["status"] in {"completed", "cancelled", "failed"}:
        break
    time.sleep(1)

if status["operation"]["status"] == "failed":
    raise RuntimeError(status["operation"]["error"])

audio = requests.get(f"{BASE_URL}/audio", timeout=60)
audio.raise_for_status()
with open("voice.wav", "wb") as output_file:
    output_file.write(audio.content)
```

### 9.3 Python: Create A Clone Prompt Once, Reuse It Many Times

```python
import json
import time
import requests

BASE_URL = "http://127.0.0.1:8059"


def request_json(method, path, **kwargs):
    response = requests.request(method, f"{BASE_URL}{path}", timeout=300, **kwargs)
    if not response.ok:
        raise RuntimeError(response.json())
    return response.json()


def wait_for_terminal_state():
    while True:
        status = request_json("GET", "/status")
        if status["operation"]["status"] in {"completed", "cancelled", "failed"}:
            return status
        time.sleep(1)


# Once per reference voice: upload the sample and keep the artifact.
with open("sample.wav", "rb") as sample_file:
    request_json(
        "POST",
        "/voice/clone-prompt",
        files={"voice_sample": ("sample.wav", sample_file, "audio/wav")},
        data={
            "sample_text": "Transcript of the sample voice.",
            "language": "en",
        },
    )

status = wait_for_terminal_state()
clone_prompt = status["operation"]["result"]["voice_clone_prompt"]

with open("clone_prompt.json", "w", encoding="utf-8") as prompt_file:
    json.dump(clone_prompt, prompt_file)

# Any number of times afterwards, with no sample upload.
for line in ["First line.", "Second line.", "Third line."]:
    request_json(
        "POST",
        "/voice/clone-from-prompt",
        json={
            "voice_clone_prompt": clone_prompt,
            "language": "en",
            "text": line,
        },
    )
    status = wait_for_terminal_state()
    if status["operation"]["status"] == "failed":
        raise RuntimeError(status["operation"]["error"])
    audio = requests.get(f"{BASE_URL}/audio", timeout=60)
    audio.raise_for_status()
    with open(f"{line[:5]}.wav", "wb") as output_file:
        output_file.write(audio.content)
```

### 9.4 Python: Discover, Load Stable Audio, Generate Sound, Download

```python
import time
import requests

BASE_URL = "http://127.0.0.1:8059"


def request_json(method, path, **kwargs):
    response = requests.request(method, f"{BASE_URL}{path}", timeout=600, **kwargs)
    if not response.ok:
        raise RuntimeError(response.json())
    return response.json()


models = request_json("GET", "/models")
sound_model = next(
    model for model in models["models"]
    if "sound_prompt" in model["supported_generation_modes"]
)

request_json("POST", "/models/load", json={"model_id": sound_model["model_id"]})

request_json(
    "POST",
    "/sound/prompt",
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
    status = request_json("GET", "/status")
    if status["operation"]["status"] in {"completed", "cancelled", "failed"}:
        break
    time.sleep(1)

if status["operation"]["status"] == "failed":
    raise RuntimeError(status["operation"]["error"])

audio = requests.get(f"{BASE_URL}/audio", timeout=60)
audio.raise_for_status()
with open("audio.wav", "wb") as output_file:
    output_file.write(audio.content)
```

## 10. AI Agent Integration Instructions

An AI agent building a client should follow these rules:

- Use `GET /models` before loading any model.
- Select a model by `supported_generation_modes`, not by hardcoded name.
- Use `POST /models/load` before generation.
- After load, call `GET /status` and inspect `capabilities`.
- Only call a generation endpoint if its mode is present in
  `capabilities.supported_generation_modes`.
- Use `/voice/design` for `voice_design`.
- Use `/voice/clone` for `clone` with a reference sample.
- Use `/voice/clone-prompt` once per reference voice when you want client-owned
  prompt reuse, then `/voice/clone-from-prompt` for every later generation.
- Use `/sound/prompt` for `sound_prompt`.
- Poll `GET /status` until `operation.status` is `completed`, `cancelled`, or
  `failed`.
- If status is `failed`, surface `operation.error.message` to the user.
- Download `GET /audio` only when `result.available` is `true`.
- Read `operation.cancellable` before offering a cancel control; do not assume
  every operation can be stopped.
- Read `capabilities.supported_languages` rather than hardcoding the language
  set, and expect a refusal rather than a substitution for anything outside it.
- Read `generation_parameter_ranges` before sending `model_parameters`; an
  out-of-range value is refused, not clamped.
- Track work through `GET /status` alone: the runtime issues the operation id,
  and `/audio` is the one place a result is collected.
- Treat `voice_clone_prompt` as yours to store. The runtime returns it and
  forgets it, so keep it if you want the voice again after a restart.
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
  -> poll status until completed, cancelled, or failed
  -> if completed and result.available, download /audio
```

## 11. Validation Checklist For Client Developers

Minimum manual validation:

- `GET /status` responds before any model is loaded and reports idle state
- `GET /models` returns at least one model
- loading a missing model returns `model_not_found`
- `POST /models/unload` with no model loaded returns `null`
- loading a model updates status and capabilities
- requesting `device_mode: "cuda"` on a CPU-only host returns
  `unsupported_device_mode` rather than loading on CPU
- an unsupported mode request returns `unsupported_mode`
- a request naming a language outside the offered set returns
  `unsupported_language` and carries the supported list
- a `model_parameters` value outside its reported range returns
  `parameter_out_of_range`
- a supported generation request completes or returns a clear failure
- `GET /audio` returns `404` with `no_generated_audio` before generation
- `GET /audio` downloads the generated WAV after successful generation
- loading Stable Audio Open reports `sound_prompt`
- `POST /sound/prompt` rejects an empty prompt
- `POST /cancel` with nothing running returns `not_cancellable`
- `POST /cancel` during Qwen voice generation returns `not_cancellable`
- `POST /cancel` during Stable Audio generation ends the operation as
  `cancelled`
- a reference sample above 64 MiB returns `413` with `upload_too_large`

## 12. Limitations

- Only one model can be loaded at a time.
- Only one mutating operation can run at a time; a second is refused with
  `busy` rather than queued, so retrying is the caller's job.
- Cancellation depends on the backend. Stable Audio generation can be stopped
  between denoising steps; Qwen voice generation cannot be interrupted, and
  load and unload are not cancellable.
- `/status` reports the current or most recent operation, so a client that
  wants a record of earlier runs keeps its own.
- There is no authentication of any kind.
- Model-specific parameter validation is adapter-dependent. Values are checked
  against `generation_parameter_ranges` where the adapter reports one, but a
  parameter the adapter does not describe may be ignored.
- Stable Audio Open produces one output per request, capped at 47.55 seconds.
- Stable Audio Open can be slow and memory-intensive on CPU; CUDA-capable Torch
  is recommended for real generation.
- Romanian and other languages outside the offered set are not available.
