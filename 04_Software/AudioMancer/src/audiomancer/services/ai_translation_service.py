#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_translation_service.py
@brief AI-assisted translation backed by one authoritative project document.
@details Persists translation text, review state, usage, budget, and resumable
         operation status exclusively in `translated_text.json`.
@author Eng. Dan Dumitru Pasare
@date 2026-07-16
@version 0.14.0
"""

# IMPORTS

import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import (
    ai_budget_service,
    chunking_document_service,
    llm_provider_service,
    prompt_template_service,
    token_usage_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS,
    OperationCancelledError,
    build_operation_output_path,
    raise_if_cancelled,
    reset_operation_data,
)
from audiomancer.services.operation_runtime_service import emit_progress_update as _emit_progress
from audiomancer.services.persistence_service import write_json_atomic
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

_AI_TRANSLATION_LOGGER = get_component_logger("ai_translation")
_TRANSLATION_LANGUAGE_LABELS = dict(config.TRANSLATION_LANGUAGE_OPTIONS)

TRANSLATION_STATUS_NOT_STARTED = "not_started"
TRANSLATION_STATUS_RUNNING = "running"
TRANSLATION_STATUS_IN_PROGRESS = "in_progress"
TRANSLATION_STATUS_CANCELLED = "cancelled"
TRANSLATION_STATUS_FAILED = "failed"
TRANSLATION_STATUS_REVIEW_PENDING = "review_pending"
TRANSLATION_STATUS_COMPLETED = "completed"
TRANSLATION_STATUS_INVALID = "invalid"

_PERSISTED_STATUSES = frozenset(
    (
        TRANSLATION_STATUS_RUNNING,
        TRANSLATION_STATUS_IN_PROGRESS,
        TRANSLATION_STATUS_CANCELLED,
        TRANSLATION_STATUS_FAILED,
        TRANSLATION_STATUS_REVIEW_PENDING,
        TRANSLATION_STATUS_COMPLETED,
    )
)
_RESUMABLE_STATUSES = frozenset(
    (
        TRANSLATION_STATUS_RUNNING,
        TRANSLATION_STATUS_IN_PROGRESS,
        TRANSLATION_STATUS_CANCELLED,
        TRANSLATION_STATUS_FAILED,
    )
)
_DOCUMENT_FIELDS = frozenset(
    (
        "target_language",
        "status",
        "token_usage",
        "budget_metadata",
        "additional_translation_instructions",
        "chunks",
    )
)
_CHUNK_FIELDS = frozenset(("chunk_id", "translated_text", "approved"))

TokenUsagePayload = dict[str, object]
BudgetMetadataPayload = dict[str, int]
TranslationDocumentPayload = dict[str, object]


# DATA MODELS / TYPEDEFINITIONS


class TranslationDocumentError(ValueError):
    """Raised when persisted translation data does not match the strict contract."""


# PUBLIC API


@trace_function(_AI_TRANSLATION_LOGGER)
def load_translation_document(project_root: str | Path) -> TranslationDocumentPayload | None:
    """Load and strictly validate the authoritative translation document."""
    document_path = build_operation_output_path(
        project_root,
        "translation",
        config.TRANSLATED_CHUNKS_FILE_NAME,
    )
    if not document_path.is_file():
        return None
    try:
        payload = json.loads(document_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _incompatible_document_error("The file is not valid JSON.") from exc
    _validate_translation_document(payload)
    return dict(payload)


@trace_function(_AI_TRANSLATION_LOGGER)
def write_translation_document(
    project_root: str | Path,
    document: TranslationDocumentPayload,
) -> Path:
    """Validate and atomically persist the authoritative translation document."""
    _validate_translation_document(document)
    document_path = build_operation_output_path(
        project_root,
        "translation",
        config.TRANSLATED_CHUNKS_FILE_NAME,
    )
    write_json_atomic(document_path, document)
    return document_path


@trace_function(_AI_TRANSLATION_LOGGER)
def load_translated_chunks(project_root: str | Path) -> list[dict[str, object]]:
    """Return minimal translated chunk records from the authoritative document."""
    document = load_translation_document(project_root)
    if document is None:
        return []
    return [dict(item) for item in document["chunks"]]


@trace_function(_AI_TRANSLATION_LOGGER)
def load_translation_summary(project_root: str | Path) -> dict[str, object]:
    """Build the effective translation summary without mutating project data."""
    source_chunks = chunking_document_service.load_chunks(project_root)
    return build_translation_summary(source_chunks, load_translation_document(project_root))


def build_translation_summary(
    source_chunks: list[dict[str, object]],
    document: TranslationDocumentPayload | None,
) -> dict[str, object]:
    """Derive counts and effective status from canonical chunks and one document."""
    total_count = len(source_chunks)
    if document is None:
        return {
            "status": TRANSLATION_STATUS_NOT_STARTED,
            "translated_count": 0,
            "approved_count": 0,
            "total_count": total_count,
            "warning_count": 0,
            "target_language": "",
            "token_usage": token_usage_service.empty_token_usage(),
        }
    chunks_by_id = {str(item["chunk_id"]): item for item in document["chunks"]}
    canonical_chunks = [
        chunks_by_id.get(str(source_chunk.get("chunk_id", "")))
        for source_chunk in _canonical_source_chunks(source_chunks)
    ]
    translated_count = sum(
        item is not None and bool(str(item["translated_text"]).strip()) for item in canonical_chunks
    )
    approved_count = sum(
        item is not None
        and bool(item["approved"])
        and bool(str(item["translated_text"]).strip())
        for item in canonical_chunks
    )
    persisted_status = str(document["status"])
    if persisted_status in {
        TRANSLATION_STATUS_RUNNING,
        TRANSLATION_STATUS_CANCELLED,
        TRANSLATION_STATUS_FAILED,
    }:
        effective_status = persisted_status
    elif total_count > 0 and translated_count == total_count and approved_count == total_count:
        effective_status = TRANSLATION_STATUS_COMPLETED
    elif total_count > 0 and translated_count == total_count:
        effective_status = TRANSLATION_STATUS_REVIEW_PENDING
    else:
        effective_status = TRANSLATION_STATUS_IN_PROGRESS
    return {
        "status": effective_status,
        "translated_count": translated_count,
        "approved_count": approved_count,
        "total_count": total_count,
        "warning_count": 0,
        "target_language": str(document["target_language"]),
        "token_usage": dict(document["token_usage"]),
    }


def translation_is_completed(project_root: str | Path) -> bool:
    """Return whether the strict translation document is fully approved."""
    return str(load_translation_summary(project_root)["status"]) == TRANSLATION_STATUS_COMPLETED


@trace_function(_AI_TRANSLATION_LOGGER)
def sync_translation_after_chunk_change(
    project_root: str | Path,
    target_language: str,
    invalidated_chunk_ids: list[str] | tuple[str, ...] | set[str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    """Synchronize an existing translation document after canonical chunk changes."""
    resolved_project_root = Path(project_root)
    source_chunks = chunking_document_service.load_chunks(resolved_project_root)
    if not source_chunks:
        raise ValueError("Run text chunking before synchronizing AI translation.")
    document = load_translation_document(resolved_project_root)
    if document is None:
        return source_chunks, [], build_translation_summary(source_chunks, None)
    if str(document["target_language"]) != target_language:
        raise _incompatible_document_error("The saved target language differs from the project.")
    synchronized = _synchronize_document_chunks(document, source_chunks, invalidated_chunk_ids)
    if synchronized:
        document["status"] = _review_status(document["chunks"])
        write_translation_document(resolved_project_root, document)
    return source_chunks, [dict(item) for item in document["chunks"]], build_translation_summary(
        source_chunks,
        document,
    )


@trace_function(_AI_TRANSLATION_LOGGER)
def start_or_continue_translation(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    target_language: str,
    progress_callback=None,
    cancel_requested=None,
    additional_translation_instructions: str | None = None,
) -> dict[str, object]:
    """Translate empty canonical chunks and checkpoint only complete chunks."""
    resolved_project_root = Path(project_root)
    _validate_translation_inputs(ai_profile_payload, target_language)
    source_chunks = chunking_document_service.load_chunks(resolved_project_root)
    if not source_chunks:
        raise ValueError("Run text chunking before starting AI translation.")
    source_chunks = _canonical_source_chunks(source_chunks)
    existing_document = load_translation_document(resolved_project_root)
    if existing_document is None:
        instructions = _normalized_additional_translation_instructions(additional_translation_instructions)
        document = _new_translation_document(source_chunks, target_language, instructions)
    else:
        document = existing_document
        if str(document["target_language"]) != target_language:
            raise _incompatible_document_error("The saved target language differs from the project.")
        _synchronize_document_chunks(document, source_chunks, ())
        if str(document["status"]) in _RESUMABLE_STATUSES:
            instructions = str(document["additional_translation_instructions"])
        else:
            instructions = str(document["additional_translation_instructions"])
    prompt_template_service.validate_required_prompts(["text_translation_system", "text_translation_user"])
    system_prompt = prompt_template_service.render_prompt("text_translation_system", {})
    budget_metadata = _build_budget_metadata(
        ai_profile_payload,
        target_language,
        system_prompt,
        instructions,
    )
    document["budget_metadata"] = budget_metadata
    document["additional_translation_instructions"] = instructions
    document["status"] = TRANSLATION_STATUS_RUNNING
    write_translation_document(resolved_project_root, document)
    token_usage = token_usage_service.restore_token_usage(document["token_usage"])
    log_path = _resolve_log_path(resolved_project_root)
    _emit_progress(
        progress_callback,
        _translated_count(document["chunks"]),
        len(document["chunks"]),
        "AI translation in progress...",
        token_usage,
    )
    try:
        for source_chunk, translated_chunk in zip(source_chunks, document["chunks"], strict=True):
            raise_if_cancelled(cancel_requested)
            if str(translated_chunk["translated_text"]).strip():
                continue
            translated_text, token_usage = _translate_text_in_budgeted_segments(
                manifest,
                ai_profile_payload,
                str(source_chunk.get("text", "")),
                target_language,
                system_prompt,
                int(source_chunk.get("sequence_index", 0)),
                len(source_chunks),
                log_path,
                token_usage,
                budget_metadata,
                instructions,
                progress_callback=progress_callback,
                translated_chunk_count=_translated_count(document["chunks"]),
                cancel_requested=cancel_requested,
            )
            translated_chunk["translated_text"] = translated_text
            translated_chunk["approved"] = False
            document["token_usage"] = token_usage
            write_translation_document(resolved_project_root, document)
            _emit_progress(
                progress_callback,
                _translated_count(document["chunks"]),
                len(document["chunks"]),
                "AI translation in progress...",
                token_usage,
            )
    except OperationCancelledError:
        document["status"] = TRANSLATION_STATUS_CANCELLED
        document["token_usage"] = token_usage
        write_translation_document(resolved_project_root, document)
        raise
    except Exception:
        document["status"] = TRANSLATION_STATUS_FAILED
        document["token_usage"] = token_usage
        write_translation_document(resolved_project_root, document)
        raise
    document["status"] = _review_status(document["chunks"])
    document["token_usage"] = token_usage
    write_translation_document(resolved_project_root, document)
    return build_translation_summary(source_chunks, document)


@trace_function(_AI_TRANSLATION_LOGGER)
def retranslate_chunk(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    target_language: str,
    chunk_id: str,
    progress_callback=None,
    cancel_requested=None,
    additional_translation_instructions: str | None = None,
) -> dict[str, object]:
    """Re-translate one chunk without clearing its prior text or approval first."""
    resolved_project_root = Path(project_root)
    _validate_translation_inputs(ai_profile_payload, target_language)
    source_chunks = chunking_document_service.load_chunks(resolved_project_root)
    document = load_translation_document(resolved_project_root)
    if document is None:
        raise ValueError("Start AI translation before re-translating a chunk.")
    if str(document["target_language"]) != target_language:
        raise _incompatible_document_error("The saved target language differs from the project.")
    source_by_id = {str(item.get("chunk_id", "")): item for item in source_chunks}
    translated_by_id = {str(item["chunk_id"]): item for item in document["chunks"]}
    if chunk_id not in source_by_id or chunk_id not in translated_by_id:
        raise ValueError(f"Unknown translation chunk: {chunk_id}")
    prompt_template_service.validate_required_prompts(["text_translation_system", "text_translation_user"])
    system_prompt = prompt_template_service.render_prompt("text_translation_system", {})
    one_off_instructions = _normalized_additional_translation_instructions(additional_translation_instructions)
    budget_metadata = _build_budget_metadata(
        ai_profile_payload,
        target_language,
        system_prompt,
        one_off_instructions,
    )
    token_usage = token_usage_service.restore_token_usage(document["token_usage"])
    log_path = _resolve_log_path(resolved_project_root)
    selected_source = source_by_id[chunk_id]
    try:
        translated_text, token_usage = _translate_text_in_budgeted_segments(
            manifest,
            ai_profile_payload,
            str(selected_source.get("text", "")),
            target_language,
            system_prompt,
            int(selected_source.get("sequence_index", 0)),
            len(source_chunks),
            log_path,
            token_usage,
            budget_metadata,
            one_off_instructions,
            progress_callback=progress_callback,
            translated_chunk_count=_translated_count(document["chunks"]),
            cancel_requested=cancel_requested,
        )
    except OperationCancelledError:
        document["status"] = TRANSLATION_STATUS_CANCELLED
        document["token_usage"] = token_usage
        write_translation_document(resolved_project_root, document)
        raise
    except Exception:
        document["status"] = TRANSLATION_STATUS_FAILED
        document["token_usage"] = token_usage
        write_translation_document(resolved_project_root, document)
        raise
    selected = translated_by_id[chunk_id]
    selected["translated_text"] = translated_text
    selected["approved"] = False
    document["budget_metadata"] = budget_metadata
    document["token_usage"] = token_usage
    document["status"] = _review_status(document["chunks"])
    write_translation_document(resolved_project_root, document)
    return build_translation_summary(source_chunks, document)


@trace_function(_AI_TRANSLATION_LOGGER)
def update_translated_text(
    project_root: str | Path,
    chunk_id: str,
    translated_text: str,
) -> dict[str, object]:
    """Persist one manual edit and invalidate approval when text changed."""
    document = _required_translation_document(project_root)
    selected = _find_document_chunk(document, chunk_id)
    if str(selected["translated_text"]) != translated_text:
        selected["translated_text"] = translated_text
        selected["approved"] = False
    document["status"] = _review_status(document["chunks"])
    write_translation_document(project_root, document)
    return load_translation_summary(project_root)


@trace_function(_AI_TRANSLATION_LOGGER)
def approve_chunk(project_root: str | Path, chunk_id: str) -> dict[str, object]:
    """Approve one non-empty translated chunk in one atomic write."""
    document = _required_translation_document(project_root)
    selected = _find_document_chunk(document, chunk_id)
    if not str(selected["translated_text"]).strip():
        raise ValueError("Translate the selected chunk before approving it.")
    selected["approved"] = True
    document["status"] = _review_status(document["chunks"])
    write_translation_document(project_root, document)
    return load_translation_summary(project_root)


@trace_function(_AI_TRANSLATION_LOGGER)
def approve_all(project_root: str | Path) -> dict[str, object]:
    """Approve every non-empty translated chunk in one atomic write."""
    document = _required_translation_document(project_root)
    for chunk in document["chunks"]:
        if str(chunk["translated_text"]).strip():
            chunk["approved"] = True
    document["status"] = _review_status(document["chunks"])
    write_translation_document(project_root, document)
    return load_translation_summary(project_root)


@trace_function(_AI_TRANSLATION_LOGGER)
def reset_translation(project_root: str | Path) -> None:
    """Delete translation and downstream runtime artifacts while preserving narrator profiles."""
    reset_operation_data(
        project_root,
        "translation",
        include_current=True,
        preserve_operation_kinds=NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS,
    )


# LOCAL HELPERS


def _validate_translation_document(payload: object) -> None:
    """Validate exact root and chunk fields without migrating legacy payloads."""
    if not isinstance(payload, dict):
        raise _incompatible_document_error("The root must be an object.")
    if set(payload) != _DOCUMENT_FIELDS:
        raise _incompatible_document_error("The root fields do not match the current contract.")
    if not isinstance(payload["target_language"], str) or not str(payload["target_language"]).strip():
        raise _incompatible_document_error("target_language must be a non-empty string.")
    if payload["status"] not in _PERSISTED_STATUSES:
        raise _incompatible_document_error("status is not supported.")
    if not isinstance(payload["token_usage"], dict):
        raise _incompatible_document_error("token_usage must be an object.")
    if not isinstance(payload["budget_metadata"], dict):
        raise _incompatible_document_error("budget_metadata must be an object.")
    if not isinstance(payload["additional_translation_instructions"], str):
        raise _incompatible_document_error("additional_translation_instructions must be a string.")
    chunks = payload["chunks"]
    if not isinstance(chunks, list):
        raise _incompatible_document_error("chunks must be an array.")
    chunk_ids: set[str] = set()
    for item in chunks:
        if not isinstance(item, dict) or set(item) != _CHUNK_FIELDS:
            raise _incompatible_document_error("Each chunk must contain only chunk_id, translated_text, approved.")
        chunk_id = item["chunk_id"]
        if not isinstance(chunk_id, str) or not chunk_id.strip() or chunk_id in chunk_ids:
            raise _incompatible_document_error("Each chunk_id must be a unique non-empty string.")
        if not isinstance(item["translated_text"], str) or type(item["approved"]) is not bool:
            raise _incompatible_document_error("Each chunk requires string translated_text and boolean approved.")
        if item["approved"] and not item["translated_text"].strip():
            raise _incompatible_document_error("An empty translation cannot be approved.")
        chunk_ids.add(chunk_id)


def _incompatible_document_error(reason: str) -> TranslationDocumentError:
    """Build the operator-facing strict-contract error."""
    return TranslationDocumentError(
        f"Translation data is incompatible: {reason} Use Reset Translation before continuing."
    )


def _new_translation_document(
    source_chunks: list[dict[str, object]],
    target_language: str,
    instructions: str,
) -> TranslationDocumentPayload:
    """Build a new strict document in canonical source order."""
    return {
        "target_language": target_language,
        "status": TRANSLATION_STATUS_IN_PROGRESS,
        "token_usage": token_usage_service.empty_token_usage(),
        "budget_metadata": {},
        "additional_translation_instructions": instructions,
        "chunks": [
            {
                "chunk_id": str(item.get("chunk_id", "")),
                "translated_text": "",
                "approved": False,
            }
            for item in _canonical_source_chunks(source_chunks)
        ],
    }


def _synchronize_document_chunks(
    document: TranslationDocumentPayload,
    source_chunks: list[dict[str, object]],
    invalidated_chunk_ids: list[str] | tuple[str, ...] | set[str],
) -> bool:
    """Align document chunks to canonical IDs while preserving unaffected records."""
    invalidated_ids = {str(value).strip() for value in invalidated_chunk_ids if str(value).strip()}
    existing_by_id = {str(item["chunk_id"]): item for item in document["chunks"]}
    synchronized_chunks: list[dict[str, object]] = []
    for source_chunk in _canonical_source_chunks(source_chunks):
        chunk_id = str(source_chunk.get("chunk_id", "")).strip()
        existing = existing_by_id.get(chunk_id)
        if existing is None or chunk_id in invalidated_ids:
            synchronized_chunks.append({"chunk_id": chunk_id, "translated_text": "", "approved": False})
        else:
            synchronized_chunks.append(dict(existing))
    changed = synchronized_chunks != document["chunks"]
    if changed:
        document["chunks"] = synchronized_chunks
    return changed


def _canonical_source_chunks(source_chunks: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return canonical chunks ordered by sequence index."""
    return sorted(source_chunks, key=lambda item: int(item.get("sequence_index", 0)))


def _review_status(chunks: object) -> str:
    """Derive the persisted review status after a durable non-operation action."""
    chunk_items = list(chunks) if isinstance(chunks, list) else []
    if chunk_items and all(str(item["translated_text"]).strip() for item in chunk_items):
        if all(bool(item["approved"]) for item in chunk_items):
            return TRANSLATION_STATUS_COMPLETED
        return TRANSLATION_STATUS_REVIEW_PENDING
    return TRANSLATION_STATUS_IN_PROGRESS


def _required_translation_document(project_root: str | Path) -> TranslationDocumentPayload:
    """Load the document or reject review actions before translation exists."""
    document = load_translation_document(project_root)
    if document is None:
        raise ValueError("Start AI translation before reviewing translated chunks.")
    return document


def _find_document_chunk(document: TranslationDocumentPayload, chunk_id: str) -> dict[str, object]:
    """Return one mutable chunk record by identifier."""
    for item in document["chunks"]:
        if str(item["chunk_id"]) == chunk_id:
            return item
    raise ValueError(f"Unknown translation chunk: {chunk_id}")


def _validate_translation_inputs(ai_profile_payload: dict[str, object], target_language: str) -> None:
    """Validate current profile and target language before an AI request."""
    required_profile_fields = ("id", "model_name", "base_url")
    if any(not str(ai_profile_payload.get(field, "")).strip() for field in required_profile_fields):
        raise ValueError("AI translation requires a valid enabled AI profile.")
    if target_language not in _TRANSLATION_LANGUAGE_LABELS:
        raise ValueError("AI translation requires a valid target language.")


def _translated_count(chunks: object) -> int:
    """Count non-empty translated chunks."""
    return sum(bool(str(item["translated_text"]).strip()) for item in list(chunks))


def _resolve_log_path(project_root: Path) -> Path:
    """Create an operation-local AI transaction log without persisting its path."""
    timestamp_token = _utc_now_iso().replace("-", "").replace(":", "").replace("+", "_").replace(".", "")
    log_path = build_operation_output_path(
        project_root,
        "translation",
        config.ai_transaction_log_file_name("translation", timestamp_token),
    )
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")
    return log_path


def _translate_text_in_budgeted_segments(
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    source_text: str,
    target_language: str,
    system_prompt: str,
    chunk_sequence_index: int,
    total_chunks: int,
    log_path: Path,
    token_usage: TokenUsagePayload,
    budget_metadata: BudgetMetadataPayload,
    additional_translation_instructions: str,
    progress_callback=None,
    translated_chunk_count: int = 0,
    cancel_requested=None,
) -> tuple[str, TokenUsagePayload]:
    """Translate one chunk locally so partial segments never become checkpoints."""
    translated_segments: list[str] = []
    cumulative_usage = token_usage
    for segment_index, source_segment in enumerate(
        _split_translation_source_text(source_text, int(budget_metadata["text_budget_tokens"])),
        start=1,
    ):
        raise_if_cancelled(cancel_requested)
        user_prompt = _render_translation_user_prompt(
            target_language,
            source_segment,
            additional_translation_instructions,
        )
        response_result = llm_provider_service.chat_json(
            ai_profile_payload,
            system_prompt,
            user_prompt,
            log_path=log_path,
            log_context={
                "operation_kind": "translation",
                "stage_label": "ai_translation",
                "profile_id": str(ai_profile_payload.get("id", "")),
                "strategy": f"{target_language}|segment {segment_index}",
                "window_index": chunk_sequence_index,
                "window_total": total_chunks,
                "project_id": str(manifest.get("project_id", "")),
            },
            cancel_requested=cancel_requested,
        )
        if isinstance(response_result, dict):
            merged_usage = token_usage_service.merge_token_usage(
                cumulative_usage,
                response_result.get("usage"),
            )
            cumulative_usage.clear()
            cumulative_usage.update(merged_usage)
        if not isinstance(response_result, dict) or not isinstance(response_result.get("payload"), dict):
            raise ValueError("AI translation returned an invalid JSON response object.")
        translated_value = response_result["payload"].get("translated_text")
        if not isinstance(translated_value, str) or not translated_value.strip():
            raise ValueError("AI translation returned an invalid or empty translated_text value.")
        translated_segments.append(translated_value.strip())
        _emit_progress(
            progress_callback,
            translated_chunk_count,
            total_chunks,
            "AI translation in progress...",
            cumulative_usage,
        )
    return "\n\n".join(translated_segments), cumulative_usage


def _build_budget_metadata(
    ai_profile_payload: dict[str, object],
    target_language: str,
    system_prompt: str,
    additional_translation_instructions: str = "",
) -> BudgetMetadataPayload:
    """Build current-profile context budgeting for the translation request."""
    user_prompt_shell = _render_translation_user_prompt(
        target_language,
        "(none)",
        additional_translation_instructions,
    )
    return ai_budget_service.context_budget_metadata(
        ai_profile_payload,
        f"{system_prompt}\n\n{user_prompt_shell}",
        config.DEFAULT_AI_TRANSLATION_MIN_SAFETY_MARGIN_TOKENS,
        config.DEFAULT_AI_TRANSLATION_SAFETY_MARGIN_CONTEXT_FRACTION,
        config.DEFAULT_AI_TRANSLATION_TEXT_CONTEXT_FRACTION,
        config.DEFAULT_AI_TRANSLATION_MIN_TEXT_BUDGET_TOKENS,
        "AI translation cannot run because the selected AI profile context window "
        "and max output tokens leave too little room for translation input",
    )


def _render_translation_user_prompt(
    target_language: str,
    source_text: str,
    additional_translation_instructions: str,
) -> str:
    """Render only per-request values into the translation user prompt."""
    instructions = _normalized_additional_translation_instructions(additional_translation_instructions)
    instruction_block = (
        f"Additional translation instructions:\n{instructions}\n\n" if instructions else ""
    )
    return prompt_template_service.render_prompt(
        "text_translation_user",
        {
            "target_language": target_language,
            "additional_translation_instructions_block": instruction_block,
            "source_text": source_text,
        },
    )


def _normalized_additional_translation_instructions(value: object) -> str:
    """Normalize optional operator translation rules."""
    return "" if value is None else str(value).strip()


def _split_translation_source_text(source_text: str, usable_input_budget: int) -> list[str]:
    """Split source text into paragraph-preserving budget-safe segments."""
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", source_text.strip()) if item.strip()]
    if not paragraphs:
        return [source_text.strip()]
    segments: list[str] = []
    current_segment: list[str] = []
    current_budget = 0
    for paragraph in paragraphs:
        for part in _split_oversized_translation_paragraph(paragraph, usable_input_budget):
            next_budget = _estimate_text_tokens(part)
            if current_segment and current_budget + next_budget > usable_input_budget:
                segments.append("\n\n".join(current_segment))
                current_segment = []
                current_budget = 0
            current_segment.append(part)
            current_budget += next_budget
    if current_segment:
        segments.append("\n\n".join(current_segment))
    return segments or [source_text.strip()]


def _split_oversized_translation_paragraph(paragraph: str, usable_input_budget: int) -> list[str]:
    """Split an oversized paragraph into sentence and word-based units."""
    if _estimate_text_tokens(paragraph) <= usable_input_budget:
        return [paragraph]
    sentences = _split_translation_sentences(paragraph)
    if len(sentences) <= 1:
        return _split_translation_sentence_by_words(paragraph, usable_input_budget)
    parts: list[str] = []
    current_part: list[str] = []
    current_budget = 0
    for sentence in sentences:
        next_budget = _estimate_text_tokens(sentence)
        if current_part and current_budget + next_budget > usable_input_budget:
            parts.append(" ".join(current_part).strip())
            current_part = []
            current_budget = 0
        if next_budget > usable_input_budget:
            if current_part:
                parts.append(" ".join(current_part).strip())
                current_part = []
                current_budget = 0
            parts.extend(_split_translation_sentence_by_words(sentence, usable_input_budget))
            continue
        current_part.append(sentence)
        current_budget += next_budget
    if current_part:
        parts.append(" ".join(current_part).strip())
    return parts or [paragraph]


def _split_translation_sentences(paragraph: str) -> list[str]:
    """Split a paragraph into approximate sentence units."""
    normalized = paragraph.strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=(?:[\"'A-Z0-9]))", normalized)
    return [part.strip() for part in parts if part.strip()]


def _split_translation_sentence_by_words(text: str, usable_input_budget: int) -> list[str]:
    """Split an oversized sentence into word-based units."""
    words = text.split()
    if not words:
        return [text.strip()]
    parts: list[str] = []
    current_words: list[str] = []
    current_budget = 0
    for word in words:
        next_budget = _estimate_text_tokens(word)
        if current_words and current_budget + next_budget > usable_input_budget:
            parts.append(" ".join(current_words))
            current_words = []
            current_budget = 0
        current_words.append(word)
        current_budget += next_budget
    if current_words:
        parts.append(" ".join(current_words))
    return parts or [text.strip()]


def _estimate_text_tokens(text: str) -> int:
    """Estimate tokens with the shared AI budgeting heuristic."""
    return ai_budget_service.estimate_text_tokens(text)


# END OF FILE
