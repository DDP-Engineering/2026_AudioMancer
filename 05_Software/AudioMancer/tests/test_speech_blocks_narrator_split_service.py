#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_speech_blocks_narrator_split_service.py
@brief Focused tests for deterministic same-narrator Speech Blocks segmentation.
@details Verifies exact source coverage, sentence integrity, quotation safety,
         multilingual behaviour, and budget-overflow flagging.
"""

# IMPORTS

import random

import pytest

from audiomancer.services import speech_blocks_narrator_split_service as narrator_split


def _plan(text: str, target_units: int = 40) -> list[dict[str, object]]:
    """
    @brief      Plan narrator blocks for one source text.
    @param[in]  text Source chunk text.
    @param[in]  target_units Preferred budget units per block.
    @return     Planned block payloads.
    @exception  None
    """
    return narrator_split.plan_narrator_blocks(text, target_units)


def _rebuild(blocks: list[dict[str, object]]) -> str:
    """
    @brief      Concatenate the exact source text of planned blocks.
    @param[in]  blocks Planned block payloads.
    @return     Reconstructed source text.
    @exception  None
    """
    return "".join(str(block["source_text"]) for block in blocks)


def test_planned_blocks_reproduce_the_source_chunk_exactly() -> None:
    """
    @brief      Verify planned blocks never lose or alter source characters.
    @return     None.
    @exception  None
    """
    source_text = (
        "Camera era goala. Pe masa statea o scrisoare nedeschisa. "
        "Afara ploua marunt, iar strada lucea sub felinare. Nimeni nu a venit."
    )

    blocks = _plan(source_text, target_units=12)

    assert _rebuild(blocks) == source_text
    assert len(blocks) > 1


def test_blocks_never_end_in_the_middle_of_a_sentence() -> None:
    """
    @brief      Verify every block boundary lands on a sentence terminator.
    @return     None.
    @exception  None
    """
    source_text = " ".join(f"Aceasta este propozitia numarul {index} din paragraf." for index in range(1, 13))

    blocks = _plan(source_text, target_units=10)

    assert len(blocks) > 1
    for block in blocks:
        assert str(block["text"]).endswith(".")


def test_multi_sentence_quotation_is_never_split_open() -> None:
    """
    @brief      Verify a quoted passage spanning several sentences stays in one block.
    @return     None.
    @exception  None
    """
    source_text = 'El spuse: "Am fost acolo. Am vazut totul. Nu mai am ce adauga." Apoi a plecat.'

    blocks = _plan(source_text, target_units=8)

    assert _rebuild(blocks) == source_text
    for block in blocks:
        assert not narrator_split.open_quote_stack(str(block["source_text"]))


def test_sentence_boundary_inside_an_open_quote_is_not_used() -> None:
    """
    @brief      Verify a sentence end inside a quotation is never promoted to a block boundary.
    @details    Covers the current deterministic same-narrator segmentation contract.
    @return     None.
    @exception  None
    """
    source_text = (
        "He had been working on it for years.\n"
        '"As in, the credit is not coming together. See what I am saying?"\n'
        "Drenthe sighed."
    )

    blocks = _plan(source_text, target_units=6)

    assert _rebuild(blocks) == source_text
    for block in blocks:
        assert "See what I am saying" not in str(block["text"]) or "As in, the credit" in str(block["text"])
        assert not narrator_split.open_quote_stack(str(block["source_text"]))


@pytest.mark.parametrize(
    ("opening_quote", "closing_quote"),
    [
        ('"', '"'),
        ("“", "”"),
        ("„", "”"),
        ("«", "»"),
        ("‹", "›"),
        ("「", "」"),
        ("『", "』"),
        ("《", "》"),
        ("〈", "〉"),
    ],
)
def test_every_supported_quote_pair_keeps_its_passage_intact(opening_quote: str, closing_quote: str) -> None:
    """
    @brief      Verify quotation tracking covers each supported delimiter pair.
    @param[in]  opening_quote Opening delimiter under test.
    @param[in]  closing_quote Matching closing delimiter.
    @return     None.
    @exception  None
    """
    quoted = f"{opening_quote}Prima parte. A doua parte. A treia parte.{closing_quote}"
    source_text = f"El incepu. {quoted} Apoi tacu."

    blocks = _plan(source_text, target_units=6)

    assert _rebuild(blocks) == source_text
    quoted_blocks = [block for block in blocks if opening_quote in str(block["source_text"])]
    assert quoted_blocks, "the quoted passage must appear in some block"
    for block in quoted_blocks:
        assert closing_quote in str(block["source_text"])


@pytest.mark.parametrize(
    "quotation",
    [
        "„Guten Tag. «Bleib bitte hier.» Wir warten.“",
        "„Bună ziua. «Rămâi aici.» Așteptăm.”",
    ],
)
def test_low_quote_closers_end_nested_quotation_before_budget_splitting(quotation: str) -> None:
    """
    @brief      Verify German and Romanian low-open quotes close before later narration is split.
    @param[in]  quotation Nested low-open quotation under test.
    @return     None.
    @exception  None
    """
    source_text = f"{quotation} Er ging weiter. Die Sonne schien hell. Niemand folgte ihm."

    blocks = _plan(source_text, target_units=8)

    assert not narrator_split.open_quote_stack(quotation)
    assert _rebuild(blocks) == source_text
    assert len(blocks) > 1
    assert all(narrator_split.NARRATOR_BUDGET_EXCEEDED_FLAG not in block["warning_flags"] for block in blocks[1:])


def test_single_oversized_sentence_stays_whole_and_is_flagged() -> None:
    """
    @brief      Verify an over-budget sentence is preserved and marked instead of cut.
    @return     None.
    @exception  None
    """
    source_text = " ".join(["cuvant"] * 60) + "."

    blocks = _plan(source_text, target_units=10)

    assert len(blocks) == 1
    assert _rebuild(blocks) == source_text
    assert narrator_split.NARRATOR_BUDGET_EXCEEDED_FLAG in blocks[0]["warning_flags"]


def test_abbreviation_does_not_create_a_block_boundary() -> None:
    """
    @brief      Verify a period closing an abbreviation is not treated as a sentence end.
    @return     None.
    @exception  None
    """
    source_text = "Dr. Ionescu a intrat in camera fara sa bata la usa mai intai."

    blocks = _plan(source_text, target_units=4)

    assert _rebuild(blocks) == source_text
    assert len(blocks) == 1


def test_short_trailing_block_is_absorbed_into_its_predecessor() -> None:
    """
    @brief      Verify greedy packing does not strand a few words as a final block.
    @return     None.
    @exception  None
    """
    source_text = "Prima propozitie este destul de lunga pentru a umple un bloc intreg singura. Nu."

    blocks = _plan(source_text, target_units=16)

    assert _rebuild(blocks) == source_text
    assert len(blocks) == 1


@pytest.mark.parametrize(
    ("label", "source_text"),
    [
        ("romanian", "Când a văzut ce se întâmplă, a tăcut. Apoi a plecat fără un cuvânt. Nimeni nu l-a oprit."),
        ("english", "He paused… Then he left. She stayed behind and waited for the rain to stop."),
        ("french", "Il entra. « Bonsoir », dit-il. Personne ne répondit dans la grande salle vide."),
        ("german", "Er kam herein. Sie schwieg lange. Dann ging er wieder hinaus in den Regen."),
        ("russian", "Он засмеялся. Она молчала. Потом он ушёл и больше не возвращался."),
    ],
)
def test_supported_languages_split_without_losing_text(label: str, source_text: str) -> None:
    """
    @brief      Verify segmentation preserves text across every supported content language.
    @param[in]  label Language label under test.
    @param[in]  source_text Source chunk text in that language.
    @return     None.
    @exception  None
    """
    blocks = narrator_split.plan_narrator_blocks(source_text, target_units=8)

    assert _rebuild(blocks) == source_text, label
    assert blocks, label
    assert all(str(block["text"]).strip() for block in blocks), label


def test_slightly_oversized_chunk_splits_into_even_blocks_without_flags() -> None:
    """
    @brief      Verify a chunk just past the budget is balanced instead of packed then flagged.
    @details    Regression guard: filling the first block to the ceiling used to strand the
                remainder, which the orphan merge then folded back into one over-budget block.
    @return     None.
    @exception  None
    """
    source_text = " ".join(f"Propozitia numarul {index} umple cateva unitati de buget." for index in range(1, 15))
    target_units = 60

    blocks = _plan(source_text, target_units)

    assert _rebuild(blocks) == source_text
    assert len(blocks) == 2
    assert all(not block["warning_flags"] for block in blocks)
    smallest = min(len(str(block["text"])) for block in blocks)
    largest = max(len(str(block["text"])) for block in blocks)
    assert smallest >= largest * 0.5, "blocks should be comparable in size, not ceiling-packed"


def test_planning_is_deterministic_across_repeated_runs() -> None:
    """
    @brief      Verify identical input always yields byte-identical blocks.
    @return     None.
    @exception  None
    """
    source_text = "Una. Doua. Trei. Patru. Cinci. Sase. Sapte. Opt. Noua. Zece."

    first = _plan(source_text, target_units=5)
    second = _plan(source_text, target_units=5)

    assert first == second


def test_blank_and_empty_chunks_produce_no_blocks() -> None:
    """
    @brief      Verify whitespace-only chunks are ignored rather than producing empty blocks.
    @return     None.
    @exception  None
    """
    assert narrator_split.plan_narrator_blocks("", 20) == []
    assert narrator_split.plan_narrator_blocks("   \n\n  ", 20) == []


def test_random_paragraphs_always_preserve_source_text() -> None:
    """
    @brief      Property check that packing never loses characters on varied generated input.
    @return     None.
    @exception  None
    """
    generator = random.Random(20260726)
    words = ["casa", "drum", "noapte", "lumina", "vânt", "poveste", "umbră", "carte"]
    terminators = [".", "!", "?", "…", '."', ".»"]
    for _ in range(200):
        sentences = []
        for _ in range(generator.randint(1, 12)):
            sentence = " ".join(generator.choice(words) for _ in range(generator.randint(1, 14)))
            sentences.append(sentence + generator.choice(terminators))
        source_text = " ".join(sentences)

        blocks = narrator_split.plan_narrator_blocks(source_text, generator.randint(3, 60))

        assert _rebuild(blocks) == source_text
