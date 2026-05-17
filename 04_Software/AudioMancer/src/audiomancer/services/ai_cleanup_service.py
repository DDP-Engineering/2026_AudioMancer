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
@brief AI-assisted text cleanup helpers for AudioMancer.
@details Consumes canonical extracted text, classifies cleanup units through
         one configured AI profile, persists cleanup artifacts, and supports
         resumable window-based progress plus AI transaction logs.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.9.1
"""

# IMPORTS

import hashlib
import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import (
    ai_budget_service,
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
from audiomancer.services.operation_runtime_service import (
    emit_progress_update as _emit_progress,
)
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

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
    r'([:;.!?\u2026]["ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â»ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â\']?)\s+-\s+(?=[A-ZÃƒÆ’Ã¢â‚¬Å¾ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã†â€™Ãƒâ€¦Ã‚Â½ÃƒÆ’Ã‹â€ Ãƒâ€¹Ã…â€œÃƒÆ’Ã‹â€ Ãƒâ€¦Ã‚Â¡])'
)  # noqa: E501
# @brief Dialogue formatter rule that inserts line breaks after attributions and pauses.
_DIALOGUE_BREAK_AFTER_ATTRIBUTION_PATTERN = re.compile(
    r"([,:])\s+-\s+(?=[A-ZÃƒÆ’Ã¢â‚¬Å¾ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã†â€™Ãƒâ€¦Ã‚Â½ÃƒÆ’Ã‹â€ Ãƒâ€¹Ã…â€œÃƒÆ’Ã‹â€ Ãƒâ€¦Ã‚Â¡])"
)  # noqa: E501
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
# @brief New AI cleanup artifact types accepted from the prompt contract.
_ARTIFACT_TYPES = {
    "story",
    "chapter_heading",
    "dialogue",
    "epigraph",
    "header",
    "footer",
    "page_number",
    "separator",
    "copyright",
    "ocr_noise",
    "noise",
    "unknown",
}
# @brief Artifact types treated as removable when the action is omitted.
_REMOVABLE_ARTIFACT_TYPES = {
    "header",
    "footer",
    "page_number",
    "separator",
    "copyright",
    "ocr_noise",
    "noise",
}
# @brief Confidence values accepted from the AI cleanup prompt contract.
_CONFIDENCE_VALUES = {"high", "medium", "low"}
# @brief Removal-ratio threshold above which one cleanup window is flagged as suspicious.
_MAX_REMOVAL_RATIO_WARNING = 0.55
# @brief Tail length inspected for late-window alternating label drift.
_SUSPICIOUS_ALTERNATION_WINDOW = 8
# @brief Persisted cleanup report payload type used by the UI and manifest sync.
CleanupReportPayload = dict[str, object]
# @brief Persisted AI cleanup operation-state payload type.
OperationStatePayload = dict[str, object]
TokenUsagePayload = dict[str, object]
BudgetMetadataPayload = dict[str, int]


# PUBLIC API


@trace_function(_AI_CLEANUP_LOGGER)
def clean_text(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
    additional_cleanup_instructions: str | None = None,
) -> CleanupReportPayload:
    """
    @brief      Run AI-assisted cleanup for one active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  additional_cleanup_instructions Optional operator-supplied cleanup rules.
    @return     Cleanup report payload for the persisted AI cleanup artifacts.
    @exception  FileNotFoundError Raised when the extracted input is missing.
    @exception  ValueError Raised on missing profile data or unusable cleanup output.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.6.2
    """
    resolved_project_root = Path(project_root)
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        raise ValueError("No imported source is available for AI-assisted cleanup.")
    profile_id = str(ai_profile_payload.get("id", "")).strip()
    model_name = str(ai_profile_payload.get("model_name", "")).strip()
    base_url = str(ai_profile_payload.get("base_url", "")).strip()
    if not profile_id or not model_name or not base_url:
        raise ValueError("AI-assisted cleanup requires a valid enabled AI profile.")

    extracted_path = resolved_project_root / config.EXTRACTED_TEXT_FILE_NAME
    if not extracted_path.is_file():
        raise FileNotFoundError(f"Extracted text is missing: {extracted_path}")

    input_text = extracted_path.read_text(encoding="utf-8")
    if not input_text.strip():
        raise ValueError("Extracted text does not contain any content to clean.")

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

    prompt_template_service.validate_required_prompts(["text_cleanup_system", "text_cleanup_user"])
    units = _build_cleanup_units(input_text)
    if not units:
        raise ValueError("Extracted text does not contain any cleanup units.")

    language_hint = _language_hint_for_text(input_text)
    script_hint = cleanup_text_analysis_service.classify_text_script(input_text)
    system_prompt = prompt_template_service.render_prompt("text_cleanup_system", {})
    existing_state = load_operation_state_file(state_path) or {}
    additional_cleanup_instructions = _resolve_additional_cleanup_instructions(
        additional_cleanup_instructions,
        existing_state,
    )
    additional_cleanup_instructions_fingerprint = _compute_prompt_fingerprint(additional_cleanup_instructions)
    budget_metadata = _build_budget_metadata(
        ai_profile_payload,
        language_hint,
        script_hint,
        system_prompt,
        additional_cleanup_instructions,
    )
    input_fingerprint = _compute_input_fingerprint(input_text)
    windows = _build_windows(units, budget_metadata)
    total_windows = len(windows)
    model_settings = _build_model_settings(ai_profile_payload, budget_metadata)
    classifications, log_relative_path, resume_is_compatible = _restore_resume_state(
        existing_state,
        input_fingerprint,
        additional_cleanup_instructions_fingerprint,
    )
    started_at = str(existing_state.get("started_at") or _utc_now_iso()) if resume_is_compatible else _utc_now_iso()
    start_window_index = _first_incomplete_window_index(windows, classifications)
    warning_details = _restore_warning_details(existing_state) if resume_is_compatible else []
    token_usage = _restore_token_usage(existing_state) if classifications else token_usage_service.empty_token_usage()
    model_settings_history = _updated_model_settings_history(
        existing_state if resume_is_compatible else {},
        model_settings,
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
        warning_details,
        token_usage,
        budget_metadata,
        model_settings,
        model_settings_history,
        additional_cleanup_instructions,
    )
    _emit_progress(
        progress_callback,
        progress_current=start_window_index,
        progress_total=total_windows,
        message="Resuming AI-assisted cleanup..." if start_window_index > 0 else "AI-assisted cleanup in progress...",
        token_usage=token_usage,
    )

    last_progress_current = start_window_index
    try:
        for window_index in range(start_window_index, total_windows):
            raise_if_cancelled(cancel_requested)
            window_units = units[windows[window_index]["start_index"] : windows[window_index]["end_index"] + 1]
            user_prompt = _render_cleanup_user_prompt(
                _cleanup_prompt_variables(
                    units,
                    windows[window_index]["start_index"],
                    windows[window_index]["end_index"],
                    language_hint,
                    script_hint,
                    additional_cleanup_instructions,
                )
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
                    "window_index": window_index + 1,
                    "window_total": total_windows,
                },
                cancel_requested=cancel_requested,
            )
            response_payload = dict(response_result.get("payload", {}))
            token_usage = token_usage_service.merge_token_usage(
                token_usage,
                response_result.get("usage"),
            )
            _apply_response_labels(
                classifications,
                response_payload,
                window_units,
                warning_details,
                window_index + 1,
            )
            last_progress_current = window_index + 1
            _write_running_state(
                state_path,
                resolved_project_root,
                input_snapshot_path,
                output_path,
                started_at,
                last_progress_current,
                total_windows,
                profile_id,
                log_relative_path,
                input_fingerprint,
                classifications,
                warning_details,
                token_usage,
                budget_metadata,
                model_settings,
                model_settings_history,
                additional_cleanup_instructions,
            )
            _emit_progress(
                progress_callback,
                progress_current=last_progress_current,
                progress_total=total_windows,
                message="AI-assisted cleanup in progress...",
                token_usage=token_usage,
            )
    except OperationCancelledError:
        _write_running_state(
            state_path,
            resolved_project_root,
            input_snapshot_path,
            output_path,
            started_at,
            last_progress_current,
            total_windows,
            profile_id,
            log_relative_path,
            input_fingerprint,
            classifications,
            warning_details,
            token_usage,
            budget_metadata,
            model_settings,
            model_settings_history,
            additional_cleanup_instructions,
            status="cancelled",
            completed_at=_utc_now_iso(),
        )
        raise

    kept_units = [unit for unit in units if classifications.get(unit["unit_id"], "unknown") in _KEEP_LABELS]
    cleaned_paragraphs = [
        _normalize_unit_paragraph_text(str(unit["text"])) for unit in kept_units if str(unit["text"]).strip()
    ]
    cleaned_paragraphs = [paragraph for paragraph in cleaned_paragraphs if paragraph.strip()]
    cleaned_paragraphs = _merge_adjacent_continuation_paragraphs(cleaned_paragraphs)
    if not cleaned_paragraphs:
        raise ValueError("AI-assisted cleanup removed all usable text.")

    cleaned_text = "\n\n".join(cleaned_paragraphs).strip() + "\n"
    output_path.write_text(cleaned_text, encoding="utf-8")
    metadata_payload = cleanup_metadata_service.write_minimal_cleanup_metadata(
        resolved_project_root,
        cleaned_text,
        "ai_assisted",
    )
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
        "cleaned_text_metadata_relative_path": relative_to_project(
            resolved_project_root,
            cleanup_metadata_service.cleanup_metadata_path(resolved_project_root),
        ),
        "cleaned_at": _utc_now_iso(),
        "detected_language": detected_language,
        "warnings": warnings,
        "warning_details": warning_details,
        "paragraph_count": len(cleaned_paragraphs),
        "removed_line_count": max(0, len(units) - len(kept_units)),
        "detected_chapter_count": chapter_count,
        "page_break_repair_count": int(metadata_payload.get("page_break_repair_count", 0)),
        "weak_boundary_count": int(metadata_payload.get("weak_boundary_count", 0)),
        "cleanup_mode": "ai_assisted",
        "ai_profile_id": profile_id,
        "model_settings": model_settings,
        "model_settings_history": model_settings_history,
        "ai_log_relative_path": log_relative_path,
        "window_count": total_windows,
        "token_usage": token_usage,
        "budget_metadata": budget_metadata,
        "additional_cleanup_instructions": additional_cleanup_instructions,
        "additional_cleanup_instructions_fingerprint": additional_cleanup_instructions_fingerprint,
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
        cleanup_metadata_service.cleanup_metadata_path(resolved_project_root),
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
        token_usage=token_usage,
        budget_metadata=budget_metadata,
        model_settings=model_settings,
        model_settings_history=model_settings_history,
        additional_cleanup_instructions=additional_cleanup_instructions,
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
        progress_current=total_windows,
        progress_total=total_windows,
        message="AI-assisted cleanup completed.",
        token_usage=token_usage,
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
    @version    0.2.0
    """
    return load_operation_state_payload(project_root, "cleanup", config.CLEANUP_STATE_FILE_NAME)


# LOCAL HELPERS


def _build_cleanup_units(text: str) -> list[dict[str, object]]:
    """
    @brief      Build the cleanup units.
    @param[in]  text Value for `text`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
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
    """
    @brief      Normalize the unit paragraph text.
    @param[in]  unit_text Text value for `unit_text`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
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
    budget_metadata: BudgetMetadataPayload,
) -> list[dict[str, int]]:
    """
    @brief      Build context-budgeted AI cleanup request windows.
    @param[in]  units Value for `units`.
    @param[in]  budget_metadata Context-budget metadata for the selected profile.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.3.0
    """
    text_budget = int(budget_metadata["text_budget_tokens"])
    max_window_units = int(budget_metadata["max_window_units"])
    windows: list[dict[str, int]] = []
    start_index = 0
    while start_index < len(units):
        current_budget = 0
        current_unit_count = 0
        end_index = start_index - 1
        while end_index + 1 < len(units):
            next_tokens = _estimate_text_tokens(_build_units_block(units, end_index + 1, end_index + 1))
            if next_tokens > text_budget:
                raise ValueError("One AI cleanup unit exceeds the configured usable input budget.")
            if max_window_units > 0 and current_unit_count >= max_window_units and end_index >= start_index:
                break
            if current_budget + next_tokens > text_budget and end_index >= start_index:
                break
            current_budget += next_tokens
            end_index += 1
            current_unit_count += 1
        windows.append({"start_index": start_index, "end_index": end_index})
        start_index = end_index + 1
    return windows


def _build_budget_metadata(
    ai_profile_payload: dict[str, object],
    language_hint: str,
    script_hint: str,
    system_prompt: str,
    additional_cleanup_instructions: str,
) -> BudgetMetadataPayload:
    """
    @brief      Build context-window budget metadata for AI cleanup.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  language_hint Detected source-language hint.
    @param[in]  script_hint Detected dominant-script hint.
    @param[in]  system_prompt Rendered system prompt.
    @param[in]  additional_cleanup_instructions Optional operator-supplied cleanup rules.
    @return     Context-budget metadata used for request-window construction.
    @exception  ValueError Raised when context and output settings leave too little input room.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.3.0
    """
    prompt_user_shell = _render_cleanup_user_prompt(
        {
            "source_language_hint": language_hint,
            "dominant_script_hint": script_hint,
            "units_block": "(none)",
            "unit_count": 0,
            "additional_cleanup_instructions": additional_cleanup_instructions,
        }
    )
    budget_metadata = ai_budget_service.context_budget_metadata(
        ai_profile_payload,
        f"{system_prompt}\n\n{prompt_user_shell}",
        config.DEFAULT_AI_CLEANUP_MIN_SAFETY_MARGIN_TOKENS,
        config.DEFAULT_AI_CLEANUP_SAFETY_MARGIN_CONTEXT_FRACTION,
        config.DEFAULT_AI_CLEANUP_TEXT_CONTEXT_FRACTION,
        config.DEFAULT_AI_CLEANUP_MIN_TEXT_BUDGET_TOKENS,
        "AI-assisted cleanup cannot run because the selected AI profile context window "
        "and max output tokens leave too little room for cleanup input",
        online_text_context_fraction=config.DEFAULT_ONLINE_AI_TEXT_CONTEXT_FRACTION,
    )
    max_window_units = (
        0
        if ai_budget_service.uses_online_text_budget(ai_profile_payload)
        else config.DEFAULT_AI_CLEANUP_MAX_WINDOW_UNITS
    )
    return {**budget_metadata, "max_window_units": max_window_units}


def _build_model_settings(
    ai_profile_payload: dict[str, object],
    budget_metadata: BudgetMetadataPayload,
) -> dict[str, object]:
    """
    @brief      Build the concrete AI model settings stored with cleanup state.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  budget_metadata Context-budget metadata derived from the profile.
    @return     JSON-ready model settings payload.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.1.0
    """
    return {
        "backend_kind": str(ai_profile_payload.get("backend_kind", "")).strip(),
        "base_url": str(ai_profile_payload.get("base_url", "")).strip(),
        "model_name": str(ai_profile_payload.get("model_name", "")).strip(),
        "temperature": ai_profile_payload.get("temperature"),
        "context_window": int(budget_metadata.get("context_window", 0)),
        "max_output_tokens": int(budget_metadata.get("max_output_tokens", 0)),
    }


def _updated_model_settings_history(
    existing_state: dict[str, object],
    model_settings: dict[str, object],
    profile_id: str,
) -> list[dict[str, object]]:
    """
    @brief      Return model-settings history with the current settings appended once.
    @param[in]  existing_state Existing cleanup operation state.
    @param[in]  model_settings Current selected model settings.
    @param[in]  profile_id Current selected profile identifier.
    @return     Ordered model-settings history.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.1.0
    """
    metadata = existing_state.get("metadata", {})
    existing_history = []
    if isinstance(metadata, dict):
        raw_history = metadata.get("model_settings_history", [])
        if isinstance(raw_history, list):
            existing_history = [dict(item) for item in raw_history if isinstance(item, dict)]
    current_item = {"profile_id": profile_id, **dict(model_settings)}
    if not existing_history or existing_history[-1] != current_item:
        existing_history.append(current_item)
    return existing_history


def _restore_resume_state(
    existing_state: dict[str, object],
    input_fingerprint: str,
    additional_cleanup_instructions_fingerprint: str,
) -> tuple[dict[str, str], str | None, bool]:
    """
    @brief      Restore the resume state.
    @param[in]  existing_state Value for `existing_state`.
    @param[in]  input_fingerprint Value for `input_fingerprint`.
    @param[in]  additional_cleanup_instructions_fingerprint Operator instruction fingerprint.
    @return     Stored classifications, existing log path, and compatibility flag.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.4.0
    """
    resume_checkpoint = dict(existing_state.get("resume_checkpoint") or {})
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    log_relative_path = metadata.get("ai_log_relative_path")
    stored_instruction_fingerprint = str(
        metadata.get("additional_cleanup_instructions_fingerprint")
        or resume_checkpoint.get("additional_cleanup_instructions_fingerprint")
        or _compute_prompt_fingerprint("")
    )
    if (
        existing_state.get("mode") != "ai_assisted"
        or str(resume_checkpoint.get("input_fingerprint", "")) != input_fingerprint
        or stored_instruction_fingerprint != additional_cleanup_instructions_fingerprint
    ):
        return {}, None, False
    stored_classifications = resume_checkpoint.get("classifications", {})
    if not isinstance(stored_classifications, dict):
        return {}, log_relative_path if isinstance(log_relative_path, str) else None, True
    return (
        {str(unit_id): str(label) for unit_id, label in stored_classifications.items() if str(unit_id).strip()},
        log_relative_path if isinstance(log_relative_path, str) else None,
        True,
    )


def _first_incomplete_window_index(
    windows: list[dict[str, int]],
    classifications: dict[str, str],
) -> int:
    """
    @brief      Find the first request window containing an unclassified unit.
    @param[in]  windows Current context-budgeted cleanup windows.
    @param[in]  classifications Stored classifications by unit id.
    @return     Zero-based window index.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.1.0
    """
    if not classifications:
        return 0
    for window_index, window_payload in enumerate(windows):
        start_index = int(window_payload["start_index"])
        end_index = int(window_payload["end_index"])
        for unit_index in range(start_index, end_index + 1):
            if f"unit-{unit_index + 1:04d}" not in classifications:
                return window_index
    return len(windows)


def _restore_warning_details(existing_state: dict[str, object]) -> list[dict[str, object]]:
    """
    @brief      Restore the warning details.
    @param[in]  existing_state Value for `existing_state`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return []
    raw_items = metadata.get("warning_details", [])
    if not isinstance(raw_items, list):
        return []
    return [dict(item) for item in raw_items if isinstance(item, dict)]


def _restore_token_usage(existing_state: dict[str, object]) -> TokenUsagePayload:
    """
    @brief      Restore the token usage.
    @param[in]  existing_state Value for `existing_state`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return token_usage_service.empty_token_usage()
    return token_usage_service.restore_token_usage(metadata.get("token_usage"))


def _render_cleanup_user_prompt(variables: dict[str, object]) -> str:
    """
    @brief      Render the AI cleanup user prompt with backward-compatible variables.
    @param[in]  variables Preferred prompt variables.
    @return     Rendered AI cleanup user prompt.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.3.0
    """
    template = prompt_template_service.load_prompt("text_cleanup_user")
    placeholder_names = set(re.findall(r"{([A-Za-z_][A-Za-z0-9_]*)}", template))
    rendered_prompt = prompt_template_service.render_prompt(
        "text_cleanup_user",
        {key: value for key, value in variables.items() if key in placeholder_names},
    )
    additional_cleanup_instructions = _normalized_additional_cleanup_instructions(
        variables.get("additional_cleanup_instructions")
    )
    if additional_cleanup_instructions and "additional_cleanup_instructions" not in placeholder_names:
        rendered_prompt = _append_additional_cleanup_instructions(
            rendered_prompt,
            additional_cleanup_instructions,
        )
    return rendered_prompt


def _cleanup_prompt_variables(
    units: list[dict[str, object]],
    start_index: int,
    end_index: int,
    language_hint: str,
    script_hint: str,
    additional_cleanup_instructions: str,
) -> dict[str, object]:
    """
    @brief      Build AI cleanup prompt variables with language and neighbor context.
    @param[in]  units Ordered cleanup units.
    @param[in]  start_index First window unit index.
    @param[in]  end_index Last window unit index.
    @param[in]  language_hint Detected source-language hint.
    @param[in]  script_hint Detected dominant-script hint.
    @param[in]  additional_cleanup_instructions Optional operator-supplied cleanup rules.
    @return     Prompt variable mapping.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.2.0
    """
    window_units = units[start_index : end_index + 1]
    return {
        "source_language_hint": language_hint,
        "dominant_script_hint": script_hint,
        "units_block": _build_units_block(units, start_index, end_index),
        "unit_count": len(window_units),
        "additional_cleanup_instructions": additional_cleanup_instructions,
    }


def _resolve_additional_cleanup_instructions(
    additional_cleanup_instructions: str | None,
    existing_state: dict[str, object],
) -> str:
    """
    @brief      Resolve the operator cleanup rules for a new or resumed AI cleanup run.
    @param[in]  additional_cleanup_instructions New operator instructions or None when resuming.
    @param[in]  existing_state Existing cleanup operation state.
    @return     Normalized operator cleanup instructions.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.2
    """
    if additional_cleanup_instructions is not None:
        return _normalized_additional_cleanup_instructions(additional_cleanup_instructions)
    if existing_state.get("mode") != "ai_assisted" or str(existing_state.get("status", "")) not in {
        "cancelled",
        "running",
        "failed",
    }:
        return ""
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return ""
    return _normalized_additional_cleanup_instructions(metadata.get("additional_cleanup_instructions"))


def _normalized_additional_cleanup_instructions(value: object) -> str:
    """
    @brief      Normalize optional operator cleanup rules for prompt insertion and state storage.
    @param[in]  value Candidate instruction text.
    @return     Trimmed instruction text.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    if value is None:
        return ""
    return str(value).strip()


def _append_additional_cleanup_instructions(prompt_text: str, additional_cleanup_instructions: str) -> str:
    """
    @brief      Append operator cleanup rules to one rendered AI cleanup prompt.
    @param[in]  prompt_text Rendered prompt template text.
    @param[in]  additional_cleanup_instructions Normalized operator rules.
    @return     Prompt text with an additional-rules section.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    if not additional_cleanup_instructions:
        return prompt_text
    return f"{prompt_text.rstrip()}\n\nAdditional operator cleanup instructions:\n{additional_cleanup_instructions}\n"


def _build_units_block(units: list[dict[str, object]], start_index: int, end_index: int) -> str:
    """
    @brief      Build the units block with neighboring context.
    @param[in]  units Ordered cleanup units.
    @param[in]  start_index First window unit index.
    @param[in]  end_index Last window unit index.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    blocks: list[str] = []
    for unit_index in range(start_index, end_index + 1):
        unit = units[unit_index]
        previous_text = "" if unit_index <= 0 else str(units[unit_index - 1]["text"])
        next_text = "" if unit_index + 1 >= len(units) else str(units[unit_index + 1]["text"])
        blocks.append(
            "\n".join(
                [
                    f"unit_id: {unit['unit_id']}",
                    f"previous_unit_text: {_prompt_context_text(previous_text)}",
                    f"unit_text: {unit['text']}",
                    f"next_unit_text: {_prompt_context_text(next_text)}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _prompt_context_text(text: str) -> str:
    """
    @brief      Trim one neighbor context text fragment for prompt inclusion.
    @param[in]  text Neighbor unit text.
    @return     Trimmed prompt context text.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    normalized = re.sub(r"\s+", " ", str(text)).strip()
    if len(normalized) <= 240:
        return normalized or "(none)"
    return normalized[:237].rstrip() + "..."


def _language_hint_for_text(text: str) -> str:
    """
    @brief      Build one source-language hint for the AI cleanup prompt.
    @param[in]  text Extracted text.
    @return     Detected language code or `unknown`.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return _detect_language(text) or "unknown"


def _compose_paragraph_text(lines: list[tuple[str, bool]]) -> str:
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
    first_line, _joined_with_previous = lines[0]
    paragraph_text = first_line.strip()
    for current_line, join_with_previous in lines[1:]:
        separator = " " if join_with_previous else "\n"
        paragraph_text += separator + current_line.strip()
    return paragraph_text.strip()


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


def _merge_adjacent_continuation_paragraphs(paragraphs: list[str]) -> list[str]:
    """
    @brief      Merge the adjacent continuation paragraphs.
    @param[in]  paragraphs Value for `paragraphs`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    merged_paragraphs: list[str] = []
    for paragraph in paragraphs:
        normalized_paragraph = paragraph.strip()
        if not normalized_paragraph:
            continue
        if merged_paragraphs and _should_continue_after_paragraph(
            merged_paragraphs[-1],
            normalized_paragraph,
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
    """
    @brief      Determine whether continue after paragraph.
    @param[in]  current_paragraph Value for `current_paragraph`.
    @param[in]  next_paragraph Value for `next_paragraph`.
    @return     True when the helper condition is satisfied.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    current_lines = [
        line.strip() for line in current_paragraph.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()
    ]
    next_lines = [
        line.strip() for line in next_paragraph.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()
    ]
    if not current_lines or not next_lines:
        return False
    return _should_continue_paragraph(current_lines[-1], next_lines[0])


def _should_continue_paragraph(current_last_line: str, next_line: str | None) -> bool:
    """
    @brief      Determine whether continue paragraph.
    @param[in]  current_last_line Value for `current_last_line`.
    @param[in]  next_line Value for `next_line`.
    @return     True when the helper condition is satisfied.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
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
    return current_text.endswith("-") or not _PARAGRAPH_TERMINAL_PATTERN.search(current_text)


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
    @version      0.2.0
    """
    results = response_payload.get("results", [])
    if not isinstance(results, list):
        raise ValueError("AI cleanup response does not contain a valid results list.")
    window_unit_map = {str(unit["unit_id"]): str(unit["text"]) for unit in window_units}
    window_classifications: dict[str, dict[str, str]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        unit_id = str(item.get("unit_id", "")).strip()
        if not unit_id:
            continue
        if unit_id not in window_unit_map:
            _append_warning_detail(
                warning_details,
                kind="invalid_result_unit",
                message=(
                    f"AI cleanup returned an unknown unit id '{unit_id}' in window {window_index}; "
                    "the result item was ignored."
                ),
                window_index=window_index,
                unit_id=unit_id,
            )
            continue
        window_classifications[unit_id] = _classification_from_result_item(item)
    normalized_labels = _normalize_window_labels(
        window_units,
        window_classifications,
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
    token_usage: TokenUsagePayload,
    budget_metadata: BudgetMetadataPayload,
    model_settings: dict[str, object],
    model_settings_history: list[dict[str, object]],
    additional_cleanup_instructions: str,
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
    @param[in]  profile_id Profile identifier.
    @param[in]  log_relative_path Path for `log_relative_path`.
    @param[in]  input_fingerprint Value for `input_fingerprint`.
    @param[in]  classifications Value for `classifications`.
    @param[in]  warning_details Value for `warning_details`.
    @param[in]  token_usage Value for `token_usage`.
    @param[in]  budget_metadata Context-budget metadata.
    @param[in]  model_settings Current selected model settings.
    @param[in]  model_settings_history Ordered selected-model settings history.
    @param[in]  additional_cleanup_instructions Optional operator-supplied cleanup rules.
    @param[in]  status Operation status token.
    @param[in]  completed_at Optional completion timestamp for terminal incomplete states.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.5.0
    """
    warning_messages = _warning_messages_from_details(warning_details)
    running_state = _build_operation_state(
        project_root,
        input_snapshot_path,
        output_path,
        report_path=None,
        metadata_path=None,
        status=status,
        progress_current=progress_current,
        progress_total=progress_total,
        started_at=started_at,
        completed_at=completed_at,
        warnings=warning_messages,
        profile_id=profile_id,
        log_relative_path=log_relative_path,
        input_fingerprint=input_fingerprint,
        classifications=classifications,
        warning_details=warning_details,
        detected_language=None,
        paragraph_count=None,
        chapter_count=None,
        token_usage=token_usage,
        budget_metadata=budget_metadata,
        model_settings=model_settings,
        model_settings_history=model_settings_history,
        additional_cleanup_instructions=additional_cleanup_instructions,
    )
    state_path.write_text(
        json.dumps(running_state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    project_workspace_service.sync_manifest_operation_summary(project_root, "cleanup", running_state)


def _warning_messages_from_details(warning_details: list[dict[str, object]]) -> list[str]:
    """
    @brief      Build compact warning messages from persisted warning details.
    @param[in]  warning_details Detailed AI cleanup warning records.
    @return     Ordered warning message list.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-17
    @version    0.1.0
    """
    return [str(item.get("message", "")).strip() for item in warning_details if str(item.get("message", "")).strip()]


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
    profile_id: str,
    log_relative_path: str,
    input_fingerprint: str,
    classifications: dict[str, str] | None,
    warning_details: list[dict[str, object]],
    detected_language: str | None,
    paragraph_count: int | None,
    chapter_count: int | None,
    token_usage: TokenUsagePayload,
    budget_metadata: BudgetMetadataPayload,
    model_settings: dict[str, object],
    model_settings_history: list[dict[str, object]],
    additional_cleanup_instructions: str,
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
    @param[in]  profile_id Profile identifier.
    @param[in]  log_relative_path Path for `log_relative_path`.
    @param[in]  input_fingerprint Value for `input_fingerprint`.
    @param[in]  classifications Value for `classifications`.
    @param[in]  warning_details Value for `warning_details`.
    @param[in]  detected_language Value for `detected_language`.
    @param[in]  paragraph_count Value for `paragraph_count`.
    @param[in]  chapter_count Value for `chapter_count`.
    @param[in]  token_usage Value for `token_usage`.
    @param[in]  budget_metadata Context-budget metadata.
    @param[in]  model_settings Current selected model settings.
    @param[in]  model_settings_history Ordered selected-model settings history.
    @param[in]  additional_cleanup_instructions Optional operator-supplied cleanup rules.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.4.0
    """
    additional_cleanup_instructions_fingerprint = _compute_prompt_fingerprint(additional_cleanup_instructions)
    artifact_paths: list[str] = [log_relative_path]
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
        mode="ai_assisted",
        started_at=started_at,
        completed_at=completed_at,
        warning_count=len(warnings),
        metadata={
            "warnings": list(warnings),
            "warning_details": [dict(item) for item in warning_details],
            "detected_language": detected_language,
            "paragraph_count": paragraph_count,
            "detected_chapter_count": chapter_count,
            "ai_profile_id": profile_id,
            "model_settings": dict(model_settings),
            "model_settings_history": [dict(item) for item in model_settings_history],
            "ai_log_relative_path": log_relative_path,
            "token_usage": token_usage_service.coerce_token_usage(token_usage),
            "budget_metadata": dict(budget_metadata),
            "additional_cleanup_instructions": additional_cleanup_instructions,
            "additional_cleanup_instructions_fingerprint": additional_cleanup_instructions_fingerprint,
        },
        resume_checkpoint={
            "completed_window_count": progress_current,
            "total_window_count": progress_total,
            "input_fingerprint": input_fingerprint,
            "classifications": None if classifications is None else dict(classifications),
            "model_settings": dict(model_settings),
            "additional_cleanup_instructions_fingerprint": additional_cleanup_instructions_fingerprint,
        }
        if status != "completed"
        else None,
    )


def _build_ai_log_path(project_root: Path, started_at: str) -> Path:
    """
    @brief      Build the ai log path.
    @param[in]  project_root Active project root folder.
    @param[in]  started_at Value for `started_at`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    started_fragment = started_at.replace(":", "").replace("+00:00", "").replace("T", "_")
    return build_operation_output_path(
        project_root,
        "cleanup",
        config.ai_transaction_log_file_name("cleanup", started_fragment),
    )


def _estimate_text_tokens(text: str) -> int:
    """
    @brief      Execute the estimate text tokens helper.
    @param[in]  text Value for `text`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return ai_budget_service.estimate_text_tokens(text)


def _compute_input_fingerprint(text: str) -> str:
    """
    @brief      Execute the compute input fingerprint helper.
    @param[in]  text Value for `text`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compute_prompt_fingerprint(prompt_text: str) -> str:
    """
    @brief      Compute a stable fingerprint for operator-supplied prompt rules.
    @param[in]  prompt_text Operator prompt-rule text.
    @return     SHA-256 fingerprint for the prompt-rule text.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


def _build_cleanup_warnings(
    detected_language: str | None,
    chapter_count: int,
    warning_details: list[dict[str, object]],
) -> list[str]:
    """
    @brief      Build the cleanup warnings.
    @param[in]  detected_language Value for `detected_language`.
    @param[in]  chapter_count Value for `chapter_count`.
    @param[in]  warning_details Value for `warning_details`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    warnings: list[str] = []
    if detected_language is None:
        warnings.append("Language detection did not produce a stable value.")
    if chapter_count == 0:
        warnings.append(
            "No explicit chapter or scene headings were detected; chunking will rely on sequential paragraph order."
        )
    warnings.extend(
        str(item.get("message", "")).strip() for item in warning_details if str(item.get("message", "")).strip()
    )
    return warnings


def _count_detected_chapters(paragraph_texts: list[str]) -> int:
    """
    @brief      Count the detected chapters.
    @param[in]  paragraph_texts Value for `paragraph_texts`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return cleanup_text_analysis_service.count_detected_chapters(paragraph_texts)


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


def _split_cleanup_block(block: str) -> list[str]:
    """
    @brief      Execute the split cleanup block helper.
    @param[in]  block Value for `block`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
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
    window_classifications: dict[str, dict[str, str]],
    warning_details: list[dict[str, object]],
    window_index: int,
) -> dict[str, str]:
    """
    @brief      Normalize the window labels.
    @param[in]  window_units Value for `window_units`.
    @param[in]  window_classifications AI classification payloads by unit id.
    @param[in]  warning_details Value for `warning_details`.
    @param[in]  window_index Current window index.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    normalized_labels: dict[str, str] = {}
    removal_count = 0
    for unit in window_units:
        unit_id = str(unit["unit_id"])
        unit_text = str(unit["text"])
        classification = window_classifications.get(unit_id, _unknown_classification())
        corrected_label = _normalize_label_for_unit(
            unit_text,
            classification,
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


def _classification_from_result_item(item: dict[str, object]) -> dict[str, str]:
    """
    @brief      Normalize one AI cleanup result item into the internal classification shape.
    @param[in]  item Raw AI result item.
    @return     Classification with label, confidence, artifact type, action, and reason.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.2.0
    """
    artifact_type = str(item.get("artifact_type", "")).strip().lower()
    if artifact_type not in _ARTIFACT_TYPES:
        artifact_type = ""
    action = str(item.get("action", "")).strip().lower()
    if action not in {"keep", "remove"}:
        action = ""
    confidence = str(item.get("confidence", "")).strip().lower()
    if confidence not in _CONFIDENCE_VALUES:
        confidence = "medium"
    label = _label_from_artifact_action(artifact_type, action)
    return {
        "label": label,
        "confidence": confidence,
        "artifact_type": artifact_type or label,
        "action": action or ("remove" if label in _REMOVABLE_LABELS else "keep"),
        "reason": str(item.get("reason", "")).strip(),
    }


def _label_from_artifact_action(artifact_type: str, action: str) -> str:
    """
    @brief      Derive the internal cleanup label from the prompt schema.
    @param[in]  artifact_type Normalized artifact type.
    @param[in]  action Normalized keep/remove action.
    @return     Internal cleanup label.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.2.0
    """
    if action == "keep":
        return "story" if artifact_type not in {"unknown", ""} else "unknown"
    if action == "remove":
        if artifact_type == "ocr_noise":
            return "noise"
        if artifact_type in _REMOVABLE_LABELS:
            return artifact_type
        return "unknown"
    return "unknown"


def _unknown_classification() -> dict[str, str]:
    """
    @brief      Return the default preserve classification.
    @return     Unknown classification payload.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return {
        "label": "unknown",
        "confidence": "medium",
        "artifact_type": "unknown",
        "action": "keep",
        "reason": "",
    }


def _normalize_label_for_unit(
    unit_text: str,
    classification: dict[str, str],
    warning_details: list[dict[str, object]],
    window_index: int,
    unit_id: str,
) -> str:
    """
    @brief      Normalize the label for unit.
    @param[in]  unit_text Text value for `unit_text`.
    @param[in]  classification Normalized AI classification payload.
    @param[in]  warning_details Value for `warning_details`.
    @param[in]  window_index Current window index.
    @param[in]  unit_id Identifier for `unit_id`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    normalized_text = unit_text.strip()
    label = classification["label"]
    confidence = classification["confidence"]
    artifact_type = classification["artifact_type"]
    action = classification["action"]
    if _looks_like_page_number(normalized_text):
        if label != "page_number":
            _append_warning_detail(
                warning_details,
                kind="page_number_label_corrected",
                message=(
                    f"AI cleanup corrected one page-number classification in window {window_index} "
                    "to preserve cleanup quality."
                ),
                window_index=window_index,
                unit_id=unit_id,
                original_label=label,
                original_artifact_type=artifact_type,
                original_action=action,
                corrected_label="page_number",
                confidence=confidence,
                reason=classification.get("reason", ""),
            )
        return "page_number"
    if _looks_like_separator_line(normalized_text):
        if label != "separator":
            _append_warning_detail(
                warning_details,
                kind="separator_label_corrected",
                message=(
                    f"AI cleanup corrected one separator classification in window {window_index} "
                    "to preserve cleanup quality."
                ),
                window_index=window_index,
                unit_id=unit_id,
                original_label=label,
                original_artifact_type=artifact_type,
                original_action=action,
                corrected_label="separator",
                confidence=confidence,
                reason=classification.get("reason", ""),
            )
        return "separator"
    if action == "remove" and label == "unknown":
        _append_warning_detail(
            warning_details,
            kind="unsupported_removal_artifact_preserved",
            message=(
                f"AI cleanup preserved one unsupported removal artifact in window {window_index} for operator review."
            ),
            window_index=window_index,
            unit_id=unit_id,
            original_label=label,
            original_artifact_type=artifact_type,
            original_action=action,
            corrected_label="unknown",
            confidence=confidence,
            reason=classification.get("reason", ""),
        )
        return "unknown"
    if label in _REMOVABLE_LABELS and confidence == "low":
        _append_warning_detail(
            warning_details,
            kind="low_confidence_removal_preserved",
            message=(
                f"AI cleanup preserved one low-confidence removable label in window {window_index} for operator review."
            ),
            window_index=window_index,
            unit_id=unit_id,
            original_label=label,
            corrected_label="unknown",
            confidence=confidence,
            reason=classification.get("reason", ""),
        )
        return "unknown"
    if label == "page_number":
        _append_warning_detail(
            warning_details,
            kind="invalid_page_number_label_corrected",
            message=(
                f"AI cleanup corrected one invalid page-number label in window {window_index} "
                "and preserved the text for review."
            ),
            window_index=window_index,
            unit_id=unit_id,
            original_label=label,
            corrected_label="unknown",
            confidence=confidence,
        )
        return "unknown"
    if label == "separator":
        _append_warning_detail(
            warning_details,
            kind="invalid_separator_label_corrected",
            message=(
                f"AI cleanup corrected one invalid separator label in window {window_index} "
                "and preserved the text for review."
            ),
            window_index=window_index,
            unit_id=unit_id,
            original_label=label,
            corrected_label="unknown",
            confidence=confidence,
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
    """
    @brief      Append the suspicious window warnings.
    @param[in]  window_units Value for `window_units`.
    @param[in]  labels Value for `labels`.
    @param[in]  removal_count Value for `removal_count`.
    @param[in]  warning_details Value for `warning_details`.
    @param[in]  window_index Current window index.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
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
        for current, following in zip(
            classification_tail,
            classification_tail[1:],
            strict=False,
        )
        if current != following
    )
    if len(classification_tail) >= 6 and flip_count >= len(classification_tail) - 2:
        _append_warning_detail(
            warning_details,
            kind="suspicious_label_drift_detected",
            message=(
                f"AI cleanup detected one suspicious late-window label pattern in window {window_index}; "
                "the affected text was preserved conservatively where needed."
            ),
            window_index=window_index,
            classification_tail=classification_tail,
        )


def _build_final_output_warning_details(
    cleaned_paragraphs: list[str],
    classifications: dict[str, str],
    units: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Build the final output warning details.
    @param[in]  cleaned_paragraphs Value for `cleaned_paragraphs`.
    @param[in]  classifications Value for `classifications`.
    @param[in]  units Value for `units`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    warning_details: list[dict[str, object]] = []
    surviving_page_number_count = sum(
        1 for paragraph in cleaned_paragraphs if _looks_like_page_number(paragraph.strip())
    )
    if surviving_page_number_count > 0:
        warning_details.append(
            {
                "kind": "numeric_artifacts_remained",
                "message": (
                    f"AI cleanup left {surviving_page_number_count} page-number-like paragraph(s) "
                    "in the cleaned output; review the result before chunking."
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
                    f"AI cleanup removed {story_like_removed_count} non-trivial unit(s); "
                    "review the cleaned text if important content appears to be missing."
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
    """
    @brief      Append the warning detail.
    @param[in]  warning_details Value for `warning_details`.
    @param[in]  kind Value for `kind`.
    @param[in]  message Operator-facing message text.
    @param[in]  metadata Value for `metadata`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    for existing in warning_details:
        if (
            str(existing.get("kind", "")) == kind
            and str(existing.get("message", "")) == message
            and all(existing.get(key) == value for key, value in metadata.items())
        ):
            return
    warning_details.append({"kind": kind, "message": message, **metadata})


def _looks_like_page_number(text: str) -> bool:
    """
    @brief      Determine whether page number.
    @param[in]  text Value for `text`.
    @return     True when the helper condition is satisfied.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return bool(_PAGE_NUMBER_PATTERN.fullmatch(text.strip()))


def _looks_like_separator_line(text: str) -> bool:
    """
    @brief      Determine whether separator line.
    @param[in]  text Value for `text`.
    @return     True when the helper condition is satisfied.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized = text.strip()
    return bool(normalized) and bool(_SEPARATOR_PATTERN.fullmatch(normalized))


# END OF FILE
