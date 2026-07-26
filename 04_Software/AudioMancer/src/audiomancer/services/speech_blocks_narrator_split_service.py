#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file speech_blocks_narrator_split_service.py
@brief Deterministic same-narrator Speech Blocks segmentation.
@details Packs whole sentences of one source chunk into evenly sized narration
         blocks without calling a model. Sentences are never cut, quoted
         passages are never opened, and the concatenated block source text
         reproduces the chunk exactly. Blocks that a single oversized sentence
         pushes past the TTS budget are flagged and left intact, because Audio
         Blocks splits them again at generation time against the real loaded
         model budget.
@author Eng. Dan Dumitru Pasare
@date 2026-07-26
@version 0.1.0
"""

# IMPORTS

import math

from audiomancer.services import cleanup_text_analysis_service, tts_budget_service

# CONSTANTS

# @brief Warning flag raised when one sentence alone exceeds the safe TTS budget.
NARRATOR_BUDGET_EXCEEDED_FLAG = "tts_budget_exceeded"

# @brief Opening delimiters mapped to the closing delimiter they expect.
# @details A same-narrator block must never begin or end inside an open quotation, so the
#          splitter tracks nesting rather than counting characters.
_OPENING_TO_CLOSING_QUOTE = {
    "“": "”",
    "„": "”",
    "«": "»",
    "‹": "›",
    "「": "」",
    "『": "』",
    "《": "》",
    "〈": "〉",
}

# @brief Straight quote handled as a toggle because it opens and closes with one character.
_TOGGLE_QUOTE = '"'

# @brief Closing marks that belong to the sentence they follow.
_TRAILING_CLOSING_MARKS = "\"'»”’)]}）】》」』〉"

# @brief Longest token before a period still treated as an abbreviation rather than a sentence end.
_ABBREVIATION_MAX_LENGTH = 3

# @brief Fraction of the target below which a trailing block is merged back into its predecessor.
_ORPHAN_BLOCK_FRACTION = 0.25

NarratorBlockPayload = dict[str, object]


# PUBLIC API


def open_quote_stack(text: str) -> list[str]:
    """
    @brief      Track quotation delimiters still open at the end of one text prefix.
    @param[in]  text Source prefix inspected up to a candidate boundary.
    @return     Closing delimiters the prefix still owes, outermost first.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    stack: list[str] = []
    for character in str(text):
        if character == _TOGGLE_QUOTE:
            if stack and stack[-1] == _TOGGLE_QUOTE:
                stack.pop()
            else:
                stack.append(_TOGGLE_QUOTE)
            continue
        if character in _OPENING_TO_CLOSING_QUOTE:
            stack.append(_OPENING_TO_CLOSING_QUOTE[character])
            continue
        if stack and character == stack[-1]:
            stack.pop()
    return stack


def plan_narrator_blocks(
    chunk_text: str,
    target_units: int,
    minimum_units: int | None = None,
    script_name: str | None = None,
) -> list[NarratorBlockPayload]:
    """
    @brief      Split one source chunk into evenly sized same-narrator blocks.
    @details    Sentences are the atomic unit, so no block ever ends mid-sentence. Sentence
                boundaries that fall inside an open quotation, or that follow an
                abbreviation, are not offered as block boundaries at all.
    @param[in]  chunk_text Exact source chunk text, normally one paragraph.
    @param[in]  target_units Preferred budget units per block.
    @param[in]  minimum_units Optional floor below which a trailing block is merged back.
    @param[in]  script_name Optional pre-classified dominant writing script.
    @return     Ordered block payloads whose `source_text` values concatenate to the input.
    @exception  ValueError Raised when the planned blocks would not reproduce the input.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    source_text = str(chunk_text)
    if not source_text.strip():
        return []
    resolved_target = max(1, int(target_units))
    resolved_minimum = (
        int(minimum_units) if minimum_units is not None else int(resolved_target * _ORPHAN_BLOCK_FRACTION)
    )
    resolved_script = script_name or cleanup_text_analysis_service.classify_text_script(source_text)

    atomic_spans = _atomic_sentence_spans(source_text)
    packed_spans = _pack_spans(atomic_spans, resolved_target, resolved_script)
    packed_spans = _absorb_orphan_tail(packed_spans, resolved_target, resolved_minimum, resolved_script)

    blocks = [_build_block(span_text, resolved_target, resolved_script) for span_text in packed_spans]
    _verify_source_coverage(source_text, blocks)
    return blocks


# INTERNAL HELPERS


def _atomic_sentence_spans(source_text: str) -> list[str]:
    """
    @brief      Build the smallest spans a same-narrator block may start or end on.
    @details    Sentence spans are merged forward whenever splitting after them would open a
                quotation or cut an abbreviation away from its sentence.
    @param[in]  source_text Exact source chunk text.
    @return     Ordered spans whose concatenation equals the input.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    sentence_spans = cleanup_text_analysis_service.sentence_spans(source_text)
    atomic_spans: list[str] = []
    pending = ""
    consumed = 0
    for sentence_span in sentence_spans:
        pending += sentence_span
        consumed += len(sentence_span)
        if consumed >= len(source_text):
            break
        if open_quote_stack(source_text[:consumed]):
            continue
        if _ends_with_abbreviation(pending):
            continue
        atomic_spans.append(pending)
        pending = ""
    if pending:
        atomic_spans.append(pending)
    return atomic_spans


def _ends_with_abbreviation(span_text: str) -> bool:
    """
    @brief      Detect a span whose final period abbreviates a word instead of ending a sentence.
    @details    Purely structural, so it behaves the same in every alphabetic language and is
                inert for scripts without letter case. Over-merging is harmless because it only
                produces a slightly longer block; under-merging would cut a sentence in two.
    @param[in]  span_text Candidate sentence span.
    @return     True when the span most likely ends on an abbreviation.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    trimmed = str(span_text).rstrip()
    while trimmed and trimmed[-1] in _TRAILING_CLOSING_MARKS:
        trimmed = trimmed[:-1].rstrip()
    if not trimmed.endswith("."):
        return False
    token = ""
    for character in reversed(trimmed[:-1]):
        if not character.isalpha():
            break
        token = character + token
    if not token or len(token) > _ABBREVIATION_MAX_LENGTH:
        return False
    return token[0].isupper()


def _pack_spans(atomic_spans: list[str], target_units: int, script_name: str) -> list[str]:
    """
    @brief      Pack atomic spans into evenly sized blocks that stay inside the target budget.
    @details    Filling every block to the maximum leaves the remainder stranded in a short
                final block, which breaks the even rhythm continuous narration depends on.
                The chunk is therefore packed toward the average of the blocks it actually
                needs rather than toward the ceiling.
    @param[in]  atomic_spans Ordered atomic spans.
    @param[in]  target_units Maximum budget units per block.
    @param[in]  script_name Dominant writing script.
    @return     Ordered packed block texts.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.2.0
    """
    total_units = tts_budget_service.estimate_budget_units("".join(atomic_spans), script_name)
    block_count = max(1, math.ceil(total_units / target_units))
    effective_target = max(1, math.ceil(total_units / block_count))

    packed_spans: list[str] = []
    current = ""
    for atomic_span in atomic_spans:
        if not current:
            current = atomic_span
            continue
        if tts_budget_service.estimate_budget_units(current + atomic_span, script_name) > effective_target:
            packed_spans.append(current)
            current = atomic_span
            continue
        current += atomic_span
    if current:
        packed_spans.append(current)
    return packed_spans


def _absorb_orphan_tail(
    packed_spans: list[str],
    target_units: int,
    minimum_units: int,
    script_name: str,
) -> list[str]:
    """
    @brief      Merge a very short trailing block back into its predecessor.
    @details    Greedy packing otherwise leaves a few stranded words as their own block at the
                end of most paragraphs, which reads as an abrupt stop in continuous narration.
    @param[in]  packed_spans Ordered packed block texts.
    @param[in]  target_units Preferred budget units per block.
    @param[in]  minimum_units Floor below which the trailing block is absorbed.
    @param[in]  script_name Dominant writing script.
    @return     Ordered packed block texts with any orphan tail absorbed.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    if len(packed_spans) < 2 or minimum_units <= 0:
        return packed_spans
    if tts_budget_service.estimate_budget_units(packed_spans[-1], script_name) >= minimum_units:
        return packed_spans
    merged = packed_spans[-2] + packed_spans[-1]
    if tts_budget_service.estimate_budget_units(merged, script_name) > target_units:
        return packed_spans
    return [*packed_spans[:-2], merged]


def _build_block(span_text: str, target_units: int, script_name: str) -> NarratorBlockPayload:
    """
    @brief      Build one narrator block payload from an exact source span.
    @param[in]  span_text Exact source span for this block.
    @param[in]  target_units Preferred budget units per block.
    @param[in]  script_name Dominant writing script.
    @return     Block payload with exact source text, spoken text, and warning flags.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    warning_flags: list[str] = []
    if tts_budget_service.estimate_budget_units(span_text, script_name) > target_units:
        warning_flags.append(NARRATOR_BUDGET_EXCEEDED_FLAG)
    return {
        "source_text": span_text,
        "text": span_text.strip(),
        "warning_flags": warning_flags,
    }


def _verify_source_coverage(source_text: str, blocks: list[NarratorBlockPayload]) -> None:
    """
    @brief      Guarantee the planned blocks reproduce the source chunk character for character.
    @details    Enforced at runtime, not only in tests: silently dropping source text would
                remove sentences from the finished audiobook.
    @param[in]  source_text Exact source chunk text.
    @param[in]  blocks Planned block payloads.
    @return     None.
    @exception  ValueError Raised when the blocks do not reproduce the source chunk.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    rebuilt = "".join(str(block.get("source_text", "")) for block in blocks)
    if rebuilt != source_text:
        raise ValueError("Deterministic narrator splitting did not preserve the source chunk text.")


# END OF FILE
