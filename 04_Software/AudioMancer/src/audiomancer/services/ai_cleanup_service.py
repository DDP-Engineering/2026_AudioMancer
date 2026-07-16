#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# ruff: noqa: E501
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_cleanup_service.py
@brief AI-assisted text cleanup service for AudioMancer.
@details Presents each cleanup window as one canonical source string, validates
         exact blocks and uniquely bounded modified Story blocks against forward
         source positions, preserves uniquely bounded omitted source gaps, renders
         artifacts with an operator-selectable spacing set, resumes compatible
         validated prefixes by source-stream offset, and persists review evidence.
@author Eng. Dan Dumitru Pasare
@date 2026-07-15
@version 1.6.0
"""

# IMPORTS

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import (
    cleanup_metadata_service,
    cleanup_text_analysis_service,
    llm_provider_service,
    project_workspace_service,
    prompt_template_service,
    token_usage_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    build_operation_output_path,
    build_operation_state_payload,
    load_operation_state_file,
    load_operation_state_payload,
    load_optional_json_artifact,
    raise_if_cancelled,
    relative_to_project,
)
from audiomancer.services.operation_runtime_service import emit_progress_update as _emit_progress
from audiomancer.services.persistence_service import write_json_atomic, write_text_atomic
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

_LOGGER = get_component_logger("ai_cleanup")
_PAGE_SEPARATOR = "\n\f\n\n"
_CONTRACT_FINGERPRINT = hashlib.sha256(
    b"window_id|artifacts-exact,story-exact-or-unique-normalized-edge-anchored-modified,min32,edge16-64,interior-any|source-ranges-complete|whitespace:restore-exact|internal-nonwhitespace-gap:preserve-exact-between-unique-exact-boundaries|artifact-output:operator-selected-two-lf,unselected-empty,default-heading-separator|confidence:high,medium,low"
).hexdigest()
_SYSTEM_PROMPT_NAME = "text_cleanup_system"
_USER_PROMPT_NAME = "text_cleanup_user"
_ARTIFACT_TYPES = frozenset({"header", "footer", "noise", "separator", "heading", "story"})
_NON_DISPLAY_ARTIFACT_TYPES = _ARTIFACT_TYPES - {"story"}
_DEFAULT_SPACING_CATEGORIES = frozenset({"heading", "separator"})
_ARTIFACT_REPLACEMENTS = {
    "header": "",
    "footer": "",
    "noise": "",
    "separator": "\n\n",
    "heading": "\n\n",
}
_CONFIDENCE_VALUES = frozenset({"high", "medium", "low"})
_MODIFIED_STORY_MIN_NORMALIZED_LENGTH = 32
_MODIFIED_STORY_MAX_EDGE_ANCHOR_LENGTH = 64

# DATA MODELS / TYPEDEFINITIONS

CleanupReportPayload = dict[str, object]
OperationStatePayload = dict[str, object]
SourcePagePayload = dict[str, object]
ValidatedWindowPayload = dict[str, object]


# PUBLIC API


def default_spacing_categories() -> list[str]:
    """
    @brief      Return the deterministic default AI Cleanup spacing selection.
    @return     Sorted non-story category names selected by default.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    return sorted(_DEFAULT_SPACING_CATEGORIES)


def selected_spacing_categories(report_payload: dict[str, object] | None) -> list[str]:
    """
    @brief      Return a compatible report's persisted spacing selection or the default.
    @param[in]  report_payload Optional AI Cleanup report payload.
    @return     Sorted validated non-story spacing categories.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    if not isinstance(report_payload, dict):
        return default_spacing_categories()
    try:
        return sorted(_normalize_spacing_categories(report_payload.get("selected_spacing_categories", [])))
    except ValueError:
        return default_spacing_categories()


def spacing_selection_available(report_payload: dict[str, object] | None) -> bool:
    """
    @brief      Return whether a report supports deterministic spacing reapplication.
    @param[in]  report_payload Optional cleanup report payload.
    @return     True for one current compatible completed AI Cleanup report.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    if not isinstance(report_payload, dict):
        return False
    if report_payload.get("cleanup_mode") != "ai_assisted":
        return False
    if report_payload.get("reconstruction_contract_fingerprint") != _CONTRACT_FINGERPRINT:
        return False
    decisions = report_payload.get("validated_window_decisions")
    if not isinstance(decisions, list) or not decisions or not all(isinstance(item, dict) for item in decisions):
        return False
    try:
        _normalize_spacing_categories(report_payload.get("selected_spacing_categories", []))
        for decision in decisions:
            _render_validated_window(dict(decision), _DEFAULT_SPACING_CATEGORIES)
    except (KeyError, TypeError, ValueError):
        return False
    return True


@trace_function(_LOGGER)
def apply_spacing_selection(
    project_root: str | Path,
    selected_categories: object,
) -> CleanupReportPayload:
    """
    @brief      Rebuild and persist cleaned text from retained AI decisions.
    @param[in]  project_root Active project root folder.
    @param[in]  selected_categories Complete selected non-story category collection.
    @return     Updated persisted AI Cleanup report payload.
    @exception  ValueError Raised when the selection or retained report is incompatible.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    root = Path(project_root)
    spacing_categories = _normalize_spacing_categories(selected_categories)
    report_path = build_operation_output_path(root, "cleanup", config.CLEANUP_REPORT_FILE_NAME)
    raw_report = load_optional_json_artifact(report_path)
    report = dict(raw_report) if isinstance(raw_report, dict) else None
    if not spacing_selection_available(report):
        raise ValueError("Compatible completed AI Cleanup decisions are unavailable for spacing reapplication.")

    raw_decisions = report.get("validated_window_decisions", [])
    rendered_decisions = [
        _render_validated_window(dict(decision), spacing_categories)
        for decision in raw_decisions
        if isinstance(decision, dict)
    ]
    cleaned_text = "".join(str(decision["reconstructed_text"]) for decision in rendered_decisions)
    if not cleaned_text.strip():
        raise ValueError("The selected AI Cleanup spacing policy removed all usable text.")

    output_path = build_operation_output_path(root, "cleanup", config.CLEANED_TEXT_FILE_NAME)
    write_text_atomic(output_path, cleaned_text)
    cleanup_metadata = cleanup_metadata_service.write_minimal_cleanup_metadata(root, cleaned_text, "ai_assisted")
    paragraphs = [part.strip() for part in re.split(r"\n[ \t]*\n+", cleaned_text.strip()) if part.strip()]
    report["validated_window_decisions"] = rendered_decisions
    report["selected_spacing_categories"] = sorted(spacing_categories)
    report["paragraph_count"] = len(paragraphs)
    report["detected_language"] = cleanup_text_analysis_service.detect_language(cleaned_text)
    report["detected_chapter_count"] = cleanup_text_analysis_service.count_detected_chapters(paragraphs)
    report["page_break_repair_count"] = int(cleanup_metadata.get("page_break_repair_count", 0))
    report["weak_boundary_count"] = int(cleanup_metadata.get("weak_boundary_count", 0))
    report["spacing_replacement_count"] = sum(
        1
        for decision in rendered_decisions
        for item in list(decision.get("removed_ranges", []))
        if isinstance(item, dict) and item.get("replacement") == "\n\n"
    )
    write_json_atomic(report_path, report)
    _LOGGER.info(
        "Applied AI cleanup spacing categories=%s replacements=%d",
        ",".join(sorted(spacing_categories)) or "none",
        report["spacing_replacement_count"],
    )
    return report


@trace_function(_LOGGER)
def clean_text(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
    additional_cleanup_instructions: str | None = None,
) -> CleanupReportPayload:
    """
    @brief      Run source-grounded AI cleanup for one project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  progress_callback Optional operation progress callback.
    @param[in]  cancel_requested Optional cooperative cancellation callback.
    @param[in]  additional_cleanup_instructions Optional operator cleanup rules.
    @return     Persisted AI Cleanup report payload.
    @exception  FileNotFoundError Raised when extracted text is missing.
    @exception  ValueError Raised for invalid input, response, or model budget.
    @exception  OperationCancelledError Raised when cooperative cancellation is requested.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.3.0
    """
    root = Path(project_root)
    _validate_request(manifest, ai_profile_payload)
    profile_id = str(ai_profile_payload["id"]).strip()
    extracted_path = root / config.EXTRACTED_TEXT_FILE_NAME
    if not extracted_path.is_file():
        raise FileNotFoundError(f"Extracted text is missing: {extracted_path}")
    input_text = _canonicalize_source_text(extracted_path.read_bytes().decode("utf-8"))
    if not input_text.strip():
        raise ValueError("Extracted text does not contain any content to clean.")

    output_path = build_operation_output_path(root, "cleanup", config.CLEANED_TEXT_FILE_NAME)
    report_path = build_operation_output_path(root, "cleanup", config.CLEANUP_REPORT_FILE_NAME)
    state_path = build_operation_output_path(root, "cleanup", config.CLEANUP_STATE_FILE_NAME)
    prompt_template_service.validate_required_prompts([_SYSTEM_PROMPT_NAME, _USER_PROMPT_NAME])
    system_prompt = prompt_template_service.render_prompt(_SYSTEM_PROMPT_NAME, {})
    language_hint = cleanup_text_analysis_service.detect_language(input_text) or "unknown"
    script_hint = cleanup_text_analysis_service.classify_text_script(input_text)
    existing_state = load_operation_state_file(state_path) or {}
    persisted_instructions = _state_metadata(existing_state).get("additional_cleanup_instructions", "")
    instructions = _normalize_instructions(
        persisted_instructions if additional_cleanup_instructions is None else additional_cleanup_instructions
    )
    input_fingerprint = _fingerprint(input_text)
    instructions_fingerprint = _fingerprint(instructions)
    checkpoint_value = existing_state.get("resume_checkpoint")
    checkpoint = checkpoint_value if isinstance(checkpoint_value, dict) else {}
    resume_compatible = _checkpoint_is_compatible(checkpoint, input_fingerprint, instructions_fingerprint)
    pages = _build_source_pages(input_text)
    source_stream = _window_source_text(pages)
    prompt_shell = _render_cleanup_user_prompt([], "cleanup-window-0000", language_hint, script_hint, instructions)
    budget_metadata = _build_budget_metadata(ai_profile_payload, system_prompt, prompt_shell)
    model_settings = _build_model_settings(ai_profile_payload, budget_metadata)
    model_settings_history = _update_model_settings_history(existing_state if resume_compatible else {}, model_settings)
    completed_windows, source_stream_offset = (
        _restored_completed_windows(checkpoint, source_stream) if resume_compatible else ([], 0)
    )
    remaining_pages = _source_pages_after_offset(pages, source_stream_offset)
    remaining_windows = _build_windows(remaining_pages, budget_metadata)
    total_window_count = len(completed_windows) + len(remaining_windows)
    existing_metadata = _state_metadata(existing_state)
    started_at = str(existing_metadata.get("started_at") or _utc_now_iso()) if resume_compatible else _utc_now_iso()
    log_relative_path = str(existing_metadata.get("log_relative_path", "")).strip() if resume_compatible else ""
    log_path = root / log_relative_path if log_relative_path else _build_ai_log_path(root, started_at)
    log_relative_path = relative_to_project(root, log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        write_text_atomic(log_path, "")
    token_usage = (
        _restored_token_usage(existing_state) if completed_windows else token_usage_service.empty_token_usage()
    )
    _LOGGER.info(
        "Starting AI cleanup profile_id=%s pages=%d windows=%d resume_window=%d source_stream_offset=%d",
        profile_id,
        len(pages),
        total_window_count,
        len(completed_windows) + 1,
        source_stream_offset,
    )
    _write_state(
        state_path,
        "running",
        len(completed_windows),
        total_window_count,
        root,
        output_path,
        started_at,
        None,
        profile_id,
        log_relative_path,
        input_fingerprint,
        instructions,
        instructions_fingerprint,
        completed_windows,
        token_usage,
        budget_metadata,
        model_settings,
        model_settings_history,
        _combined_warning_details(completed_windows),
    )
    _emit_progress(
        progress_callback,
        len(completed_windows),
        total_window_count,
        "Resuming AI-assisted cleanup..." if completed_windows else "AI-assisted cleanup in progress...",
        token_usage,
    )
    try:
        for window in remaining_windows:
            raise_if_cancelled(cancel_requested)
            window_number = len(completed_windows) + 1
            window_id = f"cleanup-window-{window_number:04d}"
            user_prompt = _render_cleanup_user_prompt(
                list(window["pages"]), window_id, language_hint, script_hint, instructions
            )
            response_result = llm_provider_service.chat_json(
                ai_profile_payload,
                system_prompt,
                user_prompt,
                log_path=log_path,
                log_context={
                    "operation_kind": "cleanup",
                    "stage_label": "ai_cleanup",
                    "profile_id": profile_id,
                    "window_index": window_number,
                    "window_total": total_window_count,
                    "window_id": window_id,
                },
                cancel_requested=cancel_requested,
                response_schema=_build_response_schema(),
                response_schema_name="text_cleanup_blocks",
            )
            payload = response_result.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("AI cleanup response must be one JSON object.")
            window_pages = list(window["pages"])
            validated = _validate_response(payload, window_pages, window_id)
            validated["window_id"] = window_id
            validated["source_window_fingerprint"] = _fingerprint(_window_source_text(window_pages))
            validated["source_stream_start"] = source_stream_offset
            source_stream_offset += int(validated["source_window_length"])
            validated["source_stream_end"] = source_stream_offset
            for preserved_block in list(validated.get("preserved_blocks", [])):
                if not isinstance(preserved_block, dict) or preserved_block.get("match_mode") != "anchored_modified":
                    continue
                _LOGGER.warning(
                    "Accepted modified AI cleanup Story window_id=%s text_block_id=%d source_start=%d source_end=%d",
                    window_id,
                    int(preserved_block["text_block_id"]),
                    int(preserved_block["source_window_start"]),
                    int(preserved_block["source_window_end"]),
                )
            for preserved_gap in list(validated.get("preserved_source_gaps", [])):
                if not isinstance(preserved_gap, dict):
                    continue
                _LOGGER.warning(
                    "Preserved omitted AI cleanup source gap window_id=%s source_start=%d source_end=%d",
                    window_id,
                    int(preserved_gap["source_window_start"]),
                    int(preserved_gap["source_window_end"]),
                )
            completed_windows.append(validated)
            token_usage = token_usage_service.merge_token_usage(token_usage, response_result.get("usage"))
            _write_state(
                state_path,
                "running",
                window_number,
                total_window_count,
                root,
                output_path,
                started_at,
                None,
                profile_id,
                log_relative_path,
                input_fingerprint,
                instructions,
                instructions_fingerprint,
                completed_windows,
                token_usage,
                budget_metadata,
                model_settings,
                model_settings_history,
                _combined_warning_details(completed_windows),
            )
            _emit_progress(
                progress_callback,
                window_number,
                total_window_count,
                "AI-assisted cleanup in progress...",
                token_usage,
            )
    except OperationCancelledError:
        _write_checkpoint_state(
            state_path,
            "cancelled",
            root,
            output_path,
            started_at,
            profile_id,
            log_relative_path,
            input_fingerprint,
            instructions,
            instructions_fingerprint,
            completed_windows,
            total_window_count,
            token_usage,
            budget_metadata,
            model_settings,
            model_settings_history,
        )
        raise
    except Exception:
        _LOGGER.exception("AI cleanup failed after %d validated windows", len(completed_windows))
        _write_checkpoint_state(
            state_path,
            "failed",
            root,
            output_path,
            started_at,
            profile_id,
            log_relative_path,
            input_fingerprint,
            instructions,
            instructions_fingerprint,
            completed_windows,
            total_window_count,
            token_usage,
            budget_metadata,
            model_settings,
            model_settings_history,
        )
        raise

    preserved_blocks = [
        block
        for window_result in completed_windows
        for block in list(window_result.get("preserved_blocks", []))
        if isinstance(block, dict)
    ]
    cleaned_text = "".join(str(window_result["reconstructed_text"]) for window_result in completed_windows)
    if not cleaned_text.strip():
        raise ValueError("AI-assisted cleanup removed all usable text.")
    write_text_atomic(output_path, cleaned_text)
    cleanup_metadata = cleanup_metadata_service.write_minimal_cleanup_metadata(root, cleaned_text, "ai_assisted")
    paragraphs = [part.strip() for part in re.split(r"\n[ \t]*\n+", cleaned_text.strip()) if part.strip()]
    detected_language = cleanup_text_analysis_service.detect_language(cleaned_text)
    warning_details = _combined_warning_details(completed_windows)
    warning_details.append(
        {
            "kind": "human_review_required",
            "severity": "warning",
            "message": "Compare cleaned text with the retained original extraction before downstream use.",
        }
    )
    removed_character_count = sum(int(item.get("removed_character_count", 0)) for item in completed_windows)
    restored_whitespace_character_count = sum(
        int(item.get("restored_whitespace_character_count", 0)) for item in completed_windows
    )
    restored_whitespace_gap_count = sum(int(item.get("restored_whitespace_gap_count", 0)) for item in completed_windows)
    artifact_replacement_count = sum(int(item.get("artifact_replacement_count", 0)) for item in completed_windows)
    modified_story_block_count = sum(int(item.get("modified_story_block_count", 0)) for item in completed_windows)
    preserved_source_gap_count = sum(int(item.get("preserved_source_gap_count", 0)) for item in completed_windows)
    warnings = [
        str(detail.get("message", "")).strip() for detail in warning_details if str(detail.get("message", "")).strip()
    ]
    report: CleanupReportPayload = {
        "detected_language": detected_language,
        "warnings": warnings,
        "warning_details": warning_details,
        "paragraph_count": len(paragraphs),
        "removed_line_count": artifact_replacement_count,
        "removed_character_count": removed_character_count,
        "restored_whitespace_character_count": restored_whitespace_character_count,
        "restored_whitespace_gap_count": restored_whitespace_gap_count,
        "detected_chapter_count": cleanup_text_analysis_service.count_detected_chapters(paragraphs),
        "page_break_repair_count": int(cleanup_metadata.get("page_break_repair_count", 0)),
        "weak_boundary_count": int(cleanup_metadata.get("weak_boundary_count", 0)),
        "cleanup_mode": "ai_assisted",
        "reconstruction_contract_fingerprint": _CONTRACT_FINGERPRINT,
        "selected_spacing_categories": default_spacing_categories(),
        "ai_profile_id": profile_id,
        "model_settings": model_settings,
        "model_settings_history": model_settings_history,
        "ai_log_relative_path": log_relative_path,
        "window_count": total_window_count,
        "validated_window_decisions": completed_windows,
        "source_page_count": len(pages),
        "preserved_block_count": len(preserved_blocks),
        "modified_story_block_count": modified_story_block_count,
        "preserved_source_gap_count": preserved_source_gap_count,
        "artifact_replacement_count": artifact_replacement_count,
        "spacing_replacement_count": sum(
            1
            for decision in completed_windows
            for item in list(decision.get("removed_ranges", []))
            if isinstance(item, dict) and item.get("replacement") == "\n\n"
        ),
        "token_usage": token_usage,
        "budget_metadata": budget_metadata,
        "additional_cleanup_instructions": instructions,
        "additional_cleanup_instructions_fingerprint": instructions_fingerprint,
    }
    write_json_atomic(report_path, report)
    completed_state = _write_state(
        state_path,
        "completed",
        total_window_count,
        total_window_count,
        root,
        output_path,
        started_at,
        _utc_now_iso(),
        profile_id,
        log_relative_path,
        input_fingerprint,
        instructions,
        instructions_fingerprint,
        None,
        token_usage,
        budget_metadata,
        model_settings,
        model_settings_history,
        warning_details,
        report_path=report_path,
        detected_language=detected_language,
        paragraph_count=len(paragraphs),
        removed_character_count=removed_character_count,
    )
    project_workspace_service.sync_manifest_operation_summary(
        root,
        "cleanup",
        completed_state,
        current_stage="text_chunking_ready",
        extra_fields={"original_language": detected_language},
    )
    _emit_progress(
        progress_callback,
        total_window_count,
        total_window_count,
        "AI-assisted cleanup completed; human review is required.",
        token_usage,
    )
    _LOGGER.info(
        "Completed AI cleanup windows=%d preserved_blocks=%d modified_story_blocks=%d preserved_source_gaps=%d removed_characters=%d",
        total_window_count,
        len(preserved_blocks),
        modified_story_block_count,
        preserved_source_gap_count,
        removed_character_count,
    )
    return report


@trace_function(_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Load the persisted AI Cleanup operation state.
    @param[in]  project_root Active project root folder.
    @return     Persisted operation state, or None when absent.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return load_operation_state_payload(project_root, "cleanup", config.CLEANUP_STATE_FILE_NAME)


# LOCAL HELPERS


def _canonicalize_source_text(text: str) -> str:
    """
    @brief      Canonicalize source newlines to LF exactly once.
    @param[in]  text Source text value.
    @return     Source text with CRLF and CR normalized to LF.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def _build_source_pages(canonical_text: str) -> list[SourcePagePayload]:
    """
    @brief      Build page-aware source units from canonical text.
    @param[in]  canonical_text Once-canonicalized source text.
    @return     Ordered source page payloads with canonical offsets.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    canonical = _canonicalize_source_text(canonical_text)
    raw_pages = canonical.split(_PAGE_SEPARATOR)
    pages: list[SourcePagePayload] = []
    source_offset = 0
    for zero_index, page_text in enumerate(raw_pages):
        pages.append(
            {
                "source_page_index": zero_index + 1,
                "source_kind": "page",
                "text": page_text,
                "source_start": source_offset,
                "source_end": source_offset + len(page_text),
            }
        )
        source_offset += len(page_text)
        if zero_index < len(raw_pages) - 1:
            source_offset += len(_PAGE_SEPARATOR)
    return pages


def _render_cleanup_user_prompt(
    pages: list[SourcePagePayload],
    window_id: str,
    source_language_hint: str,
    dominant_script_hint: str,
    additional_cleanup_instructions: str,
) -> str:
    """
    @brief      Render one canonical cleanup-window user prompt.
    @param[in]  pages Ordered source page or safe-segment payloads.
    @param[in]  window_id Cleanup window identifier.
    @param[in]  source_language_hint Detected source-language hint.
    @param[in]  dominant_script_hint Detected dominant-script hint.
    @param[in]  additional_cleanup_instructions Optional operator cleanup rules.
    @return     Rendered cleanup user prompt.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return prompt_template_service.render_prompt(
        _USER_PROMPT_NAME,
        {
            "window_id": window_id,
            "source_language_hint": source_language_hint,
            "dominant_script_hint": dominant_script_hint,
            "additional_cleanup_instructions": additional_cleanup_instructions or "None.",
            "source_window_block": _source_window_prompt_block(pages),
        },
    )


def _source_window_prompt_block(pages: list[SourcePagePayload]) -> str:
    """
    @brief      Wrap one source window in stable prompt markers.
    @param[in]  pages Ordered source page or safe-segment payloads.
    @return     Marked canonical source-window text.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return f"<<< SOURCE WINDOW START >>>\n{_window_source_text(pages)}<<< SOURCE WINDOW END >>>"


def _window_source_text(pages: list[SourcePagePayload]) -> str:
    """
    @brief      Concatenate ordered source units without provider identities.
    @param[in]  pages Ordered source page or safe-segment payloads.
    @return     Concatenated canonical source-window text.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return "".join(str(page["text"]) for page in pages)


def _source_pages_after_offset(
    pages: list[SourcePagePayload],
    source_stream_offset: int,
) -> list[SourcePagePayload]:
    """
    @brief      Return provider-visible source units after one validated stream offset.
    @param[in]  pages Ordered canonical source page payloads.
    @param[in]  source_stream_offset Count of provider-visible source characters already validated.
    @return     Copied remaining pages, with the first page trimmed when the offset falls inside it.
    @exception  ValueError Raised when the offset is negative or exceeds the source stream.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    0.1.0
    """
    if type(source_stream_offset) is not int or source_stream_offset < 0:
        raise ValueError("AI cleanup source-stream resume offset is invalid.")
    remaining_offset = source_stream_offset
    remaining_pages: list[SourcePagePayload] = []
    for page in pages:
        page_text = str(page["text"])
        if remaining_offset >= len(page_text):
            remaining_offset -= len(page_text)
            continue
        copied_page = dict(page)
        if remaining_offset:
            copied_page["source_kind"] = "segment"
            copied_page["text"] = page_text[remaining_offset:]
            copied_page["source_start"] = int(page.get("source_start", 0)) + remaining_offset
        remaining_pages.append(copied_page)
        remaining_offset = 0
    if remaining_offset:
        raise ValueError("AI cleanup source-stream resume offset exceeds the canonical source.")
    return remaining_pages


def _build_response_schema() -> dict[str, object]:
    """
    @brief      Build the strict canonical-window response schema.
    @return     Provider structured-output schema.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["window_id", "text_blocks"],
        "properties": {
            "window_id": {"type": "string", "minLength": 1},
            "text_blocks": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "text_block_id",
                        "text_block",
                        "artifact_type",
                        "confidence",
                    ],
                    "properties": {
                        "text_block_id": {"type": "integer", "minimum": 1},
                        "text_block": {"type": "string", "minLength": 1},
                        "artifact_type": {"type": "string", "enum": sorted(_ARTIFACT_TYPES)},
                        "confidence": {"type": "string", "enum": sorted(_CONFIDENCE_VALUES)},
                    },
                },
            },
        },
    }


def _validate_response(
    response_payload: dict[str, object],
    pages: list[SourcePagePayload],
    expected_window_id: str,
) -> ValidatedWindowPayload:
    """
    @brief      Validate and reconstruct one canonical source window.
    @param[in]  response_payload Provider JSON response object.
    @param[in]  pages Ordered source page or safe-segment payloads.
    @param[in]  expected_window_id Window identifier expected for the response.
    @return     Validated reconstructed window payload.
    @exception  ValueError Raised when the provider response violates the cleanup contract.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.3.0
    """
    allowed_response_fields = {"window_id", "text_blocks"}
    if set(response_payload) != allowed_response_fields:
        raise ValueError("AI cleanup response contains unsupported fields or is missing required fields.")
    if response_payload.get("window_id") != expected_window_id:
        raise ValueError("AI cleanup response window_id does not match the request.")
    raw_blocks = response_payload.get("text_blocks")
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise ValueError("AI cleanup response text_blocks must be a non-empty array.")

    allowed_block_fields = {
        "text_block_id",
        "text_block",
        "artifact_type",
        "confidence",
    }
    normalized_blocks: list[dict[str, object]] = []
    for expected_id, item in enumerate(raw_blocks, start=1):
        if not isinstance(item, dict):
            raise ValueError("Every AI cleanup text block must be one JSON object.")
        if set(item) != allowed_block_fields:
            raise ValueError("AI cleanup response block contains unsupported fields or is missing required fields.")
        block_id = item.get("text_block_id")
        if type(block_id) is not int or block_id != expected_id:
            raise ValueError("AI cleanup text_block_id values must be sequential starting at 1.")
        text_block = item.get("text_block")
        if not isinstance(text_block, str) or not text_block:
            raise ValueError("AI cleanup text_block values must be non-empty strings.")
        artifact_type = item.get("artifact_type")
        confidence = item.get("confidence")
        if artifact_type not in _ARTIFACT_TYPES:
            raise ValueError("AI cleanup response contains an unsupported artifact_type.")
        if confidence not in _CONFIDENCE_VALUES:
            raise ValueError("AI cleanup response contains an unsupported confidence value.")
        normalized_blocks.append(
            {
                "text_block_id": block_id,
                "text_block": text_block,
                "artifact_type": artifact_type,
                "confidence": confidence,
            }
        )

    source_text = _window_source_text(pages)
    preserved_blocks: list[dict[str, object]] = []
    preserved_spans: list[tuple[int, int]] = []
    removed_ranges: list[dict[str, object]] = []
    restored_whitespace_ranges: list[dict[str, object]] = []
    preserved_source_gaps: list[dict[str, object]] = []
    output_fragments: list[str] = []
    modified_story_warning_details: list[dict[str, object]] = []
    preserved_gap_warning_details: list[dict[str, object]] = []
    cursor = 0
    previous_was_modified_story = False
    previous_match_mode: str | None = None

    for block_index, block in enumerate(normalized_blocks):
        exact_text = str(block["text_block"])
        match_index = source_text.find(exact_text, cursor)
        gap_text = source_text[cursor:match_index] if match_index >= 0 else ""
        preserve_internal_gap = (
            block_index > 0
            and previous_match_mode == "exact"
            and match_index > cursor
            and not gap_text.isspace()
            and _source_occurrences(source_text, exact_text, cursor) == [match_index]
        )
        exact_gap_valid = match_index >= 0 and (
            match_index == cursor or source_text[cursor:match_index].isspace()
            or preserve_internal_gap
        )
        if not exact_gap_valid:
            fallback_span = None
            if block["artifact_type"] == "story" and not previous_was_modified_story:
                fallback_span = _locate_modified_story_span(
                    source_text,
                    cursor,
                    normalized_blocks,
                    block_index,
                )
            if fallback_span is None:
                if match_index >= 0:
                    raise ValueError(
                        "AI cleanup response leaves an unexplained source gap or violates exact source slice order."
                    )
                raise ValueError("AI cleanup text_block is not an exact source slice in forward source order.")

            match_index, block_end = fallback_span
            if match_index > cursor:
                gap_text = source_text[cursor:match_index]
                output_fragments.append(gap_text)
                restored_whitespace_ranges.append(
                    {
                        "source_window_start": cursor,
                        "source_window_end": match_index,
                        "text": gap_text,
                        "reason": "restored_whitespace_gap",
                    }
                )
            source_span_text = source_text[match_index:block_end]
            preserved_blocks.append(
                {
                    **block,
                    "match_mode": "anchored_modified",
                    "source_text": source_span_text,
                    "source_window_start": match_index,
                    "source_window_end": block_end,
                }
            )
            preserved_spans.append((match_index, block_end))
            output_fragments.append(exact_text)
            modified_story_warning_details.append(
                {
                    "kind": "modified_story_text_accepted",
                    "severity": "warning",
                    "text_block_id": int(block["text_block_id"]),
                    "source_window_start": match_index,
                    "source_window_end": block_end,
                    "message": "AI cleanup accepted modified Story text using unique normalized edge anchors; compare it with the original.",
                }
            )
            cursor = block_end
            previous_was_modified_story = True
            previous_match_mode = "anchored_modified"
            continue

        if match_index > cursor:
            gap_text = source_text[cursor:match_index]
            output_fragments.append(gap_text)
            gap_payload = {
                "source_window_start": cursor,
                "source_window_end": match_index,
                "text": gap_text,
            }
            if preserve_internal_gap:
                preserved_source_gaps.append(
                    {
                        **gap_payload,
                        "reason": "unclassified_source_gap_preserved",
                    }
                )
                preserved_spans.append((cursor, match_index))
                preserved_gap_warning_details.append(
                    {
                        "kind": "unclassified_source_gap_preserved",
                        "severity": "warning",
                        "source_window_start": cursor,
                        "source_window_end": match_index,
                        "message": "AI cleanup preserved source text omitted between unique exact block boundaries; compare it with the provider response.",
                    }
                )
            else:
                restored_whitespace_ranges.append(
                    {
                        **gap_payload,
                        "reason": "restored_whitespace_gap",
                    }
                )

        block_end = match_index + len(exact_text)
        if block["artifact_type"] in _NON_DISPLAY_ARTIFACT_TYPES:
            removed_ranges.append(_removed_range(match_index, block_end, exact_text, block))
            output_fragments.append(_ARTIFACT_REPLACEMENTS[str(block["artifact_type"])])
        else:
            preserved_blocks.append(
                {
                    **block,
                    "match_mode": "exact",
                    "source_window_start": match_index,
                    "source_window_end": block_end,
                }
            )
            preserved_spans.append((match_index, block_end))
            output_fragments.append(exact_text)
        cursor = block_end
        previous_was_modified_story = False
        previous_match_mode = "exact"

    if cursor < len(source_text):
        gap_text = source_text[cursor:]
        if not gap_text.isspace():
            raise ValueError(
                "AI cleanup response leaves an unexplained source gap or violates exact source slice order."
            )
        output_fragments.append(gap_text)
        restored_whitespace_ranges.append(
            {
                "source_window_start": cursor,
                "source_window_end": len(source_text),
                "text": gap_text,
                "reason": "restored_whitespace_gap",
            }
        )

    warning_details: list[dict[str, object]] = [
        *modified_story_warning_details,
        *preserved_gap_warning_details,
    ]
    source_offset = 0
    for page in pages:
        page_index = int(page["source_page_index"])
        page_text = str(page["text"])
        page_start = source_offset
        page_end = page_start + len(page_text)
        source_offset = page_end
        has_preserved_text = any(
            span_start < page_end and span_end > page_start for span_start, span_end in preserved_spans
        )
        if page_text and not has_preserved_text:
            warning_details.append(
                {
                    "kind": "entire_page_removed",
                    "severity": "warning",
                    "source_page_index": page_index,
                    "message": f"AI cleanup removed all content of source page/segment {page_index}.",
                }
            )

    removed_character_count = sum(len(str(item["text"])) for item in removed_ranges)
    restored_whitespace_character_count = sum(len(str(item["text"])) for item in restored_whitespace_ranges)
    total_characters = len(source_text)
    if total_characters and removed_character_count / total_characters > 0.55:
        warning_details.append(
            {
                "kind": "high_removal_ratio",
                "severity": "warning",
                "message": "AI cleanup removed more than 55% of the canonical source window.",
            }
        )
    for removed_range in removed_ranges:
        removed_text = str(removed_range["text"])
        if len(removed_text) >= 240 and len(removed_text.split()) >= 25:
            warning_details.append(
                {
                    "kind": "long_prose_like_removal",
                    "severity": "warning",
                    "message": "AI cleanup removed a long prose-like range; compare it with the original.",
                }
            )
    if len(normalized_blocks) > max(32, total_characters // 20):
        warning_details.append(
            {
                "kind": "fragmented_model_output",
                "severity": "warning",
                "message": "AI cleanup returned unusually fragmented block output.",
            }
        )
    warning_details.extend(_repeated_classification_warnings(preserved_blocks, removed_ranges))
    validated_window = {
        "preserved_blocks": preserved_blocks,
        "reconstructed_text": "".join(output_fragments),
        "removed_ranges": removed_ranges,
        "restored_whitespace_ranges": restored_whitespace_ranges,
        "preserved_source_gaps": preserved_source_gaps,
        "removed_character_count": removed_character_count,
        "restored_whitespace_character_count": restored_whitespace_character_count,
        "restored_whitespace_gap_count": len(restored_whitespace_ranges),
        "artifact_replacement_count": len(removed_ranges),
        "modified_story_block_count": len(modified_story_warning_details),
        "preserved_source_gap_count": len(preserved_source_gaps),
        "warning_details": warning_details,
        "response_block_count": len(normalized_blocks),
        "source_window_length": len(source_text),
    }
    return _render_validated_window(validated_window, _DEFAULT_SPACING_CATEGORIES)


def _locate_modified_story_span(
    source_text: str,
    cursor: int,
    blocks: list[dict[str, object]],
    block_index: int,
) -> tuple[int, int] | None:
    """
    @brief      Locate one uniquely bounded non-exact Story source span.
    @param[in]  source_text Canonical source window text.
    @param[in]  cursor First unconsumed source offset.
    @param[in]  blocks Validated ordered provider blocks.
    @param[in]  block_index Index of the non-exact Story block.
    @return     Unique source start/end pair, or None when unsafe or ambiguous.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    returned_text = str(blocks[block_index]["text_block"])
    source_start = cursor
    while source_start < len(source_text) and source_text[source_start].isspace():
        source_start += 1

    if block_index + 1 >= len(blocks):
        boundary_positions = [len(source_text)]
    else:
        next_text = str(blocks[block_index + 1]["text_block"])
        boundary_positions = _source_occurrences(source_text, next_text, source_start)
        if not boundary_positions:
            return None

    candidates: list[tuple[int, int]] = []
    for boundary in boundary_positions:
        source_end = boundary
        while source_end > source_start and source_text[source_end - 1].isspace():
            source_end -= 1
        if source_end <= source_start:
            continue
        source_candidate = source_text[source_start:source_end]
        if _modified_story_edges_match(source_candidate, returned_text):
            candidates.append((source_start, source_end))
            if len(candidates) > 1:
                return None
    return candidates[0] if len(candidates) == 1 else None


def _source_occurrences(source_text: str, exact_text: str, start: int) -> list[int]:
    """
    @brief      Return every forward occurrence of one non-empty exact block.
    @param[in]  source_text Canonical source window text.
    @param[in]  exact_text Exact next-block delimiter text.
    @param[in]  start Inclusive source search offset.
    @return     Ordered source offsets, including overlapping occurrences.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    positions: list[int] = []
    search_offset = start
    while search_offset <= len(source_text) - len(exact_text):
        position = source_text.find(exact_text, search_offset)
        if position < 0:
            break
        positions.append(position)
        search_offset = position + 1
    return positions


def _modified_story_edges_match(source_text: str, returned_text: str) -> bool:
    """
    @brief      Compare normalized edge anchors without constraining Story interior text.
    @param[in]  source_text Candidate original Story source span.
    @param[in]  returned_text Provider-returned Story text.
    @return     True when both normalized texts provide matching sufficient edges.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    normalized_source = _normalize_story_anchor_text(source_text)
    normalized_returned = _normalize_story_anchor_text(returned_text)
    minimum_length = min(len(normalized_source), len(normalized_returned))
    if minimum_length < _MODIFIED_STORY_MIN_NORMALIZED_LENGTH:
        return False
    anchor_length = min(_MODIFIED_STORY_MAX_EDGE_ANCHOR_LENGTH, minimum_length // 2)
    return (
        normalized_source[:anchor_length] == normalized_returned[:anchor_length]
        and normalized_source[-anchor_length:] == normalized_returned[-anchor_length:]
    )


def _normalize_story_anchor_text(text: str) -> str:
    """
    @brief      Case-fold Story text and discard punctuation and whitespace for edge matching.
    @param[in]  text Story source or provider text.
    @return     Concatenated Unicode alphanumeric characters.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    return "".join(character for character in text.casefold() if character.isalnum())


def _render_validated_window(
    window_payload: ValidatedWindowPayload,
    selected_categories: object,
) -> ValidatedWindowPayload:
    """
    @brief      Reconstruct one retained validated window for a complete spacing selection.
    @param[in]  window_payload Retained source-associated validation decision payload.
    @param[in]  selected_categories Complete selected non-story category collection.
    @return     Copied window payload with updated replacements and reconstructed text.
    @exception  ValueError Raised when retained ranges are missing, overlapping, or incompatible.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.2.0
    """
    spacing_categories = _normalize_spacing_categories(selected_categories)
    source_length = window_payload.get("source_window_length")
    if type(source_length) is not int or source_length < 0:
        raise ValueError("Retained AI Cleanup window length is missing or invalid.")

    fragments: list[tuple[int, int, str]] = []
    rendered_ranges: list[dict[str, object]] = []
    for raw_range in list(window_payload.get("removed_ranges", [])):
        if not isinstance(raw_range, dict):
            raise ValueError("Retained AI Cleanup artifact range is invalid.")
        decision = raw_range.get("decision")
        if not isinstance(decision, dict):
            raise ValueError("Retained AI Cleanup artifact decision is missing.")
        artifact_type = str(decision.get("artifact_type", ""))
        replacement = "\n\n" if artifact_type in spacing_categories else ""
        rendered_range = {**raw_range, "replacement": replacement}
        rendered_ranges.append(rendered_range)
        fragments.append(
            (
                int(rendered_range["source_window_start"]),
                int(rendered_range["source_window_end"]),
                replacement,
            )
        )

    for raw_block in list(window_payload.get("preserved_blocks", [])):
        if not isinstance(raw_block, dict):
            raise ValueError("Retained AI Cleanup story block is invalid.")
        fragments.append(
            (
                int(raw_block["source_window_start"]),
                int(raw_block["source_window_end"]),
                str(raw_block["text_block"]),
            )
        )

    for raw_gap in list(window_payload.get("restored_whitespace_ranges", [])):
        if not isinstance(raw_gap, dict):
            raise ValueError("Retained AI Cleanup whitespace range is invalid.")
        fragments.append(
            (
                int(raw_gap["source_window_start"]),
                int(raw_gap["source_window_end"]),
                "",
            )
        )

    for raw_gap in list(window_payload.get("preserved_source_gaps", [])):
        if not isinstance(raw_gap, dict):
            raise ValueError("Retained AI Cleanup preserved source gap is invalid.")
        if raw_gap.get("reason") != "unclassified_source_gap_preserved":
            raise ValueError("Retained AI Cleanup preserved source-gap reason is invalid.")
        fragments.append(
            (
                int(raw_gap["source_window_start"]),
                int(raw_gap["source_window_end"]),
                str(raw_gap["text"]),
            )
        )

    fragments.sort(key=lambda item: (item[0], item[1]))
    cursor = 0
    output_fragments: list[str] = []
    for start, end, output_text in fragments:
        if start != cursor or end <= start:
            raise ValueError("Retained AI Cleanup source ranges are incomplete or overlapping.")
        cursor = end
        output_fragments.append(output_text)
    if cursor != source_length:
        raise ValueError("Retained AI Cleanup source ranges do not cover the validated window.")

    return {
        **window_payload,
        "removed_ranges": rendered_ranges,
        "reconstructed_text": "".join(output_fragments),
        "selected_spacing_categories": sorted(spacing_categories),
    }


def _normalize_spacing_categories(selected_categories: object) -> frozenset[str]:
    """
    @brief      Validate one complete non-story AI Cleanup spacing selection.
    @param[in]  selected_categories Raw selected category collection.
    @return     Normalized immutable category set.
    @exception  ValueError Raised for scalar, unknown, or story selections.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    if isinstance(selected_categories, (str, bytes)) or not isinstance(
        selected_categories,
        (list, tuple, set, frozenset),
    ):
        raise ValueError("AI Cleanup spacing categories must be a collection.")
    normalized = frozenset(str(item).strip().casefold() for item in selected_categories if str(item).strip())
    unsupported = normalized - _NON_DISPLAY_ARTIFACT_TYPES
    if unsupported:
        raise ValueError(f"Unsupported AI Cleanup spacing categories: {', '.join(sorted(unsupported))}.")
    return normalized


def _removed_range(
    start: int,
    end: int,
    text: str,
    block: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Describe one deterministically rendered non-story source slice.
    @param[in]  start Inclusive canonical-window source offset.
    @param[in]  end Exclusive canonical-window source offset.
    @param[in]  text Source text value.
    @param[in]  block Validated non-story response block.
    @return     Structured artifact-rendering range.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.2.0
    """
    return {
        "source_window_start": start,
        "source_window_end": end,
        "text": text,
        "replacement": "\n\n" if block["artifact_type"] in _DEFAULT_SPACING_CATEGORIES else "",
        "decision": {
            "text_block_id": block["text_block_id"],
            "artifact_type": block["artifact_type"],
            "confidence": block["confidence"],
            "text_block": block["text_block"],
        },
    }


def _repeated_classification_warnings(
    preserved_blocks: list[dict[str, object]],
    removed_ranges: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Build warnings for text classified as both story and artifact.
    @param[in]  preserved_blocks Validated story blocks.
    @param[in]  removed_ranges Exact non-story source ranges.
    @return     Structured repeated-classification warnings.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    preserved = {str(block["text_block"]).strip() for block in preserved_blocks if str(block["text_block"]).strip()}
    removed = {str(item["text"]).strip() for item in removed_ranges if str(item["text"]).strip()}
    repeated = sorted(preserved & removed)
    if not repeated:
        return []
    return [
        {
            "kind": "inconsistent_repeated_text_classification",
            "severity": "warning",
            "message": "Identical repeated source text was both preserved and removed in one window.",
            "example": repeated[0][:160],
        }
    ]


def _build_budget_metadata(
    ai_profile_payload: dict[str, object],
    system_prompt: str,
    user_prompt_shell: str,
) -> dict[str, object]:
    """
    @brief      Build model-context budgeting metadata for cleanup windows.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  system_prompt Rendered cleanup system prompt.
    @param[in]  user_prompt_shell Rendered user-prompt shell without source pages.
    @return     Cleanup model-budget metadata.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    context_window = int(ai_profile_payload.get("context_window", config.DEFAULT_LLM_CONTEXT_WINDOW))
    max_output_tokens = int(ai_profile_payload.get("max_output_tokens", config.DEFAULT_LLM_MAX_OUTPUT_TOKENS))
    safety_margin = max(
        config.DEFAULT_AI_CLEANUP_MIN_SAFETY_MARGIN_TOKENS,
        math.ceil(context_window * config.DEFAULT_AI_CLEANUP_SAFETY_MARGIN_CONTEXT_FRACTION),
    )
    return {
        "context_window": context_window,
        "max_output_tokens": max_output_tokens,
        "prompt_budget_tokens": _estimate_text_tokens(system_prompt) + _estimate_text_tokens(user_prompt_shell),
        "safety_margin_tokens": safety_margin,
        "response_expansion_factor": config.DEFAULT_AI_CLEANUP_RESPONSE_EXPANSION_FACTOR,
        "target_page_count": config.DEFAULT_AI_CLEANUP_TARGET_PAGE_COUNT,
        "block_overhead_tokens": config.DEFAULT_AI_CLEANUP_BLOCK_OVERHEAD_TOKENS,
    }


def _build_windows(
    pages: list[SourcePagePayload],
    budget_metadata: dict[str, object],
) -> list[dict[str, object]]:
    """
    @brief      Partition source units into budget-safe cleanup windows.
    @param[in]  pages Ordered source page or safe-segment payloads.
    @param[in]  budget_metadata Cleanup model-budget metadata.
    @return     Ordered budget-safe cleanup windows.
    @exception  ValueError Raised when even one source unit cannot fit model limits.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    if not pages:
        return []
    working_pages = [dict(page) for page in pages]
    target_count = max(1, int(budget_metadata.get("target_page_count", 4)))
    windows: list[dict[str, object]] = []
    page_offset = 0
    while page_offset < len(working_pages):
        selected: list[SourcePagePayload] = []
        selected_estimate: dict[str, int] | None = None
        while page_offset + len(selected) < len(working_pages) and len(selected) < target_count:
            candidate = selected + [working_pages[page_offset + len(selected)]]
            estimate = _window_budget_estimate(candidate, budget_metadata)
            if not _window_estimate_fits(estimate, budget_metadata):
                break
            selected = candidate
            selected_estimate = estimate
        if not selected or selected_estimate is None:
            page = working_pages[page_offset]
            replacements = _split_page_at_boundary(page)
            if len(replacements) == 1:
                raise ValueError(
                    "AI cleanup profile has insufficient output capacity for the smallest source page/segment."
                )
            working_pages = working_pages[:page_offset] + replacements + working_pages[page_offset + 1 :]
            _renumber_source_pages(working_pages)
            continue
        windows.append({"pages": selected, **selected_estimate})
        page_offset += len(selected)
    return windows


def _window_budget_estimate(
    pages: list[SourcePagePayload],
    budget: dict[str, object],
) -> dict[str, int]:
    """
    @brief      Estimate prompt and response tokens for one candidate window.
    @param[in]  pages Ordered source page or safe-segment payloads.
    @param[in]  budget Cleanup model-budget metadata.
    @return     Candidate-window token estimate.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    source_tokens = _estimate_text_tokens(_window_source_text(pages))
    output_tokens = max(
        1,
        math.ceil(source_tokens * float(budget.get("response_expansion_factor", 2.0)))
        + len(pages) * int(budget.get("block_overhead_tokens", 256))
        + 64,
    )
    context_tokens = (
        int(budget.get("prompt_budget_tokens", 0))
        + source_tokens
        + output_tokens
        + int(budget.get("safety_margin_tokens", 0))
    )
    return {
        "estimated_source_tokens": source_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_context_tokens": context_tokens,
    }


def _window_estimate_fits(estimate: dict[str, int], budget: dict[str, object]) -> bool:
    """
    @brief      Check whether one window estimate fits model limits.
    @param[in]  estimate Candidate-window token estimate.
    @param[in]  budget Cleanup model-budget metadata.
    @return     True when the candidate fits all model limits.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return estimate["estimated_output_tokens"] <= int(budget.get("max_output_tokens", 0)) and estimate[
        "estimated_context_tokens"
    ] <= int(budget.get("context_window", 0))


def _split_page_at_boundary(page: SourcePagePayload) -> list[SourcePagePayload]:
    """
    @brief      Split one oversized source unit at an existing newline.
    @param[in]  page Source page or safe-segment payload.
    @return     One or two source segments split at an existing newline.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    text = str(page["text"])
    boundaries = [index + 1 for index, character in enumerate(text) if character == "\n" and index + 1 < len(text)]
    if not boundaries:
        return [page]
    boundary = min(boundaries, key=lambda value: abs(value - len(text) // 2))
    return [
        {**page, "source_kind": "segment", "text": text[:boundary]},
        {**page, "source_kind": "segment", "text": text[boundary:]},
    ]


def _renumber_source_pages(pages: list[SourcePagePayload]) -> None:
    """
    @brief      Renumber source units and recompute canonical offsets.
    @param[in]  pages Ordered source page or safe-segment payloads.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    offset = 0
    for source_index, page in enumerate(pages, start=1):
        page["source_page_index"] = source_index
        page["source_start"] = offset
        offset += len(str(page["text"]))
        page["source_end"] = offset


def _checkpoint_is_compatible(
    checkpoint: dict[str, object],
    input_fingerprint: str,
    instructions_fingerprint: str,
) -> bool:
    """
    @brief      Check checkpoint compatibility with the current cleanup contract.
    @param[in]  checkpoint Persisted cleanup checkpoint payload.
    @param[in]  input_fingerprint Canonical input-text fingerprint.
    @param[in]  instructions_fingerprint Operator-instructions fingerprint.
    @return     True when checkpoint and current contract identities match.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return (
        checkpoint.get("contract_fingerprint") == _CONTRACT_FINGERPRINT
        and checkpoint.get("input_fingerprint") == input_fingerprint
        and checkpoint.get("additional_cleanup_instructions_fingerprint") == instructions_fingerprint
        and isinstance(checkpoint.get("completed_windows"), list)
    )


def _restored_completed_windows(
    checkpoint: dict[str, object],
    source_stream: str,
) -> tuple[list[ValidatedWindowPayload], int]:
    """
    @brief      Restore the valid checkpoint prefix against canonical source-stream slices.
    @param[in]  checkpoint Persisted cleanup checkpoint payload.
    @param[in]  source_stream Canonical provider-visible source text.
    @return     Valid leading window results and the first unprocessed source-stream offset.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.2.0
    """
    restored: list[ValidatedWindowPayload] = []
    source_stream_offset = 0
    items = checkpoint.get("completed_windows", [])
    if not isinstance(items, list):
        return restored, source_stream_offset
    for zero_index, item in enumerate(items):
        if not isinstance(item, dict):
            break
        expected_id = f"cleanup-window-{zero_index + 1:04d}"
        source_window_length = item.get("source_window_length")
        if type(source_window_length) is not int or source_window_length <= 0:
            break
        source_stream_end = source_stream_offset + source_window_length
        if source_stream_end > len(source_stream):
            break
        expected_fingerprint = _fingerprint(source_stream[source_stream_offset:source_stream_end])
        if item.get("window_id") != expected_id or item.get("source_window_fingerprint") != expected_fingerprint:
            break
        if not isinstance(item.get("preserved_blocks"), list):
            break
        if not isinstance(item.get("reconstructed_text"), str):
            break
        restored_item = dict(item)
        stored_start = restored_item.get("source_stream_start", source_stream_offset)
        stored_end = restored_item.get("source_stream_end", source_stream_end)
        if stored_start != source_stream_offset or stored_end != source_stream_end:
            break
        restored_item["source_stream_start"] = source_stream_offset
        restored_item["source_stream_end"] = source_stream_end
        restored.append(restored_item)
        source_stream_offset = source_stream_end
    return restored, source_stream_offset


def _build_model_settings(profile: dict[str, object], budget: dict[str, object]) -> dict[str, object]:
    """
    @brief      Build persisted model settings for the cleanup run.
    @param[in]  profile Selected AI profile payload.
    @param[in]  budget Cleanup model-budget metadata.
    @return     Persistable model-settings payload.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return {
        "ai_profile_id": str(profile.get("id", "")),
        "backend_kind": str(profile.get("backend_kind", "")),
        "model_name": str(profile.get("model_name", "")),
        "context_window": int(budget["context_window"]),
        "max_output_tokens": int(budget["max_output_tokens"]),
        "temperature": float(profile.get("temperature", config.DEFAULT_LLM_TEMPERATURE)),
        "response_expansion_factor": float(budget["response_expansion_factor"]),
    }


def _update_model_settings_history(
    existing_state: dict[str, object], model_settings: dict[str, object]
) -> list[dict[str, object]]:
    """
    @brief      Append changed model settings to persisted history.
    @param[in]  existing_state Previously persisted cleanup state.
    @param[in]  model_settings Current persisted model settings.
    @return     Updated model-settings history.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    value = _state_metadata(existing_state).get("model_settings_history", [])
    history = [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    if not history or history[-1] != model_settings:
        history.append(dict(model_settings))
    return history


def _write_state(
    state_path: Path,
    status: str,
    progress_current: int,
    progress_total: int,
    root: Path,
    output_path: Path,
    started_at: str,
    completed_at: str | None,
    profile_id: str,
    log_relative_path: str,
    input_fingerprint: str,
    instructions: str,
    instructions_fingerprint: str,
    completed_windows: list[ValidatedWindowPayload] | None,
    token_usage: dict[str, object],
    budget_metadata: dict[str, object],
    model_settings: dict[str, object],
    model_settings_history: list[dict[str, object]],
    warning_details: list[dict[str, object]],
    *,
    report_path: Path | None = None,
    detected_language: str | None = None,
    paragraph_count: int | None = None,
    removed_character_count: int | None = None,
) -> OperationStatePayload:
    """
    @brief      Persist one complete AI Cleanup operation-state snapshot.
    @param[in]  state_path Cleanup operation-state file path.
    @param[in]  status Operation status value.
    @param[in]  progress_current Completed cleanup-window count.
    @param[in]  progress_total Total cleanup-window count.
    @param[in]  root Resolved project root path.
    @param[in]  output_path Cleaned-text output path.
    @param[in]  started_at Operation start timestamp.
    @param[in]  completed_at Optional operation completion timestamp.
    @param[in]  profile_id Selected AI profile identifier.
    @param[in]  log_relative_path Project-relative AI transaction log path.
    @param[in]  input_fingerprint Canonical input-text fingerprint.
    @param[in]  instructions Normalized operator cleanup instructions.
    @param[in]  instructions_fingerprint Operator-instructions fingerprint.
    @param[in]  completed_windows Fully validated cleanup-window results.
    @param[in]  token_usage Accumulated provider token usage.
    @param[in]  budget_metadata Cleanup model-budget metadata.
    @param[in]  model_settings Current persisted model settings.
    @param[in]  model_settings_history Persisted model-settings history.
    @param[in]  warning_details Structured cleanup warning details.
    @param[in]  report_path Optional cleanup-report path.
    @param[in]  detected_language Optional detected output language.
    @param[in]  paragraph_count Optional reconstructed paragraph count.
    @param[in]  removed_character_count Optional replaced source-character count.
    @return     Persisted operation-state payload.
    @exception  OSError Raised when atomic state persistence fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    metadata: dict[str, object] = {
        "started_at": started_at,
        "completed_at": completed_at,
        "ai_profile_id": profile_id,
        "input_relative_path": relative_to_project(root, root / config.EXTRACTED_TEXT_FILE_NAME),
        "output_relative_path": relative_to_project(root, output_path),
        "log_relative_path": log_relative_path,
        "input_fingerprint": input_fingerprint,
        "additional_cleanup_instructions": instructions,
        "additional_cleanup_instructions_fingerprint": instructions_fingerprint,
        "token_usage": token_usage,
        "budget_metadata": budget_metadata,
        "model_settings": model_settings,
        "model_settings_history": model_settings_history,
        "warning_details": warning_details,
    }
    if report_path is not None:
        metadata["report_relative_path"] = relative_to_project(root, report_path)
    if detected_language is not None:
        metadata["detected_language"] = detected_language
    if paragraph_count is not None:
        metadata["paragraph_count"] = paragraph_count
    if removed_character_count is not None:
        metadata["removed_character_count"] = removed_character_count
    checkpoint = None
    if completed_windows is not None:
        checkpoint = {
            "contract_fingerprint": _CONTRACT_FINGERPRINT,
            "input_fingerprint": input_fingerprint,
            "additional_cleanup_instructions_fingerprint": instructions_fingerprint,
            "completed_windows": completed_windows,
        }
    state = build_operation_state_payload(
        status=status,
        progress_current=progress_current,
        progress_total=progress_total,
        mode="ai_assisted",
        warning_count=len(warning_details),
        metadata=metadata,
        resume_checkpoint=checkpoint,
    )
    write_json_atomic(state_path, state)
    return state


def _write_checkpoint_state(
    state_path: Path,
    status: str,
    root: Path,
    output_path: Path,
    started_at: str,
    profile_id: str,
    log_relative_path: str,
    input_fingerprint: str,
    instructions: str,
    instructions_fingerprint: str,
    completed_windows: list[ValidatedWindowPayload],
    total_window_count: int,
    token_usage: dict[str, object],
    budget_metadata: dict[str, object],
    model_settings: dict[str, object],
    model_settings_history: list[dict[str, object]],
) -> None:
    """
    @brief      Persist resumable state after cancellation or failure.
    @param[in]  state_path Cleanup operation-state file path.
    @param[in]  status Operation status value.
    @param[in]  root Resolved project root path.
    @param[in]  output_path Cleaned-text output path.
    @param[in]  started_at Operation start timestamp.
    @param[in]  profile_id Selected AI profile identifier.
    @param[in]  log_relative_path Project-relative AI transaction log path.
    @param[in]  input_fingerprint Canonical input-text fingerprint.
    @param[in]  instructions Normalized operator cleanup instructions.
    @param[in]  instructions_fingerprint Operator-instructions fingerprint.
    @param[in]  completed_windows Fully validated cleanup-window results.
    @param[in]  total_window_count Restored prefix plus current suffix window count.
    @param[in]  token_usage Accumulated provider token usage.
    @param[in]  budget_metadata Cleanup model-budget metadata.
    @param[in]  model_settings Current persisted model settings.
    @param[in]  model_settings_history Persisted model-settings history.
    @return     None.
    @exception  OSError Raised when atomic checkpoint persistence fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.2.0
    """
    _write_state(
        state_path,
        status,
        len(completed_windows),
        total_window_count,
        root,
        output_path,
        started_at,
        _utc_now_iso(),
        profile_id,
        log_relative_path,
        input_fingerprint,
        instructions,
        instructions_fingerprint,
        completed_windows,
        token_usage,
        budget_metadata,
        model_settings,
        model_settings_history,
        _combined_warning_details(completed_windows),
    )


def _combined_warning_details(
    completed_windows: list[ValidatedWindowPayload],
) -> list[dict[str, object]]:
    """
    @brief      Flatten warning details from validated cleanup windows.
    @param[in]  completed_windows Fully validated cleanup-window results.
    @return     Flattened structured warning details.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return [
        dict(detail)
        for window in completed_windows
        for detail in list(window.get("warning_details", []))
        if isinstance(detail, dict)
    ]


def _restored_token_usage(existing_state: dict[str, object]) -> dict[str, object]:
    """
    @brief      Restore accumulated token usage from prior state.
    @param[in]  existing_state Previously persisted cleanup state.
    @return     Restored or empty token-usage payload.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    usage = _state_metadata(existing_state).get("token_usage")
    return dict(usage) if isinstance(usage, dict) else token_usage_service.empty_token_usage()


def _state_metadata(state: dict[str, object]) -> dict[str, object]:
    """
    @brief      Return a defensive copy of operation-state metadata.
    @param[in]  state Operation-state payload.
    @return     Defensive operation-state metadata copy.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    metadata = state.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _validate_request(manifest: dict[str, object], profile: dict[str, object]) -> None:
    """
    @brief      Validate project and AI profile prerequisites.
    @param[in]  manifest Active project manifest payload.
    @param[in]  profile Selected AI profile payload.
    @return     None.
    @exception  ValueError Raised when project or AI profile prerequisites are invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    if not isinstance(manifest.get("source_document"), dict):
        raise ValueError("No imported source is available for AI-assisted cleanup.")
    if any(not str(profile.get(field, "")).strip() for field in ("id", "model_name", "base_url")):
        raise ValueError("AI-assisted cleanup requires a valid enabled AI profile.")


def _normalize_instructions(value: object) -> str:
    """
    @brief      Canonicalize and trim operator cleanup instructions.
    @param[in]  value Raw operator-instructions value.
    @return     Canonical trimmed operator instructions.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return _canonicalize_source_text(str(value or "")).strip()


def _estimate_text_tokens(text: str) -> int:
    """
    @brief      Estimate token usage from UTF-8 byte length.
    @param[in]  text Source text value.
    @return     Estimated token count.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return max(1, math.ceil(len(str(text).encode("utf-8")) / 4))


def _fingerprint(text: str) -> str:
    """
    @brief      Build a stable SHA-256 text fingerprint.
    @param[in]  text Source text value.
    @return     Lowercase hexadecimal SHA-256 digest.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _build_ai_log_path(project_root: Path, started_at: str) -> Path:
    """
    @brief      Build the project-local AI transaction log path.
    @param[in]  project_root Active project root folder.
    @param[in]  started_at Operation start timestamp.
    @return     Project-local AI transaction log path.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    token = re.sub(r"[^0-9A-Za-z]+", "", started_at)[:24] or "cleanup"
    return project_root / config.ai_transaction_log_file_name("cleanup", token)


# END OF FILE
