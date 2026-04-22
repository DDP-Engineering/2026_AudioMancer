#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file cleanup_text_analysis_service.py
@brief Shared text-analysis helpers for cleanup workflows.
@details Centralizes chapter-label detection, language detection, and
         dialogue formatting shared by deterministic and AI-assisted cleanup
         so both pipelines use one consistent implementation.
@author Eng. Dan Dumitru Pasare
@date 2026-04-22
@version 0.1.0
"""

# IMPORTS

import re

from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException

# CONSTANTS

_CHAPTER_PATTERNS = (
    re.compile(r"^(chapter|capitolul|scene|scena)\s+[\wIVXLCDM0-9][\wIVXLCDM0-9 .:-]*$", re.IGNORECASE),
    re.compile(r"^[IVXLCDM]+$", re.IGNORECASE),
)
_DIALOGUE_BREAK_AFTER_PUNCTUATION_PATTERN = re.compile(r'([:;.!?\u2026]["»”\']?)\s+-\s+(?=[A-ZĂÂÎȘȚ])')
_DIALOGUE_BREAK_AFTER_ATTRIBUTION_PATTERN = re.compile(r"([,:])\s+-\s+(?=[A-ZĂÂÎȘȚ])")


# PUBLIC API


def count_detected_chapters(paragraph_texts: list[str]) -> int:
    """
    @brief      Count distinct chapter or scene labels in paragraph order.
    @param[in]  paragraph_texts Normalized paragraph text payloads.
    @return     Number of detected chapter boundaries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    chapter_count = 0
    current_chapter: str | None = None
    for paragraph_text in paragraph_texts:
        chapter_label = detect_chapter_label(paragraph_text)
        if chapter_label is not None and chapter_label != current_chapter:
            current_chapter = chapter_label
            chapter_count += 1
    return chapter_count


def detect_language(text: str) -> str | None:
    """
    @brief      Detect one stable language code from cleanup text.
    @param[in]  text Source text sample.
    @return     Detected language code or `None` when unavailable.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    sample = text.strip()
    if len(sample) < 20:
        return None
    try:
        return detect(sample[:5000])
    except LangDetectException:
        return None


def detect_chapter_label(paragraph_text: str) -> str | None:
    """
    @brief      Detect one chapter or scene label from a normalized paragraph.
    @param[in]  paragraph_text Candidate paragraph text.
    @return     Matched chapter label or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    normalized = paragraph_text.strip()
    if len(normalized) > 100:
        return None
    for pattern in _CHAPTER_PATTERNS:
        if pattern.fullmatch(normalized):
            return normalized
    return None


def format_dialogue_lines(paragraph_text: str) -> str:
    """
    @brief      Insert stable line breaks into dialogue-like paragraph text.
    @param[in]  paragraph_text Candidate paragraph text.
    @return     Dialogue-formatted paragraph text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    normalized = paragraph_text.strip()
    normalized = _DIALOGUE_BREAK_AFTER_PUNCTUATION_PATTERN.sub(r"\1\n- ", normalized)
    normalized = _DIALOGUE_BREAK_AFTER_ATTRIBUTION_PATTERN.sub(r"\1\n- ", normalized)
    return normalized


# END OF FILE
