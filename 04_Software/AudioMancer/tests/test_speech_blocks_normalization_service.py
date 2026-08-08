#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_speech_blocks_normalization_service.py
@brief Focused tests for Speech Blocks normalization helpers.
@details Verifies extracted content-kind, operation-row, warning, identifier,
         and dialogue text normalization behavior.
"""

# IMPORTS

from audiomancer.services import speech_blocks_normalization_service


def test_normalize_block_text_strips_only_dialogue_delimiters() -> None:
    """
    @brief      Verify dialogue cleanup removes outer quote/dash delimiters only for dialogue.
    @return     None.
    @exception  None
    """
    assert speech_blocks_normalization_service.normalize_block_text('"Hello."', "dialogue") == "Hello."
    assert speech_blocks_normalization_service.normalize_block_text("“Hello.”", "dialogue") == "Hello."
    assert speech_blocks_normalization_service.normalize_block_text("« Bonjour. »", "dialogue") == "Bonjour."
    assert speech_blocks_normalization_service.normalize_block_text("- Bonjour.", "dialogue") == "Bonjour."
    assert speech_blocks_normalization_service.normalize_block_text('"Hello."', "narration") == '"Hello."'


def test_content_kind_and_operation_entry_normalization() -> None:
    """
    @brief      Verify content-kind tokens and operation-row speaker fields normalize consistently.
    @return     None.
    @exception  None
    """
    assert speech_blocks_normalization_service.normalize_content_kind("Scene Ambience") == "scene_ambience"
    assert speech_blocks_normalization_service.normalize_content_kind("Background Noise") == "narration"
    assert speech_blocks_normalization_service.normalize_content_kind("unsupported") == "narration"
    assert speech_blocks_normalization_service.is_operation_content_kind("pause")

    operation_entry = speech_blocks_normalization_service.operation_speaker_entry("indication")

    assert operation_entry == {
        "speaker_kind": "operation",
        "speaker_id": "indication",
        "display_name": "Indication",
    }


def test_warning_flags_and_identifiers_are_stable() -> None:
    """
    @brief      Verify warning deduplication and Speech Block identifier formatting.
    @return     None.
    @exception  None
    """
    warning_flags = ["ambiguous_speaker"]

    speech_blocks_normalization_service.append_warning_flag(warning_flags, "ambiguous_speaker")
    speech_blocks_normalization_service.append_warning_flag(warning_flags, "model_text_modified")

    assert warning_flags == ["ambiguous_speaker", "model_text_modified"]
    assert speech_blocks_normalization_service.normalize_warning_flags([" a ", "a", "", "b"]) == ["a", "b"]
    assert speech_blocks_normalization_service.speech_block_id("chunk-0123-extra", 4) == "0123-000004"
    assert speech_blocks_normalization_service.block_text_key(" Hello   THERE ") == "hello there"


def test_chunk_identity_preserves_complete_numeric_token_above_four_digits() -> None:
    """
    @brief      Verify chunk order and Speech Block IDs remain distinct beyond chunk 9999.
    @return     None.
    @exception  None
    """
    assert speech_blocks_normalization_service.chunk_order_from_id("chunk-0001") == 1
    assert speech_blocks_normalization_service.chunk_order_from_id("chunk-10000") == 10000
    assert speech_blocks_normalization_service.chunk_order_from_id("chunk-10001") == 10001
    assert speech_blocks_normalization_service.speech_block_id("chunk-0001", 1) == "0001-000001"
    assert speech_blocks_normalization_service.speech_block_id("chunk-10000", 1) == "10000-000001"
    assert speech_blocks_normalization_service.speech_block_id("chunk-10001", 1) == "10001-000001"


# END OF FILE
