#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file speech_blocks_report_state_service.py
@brief Speech Blocks report and operation-state shaping helpers.
@details Builds Speech Blocks report payloads, warning summaries, source input
         artifact paths, and resumable operation-state payloads outside the
         orchestration service.
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.3.1
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import chunking_document_service, speech_blocks_normalization_service, token_usage_service
from audiomancer.services.operation_runtime_service import (
    build_operation_state_payload,
    relative_to_project,
)

# CONSTANTS

SPEECH_BLOCKS_STAGE_NOT_STARTED = "not_started"
SPEECH_BLOCKS_STAGE_IN_PROGRESS = "in_progress"
SPEECH_BLOCKS_STAGE_COMPLETED = "completed"

SpeechBlockPayload = dict[str, object]
SpeechBlocksReportPayload = dict[str, object]
OperationStatePayload = dict[str, object]
BudgetMetadataPayload = dict[str, int]

# PUBLIC API


def rebuild_report(
    speech_blocks: list[SpeechBlockPayload],
    source_language: str,
    source_kind: str,
    profile_id: str,
    total_chunk_count: int,
    processed_chunk_count: int,
    warning_records: list[dict[str, object]],
    token_usage: dict[str, object],
    budget_metadata: BudgetMetadataPayload | None = None,
    updated_at: str | None = None,
) -> SpeechBlocksReportPayload:
    """
    @brief      Recompute the Speech Blocks report from current persisted state.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  source_language Active source language code.
    @param[in]  source_kind Active source-kind token.
    @param[in]  profile_id Active AI profile identifier.
    @param[in]  total_chunk_count Total source chunk count.
    @param[in]  processed_chunk_count Number of processed chunks.
    @param[in]  warning_records Current warning entry list.
    @param[in]  token_usage Current cumulative token-usage payload.
    @param[in]  budget_metadata Optional context-budget metadata.
    @param[in]  updated_at Ignored legacy report timestamp override.
    @return     Rebuilt Speech Blocks report payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.2.0
    """
    _ = warning_records
    _ = updated_at
    approved_count = approved_block_count(speech_blocks)
    total_block_count = len(speech_blocks)
    warning_entries = warning_records_from_blocks(speech_blocks)
    if total_chunk_count > 0 and processed_chunk_count >= total_chunk_count and total_block_count > 0:
        stage_status = (
            SPEECH_BLOCKS_STAGE_COMPLETED if approved_count >= total_block_count else SPEECH_BLOCKS_STAGE_IN_PROGRESS
        )
    elif processed_chunk_count > 0 or speech_blocks:
        stage_status = SPEECH_BLOCKS_STAGE_IN_PROGRESS
    else:
        stage_status = SPEECH_BLOCKS_STAGE_NOT_STARTED
    report_payload: SpeechBlocksReportPayload = {
        "source_language": source_language,
        "source_kind": source_kind,
        "ai_profile_id": profile_id,
        "speech_blocks_stage_status": stage_status,
        "processed_chunk_count": processed_chunk_count,
        "total_chunk_count": total_chunk_count,
        "speech_block_count": total_block_count,
        "approved_block_count": approved_count,
        "total_block_count": total_block_count,
        "warning_count": len(warning_entries),
        "warnings": warning_entries,
        "token_usage": token_usage_service.coerce_token_usage(token_usage),
    }
    if budget_metadata is not None:
        report_payload["budget_metadata"] = dict(budget_metadata)
    return report_payload


def approved_block_count(speech_blocks: list[SpeechBlockPayload]) -> int:
    """
    @brief      Count approved Speech Blocks.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @return     Number of approved Speech Blocks.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    return sum(1 for block in speech_blocks if bool(block.get("approved", False)))


def warning_records_from_blocks(speech_blocks: list[SpeechBlockPayload]) -> list[dict[str, object]]:
    """
    @brief      Build report warning entries from current block warning flags.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @return     Ordered report warning entries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    records: list[dict[str, object]] = []
    for block in speech_blocks:
        warning_flags = speech_blocks_normalization_service.normalize_warning_flags(block.get("warning_flags"))
        if not warning_flags:
            continue
        records.append(
            {
                "chunk_id": str(block.get("chunk_id", "")).strip(),
                "speech_block_id": str(block.get("speech_block_id", "")).strip(),
                "reason": ", ".join(warning_flags),
            }
        )
    return records


def build_operation_state(
    project_root: Path,
    source_chunks: list[dict[str, object]],
    speech_blocks: list[SpeechBlockPayload],
    status: str,
    started_at: str,
    completed_at: str | None,
    source_language: str,
    source_kind: str,
    profile_id: str,
    warning_records: list[dict[str, object]],
    input_fingerprint: str,
    log_path: Path,
    token_usage: dict[str, object],
    next_chunk_index: int | None,
    budget_metadata: BudgetMetadataPayload | None = None,
) -> OperationStatePayload:
    """
    @brief      Build one persisted Speech Blocks operation-state payload.
    @param[in]  project_root Active project root folder.
    @param[in]  source_chunks Current source-chunk snapshot.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  status Persisted operation status token.
    @param[in]  started_at Operation start timestamp.
    @param[in]  completed_at Operation completion timestamp or `None`.
    @param[in]  source_language Active source language code.
    @param[in]  source_kind Active source-kind token.
    @param[in]  profile_id Active AI profile identifier.
    @param[in]  warning_records Current warning entry list.
    @param[in]  input_fingerprint Stable source snapshot fingerprint.
    @param[in]  log_path Operation-local AI transaction log path.
    @param[in]  token_usage Current cumulative token-usage payload.
    @param[in]  next_chunk_index Next chunk index to process or `None`.
    @param[in]  budget_metadata Optional context-budget metadata.
    @return     Persisted operation-state payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    _ = warning_records
    _ = started_at
    _ = completed_at
    processed_chunk_count = len({str(block.get("chunk_id", "")).strip() for block in speech_blocks})
    warning_entries = warning_records_from_blocks(speech_blocks)
    metadata_payload: dict[str, object] = {
        "source_language": source_language,
        "source_kind": source_kind,
        "ai_profile_id": profile_id,
        "processed_chunk_count": processed_chunk_count,
        "total_chunk_count": len(source_chunks),
        "speech_block_count": len(speech_blocks),
        "approved_block_count": approved_block_count(speech_blocks),
        "total_block_count": len(speech_blocks),
        "warnings": warning_entries,
        "source_snapshot_fingerprint": input_fingerprint,
        "source_chunks": [
            {
                "chunk_id": str(chunk.get("chunk_id", "")),
                "sequence_index": int(chunk.get("sequence_index", 0)),
                "text": str(chunk.get("text", "")),
            }
            for chunk in source_chunks
        ],
        "log_relative_path": relative_to_project(project_root, log_path),
        "token_usage": token_usage_service.coerce_token_usage(token_usage),
    }
    if budget_metadata is not None:
        metadata_payload["budget_metadata"] = dict(budget_metadata)
    resume_checkpoint = None
    if next_chunk_index is not None:
        resume_checkpoint = {
            "next_chunk_index": next_chunk_index,
            "run_token": started_at,
            "source_snapshot_fingerprint": input_fingerprint,
            "source_language": source_language,
            "ai_profile_id": profile_id,
            "log_relative_path": relative_to_project(project_root, log_path),
        }
        if budget_metadata is not None:
            resume_checkpoint["budget_metadata"] = dict(budget_metadata)
    return build_operation_state_payload(
        status=status,
        progress_current=processed_chunk_count,
        progress_total=len(source_chunks),
        mode="ai_assisted",
        warning_count=len(warning_entries),
        metadata=metadata_payload,
        resume_checkpoint=resume_checkpoint,
    )


def source_chunks_input_path(project_root: Path, source_kind: str) -> Path:
    """
    @brief      Resolve the upstream Speech Blocks source artifact path.
    @param[in]  project_root Active project root folder.
    @param[in]  source_kind Active source-kind token.
    @return     Absolute project-local source artifact path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    if str(source_kind).strip() == "translated":
        return project_root / config.TRANSLATED_CHUNKS_FILE_NAME
    return chunking_document_service.document_path(project_root)


# END OF FILE
