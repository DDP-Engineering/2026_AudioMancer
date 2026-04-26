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
@details Centralizes Unicode-aware line normalization, script classification,
         chapter-label detection, language detection, and dialogue formatting
         shared by deterministic and AI-assisted cleanup so both pipelines use
         one consistent implementation.
@author Eng. Dan Dumitru Pasare
@date 2026-04-22
@version 0.2.0
"""

# IMPORTS

import re
import unicodedata

from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException

# CONSTANTS

# @brief Unicode whitespace normalization pattern used before comparisons.
_WHITESPACE_PATTERN = re.compile(r"\s+")
# @brief Supported-language chapter/scene/part labels used for structure detection only.
_CHAPTER_WORD_PATTERN = (
    r"chapter|capitolul|capitol|capítulo|capitulo|capitolo|chapitre|kapitel|глава|"
    r"scene|scena|escena|cena|scène|szene|сцена|part|partea|parte|partie|teil|часть"
)
# @brief Shared chapter-heading detection patterns for supported-language cleanup.
_CHAPTER_PATTERNS = (
    re.compile(rf"^(?:{_CHAPTER_WORD_PATTERN})\s+[\wIVXLCDM0-9][\wIVXLCDM0-9 .:-]*$", re.IGNORECASE),
    re.compile(r"^第\s*[0-9０-９一二三四五六七八九十百千〇零壱弐参]+\s*[章节章節回卷部幕场場話话].*$"),
    re.compile(r"^(?:제\s*)?[0-9０-９]+\s*(?:장|화|부|막).*$"),
    re.compile(r"^[IVXLCDM]+$", re.IGNORECASE),
)
# @brief Sentence-ending punctuation accepted across supported language scripts.
_SENTENCE_TERMINAL_CHARACTERS = frozenset(".!?\u2026。！？｡．")
# @brief Closing marks ignored while checking whether a line ends a sentence.
_CLOSING_SENTENCE_MARKS = frozenset("\"'»”’)]}）】》」』〉")
# @brief Dialogue formatter rule that inserts breaks before spoken text after punctuation.
_DIALOGUE_BREAK_AFTER_PUNCTUATION_PATTERN = re.compile(r'([:;.!?\u2026。！？｡．]["»”\']?)\s+[-–—]\s+(?=\S)')
# @brief Dialogue formatter rule that inserts breaks after attributions and pauses.
_DIALOGUE_BREAK_AFTER_ATTRIBUTION_PATTERN = re.compile(r"([,:])\s+[-–—]\s+(?=\S)")
# @brief Header/footer comparison cleanup patterns that strip page-number suffixes.
_HEADER_FOOTER_PAGE_AFFIX_PATTERNS = (
    re.compile(r"^(.+?)\s*[-–—]\s*(?:page\s+)?\d+(?:\s*(?:/|of)\s*\d+)?\.?$", re.IGNORECASE),
    re.compile(r"^(?:page\s+)?\d+(?:\s*(?:/|of)\s*\d+)?\.?\s*[-–—]\s*(.+)$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+第\s*[0-9０-９一二三四五六七八九十百千〇零]+\s*[页頁]$"),
)


# PUBLIC API


def normalize_text_line(line: str) -> str:
    """
    @brief      Normalize one text line for deterministic cleanup processing.
    @param[in]  line Source line.
    @return     NFKC-normalized line with collapsed whitespace.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    normalized = unicodedata.normalize("NFKC", str(line))
    return _WHITESPACE_PATTERN.sub(" ", normalized).strip()


def normalized_compare_key(line: str) -> str:
    """
    @brief      Build one casefolded comparison key for cleanup matching.
    @param[in]  line Source line.
    @return     Stable normalized comparison key.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return normalize_text_line(line).casefold()


def normalized_header_footer_key(line: str) -> str:
    """
    @brief      Build one repeated-header/footer key with page affixes removed.
    @param[in]  line Candidate page-edge line.
    @return     Conservative comparison key or an empty string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    normalized = normalize_text_line(line)
    for pattern in _HEADER_FOOTER_PAGE_AFFIX_PATTERNS:
        match = pattern.fullmatch(normalized)
        if match is None:
            continue
        candidate = normalize_text_line(match.group(1))
        if _has_semantic_text(candidate):
            return candidate.casefold()
    return normalized.casefold()


def classify_text_script(text: str) -> str:
    """
    @brief      Classify the dominant writing script in one text fragment.
    @param[in]  text Source text fragment.
    @return     One of `latin`, `cyrillic`, `cjk`, `hangul`, `mixed`, or `unknown`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    counts = {"latin": 0, "cyrillic": 0, "cjk": 0, "hangul": 0}
    for character in text:
        script_name = _script_name_for_character(character)
        if script_name in counts:
            counts[script_name] += 1
    total = sum(counts.values())
    if total == 0:
        return "unknown"
    dominant_script, dominant_count = max(counts.items(), key=lambda item: item[1])
    if dominant_count / total >= 0.6:
        return dominant_script
    return "mixed"


def has_sentence_terminal(text: str) -> bool:
    """
    @brief      Determine whether one line ends with supported sentence punctuation.
    @param[in]  text Source line.
    @return     True when the line has a sentence-terminal suffix.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    normalized = normalize_text_line(text)
    while normalized and normalized[-1] in _CLOSING_SENTENCE_MARKS:
        normalized = normalized[:-1].rstrip()
    if not normalized:
        return False
    return normalized[-1] in _SENTENCE_TERMINAL_CHARACTERS or normalized.endswith("...")


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
    @version    0.1.1
    """
    sample = normalize_text_line(text)
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
    @version    0.2.0
    """
    normalized = normalize_text_line(paragraph_text)
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
    @version    0.2.0
    """
    normalized = str(paragraph_text).strip()
    normalized = _DIALOGUE_BREAK_AFTER_PUNCTUATION_PATTERN.sub(r"\1\n- ", normalized)
    normalized = _DIALOGUE_BREAK_AFTER_ATTRIBUTION_PATTERN.sub(r"\1\n- ", normalized)
    return normalized


# HELPER FUNCTIONS


def _has_semantic_text(text: str) -> bool:
    """
    @brief      Determine whether text contains non-page semantic characters.
    @param[in]  text Candidate text.
    @return     True when alphabetic or CJK/Hangul characters are present.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return any(character.isalpha() or _script_name_for_character(character) in {"cjk", "hangul"} for character in text)


def _script_name_for_character(character: str) -> str:
    """
    @brief      Resolve one character to a coarse cleanup script group.
    @param[in]  character Single character to classify.
    @return     Script group name or `unknown`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    codepoint = ord(character)
    if 0x0041 <= codepoint <= 0x024F or 0x1E00 <= codepoint <= 0x1EFF:
        return "latin"
    if 0x0400 <= codepoint <= 0x052F:
        return "cyrillic"
    if (
        0x3040 <= codepoint <= 0x30FF
        or 0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0xFF66 <= codepoint <= 0xFF9F
    ):
        return "cjk"
    if 0x1100 <= codepoint <= 0x11FF or 0x3130 <= codepoint <= 0x318F or 0xAC00 <= codepoint <= 0xD7AF:
        return "hangul"
    return "unknown"


# END OF FILE
