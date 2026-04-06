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
@date 2026-04-06
@version 0.1.4
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

_AI_CLEANUP_LOGGER = get_component_logger("ai_cleanup")
_CHAPTER_PATTERNS = (
    re.compile(r"^(chapter|capitolul|scene|scena)\s+[\wIVXLCDM0-9][\wIVXLCDM0-9 .:-]*$", re.IGNORECASE),
    re.compile(r"^[IVXLCDM]+$", re.IGNORECASE),
)
_PARAGRAPH_TERMINAL_PATTERN = re.compile(r'[.!?\u2026](?:["\')\]\}]+)?$')
_DIALOGUE_BREAK_AFTER_PUNCTUATION_PATTERN = re.compile(
    r'([:;.!?\u2026]["Â»â€\']?)\s+-\s+(?=[A-ZÄ‚Ã‚ÃŽÈ˜Èš])'
)
_DIALOGUE_BREAK_AFTER_ATTRIBUTION_PATTERN = re.compile(
    r'([,:])\s+-\s+(?=[A-ZÄ‚Ã‚ÃŽÈ˜Èš])'
)
_KEEP_LABELS = {"story", "unknown"}
_REMOVABLE_LABELS = {
    "header",
    "footer",
    "page_number",
    "separator",
    "copyright",
    "noise",
    "remove",
}
CleanupReportPayload = dict[str, object]
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
    @date       2026-04-06
    @version    0.1.4
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
        _apply_response_labels(classifications, response_payload)
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
    warnings = _build_cleanup_warnings(detected_language, chapter_count)
    report_payload: CleanupReportPayload = {
        "input_relative_path": relative_to_project(resolved_project_root, input_snapshot_path),
        "cleaned_text_relative_path": relative_to_project(resolved_project_root, output_path),
        "cleaned_at": _utc_now_iso(),
        "detected_language": detected_language,
        "warnings": warnings,
        "paragraph_count": len(cleaned_paragraphs),
        "removed_line_count": max(0, len(units) - len(kept_units)),
        "detected_chapter_count": chapter_count,
        "cleanup_mode": "ai_assisted",
        "ai_profile_id": profile_id,
        "ai_log_relative_path": log_relative_path,
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
    for index, block in enumerate(re.split(r"\n{2,}", normalized), start=1):
        normalized_block = block.strip()
        if not normalized_block:
            continue
        units.append(
            {
                "unit_id": f"unit-{index:04d}",
                "text": normalized_block,
                "estimated_tokens": _estimate_text_tokens(normalized_block) + 32,
            }
        )
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
        end_index = start_index - 1
        while end_index + 1 < len(units):
            next_unit = units[end_index + 1]
            next_tokens = int(next_unit["estimated_tokens"])
            if next_tokens > usable_input_budget:
                raise ValueError("One AI cleanup unit exceeds the configured usable input budget.")
            if current_budget + next_tokens > usable_input_budget and end_index >= start_index:
                break
            current_budget += next_tokens
            end_index += 1
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
) -> None:
    results = response_payload.get("results", [])
    if not isinstance(results, list):
        raise ValueError("AI cleanup response does not contain a valid results list.")
    for item in results:
        if not isinstance(item, dict):
            continue
        unit_id = str(item.get("unit_id", "")).strip()
        label = str(item.get("label", "unknown")).strip().lower() or "unknown"
        if not unit_id:
            continue
        if label not in _KEEP_LABELS and label not in _REMOVABLE_LABELS:
            label = "unknown"
        classifications[unit_id] = label


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
    return max(512, context_window - max_output_tokens - 512)


def _estimate_text_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _compute_input_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# END OF FILE
