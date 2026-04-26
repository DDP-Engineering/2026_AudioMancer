#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file tts_budget_service.py
@brief Shared TTS generation-budget helpers for AudioMancer.
@details Resolves a conservative text-splitting budget from cached VoiceWeaver
         model metadata, with configuration fallbacks before runtime generation.
@author Eng. Dan Dumitru Pasare
@date 2026-04-26
@version 0.1.0
"""

# IMPORTS

from audiomancer import config

# PUBLIC API


def resolve_cached_tts_budget(discovered_models: list[dict[str, object]] | None) -> dict[str, object]:
    """
    @brief      Resolve a cached or fallback TTS splitting budget.
    @param[in]  discovered_models Cached VoiceWeaver discovered-model payloads.
    @return     Budget metadata for prompt guidance and validation.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    for model_payload in discovered_models or []:
        if not isinstance(model_payload, dict):
            continue
        for budget_source, parameters in (
            ("default_model_parameters", model_payload.get("default_model_parameters")),
            ("range_default", _parameter_range_default(model_payload.get("generation_parameter_ranges"))),
        ):
            token_budget = _positive_int_from_mapping(parameters, "max_new_tokens")
            if token_budget is not None:
                return _budget_payload(token_budget, budget_source)
    return _budget_payload(config.DEFAULT_TTS_NARRATOR_ONLY_TOKEN_BUDGET, "config_default")


def estimated_safe_word_count(budget_payload: dict[str, object]) -> int:
    """
    @brief      Return the safe narrator-only word count from one budget payload.
    @param[in]  budget_payload Resolved TTS budget payload.
    @return     Safe word count.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return max(1, int(float(budget_payload.get("split_audio_seconds_budget", 0.0)) * _words_per_audio_second()))


def estimated_word_count(text: str) -> int:
    """
    @brief      Estimate the spoken word count for validation.
    @param[in]  text Candidate text span.
    @return     Word count estimate.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return len([word for word in str(text).split() if word.strip()])


# LOCAL HELPERS


def _budget_payload(token_budget: int, budget_source: str) -> dict[str, object]:
    """
    @brief      Build one normalized TTS budget payload.
    @param[in]  token_budget Positive model token budget.
    @param[in]  budget_source Stable source token.
    @return     Budget payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    audio_seconds_budget = int(token_budget) * _audio_seconds_per_token()
    split_audio_seconds_budget = audio_seconds_budget * _split_safety_factor()
    return {
        "model_token_budget": int(token_budget),
        "model_audio_seconds_budget": audio_seconds_budget,
        "split_audio_seconds_budget": split_audio_seconds_budget,
        "safe_word_count": max(1, int(split_audio_seconds_budget * _words_per_audio_second())),
        "approx_audio_seconds_per_token": _audio_seconds_per_token(),
        "split_safety_factor": _split_safety_factor(),
        "model_budget_source": budget_source,
    }


def _parameter_range_default(value: object) -> dict[str, object]:
    """
    @brief      Extract default generation parameters from one model range payload.
    @param[in]  value Candidate generation-parameter range mapping.
    @return     Default parameter mapping.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    if not isinstance(value, dict):
        return {}
    default_parameters: dict[str, object] = {}
    for parameter_name, range_payload in value.items():
        if isinstance(range_payload, dict) and "default" in range_payload:
            default_parameters[str(parameter_name)] = range_payload["default"]
    return default_parameters


def _positive_int_from_mapping(value: object, field_name: str) -> int | None:
    """
    @brief      Resolve one positive integer field from a mapping.
    @param[in]  value Candidate mapping.
    @param[in]  field_name Field name to read.
    @return     Positive integer or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    if not isinstance(value, dict):
        return None
    try:
        candidate = int(value.get(field_name, 0))
    except (TypeError, ValueError):
        return None
    return candidate if candidate > 0 else None


def _audio_seconds_per_token() -> float:
    """
    @brief      Return configured audio seconds represented by one generation token.
    @return     Positive seconds-per-token estimate.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return float(config.DEFAULT_TTS_APPROX_AUDIO_SECONDS_PER_TOKEN)


def _split_safety_factor() -> float:
    """
    @brief      Return configured TTS split safety factor.
    @return     Safety factor.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return float(config.DEFAULT_TTS_SPLIT_SAFETY_FACTOR)


def _words_per_audio_second() -> float:
    """
    @brief      Return configured spoken words per generated audio second.
    @return     Words-per-second estimate.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return float(config.DEFAULT_TTS_WORDS_PER_AUDIO_SECOND)


# END OF FILE
