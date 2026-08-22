<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# VoiceWeaver Voice Clone Prompt Format

## Purpose

This note defines the serialized `voice_clone_prompt` artifact returned by the
VoiceWeaver runtime for reusable Qwen Base voice cloning.

The artifact is client-owned:

- VoiceWeaver computes it
- VoiceWeaver returns it
- the client stores, invalidates, and deletes it
- VoiceWeaver does not assign a long-lived server-owned prompt id or profile

## Canonical Format

The public artifact shape is:

```json
{
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
```

Notes:

- `ref_text` stores the transcript associated with the reusable prompt and is
  used to rebuild the Qwen reference token ids during replay
- `ref_code` and `ref_spk_embedding` are each `null` when the backend did not
  produce that component
- `encoding` is always `base64`
- `shape` is the tensor shape needed to rebuild the tensor
- `dtype` is the serialized tensor dtype used by VoiceWeaver for storage

## Tensor Encoding Rules

VoiceWeaver serializes the prompt tensors into JSON-safe payloads:

- floating-point tensors are normalized to `float32`
- integer tensors are normalized to `int64`
- the tensor bytes are base64-encoded into `data`
- `shape` and `dtype` are stored alongside the bytes

This format is stable for client storage and safe to return in REST payloads.

## Decode Path

When the client later submits `voice_clone_prompt` back to
`POST /voice/clone-from-prompt`, VoiceWeaver:

1. validates the outer artifact shape
2. base64-decodes each tensor payload
3. rebuilds the tensors from `dtype` and `shape`
4. rebuilds a single-item Qwen prompt object that preserves `ref_text`
5. calls Qwen `generate_voice_clone(..., voice_clone_prompt=...)`

The runtime does not recompute prompt features from the original reference
audio during this path.

## Compatibility Validation

VoiceWeaver runs these checks in order and stops at the first failure. The two
error codes split by what the caller has to change to succeed: a `400` means
fix the payload, a `409` means load a different model.

| Check | Code | Status |
|---|---|---|
| payload parses as JSON and validates against the schema | `invalid_voice_clone_prompt` | 400 |
| `format` equals `qwen_voice_clone_prompt_v1` | `invalid_voice_clone_prompt` | 400 |
| `backend_name` matches the active backend | `incompatible_voice_clone_prompt` | 409 |
| `tts_model_type` matches the loaded model | `incompatible_voice_clone_prompt` | 409 |
| `model_id` matches the loaded model exactly | `incompatible_voice_clone_prompt` | 409 |
| `tokenizer_type` matches the loaded model exactly | `incompatible_voice_clone_prompt` | 409 |

An unrecognized `format` is deliberately a `400` rather than a `409`: no model
the runtime can load would accept it, so retrying against a different model
cannot help.

Each `409` carries both sides of the mismatch in `details`, for example
`active_model_id` and `prompt_model_id`.

The prompt is only usable while a Qwen Base model is loaded. Submitting one
with no model loaded fails with `model_not_loaded`, and with a non-clone model
loaded it fails with `unsupported_mode`.
