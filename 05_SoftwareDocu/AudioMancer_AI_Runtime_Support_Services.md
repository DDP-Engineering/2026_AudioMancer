<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer AI Runtime Support Services

## 1. Purpose

Documents the small service helpers that support AI workflows without owning a
full operator page:

- `src/audiomancer/services/ai_backend_service.py`
- `src/audiomancer/services/ai_budget_service.py`
- `src/audiomancer/services/ai_state_note_service.py`
- `src/audiomancer/services/prompt_template_service.py`
- `src/audiomancer/services/token_usage_service.py`
- `src/audiomancer/services/url_service.py`
- `src/audiomancer/services/time_service.py`

These helpers keep backend probing, prompt rendering, token accounting,
operator note text, URL normalization, and UTC timestamp formatting consistent
across cleanup, chunking, translation, character discovery, and speech-block
generation.

## 2. Responsibilities

- probe configured AI profiles and normalize discovered model metadata
- estimate conservative local context budgets when a model profile exposes a
  context window
- render prompt templates from `prompts/*.txt` with exact placeholder checking
- normalize provider-reported token usage and merge cumulative usage payloads
- render shared AI token-usage notes for page-state services
- join and trim REST endpoint URLs without double slashes or duplicated paths
- produce stable UTC ISO timestamps for persisted operation state

They do not own workflow prompts, provider chat-completion requests, UI
controller behavior, or project artifact reset policy.

## 3. Implementation Overview

Main public entrypoints:

- `ai_backend_service.probe_profile(...)`
- `ai_budget_service.estimate_text_tokens(...)`
- `ai_budget_service.available_text_budget(...)`
- `ai_budget_service.context_budget_metadata(...)`
- `ai_state_note_service.build_token_usage_notes(...)`
- `prompt_template_service.load_prompt(...)`
- `prompt_template_service.render_prompt(...)`
- `prompt_template_service.validate_required_prompts(...)`
- `token_usage_service.empty_token_usage(...)`
- `token_usage_service.normalize_provider_usage(...)`
- `token_usage_service.coerce_token_usage(...)`
- `token_usage_service.merge_token_usage(...)`
- `token_usage_service.restore_token_usage(...)`
- `url_service.join_endpoint_url(...)`
- `url_service.remove_trailing_endpoint(...)`
- `time_service.utc_now_iso()`

`ai_backend_service` supports OpenAI-compatible `/models` probing and Ollama
`/api/tags` probing. It uses the shared logging service and URL helpers, then
returns normalized success/failure payloads for settings UI state.

`prompt_template_service` resolves prompt names under the app prompt root,
loads UTF-8 text, and rejects missing or extra placeholders so a prompt change
cannot silently drop required workflow data.

`token_usage_service` provides the shared token-usage contract used by AI
operation reports, modal progress updates, and page notes.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config`
- `audiomancer.services.logging_service`
- `audiomancer.services.ui_state_service`

External dependencies:

- Python standard library: `json`, `urllib`, `pathlib`, `re`, `datetime`
- AI backend HTTP endpoints for profile probing

## 5. Inputs And Outputs

Inputs:

- AI profile dictionaries from settings
- prompt template names and placeholder values
- OpenAI-compatible response `usage` dictionaries
- base URLs and endpoint paths

Outputs:

- provider probe result dictionaries
- budget metadata dictionaries
- rendered prompt strings
- normalized token-usage dictionaries
- localized operator note strings
- normalized endpoint URLs
- UTC timestamps such as `2026-05-06T12:00:00Z`

## 6. Data Contracts

Token usage payload:

```python
{
    "input_tokens": int | None,
    "output_tokens": int | None,
    "total_tokens": int | None,
    "usage_available": bool,
}
```

Budget metadata includes the source context window, reserved output tokens,
safety tokens, estimated prompt tokens, estimated input tokens, and resulting
available input budget. Tiny or exhausted budgets raise a value error instead
of allowing an impossible AI request.

Prompt rendering requires an exact placeholder set: missing placeholders and
unused values are both treated as errors.

## 7. Workflow Integration

These helpers are consumed by AI cleanup, AI chunking, AI translation,
character discovery, Speech Blocks, AI Settings, and page-state services. They
sit below workflow orchestration and above raw configuration or HTTP payloads.

## 8. Usage

```python
prompt = prompt_template_service.render_prompt(
    "ai_translation_user.txt",
    {"source_text": text, "target_language": "Romanian"},
)
usage = token_usage_service.normalize_provider_usage(response_payload)
metadata = ai_budget_service.context_budget_metadata(profile, prompt, text)
```

## 9. Validation And Tests

Focused tests:

- `tests/test_ai_backend_service.py`
- `tests/test_ai_budget_service.py`
- `tests/test_ai_state_note_service.py`
- `tests/test_prompt_template_service.py`
- token-usage behavior is also covered through AI workflow tests
- `tests/test_operation_runtime_service.py` covers the UTC timestamp helper

Minimum validation after changes:

- `uv run python -m py_compile` for changed service files
- focused `uv run pytest` for the matching helper tests

## 10. Limitations And Future Work

- Token estimates remain conservative approximations, not tokenizer-specific
  counts.
- Backend probing is synchronous and intentionally small in scope.
- Provider-specific token fields outside the OpenAI-compatible `usage` object
  are not normalized yet.
