#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file speech_blocks_service.py
@brief AI-assisted speech-block generation helpers for AudioMancer.
@details Resolves the active Character Voices source language, converts the
         selected chunk set into speaker-attributed speech blocks, persists the
         `70_speech_blocks` workflow artifacts, and maintains resumable chunk-
         based operation state plus AI transaction logging.
"""

# IMPORTS

import hashlib
import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    character_discovery_service,
    chunking_document_service,
    narrator_definition_service,
    project_workspace_service,
    speech_blocks_generation_service,
    speech_blocks_normalization_service,
    speech_blocks_report_state_service,
    token_usage_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    build_operation_output_path,
    build_operation_state_payload,
    load_optional_json_artifact,
    raise_if_cancelled,
    reset_operation_data,
    resolve_operation_path,
    write_operation_json_artifact,
)
from audiomancer.services.operation_runtime_service import (
    emit_progress_update as _emit_progress,
)
from audiomancer.services.operation_runtime_service import (
    valid_runtime_value as _valid_runtime_value,
)
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

_SPEECH_BLOCKS_LOGGER = get_component_logger("speech_blocks")

SPEECH_BLOCKS_STAGE_NOT_STARTED = speech_blocks_report_state_service.SPEECH_BLOCKS_STAGE_NOT_STARTED
SPEECH_BLOCKS_STAGE_IN_PROGRESS = speech_blocks_report_state_service.SPEECH_BLOCKS_STAGE_IN_PROGRESS
SPEECH_BLOCKS_STAGE_COMPLETED = speech_blocks_report_state_service.SPEECH_BLOCKS_STAGE_COMPLETED

SPEAKER_KIND_NARRATOR = speech_blocks_normalization_service.SPEAKER_KIND_NARRATOR
SPEAKER_KIND_CHARACTER = speech_blocks_normalization_service.SPEAKER_KIND_CHARACTER
SPEAKER_KIND_OPERATION = speech_blocks_normalization_service.SPEAKER_KIND_OPERATION
CONTENT_KIND_NARRATION = speech_blocks_normalization_service.CONTENT_KIND_NARRATION
CONTENT_KIND_DIALOGUE = speech_blocks_normalization_service.CONTENT_KIND_DIALOGUE
CONTENT_KIND_SCENE_AMBIENCE = speech_blocks_normalization_service.CONTENT_KIND_SCENE_AMBIENCE
CONTENT_KIND_PAUSE = speech_blocks_normalization_service.CONTENT_KIND_PAUSE
CONTENT_KIND_INDICATION = speech_blocks_normalization_service.CONTENT_KIND_INDICATION

SPEECH_BLOCK_CONTENT_KINDS = speech_blocks_normalization_service.SPEECH_BLOCK_CONTENT_KINDS

_NARRATOR_SPEAKER_ID = speech_blocks_normalization_service.NARRATOR_SPEAKER_ID
_NARRATOR_DISPLAY_NAME = speech_blocks_normalization_service.NARRATOR_DISPLAY_NAME
_SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT = "direct_blocks"
_SPEECH_BLOCKS_SOURCE_SPAN_SELECTION_CONTRACT = "atomic_unit_selection"
_SPEECH_BLOCKS_NARRATOR_BOUNDARY_CONTRACT = "narrator_boundary_ids"
_SPEECH_BLOCKS_DETERMINISTIC_NARRATOR_CONTRACT = "deterministic_narrator_blocks"
_approved_block_count = speech_blocks_report_state_service.approved_block_count
_build_speech_block_payload = speech_blocks_normalization_service.build_speech_block_payload
_build_operation_state = speech_blocks_report_state_service.build_operation_state
_chunk_order_from_id = speech_blocks_normalization_service.chunk_order_from_id
_next_unused_speech_block_id = speech_blocks_normalization_service.next_unused_speech_block_id
_stable_speech_block_id = speech_blocks_normalization_service.stable_speech_block_id
_normalized_additional_speech_block_instructions = speech_blocks_generation_service.normalize_instructions
requires_ai_profile = speech_blocks_generation_service.requires_ai_profile
_is_operation_content_kind = speech_blocks_normalization_service.is_operation_content_kind
_normalize_content_kind = speech_blocks_normalization_service.normalize_content_kind
_normalize_warning_flags = speech_blocks_normalization_service.normalize_warning_flags
_operation_speaker_entry = speech_blocks_normalization_service.operation_speaker_entry
_rebuild_report = speech_blocks_report_state_service.rebuild_report
_warning_records_from_blocks = speech_blocks_report_state_service.warning_records_from_blocks

SpeechBlockPayload = dict[str, object]
SpeechBlocksReportPayload = dict[str, object]
OperationStatePayload = dict[str, object]
SpeechBlocksDocumentPayload = dict[str, object]
TokenUsagePayload = dict[str, object]
BudgetMetadataPayload = dict[str, int]
_SpeechBlocksSourceContext = tuple[list[dict[str, object]], int, str, str]

# @brief Fixed top-level field set of the authoritative single Speech Blocks document.
_SPEECH_BLOCKS_DOCUMENT_FIELDS = frozenset(
    (
        "status",
        "source",
        "ai_profile_id",
        "instructions",
        "scene_ambience",
        "response_contract",
        "token_usage",
        "budget_metadata",
        "checkpoint",
        "failure",
        "blocks",
    )
)
_SPEECH_BLOCKS_SOURCE_FIELDS = frozenset(("kind", "language", "fingerprint"))
_SPEECH_BLOCKS_SOURCE_KINDS = frozenset(("original", "translated"))
_SPEECH_BLOCKS_DOCUMENT_STATUSES = frozenset(
    ("not_started", "running", "review_pending", "completed", "failed", "cancelled")
)
_SPEECH_BLOCKS_RESPONSE_CONTRACTS = frozenset(
    (
        _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT,
        _SPEECH_BLOCKS_SOURCE_SPAN_SELECTION_CONTRACT,
        _SPEECH_BLOCKS_NARRATOR_BOUNDARY_CONTRACT,
        _SPEECH_BLOCKS_DETERMINISTIC_NARRATOR_CONTRACT,
    )
)
_UNRESOLVED_TRANSLATION_DOCUMENT = object()


class SpeechBlocksDocumentError(ValueError):
    """Raised when the authoritative single Speech Blocks document is invalid."""


def _validate_speech_blocks_document(payload: object) -> None:
    """Validate the strict, hard-break single Speech Blocks document contract."""
    if not isinstance(payload, dict) or set(payload) != set(_SPEECH_BLOCKS_DOCUMENT_FIELDS):
        raise SpeechBlocksDocumentError("Speech Blocks data has an incompatible root contract.")
    if str(payload.get("status", "")) not in _SPEECH_BLOCKS_DOCUMENT_STATUSES:
        raise SpeechBlocksDocumentError("Speech Blocks data has an invalid status.")
    source = payload.get("source")
    if not isinstance(source, dict) or set(source) != set(_SPEECH_BLOCKS_SOURCE_FIELDS):
        raise SpeechBlocksDocumentError("Speech Blocks data has an invalid source contract.")
    if str(source.get("kind", "")) not in _SPEECH_BLOCKS_SOURCE_KINDS:
        raise SpeechBlocksDocumentError("Speech Blocks data has an invalid source kind.")
    if not all(isinstance(source.get(field), str) for field in _SPEECH_BLOCKS_SOURCE_FIELDS):
        raise SpeechBlocksDocumentError("Speech Blocks source fields must be strings.")
    if not isinstance(payload.get("ai_profile_id"), str):
        raise SpeechBlocksDocumentError("Speech Blocks ai_profile_id must be a string.")
    if not isinstance(payload.get("instructions"), str):
        raise SpeechBlocksDocumentError("Speech Blocks instructions must be a string.")
    if not isinstance(payload.get("scene_ambience"), dict):
        raise SpeechBlocksDocumentError("Speech Blocks scene_ambience must be an object.")
    if str(payload.get("response_contract", "")) not in _SPEECH_BLOCKS_RESPONSE_CONTRACTS:
        raise SpeechBlocksDocumentError("Speech Blocks response_contract is invalid.")
    if not isinstance(payload.get("token_usage"), dict):
        raise SpeechBlocksDocumentError("Speech Blocks token_usage must be an object.")
    if not isinstance(payload.get("budget_metadata"), dict):
        raise SpeechBlocksDocumentError("Speech Blocks budget_metadata must be an object.")
    checkpoint = payload.get("checkpoint")
    if checkpoint is not None and not isinstance(checkpoint, dict):
        raise SpeechBlocksDocumentError("Speech Blocks checkpoint must be null or an object.")
    failure = payload.get("failure")
    if failure is not None and not isinstance(failure, dict):
        raise SpeechBlocksDocumentError("Speech Blocks failure must be null or an object.")
    if not isinstance(payload.get("blocks"), list):
        raise SpeechBlocksDocumentError("Speech Blocks blocks must be an array.")


# PUBLIC API


@trace_function(_SPEECH_BLOCKS_LOGGER)
def load_speech_blocks_document(project_root: str | Path) -> SpeechBlocksDocumentPayload | None:
    """
    @brief      Load and strictly validate the authoritative single Speech Blocks document.
    @param[in]  project_root Active project root folder.
    @return     Document payload, or `None` when the optional document is missing.
    @exception  SpeechBlocksDocumentError Raised when an existing document is unreadable or invalid.
    """
    document_path = resolve_operation_path(project_root, "speech_blocks", config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME)
    document_exists = document_path.exists()
    try:
        payload = load_optional_json_artifact(document_path)
    except (OSError, ValueError) as error:
        raise SpeechBlocksDocumentError(
            f"Speech Blocks data is unreadable. Reset Speech Blocks to recover: {error}"
        ) from error
    if payload is None and not document_exists:
        return None
    try:
        _validate_speech_blocks_document(payload)
    except SpeechBlocksDocumentError as error:
        raise SpeechBlocksDocumentError(
            f"Speech Blocks data is invalid. Reset Speech Blocks to recover: {error}"
        ) from error
    assert isinstance(payload, dict)
    return dict(payload)


def write_speech_blocks_document(
    project_root: str | Path,
    document: SpeechBlocksDocumentPayload,
) -> Path:
    """
    @brief      Strictly validate and atomically persist the single Speech Blocks document.
    @param[in]  project_root Active project root folder.
    @param[in]  document Complete Speech Blocks document payload.
    @return     Absolute project-local document path.
    @exception  SpeechBlocksDocumentError Raised when the document violates the strict contract.
    """
    _validate_speech_blocks_document(document)
    write_operation_json_artifact(project_root, "speech_blocks", config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME, document)
    return build_operation_output_path(project_root, "speech_blocks", config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME)


def _document_checkpoint(operation_state: OperationStatePayload) -> dict[str, object] | None:
    """Project the persisted document checkpoint from one in-memory operation state."""
    if not isinstance(operation_state, dict):
        return None
    started_at = str(_valid_runtime_value(operation_state.get("started_at")) or "").strip()
    resume_checkpoint = operation_state.get("resume_checkpoint")
    if isinstance(resume_checkpoint, dict):
        checkpoint = dict(resume_checkpoint)
        if started_at:
            checkpoint["run_token"] = started_at
        return checkpoint
    metadata = operation_state.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    log_relative_path = str(metadata.get("log_relative_path", "")).strip()
    run_token = started_at
    if not run_token and not log_relative_path:
        return None
    checkpoint: dict[str, object] = {
        "next_chunk_index": int(metadata.get("processed_chunk_count", 0) or 0),
        "run_token": run_token,
        "log_relative_path": log_relative_path,
        "source_snapshot_fingerprint": str(metadata.get("source_snapshot_fingerprint", "")).strip(),
        "source_language": str(metadata.get("source_language", "")).strip(),
        "ai_profile_id": str(metadata.get("ai_profile_id", "")).strip(),
        "additional_speech_block_instructions_fingerprint": str(
            metadata.get("additional_speech_block_instructions_fingerprint", "")
        ).strip(),
        "speech_blocks_response_contract": str(metadata.get("speech_blocks_response_contract", "")).strip(),
    }
    if isinstance(metadata.get("budget_metadata"), dict):
        checkpoint["budget_metadata"] = dict(metadata["budget_metadata"])
    return checkpoint


def _coerce_skipped_chunk_ids(value: object) -> list[str]:
    """Return the normalized skipped source chunk identifiers carried by a payload value."""
    if not isinstance(value, list):
        return []
    return [str(chunk_id).strip() for chunk_id in value if str(chunk_id).strip()]


def _document_skipped_chunk_ids(document: SpeechBlocksDocumentPayload) -> list[str]:
    """Return the skipped source chunk identifiers recorded on a Speech Blocks document."""
    failure = document.get("failure")
    if not isinstance(failure, dict):
        return []
    return _coerce_skipped_chunk_ids(failure.get("skipped_chunk_ids"))


def _restore_skipped_chunk_ids(operation_state: dict[str, object] | None) -> list[str]:
    """Return the skipped source chunk identifiers carried by a projected operation state."""
    if not isinstance(operation_state, dict):
        return []
    metadata = operation_state.get("metadata")
    if not isinstance(metadata, dict):
        return []
    return _coerce_skipped_chunk_ids(metadata.get("skipped_chunk_ids"))


def _uncovered_skipped_chunk_ids(
    operation_state: dict[str, object] | None,
    speech_blocks: list[SpeechBlockPayload],
) -> list[str]:
    """Return recorded skipped source chunk identifiers that still carry no Speech Blocks."""
    covered_chunk_ids = {str(block.get("chunk_id", "")).strip() for block in speech_blocks}
    return [
        chunk_id
        for chunk_id in _restore_skipped_chunk_ids(operation_state)
        if chunk_id not in covered_chunk_ids
    ]


def _ordered_skipped_chunk_ids(
    source_chunks: list[dict[str, object]],
    skipped_chunk_ids: set[str],
) -> list[str]:
    """Return the skipped source chunk identifiers in canonical source order."""
    return [
        chunk_id
        for chunk_id in (str(chunk.get("chunk_id", "")).strip() for chunk in source_chunks)
        if chunk_id in skipped_chunk_ids
    ]


def _compose_speech_blocks_document(
    speech_blocks: list[SpeechBlockPayload],
    report: SpeechBlocksReportPayload,
    operation_state: OperationStatePayload,
) -> SpeechBlocksDocumentPayload:
    """Assemble the single authoritative Speech Blocks document from report and operation state."""
    metadata = operation_state.get("metadata", {}) if isinstance(operation_state, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    source = {
        "kind": str(report.get("source_kind", metadata.get("source_kind", ""))).strip(),
        "language": str(report.get("source_language", metadata.get("source_language", ""))).strip(),
        "fingerprint": str(metadata.get("source_snapshot_fingerprint", "")).strip(),
    }
    scene_ambience = report.get("scene_ambience_generation")
    if not isinstance(scene_ambience, dict):
        scene_ambience = metadata.get("scene_ambience_generation")
    if not isinstance(scene_ambience, dict):
        scene_ambience = _resolve_scene_ambience_settings(None, False)
    response_contract = (
        str(metadata.get("speech_blocks_response_contract", "")).strip() or _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT
    )
    budget_metadata = report.get("budget_metadata")
    if not isinstance(budget_metadata, dict):
        budget_metadata = metadata.get("budget_metadata")
    status = str(operation_state.get("status", "not_started")) if isinstance(operation_state, dict) else "not_started"
    skipped_chunk_ids = _coerce_skipped_chunk_ids(metadata.get("skipped_chunk_ids"))
    return {
        "status": status,
        "source": source,
        "ai_profile_id": str(report.get("ai_profile_id", metadata.get("ai_profile_id", ""))).strip(),
        "instructions": str(
            report.get("additional_speech_block_instructions", metadata.get("additional_speech_block_instructions", ""))
        ),
        "scene_ambience": dict(scene_ambience),
        "response_contract": response_contract,
        "token_usage": token_usage_service.coerce_token_usage(report.get("token_usage", metadata.get("token_usage"))),
        "budget_metadata": dict(budget_metadata) if isinstance(budget_metadata, dict) else {},
        "checkpoint": _document_checkpoint(operation_state),
        "failure": {"skipped_chunk_ids": skipped_chunk_ids} if skipped_chunk_ids else None,
        "blocks": [dict(block) for block in speech_blocks],
    }


def _resolve_source_context(
    project_root: str | Path,
    document: SpeechBlocksDocumentPayload | None,
) -> _SpeechBlocksSourceContext:
    """
    @brief      Resolve source chunks and projection metadata once for one public operation.
    @param[in]  project_root Active project root folder.
    @param[in]  document Current Speech Blocks document or `None`.
    @return     Source chunks, total count, language, and kind with persisted fallbacks.
    @exception  None
    """
    blocks = document.get("blocks", []) if isinstance(document, dict) else []
    processed = len(
        {str(block.get("chunk_id", "")).strip() for block in blocks if isinstance(block, dict)}
        - {""}
    )
    source = document.get("source", {}) if isinstance(document, dict) else {}
    if not isinstance(source, dict):
        source = {}
    source_language = str(source.get("language", "")).strip()
    source_kind = str(source.get("kind", "")).strip()
    try:
        manifest = project_workspace_service.load_manifest(Path(project_root))
        source_resolution = resolve_source_chunks(Path(project_root), manifest)
    except (FileNotFoundError, OSError, ValueError, KeyError):
        return [], processed, source_language, source_kind
    source_chunks = [dict(chunk) for chunk in source_resolution["source_chunks"]]
    return (
        source_chunks,
        max(len(source_chunks), processed),
        source_language or str(source_resolution["selected_source_language"]),
        source_kind or str(source_resolution["source_kind"]),
    )


def _active_checkpoint_for_source(
    operation_state: OperationStatePayload, source_fingerprint: str
) -> dict[str, object] | None:
    """
    @brief      Retain an active checkpoint when an operator mutation leaves its source unchanged.
    @param[in]  operation_state Current projected operation state.
    @param[in]  source_fingerprint Fingerprint of the source used by the mutation.
    @return     Active checkpoint for the same source, if present.
    """
    metadata = operation_state.get("metadata", {})
    checkpoint = operation_state.get("resume_checkpoint")
    if (
        isinstance(metadata, dict)
        and metadata.get("source_snapshot_fingerprint") == source_fingerprint
        and isinstance(checkpoint, dict)
        and checkpoint.get("active_chunk_id")
    ):
        return checkpoint
    return None


def _covered_chunk_count(blocks: list[SpeechBlockPayload], checkpoint: object = None) -> int:
    """
    @brief      Count source chunks whose persisted rows are outside an active checkpoint.
    @param[in]  blocks Current Speech Blocks.
    @param[in]  checkpoint Optional resume checkpoint containing the active chunk identifier.
    @return     Count of covered source chunks.
    """
    active_chunk = str(checkpoint.get("active_chunk_id", "")).strip() if isinstance(checkpoint, dict) else ""
    return len({str(block.get("chunk_id", "")).strip() for block in blocks} - {"", active_chunk})


def _project_speech_blocks_report(
    document: SpeechBlocksDocumentPayload,
    source_chunk_count: int,
) -> SpeechBlocksReportPayload:
    """Project the legacy report shape from the single Speech Blocks document."""
    blocks = [block for block in document.get("blocks", []) if isinstance(block, dict)]
    source = document.get("source", {}) if isinstance(document.get("source"), dict) else {}
    checkpoint = document.get("checkpoint") if isinstance(document.get("checkpoint"), dict) else {}
    processed_chunk_count = _covered_chunk_count(blocks, checkpoint)
    total_chunk_count = max(int(source_chunk_count), processed_chunk_count)
    budget_metadata = document.get("budget_metadata")
    report = _rebuild_report(
        blocks,
        str(source.get("language", "")),
        str(source.get("kind", "")),
        str(document.get("ai_profile_id", "")),
        total_chunk_count,
        processed_chunk_count,
        document.get("token_usage", {}),
        dict(budget_metadata) if isinstance(budget_metadata, dict) else None,
    )
    scene_ambience = document.get("scene_ambience") if isinstance(document.get("scene_ambience"), dict) else {}
    report["additional_speech_block_instructions"] = str(document.get("instructions", ""))
    report["scene_ambience_generation"] = dict(scene_ambience)
    report["additional_speech_block_instructions_fingerprint"] = str(
        checkpoint.get("additional_speech_block_instructions_fingerprint", "")
    )
    return report


def _project_operation_state(
    document: SpeechBlocksDocumentPayload,
    source_chunk_count: int,
) -> OperationStatePayload:
    """Project the legacy operation-state shape from the single Speech Blocks document."""
    blocks = [block for block in document.get("blocks", []) if isinstance(block, dict)]
    source = document.get("source", {}) if isinstance(document.get("source"), dict) else {}
    checkpoint = document.get("checkpoint") if isinstance(document.get("checkpoint"), dict) else None
    processed_chunk_count = _covered_chunk_count(blocks, checkpoint)
    total_chunk_count = max(int(source_chunk_count), processed_chunk_count)
    warning_entries = _warning_records_from_blocks(blocks)
    scene_ambience = document.get("scene_ambience") if isinstance(document.get("scene_ambience"), dict) else {}
    log_relative_path = str(checkpoint.get("log_relative_path", "")).strip() if checkpoint else ""
    metadata: dict[str, object] = {
        "source_language": str(source.get("language", "")),
        "source_kind": str(source.get("kind", "")),
        "ai_profile_id": str(document.get("ai_profile_id", "")),
        "processed_chunk_count": processed_chunk_count,
        "total_chunk_count": total_chunk_count,
        "speech_block_count": len(blocks),
        "approved_block_count": _approved_block_count(blocks),
        "total_block_count": len(blocks),
        "warnings": warning_entries,
        "source_snapshot_fingerprint": str(source.get("fingerprint", "")),
        "log_relative_path": log_relative_path,
        "token_usage": token_usage_service.coerce_token_usage(document.get("token_usage")),
        "additional_speech_block_instructions": str(document.get("instructions", "")),
        "additional_speech_block_instructions_fingerprint": str(
            checkpoint.get("additional_speech_block_instructions_fingerprint", "")
        )
        if checkpoint
        else "",
        "scene_ambience_generation": dict(scene_ambience),
        "speech_blocks_response_contract": str(document.get("response_contract", ""))
        or _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT,
        "skipped_chunk_ids": _document_skipped_chunk_ids(document),
    }
    budget_metadata = document.get("budget_metadata")
    if isinstance(budget_metadata, dict) and budget_metadata:
        metadata["budget_metadata"] = dict(budget_metadata)
    status = str(document.get("status", "not_started"))
    # Older approval writes could leave an active checkpoint under a reviewed status.
    if checkpoint and checkpoint.get("active_chunk_id") and status in {"review_pending", "completed"}:
        status = "running"
    state = build_operation_state_payload(
        status=status,
        progress_current=processed_chunk_count,
        progress_total=total_chunk_count,
        mode="ai_assisted",
        warning_count=len(warning_entries),
        metadata=metadata,
        resume_checkpoint=dict(checkpoint) if isinstance(checkpoint, dict) else None,
    )
    state["started_at"] = str(checkpoint.get("run_token", "")).strip() if checkpoint else ""
    state["completed_at"] = None
    log_name = Path(log_relative_path).name if log_relative_path else ""
    state["artifact_paths"] = [config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME, *([log_name] if log_name else [])]
    return state


@trace_function(_SPEECH_BLOCKS_LOGGER)
def load_operation_state(
    project_root: str | Path,
    source_chunk_count: int | None = None,
) -> OperationStatePayload | None:
    """
    @brief      Load one optional Speech Blocks operation-state payload.
    @param[in]  project_root Active project root folder.
    @param[in]  source_chunk_count Optional count already resolved by the public caller.
    @return     Persisted operation-state payload or `None`.
    @exception  SpeechBlocksDocumentError Raised when the authoritative document exists but is unreadable or invalid.
    """
    document = load_speech_blocks_document(project_root)
    if document is None:
        return None
    if source_chunk_count is None:
        _source_chunks, source_chunk_count, _source_language, _source_kind = _resolve_source_context(
            project_root,
            document,
        )
    return _project_operation_state(document, source_chunk_count)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def load_speech_blocks_report(
    project_root: str | Path,
    source_chunk_count: int | None = None,
) -> SpeechBlocksReportPayload | None:
    """
    @brief      Load one optional Speech Blocks report payload.
    @param[in]  project_root Active project root folder.
    @param[in]  source_chunk_count Optional count already resolved by the public caller.
    @return     Persisted report payload or `None`.
    @exception  SpeechBlocksDocumentError Raised when the authoritative document exists but is unreadable or invalid.
    """
    document = load_speech_blocks_document(project_root)
    if document is None:
        return None
    if source_chunk_count is None:
        _source_chunks, source_chunk_count, _source_language, _source_kind = _resolve_source_context(
            project_root,
            document,
        )
    return _project_speech_blocks_report(document, source_chunk_count)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def load_input_source_chunks(project_root: str | Path) -> list[dict[str, object]]:
    """
    @brief      Re-resolve the current Speech Blocks source chunks from upstream artifacts.
    @param[in]  project_root Active project root folder.
    @return     Ordered source-chunk payloads, or an empty list when upstream is unavailable.
    @exception  None
    """
    resolved_project_root = Path(project_root)
    try:
        manifest = project_workspace_service.load_manifest(resolved_project_root)
        source_resolution = resolve_source_chunks(resolved_project_root, manifest)
    except (FileNotFoundError, OSError, ValueError, KeyError):
        return []
    return [dict(chunk) for chunk in source_resolution["source_chunks"]]


@trace_function(_SPEECH_BLOCKS_LOGGER)
def load_speech_blocks(
    project_root: str | Path, *, generation_manifest: dict[str, object] | None = None
) -> list[SpeechBlockPayload]:
    """
    @brief      Load one optional persisted Speech Blocks output payload.
    @param[in]  project_root Active project root folder.
    @param[in]  generation_manifest Optional manifest used to validate the translation before audio generation.
    @return     Ordered Speech Blocks payload list.
    @exception  ValueError Raised when the document is invalid or its translation is stale for generation.
    """
    document = load_speech_blocks_document(project_root)
    if document is None:
        return []
    if generation_manifest is not None:
        _validate_saved_translation_source(project_root, generation_manifest, document)
    blocks = document.get("blocks", [])
    if not isinstance(blocks, list):
        return []
    return sort_speech_blocks([_normalize_persisted_speech_block(item) for item in blocks if isinstance(item, dict)])


@trace_function(_SPEECH_BLOCKS_LOGGER)
def resolve_source_chunks(
    project_root: str | Path,
    manifest: dict[str, object],
    *,
    translation_document: object = _UNRESOLVED_TRANSLATION_DOCUMENT,
) -> dict[str, object]:
    """
    @brief      Resolve the Speech Blocks source chunks, preferring the approved translation.
    @details    Mirrors Character Discovery: when a translation exists, is complete, and every
                chunk is approved, the translated (repair-normalized) text is used regardless of
                the selected Character Voices language; otherwise the original chunking text is used.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  translation_document Optional translation document already read by a caller gate.
    @return     Source-resolution payload with normalized source chunks.
    @exception  ValueError Raised when chunking output is unavailable.
    """
    resolved_project_root = Path(project_root)
    original_chunks = sorted(
        chunking_document_service.load_chunks(resolved_project_root),
        key=lambda item: int(item.get("sequence_index", 0)),
    )
    if not original_chunks:
        raise ValueError("Run text chunking before starting Speech Blocks.")

    translated_resolution = _resolve_translated_source_chunks(
        resolved_project_root, original_chunks, translation_document,
        target_language=ai_translation_service.manifest_target_language(manifest),
    )
    if translated_resolution is not None:
        return translated_resolution

    original_language = narrator_definition_service.narrator_language_code(
        manifest.get("original_language", narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE)
    )
    return {
        "selected_source_language": original_language,
        "source_kind": "original",
        "source_chunks": [
            {
                "chunk_id": str(chunk.get("chunk_id", "")),
                "sequence_index": int(chunk.get("sequence_index", 0)),
                "text": str(chunk.get("text", "")),
                **_cleanup_provenance_fields(chunk),
            }
            for chunk in original_chunks
        ],
    }


def validate_current_translated_speech_source(project_root: str | Path, manifest: dict[str, object]) -> None:
    """
    @brief      Require a current approved translation before composing audio made from translated speech.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @return     None.
    @exception  ValueError Raised when translated Speech Blocks no longer match the verified source.
    """
    document = load_speech_blocks_document(project_root)
    if document is not None:
        _validate_saved_translation_source(project_root, manifest, document)


def _validate_saved_translation_source(
    project_root: str | Path, manifest: dict[str, object], document: SpeechBlocksDocumentPayload
) -> None:
    """@brief Check the source snapshot only for persisted translated Speech Blocks."""
    if document["source"]["kind"] == "translated":
        source = resolve_source_chunks(project_root, manifest)
        _require_matching_translation_source(document, source)


def _require_matching_translation_source(
    document: SpeechBlocksDocumentPayload, source: dict[str, object]
) -> None:
    """@brief Reject a translated source switch or stale translated snapshot."""
    saved_source = document["source"]
    source_kind = str(source["source_kind"])
    if saved_source["kind"] != "translated" and source_kind != "translated":
        return
    source_language = str(source["selected_source_language"])
    fingerprint = _build_source_fingerprint(source["source_chunks"], source_language, source_kind)
    if (
        saved_source["kind"] != source_kind
        or saved_source["language"] != source_language
        or saved_source["fingerprint"] != fingerprint
    ):
        raise ValueError("Speech Blocks use an outdated translation source. Reset and regenerate Speech Blocks.")


def _cleanup_provenance_fields(chunk: dict[str, object]) -> dict[str, object]:
    """
    @brief      Carry the cleanup boundary verdict from one chunking record into a source chunk.
    @details    Chunking already records how confident cleanup was about a paragraph rebuilt
                across a page break. Dropping it here would force Speech Blocks to re-derive
                information the pipeline has already computed correctly.
    @param[in]  chunk Persisted chunking record.
    @return     Cleanup provenance fields present on the record.
    @exception  None
    """
    return {
        "cleanup_boundary_confidence": str(chunk.get("cleanup_boundary_confidence", "") or ""),
        "cleanup_joined_across_page_break": bool(chunk.get("cleanup_joined_across_page_break", False)),
        "cleanup_warning_flags": list(chunk.get("cleanup_warning_flags", []) or []),
    }


def _resolve_translated_source_chunks(
    project_root: Path,
    original_chunks: list[dict[str, object]],
    translation_document: object = _UNRESOLVED_TRANSLATION_DOCUMENT,
    *,
    target_language: str | None = None,
) -> dict[str, object] | None:
    """
    @brief      Resolve translated source chunks when the translation is complete and fully approved.
    @param[in]  project_root Active project root folder.
    @param[in]  original_chunks Ordered original source chunks.
    @param[in]  translation_document Optional translation document already loaded by the caller.
    @return     Translated source-resolution payload, or `None` when the translation is absent,
                incomplete, or not fully approved (caller then falls back to the original text).
    @exception  None
    """
    try:
        if translation_document is _UNRESOLVED_TRANSLATION_DOCUMENT:
            translation_document = ai_translation_service.load_translation_document(project_root)
        translated = ai_translation_service.resolve_approved_translation(
            original_chunks, translation_document, target_language
        )
    except (OSError, ValueError):
        return None
    if translated is None:
        return None
    source_chunks = [
        {
            "chunk_id": str(chunk["chunk_id"]),
            "sequence_index": int(chunk["sequence_index"]),
            "text": str(chunk["text"]),
            **_cleanup_provenance_fields(chunk),
        }
        for chunk in translated
    ]
    return {
        "selected_source_language": str(translation_document["target_language"]).strip(),
        "source_kind": "translated",
        "source_chunks": source_chunks,
    }


@trace_function(_SPEECH_BLOCKS_LOGGER)
def start_or_continue_generation(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    settings_payload: dict[str, object] | None = None,
    progress_callback=None,
    cancel_requested=None,
    additional_speech_block_instructions: str | None = None,
    scene_ambience_enabled: bool | None = None,
) -> SpeechBlocksReportPayload:
    """
    @brief      Run Speech Blocks generation for the active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  settings_payload Optional application settings payload for cached TTS model budgets.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  additional_speech_block_instructions Optional operator-supplied Speech Blocks rules.
    @return     Final Speech Blocks report payload.
    @exception  ValueError Raised when prerequisites or profile data are invalid.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    """
    resolved_project_root = Path(project_root)
    source_resolution = resolve_source_chunks(resolved_project_root, manifest)
    source_chunks = list(source_resolution["source_chunks"])
    source_language = str(source_resolution["selected_source_language"])
    source_kind = str(source_resolution["source_kind"])
    resolved_voice_assignment_mode = voice_assignment_mode(manifest)
    speech_blocks_response_contract = _speech_blocks_response_contract(resolved_voice_assignment_mode)
    scene_ambience_settings = _resolve_scene_ambience_settings(settings_payload, scene_ambience_enabled)
    profile_id = str(ai_profile_payload.get("id", "")).strip()

    existing_document = load_speech_blocks_document(resolved_project_root)
    existing_state = (
        _project_operation_state(existing_document, len(source_chunks)) if existing_document is not None else {}
    )
    existing_report = (
        _project_speech_blocks_report(existing_document, len(source_chunks))
        if existing_document is not None
        else None
    )
    additional_speech_block_instructions = _resolve_additional_speech_block_instructions(
        additional_speech_block_instructions,
        existing_state,
    )
    additional_speech_block_instructions_fingerprint = _compute_generation_rules_fingerprint(
        additional_speech_block_instructions,
    )

    generation = speech_blocks_generation_service.prepare_chunk_generation(
        ai_profile_payload,
        source_language,
        _speaker_catalog(character_discovery_service.load_character_profiles(resolved_project_root)),
        resolved_voice_assignment_mode,
        settings_payload,
        additional_speech_block_instructions,
        scene_ambience_settings,
    )
    budget_metadata = generation.budget_metadata
    input_fingerprint = _build_source_fingerprint(source_chunks, source_language, source_kind)
    started_at = _resolve_started_at(existing_state)
    log_path = _resolve_log_path(resolved_project_root, started_at, existing_state)
    existing_blocks, start_chunk_index, start_offset = _restore_resume_state(
        resolved_project_root,
        existing_state,
        input_fingerprint,
        source_language,
        source_chunks,
        additional_speech_block_instructions_fingerprint,
    )
    skipped_chunk_ids = (
        set(_restore_skipped_chunk_ids(existing_state))
        if start_chunk_index > 0 or start_offset > 0 or existing_blocks
        else set()
    )
    token_usage = (
        token_usage_service.restore_token_usage(
            None if existing_report is None else existing_report.get("token_usage"),
            _metadata_token_usage(existing_state),
        )
        if start_chunk_index > 0 or start_offset > 0 or existing_blocks
        else token_usage_service.empty_token_usage()
    )
    if (
        existing_blocks
        and start_chunk_index >= len(source_chunks)
        and existing_state.get("status") not in {"running", "failed"}
    ):
        return (
            dict(existing_report)
            if isinstance(existing_report, dict)
            else _rebuild_report_with_prompt_rules(
                existing_blocks,
                source_language,
                source_kind,
                profile_id,
                len(source_chunks),
                len(source_chunks),
                token_usage,
                budget_metadata,
                additional_speech_block_instructions,
                scene_ambience_settings=scene_ambience_settings,
            )
        )

    _persist_state(
        resolved_project_root,
        existing_blocks,
        _rebuild_report_with_prompt_rules(
            existing_blocks,
            source_language,
            source_kind,
            profile_id,
            len(source_chunks),
            start_chunk_index,
            token_usage,
            budget_metadata,
            additional_speech_block_instructions,
            scene_ambience_settings=scene_ambience_settings,
        ),
        _build_operation_state_with_prompt_rules(
            resolved_project_root,
            source_chunks,
            existing_blocks,
            status="running",
            started_at=started_at,
            completed_at=None,
            source_language=source_language,
            source_kind=source_kind,
            profile_id=profile_id,
            input_fingerprint=input_fingerprint,
            log_path=log_path,
            token_usage=token_usage,
            next_chunk_index=start_chunk_index,
            budget_metadata=budget_metadata,
            additional_speech_block_instructions=additional_speech_block_instructions,
            scene_ambience_settings=scene_ambience_settings,
            speech_blocks_response_contract=speech_blocks_response_contract,
            skipped_chunk_ids=_ordered_skipped_chunk_ids(source_chunks, skipped_chunk_ids),
            active_chunk_id=(
                str(source_chunks[start_chunk_index].get("chunk_id", ""))
                if start_chunk_index < len(source_chunks) and start_offset > 0
                else ""
            ),
            next_source_offset=start_offset or None,
        ),
    )
    _emit_progress(
        progress_callback,
        start_chunk_index,
        len(source_chunks),
        "Speech Blocks generation in progress...",
        token_usage,
    )

    all_blocks = list(existing_blocks)
    covered_chunk_ids = {
        str(block.get("chunk_id", "")).strip()
        for block in all_blocks
        if str(block.get("chunk_id", "")).strip()
    }
    for chunk_index in range(start_chunk_index, len(source_chunks)):
        raise_if_cancelled(cancel_requested)
        source_chunk = _source_chunk_with_attribution_context(source_chunks, chunk_index)
        chunk_id = str(source_chunk.get("chunk_id", "")).strip()
        source_offset = start_offset if chunk_index == start_chunk_index else 0
        if chunk_id in covered_chunk_ids and not source_offset:
            continue
        prefix_blocks = [block for block in all_blocks if block["chunk_id"] == chunk_id]
        other_blocks = [block for block in all_blocks if block["chunk_id"] != chunk_id]

        def _persist_segment_progress(
            segment_blocks: list[SpeechBlockPayload],
            segment_token_usage: TokenUsagePayload,
            next_source_offset: int,
            base_blocks: list[SpeechBlockPayload] = other_blocks,
            base_usage: TokenUsagePayload = token_usage,
            current_chunk_index: int = chunk_index,
            current_chunk_id: str = chunk_id,
        ) -> None:
            """
            @brief      Persist the active chunk prefix and the exact consumed source position.
            @param[in]  segment_blocks Current active chunk blocks.
            @param[in]  segment_token_usage Usage from new requests for this chunk.
            @param[in]  next_source_offset Character offset into the original chunk.
            @param[in]  base_blocks Rows outside the current chunk.
            @param[in]  base_usage Usage before the current chunk.
            @param[in]  current_chunk_index Active source chunk index.
            @param[in]  current_chunk_id Active source chunk identifier.
            """
            persisted_blocks = _renumber_speech_blocks(source_chunks, [*base_blocks, *segment_blocks])
            persisted_usage = token_usage_service.merge_token_usage(base_usage, segment_token_usage)
            report = _rebuild_report_with_prompt_rules(
                persisted_blocks,
                source_language,
                source_kind,
                profile_id,
                len(source_chunks),
                current_chunk_index,
                persisted_usage,
                budget_metadata,
                additional_speech_block_instructions,
                scene_ambience_settings=scene_ambience_settings,
            )
            _persist_state(
                resolved_project_root,
                persisted_blocks,
                report,
                _build_operation_state_with_prompt_rules(
                    resolved_project_root,
                    source_chunks,
                    persisted_blocks,
                    status="running",
                    started_at=started_at,
                    completed_at=None,
                    source_language=source_language,
                    source_kind=source_kind,
                    profile_id=profile_id,
                    input_fingerprint=input_fingerprint,
                    log_path=log_path,
                    token_usage=persisted_usage,
                    next_chunk_index=current_chunk_index,
                    budget_metadata=budget_metadata,
                    additional_speech_block_instructions=additional_speech_block_instructions,
                    scene_ambience_settings=scene_ambience_settings,
                    speech_blocks_response_contract=speech_blocks_response_contract,
                    skipped_chunk_ids=_ordered_skipped_chunk_ids(source_chunks, skipped_chunk_ids),
                    active_chunk_id=current_chunk_id,
                    next_source_offset=next_source_offset,
                ),
            )

        try:
            chunk_blocks, chunk_token_usage = speech_blocks_generation_service.generate_chunk(
                generation,
                source_chunk,
                log_path,
                {
                    "operation_kind": "speech_blocks",
                    "stage_label": "speech_blocks_chunk",
                    "profile_id": profile_id,
                    "chunk_index": chunk_index + 1,
                    "chunk_total": len(source_chunks),
                    "chunk_id": chunk_id,
                },
                cancel_requested,
                source_offset=source_offset,
                prefix_blocks=prefix_blocks,
                segment_progress_callback=_persist_segment_progress,
            )
            skipped_chunk_ids.discard(chunk_id)
            chunk_refused = False
        except speech_blocks_generation_service.ChunkGenerationRefusedError:
            chunk_blocks, chunk_refused = [], True
            chunk_token_usage = token_usage_service.empty_token_usage()
            skipped_chunk_ids.add(chunk_id)
            covered_chunk_ids.discard(chunk_id)
        token_usage = token_usage_service.merge_token_usage(token_usage, chunk_token_usage)
        all_blocks = _renumber_speech_blocks(source_chunks, [*other_blocks, *chunk_blocks])
        if not chunk_refused:
            covered_chunk_ids.add(chunk_id)
        report = _rebuild_report_with_prompt_rules(
            all_blocks,
            source_language,
            source_kind,
            profile_id,
            len(source_chunks),
            chunk_index + 1,
            token_usage,
            budget_metadata,
            additional_speech_block_instructions,
            scene_ambience_settings=scene_ambience_settings,
        )
        _persist_state(
            resolved_project_root,
            all_blocks,
            report,
            _build_operation_state_with_prompt_rules(
                resolved_project_root,
                source_chunks,
                all_blocks,
                status="running",
                started_at=started_at,
                completed_at=None,
                source_language=source_language,
                source_kind=source_kind,
                profile_id=profile_id,
                input_fingerprint=input_fingerprint,
                log_path=log_path,
                token_usage=token_usage,
                next_chunk_index=chunk_index + 1,
                budget_metadata=budget_metadata,
                additional_speech_block_instructions=additional_speech_block_instructions,
                scene_ambience_settings=scene_ambience_settings,
                speech_blocks_response_contract=speech_blocks_response_contract,
                skipped_chunk_ids=_ordered_skipped_chunk_ids(source_chunks, skipped_chunk_ids),
            ),
        )
        _emit_progress(
            progress_callback,
            chunk_index + 1,
            len(source_chunks),
            "Speech Blocks generation in progress...",
            token_usage,
        )

    completed_at = _utc_now_iso()
    report = _rebuild_report_with_prompt_rules(
        all_blocks,
        source_language,
        source_kind,
        profile_id,
        len(source_chunks),
        len({str(block.get("chunk_id", "")).strip() for block in all_blocks} - {""}),
        token_usage,
        budget_metadata,
        additional_speech_block_instructions,
        scene_ambience_settings=scene_ambience_settings,
    )
    completed_state = _build_operation_state_with_prompt_rules(
        resolved_project_root,
        source_chunks,
        all_blocks,
        status="review_pending",
        started_at=started_at,
        completed_at=completed_at,
        source_language=source_language,
        source_kind=source_kind,
        profile_id=profile_id,
        input_fingerprint=input_fingerprint,
        log_path=log_path,
        token_usage=token_usage,
        next_chunk_index=None,
        budget_metadata=budget_metadata,
        additional_speech_block_instructions=additional_speech_block_instructions,
        scene_ambience_settings=scene_ambience_settings,
        speech_blocks_response_contract=speech_blocks_response_contract,
        skipped_chunk_ids=_ordered_skipped_chunk_ids(source_chunks, skipped_chunk_ids),
    )
    _persist_state(
        resolved_project_root,
        all_blocks,
        report,
        completed_state,
    )
    project_workspace_service.sync_manifest_operation_summary(
        resolved_project_root,
        "speech_blocks",
        completed_state,
        current_stage="character_voices_ready",
    )
    _emit_progress(
        progress_callback,
        len(source_chunks),
        len(source_chunks),
        "Speech Blocks generation completed.",
        token_usage,
    )
    return report


@trace_function(_SPEECH_BLOCKS_LOGGER)
def speaker_catalog_entries(project_root: str | Path) -> list[dict[str, object]]:
    """
    @brief      Return the editable Speech Blocks speaker catalog.
    @param[in]  project_root Active project root folder.
    @return     Ordered speaker catalog entries.
    @exception  None
    """
    return list(_speaker_catalog(character_discovery_service.load_character_profiles(Path(project_root))).values())


def speech_block_book_sort_key(speech_block: dict[str, object]) -> tuple[int, int, str]:
    """
    @brief      Build the canonical book-order sort key for one Speech Block.
    @param[in]  speech_block Speech Block or Audio Block payload.
    @return     Tuple of chunk order, chunk-local sequence index, and identifier.
    @exception  None
    """
    chunk_id = str(speech_block.get("chunk_id", "")).strip()
    return (
        _chunk_order_from_id(chunk_id),
        int(speech_block.get("sequence_index", 0)),
        str(speech_block.get("speech_block_id", "")).strip(),
    )


def sort_speech_blocks(speech_blocks: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Sort Speech Blocks or Audio Blocks in canonical book order.
    @param[in]  speech_blocks Speech Block or Audio Block payload list.
    @return     Ordered payload list.
    @exception  None
    """
    return sorted(speech_blocks, key=speech_block_book_sort_key)


def pause_duration_ms(text: object) -> int:
    """
    @brief      Parse a pause Speech Block duration from free-form text.
    @param[in]  text Candidate pause text.
    @return     Positive duration in milliseconds, or the configured default.
    @exception  None
    """
    match = re.search(r"\b(\d{1,9})\b", str(text))
    if match is None:
        return config.DEFAULT_SPEECH_BLOCK_PAUSE_DURATION_MS
    duration_ms = int(match.group(1))
    if duration_ms <= 0:
        return config.DEFAULT_SPEECH_BLOCK_PAUSE_DURATION_MS
    return duration_ms


@trace_function(_SPEECH_BLOCKS_LOGGER)
def reset_speech_blocks(project_root: str | Path) -> None:
    """
    @brief      Clear Speech Blocks plus downstream runtime data.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    """
    reset_operation_data(project_root, "speech_blocks", include_current=True)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def remove_speech_blocks_for_chunks(
    project_root: str | Path,
    chunk_ids: list[str] | tuple[str, ...] | set[str],
) -> SpeechBlocksReportPayload | None:
    """
    @brief      Remove persisted Speech Blocks for selected source chunks.
    @param[in]  project_root Active project root folder.
    @param[in]  chunk_ids Source chunk identifiers whose Speech Blocks must reset.
    @return     Updated report when Speech Blocks existed, otherwise `None`.
    @exception  None
    """
    normalized_chunk_ids = {str(chunk_id).strip() for chunk_id in chunk_ids if str(chunk_id).strip()}
    if not normalized_chunk_ids:
        return load_speech_blocks_report(project_root)
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    if not speech_blocks:
        return load_speech_blocks_report(resolved_project_root)
    preserved_blocks = [
        block for block in speech_blocks if str(block.get("chunk_id", "")).strip() not in normalized_chunk_ids
    ]
    return _persist_report_update(resolved_project_root, preserved_blocks)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def update_character_speech_block_display_name(
    project_root: str | Path,
    character_id: str,
    display_name: str | None = None,
) -> tuple[SpeechBlocksReportPayload | None, tuple[str, ...]]:
    """
    @brief      Update persisted Speech Block speaker names for one character without changing review state.
    @param[in]  project_root Active project root folder.
    @param[in]  character_id Character identifier whose display name changed.
    @param[in]  display_name Optional refreshed speaker display name.
    @return     Updated report, if Speech Blocks existed, plus affected block ids.
    @exception  None
    """
    normalized_character_id = str(character_id).strip()
    normalized_display_name = None if display_name is None else str(display_name).strip()
    if not normalized_character_id or not normalized_display_name:
        return load_speech_blocks_report(project_root), ()
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    if not speech_blocks:
        return load_speech_blocks_report(resolved_project_root), ()
    affected_block_ids: list[str] = []
    updated_blocks: list[SpeechBlockPayload] = []
    for block in speech_blocks:
        updated_block = dict(block)
        if _is_character_speech_block(updated_block, normalized_character_id):
            affected_block_ids.append(str(updated_block.get("speech_block_id", "")).strip())
            updated_block["speaker_display_name"] = normalized_display_name
        updated_blocks.append(updated_block)
    if not affected_block_ids:
        return load_speech_blocks_report(resolved_project_root), ()
    return _persist_report_update(resolved_project_root, updated_blocks), tuple(affected_block_ids)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def fallback_character_speech_blocks_to_narrator(
    project_root: str | Path,
    character_id: str,
) -> tuple[SpeechBlocksReportPayload | None, tuple[str, ...]]:
    """
    @brief      Move Speech Blocks assigned to a deleted character back to narrator review.
    @param[in]  project_root Active project root folder.
    @param[in]  character_id Deleted character identifier.
    @return     Updated report, if Speech Blocks existed, plus affected block ids.
    @exception  None
    """
    normalized_character_id = str(character_id).strip()
    if not normalized_character_id:
        return load_speech_blocks_report(project_root), ()
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    if not speech_blocks:
        return load_speech_blocks_report(resolved_project_root), ()
    affected_block_ids: list[str] = []
    updated_blocks: list[SpeechBlockPayload] = []
    for block in speech_blocks:
        updated_block = dict(block)
        if _is_character_speech_block(updated_block, normalized_character_id):
            affected_block_ids.append(str(updated_block.get("speech_block_id", "")).strip())
            updated_block["speaker_kind"] = SPEAKER_KIND_NARRATOR
            updated_block["speaker_id"] = _NARRATOR_SPEAKER_ID
            updated_block["speaker_display_name"] = _NARRATOR_DISPLAY_NAME
            updated_block["approved"] = False
            updated_block["approved_at"] = None
        updated_blocks.append(updated_block)
    if not affected_block_ids:
        return load_speech_blocks_report(resolved_project_root), ()
    return _persist_report_update(resolved_project_root, updated_blocks), tuple(affected_block_ids)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def insert_speech_block(
    project_root: str | Path,
    chunk_id: str,
    after_speech_block_id: str | None = None,
) -> tuple[SpeechBlocksReportPayload, str]:
    """
    @brief      Insert one manual Speech Block into a selected chunk.
    @param[in]  project_root Active project root folder.
    @param[in]  chunk_id Source chunk that receives the new block.
    @param[in]  after_speech_block_id Optional block id after which to insert.
    @return     Updated report payload and final inserted Speech Block id.
    @exception  ValueError Raised when Speech Blocks state, chunk, or after-block is invalid.
    """
    resolved_project_root = Path(project_root)
    selected_chunk_id = str(chunk_id).strip()
    document = load_speech_blocks_document(resolved_project_root)
    source_context = _resolve_source_context(resolved_project_root, document)
    source_chunks, _source_chunk_count, _source_language, _source_kind = source_context
    if not source_chunks:
        raise ValueError("Source chunks are required before inserting a Speech Block.")
    if not any(str(chunk.get("chunk_id", "")).strip() == selected_chunk_id for chunk in source_chunks):
        raise ValueError("The selected chunk was not found.")
    speech_blocks = load_speech_blocks(resolved_project_root)
    blocks_for_chunk = [block for block in speech_blocks if str(block.get("chunk_id", "")).strip() == selected_chunk_id]
    insertion_index = max((int(block.get("sequence_index", 0)) for block in blocks_for_chunk), default=0) + 1
    normalized_after_id = str(after_speech_block_id or "").strip()
    if normalized_after_id:
        after_block = _speech_block_by_id(blocks_for_chunk, normalized_after_id)
        if after_block is None:
            raise ValueError("The selected Speech Block was not found in the selected chunk.")
        insertion_index = int(after_block.get("sequence_index", 0)) + 1
    for block in speech_blocks:
        if (
            str(block.get("chunk_id", "")).strip() == selected_chunk_id
            and int(block.get("sequence_index", 0)) >= insertion_index
        ):
            block["sequence_index"] = int(block.get("sequence_index", 0)) + 1
    inserted_id = _next_unused_speech_block_id(selected_chunk_id, _used_speech_block_ids(speech_blocks))
    speech_blocks.append(_manual_inserted_speech_block(selected_chunk_id, insertion_index, inserted_id))
    updated_report = _persist_report_update(resolved_project_root, speech_blocks, source_context)
    inserted_block = _speech_block_by_id(load_speech_blocks(resolved_project_root), inserted_id)
    if inserted_block is None:
        raise ValueError("The inserted Speech Block could not be reloaded.")
    return updated_report, str(inserted_block.get("speech_block_id", ""))


@trace_function(_SPEECH_BLOCKS_LOGGER)
def delete_speech_block(project_root: str | Path, speech_block_id: str) -> SpeechBlocksReportPayload:
    """
    @brief      Delete one selected Speech Block and renumber its chunk.
    @details    This service owns Speech Blocks persistence only; callers that manage downstream
                Audio Blocks must remove the deleted identifier's row and generated artifacts.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Target Speech Block identifier.
    @return     Updated Speech Blocks report payload.
    @exception  ValueError Raised when the block is unknown.
    """
    resolved_project_root = Path(project_root)
    normalized_id = str(speech_block_id).strip()
    speech_blocks = load_speech_blocks(resolved_project_root)
    if _speech_block_by_id(speech_blocks, normalized_id) is None:
        raise ValueError("The selected Speech Block was not found.")
    return _persist_report_update(
        resolved_project_root,
        [block for block in speech_blocks if str(block.get("speech_block_id", "")).strip() != normalized_id],
    )


@trace_function(_SPEECH_BLOCKS_LOGGER)
def clear_speech_block_warning_flags(project_root: str | Path, speech_block_id: str) -> SpeechBlocksReportPayload:
    """
    @brief      Clear warning flags for one selected Speech Block without changing approval or audio inputs.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Target Speech Block identifier.
    @return     Updated Speech Blocks report payload.
    @exception  ValueError Raised when the block is unknown.
    """
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    selected_block = _speech_block_by_id(speech_blocks, speech_block_id)
    if selected_block is None:
        raise ValueError("The selected Speech Block was not found.")
    selected_block["warning_flags"] = []
    return _persist_compact_review_update(resolved_project_root, speech_blocks)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def approve_all_speech_blocks(project_root: str | Path) -> SpeechBlocksReportPayload:
    """
    @brief      Approve every generated Speech Block.
    @param[in]  project_root Active project root folder.
    @return     Updated Speech Blocks report payload.
    @exception  None
    """
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    approved_at = _utc_now_iso()
    for block in speech_blocks:
        block["approved"] = True
        block["approved_at"] = approved_at
        block["warning_flags"] = []
    return _persist_report_update(resolved_project_root, speech_blocks)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def approve_speech_block(project_root: str | Path, speech_block_id: str) -> SpeechBlocksReportPayload:
    """
    @brief      Approve one generated Speech Block.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Target Speech Block identifier.
    @return     Updated Speech Blocks report payload.
    @exception  ValueError Raised when the block is unknown.
    """
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    selected_block = _speech_block_by_id(speech_blocks, speech_block_id)
    if selected_block is None:
        raise ValueError("The selected Speech Block was not found.")
    selected_block["approved"] = True
    selected_block["approved_at"] = _utc_now_iso()
    selected_block["warning_flags"] = []
    return _persist_compact_review_update(resolved_project_root, speech_blocks)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def unapprove_speech_block(project_root: str | Path, speech_block_id: str) -> SpeechBlocksReportPayload:
    """
    @brief      Clear approval for one generated Speech Block.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Target Speech Block identifier.
    @return     Updated Speech Blocks report payload.
    @exception  ValueError Raised when the block is unknown.
    """
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    selected_block = _speech_block_by_id(speech_blocks, speech_block_id)
    if selected_block is None:
        raise ValueError("The selected Speech Block was not found.")
    selected_block["approved"] = False
    selected_block["approved_at"] = None
    return _persist_compact_review_update(resolved_project_root, speech_blocks)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def update_speech_block(
    project_root: str | Path,
    speech_block_id: str,
    speaker_id: str,
    content_kind: str,
    edit_payload: object,
) -> SpeechBlocksReportPayload:
    """
    @brief      Save one manually edited Speech Block and clear its warning indicator.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Target Speech Block identifier.
    @param[in]  speaker_id Selected speaker identifier.
    @param[in]  content_kind Selected content-kind token.
    @param[in]  edit_payload Edited text or Scene Ambience field payload.
    @return     Updated Speech Blocks report payload.
    @exception  ValueError Raised when the block or speaker is unknown.
    """
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    selected_block = _speech_block_by_id(speech_blocks, speech_block_id)
    if selected_block is None:
        raise ValueError("The selected Speech Block was not found.")
    normalized_content_kind = _normalize_content_kind(content_kind)
    manifest = project_workspace_service.load_manifest(resolved_project_root)
    narrator_only = voice_assignment_mode(manifest) == "same_narrator"
    if narrator_only and not _is_operation_content_kind(normalized_content_kind):
        normalized_content_kind = CONTENT_KIND_NARRATION
    if _is_operation_content_kind(normalized_content_kind):
        speaker_entry = _operation_speaker_entry(normalized_content_kind)
    elif narrator_only:
        speaker_entry = _speaker_catalog(character_discovery_service.load_character_profiles(resolved_project_root))[
            _NARRATOR_SPEAKER_ID
        ]
    else:
        speaker_catalog = _speaker_catalog(character_discovery_service.load_character_profiles(resolved_project_root))
        speaker_entry = speaker_catalog.get(str(speaker_id).strip())
        if speaker_entry is None:
            raise ValueError("The selected speaker was not found.")
    selected_block["speaker_kind"] = str(speaker_entry.get("speaker_kind", SPEAKER_KIND_NARRATOR))
    selected_block["speaker_id"] = str(speaker_entry.get("speaker_id", _NARRATOR_SPEAKER_ID))
    selected_block["speaker_display_name"] = str(speaker_entry.get("display_name", _NARRATOR_DISPLAY_NAME))
    if normalized_content_kind == CONTENT_KIND_SCENE_AMBIENCE:
        ambience_payload = _normalize_scene_ambience_edit_payload(edit_payload, selected_block)
        selected_block["content_kind"] = CONTENT_KIND_SCENE_AMBIENCE
        selected_block["text"] = str(ambience_payload["sound_prompt"])
        selected_block["sound_prompt"] = str(ambience_payload["sound_prompt"])
        selected_block["negative_prompt"] = str(ambience_payload["negative_prompt"])
        selected_block["duration_seconds"] = float(ambience_payload["duration_seconds"])
        if str(selected_block.get("ambience_position", "")).strip() not in {"opener", "closer", "scene_change"}:
            selected_block["ambience_position"] = "scene_change"
    else:
        selected_block["content_kind"] = normalized_content_kind
        selected_block["text"] = str(edit_payload)
        for field_name in ("sound_prompt", "negative_prompt", "duration_seconds"):
            selected_block.pop(field_name, None)
    selected_block["warning_flags"] = []
    selected_block["approved"] = False
    selected_block["approved_at"] = None
    return _persist_report_update(resolved_project_root, speech_blocks)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def regenerate_chunk_speech_blocks(
    project_root: str | Path,
    manifest: dict[str, object],
    chunk_id: str,
    ai_profile_payload: dict[str, object],
    settings_payload: dict[str, object] | None = None,
    progress_callback=None,
    cancel_requested=None,
    additional_speech_block_instructions: str | None = None,
    scene_ambience_enabled: bool | None = None,
) -> SpeechBlocksReportPayload:
    """
    @brief      Re-run Speech Blocks splitting for one selected source chunk.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  chunk_id Source chunk identifier to regenerate.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  settings_payload Optional application settings payload for cached TTS model budgets.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  additional_speech_block_instructions Optional operator-supplied Speech Blocks rules.
    @return     Updated Speech Blocks report payload.
    @exception  ValueError Raised when prerequisites or target chunk are invalid.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    """
    resolved_project_root = Path(project_root)
    source_resolution = resolve_source_chunks(resolved_project_root, manifest)
    source_chunks = list(source_resolution["source_chunks"])
    source_language = str(source_resolution["selected_source_language"])
    source_kind = str(source_resolution["source_kind"])
    resolved_voice_assignment_mode = voice_assignment_mode(manifest)
    speech_blocks_response_contract = _speech_blocks_response_contract(resolved_voice_assignment_mode)
    scene_ambience_settings = _resolve_scene_ambience_settings(settings_payload, scene_ambience_enabled)
    profile_id = str(ai_profile_payload.get("id", "")).strip()
    selected_chunk = next(
        (chunk for chunk in source_chunks if str(chunk.get("chunk_id", "")).strip() == chunk_id),
        None,
    )
    if selected_chunk is None:
        raise ValueError("The selected chunk was not found.")
    existing_document = load_speech_blocks_document(resolved_project_root)
    if existing_document is not None:
        _require_matching_translation_source(existing_document, source_resolution)
    existing_report = (
        _project_speech_blocks_report(existing_document, len(source_chunks))
        if existing_document is not None
        else None
    )
    existing_state = (
        _project_operation_state(existing_document, len(source_chunks)) if existing_document is not None else {}
    )
    additional_speech_block_instructions = _resolve_additional_speech_block_instructions(
        additional_speech_block_instructions,
        existing_state,
    )
    token_usage = token_usage_service.restore_token_usage(
        None if existing_report is None else existing_report.get("token_usage"),
        _metadata_token_usage(existing_state),
    )
    started_at = _resolve_started_at(existing_state)
    log_path = _resolve_log_path(resolved_project_root, started_at, existing_state)
    generation = speech_blocks_generation_service.prepare_chunk_generation(
        ai_profile_payload,
        source_language,
        _speaker_catalog(character_discovery_service.load_character_profiles(resolved_project_root)),
        resolved_voice_assignment_mode,
        settings_payload,
        additional_speech_block_instructions,
        scene_ambience_settings,
    )
    budget_metadata = generation.budget_metadata
    raise_if_cancelled(cancel_requested)
    selected_chunk_index = source_chunks.index(selected_chunk)
    selected_chunk = _source_chunk_with_attribution_context(source_chunks, selected_chunk_index)
    new_blocks, chunk_token_usage = speech_blocks_generation_service.generate_chunk(
        generation,
        selected_chunk,
        log_path,
        {
            "operation_kind": "speech_blocks",
            "stage_label": "speech_blocks_chunk_resplit",
            "profile_id": profile_id,
            "chunk_id": chunk_id,
        },
        cancel_requested,
    )
    token_usage = token_usage_service.merge_token_usage(token_usage, chunk_token_usage)
    existing_blocks = [
        block
        for block in load_speech_blocks(resolved_project_root)
        if str(block.get("chunk_id", "")).strip() != chunk_id
    ]
    all_blocks = _renumber_speech_blocks(source_chunks, [*existing_blocks, *new_blocks])
    input_fingerprint = _build_source_fingerprint(source_chunks, source_language, source_kind)
    active_checkpoint = _active_checkpoint_for_source(existing_state, input_fingerprint)
    if active_checkpoint is not None and active_checkpoint["active_chunk_id"] == chunk_id:
        active_checkpoint = None
    if active_checkpoint is not None:
        additional_speech_block_instructions = _restore_persisted_additional_speech_block_instructions(
            existing_report, existing_state
        )
    completed_at = _utc_now_iso()
    report = _rebuild_report_with_prompt_rules(
        all_blocks,
        source_language,
        source_kind,
        profile_id,
        len(source_chunks),
        _covered_chunk_count(all_blocks, active_checkpoint),
        token_usage,
        budget_metadata,
        additional_speech_block_instructions,
        scene_ambience_settings=scene_ambience_settings,
    )
    resplit_state = _build_operation_state_with_prompt_rules(
        resolved_project_root,
        source_chunks,
        all_blocks,
        status="review_pending",
        started_at=started_at,
        completed_at=completed_at,
        source_language=source_language,
        source_kind=source_kind,
        profile_id=profile_id,
        input_fingerprint=input_fingerprint,
        log_path=log_path,
        token_usage=token_usage,
        next_chunk_index=None,
        budget_metadata=budget_metadata,
        additional_speech_block_instructions=additional_speech_block_instructions,
        scene_ambience_settings=scene_ambience_settings,
        speech_blocks_response_contract=speech_blocks_response_contract,
        skipped_chunk_ids=_uncovered_skipped_chunk_ids(existing_state, all_blocks),
    )
    if active_checkpoint is not None:
        resplit_state["status"] = "running"
        resplit_state["resume_checkpoint"] = active_checkpoint
    _persist_state(
        resolved_project_root,
        all_blocks,
        report,
        resplit_state,
    )
    project_workspace_service.sync_manifest_operation_summary(
        resolved_project_root,
        "speech_blocks",
        resplit_state,
        current_stage="character_voices_ready",
    )
    _emit_progress(progress_callback, 1, 1, "Selected chunk Speech Blocks re-split completed.", token_usage)
    return report


# LOCAL HELPERS


def _speaker_catalog(character_profiles: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """
    @brief      Build the allowed speaker catalog for one Speech Blocks run.
    @param[in]  character_profiles Persisted character profiles.
    @return     Mapping from speaker identifier to stable speaker metadata.
    @exception  None
    """
    catalog = {
        _NARRATOR_SPEAKER_ID: {
            "speaker_id": _NARRATOR_SPEAKER_ID,
            "speaker_kind": SPEAKER_KIND_NARRATOR,
            "display_name": _NARRATOR_DISPLAY_NAME,
        }
    }
    for character_profile in character_profiles:
        character_id = str(character_profile.get("character_id", "")).strip()
        if not character_id:
            continue
        catalog[character_id] = {
            "speaker_id": character_id,
            "speaker_kind": SPEAKER_KIND_CHARACTER,
            "display_name": str(character_profile.get("canonical_name", "")).strip() or character_id,
            "aliases": _speaker_catalog_aliases(character_profile),
            "source_language_evidence": _speaker_catalog_evidence(character_profile),
        }
    return catalog


def _speaker_catalog_aliases(character_profile: dict[str, object]) -> list[str]:
    """
    @brief      Normalize source-language aliases for a Speech Blocks speaker catalog entry.
    @param[in]  character_profile Persisted Character Discovery profile.
    @return     Ordered unique alias strings.
    @exception  None
    """
    aliases: list[str] = []
    for raw_alias in character_profile.get("aliases", []):
        alias = str(raw_alias).strip()
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases


def _speaker_catalog_evidence(character_profile: dict[str, object]) -> list[dict[str, object]]:
    """
    @brief      Build compact source-language attribution evidence for one catalog speaker.
    @param[in]  character_profile Persisted Character Discovery profile.
    @return     Compact evidence rows safe for prompt context.
    @exception  None
    """
    evidence_rows: list[dict[str, object]] = []
    for raw_evidence in character_profile.get("evidence", []):
        if not isinstance(raw_evidence, dict):
            continue
        chunk_id = str(raw_evidence.get("chunk_id", "")).strip()
        text = str(raw_evidence.get("source_excerpt", raw_evidence.get("text", ""))).strip()
        if not chunk_id or not text:
            continue
        evidence_rows.append({"chunk_id": chunk_id, "text": _prompt_excerpt(text, 160)})
        if len(evidence_rows) >= 3:
            break
    return evidence_rows


def voice_assignment_mode(manifest: dict[str, object]) -> str:
    """
    @brief      Resolve the active Speech Blocks generation mode.
    @param[in]  manifest Active project manifest payload.
    @return     Supported voice-assignment mode.
    @exception  None
    """
    mode = str(manifest.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)).strip()
    if mode in config.TTS_VOICE_ASSIGNMENT_MODE_OPTIONS:
        return mode
    return config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE


def _speech_blocks_response_contract(voice_assignment_mode: str) -> str:
    """
    @brief      Resolve the active Speech Blocks AI response contract token.
    @param[in]  voice_assignment_mode Active project voice-assignment mode.
    @return     Response contract token persisted with resumable state.
    @exception  None
    """
    if str(voice_assignment_mode).strip() == "same_narrator":
        return _SPEECH_BLOCKS_DETERMINISTIC_NARRATOR_CONTRACT
    return _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT


def _resolve_additional_speech_block_instructions(
    additional_speech_block_instructions: str | None,
    existing_state: dict[str, object],
) -> str:
    """
    @brief      Resolve operator rules for a new or resumed Speech Blocks generation run.
    @param[in]  additional_speech_block_instructions New operator instructions or None when resuming.
    @param[in]  existing_state Existing Speech Blocks operation state.
    @return     Normalized operator Speech Blocks instructions.
    @exception  None
    """
    if additional_speech_block_instructions is not None:
        return _normalized_additional_speech_block_instructions(additional_speech_block_instructions)
    if existing_state.get("mode") != "ai_assisted" or str(existing_state.get("status", "")) not in {
        "running",
        "failed",
    }:
        return ""
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return ""
    return _normalized_additional_speech_block_instructions(metadata.get("additional_speech_block_instructions"))


def _resolve_scene_ambience_settings(
    settings_payload: dict[str, object] | None,
    enabled_override: bool | None = None,
) -> dict[str, object]:
    """
    @brief      Resolve scene-ambience generation settings for Speech Blocks.
    @param[in]  settings_payload Optional application settings payload.
    @param[in]  enabled_override Optional page-level enablement override.
    @return     Normalized scene-ambience settings payload.
    @exception  None
    """
    payload = settings_payload if isinstance(settings_payload, dict) else {}
    placement = str(
        payload.get(
            "scene_ambience_placement",
            payload.get("placement_policy", config.DEFAULT_SCENE_AMBIENCE_PLACEMENT),
        )
    ).strip()
    if placement not in config.SCENE_AMBIENCE_PLACEMENT_OPTIONS:
        placement = config.DEFAULT_SCENE_AMBIENCE_PLACEMENT
    enabled = placement != "none"
    if enabled_override is not None:
        enabled = bool(enabled_override)
    duration_seconds = _positive_float(
        payload.get("scene_ambience_duration_seconds", payload.get("duration_seconds")),
        float(config.DEFAULT_SCENE_AMBIENCE_DURATION_SECONDS),
    )
    max_blocks_per_sequence = _positive_int(
        payload.get("scene_ambience_max_blocks_per_sequence", payload.get("max_blocks_per_sequence")),
        int(config.DEFAULT_SCENE_AMBIENCE_MAX_BLOCKS_PER_SEQUENCE),
    )
    allowed_positions = _scene_ambience_allowed_positions(placement)
    negative_prompt = str(
        payload.get(
            "scene_ambience_negative_prompt",
            payload.get("negative_prompt", config.DEFAULT_SCENE_AMBIENCE_NEGATIVE_PROMPT),
        )
    ).strip()
    return {
        "enabled": enabled,
        "placement_policy": placement,
        "duration_seconds": duration_seconds,
        "max_blocks_per_sequence": max_blocks_per_sequence,
        "allowed_positions": allowed_positions,
        "negative_prompt": negative_prompt or config.DEFAULT_SCENE_AMBIENCE_NEGATIVE_PROMPT,
    }


def scene_ambience_enabled(settings_payload: dict[str, object] | None) -> bool:
    """@brief Return whether Speech Blocks is configured to add scene ambience."""
    return bool(_resolve_scene_ambience_settings(settings_payload)["enabled"])


def _scene_ambience_allowed_positions(placement_policy: str) -> list[str]:
    """
    @brief      Resolve allowed scene-ambience positions from one placement policy.
    @param[in]  placement_policy Persisted scene-ambience placement token.
    @return     Ordered allowed ambience-position tokens.
    @exception  None
    """
    return {
        "none": [],
        "openers_and_closers": ["opener", "closer"],
        "openers_closers_and_scene_changes": ["opener", "closer", "scene_change"],
    }.get(str(placement_policy).strip(), [])


def _compute_generation_rules_fingerprint(additional_speech_block_instructions: str) -> str:
    """
    @brief      Compute one stable fingerprint for operator prompt rules.
    @param[in]  additional_speech_block_instructions Operator-supplied prompt rules.
    @return     SHA-256 fingerprint for resumable Speech Blocks runs.
    @exception  None
    """
    return _compute_prompt_fingerprint(additional_speech_block_instructions)


def _restore_persisted_additional_speech_block_instructions(
    report: dict[str, object] | None,
    operation_state: dict[str, object] | None,
) -> str:
    """
    @brief      Restore persisted operator Speech Blocks rules from report or state.
    @param[in]  report Speech Blocks report payload.
    @param[in]  operation_state Speech Blocks operation-state payload.
    @return     Normalized operator Speech Blocks instructions.
    @exception  None
    """
    if isinstance(report, dict):
        restored_report_value = _normalized_additional_speech_block_instructions(
            report.get("additional_speech_block_instructions")
        )
        if restored_report_value:
            return restored_report_value
    if isinstance(operation_state, dict):
        metadata = operation_state.get("metadata", {})
        if isinstance(metadata, dict):
            restored_metadata_value = _normalized_additional_speech_block_instructions(
                metadata.get("additional_speech_block_instructions")
            )
            if restored_metadata_value:
                return restored_metadata_value
    return ""


def _restore_persisted_scene_ambience_settings(
    report: dict[str, object] | None,
    operation_state: dict[str, object] | None,
) -> dict[str, object]:
    """
    @brief      Restore persisted Scene Ambience generation settings from report or state.
    @param[in]  report Speech Blocks report payload.
    @param[in]  operation_state Speech Blocks operation-state payload.
    @return     Normalized Scene Ambience generation settings.
    @exception  None
    """
    for candidate in (
        report.get("scene_ambience_generation") if isinstance(report, dict) else None,
        (
            dict(operation_state.get("metadata", {})).get("scene_ambience_generation")
            if isinstance(operation_state, dict) and isinstance(operation_state.get("metadata"), dict)
            else None
        ),
    ):
        if isinstance(candidate, dict):
            return _resolve_scene_ambience_settings(candidate, bool(candidate.get("enabled", False)))
    return _resolve_scene_ambience_settings(None, False)


def _restore_persisted_speech_blocks_response_contract(operation_state: dict[str, object] | None) -> str:
    """
    @brief      Restore the persisted Speech Blocks response contract from operation state.
    @param[in]  operation_state Speech Blocks operation-state payload.
    @return     Known response contract token or the narrator+character contract.
    @exception  None
    """
    if not isinstance(operation_state, dict):
        return _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT
    metadata = operation_state.get("metadata", {})
    resume_checkpoint = operation_state.get("resume_checkpoint", {})
    response_contract = str(
        (metadata.get("speech_blocks_response_contract") if isinstance(metadata, dict) else "")
        or (resume_checkpoint.get("speech_blocks_response_contract") if isinstance(resume_checkpoint, dict) else "")
        or ""
    ).strip()
    if response_contract in {
        _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT,
        _SPEECH_BLOCKS_NARRATOR_BOUNDARY_CONTRACT,
        _SPEECH_BLOCKS_DETERMINISTIC_NARRATOR_CONTRACT,
    }:
        return response_contract
    return _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT


def _compute_prompt_fingerprint(prompt_text: str) -> str:
    """
    @brief      Compute a stable fingerprint for operator-supplied prompt rules.
    @param[in]  prompt_text Operator prompt-rule text.
    @return     SHA-256 fingerprint for the prompt-rule text.
    @exception  None
    """
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


def _source_chunk_with_attribution_context(
    source_chunks: list[dict[str, object]],
    chunk_index: int,
) -> dict[str, object]:
    """
    @brief      Attach previous/next non-selectable attribution context to one source chunk.
    @param[in]  source_chunks Ordered source chunks.
    @param[in]  chunk_index Current chunk index.
    @return     Source chunk payload with compact attribution context fields.
    @exception  None
    """
    source_chunk = dict(source_chunks[chunk_index])
    previous_text = str(source_chunks[chunk_index - 1].get("text", "")) if chunk_index > 0 else ""
    next_text = str(source_chunks[chunk_index + 1].get("text", "")) if chunk_index + 1 < len(source_chunks) else ""
    source_chunk["previous_context"] = _prompt_excerpt(previous_text, 360, tail=True)
    source_chunk["next_context"] = _prompt_excerpt(next_text, 360)
    return source_chunk


def _prompt_excerpt(text: str, limit: int, *, tail: bool = False) -> str:
    """
    @brief      Normalize and trim a prompt context excerpt.
    @param[in]  text Source text.
    @param[in]  limit Maximum character count.
    @param[in]  tail When true, keep the tail of oversized text.
    @return     Compact excerpt.
    @exception  None
    """
    normalized = re.sub(r"\s+", " ", str(text)).strip()
    if limit <= 0 or len(normalized) <= limit:
        return normalized
    if tail:
        return normalized[-limit:].lstrip()
    return normalized[:limit].rstrip()


def _positive_float(value: object, fallback: float) -> float:
    """
    @brief      Normalize one positive float with fallback.
    @param[in]  value Candidate float value.
    @param[in]  fallback Fallback float value.
    @return     Positive float value.
    @exception  None
    """
    try:
        normalized_value = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    return normalized_value if normalized_value > 0.0 else float(fallback)


def _positive_int(value: object, fallback: int) -> int:
    """
    @brief      Normalize one positive integer with fallback.
    @param[in]  value Candidate integer value.
    @param[in]  fallback Fallback integer value.
    @return     Positive integer value.
    @exception  None
    """
    try:
        normalized_value = int(value)
    except (TypeError, ValueError):
        return int(fallback)
    return normalized_value if normalized_value > 0 else int(fallback)


def _normalize_scene_ambience_edit_payload(
    edit_payload: object,
    existing_block: SpeechBlockPayload,
) -> dict[str, object]:
    """
    @brief      Normalize dedicated Scene Ambience edit fields.
    @param[in]  edit_payload Edited Scene Ambience payload.
    @param[in]  existing_block Existing Speech Block payload used for field fallback.
    @return     Normalized Scene Ambience edit payload.
    @exception  None
    """
    payload = edit_payload if isinstance(edit_payload, dict) else {"sound_prompt": str(edit_payload)}
    sound_prompt = str(payload.get("sound_prompt", payload.get("text", ""))).strip()
    if not sound_prompt:
        sound_prompt = str(existing_block.get("sound_prompt", existing_block.get("text", ""))).strip()
    return {
        "sound_prompt": sound_prompt,
        "negative_prompt": str(payload.get("negative_prompt", "")).strip(),
        "duration_seconds": _positive_float(
            payload.get("duration_seconds"),
            _positive_float(
                existing_block.get("duration_seconds"),
                float(config.DEFAULT_SCENE_AMBIENCE_DURATION_SECONDS),
            ),
        ),
    }


def _normalize_persisted_speech_block(payload: dict[str, object]) -> SpeechBlockPayload:
    """
    @brief      Normalize one persisted Speech Blocks payload.
    @param[in]  payload Raw persisted payload.
    @return     Normalized Speech Blocks payload.
    @exception  None
    """
    sequence_index = int(payload.get("sequence_index", 0))
    chunk_id = str(payload.get("chunk_id", "")).strip()
    speech_block_id = str(payload.get("speech_block_id", "")).strip() or (
        speech_blocks_normalization_service.speech_block_id(chunk_id, sequence_index)
    )
    speaker_kind = str(payload.get("speaker_kind", SPEAKER_KIND_NARRATOR)).strip() or SPEAKER_KIND_NARRATOR
    speaker_id = str(payload.get("speaker_id", _NARRATOR_SPEAKER_ID)).strip() or _NARRATOR_SPEAKER_ID
    speaker_display_name = str(payload.get("speaker_display_name", _NARRATOR_DISPLAY_NAME)).strip()
    if not speaker_display_name:
        speaker_display_name = _NARRATOR_DISPLAY_NAME
    content_kind = _normalize_content_kind(payload.get("content_kind", CONTENT_KIND_NARRATION))
    if _is_operation_content_kind(content_kind):
        operation_entry = _operation_speaker_entry(content_kind)
        speaker_kind = str(operation_entry["speaker_kind"])
        speaker_id = str(operation_entry["speaker_id"])
        speaker_display_name = str(operation_entry["display_name"])
    text = str(payload.get("text", ""))
    source_text = str(payload.get("source_text", text))
    normalized_payload: SpeechBlockPayload = {
        "speech_block_id": speech_block_id,
        "sequence_index": sequence_index,
        "chunk_id": chunk_id,
        "source_language": str(payload.get("source_language", "")).strip(),
        "speaker_kind": speaker_kind,
        "speaker_id": speaker_id,
        "speaker_display_name": speaker_display_name,
        "content_kind": content_kind,
        "source_text": source_text,
        "text": text,
        "warning_flags": _normalize_warning_flags(payload.get("warning_flags")),
        "approved": bool(payload.get("approved", False)),
        "approved_at": None if payload.get("approved_at") in (None, "") else str(payload.get("approved_at")),
    }
    if content_kind == CONTENT_KIND_SCENE_AMBIENCE:
        sound_prompt = str(payload.get("sound_prompt", text)).strip() or text
        normalized_payload.update(
            {
                "text": sound_prompt,
                "sound_prompt": sound_prompt,
                "negative_prompt": str(payload.get("negative_prompt", "")).strip(),
                "duration_seconds": _positive_float(
                    payload.get("duration_seconds"),
                    float(config.DEFAULT_SCENE_AMBIENCE_DURATION_SECONDS),
                ),
                "ambience_position": str(payload.get("ambience_position", "scene_change")).strip()
                if str(payload.get("ambience_position", "")).strip() in {"opener", "closer", "scene_change"}
                else "scene_change",
                "after_speech_block_id": str(payload.get("after_speech_block_id", "")).strip(),
            }
        )
    return normalized_payload


def _persist_state(
    project_root: Path,
    speech_blocks: list[SpeechBlockPayload],
    report: SpeechBlocksReportPayload,
    operation_state: OperationStatePayload,
) -> None:
    """
    @brief      Persist the Speech Blocks output, report, and state.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  report Current Speech Blocks report payload.
    @param[in]  operation_state Current Speech Blocks operation-state payload.
    @return     None.
    @exception  None
    """
    document = _compose_speech_blocks_document(speech_blocks, report, operation_state)
    write_speech_blocks_document(project_root, document)


def _rebuild_report_with_prompt_rules(
    speech_blocks: list[SpeechBlockPayload],
    source_language: str,
    source_kind: str,
    profile_id: str,
    total_chunk_count: int,
    processed_chunk_count: int,
    token_usage: dict[str, object],
    budget_metadata: BudgetMetadataPayload | None,
    additional_speech_block_instructions: str,
    scene_ambience_settings: dict[str, object] | None = None,
) -> SpeechBlocksReportPayload:
    """
    @brief      Rebuild a Speech Blocks report and persist operator prompt-rule metadata.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  source_language Active source language code.
    @param[in]  source_kind Active source-kind token.
    @param[in]  profile_id Active AI profile identifier.
    @param[in]  total_chunk_count Total source chunk count.
    @param[in]  processed_chunk_count Number of processed chunks.
    @param[in]  token_usage Current cumulative token-usage payload.
    @param[in]  budget_metadata Optional context-budget metadata.
    @param[in]  additional_speech_block_instructions Optional operator-supplied Speech Blocks rules.
    @return     Rebuilt Speech Blocks report payload.
    @exception  None
    """
    report = _rebuild_report(
        speech_blocks,
        source_language,
        source_kind,
        profile_id,
        total_chunk_count,
        processed_chunk_count,
        token_usage,
        budget_metadata,
    )
    normalized_instructions = _normalized_additional_speech_block_instructions(additional_speech_block_instructions)
    report["additional_speech_block_instructions"] = normalized_instructions
    scene_settings = scene_ambience_settings or _resolve_scene_ambience_settings(None, False)
    report["scene_ambience_generation"] = dict(scene_settings)
    report["additional_speech_block_instructions_fingerprint"] = _compute_generation_rules_fingerprint(
        normalized_instructions,
    )
    return report


def _build_operation_state_with_prompt_rules(
    project_root: Path,
    source_chunks: list[dict[str, object]],
    speech_blocks: list[SpeechBlockPayload],
    status: str,
    started_at: str,
    completed_at: str | None,
    source_language: str,
    source_kind: str,
    profile_id: str,
    input_fingerprint: str,
    log_path: Path,
    token_usage: dict[str, object],
    next_chunk_index: int | None,
    budget_metadata: BudgetMetadataPayload | None,
    additional_speech_block_instructions: str,
    scene_ambience_settings: dict[str, object] | None = None,
    speech_blocks_response_contract: str = _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT,
    active_chunk_id: str = "",
    next_source_offset: int | None = None,
    source_chunk_count: int | None = None,
    skipped_chunk_ids: list[str] | None = None,
) -> OperationStatePayload:
    """
    @brief      Build Speech Blocks operation state with operator prompt-rule metadata.
    @param[in]  project_root Active project root folder.
    @param[in]  source_chunks Current source-chunk snapshot.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  status Persisted operation status token.
    @param[in]  started_at Operation start timestamp.
    @param[in]  completed_at Operation completion timestamp or `None`.
    @param[in]  source_language Active source language code.
    @param[in]  source_kind Active source-kind token.
    @param[in]  profile_id Active AI profile identifier.
    @param[in]  input_fingerprint Stable source snapshot fingerprint.
    @param[in]  log_path Operation-local AI transaction log path.
    @param[in]  token_usage Current cumulative token-usage payload.
    @param[in]  next_chunk_index Next chunk index to process or `None`.
    @param[in]  budget_metadata Optional context-budget metadata.
    @param[in]  additional_speech_block_instructions Optional operator-supplied Speech Blocks rules.
    @param[in]  speech_blocks_response_contract Active model response contract token.
    @param[in]  active_chunk_id Source chunk whose generation is incomplete.
    @param[in]  next_source_offset Consumed character count within that chunk.
    @param[in]  source_chunk_count Optional shared projection count when source rows are unavailable.
    @param[in]  skipped_chunk_ids Source chunk identifiers the provider refused during this run.
    @return     Persisted operation-state payload.
    @exception  None
    """
    state = _build_operation_state(
        project_root,
        source_chunks,
        speech_blocks,
        status=status,
        started_at=started_at,
        source_language=source_language,
        source_kind=source_kind,
        profile_id=profile_id,
        input_fingerprint=input_fingerprint,
        log_path=log_path,
        token_usage=token_usage,
        next_chunk_index=next_chunk_index,
        budget_metadata=budget_metadata,
    )
    if source_chunk_count is not None:
        resolved_source_chunk_count = max(
            int(source_chunk_count),
            int(state.get("progress_current", 0)),
        )
        state["progress_total"] = resolved_source_chunk_count
        projected_metadata = state.get("metadata", {})
        projected_metadata = dict(projected_metadata) if isinstance(projected_metadata, dict) else {}
        projected_metadata["total_chunk_count"] = resolved_source_chunk_count
        state["metadata"] = projected_metadata
    state["started_at"] = started_at
    state["completed_at"] = completed_at
    state["artifact_paths"] = [
        config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME,
        str(log_path.name),
    ]
    normalized_instructions = _normalized_additional_speech_block_instructions(additional_speech_block_instructions)
    metadata = state.get("metadata", {})
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    metadata["additional_speech_block_instructions"] = normalized_instructions
    scene_settings = scene_ambience_settings or _resolve_scene_ambience_settings(None, False)
    instruction_fingerprint = _compute_generation_rules_fingerprint(normalized_instructions)
    response_contract = str(speech_blocks_response_contract).strip() or _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT
    metadata["additional_speech_block_instructions_fingerprint"] = instruction_fingerprint
    metadata["scene_ambience_generation"] = dict(scene_settings)
    metadata["speech_blocks_response_contract"] = response_contract
    metadata["skipped_chunk_ids"] = _coerce_skipped_chunk_ids(skipped_chunk_ids)
    state["metadata"] = metadata
    resume_checkpoint = state.get("resume_checkpoint")
    if isinstance(resume_checkpoint, dict):
        resume_checkpoint["additional_speech_block_instructions_fingerprint"] = instruction_fingerprint
        resume_checkpoint["speech_blocks_response_contract"] = response_contract
        if active_chunk_id:
            resume_checkpoint["active_chunk_id"] = str(active_chunk_id)
        if next_source_offset is not None:
            resume_checkpoint["next_source_offset"] = next_source_offset
        state["resume_checkpoint"] = resume_checkpoint
    return state


def _persist_compact_review_update(
    project_root: Path,
    speech_blocks: list[SpeechBlockPayload],
) -> SpeechBlocksReportPayload:
    """
    @brief      Persist a compact non-structural Speech Blocks review update.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_blocks Updated Speech Blocks payload list.
    @return     Updated report payload.
    @exception  None
    """
    document = load_speech_blocks_document(project_root)
    _source_chunks, source_chunk_count, _source_language, _source_kind = _resolve_source_context(
        project_root,
        document,
    )
    report = _project_speech_blocks_report(document, source_chunk_count) if document is not None else {}
    operation_state = _project_operation_state(document, source_chunk_count) if document is not None else {}
    metadata = operation_state.get("metadata", {}) if isinstance(operation_state, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    source_language = str(report.get("source_language", metadata.get("source_language", ""))).strip()
    source_kind = str(report.get("source_kind", metadata.get("source_kind", ""))).strip()
    profile_id = str(report.get("ai_profile_id", metadata.get("ai_profile_id", ""))).strip()
    token_usage = token_usage_service.restore_token_usage(report.get("token_usage"), metadata.get("token_usage"))
    budget_metadata = _restore_persisted_budget_metadata(report, operation_state)
    total_chunk_count = _metadata_int_value(report, metadata, "total_chunk_count", 0)
    processed_chunk_count = _metadata_int_value(
        report,
        metadata,
        "processed_chunk_count",
        len({str(block.get("chunk_id", "")).strip() for block in speech_blocks}),
    )
    updated_report = _rebuild_report(
        speech_blocks,
        source_language,
        source_kind,
        profile_id,
        total_chunk_count,
        processed_chunk_count,
        token_usage,
        budget_metadata,
    )
    additional_speech_block_instructions = _restore_persisted_additional_speech_block_instructions(
        report,
        operation_state,
    )
    scene_ambience_settings = _restore_persisted_scene_ambience_settings(report, operation_state)
    updated_report["additional_speech_block_instructions"] = additional_speech_block_instructions
    updated_report["scene_ambience_generation"] = dict(scene_ambience_settings)
    updated_report["additional_speech_block_instructions_fingerprint"] = _compute_generation_rules_fingerprint(
        additional_speech_block_instructions,
    )
    updated_state = _build_compact_review_operation_state(
        project_root,
        operation_state if isinstance(operation_state, dict) else {},
        updated_report,
        speech_blocks,
    )
    document = _compose_speech_blocks_document(speech_blocks, updated_report, updated_state)
    write_speech_blocks_document(project_root, document)
    project_workspace_service.sync_manifest_operation_summary(
        project_root,
        "speech_blocks",
        updated_state,
        current_stage="speech_blocks_ready"
        if str(updated_report.get("speech_blocks_stage_status", "")).strip() == SPEECH_BLOCKS_STAGE_COMPLETED
        else "character_voices_ready",
    )
    return updated_report


def _build_compact_review_operation_state(
    project_root: Path,
    operation_state: OperationStatePayload,
    report: SpeechBlocksReportPayload,
    speech_blocks: list[SpeechBlockPayload],
) -> OperationStatePayload:
    """
    @brief      Build compact Speech Blocks operation state for review-only mutations.
    @param[in]  project_root Active project root folder.
    @param[in]  operation_state Previous operation-state payload.
    @param[in]  report Updated Speech Blocks report payload.
    @param[in]  speech_blocks Updated Speech Blocks payload list.
    @return     Compact operation-state payload without source chunk snapshots.
    @exception  None
    """
    metadata = operation_state.get("metadata", {}) if isinstance(operation_state, dict) else {}
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    metadata.pop("source_chunks", None)
    metadata.update(
        {
            "source_language": str(report.get("source_language", metadata.get("source_language", ""))).strip(),
            "source_kind": str(report.get("source_kind", metadata.get("source_kind", ""))).strip(),
            "ai_profile_id": str(report.get("ai_profile_id", metadata.get("ai_profile_id", ""))).strip(),
            "processed_chunk_count": int(report.get("processed_chunk_count", 0)),
            "total_chunk_count": int(report.get("total_chunk_count", 0)),
            "speech_block_count": len(speech_blocks),
            "approved_block_count": int(report.get("approved_block_count", 0)),
            "total_block_count": len(speech_blocks),
            "warnings": list(report.get("warnings", [])) if isinstance(report.get("warnings"), list) else [],
            "token_usage": token_usage_service.coerce_token_usage(report.get("token_usage")),
        }
    )
    if report.get("budget_metadata") is not None:
        metadata["budget_metadata"] = dict(report["budget_metadata"])
    metadata["additional_speech_block_instructions"] = str(
        report.get("additional_speech_block_instructions", metadata.get("additional_speech_block_instructions", ""))
    )
    metadata["additional_speech_block_instructions_fingerprint"] = str(
        report.get(
            "additional_speech_block_instructions_fingerprint",
            metadata.get("additional_speech_block_instructions_fingerprint", ""),
        )
    )
    if isinstance(report.get("scene_ambience_generation"), dict):
        metadata["scene_ambience_generation"] = dict(report["scene_ambience_generation"])
    stage_status = str(report.get("speech_blocks_stage_status", "")).strip()
    status = (
        "completed"
        if stage_status == SPEECH_BLOCKS_STAGE_COMPLETED
        else ("not_started" if stage_status == SPEECH_BLOCKS_STAGE_NOT_STARTED else "review_pending")
    )
    started_at = _resolve_started_at(operation_state)
    completed_at = _valid_runtime_value(operation_state.get("completed_at"))
    if status == "completed" and completed_at is None:
        completed_at = _utc_now_iso()
    elif status != "completed":
        completed_at = None
    log_path = _resolve_log_path(project_root, started_at, operation_state)
    metadata["log_relative_path"] = str(log_path.name)
    resume_checkpoint = operation_state.get("resume_checkpoint")
    if isinstance(resume_checkpoint, dict):
        resume_checkpoint = dict(resume_checkpoint)
        if resume_checkpoint.get("active_chunk_id"):
            status = "running"
        resume_checkpoint["run_token"] = started_at
        resume_checkpoint["log_relative_path"] = str(log_path.name)
    else:
        resume_checkpoint = None
    state = build_operation_state_payload(
        status=status,
        progress_current=int(report.get("processed_chunk_count", 0)),
        progress_total=int(report.get("total_chunk_count", 0)),
        mode=str(operation_state.get("mode", "ai_assisted") or "ai_assisted"),
        warning_count=int(report.get("warning_count", 0)),
        metadata=metadata,
        resume_checkpoint=resume_checkpoint,
    )
    state["started_at"] = started_at
    state["completed_at"] = completed_at
    state["artifact_paths"] = [
        config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME,
        str(log_path.name),
    ]
    return state


def _metadata_int_value(
    report: SpeechBlocksReportPayload,
    metadata: dict[str, object],
    field_name: str,
    fallback: int,
) -> int:
    """
    @brief      Resolve one integer value from report metadata with fallback.
    @param[in]  report Persisted report payload.
    @param[in]  metadata Persisted operation metadata.
    @param[in]  field_name Field name to resolve.
    @param[in]  fallback Fallback integer value.
    @return     Non-negative integer value.
    @exception  None
    """
    for source in (report, metadata):
        try:
            return max(int(source.get(field_name, fallback)), 0)
        except (TypeError, ValueError):
            continue
    return max(int(fallback), 0)


def _persist_report_update(
    project_root: Path,
    speech_blocks: list[SpeechBlockPayload],
    source_context: _SpeechBlocksSourceContext | None = None,
) -> SpeechBlocksReportPayload:
    """
    @brief      Persist a review-only Speech Blocks update.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_blocks Updated Speech Blocks payload list.
    @param[in]  source_context Optional source context already resolved by the public caller.
    @return     Updated report payload.
    @exception  None
    """
    document = load_speech_blocks_document(project_root)
    if source_context is None:
        source_context = _resolve_source_context(project_root, document)
    source_chunks, source_chunk_count, resolved_source_language, resolved_source_kind = source_context
    report = _project_speech_blocks_report(document, source_chunk_count) if document is not None else {}
    operation_state = _project_operation_state(document, source_chunk_count) if document is not None else {}
    metadata = operation_state.get("metadata", {}) if isinstance(operation_state, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    source_language = str(
        report.get("source_language", metadata.get("source_language", resolved_source_language))
    ).strip()
    source_kind = str(report.get("source_kind", metadata.get("source_kind", resolved_source_kind))).strip()
    profile_id = str(report.get("ai_profile_id", metadata.get("ai_profile_id", ""))).strip()
    token_usage = token_usage_service.restore_token_usage(report.get("token_usage"), metadata.get("token_usage"))
    budget_metadata = _restore_persisted_budget_metadata(report, operation_state)
    additional_speech_block_instructions = _restore_persisted_additional_speech_block_instructions(
        report,
        operation_state,
    )
    scene_ambience_settings = _restore_persisted_scene_ambience_settings(report, operation_state)
    input_fingerprint = str(metadata.get("source_snapshot_fingerprint", "")).strip()
    if not input_fingerprint and source_chunks and source_language and source_kind:
        input_fingerprint = _build_source_fingerprint(source_chunks, source_language, source_kind)
    active_checkpoint = _active_checkpoint_for_source(
        operation_state, _build_source_fingerprint(source_chunks, source_language, source_kind)
    )
    started_at = _resolve_started_at(operation_state)
    completed_at = None
    log_path = _resolve_log_path(project_root, started_at, operation_state)
    renumbered_blocks = _renumber_speech_blocks(source_chunks, speech_blocks)
    updated_report = _rebuild_report_with_prompt_rules(
        renumbered_blocks,
        source_language,
        source_kind,
        profile_id,
        source_chunk_count,
        _covered_chunk_count(renumbered_blocks, active_checkpoint),
        token_usage,
        budget_metadata,
        additional_speech_block_instructions,
        scene_ambience_settings=scene_ambience_settings,
    )
    stage_status = str(updated_report.get("speech_blocks_stage_status", "")).strip()
    if stage_status == SPEECH_BLOCKS_STAGE_COMPLETED:
        status = "completed"
    elif stage_status == SPEECH_BLOCKS_STAGE_NOT_STARTED:
        status = "not_started"
    else:
        status = "review_pending"
    updated_state = _build_operation_state_with_prompt_rules(
        project_root,
        source_chunks,
        renumbered_blocks,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        source_language=source_language,
        source_kind=source_kind,
        profile_id=profile_id,
        input_fingerprint=input_fingerprint,
        log_path=log_path,
        token_usage=token_usage,
        next_chunk_index=None,
        budget_metadata=budget_metadata,
        additional_speech_block_instructions=additional_speech_block_instructions,
        scene_ambience_settings=scene_ambience_settings,
        speech_blocks_response_contract=_restore_persisted_speech_blocks_response_contract(operation_state),
        source_chunk_count=source_chunk_count,
        skipped_chunk_ids=_uncovered_skipped_chunk_ids(operation_state, renumbered_blocks),
    )
    if active_checkpoint is not None:
        updated_state["status"] = "running"
        updated_state["resume_checkpoint"] = active_checkpoint
    _persist_state(
        project_root,
        renumbered_blocks,
        updated_report,
        updated_state,
    )
    project_workspace_service.sync_manifest_operation_summary(
        project_root,
        "speech_blocks",
        updated_state,
        current_stage="speech_blocks_ready" if status == "completed" else "character_voices_ready",
    )
    return updated_report


def _is_character_speech_block(block: SpeechBlockPayload, character_id: str) -> bool:
    """
    @brief      Return whether one Speech Block is assigned to the selected character speaker.
    @param[in]  block Speech Block payload.
    @param[in]  character_id Character identifier to match.
    @return     True when the block currently uses that character as speaker.
    @exception  None
    """
    return (
        str(block.get("speaker_kind", "")).strip() == SPEAKER_KIND_CHARACTER
        and str(block.get("speaker_id", "")).strip() == character_id
    )


def _renumber_speech_blocks(
    source_chunks: list[dict[str, object]],
    speech_blocks: list[SpeechBlockPayload],
) -> list[SpeechBlockPayload]:
    """
    @brief      Recompute chunk-local Speech Block order fields.
    @param[in]  source_chunks Source chunks in workflow order.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @return     Renumbered Speech Blocks payload list.
    @exception  None
    """
    chunk_order = {
        str(chunk.get("chunk_id", "")).strip(): int(chunk.get("sequence_index", 0)) for chunk in source_chunks
    }
    local_counts: dict[str, int] = {}
    renumbered_blocks: list[SpeechBlockPayload] = []
    ordered_blocks = sorted(
        speech_blocks,
        key=lambda block: (
            chunk_order.get(str(block.get("chunk_id", "")).strip(), 10**9),
            int(block.get("sequence_index", 0)),
        ),
    )
    used_ids: set[str] = set()
    for block in ordered_blocks:
        chunk_id = str(block.get("chunk_id", "")).strip()
        local_counts[chunk_id] = local_counts.get(chunk_id, 0) + 1
        sequence_index = local_counts[chunk_id]
        renumbered_block = dict(block)
        renumbered_block["sequence_index"] = sequence_index
        renumbered_block["speech_block_id"] = _stable_speech_block_id(renumbered_block, chunk_id, used_ids)
        renumbered_blocks.append(renumbered_block)
    return renumbered_blocks


def _used_speech_block_ids(speech_blocks: list[SpeechBlockPayload]) -> set[str]:
    """
    @brief      Collect non-empty Speech Block identifiers from current payloads.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @return     Existing Speech Block id set.
    @exception  None
    """
    return {
        str(block.get("speech_block_id", "")).strip()
        for block in speech_blocks
        if str(block.get("speech_block_id", "")).strip()
    }


def _manual_inserted_speech_block(chunk_id: str, sequence_index: int, speech_block_id: str) -> SpeechBlockPayload:
    """
    @brief      Build the default payload for a manually inserted Speech Block.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  sequence_index Requested chunk-local insertion index.
    @param[in]  speech_block_id Temporary Speech Block identifier.
    @return     New unapproved narrator narration Speech Block payload.
    @exception  None
    """
    return {
        "speech_block_id": speech_block_id,
        "sequence_index": sequence_index,
        "chunk_id": chunk_id,
        "source_language": "",
        "speaker_kind": SPEAKER_KIND_NARRATOR,
        "speaker_id": _NARRATOR_SPEAKER_ID,
        "speaker_display_name": _NARRATOR_DISPLAY_NAME,
        "content_kind": CONTENT_KIND_NARRATION,
        "source_text": "",
        "text": "",
        "warning_flags": [],
        "approved": False,
        "approved_at": None,
    }


def _speech_block_by_id(
    speech_blocks: list[SpeechBlockPayload],
    speech_block_id: str,
) -> SpeechBlockPayload | None:
    """
    @brief      Find one Speech Block by identifier.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  speech_block_id Target Speech Block identifier.
    @return     Matching block or `None`.
    @exception  None
    """
    normalized_id = str(speech_block_id).strip()
    return next(
        (block for block in speech_blocks if str(block.get("speech_block_id", "")).strip() == normalized_id),
        None,
    )


def _build_source_fingerprint(source_chunks: list[dict[str, object]], source_language: str, source_kind: str) -> str:
    """
    @brief      Build one stable fingerprint for the Speech Blocks source snapshot.
    @param[in]  source_chunks Source snapshot payload list.
    @param[in]  source_language Active source language code.
    @param[in]  source_kind Active source-kind token.
    @return     Hex-encoded fingerprint string.
    @exception  None
    """
    fingerprint_payload = {
        "source_language": source_language,
        "source_kind": source_kind,
        "source_chunks": [
            {
                "chunk_id": str(chunk.get("chunk_id", "")),
                "sequence_index": int(chunk.get("sequence_index", 0)),
                "text": str(chunk.get("text", "")),
            }
            for chunk in source_chunks
        ],
    }
    return hashlib.sha1(  # noqa: S324
        json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _restore_resume_state(
    project_root: Path,
    existing_state: dict[str, object],
    input_fingerprint: str,
    source_language: str,
    source_chunks: list[dict[str, object]],
    additional_speech_block_instructions_fingerprint: str,
) -> tuple[list[SpeechBlockPayload], int, int]:
    """
    @brief      Restore resumable Speech Blocks state when the persisted checkpoint is still valid.
    @param[in]  project_root Active project root folder.
    @param[in]  existing_state Existing operation-state payload.
    @param[in]  input_fingerprint Current source snapshot fingerprint.
    @param[in]  source_language Active source language code.
    @param[in]  source_chunks Ordered current source chunk snapshot.
    @param[in]  additional_speech_block_instructions_fingerprint Operator instruction fingerprint.
    @return     Existing blocks, next chunk index and consumed source characters.
    @exception  None
    """
    if not isinstance(existing_state, dict):
        return [], 0, 0
    if str(existing_state.get("status", "")).strip() not in {"running", "failed", "review_pending", "completed"}:
        return [], 0, 0
    metadata = existing_state.get("metadata", {})
    resume_checkpoint = existing_state.get("resume_checkpoint", {})
    if not isinstance(metadata, dict):
        return [], 0, 0
    if str(metadata.get("source_snapshot_fingerprint", "")).strip() != input_fingerprint:
        return [], 0, 0
    if str(metadata.get("source_language", "")).strip() != source_language:
        return [], 0, 0
    resume_checkpoint_payload = resume_checkpoint if isinstance(resume_checkpoint, dict) else {}
    if not _is_resumable_speech_blocks_response_contract(metadata, resume_checkpoint_payload):
        return [], 0, 0
    stored_instruction_fingerprint = str(
        metadata.get("additional_speech_block_instructions_fingerprint")
        or resume_checkpoint_payload.get("additional_speech_block_instructions_fingerprint")
        or _compute_prompt_fingerprint("")
    )
    if stored_instruction_fingerprint != additional_speech_block_instructions_fingerprint:
        return [], 0, 0
    existing_blocks = load_speech_blocks(project_root)
    next_chunk_index = _restore_next_speech_blocks_chunk_index(
        existing_state,
        resume_checkpoint_payload,
        source_chunks,
        existing_blocks,
    )
    active_chunk_id = str(resume_checkpoint_payload.get("active_chunk_id", "")).strip()
    if active_chunk_id and next_chunk_index < len(source_chunks):
        chunk = source_chunks[next_chunk_index]
        if active_chunk_id == str(chunk["chunk_id"]):
            offset = resume_checkpoint_payload.get("next_source_offset")
            if type(offset) is int and 0 < offset <= len(str(chunk["text"])):
                return existing_blocks, next_chunk_index, offset
            # A segment index cannot safely identify the remaining source under a new budget.
            existing_blocks = [block for block in existing_blocks if block["chunk_id"] != active_chunk_id]
            return existing_blocks, next_chunk_index, 0
    active_checkpoint_status = str(existing_state.get("status", "")).strip() in {"running", "failed"}
    if next_chunk_index == 0 and (active_checkpoint_status or not existing_blocks):
        return [], 0, 0
    return existing_blocks, next_chunk_index, 0


def _is_resumable_speech_blocks_response_contract(
    metadata: dict[str, object],
    resume_checkpoint: dict[str, object],
) -> bool:
    """
    @brief      Return whether persisted Speech Blocks state uses a current response contract.
    @details    A run recorded under a retired contract is not resumed, because continuing it
                would leave one document holding blocks segmented two different ways. The
                retired contract stays readable, so the existing blocks are still shown.
    @param[in]  metadata Existing operation metadata payload.
    @param[in]  resume_checkpoint Existing resumable checkpoint payload.
    @return     True when the state can be resumed safely.
    @exception  None
    """
    response_contract = str(
        metadata.get("speech_blocks_response_contract")
        or resume_checkpoint.get("speech_blocks_response_contract")
        or ""
    ).strip()
    return response_contract in {
        _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT,
        _SPEECH_BLOCKS_DETERMINISTIC_NARRATOR_CONTRACT,
    }


def _restore_next_speech_blocks_chunk_index(
    existing_state: dict[str, object],
    resume_checkpoint: dict[str, object],
    source_chunks: list[dict[str, object]],
    existing_blocks: list[SpeechBlockPayload],
) -> int:
    """
    @brief      Restore the next Speech Blocks source-chunk index.
    @param[in]  existing_state Existing operation-state payload.
    @param[in]  resume_checkpoint Existing resumable checkpoint payload.
    @param[in]  source_chunks Ordered current source chunk snapshot.
    @param[in]  existing_blocks Persisted Speech Blocks payload list.
    @return     Clamped next source-chunk index.
    @exception  None
    """
    active_chunk_id = str(resume_checkpoint.get("active_chunk_id", "")).strip()
    if active_chunk_id:
        for chunk_index, source_chunk in enumerate(source_chunks):
            if str(source_chunk.get("chunk_id", "")).strip() == active_chunk_id:
                return chunk_index
    if str(existing_state.get("status", "")).strip() in {"running", "failed"}:
        raw_checkpoint_index = resume_checkpoint.get("next_chunk_index")
        if raw_checkpoint_index not in (None, ""):
            return max(0, min(int(raw_checkpoint_index), len(source_chunks)))
    covered_chunk_ids = {
        str(block.get("chunk_id", "")).strip()
        for block in existing_blocks
        if str(block.get("chunk_id", "")).strip()
    }
    return next(
        (
            chunk_index
            for chunk_index, source_chunk in enumerate(source_chunks)
            if str(source_chunk.get("chunk_id", "")).strip() not in covered_chunk_ids
        ),
        len(source_chunks),
    )


def _resolve_started_at(existing_state: dict[str, object]) -> str:
    """
    @brief      Resolve the stable operation start timestamp for one run.
    @param[in]  existing_state Existing operation-state payload.
    @return     Stable operation start timestamp.
    @exception  None
    """
    resume_checkpoint = existing_state.get("resume_checkpoint", {}) if isinstance(existing_state, dict) else {}
    if not isinstance(resume_checkpoint, dict):
        resume_checkpoint = {}
    started_at = _valid_runtime_value(resume_checkpoint.get("run_token"))
    return started_at or _utc_now_iso()


def _resolve_log_path(
    project_root: Path,
    started_at: str,
    existing_state: OperationStatePayload | None = None,
) -> Path:
    """
    @brief      Resolve or create the AI transaction log path for Speech Blocks.
    @param[in]  project_root Active project root folder.
    @param[in]  started_at Stable operation start timestamp.
    @param[in]  existing_state Optional state already projected by the public operation.
    @return     Operation-local AI transaction log path.
    @exception  None
    """
    if existing_state is None:
        existing_state = load_operation_state(project_root) or {}
    metadata = existing_state.get("metadata", {}) if isinstance(existing_state, dict) else {}
    resume_checkpoint = existing_state.get("resume_checkpoint", {}) if isinstance(existing_state, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    if not isinstance(resume_checkpoint, dict):
        resume_checkpoint = {}
    relative_path = str(metadata.get("log_relative_path") or resume_checkpoint.get("log_relative_path") or "").strip()
    if relative_path and "None" not in relative_path and "null" not in relative_path:
        resolved_path = project_root / relative_path
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        if not resolved_path.exists():
            resolved_path.write_text("", encoding="utf-8")
        return resolved_path
    timestamp_token = started_at.replace("-", "").replace(":", "").replace("+", "_").replace(".", "")
    log_path = build_operation_output_path(
        project_root,
        "speech_blocks",
        config.ai_transaction_log_file_name("speech_blocks", timestamp_token),
    )
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")
    return log_path


def _metadata_token_usage(existing_state: dict[str, object]) -> dict[str, object] | None:
    """
    @brief      Extract persisted token usage from one existing operation state.
    @param[in]  existing_state Existing operation-state payload.
    @return     Persisted token-usage payload or `None`.
    @exception  None
    """
    if not isinstance(existing_state, dict):
        return None
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return None
    payload = metadata.get("token_usage")
    return payload if isinstance(payload, dict) else None


def _restore_persisted_budget_metadata(
    report: dict[str, object] | None,
    operation_state: dict[str, object] | None,
) -> BudgetMetadataPayload | None:
    """
    @brief      Restore optional Speech Blocks context-budget metadata from persisted artifacts.
    @param[in]  report Persisted Speech Blocks report payload.
    @param[in]  operation_state Persisted Speech Blocks operation-state payload.
    @return     Restored budget metadata or `None`.
    @exception  None
    """
    if isinstance(report, dict):
        report_budget = report.get("budget_metadata")
        if isinstance(report_budget, dict):
            return {str(key): int(value) for key, value in report_budget.items()}
    metadata = operation_state.get("metadata", {}) if isinstance(operation_state, dict) else {}
    if isinstance(metadata, dict):
        state_budget = metadata.get("budget_metadata")
        if isinstance(state_budget, dict):
            return {str(key): int(value) for key, value in state_budget.items()}
    return None


# END OF FILE
