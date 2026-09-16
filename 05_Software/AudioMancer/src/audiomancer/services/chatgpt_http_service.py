#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chatgpt_http_service.py
@brief Fixed-destination, abortable HTTP for subscription authentication and inference.
@details Owns safe error classification and bounded payloads. Server bodies,
         callback parameters and bearer material are never diagnostic strings.
"""

# IMPORTS

import asyncio
import json
import math

import httpx

from audiomancer.services.chatgpt_storage_service import check_cancel
from audiomancer.services.logging_service import get_component_logger

# CONSTANTS

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
TOKEN_URL = "https://auth.openai.com/oauth/token"
DEVICE_CODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
DEVICE_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
MODELS_URL = "https://chatgpt.com/backend-api/codex/models"
TRUSTED_URLS = frozenset({TOKEN_URL, DEVICE_CODE_URL, DEVICE_TOKEN_URL, RESPONSES_URL})
MAX_AUTH_BYTES = 256 * 1024
_MESSAGES = {
    "pending": "Waiting for ChatGPT authorization.",
    "slow_down": "ChatGPT authorization is pending; polling more slowly.",
    "invalid_grant": "ChatGPT sign-in expired or was revoked. Sign in again.",
    "unauthorized": "ChatGPT authorization was rejected. Sign in again.",
    "quota": "ChatGPT subscription usage is exhausted or this usage is not included. Retry after your limit resets.",
    "throttled": "ChatGPT is temporarily rate limited. Retry shortly.",
    "transient": "ChatGPT is temporarily unavailable. Retry shortly.",
    "rejected": "ChatGPT rejected this request or model. Verify the model and your subscription access.",
    "redirect": "ChatGPT returned an unexpected redirect. Credentials were not forwarded.",
    "protocol": "ChatGPT returned an invalid or incomplete response.",
    "network": "Could not reach ChatGPT. Check your connection and retry.",
    "timeout": "ChatGPT request timed out.",
    "denied": "ChatGPT sign-in was denied or the device code expired. Start sign-in again.",
    "unsupported_model": "This model is unavailable to this ChatGPT account. Select another model and test it.",
    "unsupported_schema": "ChatGPT rejected JSON Schema formatting for this model. Test the model again.",
}


# PUBLIC API


class ProviderError(RuntimeError):
    """@brief Safe failure metadata used by bounded retry and login logic."""

    def __init__(self, code="protocol", *, status=0, retry_after=0):
        """@brief Accept only known diagnostic codes; never interpolate a server message."""
        self.code = code if code in _MESSAGES else "protocol"
        self.status = status
        self.retry_after = min(30.0, max(0.0, retry_after))
        self.retryable = self.code in {"throttled", "transient", "network", "timeout"}
        self.reauthenticate = self.code in {"invalid_grant", "unauthorized"}
        super().__init__(_MESSAGES[self.code])


def new_client(timeout=15):
    """@brief Create a short-lived async client with no redirect or ambient proxy credential forwarding."""
    return httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False)


def run_cancellable(operation, cancel=None, timeout=300):
    """@brief Run in the calling worker, cancel I/O and await cleanup before returning.
    @param[in] operation Coroutine that owns its HTTP and callback resources.
    @param[in] cancel Optional cooperative cancellation callback.
    @param[in] timeout Wall-clock operation limit in seconds.
    @return Coroutine result.
    @exception OperationCancelledError Raised after resources have been closed.
    """

    async def supervise():
        """@brief Poll cancellation while preserving coroutine cleanup on every exit."""
        task = asyncio.create_task(operation)
        deadline = asyncio.get_running_loop().time() + timeout
        try:
            while not task.done():
                check_cancel(cancel)
                if asyncio.get_running_loop().time() >= deadline:
                    error = ProviderError("timeout")
                    # The supervisor cannot prove that the cancelled stream emitted no output.
                    error.retryable = False
                    raise error
                await asyncio.wait({task}, timeout=0.05)
            check_cancel(cancel)
            return await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return asyncio.run(supervise())


async def request_json(url, *, data=None, payload=None):
    """@brief Send a bounded OAuth POST only to one of the built-in trusted endpoints."""
    if url not in TRUSTED_URLS or url == RESPONSES_URL:
        raise ProviderError("rejected")
    try:
        async with (
            new_client() as client,
            client.stream(
                "POST",
                url,
                data=data,
                json=payload,
                headers={"Accept": "application/json", "User-Agent": "AudioMancer"},
            ) as response,
        ):
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_AUTH_BYTES:
                    raise ProviderError()
            check_status(response, bytes(raw))
            try:
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ValueError
                return result
            except (ValueError, UnicodeError):
                raise ProviderError() from None
    except httpx.TimeoutException:
        raise ProviderError("timeout") from None
    except httpx.HTTPError:
        raise ProviderError("network") from None


def check_status(response, body=b""):
    """@brief Classify status and known error codes without exposing provider-controlled text."""
    status = response.status_code
    get_component_logger("chatgpt_http").debug("ChatGPT HTTP response status=%s", status)
    if 200 <= status < 300:
        return
    code = ""
    detail = ""
    parameter = ""
    try:
        parsed = json.loads(body)
        error = parsed.get("error", parsed)
        code = error.get("code", error.get("type", "")) if isinstance(error, dict) else error
        parameter = error.get("param", "") if isinstance(error, dict) else ""
        detail = str(parsed.get("detail", "")).lower()
    except (ValueError, AttributeError, UnicodeError):
        pass
    if not isinstance(code, str):
        code = ""
    if code in {"authorization_pending", "deviceauth_authorization_pending"}:
        category = "pending"
    elif code == "slow_down":
        category = "slow_down"
    elif code == "invalid_grant":
        category = "invalid_grant"
    elif code in {"access_denied", "authorization_declined", "expired_token", "expired_device_code"}:
        category = "denied"
    elif (
        status == 400
        and code in {"unsupported_parameter", "unsupported_value"}
        and isinstance(parameter, str)
        and parameter in {"text.format", "text.format.type", "response_format"}
    ):
        category = "unsupported_schema"
    elif status == 400 and "model" in detail and "not supported" in detail:
        category = "unsupported_model"
    elif 300 <= status < 400:
        category = "redirect"
    elif status == 401:
        category = "unauthorized"
    elif code in {"usage_limit_reached", "usage_not_included", "insufficient_quota"}:
        category = "quota"
    elif status == 429:
        category = "throttled"
    elif status >= 500:
        category = "transient"
    else:
        category = "rejected"
    try:
        retry_after = float(response.headers.get("retry-after", "0"))
        if not math.isfinite(retry_after):
            retry_after = 0
    except ValueError:
        retry_after = 0
    raise ProviderError(category, status=status, retry_after=retry_after)


# END OF FILE
