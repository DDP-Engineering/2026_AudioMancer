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
@details Verifies the conservative fallback budget, script-aware budget-unit
         estimates, and the operator narration block target.
@author Eng. Dan Dumitru Pasare
@date 2026-07-26
@version 0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    budget = tts_budget_service.resolve_cached_tts_budget([{"default_model_parameters": {"max_new_tokens": 2048}}])

    assert budget["model_token_budget"] == 2048
    assert budget["model_budget_source"] == "default_model_parameters"


def test_budget_units_use_characters_for_space_free_scripts() -> None:
    """
    @brief      Verify CJK text is budgeted by characters rather than by meaningless word counts.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    japanese_text = "彼は笑った。彼女は黙っていた。それから彼は出て行った。"

    units = tts_budget_service.estimate_budget_units(japanese_text)

    assert units > len(japanese_text.split())
    assert units >= len(japanese_text) * 0.3


def test_budget_units_stay_word_paced_for_latin_script() -> None:
    """
    @brief      Verify spaced text keeps a word-paced estimate.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    assert tts_budget_service.estimate_budget_units("") == 0
    assert tts_budget_service.estimate_budget_units("one two three") == 3


def test_operator_target_only_ever_shortens_the_model_budget() -> None:
    """
    @brief      Verify the block target narrows the budget but can never exceed the model limit.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    model_budget = tts_budget_service.resolve_cached_tts_budget(None)
    model_seconds = float(model_budget["split_audio_seconds_budget"])

    shortened = tts_budget_service.apply_block_target_audio_seconds(
        model_budget,
        {"speech_block_target_audio_seconds": 10.0},
    )
    over_asked = tts_budget_service.apply_block_target_audio_seconds(
        model_budget,
        {"speech_block_target_audio_seconds": model_seconds * 10},
    )

    assert shortened["split_audio_seconds_budget"] == 10.0
    assert shortened["safe_word_count"] < model_budget["safe_word_count"]
    assert over_asked["split_audio_seconds_budget"] == model_seconds
    assert over_asked["safe_word_count"] == model_budget["safe_word_count"]


def test_automatic_target_leaves_the_model_budget_untouched() -> None:
    """
    @brief      Verify a zero target means "follow the model budget".
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    model_budget = tts_budget_service.resolve_cached_tts_budget(None)

    automatic = tts_budget_service.apply_block_target_audio_seconds(
        model_budget,
        {"speech_block_target_audio_seconds": 0.0},
    )

    assert automatic["split_audio_seconds_budget"] == model_budget["split_audio_seconds_budget"]
    assert automatic["safe_word_count"] == model_budget["safe_word_count"]
    assert automatic["block_target_audio_seconds"] == 0.0


def test_invalid_or_out_of_range_targets_are_clamped() -> None:
    """
    @brief      Verify malformed and out-of-range operator targets never break budget resolution.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    assert tts_budget_service.resolve_block_target_audio_seconds(None) == 0.0
    assert tts_budget_service.resolve_block_target_audio_seconds({"speech_block_target_audio_seconds": "abc"}) == 0.0
    assert tts_budget_service.resolve_block_target_audio_seconds({"speech_block_target_audio_seconds": -5}) == 0.0
    assert (
        tts_budget_service.resolve_block_target_audio_seconds({"speech_block_target_audio_seconds": 0.5})
        == config.SPEECH_BLOCK_TARGET_AUDIO_SECONDS_MINIMUM
    )
    assert (
        tts_budget_service.resolve_block_target_audio_seconds({"speech_block_target_audio_seconds": 10_000})
        == config.SPEECH_BLOCK_TARGET_AUDIO_SECONDS_MAXIMUM
    )
