#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_budget_service.py
@brief Focused tests for shared AI context-budget helpers.
@details Verifies conservative token estimates and reusable input-budget math.
"""

# IMPORTS

import pytest

from audiomancer import config
from audiomancer.services import ai_budget_service


def test_estimate_text_tokens_returns_positive_conservative_count() -> None:
    """
    @brief      Verify text token estimates stay positive and scale by four characters.
    @return     None.
    @exception  None
    """
    assert ai_budget_service.estimate_text_tokens("") == 1
    assert ai_budget_service.estimate_text_tokens("12345678") == 2


def test_available_text_budget_reserves_prompt_output_and_safety_tokens() -> None:
    """
    @brief      Verify reusable input-budget math applies both reserved tokens and fraction caps.
    @return     None.
    @exception  None
    """
    assert ai_budget_service.available_text_budget(1000, 200, 100, 50, 0.5) == 500
    assert ai_budget_service.available_text_budget(1000, 400, 300, 50, 0.8) == 250


def test_context_budget_metadata_builds_common_fields_and_rejects_tiny_budget() -> None:
    """
    @brief      Verify shared context-budget metadata normalizes fields and enforces minimum input room.
    @return     None.
    @exception  None
    """
    metadata = ai_budget_service.context_budget_metadata(
        {"context_window": 1000, "output_reserve_tokens": 200},
        "prompt text",
        min_safety_margin_tokens=50,
        safety_margin_context_fraction=0.01,
        text_context_fraction=0.5,
        min_text_budget_tokens=100,
        error_prefix="Workflow cannot run",
    )

    assert metadata == {
        "context_window": 1000,
        "output_reserve_tokens": 200,
        "prompt_budget_tokens": 2,
        "text_budget_tokens": 500,
        "safety_margin_tokens": 50,
    }

    try:
        ai_budget_service.context_budget_metadata(
            {"context_window": 100, "output_reserve_tokens": 90},
            "prompt text",
            min_safety_margin_tokens=20,
            safety_margin_context_fraction=0.01,
            text_context_fraction=0.5,
            min_text_budget_tokens=10,
            error_prefix="Workflow cannot run",
        )
    except ValueError as error:
        assert str(error).startswith("Workflow cannot run")
    else:
        raise AssertionError("Expected tiny budget to raise ValueError.")


@pytest.mark.parametrize("reserve, expected", [(100, 300), (750, 198)])
def test_context_budget_metadata_bounds_online_fraction_by_reservations(reserve, expected) -> None:
    """@brief Verify the online ceiling still leaves room for the whole request."""
    profile = {"backend_kind": config.ONLINE_AI_BACKEND_KIND, "context_window": 1000,
               "output_reserve_tokens": reserve}
    metadata = ai_budget_service.context_budget_metadata(
        profile, "prompt text", 50, 0.01, 0.5, 100, "Workflow cannot run", 0.3
    )
    assert metadata["text_budget_tokens"] == expected

    profile["output_reserve_tokens"] = 950
    with pytest.raises(ValueError, match="Workflow cannot run"):
        ai_budget_service.context_budget_metadata(
            profile, "prompt text", 50, 0.01, 0.5, 100, "Workflow cannot run", 0.3
        )


def test_effective_context_bounds_configuration_by_matching_server_limit() -> None:
    """@brief Verify the loaded limit is enforced while smaller manual budgets still win."""
    profile = {
        "model_name": "model-a", "context_window": 65536, "discovered_context_model_name": "model-a",
        "discovered_context_window": 262144, "server_context_window": 32768,
    }
    metadata = ai_budget_service.context_budget_metadata(profile, "prompt", 50, 0.01, 0.5, 100, "No room")
    assert metadata["context_window"] == 32768
    assert profile["context_window"] == 65536
    assert ai_budget_service.effective_context_window({**profile, "context_window": 16384}) == 16384
    assert ai_budget_service.effective_context_window({**profile, "model_name": "model-b"}) == 65536


def test_context_window_limit_prefers_loaded_server_and_falls_back_to_model() -> None:
    """@brief Follow the loaded limit when present and the model maximum otherwise."""
    profile = {
        "backend_kind": "lmstudio", "model_name": "model-a", "context_window": 65536,
        "discovered_context_model_name": "model-a", "discovered_context_window": 16384,
        "server_context_window": 32768,
    }
    assert ai_budget_service.effective_context_window(profile) == 32768
    assert ai_budget_service.effective_context_window({**profile, "server_context_window": None}) == 16384


def test_subscription_model_default_does_not_cap_manual_context() -> None:
    """@brief A subscription catalog default can be manually increased."""
    profile = {
        "backend_kind": config.CHATGPT_BACKEND_KIND, "model_name": "subscription-model",
        "context_window": 65536, "discovered_context_model_name": "subscription-model",
        "discovered_context_window": 32768,
    }
    assert ai_budget_service.effective_context_window(profile) == 65536


# END OF FILE
