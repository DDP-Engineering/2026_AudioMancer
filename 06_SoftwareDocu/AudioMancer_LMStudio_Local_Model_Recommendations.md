<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer LM Studio Local Model Recommendations

## Example models

Evaluate `Qwen3.8-27B`, `google/gemma-4-12b`, `meta/muse-glimmer` or
`openai/gpt-oss-20b`. Use the exact identifier exposed by your LM Studio server.
These examples are not a measured ranking or a guarantee of compatibility.

Select the `lmstudio` backend and the server's `/v1` URL in AI Settings.
The table gives starting values for context, temperature and reasoning only.
Test a representative chapter; follow the model card if it requires different
sampling settings. These are workload suggestions, not model maximum capacities.

## Starting settings

| Operation | Context (tokens) | Temperature | Reasoning in AudioMancer |
| --- | --- | --- | --- |
| AI Cleanup | 32768 | 0.1 | Provider default |
| AI Chunking | 32768 | 0.1 | Provider default |
| Book Analysis | 32768; try 65536 if needed | 0.2 | Thinking enabled, if supported |
| AI Translation | 32768 | 0.2 | Provider default |
| Character Discovery | 32768; try 65536 if needed | 0.1 | Thinking enabled, if supported |
| Narrator description | 16384 | 0.3 | Provider default |
| Speech Blocks — narrator and characters | 32768 | 0.1 | Thinking enabled, if supported |

## Context and reasoning

Load the intended context in LM Studio first. AudioMancer's Context Window must
not exceed that loaded capacity or the model's supported limit. Start with 32768
for most tasks; try 65536 only when supported and useful, with enough memory.
Changing AudioMancer's value alone does not reload the server model. Larger
context can increase memory use and response time.

Provider default leaves reasoning to LM Studio. Thinking enabled requests Medium
when supported by the endpoint. If unsupported, use Provider default and configure
the model's supported reasoning control in LM Studio. For simple cleanup, chunking
and narrator descriptions, try Low in the LM Studio preset when available.
For gpt-oss-20b, start with Low; compare Medium for analysis or speaker attribution.
Disabling thinking is model-dependent. Local profiles do not use the ChatGPT
subscription's per-model effort selector.

AI Cleanup requires working strict structured output; confirm compatibility
before assigning a model. Same-narrator Speech Blocks, TTS and audio assembly do
not use these LLM settings.

## References

- [LM Studio model configuration](https://lmstudio.ai/docs/python/llm-prediction/parameters)
- [gpt-oss-20b model card](https://huggingface.co/openai/gpt-oss-20b)
