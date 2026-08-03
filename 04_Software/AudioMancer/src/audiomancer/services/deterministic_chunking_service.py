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
         and atomically checkpoints resumable lifecycle and chunk data in the
         strict authoritative `chunks_text.json` document.
"""

# IMPORTS

from functools import partial
from pathlib import Path
import re
from time import monotonic

from audiomancer import config
from audiomancer.services import (
    chunking_document_service,
    cleanup_metadata_service,
    cleanup_text_analysis_service,
    project_workspace_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    emit_progress_update,
    raise_if_cancelled,
)

# CONSTANTS

# @brief Component logger used by the deterministic chunking workflow.
_CHUNKING_LOGGER = get_component_logger("deterministic_chunking")
_emit_progress = partial(emit_progress_update, include_token_usage=False)

# @brief Strict uppercase grammar for bare Roman-numeral chapter headings.
_ROMAN_NUMERAL_PATTERN = re.compile(
    r"(?=[MDCLXVI]+$)M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
)
# @brief Supported chapter-heading detection patterns used for transient chapter-count and prompt context.
_CHAPTER_PATTERNS = (
    re.compile(r"^(chapter|capitolul|scene|scena)\s+[\wIVXLCDM0-9][\wIVXLCDM0-9 .:-]*$", re.IGNORECASE),
    _ROMAN_NUMERAL_PATTERN,
)

# @brief Maximum deterministic paragraphs processed between resumable checkpoints.
_CHECKPOINT_PARAGRAPH_INTERVAL = 200

# @brief Maximum seconds between deterministic resumable checkpoints.
_CHECKPOINT_TIME_INTERVAL_SECONDS = 2.0

# @brief Minimum seconds between non-terminal progress emissions.
_PROGRESS_EMIT_INTERVAL_SECONDS = 0.1

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
    @exception  IncompatibleChunkingDocumentError Raised for incompatible data; reset Chunking first.
    """
    resolved_project_root = Path(project_root)
    if not isinstance(manifest.get("source_document"), dict):
        raise ValueError("No imported source is available for deterministic chunking.")
    cleaned_path = resolved_project_root / config.CLEANED_TEXT_FILE_NAME
    if not cleaned_path.is_file():
        raise FileNotFoundError("Deterministic chunking requires cleaned text first.")
    input_text = cleaned_path.read_text(encoding="utf-8")
    paragraph_records = _build_paragraph_records(input_text, resolved_project_root)
    if not paragraph_records:
        raise ValueError("Cleaned text does not contain any chunkable paragraphs.")
    if not any(_is_narratable_record(record) for record in paragraph_records):
        raise ValueError("Cleaned text does not contain any narratable paragraphs.")

    existing_document = chunking_document_service.load_chunking_document(resolved_project_root)
    start_index = 0
    chunks: list[ChunkPayload] = []
    if existing_document is not None and existing_document["status"] in chunking_document_service.RESUMABLE_STATUSES:
        if existing_document["mode"] != "deterministic":
            raise chunking_document_service.IncompatibleChunkingDocumentError(
                "Chunking data is incompatible. Use Reset Chunking before continuing."
            )
        if existing_document["source_fingerprint"] != chunking_document_service.source_fingerprint(input_text):
            raise chunking_document_service.IncompatibleChunkingDocumentError(
                "Cleaned text changed. Use Reset Chunking before continuing."
            )
        next_paragraph = int(existing_document["next_paragraph"])
        start_index = next_paragraph - 1
        chunks = list(existing_document["chunks"])
        expected_chunk_count = sum(
            _is_narratable_record(record)
            for record in paragraph_records[:start_index]
        )
        if len(chunks) != expected_chunk_count:
            raise chunking_document_service.IncompatibleChunkingDocumentError(
                "Chunking data is incompatible. Use Reset Chunking before continuing."
            )

    document = chunking_document_service.build_document(
        status="running",
        mode="deterministic",
        source_text=input_text,
        chunks=chunks,
        next_paragraph=start_index + 1,
    )
    chunking_document_service.write_chunking_document(resolved_project_root, document)
    progress_total = len(paragraph_records)
    chapter_count, last_chapter_label = _chapter_count_state_from_chunks(chunks)
    last_checkpoint_index = start_index
    last_checkpoint_time = monotonic()
    last_progress_time = last_checkpoint_time
    try:
        for chunk_index in range(start_index, progress_total):
            raise_if_cancelled(cancel_requested)
            paragraph_record = paragraph_records[chunk_index]
            if _is_narratable_record(paragraph_record):
                chunk = _build_chunk_payload(
                    len(chunks) + 1,
                    paragraph_record,
                    starts_after_scene_separator=_starts_after_scene_separator(
                        paragraph_records,
                        chunk_index,
                    ),
                )
                next_chapter_count, next_chapter_label = _update_chapter_count(
                    chapter_count,
                    last_chapter_label,
                    chunk,
                )
                chunks.append(chunk)
                chapter_count = next_chapter_count
                last_chapter_label = next_chapter_label
            document["chunks"] = chunks
            document["next_paragraph"] = chunk_index + 2
            progress_current = chunk_index + 1
            current_time = monotonic()
            if _should_write_checkpoint(
                progress_current,
                last_checkpoint_index,
                current_time,
                last_checkpoint_time,
            ):
                chunking_document_service.write_chunking_document(resolved_project_root, document)
                last_checkpoint_index = progress_current
                last_checkpoint_time = current_time
            if _should_emit_progress(
                progress_current,
                progress_total,
                current_time,
                last_progress_time,
            ):
                _emit_progress(
                    progress_callback,
                    progress_current=progress_current,
                    progress_total=progress_total,
                    message="Deterministic chunking in progress...",
                )
                last_progress_time = current_time
    except OperationCancelledError:
        document["status"] = "cancelled"
        chunking_document_service.write_chunking_document(resolved_project_root, document)
        raise
    except Exception:
        document["status"] = "failed"
        chunking_document_service.write_chunking_document(resolved_project_root, document)
        raise

    document["status"] = "completed"
    document["next_paragraph"] = None
    document["warnings"] = _build_chunking_warnings(chapter_count)
    chunking_document_service.write_chunking_document(resolved_project_root, document)
    operation_state = chunking_document_service.derive_operation_state(document)
    project_workspace_service.sync_manifest_operation_summary(
        resolved_project_root,
        "chunking",
        operation_state,
        current_stage="translation_ready",
    )
    _emit_progress(
        progress_callback,
        progress_current=progress_total,
        progress_total=progress_total,
        message="Deterministic chunking completed.",
    )
    return chunking_document_service.derive_report(document)


@trace_function(_CHUNKING_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Load one optional chunking operation-state payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted chunking operation-state payload or `None`.
    @exception  None
    """
    document = chunking_document_service.load_chunking_document(project_root)
    return None if document is None else chunking_document_service.derive_operation_state(document)


@trace_function(_CHUNKING_LOGGER)
def load_chunks(project_root: str | Path) -> list[ChunkPayload]:
    """
    @brief      Load the optional persisted chunk artifact from one project.
    @param[in]  project_root Active project root folder.
    @return     Ordered chunk payload list.
    @exception  None
    """
    return chunking_document_service.load_chunks(project_root)


# LOCAL HELPERS


def _is_narratable_record(paragraph_record: dict[str, object]) -> bool:
    """Return whether one Cleanup paragraph should be materialized as audio text."""
    return not cleanup_text_analysis_service.is_scene_separator_artifact(
        str(paragraph_record.get("text") or ""),
        str(paragraph_record.get("role") or "body"),
    )


def _starts_after_scene_separator(
    paragraph_records: list[dict[str, object]],
    paragraph_index: int,
) -> bool:
    """Return whether one narratable paragraph follows an omitted scene separator."""
    return paragraph_index > 0 and not _is_narratable_record(
        paragraph_records[paragraph_index - 1]
    )


def _build_paragraph_records(cleaned_text: str, project_root: str | Path | None = None) -> list[dict[str, object]]:
    """
    @brief      Build the paragraph records.
    @param[in]  cleaned_text Text value for `cleaned_text`.
    @return     Derived helper result.
    """
    if project_root is not None:
        paragraph_records = cleanup_metadata_service.load_completed_paragraph_records(
            project_root,
            cleaned_text,
        )
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
    *,
    starts_after_scene_separator: bool = False,
) -> ChunkPayload:
    """
    @brief      Build the chunk payload.
    @param[in]  sequence_index Value for `sequence_index`.
    @param[in]  paragraph_record Value for `paragraph_record`.
    @return     Derived helper result.
    """
    return {
        "chunk_id": f"chunk-{sequence_index:04d}",
        "sequence_index": sequence_index,
        "text": str(paragraph_record["text"]),
        "cleanup_boundary_confidence": paragraph_record.get("boundary_confidence"),
        "cleanup_joined_across_page_break": bool(paragraph_record.get("joined_across_page_break", False)),
        "cleanup_warning_flags": list(paragraph_record.get("warning_flags", [])),
        "cleanup_role": str(paragraph_record.get("role") or "body"),
        "starts_after_scene_separator": starts_after_scene_separator,
    }


def _should_write_checkpoint(
    progress_current: int,
    last_checkpoint_index: int,
    current_time: float,
    last_checkpoint_time: float,
) -> bool:
    """
    @brief      Return whether deterministic chunking should persist one running checkpoint.
    @param[in]  progress_current Current completed paragraph count.
    @param[in]  last_checkpoint_index Paragraph count at the previous checkpoint.
    @param[in]  current_time Current monotonic timestamp.
    @param[in]  last_checkpoint_time Monotonic timestamp of the previous checkpoint.
    @return     True when checkpoint interval policy is met.
    @exception  None
    """
    return (
        progress_current - last_checkpoint_index >= _CHECKPOINT_PARAGRAPH_INTERVAL
        or current_time - last_checkpoint_time >= _CHECKPOINT_TIME_INTERVAL_SECONDS
    )


def _should_emit_progress(
    progress_current: int,
    progress_total: int,
    current_time: float,
    last_progress_time: float,
) -> bool:
    """
    @brief      Return whether deterministic chunking should emit one non-terminal progress callback.
    @param[in]  progress_current Current completed paragraph count.
    @param[in]  progress_total Total paragraph count.
    @param[in]  current_time Current monotonic timestamp.
    @param[in]  last_progress_time Monotonic timestamp of the previous progress callback.
    @return     True when progress should be emitted.
    @exception  None
    """
    return (
        progress_current < progress_total
        and current_time - last_progress_time >= _PROGRESS_EMIT_INTERVAL_SECONDS
    )


def _build_chunking_warnings(chapter_count: int) -> list[str]:
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


def _chapter_count_state_from_chunks(chunks: list[ChunkPayload]) -> tuple[int, str | None]:
    """
    @brief      Build the incremental chapter-count state for an existing chunk prefix.
    @param[in]  chunks Current ordered chunk payload prefix.
    @return     Detected chapter count and last detected chapter label.
    @exception  None
    """
    chapter_count = 0
    last_chapter_label: str | None = None
    for chunk in chunks:
        chapter_count, last_chapter_label = _update_chapter_count(chapter_count, last_chapter_label, chunk)
    return chapter_count, last_chapter_label


def _update_chapter_count(
    chapter_count: int,
    last_chapter_label: str | None,
    chunk: ChunkPayload,
) -> tuple[int, str | None]:
    """
    @brief      Update chapter-count state from one newly appended chunk.
    @param[in]  chapter_count Current detected chapter count.
    @param[in]  last_chapter_label Previous detected chapter label.
    @param[in]  chunk Newly appended chunk payload.
    @return     Updated chapter count and last detected chapter label.
    @exception  None
    """
    chapter_label = _chapter_label_from_text(str(chunk.get("text", "")))
    if chapter_label is not None and chapter_label != last_chapter_label:
        return chapter_count + 1, chapter_label
    return chapter_count, last_chapter_label


def _chapter_count_from_chunks(chunks: list[ChunkPayload]) -> int:
    """
    @brief      Count distinct chapter or scene headings from chunk text.
    @param[in]  chunks Value for `chunks`.
    @return     Helper result.
    """
    chapter_labels: list[str] = []
    for chunk in chunks:
        chapter_label = _chapter_label_from_text(str(chunk.get("text", "")))
        if chapter_label is not None and (not chapter_labels or chapter_labels[-1] != chapter_label):
            chapter_labels.append(chapter_label)
    return len(chapter_labels)


def _chapter_label_from_text(chunk_text: str) -> str | None:
    """
    @brief      Return the first chapter or scene heading found in chunk text.
    @param[in]  chunk_text Chunk text to scan.
    @return     Detected chapter label or `None`.
    """
    for line in chunk_text.splitlines():
        chapter_label = _detect_chapter_label(line)
        if chapter_label is not None:
            return chapter_label
    return None


def _detect_chapter_label(paragraph_text: str) -> str | None:
    """
    @brief      Detect the chapter label.
    @param[in]  paragraph_text Text value for `paragraph_text`.
    @return     Derived helper result.
    """
    normalized = paragraph_text.strip()
    if len(normalized) > 100:
        return None
    for pattern in _CHAPTER_PATTERNS:
        if pattern.fullmatch(normalized):
            return normalized
    return None


# END OF FILE
