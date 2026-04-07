#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_cleanup_service.py
@brief AI-assisted text cleanup helpers for AudioMancer.
@details Consumes canonical extracted text, classifies cleanup units through
         one configured AI profile, persists cleanup artifacts in `10_cleanup`,
         and supports resumable window-based progress plus AI transaction logs.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.2.0
"""

# IMPORTS

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from langdetect import LangDetectException, detect

from audiomancer import config
from audiomancer.services import llm_provider_service
from audiomancer.services import prompt_template_service
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

# @brief Component logger used by the AI-assisted cleanup workflow.
_AI_CLEANUP_LOGGER = get_component_logger("ai_cleanup")
# @brief Supported chapter-heading detection patterns reused during cleanup summary building.
_CHAPTER_PATTERNS = (
    re.compile(r"^(chapter|capitolul|scene|scena)\s+[\wIVXLCDM0-9][\wIVXLCDM0-9 .:-]*$", re.IGNORECASE),
    re.compile(r"^[IVXLCDM]+$", re.IGNORECASE),
)
# @brief Conservative page-number matcher used for unit splitting and label validation.
_PAGE_NUMBER_PATTERN = re.compile(r"^(?:page\s+)?\d+(?:\s*/\s*\d+)?$", re.IGNORECASE)
# @brief Decorative-separator matcher used for unit splitting and label validation.
_SEPARATOR_PATTERN = re.compile(r"^[*#=_~.\-]{3,}$|^(?:[*#=_~.\-]\s+){2,}[*#=_~.\-]?$")
# @brief Sentence-terminal matcher used to decide whether wrapped lines should join.
_PARAGRAPH_TERMINAL_PATTERN = re.compile(r'[.!?\u2026](?:["\')\]\}]+)?$')
# @brief Dialogue formatter rule that inserts line breaks before continued spoken text.
_DIALOGUE_BREAK_AFTER_PUNCTUATION_PATTERN = re.compile(
    r'([:;.!?\u2026]["Â»â€\']?)\s+-\s+(?=[A-ZÄ‚Ã‚ÃŽÈ˜Èš])'
)
# @brief Dialogue formatter rule that inserts line breaks after attributions and pauses.
_DIALOGUE_BREAK_AFTER_ATTRIBUTION_PATTERN = re.compile(
    r'([,:])\s+-\s+(?=[A-ZÄ‚Ã‚ÃŽÈ˜Èš])'
)
# @brief Labels that preserve one cleanup unit in the final cleaned output.
_KEEP_LABELS = {"story", "unknown"}
# @brief Labels that remove one cleanup unit from the final cleaned output.
_REMOVABLE_LABELS = {
    "header",
    "footer",
    "page_number",
    "separator",
    "copyright",
    "noise",
    "remove",
}
# @brief Removal-ratio threshold above which one cleanup window is flagged as suspicious.
_MAX_REMOVAL_RATIO_WARNING = 0.55
# @brief Tail length inspected for late-window alternating label drift.
_SUSPICIOUS_ALTERNATION_WINDOW = 8
# @brief Persisted cleanup report payload type used by the UI and manifest sync.
CleanupReportPayload = dict[str, object]
# @brief Persisted AI cleanup operation-state payload type.
OperationStatePayload = dict[str, object]


# PUBLIC API


@trace_function(_AI_CLEANUP_LOGGER)
def clean_text(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
) -> CleanupReportPayload:
    """
    @brief      Run AI-assisted cleanup for one active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Cleanup report payload for the persisted AI cleanup artifacts.
    @exception  FileNotFoundError Raised when the extracted input is missing.
    @exception  ValueError Raised on missing profile data or unusable cleanup output.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    resolved_project_root = Path(project_root)
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        raise ValueError("No imported source is available for AI-assisted cleanup.")
    extracted_relative_path = manifest.get("extracted_text_relative_path")
    if not isinstance(extracted_relative_path, str) or not extracted_relative_path.strip():
        raise FileNotFoundError("AI-assisted cleanup requires extracted text first.")

    profile_id = str(ai_profile_payload.get("id", "")).strip()
    model_name = str(ai_profile_payload.get("model_name", "")).strip()
    base_url = str(ai_profile_payload.get("base_url", "")).strip()
    if not profile_id or not model_name or not base_url:
        raise ValueError("AI-assisted cleanup requires a valid enabled AI profile.")

    extracted_path = resolved_project_root / extracted_relative_path
    if not extracted_path.is_file():
        raise FileNotFoundError(f"Extracted text is missing: {extracted_path}")

    input_text = extracted_path.read_text(encoding="utf-8")
    if not input_text.strip():
        raise ValueError("Extracted text does not contain any content to clean.")

    original_name = str(
        source_document.get("original_name") or Path(extracted_relative_path).name
    )
    input_snapshot_path = build_operation_input_snapshot_path(
        resolved_project_root,
        "cleanup",
        original_name,
    )
    input_snapshot_path.write_text(input_text, encoding="utf-8")

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

    prompt_template_service.validate_required_prompts(
        ["text_cleanup_system", "text_cleanup_user"]
    )
    units = _build_cleanup_units(input_text)
    if not units:
        raise ValueError("Extracted text does not contain any cleanup units.")

    existing_state = _load_operation_state(state_path) or {}
    started_at = str(existing_state.get("started_at") or _utc_now_iso())
    input_fingerprint = _compute_input_fingerprint(input_text)
    windows = _build_windows(units, _usable_input_budget(ai_profile_payload))
    total_windows = len(windows)
    start_window_index, classifications, log_relative_path = _restore_resume_state(
        existing_state,
        total_windows,
        input_fingerprint,
        profile_id,
    )
    warning_details = _restore_warning_details(existing_state)
    if not log_relative_path:
        log_path = _build_ai_log_path(resolved_project_root, started_at)
        log_relative_path = relative_to_project(resolved_project_root, log_path)
    else:
        log_path = resolved_project_root / log_relative_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")

    _write_running_state(
        state_path,
        resolved_project_root,
        input_snapshot_path,
        output_path,
        started_at,
        start_window_index,
        total_windows,
        profile_id,
        log_relative_path,
        input_fingerprint,
        classifications,
        warning_details,
    )
    _emit_progress(
        progress_callback,
        progress_current=start_window_index,
        progress_total=total_windows,
        message="Resuming AI-assisted cleanup..." if start_window_index > 0 else "AI-assisted cleanup in progress...",
    )

    system_prompt = prompt_template_service.render_prompt("text_cleanup_system", {})
    for window_index in range(start_window_index, total_windows):
        raise_if_cancelled(cancel_requested)
        window_units = units[
            windows[window_index]["start_index"]: windows[window_index]["end_index"] + 1
        ]
        user_prompt = prompt_template_service.render_prompt(
            "text_cleanup_user",
            {"units_block": _build_units_block(window_units)},
        )
        response_payload = llm_provider_service.chat_json(
            ai_profile_payload,
            system_prompt,
            user_prompt,
            log_path=log_path,
            log_context={
                "operation_kind": "cleanup",
                "stage_label": "ai_cleanup",
                "profile_id": profile_id,
                "window_index": window_index + 1,
                "window_total": total_windows,
            },
            cancel_requested=cancel_requested,
        )
        _apply_response_labels(
            classifications,
            response_payload,
            window_units,
            warning_details,
            window_index + 1,
        )
        _write_running_state(
            state_path,
            resolved_project_root,
            input_snapshot_path,
            output_path,
            started_at,
            window_index + 1,
            total_windows,
            profile_id,
            log_relative_path,
            input_fingerprint,
            classifications,
            warning_details,
        )
        _emit_progress(
            progress_callback,
            progress_current=window_index + 1,
            progress_total=total_windows,
            message="AI-assisted cleanup in progress...",
        )

    kept_units = [
        unit
        for unit in units
        if classifications.get(unit["unit_id"], "unknown") in _KEEP_LABELS
    ]
    cleaned_paragraphs = [
        _normalize_unit_paragraph_text(str(unit["text"]))
        for unit in kept_units
        if str(unit["text"]).strip()
    ]
    cleaned_paragraphs = [paragraph for paragraph in cleaned_paragraphs if paragraph.strip()]
    cleaned_paragraphs = _merge_adjacent_continuation_paragraphs(cleaned_paragraphs)
    if not cleaned_paragraphs:
        raise ValueError("AI-assisted cleanup removed all usable text.")

    cleaned_text = "\n\n".join(cleaned_paragraphs).strip() + "\n"
    output_path.write_text(cleaned_text, encoding="utf-8")
    detected_language = _detect_language(cleaned_text)
    chapter_count = _count_detected_chapters(cleaned_paragraphs)
    warning_details.extend(
        _build_final_output_warning_details(
            cleaned_paragraphs,
            classifications,
            units,
        )
    )
    warnings = _build_cleanup_warnings(detected_language, chapter_count, warning_details)
    report_payload: CleanupReportPayload = {
        "input_relative_path": relative_to_project(resolved_project_root, input_snapshot_path),
        "cleaned_text_relative_path": relative_to_project(resolved_project_root, output_path),
        "cleaned_at": _utc_now_iso(),
        "detected_language": detected_language,
        "warnings": warnings,
        "warning_details": warning_details,
        "paragraph_count": len(cleaned_paragraphs),
        "removed_line_count": max(0, len(units) - len(kept_units)),
        "detected_chapter_count": chapter_count,
        "cleanup_mode": "ai_assisted",
        "ai_profile_id": profile_id,
        "ai_log_relative_path": log_relative_path,
        "window_count": total_windows,
    }
    report_path.write_text(
        json.dumps(report_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    completed_state = _build_operation_state(
        resolved_project_root,
        input_snapshot_path,
        output_path,
        report_path,
        status="completed",
        progress_current=total_windows,
        progress_total=total_windows,
        started_at=started_at,
        completed_at=report_payload["cleaned_at"],
        warnings=warnings,
        profile_id=profile_id,
        log_relative_path=log_relative_path,
        input_fingerprint=input_fingerprint,
        classifications=None,
        warning_details=warning_details,
        detected_language=detected_language,
        paragraph_count=len(cleaned_paragraphs),
        chapter_count=chapter_count,
    )
    state_path.write_text(
        json.dumps(completed_state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _emit_progress(
        progress_callback,
        progress_current=total_windows,
        progress_total=total_windows,
        message="AI-assisted cleanup completed.",
    )
    return report_payload


@trace_function(_AI_CLEANUP_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Load one optional cleanup operation-state payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted cleanup operation-state payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    return _load_operation_state(
        build_operation_output_path(project_root, "cleanup", config.OPERATION_STATE_FILE_NAME)
    )


# LOCAL HELPERS


def _emit_progress(progress_callback, progress_current: int, progress_total: int, message: str) -> None:
    if callable(progress_callback):
        progress_callback(
            progress_current,
            progress_total,
            progress_percent(progress_current, progress_total),
            message,
        )


def _build_cleanup_units(text: str) -> list[dict[str, object]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    units: list[dict[str, object]] = []
    next_index = 1
    for block in re.split(r"\n{2,}", normalized):
        for normalized_block in _split_cleanup_block(block):
            units.append(
                {
                    "unit_id": f"unit-{next_index:04d}",
                    "text": normalized_block,
                    "estimated_tokens": _estimate_text_tokens(normalized_block) + 32,
                }
            )
            next_index += 1
    return units


def _normalize_unit_paragraph_text(unit_text: str) -> str:
    normalized_lines = [
        re.sub(r"\s+", " ", raw_line).strip()
        for raw_line in unit_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    paragraph_lines: list[tuple[str, bool]] = []
    merge_with_previous_line = False
    for line_index, normalized_line in enumerate(normalized_lines):
        if not normalized_line:
            continue
        paragraph_lines.append((normalized_line, merge_with_previous_line))
        next_line = _next_content_line(normalized_lines, line_index + 1)
        merge_with_previous_line = _should_continue_paragraph(normalized_line, next_line)
    return _format_dialogue_lines(_compose_paragraph_text(paragraph_lines))


def _build_windows(
    units: list[dict[str, object]],
    usable_input_budget: int,
) -> list[dict[str, int]]:
    windows: list[dict[str, int]] = []
    start_index = 0
    while start_index < len(units):
        current_budget = 0
        current_unit_count = 0
        end_index = start_index - 1
        while end_index + 1 < len(units):
            next_unit = units[end_index + 1]
            next_tokens = int(next_unit["estimated_tokens"])
            if next_tokens > usable_input_budget:
                raise ValueError("One AI cleanup unit exceeds the configured usable input budget.")
            if (
                current_unit_count >= config.DEFAULT_AI_CLEANUP_MAX_WINDOW_UNITS
                and end_index >= start_index
            ):
                break
            if current_budget + next_tokens > usable_input_budget and end_index >= start_index:
                break
            current_budget += next_tokens
            end_index += 1
            current_unit_count += 1
        windows.append({"start_index": start_index, "end_index": end_index})
        start_index = end_index + 1
    return windows


def _restore_resume_state(
    existing_state: dict[str, object],
    total_windows: int,
    input_fingerprint: str,
    profile_id: str,
) -> tuple[int, dict[str, str], str | None]:
    resume_checkpoint = dict(existing_state.get("resume_checkpoint") or {})
    log_relative_path = existing_state.get("metadata", {}).get("ai_log_relative_path")
    if (
        existing_state.get("mode") != "ai_assisted"
        or str(resume_checkpoint.get("input_fingerprint", "")) != input_fingerprint
        or str(resume_checkpoint.get("profile_id", "")) != profile_id
        or int(resume_checkpoint.get("total_window_count", 0)) != total_windows
    ):
        return 0, {}, log_relative_path if isinstance(log_relative_path, str) else None
    completed_window_count = int(resume_checkpoint.get("completed_window_count", 0))
    stored_classifications = resume_checkpoint.get("classifications", {})
    if not isinstance(stored_classifications, dict):
        return completed_window_count, {}, log_relative_path if isinstance(log_relative_path, str) else None
    return (
        completed_window_count,
        {
            str(unit_id): str(label)
            for unit_id, label in stored_classifications.items()
            if str(unit_id).strip()
        },
        log_relative_path if isinstance(log_relative_path, str) else None,
    )


def _restore_warning_details(existing_state: dict[str, object]) -> list[dict[str, object]]:
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return []
    raw_items = metadata.get("warning_details", [])
    if not isinstance(raw_items, list):
        return []
    return [dict(item) for item in raw_items if isinstance(item, dict)]


def _build_units_block(units: list[dict[str, object]]) -> str:
    return "\n\n".join(
        f"{unit['unit_id']}:\n{unit['text']}"
        for unit in units
    )


def _compose_paragraph_text(lines: list[tuple[str, bool]]) -> str:
    if not lines:
        return ""
    first_line, _joined_with_previous = lines[0]
    paragraph_text = first_line.strip()
    for current_line, join_with_previous in lines[1:]:
        separator = " " if join_with_previous else "\n"
        paragraph_text += separator + current_line.strip()
    return paragraph_text.strip()


def _format_dialogue_lines(paragraph_text: str) -> str:
    normalized = paragraph_text.strip()
    normalized = _DIALOGUE_BREAK_AFTER_PUNCTUATION_PATTERN.sub(r"\1\n- ", normalized)
    normalized = _DIALOGUE_BREAK_AFTER_ATTRIBUTION_PATTERN.sub(r"\1\n- ", normalized)
    return normalized


def _merge_adjacent_continuation_paragraphs(paragraphs: list[str]) -> list[str]:
    merged_paragraphs: list[str] = []
    for paragraph in paragraphs:
        normalized_paragraph = paragraph.strip()
        if not normalized_paragraph:
            continue
        if (
            merged_paragraphs
            and _should_continue_after_paragraph(
                merged_paragraphs[-1],
                normalized_paragraph,
            )
        ):
            merged_paragraphs[-1] = _format_dialogue_lines(
                merged_paragraphs[-1].rstrip() + " " + normalized_paragraph.lstrip()
            )
            continue
        merged_paragraphs.append(normalized_paragraph)
    return merged_paragraphs


def _should_continue_after_paragraph(
    current_paragraph: str,
    next_paragraph: str,
) -> bool:
    current_lines = [
        line.strip()
        for line in current_paragraph.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.strip()
    ]
    next_lines = [
        line.strip()
        for line in next_paragraph.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.strip()
    ]
    if not current_lines or not next_lines:
        return False
    return _should_continue_paragraph(current_lines[-1], next_lines[0])


def _should_continue_paragraph(current_last_line: str, next_line: str | None) -> bool:
    if next_line is None:
        return False
    if _detect_chapter_label(next_line) is not None:
        return False
    if next_line.startswith("- "):
        return False
    current_text = current_last_line.strip()
    if not current_text:
        return False
    if current_text.endswith(":"):
        return False
    if current_text.endswith("-"):
        return True
    if _PARAGRAPH_TERMINAL_PATTERN.search(current_text):
        return False
    return True


def _next_content_line(lines: list[str], start_index: int) -> str | None:
    for normalized_line in lines[start_index:]:
        if normalized_line:
            return normalized_line
    return None


def _apply_response_labels(
    classifications: dict[str, str],
    response_payload: dict[str, object],
    window_units: list[dict[str, object]],
    warning_details: list[dict[str, object]],
    window_index: int,
) -> None:
    """
    @brief      Normalize one AI cleanup response conservatively before labels are committed.
    @param[in,out] classifications Accumulated cleanup classifications.
    @param[in]     response_payload Structured AI response payload.
    @param[in]     window_units Ordered cleanup units in the current window.
    @param[in,out] warning_details Accumulated structured warning details.
    @param[in]     window_index One-based cleanup window index.
    @return       None.
    @exception    ValueError Raised when the AI response does not contain a valid results list.
    @author       Eng. Dan Dumitru Pasare
    @date         2026-04-07
    @version      0.1.0
    """
    results = response_payload.get("results", [])
    if not isinstance(results, list):
        raise ValueError("AI cleanup response does not contain a valid results list.")
    window_unit_map = {
        str(unit["unit_id"]): str(unit["text"])
        for unit in window_units
    }
    window_labels: dict[str, str] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        unit_id = str(item.get("unit_id", "")).strip()
        label = str(item.get("label", "unknown")).strip().lower() or "unknown"
        if not unit_id:
            continue
        if label not in _KEEP_LABELS and label not in _REMOVABLE_LABELS:
            label = "unknown"
        if unit_id not in window_unit_map:
            _append_warning_detail(
                warning_details,
                kind="invalid_result_unit",
                message=f"AI cleanup returned an unknown unit id '{unit_id}' in window {window_index}; the result item was ignored.",
                window_index=window_index,
                unit_id=unit_id,
            )
            continue
        window_labels[unit_id] = label
    normalized_labels = _normalize_window_labels(
        window_units,
        window_labels,
        warning_details,
        window_index,
    )
    for unit in window_units:
        unit_id = str(unit["unit_id"])
        classifications[unit_id] = normalized_labels.get(unit_id, "unknown")


def _write_running_state(
    state_path: Path,
    project_root: Path,
    input_snapshot_path: Path,
    output_path: Path,
    started_at: str,
    progress_current: int,
    progress_total: int,
    profile_id: str,
    log_relative_path: str,
    input_fingerprint: str,
    classifications: dict[str, str],
    warning_details: list[dict[str, object]],
) -> None:
    running_state = _build_operation_state(
        project_root,
        input_snapshot_path,
        output_path,
        report_path=None,
        status="running",
        progress_current=progress_current,
        progress_total=progress_total,
        started_at=started_at,
        completed_at=None,
        warnings=[],
        profile_id=profile_id,
        log_relative_path=log_relative_path,
        input_fingerprint=input_fingerprint,
        classifications=classifications,
        warning_details=warning_details,
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
    profile_id: str,
    log_relative_path: str,
    input_fingerprint: str,
    classifications: dict[str, str] | None,
    warning_details: list[dict[str, object]],
    detected_language: str | None,
    paragraph_count: int | None,
    chapter_count: int | None,
) -> OperationStatePayload:
    artifact_paths: list[str] = [log_relative_path]
    if report_path is not None and report_path.is_file():
        artifact_paths.append(relative_to_project(project_root, report_path))
    return {
        "folder_relative_path": config.CLEANUP_FOLDER_NAME,
        "status": status,
        "input_paths": [relative_to_project(project_root, input_snapshot_path)],
        "output_paths": (
            [relative_to_project(project_root, output_path)]
            if output_path.is_file()
            else []
        ),
        "artifact_paths": artifact_paths,
        "progress_current": progress_current,
        "progress_total": progress_total,
        "mode": "ai_assisted",
        "started_at": started_at,
        "completed_at": completed_at,
        "updated_at": _utc_now_iso(),
        "warning_count": len(warnings),
        "metadata": {
            "warnings": list(warnings),
            "warning_details": [dict(item) for item in warning_details],
            "detected_language": detected_language,
            "paragraph_count": paragraph_count,
            "detected_chapter_count": chapter_count,
            "ai_profile_id": profile_id,
            "ai_log_relative_path": log_relative_path,
        },
        "resume_checkpoint": {
            "completed_window_count": progress_current,
            "total_window_count": progress_total,
            "profile_id": profile_id,
            "input_fingerprint": input_fingerprint,
            "classifications": None if classifications is None else dict(classifications),
        } if status != "completed" else None,
    }


def _load_operation_state(state_path: Path) -> OperationStatePayload | None:
    if not state_path.is_file():
        return None
    return dict(json.loads(state_path.read_text(encoding="utf-8")))


def _build_ai_log_path(project_root: Path, started_at: str) -> Path:
    started_fragment = (
        started_at.replace(":", "")
        .replace("+00:00", "")
        .replace("T", "_")
    )
    return build_operation_artifact_path(
        project_root,
        "cleanup",
        f"{config.AI_TRANSACTION_LOG_FILE_PREFIX}{started_fragment}.log",
    )


def _usable_input_budget(profile_payload: dict[str, object]) -> int:
    context_window = int(
        profile_payload.get("context_window", config.DEFAULT_LLM_CONTEXT_WINDOW)
    )
    max_output_tokens = int(
        profile_payload.get(
            "max_output_tokens",
            config.DEFAULT_LLM_MAX_OUTPUT_TOKENS,
        )
    )
    return max(512, context_window - max_output_tokens - 1024)


def _estimate_text_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _compute_input_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_cleanup_warnings(
    detected_language: str | None,
    chapter_count: int,
    warning_details: list[dict[str, object]],
) -> list[str]:
    warnings: list[str] = []
    if detected_language is None:
        warnings.append("Language detection did not produce a stable value.")
    if chapter_count == 0:
        warnings.append(
            "No explicit chapter or scene headings were detected; chunking will rely on sequential paragraph order."
        )
    warnings.extend(
        str(item.get("message", "")).strip()
        for item in warning_details
        if str(item.get("message", "")).strip()
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


def _detect_chapter_label(paragraph_text: str) -> str | None:
    normalized = paragraph_text.strip()
    if len(normalized) > 100:
        return None
    for pattern in _CHAPTER_PATTERNS:
        if pattern.fullmatch(normalized):
            return normalized
    return None


def _detect_language(text: str) -> str | None:
    sample = text.strip()
    if len(sample) < 20:
        return None
    try:
        return detect(sample[:5000])
    except LangDetectException:
        return None


def _split_cleanup_block(block: str) -> list[str]:
    normalized_lines = [
        re.sub(r"\s+", " ", raw_line).strip()
        for raw_line in block.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    segments: list[str] = []
    story_buffer: list[str] = []
    for normalized_line in normalized_lines:
        if not normalized_line:
            continue
        if _looks_like_page_number(normalized_line) or _looks_like_separator_line(normalized_line):
            if story_buffer:
                segments.append("\n".join(story_buffer).strip())
                story_buffer = []
            segments.append(normalized_line)
            continue
        story_buffer.append(normalized_line)
    if story_buffer:
        segments.append("\n".join(story_buffer).strip())
    return [segment for segment in segments if segment.strip()]


def _normalize_window_labels(
    window_units: list[dict[str, object]],
    window_labels: dict[str, str],
    warning_details: list[dict[str, object]],
    window_index: int,
) -> dict[str, str]:
    normalized_labels: dict[str, str] = {}
    removal_count = 0
    for unit in window_units:
        unit_id = str(unit["unit_id"])
        unit_text = str(unit["text"])
        label = window_labels.get(unit_id, "unknown")
        corrected_label = _normalize_label_for_unit(
            unit_text,
            label,
            warning_details,
            window_index,
            unit_id,
        )
        normalized_labels[unit_id] = corrected_label
        if corrected_label in _REMOVABLE_LABELS:
            removal_count += 1
    _append_suspicious_window_warnings(
        window_units,
        normalized_labels,
        removal_count,
        warning_details,
        window_index,
    )
    return normalized_labels


def _normalize_label_for_unit(
    unit_text: str,
    label: str,
    warning_details: list[dict[str, object]],
    window_index: int,
    unit_id: str,
) -> str:
    normalized_text = unit_text.strip()
    if _looks_like_page_number(normalized_text):
        if label != "page_number":
            _append_warning_detail(
                warning_details,
                kind="page_number_label_corrected",
                message=f"AI cleanup corrected one page-number classification in window {window_index} to preserve cleanup quality.",
                window_index=window_index,
                unit_id=unit_id,
                original_label=label,
                corrected_label="page_number",
            )
        return "page_number"
    if _looks_like_separator_line(normalized_text):
        if label != "separator":
            _append_warning_detail(
                warning_details,
                kind="separator_label_corrected",
                message=f"AI cleanup corrected one separator classification in window {window_index} to preserve cleanup quality.",
                window_index=window_index,
                unit_id=unit_id,
                original_label=label,
                corrected_label="separator",
            )
        return "separator"
    if label == "page_number":
        _append_warning_detail(
            warning_details,
            kind="invalid_page_number_label_corrected",
            message=f"AI cleanup corrected one invalid page-number label in window {window_index} and preserved the text for review.",
            window_index=window_index,
            unit_id=unit_id,
            original_label=label,
            corrected_label="unknown",
        )
        return "unknown"
    if label == "separator":
        _append_warning_detail(
            warning_details,
            kind="invalid_separator_label_corrected",
            message=f"AI cleanup corrected one invalid separator label in window {window_index} and preserved the text for review.",
            window_index=window_index,
            unit_id=unit_id,
            original_label=label,
            corrected_label="unknown",
        )
        return "unknown"
    return label


def _append_suspicious_window_warnings(
    window_units: list[dict[str, object]],
    labels: dict[str, str],
    removal_count: int,
    warning_details: list[dict[str, object]],
    window_index: int,
) -> None:
    total_units = max(len(window_units), 1)
    removal_ratio = removal_count / total_units
    if removal_ratio >= _MAX_REMOVAL_RATIO_WARNING:
        _append_warning_detail(
            warning_details,
            kind="high_removal_ratio_detected",
            message=(
                f"AI cleanup removed or classified {removal_count} of {total_units} units in window {window_index}; "
                "review the cleaned output before chunking."
            ),
            window_index=window_index,
            removal_count=removal_count,
            unit_count=total_units,
            removal_ratio=round(removal_ratio, 3),
        )

    classification_tail: list[str] = []
    for unit in window_units[-_SUSPICIOUS_ALTERNATION_WINDOW:]:
        unit_text = str(unit["text"]).strip()
        unit_id = str(unit["unit_id"])
        if _looks_like_page_number(unit_text) or _looks_like_separator_line(unit_text):
            classification_tail.append("artifact")
        elif labels.get(unit_id, "unknown") in _REMOVABLE_LABELS:
            classification_tail.append("removed_story_like")
        else:
            classification_tail.append("kept_story_like")
    flip_count = sum(
        1
        for current, following in zip(classification_tail, classification_tail[1:])
        if current != following
    )
    if len(classification_tail) >= 6 and flip_count >= len(classification_tail) - 2:
        _append_warning_detail(
            warning_details,
            kind="suspicious_label_drift_detected",
            message=f"AI cleanup detected one suspicious late-window label pattern in window {window_index}; the affected text was preserved conservatively where needed.",
            window_index=window_index,
            classification_tail=classification_tail,
        )


def _build_final_output_warning_details(
    cleaned_paragraphs: list[str],
    classifications: dict[str, str],
    units: list[dict[str, object]],
) -> list[dict[str, object]]:
    warning_details: list[dict[str, object]] = []
    surviving_page_number_count = sum(
        1 for paragraph in cleaned_paragraphs if _looks_like_page_number(paragraph.strip())
    )
    if surviving_page_number_count > 0:
        warning_details.append(
            {
                "kind": "numeric_artifacts_remained",
                "message": (
                    f"AI cleanup left {surviving_page_number_count} page-number-like paragraph(s) in the cleaned output; review the result before chunking."
                ),
                "surviving_page_number_count": surviving_page_number_count,
            }
        )
    story_like_removed_count = sum(
        1
        for unit in units
        if classifications.get(str(unit["unit_id"]), "unknown") in _REMOVABLE_LABELS
        and not _looks_like_page_number(str(unit["text"]).strip())
        and not _looks_like_separator_line(str(unit["text"]).strip())
    )
    if story_like_removed_count > 0:
        warning_details.append(
            {
                "kind": "story_like_units_removed",
                "message": (
                    f"AI cleanup removed {story_like_removed_count} non-trivial unit(s); review the cleaned text if important content appears to be missing."
                ),
                "story_like_removed_count": story_like_removed_count,
            }
        )
    return warning_details


def _append_warning_detail(
    warning_details: list[dict[str, object]],
    *,
    kind: str,
    message: str,
    **metadata: object,
) -> None:
    for existing in warning_details:
        if (
            str(existing.get("kind", "")) == kind
            and str(existing.get("message", "")) == message
            and all(existing.get(key) == value for key, value in metadata.items())
        ):
            return
    warning_details.append({"kind": kind, "message": message, **metadata})


def _looks_like_page_number(text: str) -> bool:
    return bool(_PAGE_NUMBER_PATTERN.fullmatch(text.strip()))


def _looks_like_separator_line(text: str) -> bool:
    normalized = text.strip()
    return bool(normalized) and bool(_SEPARATOR_PATTERN.fullmatch(normalized))


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# END OF FILE
