#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file descriptors.py
@brief Validate source-anchored AI boundary descriptors.
@details Only consecutive anchored ranges can commit; model text is never used as book content.
"""

# IMPORTS

import unicodedata

# CONSTANTS

_ANCHOR_WORD_LIMIT = 8
_ANCHOR_MIN_CONSECUTIVE_WORDS = 5

# PUBLIC API


def _build_response_schema() -> dict[str, object]:
    """
    @brief      Build the strict AI chunk descriptor response schema.
    @return     Provider structured-output schema.
    @exception  None.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["chunks"],
        "properties": {
            "chunks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "start_paragraph",
                        "start_text",
                        "break_after_paragraph",
                    ],
                    "properties": {
                        "start_paragraph": {"type": "integer", "minimum": 1},
                        "start_text": {"type": "string", "minLength": 1},
                        "break_after_paragraph": {"type": "integer", "minimum": 1},
                    },
                },
            },
        },
    }


def _paragraph_start_anchor(paragraph_text: str) -> str:
    """
    @brief      Build the canonical start anchor for one paragraph.
    @param[in]  paragraph_text Canonical paragraph text.
    @return     First eight normalized words, or the whole shorter paragraph.
    @exception  None.
    """
    return " ".join(str(paragraph_text).split()[:_ANCHOR_WORD_LIMIT])


def _normalized_anchor_words(anchor_text: str) -> list[str]:
    """
    @brief      Canonicalize anchor words for tolerant deterministic comparison.
    @param[in]  anchor_text Source or model-returned anchor text.
    @return     Up to eight case-folded compatibility-normalized words without punctuation.
    @exception  None.
    """
    normalized_text = unicodedata.normalize("NFKC", str(anchor_text)).casefold()
    normalized_words: list[str] = []
    for raw_word in normalized_text.split():
        normalized_word = "".join(character for character in raw_word if character.isalnum())
        if normalized_word:
            normalized_words.append(normalized_word)
        if len(normalized_words) == _ANCHOR_WORD_LIMIT:
            break
    return normalized_words


def _normalized_complete_anchor(anchor_text: str) -> str:
    """
    @brief      Canonicalize one complete anchor while retaining punctuation.
    @param[in]  anchor_text Source or model-returned anchor text.
    @return     Compatibility-normalized, case-folded, whitespace-collapsed anchor.
    @exception  None.
    """
    normalized_text = unicodedata.normalize("NFKC", str(anchor_text)).casefold()
    return " ".join(normalized_text.split())


def _start_anchor_matches(paragraph_text: str, returned_anchor: str) -> bool:
    """
    @brief      Confirm a model anchor against its declared source paragraph.
    @param[in]  paragraph_text Canonical source paragraph text.
    @param[in]  returned_anchor Model-returned start anchor.
    @return     True for an exact punctuation anchor, a complete short match, or a five-word run.
    @exception  None.
    """
    expected_words = _normalized_anchor_words(_paragraph_start_anchor(paragraph_text))
    returned_words = _normalized_anchor_words(returned_anchor)
    if not expected_words:
        expected_anchor = _normalized_complete_anchor(_paragraph_start_anchor(paragraph_text))
        return bool(expected_anchor) and (_normalized_complete_anchor(returned_anchor) == expected_anchor)
    if len(expected_words) < _ANCHOR_MIN_CONSECUTIVE_WORDS:
        return returned_words == expected_words

    longest_run = 0
    current_run = 0
    for expected_word, returned_word in zip(expected_words, returned_words, strict=False):
        if returned_word == expected_word:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    return longest_run >= _ANCHOR_MIN_CONSECUTIVE_WORDS


def _validate_chunk_descriptor_prefix(
    response_payload: dict[str, object],
    paragraph_records: list[dict[str, object]],
    window_start_index: int,
    window_end_index: int,
) -> tuple[list[dict[str, int]], bool]:
    """
    @brief      Validate the longest consecutive descriptor prefix.
    @param[in]  response_payload Provider JSON response object.
    @param[in]  paragraph_records Full ordered paragraph record list.
    @param[in]  window_start_index Zero-based absolute first paragraph index.
    @param[in]  window_end_index Zero-based absolute last paragraph index.
    @return     Validated absolute prefix ranges and whole-response validity.
    @exception  None.
    """
    if set(response_payload) != {"chunks"}:
        return [], False
    raw_chunks = response_payload.get("chunks")
    if not isinstance(raw_chunks, list) or not raw_chunks:
        return [], False

    expected_start_paragraph = window_start_index + 1
    validated_ranges: list[dict[str, int]] = []
    required_fields = {"start_paragraph", "start_text", "break_after_paragraph"}
    for item in raw_chunks:
        if not isinstance(item, dict) or set(item) != required_fields:
            return validated_ranges, False
        start_paragraph = item.get("start_paragraph")
        break_after_paragraph = item.get("break_after_paragraph")
        start_text = item.get("start_text")
        if type(start_paragraph) is not int or type(break_after_paragraph) is not int:
            return validated_ranges, False
        if not isinstance(start_text, str):
            return validated_ranges, False
        if start_paragraph != expected_start_paragraph:
            return validated_ranges, False
        if not window_start_index + 1 <= start_paragraph <= window_end_index + 1:
            return validated_ranges, False
        if not start_paragraph <= break_after_paragraph <= window_end_index + 1:
            return validated_ranges, False
        paragraph_text = str(paragraph_records[start_paragraph - 1]["text"])
        if not _start_anchor_matches(paragraph_text, start_text):
            return validated_ranges, False
        validated_ranges.append(
            {
                "start_index": start_paragraph - 1,
                "end_index": break_after_paragraph - 1,
            }
        )
        expected_start_paragraph = break_after_paragraph + 1
    return validated_ranges, True


# END OF FILE
