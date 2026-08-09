<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# AI Runtime

## 1. Purpose

AI Runtime is the cross-cutting provider boundary for AI-assisted workflows. It
probes configured OpenAI-compatible and Ollama backends, sends cancellable
structured chat requests, budgets context, renders prompts, tracks token use,
and lets operators manage AI profiles and defaults.

## 2. Responsibilities

- Normalize backend discovery responses and connection failures without
  exposing provider-specific payloads to the UI.
- Derive OpenAI-compatible chat and model-probe endpoints through one shared
  version-aware URL policy (`REQ-FUNC-9273a9ed`).
- Associate optional context metadata with its exact effective model and
  preserve successful profile-local discovery across failed probes
  (`REQ-FUNC-20817a63`, `REQ-FUNC-e9d13e10`, `REQ-FUNC-6c33e242`).
- Build conservative context budgets and reject requests whose usable text
  budget is too small.
- Send JSON-oriented chat completions with structured-output fallbacks,
  retained call-local compatibility adaptations, bounded cancellation-aware
  retries, null/refusal handling, hard output-length failure detection,
  response repair, transaction logging, and redaction
  (`REQ-FUNC-23c51ea4`, `REQ-FUNC-18168ed4`, `REQ-FUNC-388c7b18`).
- Load, render, and validate prompt templates with exact placeholders.
- Normalize, merge, restore, and localize provider token usage, deriving a
  missing total from valid input/output counts without changing the durable
  schema (`REQ-FUNC-a0ea278d`).
- Present editable, localized AI profiles/default selectors and persist their
  merged settings through the shared settings controller.

It does not own domain prompts, project-local workflow artifacts, or the
semantic validation of a domain's provider response.

## 3. Implementation Overview

`ai_backend_service.probe_profile` validates a profile URL/backend kind then
normalizes `/v1/models` or Ollama tags results. Generic OpenAI-compatible entries
may carry inline context metadata; LM Studio adds optional native model and
loaded-instance metadata; Ollama queries `/api/show` only for the confirmed
effective model. Operating-system and HTTP protocol failures during response
reading remain inside the normal failed-result boundary.
`llm_provider_service.chat_json`
builds a `/v1/chat/completions` endpoint and request payload, supports response-format and token
parameter compatibility retries retained across the current invocation,
cooperatively cancels both waiting requests and short-sliced exponential retry
backoff, rejects explicit output-length termination before content parsing or
repair, treats null/refused assistant content as non-repairable, parses/repairs
bounded non-truncated JSON responses, and redacts sensitive transaction logs.

`ai_budget_service` calculates prompt, output, safety, and usable-text budgets.
`prompt_template_service` resolves template files and rejects missing or extra
placeholders. `token_usage_service` normalizes provider usage into a common
payload, while `ai_state_note_service` builds the shared enabled-profile
selector contract for Text Chunking, AI Translation, Character Discovery,
Speech Blocks, and narrator generation and produces localized persisted-usage
notes (`REQ-NFR-d559facc`). Cleanup retains its distinct whitespace-label
projection rather than being forced through that shared normalizer. The AI
Settings page owns in-memory profile editing/default selectors.
It tracks the stable profile ID represented by the editor, synchronizes that
owner before selection changes, treats successful probes as authoritative for
discovery, and lets failed probes update status without erasing prior metadata.
Its controller opens, probes, applies, or saves the dialog.

## 4. Dependencies

Internal dependencies include configuration, URL/logging/UI-state/settings
services, and the App Shell dialog host. AI workflow components provide their
own prompts and operation state. External dependencies are standard-library
HTTP/JSON/threading primitives and PySide6 for profile UI; the runtime has no
hard SDK dependency on a particular AI vendor.

## 5. Inputs And Outputs

Inputs include normalized profile dictionaries, model/provider HTTP responses,
prompt template files and replacement values, chat messages/schema, optional
cancellation callbacks, and settings-page edits. Outputs include normalized
model descriptors/probe results, JSON objects, redacted transaction logs,
budget metadata, token-usage payloads/localized notes, and validated merged
settings payloads.

## 6. Data Contracts

A profile carries enabled state, backend kind, base URL, model identifier,
context/output/time-out/temperature values, structured-output support, and
optional API key. Probe results use `success`, `message`, discovered-model
details/count, optional context window, its exact owning model identifier, and
selected-model validity. The context and owner are populated together only for
positive values within the editor-supported range. Successful probes may
replace profile-local discovery, including with an empty model list; failed
probes preserve the last successful model list, discovered model/context,
typed model, and configured context while updating failure status/message.
Automatically discovered context fills the configured value only when its
owner matches the effective model and the operator has not overridden context
(`REQ-FUNC-6f8e52c8`). Token
usage maps the provider's `prompt_tokens`, `completion_tokens`, and
`total_tokens` to input/output/total values plus `usage_available`. Finite
non-negative integral floats normalize to integers, and an absent/null total is
derived only when both input and output exist; a valid reported total remains
authoritative. Persisted usage notes restore only report and operation-metadata
usage; a noncanonical top-level operation-state field is ignored
(`REQ-NFR-6634ea30`). Repair usage is merged with the original response usage.
Prompt rendering requires exact named placeholders. Chat responses must parse
to JSON objects. Null scalar or multipart text is empty; a refusal explanation
becomes a clear safe ValueError, while reasoning-only output remains empty and
never triggers model repair. A provider that explicitly rejects `response_format` is
retried once without it, and one that explicitly rejects `max_tokens` is
retried with `max_completion_tokens`; each adapted payload remains active for
later outer retries in that invocation only. Transient outer retries wait 0.5,
1.0, 2.0, then at most 4.0 seconds, polling cancellation every 0.05 seconds.
Logging redacts sensitive field names before persistence.

OpenAI-compatible generation and Test Connection append
`/v1/chat/completions` and `/v1/models` through `join_endpoint_url` with
duplicate-version collapse enabled. Root and proxy-prefixed bases therefore
gain one version segment, existing `/v1` bases do not duplicate it, and the
shared helper preserves query and fragment data identically for both paths
(`REQ-FUNC-9273a9ed`).

Callers may opt into a strict schema path. Strict calls require a profile that
advertises structured output plus a supplied JSON Schema, may disable the
unconstrained `response_format` fallback and model-based JSON repair, and may
override retry/output-token limits. Cleanup uses this path; existing AI
operations retain the default compatibility behavior.

For the first OpenAI-compatible chat-completion choice, an explicit
`finish_reason` of `"length"` is a hard provider failure: `chat_json` raises a
fixed `RuntimeError` that identifies the provider output-token limit before it
reads message content, parses JSON, performs local repair, or issues a
model-repair request. Providers that omit the field remain compatible, and
other finish reasons keep their existing behavior.

## 7. Workflow Integration

Text Cleanup, Text Chunking, AI Translation, Character Discovery, narrator
generation, and Speech Blocks obtain their selected profile, budgets, prompts,
provider request behavior, and usage notes here. The five behavior-equivalent
strip-normalizing selector wrappers delegate to the shared builder while
keeping their public workflow-specific names and configured-default keys.
Their source coverage and artifact semantics remain domain-owned.

## 8. Usage

Domain services call `context_budget_metadata`, `render_prompt`, and
`chat_json`, passing their own request schema/cancellation/log destination.
Controllers resolve enabled profiles rather than reading settings directly.
The App Shell invokes `show_ai_settings_dialog`; users can add/remove profiles,
switch among profiles without losing dialog-session edits
(`REQ-FUNC-8eba808c`), probe connectivity, select defaults, and save the
resulting settings payload. The middle action is labeled Apply because it
persists without closing; OK persists and closes (`REQ-UX-aa109e16`). Reopening
after Cancel reloads persisted settings, so Cancel continues to discard the
dialog session.

## 9. Validation And Tests

Primary automated coverage:

- `tests/test_ai_backend_service.py`
- `tests/test_ai_budget_service.py`
- `tests/test_ai_state_note_service.py`
- `tests/test_prompt_template_service.py`
- `tests/test_token_usage_service.py`
- `tests/test_llm_provider_service.py`
- `tests/test_url_service.py`
- `tests/test_ai_settings_page.py`
- `tests/test_ai_settings_ui_controller.py`

These cover backend models/failures including response-read containment,
provider-specific exact-model context discovery, profile switching/mutation
ownership, failed-probe retention/settings reload, manual context overrides,
context budgets, token
normalization including derived totals and integral floats, merge/ordered
restore and localized notes, prompt placeholder rules, null/refusal and
multipart chat content, exact retained compatibility request sequences,
bounded retry timing/backoff cancellation, response-wait cancellation,
redaction, and profile dialog editing/probing/persistence. Minimum validation after a change:
run the focused modules above with `uv run pytest`, plus
`uv run python -m py_compile` and `uv run ruff check` on changed files.

`test_llm_provider_service.py` additionally verifies that both malformed and
otherwise valid output-length-limited responses fail after one provider
request, log `parsed_failure` rather than repaired success, preserve normal
`stop` and omitted-finish-reason parsing, and leave non-truncated
malformed-response model repair available.

## 10. Limitations And Future Work

Token counts are conservative estimates rather than provider tokenizers.
Provider networking remains synchronous inside the request worker, so timely
cancellation of an in-flight HTTP operation depends on polling/timeout behavior;
retry backoff itself is cancellation-aware. The settings-page suite
covers the current UI contract, but not live remote backend integration; that
requires controlled manual/provider testing. Domain services must still
validate output schemas beyond JSON-object parsing.

Explicit output-length termination is a hard provider failure and is never
repairable JSON.

## Files

From the adopted component map:

- `04_Software/AudioMancer/src/audiomancer/services/ai_backend_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ai_budget_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ai_state_note_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/settings_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/cleanup_ai_adjudication_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ai_chunking_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/prompt_template_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/token_usage_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/ai_settings_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/ai_settings_page.py`
- `04_Software/AudioMancer/tests/test_ai_backend_service.py`
- `04_Software/AudioMancer/tests/test_ai_budget_service.py`
- `04_Software/AudioMancer/tests/test_ai_settings_ui_controller.py`
- `04_Software/AudioMancer/tests/test_ai_settings_page.py`
- `04_Software/AudioMancer/tests/test_ai_state_note_service.py`
- `04_Software/AudioMancer/tests/test_llm_provider_service.py`
- `04_Software/AudioMancer/tests/test_settings_service.py`
- `04_Software/AudioMancer/tests/test_cleanup_adjudication_contract.py`
- `04_Software/AudioMancer/tests/test_ai_chunking_service.py`
- `04_Software/AudioMancer/tests/test_ai_translation_service.py`
- `04_Software/AudioMancer/tests/test_main_window_ai_profiles.py`
- `04_Software/AudioMancer/tests/test_prompt_template_service.py`
- `04_Software/AudioMancer/tests/test_token_usage_service.py`
