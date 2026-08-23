#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_tts_budget_service.py
@brief Focused tests for shared TTS generation-budget helpers.
@details Verifies the conservative fallback budget, the runtime-reported token
         and audio-rate limits, and script-aware budget-unit estimates.
"""

# IMPORTS

from audiomancer import config
from audiomancer.services import tts_budget_service


def test_fallback_budget_matches_the_voiceweaver_clone_cap() -> None:
    """
    @brief      Verify an unprobed runtime is never planned beyond the clone token cap.
    @details    VoiceWeaver caps clone models at 512 codec tokens, so a larger fallback would
                plan blocks the runtime silently truncates.
    @return     None.
    @exception  None
    """
    budget = tts_budget_service.resolve_cached_tts_budget(None)

    assert budget["model_token_budget"] == 512
    assert budget["model_budget_source"] == "config_default"
    assert budget["split_audio_seconds_budget"] < budget["model_audio_seconds_budget"]
    assert budget["safe_word_count"] > 0


def test_discovered_model_budget_overrides_the_fallback() -> None:
    """
    @brief      Verify a probed model's reported token budget wins over the configured fallback.
    @return     None.
    @exception  None
    """
    budget = tts_budget_service.resolve_cached_tts_budget([{"default_model_parameters": {"max_new_tokens": 2048}}])

    assert budget["model_token_budget"] == 2048
    assert budget["model_budget_source"] == "default_model_parameters"


def test_budget_units_stay_word_paced_for_latin_script() -> None:
    """
    @brief      Verify spaced text keeps a word-paced estimate.
    @return     None.
    @exception  None
    """
    assert tts_budget_service.estimate_budget_units("") == 0
    assert tts_budget_service.estimate_budget_units("one two three") == 3


def test_budget_plans_against_the_runtime_recommended_maximum() -> None:
    """
    @brief      Verify REQ-FUNC-82401294 the reported recommended maximum wins over the default.
    @return     None.
    @exception  None
    """
    budget = tts_budget_service.resolve_cached_tts_budget(
        [
            {
                "default_model_parameters": {"max_new_tokens": 512},
                "generation_parameter_ranges": {
                    "max_new_tokens": {
                        "default": 512,
                        "minimum": 128,
                        "recommended_maximum": 2048,
                        "hard_maximum": 8192,
                    }
                },
            }
        ]
    )

    assert budget["model_token_budget"] == 2048
    assert budget["model_budget_source"] == "range_recommended_maximum"


def test_recommended_maximum_never_exceeds_the_reported_hard_maximum() -> None:
    """
    @brief      Verify REQ-FUNC-82401294 a recommended maximum above the hard maximum is bounded.
    @return     None.
    @exception  None
    """
    budget = tts_budget_service.resolve_cached_tts_budget(
        [
            {
                "generation_parameter_ranges": {
                    "max_new_tokens": {"default": 512, "recommended_maximum": 9000, "hard_maximum": 8192}
                }
            }
        ]
    )

    assert budget["model_token_budget"] == 8192


def test_budget_falls_back_to_the_model_default_without_a_recommended_maximum() -> None:
    """
    @brief      Verify REQ-FUNC-82401294 a model reporting no recommended maximum keeps its default.
    @return     None.
    @exception  None
    """
    budget = tts_budget_service.resolve_cached_tts_budget(
        [
            {
                "default_model_parameters": {"max_new_tokens": 512},
                "generation_parameter_ranges": {"max_new_tokens": {"default": 512, "minimum": 128}},
            }
        ]
    )

    assert budget["model_token_budget"] == 512
    assert budget["model_budget_source"] == "default_model_parameters"


def test_budget_converts_tokens_with_the_runtime_reported_audio_rate() -> None:
    """
    @brief      Verify REQ-FUNC-9029b464 the reported per-token audio rate drives the conversion.
    @return     None.
    @exception  None
    """
    budget = tts_budget_service.resolve_cached_tts_budget(
        [
            {
                "generation_parameter_ranges": {
                    "max_new_tokens": {
                        "recommended_maximum": 1000,
                        "hard_maximum": 8192,
                        "approx_audio_seconds_per_token": 0.05,
                    }
                }
            }
        ]
    )

    assert budget["approx_audio_seconds_per_token"] == 0.05
    assert budget["model_audio_seconds_budget"] == 50.0


def test_budget_falls_back_to_the_configured_audio_rate() -> None:
    """
    @brief      Verify REQ-FUNC-9029b464 a model reporting no rate uses the configured estimate.
    @return     None.
    @exception  None
    """
    budget = tts_budget_service.resolve_cached_tts_budget([{"default_model_parameters": {"max_new_tokens": 1000}}])

    assert budget["approx_audio_seconds_per_token"] == config.DEFAULT_TTS_APPROX_AUDIO_SECONDS_PER_TOKEN


def test_preview_word_bounds_span_the_configured_clone_reference_window() -> None:
    """
    @brief      Verify the shared preview word range follows the configured voice-clone durations.
    @return     None.
    @exception  None
    """
    minimum_words, maximum_words = tts_budget_service.preview_word_bounds()

    assert minimum_words == 25
    assert maximum_words == 44


def test_operator_token_maximum_lowers_the_runtime_reported_budget() -> None:
    """
    @brief      Verify REQ-FUNC-8ee67d8f an operator maximum below the reported budget wins.
    @return     None.
    @exception  None
    """
    budget = tts_budget_service.resolve_cached_tts_budget(
        [{"generation_parameter_ranges": {"max_new_tokens": {"recommended_maximum": 2048, "hard_maximum": 8192}}}],
        max_generation_tokens=1024,
    )

    assert budget["model_token_budget"] == 1024
    assert budget["operator_token_maximum"] == 1024


def test_operator_token_maximum_never_raises_the_runtime_reported_budget() -> None:
    """
    @brief      Verify REQ-FUNC-8ee67d8f an operator maximum above the reported budget is ignored.
    @return     None.
    @exception  None
    """
    budget = tts_budget_service.resolve_cached_tts_budget(
        [{"generation_parameter_ranges": {"max_new_tokens": {"recommended_maximum": 2048, "hard_maximum": 8192}}}],
        max_generation_tokens=4096,
    )

    assert budget["model_token_budget"] == 2048


def test_generation_token_limit_falls_back_to_the_shipped_default() -> None:
    """
    @brief      Verify REQ-FUNC-8ee67d8f an unconfigured or malformed maximum uses the default.
    @return     None.
    @exception  None
    """
    assert tts_budget_service.resolve_generation_token_limit(None) == config.DEFAULT_SPEECH_BLOCK_MAX_GENERATION_TOKENS
    assert tts_budget_service.resolve_generation_token_limit({}) == config.DEFAULT_SPEECH_BLOCK_MAX_GENERATION_TOKENS
    assert (
        tts_budget_service.resolve_generation_token_limit({"speech_block_max_generation_tokens": "bad"})
        == config.DEFAULT_SPEECH_BLOCK_MAX_GENERATION_TOKENS
    )
    assert tts_budget_service.resolve_generation_token_limit({"speech_block_max_generation_tokens": 640}) == 640


def test_budget_reports_the_model_hard_token_maximum_alongside_the_operator_target() -> None:
    """
    @brief      Verify REQ-FUNC-79fd5f3a the reported hard maximum travels beside the operator target.
    @return     None.
    @exception  None
    """
    budget = tts_budget_service.resolve_cached_tts_budget(
        [{"generation_parameter_ranges": {"max_new_tokens": {"recommended_maximum": 2048, "hard_maximum": 8192}}}],
        max_generation_tokens=1024,
    )

    assert budget["model_token_budget"] == 1024
    assert budget["hard_token_maximum"] == 8192
    assert budget["hard_word_count"] > budget["safe_word_count"]


def test_hard_token_maximum_falls_back_to_the_uncapped_model_budget() -> None:
    """
    @brief      Verify REQ-FUNC-79fd5f3a an unreported hard maximum leaves the model budget as the ceiling.
    @return     None.
    @exception  None
    """
    budget = tts_budget_service.resolve_cached_tts_budget(
        [{"generation_parameter_ranges": {"max_new_tokens": {"recommended_maximum": 2048}}}],
        max_generation_tokens=1024,
    )

    assert budget["model_token_budget"] == 1024
    assert budget["hard_token_maximum"] == 2048
