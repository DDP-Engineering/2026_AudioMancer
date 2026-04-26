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
@brief Cleaned-text paragraph metadata helpers for AudioMancer.
@details Persists and loads page-break-aware paragraph records beside the
         canonical cleaned-text artifact so downstream chunking can use cleanup
         provenance without changing the operator-editable text file.
@author Eng. Dan Dumitru Pasare
@date 2026-04-26
@version 0.1.0
"""

# IMPORTS

from datetime import UTC, datetime
import json
from pathlib import Path

from audiomancer import config
from audiomancer.services.operation_runtime_service import relative_to_project, resolve_operation_path

# CONSTANTS

# @brief Schema version for the cleaned-text metadata sidecar.
CLEANED_TEXT_METADATA_SCHEMA_VERSION = 1

# @brief Canonical paragraph-record payload type.
ParagraphRecordPayload = dict[str, object]

# @brief Canonical cleaned-text metadata payload type.
CleanupMetadataPayload = dict[str, object]


# PUBLIC API


def cleanup_metadata_path(project_root: str | Path) -> Path:
    """
    @brief      Resolve the cleaned-text metadata sidecar path.
    @param[in]  project_root Active project root folder.
    @return     Absolute metadata sidecar path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return resolve_operation_path(project_root, "cleanup", config.CLEANED_TEXT_METADATA_FILE_NAME)


def build_paragraph_records_from_text(cleaned_text: str) -> list[ParagraphRecordPayload]:
    """
    @brief      Build fallback paragraph records from canonical cleaned text.
    @param[in]  cleaned_text Canonical cleaned-text artifact content.
    @return     Ordered paragraph metadata records.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    normalized = cleaned_text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [paragraph.strip() for paragraph in normalized.split("\n\n") if paragraph.strip()]
    records: list[ParagraphRecordPayload] = []
    line_number = 1
    for index, paragraph_text in enumerate(paragraphs, start=1):
        line_count = max(1, len(paragraph_text.splitlines()))
        records.append(
            {
                "paragraph_id": f"paragraph-{index:04d}",
                "text": paragraph_text,
                "source_start_line": line_number,
                "source_end_line": line_number + line_count - 1,
                "source_page_start": None,
                "source_page_end": None,
                "starts_after_page_break": False,
                "joined_across_page_break": False,
                "boundary_confidence": "strong",
                "warning_flags": [],
            }
        )
        line_number += line_count + 1
    return records


def finalize_paragraph_records(records: list[ParagraphRecordPayload]) -> list[ParagraphRecordPayload]:
    """
    @brief      Assign stable paragraph ids and cleaned-text line spans.
    @param[in]  records Paragraph records with finalized text.
    @return     Normalized ordered paragraph records.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    finalized: list[ParagraphRecordPayload] = []
    line_number = 1
    for index, record in enumerate(records, start=1):
        paragraph_text = str(record.get("text", "")).strip()
        if not paragraph_text:
            continue
        line_count = max(1, len(paragraph_text.splitlines()))
        finalized_record = dict(record)
        finalized_record["paragraph_id"] = f"paragraph-{len(finalized) + 1:04d}"
        finalized_record["text"] = paragraph_text
        finalized_record["source_start_line"] = line_number
        finalized_record["source_end_line"] = line_number + line_count - 1
        finalized_record.setdefault("source_page_start", None)
        finalized_record.setdefault("source_page_end", None)
        finalized_record.setdefault("starts_after_page_break", False)
        finalized_record.setdefault("joined_across_page_break", False)
        finalized_record.setdefault("boundary_confidence", "strong")
        finalized_record["warning_flags"] = [str(item) for item in list(finalized_record.get("warning_flags", []))]
        finalized.append(finalized_record)
        line_number += line_count + 1
        _ = index
    return finalized


def write_cleanup_metadata(
    project_root: str | Path,
    input_path: str | Path | None,
    cleaned_text_path: str | Path,
    paragraph_records: list[ParagraphRecordPayload],
    cleanup_mode: str,
) -> CleanupMetadataPayload:
    """
    @brief      Persist one cleaned-text metadata sidecar.
    @param[in]  project_root Active project root folder.
    @param[in]  input_path Optional cleanup input path.
    @param[in]  cleaned_text_path Canonical cleaned-text path.
    @param[in]  paragraph_records Final paragraph metadata records.
    @param[in]  cleanup_mode Cleanup mode that produced the records.
    @return     Persisted metadata payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    metadata_path = cleanup_metadata_path(resolved_project_root)
    metadata_payload = {
        "schema_version": CLEANED_TEXT_METADATA_SCHEMA_VERSION,
        "cleanup_mode": cleanup_mode,
        "input_relative_path": (
            None if input_path is None else relative_to_project(resolved_project_root, Path(input_path))
        ),
        "cleaned_text_relative_path": relative_to_project(resolved_project_root, Path(cleaned_text_path)),
        "created_at": _utc_now_iso(),
        "paragraph_count": len(paragraph_records),
        "page_break_repair_count": sum(
            1 for record in paragraph_records if bool(record.get("joined_across_page_break"))
        ),
        "weak_boundary_count": sum(1 for record in paragraph_records if record.get("boundary_confidence") == "weak"),
        "paragraphs": [dict(record) for record in paragraph_records],
    }
    metadata_path.write_text(
        json.dumps(metadata_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return metadata_payload


def write_minimal_cleanup_metadata(
    project_root: str | Path,
    cleaned_text: str,
    cleanup_mode: str,
) -> CleanupMetadataPayload:
    """
    @brief      Persist metadata reconstructed from edited or AI-cleaned text.
    @param[in]  project_root Active project root folder.
    @param[in]  cleaned_text Canonical cleaned text.
    @param[in]  cleanup_mode Cleanup mode label.
    @return     Persisted metadata payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    cleaned_text_path = Path(project_root) / config.CLEANED_TEXT_FILE_NAME
    records = build_paragraph_records_from_text(cleaned_text)
    return write_cleanup_metadata(project_root, None, cleaned_text_path, records, cleanup_mode)


def load_cleanup_metadata(project_root: str | Path) -> CleanupMetadataPayload | None:
    """
    @brief      Load the optional cleaned-text metadata sidecar.
    @param[in]  project_root Active project root folder.
    @return     Metadata payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    metadata_path = cleanup_metadata_path(project_root)
    if not metadata_path.is_file():
        return None
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    return dict(payload) if isinstance(payload, dict) else None


def load_or_build_paragraph_records(
    project_root: str | Path,
    cleaned_text: str,
) -> list[ParagraphRecordPayload]:
    """
    @brief      Prefer metadata paragraph records and fall back to text splitting.
    @param[in]  project_root Active project root folder.
    @param[in]  cleaned_text Canonical cleaned text.
    @return     Ordered chunkable paragraph records.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    metadata_payload = load_cleanup_metadata(project_root)
    if isinstance(metadata_payload, dict):
        paragraph_payloads = metadata_payload.get("paragraphs", [])
        if isinstance(paragraph_payloads, list):
            records = [_normalize_loaded_record(item, index) for index, item in enumerate(paragraph_payloads, start=1)]
            records = [record for record in records if str(record.get("text", "")).strip()]
            if records:
                return records
    return build_paragraph_records_from_text(cleaned_text)


def remove_cleanup_metadata(project_root: str | Path) -> None:
    """
    @brief      Remove stale cleaned-text metadata if it exists.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    metadata_path = cleanup_metadata_path(project_root)
    if metadata_path.is_file():
        metadata_path.unlink()


# LOCAL HELPERS


def _normalize_loaded_record(item: object, index: int) -> ParagraphRecordPayload:
    """
    @brief      Normalize one loaded metadata paragraph record.
    @param[in]  item Raw paragraph record.
    @param[in]  index Fallback one-based paragraph index.
    @return     Normalized paragraph record.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    payload = item if isinstance(item, dict) else {}
    return {
        "paragraph_id": str(payload.get("paragraph_id") or f"paragraph-{index:04d}"),
        "text": str(payload.get("text", "")).strip(),
        "source_start_line": _positive_int(payload.get("source_start_line"), index),
        "source_end_line": _positive_int(payload.get("source_end_line"), index),
        "source_page_start": _optional_positive_int(payload.get("source_page_start")),
        "source_page_end": _optional_positive_int(payload.get("source_page_end")),
        "starts_after_page_break": bool(payload.get("starts_after_page_break", False)),
        "joined_across_page_break": bool(payload.get("joined_across_page_break", False)),
        "boundary_confidence": str(payload.get("boundary_confidence") or "strong"),
        "warning_flags": [str(flag) for flag in list(payload.get("warning_flags", []))],
    }


def _optional_positive_int(value: object) -> int | None:
    """
    @brief      Normalize one optional positive integer.
    @param[in]  value Raw value.
    @return     Positive integer or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    try:
        resolved_value = int(value)
    except (TypeError, ValueError):
        return None
    return resolved_value if resolved_value > 0 else None


def _positive_int(value: object, fallback: int) -> int:
    """
    @brief      Normalize one positive integer with fallback.
    @param[in]  value Raw value.
    @param[in]  fallback Fallback value.
    @return     Positive integer.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    resolved_value = _optional_positive_int(value)
    return fallback if resolved_value is None else resolved_value


def _utc_now_iso() -> str:
    """
    @brief      Build one current UTC timestamp in stable ISO-8601 format.
    @return     UTC timestamp string without microseconds.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# END OF FILE
