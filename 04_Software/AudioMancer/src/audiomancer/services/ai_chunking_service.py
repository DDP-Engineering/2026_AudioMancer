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
@version 0.3.0
"""

# IMPORTS

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    deterministic_chunking_service,
    llm_provider_service,
    prompt_template_service,
    token_usage_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    build_operation_input_snapshot_path,
    build_operation_output_path,
    progress_percent,
    raise_if_cancelled,
    relative_to_project,
    resolve_operation_path,
)

# CONSTANTS

# @brief Component logger used by the AI-assisted chunking workflow.
_AI_CHUNKING_LOGGER = get_component_logger("ai_chunking")

# @brief Strategy-specific paragraph window sizes used for AI chunk-boundary requests.
_WINDOW_SIZE_BY_STRATEGY = {
    "paragraph": 18,
    "meaning": 14,
    "scene": 10,
}

# @brief Canonical chunk-record payload type persisted for downstream workflow steps.
ChunkPayload = dict[str, object]

# @brief Persisted AI chunking report payload type.
ChunkingReportPayload = dict[str, object]

# @brief Persisted AI chunking operation-state payload type.
OperationStatePayload = dict[str, object]
TokenUsagePayload = dict[str, object]


# PUBLIC API


@trace_function(_AI_CHUNKING_LOGGER)
def chunk_text(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    semantic_strategy: str,
    progress_callback=None,
    cancel_requested=None,
) -> ChunkingReportPayload:
    """
    @brief      Run AI-assisted chunking for one active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  semantic_strategy Selected semantic strategy token.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Chunking report payload for the persisted AI chunking artifacts.
    @exception  FileNotFoundError Raised when the cleaned input is missing.
    @exception  ValueError Raised on missing profile data or unusable cleaned text.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
        @version    0.3.0
    """
    resolved_project_root = Path(project_root)
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        raise ValueError("No imported source is available for AI-assisted chunking.")

    cleaned_relative_path = f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"

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
    paragraph_records = _build_paragraph_records(input_text)
    if not paragraph_records:
        raise ValueError("Cleaned text does not contain any paragraphs for AI chunking.")

    original_name = str(source_document.get("original_name") or Path(cleaned_relative_path).name)
    input_snapshot_path = build_operation_input_snapshot_path(
        resolved_project_root,
        "chunking",
        original_name,
    )
    input_snapshot_path.write_text(input_text, encoding="utf-8")

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
        config.OPERATION_STATE_FILE_NAME,
    )

    prompt_template_service.validate_required_prompts(["text_chunking_system", "text_chunking_user"])
    input_fingerprint = _compute_input_fingerprint(input_text)
    windows = _build_windows(paragraph_records, semantic_strategy)
    total_windows = len(windows)
    if total_windows == 0:
        raise ValueError("Cleaned text does not contain any paragraphs for AI chunking.")

    existing_state = load_operation_state(resolved_project_root) or {}
    started_at = str(existing_state.get("started_at") or _utc_now_iso())
    start_window_index, committed_break_ids, log_relative_path = _restore_resume_state(
        existing_state,
        total_windows,
        input_fingerprint,
        profile_id,
        semantic_strategy,
    )
    token_usage = _restore_token_usage(existing_state)
    if start_window_index == 0:
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
        progress_current=start_window_index,
        progress_total=total_windows,
        warnings=[],
        paragraph_records=paragraph_records,
        committed_break_ids=committed_break_ids,
        profile_id=profile_id,
        semantic_strategy=semantic_strategy,
        input_fingerprint=input_fingerprint,
        log_relative_path=log_relative_path,
        token_usage=token_usage,
    )
    _emit_progress(
        progress_callback,
        progress_current=start_window_index,
        progress_total=total_windows,
        message="Resuming AI-assisted chunking..." if start_window_index > 0 else "AI-assisted chunking in progress...",
        token_usage=token_usage,
    )

    system_prompt = prompt_template_service.render_prompt(
        "text_chunking_system",
        {"strategy": semantic_strategy},
    )
    for window_index in range(start_window_index, total_windows):
        raise_if_cancelled(cancel_requested)
        window_payload = windows[window_index]
        window_records = paragraph_records[int(window_payload["start_index"]) : int(window_payload["end_index"]) + 1]
        user_prompt = prompt_template_service.render_prompt(
            "text_chunking_user",
            {
                "strategy": semantic_strategy,
                "units_block": _build_units_block(window_records),
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
                    "window_index": window_index + 1,
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
            progress_current=window_index + 1,
            progress_total=total_windows,
            warnings=[],
            paragraph_records=processed_records,
            committed_break_ids=committed_break_ids,
            profile_id=profile_id,
            semantic_strategy=semantic_strategy,
            input_fingerprint=input_fingerprint,
            log_relative_path=log_relative_path,
            token_usage=token_usage,
        )
        _emit_progress(
            progress_callback,
            progress_current=window_index + 1,
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
        "semantic_strategy": semantic_strategy,
        "log_relative_path": log_relative_path,
        "token_usage": token_usage,
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
        committed_break_ids=committed_break_ids,
        profile_id=profile_id,
        semantic_strategy=semantic_strategy,
        input_fingerprint=input_fingerprint,
        log_relative_path=log_relative_path,
        resume_checkpoint=None,
        token_usage=token_usage,
    )
    state_path.write_text(
        json.dumps(completed_state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
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
    @version    0.1.0
    """
    state_path = resolve_operation_path(project_root, "chunking", config.OPERATION_STATE_FILE_NAME)
    if not state_path.is_file():
        return None
    return dict(json.loads(state_path.read_text(encoding="utf-8")))


# LOCAL HELPERS


def _emit_progress(
    progress_callback,
    progress_current: int,
    progress_total: int,
    message: str,
    token_usage: TokenUsagePayload | None = None,
) -> None:
    """
    @brief      Emit the progress.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  progress_current Value for `progress_current`.
    @param[in]  progress_total Value for `progress_total`.
    @param[in]  message Operator-facing message text.
    @param[in]  token_usage Value for `token_usage`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if callable(progress_callback):
        progress_callback(
            progress_current,
            progress_total,
            progress_percent(progress_current, progress_total),
            message,
            token_usage,
        )


def _compute_input_fingerprint(input_text: str) -> str:
    """
    @brief      Execute the compute input fingerprint helper.
    @param[in]  input_text Text value for `input_text`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return hashlib.sha256(input_text.encode("utf-8")).hexdigest()


def _build_windows(
    paragraph_records: list[dict[str, object]],
    semantic_strategy: str,
) -> list[dict[str, int]]:
    """
    @brief      Build the windows.
    @param[in]  paragraph_records Value for `paragraph_records`.
    @param[in]  semantic_strategy Value for `semantic_strategy`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    window_size = _WINDOW_SIZE_BY_STRATEGY.get(
        semantic_strategy,
        _WINDOW_SIZE_BY_STRATEGY[config.DEFAULT_AI_CHUNKING_STRATEGY],
    )
    windows: list[dict[str, int]] = []
    start_index = 0
    while start_index < len(paragraph_records):
        end_index = min(len(paragraph_records) - 1, start_index + window_size - 1)
        windows.append(
            {
                "start_index": start_index,
                "end_index": end_index,
            }
        )
        start_index = end_index + 1
    return windows


def _build_paragraph_records(cleaned_text: str) -> list[dict[str, object]]:
    """
    @brief      Build the paragraph records.
    @param[in]  cleaned_text Text value for `cleaned_text`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    records = deterministic_chunking_service._build_paragraph_records(cleaned_text)
    for index, record in enumerate(records, start=1):
        record["unit_id"] = f"paragraph-{index:04d}"
    return records


def _restore_resume_state(
    existing_state: dict[str, object],
    total_windows: int,
    input_fingerprint: str,
    profile_id: str,
    semantic_strategy: str,
) -> tuple[int, list[str], str | None]:
    """
    @brief      Restore the resume state.
    @param[in]  existing_state Value for `existing_state`.
    @param[in]  total_windows Total number of windows.
    @param[in]  input_fingerprint Value for `input_fingerprint`.
    @param[in]  profile_id Profile identifier.
    @param[in]  semantic_strategy Value for `semantic_strategy`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if str(existing_state.get("status", "")) not in {"running", "failed"}:
        return 0, [], None
    if str(existing_state.get("mode", "")) != "ai_assisted":
        return 0, [], None
    resume_checkpoint = dict(existing_state.get("resume_checkpoint") or {})
    if str(resume_checkpoint.get("input_fingerprint", "")) != input_fingerprint:
        return 0, [], None
    if str(resume_checkpoint.get("profile_id", "")) != profile_id:
        return 0, [], None
    if str(resume_checkpoint.get("semantic_strategy", "")) != semantic_strategy:
        return 0, [], None
    if int(existing_state.get("progress_total", 0)) != total_windows:
        return 0, [], None
    start_window_index = int(resume_checkpoint.get("completed_window_count", 0))
    committed_break_ids = [
        str(item) for item in list(resume_checkpoint.get("committed_break_ids", [])) if str(item).strip()
    ]
    log_relative_path = resume_checkpoint.get("log_relative_path")
    return (
        min(start_window_index, total_windows),
        committed_break_ids,
        (None if log_relative_path in (None, "") else str(log_relative_path)),
    )


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
    current_chapter: str | None = None
    chunk_index = 1
    for record_index, paragraph_record in enumerate(paragraph_records):
        chapter_label = deterministic_chunking_service._detect_chapter_label(str(paragraph_record["text"]))
        if chapter_label is not None:
            current_chapter = chapter_label
        is_boundary = str(paragraph_record["unit_id"]) in boundary_ids
        is_last_record = record_index == len(paragraph_records) - 1
        if not is_boundary and not is_last_record:
            continue
        selected_records = paragraph_records[start_index : record_index + 1]
        chunks.append(
            {
                "chunk_id": f"chunk-{chunk_index:04d}",
                "sequence_index": chunk_index,
                "chapter_label": current_chapter,
                "text": "\n\n".join(str(item["text"]) for item in selected_records).strip(),
                "source_start_line": int(selected_records[0]["line_start"]),
                "source_end_line": int(selected_records[-1]["line_end"]),
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
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
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
        committed_break_ids=committed_break_ids,
        profile_id=profile_id,
        semantic_strategy=semantic_strategy,
        input_fingerprint=input_fingerprint,
        log_relative_path=log_relative_path,
        token_usage=token_usage,
        resume_checkpoint={
            "input_fingerprint": input_fingerprint,
            "profile_id": profile_id,
            "semantic_strategy": semantic_strategy,
            "completed_window_count": progress_current,
            "total_window_count": progress_total,
            "committed_break_ids": list(committed_break_ids),
            "log_relative_path": log_relative_path,
        },
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
    committed_break_ids: list[str],
    profile_id: str,
    semantic_strategy: str,
    input_fingerprint: str,
    log_relative_path: str,
    resume_checkpoint: dict[str, object] | None,
    token_usage: TokenUsagePayload,
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
    @param[in]  committed_break_ids Value for `committed_break_ids`.
    @param[in]  profile_id Profile identifier.
    @param[in]  semantic_strategy Value for `semantic_strategy`.
    @param[in]  input_fingerprint Value for `input_fingerprint`.
    @param[in]  log_relative_path Path for `log_relative_path`.
    @param[in]  resume_checkpoint Value for `resume_checkpoint`.
    @param[in]  token_usage Value for `token_usage`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    artifact_paths = [log_relative_path]
    if report_path is not None and report_path.is_file():
        artifact_paths.insert(0, relative_to_project(project_root, report_path))
    return {
        "folder_relative_path": config.CHUNKING_FOLDER_NAME,
        "status": status,
        "input_paths": [relative_to_project(project_root, input_snapshot_path)],
        "output_paths": ([relative_to_project(project_root, output_path)] if output_path.is_file() else []),
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
            "chunk_count": 0 if chunks is None else len(chunks),
            "detected_chapter_count": 0 if chunks is None else _chapter_count_from_chunks(chunks),
            "chunks": None if chunks is None else list(chunks),
            "ai_profile_id": profile_id,
            "semantic_strategy": semantic_strategy,
            "input_fingerprint": input_fingerprint,
            "log_relative_path": log_relative_path,
            "committed_break_ids": list(committed_break_ids),
            "token_usage": token_usage_service.coerce_token_usage(token_usage),
        },
        "resume_checkpoint": None if resume_checkpoint is None else dict(resume_checkpoint),
    }


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
        f"{config.AI_TRANSACTION_LOG_FILE_PREFIX}{timestamp_token}.log",
    )


def _utc_now_iso() -> str:
    """
    @brief      Execute the utc now iso helper.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# END OF FILE
