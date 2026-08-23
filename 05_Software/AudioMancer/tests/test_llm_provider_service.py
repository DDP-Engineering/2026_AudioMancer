#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_llm_provider_service.py
@brief Focused tests for the AudioMancer LLM provider service.
@details Verifies JSON normalization and retry behavior for AI-assisted
         cleanup provider requests.
"""

# IMPORTS

import io
import json
import time
from types import SimpleNamespace
from urllib import error

import pytest

from audiomancer.services import llm_provider_service
from audiomancer.services.operation_runtime_service import OperationCancelledError


class _FakeResponse:
    """
    @brief Minimal context-manager response used by provider HTTP tests.
    @details Stores one response body and exposes the subset of the urllib
             response contract needed by the LLM provider service.
    """

    def __init__(self, body: str) -> None:
        """
        @brief      Provide the init test helper.
        @return     None.
        @exception  None
        """
        self._body = body

    def __enter__(self):
        """
        @brief      Provide the enter test helper.
        @return     None.
        @exception  None
        """
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """
        @brief      Provide the exit test helper.
        @return     None.
        @exception  None
        """
        _ = exc_type
        _ = exc
        _ = tb

    def read(self) -> bytes:
        """
        @brief      Return the configured fake response body as UTF-8 bytes.
        @return     Encoded fake response body.
        @exception  None
        """
        return self._body.encode("utf-8")


def test_chat_json_parses_fenced_json(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify fenced JSON model output is normalized into one JSON object.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    monkeypatch.setattr(
        llm_provider_service.request,
        "urlopen",
        lambda *_args, **_kwargs: _FakeResponse(
            '{"choices":[{"message":{"content":"```json\\n{\\"results\\":[{\\"unit_id\\":\\"unit-0001\\",\\"label\\":\\"story\\"}]}\\n```"}}]}'
        ),
    )

    result = llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "model_name": "qwen3-8b",
            "request_timeout_seconds": 30,
            "temperature": 0.2,
            "max_output_tokens": 256,
        },
        "system",
        "user",
        log_path=tmp_path / "transactions.log",
    )

    assert result["payload"]["results"][0]["label"] == "story"
    assert result["usage"]["usage_available"] is False


def test_chat_json_retries_transient_failure(monkeypatch) -> None:
    """
    @brief      Verify transient provider failures are retried before success.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    call_counter = {"count": 0}
    retry_delays: list[float] = []

    def _fake_urlopen(*_args, **_kwargs):
        """
        @brief      Simulate one transient provider failure followed by success.
        @param[in]  _args Ignored positional request arguments.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  URLError Raised on the first request attempt.
        """
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            raise error.URLError("temporary failure")
        return _FakeResponse(
            '{"choices":[{"message":{"content":"{\\"results\\":[{\\"unit_id\\":\\"unit-0001\\",\\"label\\":\\"story\\"}]}"}}]}'
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(
        llm_provider_service,
        "_wait_for_retry_backoff",
        lambda delay_seconds, _cancel_requested: retry_delays.append(delay_seconds),
        raising=False,
    )

    result = llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "model_name": "qwen3-8b",
            "request_timeout_seconds": 30,
            "temperature": 0.2,
            "max_output_tokens": 256,
        },
        "system",
        "user",
    )

    assert call_counter["count"] == 2
    assert retry_delays == [0.5]
    assert result["payload"]["results"][0]["unit_id"] == "unit-0001"


def test_chat_json_uses_bounded_exponential_retry_delays(monkeypatch) -> None:
    """
    @brief      Verify exact bounded delays occur only before remaining outer attempts.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    call_counter = {"count": 0}
    retry_delays: list[float] = []

    def _transient_failure(*_args, **_kwargs):
        """
        @brief      Raise one controlled transient provider failure.
        @param[in]  _args Ignored positional request arguments.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     None.
        @exception  _TransientProviderError Always raised for this retry test.
        """
        call_counter["count"] += 1
        raise llm_provider_service._TransientProviderError(  # noqa: SLF001
            "Transient AI provider failure: controlled test failure"
        )

    monkeypatch.setattr(
        llm_provider_service,
        "_request_chat_completion_with_cancellation",
        _transient_failure,
    )
    monkeypatch.setattr(
        llm_provider_service,
        "_wait_for_retry_backoff",
        lambda delay_seconds, _cancel_requested: retry_delays.append(delay_seconds),
        raising=False,
    )

    with pytest.raises(RuntimeError, match="controlled test failure"):
        llm_provider_service.chat_json(
            {
                "id": "profile_1",
                "backend_kind": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-5.4-mini",
                "request_timeout_seconds": 30,
                "temperature": 0.1,
                "max_output_tokens": 256,
            },
            "system",
            "user",
            retry_count_override=5,
        )

    assert call_counter["count"] == 6
    assert retry_delays == [0.5, 1.0, 2.0, 4.0, 4.0]


def test_chat_json_cancels_before_retry_backoff_without_another_request(monkeypatch) -> None:
    """
    @brief      Verify cancellation before waiting prevents the next provider dispatch.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    call_counter = {"count": 0}

    def _transient_failure(*_args, **_kwargs):
        """
        @brief      Raise one controlled transient provider failure.
        @param[in]  _args Ignored positional request arguments.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     None.
        @exception  _TransientProviderError Always raised for this cancellation test.
        """
        call_counter["count"] += 1
        raise llm_provider_service._TransientProviderError(  # noqa: SLF001
            "Transient AI provider failure: controlled test failure"
        )

    monkeypatch.setattr(
        llm_provider_service,
        "_request_chat_completion_with_cancellation",
        _transient_failure,
    )
    monkeypatch.setattr(
        llm_provider_service,
        "time",
        SimpleNamespace(
            monotonic=time.monotonic,
            sleep=lambda _seconds: pytest.fail("Cancellation before backoff must not sleep."),
        ),
        raising=False,
    )

    with pytest.raises(OperationCancelledError, match="retry backoff"):
        llm_provider_service.chat_json(
            {
                "id": "profile_1",
                "backend_kind": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-5.4-mini",
                "request_timeout_seconds": 30,
                "temperature": 0.1,
                "max_output_tokens": 256,
            },
            "system",
            "user",
            cancel_requested=lambda: True,
            retry_count_override=3,
        )

    assert call_counter["count"] == 1


def test_chat_json_cancels_during_sliced_retry_backoff(monkeypatch) -> None:
    """
    @brief      Verify short polling slices stop a backoff before another provider request.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    call_counter = {"count": 0}
    clock = {"now": 0.0}
    cancellation_checks = {"count": 0}
    sleep_slices: list[float] = []

    def _transient_failure(*_args, **_kwargs):
        """
        @brief      Raise one controlled transient provider failure.
        @param[in]  _args Ignored positional request arguments.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     None.
        @exception  _TransientProviderError Always raised for this backoff test.
        """
        call_counter["count"] += 1
        raise llm_provider_service._TransientProviderError(  # noqa: SLF001
            "Transient AI provider failure: controlled test failure"
        )

    def _cancel_requested() -> bool:
        """
        @brief      Request cancellation after three polling checks.
        @return     True after the configured check count is reached.
        @exception  None
        """
        cancellation_checks["count"] += 1
        return cancellation_checks["count"] >= 3

    def _sleep(seconds: float) -> None:
        """
        @brief      Advance the controlled retry clock by one sleep slice.
        @param[in]  seconds Requested sleep duration.
        @return     None.
        @exception  None
        """
        sleep_slices.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(
        llm_provider_service,
        "_request_chat_completion_with_cancellation",
        _transient_failure,
    )
    monkeypatch.setattr(
        llm_provider_service,
        "time",
        SimpleNamespace(monotonic=lambda: clock["now"], sleep=_sleep),
        raising=False,
    )

    with pytest.raises(OperationCancelledError, match="retry backoff"):
        llm_provider_service.chat_json(
            {
                "id": "profile_1",
                "backend_kind": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-5.4-mini",
                "request_timeout_seconds": 30,
                "temperature": 0.1,
                "max_output_tokens": 256,
            },
            "system",
            "user",
            cancel_requested=_cancel_requested,
            retry_count_override=3,
        )

    assert call_counter["count"] == 1
    assert sleep_slices == [0.05, 0.05]


def test_chat_json_sends_response_format_when_structured_output_is_supported(monkeypatch) -> None:
    """
    @brief      Verify structured-output-capable profiles request JSON-object response format.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[dict[str, object]] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Capture one structured-output provider request.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  None
        """
        request_bodies.append(json.loads(http_request.data.decode("utf-8")))
        return _FakeResponse(
            '{"choices":[{"message":{"content":"{\\"results\\":[{\\"unit_id\\":\\"unit-0001\\"}]}"}}]}'
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)

    llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-5.4-mini",
            "request_timeout_seconds": 30,
            "temperature": 0.1,
            "max_output_tokens": 256,
            "supports_structured_output": True,
        },
        "system",
        "user",
    )

    assert request_bodies[0]["response_format"] == {"type": "json_object"}


def test_chat_json_sends_json_schema_response_format_for_local_backends(monkeypatch) -> None:
    """
    @brief      Verify local backends receive their supported JSON Schema response format.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[dict[str, object]] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Capture one local-backend structured-output provider request.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  None
        """
        request_bodies.append(json.loads(http_request.data.decode("utf-8")))
        return _FakeResponse(
            '{"choices":[{"message":{"content":"{\\"results\\":[{\\"unit_id\\":\\"unit-0001\\"}]}"}}]}'
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)

    expected_response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "audiomancer_json_response",
            "schema": {
                "type": "object",
                "additionalProperties": True,
            },
        },
    }
    for backend_kind in ("lmstudio", "ollama"):
        llm_provider_service.chat_json(
            {
                "id": "profile_1",
                "backend_kind": backend_kind,
                "base_url": "http://127.0.0.1:1234/v1",
                "model_name": "google/gemma-4-26b-a4b",
                "request_timeout_seconds": 30,
                "temperature": 0.1,
                "max_output_tokens": 256,
                "supports_structured_output": True,
            },
            "system",
            "user",
        )

    assert [request_body["response_format"] for request_body in request_bodies] == [
        expected_response_format,
        expected_response_format,
    ]


def test_chat_json_sends_operation_schema_response_format_for_local_backends(monkeypatch) -> None:
    """
    @brief      Verify local structured-output requests can use an operation-specific JSON Schema.
    @details    Covers SB3-SPEC-001 and REQ-FUNC-044.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[dict[str, object]] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Capture one operation-specific structured-output provider request.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  None
        """
        request_bodies.append(json.loads(http_request.data.decode("utf-8")))
        return _FakeResponse('{"choices":[{"message":{"content":"{\\"blocks\\":[]}"}}]}')

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)
    speech_blocks_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["blocks"],
        "properties": {
            "blocks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["source_span_ids", "speaker_id", "content_kind", "confidence"],
                    "properties": {
                        "source_span_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                        "speaker_id": {"type": "string"},
                        "content_kind": {"type": "string"},
                        "confidence": {"type": "string"},
                        "warning_flags": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        },
    }

    llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234/v1",
            "model_name": "google/gemma-4-26b-a4b",
            "request_timeout_seconds": 30,
            "temperature": 0.1,
            "max_output_tokens": 256,
            "supports_structured_output": True,
        },
        "system",
        "user",
        response_schema=speech_blocks_schema,
        response_schema_name="speech_blocks_source_span_selection",
    )

    assert request_bodies[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "speech_blocks_source_span_selection",
            "schema": speech_blocks_schema,
        },
    }


def test_chat_json_omits_response_format_when_structured_output_is_not_supported(monkeypatch) -> None:
    """
    @brief      Verify profiles without structured-output support keep prompt-only JSON behavior.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[dict[str, object]] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Capture one prompt-only provider request.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  None
        """
        request_bodies.append(json.loads(http_request.data.decode("utf-8")))
        return _FakeResponse(
            '{"choices":[{"message":{"content":"{\\"results\\":[{\\"unit_id\\":\\"unit-0001\\"}]}"}}]}'
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)

    llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "model_name": "qwen3-8b",
            "request_timeout_seconds": 30,
            "temperature": 0.2,
            "max_output_tokens": 256,
            "supports_structured_output": False,
        },
        "system",
        "user",
    )

    assert "response_format" not in request_bodies[0]


def test_chat_json_retries_without_response_format_when_provider_rejects_it(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify unsupported response_format failures retry once without the field and log fallback.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[dict[str, object]] = []
    retry_delays: list[float] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate one response_format compatibility failure followed by success.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  HTTPError Raised on the first incompatible request.
        """
        request_payload = json.loads(http_request.data.decode("utf-8"))
        request_bodies.append(request_payload)
        if len(request_bodies) == 1:
            raise error.HTTPError(
                http_request.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(
                    b'{"error":{"message":"Unsupported parameter: response_format",'
                    b'"param":"response_format","code":"unsupported_parameter"}}'
                ),
            )
        return _FakeResponse(
            '{"choices":[{"message":{"content":"{\\"results\\":[{\\"unit_id\\":\\"unit-0001\\"}]}"}}]}'
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(
        llm_provider_service,
        "_wait_for_retry_backoff",
        lambda delay_seconds, _cancel_requested: retry_delays.append(delay_seconds),
        raising=False,
    )
    log_path = tmp_path / "transactions.log"

    result = llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-5.4-mini",
            "request_timeout_seconds": 30,
            "temperature": 0.1,
            "max_output_tokens": 256,
            "supports_structured_output": True,
        },
        "system",
        "user",
        log_path=log_path,
    )

    log_text = log_path.read_text(encoding="utf-8")

    assert len(request_bodies) == 2
    assert request_bodies[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in request_bodies[1]
    assert "response_format_unsupported_retry_without_response_format" in log_text
    assert retry_delays == []
    assert result["payload"]["results"][0]["unit_id"] == "unit-0001"


def test_chat_json_retains_response_format_fallback_across_outer_retries(
    monkeypatch,
    tmp_path,
) -> None:
    """
    @brief      Verify learned response-format compatibility survives a transient failure.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[dict[str, object]] = []
    retry_delays: list[float] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate one response-format rejection followed by success.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  HTTPError Raised for the first incompatible request.
        """
        request_payload = json.loads(http_request.data.decode("utf-8"))
        request_bodies.append(request_payload)
        if len(request_bodies) == 1:
            raise error.HTTPError(
                http_request.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(
                    b'{"error":{"message":"Unsupported parameter: response_format",'
                    b'"param":"response_format","code":"unsupported_parameter"}}'
                ),
            )
        if len(request_bodies) == 2:
            raise error.HTTPError(
                http_request.full_url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=io.BytesIO(b'{"error":{"message":"temporarily rate limited"}}'),
            )
        return _FakeResponse(
            '{"choices":[{"message":{"content":"{\\"results\\":[{\\"unit_id\\":\\"retained-format\\"}]}"}}]}'
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(
        llm_provider_service,
        "_wait_for_retry_backoff",
        lambda delay_seconds, _cancel_requested: retry_delays.append(delay_seconds),
        raising=False,
    )
    log_path = tmp_path / "transactions.log"

    result = llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-5.4-mini",
            "request_timeout_seconds": 30,
            "temperature": 0.1,
            "max_output_tokens": 256,
            "supports_structured_output": True,
        },
        "system",
        "user",
        log_path=log_path,
        retry_count_override=1,
    )

    fallback_records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("exchange_event") == "request_fallback"
    ]
    assert len(request_bodies) == 3
    assert "response_format" in request_bodies[0]
    assert "response_format" not in request_bodies[1]
    assert "response_format" not in request_bodies[2]
    assert len(fallback_records) == 1
    assert retry_delays == [0.5]
    assert result["payload"]["results"][0]["unit_id"] == "retained-format"


def test_chat_json_resets_response_format_compatibility_for_separate_calls(monkeypatch) -> None:
    """
    @brief      Verify one invocation's compatibility state never changes a later invocation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[dict[str, object]] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate one compatibility rejection among separate provider calls.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  HTTPError Raised for the first incompatible request.
        """
        request_payload = json.loads(http_request.data.decode("utf-8"))
        request_bodies.append(request_payload)
        if len(request_bodies) == 1:
            raise error.HTTPError(
                http_request.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(b'{"error":{"message":"response_format is not supported"}}'),
            )
        return _FakeResponse(
            '{"choices":[{"message":{"content":"{\\"results\\":[{\\"unit_id\\":\\"reset\\"}]}"}}]}'
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)
    profile_payload = {
        "id": "profile_1",
        "backend_kind": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-5.4-mini",
        "request_timeout_seconds": 30,
        "temperature": 0.1,
        "max_output_tokens": 256,
        "supports_structured_output": True,
    }

    llm_provider_service.chat_json(profile_payload, "system", "first")
    llm_provider_service.chat_json(profile_payload, "system", "second")

    assert ["response_format" in body for body in request_bodies] == [True, False, True]


def test_chat_json_does_not_fallback_when_unconstrained_output_is_disabled(monkeypatch) -> None:
    """
    @brief      Verify policy-disabled response-format fallback stops after rejection.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[dict[str, object]] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Reject a structured-output request without a successful fallback.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     None.
        @exception  HTTPError Always raised for this policy test.
        """
        request_bodies.append(json.loads(http_request.data.decode("utf-8")))
        raise error.HTTPError(
            http_request.full_url,
            400,
            "Bad Request",
            hdrs=None,
            fp=io.BytesIO(b'{"error":{"message":"response_format is not supported"}}'),
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)

    with pytest.raises(
        RuntimeError,
        match="AI provider does not support required structured JSON output",
    ) as error_info:
        llm_provider_service.chat_json(
            {
                "id": "profile_1",
                "backend_kind": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-5.4-mini",
                "request_timeout_seconds": 30,
                "temperature": 0.1,
                "max_output_tokens": 256,
                "supports_structured_output": True,
            },
            "system",
            "user",
            allow_unconstrained_fallback=False,
            retry_count_override=3,
        )

    assert len(request_bodies) == 1
    assert type(error_info.value) is RuntimeError


def test_chat_json_can_cancel_while_waiting_for_model_response(monkeypatch) -> None:
    """
    @brief      Verify provider waits remain cooperatively cancellable before one response returns.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """

    def _slow_request(_profile_payload, _request_payload):
        """
        @brief      Provide the slow request test helper.
        @return     None.
        @exception  None
        """
        time.sleep(0.3)
        return (
            {"choices": [{"message": {"content": ('{"results":[{"unit_id":"unit-0001","label":"story"}]}')}}]},
            '{"choices":[{"message":{"content":"{\\"results\\":[{\\"unit_id\\":\\"unit-0001\\",\\"label\\":\\"story\\"}]}"}}]}',
        )

    started_at = time.monotonic()
    monkeypatch.setattr(
        llm_provider_service,
        "_request_chat_completion",
        _slow_request,
    )

    try:
        llm_provider_service.chat_json(
            {
                "id": "profile_1",
                "backend_kind": "lmstudio",
                "base_url": "http://127.0.0.1:1234",
                "model_name": "qwen3-8b",
                "request_timeout_seconds": 30,
                "temperature": 0.2,
                "max_output_tokens": 256,
            },
            "system",
            "user",
            cancel_requested=lambda: (time.monotonic() - started_at) >= 0.05,
        )
    except OperationCancelledError as error:
        assert str(error) == "AI operation cancelled while waiting for the model response."
    else:  # pragma: no cover - defensive assertion path.
        raise AssertionError("Expected AI request cancellation while waiting for the model response.")


def test_chat_json_retries_with_max_completion_tokens_when_required(
    monkeypatch,
) -> None:
    """
    @brief      Verify provider requests retry with max_completion_tokens after one compatibility failure.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[str] = []
    retry_delays: list[float] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate one max-token compatibility failure followed by success.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  HTTPError Raised on the first incompatible request.
        """
        body_text = http_request.data.decode("utf-8")
        request_bodies.append(body_text)
        if len(request_bodies) == 1:
            raise error.HTTPError(
                http_request.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(
                    b'{"error":{"message":"Unsupported parameter: '
                    b"'max_tokens' is not supported with this model. "
                    b"Use 'max_completion_tokens' instead.\","
                    b'"param":"max_tokens","code":"unsupported_parameter"}}'
                ),
            )
        return _FakeResponse(
            '{"choices":[{"message":{"content":"{\\"results\\":[{\\"unit_id\\":\\"unit-0001\\",\\"label\\":\\"story\\"}]}"}}]}'
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(
        llm_provider_service,
        "_wait_for_retry_backoff",
        lambda delay_seconds, _cancel_requested: retry_delays.append(delay_seconds),
        raising=False,
    )

    result = llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-5-mini",
            "request_timeout_seconds": 30,
            "temperature": 0.2,
            "max_output_tokens": 256,
        },
        "system",
        "user",
    )

    assert len(request_bodies) == 2
    assert '"max_tokens": 256' in request_bodies[0]
    assert '"max_completion_tokens": 256' in request_bodies[1]
    assert '"max_tokens": 256' not in request_bodies[1]
    assert retry_delays == []
    assert result["payload"]["results"][0]["unit_id"] == "unit-0001"


def test_chat_json_retains_max_completion_tokens_across_outer_retries(monkeypatch) -> None:
    """
    @brief      Verify learned max-token compatibility survives a transient failure.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[dict[str, object]] = []
    retry_delays: list[float] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate one token-field rejection followed by success.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  HTTPError Raised for the first incompatible request.
        """
        request_payload = json.loads(http_request.data.decode("utf-8"))
        request_bodies.append(request_payload)
        if len(request_bodies) == 1:
            raise error.HTTPError(
                http_request.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(
                    b'{"error":{"message":"Use max_completion_tokens instead",'
                    b'"param":"max_tokens","code":"unsupported_parameter"}}'
                ),
            )
        if len(request_bodies) == 2:
            raise error.HTTPError(
                http_request.full_url,
                503,
                "Unavailable",
                hdrs=None,
                fp=io.BytesIO(b'{"error":{"message":"temporarily unavailable"}}'),
            )
        return _FakeResponse(
            '{"choices":[{"message":{"content":"{\\"results\\":[{\\"unit_id\\":\\"retained-token\\"}]}"}}]}'
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(
        llm_provider_service,
        "_wait_for_retry_backoff",
        lambda delay_seconds, _cancel_requested: retry_delays.append(delay_seconds),
        raising=False,
    )

    result = llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-5-mini",
            "request_timeout_seconds": 30,
            "temperature": 0.2,
            "max_output_tokens": 256,
        },
        "system",
        "user",
        retry_count_override=1,
    )

    assert len(request_bodies) == 3
    assert "max_tokens" in request_bodies[0]
    assert "max_completion_tokens" not in request_bodies[0]
    assert "max_tokens" not in request_bodies[1]
    assert request_bodies[1]["max_completion_tokens"] == 256
    assert "max_tokens" not in request_bodies[2]
    assert request_bodies[2]["max_completion_tokens"] == 256
    assert retry_delays == [0.5]
    assert result["payload"]["results"][0]["unit_id"] == "retained-token"


def test_chat_json_retains_max_completion_tokens_for_json_repair(monkeypatch) -> None:
    """
    @brief      Verify a JSON repair request retains the learned provider token field.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[dict[str, object]] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate token-field negotiation followed by JSON repair.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake provider response for negotiation or repair.
        @exception  HTTPError Raised while the incompatible token field is present.
        """
        request_payload = json.loads(http_request.data.decode("utf-8"))
        request_bodies.append(request_payload)
        if "max_tokens" in request_payload:
            raise error.HTTPError(
                http_request.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(
                    b'{"error":{"message":"Use max_completion_tokens instead",'
                    b'"param":"max_tokens","code":"unsupported_parameter"}}'
                ),
            )
        if len(request_bodies) == 2:
            return _FakeResponse(json.dumps({"choices": [{"message": {"content": "not json"}}]}))
        return _FakeResponse(
            json.dumps({"choices": [{"message": {"content": '{"translated_text":"repaired"}'}}]})
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)

    result = llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-5-mini",
            "request_timeout_seconds": 30,
            "temperature": 0.2,
            "max_output_tokens": 256,
        },
        "system",
        "user",
    )

    assert len(request_bodies) == 3
    assert "max_tokens" in request_bodies[0]
    assert all("max_tokens" not in request_payload for request_payload in request_bodies[1:])
    assert all(request_payload["max_completion_tokens"] == 256 for request_payload in request_bodies[1:])
    assert result["payload"]["translated_text"] == "repaired"


def test_chat_json_repairs_invalid_backslash_escapes_in_model_output(
    monkeypatch,
) -> None:
    """
    @brief      Verify malformed backslash escapes inside model JSON are repaired locally.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    malformed_content = '{"translated_text":"Path C:\\Temp\\Books\\Dune"}'
    monkeypatch.setattr(
        llm_provider_service.request,
        "urlopen",
        lambda *_args, **_kwargs: _FakeResponse(json.dumps({"choices": [{"message": {"content": malformed_content}}]})),
    )

    result = llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-5.4-mini",
            "request_timeout_seconds": 30,
            "temperature": 0.1,
            "max_output_tokens": 256,
        },
        "system",
        "user",
    )

    assert result["payload"]["translated_text"] == "Path C:\\Temp\\Books\\Dune"


def test_chat_json_repairs_non_json_output_with_followup_request(
    monkeypatch,
) -> None:
    """
    @brief      Verify one malformed non-JSON response can be repaired through one follow-up request.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[str] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate malformed content followed by a repair response.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake provider response for initial or repair request.
        @exception  None
        """
        request_bodies.append(http_request.data.decode("utf-8"))
        if len(request_bodies) == 1:
            return _FakeResponse(
                json.dumps({"choices": [{"message": {"content": "Translated text: Hello from the model."}}]})
            )
        return _FakeResponse(
            json.dumps({"choices": [{"message": {"content": '{"translated_text":"Hello from the model."}'}}]})
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)

    result = llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-5.4-mini",
            "request_timeout_seconds": 30,
            "temperature": 0.1,
            "max_output_tokens": 256,
            "supports_structured_output": True,
        },
        "system",
        "user",
    )

    assert len(request_bodies) == 2
    assert json.loads(request_bodies[0])["response_format"] == {"type": "json_object"}
    assert "response_format" not in json.loads(request_bodies[1])
    assert "Repair the following malformed JSON" in request_bodies[1]
    assert result["payload"]["translated_text"] == "Hello from the model."


def test_chat_json_does_not_repair_empty_message_content(monkeypatch) -> None:
    """
    @brief      Verify empty assistant content fails without a JSON-repair follow-up request.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[str] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate a reasoning-only provider response with empty message content.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake empty-content provider response.
        @exception  None
        """
        request_bodies.append(http_request.data.decode("utf-8"))
        return _FakeResponse(
            json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "\n\n",
                                "reasoning_content": "The model thought about the answer but emitted no JSON content.",
                            }
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)

    try:
        llm_provider_service.chat_json(
            {
                "id": "profile_1",
                "backend_kind": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "model_name": "qwen3.6-35b-a3b",
                "request_timeout_seconds": 30,
                "temperature": 0.1,
                "max_output_tokens": 256,
                "supports_structured_output": True,
            },
            "system",
            "user",
        )
    except ValueError as error_object:
        assert str(error_object) == "AI provider returned an empty response."
        assert len(request_bodies) == 1
    else:  # pragma: no cover - defensive assertion path.
        raise AssertionError("Expected empty provider response to fail.")


@pytest.mark.parametrize(
    ("message_payload", "expected_error"),
    [
        (
            {"content": None, "refusal": "The provider safety policy refused this request."},
            "AI provider refused the request: The provider safety policy refused this request.",
        ),
        ({"content": None}, "AI provider returned an empty response."),
        (
            {
                "content": None,
                "reasoning_content": "Reasoning was produced without an assistant answer.",
            },
            "AI provider returned an empty response.",
        ),
        (
            {"content": [{"type": "text", "text": None}]},
            "AI provider returned an empty response.",
        ),
    ],
)
def test_chat_json_rejects_null_or_refused_content_without_repair(
    monkeypatch,
    tmp_path,
    message_payload,
    expected_error,
) -> None:
    """
    @brief      Verify null, reasoning-only, and refused content fails after one request.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  message_payload Provider message payload under test.
    @param[in]  expected_error Expected safe failure message.
    @return     None.
    @exception  None
    """
    request_bodies: list[str] = []
    secret_value = "sk-private-null-content-secret"

    def _fake_urlopen(http_request, **_kwargs):
        request_bodies.append(http_request.data.decode("utf-8"))
        return _FakeResponse(json.dumps({"choices": [{"message": message_payload}]}))

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)
    log_path = tmp_path / "transactions.log"

    with pytest.raises(ValueError) as error_info:
        llm_provider_service.chat_json(
            {
                "id": "profile_1",
                "backend_kind": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "api_key": secret_value,
                "model_name": "qwen3.6-35b-a3b",
                "request_timeout_seconds": 30,
                "temperature": 0.1,
                "max_output_tokens": 256,
                "supports_structured_output": True,
            },
            "system",
            "user",
            log_path=log_path,
        )

    assert str(error_info.value) == expected_error
    assert len(request_bodies) == 1
    assert secret_value not in log_path.read_text(encoding="utf-8")


def test_chat_json_joins_multipart_content_with_null_text_parts(monkeypatch) -> None:
    """
    @brief      Verify null multipart text is empty while valid text remains unchanged.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[str] = []

    def _fake_urlopen(http_request, **_kwargs):
        request_bodies.append(http_request.data.decode("utf-8"))
        return _FakeResponse(
            json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {"type": "text", "text": None},
                                    {"type": "text", "text": '{"results":[{"unit_id":"multipart"}]}'},
                                    {"type": "text", "text": None},
                                ]
                            }
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)

    result = llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model_name": "qwen3.6-35b-a3b",
            "request_timeout_seconds": 30,
            "temperature": 0.1,
            "max_output_tokens": 256,
            "supports_structured_output": True,
        },
        "system",
        "user",
    )

    assert len(request_bodies) == 1
    assert result["payload"]["results"][0]["unit_id"] == "multipart"


def test_chat_json_rejects_output_length_limited_malformed_json(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify output-length termination fails before malformed JSON repair.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[str] = []
    truncated_content = '{"results":[{"unit_id":"partial"'

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Return one explicitly output-length-limited malformed response.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake provider response.
        @exception  None
        """
        request_bodies.append(http_request.data.decode("utf-8"))
        return _FakeResponse(
            json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": truncated_content},
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)
    log_path = tmp_path / "transactions.log"

    try:
        llm_provider_service.chat_json(
            {
                "id": "profile_1",
                "backend_kind": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-5.4-mini",
                "request_timeout_seconds": 30,
                "temperature": 0.1,
                "max_output_tokens": 256,
            },
            "system",
            "user",
            log_path=log_path,
        )
    except RuntimeError as error_object:
        error_text = str(error_object)
        assert "output-token limit" in error_text
        assert "256" in error_text
        assert truncated_content not in error_text
    else:  # pragma: no cover - defensive assertion path.
        raise AssertionError("Expected output-length-limited response to fail.")

    transaction_records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(request_bodies) == 1
    assert any(record.get("parsed_status") == "parsed_failure" for record in transaction_records)
    assert not any(
        record.get("parsed_status") == "parsed_success_after_repair"
        for record in transaction_records
    )


def test_chat_json_rejects_output_length_limited_valid_json(monkeypatch) -> None:
    """
    @brief      Verify output-length termination rejects otherwise valid JSON content.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    request_bodies: list[str] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Return one explicitly output-length-limited valid JSON response.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake provider response.
        @exception  None
        """
        request_bodies.append(http_request.data.decode("utf-8"))
        return _FakeResponse(
            json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": '{"results":[]}'},
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)

    try:
        llm_provider_service.chat_json(
            {
                "id": "profile_1",
                "backend_kind": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-5.4-mini",
                "request_timeout_seconds": 30,
                "temperature": 0.1,
                "max_output_tokens": 256,
            },
            "system",
            "user",
        )
    except RuntimeError as error_object:
        assert str(error_object) == (
            "AI provider response reached the provider output-token limit of 256 tokens."
        )
    else:  # pragma: no cover - defensive assertion path.
        raise AssertionError("Expected output-length-limited response to fail.")

    assert len(request_bodies) == 1


def test_chat_json_accepts_stop_and_omitted_finish_reasons(monkeypatch) -> None:
    """
    @brief      Verify normal and legacy provider finish reasons retain JSON parsing.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    response_payloads = [
        json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"results":[{"unit_id":"stopped"}]}'},
                    }
                ]
            }
        ),
        json.dumps(
            {
                "choices": [
                    {
                        "message": {"content": '{"results":[{"unit_id":"legacy"}]}'},
                    }
                ]
            }
        ),
    ]

    monkeypatch.setattr(
        llm_provider_service.request,
        "urlopen",
        lambda *_args, **_kwargs: _FakeResponse(response_payloads.pop(0)),
    )

    profile_payload = {
        "id": "profile_1",
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234",
        "model_name": "qwen3-8b",
        "request_timeout_seconds": 30,
        "temperature": 0.2,
        "max_output_tokens": 256,
    }
    stopped_result = llm_provider_service.chat_json(profile_payload, "system", "user")
    legacy_result = llm_provider_service.chat_json(profile_payload, "system", "user")

    assert stopped_result["payload"]["results"][0]["unit_id"] == "stopped"
    assert legacy_result["payload"]["results"][0]["unit_id"] == "legacy"


def test_chat_json_normalizes_provider_usage(monkeypatch) -> None:
    """
    @brief      Verify provider usage fields are normalized into the shared token payload.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    monkeypatch.setattr(
        llm_provider_service.request,
        "urlopen",
        lambda *_args, **_kwargs: _FakeResponse(
            json.dumps(
                {
                    "choices": [{"message": {"content": '{"results":[{"unit_id":"unit-0001"}]}'}}],
                    "usage": {
                        "prompt_tokens": 123,
                        "completion_tokens": 45,
                        "total_tokens": 168,
                    },
                }
            )
        ),
    )

    result = llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-5.4-mini",
            "request_timeout_seconds": 30,
            "temperature": 0.1,
            "max_output_tokens": 256,
        },
        "system",
        "user",
    )

    assert result["usage"] == {
        "input_tokens": 123,
        "output_tokens": 45,
        "total_tokens": 168,
        "usage_available": True,
    }


def test_chat_json_logs_raw_message_content_on_parse_failure(
    monkeypatch,
    tmp_path,
) -> None:
    """
    @brief      Verify parse failures persist the raw assistant content in the transaction log.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    response_counter = {"count": 0}

    def _fake_urlopen(*_args, **_kwargs):
        """
        @brief      Simulate provider responses that remain invalid JSON.
        @param[in]  _args Ignored positional request arguments.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake invalid provider response.
        @exception  None
        """
        response_counter["count"] += 1
        if response_counter["count"] == 1:
            return _FakeResponse(json.dumps({"choices": [{"message": {"content": "not valid json"}}]}))
        return _FakeResponse(json.dumps({"choices": [{"message": {"content": "still not valid json"}}]}))

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)

    try:
        llm_provider_service.chat_json(
            {
                "id": "profile_1",
                "backend_kind": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-5.4-mini",
                "request_timeout_seconds": 30,
                "temperature": 0.1,
                "max_output_tokens": 256,
            },
            "system",
            "user",
            log_path=tmp_path / "transactions.log",
        )
    except ValueError:
        log_text = (tmp_path / "transactions.log").read_text(encoding="utf-8")
        assert "not valid json" in log_text
        assert "raw_message_content" in log_text
    else:  # pragma: no cover - defensive assertion path.
        raise AssertionError("Expected JSON parse failure to be raised.")


def test_chat_json_redacts_sensitive_values_from_transaction_log(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify sensitive transaction-log context fields are redacted before persistence.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    secret_value = "redaction-test-api-key"
    authorization_value = "Bearer redaction-test-token"
    monkeypatch.setattr(
        llm_provider_service.request,
        "urlopen",
        lambda *_args, **_kwargs: _FakeResponse(
            json.dumps({"choices": [{"message": {"content": '{"results":[{"unit_id":"unit-0001"}]}'}}]})
        ),
    )
    log_path = tmp_path / "transactions.log"

    llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-5.4-mini",
            "api_key": secret_value,
            "request_timeout_seconds": 30,
            "temperature": 0.1,
            "max_output_tokens": 256,
        },
        "system",
        "user",
        log_path=log_path,
        log_context={
            "api_key": secret_value,
            "headers": {"Authorization": authorization_value},
            "nested": [{"access_token": secret_value}],
        },
    )

    log_text = log_path.read_text(encoding="utf-8")
    log_entries = [json.loads(line) for line in log_text.splitlines()]

    assert secret_value not in log_text
    assert authorization_value not in log_text
    assert all(entry["api_key"] == "[REDACTED]" for entry in log_entries)
    assert all(entry["headers"]["Authorization"] == "[REDACTED]" for entry in log_entries)
    assert all(entry["nested"][0]["access_token"] == "[REDACTED]" for entry in log_entries)


def test_chat_json_does_not_retry_permanent_http_failure(monkeypatch) -> None:
    """
    @brief      Verify permanent provider HTTP failures are surfaced without retry loops.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    call_counter = {"count": 0}
    retry_delays: list[float] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate a permanent unauthorized provider failure.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     None.
        @exception  HTTPError Always raised with a 401 status.
        """
        call_counter["count"] += 1
        raise error.HTTPError(
            http_request.full_url,
            401,
            "Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"error":{"message":"invalid api key"}}'),
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(
        llm_provider_service,
        "_wait_for_retry_backoff",
        lambda delay_seconds, _cancel_requested: retry_delays.append(delay_seconds),
        raising=False,
    )

    try:
        llm_provider_service.chat_json(
            {
                "id": "profile_1",
                "backend_kind": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-5.4-mini",
                "request_timeout_seconds": 30,
                "temperature": 0.1,
                "max_output_tokens": 256,
            },
            "system",
            "user",
        )
    except RuntimeError as error_object:
        assert "HTTP 401" in str(error_object)
    else:  # pragma: no cover - defensive assertion path.
        raise AssertionError("Expected permanent HTTP failure to be raised.")

    assert call_counter["count"] == 1
    assert retry_delays == []


def test_build_chat_endpoint_keeps_complete_chat_completions_endpoint() -> None:
    """
    @brief      Verify complete chat-completions endpoints are not duplicated during normalization.
    @return     None.
    @exception  None
    """
    assert (
        llm_provider_service._build_chat_endpoint("https://api.example.com/v1/chat/completions")  # noqa: SLF001
        == "https://api.example.com/v1/chat/completions"
    )


@pytest.mark.parametrize(
    ("base_url", "expected_url"),
    [
        ("https://api.example.com", "https://api.example.com/v1/chat/completions"),
        ("https://api.example.com/", "https://api.example.com/v1/chat/completions"),
        ("https://api.example.com/v1", "https://api.example.com/v1/chat/completions"),
        ("https://api.example.com/v1/", "https://api.example.com/v1/chat/completions"),
        ("https://api.example.com/proxy", "https://api.example.com/proxy/v1/chat/completions"),
        (
            "https://gateway.example.com/proxy/?api-version=2026-08-09",
            "https://gateway.example.com/proxy/v1/chat/completions?api-version=2026-08-09",
        ),
        (
            "https://gateway.example.com/proxy?api-version=2026-08-09#route",
            "https://gateway.example.com/proxy/v1/chat/completions?api-version=2026-08-09#route",
        ),
    ],
)
def test_build_chat_endpoint_uses_shared_versioned_derivation(base_url, expected_url) -> None:
    """
    @brief      Verify chat endpoint derivation preserves one shared versioned URL policy.
    @param[in]  base_url Candidate provider base URL.
    @param[in]  expected_url Expected chat-completions endpoint.
    @return     None.
    @exception  None
    """
    assert llm_provider_service._build_chat_endpoint(base_url) == expected_url  # noqa: SLF001


def test_chat_json_requests_the_shared_versioned_endpoint(monkeypatch) -> None:
    """
    @brief      Verify generation sends its request to the shared query-preserving endpoint.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    observed_urls: list[str] = []

    def _fake_urlopen(http_request, timeout):
        """
        @brief      Capture the generated request URL and return one valid chat response.
        @return     Fake successful provider response.
        @exception  None
        """
        observed_urls.append(http_request.full_url)
        assert timeout == 30
        return _FakeResponse('{"choices":[{"message":{"content":"{\\"result\\":\\"ok\\"}"}}]}')

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)

    llm_provider_service.chat_json(
        {
            "id": "profile_1",
            "backend_kind": "openai_compatible",
            "base_url": "https://gateway.example.com/proxy?api-version=2026-08-09",
            "model_name": "model-a",
            "request_timeout_seconds": 30,
            "temperature": 0.2,
            "max_output_tokens": 256,
        },
        "system",
        "user",
    )

    assert observed_urls == [
        "https://gateway.example.com/proxy/v1/chat/completions?api-version=2026-08-09"
    ]


def test_retry_classification_uses_exception_type_not_message_text() -> None:
    """
    @brief      Verify permanent errors cannot opt into retries through provider wording.
    @return     None.
    @exception  None
    """
    assert llm_provider_service._is_retryable_error(  # noqa: SLF001
        RuntimeError("Permanent HTTP 400: service temporarily unavailable")
    ) is False
    assert llm_provider_service._is_retryable_error(TimeoutError("socket read failed")) is True  # noqa: SLF001


def test_strip_code_fence_preserves_single_line_json() -> None:
    """
    @brief      Verify compact fenced provider responses retain their JSON payload.
    @return     None.
    @exception  None
    """
    assert llm_provider_service._strip_code_fence('```json {"value": 1} ```') == '{"value": 1}'  # noqa: SLF001


def test_failed_exchange_records_the_response_body_and_usage(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify a failure record keeps the provider response it failed on.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    response_body = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"content": ""},
                }
            ],
            "usage": {
                "prompt_tokens": 900,
                "completion_tokens": 256,
                "total_tokens": 1156,
            },
        }
    )

    def _fake_urlopen(_http_request, **_kwargs):
        """
        @brief      Return one output-length-limited response carrying usage.
        @param[in]  _http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake provider response.
        @exception  None
        """
        return _FakeResponse(response_body)

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)
    log_path = tmp_path / "transactions.log"

    with pytest.raises(RuntimeError):
        llm_provider_service.chat_json(
            _length_limited_profile(),
            "system",
            "user",
            log_path=log_path,
        )

    failure_record = _one_failure_record(log_path)
    assert failure_record["raw_response_body"] == response_body
    assert failure_record["usage"]["output_tokens"] == 256


def test_transport_failure_record_omits_the_response_fields(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify a failure with no provider response records no response fields.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """

    def _fake_urlopen(_http_request, **_kwargs):
        """
        @brief      Fail every attempt before any provider response exists.
        @param[in]  _http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     None.
        @exception  URLError Raised on every request attempt.
        """
        raise error.URLError("no route to provider")

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)
    log_path = tmp_path / "transactions.log"

    with pytest.raises(RuntimeError):
        llm_provider_service.chat_json(
            _length_limited_profile(),
            "system",
            "user",
            log_path=log_path,
            retry_count_override=0,
        )

    failure_record = _one_failure_record(log_path)
    assert "raw_response_body" not in failure_record
    assert "usage" not in failure_record


def _length_limited_profile() -> dict[str, object]:
    """Return one profile whose output limit is small enough to name in errors."""
    return {
        "id": "profile_1",
        "backend_kind": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-5.4-mini",
        "request_timeout_seconds": 30,
        "temperature": 0.1,
        "max_output_tokens": 256,
    }


def _one_failure_record(log_path) -> dict[str, object]:
    """
    @brief      Return the single failure record written to one transaction log.
    @param[in]  log_path Transaction log path.
    @return     Single parsed failure record.
    @exception  AssertionError Raised when the expected single failure is absent.
    """
    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    failures = [record for record in records if record.get("exchange_event") == "failure"]
    assert len(failures) == 1
    return failures[0]


# END OF FILE
