#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_chatgpt_models.py
@brief Model candidates and account-bound capability evidence.
@details Exercises isolated protocol, lifecycle and workflow fixtures without live credentials.
"""

# IMPORTS

import importlib
import importlib.util

import pytest

from audiomancer.services import ai_backend_service, chatgpt_provider_service
from test_chatgpt_provider import manager


def model_service():
    """@brief Load the account model verification boundary."""
    name = "audiomancer.services.chatgpt_model_service"
    assert importlib.util.find_spec(name) is not None, "Account-bound model verification is missing"
    return importlib.import_module(name)


def test_successful_text_and_cleanup_schema_probe_records_protected_evidence(monkeypatch):
    """@brief Verify successful text and cleanup schema probe records protected evidence."""
    service = model_service()
    account, calls = manager(), []

    def complete(profile, system, user, **kwargs):
        """@brief Return deterministic completion text and canonical usage."""
        calls.append(kwargs)
        text = (
            '{"ok":true}'
            if len(calls) == 1
            else '{"batch_id":"audiomancer-probe","answers":[{"question_id":"q1","choice":"keep"}]}'
        )
        return chatgpt_provider_service.Completion(text, {})

    monkeypatch.setattr(service.provider, "complete", complete)
    result = service.verify_profile({"model_name": "gpt-5.5"}, manager=account)
    assert result["success"] and result["supports_structured_output"]
    generation, _ = account.acquire()
    assert account.is_verified(generation, "gpt-5.5", schema=True)
    assert calls[1]["schema"]["properties"]["answers"]["minItems"] == 1
    account.disconnect()
    with pytest.raises(RuntimeError, match="changed"):
        account.is_verified(generation, "gpt-5.5", schema=True)


def test_ignored_schema_does_not_grant_cleanup_capability(monkeypatch):
    """@brief Verify ignored schema does not grant cleanup capability."""
    service = model_service()
    account = manager()
    monkeypatch.setattr(
        service.provider, "complete", lambda *a, **k: chatgpt_provider_service.Completion('{"ok":true}', {})
    )
    result = service.verify_profile({"model_name": "custom-model"}, manager=account)
    assert result["success"] and not result["supports_structured_output"]
    assert result["selected_model_valid"]


def test_backend_probe_does_not_send_subscription_tokens_to_models_endpoint(monkeypatch):
    """@brief Verify backend probe does not send subscription tokens to models endpoint."""
    service = model_service()
    calls = []
    monkeypatch.setattr(service, "verify_profile", lambda profile: calls.append(profile) or {"success": True})
    monkeypatch.setattr(ai_backend_service, "_read_json", lambda *a, **k: pytest.fail("API-key model discovery used"))
    assert ai_backend_service.probe_profile({"backend_kind": "chatgpt_subscription"})["success"]
    assert len(calls) == 1

@pytest.mark.parametrize("model", ["gpt-5.6-terra", "gpt-5.6-luna"])
def test_smaller_models_are_candidates_without_granting_capabilities(model):
    """@brief Terra and Luna are selectable hints before any account-specific probe succeeds."""
    service = model_service()
    account = manager()
    result = service.verify_profile({"model_name": ""}, manager=account)
    candidates = {entry["id"] for entry in result["discovered_models"]}
    assert model in candidates
    generation, _ = account.acquire()
    assert not account.is_verified(generation, model, schema=True)


# END OF FILE
