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
@version 0.10.0
"""

# IMPORTS

import hashlib
import json
from pathlib import Path
import re
import unicodedata

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
    load_operation_state_file,
    load_operation_state_payload,
    raise_if_cancelled,
    relative_to_project,
)
from audiomancer.services.operation_runtime_service import (
    emit_progress_update as _emit_progress,
)
from audiomancer.services.persistence_service import write_json_atomic
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

# @brief Component logger used by the AI-assisted chunking workflow.
_AI_CHUNKING_LOGGER = get_component_logger("ai_chunking")

# @brief Maximum number of paragraph-prefix words requested from the model.
_ANCHOR_WORD_LIMIT = 8

# @brief Consecutive normalized words required to confirm a non-short anchor.
_ANCHOR_MIN_CONSECUTIVE_WORDS = 5

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
    chunking_context_mode: str | None = None,
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
    @param[in]  chunking_context_mode Optional AI chunking context mode token.
    @return     Chunking report payload for the persisted AI chunking artifacts.
    @exception  FileNotFoundError Raised when the cleaned input is missing.
    @exception  ValueError Raised on missing profile data or unusable cleaned text.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.0.0
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
    existing_state = _load_resume_state(state_path)
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
        chunking_context_mode=chunking_context_mode,
    )
    profile_runtime_metadata = _build_profile_runtime_metadata(ai_profile_payload)
    input_fingerprint = _compute_input_fingerprint(input_text)
    (
        completed_window_count,
        next_paragraph,
        committed_chunks,
        context_window_fallback_count,
        log_relative_path,
        token_usage,
    ) = _restore_descriptor_resume_state(
        existing_state,
        output_path,
        len(paragraph_records),
        input_fingerprint,
        semantic_strategy,
        additional_chunking_instructions_fingerprint,
    )
    started_at = str(existing_state.get("started_at") or _utc_now_iso()) if completed_window_count else _utc_now_iso()
    profile_usage_history = _merge_profile_usage_history(
        _restore_profile_usage_history(existing_state) if completed_window_count else [],
        profile_runtime_metadata,
    )
    if completed_window_count == 0:
        _write_chunk_payload(output_path, [])

    if not log_relative_path:
        log_path = _build_ai_log_path(resolved_project_root, started_at)
        log_relative_path = relative_to_project(resolved_project_root, log_path)
    else:
        log_path = resolved_project_root / log_relative_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")

    remaining_windows = _build_windows_from_index(
        paragraph_records,
        next_paragraph - 1,
        semantic_strategy,
        budget_metadata,
    )
    total_windows = completed_window_count + len(remaining_windows)
    _write_descriptor_state(
        state_path=state_path,
        project_root=resolved_project_root,
        input_snapshot_path=input_snapshot_path,
        output_path=output_path,
        started_at=started_at,
        progress_current=completed_window_count,
        progress_total=total_windows,
        chunks=committed_chunks,
        profile_id=profile_id,
        semantic_strategy=semantic_strategy,
        input_fingerprint=input_fingerprint,
        log_relative_path=log_relative_path,
        token_usage=token_usage,
        budget_metadata=budget_metadata,
        profile_runtime_metadata=profile_runtime_metadata,
        profile_usage_history=profile_usage_history,
        next_paragraph=next_paragraph,
        additional_chunking_instructions_fingerprint=additional_chunking_instructions_fingerprint,
        context_window_fallback_count=context_window_fallback_count,
    )
    _emit_progress(
        progress_callback,
        progress_current=completed_window_count,
        progress_total=total_windows,
        message=(
            "Resuming AI-assisted chunking..." if completed_window_count > 0 else "AI-assisted chunking in progress..."
        ),
        token_usage=token_usage,
    )

    try:
        while next_paragraph <= len(paragraph_records):
            raise_if_cancelled(cancel_requested)
            remaining_windows = _build_windows_from_index(
                paragraph_records,
                next_paragraph - 1,
                semantic_strategy,
                budget_metadata,
            )
            window_payload = remaining_windows[0]
            window_start_index = int(window_payload["start_index"])
            window_end_index = int(window_payload["end_index"])
            window_records = paragraph_records[window_start_index : window_end_index + 1]
            is_final_window = window_end_index == len(paragraph_records) - 1
            total_windows = completed_window_count + len(remaining_windows)
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
                        "window_index": completed_window_count + 1,
                        "window_total": total_windows,
                    },
                    cancel_requested=cancel_requested,
                    response_schema=_build_response_schema(),
                    response_schema_name="text_chunk_descriptors",
                )
            except OperationCancelledError as error:
                raise OperationCancelledError(
                    "AI-assisted chunking cancelled while waiting for the model response."
                ) from error
            response_payload = response_result.get("payload")
            if not isinstance(response_payload, dict):
                raise ValueError("AI chunking response must be one JSON object.")
            token_usage = token_usage_service.merge_token_usage(token_usage, response_result.get("usage"))
            validated_ranges = _validate_chunk_descriptors(
                response_payload,
                paragraph_records,
                window_start_index,
                window_end_index,
            )

            progress_message = "AI-assisted chunking in progress..."
            if validated_ranges:
                _append_chunks_from_ranges(
                    committed_chunks,
                    paragraph_records,
                    validated_ranges,
                    semantic_strategy,
                )
                next_paragraph = int(validated_ranges[-1]["end_index"]) + 2
                if is_final_window and next_paragraph <= len(paragraph_records):
                    _append_chunks_from_ranges(
                        committed_chunks,
                        paragraph_records,
                        [{"start_index": next_paragraph - 1, "end_index": len(paragraph_records) - 1}],
                        semantic_strategy,
                    )
                    next_paragraph = len(paragraph_records) + 1
            elif is_final_window:
                _append_chunks_from_ranges(
                    committed_chunks,
                    paragraph_records,
                    [{"start_index": window_start_index, "end_index": len(paragraph_records) - 1}],
                    semantic_strategy,
                )
                next_paragraph = len(paragraph_records) + 1
            else:
                _append_chunks_from_ranges(
                    committed_chunks,
                    paragraph_records,
                    [{"start_index": window_start_index, "end_index": window_end_index}],
                    semantic_strategy,
                )
                context_window_fallback_count += 1
                next_paragraph = window_end_index + 2
                first_paragraph = window_start_index + 1
                last_paragraph = window_end_index + 1
                progress_message = (
                    f"AI chunking returned no valid split for paragraphs {first_paragraph}-{last_paragraph}. "
                    "AudioMancer saved this text window as one chunk."
                )

            completed_window_count += 1
            remaining_windows = _build_windows_from_index(
                paragraph_records,
                next_paragraph - 1,
                semantic_strategy,
                budget_metadata,
            )
            total_windows = completed_window_count + len(remaining_windows)
            _write_descriptor_state(
                state_path=state_path,
                project_root=resolved_project_root,
                input_snapshot_path=input_snapshot_path,
                output_path=output_path,
                started_at=started_at,
                progress_current=completed_window_count,
                progress_total=total_windows,
                chunks=committed_chunks,
                profile_id=profile_id,
                semantic_strategy=semantic_strategy,
                input_fingerprint=input_fingerprint,
                log_relative_path=log_relative_path,
                token_usage=token_usage,
                budget_metadata=budget_metadata,
                profile_runtime_metadata=profile_runtime_metadata,
                profile_usage_history=profile_usage_history,
                next_paragraph=next_paragraph,
                additional_chunking_instructions_fingerprint=additional_chunking_instructions_fingerprint,
                context_window_fallback_count=context_window_fallback_count,
            )
            _emit_progress(
                progress_callback,
                progress_current=completed_window_count,
                progress_total=total_windows,
                message=progress_message,
                token_usage=token_usage,
            )
    except OperationCancelledError:
        _write_descriptor_state(
            state_path=state_path,
            project_root=resolved_project_root,
            input_snapshot_path=input_snapshot_path,
            output_path=output_path,
            started_at=started_at,
            progress_current=completed_window_count,
            progress_total=total_windows,
            chunks=committed_chunks,
            profile_id=profile_id,
            semantic_strategy=semantic_strategy,
            input_fingerprint=input_fingerprint,
            log_relative_path=log_relative_path,
            token_usage=token_usage,
            budget_metadata=budget_metadata,
            profile_runtime_metadata=profile_runtime_metadata,
            profile_usage_history=profile_usage_history,
            next_paragraph=next_paragraph,
            additional_chunking_instructions_fingerprint=additional_chunking_instructions_fingerprint,
            context_window_fallback_count=context_window_fallback_count,
            status="cancelled",
            completed_at=_utc_now_iso(),
        )
        raise
    except Exception:
        _write_descriptor_state(
            state_path=state_path,
            project_root=resolved_project_root,
            input_snapshot_path=input_snapshot_path,
            output_path=output_path,
            started_at=started_at,
            progress_current=completed_window_count,
            progress_total=total_windows,
            chunks=committed_chunks,
            profile_id=profile_id,
            semantic_strategy=semantic_strategy,
            input_fingerprint=input_fingerprint,
            log_relative_path=log_relative_path,
            token_usage=token_usage,
            budget_metadata=budget_metadata,
            profile_runtime_metadata=profile_runtime_metadata,
            profile_usage_history=profile_usage_history,
            next_paragraph=next_paragraph,
            additional_chunking_instructions_fingerprint=additional_chunking_instructions_fingerprint,
            context_window_fallback_count=context_window_fallback_count,
            status="failed",
            completed_at=_utc_now_iso(),
        )
        raise

    chunks = committed_chunks
    _write_chunk_payload(output_path, chunks)
    chapter_count = _chapter_count_from_chunks(chunks)
    warnings = deterministic_chunking_service._build_chunking_warnings(chapter_count)
    if context_window_fallback_count:
        window_label = (
            "One text window was"
            if context_window_fallback_count == 1
            else (f"{context_window_fallback_count} text windows were")
        )
        warnings.append(
            f"{window_label} saved as a fallback chunk because AI chunking returned no valid internal split. "
            "A larger AI chunking context may produce more natural boundaries."
        )
    report_payload: ChunkingReportPayload = {
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
        "context_window_fallback_count": context_window_fallback_count,
    }
    write_json_atomic(report_path, report_payload)
    completed_state = _build_operation_state(
        project_root=resolved_project_root,
        input_snapshot_path=input_snapshot_path,
        output_path=output_path,
        report_path=report_path,
        status="completed",
        progress_current=total_windows,
        progress_total=total_windows,
        started_at=started_at,
        completed_at=None,
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
    write_json_atomic(state_path, completed_state)
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
    try:
        return load_operation_state_payload(project_root, "chunking", config.CHUNKING_STATE_FILE_NAME)
    except (OSError, TypeError, json.JSONDecodeError) as error:
        _AI_CHUNKING_LOGGER.warning("Ignored unreadable AI chunking state file: %s", error)
        return None


# LOCAL HELPERS


def _load_resume_state(state_path: Path) -> OperationStatePayload:
    """
    @brief      Load resumable AI chunking state, treating malformed JSON as no state.
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
        _AI_CHUNKING_LOGGER.warning("Restarting AI chunking after unreadable state file: %s", error)
        return {}


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
    chunking_context_mode: str | None = None,
) -> BudgetMetadataPayload:
    """
    @brief      Build context-window budget metadata for AI chunking.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  semantic_strategy Selected semantic strategy token.
    @param[in]  system_prompt Rendered system prompt.
    @param[in]  additional_chunking_instructions Optional operator-supplied chunking rules.
    @param[in]  chunking_context_mode Optional AI chunking context mode token.
    @return     Context-budget metadata used for request-window construction.
    @exception  ValueError Raised when context and output settings leave too little input room.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.3.1
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
    if (
        ai_budget_service.uses_online_text_budget(ai_profile_payload)
        or chunking_context_mode == config.AI_CHUNKING_CONTEXT_MODE_MAXIMUM
    ):
        strategy_paragraph_cap = 0
    elif chunking_context_mode == config.AI_CHUNKING_CONTEXT_MODE_WIDE_SCENE:
        strategy_paragraph_cap = config.AI_CHUNKING_WIDE_WINDOW_SIZE_BY_STRATEGY.get(
            semantic_strategy,
            config.AI_CHUNKING_WIDE_WINDOW_SIZE_BY_STRATEGY[config.DEFAULT_AI_CHUNKING_STRATEGY],
        )
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
    _ = existing_state
    return _normalized_additional_chunking_instructions(additional_chunking_instructions)


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
        record["paragraph_number"] = index
    return records


def _restore_descriptor_resume_state(
    existing_state: dict[str, object],
    output_path: Path,
    paragraph_count: int,
    input_fingerprint: str,
    semantic_strategy: str,
    additional_chunking_instructions_fingerprint: str,
) -> tuple[int, int, list[ChunkPayload], int, str | None, TokenUsagePayload]:
    """
    @brief      Restore only the descriptor-contract AI chunking checkpoint.
    @param[in]  existing_state Persisted operation state.
    @param[in]  output_path Canonical committed chunk artifact path.
    @param[in]  paragraph_count Current canonical paragraph count.
    @param[in]  input_fingerprint Current cleaned-text fingerprint.
    @param[in]  semantic_strategy Current semantic strategy.
    @param[in]  additional_chunking_instructions_fingerprint Current instruction fingerprint.
    @return     Completed windows, next paragraph, committed chunks, fallback count, log path, and usage.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.0.0
    """
    empty_result = (0, 1, [], 0, None, token_usage_service.empty_token_usage())
    if str(existing_state.get("status", "")) not in {"running", "failed", "cancelled"}:
        return empty_result
    if str(existing_state.get("mode", "")) != "ai_assisted":
        return empty_result
    checkpoint = existing_state.get("resume_checkpoint")
    expected_fields = {
        "input_fingerprint",
        "semantic_strategy",
        "additional_chunking_instructions_fingerprint",
        "next_paragraph",
        "committed_chunk_count",
        "completed_window_count",
        "context_window_fallback_count",
        "token_usage",
        "log_relative_path",
    }
    if not isinstance(checkpoint, dict) or set(checkpoint) != expected_fields:
        return empty_result
    if str(checkpoint.get("input_fingerprint", "")) != input_fingerprint:
        return empty_result
    if str(checkpoint.get("semantic_strategy", "")) != semantic_strategy:
        return empty_result
    if (
        str(checkpoint.get("additional_chunking_instructions_fingerprint", ""))
        != additional_chunking_instructions_fingerprint
    ):
        return empty_result

    next_paragraph = checkpoint.get("next_paragraph")
    committed_chunk_count = checkpoint.get("committed_chunk_count")
    completed_window_count = checkpoint.get("completed_window_count")
    fallback_count = checkpoint.get("context_window_fallback_count")
    if any(
        type(value) is not int
        for value in (next_paragraph, committed_chunk_count, completed_window_count, fallback_count)
    ):
        return empty_result
    if not 1 <= int(next_paragraph) <= paragraph_count + 1:
        return empty_result
    if min(int(committed_chunk_count), int(completed_window_count), int(fallback_count)) < 0:
        return empty_result
    try:
        raw_chunks = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError):
        return empty_result
    if not isinstance(raw_chunks, list) or len(raw_chunks) != int(committed_chunk_count):
        return empty_result
    committed_chunks = [dict(item) for item in raw_chunks if isinstance(item, dict)]
    if len(committed_chunks) != int(committed_chunk_count):
        return empty_result
    log_relative_path = checkpoint.get("log_relative_path")
    return (
        int(completed_window_count),
        int(next_paragraph),
        committed_chunks,
        int(fallback_count),
        None if log_relative_path in (None, "") else str(log_relative_path),
        token_usage_service.restore_token_usage(checkpoint.get("token_usage")),
    )


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


def _build_response_schema() -> dict[str, object]:
    """
    @brief      Build the strict AI chunk descriptor response schema.
    @return     Provider structured-output schema.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.0.0
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["chunks"],
        "properties": {
            "chunks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "start_paragraph",
                        "start_text",
                        "break_after_paragraph",
                    ],
                    "properties": {
                        "start_paragraph": {"type": "integer", "minimum": 1},
                        "start_text": {"type": "string", "minLength": 1},
                        "break_after_paragraph": {"type": "integer", "minimum": 1},
                    },
                },
            },
        },
    }


def _paragraph_start_anchor(paragraph_text: str) -> str:
    """
    @brief      Build the canonical start anchor for one paragraph.
    @param[in]  paragraph_text Canonical paragraph text.
    @return     First eight normalized words, or the whole shorter paragraph.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.0.0
    """
    return " ".join(str(paragraph_text).split()[:_ANCHOR_WORD_LIMIT])


def _normalized_anchor_words(anchor_text: str) -> list[str]:
    """
    @brief      Canonicalize anchor words for tolerant deterministic comparison.
    @param[in]  anchor_text Source or model-returned anchor text.
    @return     Up to eight case-folded compatibility-normalized words without punctuation.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    0.1.0
    """
    normalized_text = unicodedata.normalize("NFKC", str(anchor_text)).casefold()
    normalized_words: list[str] = []
    for raw_word in normalized_text.split():
        normalized_word = "".join(character for character in raw_word if character.isalnum())
        if normalized_word:
            normalized_words.append(normalized_word)
        if len(normalized_words) == _ANCHOR_WORD_LIMIT:
            break
    return normalized_words


def _start_anchor_matches(paragraph_text: str, returned_anchor: str) -> bool:
    """
    @brief      Confirm a model anchor against its declared source paragraph.
    @param[in]  paragraph_text Canonical source paragraph text.
    @param[in]  returned_anchor Model-returned start anchor.
    @return     True for a complete short match or a five-word consecutive match.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    0.1.0
    """
    expected_words = _normalized_anchor_words(_paragraph_start_anchor(paragraph_text))
    returned_words = _normalized_anchor_words(returned_anchor)
    if not expected_words:
        return False
    if len(expected_words) < _ANCHOR_MIN_CONSECUTIVE_WORDS:
        return returned_words == expected_words

    longest_run = 0
    current_run = 0
    for expected_word, returned_word in zip(expected_words, returned_words, strict=False):
        if returned_word == expected_word:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    return longest_run >= _ANCHOR_MIN_CONSECUTIVE_WORDS


def _validate_chunk_descriptors(
    response_payload: dict[str, object],
    paragraph_records: list[dict[str, object]],
    window_start_index: int,
    window_end_index: int,
) -> list[dict[str, int]] | None:
    """
    @brief      Validate one descriptor response atomically.
    @param[in]  response_payload Provider JSON response object.
    @param[in]  paragraph_records Full ordered paragraph record list.
    @param[in]  window_start_index Zero-based absolute first paragraph index.
    @param[in]  window_end_index Zero-based absolute last paragraph index.
    @return     Validated absolute ranges, or None when no valid split exists.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.1.0
    """
    if set(response_payload) != {"chunks"}:
        return None
    raw_chunks = response_payload.get("chunks")
    if not isinstance(raw_chunks, list) or not raw_chunks:
        return None

    expected_start_paragraph = window_start_index + 1
    validated_ranges: list[dict[str, int]] = []
    required_fields = {"start_paragraph", "start_text", "break_after_paragraph"}
    for item in raw_chunks:
        if not isinstance(item, dict) or set(item) != required_fields:
            return None
        start_paragraph = item.get("start_paragraph")
        break_after_paragraph = item.get("break_after_paragraph")
        start_text = item.get("start_text")
        if type(start_paragraph) is not int or type(break_after_paragraph) is not int:
            return None
        if not isinstance(start_text, str):
            return None
        if start_paragraph != expected_start_paragraph:
            return None
        if not window_start_index + 1 <= start_paragraph <= window_end_index + 1:
            return None
        if not start_paragraph <= break_after_paragraph <= window_end_index + 1:
            return None
        paragraph_text = str(paragraph_records[start_paragraph - 1]["text"])
        if not _start_anchor_matches(paragraph_text, start_text):
            return None
        validated_ranges.append(
            {
                "start_index": start_paragraph - 1,
                "end_index": break_after_paragraph - 1,
            }
        )
        expected_start_paragraph = break_after_paragraph + 1
    return validated_ranges


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
    for index, record in enumerate(paragraph_records):
        paragraph_number = int(record.get("paragraph_number", index + 1))
        blocks.append(f"Paragraph {paragraph_number}\n{record['text']}")
    return "\n\n".join(blocks).strip()


def _build_chunk_from_range(
    paragraph_records: list[dict[str, object]],
    start_index: int,
    end_index: int,
    semantic_strategy: str,
    sequence_index: int,
) -> ChunkPayload:
    """
    @brief      Build one canonical AI chunk from an absolute paragraph range.
    @param[in]  paragraph_records Full ordered paragraph record list.
    @param[in]  start_index Zero-based inclusive first paragraph index.
    @param[in]  end_index Zero-based inclusive last paragraph index.
    @param[in]  semantic_strategy Selected semantic strategy.
    @param[in]  sequence_index One-based canonical chunk sequence number.
    @return     Canonical chunk payload.
    @exception  ValueError Raised when the selected range is empty or invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.0.0
    """
    selected_records = paragraph_records[start_index : end_index + 1]
    if not selected_records:
        raise ValueError("AI chunk range does not contain any paragraphs.")
    return {
        "chunk_id": f"chunk-{sequence_index:04d}",
        "sequence_index": sequence_index,
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
    }


def _append_chunks_from_ranges(
    chunks: list[ChunkPayload],
    paragraph_records: list[dict[str, object]],
    ranges: list[dict[str, int]],
    semantic_strategy: str,
) -> None:
    """
    @brief      Append canonical chunks for validated absolute paragraph ranges.
    @param[in,out] chunks Existing committed chunk payload list.
    @param[in]  paragraph_records Full ordered paragraph record list.
    @param[in]  ranges Validated absolute paragraph ranges.
    @param[in]  semantic_strategy Selected semantic strategy.
    @return     None.
    @exception  ValueError Raised when a range is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.0.0
    """
    for range_payload in ranges:
        chunks.append(
            _build_chunk_from_range(
                paragraph_records,
                int(range_payload["start_index"]),
                int(range_payload["end_index"]),
                semantic_strategy,
                len(chunks) + 1,
            )
        )


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


def _write_descriptor_state(
    state_path: Path,
    project_root: Path,
    input_snapshot_path: Path,
    output_path: Path,
    started_at: str,
    progress_current: int,
    progress_total: int,
    chunks: list[ChunkPayload],
    profile_id: str,
    semantic_strategy: str,
    input_fingerprint: str,
    log_relative_path: str,
    token_usage: TokenUsagePayload,
    budget_metadata: BudgetMetadataPayload,
    profile_runtime_metadata: ProfileRuntimeMetadataPayload,
    profile_usage_history: list[ProfileRuntimeMetadataPayload],
    next_paragraph: int,
    additional_chunking_instructions_fingerprint: str,
    context_window_fallback_count: int,
    status: str = "running",
    completed_at: str | None = None,
) -> None:
    """
    @brief      Persist one descriptor-contract AI chunking checkpoint.
    @return     None.
    @exception  OSError Raised when state persistence fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.0.0
    """
    _write_chunk_payload(output_path, chunks)
    state_payload = _build_operation_state(
        project_root=project_root,
        input_snapshot_path=input_snapshot_path,
        output_path=output_path,
        report_path=None,
        status=status,
        progress_current=progress_current,
        progress_total=progress_total,
        started_at=started_at,
        completed_at=completed_at,
        warnings=[],
        chunks=chunks,
        profile_id=profile_id,
        semantic_strategy=semantic_strategy,
        log_relative_path=log_relative_path,
        resume_checkpoint={
            "input_fingerprint": input_fingerprint,
            "semantic_strategy": semantic_strategy,
            "additional_chunking_instructions_fingerprint": additional_chunking_instructions_fingerprint,
            "next_paragraph": int(next_paragraph),
            "committed_chunk_count": len(chunks),
            "completed_window_count": int(progress_current),
            "context_window_fallback_count": int(context_window_fallback_count),
            "token_usage": token_usage_service.coerce_token_usage(token_usage),
            "log_relative_path": log_relative_path,
        },
        token_usage=token_usage,
        budget_metadata=budget_metadata,
        profile_runtime_metadata=profile_runtime_metadata,
        profile_usage_history=profile_usage_history,
    )
    write_json_atomic(state_path, state_payload)


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
    _ = project_root
    _ = input_snapshot_path
    _ = output_path
    _ = report_path
    return build_operation_state_payload(
        status=status,
        progress_current=progress_current,
        progress_total=progress_total,
        mode="ai_assisted",
        warning_count=len(warnings),
        metadata={
            "warnings": list(warnings),
            "chunk_count": 0 if chunks is None else len(chunks),
            "detected_chapter_count": 0 if chunks is None else _chapter_count_from_chunks(chunks),
            "ai_profile_id": profile_id,
            **profile_runtime_metadata,
            "semantic_strategy": semantic_strategy,
            "log_relative_path": log_relative_path,
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
