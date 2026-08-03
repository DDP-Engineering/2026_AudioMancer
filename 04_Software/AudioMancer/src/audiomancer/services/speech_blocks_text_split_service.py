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

_CANDIDATE_KIND_DIALOGUE = "dialogue_candidate"
_CANDIDATE_KIND_NARRATION = "narration_candidate"
_CANDIDATE_KIND_ATTRIBUTION = "attribution_candidate"
_CANDIDATE_KIND_MIXED = "mixed_candidate"

_ATOMIC_KIND_DIALOGUE = "dialogue"
_ATOMIC_KIND_ATTRIBUTION = "attribution"
_ATOMIC_KIND_NARRATION = "narration"
_ATOMIC_KIND_SEPARATOR = "separator"
_ATOMIC_KIND_MIXED = "mixed"

_DIALOGUE_QUOTE_PAIRS = {
    '"': '"',
    "'": "'",
    "“": "”",
    "‘": "’",
    "«": "»",
    "»": "«",
    "„": "“",
    "‚": "‘",
    "「": "」",
    "『": "』",
    "《": "》",
    "〈": "〉",
}
_DIALOGUE_DASHES = ("-", "–", "—", "―")
_DIALOGUE_TRAILING_PUNCTUATION = set(',.!?;:，。！？；：、"”’»«」』》〉')

_MAX_NARRATION_SENTENCE_SOURCE_SPANS = 24

_ATOMIC_DIALOGUE_QUOTE_PAIRS = {
    '"': '"',
    "'": "'",
    "“": "”",
    "‘": "’",
    "„": "”",
    "‚": "‘",
    "«": "»",
    "»": "«",
    "‹": "›",
    "「": "」",
    "『": "』",
    "《": "》",
    "〈": "〉",
}

_ATOMIC_DIALOGUE_QUOTE_CLOSERS = {
    '"': ('"',),
    "'": ("'",),
    "“": ("”",),
    "‘": ("’",),
    "„": ("”", "“"),
    "‚": ("‘",),
    "«": ("»",),
    "»": ("«",),
    "‹": ("›",),
    "「": ("」",),
    "『": ("』",),
    "《": ("》",),
    "〈": ("〉",),
}

_ATTRIBUTION_VERBS = (
    "said",
    "asked",
    "answered",
    "replied",
    "whispered",
    "shouted",
    "called",
    "muttered",
    "snapped",
    "demanded",
    "cried",
    "spuse",
    "zise",
    "intreba",
    "întrebă",
    "intrebă",
    "întreba",
    "raspunse",
    "răspunse",
    "sopti",
    "șopti",
    "sopti",
    "striga",
    "strigă",
    "dit",
    "demanda",
    "demande",
    "répondit",
    "repondit",
    "murmura",
    "dijo",
    "pregunto",
    "preguntó",
    "respondio",
    "respondió",
    "sagte",
    "fragte",
    "antwortete",
    "disse",
    "chiese",
    "rispose",
)

# PUBLIC API


def build_source_spans(text: str) -> list[dict[str, object]]:
    """
    @brief      Build deterministic source spans for Speech Blocks model selection.
    @param[in]  text Active source chunk or AI-budget segment text.
    @return     Ordered source-span payloads with stable IDs, offsets, exact text, and candidate kind.
    @exception  None
    """
    source_text = str(text)
    if not source_text:
        return []

    spans: list[dict[str, object]] = []
    for paragraph_start, paragraph_end in _paragraph_ranges(source_text):
        paragraph = source_text[paragraph_start:paragraph_end]
        if _is_dash_dialogue_paragraph(paragraph):
            _append_dash_dialogue_source_spans(spans, source_text, paragraph_start, paragraph_end)
            continue

        dialogue_ranges = _quote_dialogue_ranges(paragraph)
        if not dialogue_ranges:
            _append_narration_source_spans(spans, source_text, paragraph_start, paragraph_end)
            continue

        cursor = 0
        for dialogue_start, dialogue_end in dialogue_ranges:
            if dialogue_start > cursor:
                _append_source_span(
                    spans,
                    source_text,
                    paragraph_start + cursor,
                    paragraph_start + dialogue_start,
                    _candidate_kind_for_context_span(paragraph[cursor:dialogue_start]),
                )
            _append_source_span(
                spans,
                source_text,
                paragraph_start + dialogue_start,
                paragraph_start + dialogue_end,
                _CANDIDATE_KIND_DIALOGUE,
            )
            cursor = dialogue_end
        if cursor < len(paragraph):
            _append_source_span(
                spans,
                source_text,
                paragraph_start + cursor,
                paragraph_end,
                _candidate_kind_for_context_span(paragraph[cursor:]),
            )

    return _renumber_source_spans(spans)


def build_atomic_speech_units(
    text: str,
    source_spans: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """
    @brief      Build deterministic atomic speech units for Speech Blocks speaker assignment.
    @param[in]  text Active source chunk or AI-budget segment text.
    @param[in]  source_spans Optional source-span provenance rows.
    @return     Ordered atomic-unit payloads with stable IDs, offsets, exact text, and structural kind.
    @exception  None
    """
    source_text = str(text)
    if not source_text:
        return []
    span_payloads = source_spans if isinstance(source_spans, list) and source_spans else build_source_spans(source_text)
    atomic_units: list[dict[str, object]] = []
    for raw_span in span_payloads:
        if not isinstance(raw_span, dict):
            continue
        source_span_id = str(raw_span.get("source_span_id", raw_span.get("id", ""))).strip()
        try:
            span_start = int(raw_span.get("start_offset", 0))
            span_end = int(raw_span.get("end_offset", span_start))
        except (TypeError, ValueError):
            continue
        if span_start < 0 or span_end <= span_start or span_end > len(source_text):
            continue
        span_text = str(raw_span.get("text", source_text[span_start:span_end]))
        if span_text != source_text[span_start:span_end]:
            span_text = source_text[span_start:span_end]
        for local_start, local_end, structural_kind in _atomic_ranges(span_text):
            if local_end <= local_start:
                continue
            _append_atomic_unit(
                atomic_units,
                source_text,
                source_span_id,
                span_start + local_start,
                span_start + local_end,
                structural_kind,
            )
    return _renumber_atomic_units(_coalesce_atomic_units(atomic_units))


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
    return [match.group(0) for match in re.finditer(r"\S+\s*", str(text)) if match.group(0)]


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


def _paragraph_ranges(text: str) -> list[tuple[int, int]]:
    """
    @brief      Return paragraph-like ranges without crossing blank-line boundaries.
    @param[in]  text Source text.
    @return     Ordered `(start, end)` ranges.
    @exception  None
    """
    source_text = str(text)
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for match in re.finditer(r"\r?\n[ \t]*\r?\n+", source_text):
        end_offset = match.end()
        if cursor < end_offset:
            ranges.append((cursor, end_offset))
        cursor = end_offset
    if cursor < len(source_text):
        ranges.append((cursor, len(source_text)))
    return ranges


def _atomic_ranges(text: str) -> list[tuple[int, int, str]]:
    """
    @brief      Split one source-span text into atomic dialogue, attribution, narration, or separator ranges.
    @param[in]  text Source-span text.
    @return     Ordered local `(start, end, structural_kind)` ranges.
    @exception  None
    """
    source_text = str(text)
    if not source_text:
        return []
    if _span_is_dash_led_dialogue(source_text):
        return _coalesce_atomic_ranges(_dash_atomic_ranges(source_text))

    dialogue_ranges = _atomic_quote_dialogue_ranges(source_text)
    if not dialogue_ranges:
        return [(0, len(source_text), _atomic_context_kind(source_text))]

    ranges: list[tuple[int, int, str]] = []
    cursor = 0
    for dialogue_start, dialogue_end in dialogue_ranges:
        if dialogue_start > cursor:
            ranges.append((cursor, dialogue_start, _atomic_context_kind(source_text[cursor:dialogue_start])))
        ranges.append((dialogue_start, dialogue_end, _ATOMIC_KIND_DIALOGUE))
        cursor = dialogue_end
    if cursor < len(source_text):
        ranges.append((cursor, len(source_text), _atomic_context_kind(source_text[cursor:])))
    return _coalesce_atomic_ranges(ranges)


def _span_is_dash_led_dialogue(text: str) -> bool:
    """
    @brief      Return whether text starts with a dialogue dash after leading whitespace.
    @param[in]  text Candidate source-span text.
    @return     True when the span is dash-led dialogue.
    @exception  None
    """
    stripped_text = str(text).lstrip()
    return bool(stripped_text) and _is_dialogue_dash_character(stripped_text[0])


def _dash_atomic_ranges(text: str) -> list[tuple[int, int, str]]:
    """
    @brief      Split dash-led dialogue into dialogue and inline attribution ranges.
    @param[in]  text Dash-led source-span text.
    @return     Ordered local `(start, end, structural_kind)` ranges.
    @exception  None
    """
    source_text = str(text)
    marker_offsets = [
        offset
        for offset, character in enumerate(source_text)
        if _dash_marker_is_dialogue_boundary(source_text, offset, character)
    ]
    if not marker_offsets:
        return [(0, len(source_text), _atomic_context_kind(source_text))]

    ranges: list[tuple[int, int, str]] = []
    for index, marker_offset in enumerate(marker_offsets):
        segment_end = marker_offsets[index + 1] if index + 1 < len(marker_offsets) else len(source_text)
        segment_start = marker_offset
        while segment_start > 0 and source_text[segment_start - 1].isspace():
            segment_start -= 1
        segment_text = source_text[segment_start:segment_end]
        split_offset = _dash_dialogue_attribution_split_offset(segment_text)
        if split_offset <= 0:
            ranges.append((segment_start, segment_end, _ATOMIC_KIND_DIALOGUE))
            continue
        ranges.append((segment_start, segment_start + split_offset, _ATOMIC_KIND_DIALOGUE))
        if segment_start + split_offset < segment_end:
            ranges.append((segment_start + split_offset, segment_end, _ATOMIC_KIND_ATTRIBUTION))
    return ranges


def _dash_dialogue_attribution_split_offset(segment_text: str) -> int:
    """
    @brief      Return the local split between dash dialogue and inline attribution.
    @param[in]  segment_text One dash-led dialogue segment.
    @return     Split offset, or zero when no inline attribution is visible.
    @exception  None
    """
    text = str(segment_text)
    for match in re.finditer(r"[.!?…]\s+", text):
        tail = text[match.end() :]
        if _looks_like_attribution(tail):
            return match.end()
    return 0


def _atomic_quote_dialogue_ranges(text: str) -> list[tuple[int, int]]:
    """
    @brief      Return quoted dialogue ranges for atomic unit splitting.
    @param[in]  text Source-span text.
    @return     Ordered local `(start, end)` dialogue ranges.
    @exception  None
    """
    source_text = str(text)
    ranges: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(source_text):
        opener = source_text[cursor]
        closers = _ATOMIC_DIALOGUE_QUOTE_CLOSERS.get(opener)
        if not closers or not _quote_opener_is_plausible(source_text, cursor):
            cursor += 1
            continue
        close_indices = [
            close_index
            for close_index in (source_text.find(closer, cursor + 1) for closer in closers)
            if close_index >= 0
        ]
        close_index = min(close_indices) if close_indices else -1
        if close_index < 0:
            cursor += 1
            continue
        if _quoted_range_looks_like_dialogue(source_text, cursor, close_index + 1):
            ranges.append((cursor, close_index + 1))
        cursor = close_index + 1
    return ranges


def _quoted_range_looks_like_dialogue(text: str, start_offset: int, end_offset: int) -> bool:
    """
    @brief      Return whether one quoted range looks like spoken dialogue.
    @param[in]  text Full source text containing the quoted range.
    @param[in]  start_offset Inclusive quote opener offset.
    @param[in]  end_offset Exclusive quote closer offset.
    @return     True when punctuation or nearby attribution supports dialogue.
    @exception  None
    """
    source_text = str(text)
    quoted_text = source_text[int(start_offset) + 1 : max(int(end_offset) - 1, int(start_offset) + 1)].strip()
    if not quoted_text:
        return False
    if any(character in quoted_text for character in ",.!?;:，。！？；：、"):
        return True
    before_context = _local_quote_context_before(source_text, int(start_offset))
    after_context = _local_quote_context_after(source_text, int(end_offset))
    return _looks_like_attribution(before_context) or _looks_like_attribution(after_context)


def _local_quote_context_before(text: str, start_offset: int) -> str:
    """
    @brief      Return local same-sentence text before a quote opener.
    @param[in]  text Source text.
    @param[in]  start_offset Quote opener offset.
    @return     Same-sentence prefix near the quote.
    @exception  None
    """
    source_text = str(text)
    sentence_start = max(
        source_text.rfind(boundary, 0, int(start_offset)) for boundary in (".", "!", "?", "\n")
    )
    return source_text[sentence_start + 1 : int(start_offset)]


def _local_quote_context_after(text: str, end_offset: int) -> str:
    """
    @brief      Return local same-sentence text after a quote closer.
    @param[in]  text Source text.
    @param[in]  end_offset Quote closer-exclusive offset.
    @return     Same-sentence suffix near the quote.
    @exception  None
    """
    source_text = str(text)
    sentence_ends = [
        sentence_end
        for sentence_end in (source_text.find(boundary, int(end_offset)) for boundary in (".", "!", "?", "\n"))
        if sentence_end >= 0
    ]
    sentence_end = min(sentence_ends) if sentence_ends else len(source_text)
    return source_text[int(end_offset) : sentence_end]


def _atomic_context_kind(text: str) -> str:
    """
    @brief      Classify context between atomic dialogue units.
    @param[in]  text Context text.
    @return     Atomic structural kind.
    @exception  None
    """
    stripped_text = str(text).strip()
    if not stripped_text:
        return _ATOMIC_KIND_SEPARATOR
    if stripped_text in {",", ";", ":", "،"}:
        return _ATOMIC_KIND_ATTRIBUTION
    if _looks_like_attribution(stripped_text):
        return _ATOMIC_KIND_ATTRIBUTION
    return _ATOMIC_KIND_NARRATION


def _coalesce_atomic_ranges(ranges: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """
    @brief      Merge adjacent atomic ranges that have the same structural kind.
    @param[in]  ranges Candidate atomic ranges.
    @return     Coalesced ordered ranges.
    @exception  None
    """
    coalesced_ranges: list[tuple[int, int, str]] = []
    for start_offset, end_offset, structural_kind in ranges:
        if coalesced_ranges and coalesced_ranges[-1][2] == structural_kind and coalesced_ranges[-1][1] == start_offset:
            previous_start, _previous_end, _previous_kind = coalesced_ranges[-1]
            coalesced_ranges[-1] = (previous_start, end_offset, structural_kind)
            continue
        coalesced_ranges.append((start_offset, end_offset, structural_kind))
    return coalesced_ranges


def _looks_like_attribution(text: str) -> bool:
    """
    @brief      Return whether text looks like dialogue attribution in supported languages.
    @param[in]  text Candidate context text.
    @return     True when the text contains a known attribution verb.
    @exception  None
    """
    normalized_text = " ".join(str(text).strip().casefold().split())
    if not normalized_text:
        return False
    return any(re.search(rf"(?<!\w){re.escape(verb)}(?!\w)", normalized_text) for verb in _ATTRIBUTION_VERBS)


def _append_atomic_unit(
    atomic_units: list[dict[str, object]],
    source_text: str,
    source_span_id: str,
    start_offset: int,
    end_offset: int,
    structural_kind: str,
) -> None:
    """
    @brief      Append one exact atomic unit.
    @param[in,out] atomic_units Mutable atomic-unit payload list.
    @param[in]  source_text Full source text.
    @param[in]  source_span_id Parent source-span identifier.
    @param[in]  start_offset Inclusive source-text start offset.
    @param[in]  end_offset Exclusive source-text end offset.
    @param[in]  structural_kind Atomic structural kind.
    @return     None.
    @exception  None
    """
    if end_offset <= start_offset:
        return
    atomic_units.append(
        {
            "atomic_unit_id": "",
            "source_span_id": str(source_span_id).strip(),
            "start_offset": int(start_offset),
            "end_offset": int(end_offset),
            "text": source_text[start_offset:end_offset],
            "structural_kind": str(structural_kind).strip() or _ATOMIC_KIND_NARRATION,
        }
    )


def _renumber_atomic_units(atomic_units: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Assign stable ordered atomic-unit identifiers.
    @param[in]  atomic_units Atomic units in source order.
    @return     New atomic-unit payload list with `uNNN` identifiers.
    @exception  None
    """
    renumbered_units: list[dict[str, object]] = []
    for index, unit in enumerate(atomic_units, start=1):
        atomic_unit = dict(unit)
        atomic_unit["atomic_unit_id"] = f"u{index:03d}"
        renumbered_units.append(atomic_unit)
    return renumbered_units


def _coalesce_atomic_units(atomic_units: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Merge contiguous atomic units that have the same structural kind.
    @param[in]  atomic_units Candidate atomic units.
    @return     Coalesced atomic units with exact text coverage preserved.
    @exception  None
    """
    coalesced_units: list[dict[str, object]] = []
    for atomic_unit in atomic_units:
        if (
            coalesced_units
            and coalesced_units[-1]["structural_kind"] == atomic_unit["structural_kind"]
            and int(coalesced_units[-1]["end_offset"]) == int(atomic_unit["start_offset"])
        ):
            previous_unit = dict(coalesced_units[-1])
            source_span_ids = [
                str(source_span_id).strip()
                for source_span_id in previous_unit.get("source_span_ids", [previous_unit.get("source_span_id", "")])
                if str(source_span_id).strip()
            ]
            next_source_span_id = str(atomic_unit.get("source_span_id", "")).strip()
            if next_source_span_id and next_source_span_id not in source_span_ids:
                source_span_ids.append(next_source_span_id)
            previous_unit["end_offset"] = int(atomic_unit["end_offset"])
            previous_unit["text"] = f"{previous_unit['text']}{atomic_unit['text']}"
            previous_unit["source_span_ids"] = source_span_ids
            coalesced_units[-1] = previous_unit
            continue
        coalesced_unit = dict(atomic_unit)
        coalesced_unit["source_span_ids"] = [str(atomic_unit.get("source_span_id", "")).strip()]
        coalesced_units.append(coalesced_unit)
    return coalesced_units


def _is_dash_dialogue_paragraph(paragraph: str) -> bool:
    """
    @brief      Return whether a paragraph begins with a common dialogue dash.
    @param[in]  paragraph Paragraph text.
    @return     True when the first non-space character is a dialogue dash.
    @exception  None
    """
    stripped_paragraph = str(paragraph).lstrip()
    return bool(stripped_paragraph) and _is_dialogue_dash_character(stripped_paragraph[0])


def _is_dialogue_dash_character(character: str) -> bool:
    """
    @brief      Return whether one character is a known dialogue dash marker.
    @param[in]  character Candidate character.
    @return     True when the character can introduce dash-led dialogue.
    @exception  None
    """
    return str(character) in {*_DIALOGUE_DASHES, "\u2013", "\u2014", "\u2015", "\u2e3a", "\u2e3b"}


def _append_dash_dialogue_source_spans(
    spans: list[dict[str, object]],
    source_text: str,
    paragraph_start: int,
    paragraph_end: int,
) -> None:
    """
    @brief      Append dash-led dialogue spans, splitting repeated dialogue turns when visible.
    @param[in,out] spans Mutable source-span payload list.
    @param[in]  source_text Full source text.
    @param[in]  paragraph_start Inclusive paragraph start offset.
    @param[in]  paragraph_end Exclusive paragraph end offset.
    @return     None.
    @exception  None
    """
    paragraph = source_text[paragraph_start:paragraph_end]
    dash_ranges = _dash_dialogue_ranges(paragraph)
    if len(dash_ranges) <= 1:
        candidate_kind = (
            _CANDIDATE_KIND_MIXED if _dash_dialogue_has_inline_attribution(paragraph) else _CANDIDATE_KIND_DIALOGUE
        )
        _append_source_span(spans, source_text, paragraph_start, paragraph_end, candidate_kind)
        return

    for local_start, local_end in dash_ranges:
        span_text = paragraph[local_start:local_end]
        candidate_kind = (
            _CANDIDATE_KIND_MIXED
            if _dash_dialogue_has_inline_attribution(span_text) or _dash_dialogue_span_looks_like_attribution(span_text)
            else _CANDIDATE_KIND_DIALOGUE
        )
        _append_source_span(
            spans,
            source_text,
            paragraph_start + local_start,
            paragraph_start + local_end,
            candidate_kind,
        )


def _dash_dialogue_ranges(paragraph: str) -> list[tuple[int, int]]:
    """
    @brief      Return local ranges for repeated dash-led dialogue turns.
    @param[in]  paragraph Dash-led paragraph text.
    @return     Ordered local `(start, end)` ranges.
    @exception  None
    """
    paragraph_text = str(paragraph)
    marker_offsets = [
        offset
        for offset, character in enumerate(paragraph_text)
        if _dash_marker_is_dialogue_boundary(paragraph_text, offset, character)
    ]
    if not marker_offsets:
        return []

    boundary_starts: list[int] = []
    for marker_offset in marker_offsets:
        boundary_start = marker_offset
        while boundary_start > 0 and paragraph_text[boundary_start - 1].isspace():
            boundary_start -= 1
        if not boundary_starts and not paragraph_text[:marker_offset].strip():
            boundary_start = 0
        boundary_starts.append(boundary_start)

    ranges: list[tuple[int, int]] = []
    for index, boundary_start in enumerate(boundary_starts):
        boundary_end = boundary_starts[index + 1] if index + 1 < len(boundary_starts) else len(paragraph_text)
        if boundary_end > boundary_start:
            ranges.append((boundary_start, boundary_end))
    return ranges


def _dash_marker_is_dialogue_boundary(paragraph: str, offset: int, character: str) -> bool:
    """
    @brief      Return whether a dash marks a new dialogue turn instead of an in-word hyphen.
    @param[in]  paragraph Paragraph text.
    @param[in]  offset Candidate dash offset.
    @param[in]  character Candidate dash character.
    @return     True when the dash has boundary-like surrounding whitespace.
    @exception  None
    """
    if not _is_dialogue_dash_character(character):
        return False
    previous_character = paragraph[offset - 1] if offset > 0 else ""
    next_character = paragraph[offset + 1] if offset + 1 < len(paragraph) else ""
    if previous_character and not previous_character.isspace():
        return False
    return not next_character or next_character.isspace()


def _dash_dialogue_has_inline_attribution(paragraph: str) -> bool:
    """
    @brief      Return whether dash-led text appears to mix dialogue with speaker attribution.
    @param[in]  paragraph Dash-led paragraph or source-span text.
    @return     True when there is text after a sentence terminator inside the dash span.
    @exception  None
    """
    stripped_text = str(paragraph).strip()
    if not stripped_text:
        return False
    content_start = 1 if _is_dialogue_dash_character(stripped_text[0]) else 0
    content_text = stripped_text[content_start:].strip()
    return bool(re.search(r"[.!?]\s+\S", content_text))


def _dash_dialogue_span_looks_like_attribution(span_text: str) -> bool:
    """
    @brief      Return whether a dash span looks like an attribution continuation.
    @param[in]  span_text Dash-led source-span text.
    @return     True when the first spoken token after the dash starts lowercase.
    @exception  None
    """
    stripped_text = str(span_text).lstrip()
    if not stripped_text or not _is_dialogue_dash_character(stripped_text[0]):
        return False
    content_text = stripped_text[1:].lstrip()
    return bool(content_text) and content_text[0].islower()


def _append_narration_source_spans(
    spans: list[dict[str, object]],
    source_text: str,
    paragraph_start: int,
    paragraph_end: int,
) -> None:
    """
    @brief      Append narration spans, using sentence boundaries when the span list stays manageable.
    @param[in,out] spans Mutable source-span payload list.
    @param[in]  source_text Full source text.
    @param[in]  paragraph_start Inclusive paragraph start offset.
    @param[in]  paragraph_end Exclusive paragraph end offset.
    @return     None.
    @exception  None
    """
    paragraph = source_text[paragraph_start:paragraph_end]
    sentence_spans = ai_sentence_spans(paragraph)
    if len(sentence_spans) <= 1 or len(sentence_spans) > _MAX_NARRATION_SENTENCE_SOURCE_SPANS:
        _append_source_span(spans, source_text, paragraph_start, paragraph_end, _CANDIDATE_KIND_NARRATION)
        return

    cursor = paragraph_start
    for sentence_span in sentence_spans:
        next_cursor = cursor + len(sentence_span)
        _append_source_span(spans, source_text, cursor, next_cursor, _CANDIDATE_KIND_NARRATION)
        cursor = next_cursor
    if cursor < paragraph_end:
        _append_source_span(spans, source_text, cursor, paragraph_end, _CANDIDATE_KIND_NARRATION)


def _quote_dialogue_ranges(paragraph: str) -> list[tuple[int, int]]:
    """
    @brief      Return non-overlapping quoted dialogue ranges for one paragraph.
    @param[in]  paragraph Paragraph text.
    @return     Ordered `(start, end)` ranges local to the paragraph.
    @exception  None
    """
    source_text = str(paragraph)
    ranges: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(source_text):
        opener = source_text[cursor]
        closer = _DIALOGUE_QUOTE_PAIRS.get(opener)
        if closer is None or not _quote_opener_is_plausible(source_text, cursor):
            cursor += 1
            continue
        close_index = source_text.find(closer, cursor + 1)
        if close_index < 0:
            cursor += 1
            continue
        end_offset = _extend_through_trailing_dialogue_punctuation(source_text, close_index + 1)
        ranges.append((cursor, end_offset))
        cursor = end_offset
    return ranges


def _quote_opener_is_plausible(text: str, opener_offset: int) -> bool:
    """
    @brief      Avoid treating apostrophes inside words as dialogue quotes.
    @param[in]  text Paragraph text.
    @param[in]  opener_offset Candidate quote offset.
    @return     True when the quote can plausibly begin dialogue.
    @exception  None
    """
    quote = text[opener_offset]
    if quote not in {"'", '"'}:
        return True
    previous_character = text[opener_offset - 1] if opener_offset > 0 else ""
    next_character = text[opener_offset + 1] if opener_offset + 1 < len(text) else ""
    if quote == "'" and previous_character.isalnum() and next_character.isalnum():
        return False
    return opener_offset == 0 or previous_character.isspace() or previous_character in "([{<:-—–―"


def _extend_through_trailing_dialogue_punctuation(text: str, end_offset: int) -> int:
    """
    @brief      Include punctuation that immediately belongs to the quoted dialogue span.
    @param[in]  text Paragraph text.
    @param[in]  end_offset Offset just after the quote closer.
    @return     Extended end offset.
    @exception  None
    """
    cursor = int(end_offset)
    while cursor < len(text) and text[cursor] in _DIALOGUE_TRAILING_PUNCTUATION:
        cursor += 1
    return cursor


def _candidate_kind_for_context_span(text: str) -> str:
    """
    @brief      Classify non-dialogue context around a detected dialogue span.
    @param[in]  text Context span text.
    @return     Candidate kind token.
    @exception  None
    """
    stripped_text = str(text).strip()
    if not stripped_text:
        return _CANDIDATE_KIND_NARRATION
    if stripped_text.startswith((",", ";", ":", "，", "；", "：")):
        return _CANDIDATE_KIND_ATTRIBUTION
    return _CANDIDATE_KIND_MIXED


def _append_source_span(
    spans: list[dict[str, object]],
    source_text: str,
    start_offset: int,
    end_offset: int,
    candidate_kind: str,
) -> None:
    """
    @brief      Append one exact source span when it covers at least one character.
    @param[in,out] spans Mutable source-span payload list.
    @param[in]  source_text Full source text.
    @param[in]  start_offset Inclusive start offset.
    @param[in]  end_offset Exclusive end offset.
    @param[in]  candidate_kind Candidate kind token.
    @return     None.
    @exception  None
    """
    if end_offset <= start_offset:
        return
    spans.append(
        {
            "source_span_id": "",
            "start_offset": int(start_offset),
            "end_offset": int(end_offset),
            "text": source_text[start_offset:end_offset],
            "candidate_kind": str(candidate_kind).strip() or _CANDIDATE_KIND_NARRATION,
        }
    )


def _renumber_source_spans(spans: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Assign stable ordered source-span identifiers.
    @param[in]  spans Source spans in source order.
    @return     New span payload list with `sNNN` identifiers.
    @exception  None
    """
    renumbered_spans: list[dict[str, object]] = []
    for index, span in enumerate(spans, start=1):
        source_span = dict(span)
        source_span["source_span_id"] = f"s{index:03d}"
        renumbered_spans.append(source_span)
    return renumbered_spans


# END OF FILE
