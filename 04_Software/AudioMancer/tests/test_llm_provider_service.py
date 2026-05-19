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
@author Eng. Dan Dumitru Pasare
@date 2026-04-22
@version 0.8.2
"""

# IMPORTS

import io
import json
import time
from urllib import error

from audiomancer.services import llm_provider_service
from audiomancer.services.operation_runtime_service import OperationCancelledError


class _FakeResponse:
    """
    @brief Minimal context-manager response used by provider HTTP tests.
    @details Stores one response body and exposes the subset of the urllib
             response contract needed by the LLM provider service.
    @author Eng. Dan Dumitru Pasare
    @date 2026-04-29
    @version 0.1.0
    """

    def __init__(self, body: str) -> None:
        """
        @brief      Provide the init test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        self._body = body

    def __enter__(self):
        """
        @brief      Provide the enter test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """
        @brief      Provide the exit test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        _ = exc_type
        _ = exc
        _ = tb

    def read(self) -> bytes:
        """
        @brief      Return the configured fake response body as UTF-8 bytes.
        @return     Encoded fake response body.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
        """
        return self._body.encode("utf-8")


def test_chat_json_parses_fenced_json(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify fenced JSON model output is normalized into one JSON object.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    call_counter = {"count": 0}

    def _fake_urlopen(*_args, **_kwargs):
        """
        @brief      Simulate one transient provider failure followed by success.
        @param[in]  _args Ignored positional request arguments.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  URLError Raised on the first request attempt.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
        """
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            raise error.URLError("temporary failure")
        return _FakeResponse(
            '{"choices":[{"message":{"content":"{\\"results\\":[{\\"unit_id\\":\\"unit-0001\\",\\"label\\":\\"story\\"}]}"}}]}'
        )

    monkeypatch.setattr(llm_provider_service.request, "urlopen", _fake_urlopen)

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
    assert result["payload"]["results"][0]["unit_id"] == "unit-0001"


def test_chat_json_sends_response_format_when_structured_output_is_supported(monkeypatch) -> None:
    """
    @brief      Verify structured-output-capable profiles request JSON-object response format.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    request_bodies: list[dict[str, object]] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Capture one structured-output provider request.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-08
        @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-10
    @version    0.1.0
    """
    request_bodies: list[dict[str, object]] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Capture one local-backend structured-output provider request.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-10
        @version    0.1.0
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


def test_chat_json_omits_response_format_when_structured_output_is_not_supported(monkeypatch) -> None:
    """
    @brief      Verify profiles without structured-output support keep prompt-only JSON behavior.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    request_bodies: list[dict[str, object]] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Capture one prompt-only provider request.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-08
        @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    request_bodies: list[dict[str, object]] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate one response_format compatibility failure followed by success.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  HTTPError Raised on the first incompatible request.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-08
        @version    0.1.0
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
    assert result["payload"]["results"][0]["unit_id"] == "unit-0001"


def test_chat_json_can_cancel_while_waiting_for_model_response(monkeypatch) -> None:
    """
    @brief      Verify provider waits remain cooperatively cancellable before one response returns.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """

    def _slow_request(_profile_payload, _request_payload):
        """
        @brief      Provide the slow request test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
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
        assert "waiting for the model response" in str(error)
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    request_bodies: list[str] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate one max-token compatibility failure followed by success.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake successful provider response.
        @exception  HTTPError Raised on the first incompatible request.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
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
    assert result["payload"]["results"][0]["unit_id"] == "unit-0001"


def test_chat_json_repairs_invalid_backslash_escapes_in_model_output(
    monkeypatch,
) -> None:
    """
    @brief      Verify malformed backslash escapes inside model JSON are repaired locally.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    request_bodies: list[str] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate malformed content followed by a repair response.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake provider response for initial or repair request.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-19
    @version    0.1.0
    """
    request_bodies: list[str] = []

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate a reasoning-only provider response with empty message content.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake empty-content provider response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-19
        @version    0.1.0
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


def test_chat_json_normalizes_provider_usage(monkeypatch) -> None:
    """
    @brief      Verify provider usage fields are normalized into the shared token payload.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    response_counter = {"count": 0}

    def _fake_urlopen(*_args, **_kwargs):
        """
        @brief      Simulate provider responses that remain invalid JSON.
        @param[in]  _args Ignored positional request arguments.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake invalid provider response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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
            "nested": [{"runtime_api_key": secret_value}],
        },
    )

    log_text = log_path.read_text(encoding="utf-8")
    log_entries = [json.loads(line) for line in log_text.splitlines()]

    assert secret_value not in log_text
    assert authorization_value not in log_text
    assert all(entry["api_key"] == "[REDACTED]" for entry in log_entries)
    assert all(entry["headers"]["Authorization"] == "[REDACTED]" for entry in log_entries)
    assert all(entry["nested"][0]["runtime_api_key"] == "[REDACTED]" for entry in log_entries)


def test_chat_json_does_not_retry_permanent_http_failure(monkeypatch) -> None:
    """
    @brief      Verify permanent provider HTTP failures are surfaced without retry loops.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    call_counter = {"count": 0}

    def _fake_urlopen(http_request, **_kwargs):
        """
        @brief      Simulate a permanent unauthorized provider failure.
        @param[in]  http_request Provider HTTP request.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     None.
        @exception  HTTPError Always raised with a 401 status.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
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


def test_build_chat_endpoint_keeps_complete_chat_completions_endpoint() -> None:
    """
    @brief      Verify complete chat-completions endpoints are not duplicated during normalization.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    assert (
        llm_provider_service._build_chat_endpoint("https://api.example.com/v1/chat/completions")  # noqa: SLF001
        == "https://api.example.com/v1/chat/completions"
    )


# END OF FILE
