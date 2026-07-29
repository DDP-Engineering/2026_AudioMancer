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
@author Eng. Dan Dumitru Pasare
@date 2026-04-11
@version 0.6.0
"""

# IMPORTS

from functools import partial
import json
from pathlib import Path
import re

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
    build_operation_state_payload,
    emit_progress_update,
    load_operation_state_file,
    raise_if_cancelled,
)
from audiomancer.services.persistence_service import write_json_atomic
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

# @brief Component logger used by the deterministic chunking workflow.
_CHUNKING_LOGGER = get_component_logger("deterministic_chunking")
_emit_progress = partial(emit_progress_update, include_token_usage=False)

# @brief Supported chapter-heading detection patterns used for transient chapter-count and prompt context.
_CHAPTER_PATTERNS = (
    re.compile(r"^(chapter|capitolul|scene|scena)\s+[\wIVXLCDM0-9][\wIVXLCDM0-9 .:-]*$", re.IGNORECASE),
    re.compile(r"^[IVXLCDM]+$", re.IGNORECASE),
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.3.0
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
    try:
        for chunk_index in range(start_index, progress_total):
            raise_if_cancelled(cancel_requested)
            paragraph_record = paragraph_records[chunk_index]
            if _is_narratable_record(paragraph_record):
                chunk = _build_chunk_payload(len(chunks) + 1, paragraph_record)
                chunks.append(chunk)
                chapter_count, last_chapter_label = _update_chapter_count(
                    chapter_count,
                    last_chapter_label,
                    chunk,
                )
            document["chunks"] = chunks
            document["next_paragraph"] = chunk_index + 2
            chunking_document_service.write_chunking_document(resolved_project_root, document)
            _emit_progress(
                progress_callback,
                progress_current=chunk_index + 1,
                progress_total=progress_total,
                message="Deterministic chunking in progress...",
            )
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.1
    """
    document = chunking_document_service.load_chunking_document(project_root)
    return None if document is None else chunking_document_service.derive_operation_state(document)


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
    document = chunking_document_service.load_chunking_document(project_root)
    return None if document is None else chunking_document_service.derive_report(document)


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
    return chunking_document_service.load_chunks(project_root)


# LOCAL HELPERS


def _is_narratable_record(paragraph_record: dict[str, object]) -> bool:
    """Return whether one Cleanup paragraph should be materialized as audio text."""
    return not cleanup_text_analysis_service.is_scene_separator_artifact(
        str(paragraph_record.get("text") or ""),
        str(paragraph_record.get("role") or "body"),
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
) -> ChunkPayload:
    """
    @brief      Build the chunk payload.
    @param[in]  sequence_index Value for `sequence_index`.
    @param[in]  paragraph_record Value for `paragraph_record`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    return {
        "chunk_id": f"chunk-{sequence_index:04d}",
        "sequence_index": sequence_index,
        "text": str(paragraph_record["text"]),
        "cleanup_boundary_confidence": paragraph_record.get("boundary_confidence"),
        "cleanup_joined_across_page_break": bool(paragraph_record.get("joined_across_page_break", False)),
        "cleanup_warning_flags": list(paragraph_record.get("warning_flags", [])),
        "cleanup_role": str(paragraph_record.get("role") or "body"),
    }


def semantic_cut_priority(role: str, sentence_complete: bool) -> int:
    """Return the approved semantic cut tier before any size-balance cost."""
    if role == "heading":
        return 0
    if role == "scene_separator":
        return 1
    if role in {"list_item", "verse", "preformatted", "footnote"}:
        return 2
    if sentence_complete:
        return 3
    return 4


def split_for_hard_limit(
    text: str,
    *,
    hard_limit: int,
) -> tuple[list[str], bool]:
    """Split at sentence ends, using mid-sentence cuts only for oversized sentences."""
    if hard_limit <= 0:
        raise ValueError("Chunk hard limit must be positive.")
    sentences = [
        item.strip()
        for item in cleanup_text_analysis_service.sentence_spans(str(text))
        if item.strip()
    ]
    if not sentences:
        return [], False
    result: list[str] = []
    used_mid_sentence_fallback = False
    for sentence in sentences:
        if len(sentence) <= hard_limit:
            result.append(sentence)
            continue
        used_mid_sentence_fallback = True
        remaining = sentence
        while len(remaining) > hard_limit:
            split_at = remaining.rfind(" ", 0, hard_limit + 1)
            if split_at <= 0:
                split_at = hard_limit
            result.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()
        if remaining:
            result.append(remaining)
    return result, used_mid_sentence_fallback


def _write_chunk_payload(output_path: Path, chunks: list[ChunkPayload]) -> None:
    """
    @brief      Write the chunk payload.
    @param[in]  output_path Output file path.
    @param[in]  chunks Value for `chunks`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    write_json_atomic(output_path, chunks)


def _load_partial_chunks(output_path: Path) -> list[ChunkPayload]:
    """
    @brief      Load the partial chunks.
    @param[in]  output_path Output file path.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    if not output_path.is_file():
        return []
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _CHUNKING_LOGGER.warning("Ignored unreadable partial chunk artifact: %s", error)
        return []
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


def _load_resume_state(state_path: Path) -> OperationStatePayload:
    """
    @brief      Load resumable chunking state, treating malformed JSON as no state.
    @param[in]  state_path Operation-state file path.
    @return     Persisted state payload or an empty dictionary.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    try:
        return load_operation_state_file(state_path) or {}
    except (OSError, TypeError, json.JSONDecodeError) as error:
        _CHUNKING_LOGGER.warning("Restarting deterministic chunking after unreadable state file: %s", error)
        return {}


def _write_running_state(
    state_path: Path,
    project_root: Path,
    input_snapshot_path: Path,
    output_path: Path,
    started_at: str,
    progress_current: int,
    progress_total: int,
    chunks: list[ChunkPayload],
    chapter_count: int,
    status: str = "running",
    completed_at: str | None = None,
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
    @param[in]  chapter_count Current detected chapter count.
    @param[in]  status Operation status to persist.
    @param[in]  completed_at Optional terminal timestamp.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    running_state = _build_operation_state(
        project_root,
        input_snapshot_path=input_snapshot_path,
        output_path=output_path,
        report_path=None,
        status=status,
        progress_current=progress_current,
        progress_total=progress_total,
        started_at=started_at,
        completed_at=completed_at,
        warnings=[],
        chunk_count=len(chunks),
        chapter_count=chapter_count,
        resume_checkpoint=None if status == "completed" else {"next_chunk_index": progress_current},
    )
    write_json_atomic(state_path, running_state)


def _persist_terminal_state(
    state_path: Path,
    project_root: Path,
    input_snapshot_path: Path,
    output_path: Path,
    started_at: str,
    progress_total: int,
    chunks: list[ChunkPayload],
    chapter_count: int,
    status: str,
) -> None:
    """
    @brief      Persist the latest deterministic chunks and a terminal resumable state.
    @param[in]  state_path Operation-state file path.
    @param[in]  project_root Active project root folder.
    @param[in]  input_snapshot_path Input snapshot file path.
    @param[in]  output_path Output file path.
    @param[in]  started_at Original operation start timestamp.
    @param[in]  progress_total Total paragraph count.
    @param[in]  chunks Latest in-memory chunk payloads.
    @param[in]  chapter_count Latest detected chapter count.
    @param[in]  status Terminal status token.
    @return     None
    @exception  OSError Raised when persistence fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    _write_chunk_payload(output_path, chunks)
    _write_running_state(
        state_path,
        project_root,
        input_snapshot_path,
        output_path,
        started_at,
        len(chunks),
        progress_total,
        chunks,
        chapter_count,
        status=status,
        completed_at=_utc_now_iso(),
    )


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
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
    @brief      Return whether deterministic chunking should emit one progress callback.
    @param[in]  progress_current Current completed paragraph count.
    @param[in]  progress_total Total paragraph count.
    @param[in]  current_time Current monotonic timestamp.
    @param[in]  last_progress_time Monotonic timestamp of the previous progress callback.
    @return     True when progress should be emitted.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    return progress_current >= progress_total or current_time - last_progress_time >= _PROGRESS_EMIT_INTERVAL_SECONDS


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
    @param[in]  resume_checkpoint Value for `resume_checkpoint`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    _ = project_root
    _ = input_snapshot_path
    _ = output_path
    _ = report_path
    return build_operation_state_payload(
        status=status,
        progress_current=progress_current,
        progress_total=progress_total,
        mode="deterministic",
        warning_count=len(warnings),
        metadata={
            "warnings": list(warnings),
            "chunk_count": chunk_count,
            "detected_chapter_count": chapter_count,
        },
        resume_checkpoint=resume_checkpoint,
    )


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


def _chapter_count_state_from_chunks(chunks: list[ChunkPayload]) -> tuple[int, str | None]:
    """
    @brief      Build the incremental chapter-count state for an existing chunk prefix.
    @param[in]  chunks Current ordered chunk payload prefix.
    @return     Detected chapter count and last detected chapter label.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
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


# END OF FILE
