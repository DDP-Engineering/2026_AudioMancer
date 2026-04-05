#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.1.1
"""

# IMPORTS

from urllib import error

from audiomancer import config
from audiomancer.services import ai_backend_service


def test_probe_profile_normalizes_openai_compatible_models(monkeypatch) -> None:
    def _fake_read_json(url, headers, timeout_seconds):
        assert url == "http://127.0.0.1:1234/v1/models"
        assert timeout_seconds == config.DEFAULT_AI_CONNECT_TIMEOUT_SECONDS
        return {"data": [{"id": "qwen3-8b"}, {"id": "llama-3.1-8b"}]}

    monkeypatch.setattr(ai_backend_service, "_read_json", _fake_read_json)

    result = ai_backend_service.probe_profile({
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234/v1",
        "api_key": "",
        "model_name": "qwen3-8b",
        "request_timeout_seconds": 30,
    })

    assert result.success is True
    assert result.discovered_model_count == 2
    assert result.selected_model_valid is True
    assert [model.id for model in result.discovered_models] == [
        "qwen3-8b",
        "llama-3.1-8b",
    ]


def test_probe_profile_normalizes_ollama_models(monkeypatch) -> None:
    def _fake_read_json(url, headers, timeout_seconds):
        assert url == "http://localhost:11434/api/tags"
        return {"models": [{"name": "qwen3:8b"}, {"name": "llama3.1:8b"}]}

    monkeypatch.setattr(ai_backend_service, "_read_json", _fake_read_json)

    result = ai_backend_service.probe_profile({
        "backend_kind": "ollama",
        "base_url": "http://localhost:11434/v1",
        "api_key": "",
        "model_name": "missing",
        "request_timeout_seconds": 20,
    })

    assert result.success is True
    assert result.discovered_model_count == 2
    assert result.selected_model_valid is False


def test_probe_profile_maps_backend_failures(monkeypatch) -> None:
    def _fake_probe(*args, **kwargs):
        raise error.URLError("connection refused")

    monkeypatch.setattr(
        ai_backend_service,
        "_probe_openai_compatible_models",
        _fake_probe,
    )

    result = ai_backend_service.probe_profile({
        "backend_kind": "openai_compatible",
        "base_url": "http://127.0.0.1:8000/v1",
        "api_key": "secret",
        "model_name": "qwen3-8b",
        "request_timeout_seconds": 15,
    })

    assert result.success is False
    assert result.discovered_model_count == 0
    assert "connection refused" in result.message
