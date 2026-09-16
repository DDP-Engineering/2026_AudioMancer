#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_chatgpt_provider.py
@brief Responses transport completion, cancellation and JSON facade contracts.
@details Exercises isolated protocol, lifecycle and workflow fixtures without live credentials.
"""

# IMPORTS

import asyncio
import importlib
import importlib.util
import json
import threading
import time

import httpx
import pytest

from audiomancer.services.chatgpt_credential_service import Credential, CredentialManager
from audiomancer.services.chatgpt_storage_service import MemoryStore


def provider():
    """@brief Load the completed Responses boundary."""
    name = "audiomancer.services.chatgpt_provider_service"
    assert importlib.util.find_spec(name) is not None, "Complete Responses transport is missing"
    return importlib.import_module(name)


def manager():
    """@brief Create an isolated signed-in memory account."""
    value = CredentialManager(MemoryStore())
    value.finish_login(
        value.begin_login(), Credential("synthetic-access", "synthetic-refresh", time.time() + 3600, "one")
    )
    return value


def sse(payload, *, event=None):
    """@brief Encode one protocol event as UTF-8 SSE."""
    return (
        (("event: " + event + "\r\n") if event else "").encode()
        + b"data: "
        + json.dumps(payload, ensure_ascii=False).encode()
        + b"\r\n\r\n"
    )


def completed(text='{"ok":true}', **extra):
    """@brief Build a complete assistant response fixture."""
    return {
        "type": "response.completed",
        "response": {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            **extra,
        },
    }


class Fragments(httpx.AsyncByteStream):
    """@brief Emit byte-fragmented HTTP streams and record closure."""

    def __init__(self, data, *, hang=False):
        self.data, self.hang, self.closed = data, hang, False

    async def __aiter__(self):
        for byte in self.data:
            yield bytes([byte])
        if self.hang:
            await asyncio.sleep(30)

    async def aclose(self):
        """@brief Record transport closure."""
        self.closed = True


def install(monkeypatch, service, stream, status=200, captures=None):
    """@brief Inject a network-free async HTTP transport."""

    async def handle(request):
        """@brief Return the configured synthetic HTTP response."""
        if captures is not None:
            captures.append(request)
        return httpx.Response(status, stream=stream, headers={"content-type": "text/event-stream"})

    monkeypatch.setattr(
        service.http, "new_client", lambda timeout=15: httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )


def test_fragmented_stream_terminal_closes_open_socket_without_duplicate_text(monkeypatch):
    """@brief Verify fragmented stream terminal closes open socket without duplicate text."""
    service = provider()
    data = b": heartbeat\r\n\r\n" + sse({"type": "response.output_text.delta", "delta": '{"name":"țară"}'})
    data += sse(completed('{"name":"țară"}', usage={"input_tokens": 20, "output_tokens": 5, "total_tokens": 25}))
    stream, captures = Fragments(data, hang=True), []
    install(monkeypatch, service, stream, captures=captures)
    result = service.complete({"model_name": "gpt-5.4"}, "System", "User", manager=manager())
    assert result.text == '{"name":"țară"}'
    assert result.usage["total_tokens"] == 25
    assert stream.closed
    body = json.loads(captures[0].content)
    assert body["store"] is False and body["stream"] is True
    assert not {"temperature", "max_tokens", "max_output_tokens", "messages"} & body.keys()
    assert captures[0].url == service.http.RESPONSES_URL


@pytest.mark.parametrize(
    "event",
    [
        {"type": "response.incomplete", "response": {"status": "incomplete"}},
        {"type": "response.failed", "response": {"error": {"message": "secret-sentinel"}}},
        {"type": "response.refusal.delta", "delta": "secret-sentinel"},
        {"type": "response.output_item.added", "item": {"type": "function_call"}},
    ],
)
def test_terminal_errors_never_become_json_or_repair(monkeypatch, event):
    """@brief Verify terminal errors never become json or repair."""
    service = provider()
    stream = Fragments(sse({"type": "response.output_text.delta", "delta": '{"ok":true}'}) + sse(event))
    captures = []
    install(monkeypatch, service, stream, captures=captures)
    with pytest.raises(RuntimeError) as error:
        service.complete({"model_name": "gpt-5.4"}, "System", "User", manager=manager())
    assert "sentinel" not in str(error.value)
    assert len(captures) == 1 and stream.closed


def test_eof_without_terminal_is_rejected_without_retry_after_output(monkeypatch):
    """@brief Verify eof without terminal is rejected without retry after output."""
    service = provider()
    captures = []
    install(
        monkeypatch, service, Fragments(sse({"type": "response.output_text.delta", "delta": "{}"})), captures=captures
    )
    with pytest.raises(RuntimeError, match="incomplete"):
        service.complete({"model_name": "gpt-5.4"}, "System", "User", manager=manager())
    assert len(captures) == 1


def test_required_schema_ignores_editable_profile_capability(monkeypatch):
    """@brief Verify required schema ignores editable profile capability."""
    service = provider()
    captures = []
    install(monkeypatch, service, Fragments(sse(completed())), captures=captures)
    with pytest.raises(ValueError, match="verified"):
        service.complete(
            {"model_name": "gpt-5.4", "supports_structured_output": True},
            "System",
            "User",
            manager=manager(),
            schema={"type": "object"},
            require_schema=True,
        )
    assert not captures


def test_zero_retry_override_and_quota_do_not_repeat(monkeypatch):
    """@brief Verify zero retry override and quota do not repeat."""
    service = provider()
    for status, body in [(503, b"{}"), (429, b'{"error":{"code":"usage_limit_reached"}}')]:
        captures = []
        install(monkeypatch, service, Fragments(body), status=status, captures=captures)
        with pytest.raises(RuntimeError):
            service.complete({"model_name": "gpt-5.4"}, "System", "User", manager=manager(), retry_count=0)
        assert len(captures) == 1


def test_live_dialect_allows_missing_content_type_and_empty_terminal_output(monkeypatch):
    """@brief Verify live dialect allows missing content type and empty terminal output."""
    service = provider()
    message = {
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": '{"ok":true}'}],
    }
    stream = Fragments(
        sse({"type": "response.output_item.done", "item": message, "output_index": 0})
        + sse({"type": "response.completed", "response": {"status": "completed", "output": []}})
    )

    async def handle(request):
        """@brief Return the configured synthetic HTTP response."""
        return httpx.Response(200, stream=stream)

    monkeypatch.setattr(
        service.http, "new_client", lambda timeout=15: httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    assert service.complete({"model_name": "gpt-5.5"}, "System", "User", manager=manager()).text == '{"ok":true}'


def test_stream_cancellation_closes_transport_before_return(monkeypatch):
    """@brief A stalled active stream is closed before cancellation reaches the workflow."""
    from audiomancer.services.operation_runtime_service import OperationCancelledError

    service = provider()
    stream = Fragments(sse({"type": "response.created"}), hang=True)
    install(monkeypatch, service, stream)
    cancelled = threading.Event()
    timer = threading.Timer(0.1, cancelled.set)
    timer.start()
    try:
        with pytest.raises(OperationCancelledError):
            service.complete({"model_name": "gpt-5.5"}, "system", "user", manager=manager(), cancel=cancelled.is_set)
        assert stream.closed
    finally:
        timer.join()


def test_one_unauthorized_recovery_uses_rotated_token_only_at_fixed_destination(monkeypatch):
    """@brief HTTP 401 refreshes once and never uses the editable profile URL or API key."""
    service, account, requests = provider(), manager(), []
    account.refresh = lambda old, cancel: Credential("rotated-access", "rotated-refresh", time.time() + 3600, "one")

    async def handle(request):
        """@brief Reject the original token and complete the rotated-token request."""
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(401, json={"error": {"code": "unauthorized"}})
        return httpx.Response(200, stream=Fragments(sse(completed())))

    monkeypatch.setattr(
        service.http, "new_client", lambda timeout=15: httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    service.complete(
        {"model_name": "gpt-5.5", "base_url": "https://evil.test", "api_key": "wrong"},
        "system",
        "user",
        manager=account,
        retry_count=1,
    )
    assert len(requests) == 2
    assert all(str(request.url) == service.http.RESPONSES_URL for request in requests)
    assert requests[1].headers["authorization"] == "Bearer rotated-access"


def test_multiline_sse_data_and_terminal_refusal_are_not_ambiguous(monkeypatch):
    """@brief Multiline events parse correctly while completed refusals cannot be repaired."""
    service = provider()
    raw = json.dumps(completed(), indent=2).splitlines()
    stream = Fragments(b"\n".join(b"data: " + line.encode() for line in raw) + b"\n\n")
    install(monkeypatch, service, stream)
    assert service.complete({"model_name": "gpt-5.5"}, "s", "u", manager=manager()).text == '{"ok":true}'
    event = completed()
    event["response"]["output"][0]["content"] = [{"type": "refusal", "refusal": "sentinel"}]
    install(monkeypatch, service, Fragments(sse(event)))
    with pytest.raises(RuntimeError):
        service.complete({"model_name": "gpt-5.5"}, "s", "u", manager=manager())


def test_wall_clock_timeout_after_output_never_replays_request(monkeypatch):
    """@brief The total request deadline cannot retry a stream after partial output."""
    service, requests = provider(), []
    stream = Fragments(sse({"type": "response.output_text.delta", "delta": "{"}), hang=True)
    install(monkeypatch, service, stream, captures=requests)
    with pytest.raises(RuntimeError, match="timed out"):
        service.complete(
            {"model_name": "gpt-5.5", "request_timeout_seconds": 1}, "system", "user", manager=manager(), retry_count=1
        )
    assert len(requests) == 1
    assert stream.closed


@pytest.mark.parametrize("required,retries,expected_calls", [(False, 2, 2), (True, 2, 1), (False, 0, 1)])
def test_explicit_schema_rejection_respects_call_local_fallback(monkeypatch, required, retries, expected_calls):
    """@brief Optional schema fallback stays local, bounded and forbidden by required-schema callers."""
    service, account, requests = provider(), manager(), []
    generation, _ = account.acquire()
    account.mark_verified(generation, "gpt-5.5", True)

    async def handle(request):
        """@brief Reject only schema formatting, then complete the unconstrained request."""
        requests.append(json.loads(request.content))
        if "text" in requests[-1]:
            return httpx.Response(400, json={"error": {"code": "unsupported_parameter", "param": "text.format"}})
        return httpx.Response(200, stream=Fragments(sse(completed())))

    monkeypatch.setattr(
        service.http, "new_client", lambda timeout=15: httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    arguments = {
        "manager": account,
        "schema": {"type": "object"},
        "require_schema": required,
        "allow_schema_fallback": True,
        "retry_count": retries,
    }
    if expected_calls == 2:
        assert service.complete({"model_name": "gpt-5.5"}, "system", "user", **arguments).text == '{"ok":true}'
        assert account.is_verified(generation, "gpt-5.5", schema=True)
        assert "text" in service.build_request({"model_name": "gpt-5.5"}, "system", "user", schema={})[0]
    else:
        with pytest.raises(service.http.ProviderError):
            service.complete({"model_name": "gpt-5.5"}, "system", "user", **arguments)
    assert len(requests) == expected_calls


@pytest.mark.parametrize("effort", ["low", "high", "max"])
def test_explicit_effort_is_sent_exactly_and_reported(monkeypatch, effort):
    """@brief Subscription profiles send the selected supported effort instead of a hard-coded medium."""
    service, captures = provider(), []
    install(monkeypatch, service, Fragments(sse(completed())), captures=captures)
    result = service.complete({"model_name": "gpt-5.6-luna", "reasoning_effort": effort}, "s", "u", manager=manager())
    assert json.loads(captures[0].content)["reasoning"]["effort"] == effort
    assert result.reasoning_effort_effective == effort
    assert result.reasoning_mode_effective == "enabled"


def test_unsupported_effort_never_submits_or_falls_back(monkeypatch):
    """@brief An unavailable saved choice fails before inference, including a legacy disabled choice."""
    service = provider()
    monkeypatch.setattr(service.http, "new_client", lambda *args, **kwargs: pytest.fail("Unexpected network request"))
    for preference in ({"reasoning_effort": "ultra"}, {"reasoning_mode": "disabled"}):
        with pytest.raises(ValueError, match="reasoning effort"):
            service.complete({"model_name": "gpt-5.6-luna", **preference}, "s", "u", manager=manager())


# END OF FILE
