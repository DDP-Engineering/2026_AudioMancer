#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file materialization.py
@brief Source-only structural chunk construction.
@details Accepted ranges are split at protected source roles and carry honest aggregate metadata.
"""

# IMPORTS

from hashlib import sha256
import json

from audiomancer.cleanup import text as cleanup_text_analysis_service

# CONSTANTS

ChunkPayload = dict[str, object]

# PUBLIC API


def _is_structural_boundary_record(record: dict[str, object]) -> bool:
    """
    @brief      Identify an explicit heading or scene-separator paragraph.
    @param[in]  record Canonical Cleanup paragraph record.
    @return     True when deterministic fallback must preserve this boundary.
    @exception  None.
    """
    role = str(record.get("role") or "body")
    if role == "heading":
        return True
    return not _is_narratable_record(record)


def _effective_cleanup_role(record: dict[str, object]) -> str:
    """
    @brief      Return the role exposed by an AI chunk after user text edits.
    @param[in]  record Canonical Cleanup paragraph record.
    @return     Stored role or a recovered raw scene-separator role.
    @exception  None.
    """
    role = str(record.get("role") or "body")
    if not _is_narratable_record(record):
        return "scene_separator"
    return role


def _deterministic_structural_fallback_ranges(
    paragraph_records: list[dict[str, object]],
    window_start_index: int,
    window_end_index: int,
) -> list[dict[str, int]]:
    """
    @brief      Split a rejected AI window around explicit structural paragraphs.
    @param[in]  paragraph_records Full ordered paragraph record list.
    @param[in]  window_start_index Zero-based inclusive first paragraph index.
    @param[in]  window_end_index Zero-based inclusive last paragraph index.
    @return     Consecutive ranges that preserve headings and scene separators.
    @exception  None.
    """
    structural_indices = [
        index
        for index in range(window_start_index, window_end_index + 1)
        if _is_structural_boundary_record(paragraph_records[index])
    ]
    if not structural_indices:
        return [
            {
                "start_index": window_start_index,
                "end_index": window_end_index,
            }
        ]

    ranges: list[dict[str, int]] = []
    next_index = window_start_index
    for structural_index in structural_indices:
        if next_index < structural_index:
            ranges.append(
                {
                    "start_index": next_index,
                    "end_index": structural_index - 1,
                }
            )
        ranges.append(
            {
                "start_index": structural_index,
                "end_index": structural_index,
            }
        )
        next_index = structural_index + 1
    if next_index <= window_end_index:
        ranges.append(
            {
                "start_index": next_index,
                "end_index": window_end_index,
            }
        )
    return ranges


def _build_units_block(paragraph_records: list[dict[str, object]]) -> str:
    """
    @brief      Build the units block.
    @param[in]  paragraph_records Value for `paragraph_records`.
    @return     Derived helper result.
    """
    blocks: list[str] = []
    for index, record in enumerate(paragraph_records):
        paragraph_number = int(record.get("paragraph_number", index + 1))
        blocks.append(f"Paragraph {paragraph_number}\n{record['text']}")
    return "\n\n".join(blocks).strip()


def _build_chunk_from_range(
    paragraph_records: list[dict[str, object]],
    start_index: int,
    end_index: int,
    sequence_index: int,
) -> ChunkPayload:
    """
    @brief      Build one canonical AI chunk from an absolute paragraph range.
    @param[in]  paragraph_records Full ordered paragraph record list.
    @param[in]  start_index Zero-based inclusive first paragraph index.
    @param[in]  end_index Zero-based inclusive last paragraph index.
    @param[in]  sequence_index One-based canonical chunk sequence number.
    @return     Canonical chunk payload.
    @exception  ValueError Raised when the selected range is empty or invalid.
    """
    selected_records = paragraph_records[start_index : end_index + 1]
    if not selected_records:
        raise ValueError("AI chunk range does not contain any paragraphs.")
    return {
        "chunk_id": f"chunk-{sequence_index:04d}",
        "sequence_index": sequence_index,
        "text": "\n\n".join(str(item["text"]) for item in selected_records).strip(),
        "cleanup_boundary_confidence": weakest_confidence(selected_records),
        "source_paragraph_start": start_index + 1,
        "source_paragraph_end": end_index + 1,
        "cleanup_joined_across_page_break": any(
            bool(item.get("joined_across_page_break", False)) for item in selected_records
        ),
        "cleanup_warning_flags": _merged_warning_flags(selected_records),
        "cleanup_role": next(
            (_effective_cleanup_role(item) for item in selected_records if _effective_cleanup_role(item) != "body"),
            _effective_cleanup_role(selected_records[0]),
        ),
        "starts_after_scene_separator": _starts_after_scene_separator(
            paragraph_records,
            start_index,
        ),
    }


def _is_narratable_record(record: dict[str, object]) -> bool:
    """Return whether one Cleanup paragraph should be materialized as audio text."""
    return not cleanup_text_analysis_service.is_scene_separator_artifact(
        str(record.get("text") or ""),
        str(record.get("role") or "body"),
    )


def _starts_after_scene_separator(
    paragraph_records: list[dict[str, object]],
    start_index: int,
) -> bool:
    """Return whether the narratable range starts immediately after a scene separator."""
    return start_index > 0 and not _is_narratable_record(paragraph_records[start_index - 1])


def _narratable_subranges(paragraph_records, start_index, end_index):
    """@brief Split a valid range at separators, standalone roles and role transitions."""
    if start_index < 0 or end_index < start_index or end_index >= len(paragraph_records):
        raise ValueError("Chunk range is outside the available paragraphs.")
    ranges = []
    start = None
    previous_role = None
    for index in range(start_index, end_index + 1):
        record = paragraph_records[index]
        role = _effective_cleanup_role(record)
        narratable = _is_narratable_record(record)
        boundary = role != previous_role or role in {"heading", "page_artifact"}
        if start is not None and (not narratable or boundary):
            ranges.append({"start_index": start, "end_index": index - 1})
            start = None
        if narratable and start is None:
            start = index
        previous_role = role
    if start is not None:
        ranges.append({"start_index": start, "end_index": end_index})
    return ranges


def _append_chunks_from_ranges(
    chunks: list[ChunkPayload],
    paragraph_records: list[dict[str, object]],
    ranges: list[dict[str, int]],
) -> None:
    """
    @brief      Append canonical chunks for validated absolute paragraph ranges.
    @param[in,out] chunks Existing committed chunk payload list.
    @param[in]  paragraph_records Full ordered paragraph record list.
    @param[in]  ranges Validated absolute paragraph ranges.
    @return     None.
    @exception  ValueError Raised when a range is invalid.
    """
    for range_payload in ranges:
        narratable_ranges = _narratable_subranges(
            paragraph_records,
            int(range_payload["start_index"]),
            int(range_payload["end_index"]),
        )
        for narratable_range in narratable_ranges:
            chunks.append(
                _build_chunk_from_range(
                    paragraph_records,
                    narratable_range["start_index"],
                    narratable_range["end_index"],
                    len(chunks) + 1,
                )
            )


def _merged_warning_flags(paragraph_records: list[dict[str, object]]) -> list[str]:
    """
    @brief      Merge cleanup warning flags across selected paragraph records.
    @param[in]  paragraph_records Paragraph records in one AI chunk span.
    @return     Ordered unique warning flags.
    """
    flags: list[str] = []
    for record in paragraph_records:
        for flag in list(record.get("warning_flags", [])):
            resolved_flag = str(flag)
            if resolved_flag and resolved_flag not in flags:
                flags.append(resolved_flag)
    return flags


def weakest_confidence(records):
    """@brief Return the weakest confidence, retaining unknown for any unknown input."""
    ranks = {"low": 0, "medium": 1, "strong": 2}
    values = [item.get("boundary_confidence") for item in records]
    if not values or any(value not in ranks for value in values):
        return None
    return min(values, key=ranks.__getitem__)


def plan_fingerprint(records):
    """@brief Identify source text, roles, boundaries and metadata under the current core policy."""
    fields = ("text", "role", "boundary_confidence", "joined_across_page_break", "warning_flags")
    payload = ["chunking-policy-1", [{key: record.get(key) for key in fields} for record in records]]
    return "sha256:" + sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def validate_coverage(chunks, records, processed_count=None):
    """@brief Reject gaps, overlaps, role violations and fabricated text in an automatic prefix.
    @exception ValueError Source coverage or materialized source metadata is invalid.
    """
    limit = len(records) if processed_count is None else processed_count
    if type(limit) is not int or not 0 <= limit <= len(records):
        raise ValueError("Chunking checkpoint is outside the source paragraphs.")
    cursor = 0
    for sequence, chunk in enumerate(chunks, 1):
        while cursor < limit and not _is_narratable_record(records[cursor]):
            cursor += 1
        start = chunk.get("source_paragraph_start")
        end = chunk.get("source_paragraph_end")
        if type(start) is not int or type(end) is not int or start != cursor + 1 or not start <= end <= limit:
            raise ValueError("Chunking source coverage contains a gap, overlap or invalid range.")
        ranges = _narratable_subranges(records, start - 1, end - 1)
        if ranges != [{"start_index": start - 1, "end_index": end - 1}]:
            raise ValueError("Chunking range crosses a protected structural boundary.")
        expected = _build_chunk_from_range(records, start - 1, end - 1, sequence)
        if chunk != expected:
            raise ValueError("Chunking checkpoint differs from its source paragraphs.")
        cursor = end
    while cursor < limit and not _is_narratable_record(records[cursor]):
        cursor += 1
    if cursor != limit:
        raise ValueError("Chunking source coverage is incomplete.")


def manual_metadata(chunk, text):
    """@brief Clear automatic provenance on a changed or inserted manual chunk."""
    result = dict(
        chunk,
        text=text,
        source_paragraph_start=None,
        source_paragraph_end=None,
        cleanup_boundary_confidence=None,
        cleanup_joined_across_page_break=False,
        cleanup_warning_flags=[],
        cleanup_role="body",
    )
    if cleanup_text_analysis_service.detect_chapter_label(text.strip()) is not None:
        result["cleanup_role"] = "heading"
    elif cleanup_text_analysis_service.is_scene_separator_artifact(text, "body"):
        result["cleanup_role"] = "scene_separator"
    return result


def build_warnings(chapter_count: int) -> list[str]:
    """
    @brief      Build the chunking warnings.
    @param[in]  chapter_count Value for `chapter_count`.
    @return     Derived helper result.
    """
    warnings: list[str] = []
    if chapter_count == 0:
        warnings.append(
            "No explicit chapter or scene headings were detected; chunk metadata uses sequential ordering only."
        )
    return warnings


# END OF FILE
