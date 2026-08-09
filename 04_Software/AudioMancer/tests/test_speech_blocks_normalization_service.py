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

import pytest

from audiomancer.services import speech_blocks_normalization_service, speech_blocks_text_split_service


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


def test_tts_budget_split_preserves_exact_source_whitespace_slices() -> None:
    """
    @brief      Verify TTS splitting retains blank lines and repeated or trailing source whitespace.
    @return     None.
    @exception  None
    """
    source_text = (
        "First paragraph has  repeated spaces.\n\n"
        "Second paragraph contains enough words to split safely.\n\n"
        "Third paragraph also exceeds the small configured budget.  \n"
    )
    blocks, _warnings = speech_blocks_normalization_service.split_over_budget_ai_blocks(
        "chunk-0001",
        [{"content_kind": "narration", "source_text": source_text, "text": source_text, "warning_flags": []}],
        {"safe_word_count": 5},
    )

    assert len(blocks) > 1
    assert "".join(str(block["source_text"]) for block in blocks) == source_text
    cursor = 0
    for block in blocks:
        source_slice = str(block["source_text"])
        assert source_slice
        assert source_text[cursor : cursor + len(source_slice)] == source_slice
        cursor += len(source_slice)
    assert cursor == len(source_text)


def test_tts_budget_split_keeps_differing_audio_text_out_of_source_provenance() -> None:
    """
    @brief      Verify model audio text can split independently without replacing exact source slices.
    @return     None.
    @exception  None
    """
    source_text = "Original source sentence one.\n\nOriginal  source sentence two with trailing space. "
    audio_text = "Model audio wording one has changed. Model audio wording two is also intentionally different."
    blocks, _warnings = speech_blocks_normalization_service.split_over_budget_ai_blocks(
        "chunk-0002",
        [{"content_kind": "narration", "source_text": source_text, "text": audio_text, "warning_flags": []}],
        {"safe_word_count": 5},
    )

    assert len(blocks) > 1
    assert "".join(str(block["source_text"]) for block in blocks) == source_text
    assert all(str(block["source_text"]) for block in blocks)
    assert "Model audio" in " ".join(str(block["text"]) for block in blocks)
    assert all(
        speech_blocks_normalization_service.tts_budget_unit_count(str(block["text"])) <= 5 for block in blocks
    )


@pytest.mark.parametrize(
    ("source_text", "safe_word_count"),
    [
        ("\t\t\n\nalpha one two three four five six seven eight ", 3),
        ("\n \n\n\t\n\nalpha one two three four five six seven eight  \n", 3),
        ("\tdelta\tgammabeta\n\n\n\t", 1),
    ],
)
def test_tts_budget_split_preserves_whitespace_only_semantic_spans(
    source_text: str,
    safe_word_count: int,
) -> None:
    """
    @brief      Verify recursive semantic and hard splitting never drops boundary whitespace provenance.
    @param[in]  source_text Source with leading or adjacent whitespace-only semantic spans.
    @return     None.
    @exception  None
    """
    split_parts, _used_hard_split = speech_blocks_normalization_service.split_text_for_tts_budget(
        source_text,
        "narration",
        safe_word_count,
    )
    hard_parts = speech_blocks_normalization_service.hard_split_text_for_tts_budget(
        source_text,
        "narration",
        safe_word_count,
    )

    assert split_parts
    assert "".join(split_parts) == source_text
    assert "".join(hard_parts) == source_text


def test_dialogue_normalization_unwraps_every_authoritative_quote_pair() -> None:
    """
    @brief      Verify spoken dialogue unwrapping follows the splitter's authoritative quote pairs.
    @return     None.
    @exception  None
    """
    expected_pairs = {
        ("„", "”"),
        ("„", "“"),
        ("‚", "‘"),
        ("‚", "'"),
        ("»", "«"),
        ("‹", "›"),
        ("「", "」"),
        ("『", "』"),
        ("《", "》"),
        ("〈", "〉"),
    }
    authoritative_pairs = set(speech_blocks_text_split_service.dialogue_quote_pairs())

    assert expected_pairs <= authoritative_pairs
    for opening_quote, closing_quote in authoritative_pairs:
        wrapped_text = f"{opening_quote}Spoken dialogue.{closing_quote}"
        assert speech_blocks_normalization_service.normalize_block_text(wrapped_text, "dialogue") == "Spoken dialogue."
        assert speech_blocks_normalization_service.normalize_block_text(wrapped_text, "narration") == wrapped_text


# END OF FILE
