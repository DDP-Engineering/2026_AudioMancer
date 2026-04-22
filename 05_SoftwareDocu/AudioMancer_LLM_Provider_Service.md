<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer LLM Provider Service

## 1. Purpose

The LLM provider service centralizes OpenAI-compatible chat-completion calls
used by AI-assisted cleanup, AI-assisted chunking, AI translation, and
character discovery.

It exists to keep provider communication, malformed-JSON handling, token-usage
normalization, and operation-local AI transaction logging in one shared layer.

## 2. Responsibilities

The service owns:

- request construction for `POST /v1/chat/completions`
- endpoint normalization for base URLs that already include `/v1` or the full
  `/chat/completions` path
- compatibility retry when one backend rejects `max_tokens` and requests
  `max_completion_tokens`
- response extraction from OpenAI-compatible `choices[].message.content`
- conservative local JSON repair and one follow-up JSON-repair request
- cooperative cancellation while waiting for provider responses
- normalized token-usage extraction from the response `usage` object
- append-only AI transaction logging for request, response, and failure events
- transient-only retry classification so permanent HTTP failures surface
  immediately

The service does not own:

- workflow-specific prompts
- chunking, cleanup, translation, or character-discovery business rules
- token estimation when the backend does not report usage

## 3. Implementation Overview

The implementation lives in:

- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/token_usage_service.py`

Main flow:

1. `chat_json(...)` builds one OpenAI-compatible chat-completions payload.
2. `_request_chat_completion_with_cancellation(...)` runs the blocking HTTP
   request in one worker thread so the caller can cancel cooperatively.
3. `_request_chat_completion(...)` posts JSON to the resolved endpoint,
   preserves already-complete `/chat/completions` URLs, and retries once with
   `max_completion_tokens` when a backend explicitly rejects `max_tokens`.
4. `_extract_message_content(...)` reads assistant text from the first choice.
5. `_parse_json_content(...)` strips fences, trims surrounding text, and
   attempts one conservative local repair pass for malformed JSON content.
6. `_repair_json_response_with_model(...)` sends one follow-up repair request
   only when the assistant text is still not parseable as JSON.
7. `token_usage_service.normalize_provider_usage(...)` extracts
   `prompt_tokens`, `completion_tokens`, and `total_tokens` when the backend
   reports them.
8. `chat_json(...)` returns one shared result object with `payload` and
   normalized `usage`, and writes one transaction-log entry for the request
   plus the final outcome.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config`
- `audiomancer.services.logging_service`
- `audiomancer.services.operation_runtime_service`
- `audiomancer.services.token_usage_service`

External dependencies:

- Python standard library: `json`, `threading`, `time`, `urllib`
- one OpenAI-compatible HTTP backend such as OpenAI API, LM Studio, or Ollama
  when it exposes compatible endpoints

## 5. Inputs And Outputs

Inputs:

- one normalized AI profile payload with `base_url`, `model_name`,
  `temperature`, timeout, and output-token settings
- one system prompt and one user prompt
- optional `log_path` and per-request `log_context`
- optional cancellation callback

Outputs:

- one result dictionary:
  - `payload`: parsed JSON object returned by the model
  - `usage`: normalized token-usage payload
- one append-only log file when `log_path` is provided

The service can raise:

- `RuntimeError` for HTTP, transport, or provider failures
- `ValueError` for empty, invalid, or non-object JSON content
- `OperationCancelledError` when cancellation is requested during the wait

## 6. Data Contracts

`chat_json(...)` now returns:

```python
{
    "payload": {"...": "..."},
    "usage": {
        "input_tokens": int | None,
        "output_tokens": int | None,
        "total_tokens": int | None,
        "usage_available": bool,
    },
}
```

Usage normalization rules:

- `usage.prompt_tokens` maps to `input_tokens`
- `usage.completion_tokens` maps to `output_tokens`
- `usage.total_tokens` maps to `total_tokens`
- when the backend omits usage or returns incomplete usage, the normalized
  payload becomes unavailable and all numeric fields remain `None`
- the service does not estimate tokens from text length

Transaction-log response entries now include normalized usage:

- `usage` for the final request result
- `repair_usage` when one follow-up repair request was needed

## 7. Workflow Integration

Current in-repo callers are:

- `ai_cleanup_service.clean_text(...)`
- `ai_chunking_service.chunk_text(...)`
- `ai_translation_service._translate_text_in_budgeted_segments(...)`
- `character_discovery_service.start_or_continue_discovery(...)`

Downstream consumers use the returned `usage` payload to:

- update live token counters in the modal progress dialog
- persist cumulative token totals in operation-local report and state files
- surface token totals in page notes after reload

## 8. Usage

Typical service call:

```python
result = llm_provider_service.chat_json(
    ai_profile_payload,
    system_prompt,
    user_prompt,
    log_path=log_path,
    log_context={"operation_kind": "translation"},
    cancel_requested=cancel_requested,
)
payload = dict(result["payload"])
usage = dict(result["usage"])
```

The caller is responsible for:

- validating the selected AI profile before calling
- interpreting the workflow-specific `payload` keys
- accumulating `usage` across multiple requests when one workflow spans
  multiple windows or segments

## 9. Validation And Tests

Focused automated coverage lives in:

- `04_Software/AudioMancer/tests/test_llm_provider_service.py`

Current tests cover:

- fenced JSON normalization
- transient retry behavior
- no retry on permanent HTTP failures
- cooperative cancellation during provider waits
- `max_completion_tokens` compatibility retry
- invalid backslash escape repair
- follow-up JSON-repair requests
- raw-content logging on parse failure
- normalized usage extraction from provider responses

Minimum validation after changes:

- `uv run python -m py_compile 04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py`
- `uv run python -m py_compile 04_Software/AudioMancer/src/audiomancer/services/token_usage_service.py`
- targeted `uv run pytest tests/test_llm_provider_service.py`

## 10. Limitations And Future Work

- The service still relies on prompt-shaped JSON rather than schema-enforced
  structured output.
- Only the standard OpenAI-compatible `usage` object is recognized; provider-
  specific token fields are ignored.
- Usage remains unavailable when the backend omits or partially populates
  token counts.
- The service only reads the first returned choice.
