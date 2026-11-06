#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chunking_ai_service.py
@brief AI request policy and provider boundary for Chunking.
@details Builds budget-aware prompts and forwards descriptor requests without source materialization or persistence.
"""

# IMPORTS

from hashlib import sha256
import json
import re

from audiomancer import config
from audiomancer.services import ai_budget_service, llm_provider_service, prompt_template_service

# CONSTANTS

BudgetMetadataPayload = dict[str, int]

# PUBLIC API


def _build_budget_metadata(
    ai_profile_payload: dict[str, object],
    semantic_strategy: str,
    system_prompt: str,
    additional_chunking_instructions: str,
    chunking_context_mode: str | None = None,
) -> BudgetMetadataPayload:
    """
    @brief      Build context-window budget metadata for AI chunking.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  semantic_strategy Selected semantic strategy token.
    @param[in]  system_prompt Rendered system prompt.
    @param[in]  additional_chunking_instructions Optional operator-supplied chunking rules.
    @param[in]  chunking_context_mode Optional AI chunking context mode token.
    @return     Context-budget metadata used for request-window construction.
    @exception  ValueError Raised when context and output settings leave too little input room.
    """
    prompt_user_shell = _render_chunking_user_prompt(
        {
            "strategy": semantic_strategy,
            "units_block": "",
            "additional_chunking_instructions": additional_chunking_instructions,
        },
    )
    budget_metadata = ai_budget_service.context_budget_metadata(
        ai_profile_payload,
        f"{system_prompt}\n\n{prompt_user_shell}",
        config.DEFAULT_AI_CHUNKING_MIN_SAFETY_MARGIN_TOKENS,
        config.DEFAULT_AI_CHUNKING_SAFETY_MARGIN_CONTEXT_FRACTION,
        config.DEFAULT_AI_CHUNKING_TEXT_CONTEXT_FRACTION,
        config.DEFAULT_AI_CHUNKING_MIN_TEXT_BUDGET_TOKENS,
        "AI-assisted chunking cannot run because the selected AI profile context window "
        "and max output tokens leave too little room for chunking input",
        online_text_context_fraction=config.DEFAULT_ONLINE_AI_TEXT_CONTEXT_FRACTION,
    )
    if (
        ai_budget_service.uses_online_text_budget(ai_profile_payload)
        or chunking_context_mode == config.AI_CHUNKING_CONTEXT_MODE_MAXIMUM
    ):
        strategy_paragraph_cap = 0
    elif chunking_context_mode == config.AI_CHUNKING_CONTEXT_MODE_WIDE_SCENE:
        strategy_paragraph_cap = config.AI_CHUNKING_WIDE_WINDOW_SIZE_BY_STRATEGY.get(
            semantic_strategy,
            config.AI_CHUNKING_WIDE_WINDOW_SIZE_BY_STRATEGY[config.DEFAULT_AI_CHUNKING_STRATEGY],
        )
    else:
        strategy_paragraph_cap = config.AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY.get(
            semantic_strategy,
            config.AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY[config.DEFAULT_AI_CHUNKING_STRATEGY],
        )
    return {
        **budget_metadata,
        "strategy_paragraph_cap": strategy_paragraph_cap,
    }


def _render_chunking_user_prompt(variables: dict[str, object]) -> str:
    """
    @brief      Render the AI chunking user prompt with optional operator rules.
    @param[in]  variables Prompt variables.
    @return     Rendered AI chunking user prompt.
    """
    template = prompt_template_service.load_prompt("text_chunking_user")
    placeholder_names = set(re.findall(r"{([A-Za-z_][A-Za-z0-9_]*)}", template))
    rendered_prompt = prompt_template_service.render_prompt(
        "text_chunking_user",
        {key: value for key, value in variables.items() if key in placeholder_names},
    )
    additional_chunking_instructions = _normalized_additional_chunking_instructions(
        variables.get("additional_chunking_instructions")
    )
    if additional_chunking_instructions and "additional_chunking_instructions" not in placeholder_names:
        rendered_prompt = _append_additional_chunking_instructions(
            rendered_prompt,
            additional_chunking_instructions,
        )
    return rendered_prompt


def _normalized_additional_chunking_instructions(value: object) -> str:
    """
    @brief      Normalize optional operator chunking rules for prompt insertion and state storage.
    @param[in]  value Candidate instruction text.
    @return     Trimmed instruction text.
    """
    if value is None:
        return ""
    return str(value).strip()


def _append_additional_chunking_instructions(prompt_text: str, additional_chunking_instructions: str) -> str:
    """
    @brief      Append operator chunking rules to one rendered AI chunking prompt.
    @param[in]  prompt_text Rendered prompt template text.
    @param[in]  additional_chunking_instructions Normalized operator rules.
    @return     Prompt text with an additional-rules section.
    """
    if not additional_chunking_instructions:
        return prompt_text
    return f"{prompt_text.rstrip()}\n\nAdditional operator chunking instructions:\n{additional_chunking_instructions}\n"


def _estimate_text_tokens(text: str) -> int:
    """
    @brief      Estimate token usage for local budget checks.
    @param[in]  text Value for `text`.
    @return     Estimated token count.
    @exception  None
    """
    return ai_budget_service.estimate_text_tokens(text)


def request_fingerprint(profile, system_prompt, user_template, strategy, instructions, budget):
    """@brief Hash nonsecret request-affecting settings without persisting runtime profile data."""
    keys = (
        "backend_kind",
        "base_url",
        "model_name",
        "temperature",
        "context_window",
        "output_reserve_tokens",
        "reasoning_mode",
        "reasoning_effort",
        "supports_structured_output",
    )
    payload = [
        "chunking-request-1",
        {key: profile.get(key) for key in keys},
        system_prompt,
        user_template,
        strategy,
        instructions,
        budget,
    ]
    return "sha256:" + sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def request_boundaries(profile, system_prompt, user_prompt, **kwargs):
    """@brief Request descriptor JSON; provider exceptions remain visible to run orchestration."""
    return llm_provider_service.chat_json(profile, system_prompt, user_prompt, **kwargs)


# END OF FILE
