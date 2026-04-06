#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
@date 2026-04-06
@version 0.2.0
"""

# IMPORTS

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

    payload = llm_provider_service.chat_json(
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

    assert payload["results"][0]["label"] == "story"


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

    payload = llm_provider_service.chat_json(
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
    assert payload["results"][0]["unit_id"] == "unit-0001"


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
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"results":[{"unit_id":"unit-0001","label":"story"}]}'
                            )
                        }
                    }
                ]
            },
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


# END OF FILE
