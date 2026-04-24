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
  "model_id": "Qwen3-TTS-12Hz-0.6B-Base",
  "tokenizer_type": "qwen3_tts_tokenizer_12hz",
  "tts_model_type": "base",
  "prompt": {
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

- `ref_code` may be `null`
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
`POST /v1/voice/clone-from-prompt`, VoiceWeaver:

1. validates the outer artifact shape
2. base64-decodes each tensor payload
3. rebuilds the tensors from `dtype` and `shape`
4. reconstructs the Qwen `voice_clone_prompt` dictionary using single-item lists
5. calls Qwen `generate_voice_clone(..., voice_clone_prompt=...)`

The runtime does not recompute prompt features from the original reference
audio during this path.

## Compatibility Validation

VoiceWeaver rejects reusable prompts when any of these checks fail:

- `format` must equal `qwen_voice_clone_prompt_v1`
- `backend_name` must match the active backend
- `tts_model_type` must equal `base`
- `model_id` must match the loaded model exactly
- `tokenizer_type` must match the loaded model exactly

Error codes:

- malformed payload: `invalid_voice_clone_prompt`
- well-formed but incompatible payload: `incompatible_voice_clone_prompt`
