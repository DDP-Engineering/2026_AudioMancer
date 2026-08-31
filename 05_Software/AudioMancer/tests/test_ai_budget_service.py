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


def test_context_budget_metadata_uses_direct_online_context_fraction() -> None:
    """
    @brief      Verify online provider budgets use the configured direct context fraction.
    @return     None.
    @exception  None
    """
    metadata = ai_budget_service.context_budget_metadata(
        {
            "backend_kind": config.ONLINE_AI_BACKEND_KIND,
            "context_window": 1000,
            "output_reserve_tokens": 950,
        },
        "prompt text",
        min_safety_margin_tokens=50,
        safety_margin_context_fraction=0.01,
        text_context_fraction=0.5,
        min_text_budget_tokens=100,
        error_prefix="Workflow cannot run",
        online_text_context_fraction=config.DEFAULT_ONLINE_AI_TEXT_CONTEXT_FRACTION,
    )

    assert metadata["text_budget_tokens"] == 300
    assert ai_budget_service.uses_online_text_budget({"backend_kind": config.ONLINE_AI_BACKEND_KIND}) is True
    assert ai_budget_service.uses_online_text_budget({"backend_kind": "lmstudio"}) is False


# END OF FILE
