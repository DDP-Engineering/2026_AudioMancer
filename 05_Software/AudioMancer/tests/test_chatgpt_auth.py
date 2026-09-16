#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_chatgpt_auth.py
@brief OAuth protocol fixtures exercise only AudioMancer-owned synthetic credentials.
@details Exercises isolated protocol, lifecycle and workflow fixtures without live credentials.
"""

# IMPORTS

import asyncio
import base64
import importlib
import importlib.util
import json
from urllib.parse import parse_qs, urlparse

import pytest


def auth():
    """@brief Load the OAuth boundary under test."""
    name = "audiomancer.services.chatgpt_auth_service"
    assert importlib.util.find_spec(name) is not None, "Subscription OAuth flows are missing"
    return importlib.import_module(name)


def tokens():
    """@brief Build synthetic JWT metadata and OAuth tokens."""
    claims = {"https://api.openai.com/auth": {"chatgpt_account_id": "account-one"}, "email": "tester@example.test"}
    jwt = "x." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=") + ".x"
    return {"access_token": jwt, "refresh_token": "synthetic-refresh", "expires_in": 3600}


def test_pkce_authorization_and_token_claim_validation():
    """@brief Verify pkce authorization and token claim validation."""
    service = auth()
    url, verifier, state = service.authorization_request()
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "auth.openai.com"
    assert query["state"] == [state]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"][0] != verifier
    assert query["redirect_uri"] == ["http://localhost:1455/auth/callback"]
    assert len(verifier) >= 43 and len(state) >= 32
    credential = service.credential_from_tokens(tokens(), clock=lambda: 100)
    assert credential.account_id == "account-one"
    assert credential.expires_at == 3700
    with pytest.raises(RuntimeError):
        service.credential_from_tokens({**tokens(), "access_token": "invalid"})


def test_device_pending_slowdown_success_and_fixed_exchange(monkeypatch):
    """@brief Verify device pending slowdown success and fixed exchange."""
    service = auth()
    calls, notices, delays = [], [], []
    responses = [
        {"device_auth_id": "device-secret", "user_code": "ABCD-EFGH", "interval": "1"},
        service.http.ProviderError("pending", status=403),
        service.http.ProviderError("slow_down", status=400),
        {"authorization_code": "code-secret", "code_verifier": "verifier-secret"},
        tokens(),
    ]

    async def request(url, **kwargs):
        """@brief Serve the next expected OAuth response."""
        calls.append((url, kwargs))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def sleep(delay):
        """@brief Record or bypass test-only polling delays."""
        delays.append(delay)

    monkeypatch.setattr(service.http, "request_json", request)
    monkeypatch.setattr(service.asyncio, "sleep", sleep)
    credential = asyncio.run(service._device_flow(notices.append))
    assert credential.account_id == "account-one"
    assert delays == [1, 1, 6]
    assert calls[-1][1]["data"]["redirect_uri"] == "https://auth.openai.com/deviceauth/callback"
    assert calls[-1][1]["data"]["code_verifier"] == "verifier-secret"
    assert notices[0]["url"] == "https://auth.openai.com/codex/device"
    assert "device-secret" not in str(notices)


def test_browser_rejects_wrong_state_then_accepts_callback_and_releases_port(monkeypatch):
    """@brief Verify browser rejects wrong state then accepts callback and releases port."""
    service = auth()
    exchanges = []

    async def request(url, **kwargs):
        """@brief Serve the next expected OAuth response."""
        exchanges.append(kwargs)
        return tokens()

    monkeypatch.setattr(service.http, "request_json", request)

    async def scenario():
        """@brief Exercise listener ownership and verify port reuse after cleanup."""
        callbacks = []

        async def callback(query):
            """@brief Send a synthetic OAuth callback over the real loopback listener."""
            reader, writer = await asyncio.open_connection("127.0.0.1", 1455)
            writer.write(f"GET /auth/callback?{query} HTTP/1.1\r\nHost: localhost:1455\r\n\r\n".encode())
            await writer.drain()
            result = await reader.read()
            writer.close()
            await writer.wait_closed()
            return result

        async def send(state):
            """@brief Reject an invalid state before sending the correct OAuth state."""
            assert b"400" in await callback("code=bad&state=wrong")
            assert b"200" in await callback("code=good&state=" + state)

        def progress(payload):
            """@brief Capture authorization progress and dispatch a loopback callback."""
            state = parse_qs(urlparse(payload["url"]).query)["state"][0]
            callbacks.append(asyncio.create_task(send(state)))

        result = await service._browser_flow(progress)
        await asyncio.gather(*callbacks)
        listener = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 1455)
        listener.close()
        await listener.wait_closed()
        return result

    assert asyncio.run(scenario()).account_id == "account-one"
    assert len(exchanges) == 1
    assert exchanges[0]["data"]["code"] == "good"


def test_cancellation_awaits_transport_cleanup():
    """@brief Verify cancellation awaits transport cleanup."""
    service = auth()
    from audiomancer.services.operation_runtime_service import OperationCancelledError

    entered, closed = [], []

    async def operation():
        """@brief Keep I/O pending and record awaited cancellation cleanup."""
        try:
            entered.append(True)
            await asyncio.sleep(30)
        finally:
            closed.append(True)

    with pytest.raises(OperationCancelledError):
        service.http.run_cancellable(operation(), lambda: bool(entered))
    assert closed == [True]


def test_http_error_body_is_not_a_diagnostic_and_redirect_is_rejected():
    """@brief Verify http error body is not a diagnostic and redirect is rejected."""
    service = auth()
    import httpx

    response = httpx.Response(302, headers={"Location": "https://evil.test/sentinel"})
    with pytest.raises(service.http.ProviderError) as error:
        service.http.check_status(response, b'{"error":"sentinel-token"}')
    assert "sentinel" not in str(error.value)
    assert not error.value.retryable


def test_device_explicit_denial_does_not_poll_until_timeout(monkeypatch):
    """@brief Verify device explicit denial does not poll until timeout."""
    service = auth()
    calls = []

    async def request(url, **kwargs):
        """@brief Serve the next expected OAuth response."""
        calls.append(url)
        if len(calls) == 1:
            return {"device_auth_id": "device", "user_code": "CODE", "interval": 1}
        if len(calls) > 2:
            pytest.fail("Explicit denial must stop polling")
        raise service.http.ProviderError("denied", status=403)

    async def sleep(delay):
        """@brief Record or bypass test-only polling delays."""
        pass

    monkeypatch.setattr(service.http, "request_json", request)
    monkeypatch.setattr(service.asyncio, "sleep", sleep)
    with pytest.raises(service.http.ProviderError):
        asyncio.run(service._device_flow(lambda notice: None))


def test_hosted_model_rejection_has_actionable_safe_diagnostic():
    """@brief Verify hosted model rejection has actionable safe diagnostic."""
    service = auth()
    import httpx

    with pytest.raises(service.http.ProviderError, match="model is unavailable"):
        service.http.check_status(
            httpx.Response(400), b'{"detail":"The model is not supported when using Codex with a ChatGPT account."}'
        )


def test_occupied_callback_port_offers_device_fallback_without_opening_browser():
    """@brief An occupied callback port fails before presenting an unusable authorization URL."""
    service = auth()

    async def scenario():
        """@brief Retain a competing loopback listener during the browser attempt."""
        listener = await asyncio.start_server(lambda reader, writer: writer.close(), "127.0.0.1", 1455)
        try:
            with pytest.raises(RuntimeError, match="device-code"):
                await service._browser_flow(lambda notice: pytest.fail("Browser must not open before binding"))
        finally:
            listener.close()
            await listener.wait_closed()

    asyncio.run(scenario())


@pytest.mark.parametrize("method", ["browser", "device"])
@pytest.mark.parametrize("ending", ["cancel", "timeout"])
def test_pending_login_releases_resources_without_saving(monkeypatch, method, ending):
    """@brief Real pending flows cancel or expire without persisting credentials or retaining a listener."""
    service = auth()
    from audiomancer.services.operation_runtime_service import OperationCancelledError

    notices = []

    async def request(url, **kwargs):
        """@brief Supply a device code but never an authorized token."""
        assert url == service.http.DEVICE_CODE_URL
        return {"device_auth_id": "sentinel-device", "user_code": "TEST-CODE", "interval": 30}

    monkeypatch.setattr(service.http, "request_json", request)
    operation = service._browser_flow(notices.append) if method == "browser" else service._device_flow(notices.append)
    expected = OperationCancelledError if ending == "cancel" else service.http.ProviderError
    with pytest.raises(expected):
        service.http.run_cancellable(operation, lambda: ending == "cancel" and bool(notices), timeout=0.08)
    assert len(notices) == 1

    async def reuse_port():
        """@brief Prove that cleanup completed before the synchronous call returned."""
        listener = await asyncio.start_server(lambda reader, writer: writer.close(), "127.0.0.1", 1455)
        listener.close()
        await listener.wait_closed()

    asyncio.run(reuse_port())


def test_browser_denial_is_safe_and_releases_listener(monkeypatch):
    """@brief A matching denied callback fails without exchanging a code or exposing provider error text."""
    service = auth()

    async def request(*args, **kwargs):
        """@brief Reject accidental token exchange after denial."""
        pytest.fail("Denied login must not exchange a token")

    monkeypatch.setattr(service.http, "request_json", request)

    async def scenario():
        """@brief Submit a matching denial through the actual loopback socket."""
        callbacks = []

        async def deny(state):
            """@brief Deliver an OAuth error containing a diagnostic sentinel."""
            reader, writer = await asyncio.open_connection("127.0.0.1", 1455)
            writer.write(f"GET /auth/callback?state={state}&error=sentinel-secret HTTP/1.1\r\n\r\n".encode())
            await writer.drain()
            await reader.read()
            writer.close()
            await writer.wait_closed()

        def progress(notice):
            """@brief Schedule the callback after the listener has bound."""
            state = parse_qs(urlparse(notice["url"]).query)["state"][0]
            callbacks.append(asyncio.create_task(deny(state)))

        with pytest.raises(RuntimeError, match="denied") as error:
            await service._browser_flow(progress)
        assert "sentinel" not in str(error.value)
        await asyncio.gather(*callbacks)
        listener = await asyncio.start_server(lambda reader, writer: writer.close(), "127.0.0.1", 1455)
        listener.close()
        await listener.wait_closed()

    asyncio.run(scenario())


# END OF FILE
