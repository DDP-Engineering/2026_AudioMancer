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
    ai_budget_service,
    ai_translation_service,
    character_discovery_service,
    chunking_document_service,
    llm_provider_service,
    narrator_definition_service,
    project_workspace_service,
    prompt_template_service,
    speech_blocks_narrator_split_service,
    speech_blocks_normalization_service,
    speech_blocks_report_state_service,
    speech_blocks_text_split_service,
    token_usage_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
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
_DIRECT_BLOCK_PROMPT_NAMES = ("speech_blocks_system", "speech_blocks_user")
_SPEECH_BLOCKS_DIRECT_SOURCE_TOKEN_CAP = 2000
_approved_block_count = speech_blocks_report_state_service.approved_block_count
_build_speech_block_payload = speech_blocks_normalization_service.build_speech_block_payload
_build_operation_state = speech_blocks_report_state_service.build_operation_state
_chunk_order_from_id = speech_blocks_normalization_service.chunk_order_from_id
_is_operation_content_kind = speech_blocks_normalization_service.is_operation_content_kind
_normalize_block_text = speech_blocks_normalization_service.normalize_block_text
_normalize_chunk_blocks = speech_blocks_normalization_service.normalize_chunk_blocks
_normalize_content_kind = speech_blocks_normalization_service.normalize_content_kind
_normalize_warning_flags = speech_blocks_normalization_service.normalize_warning_flags
_operation_display_name = speech_blocks_normalization_service.operation_display_name
_operation_speaker_entry = speech_blocks_normalization_service.operation_speaker_entry
_rebuild_report = speech_blocks_report_state_service.rebuild_report
_resolve_narrator_only_budget = speech_blocks_normalization_service.resolve_narrator_only_budget
_safe_tts_word_count = speech_blocks_normalization_service.safe_tts_word_count
_speaker_match_key = speech_blocks_normalization_service.speaker_match_key
_speech_block_id = speech_blocks_normalization_service.speech_block_id
_speech_block_warning_reason = speech_blocks_normalization_service.speech_block_warning_reason
_warning_records_from_blocks = speech_blocks_report_state_service.warning_records_from_blocks
_split_text_for_ai_context_budget = speech_blocks_text_split_service.split_text_for_ai_context_budget

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
        "failure": None,
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


def _project_speech_blocks_report(
    document: SpeechBlocksDocumentPayload,
    source_chunk_count: int,
) -> SpeechBlocksReportPayload:
    """Project the legacy report shape from the single Speech Blocks document."""
    blocks = [block for block in document.get("blocks", []) if isinstance(block, dict)]
    source = document.get("source", {}) if isinstance(document.get("source"), dict) else {}
    checkpoint = document.get("checkpoint") if isinstance(document.get("checkpoint"), dict) else {}
    processed_chunk_count = len({str(block.get("chunk_id", "")).strip() for block in blocks} - {""})
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
    processed_chunk_count = len({str(block.get("chunk_id", "")).strip() for block in blocks} - {""})
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
    }
    budget_metadata = document.get("budget_metadata")
    if isinstance(budget_metadata, dict) and budget_metadata:
        metadata["budget_metadata"] = dict(budget_metadata)
    status = str(document.get("status", "not_started"))
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
    state["completed_at"] = _utc_now_iso() if status == "completed" else None
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
def load_speech_blocks(project_root: str | Path) -> list[SpeechBlockPayload]:
    """
    @brief      Load one optional persisted Speech Blocks output payload.
    @param[in]  project_root Active project root folder.
    @return     Ordered Speech Blocks payload list.
    @exception  SpeechBlocksDocumentError Raised when the authoritative document exists but is unreadable or invalid.
    """
    document = load_speech_blocks_document(project_root)
    if document is None:
        return []
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
        resolved_project_root,
        original_chunks,
        translation_document,
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
        if translation_document is None:
            return None
        if not isinstance(translation_document, dict):
            return None
        translation_summary = ai_translation_service.build_translation_summary(original_chunks, translation_document)
        if str(translation_summary["status"]) != ai_translation_service.TRANSLATION_STATUS_COMPLETED:
            return None
        translated_records = [dict(item) for item in translation_document["chunks"]]
    except (OSError, ValueError):
        return None
    translated_by_id = {
        str(chunk.get("chunk_id", "")): dict(chunk)
        for chunk in translated_records
        if isinstance(chunk, dict) and str(chunk.get("chunk_id", "")).strip()
    }
    source_chunks: list[dict[str, object]] = []
    for original_chunk in original_chunks:
        chunk_id = str(original_chunk.get("chunk_id", "")).strip()
        translated_chunk = translated_by_id.get(chunk_id)
        translated_text = "" if translated_chunk is None else str(translated_chunk.get("translated_text", ""))
        if not translated_text.strip():
            return None
        source_chunks.append(
            {
                "chunk_id": chunk_id,
                "sequence_index": int(original_chunk.get("sequence_index", 0)),
                "text": translated_text,
                **_cleanup_provenance_fields(original_chunk),
            }
        )
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
    narrator_only_mode = str(resolved_voice_assignment_mode).strip() == "same_narrator"
    speech_blocks_response_contract = _speech_blocks_response_contract(resolved_voice_assignment_mode)
    scene_ambience_settings = _resolve_scene_ambience_settings(settings_payload, scene_ambience_enabled)

    profile_id = str(ai_profile_payload.get("id", "")).strip()
    model_name = str(ai_profile_payload.get("model_name", "")).strip()
    base_url = str(ai_profile_payload.get("base_url", "")).strip()
    # Same-narrator segmentation is deterministic, so a model is only needed for scene ambience.
    requires_ai_profile = not narrator_only_mode or bool(scene_ambience_settings["enabled"])
    if requires_ai_profile and (not profile_id or not model_name or not base_url):
        raise ValueError("Speech Blocks generation requires a valid enabled AI profile.")

    prompt_names = ("", "") if narrator_only_mode else _DIRECT_BLOCK_PROMPT_NAMES
    if not narrator_only_mode:
        prompt_template_service.validate_required_prompts(list(prompt_names))
    if bool(scene_ambience_settings["enabled"]):
        prompt_template_service.validate_required_prompts(["scene_ambience_system", "scene_ambience_user"])
    tts_budget = _resolve_narrator_only_budget(settings_payload)
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

    speaker_catalog = _speaker_catalog(character_discovery_service.load_character_profiles(resolved_project_root))
    system_prompt = "" if narrator_only_mode else prompt_template_service.render_prompt(prompt_names[0], {})
    # Deterministic segmentation sends no source text to a model, so it has no context budget.
    budget_metadata: BudgetMetadataPayload = (
        {}
        if narrator_only_mode
        else _build_budget_metadata(
            ai_profile_payload,
            system_prompt,
            prompt_names[1],
            source_language,
            speaker_catalog,
            resolved_voice_assignment_mode,
            tts_budget,
            additional_speech_block_instructions,
        )
    )
    input_fingerprint = _build_source_fingerprint(source_chunks, source_language, source_kind)
    started_at = _resolve_started_at(existing_state)
    log_path = _resolve_log_path(resolved_project_root, started_at, existing_state)
    existing_blocks, start_chunk_index = _restore_resume_state(
        resolved_project_root,
        existing_state,
        input_fingerprint,
        source_language,
        source_chunks,
        additional_speech_block_instructions_fingerprint,
    )
    start_segment_index = _restore_next_speech_blocks_segment_index(existing_state, source_chunks, start_chunk_index)
    token_usage = (
        token_usage_service.restore_token_usage(
            None if existing_report is None else existing_report.get("token_usage"),
            _metadata_token_usage(existing_state),
        )
        if start_chunk_index > 0 or existing_blocks
        else token_usage_service.empty_token_usage()
    )
    if existing_blocks and start_chunk_index >= len(source_chunks):
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
            active_chunk_id=(
                str(source_chunks[start_chunk_index].get("chunk_id", ""))
                if start_chunk_index < len(source_chunks) and start_segment_index > 0
                else ""
            ),
            next_segment_index=start_segment_index if start_segment_index > 0 else None,
            completed_segment_count=start_segment_index if start_segment_index > 0 else None,
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
        resumes_active_segment = chunk_index == start_chunk_index and start_segment_index > 0
        if chunk_id in covered_chunk_ids and not resumes_active_segment:
            continue
        existing_chunk_block_count = sum(
            1 for block in all_blocks if str(block.get("chunk_id", "")).strip() == chunk_id
        )

        def _persist_segment_progress(
            segment_blocks: list[SpeechBlockPayload],
            _segment_warnings: list[dict[str, object]],
            segment_token_usage: TokenUsagePayload,
            next_segment_index: int,
            segment_total: int,
            base_blocks: list[SpeechBlockPayload] = all_blocks,
            base_token_usage: TokenUsagePayload = token_usage,
            current_chunk_index: int = chunk_index,
            current_chunk_id: str = chunk_id,
            current_chunk_block_count: int = existing_chunk_block_count,
        ) -> None:
            """
            @brief      Persist resumable Speech Blocks progress after one direct request segment.
            @param[in]  segment_blocks Chunk-local blocks generated so far in this call.
            @param[in]  _segment_warnings Ignored chunk-local warning snapshot supplied by the callback contract.
            @param[in]  segment_token_usage Chunk-local token usage generated so far in this call.
            @param[in]  next_segment_index One-based next segment cursor after the persisted segment.
            @param[in]  segment_total Total segment count for the active chunk.
            @return     None.
            @exception  None
            """
            continued_segment_blocks = _continue_chunk_sequence_indices(
                segment_blocks,
                current_chunk_block_count,
            )
            persisted_blocks = _renumber_speech_blocks(source_chunks, [*base_blocks, *continued_segment_blocks])
            persisted_usage = token_usage_service.merge_token_usage(base_token_usage, segment_token_usage)
            chunk_complete = next_segment_index >= segment_total
            processed_chunk_count = current_chunk_index + 1 if chunk_complete else current_chunk_index
            report = _rebuild_report_with_prompt_rules(
                persisted_blocks,
                source_language,
                source_kind,
                profile_id,
                len(source_chunks),
                processed_chunk_count,
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
                    next_chunk_index=processed_chunk_count,
                    budget_metadata=budget_metadata,
                    additional_speech_block_instructions=additional_speech_block_instructions,
                    scene_ambience_settings=scene_ambience_settings,
                    speech_blocks_response_contract=speech_blocks_response_contract,
                    active_chunk_id=current_chunk_id if not chunk_complete else "",
                    next_segment_index=next_segment_index if not chunk_complete else None,
                    completed_segment_count=next_segment_index if not chunk_complete else None,
                ),
            )

        chunk_blocks, _chunk_warnings, chunk_token_usage = _generate_budgeted_chunk_blocks(
            ai_profile_payload,
            system_prompt,
            source_chunk,
            source_language,
            speaker_catalog,
            resolved_voice_assignment_mode,
            tts_budget,
            prompt_names[1],
            budget_metadata,
            additional_speech_block_instructions,
            log_path,
            {
                "operation_kind": "speech_blocks",
                "stage_label": "speech_blocks_chunk",
                "profile_id": profile_id,
                "chunk_index": chunk_index + 1,
                "chunk_total": len(source_chunks),
                "chunk_id": str(source_chunk.get("chunk_id", "")),
            },
            cancel_requested,
            "Speech Blocks generation cancelled while waiting for the model response.",
            start_segment_index=start_segment_index if chunk_index == start_chunk_index else 0,
            segment_progress_callback=(
                _persist_segment_progress
                if str(resolved_voice_assignment_mode).strip() != "same_narrator"
                else None
            ),
        )
        token_usage = token_usage_service.merge_token_usage(token_usage, chunk_token_usage)
        if bool(scene_ambience_settings["enabled"]):
            ambience_blocks, ambience_token_usage = _generate_scene_ambience_blocks(
                ai_profile_payload,
                source_chunk,
                source_language,
                chunk_blocks,
                scene_ambience_settings,
                log_path,
                {
                    "operation_kind": "speech_blocks",
                    "stage_label": "scene_ambience_chunk",
                    "profile_id": profile_id,
                    "chunk_index": chunk_index + 1,
                    "chunk_total": len(source_chunks),
                    "chunk_id": str(source_chunk.get("chunk_id", "")),
                },
                cancel_requested,
            )
            token_usage = token_usage_service.merge_token_usage(token_usage, ambience_token_usage)
            chunk_blocks = _insert_scene_ambience_blocks(chunk_blocks, ambience_blocks)
        chunk_blocks = _continue_chunk_sequence_indices(chunk_blocks, existing_chunk_block_count)
        all_blocks.extend(chunk_blocks)
        all_blocks = _renumber_speech_blocks(source_chunks, all_blocks)
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
        len(source_chunks),
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
    narrator_only_mode = str(resolved_voice_assignment_mode).strip() == "same_narrator"
    speech_blocks_response_contract = _speech_blocks_response_contract(resolved_voice_assignment_mode)
    tts_budget = _resolve_narrator_only_budget(settings_payload)
    scene_ambience_settings = _resolve_scene_ambience_settings(settings_payload, scene_ambience_enabled)

    profile_id = str(ai_profile_payload.get("id", "")).strip()
    model_name = str(ai_profile_payload.get("model_name", "")).strip()
    base_url = str(ai_profile_payload.get("base_url", "")).strip()
    # Same-narrator segmentation is deterministic, so a model is only needed for scene ambience.
    requires_ai_profile = not narrator_only_mode or bool(scene_ambience_settings["enabled"])
    if requires_ai_profile and (not profile_id or not model_name or not base_url):
        raise ValueError("Speech Blocks generation requires a valid enabled AI profile.")

    prompt_names = ("", "") if narrator_only_mode else _DIRECT_BLOCK_PROMPT_NAMES
    selected_chunk = next(
        (chunk for chunk in source_chunks if str(chunk.get("chunk_id", "")).strip() == chunk_id),
        None,
    )
    if selected_chunk is None:
        raise ValueError("The selected chunk was not found.")
    if not narrator_only_mode:
        prompt_template_service.validate_required_prompts(list(prompt_names))
    if bool(scene_ambience_settings["enabled"]):
        prompt_template_service.validate_required_prompts(["scene_ambience_system", "scene_ambience_user"])
    existing_document = load_speech_blocks_document(resolved_project_root)
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
    speaker_catalog = _speaker_catalog(character_discovery_service.load_character_profiles(resolved_project_root))
    system_prompt = "" if narrator_only_mode else prompt_template_service.render_prompt(prompt_names[0], {})
    # Deterministic segmentation sends no source text to a model, so it has no context budget.
    budget_metadata: BudgetMetadataPayload = (
        {}
        if narrator_only_mode
        else _build_budget_metadata(
            ai_profile_payload,
            system_prompt,
            prompt_names[1],
            source_language,
            speaker_catalog,
            resolved_voice_assignment_mode,
            tts_budget,
            additional_speech_block_instructions,
        )
    )
    raise_if_cancelled(cancel_requested)
    selected_chunk_index = source_chunks.index(selected_chunk)
    selected_chunk = _source_chunk_with_attribution_context(source_chunks, selected_chunk_index)
    new_blocks, _chunk_warnings, chunk_token_usage = _generate_budgeted_chunk_blocks(
        ai_profile_payload,
        system_prompt,
        dict(selected_chunk),
        source_language,
        speaker_catalog,
        resolved_voice_assignment_mode,
        tts_budget,
        prompt_names[1],
        budget_metadata,
        additional_speech_block_instructions,
        log_path,
        {
            "operation_kind": "speech_blocks",
            "stage_label": "speech_blocks_chunk_resplit",
            "profile_id": profile_id,
            "chunk_id": str(selected_chunk.get("chunk_id", "")),
        },
        cancel_requested,
        "Speech Blocks re-splitting cancelled while waiting for the model response.",
    )
    token_usage = token_usage_service.merge_token_usage(token_usage, chunk_token_usage)
    if bool(scene_ambience_settings["enabled"]):
        ambience_blocks, ambience_token_usage = _generate_scene_ambience_blocks(
            ai_profile_payload,
            dict(selected_chunk),
            source_language,
            new_blocks,
            scene_ambience_settings,
            log_path,
            {
                "operation_kind": "speech_blocks",
                "stage_label": "scene_ambience_chunk_resplit",
                "profile_id": profile_id,
                "chunk_id": str(selected_chunk.get("chunk_id", "")),
            },
            cancel_requested,
        )
        token_usage = token_usage_service.merge_token_usage(token_usage, ambience_token_usage)
        new_blocks = _insert_scene_ambience_blocks(new_blocks, ambience_blocks)
    existing_blocks = [
        block
        for block in load_speech_blocks(resolved_project_root)
        if str(block.get("chunk_id", "")).strip() != chunk_id
    ]
    all_blocks = _renumber_speech_blocks(source_chunks, [*existing_blocks, *new_blocks])
    input_fingerprint = _build_source_fingerprint(source_chunks, source_language, source_kind)
    completed_at = _utc_now_iso()
    report = _rebuild_report_with_prompt_rules(
        all_blocks,
        source_language,
        source_kind,
        profile_id,
        len(source_chunks),
        len({str(block.get("chunk_id", "")).strip() for block in all_blocks}),
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
    )
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


def _chunk_user_prompt(
    source_chunk: dict[str, object],
    source_language: str,
    speaker_catalog: dict[str, dict[str, object]],
    voice_assignment_mode: str = config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
    tts_budget: dict[str, object] | None = None,
    prompt_name: str = "speech_blocks_user",
    additional_speech_block_instructions: str = "",
) -> str:
    """
    @brief      Render the chunk-specific Speech Blocks user prompt.
    @param[in]  source_chunk Source chunk payload.
    @param[in]  source_language Active source language code.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  voice_assignment_mode Active project voice-assignment mode.
    @param[in]  tts_budget Optional narrator-only TTS budget metadata.
    @param[in]  prompt_name Prompt template name.
    @param[in]  additional_speech_block_instructions Optional operator-supplied Speech Blocks rules.
    @return     Rendered prompt text.
    @exception  None
    """
    budget_payload = tts_budget or _resolve_narrator_only_budget(None)
    return _render_speech_blocks_user_prompt(
        prompt_name,
        {
            "source_language": narrator_definition_service.narrator_language_label(source_language),
            "chunk_id": str(source_chunk.get("chunk_id", "")),
            "chunk_text": str(source_chunk.get("text", "")),
            "source_context_json": json.dumps(
                _compact_source_context_for_prompt(source_chunk),
                indent=2,
                ensure_ascii=False,
            ),
            "speaker_catalog_json": json.dumps(list(speaker_catalog.values()), indent=2, ensure_ascii=False),
            "voice_assignment_mode": voice_assignment_mode,
            "max_tts_tokens": str(int(budget_payload.get("model_token_budget", 0))),
            "safe_tts_words": str(int(budget_payload.get("safe_word_count", 0))),
            "tts_budget_source": str(budget_payload.get("model_budget_source", "")),
            "additional_speech_block_instructions": additional_speech_block_instructions,
        },
    )


def _render_speech_blocks_user_prompt(prompt_name: str, variables: dict[str, object]) -> str:
    """
    @brief      Render one Speech Blocks user prompt with optional operator rules.
    @param[in]  prompt_name Prompt template identifier.
    @param[in]  variables Prompt variables.
    @return     Rendered Speech Blocks prompt.
    @exception  None
    """
    template = prompt_template_service.load_prompt(prompt_name)
    placeholder_names = set(re.findall(r"{([A-Za-z_][A-Za-z0-9_]*)}", template))
    rendered_prompt = prompt_template_service.render_prompt(
        prompt_name,
        {key: value for key, value in variables.items() if key in placeholder_names},
    )
    additional_speech_block_instructions = _normalized_additional_speech_block_instructions(
        variables.get("additional_speech_block_instructions")
    )
    if additional_speech_block_instructions and "additional_speech_block_instructions" not in placeholder_names:
        rendered_prompt = _append_additional_speech_block_instructions(
            rendered_prompt,
            additional_speech_block_instructions,
        )
    return rendered_prompt


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
    return {
        "enabled": enabled,
        "placement_policy": placement,
        "duration_seconds": duration_seconds,
        "max_blocks_per_sequence": max_blocks_per_sequence,
        "allowed_positions": allowed_positions,
    }


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


def _normalized_additional_speech_block_instructions(value: object) -> str:
    """
    @brief      Normalize optional operator Speech Blocks rules for prompts and state storage.
    @param[in]  value Candidate instruction text.
    @return     Trimmed instruction text.
    @exception  None
    """
    if value is None:
        return ""
    return str(value).strip()


def _append_additional_speech_block_instructions(prompt_text: str, additional_speech_block_instructions: str) -> str:
    """
    @brief      Append operator Speech Blocks rules to one rendered prompt.
    @param[in]  prompt_text Rendered prompt template text.
    @param[in]  additional_speech_block_instructions Normalized operator rules.
    @return     Prompt text with an additional-rules section.
    @exception  None
    """
    if not additional_speech_block_instructions:
        return prompt_text
    return (
        f"{prompt_text.rstrip()}\n\n"
        f"Additional operator Speech Blocks instructions:\n{additional_speech_block_instructions}\n"
    )


def _compute_prompt_fingerprint(prompt_text: str) -> str:
    """
    @brief      Compute a stable fingerprint for operator-supplied prompt rules.
    @param[in]  prompt_text Operator prompt-rule text.
    @return     SHA-256 fingerprint for the prompt-rule text.
    @exception  None
    """
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


def _build_budget_metadata(
    ai_profile_payload: dict[str, object],
    system_prompt: str,
    prompt_name: str,
    source_language: str,
    speaker_catalog: dict[str, dict[str, object]],
    voice_assignment_mode: str,
    tts_budget: dict[str, object] | None,
    additional_speech_block_instructions: str = "",
) -> BudgetMetadataPayload:
    """
    @brief      Build context-window budget metadata for AI Speech Blocks requests.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  system_prompt Rendered Speech Blocks system prompt.
    @param[in]  prompt_name Active Speech Blocks user prompt template name.
    @param[in]  source_language Active source language code.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  voice_assignment_mode Active project voice-assignment mode.
    @param[in]  tts_budget Optional narrator-only TTS budget metadata.
    @param[in]  additional_speech_block_instructions Optional operator-supplied Speech Blocks rules.
    @return     Context-budget metadata used for source chunk segmentation.
    @exception  ValueError Raised when context and output settings leave too little input room.
    """
    prompt_shell = _chunk_user_prompt(
        {"chunk_id": "", "text": ""},
        source_language,
        speaker_catalog,
        voice_assignment_mode,
        tts_budget,
        prompt_name,
        additional_speech_block_instructions,
    )
    return ai_budget_service.context_budget_metadata(
        ai_profile_payload,
        f"{system_prompt}\n\n{prompt_shell}",
        config.DEFAULT_SPEECH_BLOCKS_MIN_SAFETY_MARGIN_TOKENS,
        config.DEFAULT_SPEECH_BLOCKS_SAFETY_MARGIN_CONTEXT_FRACTION,
        config.DEFAULT_SPEECH_BLOCKS_TEXT_CONTEXT_FRACTION,
        config.DEFAULT_SPEECH_BLOCKS_MIN_TEXT_BUDGET_TOKENS,
        "AI-assisted Speech Blocks generation cannot run because the selected AI profile context window "
        "and max output tokens leave too little room for source chunk input",
        online_text_context_fraction=config.DEFAULT_ONLINE_AI_TEXT_CONTEXT_FRACTION,
    )


def _generate_budgeted_chunk_blocks(
    ai_profile_payload: dict[str, object],
    system_prompt: str,
    source_chunk: dict[str, object],
    source_language: str,
    speaker_catalog: dict[str, dict[str, object]],
    voice_assignment_mode: str,
    tts_budget: dict[str, object] | None,
    prompt_name: str,
    budget_metadata: BudgetMetadataPayload,
    additional_speech_block_instructions: str,
    log_path: Path,
    log_context: dict[str, object],
    cancel_requested,
    cancellation_message: str,
    start_segment_index: int = 0,
    segment_progress_callback=None,
) -> tuple[list[SpeechBlockPayload], list[dict[str, object]], TokenUsagePayload]:
    """
    @brief      Generate one source chunk through budgeted AI request segments.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  system_prompt Rendered Speech Blocks system prompt.
    @param[in]  source_chunk Full source chunk payload.
    @param[in]  source_language Active source language code.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  voice_assignment_mode Active project voice-assignment mode.
    @param[in]  tts_budget Optional narrator-only TTS budget metadata.
    @param[in]  prompt_name Active Speech Blocks user prompt template name.
    @param[in]  budget_metadata Context-budget metadata.
    @param[in]  additional_speech_block_instructions Optional operator-supplied Speech Blocks rules.
    @param[in]  log_path Operation-local AI transaction log path.
    @param[in]  log_context Base AI transaction log context.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  cancellation_message Message used when the request is cancelled.
    @return     Generated Speech Blocks, warning entries, and provider token usage for this chunk.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    """
    if str(voice_assignment_mode).strip() == "same_narrator":
        raise_if_cancelled(cancel_requested)
        chunk_blocks, chunk_warnings = _deterministic_narrator_chunk_blocks(
            source_chunk,
            source_language,
            tts_budget,
        )
        return (
            _renumber_single_chunk_blocks(str(source_chunk.get("chunk_id", "")).strip(), chunk_blocks),
            chunk_warnings,
            token_usage_service.empty_token_usage(),
        )

    chunk_segments = _budgeted_source_chunk_segments(
        source_chunk,
        budget_metadata,
        source_token_cap=_SPEECH_BLOCKS_DIRECT_SOURCE_TOKEN_CAP,
    )
    combined_blocks: list[SpeechBlockPayload] = []
    combined_warnings: list[dict[str, object]] = []
    chunk_token_usage = token_usage_service.empty_token_usage()
    for segment_zero_index, segment_chunk in enumerate(chunk_segments):
        if segment_zero_index < max(0, int(start_segment_index)):
            continue
        segment_index = segment_zero_index + 1
        user_prompt = _chunk_user_prompt(
            segment_chunk,
            source_language,
            speaker_catalog,
            voice_assignment_mode,
            tts_budget,
            prompt_name,
            additional_speech_block_instructions,
        )
        try:
            response_result = _generate_direct_block_response(
                ai_profile_payload,
                system_prompt,
                user_prompt,
                segment_chunk,
                log_path=log_path,
                log_context={
                    **dict(log_context),
                    "segment_index": segment_index,
                    "segment_total": len(chunk_segments),
                    "response_contract": _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT,
                },
                cancel_requested=cancel_requested,
            )
        except OperationCancelledError as error:
            raise OperationCancelledError(cancellation_message) from error
        chunk_token_usage = token_usage_service.merge_token_usage(chunk_token_usage, response_result.get("usage"))
        segment_blocks, segment_warnings = _normalize_chunk_blocks(
            segment_chunk,
            dict(response_result.get("payload", {})),
            speaker_catalog,
            source_language,
            voice_assignment_mode=voice_assignment_mode,
            tts_budget=tts_budget,
        )
        combined_blocks.extend(segment_blocks)
        combined_blocks = _renumber_single_chunk_blocks(
            str(source_chunk.get("chunk_id", "")).strip(),
            combined_blocks,
        )
        combined_warnings.extend(segment_warnings)
        if segment_progress_callback is not None:
            segment_progress_callback(
                list(combined_blocks),
                list(combined_warnings),
                dict(chunk_token_usage),
                segment_index,
                len(chunk_segments),
            )
            raise_if_cancelled(cancel_requested)
    return (
        _renumber_single_chunk_blocks(str(source_chunk.get("chunk_id", "")).strip(), combined_blocks),
        combined_warnings,
        chunk_token_usage,
    )


def _deterministic_narrator_chunk_blocks(
    source_chunk: dict[str, object],
    source_language: str,
    tts_budget: dict[str, object] | None,
) -> tuple[list[SpeechBlockPayload], list[dict[str, object]]]:
    """
    @brief      Segment one source chunk into same-narrator Speech Blocks without any model call.
    @details    Every block keeps whole sentences and the narrator voice, so the only decision
                left is where to place block boundaries, which is purely structural. Blocks the
                TTS budget cannot hold are flagged rather than cut, because Audio Blocks splits
                them again at generation time against the real loaded-model budget.
    @param[in]  source_chunk Source chunk payload, normally one cleaned paragraph.
    @param[in]  source_language Active source language code.
    @param[in]  tts_budget Optional narrator-only TTS budget metadata.
    @return     Generated Speech Blocks plus warning entries.
    @exception  ValueError Raised when segmentation would not reproduce the source chunk.
    """
    chunk_id = str(source_chunk.get("chunk_id", "")).strip()
    planned_blocks = speech_blocks_narrator_split_service.plan_narrator_blocks(
        str(source_chunk.get("text", "")),
        _safe_tts_word_count(tts_budget),
    )
    review_flags = _cleanup_review_warning_flags(source_chunk)

    speech_blocks: list[SpeechBlockPayload] = []
    warning_entries: list[dict[str, object]] = []
    for sequence_index, planned_block in enumerate(planned_blocks, start=1):
        warning_flags = [*list(planned_block.get("warning_flags", [])), *review_flags]
        if speech_blocks_narrator_split_service.NARRATOR_BUDGET_EXCEEDED_FLAG in warning_flags:
            warning_entries.append(
                {
                    "chunk_id": chunk_id,
                    "reason": _speech_block_warning_reason(
                        speech_blocks_narrator_split_service.NARRATOR_BUDGET_EXCEEDED_FLAG
                    ),
                }
            )
        speech_blocks.append(
            _build_speech_block_payload(
                chunk_id,
                sequence_index,
                source_language,
                SPEAKER_KIND_NARRATOR,
                _NARRATOR_SPEAKER_ID,
                _NARRATOR_DISPLAY_NAME,
                CONTENT_KIND_NARRATION,
                str(planned_block.get("text", "")),
                _normalize_warning_flags(warning_flags),
                source_text=str(planned_block.get("source_text", "")),
            )
        )
    if review_flags and speech_blocks:
        warning_entries.append({"chunk_id": chunk_id, "reason": _speech_block_warning_reason("weak_source_boundary")})
    return speech_blocks, warning_entries


def _cleanup_review_warning_flags(source_chunk: dict[str, object]) -> list[str]:
    """
    @brief      Surface uncertain upstream paragraph boundaries as Speech Block review flags.
    @details    Cleanup already decides whether a paragraph was stitched back together across a
                page break and how confident that decision was. Carrying the verdict here is
                what makes a sentence broken by a page separator visible to the operator.
    @param[in]  source_chunk Source chunk payload carrying cleanup provenance.
    @return     Warning flags to attach to every block of this chunk.
    @exception  None
    """
    boundary_confidence = str(source_chunk.get("cleanup_boundary_confidence", "") or "").strip()
    joined_across_page_break = bool(source_chunk.get("cleanup_joined_across_page_break", False))
    if not joined_across_page_break and boundary_confidence in {"", "strong"}:
        return []
    return ["weak_source_boundary", "needs_review"]


def _generate_direct_block_response(
    ai_profile_payload: dict[str, object],
    system_prompt: str,
    user_prompt: str,
    source_chunk: dict[str, object],
    log_path: Path,
    log_context: dict[str, object],
    cancel_requested,
) -> dict[str, object]:
    """
    @brief      Request one direct Speech Blocks response without repair.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  system_prompt Rendered Speech Blocks system prompt.
    @param[in]  user_prompt Rendered Speech Blocks user prompt.
    @param[in]  source_chunk Source chunk or source segment.
    @param[in]  log_path Operation-local AI transaction log path.
    @param[in]  log_context Base AI transaction log context.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Provider result or deterministic segment fallback payload.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    """
    response_schema = _direct_block_response_schema()
    response_schema_name = "speech_blocks_direct_blocks"
    raise_if_cancelled(cancel_requested)
    try:
        response_result = llm_provider_service.chat_json(
            ai_profile_payload,
            system_prompt,
            user_prompt,
            log_path=log_path,
            log_context=log_context,
            cancel_requested=cancel_requested,
            structured_output=True,
            response_schema=response_schema,
            response_schema_name=response_schema_name,
        )
    except ValueError:
        return {
            "payload": {
                "blocks": [
                    {
                        "text": str(source_chunk.get("text", "")),
                        "speaker_id": _NARRATOR_SPEAKER_ID,
                        "content_kind": CONTENT_KIND_NARRATION,
                        "confidence": "low",
                        "warning_flags": ["speech_blocks_ai_parse_failed", "needs_review"],
                    }
                ]
            },
            "usage": token_usage_service.empty_token_usage(),
        }
    raise_if_cancelled(cancel_requested)
    return response_result


def _direct_block_response_schema() -> dict[str, object]:
    """
    @brief      Build the structured-output schema for direct Speech Blocks responses.
    @return     JSON Schema payload.
    @exception  None
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["blocks"],
        "properties": {
            "blocks": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "speaker_id", "content_kind", "confidence", "warning_flags"],
                    "properties": {
                        "text": {"type": "string"},
                        "speaker_id": {"type": "string"},
                        "content_kind": {"type": "string", "enum": ["narration", "dialogue"]},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "warning_flags": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        },
    }


def _compact_source_context_for_prompt(source_chunk: dict[str, object]) -> dict[str, object]:
    """
    @brief      Build non-selectable attribution context for a Speech Blocks prompt.
    @param[in]  source_chunk Source chunk or AI-budget segment payload.
    @return     Previous/next context rows marked as non-selectable.
    @exception  None
    """
    return {
        "previous_context": {
            "available": bool(str(source_chunk.get("previous_context", "")).strip()),
            "selectable": False,
            "text": str(source_chunk.get("previous_context", "")).strip(),
        },
        "next_context": {
            "available": bool(str(source_chunk.get("next_context", "")).strip()),
            "selectable": False,
            "text": str(source_chunk.get("next_context", "")).strip(),
        },
        "rule": "This context may help attribution only. It is not selectable source text.",
    }


def _generate_scene_ambience_blocks(
    ai_profile_payload: dict[str, object],
    source_chunk: dict[str, object],
    source_language: str,
    speech_blocks: list[SpeechBlockPayload],
    scene_ambience_settings: dict[str, object],
    log_path: Path,
    log_context: dict[str, object],
    cancel_requested,
) -> tuple[list[SpeechBlockPayload], TokenUsagePayload]:
    """
    @brief      Generate prompt-based scene ambience blocks for one completed source chunk.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  source_chunk Source chunk payload.
    @param[in]  source_language Active source language code.
    @param[in]  speech_blocks Chunk-local narration and dialogue Speech Blocks.
    @param[in]  scene_ambience_settings Normalized scene-ambience policy payload.
    @param[in]  log_path Operation-local AI transaction log path.
    @param[in]  log_context Base AI transaction log context.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Scene ambience blocks and provider token usage.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    """
    if not speech_blocks:
        return [], token_usage_service.empty_token_usage()
    system_prompt = prompt_template_service.render_prompt("scene_ambience_system", {})
    user_prompt = _scene_ambience_user_prompt(
        source_chunk,
        source_language,
        speech_blocks,
        scene_ambience_settings,
    )
    try:
        response_result = llm_provider_service.chat_json(
            ai_profile_payload,
            system_prompt,
            user_prompt,
            log_path=log_path,
            log_context={**dict(log_context), "response_contract": "scene_ambience_blocks"},
            cancel_requested=cancel_requested,
        )
    except OperationCancelledError as error:
        raise OperationCancelledError(
            "Speech Blocks generation cancelled while waiting for scene ambience analysis."
        ) from error
    return (
        _normalize_scene_ambience_response(
            dict(response_result.get("payload", {})),
            str(source_chunk.get("chunk_id", "")).strip(),
            source_language,
            scene_ambience_settings,
        ),
        token_usage_service.restore_token_usage(response_result.get("usage")),
    )


def _scene_ambience_user_prompt(
    source_chunk: dict[str, object],
    source_language: str,
    speech_blocks: list[SpeechBlockPayload],
    scene_ambience_settings: dict[str, object],
) -> str:
    """
    @brief      Render the scene-ambience chunk prompt.
    @param[in]  source_chunk Source chunk payload.
    @param[in]  source_language Active source language code.
    @param[in]  speech_blocks Chunk-local Speech Blocks.
    @param[in]  scene_ambience_settings Normalized scene-ambience policy payload.
    @return     Rendered scene-ambience prompt text.
    @exception  None
    """
    compact_blocks = [
        {
            "speech_block_id": str(block.get("speech_block_id", "")).strip(),
            "sequence_index": int(block.get("sequence_index", 0)),
            "speaker": str(block.get("speaker_display_name", "")).strip(),
            "content_kind": str(block.get("content_kind", "")).strip(),
            "text": str(block.get("text", "")),
        }
        for block in speech_blocks
    ]
    allowed_positions = list(scene_ambience_settings.get("allowed_positions", []))
    return prompt_template_service.render_prompt(
        "scene_ambience_user",
        {
            "source_language": narrator_definition_service.narrator_language_label(source_language),
            "chunk_id": str(source_chunk.get("chunk_id", "")),
            "chunk_text": str(source_chunk.get("text", "")),
            "placement_policy": str(scene_ambience_settings.get("placement_policy", "")),
            "duration_seconds": str(float(scene_ambience_settings.get("duration_seconds", 10.0))),
            "max_blocks_per_sequence": str(int(scene_ambience_settings.get("max_blocks_per_sequence", 6))),
            "allowed_positions": ", ".join(allowed_positions),
            "speech_blocks_json": json.dumps(compact_blocks, indent=2, ensure_ascii=False),
        },
    )


def _normalize_scene_ambience_response(
    payload: dict[str, object],
    chunk_id: str,
    source_language: str,
    scene_ambience_settings: dict[str, object],
) -> list[SpeechBlockPayload]:
    """
    @brief      Normalize one scene-ambience LLM response into operation Speech Blocks.
    @param[in]  payload Raw JSON response payload.
    @param[in]  chunk_id Current source chunk identifier.
    @param[in]  source_language Active source language code.
    @param[in]  scene_ambience_settings Normalized scene-ambience policy payload.
    @return     Normalized scene-ambience Speech Blocks.
    @exception  None
    """
    raw_blocks = payload.get("scene_ambience_blocks", [])
    if not isinstance(raw_blocks, list):
        return []
    allowed_positions = {str(item) for item in scene_ambience_settings.get("allowed_positions", [])}
    max_sequence_duration = float(scene_ambience_settings.get("duration_seconds", 10.0))
    max_blocks_per_sequence = int(scene_ambience_settings.get("max_blocks_per_sequence", 6))
    normalized_blocks: list[SpeechBlockPayload] = []
    sequence_counts: dict[tuple[str, str], int] = {}
    for raw_block in raw_blocks:
        if not isinstance(raw_block, dict):
            continue
        ambience_position = str(raw_block.get("ambience_position", "")).strip()
        if ambience_position not in allowed_positions:
            continue
        after_speech_block_id = str(raw_block.get("after_speech_block_id", "")).strip()
        sound_prompt = str(raw_block.get("sound_prompt", raw_block.get("text", ""))).strip()
        if not sound_prompt:
            continue
        sequence_key = (ambience_position, after_speech_block_id if ambience_position == "scene_change" else "")
        negative_prompt = str(raw_block.get("negative_prompt", "")).strip()
        if not negative_prompt:
            negative_prompt = "speech, voices, dialogue, singing, music, low quality, distorted"
        remaining_slots = max_blocks_per_sequence - sequence_counts.get(sequence_key, 0)
        if remaining_slots <= 0:
            continue
        split_prompts = _split_composed_scene_ambience_prompt(sound_prompt)[:remaining_slots]
        if not split_prompts:
            continue
        for split_prompt in split_prompts:
            sequence_counts[sequence_key] = sequence_counts.get(sequence_key, 0) + 1
            normalized_blocks.append(
                {
                    "speech_block_id": "",
                    "sequence_index": 0,
                    "chunk_id": chunk_id,
                    "source_language": source_language,
                    "speaker_kind": SPEAKER_KIND_OPERATION,
                    "speaker_id": CONTENT_KIND_SCENE_AMBIENCE,
                    "speaker_display_name": _operation_display_name(CONTENT_KIND_SCENE_AMBIENCE),
                    "content_kind": CONTENT_KIND_SCENE_AMBIENCE,
                    "source_text": "",
                    "text": split_prompt,
                    "sound_prompt": split_prompt,
                    "negative_prompt": negative_prompt,
                    "duration_seconds": max_sequence_duration,
                    "ambience_position": ambience_position,
                    "after_speech_block_id": after_speech_block_id,
                    "warning_flags": [],
                    "approved": False,
                    "approved_at": None,
                }
            )
    return normalized_blocks


def _split_composed_scene_ambience_prompt(sound_prompt: str) -> list[str]:
    """
    @brief      Split one composed Scene Ambience prompt into simple sound-source prompts.
    @param[in]  sound_prompt Candidate sound prompt.
    @return     One or more simple sound prompts.
    @exception  None
    """
    normalized_prompt = " ".join(str(sound_prompt).strip().split())
    if not normalized_prompt:
        return []
    separators = (
        r"\s*;\s*",
        r"\s*,\s*(?=(?:a |an |the |low-volume |subtle |soft |occasional |intermittent |sparse |"
        r"irregular |distant |muffled |fading |shifting |approaching |receding |quiet |faint |"
        r"very faint |steady |sudden |heavy |rapid |rhythmic ))",
        r"\s+(?:and|plus)\s+(?=(?:a |an |the |low-volume |subtle |soft |occasional |intermittent |"
        r"sparse |irregular |distant |muffled |fading |shifting |approaching |receding |quiet |"
        r"faint |very faint |steady |sudden |heavy |rapid |rhythmic ))",
    )
    parts = [normalized_prompt]
    for separator in separators:
        split_parts: list[str] = []
        for part in parts:
            split_parts.extend(re.split(separator, part, flags=re.IGNORECASE))
        parts = split_parts
    normalized_parts: list[str] = []
    for part in parts:
        normalized_part = " ".join(str(part).strip(" .").split())
        if normalized_part and normalized_part not in normalized_parts:
            normalized_parts.append(normalized_part)
    return normalized_parts or [normalized_prompt]


def _insert_scene_ambience_blocks(
    speech_blocks: list[SpeechBlockPayload],
    scene_ambience_blocks: list[SpeechBlockPayload],
) -> list[SpeechBlockPayload]:
    """
    @brief      Insert scene ambience blocks at chunk-local opener, closer, and scene-change positions.
    @param[in]  speech_blocks Chunk-local spoken Speech Blocks.
    @param[in]  scene_ambience_blocks Scene ambience operation Speech Blocks.
    @return     Renumbered chunk-local Speech Blocks including scene ambience.
    @exception  None
    """
    if not scene_ambience_blocks:
        return speech_blocks
    opener_blocks = [
        dict(block) for block in scene_ambience_blocks if str(block.get("ambience_position", "")) == "opener"
    ]
    closer_blocks = [
        dict(block) for block in scene_ambience_blocks if str(block.get("ambience_position", "")) == "closer"
    ]
    scene_change_blocks = [
        dict(block) for block in scene_ambience_blocks if str(block.get("ambience_position", "")) == "scene_change"
    ]
    ordered_blocks: list[SpeechBlockPayload] = [*opener_blocks]
    spoken_block_positions: list[tuple[str, int]] = []
    pending_scene_changes = list(scene_change_blocks)
    for speech_block in speech_blocks:
        spoken_block_positions.append(
            (str(speech_block.get("speech_block_id", "")).strip(), len(ordered_blocks))
        )
        ordered_blocks.append(dict(speech_block))
        speech_block_id = str(speech_block.get("speech_block_id", "")).strip()
        matching_changes = [
            block
            for block in pending_scene_changes
            if str(block.get("after_speech_block_id", "")).strip() == speech_block_id
        ]
        ordered_blocks.extend(matching_changes)
        pending_scene_changes = [block for block in pending_scene_changes if block not in matching_changes]
    ordered_blocks.extend(pending_scene_changes)
    ordered_blocks.extend(closer_blocks)
    chunk_id = str(speech_blocks[0].get("chunk_id", "") if speech_blocks else "").strip()
    renumbered_blocks = _renumber_single_chunk_blocks(chunk_id, ordered_blocks)
    spoken_id_remap = {
        old_id: str(renumbered_blocks[position].get("speech_block_id", "")).strip()
        for old_id, position in spoken_block_positions
        if old_id
    }
    for block in renumbered_blocks:
        if str(block.get("content_kind", "")).strip() != CONTENT_KIND_SCENE_AMBIENCE:
            continue
        after_speech_block_id = str(block.get("after_speech_block_id", "")).strip()
        if after_speech_block_id in spoken_id_remap:
            block["after_speech_block_id"] = spoken_id_remap[after_speech_block_id]
    return renumbered_blocks


def _budgeted_source_chunk_segments(
    source_chunk: dict[str, object],
    budget_metadata: BudgetMetadataPayload,
    source_token_cap: int | None = None,
) -> list[dict[str, object]]:
    """
    @brief      Split one source chunk into AI-context-budgeted request segment payloads.
    @param[in]  source_chunk Full source chunk payload.
    @param[in]  budget_metadata Context-budget metadata.
    @return     Ordered source chunk segment payloads using the original chunk id.
    @exception  None
    """
    text_budget_tokens = int(budget_metadata["text_budget_tokens"])
    if source_token_cap is not None:
        text_budget_tokens = min(text_budget_tokens, max(1, int(source_token_cap)))
    source_text = str(source_chunk.get("text", ""))
    text_segments = _split_text_for_ai_context_budget(source_text, text_budget_tokens)
    if not text_segments:
        return [dict(source_chunk)]
    return [{**dict(source_chunk), "text": text_segment} for text_segment in text_segments]


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
    speech_block_id = str(payload.get("speech_block_id", "")).strip() or _speech_block_id(chunk_id, sequence_index)
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
    next_segment_index: int | None = None,
    completed_segment_count: int | None = None,
    source_chunk_count: int | None = None,
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
    @param[in]  source_chunk_count Optional shared projection count when source rows are unavailable.
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
    state["metadata"] = metadata
    resume_checkpoint = state.get("resume_checkpoint")
    if isinstance(resume_checkpoint, dict):
        resume_checkpoint["additional_speech_block_instructions_fingerprint"] = instruction_fingerprint
        resume_checkpoint["speech_blocks_response_contract"] = response_contract
        if active_chunk_id:
            resume_checkpoint["active_chunk_id"] = str(active_chunk_id)
        if next_segment_index is not None:
            resume_checkpoint["next_segment_index"] = max(0, int(next_segment_index))
        if completed_segment_count is not None:
            resume_checkpoint["completed_segment_count"] = max(0, int(completed_segment_count))
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
    started_at = _resolve_started_at(operation_state if isinstance(operation_state, dict) else {})
    completed_at = None
    log_path = _resolve_log_path(project_root, started_at, operation_state)
    renumbered_blocks = _renumber_speech_blocks(source_chunks, speech_blocks)
    updated_report = _rebuild_report_with_prompt_rules(
        renumbered_blocks,
        source_language,
        source_kind,
        profile_id,
        source_chunk_count,
        len({str(block.get("chunk_id", "")).strip() for block in renumbered_blocks}),
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
    )
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


def _renumber_single_chunk_blocks(
    chunk_id: str,
    speech_blocks: list[SpeechBlockPayload],
) -> list[SpeechBlockPayload]:
    """
    @brief      Recompute block order for one chunk while preserving current list order.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  speech_blocks Current Speech Blocks payload list for the chunk.
    @return     Renumbered Speech Blocks payload list.
    @exception  None
    """
    normalized_chunk_id = str(chunk_id).strip()
    renumbered_blocks: list[SpeechBlockPayload] = []
    used_ids: set[str] = set()
    for sequence_index, block in enumerate(speech_blocks, start=1):
        renumbered_block = dict(block)
        renumbered_block["sequence_index"] = sequence_index
        renumbered_block["chunk_id"] = normalized_chunk_id
        renumbered_block["speech_block_id"] = _stable_speech_block_id(renumbered_block, normalized_chunk_id, used_ids)
        renumbered_blocks.append(renumbered_block)
    return renumbered_blocks


def _continue_chunk_sequence_indices(
    speech_blocks: list[SpeechBlockPayload],
    existing_block_count: int,
) -> list[SpeechBlockPayload]:
    """
    @brief      Continue new chunk-local sequence indices after already persisted rows.
    @param[in]  speech_blocks New Speech Blocks in canonical list order.
    @param[in]  existing_block_count Number of earlier rows retained for the same chunk.
    @return     Copied blocks with contiguous continued sequence indices.
    @exception  None
    """
    sequence_offset = max(0, int(existing_block_count))
    continued_blocks: list[SpeechBlockPayload] = []
    for sequence_index, block in enumerate(speech_blocks, start=sequence_offset + 1):
        continued_block = dict(block)
        continued_block["sequence_index"] = sequence_index
        continued_blocks.append(continued_block)
    return continued_blocks


def _stable_speech_block_id(block: SpeechBlockPayload, chunk_id: str, used_ids: set[str]) -> str:
    """
    @brief      Preserve one existing Speech Block id or allocate a new stable id.
    @param[in]  block Speech Block payload being renumbered.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  used_ids Speech Block ids already emitted in this renumbering pass.
    @return     Stable Speech Block identifier.
    @exception  None
    """
    existing_id = str(block.get("speech_block_id", "")).strip()
    if existing_id and existing_id not in used_ids:
        used_ids.add(existing_id)
        return existing_id
    generated_id = _next_unused_speech_block_id(chunk_id, used_ids)
    used_ids.add(generated_id)
    return generated_id


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


def _next_unused_speech_block_id(chunk_id: str, used_ids: set[str]) -> str:
    """
    @brief      Allocate an id absent from the current Speech Blocks document.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  used_ids Speech Block ids present in the document or emitted in this pass.
    @return     Unused Speech Block identifier.
    @exception  None
    """
    chunk_numeric_prefix = f"{_chunk_order_from_id(chunk_id):04d}"
    next_index = 1
    suffix_pattern = re.compile(rf"^{re.escape(chunk_numeric_prefix)}-(\d+)$")
    for speech_block_id in used_ids:
        match = suffix_pattern.match(speech_block_id)
        if match is not None:
            next_index = max(next_index, int(match.group(1)) + 1)
    candidate_id = _speech_block_id(chunk_id, next_index)
    while candidate_id in used_ids:
        next_index += 1
        candidate_id = _speech_block_id(chunk_id, next_index)
    return candidate_id


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
) -> tuple[list[SpeechBlockPayload], int]:
    """
    @brief      Restore resumable Speech Blocks state when the persisted checkpoint is still valid.
    @param[in]  project_root Active project root folder.
    @param[in]  existing_state Existing operation-state payload.
    @param[in]  input_fingerprint Current source snapshot fingerprint.
    @param[in]  source_language Active source language code.
    @param[in]  source_chunks Ordered current source chunk snapshot.
    @param[in]  additional_speech_block_instructions_fingerprint Operator instruction fingerprint.
    @return     Existing blocks and the next chunk index.
    @exception  None
    """
    if not isinstance(existing_state, dict):
        return [], 0
    if str(existing_state.get("status", "")).strip() not in {"running", "failed", "review_pending", "completed"}:
        return [], 0
    metadata = existing_state.get("metadata", {})
    resume_checkpoint = existing_state.get("resume_checkpoint", {})
    if not isinstance(metadata, dict):
        return [], 0
    if str(metadata.get("source_snapshot_fingerprint", "")).strip() != input_fingerprint:
        return [], 0
    if str(metadata.get("source_language", "")).strip() != source_language:
        return [], 0
    resume_checkpoint_payload = resume_checkpoint if isinstance(resume_checkpoint, dict) else {}
    if not _is_resumable_speech_blocks_response_contract(metadata, resume_checkpoint_payload):
        return [], 0
    stored_instruction_fingerprint = str(
        metadata.get("additional_speech_block_instructions_fingerprint")
        or resume_checkpoint_payload.get("additional_speech_block_instructions_fingerprint")
        or _compute_prompt_fingerprint("")
    )
    if stored_instruction_fingerprint != additional_speech_block_instructions_fingerprint:
        return [], 0
    existing_blocks = load_speech_blocks(project_root)
    next_chunk_index = _restore_next_speech_blocks_chunk_index(
        existing_state,
        resume_checkpoint_payload,
        source_chunks,
        existing_blocks,
    )
    next_segment_index = 0
    if 0 <= next_chunk_index < len(source_chunks):
        raw_segment_index = resume_checkpoint_payload.get("next_segment_index")
        if raw_segment_index not in (None, ""):
            next_segment_index = max(0, int(raw_segment_index))
    active_checkpoint_status = str(existing_state.get("status", "")).strip() in {"running", "failed"}
    if next_chunk_index <= 0 and next_segment_index <= 0 and (active_checkpoint_status or not existing_blocks):
        return [], 0
    return existing_blocks, next_chunk_index


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


def _restore_next_speech_blocks_segment_index(
    existing_state: dict[str, object],
    source_chunks: list[dict[str, object]],
    next_chunk_index: int,
) -> int:
    """
    @brief      Restore the next segment index for an active direct-block chunk.
    @param[in]  existing_state Existing operation-state payload.
    @param[in]  source_chunks Current source chunk snapshot.
    @param[in]  next_chunk_index Restored next chunk index.
    @return     Zero-based segment index to resume inside the active chunk.
    @exception  None
    """
    if not isinstance(existing_state, dict):
        return 0
    resume_checkpoint = existing_state.get("resume_checkpoint", {})
    if not isinstance(resume_checkpoint, dict):
        return 0
    checkpoint_contract = str(resume_checkpoint.get("speech_blocks_response_contract", "")).strip()
    if checkpoint_contract != _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT:
        return 0
    if next_chunk_index < 0 or next_chunk_index >= len(source_chunks):
        return 0
    active_chunk_id = str(resume_checkpoint.get("active_chunk_id", "")).strip()
    expected_chunk_id = str(source_chunks[next_chunk_index].get("chunk_id", "")).strip()
    if active_chunk_id and active_chunk_id != expected_chunk_id:
        return 0
    raw_segment_index = resume_checkpoint.get("next_segment_index")
    if raw_segment_index in (None, ""):
        return 0
    return max(0, int(raw_segment_index))


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
