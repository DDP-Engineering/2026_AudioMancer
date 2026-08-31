#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file book_analysis_budget_service.py
@brief Build conservative request budgets for hierarchical Book Analysis.
@details Enforces the operation's minimum context and selects the smaller of
         its backend input fraction and the capacity remaining after prompt,
         output, reasoning, and safety reserves.
"""

# IMPORTS

from audiomancer import config
from audiomancer.services import ai_budget_service

# PUBLIC API


def build_request_budget(
    profile_payload: dict[str, object],
    prompt_text: str,
) -> dict[str, int | str]:
    """
    @brief      Build the safe context allocation for one Book Analysis request.
    @param[in]  profile_payload Normalized AI profile payload.
    @param[in]  prompt_text Rendered prompt shell without source text.
    @return     Effective context and reserve metadata.
    @exception  ValueError Raised when the profile context or remaining source
                capacity is below the Book Analysis minimum.
    """
    context_window = int(profile_payload.get("context_window", 0) or 0)
    if context_window < config.BOOK_ANALYSIS_MIN_CONTEXT_TOKENS:
        raise ValueError(
            "Book Analysis requires an AI profile context window of at least "
            "16,384 tokens."
        )

    reasoning_mode = str(
        profile_payload.get("reasoning_mode", "provider_default")
    ).strip()
    configured_output_tokens = max(
        1,
        int(
            profile_payload.get(
                "output_reserve_tokens",
                config.DEFAULT_LLM_OUTPUT_RESERVE_TOKENS,
            )
            or config.DEFAULT_LLM_OUTPUT_RESERVE_TOKENS
        ),
    )
    output_reserve_tokens = min(
        configured_output_tokens,
        max(
            1_024,
            int(context_window * config.BOOK_ANALYSIS_OUTPUT_CONTEXT_FRACTION),
        ),
    )
    reasoning_reserve_tokens = (
        0
        if reasoning_mode == "disabled"
        else int(context_window * config.BOOK_ANALYSIS_REASONING_CONTEXT_FRACTION)
    )
    prompt_reserve_tokens = ai_budget_service.estimate_text_tokens(prompt_text)
    safety_reserve_tokens = max(
        config.BOOK_ANALYSIS_MIN_SAFETY_TOKENS,
        int(context_window * config.BOOK_ANALYSIS_SAFETY_CONTEXT_FRACTION),
    )
    source_context_fraction = (
        config.BOOK_ANALYSIS_ONLINE_SOURCE_CONTEXT_FRACTION
        if ai_budget_service.uses_online_text_budget(profile_payload)
        else config.BOOK_ANALYSIS_LOCAL_SOURCE_CONTEXT_FRACTION
    )
    post_reserve_capacity = (
        context_window
        - output_reserve_tokens
        - reasoning_reserve_tokens
        - prompt_reserve_tokens
        - safety_reserve_tokens
    )
    source_budget_tokens = min(
        int(context_window * source_context_fraction),
        post_reserve_capacity,
    )
    if source_budget_tokens < config.BOOK_ANALYSIS_MIN_SOURCE_TOKENS:
        raise ValueError(
            "Book Analysis profile reserves leave too little context for "
            "source text."
        )
    return {
        "context_window": context_window,
        "source_budget_tokens": source_budget_tokens,
        "output_reserve_tokens": output_reserve_tokens,
        "reasoning_reserve_tokens": reasoning_reserve_tokens,
        "prompt_reserve_tokens": prompt_reserve_tokens,
        "safety_reserve_tokens": safety_reserve_tokens,
        "reasoning_mode": reasoning_mode,
    }


def reduced_source_budget(source_budget_tokens: int) -> int:
    """
    @brief      Reduce one source budget for the single context-overflow retry.
    @param[in]  source_budget_tokens Initial estimated source-token budget.
    @return     Smaller positive estimated source-token budget.
    @exception  None
    """
    return max(
        1,
        int(
            int(source_budget_tokens)
            * config.BOOK_ANALYSIS_OVERFLOW_RETRY_FRACTION
        ),
    )


def source_text_fits(text: str, source_budget_tokens: int) -> bool:
    """
    @brief      Return whether one indivisible source item fits the budget.
    @param[in]  text Source text that Book Analysis may not split.
    @param[in]  source_budget_tokens Available estimated source-token budget.
    @return     True when the estimated text tokens do not exceed the budget.
    @exception  None
    """
    return ai_budget_service.estimate_text_tokens(text) <= int(source_budget_tokens)


# END OF FILE
