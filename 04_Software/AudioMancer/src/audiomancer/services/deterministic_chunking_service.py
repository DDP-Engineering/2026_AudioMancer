#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file deterministic_chunking_service.py
@brief Deterministic text chunking helpers for AudioMancer.
@details Consumes cleaned text, produces one ordered paragraph chunk per unit,
         persists chunk artifacts in `20_chunking`, and maintains resumable
         operation state for interrupted deterministic chunking runs.
@author Eng. Dan Dumitru Pasare
@date 2026-04-11
@version 0.3.0
"""

# IMPORTS

from datetime import UTC, datetime
import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import cleanup_metadata_service
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    build_operation_output_path,
    progress_percent,
    raise_if_cancelled,
    relative_to_project,
    resolve_operation_path,
)

# CONSTANTS

# @brief Component logger used by the deterministic chunking workflow.
_CHUNKING_LOGGER = get_component_logger("deterministic_chunking")

# @brief Supported chapter-heading detection patterns used to carry chapter metadata across chunks.
_CHAPTER_PATTERNS = (
    re.compile(r"^(chapter|capitolul|scene|scena)\s+[\wIVXLCDM0-9][\wIVXLCDM0-9 .:-]*$", re.IGNORECASE),
    re.compile(r"^[IVXLCDM]+$", re.IGNORECASE),
)

# @brief Canonical chunk-record payload type persisted for downstream workflow steps.
ChunkPayload = dict[str, object]

# @brief Persisted deterministic chunking report payload type.
ChunkingReportPayload = dict[str, object]

# @brief Persisted deterministic chunking operation-state payload type.
OperationStatePayload = dict[str, object]


# PUBLIC API


@trace_function(_CHUNKING_LOGGER)
def chunk_text(
    project_root: str | Path,
    manifest: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
) -> ChunkingReportPayload:
    """
    @brief      Run deterministic chunking for one active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  progress_callback Optional zero-copy progress callback.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Chunking report payload for the persisted artifacts.
    @exception  FileNotFoundError Raised when the cleaned input is missing.
    @exception  ValueError Raised when no chunkable paragraphs remain.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.2.0
    """
    resolved_project_root = Path(project_root)
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        raise ValueError("No imported source is available for deterministic chunking.")

    cleaned_relative_path = config.CLEANED_TEXT_FILE_NAME

    cleaned_path = resolved_project_root / cleaned_relative_path
    if not cleaned_path.is_file():
        raise FileNotFoundError("Deterministic chunking requires cleaned text first.")

    input_text = cleaned_path.read_text(encoding="utf-8")
    paragraph_records = _build_paragraph_records(input_text, resolved_project_root)
    if not paragraph_records:
        raise ValueError("Cleaned text does not contain any chunkable paragraphs.")

    _ = source_document
    input_snapshot_path = cleaned_path

    output_path = build_operation_output_path(
        resolved_project_root,
        "chunking",
        config.CHUNK_ARTIFACT_FILE_NAME,
    )
    report_path = build_operation_output_path(
        resolved_project_root,
        "chunking",
        config.CHUNKING_REPORT_FILE_NAME,
    )
    state_path = build_operation_output_path(
        resolved_project_root,
        "chunking",
        config.CHUNKING_STATE_FILE_NAME,
    )

    existing_state = _load_operation_state(state_path) or {}
    progress_total = len(paragraph_records)
    started_at = str(existing_state.get("started_at") or _utc_now_iso())
    resume_checkpoint = dict(existing_state.get("resume_checkpoint") or {})
    start_chunk_index = int(resume_checkpoint.get("next_chunk_index", 0))
    chunks = _load_partial_chunks(output_path) if start_chunk_index > 0 else []
    if len(chunks) != start_chunk_index:
        chunks = []
        start_chunk_index = 0
        output_path.write_text("[]\n", encoding="utf-8")

    _write_running_state(
        state_path,
        resolved_project_root,
        input_snapshot_path,
        output_path,
        started_at,
        start_chunk_index,
        progress_total,
        chunks,
    )
    _emit_progress(
        progress_callback,
        progress_current=start_chunk_index,
        progress_total=progress_total,
        message="Deterministic chunking in progress...",
    )

    current_chapter = _current_chapter_from_chunks(chunks)
    chapter_count = _chapter_count_from_chunks(chunks)
    for chunk_index in range(start_chunk_index, progress_total):
        raise_if_cancelled(cancel_requested)
        paragraph_record = paragraph_records[chunk_index]
        chapter_label = _detect_chapter_label(str(paragraph_record["text"]))
        if chapter_label is not None and chapter_label != current_chapter:
            current_chapter = chapter_label
            chapter_count += 1
        chunks.append(
            _build_chunk_payload(
                chunk_index + 1,
                paragraph_record,
                current_chapter,
            )
        )
        _write_chunk_payload(output_path, chunks)
        _write_running_state(
            state_path,
            resolved_project_root,
            input_snapshot_path,
            output_path,
            started_at,
            chunk_index + 1,
            progress_total,
            chunks,
        )
        _emit_progress(
            progress_callback,
            progress_current=chunk_index + 1,
            progress_total=progress_total,
            message="Deterministic chunking in progress...",
        )

    warnings = _build_chunking_warnings(chapter_count)
    report_payload: ChunkingReportPayload = {
        "input_relative_path": relative_to_project(resolved_project_root, input_snapshot_path),
        "chunk_artifact_relative_path": relative_to_project(resolved_project_root, output_path),
        "chunked_at": _utc_now_iso(),
        "warnings": warnings,
        "chunk_count": len(chunks),
        "detected_chapter_count": chapter_count,
        "chunking_mode": "deterministic",
    }
    report_path.write_text(
        json.dumps(report_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    completed_state = _build_operation_state(
        resolved_project_root,
        input_snapshot_path=input_snapshot_path,
        output_path=output_path,
        report_path=report_path,
        status="completed",
        progress_current=progress_total,
        progress_total=progress_total,
        started_at=started_at,
        completed_at=report_payload["chunked_at"],
        warnings=warnings,
        chunk_count=len(chunks),
        chapter_count=chapter_count,
        chunks=None,
        resume_checkpoint=None,
    )
    state_path.write_text(
        json.dumps(completed_state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _emit_progress(
        progress_callback,
        progress_current=progress_total,
        progress_total=progress_total,
        message="Deterministic chunking completed.",
    )
    return report_payload


@trace_function(_CHUNKING_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Load one optional chunking operation-state payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted chunking operation-state payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    return _load_operation_state(resolve_operation_path(project_root, "chunking", config.CHUNKING_STATE_FILE_NAME))


@trace_function(_CHUNKING_LOGGER)
def load_chunking_report(project_root: str | Path) -> ChunkingReportPayload | None:
    """
    @brief      Load one optional deterministic chunking report payload.
    @param[in]  project_root Active project root folder.
    @return     Chunking report payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    report_path = resolve_operation_path(
        project_root,
        "chunking",
        config.CHUNKING_REPORT_FILE_NAME,
    )
    if not report_path.is_file():
        return None
    return dict(json.loads(report_path.read_text(encoding="utf-8")))


@trace_function(_CHUNKING_LOGGER)
def load_chunks(project_root: str | Path) -> list[ChunkPayload]:
    """
    @brief      Load the optional persisted chunk artifact from one project.
    @param[in]  project_root Active project root folder.
    @return     Ordered chunk payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    output_path = resolve_operation_path(
        project_root,
        "chunking",
        config.CHUNK_ARTIFACT_FILE_NAME,
    )
    return _load_partial_chunks(output_path)


# LOCAL HELPERS


def _emit_progress(progress_callback, progress_current: int, progress_total: int, message: str) -> None:
    """
    @brief      Emit the progress.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  progress_current Value for `progress_current`.
    @param[in]  progress_total Value for `progress_total`.
    @param[in]  message Operator-facing message text.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    if callable(progress_callback):
        progress_callback(
            progress_current,
            progress_total,
            progress_percent(progress_current, progress_total),
            message,
        )


def _build_paragraph_records(cleaned_text: str, project_root: str | Path | None = None) -> list[dict[str, object]]:
    """
    @brief      Build the paragraph records.
    @param[in]  cleaned_text Text value for `cleaned_text`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    if project_root is not None:
        paragraph_records = cleanup_metadata_service.load_or_build_paragraph_records(project_root, cleaned_text)
    else:
        paragraph_records = cleanup_metadata_service.build_paragraph_records_from_text(cleaned_text)
    records: list[dict[str, object]] = []
    for record in paragraph_records:
        records.append(
            {
                **dict(record),
                "line_start": int(record.get("source_start_line", 1)),
                "line_end": int(record.get("source_end_line", record.get("source_start_line", 1))),
            }
        )
    return records


def _build_chunk_payload(
    sequence_index: int,
    paragraph_record: dict[str, object],
    chapter_label: str | None,
) -> ChunkPayload:
    """
    @brief      Build the chunk payload.
    @param[in]  sequence_index Value for `sequence_index`.
    @param[in]  paragraph_record Value for `paragraph_record`.
    @param[in]  chapter_label Value for `chapter_label`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return {
        "chunk_id": f"chunk-{sequence_index:04d}",
        "sequence_index": sequence_index,
        "chapter_label": chapter_label,
        "text": str(paragraph_record["text"]),
        "source_start_line": int(paragraph_record["line_start"]),
        "source_end_line": int(paragraph_record["line_end"]),
        "source_page_start": paragraph_record.get("source_page_start"),
        "source_page_end": paragraph_record.get("source_page_end"),
        "cleanup_boundary_confidence": paragraph_record.get("boundary_confidence"),
        "cleanup_joined_across_page_break": bool(paragraph_record.get("joined_across_page_break", False)),
        "cleanup_warning_flags": list(paragraph_record.get("warning_flags", [])),
        "chunking_mode": "deterministic",
        "semantic_strategy": None,
        "scene_note": None,
    }


def _write_chunk_payload(output_path: Path, chunks: list[ChunkPayload]) -> None:
    """
    @brief      Write the chunk payload.
    @param[in]  output_path Output file path.
    @param[in]  chunks Value for `chunks`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    output_path.write_text(
        json.dumps(chunks, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_partial_chunks(output_path: Path) -> list[ChunkPayload]:
    """
    @brief      Load the partial chunks.
    @param[in]  output_path Output file path.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not output_path.is_file():
        return []
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


def _write_running_state(
    state_path: Path,
    project_root: Path,
    input_snapshot_path: Path,
    output_path: Path,
    started_at: str,
    progress_current: int,
    progress_total: int,
    chunks: list[ChunkPayload],
) -> None:
    """
    @brief      Write the running state.
    @param[in]  state_path Operation-state file path.
    @param[in]  project_root Active project root folder.
    @param[in]  input_snapshot_path Input snapshot file path.
    @param[in]  output_path Output file path.
    @param[in]  started_at Value for `started_at`.
    @param[in]  progress_current Value for `progress_current`.
    @param[in]  progress_total Value for `progress_total`.
    @param[in]  chunks Value for `chunks`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    running_state = _build_operation_state(
        project_root,
        input_snapshot_path=input_snapshot_path,
        output_path=output_path,
        report_path=None,
        status="running",
        progress_current=progress_current,
        progress_total=progress_total,
        started_at=started_at,
        completed_at=None,
        warnings=[],
        chunk_count=len(chunks),
        chapter_count=_chapter_count_from_chunks(chunks),
        chunks=chunks,
        resume_checkpoint={"next_chunk_index": progress_current},
    )
    state_path.write_text(
        json.dumps(running_state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _build_operation_state(
    project_root: Path,
    input_snapshot_path: Path,
    output_path: Path,
    report_path: Path | None,
    status: str,
    progress_current: int,
    progress_total: int,
    started_at: str,
    completed_at: str | None,
    warnings: list[str],
    chunk_count: int,
    chapter_count: int,
    chunks: list[ChunkPayload] | None,
    resume_checkpoint: dict[str, object] | None,
) -> OperationStatePayload:
    """
    @brief      Build the operation state.
    @param[in]  project_root Active project root folder.
    @param[in]  input_snapshot_path Input snapshot file path.
    @param[in]  output_path Output file path.
    @param[in]  report_path Report file path.
    @param[in]  status Value for `status`.
    @param[in]  progress_current Value for `progress_current`.
    @param[in]  progress_total Value for `progress_total`.
    @param[in]  started_at Value for `started_at`.
    @param[in]  completed_at Value for `completed_at`.
    @param[in]  warnings Value for `warnings`.
    @param[in]  chunk_count Value for `chunk_count`.
    @param[in]  chapter_count Value for `chapter_count`.
    @param[in]  chunks Value for `chunks`.
    @param[in]  resume_checkpoint Value for `resume_checkpoint`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    artifact_paths: list[str] = []
    if report_path is not None and report_path.is_file():
        artifact_paths.append(relative_to_project(project_root, report_path))
    return {
        "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        "status": status,
        "input_paths": [relative_to_project(project_root, input_snapshot_path)],
        "output_paths": ([relative_to_project(project_root, output_path)] if output_path.is_file() else []),
        "artifact_paths": artifact_paths,
        "progress_current": progress_current,
        "progress_total": progress_total,
        "mode": "deterministic",
        "started_at": started_at,
        "completed_at": completed_at,
        "updated_at": _utc_now_iso(),
        "warning_count": len(warnings),
        "metadata": {
            "warnings": list(warnings),
            "chunk_count": chunk_count,
            "detected_chapter_count": chapter_count,
            "chunks": None if chunks is None else list(chunks),
        },
        "resume_checkpoint": None if resume_checkpoint is None else dict(resume_checkpoint),
    }


def _build_chunking_warnings(chapter_count: int) -> list[str]:
    """
    @brief      Build the chunking warnings.
    @param[in]  chapter_count Value for `chapter_count`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    warnings: list[str] = []
    if chapter_count == 0:
        warnings.append(
            "No explicit chapter or scene headings were detected; chunk metadata uses sequential ordering only."
        )
    return warnings


def _chapter_count_from_chunks(chunks: list[ChunkPayload]) -> int:
    """
    @brief      Execute the chapter count from chunks helper.
    @param[in]  chunks Value for `chunks`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    chapter_labels: list[str] = []
    for chunk in chunks:
        chapter_label = chunk.get("chapter_label")
        if chapter_label in (None, ""):
            continue
        resolved_label = str(chapter_label)
        if not chapter_labels or chapter_labels[-1] != resolved_label:
            chapter_labels.append(resolved_label)
    return len(chapter_labels)


def _current_chapter_from_chunks(chunks: list[ChunkPayload]) -> str | None:
    """
    @brief      Return the current chapter from chunks.
    @param[in]  chunks Value for `chunks`.
    @return     Resolved helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    for chunk in reversed(chunks):
        chapter_label = chunk.get("chapter_label")
        if chapter_label not in (None, ""):
            return str(chapter_label)
    return None


def _detect_chapter_label(paragraph_text: str) -> str | None:
    """
    @brief      Detect the chapter label.
    @param[in]  paragraph_text Text value for `paragraph_text`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized = paragraph_text.strip()
    if len(normalized) > 100:
        return None
    for pattern in _CHAPTER_PATTERNS:
        if pattern.fullmatch(normalized):
            return normalized
    return None


def _load_operation_state(state_path: Path) -> OperationStatePayload | None:
    """
    @brief      Load the operation state.
    @param[in]  state_path Operation-state file path.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not state_path.is_file():
        return None
    return dict(json.loads(state_path.read_text(encoding="utf-8")))


def _utc_now_iso() -> str:
    """
    @brief      Execute the utc now iso helper.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# END OF FILE
