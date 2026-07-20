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
    load_optional_json_artifact,
    raise_if_cancelled,
)
from audiomancer.services.operation_runtime_service import emit_progress_update as _emit_progress
from audiomancer.services.persistence_service import write_json_atomic, write_text_atomic
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

_LOGGER = get_component_logger("ai_cleanup")
_PAGE_BREAK = "\f"
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
    decisions = report_payload.get("decisions")
    if not isinstance(decisions, dict):
        return default_spacing_categories()
    try:
        return sorted(_normalize_spacing_categories(decisions.get("selected_spacing_categories", [])))
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
    if report_payload.get("status") != "completed" or report_payload.get("mode") != "ai_assisted":
        return False
    decisions = report_payload.get("decisions")
    if not isinstance(decisions, dict):
        return False
    items = decisions.get("items")
    if not isinstance(items, list) or not items:
        return False
    try:
        _normalize_spacing_categories(decisions.get("selected_spacing_categories", []))
        _validate_decision_items(items)
    except (TypeError, ValueError):
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
    document_path = build_operation_output_path(root, "cleanup", config.CLEANUP_DOCUMENT_FILE_NAME)
    document = load_cleanup_document(root)
    if not spacing_selection_available(document):
        raise ValueError("Compatible completed AI Cleanup decisions are unavailable for spacing reapplication.")
    source_path = root / config.EXTRACTED_TEXT_FILE_NAME
    if not source_path.is_file():
        raise FileNotFoundError(f"Extracted text is missing: {source_path}")
    source_text = _canonicalize_source_text(source_path.read_text(encoding="utf-8"))
    if document.get("source_fingerprint") != _source_fingerprint(source_text):
        raise ValueError("AI Cleanup source changed; reset cleanup before applying spacing.")
    decisions = document.get("decisions")
    assert isinstance(decisions, dict)
    raw_decisions = decisions.get("items", [])
    cleaned_text = _render_document(
        source_text,
        raw_decisions,
        spacing_categories,
        require_complete=True,
    )
    if not cleaned_text.strip():
        raise ValueError("The selected AI Cleanup spacing policy removed all usable text.")

    output_path = build_operation_output_path(root, "cleanup", config.CLEANED_TEXT_FILE_NAME)
    write_text_atomic(output_path, cleaned_text)
    updated_decisions = dict(decisions)
    updated_decisions["selected_spacing_categories"] = sorted(spacing_categories)
    document["decisions"] = updated_decisions
    write_json_atomic(document_path, document)
    _LOGGER.info(
        "Applied AI cleanup spacing categories=%s",
        ",".join(sorted(spacing_categories)) or "none",
    )
    return document


@trace_function(_LOGGER)
def clean_text(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
    additional_cleanup_instructions: str | None = None,
) -> CleanupReportPayload:
    """Run or continue AI-assisted cleanup using only ``cleanup.json``."""
    root = Path(project_root)
    _validate_request(manifest, ai_profile_payload)
    profile_id = str(ai_profile_payload["id"]).strip()
    extracted_path = root / config.EXTRACTED_TEXT_FILE_NAME
    if not extracted_path.is_file():
        raise FileNotFoundError(f"Extracted text is missing: {extracted_path}")
    input_text = _canonicalize_source_text(extracted_path.read_bytes().decode("utf-8"))
    if not input_text.strip():
        raise ValueError("Extracted text does not contain any content to clean.")

    document_path = build_operation_output_path(root, "cleanup", config.CLEANUP_DOCUMENT_FILE_NAME)
    output_path = build_operation_output_path(root, "cleanup", config.CLEANED_TEXT_FILE_NAME)
    source_fingerprint = _source_fingerprint(input_text)
    existing_document = load_cleanup_document(root)
    if existing_document is None:
        instructions = _normalize_instructions(additional_cleanup_instructions)
        items: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []
        token_usage = token_usage_service.empty_token_usage()
        document = _build_cleanup_document(
            "running",
            source_fingerprint,
            instructions,
            token_usage,
            warnings,
            items,
            default_spacing_categories(),
        )
        processed_offset = 0
    else:
        if existing_document["status"] == "completed":
            raise ValueError("AI Cleanup is already completed; reset cleanup before starting again.")
        if existing_document["status"] not in {"running", "failed", "cancelled"}:
            raise ValueError("AI Cleanup cannot continue from the persisted status.")
        if existing_document["source_fingerprint"] != source_fingerprint:
            raise ValueError("AI Cleanup source changed; reset cleanup before continuing.")
        document = existing_document
        instructions = str(document["instructions"])
        decisions = document["decisions"]
        assert isinstance(decisions, dict)
        items = [dict(item) for item in decisions["items"] if isinstance(item, dict)]
        warnings = [dict(item) for item in document["warnings"] if isinstance(item, dict)]
        token_usage = token_usage_service.coerce_token_usage(document["token_usage"])
        processed_offset = _validate_decision_items(items, source_length=len(input_text))
        document["status"] = "running"

    prompt_template_service.validate_required_prompts([_SYSTEM_PROMPT_NAME, _USER_PROMPT_NAME])
    system_prompt = prompt_template_service.render_prompt(_SYSTEM_PROMPT_NAME, {})
    language_hint = cleanup_text_analysis_service.detect_language(input_text) or "unknown"
    script_hint = cleanup_text_analysis_service.classify_text_script(input_text)
    pages = _build_source_pages(input_text)
    prompt_shell = _render_cleanup_user_prompt([], "cleanup-window-0000", language_hint, script_hint, instructions)
    budget_metadata = _build_budget_metadata(ai_profile_payload, system_prompt, prompt_shell)
    remaining_pages = _source_pages_after_offset(pages, processed_offset)
    remaining_windows = _build_windows(remaining_pages, budget_metadata)
    total_characters = len(input_text)
    log_path = _build_ai_log_path(root, _utc_now_iso())
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        write_text_atomic(log_path, "")

    document["status"] = "running"
    document["token_usage"] = token_usage
    document["warnings"] = warnings
    decisions = document["decisions"]
    assert isinstance(decisions, dict)
    decisions["items"] = items
    write_json_atomic(document_path, document)
    project_workspace_service.sync_manifest_operation_summary(
        root,
        "cleanup",
        document,
        current_stage="text_cleanup_ready",
    )
    _emit_progress(
        progress_callback,
        processed_offset,
        total_characters,
        "Resuming AI-assisted cleanup..." if processed_offset else "AI-assisted cleanup in progress...",
        token_usage,
    )
    _LOGGER.info(
        "Starting AI cleanup profile_id=%s pages=%d windows=%d source_offset=%d",
        profile_id,
        len(pages),
        len(remaining_windows),
        processed_offset,
    )

    try:
        for window_number, window in enumerate(remaining_windows, start=1):
            raise_if_cancelled(cancel_requested)
            window_id = f"cleanup-window-{window_number:04d}"
            window_pages = list(window["pages"])
            user_prompt = _render_cleanup_user_prompt(
                window_pages,
                window_id,
                language_hint,
                script_hint,
                instructions,
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
                    "window_total": len(remaining_windows),
                    "window_id": window_id,
                },
                cancel_requested=cancel_requested,
                response_schema=_build_response_schema(),
                response_schema_name="text_cleanup_blocks",
            )
            payload = response_result.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("AI cleanup response must be one JSON object.")
            validated = _validate_response(payload, window_pages, window_id)
            if not window_pages:
                raise ValueError("AI cleanup produced an empty source window.")
            window_start = int(window_pages[0]["source_start"])
            window_end = int(window_pages[-1]["source_end"])
            if window_start != processed_offset:
                raise ValueError("AI Cleanup checkpoint is not a continuous source prefix.")
            window_items = _window_to_document_items(validated, window_start)
            if (
                _validate_decision_items(window_items, source_length=window_end, start_offset=window_start)
                != window_end
            ):
                raise ValueError("AI Cleanup window decisions do not cover the complete source window.")
            items.extend(window_items)
            processed_offset = window_end
            warnings.extend(_compact_window_warnings(validated, window_pages, window_start))
            token_usage = token_usage_service.merge_token_usage(token_usage, response_result.get("usage"))
            document["status"] = "running"
            document["token_usage"] = token_usage
            document["warnings"] = warnings
            decisions = document["decisions"]
            assert isinstance(decisions, dict)
            decisions["items"] = items
            write_json_atomic(document_path, document)
            _emit_progress(
                progress_callback,
                processed_offset,
                total_characters,
                "AI-assisted cleanup in progress...",
                token_usage,
            )

        _validate_decision_items(items, source_length=total_characters, require_complete=True)
        spacing_categories = selected_spacing_categories(document)
        cleaned_text = _render_document(
            input_text,
            items,
            spacing_categories,
            require_complete=True,
        )
        if not cleaned_text.strip():
            raise ValueError("AI-assisted cleanup removed all usable text.")
        write_text_atomic(output_path, cleaned_text)
        if not any(item.get("kind") == "human_review_required" for item in warnings):
            warnings.append({"kind": "human_review_required"})
        document["status"] = "completed"
        document["token_usage"] = token_usage
        document["warnings"] = warnings
        write_json_atomic(document_path, document)
    except OperationCancelledError:
        document["status"] = "cancelled"
        document["token_usage"] = token_usage
        document["warnings"] = warnings
        write_json_atomic(document_path, document)
        project_workspace_service.sync_manifest_operation_summary(
            root,
            "cleanup",
            document,
            current_stage="text_cleanup_ready",
        )
        raise
    except Exception:
        _LOGGER.exception("AI cleanup failed at source offset %d", processed_offset)
        document["status"] = "failed"
        document["token_usage"] = token_usage
        document["warnings"] = warnings
        write_json_atomic(document_path, document)
        project_workspace_service.sync_manifest_operation_summary(
            root,
            "cleanup",
            document,
            current_stage="text_cleanup_ready",
        )
        raise

    detected_language = cleanup_text_analysis_service.detect_language(cleaned_text)
    project_workspace_service.sync_manifest_operation_summary(
        root,
        "cleanup",
        document,
        current_stage="text_chunking_ready",
        extra_fields={"original_language": detected_language},
    )
    _emit_progress(
        progress_callback,
        total_characters,
        total_characters,
        "AI-assisted cleanup completed; human review is required.",
        token_usage,
    )
    _LOGGER.info(
        "Completed AI cleanup source_characters=%d decisions=%d warnings=%d",
        total_characters,
        len(items),
        len(warnings),
    )
    return document


@trace_function(_LOGGER)
def load_cleanup_document(project_root: str | Path) -> CleanupReportPayload | None:
    """Load and strictly validate the authoritative AI Cleanup document."""
    document_path = Path(project_root) / config.CLEANUP_DOCUMENT_FILE_NAME
    payload = load_optional_json_artifact(document_path)
    if payload is None:
        return None
    return _validate_cleanup_document(payload)


@trace_function(_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """Compatibility API returning the authoritative AI Cleanup document."""
    return load_cleanup_document(project_root)


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


def _source_fingerprint(text: str) -> str:
    """Return the canonical SHA-256 source identity stored in ``cleanup.json``."""
    return f"sha256:{_fingerprint(_canonicalize_source_text(text))}"


def _build_cleanup_document(
    status: str,
    source_fingerprint: str,
    instructions: str,
    token_usage: dict[str, object],
    warnings: list[dict[str, object]],
    items: list[dict[str, object]],
    spacing_categories: object,
) -> CleanupReportPayload:
    """Build the exact authoritative AI Cleanup document shape."""
    return {
        "status": status,
        "mode": "ai_assisted",
        "source_fingerprint": source_fingerprint,
        "instructions": instructions,
        "token_usage": token_usage_service.coerce_token_usage(token_usage),
        "warnings": [dict(item) for item in warnings],
        "decisions": {
            "selected_spacing_categories": sorted(_normalize_spacing_categories(spacing_categories)),
            "items": [dict(item) for item in items],
        },
    }


def _validate_cleanup_document(payload: object) -> CleanupReportPayload:
    """Validate ``cleanup.json`` without accepting legacy AI metadata."""
    required_fields = {
        "status",
        "mode",
        "source_fingerprint",
        "instructions",
        "token_usage",
        "warnings",
        "decisions",
    }
    if not isinstance(payload, dict) or set(payload) != required_fields:
        raise ValueError("cleanup.json contains unsupported fields or is missing required fields.")
    status = payload.get("status")
    if status not in {"running", "failed", "cancelled", "completed"}:
        raise ValueError("cleanup.json contains an unsupported status.")
    if payload.get("mode") != "ai_assisted":
        raise ValueError("cleanup.json is not an AI-assisted Cleanup document.")
    source_fingerprint = payload.get("source_fingerprint")
    if not isinstance(source_fingerprint, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", source_fingerprint) is None:
        raise ValueError("cleanup.json contains an invalid source fingerprint.")
    instructions = payload.get("instructions")
    if not isinstance(instructions, str):
        raise ValueError("cleanup.json instructions must be a string.")

    raw_usage = payload.get("token_usage")
    if not isinstance(raw_usage, dict) or set(raw_usage) != {
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "usage_available",
    }:
        raise ValueError("cleanup.json contains invalid token usage.")
    token_usage = token_usage_service.coerce_token_usage(raw_usage)
    if token_usage != raw_usage:
        raise ValueError("cleanup.json token usage is not canonical.")

    raw_warnings = payload.get("warnings")
    if not isinstance(raw_warnings, list):
        raise ValueError("cleanup.json warnings must be an array.")
    warnings: list[dict[str, object]] = []
    for raw_warning in raw_warnings:
        if not isinstance(raw_warning, dict) or set(raw_warning) not in ({"kind"}, {"kind", "start", "end"}):
            raise ValueError("cleanup.json contains an invalid warning entry.")
        kind = raw_warning.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("cleanup.json warning kinds must be non-empty strings.")
        normalized_warning: dict[str, object] = {"kind": kind.strip()}
        if "start" in raw_warning:
            start = raw_warning.get("start")
            end = raw_warning.get("end")
            if type(start) is not int or type(end) is not int or start < 0 or end <= start:
                raise ValueError("cleanup.json warning ranges are invalid.")
            normalized_warning.update({"start": start, "end": end})
        warnings.append(normalized_warning)

    raw_decisions = payload.get("decisions")
    if not isinstance(raw_decisions, dict) or set(raw_decisions) != {
        "selected_spacing_categories",
        "items",
    }:
        raise ValueError("cleanup.json decisions are invalid.")
    raw_categories = raw_decisions.get("selected_spacing_categories")
    if not isinstance(raw_categories, list):
        raise ValueError("cleanup.json spacing categories must be an array.")
    spacing_categories = sorted(_normalize_spacing_categories(raw_categories))
    raw_items = raw_decisions.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("cleanup.json decision items must be an array.")
    _validate_decision_items(raw_items)
    return _build_cleanup_document(
        str(status),
        source_fingerprint,
        instructions,
        token_usage,
        warnings,
        [dict(item) for item in raw_items if isinstance(item, dict)],
        spacing_categories,
    )


def _validate_decision_items(
    items: object,
    *,
    source_length: int | None = None,
    require_complete: bool = False,
    start_offset: int = 0,
) -> int:
    """Validate ordered, non-overlapping decisions covering one continuous prefix."""
    if not isinstance(items, list):
        raise ValueError("AI Cleanup decision items must be an array.")
    if type(start_offset) is not int or start_offset < 0:
        raise ValueError("AI Cleanup decision start offset is invalid.")
    if source_length is not None and (type(source_length) is not int or source_length < start_offset):
        raise ValueError("AI Cleanup source length is invalid.")
    cursor = start_offset
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Every AI Cleanup decision item must be an object.")
        start = item.get("start")
        end = item.get("end")
        kind = item.get("kind")
        if type(start) is not int or type(end) is not int or start != cursor or end <= start:
            raise ValueError("AI Cleanup decision items must cover a continuous ordered prefix.")
        if source_length is not None and end > source_length:
            raise ValueError("AI Cleanup decision item exceeds the source length.")
        if kind in _NON_DISPLAY_ARTIFACT_TYPES:
            if set(item) != {"start", "end", "kind", "confidence"} or item.get("confidence") not in _CONFIDENCE_VALUES:
                raise ValueError("AI Cleanup artifact decisions are invalid.")
        elif kind == "story":
            if set(item) not in ({"start", "end", "kind"}, {"start", "end", "kind", "output_text"}):
                raise ValueError("AI Cleanup Story decisions are invalid.")
            if "output_text" in item and (not isinstance(item.get("output_text"), str) or not item["output_text"]):
                raise ValueError("AI Cleanup modified Story output must be non-empty text.")
        elif kind in {"whitespace", "preserved_source_gap"}:
            if set(item) != {"start", "end", "kind"}:
                raise ValueError("AI Cleanup source-gap decisions are invalid.")
        else:
            raise ValueError("AI Cleanup decision contains an unsupported kind.")
        cursor = end
    if require_complete and (source_length is None or cursor != source_length):
        raise ValueError("AI Cleanup decisions do not cover the complete source.")
    return cursor


def _render_document(
    source_text: str,
    items: object,
    selected_categories: object,
    *,
    require_complete: bool,
) -> str:
    """Reconstruct clean text deterministically from source offsets and decisions."""
    canonical_source = _canonicalize_source_text(source_text)
    assert isinstance(items, list)
    _validate_decision_items(
        items,
        source_length=len(canonical_source),
        require_complete=require_complete,
    )
    spacing_categories = _normalize_spacing_categories(selected_categories)
    output_fragments: list[str] = []
    for item in items:
        assert isinstance(item, dict)
        kind = str(item["kind"])
        start = int(item["start"])
        end = int(item["end"])
        if kind == "story":
            output_fragments.append(str(item.get("output_text", canonical_source[start:end])))
        elif kind == "preserved_source_gap":
            output_fragments.append(canonical_source[start:end])
        elif kind in spacing_categories:
            output_fragments.append("\n\n")
    return "".join(output_fragments)


def _window_to_document_items(
    validated_window: ValidatedWindowPayload,
    window_start: int,
) -> list[dict[str, object]]:
    """Compact one validated runtime window into absolute source decisions."""
    items: list[dict[str, object]] = []
    for raw_range in validated_window.get("removed_ranges", []):
        if not isinstance(raw_range, dict):
            continue
        decision = raw_range.get("decision")
        if not isinstance(decision, dict):
            raise ValueError("AI Cleanup artifact decision is missing.")
        items.append(
            {
                "start": window_start + int(raw_range["source_window_start"]),
                "end": window_start + int(raw_range["source_window_end"]),
                "kind": str(decision["artifact_type"]),
                "confidence": str(decision["confidence"]),
            }
        )
    for raw_block in validated_window.get("preserved_blocks", []):
        if not isinstance(raw_block, dict):
            continue
        item: dict[str, object] = {
            "start": window_start + int(raw_block["source_window_start"]),
            "end": window_start + int(raw_block["source_window_end"]),
            "kind": "story",
        }
        if raw_block.get("match_mode") == "anchored_modified":
            item["output_text"] = str(raw_block["text_block"])
        items.append(item)
    for raw_gap in validated_window.get("restored_whitespace_ranges", []):
        if isinstance(raw_gap, dict):
            items.append(
                {
                    "start": window_start + int(raw_gap["source_window_start"]),
                    "end": window_start + int(raw_gap["source_window_end"]),
                    "kind": "whitespace",
                }
            )
    for raw_gap in validated_window.get("preserved_source_gaps", []):
        if isinstance(raw_gap, dict):
            items.append(
                {
                    "start": window_start + int(raw_gap["source_window_start"]),
                    "end": window_start + int(raw_gap["source_window_end"]),
                    "kind": "preserved_source_gap",
                }
            )
    items.sort(key=lambda item: (int(item["start"]), int(item["end"])))
    return items


def _compact_window_warnings(
    validated_window: ValidatedWindowPayload,
    window_pages: list[SourcePagePayload],
    window_start: int,
) -> list[dict[str, object]]:
    """Keep only functional warning kind and optional absolute source range."""
    warnings: list[dict[str, object]] = []
    for raw_warning in validated_window.get("warning_details", []):
        if not isinstance(raw_warning, dict):
            continue
        kind = str(raw_warning.get("kind", "")).strip()
        if not kind:
            continue
        warning: dict[str, object] = {"kind": kind}
        local_start = raw_warning.get("source_window_start")
        local_end = raw_warning.get("source_window_end")
        if type(local_start) is int and type(local_end) is int and local_end > local_start:
            warning.update({"start": window_start + local_start, "end": window_start + local_end})
        elif kind == "entire_page_removed":
            page_index = raw_warning.get("source_page_index")
            matching_page = next(
                (page for page in window_pages if page.get("source_page_index") == page_index),
                None,
            )
            if matching_page is not None:
                start = int(matching_page["source_start"])
                end = int(matching_page["source_end"])
                if end > start:
                    warning.update({"start": start, "end": end})
        warnings.append(warning)
    return warnings


def _build_source_pages(canonical_text: str) -> list[SourcePagePayload]:
    """Build runtime page units while preserving absolute source offsets."""
    canonical = _canonicalize_source_text(canonical_text)
    pages: list[SourcePagePayload] = []
    source_start = 0
    for page_break in re.finditer(_PAGE_BREAK, canonical):
        source_end = page_break.end()
        pages.append(
            {
                "source_page_index": len(pages) + 1,
                "source_kind": "page",
                "text": canonical[source_start:source_end],
                "source_start": source_start,
                "source_end": source_end,
            }
        )
        source_start = source_end
    if source_start < len(canonical) or not pages:
        pages.append(
            {
                "source_page_index": len(pages) + 1,
                "source_kind": "page",
                "text": canonical[source_start:],
                "source_start": source_start,
                "source_end": len(canonical),
            }
        )
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
            match_index == cursor or source_text[cursor:match_index].isspace() or preserve_internal_gap
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
    """Split an oversized source unit without changing absolute offsets."""
    text = str(page["text"])
    boundaries = [index + 1 for index, character in enumerate(text) if character == "\n" and index + 1 < len(text)]
    if not boundaries:
        return [page]
    boundary = min(boundaries, key=lambda value: abs(value - len(text) // 2))
    source_start = int(page["source_start"])
    split_offset = source_start + boundary
    return [
        {
            **page,
            "source_kind": "segment",
            "text": text[:boundary],
            "source_start": source_start,
            "source_end": split_offset,
        },
        {
            **page,
            "source_kind": "segment",
            "text": text[boundary:],
            "source_start": split_offset,
            "source_end": int(page["source_end"]),
        },
    ]


def _renumber_source_pages(pages: list[SourcePagePayload]) -> None:
    """Renumber runtime source units while retaining their absolute offsets."""
    for source_index, page in enumerate(pages, start=1):
        page["source_page_index"] = source_index


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
