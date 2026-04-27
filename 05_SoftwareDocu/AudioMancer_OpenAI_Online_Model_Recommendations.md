<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer OpenAI Online Model Recommendations

## 1. Purpose

This note recommends online OpenAI model profiles for the AudioMancer
AI-assisted workflows that are configured through the `AI Settings` window.

These recommendations are for OpenAI-hosted online models reached through the
OpenAI-compatible backend (`https://api.openai.com/v1`). They are not intended
for local LM Studio profiles or offline models.

## 2. Configurable AI Settings Fields

The current `AI Settings` window exposes the following relevant profile fields:

- `Backend Kind`
- `Base URL`
- `API Key`
- `Model Name`
- `Context Window`
- `Max Output Tokens`
- `Timeout (s)`
- `Temperature`
- `Structured output supported`
- per-operation default profile selectors

The current provider request uses `model`, `messages`, `temperature`, and
`max_tokens`. Reasoning-effort controls are not exposed in the current
AudioMancer UI.

## 3. Recommended Profiles

| Operation | Recommended model | Purpose | Temperature | Context Window | Max Output Tokens | Timeout (s) | Structured output |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| AI Cleanup | `gpt-5.4-nano` | Low-cost cleanup/classification where deterministic post-validation is available. | `0.0` or `0.1` | `400000` | `32768` | `500` | `true` |
| AI Chunking | `gpt-5.4-mini` | Balanced semantic and scene boundary detection at moderate cost. | `0.1` | `400000` | `32768` | `600` | `true` |
| AI Translation | `gpt-5.5` | Highest quality for literary translation, tone, and nuance. Use `gpt-5.4` when cost matters more. | `0.2` | `1000000` | `64000` | `900` | `true` |
| Character Discovery | `gpt-5.4` | Strong source-grounded character identification, alias handling, and voice-definition handoff quality. | `0.1` | `1000000` | `64000` | `700` | `true` |
| Speech Blocks | `gpt-5.4` | Strong dialogue segmentation and speaker-attribution quality without using the flagship model for every chunk. | `0.0` or `0.1` | `1000000` | `64000` | `600` | `true` |

## 4. Default Profile Assignment

Recommended default selectors:

- `Default Cleanup Profile`: `Cleanup_gpt-5.4-nano`
- `Default Chunking Profile`: `Chunking_gpt-5.4-mini`
- `Default Translation Profile`: `Translation_gpt-5.5`
- `Default Character Extraction Profile`: `CharacterDiscovery_gpt-5.4`
- `Default Speech Blocks Profile`: `SpeechBlocks_gpt-5.4`

## 5. Practical Notes

- Keep temperature low for JSON-producing operations. Cleanup, chunking, and
  Speech Blocks should prioritize reproducibility over creative variation.
- Translation can use a slightly higher temperature because style and fluency
  matter, but it should still remain conservative for review stability.
- `Structured output supported` should be enabled for these online OpenAI
  profiles, even though the current provider layer primarily relies on JSON
  prompting and JSON repair.
- `gpt-5.5` is best reserved for the operation where quality has the largest
  direct user-facing impact: translation.
- `gpt-5.4` is the safer default for Character Discovery and Speech Blocks
  because incorrect character identity, speaker attribution, or segmentation can
  cascade into Character Voices and Audio Blocks.
- `gpt-5.4-mini` is a good middle tier for chunking because chunk boundaries
  need judgment but are still easier to review and regenerate than translation.
- `gpt-5.4-nano` is acceptable for cleanup when the deterministic cleanup and
  validation paths remain the primary guardrails.

## 6. Example Profile Names

Suggested profile labels:

- `Cleanup_gpt-5.4-nano`
- `Chunking_gpt-5.4-mini`
- `Translation_gpt-5.5`
- `CharacterDiscovery_gpt-5.4`
- `SpeechBlocks_gpt-5.4`

Use the same OpenAI base URL for all five profiles:

```text
https://api.openai.com/v1
```

Store the API key only in the `AI Settings` window. Do not copy API keys into
documentation, exported project files, or screenshots.
