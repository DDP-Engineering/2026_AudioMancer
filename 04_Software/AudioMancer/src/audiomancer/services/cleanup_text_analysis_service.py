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
"""

# IMPORTS

import re
import unicodedata

from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException

# CONSTANTS

# @brief Unicode whitespace normalization pattern used before comparisons.
_WHITESPACE_PATTERN = re.compile(r"\s+")
# @brief Repeated same-glyph separators accepted when no semantic text is present.
_SCENE_SEPARATOR_REPEAT_PATTERN = re.compile(
    r"(?P<marker>[*_~#=•·◆◇♦◊▪■□●○\-\u2013\u2014])"
    r"(?:\s*(?P=marker)){2,}"
)
# @brief Common singleton ornaments used as scene or section breaks in books.
_SCENE_SEPARATOR_SINGLETONS = frozenset(
    (
        "⁂",
        "❦",
        "❧",
        "☙",
        "※",
        "⁕",
        "✦",
        "✧",
    )
)
# @brief Supported-language chapter/scene/part labels used for structure detection only.
_CHAPTER_WORD_PATTERN = (
    r"chapter|capitolul|capitol|capítulo|capitulo|capitolo|chapitre|kapitel|глава|"
    r"scene|scena|escena|cena|scène|szene|сцена|part|partea|parte|partie|teil|часть"
)
# @brief Strict uppercase grammar for bare Roman-numeral chapter headings.
_ROMAN_NUMERAL_PATTERN = re.compile(
    r"(?=[MDCLXVI]+$)M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
)
# @brief Shared chapter-heading detection patterns for supported-language cleanup.
_CHAPTER_PATTERNS = (
    re.compile(rf"^(?:{_CHAPTER_WORD_PATTERN})\s+[\wIVXLCDM0-9][\wIVXLCDM0-9 .:-]*$", re.IGNORECASE),
    re.compile(r"^第\s*[0-9０-９一二三四五六七八九十百千〇零壱弐参]+\s*[章节章節回卷部幕场場話话].*$"),
    re.compile(r"^(?:제\s*)?[0-9０-９]+\s*(?:장|화|부|막).*$"),
    _ROMAN_NUMERAL_PATTERN,
)
# @brief Sentence-ending punctuation accepted across supported language scripts.
_SENTENCE_TERMINAL_CHARACTERS = frozenset(".!?\u2026。！？｡．؟")
# @brief Clause-level marks treated as boundaries only when finer spans are requested.
_CLAUSE_TERMINAL_CHARACTERS = frozenset(";:；：؛")
# @brief Terminals that end a sentence without requiring any following whitespace.
# @details CJK punctuation is written flush against the next sentence, so demanding a
#          trailing space would collapse a whole CJK paragraph into a single span.
_WIDE_SENTENCE_TERMINAL_CHARACTERS = frozenset("。！？｡．；：")
# @brief Closing marks ignored while checking whether a line ends a sentence.
_CLOSING_SENTENCE_MARKS = frozenset("\"'»”’)]}）】》」』〉")
# @brief Header/footer comparison cleanup patterns that strip page-number suffixes.
_HEADER_FOOTER_PAGE_AFFIX_PATTERNS = (
    re.compile(r"^(.+?)\s*[-–—]\s*(?:page\s+)?\d+(?:\s*(?:/|of)\s*\d+)?\.?$", re.IGNORECASE),
    re.compile(r"^(?:page\s+)?\d+(?:\s*(?:/|of)\s*\d+)?\.?\s*[-–—]\s*(.+)$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+第\s*[0-9０-９一二三四五六七八九十百千〇零]+\s*[页頁]$"),
)


# PUBLIC API


def is_scene_separator_artifact(
    text: str,
    role: str | None = None,
) -> bool:
    """
    @brief      Identify a non-narratable scene-separator paragraph.
    @details    An explicit Cleanup role is authoritative. Raw-text recovery is
                intentionally limited to repeated identical marker glyphs and
                known singleton ornaments so ambiguous punctuation remains
                narratable after user edits.
    @param[in]  text Candidate paragraph text.
    @param[in]  role Optional Cleanup paragraph role.
    @return     True when Chunking must treat the paragraph as a hard boundary.
    @exception  None
    """
    normalized_role = str(role or "body").strip().casefold()
    if normalized_role == "scene_separator":
        return True
    if normalized_role not in {"", "body"}:
        return False
    normalized_text = normalize_text_line(text)
    if normalized_text in _SCENE_SEPARATOR_SINGLETONS:
        return True
    return bool(_SCENE_SEPARATOR_REPEAT_PATTERN.fullmatch(normalized_text))


def normalize_text_line(line: str) -> str:
    """
    @brief      Normalize one text line for deterministic cleanup processing.
    @param[in]  line Source line.
    @return     NFKC-normalized line with collapsed whitespace.
    @exception  None
    """
    normalized = unicodedata.normalize("NFKC", str(line))
    return _WHITESPACE_PATTERN.sub(" ", normalized).strip()


def normalized_compare_key(line: str) -> str:
    """
    @brief      Build one casefolded comparison key for cleanup matching.
    @param[in]  line Source line.
    @return     Stable normalized comparison key.
    @exception  None
    """
    return normalize_text_line(line).casefold()


def normalized_header_footer_key(line: str) -> str:
    """
    @brief      Build one repeated-header/footer key with page affixes removed.
    @param[in]  line Candidate page-edge line.
    @return     Conservative comparison key or an empty string.
    @exception  None
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
    """
    normalized = normalize_text_line(text)
    while normalized and normalized[-1] in _CLOSING_SENTENCE_MARKS:
        normalized = normalized[:-1].rstrip()
    if not normalized:
        return False
    return normalized[-1] in _SENTENCE_TERMINAL_CHARACTERS or normalized.endswith("...")


def sentence_spans(text: str, include_clause_marks: bool = False) -> list[str]:
    """
    @brief      Split text into ordered, source-preserving sentence spans.
    @details    Concatenating the returned spans reproduces the input exactly, so callers can
                slice the source without losing characters. Latin-script terminals require
                following whitespace, which keeps decimals such as `3.14` intact, while CJK
                terminals end a span immediately because they carry no trailing space.
    @param[in]  text Source text fragment.
    @param[in]  include_clause_marks True to also break on clause marks such as `;` and `:`.
    @return     Ordered spans whose concatenation equals the input.
    @exception  None
    """
    source_text = str(text)
    if not source_text:
        return []
    terminal_characters = _SENTENCE_TERMINAL_CHARACTERS
    if include_clause_marks:
        terminal_characters = terminal_characters | _CLAUSE_TERMINAL_CHARACTERS

    spans: list[str] = []
    span_start = 0
    index = 0
    text_length = len(source_text)
    while index < text_length:
        if source_text[index] not in terminal_characters:
            index += 1
            continue
        run_end = index
        while run_end < text_length and source_text[run_end] in terminal_characters:
            run_end += 1
        ends_without_space = any(
            character in _WIDE_SENTENCE_TERMINAL_CHARACTERS for character in source_text[index:run_end]
        )
        cursor = run_end
        while cursor < text_length and source_text[cursor] in _CLOSING_SENTENCE_MARKS:
            cursor += 1
        whitespace_end = cursor
        while whitespace_end < text_length and source_text[whitespace_end].isspace():
            whitespace_end += 1
        if not (ends_without_space or whitespace_end > cursor or cursor >= text_length):
            index = cursor
            continue
        boundary = whitespace_end
        spans.append(source_text[span_start:boundary])
        span_start = boundary
        index = boundary
    if span_start < text_length:
        spans.append(source_text[span_start:])
    return [span for span in spans if span]


def detect_language(text: str) -> str | None:
    """
    @brief      Detect one stable language code from cleanup text.
    @param[in]  text Source text sample.
    @return     Detected language code or `None` when unavailable.
    @exception  None
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
    """
    normalized = normalize_text_line(paragraph_text)
    if len(normalized) > 100:
        return None
    for pattern in _CHAPTER_PATTERNS:
        if pattern.fullmatch(normalized):
            return normalized
    return None


# HELPER FUNCTIONS


def _has_semantic_text(text: str) -> bool:
    """
    @brief      Determine whether text contains non-page semantic characters.
    @param[in]  text Candidate text.
    @return     True when alphabetic or CJK/Hangul characters are present.
    @exception  None
    """
    return any(character.isalpha() or _script_name_for_character(character) in {"cjk", "hangul"} for character in text)


def _script_name_for_character(character: str) -> str:
    """
    @brief      Resolve one character to a coarse cleanup script group.
    @param[in]  character Single character to classify.
    @return     Script group name or `unknown`.
    @exception  None
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
