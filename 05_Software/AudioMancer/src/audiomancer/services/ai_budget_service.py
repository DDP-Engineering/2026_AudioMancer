#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_budget_service.py
@brief Shared AI context-budget helpers for AudioMancer.
@details Centralizes conservative token estimates and context-window input
         budget calculations used by AI-assisted workflow services.
"""

# IMPORTS

from audiomancer import config

# PUBLIC API


def estimate_text_tokens(text: str) -> int:
    """
    @brief      Estimate token usage for local AI budget checks.
    @param[in]  text Candidate prompt or payload text.
    @return     Positive estimated token count.
    @exception  None
    """
    return max(1, len(str(text)) // 4)


def available_text_budget(
    context_window: int,
    max_output_tokens: int,
    prompt_budget_tokens: int,
    safety_margin_tokens: int,
    text_context_fraction: float,
) -> int:
    """
    @brief      Compute usable input tokens for one AI request.
    @param[in]  context_window Selected profile context window.
    @param[in]  max_output_tokens Reserved maximum output tokens.
    @param[in]  prompt_budget_tokens Estimated system and prompt-shell tokens.
    @param[in]  safety_margin_tokens Reserved safety margin tokens.
    @param[in]  text_context_fraction Maximum context fraction available to input text.
    @return     Usable input-token budget.
    @exception  None
    """
    available_budget = (
        int(context_window) - int(max_output_tokens) - int(prompt_budget_tokens) - int(safety_margin_tokens)
    )
    return min(
        int(int(context_window) * float(text_context_fraction)),
        available_budget,
    )


def uses_online_text_budget(ai_profile_payload: dict[str, object]) -> bool:
    """
    @brief      Return whether one AI profile should use online-provider text budgeting.
    @param[in]  ai_profile_payload Selected AI profile payload.
    @return     True when the profile backend is the configured online AI backend.
    @exception  None
    """
    return str(ai_profile_payload.get("backend_kind", "")).strip() == config.ONLINE_AI_BACKEND_KIND


def context_budget_metadata(
    ai_profile_payload: dict[str, object],
    prompt_text: str,
    min_safety_margin_tokens: int,
    safety_margin_context_fraction: float,
    text_context_fraction: float,
    min_text_budget_tokens: int,
    error_prefix: str,
    online_text_context_fraction: float | None = None,
) -> dict[str, int]:
    """
    @brief      Build common AI context-window budget metadata.
    @param[in]  ai_profile_payload Selected AI profile payload.
    @param[in]  prompt_text Rendered system plus user-shell prompt text.
    @param[in]  min_safety_margin_tokens Minimum reserved safety-margin tokens.
    @param[in]  safety_margin_context_fraction Context fraction reserved as safety margin.
    @param[in]  text_context_fraction Maximum context fraction available to input text.
    @param[in]  min_text_budget_tokens Minimum usable text budget required by the workflow.
    @param[in]  error_prefix Workflow-specific error message prefix.
    @param[in]  online_text_context_fraction Optional direct context fraction for online AI providers.
    @return     Common context-budget metadata fields.
    @exception  ValueError Raised when the selected profile leaves too little input room.
    """
    context_window = max(1, int(ai_profile_payload.get("context_window", config.DEFAULT_LLM_CONTEXT_WINDOW)))
    max_output_tokens = max(
        1,
        int(ai_profile_payload.get("max_output_tokens", config.DEFAULT_LLM_MAX_OUTPUT_TOKENS)),
    )
    prompt_budget_tokens = estimate_text_tokens(prompt_text)
    safety_margin_tokens = max(
        int(min_safety_margin_tokens),
        int(context_window * float(safety_margin_context_fraction)),
    )
    if online_text_context_fraction is not None and uses_online_text_budget(ai_profile_payload):
        text_budget_tokens = int(context_window * float(online_text_context_fraction))
    else:
        text_budget_tokens = available_text_budget(
            context_window,
            max_output_tokens,
            prompt_budget_tokens,
            safety_margin_tokens,
            text_context_fraction,
        )
    min_text_budget = int(min_text_budget_tokens)
    if text_budget_tokens < min_text_budget:
        raise ValueError(
            f"{error_prefix} ({text_budget_tokens} estimated tokens available, {min_text_budget} required)."
        )
    return {
        "context_window": context_window,
        "max_output_tokens": max_output_tokens,
        "prompt_budget_tokens": prompt_budget_tokens,
        "text_budget_tokens": text_budget_tokens,
        "safety_margin_tokens": safety_margin_tokens,
    }


# END OF FILE
