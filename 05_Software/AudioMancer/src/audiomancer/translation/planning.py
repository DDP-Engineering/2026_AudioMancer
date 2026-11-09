#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file planning.py
@brief Plan bounded source fragments for translation.
@details Use paragraph markers to reconstruct translations across requests.
"""

# IMPORTS

from dataclasses import dataclass
import re

from audiomancer.services.ai_budget_service import estimate_text_tokens as _estimate_text_tokens

# DATA MODELS / TYPEDEFINITIONS


@dataclass(frozen=True)
class _TranslationTextSegment:
    """
    @brief      Carry one budgeted text segment and its leading paragraph relationship.
    """

    text: str
    continues_previous_paragraph: bool


# PUBLIC API


def paragraph_count(text: str) -> int:
    """@brief Count nonempty paragraphs separated by a blank line."""
    return len(_paragraphs(text))


def _paragraphs(text: str) -> list[str]:
    """@brief Split prose into nonempty paragraphs without changing internal line breaks."""
    return [item.strip() for item in re.split(r"\n\s*\n", text.strip()) if item.strip()]


def _split_translation_source_text(source_text: str, usable_input_budget: int) -> list[_TranslationTextSegment]:
    """@brief Pack source spans in order using the estimate of each assembled fragment.
    @exception ValueError An unbroken span exceeds the available source budget.
    """
    if usable_input_budget <= 0:
        raise ValueError("Translation source budget must be positive.")
    fragments = []
    for paragraph in _paragraphs(source_text):
        pieces = _paragraph_pieces(paragraph, usable_input_budget)
        fragments.extend(_TranslationTextSegment(piece, index > 0) for index, piece in enumerate(pieces))
    return _pack_fragments(fragments, usable_input_budget)


def _paragraph_pieces(paragraph: str, limit: int) -> list[str]:
    """@brief Prefer complete paragraphs, then sentences, then whole words."""
    if _estimate_text_tokens(paragraph) <= limit:
        return [paragraph]
    pieces = []
    for sentence in _split_translation_sentences(paragraph):
        pieces.extend([sentence] if _estimate_text_tokens(sentence) <= limit else sentence.split())
    return pieces


def _pack_fragments(fragments: list[_TranslationTextSegment], limit: int) -> list[_TranslationTextSegment]:
    """@brief Count the actual spaces or paragraph breaks when adding each source span."""
    result = []
    current = None
    for part in fragments:
        if _estimate_text_tokens(part.text) > limit:
            raise ValueError(
                "An unbroken source span exceeds the AI translation budget. Choose a larger profile or edit the source."
            )
        if current is None:
            current = part
            continue
        separator = " " if part.continues_previous_paragraph else "\n\n"
        candidate = current.text + separator + part.text
        if _estimate_text_tokens(candidate) <= limit:
            current = _TranslationTextSegment(candidate, current.continues_previous_paragraph)
        else:
            result.append(current)
            current = part
    if current is not None:
        result.append(current)
    return result


def _join_translation_text_segments(segments: list[_TranslationTextSegment]) -> str:
    """
    @brief      Join text segments using their original paragraph relationships.
    @param[in]  segments Ordered text segments with leading-boundary metadata.
    @return     Reconstructed text with true paragraph and continuation delimiters.
    """
    joined_text = ""
    for segment in segments:
        if joined_text:
            joined_text += " " if segment.continues_previous_paragraph else "\n\n"
        joined_text += segment.text
    return joined_text


def _split_translation_sentences(paragraph: str) -> list[str]:
    """
    @brief      Split a paragraph into approximate sentence units.
    @param[in]  paragraph Source paragraph being segmented or translated.
    @return     Ordered translation sentences.
    """
    normalized = paragraph.strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=(?:[\"'A-Z0-9]))", normalized)
    return [part.strip() for part in parts if part.strip()]


# END OF FILE
