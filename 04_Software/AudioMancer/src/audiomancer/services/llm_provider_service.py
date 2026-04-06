#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
         transient failures, normalizes JSON model output, and optionally
         appends detailed transaction records to one operation-local log file
         while keeping UI-driven cancellation responsive during provider waits.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.2.0
"""

# IMPORTS

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from audiomancer import config
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import OperationCancelledError

# CONSTANTS

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
    @return     Parsed JSON object returned by the model.
    @exception  RuntimeError Raised on provider or transport failures.
    @exception  ValueError Raised on invalid or non-object JSON output.
    @exception  OperationCancelledError Raised when cooperative cancellation is requested.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    request_payload = {
        "model": str(profile_payload.get("model_name", "")).strip(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(
            profile_payload.get("temperature", config.DEFAULT_LLM_TEMPERATURE)
        ),
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
        try:
            raw_payload, raw_body = _request_chat_completion_with_cancellation(
                profile_payload,
                request_payload,
                cancel_requested=cancel_requested,
            )
            parsed_payload = _parse_json_content(_extract_message_content(raw_payload))
            _append_ai_log(
                log_path,
                {
                    "exchange_event": "response",
                    "parsed_status": "parsed_success",
                    "attempt_index": attempt_index,
                    "raw_response_body": raw_body,
                    **dict(log_context or {}),
                },
            )
            return parsed_payload
        except Exception as error_object:
            last_error = error_object
            _append_ai_log(
                log_path,
                {
                    "exchange_event": "failure",
                    "parsed_status": "parsed_failure",
                    "attempt_index": attempt_index,
                    "error_text": str(error_object),
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
    result_holder: dict[str, object] = {}
    error_holder: dict[str, Exception] = {}

    def _request_worker() -> None:
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
            raise OperationCancelledError(
                "AI-assisted cleanup cancelled while waiting for the model response."
            )
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
        if http_error.code in {408, 409, 429} or http_error.code >= 500:
            raise RuntimeError(
                f"Transient AI provider failure: HTTP {http_error.code}: {error_body}"
            ) from http_error
        raise RuntimeError(
            f"AI provider request failed with HTTP {http_error.code}: {error_body}"
        ) from http_error
    except error.URLError as url_error:
        raise RuntimeError(
            f"AI provider request failed: {getattr(url_error, 'reason', url_error)}"
        ) from url_error
    payload = json.loads(raw_body)
    if not isinstance(payload, dict):
        raise ValueError("AI provider returned a non-object JSON payload.")
    return dict(payload), raw_body


def _build_chat_endpoint(base_url: str) -> str:
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


def _extract_message_content(payload: dict[str, object]) -> str:
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
    normalized = content.strip()
    if normalized.startswith("```"):
        normalized = _strip_code_fence(normalized)
    if not normalized:
        raise ValueError("AI provider returned an empty response.")
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        trimmed = _trim_json_like_payload(normalized)
        payload = json.loads(_repair_json_like_content(trimmed))
    if not isinstance(payload, dict):
        raise ValueError("AI provider did not return a JSON object.")
    return dict(payload)


def _strip_code_fence(content: str) -> str:
    stripped_lines = content.splitlines()
    if stripped_lines and stripped_lines[0].startswith("```"):
        stripped_lines = stripped_lines[1:]
    if stripped_lines and stripped_lines[-1].startswith("```"):
        stripped_lines = stripped_lines[:-1]
    return "\n".join(stripped_lines).strip()


def _trim_json_like_payload(content: str) -> str:
    start_indexes = [index for index in (content.find("{"), content.find("[")) if index >= 0]
    if not start_indexes:
        raise ValueError("AI provider did not return JSON content.")
    trimmed = content[min(start_indexes):]
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
            repaired.append(character)
            escape_active = True
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
    return "".join(repaired)


def _is_likely_string_terminator(content: str, quote_index: int) -> bool:
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
    return content[next_value_index] in {'"', "{", "[", "]", "}", "-", "t", "f", "n"} or content[next_value_index].isdigit()


def _next_non_whitespace_index(content: str, start_index: int) -> int | None:
    for index in range(start_index, len(content)):
        if not content[index].isspace():
            return index
    return None


def _is_retryable_error(error_object: Exception) -> bool:
    message = str(error_object).lower()
    return (
        "transient ai provider failure" in message
        or "timed out" in message
        or "temporarily" in message
        or "request failed" in message
    )


def _append_ai_log(log_path: str | Path | None, payload: dict[str, object]) -> None:
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
