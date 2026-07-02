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


def test_build_source_spans_preserves_exact_text_and_paragraph_boundaries() -> None:
    """
    @brief      Verify deterministic Speech Blocks source spans preserve exact source text.
    @details    Covers SBSPAN-001, SBSPAN-003, and REQ-FUNC-042.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    source_text = 'Naratiune inainte. "Deal," the pilot said.\n\n- Vii acasa? intreba Ion.'

    source_spans = speech_blocks_text_split_service.build_source_spans(source_text)

    _assert_source_spans_reconstruct_text(source_text, source_spans)
    paragraph_boundary_end = source_text.index("\n\n") + 2
    assert all(
        not (int(span["start_offset"]) < paragraph_boundary_end < int(span["end_offset"])) for span in source_spans
    )


def test_build_source_spans_classifies_multilingual_dialogue_conventions() -> None:
    """
    @brief      Verify multilingual dialogue markers produce language-neutral source-span candidate kinds.
    @details    Covers SBSPAN-002, SBSPAN-003, and REQ-FUNC-043.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    cases = [
        ("romanian_guillemet", "«Bună seara.»", "dialogue_candidate"),
        ("romanian_dash", "— Vii acasă?", "dialogue_candidate"),
        ("french_guillemet_attribution", "« Bonjour », dit-elle.", "mixed_candidate"),
        ("german_low_high_quote", "„Guten Morgen.“", "dialogue_candidate"),
        ("german_reversed_guillemet_attribution", "»Guten Morgen«, sagte Anna.", "mixed_candidate"),
        ("russian_dash_attribution", "— Пойдём домой? — спросил Иван.", "mixed_candidate"),
        ("japanese_corner_quote", "太郎は言った。「行こう。」", "mixed_candidate"),
        ("chinese_fullwidth_quote", "她说：“走吧。”", "mixed_candidate"),
        ("mixed_narration_dialogue", 'The pilot nodded. "Deal," the pilot said.', "mixed_candidate"),
    ]

    for label, source_text, expected_kind in cases:
        source_spans = speech_blocks_text_split_service.build_source_spans(source_text)

        _assert_source_spans_reconstruct_text(source_text, source_spans)
        candidate_kinds = {str(span.get("candidate_kind", "")) for span in source_spans if str(span["text"]).strip()}
        assert expected_kind in candidate_kinds, label


def test_build_atomic_speech_units_splits_many_elements_inside_one_span() -> None:
    """
    @brief      Verify one source span can produce many ordered atomic Speech Blocks units.
    @details    Covers SB-ATOMIC-001 and REQ-FUNC-050.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """
    source_text = '"Are you coming?" Ana asked. "Not yet," Ion said. "Then hurry."'
    source_spans = [
        {
            "source_span_id": "s001",
            "start_offset": 0,
            "end_offset": len(source_text),
            "text": source_text,
            "candidate_kind": "mixed_candidate",
        }
    ]

    atomic_units = speech_blocks_text_split_service.build_atomic_speech_units(source_text, source_spans)

    assert [unit["atomic_unit_id"] for unit in atomic_units] == ["u001", "u002", "u003", "u004", "u005"]
    assert [unit["structural_kind"] for unit in atomic_units] == [
        "dialogue",
        "attribution",
        "dialogue",
        "attribution",
        "dialogue",
    ]
    assert [unit["text"] for unit in atomic_units] == [
        '"Are you coming?"',
        " Ana asked. ",
        '"Not yet,"',
        " Ion said. ",
        '"Then hurry."',
    ]
    assert {unit["source_span_id"] for unit in atomic_units} == {"s001"}
    _assert_atomic_units_reconstruct_text(source_text, atomic_units)


def test_build_atomic_speech_units_classifies_multilingual_attribution_patterns() -> None:
    """
    @brief      Verify multilingual dialogue attribution is separated from dialogue.
    @details    Covers SB-ATOMIC-002 and REQ-FUNC-051.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """
    cases = [
        ('"Come?" Ana asked. "Soon."', ["dialogue", "attribution", "dialogue"]),
        ("\u201eVii?\u201d \u00eentreb\u0103 Ana. \u201eCur\u00e2nd.\u201d", ["dialogue", "attribution", "dialogue"]),
        ("\u00ab Tu viens ? \u00bb demanda Ana. \u00ab Bient\u00f4t. \u00bb", ["dialogue", "attribution", "dialogue"]),
        ("\u201eKommst du?\u201c, fragte Anna. \u201eBald.\u201c", ["dialogue", "attribution", "dialogue"]),
        ("\u2014 Vii? \u00eentreb\u0103 Ana. \u2014 Cur\u00e2nd.", ["dialogue", "attribution", "dialogue"]),
    ]

    for source_text, expected_kinds in cases:
        atomic_units = speech_blocks_text_split_service.build_atomic_speech_units(source_text)

        assert [unit["structural_kind"] for unit in atomic_units if str(unit["text"]).strip()] == expected_kinds
        _assert_atomic_units_reconstruct_text(source_text, atomic_units)
        for unit in atomic_units:
            if unit["structural_kind"] == "dialogue":
                assert " asked" not in str(unit["text"]).casefold()
                assert "întreb" not in str(unit["text"]).casefold()
                assert "demanda" not in str(unit["text"]).casefold()
                assert "fragte" not in str(unit["text"]).casefold()


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


def _assert_source_spans_reconstruct_text(source_text: str, source_spans: list[dict[str, object]]) -> None:
    """
    @brief      Assert source span IDs, offsets, and text form one exact contiguous source string.
    @param[in]  source_text Expected full source text.
    @param[in]  source_spans Candidate source-span payloads.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    assert source_spans
    cursor = 0
    for index, span in enumerate(source_spans, start=1):
        assert span["source_span_id"] == f"s{index:03d}"
        assert span["start_offset"] == cursor
        assert int(span["end_offset"]) > cursor
        assert span["text"] == source_text[cursor : int(span["end_offset"])]
        assert span["candidate_kind"] in {
            "dialogue_candidate",
            "narration_candidate",
            "attribution_candidate",
            "mixed_candidate",
        }
        cursor = int(span["end_offset"])
    assert cursor == len(source_text)
    assert "".join(str(span["text"]) for span in source_spans) == source_text


def _assert_atomic_units_reconstruct_text(source_text: str, atomic_units: list[dict[str, object]]) -> None:
    """
    @brief      Assert atomic unit IDs, offsets, and text form one exact contiguous source string.
    @param[in]  source_text Expected full source text.
    @param[in]  atomic_units Candidate atomic-unit payloads.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """
    assert atomic_units
    cursor = 0
    for index, unit in enumerate(atomic_units, start=1):
        assert unit["atomic_unit_id"] == f"u{index:03d}"
        assert unit["start_offset"] == cursor
        assert int(unit["end_offset"]) > cursor
        assert unit["text"] == source_text[cursor : int(unit["end_offset"])]
        assert unit["structural_kind"] in {
            "dialogue",
            "attribution",
            "narration",
            "separator",
            "mixed",
        }
        cursor = int(unit["end_offset"])
    assert cursor == len(source_text)
    assert "".join(str(unit["text"]) for unit in atomic_units) == source_text


# END OF FILE
