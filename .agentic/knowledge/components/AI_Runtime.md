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
- Build conservative context budgets and reject requests whose usable text
  budget is too small.
- Send JSON-oriented chat completions with structured-output fallbacks,
  retries, cancellation, response repair, transaction logging, and redaction.
- Load, render, and validate prompt templates with exact placeholders.
- Normalize, merge, restore, and localize provider token usage.
- Present editable, localized AI profiles/default selectors and persist their
  merged settings through the shared settings controller.

It does not own domain prompts, project-local workflow artifacts, or the
semantic validation of a domain's provider response.

## 3. Implementation Overview

`ai_backend_service.probe_profile` validates a profile URL/backend kind then
normalizes `/models` or Ollama tags results. `llm_provider_service.chat_json`
builds a chat endpoint and request payload, supports response-format and token
parameter compatibility retries, cooperatively cancels waiting requests,
parses/repairs bounded JSON responses, and redacts sensitive transaction logs.

`ai_budget_service` calculates prompt, output, safety, and usable-text budgets.
`prompt_template_service` resolves template files and rejects missing or extra
placeholders. `token_usage_service` normalizes provider usage into a common
payload, while `ai_state_note_service` produces localized persisted-usage
notes. The AI Settings page owns in-memory profile editing/default selectors;
its controller opens, probes, applies, or saves the dialog.

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
details/count, optional context window, and selected-model validity. Token
usage maps the provider's `prompt_tokens`, `completion_tokens`, and
`total_tokens` to input/output/total values plus `usage_available`; repair
usage is merged with the original response usage. Prompt rendering requires
exact named placeholders. Chat responses must parse to JSON objects. A provider
that explicitly rejects `response_format` is retried once without it, and one
that explicitly rejects `max_tokens` is retried with `max_completion_tokens`;
logging redacts sensitive field names before persistence.

## 7. Workflow Integration

Text Cleanup, Text Chunking, AI Translation, Character Discovery, narrator
generation, and Speech Blocks obtain their selected profile, budgets, prompts,
provider request behavior, and usage notes here. Their source coverage and
artifact semantics remain domain-owned.

## 8. Usage

Domain services call `context_budget_metadata`, `render_prompt`, and
`chat_json`, passing their own request schema/cancellation/log destination.
Controllers resolve enabled profiles rather than reading settings directly.
The App Shell invokes `show_ai_settings_dialog`; users can add/remove profiles,
probe connectivity, select defaults, and save the resulting settings payload.

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

These cover backend models/failures, context budgets, token
normalization/merge/ordered restore and localized notes, prompt placeholder
rules, chat JSON parsing/retries/cancellation/format fallbacks/redaction, and
profile dialog editing/probing/persistence. Minimum validation after a change:
run the focused modules above with `uv run pytest`, plus
`uv run python -m py_compile` and `uv run ruff check` on changed files.

## 10. Limitations And Future Work

Token counts are conservative estimates rather than provider tokenizers.
Provider networking remains synchronous inside the request worker, so timely
cancellation depends on polling/timeout behavior. The settings-page suite
covers the current UI contract, but not live remote backend integration; that
requires controlled manual/provider testing. Domain services must still
validate output schemas beyond JSON-object parsing.
