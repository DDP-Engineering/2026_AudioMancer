<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer LM Studio Local Model Recommendations

## 1. Purpose

This note recommends local LM Studio model profiles for AudioMancer
AI-assisted workflows configured through the `AI Settings` window.

These recommendations target a Windows workstation with an NVIDIA RTX 5060 Ti
16 GB GPU and 32 GB system RAM. Controlled overflow into system RAM is accepted,
but the profiles stay conservative because long context windows increase KV
cache memory and can make generation much slower.

The model information below was checked from LM Studio Hub and model cards on
2026-04-27.

## 2. LM Studio Profile Setup

Use LM Studio as an OpenAI-compatible local server:

- `Backend Kind`: OpenAI-compatible
- `Base URL`: `http://localhost:1234/v1`
- `API Key`: any local placeholder value, for example `lm-studio`
- `Model Name`: the LM Studio model identifier shown in the table below
- `Structured output supported`: start with `false` for local profiles

AudioMancer currently sends chat-completion requests with `model`, `messages`,
`temperature`, and `max_tokens`. It uses JSON prompting, JSON parsing, and JSON
repair rather than sending a provider-side schema. Keep `Structured output
supported` disabled until a specific LM Studio build and model revision pass the
prompt-contract tests for the operation.

## 3. Recommended Profiles

| Operation | Recommended LM Studio model | Fallback model | Purpose | Temperature | Context Window | Max Output Tokens | Timeout (s) | Structured output |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| AI Cleanup | `mistralai/mistral-small-3.2` | `openai/gpt-oss-20b` | Stable deterministic cleanup/classification with good instruction following. | `0.0` or `0.05` | `32768` | `8192` | `900` | `false` |
| AI Chunking | `qwen/qwen3-30b-a3b-2507` | `mistralai/mistral-small-3.2` | Long-context semantic and scene boundary detection across multilingual text. | `0.05` | `65536` | `12288` | `1200` | `false` |
| AI Translation | `google/gemma-3-27b` | `qwen/qwen3-30b-a3b-2507` | Multilingual literary translation on a model that still fits the local hardware class. | `0.15` or `0.2` | `32768` | `8192` | `1800` | `false` |
| Character Discovery | `qwen/qwen3-30b-a3b-2507` | `mistralai/mistral-small-3.2` | Source-grounded character identification, aliases, and voice-definition handoff quality. | `0.05` | `65536` | `12288` | `1200` | `false` |
| Speech Blocks | `qwen/qwen3-30b-a3b-2507` | `mistralai/mistral-small-3.2` | Dialogue segmentation and speaker attribution with strong multilingual context handling. | `0.0` or `0.05` | `65536` | `16384` | `1500` | `false` |

## 4. Default Profile Assignment

Recommended default selectors:

- `Default Cleanup Profile`: `Cleanup_LMStudio_MistralSmall3.2_24B`
- `Default Chunking Profile`: `Chunking_LMStudio_Qwen3_30B_A3B_2507`
- `Default Translation Profile`: `Translation_LMStudio_Gemma3_27B`
- `Default Character Extraction Profile`: `CharacterDiscovery_LMStudio_Qwen3_30B_A3B_2507`
- `Default Speech Blocks Profile`: `SpeechBlocks_LMStudio_Qwen3_30B_A3B_2507`

## 5. Hardware And Quantization Notes

- Prefer LM Studio GGUF downloads for this NVIDIA/Windows target. Start with a
  4-bit quantization for the 24B, 27B, and 30B-class models.
- If the model loads but generation stalls or swaps heavily, reduce the
  configured context window from `65536` to `32768` before lowering the model
  size.
- Native context limits such as 128k or 262k are model capabilities, not safe
  default settings for this 16 GB VRAM target. Use them only after measuring
  memory use and generation speed on representative AudioMancer chunks.
- `qwen/qwen3-30b-a3b-2507` is listed by LM Studio as a 30B model. The original
  model card describes 30.5B total parameters and 29.9B non-embedding
  parameters. If the requirement is interpreted as strictly below 30.0B total
  parameters, use `mistralai/mistral-small-3.2` as the primary local model.
- Gemma 3 27B lists an 8192-token maximum output in LM Studio. Keep translation
  chunks sized so the translated JSON response stays below that limit.

## 6. Practical Notes

- For JSON-producing operations, keep temperature near zero and prefer
  regeneration over creative sampling.
- Use Qwen3 30B-A3B 2507 in non-thinking mode for Character Discovery and Speech
  Blocks. The LM Studio profile is useful here because it does not emit
  `<think>` blocks.
- Mistral Small 3.2 is the safest fallback when a local model starts producing
  invalid JSON or repetitive output.
- gpt-oss-20b is useful as a fast local fallback for cleanup and chunking, but
  set its LM Studio reasoning effort to low and verify JSON output before using
  it in production workflows. Avoid it for Speech Blocks until prompt-contract
  tests prove that reasoning text cannot leak into JSON.
- Translation is the operation most likely to expose local-model quality limits.
  For final production translation, compare Gemma 3 27B and Qwen3 30B-A3B on a
  reviewed sample before committing to one model for a full book.

## 7. Example Profile Names

Suggested profile labels:

- `Cleanup_LMStudio_MistralSmall3.2_24B`
- `Chunking_LMStudio_Qwen3_30B_A3B_2507`
- `Translation_LMStudio_Gemma3_27B`
- `CharacterDiscovery_LMStudio_Qwen3_30B_A3B_2507`
- `SpeechBlocks_LMStudio_Qwen3_30B_A3B_2507`
- `Fallback_LMStudio_gpt-oss-20b`

Use the same local base URL for all LM Studio profiles:

```text
http://localhost:1234/v1
```

## 8. Sources Checked

- LM Studio local server documentation: https://lmstudio.ai/docs/developer/core/server
- LM Studio OpenAI-compatible endpoints: https://lmstudio.ai/docs/developer/openai-compat
- Qwen3 30B-A3B 2507 LM Studio page: https://lmstudio.ai/models/qwen/qwen3-30b-a3b-2507
- Qwen3 30B-A3B Instruct 2507 model card: https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507
- Mistral Small 3.2 24B LM Studio page: https://lmstudio.ai/models/mistralai/mistral-small-3.2
- Gemma 3 27B LM Studio page: https://lmstudio.ai/models/google/gemma-3-27b
- gpt-oss 20B LM Studio page: https://lmstudio.ai/models/openai/gpt-oss-20b
- gpt-oss 20B model card: https://huggingface.co/openai/gpt-oss-20b
