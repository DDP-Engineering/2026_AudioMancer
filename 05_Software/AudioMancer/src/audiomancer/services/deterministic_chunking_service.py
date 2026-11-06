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
from time import monotonic

from audiomancer import config
from audiomancer.chunking import materialization
from audiomancer.services import (
    chunking_document_service,
    chunking_input_service,
    chunking_publication_service,
    cleanup_text_analysis_service,
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
    *,
    restart: bool = False,
) -> ChunkingReportPayload:
    """
    @brief      Run deterministic chunking for one active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  progress_callback Optional zero-copy progress callback.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  restart Explicitly discard an unfinished checkpoint and start from source.
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

    existing_document = None if restart else chunking_document_service.load_checkpoint(resolved_project_root)
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
        expected_chunk_count = sum(_is_narratable_record(record) for record in paragraph_records[:start_index])
        if len(chunks) != expected_chunk_count:
            raise chunking_document_service.IncompatibleChunkingDocumentError(
                "Chunking data is incompatible. Use Reset Chunking before continuing."
            )

    plan_identity = materialization.plan_fingerprint(paragraph_records)
    if existing_document is not None and existing_document["status"] in chunking_document_service.RESUMABLE_STATUSES:
        if existing_document["plan_fingerprint"] != plan_identity:
            raise ValueError("Cleanup paragraph plan changed. Restart Chunking before continuing.")
        materialization.validate_coverage(chunks, paragraph_records, start_index)

    document = chunking_document_service.build_document(
        status="running",
        mode="deterministic",
        source_text=input_text,
        chunks=chunks,
        next_paragraph=start_index + 1,
        plan_fingerprint=plan_identity,
    )
    checkpoint_path = chunking_document_service.write_checkpoint(resolved_project_root, document)
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
                chunking_document_service.write_checkpoint(resolved_project_root, document)
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
        chunking_document_service.write_checkpoint(resolved_project_root, document)
        raise
    except Exception:
        document["status"] = "failed"
        chunking_document_service.write_checkpoint(resolved_project_root, document)
        raise

    document["status"] = "completed"
    document["next_paragraph"] = None
    document["warnings"] = _build_chunking_warnings(chapter_count)
    try:
        materialization.validate_coverage(chunks, paragraph_records)
        chunking_publication_service.publish_chunks(
            resolved_project_root, document, check_cancelled=lambda: raise_if_cancelled(cancel_requested)
        )
    except Exception as error:
        document["status"] = "cancelled" if isinstance(error, OperationCancelledError) else "failed"
        document["next_paragraph"] = len(paragraph_records) + 1
        try:
            chunking_document_service.write_checkpoint(
                resolved_project_root, document, pending=checkpoint_path.name == config.CHUNKING_PENDING_FILE_NAME
            )
        except (OSError, ValueError):
            _CHUNKING_LOGGER.exception("Could not persist terminal Chunking checkpoint after publication failure")
        raise
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
    document = chunking_document_service.load_checkpoint(project_root)
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
    return paragraph_index > 0 and not _is_narratable_record(paragraph_records[paragraph_index - 1])


_build_paragraph_records = chunking_input_service.load_paragraph_records


def _build_chunk_payload(sequence_index, paragraph_record, *, starts_after_scene_separator=False):
    """@brief Build one deterministic source chunk with shared structural metadata."""
    chunk = materialization._build_chunk_from_range([paragraph_record], 0, 0, sequence_index)
    number = paragraph_record.get("paragraph_number")
    chunk["source_paragraph_start"] = number
    chunk["source_paragraph_end"] = number
    chunk["starts_after_scene_separator"] = starts_after_scene_separator
    return chunk


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
    return progress_current < progress_total and current_time - last_progress_time >= _PROGRESS_EMIT_INTERVAL_SECONDS


_build_chunking_warnings = materialization.build_warnings


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
    chapter_label = chunking_document_service.chapter_label_from_text(str(chunk.get("text", "")))
    if chapter_label is not None and chapter_label != last_chapter_label:
        return chapter_count + 1, chapter_label
    return chapter_count, last_chapter_label


# END OF FILE
