#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_backend_service.py
@brief Focused tests for the AI backend probe service.
@details Verifies backend probe success/failure normalization for the current
         AI Settings connectivity flow.
"""

# IMPORTS

from http.client import IncompleteRead
import json
from urllib import error

import pytest

from audiomancer import config
from audiomancer.services import ai_backend_service


class _FakeResponse:
    """
    @brief      Minimal context-managed HTTP response used by transport tests.
    """

    def __init__(self, payload: bytes = b"", read_error: BaseException | None = None) -> None:
        """
        @brief      Store response bytes or one error to raise during `read()`.
        @param[in]  payload Bytes returned by `read()`.
        @param[in]  read_error Optional exception raised by `read()`.
        @return     None.
        @exception  None
        """
        self._payload = payload
        self._read_error = read_error

    def __enter__(self):
        """@brief Return this fake response to the context manager."""
        return self

    def __exit__(self, exception_type, exception, traceback) -> bool:
        """@brief Leave the response context without suppressing exceptions."""
        return False

    def read(self) -> bytes:
        """
        @brief      Return response bytes or raise the configured read-phase error.
        @return     Configured payload bytes.
        @exception  BaseException When a read error was configured.
        """
        if self._read_error is not None:
            raise self._read_error
        return self._payload


def test_probe_profile_normalizes_openai_compatible_models(monkeypatch) -> None:
    """
    @brief      Verify OpenAI-compatible model lists are normalized correctly.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """

    def _fake_read_json(url, headers, timeout_seconds, **_kwargs):
        """
        @brief      Return a fake OpenAI-compatible model-list payload.
        @param[in]  url Requested endpoint URL.
        @param[in]  headers Ignored request headers.
        @param[in]  timeout_seconds Requested timeout.
        @return     Fake JSON payload.
        @exception  None
        """
        assert url == "http://127.0.0.1:1234/v1/models"
        assert timeout_seconds == config.DEFAULT_AI_CONNECT_TIMEOUT_SECONDS
        return {"data": [{"id": "qwen3-8b"}, {"id": "llama-3.1-8b"}]}

    monkeypatch.setattr(ai_backend_service, "_read_json", _fake_read_json)

    result = ai_backend_service.probe_profile(
        {
            "backend_kind": "openai_compatible",
            "base_url": "http://127.0.0.1:1234/v1",
            "api_key": "",
            "model_name": "qwen3-8b",
            "request_timeout_seconds": 30,
        }
    )

    assert result["success"] is True
    assert result["discovered_model_count"] == 2
    assert result["selected_model_valid"] is True
    assert [model["id"] for model in result["discovered_models"]] == [
        "qwen3-8b",
        "llama-3.1-8b",
    ]


@pytest.mark.parametrize(
    ("base_url", "expected_url"),
    [
        ("https://api.example.com", "https://api.example.com/v1/models"),
        ("https://api.example.com/", "https://api.example.com/v1/models"),
        ("https://api.example.com/v1", "https://api.example.com/v1/models"),
        ("https://api.example.com/v1/", "https://api.example.com/v1/models"),
        ("https://api.example.com/proxy", "https://api.example.com/proxy/v1/models"),
        (
            "https://gateway.example.com/proxy/?api-version=2026-08-09",
            "https://gateway.example.com/proxy/v1/models?api-version=2026-08-09",
        ),
        (
            "https://gateway.example.com/proxy?api-version=2026-08-09#route",
            "https://gateway.example.com/proxy/v1/models?api-version=2026-08-09#route",
        ),
    ],
)
def test_openai_compatible_model_probe_uses_shared_versioned_derivation(
    monkeypatch,
    base_url,
    expected_url,
) -> None:
    """
    @brief      Verify Test Connection derives model endpoints with the shared URL policy.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  base_url Candidate provider base URL.
    @param[in]  expected_url Expected models endpoint.
    @return     None.
    @exception  None
    """
    observed_urls: list[str] = []

    def _fake_read_json(url, headers, timeout_seconds, **_kwargs):
        """
        @brief      Capture one derived model-probe URL and return a valid model list.
        @return     Minimal OpenAI-compatible model-list payload.
        @exception  None
        """
        observed_urls.append(url)
        assert headers == {"Accept": "application/json"}
        assert timeout_seconds == 17
        return {"data": [{"id": "model-a"}]}

    monkeypatch.setattr(ai_backend_service, "_read_json", _fake_read_json)

    discovered_models = ai_backend_service._probe_openai_compatible_models(  # noqa: SLF001
        {"base_url": base_url, "api_key": ""},
        17,
    )

    assert observed_urls == [expected_url]
    assert discovered_models == [{"id": "model-a", "label": "model-a"}]


def test_probe_profile_normalizes_ollama_models(monkeypatch) -> None:
    """
    @brief      Verify Ollama model lists are normalized correctly.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """

    def _fake_read_json(url, headers, timeout_seconds, **_kwargs):
        """
        @brief      Return a fake Ollama tags payload.
        @param[in]  url Requested endpoint URL.
        @param[in]  headers Ignored request headers.
        @param[in]  timeout_seconds Requested timeout.
        @return     Fake JSON payload.
        @exception  None
        """
        assert url == "http://localhost:11434/api/tags"
        return {"models": [{"name": "qwen3:8b"}, {"name": "llama3.1:8b"}]}

    monkeypatch.setattr(ai_backend_service, "_read_json", _fake_read_json)

    result = ai_backend_service.probe_profile(
        {
            "backend_kind": "ollama",
            "base_url": "http://localhost:11434/v1",
            "api_key": "",
            "model_name": "missing",
            "user_overrode_model_name": True,
            "request_timeout_seconds": 20,
        }
    )

    assert result["success"] is True
    assert result["discovered_model_count"] == 2
    assert result["selected_model_valid"] is False


def test_probe_profile_maps_backend_failures(monkeypatch) -> None:
    """
    @brief      Verify provider probe failures are surfaced as failed results.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """

    def _fake_probe(*args, **kwargs):
        """
        @brief      Raise one fake backend connectivity failure.
        @param[in]  args Ignored positional arguments.
        @param[in]  kwargs Ignored keyword arguments.
        @return     None.
        @exception  urllib.error.URLError Always raised for the fake probe.
        """
        raise error.URLError("connection refused")

    monkeypatch.setattr(
        ai_backend_service,
        "_probe_openai_compatible_models",
        _fake_probe,
    )

    result = ai_backend_service.probe_profile(
        {
            "backend_kind": "openai_compatible",
            "base_url": "http://127.0.0.1:8000/v1",
            "api_key": "secret",
            "model_name": "qwen3-8b",
            "request_timeout_seconds": 15,
        }
    )

    assert result["success"] is False
    assert result["discovered_model_count"] == 0
    assert str(result["message"]).startswith("Connection failed:")
    assert "secret" not in str(result["message"])


def test_probe_profile_discovers_generic_inline_context_for_exact_model(monkeypatch) -> None:
    """
    @brief      Verify generic inline context metadata belongs to the exact selected model.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """

    def _fake_read_json(url, headers, timeout_seconds, **_kwargs):
        assert url == "https://provider.test/v1/models"
        return {
            "data": [
                {"id": "model-a", "context_length": 32768},
                {"id": "model-b", "max_context_length": 131072},
            ]
        }

    monkeypatch.setattr(ai_backend_service, "_read_json", _fake_read_json)
    result = ai_backend_service.probe_profile(
        {
            "backend_kind": "openai_compatible",
            "base_url": "https://provider.test/v1",
            "model_name": "model-a",
        }
    )

    assert result["success"] is True
    assert result["discovered_context_window"] == 32768
    assert result["discovered_context_model_name"] == "model-a"


def test_probe_profile_discovers_lm_studio_loaded_instance_context(monkeypatch) -> None:
    """
    @brief      Verify LM Studio prefers the matching loaded runtime context.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """

    def _fake_read_json(url, headers, timeout_seconds, **_kwargs):
        if url == "http://127.0.0.1:1234/v1/models":
            return {"data": [{"id": "publisher/model-a"}]}
        assert url == "http://127.0.0.1:1234/api/v1/models"
        return {
            "models": [
                {
                    "key": "publisher/model-a",
                    "max_context_length": 131072,
                    "loaded_instances": [
                        {"id": "publisher/model-a", "config": {"context_length": 24576}}
                    ],
                }
            ]
        }

    monkeypatch.setattr(ai_backend_service, "_read_json", _fake_read_json)
    result = ai_backend_service.probe_profile(
        {
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234/v1",
            "model_name": "publisher/model-a",
        }
    )

    assert result["discovered_context_window"] == 24576
    assert result["discovered_context_model_name"] == "publisher/model-a"


def test_probe_profile_uses_lm_studio_model_context_limit_without_loaded_match(monkeypatch) -> None:
    """
    @brief      Verify LM Studio falls back to the matched model's supported context limit.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """

    def _fake_read_json(url, headers, timeout_seconds, **_kwargs):
        if url == "http://127.0.0.1:1234/v1/models":
            return {"data": [{"id": "publisher/model-a"}]}
        return {
            "models": [
                {
                    "key": "publisher/model-a",
                    "max_context_length": 65536,
                    "loaded_instances": [{"id": "other-instance", "config": {"context_length": 4096}}],
                }
            ]
        }

    monkeypatch.setattr(ai_backend_service, "_read_json", _fake_read_json)
    result = ai_backend_service.probe_profile(
        {
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234/v1",
            "model_name": "publisher/model-a",
        }
    )

    assert result["discovered_context_window"] == 65536
    assert result["discovered_context_model_name"] == "publisher/model-a"


def test_lm_studio_optional_metadata_failure_preserves_model_success(monkeypatch) -> None:
    """
    @brief      Verify optional LM Studio metadata failure does not erase model discovery.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """

    def _fake_read_json(url, headers, timeout_seconds, **_kwargs):
        if url == "http://127.0.0.1:1234/v1/models":
            return {"data": [{"id": "model-a"}]}
        raise ConnectionResetError("native metadata reset")

    monkeypatch.setattr(ai_backend_service, "_read_json", _fake_read_json)
    result = ai_backend_service.probe_profile(
        {
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234/v1",
            "model_name": "model-a",
        }
    )

    assert result["success"] is True
    assert result["discovered_model_count"] == 1
    assert result["discovered_context_window"] is None
    assert result["discovered_context_model_name"] is None


def test_probe_profile_posts_exact_ollama_model_for_context(monkeypatch) -> None:
    """
    @brief      Verify Ollama context discovery uses the exact selected model in `/api/show`.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    observed_requests = []
    responses = iter(
        [
            _FakeResponse(json.dumps({"models": [{"name": "gemma4:latest"}]}).encode("utf-8")),
            _FakeResponse(
                json.dumps(
                    {
                        "model_info": {
                            "gemma4.attention.head_count": 8,
                            "gemma4.context_length": 131072,
                        }
                    }
                ).encode("utf-8")
            ),
        ]
    )

    def _fake_urlopen(http_request, timeout):
        observed_requests.append(http_request)
        return next(responses)

    monkeypatch.setattr(ai_backend_service.request, "urlopen", _fake_urlopen)
    result = ai_backend_service.probe_profile(
        {
            "backend_kind": "ollama",
            "base_url": "http://localhost:11434/v1",
            "model_name": "gemma4:latest",
        }
    )

    assert [request_object.full_url for request_object in observed_requests] == [
        "http://localhost:11434/api/tags",
        "http://localhost:11434/api/show",
    ]
    assert [request_object.get_method() for request_object in observed_requests] == ["GET", "POST"]
    assert json.loads(observed_requests[1].data.decode("utf-8")) == {"model": "gemma4:latest"}
    assert result["discovered_context_window"] == 131072
    assert result["discovered_context_model_name"] == "gemma4:latest"


@pytest.mark.parametrize("context_value", [None, True, "large", 0, -1, 1_000_001])
def test_probe_profile_ignores_invalid_context_metadata(monkeypatch, context_value) -> None:
    """
    @brief      Verify malformed, non-positive, and out-of-range context values are ignored.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  context_value Invalid provider value under test.
    @return     None.
    @exception  None
    """

    def _fake_read_json(url, headers, timeout_seconds, **_kwargs):
        return {"data": [{"id": "model-a", "context_length": context_value}]}

    monkeypatch.setattr(ai_backend_service, "_read_json", _fake_read_json)
    result = ai_backend_service.probe_profile(
        {
            "backend_kind": "openai_compatible",
            "base_url": "https://provider.test/v1",
            "model_name": "model-a",
        }
    )

    assert result["success"] is True
    assert result["discovered_context_window"] is None
    assert result["discovered_context_model_name"] is None


def test_probe_profile_does_not_claim_context_for_a_different_model(monkeypatch) -> None:
    """
    @brief      Verify context metadata for another model is never associated with the selection.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """

    def _fake_read_json(url, headers, timeout_seconds, **_kwargs):
        return {
            "data": [
                {"id": "model-a"},
                {"id": "model-b", "context_length": 65536},
            ]
        }

    monkeypatch.setattr(ai_backend_service, "_read_json", _fake_read_json)
    result = ai_backend_service.probe_profile(
        {
            "backend_kind": "openai_compatible",
            "base_url": "https://provider.test/v1",
            "model_name": "model-a",
        }
    )

    assert result["success"] is True
    assert result["discovered_context_window"] is None
    assert result["discovered_context_model_name"] is None


@pytest.mark.parametrize(
    ("payload", "read_error"),
    [
        (b"", ConnectionResetError("secret-reset-detail")),
        (b"", IncompleteRead(b"raw-secret-body")),
        (b"", TimeoutError("secret-timeout-detail")),
        (b"\xff", None),
        (b"not-json-secret-body", None),
    ],
    ids=("connection-reset", "incomplete-read", "timeout", "invalid-utf8", "invalid-json"),
)
def test_probe_profile_contains_read_phase_and_decode_failures(
    monkeypatch,
    payload: bytes,
    read_error: BaseException | None,
) -> None:
    """
    @brief      Verify read-phase transport and response decoding errors become safe failures.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  payload Response bytes used when no read error is configured.
    @param[in]  read_error Optional response.read() exception.
    @return     None.
    @exception  None
    """
    monkeypatch.setattr(
        ai_backend_service.request,
        "urlopen",
        lambda http_request, timeout: _FakeResponse(payload, read_error),
    )
    result = ai_backend_service.probe_profile(
        {
            "backend_kind": "openai_compatible",
            "base_url": "https://provider.test/v1",
            "api_key": "api-secret-value",
            "model_name": "model-a",
        }
    )

    assert result["success"] is False
    assert result["discovered_model_count"] == 0
    assert str(result["message"]).startswith("Connection failed:")
    assert "api-secret-value" not in str(result["message"])
    assert "raw-secret-body" not in str(result["message"])
    assert "secret-" not in str(result["message"])


def test_probe_profile_rejects_invalid_base_url() -> None:
    """
    @brief      Verify invalid backend base URLs are rejected before network access.
    @return     None.
    @exception  None
    """
    result = ai_backend_service.probe_profile(
        {
            "backend_kind": "openai_compatible",
            "base_url": "127.0.0.1:8000/v1",
            "api_key": "secret",
            "model_name": "qwen3-8b",
            "request_timeout_seconds": 15,
        }
    )

    assert result["success"] is False
    assert result["message"] == "Base URL is invalid."


# END OF FILE
