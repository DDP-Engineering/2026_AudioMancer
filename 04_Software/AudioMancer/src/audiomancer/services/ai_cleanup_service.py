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
         exact forward-preserved blocks, and persists resumable review artifacts.
@author Eng. Dan Dumitru Pasare
@date 2026-07-14
@version 1.0.0
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
    b"window_id|text_blocks|text_block_id|text_block|artifact_type:footer,header,heading,noise,separator,story|confidence:high,medium,low"
).hexdigest()
_SYSTEM_PROMPT_NAME = "text_cleanup_system"
_USER_PROMPT_NAME = "text_cleanup_user"
_ARTIFACT_TYPES = frozenset({"header", "footer", "noise", "separator", "heading", "story"})
_REMOVABLE_ARTIFACT_TYPES = frozenset({"header", "footer", "noise"})
_CONFIDENCE_VALUES = frozenset({"high", "medium", "low"})
CleanupReportPayload = dict[str, object]
OperationStatePayload = dict[str, object]
SourcePagePayload = dict[str, object]
ValidatedWindowPayload = dict[str, object]


# PUBLIC API


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
    @brief      Run strict exact-source AI cleanup for one project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  cancel_requested Optional cancellation callback.
    @param[in]  additional_cleanup_instructions Optional operator cleanup rules.
    @return     Persisted cleanup report payload.
    @exception  FileNotFoundError Raised when extracted text is missing.
    @exception  ValueError Raised for invalid input, response, or model budget.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-14
    @version    1.0.0
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
    prompt_shell = _render_cleanup_user_prompt([], "cleanup-window-0000", language_hint, script_hint, instructions)
    budget_metadata = _build_budget_metadata(ai_profile_payload, system_prompt, prompt_shell)
    windows = _build_windows(pages, budget_metadata)
    model_settings = _build_model_settings(ai_profile_payload, budget_metadata)
    model_settings_history = _update_model_settings_history(existing_state if resume_compatible else {}, model_settings)
    completed_windows = _restored_completed_windows(checkpoint, windows) if resume_compatible else []
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
        "Starting AI cleanup profile_id=%s pages=%d windows=%d resume_window=%d",
        profile_id,
        len(pages),
        len(windows),
        len(completed_windows) + 1,
    )
    _write_state(
        state_path,
        "running",
        len(completed_windows),
        len(windows),
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
        len(windows),
        "Resuming AI-assisted cleanup..." if completed_windows else "AI-assisted cleanup in progress...",
        token_usage,
    )
    try:
        for zero_index in range(len(completed_windows), len(windows)):
            raise_if_cancelled(cancel_requested)
            window = windows[zero_index]
            window_number = zero_index + 1
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
                    "window_total": len(windows),
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
            completed_windows.append(validated)
            token_usage = token_usage_service.merge_token_usage(token_usage, response_result.get("usage"))
            _write_state(
                state_path,
                "running",
                window_number,
                len(windows),
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
                len(windows),
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
            windows,
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
            windows,
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
    cleaned_text = _format_cleaned_text("".join(str(block["text_block"]) for block in preserved_blocks))
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
    normalized_whitespace_character_count = sum(
        int(item.get("normalized_whitespace_character_count", 0)) for item in completed_windows
    )
    whitespace_gap_count = sum(int(item.get("whitespace_gap_count", 0)) for item in completed_windows)
    removal_decision_count = sum(int(item.get("removal_decision_count", 0)) for item in completed_windows)
    warnings = [
        str(detail.get("message", "")).strip() for detail in warning_details if str(detail.get("message", "")).strip()
    ]
    report: CleanupReportPayload = {
        "detected_language": detected_language,
        "warnings": warnings,
        "warning_details": warning_details,
        "paragraph_count": len(paragraphs),
        "removed_line_count": removal_decision_count,
        "removed_character_count": removed_character_count,
        "normalized_whitespace_character_count": normalized_whitespace_character_count,
        "whitespace_gap_count": whitespace_gap_count,
        "detected_chapter_count": cleanup_text_analysis_service.count_detected_chapters(paragraphs),
        "page_break_repair_count": int(cleanup_metadata.get("page_break_repair_count", 0)),
        "weak_boundary_count": int(cleanup_metadata.get("weak_boundary_count", 0)),
        "cleanup_mode": "ai_assisted",
        "ai_profile_id": profile_id,
        "model_settings": model_settings,
        "model_settings_history": model_settings_history,
        "ai_log_relative_path": log_relative_path,
        "window_count": len(windows),
        "validated_window_decisions": completed_windows,
        "source_page_count": len(pages),
        "preserved_block_count": len(preserved_blocks),
        "removal_decision_count": removal_decision_count,
        "token_usage": token_usage,
        "budget_metadata": budget_metadata,
        "additional_cleanup_instructions": instructions,
        "additional_cleanup_instructions_fingerprint": instructions_fingerprint,
    }
    write_json_atomic(report_path, report)
    completed_state = _write_state(
        state_path,
        "completed",
        len(windows),
        len(windows),
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
        len(windows),
        len(windows),
        "AI-assisted cleanup completed; human review is required.",
        token_usage,
    )
    _LOGGER.info(
        "Completed AI cleanup windows=%d preserved_blocks=%d removed_characters=%d",
        len(windows),
        len(preserved_blocks),
        removed_character_count,
    )
    return report


@trace_function(_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Load one optional cleanup operation-state payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted cleanup state or `None`.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-14
    @version    1.0.0
    """
    return load_operation_state_payload(project_root, "cleanup", config.CLEANUP_STATE_FILE_NAME)


# LOCAL HELPERS


def _canonicalize_source_text(text: str) -> str:
    """
    @brief      Handle canonicalize source text.
    @version    1.0.0
    """
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def _build_source_pages(canonical_text: str) -> list[SourcePagePayload]:
    """
    @brief      Handle build source pages.
    @version    1.0.0
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
    @brief      Render one canonical cleanup-window prompt.
    @version    1.0.0
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
    @brief      Wrap one concatenated canonical source window in stable markers.
    @version    1.0.0
    """
    return f"<<< SOURCE WINDOW START >>>\n{_window_source_text(pages)}<<< SOURCE WINDOW END >>>"


def _window_source_text(pages: list[SourcePagePayload]) -> str:
    """
    @brief      Concatenate ordered source units without provider-visible identities.
    @version    1.0.0
    """
    return "".join(str(page["text"]) for page in pages)


def _build_response_schema() -> dict[str, object]:
    """
    @brief      Build the strict canonical-window response schema.
    @return     Provider structured-output schema for AI Cleanup blocks.
    @exception  None.
    @version    1.0.0
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
    @brief      Validate blocks globally against one canonical source window.
    @param[in]  response_payload Provider JSON object.
    @param[in]  pages Ordered source pages or safe source segments.
    @param[in]  expected_window_id Requested cleanup-window identifier.
    @return     Preserved blocks, removals, normalization evidence, and warnings.
    @exception  ValueError Raised when the response violates the cleanup contract.
    @version    1.0.0
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
                "remove": confidence == "high" and artifact_type in _REMOVABLE_ARTIFACT_TYPES,
            }
        )

    source_text = _window_source_text(pages)
    preserved_blocks: list[dict[str, object]] = []
    preserved_spans: list[tuple[int, int]] = []
    removed_ranges: list[dict[str, object]] = []
    normalized_whitespace_ranges: list[dict[str, object]] = []
    all_removal_decisions: list[dict[str, object]] = []
    pending_removals: list[dict[str, object]] = []
    cursor = 0
    for block in normalized_blocks:
        if bool(block["remove"]):
            pending_removals.append(block)
            all_removal_decisions.append(block)
            continue
        exact_text = str(block["text_block"])
        match_index = source_text.find(exact_text, cursor)
        if match_index < 0:
            raise ValueError("Preserved text is not an exact source slice or leaves an unexplained source gap.")
        if match_index > cursor:
            gap_text = source_text[cursor:match_index]
            if gap_text.isspace():
                normalized_whitespace_ranges.append(
                    {
                        "source_window_start": cursor,
                        "source_window_end": match_index,
                        "text": gap_text,
                        "reason": "whitespace_only_gap",
                    }
                )
            elif pending_removals:
                removed_ranges.append(_removed_range(cursor, match_index, gap_text, pending_removals))
            else:
                raise ValueError(
                    "AI cleanup response leaves an unexplained source gap or violates exact source slice order."
                )
        preserved_blocks.append({key: value for key, value in block.items() if key != "remove"})
        preserved_spans.append((match_index, match_index + len(exact_text)))
        cursor = match_index + len(exact_text)
        pending_removals = []

    if cursor < len(source_text):
        gap_text = source_text[cursor:]
        if gap_text.isspace():
            normalized_whitespace_ranges.append(
                {
                    "source_window_start": cursor,
                    "source_window_end": len(source_text),
                    "text": gap_text,
                    "reason": "whitespace_only_gap",
                }
            )
        else:
            gap_decisions = pending_removals if preserved_blocks else all_removal_decisions
            if not gap_decisions:
                raise ValueError(
                    "AI cleanup response leaves an unexplained source gap or violates exact source slice order."
                )
            removed_ranges.append(_removed_range(cursor, len(source_text), gap_text, gap_decisions))

    warning_details: list[dict[str, object]] = []
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
    normalized_whitespace_character_count = sum(len(str(item["text"])) for item in normalized_whitespace_ranges)
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
    return {
        "preserved_blocks": preserved_blocks,
        "preserved_text": "".join(str(item["text_block"]) for item in preserved_blocks),
        "removed_ranges": removed_ranges,
        "normalized_whitespace_ranges": normalized_whitespace_ranges,
        "removed_character_count": removed_character_count,
        "normalized_whitespace_character_count": normalized_whitespace_character_count,
        "whitespace_gap_count": len(normalized_whitespace_ranges),
        "removal_decision_count": len(all_removal_decisions),
        "warning_details": warning_details,
        "response_block_count": len(normalized_blocks),
    }


def _removed_range(
    start: int,
    end: int,
    text: str,
    decisions: list[dict[str, object]],
) -> dict[str, object]:
    """
    @brief      Describe one removed range in canonical window coordinates.
    @version    1.0.0
    """
    return {
        "source_window_start": start,
        "source_window_end": end,
        "text": text,
        "decisions": [
            {
                "text_block_id": item["text_block_id"],
                "artifact_type": item["artifact_type"],
                "confidence": item["confidence"],
                "advisory_text_block": item["text_block"],
            }
            for item in decisions
        ],
    }


def _repeated_classification_warnings(
    preserved_blocks: list[dict[str, object]],
    removed_ranges: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Handle repeated classification warnings.
    @version    1.0.0
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
    @brief      Handle build cleanup budget metadata.
    @version    1.0.0
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
    @brief      Handle build cleanup windows.
    @version    1.0.0
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
    @brief      Handle window budget estimate.
    @version    1.0.0
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
    @brief      Handle window estimate fits.
    @version    1.0.0
    """
    return estimate["estimated_output_tokens"] <= int(budget.get("max_output_tokens", 0)) and estimate[
        "estimated_context_tokens"
    ] <= int(budget.get("context_window", 0))


def _split_page_at_boundary(page: SourcePagePayload) -> list[SourcePagePayload]:
    """
    @brief      Handle split page at boundary.
    @version    1.0.0
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
    @brief      Handle renumber source pages.
    @version    1.0.0
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
    @brief      Handle cleanup checkpoint is compatible.
    @version    1.0.0
    """
    return (
        checkpoint.get("contract_fingerprint") == _CONTRACT_FINGERPRINT
        and checkpoint.get("input_fingerprint") == input_fingerprint
        and checkpoint.get("additional_cleanup_instructions_fingerprint") == instructions_fingerprint
        and isinstance(checkpoint.get("completed_windows"), list)
    )


def _restored_completed_windows(
    checkpoint: dict[str, object],
    windows: list[dict[str, object]],
) -> list[ValidatedWindowPayload]:
    """
    @brief      Handle restored completed windows.
    @version    1.0.0
    """
    restored: list[ValidatedWindowPayload] = []
    items = checkpoint.get("completed_windows", [])
    if not isinstance(items, list):
        return restored
    for zero_index, item in enumerate(items):
        if zero_index >= len(windows) or not isinstance(item, dict):
            break
        expected_id = f"cleanup-window-{zero_index + 1:04d}"
        expected_fingerprint = _fingerprint(_window_source_text(list(windows[zero_index]["pages"])))
        if item.get("window_id") != expected_id or item.get("source_window_fingerprint") != expected_fingerprint:
            break
        if not isinstance(item.get("preserved_blocks"), list):
            break
        restored.append(dict(item))
    return restored


def _build_model_settings(profile: dict[str, object], budget: dict[str, object]) -> dict[str, object]:
    """
    @brief      Handle build model settings.
    @version    1.0.0
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
    @brief      Handle update model settings history.
    @version    1.0.0
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
    @brief      Handle write state.
    @version    1.0.0
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
    windows: list[dict[str, object]],
    token_usage: dict[str, object],
    budget_metadata: dict[str, object],
    model_settings: dict[str, object],
    model_settings_history: list[dict[str, object]],
) -> None:
    """
    @brief      Handle write checkpoint state.
    @version    1.0.0
    """
    _write_state(
        state_path,
        status,
        len(completed_windows),
        len(windows),
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
    @brief      Handle combined warning details.
    @version    1.0.0
    """
    return [
        dict(detail)
        for window in completed_windows
        for detail in list(window.get("warning_details", []))
        if isinstance(detail, dict)
    ]


def _restored_token_usage(existing_state: dict[str, object]) -> dict[str, object]:
    """
    @brief      Handle restored token usage.
    @version    1.0.0
    """
    usage = _state_metadata(existing_state).get("token_usage")
    return dict(usage) if isinstance(usage, dict) else token_usage_service.empty_token_usage()


def _state_metadata(state: dict[str, object]) -> dict[str, object]:
    """
    @brief      Handle state metadata.
    @version    1.0.0
    """
    metadata = state.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _validate_request(manifest: dict[str, object], profile: dict[str, object]) -> None:
    """
    @brief      Handle validate request.
    @version    1.0.0
    """
    if not isinstance(manifest.get("source_document"), dict):
        raise ValueError("No imported source is available for AI-assisted cleanup.")
    if any(not str(profile.get(field, "")).strip() for field in ("id", "model_name", "base_url")):
        raise ValueError("AI-assisted cleanup requires a valid enabled AI profile.")


def _normalize_instructions(value: object) -> str:
    """
    @brief      Handle normalize instructions.
    @version    1.0.0
    """
    return _canonicalize_source_text(str(value or "")).strip()


def _format_cleaned_text(text: str) -> str:
    """
    @brief      Handle format cleaned text.
    @version    1.0.0
    """
    normalized = _canonicalize_source_text(text).replace("\f", "")
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", normalized)
    return normalized.strip() + "\n"


def _estimate_text_tokens(text: str) -> int:
    """
    @brief      Handle estimate text tokens.
    @version    1.0.0
    """
    return max(1, math.ceil(len(str(text).encode("utf-8")) / 4))


def _fingerprint(text: str) -> str:
    """
    @brief      Handle fingerprint.
    @version    1.0.0
    """
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _build_ai_log_path(project_root: Path, started_at: str) -> Path:
    """
    @brief      Handle build ai log path.
    @version    1.0.0
    """
    token = re.sub(r"[^0-9A-Za-z]+", "", started_at)[:24] or "cleanup"
    return project_root / config.ai_transaction_log_file_name("cleanup", token)


# END OF FILE
