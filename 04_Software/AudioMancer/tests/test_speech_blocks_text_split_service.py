#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_speech_blocks_text_split_service.py
@brief Focused tests for Speech Blocks text splitting helpers.
@details Verifies AI-context source segmentation and TTS budget-unit estimates
         outside the large Speech Blocks orchestration service.
"""

# IMPORTS


from audiomancer.services import (
    speech_blocks_text_split_service,
    tts_budget_service,
)


def test_split_text_for_ai_context_budget_preserves_ordered_segments() -> None:
    """
    @brief      Verify AI-context splitting produces ordered spans under a small token budget.
    @return     None.
    @exception  None
    """
    source_text = "First sentence. Second sentence. Third sentence."

    split_parts = speech_blocks_text_split_service.split_text_for_ai_context_budget(source_text, 5)

    assert "".join(split_parts) == source_text
    assert len(split_parts) > 1


def test_estimate_budget_units_handles_words_and_compact_scripts() -> None:
    """
    @brief      Verify TTS budget units work for spaced and compact text.
    @return     None.
    @exception  None
    """
    assert tts_budget_service.estimate_budget_units("") == 0
    assert tts_budget_service.estimate_budget_units("one two three") == 3
    assert tts_budget_service.estimate_budget_units("abcdefghijklmno") >= 3


# END OF FILE
