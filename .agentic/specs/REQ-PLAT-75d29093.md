# REQ-PLAT-75d29093 - Delegate AI output length to providers

## Behavior

Every call to the shared chat-completion provider boundary omits both
`max_tokens` and `max_completion_tokens`. This includes the initial request,
the response-format fallback, retries, and the model-based JSON repair
request. A provider-reported `finish_reason: "length"` remains a failure, but
the diagnostic must not claim that AudioMancer sent a numeric output limit.

## Data / interface

Normalized profiles replace `max_output_tokens` with the positive integer
`output_reserve_tokens`. During settings normalization, an existing profile
without the new field migrates its legacy positive `max_output_tokens` value
to `output_reserve_tokens`; persisted normalized settings no longer contain
the legacy field. The reserve remains local to budget calculations and is not
serialized to a provider request. The shared chat API removes its
`max_output_tokens_override` parameter because no caller may request a
provider-side output cap.

## Examples

A profile with a 32,768-token context and a 16,384-token output reserve may
plan only the source text that fits after that reserve, but its chat payload
contains model, messages, temperature, optional reasoning control, and
optional response format—never an output-token limit.

## Acceptance

Targeted provider, settings, budget, UI, localization, and affected workflow
tests run without network access. No live provider is started or contacted.
