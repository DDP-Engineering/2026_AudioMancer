#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_chatgpt_catalog.py
@brief Native model discovery and exact reasoning selection contracts.
@details Injects account stores, clocks and HTTP transports without live credentials.
"""

# IMPORTS

import asyncio
from dataclasses import replace
import importlib
import importlib.util
import json
from threading import Event, Timer

import httpx
import pytest

from audiomancer.services import chatgpt_http_service as http
from audiomancer.services.operation_runtime_service import OperationCancelledError
from test_chatgpt_provider import manager


def catalog():
    """@brief Locate the native catalog boundary before exercising its behavior."""
    name = "audiomancer.services.chatgpt_catalog_service"
    assert importlib.util.find_spec(name), "Native subscription catalog service is missing"
    return importlib.import_module(name)


def entry(model="future-model", **changes):
    """@brief Build a native provider metadata entry with deliberately irrelevant instructions."""
    return {
        "slug": model,
        "visibility": "list",
        "input_modalities": ["text"],
        "priority": 2,
        "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}],
        "default_reasoning_level": "low",
        "context_window": 272000,
        "max_context_window": 872000,
        "base_instructions": "Do not persist provider instructions",
        **changes,
    }


def install(monkeypatch, handler):
    """@brief Replace network access with a deterministic HTTP transport."""
    monkeypatch.setattr(http, "new_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_native_discovery_filters_primary_text_models_and_caches_by_connection(monkeypatch):
    """@brief Fresh metadata discovers future names, excludes hidden/nontext entries and obeys refresh TTL."""
    service, account, calls = catalog(), manager(), []

    def handle(request):
        """@brief Capture only the synthetic request and serve the native catalog shape."""
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "models": [
                    entry(),
                    entry("hidden", visibility="hide"),
                    entry("audio", input_modalities=["audio"]),
                    entry("first", priority=1),
                ]
            },
        )

    install(monkeypatch, handle)
    result = service.list_models(manager=account, now=1000)
    assert result["source"] == "live"
    assert [m["id"] for m in result["models"]] == ["first", "future-model"]
    assert result["models"][1]["efforts"] == ["low", "high"]
    assert result["models"][1]["context_window"] == 272000
    assert calls[0].method == "GET"
    assert str(calls[0].url).startswith("https://chatgpt.com/backend-api/codex/models?client_version=")
    assert calls[0].headers["authorization"] == "Bearer synthetic-access"
    assert "base_instructions" not in json.dumps(account.store.read())
    assert service.list_models(manager=account, now=1001)["source"] == "cache"
    assert service.list_models(manager=account, now=1001)["models"][1]["context_window"] == 272000
    assert len(calls) == 1
    service.list_models(manager=account, now=1002, force=True)
    assert len(calls) == 2
    generation, _ = account.acquire()
    assert not account.is_verified(generation, "future-model", schema=True)
    account.disconnect()
    signed_out = service.list_models(manager=account, now=1003)
    assert signed_out["source"] == "builtin"
    assert "future-model" not in [m["id"] for m in signed_out["models"]]


def test_refresh_failure_keeps_last_good_cache_without_claiming_freshness(monkeypatch):
    """@brief Invalid/failed refresh never overwrites the current account's useful metadata."""
    service, account = catalog(), manager()
    install(monkeypatch, lambda request: httpx.Response(200, json={"models": [entry()]}))
    service.list_models(manager=account, now=1000)
    install(monkeypatch, lambda request: httpx.Response(503, text="sentinel-server-error"))
    result = service.list_models(manager=account, now=5000)
    assert result["source"] == "stale_cache"
    assert result["models"][0]["id"] == "future-model"
    assert "sentinel" not in str(result)


def test_cancel_and_disconnect_during_fetch_cannot_restore_catalog(monkeypatch):
    """@brief Cancellation propagates and a late response cannot become a new connection's cache."""
    service, account = catalog(), manager()

    def handle(request):
        """@brief Disconnect before returning a formerly authorized response."""
        account.disconnect()
        return httpx.Response(200, json={"models": [entry()]})

    install(monkeypatch, handle)
    with pytest.raises(RuntimeError, match="changed"):
        service.list_models(manager=account)
    assert not account.store.read().get("catalog")
    with pytest.raises(OperationCancelledError):
        service.list_models(manager=manager(), cancel=lambda: True)


@pytest.mark.parametrize("body", [{"models": "wrong"}, {"models": [entry(slug="bad\nmodel")]}, {}])
def test_invalid_metadata_uses_labelled_builtin_candidates(monkeypatch, body):
    """@brief Malformed metadata cannot become selectable models or stored capability data."""
    service, account = catalog(), manager()
    install(monkeypatch, lambda request: httpx.Response(200, json=body))
    result = service.list_models(manager=account)
    assert result["source"] == "builtin"
    assert {"gpt-5.6-terra", "gpt-5.6-luna"} <= {m["id"] for m in result["models"]}


def test_catalog_401_rotates_once_and_redirect_never_forwards_credentials(monkeypatch):
    """@brief Only the built-in catalog receives authorization, with one serialized 401 recovery."""
    service, account, calls = catalog(), manager(), []
    account.refresh = lambda credential, cancel: replace(credential, access_token="rotated-access")

    def handle(request):
        """@brief Reject the first bearer and accept its single replacement."""
        calls.append(request)
        return httpx.Response(401) if len(calls) == 1 else httpx.Response(200, json={"models": [entry()]})

    install(monkeypatch, handle)
    assert service.list_models(manager=account)["source"] == "live"
    assert len(calls) == 2 and calls[1].headers["authorization"] == "Bearer rotated-access"
    install(monkeypatch, lambda request: httpx.Response(302, headers={"location": "https://untrusted.example"}))
    assert service.list_models(manager=account, force=True)["source"] == "stale_cache"


def test_stream_cancellation_closes_catalog_transport(monkeypatch):
    """@brief Cancelling a blocked metadata stream waits for its resource cleanup."""
    service, cancelled = catalog(), Event()

    class Blocked(httpx.AsyncByteStream):
        """@brief Model a catalog response that never finishes its body."""
        closed = False

        async def __aiter__(self):
            """@brief Yield a partial object then wait for cancellation."""
            yield b'{"models":'
            await asyncio.sleep(30)

        async def aclose(self):
            """@brief Record HTTP resource release."""
            self.closed = True

    stream = Blocked()
    install(monkeypatch, lambda request: httpx.Response(200, stream=stream))
    timer = Timer(0.15, cancelled.set)
    timer.start()
    try:
        with pytest.raises(OperationCancelledError):
            service.list_models(manager=manager(), cancel=cancelled.is_set)
        assert stream.closed
    finally:
        timer.cancel()


def test_oversized_catalog_and_malformed_cache_do_not_break_account(monkeypatch):
    """@brief Optional metadata obeys response limits and a bad cache can be replaced safely."""
    service, account = catalog(), manager()
    payload = account.store.read()
    payload["catalog"] = {"fetched_at": "invalid", "models": []}
    account.store.write(payload)
    install(monkeypatch, lambda request: httpx.Response(200, content=b"x" * (service.MAX_CATALOG_BYTES + 1)))
    assert service.list_models(manager=account)["source"] == "builtin"
    install(monkeypatch, lambda request: httpx.Response(200, json={"models": [entry()]}))
    assert service.list_models(manager=account)["source"] == "live"


def test_cached_models_survive_temporary_credential_refresh_failure(monkeypatch):
    """@brief Offline renewal keeps the last good same-account catalog available as stale metadata."""
    service, account = catalog(), manager()
    install(monkeypatch, lambda request: httpx.Response(200, json={"models": [entry()]}))
    service.list_models(manager=account, now=1000)
    payload = account.store.read()
    payload["credential"]["expires_at"] = 1
    account.store.write(payload)

    def unavailable(credential, cancel):
        """@brief Simulate temporary token endpoint unavailability."""
        raise http.ProviderError("network")

    account.refresh = unavailable
    result = service.list_models(manager=account, force=True, now=5000)
    assert result["source"] == "stale_cache"
    assert result["models"][0]["id"] == "future-model"


@pytest.mark.parametrize("context", [None, True, -1, "272000", 10**20])
def test_invalid_context_metadata_remains_unknown(monkeypatch, context):
    """@brief Missing or invalid default context never borrows the separate maximum capacity."""
    service = catalog()
    install(monkeypatch, lambda request: httpx.Response(200, json={"models": [entry(context_window=context)]}))
    result = service.list_models(manager=manager())
    assert result["models"][0]["context_window"] is None


def test_legacy_catalog_without_context_refreshes_even_inside_ttl(monkeypatch):
    """@brief Upgrade cached model metadata on opening settings without waiting an hour."""
    service, account, calls = catalog(), manager(), []
    payload = account.store.read()
    payload["catalog"] = {"fetched_at": 1000, "models": [
        {"id": "future-model", "efforts": ["low"], "default_effort": "low"}
    ]}
    account.store.write(payload)

    def handle(request):
        """@brief Supply context metadata missing from an older cache."""
        calls.append(request)
        return httpx.Response(200, json={"models": [entry()]})

    install(monkeypatch, handle)
    result = service.list_models(manager=account, now=1001)
    assert len(calls) == 1
    assert result["source"] == "live"
    assert result["models"][0]["context_window"] == 272000


# END OF FILE
