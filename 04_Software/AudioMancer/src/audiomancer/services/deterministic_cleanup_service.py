#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file deterministic_cleanup_service.py
@brief Deterministic text cleanup helpers for AudioMancer.
@details Consumes extracted text, removes repeated headers and footers plus
         page-number noise conservatively, applies script-aware paragraph
         cleanup for supported languages, preserves paragraph and chapter
         structure, and persists cleanup artifacts with resumable state.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.5.1
"""

# IMPORTS

from collections import Counter
from functools import partial
import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import cleanup_metadata_service, cleanup_text_analysis_service, project_workspace_service
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    build_operation_output_path,
    build_operation_state_payload,
    emit_progress_update,
    load_operation_state_file,
    load_operation_state_payload,
    raise_if_cancelled,
    relative_to_project,
    resolve_project_relative_path,
)
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

# @brief Component logger used by the deterministic cleanup workflow.
_CLEANUP_LOGGER = get_component_logger("deterministic_cleanup")
_emit_progress = partial(emit_progress_update, include_token_usage=False)
# @brief Persisted deterministic cleanup report payload type.
CleanupReportPayload = dict[str, object]
# @brief Persisted deterministic cleanup operation-state payload type.
OperationStatePayload = dict[str, object]
# @brief Internal paragraph-line accumulator type used while rebuilding cleaned text.
CleanupLineParts = list[dict[str, object]]

# @brief Internal cleaned paragraph metadata record type.
CleanupParagraphRecord = dict[str, object]
# @brief Page-break separator pattern used to reconstruct extracted PDF pages.
_PAGE_SPLIT_PATTERN = re.compile(r"\n\n\f\n\n")
# @brief Conservative page-number matchers used during deterministic cleanup.
_PAGE_NUMBER_PATTERNS = (
    re.compile(r"^(?:page\s+)?\d+(?:\s*(?:/|of)\s*\d+)?\.?$", re.IGNORECASE),
    re.compile(r"^[-–—]\s*\d+\s*[-–—]$"),
    re.compile(r"^第\s*[0-9０-９一二三四五六七八九十百千〇零]+\s*[页頁]$"),
)
# @brief Roman numeral page-number matcher used only at page edges.
_ROMAN_PAGE_NUMBER_PATTERN = re.compile(r"^[ivxlcdm]{1,8}\.?$", re.IGNORECASE)
# @brief Decorative-separator matcher used to remove non-story break lines.
_SEPARATOR_LINE_PATTERN = re.compile(r"^[*#=_~.\-]{3,}$|^(?:[*#=_~.\-]\s+){2,}[*#=_~.\-]?$")
# @brief Dialogue formatter rule that inserts line breaks before continued spoken text.
_DIALOGUE_BREAK_AFTER_PUNCTUATION_PATTERN = re.compile(
    r'([:;.!?\u2026]["Ãƒâ€šÃ‚Â»ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â\']?)\s+-\s+(?=[A-ZÃƒâ€žÃ¢â‚¬Å¡ÃƒÆ’Ã¢â‚¬Å¡ÃƒÆ’Ã…Â½ÃƒË†Ã‹Å“ÃƒË†Ã…Â¡])'
)  # noqa: E501
# @brief Dialogue formatter rule that inserts line breaks after attributions and pauses.
_DIALOGUE_BREAK_AFTER_ATTRIBUTION_PATTERN = re.compile(
    r"([,:])\s+-\s+(?=[A-ZÃƒâ€žÃ¢â‚¬Å¡ÃƒÆ’Ã¢â‚¬Å¡ÃƒÆ’Ã…Â½ÃƒË†Ã‹Å“ÃƒË†Ã…Â¡])"
)  # noqa: E501


# PUBLIC API


@trace_function(_CLEANUP_LOGGER)
def clean_text(
    project_root: str | Path,
    manifest: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
) -> CleanupReportPayload:
    """
    @brief      Run deterministic cleanup for one active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  progress_callback Optional zero-copy progress callback.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Cleanup report payload for the persisted artifacts.
    @exception  FileNotFoundError Raised when the extracted input is missing.
    @exception  ValueError Raised when cleanup cannot produce usable text.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.3.3
    """
    resolved_project_root = Path(project_root)
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        raise ValueError("No imported source is available for deterministic cleanup.")

    extracted_relative_path = manifest.get("extracted_text_relative_path")
    if not isinstance(extracted_relative_path, str) or not extracted_relative_path.strip():
        raise FileNotFoundError("Deterministic cleanup requires extracted text first.")

    extracted_path = resolve_project_relative_path(resolved_project_root, extracted_relative_path)
    if not extracted_path.is_file():
        raise FileNotFoundError(f"Extracted text is missing: {extracted_path}")

    _ = source_document
    input_snapshot_path = extracted_path

    output_path = build_operation_output_path(
        resolved_project_root,
        "cleanup",
        config.CLEANED_TEXT_FILE_NAME,
    )
    report_path = build_operation_output_path(
        resolved_project_root,
        "cleanup",
        config.CLEANUP_REPORT_FILE_NAME,
    )
    state_path = build_operation_output_path(
        resolved_project_root,
        "cleanup",
        config.CLEANUP_STATE_FILE_NAME,
    )

    input_text = extracted_path.read_text(encoding="utf-8")
    pages = _split_pages(input_text)
    if not any(page.strip() for page in pages):
        raise ValueError("Extracted text does not contain any content to clean.")

    existing_state = load_operation_state_file(state_path) or {}
    progress_total = len(pages)
    started_at = str(existing_state.get("started_at") or _utc_now_iso())
    resume_checkpoint = dict(existing_state.get("resume_checkpoint") or {})
    start_page_index = int(resume_checkpoint.get("next_page_index", 0))
    cleaned_pages = list(existing_state.get("metadata", {}).get("cleaned_pages") or [])
    removed_header_footer_count = int(existing_state.get("metadata", {}).get("removed_header_footer_line_count", 0))
    removed_page_number_count = int(existing_state.get("metadata", {}).get("removed_page_number_line_count", 0))
    removed_separator_count = int(existing_state.get("metadata", {}).get("removed_separator_line_count", 0))

    if len(cleaned_pages) != progress_total or start_page_index <= 0:
        cleaned_pages, removed_header_footer_count = _remove_repeated_headers_and_footers(pages)
        removed_page_number_count = 0
        removed_separator_count = 0
        start_page_index = 0
        output_path.write_text("", encoding="utf-8")

    paragraph_records: list[CleanupParagraphRecord] = []
    current_lines: CleanupLineParts = []
    if start_page_index > 0 and output_path.is_file():
        restored_output = output_path.read_text(encoding="utf-8").strip()
        paragraph_records = [
            {"text": paragraph.strip(), "boundary_confidence": "strong"}
            for paragraph in restored_output.split("\n\n")
            if paragraph.strip()
        ]

    warnings: list[str] = []
    _write_running_state(
        state_path,
        resolved_project_root,
        input_snapshot_path,
        output_path,
        started_at,
        start_page_index,
        progress_total,
        warnings,
        cleaned_pages,
        removed_header_footer_count,
        removed_page_number_count,
        removed_separator_count,
    )
    _emit_progress(
        progress_callback,
        progress_current=start_page_index,
        progress_total=progress_total,
        message="Deterministic cleanup in progress...",
    )

    for page_index in range(start_page_index, progress_total):
        raise_if_cancelled(cancel_requested)
        page_paragraphs, current_lines, page_number_removed_count, separator_removed_count = _build_page_paragraphs(
            cleaned_pages[page_index],
            cleaned_pages[page_index + 1] if page_index + 1 < len(cleaned_pages) else None,
            current_lines,
            page_index,
        )
        removed_page_number_count += page_number_removed_count
        removed_separator_count += separator_removed_count
        paragraph_records.extend(page_paragraphs)
        _write_partial_output(output_path, [str(record["text"]) for record in paragraph_records], current_lines)
        _write_running_state(
            state_path,
            resolved_project_root,
            input_snapshot_path,
            output_path,
            started_at,
            page_index + 1,
            progress_total,
            warnings,
            cleaned_pages,
            removed_header_footer_count,
            removed_page_number_count,
            removed_separator_count,
        )
        _emit_progress(
            progress_callback,
            progress_current=page_index + 1,
            progress_total=progress_total,
            message="Deterministic cleanup in progress...",
        )

    if current_lines:
        paragraph_records.append(_build_paragraph_record(current_lines))

    paragraph_records = [
        {**record, "text": _format_dialogue_lines(str(record["text"]))}
        for record in paragraph_records
        if str(record.get("text", "")).strip()
    ]
    paragraph_records = cleanup_metadata_service.finalize_paragraph_records(paragraph_records)
    if not paragraph_records:
        raise ValueError("Cleanup removed all usable text.")

    paragraph_texts = [str(record["text"]) for record in paragraph_records]
    cleaned_text = "\n\n".join(paragraph_texts).strip() + "\n"
    output_path.write_text(cleaned_text, encoding="utf-8")
    metadata_payload = cleanup_metadata_service.write_cleanup_metadata(
        resolved_project_root,
        input_snapshot_path,
        output_path,
        paragraph_records,
        "deterministic",
    )

    detected_language = _detect_language(cleaned_text)
    chapter_count = _count_detected_chapters(paragraph_texts)
    page_break_repair_count = int(metadata_payload.get("page_break_repair_count", 0))
    weak_boundary_count = int(metadata_payload.get("weak_boundary_count", 0))
    warnings = _build_cleanup_warnings(detected_language, chapter_count, page_break_repair_count, weak_boundary_count)
    report_payload: CleanupReportPayload = {
        "input_relative_path": relative_to_project(resolved_project_root, input_snapshot_path),
        "cleaned_text_relative_path": relative_to_project(resolved_project_root, output_path),
        "cleaned_text_metadata_relative_path": relative_to_project(
            resolved_project_root,
            cleanup_metadata_service.cleanup_metadata_path(resolved_project_root),
        ),
        "cleaned_at": _utc_now_iso(),
        "detected_language": detected_language,
        "warnings": warnings,
        "paragraph_count": len(paragraph_texts),
        "page_break_repair_count": page_break_repair_count,
        "weak_boundary_count": weak_boundary_count,
        "removed_line_count": (removed_header_footer_count + removed_page_number_count + removed_separator_count),
        "removed_header_footer_line_count": removed_header_footer_count,
        "removed_page_number_line_count": removed_page_number_count,
        "removed_separator_line_count": removed_separator_count,
        "detected_chapter_count": chapter_count,
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
        metadata_path=cleanup_metadata_service.cleanup_metadata_path(resolved_project_root),
        status="completed",
        progress_current=progress_total,
        progress_total=progress_total,
        started_at=started_at,
        completed_at=report_payload["cleaned_at"],
        warnings=warnings,
        cleaned_pages=None,
        removed_header_footer_count=removed_header_footer_count,
        removed_page_number_count=removed_page_number_count,
        removed_separator_count=removed_separator_count,
        resume_checkpoint=None,
        detected_language=detected_language,
        paragraph_count=len(paragraph_texts),
        chapter_count=chapter_count,
    )
    state_path.write_text(
        json.dumps(completed_state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    project_workspace_service.sync_manifest_operation_summary(
        resolved_project_root,
        "cleanup",
        completed_state,
        current_stage="text_chunking_ready",
        extra_fields={"original_language": detected_language},
    )
    _emit_progress(
        progress_callback,
        progress_current=progress_total,
        progress_total=progress_total,
        message="Deterministic cleanup completed.",
    )
    return report_payload


@trace_function(_CLEANUP_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Load one optional cleanup operation-state payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted cleanup operation-state payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    return load_operation_state_payload(project_root, "cleanup", config.CLEANUP_STATE_FILE_NAME)


@trace_function(_CLEANUP_LOGGER)
def load_cleanup_report(project_root: str | Path) -> CleanupReportPayload | None:
    """
    @brief      Load one optional deterministic cleanup report payload.
    @param[in]  project_root Active project root folder.
    @return     Cleanup report payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    report_path = build_operation_output_path(
        project_root,
        "cleanup",
        config.CLEANUP_REPORT_FILE_NAME,
    )
    if not report_path.is_file():
        return None
    return dict(json.loads(report_path.read_text(encoding="utf-8")))


# LOCAL HELPERS


def _write_partial_output(
    output_path: Path,
    paragraphs: list[str],
    current_lines: CleanupLineParts,
) -> None:
    """
    @brief      Write the partial output.
    @param[in]  output_path Output file path.
    @param[in]  paragraphs Value for `paragraphs`.
    @param[in]  current_lines Value for `current_lines`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    payload_parts = list(paragraphs)
    if current_lines:
        payload_parts.append(_compose_paragraph_text(current_lines))
    output_text = "\n\n".join(item for item in payload_parts if item.strip())
    if output_text:
        output_text = output_text.strip() + "\n"
    output_path.write_text(output_text, encoding="utf-8")


def _write_running_state(
    state_path: Path,
    project_root: Path,
    input_snapshot_path: Path,
    output_path: Path,
    started_at: str,
    progress_current: int,
    progress_total: int,
    warnings: list[str],
    cleaned_pages: list[str],
    removed_header_footer_count: int,
    removed_page_number_count: int,
    removed_separator_count: int,
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
    @param[in]  warnings Value for `warnings`.
    @param[in]  cleaned_pages Value for `cleaned_pages`.
    @param[in]  removed_header_footer_count Value for `removed_header_footer_count`.
    @param[in]  removed_page_number_count Value for `removed_page_number_count`.
    @param[in]  removed_separator_count Value for `removed_separator_count`.
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
        metadata_path=None,
        status="running",
        progress_current=progress_current,
        progress_total=progress_total,
        started_at=started_at,
        completed_at=None,
        warnings=warnings,
        cleaned_pages=cleaned_pages,
        removed_header_footer_count=removed_header_footer_count,
        removed_page_number_count=removed_page_number_count,
        removed_separator_count=removed_separator_count,
        resume_checkpoint={"next_page_index": progress_current},
        detected_language=None,
        paragraph_count=None,
        chapter_count=None,
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
    metadata_path: Path | None,
    status: str,
    progress_current: int,
    progress_total: int,
    started_at: str,
    completed_at: str | None,
    warnings: list[str],
    cleaned_pages: list[str] | None,
    removed_header_footer_count: int,
    removed_page_number_count: int,
    removed_separator_count: int,
    resume_checkpoint: dict[str, object] | None,
    detected_language: str | None,
    paragraph_count: int | None,
    chapter_count: int | None,
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
    @param[in]  cleaned_pages Value for `cleaned_pages`.
    @param[in]  removed_header_footer_count Value for `removed_header_footer_count`.
    @param[in]  removed_page_number_count Value for `removed_page_number_count`.
    @param[in]  removed_separator_count Value for `removed_separator_count`.
    @param[in]  resume_checkpoint Value for `resume_checkpoint`.
    @param[in]  detected_language Value for `detected_language`.
    @param[in]  paragraph_count Value for `paragraph_count`.
    @param[in]  chapter_count Value for `chapter_count`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    artifact_paths: list[str] = []
    if report_path is not None and report_path.is_file():
        artifact_paths.append(relative_to_project(project_root, report_path))
    output_paths = [relative_to_project(project_root, output_path)] if output_path.is_file() else []
    if metadata_path is not None and metadata_path.is_file():
        output_paths.append(relative_to_project(project_root, metadata_path))
    return build_operation_state_payload(
        status=status,
        input_paths=[relative_to_project(project_root, input_snapshot_path)],
        output_paths=output_paths,
        artifact_paths=artifact_paths,
        progress_current=progress_current,
        progress_total=progress_total,
        mode="deterministic",
        started_at=started_at,
        completed_at=completed_at,
        warning_count=len(warnings),
        metadata={
            "warnings": list(warnings),
            "cleaned_pages": None if cleaned_pages is None else list(cleaned_pages),
            "removed_header_footer_line_count": removed_header_footer_count,
            "removed_page_number_line_count": removed_page_number_count,
            "removed_separator_line_count": removed_separator_count,
            "detected_language": detected_language,
            "paragraph_count": paragraph_count,
            "detected_chapter_count": chapter_count,
        },
        resume_checkpoint=resume_checkpoint,
    )


def _split_pages(extracted_text: str) -> list[str]:
    """
    @brief      Execute the split pages helper.
    @param[in]  extracted_text Text value for `extracted_text`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized = extracted_text.replace("\r\n", "\n").replace("\r", "\n")
    segments = [segment for segment in _PAGE_SPLIT_PATTERN.split(normalized) if segment.strip()]
    return segments or [normalized]


def _remove_repeated_headers_and_footers(pages: list[str]) -> tuple[list[str], int]:
    """
    @brief      Remove repeated normalized page-edge headers and footers.
    @param[in]  pages Value for `pages`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
    """
    top_counts: Counter[str] = Counter()
    bottom_counts: Counter[str] = Counter()
    page_entries: list[tuple[list[str], list[int]]] = []
    for page in pages:
        lines = [line.rstrip() for line in page.split("\n")]
        non_empty_indexes = [index for index, line in enumerate(lines) if line.strip()]
        page_entries.append((lines, non_empty_indexes))
        for index in non_empty_indexes[:2]:
            candidate = lines[index].strip()
            if _is_header_footer_candidate(candidate):
                top_counts[_header_footer_match_key(candidate)] += 1
        for index in non_empty_indexes[-2:]:
            candidate = lines[index].strip()
            if _is_header_footer_candidate(candidate):
                bottom_counts[_header_footer_match_key(candidate)] += 1
    repeated_top = {value for value, count in top_counts.items() if count >= 2}
    repeated_bottom = {value for value, count in bottom_counts.items() if count >= 2}
    cleaned_pages: list[str] = []
    removed_count = 0
    for lines, non_empty_indexes in page_entries:
        candidate_indexes: set[int] = set()
        for index in non_empty_indexes[:2]:
            if _header_footer_match_key(lines[index].strip()) in repeated_top:
                candidate_indexes.add(index)
        for index in non_empty_indexes[-2:]:
            if _header_footer_match_key(lines[index].strip()) in repeated_bottom:
                candidate_indexes.add(index)
        cleaned_lines: list[str] = []
        for index, line in enumerate(lines):
            if index in candidate_indexes:
                removed_count += 1
                continue
            cleaned_lines.append(line)
        cleaned_pages.append("\n".join(cleaned_lines))
    return cleaned_pages, removed_count


def _build_page_paragraphs(
    page: str,
    next_page: str | None,
    carried_lines: CleanupLineParts,
    page_index: int,
) -> tuple[list[CleanupParagraphRecord], CleanupLineParts, int, int]:
    """
    @brief      Build the page paragraphs.
    @param[in]  page Value for `page`.
    @param[in]  next_page Value for `next_page`.
    @param[in]  carried_lines Value for `carried_lines`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    paragraph_records: list[CleanupParagraphRecord] = []
    current_lines = list(carried_lines)
    removed_page_number_count = 0
    removed_separator_count = 0
    merge_with_previous_line = bool(carried_lines)
    normalized_lines = [re.sub(r"\s+", " ", raw_line).strip() for raw_line in page.split("\n")]
    page_edge_indexes = set(_page_edge_line_indexes(normalized_lines))
    first_content_line_seen = False
    for line_index, normalized_line in enumerate(normalized_lines):
        if not normalized_line:
            if current_lines:
                next_line = _next_content_line(normalized_lines, line_index + 1)
                if next_line is None:
                    next_line = _first_content_line(next_page) if next_page is not None else None
                if _should_continue_paragraph(_line_text(current_lines[-1]), next_line):
                    merge_with_previous_line = True
                    continue
                paragraph_records.append(_build_paragraph_record(current_lines))
                current_lines = []
            continue
        if _looks_like_page_number(normalized_line, page_edge=line_index in page_edge_indexes):
            removed_page_number_count += 1
            continue
        if _looks_like_separator_line(normalized_line):
            removed_separator_count += 1
            continue
        current_lines.append(
            _build_line_part(
                normalized_line,
                merge_with_previous_line,
                page_index,
                starts_after_page_break=(page_index > 0 and not current_lines and not first_content_line_seen),
            )
        )
        first_content_line_seen = True
        merge_with_previous_line = False
    if current_lines and not _should_continue_paragraph_across_page_break(current_lines, next_page):
        paragraph_records.append(_build_paragraph_record(current_lines))
        current_lines = []
    return paragraph_records, current_lines, removed_page_number_count, removed_separator_count


def _build_cleanup_warnings(
    detected_language: str | None,
    chapter_count: int,
    page_break_repair_count: int,
    weak_boundary_count: int,
) -> list[str]:
    """
    @brief      Build the cleanup warnings.
    @param[in]  detected_language Value for `detected_language`.
    @param[in]  chapter_count Value for `chapter_count`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    warnings: list[str] = []
    if detected_language is None:
        warnings.append("Language detection did not produce a stable value.")
    if chapter_count == 0:
        warnings.append(
            "No explicit chapter or scene headings were detected; chunking will rely on sequential paragraph order."
        )
    if page_break_repair_count > 0:
        warnings.append(
            f"Repaired {page_break_repair_count} paragraph continuation(s) across page breaks before chunking."
        )
    if weak_boundary_count > 0:
        warnings.append(
            f"Preserved {weak_boundary_count} low-confidence paragraph boundary/boundaries after page breaks."
        )
    return warnings


def _count_detected_chapters(paragraph_texts: list[str]) -> int:
    """
    @brief      Count the detected chapters.
    @param[in]  paragraph_texts Value for `paragraph_texts`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    return cleanup_text_analysis_service.count_detected_chapters(paragraph_texts)


def _detect_language(text: str) -> str | None:
    """
    @brief      Detect the language.
    @param[in]  text Value for `text`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return cleanup_text_analysis_service.detect_language(text)


def _detect_chapter_label(paragraph_text: str) -> str | None:
    """
    @brief      Detect the chapter label.
    @param[in]  paragraph_text Text value for `paragraph_text`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return cleanup_text_analysis_service.detect_chapter_label(paragraph_text)


def _is_header_footer_candidate(line: str) -> bool:
    """
    @brief      Determine whether header footer candidate.
    @param[in]  line Value for `line`.
    @return     True when the helper condition is satisfied.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
    """
    normalized_line = cleanup_text_analysis_service.normalize_text_line(line)
    return (
        len(normalized_line) >= 4
        and any(character.isalpha() for character in normalized_line)
        and not _looks_like_page_number(normalized_line, page_edge=True)
        and _detect_chapter_label(normalized_line) is None
    )


def _looks_like_page_number(line: str, page_edge: bool = False) -> bool:
    """
    @brief      Determine whether page number.
    @param[in]  line Value for `line`.
    @param[in]  page_edge True when the line is near the top or bottom of a page.
    @return     True when the helper condition is satisfied.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    normalized = cleanup_text_analysis_service.normalize_text_line(line)
    if any(pattern.fullmatch(normalized) for pattern in _PAGE_NUMBER_PATTERNS):
        return True
    return page_edge and bool(_ROMAN_PAGE_NUMBER_PATTERN.fullmatch(normalized))


def _looks_like_separator_line(line: str) -> bool:
    """
    @brief      Determine whether separator line.
    @param[in]  line Value for `line`.
    @return     True when the helper condition is satisfied.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    normalized = line.strip()
    return bool(normalized) and bool(_SEPARATOR_LINE_PATTERN.fullmatch(normalized))


def _format_dialogue_lines(paragraph_text: str) -> str:
    """
    @brief      Format the dialogue lines.
    @param[in]  paragraph_text Text value for `paragraph_text`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return cleanup_text_analysis_service.format_dialogue_lines(paragraph_text)


def _build_line_part(
    text: str,
    join_with_previous: bool,
    page_index: int,
    starts_after_page_break: bool,
) -> dict[str, object]:
    """
    @brief      Build one paragraph-line accumulator payload.
    @param[in]  text Normalized line text.
    @param[in]  join_with_previous True when the line should be joined with a space.
    @param[in]  page_index Zero-based source page index.
    @param[in]  starts_after_page_break True when the line starts a paragraph after a page break.
    @return     Line accumulator payload.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return {
        "text": text,
        "join_with_previous": join_with_previous,
        "page_index": page_index,
        "starts_after_page_break": starts_after_page_break,
    }


def _line_text(line_part: dict[str, object]) -> str:
    """
    @brief      Return the normalized text from one line accumulator payload.
    @param[in]  line_part Line accumulator payload.
    @return     Line text.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return str(line_part.get("text", ""))


def _build_paragraph_record(lines: CleanupLineParts) -> CleanupParagraphRecord:
    """
    @brief      Build one page-break-aware paragraph metadata record.
    @param[in]  lines Paragraph line accumulator payloads.
    @return     Paragraph metadata record without final paragraph id.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    page_indexes = [int(line["page_index"]) for line in lines if "page_index" in line]
    starts_after_page_break = bool(lines and lines[0].get("starts_after_page_break", False))
    joined_across_page_break = len(set(page_indexes)) > 1
    warning_flags: list[str] = []
    if starts_after_page_break and len(_compose_paragraph_text(lines).split()) <= 3:
        warning_flags.append("short_fragment_after_page_break")
    boundary_confidence = "repaired" if joined_across_page_break else ("weak" if starts_after_page_break else "strong")
    return {
        "text": _compose_paragraph_text(lines),
        "source_page_start": (min(page_indexes) + 1 if page_indexes else None),
        "source_page_end": (max(page_indexes) + 1 if page_indexes else None),
        "starts_after_page_break": starts_after_page_break,
        "joined_across_page_break": joined_across_page_break,
        "boundary_confidence": boundary_confidence,
        "warning_flags": warning_flags,
    }


def _compose_paragraph_text(lines: CleanupLineParts) -> str:
    """
    @brief      Compose the paragraph text.
    @param[in]  lines Value for `lines`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not lines:
        return ""
    paragraph_text = _line_text(lines[0]).strip()
    for line_part in lines[1:]:
        separator = " " if bool(line_part.get("join_with_previous", False)) else "\n"
        paragraph_text += separator + _line_text(line_part).strip()
    return paragraph_text.strip()


def _should_continue_paragraph(
    current_last_line: str,
    next_line: str | None,
    page_break_context: bool = False,
) -> bool:
    """
    @brief      Determine whether continue paragraph.
    @param[in]  current_last_line Value for `current_last_line`.
    @param[in]  next_line Value for `next_line`.
    @return     True when the helper condition is satisfied.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    if next_line is None:
        return False
    if _detect_chapter_label(next_line) is not None:
        return False
    if _looks_like_page_number(next_line) or _looks_like_separator_line(next_line):
        return False
    current_normalized = cleanup_text_analysis_service.normalize_text_line(current_last_line)
    next_normalized = cleanup_text_analysis_service.normalize_text_line(next_line)
    if page_break_context and _has_language_agnostic_continuation_shape(current_normalized):
        return True
    script_name = cleanup_text_analysis_service.classify_text_script(f"{current_normalized} {next_normalized}")
    first_letter = _first_letter(next_normalized)
    if script_name in {"latin", "cyrillic"}:
        return bool(first_letter and first_letter.islower())
    if script_name in {"cjk", "hangul"}:
        return not cleanup_text_analysis_service.has_sentence_terminal(current_normalized)
    return (
        len(current_normalized) >= 24
        and len(next_normalized) >= 8
        and not cleanup_text_analysis_service.has_sentence_terminal(current_normalized)
    )


def _has_language_agnostic_continuation_shape(text: str) -> bool:
    """
    @brief      Detect structural continuation cues that do not depend on vocabulary.
    @param[in]  text Normalized current paragraph ending.
    @return     True when the next page likely continues the same paragraph.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    normalized = text.strip()
    if not normalized:
        return False
    if not cleanup_text_analysis_service.has_sentence_terminal(normalized):
        return True
    continuation_suffixes = (",", ":", ";", "-", "–", "—", "(", "[", "{", '"', "'", "„", "“", "«")
    if normalized.endswith(continuation_suffixes):
        return True
    return _has_unclosed_quote(normalized)


def _has_unclosed_quote(text: str) -> bool:
    """
    @brief      Detect a likely unclosed quoted span using common quote marks.
    @param[in]  text Text to inspect.
    @return     True when quote counts suggest an unfinished quotation.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    quote_pairs = (('"', '"'), ("“", "”"), ("„", "”"), ("«", "»"), ("'", "'"))
    for opening_quote, closing_quote in quote_pairs:
        if opening_quote == closing_quote:
            if text.count(opening_quote) % 2 == 1:
                return True
            continue
        if text.count(opening_quote) > text.count(closing_quote):
            return True
    return False


def _should_continue_paragraph_across_page_break(
    current_lines: CleanupLineParts,
    next_page: str | None,
) -> bool:
    """
    @brief      Determine whether continue paragraph across page break.
    @param[in]  current_lines Value for `current_lines`.
    @param[in]  next_page Value for `next_page`.
    @return     True when the helper condition is satisfied.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not current_lines or next_page is None:
        return False
    next_content_line = _first_content_line(next_page)
    return _should_continue_paragraph(_line_text(current_lines[-1]).strip(), next_content_line, page_break_context=True)


def _next_content_line(lines: list[str], start_index: int) -> str | None:
    """
    @brief      Resolve the next content line.
    @param[in]  lines Value for `lines`.
    @param[in]  start_index Value for `start_index`.
    @return     Resolved helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    for normalized_line in lines[start_index:]:
        if not normalized_line:
            continue
        if _looks_like_page_number(normalized_line) or _looks_like_separator_line(normalized_line):
            continue
        return normalized_line
    return None


def _first_content_line(page: str | None) -> str | None:
    """
    @brief      Return the first content line.
    @param[in]  page Value for `page`.
    @return     Resolved helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    if page is None:
        return None
    normalized_lines = [re.sub(r"\s+", " ", raw_line).strip() for raw_line in page.split("\n")]
    page_edge_indexes = set(_page_edge_line_indexes(normalized_lines))
    for line_index, normalized_line in enumerate(normalized_lines):
        if (
            not normalized_line
            or _looks_like_page_number(
                normalized_line,
                page_edge=line_index in page_edge_indexes,
            )
            or _looks_like_separator_line(normalized_line)
        ):
            continue
        return normalized_line
    return None


def _header_footer_match_key(line: str) -> str:
    """
    @brief      Build one normalized repeated-header/footer comparison key.
    @param[in]  line Candidate page-edge line.
    @return     Header/footer comparison key.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return cleanup_text_analysis_service.normalized_header_footer_key(line)


def _page_edge_line_indexes(lines: list[str]) -> tuple[int, ...]:
    """
    @brief      Return the non-empty line indexes considered page-edge context.
    @param[in]  lines Normalized page lines.
    @return     Tuple of top and bottom candidate indexes.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    non_empty_indexes = [index for index, line in enumerate(lines) if line.strip()]
    return tuple(dict.fromkeys([*non_empty_indexes[:2], *non_empty_indexes[-2:]]))


def _first_letter(text: str) -> str | None:
    """
    @brief      Return the first alphabetic character from one text fragment.
    @param[in]  text Source text fragment.
    @return     First letter or `None`.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    for character in text:
        if character.isalpha():
            return character
    return None


# END OF FILE
