#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
         page-number noise conservatively, preserves paragraph and chapter
         structure, and persists cleanup artifacts with resumable state.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.2.2
"""

# IMPORTS

from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
import re

from langdetect import LangDetectException, detect

from audiomancer import config
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    build_operation_artifact_path,
    build_operation_input_snapshot_path,
    build_operation_output_path,
    progress_percent,
    raise_if_cancelled,
    relative_to_project,
)

# CONSTANTS

# @brief Component logger used by the deterministic cleanup workflow.
_CLEANUP_LOGGER = get_component_logger("deterministic_cleanup")
# @brief Persisted deterministic cleanup report payload type.
CleanupReportPayload = dict[str, object]
# @brief Persisted deterministic cleanup operation-state payload type.
OperationStatePayload = dict[str, object]
# @brief Internal paragraph-line accumulator type used while rebuilding cleaned text.
CleanupLineParts = list[tuple[str, bool]]
# @brief Page-break separator pattern used to reconstruct extracted PDF pages.
_PAGE_SPLIT_PATTERN = re.compile(r"\n\n\f\n\n")
# @brief Conservative page-number matcher used during deterministic cleanup.
_PAGE_NUMBER_PATTERN = re.compile(r"^(?:page\s+)?\d+(?:\s*/\s*\d+)?$", re.IGNORECASE)
# @brief Supported chapter-heading detection patterns reused for cleanup summary metadata.
_CHAPTER_PATTERNS = (
    re.compile(r"^(chapter|capitolul|scene|scena)\s+[\wIVXLCDM0-9][\wIVXLCDM0-9 .:-]*$", re.IGNORECASE),
    re.compile(r"^[IVXLCDM]+$", re.IGNORECASE),
)
# @brief Sentence-terminal matcher used to detect soft-wrapped paragraph continuation.
_PARAGRAPH_TERMINAL_PATTERN = re.compile(r'[.!?\u2026](?:["\')\]\}]+)?$')
# @brief Decorative-separator matcher used to remove non-story break lines.
_SEPARATOR_LINE_PATTERN = re.compile(r"^[*#=_~.\-]{3,}$|^(?:[*#=_~.\-]\s+){2,}[*#=_~.\-]?$")
# @brief Dialogue formatter rule that inserts line breaks before continued spoken text.
_DIALOGUE_BREAK_AFTER_PUNCTUATION_PATTERN = re.compile(r'([:;.!?\u2026]["»”\']?)\s+-\s+(?=[A-ZĂÂÎȘȚ])')
# @brief Dialogue formatter rule that inserts line breaks after attributions and pauses.
_DIALOGUE_BREAK_AFTER_ATTRIBUTION_PATTERN = re.compile(r"([,:])\s+-\s+(?=[A-ZĂÂÎȘȚ])")


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
    @version    0.2.1
    """
    resolved_project_root = Path(project_root)
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        raise ValueError("No imported source is available for deterministic cleanup.")

    extracted_relative_path = manifest.get("extracted_text_relative_path")
    if not isinstance(extracted_relative_path, str) or not extracted_relative_path.strip():
        raise FileNotFoundError("Deterministic cleanup requires extracted text first.")

    extracted_path = resolved_project_root / extracted_relative_path
    if not extracted_path.is_file():
        raise FileNotFoundError(f"Extracted text is missing: {extracted_path}")

    original_name = str(source_document.get("original_name") or Path(extracted_relative_path).name)
    input_snapshot_path = build_operation_input_snapshot_path(
        resolved_project_root,
        "cleanup",
        original_name,
    )
    input_snapshot_path.write_text(
        extracted_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    output_path = build_operation_output_path(
        resolved_project_root,
        "cleanup",
        config.CLEANED_TEXT_FILE_NAME,
    )
    report_path = build_operation_artifact_path(
        resolved_project_root,
        "cleanup",
        config.CLEANUP_REPORT_FILE_NAME,
    )
    state_path = build_operation_output_path(
        resolved_project_root,
        "cleanup",
        config.OPERATION_STATE_FILE_NAME,
    )

    input_text = extracted_path.read_text(encoding="utf-8")
    pages = _split_pages(input_text)
    if not any(page.strip() for page in pages):
        raise ValueError("Extracted text does not contain any content to clean.")

    existing_state = _load_operation_state(state_path) or {}
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

    paragraph_texts: list[str] = []
    current_lines: CleanupLineParts = []
    if start_page_index > 0 and output_path.is_file():
        restored_output = output_path.read_text(encoding="utf-8").strip()
        paragraph_texts = [paragraph.strip() for paragraph in restored_output.split("\n\n") if paragraph.strip()]

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
        )
        removed_page_number_count += page_number_removed_count
        removed_separator_count += separator_removed_count
        paragraph_texts.extend(page_paragraphs)
        _write_partial_output(output_path, paragraph_texts, current_lines)
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
        paragraph_texts.append(_compose_paragraph_text(current_lines))

    paragraph_texts = [_format_dialogue_lines(text) for text in paragraph_texts if text.strip()]
    if not paragraph_texts:
        raise ValueError("Cleanup removed all usable text.")

    cleaned_text = "\n\n".join(paragraph_texts).strip() + "\n"
    output_path.write_text(cleaned_text, encoding="utf-8")

    detected_language = _detect_language(cleaned_text)
    chapter_count = _count_detected_chapters(paragraph_texts)
    warnings = _build_cleanup_warnings(detected_language, chapter_count)
    report_payload: CleanupReportPayload = {
        "input_relative_path": relative_to_project(resolved_project_root, input_snapshot_path),
        "cleaned_text_relative_path": relative_to_project(resolved_project_root, output_path),
        "cleaned_at": _utc_now_iso(),
        "detected_language": detected_language,
        "warnings": warnings,
        "paragraph_count": len(paragraph_texts),
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
    @version    0.1.1
    """
    return _load_operation_state(build_operation_output_path(project_root, "cleanup", config.OPERATION_STATE_FILE_NAME))


@trace_function(_CLEANUP_LOGGER)
def load_cleanup_report(project_root: str | Path) -> CleanupReportPayload | None:
    """
    @brief      Load one optional deterministic cleanup report payload.
    @param[in]  project_root Active project root folder.
    @return     Cleanup report payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    report_path = build_operation_artifact_path(
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
    payload_parts = list(paragraphs)
    if current_lines:
        payload_parts.append(_compose_paragraph_text(current_lines))
    output_text = "\n\n".join(item for item in payload_parts if item.strip())
    if output_text:
        output_text = output_text.strip() + "\n"
    output_path.write_text(output_text, encoding="utf-8")


def _emit_progress(progress_callback, progress_current: int, progress_total: int, message: str) -> None:
    if callable(progress_callback):
        progress_callback(
            progress_current,
            progress_total,
            progress_percent(progress_current, progress_total),
            message,
        )


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
    artifact_paths: list[str] = []
    if report_path is not None and report_path.is_file():
        artifact_paths.append(relative_to_project(project_root, report_path))
    return {
        "folder_relative_path": config.CLEANUP_FOLDER_NAME,
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
            "cleaned_pages": None if cleaned_pages is None else list(cleaned_pages),
            "removed_header_footer_line_count": removed_header_footer_count,
            "removed_page_number_line_count": removed_page_number_count,
            "removed_separator_line_count": removed_separator_count,
            "detected_language": detected_language,
            "paragraph_count": paragraph_count,
            "detected_chapter_count": chapter_count,
        },
        "resume_checkpoint": None if resume_checkpoint is None else dict(resume_checkpoint),
    }


def _load_operation_state(state_path: Path) -> OperationStatePayload | None:
    if not state_path.is_file():
        return None
    return dict(json.loads(state_path.read_text(encoding="utf-8")))


def _split_pages(extracted_text: str) -> list[str]:
    normalized = extracted_text.replace("\r\n", "\n").replace("\r", "\n")
    segments = [segment for segment in _PAGE_SPLIT_PATTERN.split(normalized) if segment.strip()]
    return segments or [normalized]


def _remove_repeated_headers_and_footers(pages: list[str]) -> tuple[list[str], int]:
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
                top_counts[candidate] += 1
        for index in non_empty_indexes[-2:]:
            candidate = lines[index].strip()
            if _is_header_footer_candidate(candidate):
                bottom_counts[candidate] += 1
    repeated_top = {value for value, count in top_counts.items() if count >= 2}
    repeated_bottom = {value for value, count in bottom_counts.items() if count >= 2}
    cleaned_pages: list[str] = []
    removed_count = 0
    for lines, non_empty_indexes in page_entries:
        candidate_indexes: set[int] = set()
        for index in non_empty_indexes[:2]:
            if lines[index].strip() in repeated_top:
                candidate_indexes.add(index)
        for index in non_empty_indexes[-2:]:
            if lines[index].strip() in repeated_bottom:
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
) -> tuple[list[str], CleanupLineParts, int, int]:
    paragraph_texts: list[str] = []
    current_lines = list(carried_lines)
    removed_page_number_count = 0
    removed_separator_count = 0
    merge_with_previous_line = bool(carried_lines)
    normalized_lines = [re.sub(r"\s+", " ", raw_line).strip() for raw_line in page.split("\n")]
    for line_index, normalized_line in enumerate(normalized_lines):
        if not normalized_line:
            if current_lines:
                next_line = _next_content_line(normalized_lines, line_index + 1)
                if next_line is None:
                    next_line = _first_content_line(next_page) if next_page is not None else None
                if _should_continue_paragraph(current_lines[-1][0], next_line):
                    merge_with_previous_line = True
                    continue
                paragraph_texts.append(_compose_paragraph_text(current_lines))
                current_lines = []
            continue
        if _looks_like_page_number(normalized_line):
            removed_page_number_count += 1
            continue
        if _looks_like_separator_line(normalized_line):
            removed_separator_count += 1
            continue
        current_lines.append((normalized_line, merge_with_previous_line))
        merge_with_previous_line = False
    if current_lines and not _should_continue_paragraph_across_page_break(current_lines, next_page):
        paragraph_texts.append(_compose_paragraph_text(current_lines))
        current_lines = []
    return paragraph_texts, current_lines, removed_page_number_count, removed_separator_count


def _build_cleanup_warnings(detected_language: str | None, chapter_count: int) -> list[str]:
    warnings: list[str] = []
    if detected_language is None:
        warnings.append("Language detection did not produce a stable value.")
    if chapter_count == 0:
        warnings.append(
            "No explicit chapter or scene headings were detected; chunking will rely on sequential paragraph order."
        )
    return warnings


def _count_detected_chapters(paragraph_texts: list[str]) -> int:
    chapter_count = 0
    current_chapter: str | None = None
    for paragraph_text in paragraph_texts:
        chapter_label = _detect_chapter_label(paragraph_text)
        if chapter_label is not None and chapter_label != current_chapter:
            current_chapter = chapter_label
            chapter_count += 1
    return chapter_count


def _detect_language(text: str) -> str | None:
    sample = text.strip()
    if len(sample) < 20:
        return None
    try:
        return detect(sample[:5000])
    except LangDetectException:
        return None


def _detect_chapter_label(paragraph_text: str) -> str | None:
    normalized = paragraph_text.strip()
    if len(normalized) > 100:
        return None
    for pattern in _CHAPTER_PATTERNS:
        if pattern.fullmatch(normalized):
            return normalized
    return None


def _is_header_footer_candidate(line: str) -> bool:
    return (
        len(line) >= 4
        and any(character.isalpha() for character in line)
        and not _looks_like_page_number(line)
        and _detect_chapter_label(line) is None
    )


def _looks_like_page_number(line: str) -> bool:
    return bool(_PAGE_NUMBER_PATTERN.fullmatch(line.strip()))


def _looks_like_separator_line(line: str) -> bool:
    normalized = line.strip()
    return bool(normalized) and bool(_SEPARATOR_LINE_PATTERN.fullmatch(normalized))


def _format_dialogue_lines(paragraph_text: str) -> str:
    normalized = paragraph_text.strip()
    normalized = _DIALOGUE_BREAK_AFTER_PUNCTUATION_PATTERN.sub(r"\1\n- ", normalized)
    normalized = _DIALOGUE_BREAK_AFTER_ATTRIBUTION_PATTERN.sub(r"\1\n- ", normalized)
    return normalized


def _compose_paragraph_text(lines: CleanupLineParts) -> str:
    if not lines:
        return ""
    first_line, _joined_with_previous = lines[0]
    paragraph_text = first_line.strip()
    for current_line, join_with_previous in lines[1:]:
        separator = " " if join_with_previous else "\n"
        paragraph_text += separator + current_line.strip()
    return paragraph_text.strip()


def _should_continue_paragraph(current_last_line: str, next_line: str | None) -> bool:
    if next_line is None:
        return False
    if _detect_chapter_label(next_line) is not None:
        return False
    if _looks_like_page_number(next_line) or _looks_like_separator_line(next_line):
        return False
    return next_line[:1].islower()


def _should_continue_paragraph_across_page_break(
    current_lines: CleanupLineParts,
    next_page: str | None,
) -> bool:
    if not current_lines or next_page is None:
        return False
    next_content_line = _first_content_line(next_page)
    return _should_continue_paragraph(current_lines[-1][0].strip(), next_content_line)


def _next_content_line(lines: list[str], start_index: int) -> str | None:
    for normalized_line in lines[start_index:]:
        if not normalized_line:
            continue
        if _looks_like_page_number(normalized_line) or _looks_like_separator_line(normalized_line):
            continue
        return normalized_line
    return None


def _first_content_line(page: str | None) -> str | None:
    if page is None:
        return None
    for raw_line in page.split("\n"):
        normalized_line = re.sub(r"\s+", " ", raw_line).strip()
        if (
            not normalized_line
            or _looks_like_page_number(normalized_line)
            or _looks_like_separator_line(normalized_line)
        ):
            continue
        return normalized_line
    return None


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# END OF FILE
