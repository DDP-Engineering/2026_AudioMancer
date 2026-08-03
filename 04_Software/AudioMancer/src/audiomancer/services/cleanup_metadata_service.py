#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file cleanup_metadata_service.py
@brief Paragraph-offset readers for the single Cleanup document.
@details Reconstructs paragraph text from clean_text.txt offsets stored in
         cleanup.json; it does not create or read a metadata sidecar.
"""

from __future__ import annotations

import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import cleanup_text_analysis_service
from audiomancer.services.source_ledger_service import text_sha256

ParagraphRecordPayload = dict[str, object]
CleanupMetadataPayload = dict[str, object]
_WARNING_REASON_CODES = frozenset(
    {
        "deterministic_fallback",
        "page_transition_repaired",
        "unknown_line_boundary",
    }
)


def cleanup_metadata_path(project_root: str | Path) -> Path:
    """Return the sole Cleanup metadata path."""
    return Path(project_root) / config.CLEANUP_DOCUMENT_FILE_NAME


def build_paragraph_records_from_text(
    cleaned_text: str,
) -> list[ParagraphRecordPayload]:
    """Build minimal user-edited paragraph records and runtime text slices."""
    source = str(cleaned_text).replace("\r\n", "\n").replace("\r", "\n")
    records: list[ParagraphRecordPayload] = []
    cursor = 0
    limit = len(source.rstrip("\n"))
    while cursor < limit:
        separator = source.find("\n\n", cursor, limit)
        raw_end = limit if separator < 0 else separator
        start = cursor
        end = raw_end
        while start < end and source[start] in "\r\n":
            start += 1
        while end > start and source[end - 1] in "\r\n":
            end -= 1
        if start < end and source[start:end].strip():
            paragraph_text = source[start:end]
            is_scene_separator = cleanup_text_analysis_service.is_scene_separator_artifact(
                paragraph_text,
            )
            records.append(
                _runtime_record(
                    {
                        "paragraph_id": f"paragraph-{len(records) + 1:06d}",
                        "output_start": start,
                        "output_end": end,
                        "role": "scene_separator" if is_scene_separator else "body",
                        "confidence": "strong",
                        "reason_codes": [
                            "user_edited_scene_separator" if is_scene_separator else "user_edited"
                        ],
                        "source_page_start": None,
                        "source_page_end": None,
                        "starts_after_page_transition": False,
                        "crosses_page_transition": False,
                        "source_unit_ids": [],
                        "provenance_available": False,
                    },
                    source,
                )
            )
        if separator < 0:
            break
        cursor = separator + 2
        while cursor < limit and source[cursor] == "\n":
            cursor += 1
    return records


def load_cleanup_metadata(
    project_root: str | Path,
) -> CleanupMetadataPayload | None:
    """Load cleanup.json as the sole optional Cleanup metadata document."""
    path = cleanup_metadata_path(project_root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return dict(payload) if isinstance(payload, dict) else None


def load_completed_paragraph_records(
    project_root: str | Path,
    cleaned_text: str,
) -> list[ParagraphRecordPayload]:
    """Load verified completed Cleanup paragraphs for a downstream consumer."""
    document = load_cleanup_metadata(project_root)
    if not isinstance(document, dict) or document.get("status") != "completed":
        raise ValueError(
            "Chunking requires completed Cleanup metadata in cleanup.json."
        )
    if document.get("output_hash") != text_sha256(cleaned_text):
        raise ValueError("clean_text.txt does not match cleanup.json.")
    paragraphs = document.get("paragraphs")
    if not isinstance(paragraphs, list):
        raise ValueError("cleanup.json paragraph metadata is invalid.")
    records: list[ParagraphRecordPayload] = []
    previous_end = 0
    for index, item in enumerate(paragraphs, start=1):
        if not isinstance(item, dict):
            raise ValueError("cleanup.json paragraph metadata is invalid.")
        start = _integer(item.get("output_start"), -1)
        end = _integer(item.get("output_end"), -1)
        if (
            start < previous_end
            or end <= start
            or end > len(cleaned_text)
            or not cleaned_text[start:end].strip()
        ):
            raise ValueError("cleanup.json paragraph offsets are invalid.")
        previous_end = end
        normalized = dict(item)
        normalized["paragraph_id"] = str(
            item.get("paragraph_id") or f"paragraph-{index:06d}"
        )
        records.append(_runtime_record(normalized, cleaned_text))
    return records


def load_or_build_paragraph_records(
    project_root: str | Path,
    cleaned_text: str,
) -> list[ParagraphRecordPayload]:
    """Load completed Cleanup offsets or build minimal runtime fallback records."""
    if cleanup_metadata_path(project_root).is_file():
        return load_completed_paragraph_records(project_root, cleaned_text)
    return build_paragraph_records_from_text(cleaned_text)


def persisted_paragraph_records(
    records: list[ParagraphRecordPayload],
) -> list[ParagraphRecordPayload]:
    """Remove runtime-only text and compatibility aliases from paragraph records."""
    persisted_fields = (
        "paragraph_id",
        "output_start",
        "output_end",
        "role",
        "confidence",
        "reason_codes",
        "source_page_start",
        "source_page_end",
        "starts_after_page_transition",
        "crosses_page_transition",
        "source_unit_ids",
        "provenance_available",
    )
    return [
        {
            field: item.get(field)
            for field in persisted_fields
        }
        for item in records
    ]


def _runtime_record(
    item: dict[str, object],
    cleaned_text: str,
) -> ParagraphRecordPayload:
    """Add runtime text and legacy aliases used by existing downstream services."""
    start = _integer(item.get("output_start"), 0)
    end = _integer(item.get("output_end"), start)
    text = cleaned_text[start:end]
    start_line = cleaned_text.count("\n", 0, start) + 1
    end_line = start_line + text.count("\n")
    confidence = str(item.get("confidence") or "strong")
    crosses_page = bool(item.get("crosses_page_transition", False))
    return {
        **item,
        "text": text,
        "source_start_line": start_line,
        "source_end_line": end_line,
        "starts_after_page_break": bool(
            item.get("starts_after_page_transition", False)
        ),
        "joined_across_page_break": crosses_page,
        "boundary_confidence": confidence,
        "warning_flags": [
            resolved
            for value in item.get("reason_codes", [])
            if (resolved := str(value)) in _WARNING_REASON_CODES
        ],
    }


def _integer(value: object, fallback: int) -> int:
    """Return one integer value or a caller-provided fallback."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


# END OF FILE
