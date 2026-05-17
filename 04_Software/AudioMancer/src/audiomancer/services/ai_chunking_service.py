#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_chunking_service.py
@brief AI-assisted text chunking helpers for AudioMancer.
@details Consumes canonical cleaned text, asks one configured AI profile to
         decide semantic chunk boundaries over ordered paragraphs, persists the
         canonical chunk artifacts in `20_chunking`, and maintains resumable
         window-based operation state plus AI transaction logging.
@author Eng. Dan Dumitru Pasare
@date 2026-04-11
@version 0.9.0
"""

# IMPORTS

import hashlib
import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import (
    ai_budget_service,
    deterministic_chunking_service,
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
    load_operation_state_payload,
    raise_if_cancelled,
    relative_to_project,
)
from audiomancer.services.operation_runtime_service import (
    emit_progress_update as _emit_progress,
)
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

# @brief Component logger used by the AI-assisted chunking workflow.
_AI_CHUNKING_LOGGER = get_component_logger("ai_chunking")

# @brief Canonical chunk-record payload type persisted for downstream workflow steps.
ChunkPayload = dict[str, object]

# @brief Persisted AI chunking report payload type.
ChunkingReportPayload = dict[str, object]

# @brief Persisted AI chunking operation-state payload type.
OperationStatePayload = dict[str, object]
TokenUsagePayload = dict[str, object]
BudgetMetadataPayload = dict[str, int]
ProfileRuntimeMetadataPayload = dict[str, object]


# PUBLIC API


@trace_function(_AI_CHUNKING_LOGGER)
def chunk_text(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    semantic_strategy: str,
    progress_callback=None,
    cancel_requested=None,
    additional_chunking_instructions: str | None = None,
) -> ChunkingReportPayload:
    """
    @brief      Run AI-assisted chunking for one active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  semantic_strategy Selected semantic strategy token.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  additional_chunking_instructions Optional operator-supplied chunking rules.
    @return     Chunking report payload for the persisted AI chunking artifacts.
    @exception  FileNotFoundError Raised when the cleaned input is missing.
    @exception  ValueError Raised on missing profile data or unusable cleaned text.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.6.0
    """
    resolved_project_root = Path(project_root)
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        raise ValueError("No imported source is available for AI-assisted chunking.")

    cleaned_relative_path = config.CLEANED_TEXT_FILE_NAME

    profile_id = str(ai_profile_payload.get("id", "")).strip()
    model_name = str(ai_profile_payload.get("model_name", "")).strip()
    base_url = str(ai_profile_payload.get("base_url", "")).strip()
    if not profile_id or not model_name or not base_url:
        raise ValueError("AI-assisted chunking requires a valid enabled AI profile.")

    if semantic_strategy not in config.AI_CHUNKING_STRATEGY_OPTIONS:
        raise ValueError("AI-assisted chunking requires a valid semantic strategy.")

    cleaned_path = resolved_project_root / cleaned_relative_path
    if not cleaned_path.is_file():
        raise FileNotFoundError("AI-assisted chunking requires cleaned text first.")

    input_text = cleaned_path.read_text(encoding="utf-8")
    paragraph_records = _build_paragraph_records(input_text, resolved_project_root)
    if not paragraph_records:
        raise ValueError("Cleaned text does not contain any paragraphs for AI chunking.")

    _ = source_document
    input_snapshot_path = cleaned_path

    output_path = build_operation_output_path(
        resolved_project_root,
        "chunking",
        config.CHUNK_ARTIFACT_FILE_NAME,
    )
    report_path = build_operation_output_path(
        resolved_project_root,
        "chunking",
        config.CHUNKING_REPORT_FILE_NAME,
    )
    state_path = build_operation_output_path(
        resolved_project_root,
        "chunking",
        config.CHUNKING_STATE_FILE_NAME,
    )

    prompt_template_service.validate_required_prompts(["text_chunking_system", "text_chunking_user"])
    system_prompt = prompt_template_service.render_prompt(
        "text_chunking_system",
        {"strategy": semantic_strategy},
    )
    existing_state = load_operation_state(resolved_project_root) or {}
    additional_chunking_instructions = _resolve_additional_chunking_instructions(
        additional_chunking_instructions,
        existing_state,
    )
    additional_chunking_instructions_fingerprint = _compute_prompt_fingerprint(additional_chunking_instructions)
    budget_metadata = _build_budget_metadata(
        ai_profile_payload,
        semantic_strategy,
        system_prompt,
        additional_chunking_instructions,
    )
    profile_runtime_metadata = _build_profile_runtime_metadata(ai_profile_payload)
    input_fingerprint = _compute_input_fingerprint(input_text)
    all_windows = _build_windows(paragraph_records, semantic_strategy, budget_metadata)
    if not all_windows:
        raise ValueError("Cleaned text does not contain any paragraphs for AI chunking.")

    started_at = str(existing_state.get("started_at") or _utc_now_iso())
    completed_window_count, completed_unit_count, committed_break_ids, log_relative_path = _restore_resume_state(
        existing_state,
        len(all_windows),
        input_fingerprint,
        semantic_strategy,
        additional_chunking_instructions_fingerprint,
        paragraph_records,
        all_windows,
        budget_metadata,
    )
    windows = _build_windows_from_index(paragraph_records, completed_unit_count, semantic_strategy, budget_metadata)
    total_windows = completed_window_count + len(windows)
    token_usage = (
        _restore_token_usage(existing_state) if completed_unit_count > 0 else token_usage_service.empty_token_usage()
    )
    profile_usage_history = _merge_profile_usage_history(
        _restore_profile_usage_history(existing_state),
        profile_runtime_metadata,
    )
    if completed_unit_count == 0:
        output_path.write_text("[]\n", encoding="utf-8")

    if not log_relative_path:
        log_path = _build_ai_log_path(resolved_project_root, started_at)
        log_relative_path = relative_to_project(resolved_project_root, log_path)
    else:
        log_path = resolved_project_root / log_relative_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")

    _write_running_state(
        state_path=state_path,
        project_root=resolved_project_root,
        input_snapshot_path=input_snapshot_path,
        output_path=output_path,
        report_path=None,
        started_at=started_at,
        progress_current=completed_window_count,
        progress_total=total_windows,
        warnings=[],
        paragraph_records=paragraph_records[:completed_unit_count],
        committed_break_ids=committed_break_ids,
        profile_id=profile_id,
        semantic_strategy=semantic_strategy,
        input_fingerprint=input_fingerprint,
        log_relative_path=log_relative_path,
        token_usage=token_usage,
        budget_metadata=budget_metadata,
        profile_runtime_metadata=profile_runtime_metadata,
        profile_usage_history=profile_usage_history,
        completed_unit_count=completed_unit_count,
        additional_chunking_instructions=additional_chunking_instructions,
    )
    _emit_progress(
        progress_callback,
        progress_current=completed_window_count,
        progress_total=total_windows,
        message=(
            "Resuming AI-assisted chunking..." if completed_unit_count > 0 else "AI-assisted chunking in progress..."
        ),
        token_usage=token_usage,
    )

    for relative_window_index, window_payload in enumerate(windows):
        progress_window_index = completed_window_count + relative_window_index
        raise_if_cancelled(cancel_requested)
        window_records = paragraph_records[int(window_payload["start_index"]) : int(window_payload["end_index"]) + 1]
        user_prompt = _render_chunking_user_prompt(
            {
                "strategy": semantic_strategy,
                "units_block": _build_units_block(window_records),
                "additional_chunking_instructions": additional_chunking_instructions,
            },
        )
        try:
            response_result = llm_provider_service.chat_json(
                ai_profile_payload,
                system_prompt,
                user_prompt,
                log_path=log_path,
                log_context={
                    "operation_kind": "chunking",
                    "stage_label": "ai_chunking",
                    "profile_id": profile_id,
                    "semantic_strategy": semantic_strategy,
                    "window_index": progress_window_index + 1,
                    "window_total": total_windows,
                },
                cancel_requested=cancel_requested,
            )
        except OperationCancelledError as error:
            raise OperationCancelledError(
                "AI-assisted chunking cancelled while waiting for the model response."
            ) from error
        response_payload = dict(response_result.get("payload", {}))
        token_usage = token_usage_service.merge_token_usage(
            token_usage,
            response_result.get("usage"),
        )
        committed_break_ids = _merge_committed_break_ids(
            committed_break_ids,
            _normalize_break_after_ids(response_payload, window_records),
            paragraph_records,
        )
        processed_records = paragraph_records[: int(window_payload["end_index"]) + 1]
        partial_chunks = _build_chunks_from_break_ids(
            processed_records,
            committed_break_ids,
            semantic_strategy,
        )
        _write_chunk_payload(output_path, partial_chunks)
        _write_running_state(
            state_path=state_path,
            project_root=resolved_project_root,
            input_snapshot_path=input_snapshot_path,
            output_path=output_path,
            report_path=None,
            started_at=started_at,
            progress_current=progress_window_index + 1,
            progress_total=total_windows,
            warnings=[],
            paragraph_records=processed_records,
            committed_break_ids=committed_break_ids,
            profile_id=profile_id,
            semantic_strategy=semantic_strategy,
            input_fingerprint=input_fingerprint,
            log_relative_path=log_relative_path,
            token_usage=token_usage,
            budget_metadata=budget_metadata,
            profile_runtime_metadata=profile_runtime_metadata,
            profile_usage_history=profile_usage_history,
            completed_unit_count=int(window_payload["end_index"]) + 1,
            additional_chunking_instructions=additional_chunking_instructions,
        )
        _emit_progress(
            progress_callback,
            progress_current=progress_window_index + 1,
            progress_total=total_windows,
            message="AI-assisted chunking in progress...",
            token_usage=token_usage,
        )

    chunks = _build_chunks_from_break_ids(
        paragraph_records,
        committed_break_ids,
        semantic_strategy,
    )
    _write_chunk_payload(output_path, chunks)
    chapter_count = _chapter_count_from_chunks(chunks)
    warnings = deterministic_chunking_service._build_chunking_warnings(chapter_count)
    report_payload: ChunkingReportPayload = {
        "input_relative_path": relative_to_project(resolved_project_root, input_snapshot_path),
        "chunk_artifact_relative_path": relative_to_project(resolved_project_root, output_path),
        "chunked_at": _utc_now_iso(),
        "warnings": warnings,
        "chunk_count": len(chunks),
        "detected_chapter_count": chapter_count,
        "chunking_mode": "ai_assisted",
        "ai_profile_id": profile_id,
        **profile_runtime_metadata,
        "semantic_strategy": semantic_strategy,
        "log_relative_path": log_relative_path,
        "token_usage": token_usage,
        "budget_metadata": budget_metadata,
        "profile_usage_history": profile_usage_history,
        "additional_chunking_instructions": additional_chunking_instructions,
        "additional_chunking_instructions_fingerprint": additional_chunking_instructions_fingerprint,
    }
    report_path.write_text(
        json.dumps(report_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    completed_state = _build_operation_state(
        project_root=resolved_project_root,
        input_snapshot_path=input_snapshot_path,
        output_path=output_path,
        report_path=report_path,
        status="completed",
        progress_current=total_windows,
        progress_total=total_windows,
        started_at=started_at,
        completed_at=report_payload["chunked_at"],
        warnings=warnings,
        chunks=None,
        profile_id=profile_id,
        semantic_strategy=semantic_strategy,
        log_relative_path=log_relative_path,
        resume_checkpoint=None,
        token_usage=token_usage,
        budget_metadata=budget_metadata,
        profile_runtime_metadata=profile_runtime_metadata,
        profile_usage_history=profile_usage_history,
    )
    state_path.write_text(
        json.dumps(completed_state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    project_workspace_service.sync_manifest_operation_summary(
        resolved_project_root,
        "chunking",
        completed_state,
        current_stage="translation_ready",
    )
    _emit_progress(
        progress_callback,
        progress_current=total_windows,
        progress_total=total_windows,
        message="AI-assisted chunking completed.",
        token_usage=token_usage,
    )
    return report_payload


@trace_function(_AI_CHUNKING_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Load one optional AI chunking operation-state payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted chunking operation-state payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    return load_operation_state_payload(project_root, "chunking", config.CHUNKING_STATE_FILE_NAME)


# LOCAL HELPERS


def _compute_input_fingerprint(input_text: str) -> str:
    """
    @brief      Execute the compute input fingerprint helper.
    @param[in]  input_text Text value for `input_text`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    return hashlib.sha256(input_text.encode("utf-8")).hexdigest()


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


def _build_windows(
    paragraph_records: list[dict[str, object]],
    semantic_strategy: str,
    budget_metadata: BudgetMetadataPayload,
) -> list[dict[str, int]]:
    """
    @brief      Build context-budgeted AI request windows.
    @param[in]  paragraph_records Value for `paragraph_records`.
    @param[in]  semantic_strategy Value for `semantic_strategy`.
    @param[in]  budget_metadata Context-budget metadata for the selected profile.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.4.0
    """
    _ = semantic_strategy
    text_budget = int(budget_metadata["text_budget_tokens"])
    paragraph_cap = int(budget_metadata["strategy_paragraph_cap"])
    windows: list[dict[str, int]] = []
    start_index = 0
    while start_index < len(paragraph_records):
        end_index = start_index - 1
        current_window_tokens = 0
        current_paragraph_count = 0
        while end_index + 1 < len(paragraph_records) and (
            paragraph_cap <= 0 or current_paragraph_count < paragraph_cap
        ):
            candidate_record = paragraph_records[end_index + 1]
            candidate_tokens = _estimate_text_tokens(_build_units_block([candidate_record]))
            if current_paragraph_count > 0 and current_window_tokens + candidate_tokens > text_budget:
                break
            current_window_tokens += candidate_tokens
            current_paragraph_count += 1
            end_index += 1
        windows.append(
            {
                "start_index": start_index,
                "end_index": end_index,
            }
        )
        start_index = end_index + 1
    return windows


def _build_windows_from_index(
    paragraph_records: list[dict[str, object]],
    start_index: int,
    semantic_strategy: str,
    budget_metadata: BudgetMetadataPayload,
) -> list[dict[str, int]]:
    """
    @brief      Build context-budgeted AI request windows from one absolute paragraph index.
    @param[in]  paragraph_records Value for `paragraph_records`.
    @param[in]  start_index First absolute paragraph index still needing AI processing.
    @param[in]  semantic_strategy Value for `semantic_strategy`.
    @param[in]  budget_metadata Context-budget metadata for the selected profile.
    @return     Absolute-index window payloads for the remaining text.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.1.0
    """
    resolved_start_index = max(0, min(int(start_index), len(paragraph_records)))
    if resolved_start_index >= len(paragraph_records):
        return []
    relative_windows = _build_windows(
        paragraph_records[resolved_start_index:],
        semantic_strategy,
        budget_metadata,
    )
    return [
        {
            "start_index": int(window["start_index"]) + resolved_start_index,
            "end_index": int(window["end_index"]) + resolved_start_index,
        }
        for window in relative_windows
    ]


def _build_budget_metadata(
    ai_profile_payload: dict[str, object],
    semantic_strategy: str,
    system_prompt: str,
    additional_chunking_instructions: str,
) -> BudgetMetadataPayload:
    """
    @brief      Build context-window budget metadata for AI chunking.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  semantic_strategy Selected semantic strategy token.
    @param[in]  system_prompt Rendered system prompt.
    @param[in]  additional_chunking_instructions Optional operator-supplied chunking rules.
    @return     Context-budget metadata used for request-window construction.
    @exception  ValueError Raised when context and output settings leave too little input room.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.3.0
    """
    prompt_user_shell = _render_chunking_user_prompt(
        {
            "strategy": semantic_strategy,
            "units_block": "",
            "additional_chunking_instructions": additional_chunking_instructions,
        },
    )
    budget_metadata = ai_budget_service.context_budget_metadata(
        ai_profile_payload,
        f"{system_prompt}\n\n{prompt_user_shell}",
        config.DEFAULT_AI_CHUNKING_MIN_SAFETY_MARGIN_TOKENS,
        config.DEFAULT_AI_CHUNKING_SAFETY_MARGIN_CONTEXT_FRACTION,
        config.DEFAULT_AI_CHUNKING_TEXT_CONTEXT_FRACTION,
        config.DEFAULT_AI_CHUNKING_MIN_TEXT_BUDGET_TOKENS,
        "AI-assisted chunking cannot run because the selected AI profile context window "
        "and max output tokens leave too little room for chunking input",
        online_text_context_fraction=config.DEFAULT_ONLINE_AI_TEXT_CONTEXT_FRACTION,
    )
    if ai_budget_service.uses_online_text_budget(ai_profile_payload):
        strategy_paragraph_cap = 0
    else:
        strategy_paragraph_cap = config.AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY.get(
            semantic_strategy,
            config.AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY[config.DEFAULT_AI_CHUNKING_STRATEGY],
        )
    return {
        **budget_metadata,
        "strategy_paragraph_cap": strategy_paragraph_cap,
    }


def _render_chunking_user_prompt(variables: dict[str, object]) -> str:
    """
    @brief      Render the AI chunking user prompt with optional operator rules.
    @param[in]  variables Prompt variables.
    @return     Rendered AI chunking user prompt.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    template = prompt_template_service.load_prompt("text_chunking_user")
    placeholder_names = set(re.findall(r"{([A-Za-z_][A-Za-z0-9_]*)}", template))
    rendered_prompt = prompt_template_service.render_prompt(
        "text_chunking_user",
        {key: value for key, value in variables.items() if key in placeholder_names},
    )
    additional_chunking_instructions = _normalized_additional_chunking_instructions(
        variables.get("additional_chunking_instructions")
    )
    if additional_chunking_instructions and "additional_chunking_instructions" not in placeholder_names:
        rendered_prompt = _append_additional_chunking_instructions(
            rendered_prompt,
            additional_chunking_instructions,
        )
    return rendered_prompt


def _resolve_additional_chunking_instructions(
    additional_chunking_instructions: str | None,
    existing_state: dict[str, object],
) -> str:
    """
    @brief      Resolve the operator chunking rules for a new or resumed AI chunking run.
    @param[in]  additional_chunking_instructions New operator instructions or None when resuming.
    @param[in]  existing_state Existing chunking operation state.
    @return     Normalized operator chunking instructions.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    if additional_chunking_instructions is not None:
        return _normalized_additional_chunking_instructions(additional_chunking_instructions)
    if existing_state.get("mode") != "ai_assisted" or str(existing_state.get("status", "")) not in {
        "running",
        "failed",
    }:
        return ""
    resume_checkpoint = existing_state.get("resume_checkpoint", {})
    if not isinstance(resume_checkpoint, dict):
        return ""
    return _normalized_additional_chunking_instructions(resume_checkpoint.get("additional_chunking_instructions"))


def _normalized_additional_chunking_instructions(value: object) -> str:
    """
    @brief      Normalize optional operator chunking rules for prompt insertion and state storage.
    @param[in]  value Candidate instruction text.
    @return     Trimmed instruction text.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    if value is None:
        return ""
    return str(value).strip()


def _append_additional_chunking_instructions(prompt_text: str, additional_chunking_instructions: str) -> str:
    """
    @brief      Append operator chunking rules to one rendered AI chunking prompt.
    @param[in]  prompt_text Rendered prompt template text.
    @param[in]  additional_chunking_instructions Normalized operator rules.
    @return     Prompt text with an additional-rules section.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    if not additional_chunking_instructions:
        return prompt_text
    return f"{prompt_text.rstrip()}\n\nAdditional operator chunking instructions:\n{additional_chunking_instructions}\n"


def _build_profile_runtime_metadata(ai_profile_payload: dict[str, object]) -> ProfileRuntimeMetadataPayload:
    """
    @brief      Build persisted runtime metadata for the selected AI profile.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @return     JSON-ready profile settings relevant to AI chunking behavior.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.1.0
    """
    return {
        "model_name": str(ai_profile_payload.get("model_name", "")).strip(),
        "context_window": int(ai_profile_payload.get("context_window", 0) or 0),
        "max_output_tokens": int(ai_profile_payload.get("max_output_tokens", 0) or 0),
        "temperature": float(ai_profile_payload.get("temperature", 0.0) or 0.0),
    }


def _estimate_text_tokens(text: str) -> int:
    """
    @brief      Estimate token usage for local budget checks.
    @param[in]  text Value for `text`.
    @return     Estimated token count.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    return ai_budget_service.estimate_text_tokens(text)


def _build_paragraph_records(cleaned_text: str, project_root: str | Path | None = None) -> list[dict[str, object]]:
    """
    @brief      Build the paragraph records.
    @param[in]  cleaned_text Text value for `cleaned_text`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    records = deterministic_chunking_service._build_paragraph_records(cleaned_text, project_root)
    for index, record in enumerate(records, start=1):
        record["unit_id"] = str(record.get("paragraph_id") or f"paragraph-{index:04d}")
    return records


def _restore_resume_state(
    existing_state: dict[str, object],
    total_windows: int,
    input_fingerprint: str,
    semantic_strategy: str,
    additional_chunking_instructions_fingerprint: str,
    paragraph_records: list[dict[str, object]],
    windows: list[dict[str, int]],
    budget_metadata: BudgetMetadataPayload,
) -> tuple[int, int, list[str], str | None]:
    """
    @brief      Restore the resume state.
    @param[in]  existing_state Value for `existing_state`.
    @param[in]  total_windows Total number of windows.
    @param[in]  input_fingerprint Value for `input_fingerprint`.
    @param[in]  semantic_strategy Value for `semantic_strategy`.
    @param[in]  additional_chunking_instructions_fingerprint Operator instruction fingerprint.
    @param[in]  paragraph_records Value for `paragraph_records`.
    @param[in]  windows Current full-document request windows.
    @param[in]  budget_metadata Current context-budget metadata.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.5.0
    """
    if str(existing_state.get("status", "")) not in {"running", "failed"}:
        return 0, 0, [], None
    if str(existing_state.get("mode", "")) != "ai_assisted":
        return 0, 0, [], None
    resume_checkpoint = dict(existing_state.get("resume_checkpoint") or {})
    if str(resume_checkpoint.get("input_fingerprint", "")) != input_fingerprint:
        return 0, 0, [], None
    if str(resume_checkpoint.get("semantic_strategy", "")) != semantic_strategy:
        return 0, 0, [], None
    stored_instruction_fingerprint = str(
        resume_checkpoint.get("additional_chunking_instructions_fingerprint") or _compute_prompt_fingerprint("")
    )
    if stored_instruction_fingerprint != additional_chunking_instructions_fingerprint:
        return 0, 0, [], None
    completed_window_count = max(0, int(resume_checkpoint.get("completed_window_count", 0)))
    completed_unit_count = _restore_completed_unit_count(resume_checkpoint, paragraph_records)
    if completed_unit_count <= 0:
        return 0, 0, [], None
    committed_break_ids = [
        str(item) for item in list(resume_checkpoint.get("committed_break_ids", [])) if str(item).strip()
    ]
    log_relative_path = resume_checkpoint.get("log_relative_path")
    return (
        min(completed_window_count, total_windows),
        completed_unit_count,
        committed_break_ids,
        (None if log_relative_path in (None, "") else str(log_relative_path)),
    )


def _restore_completed_unit_count(
    resume_checkpoint: dict[str, object],
    paragraph_records: list[dict[str, object]],
) -> int:
    """
    @brief      Restore the count of paragraphs already processed by previous AI windows.
    @param[in]  resume_checkpoint Persisted AI chunking checkpoint payload.
    @param[in]  paragraph_records Current paragraph records.
    @return     Completed paragraph count, or zero when the checkpoint cannot be trusted.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.2.0
    """
    raw_completed_unit_count = resume_checkpoint.get("completed_unit_count")
    if raw_completed_unit_count not in (None, ""):
        return max(0, min(int(raw_completed_unit_count), len(paragraph_records)))
    return 0


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


def _restore_profile_usage_history(existing_state: dict[str, object]) -> list[ProfileRuntimeMetadataPayload]:
    """
    @brief      Restore persisted AI profile runtime settings used by earlier chunking segments.
    @param[in]  existing_state Persisted operation-state payload.
    @return     Ordered profile runtime metadata entries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.1.0
    """
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return []
    raw_history = metadata.get("profile_usage_history", [])
    if not isinstance(raw_history, list):
        return []
    profile_usage_history: list[ProfileRuntimeMetadataPayload] = []
    for item in raw_history:
        if isinstance(item, dict):
            profile_usage_history.append(dict(item))
    return profile_usage_history


def _merge_profile_usage_history(
    existing_history: list[ProfileRuntimeMetadataPayload],
    profile_runtime_metadata: ProfileRuntimeMetadataPayload,
) -> list[ProfileRuntimeMetadataPayload]:
    """
    @brief      Append the current profile runtime settings when not already represented.
    @param[in]  existing_history Existing ordered profile runtime metadata entries.
    @param[in]  profile_runtime_metadata Current selected profile runtime metadata.
    @return     Ordered profile runtime metadata history.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.1.0
    """
    resolved_history = [dict(item) for item in existing_history]
    if dict(profile_runtime_metadata) not in resolved_history:
        resolved_history.append(dict(profile_runtime_metadata))
    return resolved_history


def _build_units_block(paragraph_records: list[dict[str, object]]) -> str:
    """
    @brief      Build the units block.
    @param[in]  paragraph_records Value for `paragraph_records`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    blocks: list[str] = []
    for record in paragraph_records:
        blocks.append(f"{record['unit_id']}\n{record['text']}")
    return "\n\n".join(blocks).strip()


def _normalize_break_after_ids(
    response_payload: dict[str, object],
    window_records: list[dict[str, object]],
) -> list[str]:
    """
    @brief      Normalize the break after ids.
    @param[in]  response_payload Payload for `response_payload`.
    @param[in]  window_records Value for `window_records`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    valid_ids = {str(record["unit_id"]) for record in window_records}
    raw_ids = response_payload.get("break_after_unit_ids", [])
    if not isinstance(raw_ids, list):
        return []
    normalized: list[str] = []
    for item in raw_ids:
        resolved = str(item).strip()
        if not resolved or resolved not in valid_ids or resolved in normalized:
            continue
        normalized.append(resolved)
    return normalized


def _merge_committed_break_ids(
    existing_ids: list[str],
    new_ids: list[str],
    paragraph_records: list[dict[str, object]],
) -> list[str]:
    """
    @brief      Merge the committed break ids.
    @param[in]  existing_ids Value for `existing_ids`.
    @param[in]  new_ids Value for `new_ids`.
    @param[in]  paragraph_records Value for `paragraph_records`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    order = {str(record["unit_id"]): index for index, record in enumerate(paragraph_records)}
    merged = {item for item in existing_ids + new_ids if item in order}
    return sorted(merged, key=lambda item: order[item])


def _build_chunks_from_break_ids(
    paragraph_records: list[dict[str, object]],
    committed_break_ids: list[str],
    semantic_strategy: str,
) -> list[ChunkPayload]:
    """
    @brief      Build the chunks from break ids.
    @param[in]  paragraph_records Value for `paragraph_records`.
    @param[in]  committed_break_ids Value for `committed_break_ids`.
    @param[in]  semantic_strategy Value for `semantic_strategy`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not paragraph_records:
        return []
    boundary_ids = set(committed_break_ids)
    chunks: list[ChunkPayload] = []
    start_index = 0
    chunk_index = 1
    for record_index, paragraph_record in enumerate(paragraph_records):
        is_boundary = str(paragraph_record["unit_id"]) in boundary_ids
        is_last_record = record_index == len(paragraph_records) - 1
        if not is_boundary and not is_last_record:
            continue
        selected_records = paragraph_records[start_index : record_index + 1]
        chunks.append(
            {
                "chunk_id": f"chunk-{chunk_index:04d}",
                "sequence_index": chunk_index,
                "text": "\n\n".join(str(item["text"]) for item in selected_records).strip(),
                "source_start_line": int(selected_records[0]["line_start"]),
                "source_end_line": int(selected_records[-1]["line_end"]),
                "source_page_start": selected_records[0].get("source_page_start"),
                "source_page_end": selected_records[-1].get("source_page_end"),
                "cleanup_boundary_confidence": selected_records[0].get("boundary_confidence"),
                "cleanup_joined_across_page_break": any(
                    bool(item.get("joined_across_page_break", False)) for item in selected_records
                ),
                "cleanup_warning_flags": _merged_warning_flags(selected_records),
                "chunking_mode": "ai_assisted",
                "semantic_strategy": semantic_strategy,
                "scene_note": None,
            }
        )
        chunk_index += 1
        start_index = record_index + 1
    return chunks


def _write_chunk_payload(output_path: Path, chunks: list[ChunkPayload]) -> None:
    """
    @brief      Write the chunk payload.
    @param[in]  output_path Output file path.
    @param[in]  chunks Value for `chunks`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    output_path.write_text(
        json.dumps(chunks, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _merged_warning_flags(paragraph_records: list[dict[str, object]]) -> list[str]:
    """
    @brief      Merge cleanup warning flags across selected paragraph records.
    @param[in]  paragraph_records Paragraph records in one AI chunk span.
    @return     Ordered unique warning flags.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    flags: list[str] = []
    for record in paragraph_records:
        for flag in list(record.get("warning_flags", [])):
            resolved_flag = str(flag)
            if resolved_flag and resolved_flag not in flags:
                flags.append(resolved_flag)
    return flags


def _write_running_state(
    state_path: Path,
    project_root: Path,
    input_snapshot_path: Path,
    output_path: Path,
    report_path: Path | None,
    started_at: str,
    progress_current: int,
    progress_total: int,
    warnings: list[str],
    paragraph_records: list[dict[str, object]],
    committed_break_ids: list[str],
    profile_id: str,
    semantic_strategy: str,
    input_fingerprint: str,
    log_relative_path: str,
    token_usage: TokenUsagePayload,
    budget_metadata: BudgetMetadataPayload,
    profile_runtime_metadata: ProfileRuntimeMetadataPayload,
    profile_usage_history: list[ProfileRuntimeMetadataPayload],
    completed_unit_count: int,
    additional_chunking_instructions: str,
) -> None:
    """
    @brief      Write the running state.
    @param[in]  state_path Operation-state file path.
    @param[in]  project_root Active project root folder.
    @param[in]  input_snapshot_path Input snapshot file path.
    @param[in]  output_path Output file path.
    @param[in]  report_path Report file path.
    @param[in]  started_at Value for `started_at`.
    @param[in]  progress_current Value for `progress_current`.
    @param[in]  progress_total Value for `progress_total`.
    @param[in]  warnings Value for `warnings`.
    @param[in]  paragraph_records Value for `paragraph_records`.
    @param[in]  committed_break_ids Value for `committed_break_ids`.
    @param[in]  profile_id Profile identifier.
    @param[in]  semantic_strategy Value for `semantic_strategy`.
    @param[in]  input_fingerprint Value for `input_fingerprint`.
    @param[in]  log_relative_path Path for `log_relative_path`.
    @param[in]  token_usage Value for `token_usage`.
    @param[in]  budget_metadata Context-budget metadata.
    @param[in]  profile_runtime_metadata Runtime metadata for the current AI profile.
    @param[in]  profile_usage_history Runtime metadata entries used across resumed segments.
    @param[in]  completed_unit_count Number of paragraph units processed by completed AI windows.
    @param[in]  additional_chunking_instructions Optional operator-supplied chunking rules.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.4.0
    """
    additional_chunking_instructions_fingerprint = _compute_prompt_fingerprint(additional_chunking_instructions)
    chunks = _build_chunks_from_break_ids(
        paragraph_records,
        committed_break_ids,
        semantic_strategy,
    )
    state_payload = _build_operation_state(
        project_root=project_root,
        input_snapshot_path=input_snapshot_path,
        output_path=output_path,
        report_path=report_path,
        status="running",
        progress_current=progress_current,
        progress_total=progress_total,
        started_at=started_at,
        completed_at=None,
        warnings=warnings,
        chunks=chunks,
        profile_id=profile_id,
        semantic_strategy=semantic_strategy,
        log_relative_path=log_relative_path,
        token_usage=token_usage,
        resume_checkpoint={
            "input_fingerprint": input_fingerprint,
            "profile_id": profile_id,
            "semantic_strategy": semantic_strategy,
            "completed_window_count": progress_current,
            "total_window_count": progress_total,
            "completed_unit_count": int(completed_unit_count),
            "committed_break_ids": list(committed_break_ids),
            "log_relative_path": log_relative_path,
            "additional_chunking_instructions": additional_chunking_instructions,
            "additional_chunking_instructions_fingerprint": additional_chunking_instructions_fingerprint,
        },
        budget_metadata=budget_metadata,
        profile_runtime_metadata=profile_runtime_metadata,
        profile_usage_history=profile_usage_history,
    )
    state_path.write_text(
        json.dumps(state_payload, indent=2, ensure_ascii=False) + "\n",
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
    chunks: list[ChunkPayload] | None,
    profile_id: str,
    semantic_strategy: str,
    log_relative_path: str,
    resume_checkpoint: dict[str, object] | None,
    token_usage: TokenUsagePayload,
    budget_metadata: BudgetMetadataPayload,
    profile_runtime_metadata: ProfileRuntimeMetadataPayload,
    profile_usage_history: list[ProfileRuntimeMetadataPayload],
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
    @param[in]  chunks Value for `chunks`.
    @param[in]  profile_id Profile identifier.
    @param[in]  semantic_strategy Value for `semantic_strategy`.
    @param[in]  log_relative_path Path for `log_relative_path`.
    @param[in]  resume_checkpoint Value for `resume_checkpoint`.
    @param[in]  token_usage Value for `token_usage`.
    @param[in]  budget_metadata Context-budget metadata.
    @param[in]  profile_runtime_metadata Runtime metadata for the current AI profile.
    @param[in]  profile_usage_history Runtime metadata entries used across resumed segments.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.5.0
    """
    artifact_paths = [log_relative_path]
    if report_path is not None and report_path.is_file():
        artifact_paths.insert(0, relative_to_project(project_root, report_path))
    return build_operation_state_payload(
        status=status,
        input_paths=[relative_to_project(project_root, input_snapshot_path)],
        output_paths=([relative_to_project(project_root, output_path)] if output_path.is_file() else []),
        artifact_paths=artifact_paths,
        progress_current=progress_current,
        progress_total=progress_total,
        mode="ai_assisted",
        started_at=started_at,
        completed_at=completed_at,
        warning_count=len(warnings),
        metadata={
            "warnings": list(warnings),
            "chunk_count": 0 if chunks is None else len(chunks),
            "detected_chapter_count": 0 if chunks is None else _chapter_count_from_chunks(chunks),
            "ai_profile_id": profile_id,
            **profile_runtime_metadata,
            "semantic_strategy": semantic_strategy,
            "token_usage": token_usage_service.coerce_token_usage(token_usage),
            "budget_metadata": dict(budget_metadata),
            "profile_usage_history": [dict(item) for item in profile_usage_history],
        },
        resume_checkpoint=resume_checkpoint,
    )


def _chapter_count_from_chunks(chunks: list[ChunkPayload]) -> int:
    """
    @brief      Execute the chapter count from chunks helper.
    @param[in]  chunks Value for `chunks`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return deterministic_chunking_service._chapter_count_from_chunks(chunks)


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
    timestamp_token = started_at.replace("-", "").replace(":", "").replace("+", "_").replace(".", "")
    return build_operation_output_path(
        project_root,
        "chunking",
        config.ai_transaction_log_file_name("chunking", timestamp_token),
    )


# END OF FILE
