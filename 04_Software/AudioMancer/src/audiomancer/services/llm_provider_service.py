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
@author Eng. Dan Dumitru Pasare
@date 2026-04-11
@version 0.5.0
"""

# IMPORTS

from datetime import UTC, datetime
import json
from pathlib import Path
import threading
import time
from urllib import error, parse, request

from audiomancer import config
from audiomancer.services import token_usage_service
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import OperationCancelledError

# CONSTANTS

# @brief Component logger used by OpenAI-compatible provider requests.
_LLM_PROVIDER_LOGGER = get_component_logger("llm_provider")


# PUBLIC API


@trace_function(_LLM_PROVIDER_LOGGER)
def chat_json(
    profile_payload: dict[str, object],
    system_prompt: str,
    user_prompt: str,
    log_path: str | Path | None = None,
    log_context: dict[str, object] | None = None,
    cancel_requested=None,
) -> dict[str, object]:
    """
    @brief      Run one chat-completion request and parse JSON content.
    @param[in]  profile_payload Normalized AI profile payload.
    @param[in]  system_prompt System-role prompt body.
    @param[in]  user_prompt User-role prompt body.
    @param[in]  log_path Optional operation-local AI transaction log file.
    @param[in]  log_context Optional per-request log metadata.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Parsed JSON payload plus normalized token-usage data.
    @exception  RuntimeError Raised on provider or transport failures.
    @exception  ValueError Raised on invalid or non-object JSON output.
    @exception  OperationCancelledError Raised when cooperative cancellation is requested.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.5.0
    """
    request_payload = {
        "model": str(profile_payload.get("model_name", "")).strip(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(profile_payload.get("temperature", config.DEFAULT_LLM_TEMPERATURE)),
        "max_tokens": int(
            profile_payload.get(
                "max_output_tokens",
                config.DEFAULT_LLM_MAX_OUTPUT_TOKENS,
            )
        ),
    }
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

    attempts = max(1, config.DEFAULT_LLM_REQUEST_RETRY_COUNT + 1)
    last_error: Exception | None = None
    for attempt_index in range(1, attempts + 1):
        raw_content: str | None = None
        try:
            raw_payload, raw_body = _request_chat_completion_with_cancellation(
                profile_payload,
                request_payload,
                cancel_requested=cancel_requested,
            )
            raw_content = _extract_message_content(raw_payload)
            try:
                parsed_payload = _parse_json_content(raw_content)
                normalized_usage = token_usage_service.normalize_provider_usage(raw_payload)
            except ValueError as parse_error:
                (
                    parsed_payload,
                    repair_body,
                    repaired_content,
                    repair_usage,
                ) = _repair_json_response_with_model(
                    profile_payload,
                    raw_content,
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
        except Exception as error_object:
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
    assert last_error is not None
    raise last_error


# LOCAL HELPERS


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    result_holder: dict[str, object] = {}
    error_holder: dict[str, Exception] = {}

    def _request_worker() -> None:
        """
        @brief      Execute the request worker helper.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        try:
            result_holder["payload"] = _request_chat_completion(
                profile_payload,
                request_payload,
            )
        except Exception as error_object:  # pragma: no cover - exercised via caller.
            error_holder["error"] = error_object

    request_thread = threading.Thread(
        target=_request_worker,
        name="audiomancer-llm-request",
        daemon=True,
    )
    request_thread.start()
    while request_thread.is_alive():
        if callable(cancel_requested) and bool(cancel_requested()):
            raise OperationCancelledError("AI-assisted cleanup cancelled while waiting for the model response.")
        request_thread.join(timeout=0.05)
        time.sleep(0.01)
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.3.0
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
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
    except error.HTTPError as http_error:
        error_body = http_error.read().decode("utf-8", errors="replace")
        if _supports_max_completion_tokens_retry(http_error.code, error_body):
            compatibility_payload = _build_max_completion_tokens_payload(request_payload)
            if compatibility_payload != request_payload:
                return _request_chat_completion(profile_payload, compatibility_payload)
        if http_error.code in {408, 409, 429} or http_error.code >= 500:
            raise RuntimeError(f"Transient AI provider failure: HTTP {http_error.code}: {error_body}") from http_error
        raise RuntimeError(f"AI provider request failed with HTTP {http_error.code}: {error_body}") from http_error
    except error.URLError as url_error:
        raise RuntimeError(f"AI provider request failed: {getattr(url_error, 'reason', url_error)}") from url_error
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    normalized_base = base_url.rstrip("/")
    parsed_url = parse.urlparse(normalized_base)
    base_path = parsed_url.path.rstrip("/")
    if base_path.endswith("/v1"):
        full_path = f"{base_path}/chat/completions"
    elif base_path:
        full_path = f"{base_path}/v1/chat/completions"
    else:
        full_path = "/v1/chat/completions"
    return parse.urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            full_path,
            "",
            "",
            "",
        )
    )


def _supports_max_completion_tokens_retry(status_code: int, error_body: str) -> bool:
    """
    @brief      Decide whether one provider failure should retry with max_completion_tokens.
    @param[in]  status_code HTTP status code returned by the provider.
    @param[in]  error_body Provider error response body.
    @return     True when the provider explicitly rejected the max_tokens field.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    if status_code != 400:
        return False
    normalized_body = (error_body or "").lower()
    return (
        '"param":"max_tokens"' in normalized_body or '"param": "max_tokens"' in normalized_body
    ) and "max_completion_tokens" in normalized_body


def _build_max_completion_tokens_payload(
    request_payload: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Convert one request payload to use max_completion_tokens.
    @param[in]  request_payload Original request payload.
    @return     Compatibility payload for providers that reject max_tokens.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    compatibility_payload = dict(request_payload)
    if "max_tokens" not in compatibility_payload:
        return compatibility_payload
    compatibility_payload["max_completion_tokens"] = compatibility_payload.pop("max_tokens")
    return compatibility_payload


def _extract_message_content(payload: dict[str, object]) -> str:
    """
    @brief      Execute the extract message content helper.
    @param[in]  payload Optional payload processed by the helper.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        raise ValueError("AI provider response does not contain any choices.")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("AI provider response contains an invalid choice payload.")
    message = first_choice.get("message", {})
    if not isinstance(message, dict):
        raise ValueError("AI provider response contains an invalid message payload.")
    content = message.get("content", "")
    if isinstance(content, list):
        joined_content: list[str] = []
        for item in content:
            if isinstance(item, dict):
                joined_content.append(str(item.get("text", "")))
        return "".join(joined_content)
    return str(content)


def _parse_json_content(content: str) -> dict[str, object]:
    """
    @brief      Execute the parse json content helper.
    @param[in]  content Value for `content`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
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
    cancel_requested=None,
) -> tuple[dict[str, object], str, str, dict[str, object]]:
    """
    @brief      Execute the repair json response with model helper.
    @param[in]  profile_payload Profile payload.
    @param[in]  malformed_content Value for `malformed_content`.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    message = str(error_object).lower()
    return (
        "transient ai provider failure" in message
        or "timed out" in message
        or "temporarily" in message
        or "request failed" in message
    )


def _append_ai_log(log_path: str | Path | None, payload: dict[str, object]) -> None:
    """
    @brief      Append the ai log.
    @param[in]  log_path Operation log file path.
    @param[in]  payload Optional payload processed by the helper.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if log_path is None:
        return
    resolved_log_path = Path(log_path)
    resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
    log_payload = {
        "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat(),
        **payload,
    }
    existing_text = ""
    if resolved_log_path.exists():
        existing_text = resolved_log_path.read_text(encoding="utf-8")
    resolved_log_path.write_text(
        existing_text + json.dumps(log_payload, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# END OF FILE
