<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer ChatGPT Subscription Model Recommendations

## Setup

Select `chatgpt_subscription` in AI Settings and sign in through the browser or
with a device code. No API key is needed. Subscription allowance is separate from
API billing. These recommendations cover subscription profiles; local profiles
are described in the LM Studio guide.

The primary model list refreshes from the account catalog; Refresh models updates
it manually. Test model separately verifies text access and strict schema support.
AI Cleanup requires successful strict schema verification.

## Starting recommendations

These are starting points balancing audiobook quality and consumption, not measured
benchmarks on your books. Compare a representative chapter before a whole-book run.
Availability and reasoning options depend on the current account catalog.

| AudioMancer step | Recommended model | Reasoning effort | Guidance |
| --- | --- | --- | --- |
| Text Cleanup — optional AI assistance | GPT-5.6 Luna | Low | Bounded classification of ambiguous text boundaries. Try Terra if decisions are unreliable. Test model must verify strict schema support. |
| AI Text Chunking | GPT-5.6 Terra | Low | Identifies coherent scenes and boundaries. Use Medium for complicated scene transitions. |
| Book Analysis | GPT-5.6 Sol | Medium | Summarization and consolidation require understanding relationships across the book. |
| AI Translation | GPT-5.6 Sol | Medium | Prioritizes meaning, literary tone and dialogue consistency. Terra Medium is the economical alternative. |
| Characters — discovery and profiles | GPT-5.6 Terra | Medium | Balances extraction quality with consumption. Use Sol Medium for large casts, aliases or ambiguous identities. |
| Narrator Voice — written voice description | GPT-5.6 Terra | Low | A small creative task that usually needs little extended reasoning. |
| Character Voices — voice samples | No ChatGPT model | — | Audio generation uses the configured TTS provider. |
| Speech Blocks — narrator and characters | GPT-5.6 Terra | Medium | Speaker attribution and narration/dialogue separation need careful interpretation. Use Sol Medium for difficult dialogue. |
| Speech Blocks — same narrator | No ChatGPT model | — | Uses deterministic sentence packing. |
| Audio Blocks | No ChatGPT model | — | Uses the configured TTS provider. |
| Audio Assembly / export | No ChatGPT model | — | Audio processing and assembly do not require an LLM. |

## Reasoning and context

Choose explicit Low or Medium for consistent preferences. Reserve High for cases
where a chapter comparison demonstrates an improvement. GPT-6 Astra Medium is an
escalation option for difficult material; XHigh, Max and Ultra are not routine
recommendations. Higher reasoning uses more tokens and time; API prices do not
translate directly into subscription savings.

Selecting a model fills Context Window from its reported default. You may edit it;
refreshing or reopening settings preserves that override until another model is
selected. Unknown defaults retain the existing value. Temperature is controlled
by the provider. Output Reserve is a planning allowance, not a transmitted output
limit. Changing reasoning effort starts a new Book Analysis candidate rather than
resuming checkpoints produced with a different effort.

Model discovery does not prove inference or schema compatibility. Keep credentials
in AudioMancer's protected store or select session-only storage. Audio generation
uses the configured TTS service, not this subscription connection.

## Reference

- [OpenAI model and reasoning guidance](https://learn.chatgpt.com/docs/models)
