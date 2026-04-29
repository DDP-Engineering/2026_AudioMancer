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
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.1.0
"""

# IMPORTS

from audiomancer.services import speech_blocks_text_split_service


def test_split_text_for_ai_context_budget_preserves_ordered_segments() -> None:
    """
    @brief      Verify AI-context splitting produces ordered spans under a small token budget.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    source_text = "First sentence. Second sentence. Third sentence."

    split_parts = speech_blocks_text_split_service.split_text_for_ai_context_budget(source_text, 5)

    assert "".join(split_parts) == source_text
    assert len(split_parts) > 1


def test_tts_budget_unit_count_handles_words_and_compact_scripts() -> None:
    """
    @brief      Verify TTS budget units work for spaced and compact text.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    assert speech_blocks_text_split_service.tts_budget_unit_count("") == 0
    assert speech_blocks_text_split_service.tts_budget_unit_count("one two three") == 3
    assert speech_blocks_text_split_service.tts_budget_unit_count("abcdefghijklmno") >= 3


# END OF FILE
