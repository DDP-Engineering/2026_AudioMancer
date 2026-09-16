#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_chatgpt_facade.py
@brief Shared JSON and workflow contracts stay consistent with subscription dispatch.
@details Exercises isolated protocol, lifecycle and workflow fixtures without live credentials.
"""

# IMPORTS

import pytest

from audiomancer.services import (
    ai_budget_service,
    chatgpt_credential_service,
    chatgpt_provider_service,
    llm_provider_service,
    text_cleanup_service,
    token_usage_service,
)
from test_chatgpt_provider import manager


def test_subscription_json_repair_stays_on_same_account_and_merges_usage(monkeypatch, tmp_path):
    """@brief Verify subscription json repair stays on same account and merges usage."""
    account = manager()
    monkeypatch.setattr(chatgpt_credential_service, "get_manager", lambda: account)
    calls = []
    usage = {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True}

    def complete(profile, system, user, **kwargs):
        """@brief Return deterministic completion text and canonical usage."""
        calls.append((profile, system, user, kwargs))
        return chatgpt_provider_service.Completion("not json" if len(calls) == 1 else '{"ok":true}', usage, "enabled")

    monkeypatch.setattr(chatgpt_provider_service, "complete", complete)
    monkeypatch.setattr(
        llm_provider_service,
        "_request_chat_completion_with_cancellation",
        lambda *a, **k: pytest.fail("Subscription request leaked into API-key transport"),
    )
    profile = {"backend_kind": "chatgpt_subscription", "model_name": "gpt-5.4", "api_key": "sentinel"}
    log = tmp_path / "ai.jsonl"
    result = llm_provider_service.chat_json(profile, "system", "user", log_path=log)
    assert result["payload"] == {"ok": True}
    assert result["usage"]["total_tokens"] == 24
    assert result["request_metadata"]["reasoning_mode_effective"] == "enabled"
    assert len(calls) == 2
    assert calls[0][3]["generation"] == calls[1][3]["generation"]
    assert calls[0][0] == calls[1][0]
    assert "sentinel" not in log.read_text()


def test_subscription_no_repair_policy_is_preserved(monkeypatch):
    """@brief Verify subscription no repair policy is preserved."""
    monkeypatch.setattr(chatgpt_credential_service, "get_manager", manager)
    calls = []

    def complete(*args, **kwargs):
        """@brief Return deterministic completion text and canonical usage."""
        calls.append(kwargs)
        return chatgpt_provider_service.Completion("not json", token_usage_service.empty_token_usage())

    monkeypatch.setattr(chatgpt_provider_service, "complete", complete)
    monkeypatch.setattr(
        llm_provider_service,
        "_request_chat_completion_with_cancellation",
        lambda *a, **k: pytest.fail("Subscription dispatch missing"),
    )
    with pytest.raises(ValueError):
        llm_provider_service.chat_json(
            {"backend_kind": "chatgpt_subscription", "model_name": "gpt-5.4"},
            "system",
            "user",
            allow_model_json_repair=False,
            retry_count_override=0,
        )
    assert len(calls) == 1 and calls[0]["retry_count"] == 0


def test_subscription_uses_online_budget_and_cleanup_classification():
    """@brief Verify subscription uses online budget and cleanup classification."""
    assert ai_budget_service.uses_online_text_budget({"backend_kind": "chatgpt_subscription"})
    assert text_cleanup_service._is_online_backend("chatgpt_subscription")
    assert not ai_budget_service.uses_online_text_budget({"backend_kind": "lmstudio"})


def test_responses_usage_does_not_double_count_cached_or_reasoning_tokens():
    """@brief Verify responses usage does not double count cached or reasoning tokens."""
    usage = token_usage_service.normalize_provider_usage(
        {
            "usage": {
                "input_tokens": 20,
                "output_tokens": 8,
                "input_tokens_details": {"cached_tokens": 10},
                "output_tokens_details": {"reasoning_tokens": 5},
            }
        }
    )
    assert usage == {"input_tokens": 20, "output_tokens": 8, "total_tokens": 28, "usage_available": True}


def test_cleanup_subscription_uses_actual_schema_facade_and_domain_validation(monkeypatch):
    """@brief Cleanup retains its strict schema and exact-answer policy through subscription dispatch."""
    from audiomancer.services import cleanup_ai_adjudication_service as cleanup

    account = manager()
    monkeypatch.setattr(chatgpt_credential_service, "get_manager", lambda: account)
    calls = []

    def complete(profile, system, user, **kwargs):
        """@brief Return one exact domain answer while retaining the actual facade contract."""
        calls.append(kwargs)
        return chatgpt_provider_service.Completion(
            '{"batch_id":"batch-one","answers":[{"question_id":"q1","choice":"join_with_space"}]}',
            {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
        )

    monkeypatch.setattr(chatgpt_provider_service, "complete", complete)
    profile = {
        "backend_kind": "chatgpt_subscription",
        "model_name": "gpt-5.5",
        "context_window": 16384,
        "output_reserve_tokens": 8192,
        "supports_structured_output": True,
    }
    questions = [
        {
            "question_id": "q1",
            "question_type": "boundary",
            "left_text": "A sentence",
            "right_text": "continues.",
            "choices": ["join_with_space", "set_paragraph_break"],
        }
    ]
    answers, usage = cleanup._ask(profile, "batch-one", questions, verifier=False, log_path=None, cancel_requested=None)
    assert answers == [{"question_id": "q1", "choice": "join_with_space"}]
    assert usage["total_tokens"] == 15
    assert calls[0]["require_schema"] and calls[0]["retry_count"] == 0
    assert calls[0]["schema"]["additionalProperties"] is False


# END OF FILE
