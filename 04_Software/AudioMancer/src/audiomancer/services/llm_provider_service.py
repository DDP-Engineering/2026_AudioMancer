#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file llm_provider_service.py
@brief OpenAI-compatible request helpers for AudioMancer AI workflows.
@details Sends chat-completion requests through configured AI profiles, retries
         transient failures, normalizes JSON model output, repairs malformed
         JSON responses conservatively, and optionally appends detailed
         transaction records to one operation-local log file while keeping
         UI-driven cancellation responsive during provider waits.
"""

# IMPORTS

import json
from pathlib import Path
import re
import threading
import time
from urllib import error, request

from audiomancer import config
from audiomancer.services import token_usage_service
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import OperationCancelledError
from audiomancer.services.time_service import utc_now_iso
from audiomancer.services.url_service import join_endpoint_url

# CONSTANTS

# @brief Component logger used by OpenAI-compatible provider requests.
_LLM_PROVIDER_LOGGER = get_component_logger("llm_provider")

# @brief Initial delay before the first transient outer retry.
_RETRY_INITIAL_DELAY_SECONDS = 0.5

# @brief Maximum delay applied before any one transient outer retry.
_RETRY_MAX_DELAY_SECONDS = 4.0

# @brief Maximum sleep slice used while polling retry-backoff cancellation.
_RETRY_CANCEL_POLL_SECONDS = 0.05

# @brief Placeholder used in AI transaction logs for sensitive fields.
_REDACTED_LOG_VALUE = "[REDACTED]"

# @brief Exact field names that must never be persisted to transaction logs.
_SENSITIVE_LOG_FIELD_NAMES = frozenset(
    {
        "api_key",
        "authorization",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "tts_runtime_api_key",
        "runtime_api_key",
    }
)


class _UnsupportedResponseFormatError(RuntimeError):
    """
    @brief Private marker for providers that reject response_format.
    @details Allows chat_json to retry one structured-output request without
             response_format while keeping normal permanent HTTP failures
             surfaced unchanged.
    """


class _UnsupportedMaxTokensError(RuntimeError):
    """
    @brief Private marker for providers that require max_completion_tokens.
    @details Allows chat_json to retain the compatible token parameter across
             later outer attempts in the same invocation.
    """


class _TransientProviderError(RuntimeError):
    """Mark provider and transport failures that are safe to retry."""


# PUBLIC API


@trace_function(_LLM_PROVIDER_LOGGER)
def chat_json(
    profile_payload: dict[str, object],
    system_prompt: str,
    user_prompt: str,
    log_path: str | Path | None = None,
    log_context: dict[str, object] | None = None,
    cancel_requested=None,
    structured_output: bool = True,
    response_schema: dict[str, object] | None = None,
    response_schema_name: str = "audiomancer_json_response",
    require_response_schema: bool = False,
    allow_unconstrained_fallback: bool = True,
    allow_model_json_repair: bool = True,
    retry_count_override: int | None = None,
    max_output_tokens_override: int | None = None,
) -> dict[str, object]:
    """
    @brief      Run one chat-completion request and parse JSON content.
    @param[in]  profile_payload Normalized AI profile payload.
    @param[in]  system_prompt System-role prompt body.
    @param[in]  user_prompt User-role prompt body.
    @param[in]  log_path Optional operation-local AI transaction log file.
    @param[in]  log_context Optional per-request log metadata.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  structured_output Enable provider JSON-object mode when the profile supports it.
    @param[in]  response_schema Optional operation-specific JSON Schema for structured-output providers.
    @param[in]  response_schema_name Provider-facing schema name used with `response_schema`.
    @return     Parsed JSON payload plus normalized token-usage data.
    @exception  RuntimeError Raised on provider or transport failures.
    @exception  ValueError Raised on invalid or non-object JSON output.
    @exception  OperationCancelledError Raised when cooperative cancellation is requested.
    """
    if require_response_schema and (
        response_schema is None or not bool(profile_payload.get("supports_structured_output", False))
    ):
        raise ValueError("This operation requires provider-enforced JSON Schema output.")
    request_payload = {
        "model": str(profile_payload.get("model_name", "")).strip(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(profile_payload.get("temperature", config.DEFAULT_LLM_TEMPERATURE)),
        "max_tokens": int(
            max_output_tokens_override
            if max_output_tokens_override is not None
            else profile_payload.get("max_output_tokens", config.DEFAULT_LLM_MAX_OUTPUT_TOKENS)
        ),
    }
    if structured_output and bool(profile_payload.get("supports_structured_output", False)):
        request_payload["response_format"] = _build_response_format(
            profile_payload,
            response_schema=response_schema,
            response_schema_name=response_schema_name,
        )
    _append_ai_log(
        log_path,
        {
            "exchange_event": "request",
            "parsed_status": "pending",
            "profile_id": str(profile_payload.get("id", "")),
            "backend_kind": str(profile_payload.get("backend_kind", "")),
            "base_url": str(profile_payload.get("base_url", "")),
            "model_name": request_payload["model"],
            "request_payload": request_payload,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            **dict(log_context or {}),
        },
    )

    attempts = max(
        1,
        (
            config.DEFAULT_LLM_REQUEST_RETRY_COUNT
            if retry_count_override is None
            else int(retry_count_override)
        )
        + 1,
    )
    last_error: Exception | None = None
    active_request_payload = request_payload
    for attempt_index in range(1, attempts + 1):
        raw_content: str | None = None
        try:
            while True:
                try:
                    raw_payload, raw_body = _request_chat_completion_with_cancellation(
                        profile_payload,
                        active_request_payload,
                        cancel_requested=cancel_requested,
                    )
                    break
                except _UnsupportedResponseFormatError as error_object:
                    if (
                        "response_format" not in active_request_payload
                        or not allow_unconstrained_fallback
                    ):
                        raise
                    active_request_payload = _build_without_response_format_payload(
                        active_request_payload
                    )
                    _append_ai_log(
                        log_path,
                        {
                            "exchange_event": "request_fallback",
                            "parsed_status": "response_format_unsupported_retry_without_response_format",
                            "attempt_index": attempt_index,
                            "error_text": str(error_object),
                            "request_payload": active_request_payload,
                            **dict(log_context or {}),
                        },
                    )
                except _UnsupportedMaxTokensError:
                    active_request_payload = _build_max_completion_tokens_payload(active_request_payload)
            raw_content = _extract_message_content(raw_payload)
            try:
                parsed_payload = _parse_json_content(raw_content)
                normalized_usage = token_usage_service.normalize_provider_usage(raw_payload)
            except ValueError as parse_error:
                if not raw_content.strip() or not allow_model_json_repair:
                    raise
                (
                    parsed_payload,
                    repair_body,
                    repaired_content,
                    repair_usage,
                ) = _repair_json_response_with_model(
                    profile_payload,
                    raw_content,
                    active_request_payload,
                    cancel_requested=cancel_requested,
                )
                normalized_usage = token_usage_service.merge_token_usage(
                    token_usage_service.normalize_provider_usage(raw_payload),
                    repair_usage,
                )
                _append_ai_log(
                    log_path,
                    {
                        "exchange_event": "response",
                        "parsed_status": "parsed_success_after_repair",
                        "attempt_index": attempt_index,
                        "raw_response_body": raw_body,
                        "raw_message_content": raw_content,
                        "repair_error_text": str(parse_error),
                        "repair_response_body": repair_body,
                        "repair_message_content": repaired_content,
                        "usage": normalized_usage,
                        "repair_usage": repair_usage,
                        **dict(log_context or {}),
                    },
                )
                return {
                    "payload": parsed_payload,
                    "usage": normalized_usage,
                }
            _append_ai_log(
                log_path,
                {
                    "exchange_event": "response",
                    "parsed_status": "parsed_success",
                    "attempt_index": attempt_index,
                    "raw_response_body": raw_body,
                    "raw_message_content": raw_content,
                    "usage": normalized_usage,
                    **dict(log_context or {}),
                },
            )
            return {
                "payload": parsed_payload,
                "usage": normalized_usage,
            }
        except OperationCancelledError:
            raise
        except Exception as error_object:
            if isinstance(error_object, _UnsupportedResponseFormatError):
                error_object = RuntimeError(
                    "AI provider does not support required structured JSON output."
                )
            elif isinstance(error_object, _UnsupportedMaxTokensError):
                error_object = RuntimeError(
                    "AI provider rejected the supported output-token limit fields."
                )
            last_error = error_object
            _append_ai_log(
                log_path,
                {
                    "exchange_event": "failure",
                    "parsed_status": "parsed_failure",
                    "attempt_index": attempt_index,
                    "error_text": str(error_object),
                    "raw_message_content": raw_content,
                    **dict(log_context or {}),
                },
            )
            if attempt_index >= attempts or not _is_retryable_error(error_object):
                break
            retry_delay = min(
                _RETRY_MAX_DELAY_SECONDS,
                _RETRY_INITIAL_DELAY_SECONDS * (2 ** (attempt_index - 1)),
            )
            _wait_for_retry_backoff(retry_delay, cancel_requested)
    assert last_error is not None
    raise last_error


# LOCAL HELPERS


def _wait_for_retry_backoff(delay_seconds: float, cancel_requested=None) -> None:
    """
    @brief      Wait for one retry delay while polling cooperative cancellation.
    @param[in]  delay_seconds Total bounded delay before the next outer attempt.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     None.
    @exception  OperationCancelledError Raised when cancellation is requested.
    """
    if callable(cancel_requested) and bool(cancel_requested()):
        raise OperationCancelledError("AI operation cancelled during provider retry backoff.")
    deadline = time.monotonic() + max(0.0, float(delay_seconds))
    while True:
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            return
        time.sleep(min(_RETRY_CANCEL_POLL_SECONDS, remaining_seconds))
        if callable(cancel_requested) and bool(cancel_requested()):
            raise OperationCancelledError("AI operation cancelled during provider retry backoff.")


def _request_chat_completion_with_cancellation(
    profile_payload: dict[str, object],
    request_payload: dict[str, object],
    cancel_requested=None,
) -> tuple[dict[str, object], str]:
    """
    @brief      Execute the request chat completion with cancellation helper.
    @param[in]  profile_payload Profile payload.
    @param[in]  request_payload Payload for `request_payload`.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Helper result.
    """
    _LLM_PROVIDER_LOGGER.debug(
        "Starting cancellable AI provider request base_url=%s",
        str(profile_payload.get("base_url", "")).strip(),
    )
    result_holder: dict[str, object] = {}
    error_holder: dict[str, Exception] = {}

    def _request_worker() -> None:
        """
        @brief      Execute the request worker helper.
        @return     None.
        """
        try:
            result_holder["payload"] = _request_chat_completion(
                profile_payload,
                request_payload,
            )
        except Exception as error_object:  # pragma: no cover - exercised via caller.
            _LLM_PROVIDER_LOGGER.warning("AI provider request worker failed: %s", error_object)
            error_holder["error"] = error_object

    request_thread = threading.Thread(
        target=_request_worker,
        name="audiomancer-llm-request",
        daemon=True,
    )
    request_thread.start()
    while request_thread.is_alive():
        if callable(cancel_requested) and bool(cancel_requested()):
            _LLM_PROVIDER_LOGGER.info("AI provider request cancelled while waiting for model response.")
            raise OperationCancelledError("AI operation cancelled while waiting for the model response.")
        request_thread.join(timeout=0.05)
    if "error" in error_holder:
        raise error_holder["error"]
    payload = result_holder.get("payload")
    if not isinstance(payload, tuple) or len(payload) != 2:
        raise RuntimeError("AI provider request did not return a valid response payload.")
    return payload


def _request_chat_completion(
    profile_payload: dict[str, object],
    request_payload: dict[str, object],
) -> tuple[dict[str, object], str]:
    """
    @brief      Execute one provider chat-completion HTTP request.
    @param[in]  profile_payload Normalized AI profile payload.
    @param[in]  request_payload Serialized provider request payload.
    @return     Parsed JSON response payload plus raw response body text.
    @exception  RuntimeError Raised when the provider returns an HTTP or transport failure.
    @exception  ValueError Raised when the provider returns an invalid JSON payload.
    """
    endpoint = _build_chat_endpoint(str(profile_payload.get("base_url", "")))
    api_key = str(profile_payload.get("api_key", "")).strip()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout_seconds = int(
        profile_payload.get(
            "request_timeout_seconds",
            config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
        )
    )
    body = json.dumps(request_payload).encode("utf-8")
    http_request = request.Request(
        endpoint,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        _LLM_PROVIDER_LOGGER.debug(
            "Sending AI provider request endpoint=%s timeout_seconds=%s",
            endpoint,
            timeout_seconds,
        )
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
    except error.HTTPError as http_error:
        error_body = http_error.read().decode("utf-8", errors="replace")
        if "response_format" in request_payload and _supports_response_format_retry(http_error.code, error_body):
            _LLM_PROVIDER_LOGGER.info("Retrying AI provider request without response_format compatibility field.")
            raise _UnsupportedResponseFormatError(error_body) from http_error
        if _supports_max_completion_tokens_retry(http_error.code, error_body):
            compatibility_payload = _build_max_completion_tokens_payload(request_payload)
            if compatibility_payload != request_payload:
                _LLM_PROVIDER_LOGGER.info(
                    "Retrying AI provider request with max_completion_tokens compatibility payload."
                )
                raise _UnsupportedMaxTokensError(error_body) from http_error
        if http_error.code in {408, 409, 429} or http_error.code >= 500:
            _LLM_PROVIDER_LOGGER.warning("Transient AI provider HTTP failure: status=%s", http_error.code)
            raise _TransientProviderError(
                f"Transient AI provider failure: HTTP {http_error.code}: {error_body}"
            ) from http_error
        _LLM_PROVIDER_LOGGER.warning("AI provider HTTP request failed: status=%s", http_error.code)
        raise RuntimeError(f"AI provider request failed with HTTP {http_error.code}: {error_body}") from http_error
    except error.URLError as url_error:
        _LLM_PROVIDER_LOGGER.warning("AI provider URL request failed: %s", getattr(url_error, "reason", url_error))
        raise _TransientProviderError(
            f"AI provider request failed: {getattr(url_error, 'reason', url_error)}"
        ) from url_error
    except (TimeoutError, OSError) as transport_error:
        _LLM_PROVIDER_LOGGER.warning("Transient AI provider transport failure: %s", transport_error)
        raise _TransientProviderError(
            f"AI provider transport failure: {transport_error}"
        ) from transport_error
    payload = json.loads(raw_body)
    if not isinstance(payload, dict):
        raise ValueError("AI provider returned a non-object JSON payload.")
    return dict(payload), raw_body


def _build_chat_endpoint(base_url: str) -> str:
    """
    @brief      Resolve one chat-completions endpoint from the configured base URL.
    @param[in]  base_url Operator-configured provider base URL.
    @return     Fully qualified chat-completions endpoint.
    @exception  None
    """
    return join_endpoint_url(
        base_url,
        "/v1/chat/completions",
        collapse_duplicate_version=True,
    )


def _build_response_format(
    profile_payload: dict[str, object],
    response_schema: dict[str, object] | None = None,
    response_schema_name: str = "audiomancer_json_response",
) -> dict[str, object]:
    """
    @brief      Build the provider-specific structured-output response format.
    @param[in]  profile_payload Normalized AI profile payload.
    @param[in]  response_schema Optional operation-specific JSON Schema.
    @param[in]  response_schema_name Provider-facing schema name used with `response_schema`.
    @return     Response-format payload accepted by the selected backend kind.
    @exception  None
    """
    backend_kind = str(profile_payload.get("backend_kind", "")).strip()
    if isinstance(response_schema, dict) and response_schema:
        schema_name = str(response_schema_name).strip() or "audiomancer_json_response"
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": dict(response_schema),
            },
        }
    if backend_kind not in {"lmstudio", "ollama"}:
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "audiomancer_json_response",
            "schema": {
                "type": "object",
                "additionalProperties": True,
            },
        },
    }


def _supports_max_completion_tokens_retry(status_code: int, error_body: str) -> bool:
    """
    @brief      Decide whether one provider failure should retry with max_completion_tokens.
    @param[in]  status_code HTTP status code returned by the provider.
    @param[in]  error_body Provider error response body.
    @return     True when the provider explicitly rejected the max_tokens field.
    @exception  None
    """
    if status_code != 400:
        return False
    normalized_body = (error_body or "").lower()
    return (
        '"param":"max_tokens"' in normalized_body or '"param": "max_tokens"' in normalized_body
    ) and "max_completion_tokens" in normalized_body


def _supports_response_format_retry(status_code: int, error_body: str) -> bool:
    """
    @brief      Decide whether one provider failure should retry without response_format.
    @param[in]  status_code HTTP status code returned by the provider.
    @param[in]  error_body Provider error response body.
    @return     True when the provider explicitly rejected response_format.
    @exception  None
    """
    if status_code != 400:
        return False
    normalized_body = (error_body or "").lower()
    if "response_format" not in normalized_body:
        return False
    unsupported_markers = (
        "unsupported",
        "not supported",
        "unknown parameter",
        "unrecognized",
        "invalid parameter",
        "must be",
    )
    return any(marker in normalized_body for marker in unsupported_markers)


def _build_max_completion_tokens_payload(
    request_payload: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Convert one request payload to use max_completion_tokens.
    @param[in]  request_payload Original request payload.
    @return     Compatibility payload for providers that reject max_tokens.
    @exception  None
    """
    compatibility_payload = dict(request_payload)
    if "max_tokens" not in compatibility_payload:
        return compatibility_payload
    compatibility_payload["max_completion_tokens"] = compatibility_payload.pop("max_tokens")
    return compatibility_payload


def _build_without_response_format_payload(
    request_payload: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Convert one request payload to omit response_format.
    @param[in]  request_payload Original request payload.
    @return     Compatibility payload for providers that reject response_format.
    @exception  None
    """
    compatibility_payload = dict(request_payload)
    compatibility_payload.pop("response_format", None)
    return compatibility_payload


def _extract_message_content(payload: dict[str, object]) -> str:
    """
    @brief      Execute the extract message content helper.
    @param[in]  payload Optional payload processed by the helper.
    @return     Helper result.
    """
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        raise ValueError("AI provider response does not contain any choices.")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("AI provider response contains an invalid choice payload.")
    finish_reason = first_choice.get("finish_reason")
    if isinstance(finish_reason, str) and finish_reason.strip().lower() == "length":
        raise RuntimeError("AI provider response reached the provider output-token limit.")
    message = first_choice.get("message", {})
    if not isinstance(message, dict):
        raise ValueError("AI provider response contains an invalid message payload.")
    content = message.get("content")
    if isinstance(content, list):
        joined_content: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_content = item.get("text")
                joined_content.append("" if text_content is None else str(text_content))
        normalized_content = "".join(joined_content)
    else:
        normalized_content = "" if content is None else str(content)
    if not normalized_content.strip():
        refusal = message.get("refusal")
        if isinstance(refusal, str) and refusal.strip():
            raise ValueError(f"AI provider refused the request: {refusal.strip()}")
    return normalized_content


def _parse_json_content(content: str) -> dict[str, object]:
    """
    @brief      Execute the parse json content helper.
    @param[in]  content Value for `content`.
    @return     Helper result.
    """
    normalized = content.strip()
    if normalized.startswith("```"):
        normalized = _strip_code_fence(normalized)
    if not normalized:
        raise ValueError("AI provider returned an empty response.")
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError as error_object:
        trimmed = _trim_json_like_payload(normalized)
        try:
            payload = json.loads(_repair_json_like_content(trimmed))
        except json.JSONDecodeError as repaired_error:
            raise ValueError(str(repaired_error)) from error_object
    if not isinstance(payload, dict):
        raise ValueError("AI provider did not return a JSON object.")
    return dict(payload)


def _strip_code_fence(content: str) -> str:
    """
    @brief      Execute the strip code fence helper.
    @param[in]  content Value for `content`.
    @return     Helper result.
    """
    single_line_match = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if single_line_match is not None:
        return single_line_match.group(1).strip()
    stripped_lines = content.splitlines()
    if stripped_lines and stripped_lines[0].startswith("```"):
        stripped_lines = stripped_lines[1:]
    if stripped_lines and stripped_lines[-1].startswith("```"):
        stripped_lines = stripped_lines[:-1]
    return "\n".join(stripped_lines).strip()


def _trim_json_like_payload(content: str) -> str:
    """
    @brief      Execute the trim json like payload helper.
    @param[in]  content Value for `content`.
    @return     Helper result.
    """
    start_indexes = [index for index in (content.find("{"), content.find("[")) if index >= 0]
    if not start_indexes:
        raise ValueError("AI provider did not return JSON content.")
    trimmed = content[min(start_indexes) :]
    try:
        decoder = json.JSONDecoder()
        parsed_payload, _end_index = decoder.raw_decode(trimmed)
    except json.JSONDecodeError:
        end_index = max(trimmed.rfind("}"), trimmed.rfind("]"))
        if end_index < 0:
            raise ValueError("AI provider did not return JSON content.") from None
        return trimmed[: end_index + 1]
    return json.dumps(parsed_payload, ensure_ascii=False)


def _repair_json_like_content(content: str) -> str:
    """
    @brief      Execute the repair json like content helper.
    @param[in]  content Value for `content`.
    @return     Helper result.
    """
    repaired: list[str] = []
    in_string = False
    escape_active = False
    for index, character in enumerate(content):
        if not in_string:
            repaired.append(character)
            if character == '"':
                in_string = True
            continue
        if escape_active:
            repaired.append(character)
            escape_active = False
            continue
        if character == "\\":
            if _is_valid_json_escape_sequence(content, index + 1):
                repaired.append(character)
                escape_active = True
            else:
                repaired.append("\\\\")
            continue
        if character in "\r\n":
            repaired.append("\\n")
            continue
        if character == '"':
            if _is_likely_string_terminator(content, index):
                repaired.append(character)
                in_string = False
            else:
                repaired.append('\\"')
            continue
        repaired.append(character)
    if escape_active:
        repaired.append("\\")
    return "".join(repaired)


def _is_valid_json_escape_sequence(content: str, escape_index: int) -> bool:
    """
    @brief      Determine whether valid json escape sequence.
    @param[in]  content Value for `content`.
    @param[in]  escape_index Value for `escape_index`.
    @return     True when the helper condition is satisfied.
    """
    if escape_index >= len(content):
        return False
    escape_character = content[escape_index]
    if escape_character in {'"', "\\", "/", "b", "f", "n", "r", "t"}:
        return True
    if escape_character != "u":
        return False
    return escape_index + 4 < len(content) and all(
        character in "0123456789abcdefABCDEF" for character in content[escape_index + 1 : escape_index + 5]
    )


def _repair_json_response_with_model(
    profile_payload: dict[str, object],
    malformed_content: str,
    active_request_payload: dict[str, object],
    cancel_requested=None,
) -> tuple[dict[str, object], str, str, dict[str, object]]:
    """
    @brief      Execute the repair json response with model helper.
    @param[in]  profile_payload Profile payload.
    @param[in]  malformed_content Value for `malformed_content`.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Helper result.
    """
    repair_request_payload = {
        "model": str(profile_payload.get("model_name", "")).strip(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You repair malformed JSON. Return one valid JSON object only. "
                    "Preserve the original keys and values. Do not translate, summarize, "
                    "or add commentary. If a string contains a literal backslash that "
                    "breaks JSON escaping, escape the backslash so the string remains literal."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Repair the following malformed JSON into one valid JSON object. "
                    "Return only the repaired JSON object.\n\n"
                    "MALFORMED_JSON_BEGIN\n"
                    f"{malformed_content}\n"
                    "MALFORMED_JSON_END"
                ),
            },
        ],
        "temperature": 0.0,
        "max_tokens": int(
            profile_payload.get(
                "max_output_tokens",
                config.DEFAULT_LLM_MAX_OUTPUT_TOKENS,
            )
        ),
    }
    if "max_completion_tokens" in active_request_payload:
        repair_request_payload = _build_max_completion_tokens_payload(repair_request_payload)
    repair_payload, repair_body = _request_chat_completion_with_cancellation(
        profile_payload,
        repair_request_payload,
        cancel_requested=cancel_requested,
    )
    repaired_content = _extract_message_content(repair_payload)
    return (
        _parse_json_content(repaired_content),
        repair_body,
        repaired_content,
        token_usage_service.normalize_provider_usage(repair_payload),
    )


def _is_likely_string_terminator(content: str, quote_index: int) -> bool:
    """
    @brief      Determine whether likely string terminator.
    @param[in]  content Value for `content`.
    @param[in]  quote_index Value for `quote_index`.
    @return     True when the helper condition is satisfied.
    """
    next_index = _next_non_whitespace_index(content, quote_index + 1)
    if next_index is None:
        return True
    next_character = content[next_index]
    if next_character == ":":
        return True
    if next_character in {"}", "]"}:
        return True
    if next_character != ",":
        return False
    next_value_index = _next_non_whitespace_index(content, next_index + 1)
    if next_value_index is None:
        return True
    return (
        content[next_value_index] in {'"', "{", "[", "]", "}", "-", "t", "f", "n"}
        or content[next_value_index].isdigit()
    )


def _next_non_whitespace_index(content: str, start_index: int) -> int | None:
    """
    @brief      Resolve the next non whitespace index.
    @param[in]  content Value for `content`.
    @param[in]  start_index Value for `start_index`.
    @return     Resolved helper result.
    """
    for index in range(start_index, len(content)):
        if not content[index].isspace():
            return index
    return None


def _is_retryable_error(error_object: Exception) -> bool:
    """
    @brief      Determine whether retryable error.
    @param[in]  error_object Value for `error_object`.
    @return     True when the helper condition is satisfied.
    """
    return isinstance(error_object, (_TransientProviderError, TimeoutError))


def _append_ai_log(log_path: str | Path | None, payload: dict[str, object]) -> None:
    """
    @brief      Append the ai log.
    @param[in]  log_path Operation log file path.
    @param[in]  payload Optional payload processed by the helper.
    @return     None.
    """
    if log_path is None:
        return
    resolved_log_path = Path(log_path)
    resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
    log_payload = _redact_ai_log_value(
        {
            "timestamp": utc_now_iso(),
            **payload,
        }
    )
    with resolved_log_path.open("a", encoding="utf-8") as log_handle:
        log_handle.write(json.dumps(log_payload, ensure_ascii=False) + "\n")


def _redact_ai_log_value(value: object) -> object:
    """
    @brief      Redact sensitive values from one AI transaction log payload.
    @param[in]  value Payload value to inspect recursively.
    @return     Value with sensitive fields replaced by a fixed placeholder.
    @exception  None
    """
    if isinstance(value, dict):
        redacted_payload: dict[str, object] = {}
        for key, item_value in value.items():
            key_text = str(key)
            if _is_sensitive_log_field(key_text):
                redacted_payload[key_text] = _REDACTED_LOG_VALUE
            else:
                redacted_payload[key_text] = _redact_ai_log_value(item_value)
        return redacted_payload
    if isinstance(value, list):
        return [_redact_ai_log_value(item_value) for item_value in value]
    return value


def _is_sensitive_log_field(field_name: str) -> bool:
    """
    @brief      Determine whether one transaction-log field name is sensitive.
    @param[in]  field_name Candidate field name.
    @return     True when the field value must be redacted before persistence.
    @exception  None
    """
    normalized_name = field_name.strip().casefold().replace("-", "_")
    return normalized_name in _SENSITIVE_LOG_FIELD_NAMES or normalized_name.endswith("_api_key")


# END OF FILE
