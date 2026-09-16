#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chatgpt_provider_service.py
@brief Normalize complete text Responses from the subscription backend.
@details Bounded SSE parsing requires an explicit successful terminal event.
         Account generations, strict schema evidence and retries remain explicit.
"""

# IMPORTS

import codecs
from dataclasses import dataclass, replace
import json
import time

import httpx

from audiomancer import config
from audiomancer.services import chatgpt_catalog_service, token_usage_service
from audiomancer.services import chatgpt_http_service as http
from audiomancer.services.chatgpt_credential_service import get_manager
from audiomancer.services.chatgpt_storage_service import check_cancel
from audiomancer.services.logging_service import get_component_logger

# CONSTANTS

_MAX_EVENT_CHARS = 4 * 1024 * 1024
_MAX_STREAM_BYTES = 32 * 1024 * 1024
_LOGGER = get_component_logger("chatgpt_provider")

# DATA MODELS


@dataclass(frozen=True)
class Completion:
    """@brief Provider-neutral completed text and canonical usage metadata."""

    text: str
    usage: dict
    reasoning_mode_effective: str = "provider_default"
    reasoning_effort_effective: str = "provider_default"


# PUBLIC API


def complete(
    profile,
    system,
    user,
    *,
    cancel=None,
    manager=None,
    generation=None,
    schema=None,
    schema_name="audiomancer_json_response",
    require_schema=False,
    allow_schema_fallback=False,
    verify_schema=False,
    retry_count=None,
):
    """@brief Complete a text request while preserving a pinned account and bounded retries.
    @param[in] verify_schema Internal model-verification probe; never read from profile data.
    @return Completion containing only validated terminal text and normalized usage.
    @exception ValueError Raised before network I/O when required schema evidence is absent.
    """
    _LOGGER.debug("Starting ChatGPT subscription text completion")
    manager = manager if manager is not None else get_manager()
    generation, credential = manager.acquire(cancel, expected=generation)
    model = str(profile.get("model_name", "")).strip()
    if not model or len(model) > 200:
        raise ValueError("Select a ChatGPT model in AI Settings.")
    verified = manager.is_verified(generation, model, schema=True, cancel=cancel)
    if require_schema and (schema is None or not verified):
        raise ValueError("This operation requires verified ChatGPT JSON Schema support. Test the model in AI Settings.")
    chatgpt_catalog_service.validate_effort(
        profile, chatgpt_catalog_service.cached_models(manager, generation, cancel)
    )
    body, effective = build_request(
        profile, system, user, schema=schema if (verified or verify_schema) else None, schema_name=schema_name
    )
    retries = config.DEFAULT_LLM_REQUEST_RETRY_COUNT if retry_count is None else max(0, int(retry_count))
    timeout = max(
        1.0, min(3600.0, float(profile.get("request_timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS)))
    )
    refreshed = False
    for attempt in range(retries + 1):
        check_cancel(cancel)
        manager.assert_current(generation, cancel)
        try:
            completion = http.run_cancellable(_request(body, credential, timeout, effective), cancel, timeout)
            manager.assert_current(generation, cancel)
            return replace(
                completion, reasoning_effort_effective=body.get("reasoning", {}).get("effort", "provider_default")
            )
        except http.ProviderError as error:
            if (
                error.code == "unsupported_schema"
                and allow_schema_fallback
                and not require_schema
                and "text" in body
                and attempt < retries
            ):
                body = {key: value for key, value in body.items() if key != "text"}
                continue
            if error.status == 401 and not refreshed and attempt < retries:
                generation, credential = manager.acquire(
                    cancel, expected=generation, rejected_token=credential.access_token
                )
                refreshed = True
                continue
            if attempt >= retries or not error.retryable:
                raise
            _backoff(max(error.retry_after, min(4.0, 0.5 * 2**attempt)), cancel)
    raise http.ProviderError()


def build_request(profile, system, user, *, schema=None, schema_name="audiomancer_json_response"):
    """@brief Build the Responses dialect without Chat Completions-only parameters."""
    body = {
        "model": str(profile.get("model_name", "")).strip(),
        "instructions": system,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": user}]}],
        "store": False,
        "stream": True,
    }
    effort = chatgpt_catalog_service.requested_effort(profile)
    effective = chatgpt_catalog_service.reasoning_mode(effort)
    if effort != "provider_default":
        body["reasoning"] = {"effort": effort}
    if schema is not None:
        body["text"] = {
            "format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": _schema_dialect(schema)}
        }
    return body, effective


# LOCAL HELPERS


def _schema_dialect(value):
    """@brief Translate const to an equivalent singleton enum without weakening constraints."""
    if isinstance(value, dict):
        return {
            ("enum" if key == "const" else key): ([item] if key == "const" else _schema_dialect(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_schema_dialect(item) for item in value]
    return value


def _backoff(delay, cancel):
    """@brief Keep retry sleeps bounded and responsive to workflow cancellation."""
    deadline = time.monotonic() + delay
    while time.monotonic() < deadline:
        check_cancel(cancel)
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


async def _events(response):
    """@brief Decode fragmented UTF-8 SSE with CRLF, comments and multiline data."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    buffer, data, event, total, size = "", [], "", 0, 0
    try:
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > _MAX_STREAM_BYTES:
                raise http.ProviderError()
            buffer += decoder.decode(chunk)
            if len(buffer) > _MAX_EVENT_CHARS:
                raise http.ProviderError()
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.removesuffix("\r")
                if not line:
                    if data:
                        raw = "\n".join(data)
                        if raw == "[DONE]":
                            raise http.ProviderError()
                        try:
                            payload = json.loads(raw)
                            if not isinstance(payload, dict):
                                raise ValueError
                            payload.setdefault("type", event)
                        except (ValueError, TypeError):
                            raise http.ProviderError() from None
                        yield payload
                    data, event, size = [], "", 0
                elif line.startswith("data:"):
                    value = line[5:].removeprefix(" ")
                    size += len(value)
                    if size > _MAX_EVENT_CHARS:
                        raise http.ProviderError()
                    data.append(value)
                elif line.startswith("event:"):
                    event = line[6:].strip()
        decoder.decode(b"", final=True)
    except UnicodeError:
        raise http.ProviderError() from None
    # EOF is never proof of a successful response, even if it contains valid JSON.
    raise http.ProviderError()


def _terminal_text(response, deltas):
    """@brief Accept completed assistant text only, excluding refusals and tool execution."""
    if response.get("status") != "completed" or response.get("error") or response.get("incomplete_details"):
        raise http.ProviderError()
    parts = []
    output = response.get("output")
    if output is not None:
        if not isinstance(output, list):
            raise http.ProviderError()
        for item in output:
            if not isinstance(item, dict):
                raise http.ProviderError()
            if item.get("type") == "reasoning":
                continue
            if (
                item.get("type") != "message"
                or item.get("role") != "assistant"
                or item.get("status", "completed") != "completed"
            ):
                raise http.ProviderError()
            content = item.get("content", [])
            if not isinstance(content, list):
                raise http.ProviderError()
            for part in content:
                if (
                    not isinstance(part, dict)
                    or part.get("type") != "output_text"
                    or not isinstance(part.get("text"), str)
                ):
                    raise http.ProviderError()
                parts.append(part["text"])
    else:
        parts = ["".join(deltas[key]) for key in sorted(deltas)]
    text = "".join(parts)
    if not text.strip():
        raise http.ProviderError()
    return text


async def _request(body, credential, timeout, effective):
    """@brief Close the streaming response immediately after a verified terminal event."""
    headers = {
        "Authorization": "Bearer " + credential.access_token,
        "ChatGPT-Account-Id": credential.account_id,
        "originator": "audiomancer",
        "User-Agent": "AudioMancer",
        "Accept": "text/event-stream",
        "OpenAI-Beta": "responses=experimental",
    }
    if credential.residency:
        headers["x-openai-internal-codex-residency"] = credential.residency
    output_seen, deltas, completed_items = False, {}, {}
    try:
        async with (
            http.new_client(timeout) as client,
            client.stream("POST", http.RESPONSES_URL, json=body, headers=headers) as response,
        ):
            if not 200 <= response.status_code < 300:
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > http.MAX_AUTH_BYTES:
                        break
                http.check_status(response, bytes(raw[: http.MAX_AUTH_BYTES]))
            content_type = response.headers.get("content-type", "").lower()
            if content_type and "text/event-stream" not in content_type:
                raise http.ProviderError()
            async for event in _events(response):
                kind = event.get("type", "")
                if not isinstance(kind, str):
                    raise http.ProviderError()
                if kind == "response.output_text.delta":
                    delta = event.get("delta")
                    if not isinstance(delta, str):
                        raise http.ProviderError()
                    key = (event.get("output_index", 0), event.get("content_index", 0))
                    if any(type(index) is not int or index < 0 for index in key):
                        raise http.ProviderError()
                    deltas.setdefault(key, []).append(delta)
                    output_seen |= bool(delta)
                elif kind in {"response.output_item.added", "response.output_item.done"}:
                    item = event.get("item", {})
                    if not isinstance(item, dict) or item.get("type") not in {"message", "reasoning"}:
                        raise http.ProviderError()
                    if item.get("type") == "message" and item.get("role") != "assistant":
                        raise http.ProviderError()
                    if kind == "response.output_item.done":
                        index = event.get("output_index", 0)
                        if type(index) is not int or index < 0:
                            raise http.ProviderError()
                        completed_items[index] = item
                    output_seen = True
                elif kind in {"response.completed", "response.done"}:
                    terminal = event.get("response")
                    if not isinstance(terminal, dict):
                        raise http.ProviderError()
                    if not terminal.get("output") and completed_items:
                        terminal = {
                            **terminal,
                            "output": [completed_items[index] for index in sorted(completed_items)],
                        }
                    text = _terminal_text(terminal, deltas)
                    usage = token_usage_service.normalize_provider_usage(terminal)
                    return Completion(text, usage, effective)
                elif (
                    kind in {"error", "response.failed", "response.incomplete", "response.cancelled"}
                    or "refusal" in kind
                    or "function_call" in kind
                    or "tool_call" in kind
                ):
                    raise http.ProviderError()
    except httpx.HTTPError as error:
        failure = http.ProviderError("timeout" if isinstance(error, httpx.TimeoutException) else "network")
        failure.retryable = not output_seen
        raise failure from None
    except http.ProviderError as error:
        if output_seen:
            error.retryable = False
        raise
    raise http.ProviderError()


# END OF FILE
