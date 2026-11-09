#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file speech_blocks_text_split_service.py
@brief Speech Blocks text splitting helpers.
@details Provides source-text segmentation for AI context budgets and
         conservative TTS budget-unit estimates outside the orchestration
         service.
"""

# IMPORTS

import re

from audiomancer.services import ai_budget_service, cleanup_text_analysis_service

# CONSTANTS

_DIALOGUE_QUOTE_CLOSERS = {
    '"': ('"',),
    "'": ("'",),
    "“": ("”",),
    "‘": ("’",),
    "„": ("“", "”"),
    "‚": ("‘", "'"),
    "«": ("»",),
    "»": ("«",),
    "‹": ("›",),
    "「": ("」",),
    "『": ("』",),
    "《": ("》",),
    "〈": ("〉",),
}
# PUBLIC API


def dialogue_quote_pairs() -> tuple[tuple[str, str], ...]:
    """
    @brief      Return every dialogue quote pair recognized by source splitting.
    @return     Ordered opening and closing quote pairs.
    @exception  None
    """
    return tuple(
        (opening_quote, closing_quote)
        for opening_quote, closing_quotes in _DIALOGUE_QUOTE_CLOSERS.items()
        for closing_quote in closing_quotes
    )


def split_text_for_ai_context_budget(text: str, text_budget_tokens: int, boundary_index: int = 0) -> list[str]:
    """
    @brief      Split source text into ordered spans that fit the AI input text budget.
    @param[in]  text Source text span.
    @param[in]  text_budget_tokens Maximum estimated input tokens for chunk text.
    @param[in]  boundary_index Preferred boundary level index.
    @return     Ordered text spans.
    @exception  None
    """
    source_text = str(text)
    if not source_text:
        return []
    if ai_budget_service.estimate_text_tokens(source_text) <= text_budget_tokens:
        return [source_text]
    splitters = (ai_paragraph_spans, ai_sentence_spans, ai_word_spans)
    if boundary_index >= len(splitters):
        return hard_split_text_for_ai_context_budget(source_text, text_budget_tokens)
    spans = splitters[boundary_index](source_text)
    if len(spans) <= 1:
        return split_text_for_ai_context_budget(source_text, text_budget_tokens, boundary_index + 1)
    split_parts: list[str] = []
    current_part = ""
    for span in spans:
        span_parts = (
            [span]
            if ai_budget_service.estimate_text_tokens(span) <= text_budget_tokens
            else split_text_for_ai_context_budget(span, text_budget_tokens, boundary_index + 1)
        )
        for span_part in span_parts:
            candidate_part = f"{current_part}{span_part}" if current_part else span_part
            if current_part and ai_budget_service.estimate_text_tokens(candidate_part) > text_budget_tokens:
                split_parts.append(current_part)
                current_part = span_part
            else:
                current_part = candidate_part
    if current_part:
        split_parts.append(current_part)
    return split_parts


def ai_paragraph_spans(text: str) -> list[str]:
    """
    @brief      Split text into paragraph spans while preserving separators.
    @param[in]  text Source text span.
    @return     Ordered paragraph spans.
    @exception  None
    """
    return [match.group(0) for match in re.finditer(r".+?(?:\n\s*\n+|$)", str(text), flags=re.DOTALL) if match.group(0)]


def ai_sentence_spans(text: str) -> list[str]:
    """
    @brief      Split text into sentence spans while preserving trailing whitespace.
    @details    Delegates to the shared script-aware primitive; clause marks stay in scope
                because context-budget splitting benefits from finer spans.
    @param[in]  text Source text span.
    @return     Ordered sentence spans.
    @exception  None
    """
    return cleanup_text_analysis_service.sentence_spans(text, include_clause_marks=True)


def ai_word_spans(text: str) -> list[str]:
    """
    @brief      Split text into whitespace-preserving word spans.
    @param[in]  text Source text span.
    @return     Ordered word spans.
    @exception  None
    """
    return [match.group(0) for match in re.finditer(r"\S+\s*|^\s+", str(text)) if match.group(0)]


def hard_split_text_for_ai_context_budget(text: str, text_budget_tokens: int) -> list[str]:
    """
    @brief      Split text by characters when no semantic boundary fits the AI input budget.
    @param[in]  text Source text span.
    @param[in]  text_budget_tokens Maximum estimated input tokens for chunk text.
    @return     Ordered text spans.
    @exception  None
    """
    max_characters = max(1, int(text_budget_tokens) * 4)
    return [str(text)[index : index + max_characters] for index in range(0, len(str(text)), max_characters)]


# END OF FILE
