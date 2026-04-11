#!/usr/bin/env python3
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
@date 2026-04-11
@version 0.5.0
"""

# IMPORTS

import io
import json
import time
from urllib import error

from audiomancer.services import llm_provider_service
from audiomancer.services.operation_runtime_service import OperationCancelledError


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type
        _ = exc
        _ = tb

    def read(self) -> bytes:
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
        },
        "system",
        "user",
    )

    assert len(request_bodies) == 2
    assert "Repair the following malformed JSON" in request_bodies[1]
    assert result["payload"]["translated_text"] == "Hello from the model."


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


# END OF FILE
