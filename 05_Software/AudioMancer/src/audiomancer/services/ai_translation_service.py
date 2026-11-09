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
"""

# IMPORTS

import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    chunking_document_service,
    project_workspace_service,
    prompt_template_service,
    token_usage_service,
)
from audiomancer.services import (
    llm_provider_service as llm_provider_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    build_operation_output_path,
    raise_if_cancelled,
)
from audiomancer.services.operation_runtime_service import emit_progress_update as _emit_progress
from audiomancer.services.persistence_service import ProjectFileRecoveryError, write_json_atomic
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso
from audiomancer.services.translation_ai_service import (
    _build_budget_metadata,
    _normalized_additional_translation_instructions,
    _translate_text_in_budgeted_segments,
    request_fingerprint,
)
from audiomancer.services.translation_publication_service import publish_translation
from audiomancer.translation import document as translation_document
from audiomancer.translation.document import (
    _RESUMABLE_STATUSES,
    _TRANSLATION_LANGUAGE_LABELS,
    canonical_source_chunks,
    incompatible_document_error,
    new_translation_document,
    review_status,
    source_fingerprint,
    synchronize_document_chunks,
    validate_translation_document,
)

# CONSTANTS

_AI_TRANSLATION_LOGGER = get_component_logger("ai_translation")
TranslationDocumentPayload = dict[str, object]


# PUBLIC DOCUMENT CONTRACT

TRANSLATION_STATUS_CANCELLED = translation_document.TRANSLATION_STATUS_CANCELLED
TRANSLATION_STATUS_COMPLETED = translation_document.TRANSLATION_STATUS_COMPLETED
TRANSLATION_STATUS_FAILED = translation_document.TRANSLATION_STATUS_FAILED
TRANSLATION_STATUS_IN_PROGRESS = translation_document.TRANSLATION_STATUS_IN_PROGRESS
TRANSLATION_STATUS_INVALID = translation_document.TRANSLATION_STATUS_INVALID
TRANSLATION_STATUS_NOT_STARTED = translation_document.TRANSLATION_STATUS_NOT_STARTED
TRANSLATION_STATUS_REVIEW_PENDING = translation_document.TRANSLATION_STATUS_REVIEW_PENDING
TRANSLATION_STATUS_RUNNING = translation_document.TRANSLATION_STATUS_RUNNING
TranslationDocumentError = translation_document.TranslationDocumentError
aligned_chunks = translation_document.aligned_chunks
build_translation_summary = translation_document.build_translation_summary
resolve_approved_translation = translation_document.resolve_approved_translation

# PUBLIC API


def manifest_target_language(manifest: dict[str, object]) -> str:
    """
    @brief      Resolve the supported translation target language from a manifest.
    @param[in]  manifest Active project manifest payload.
    @return     Supported target-language token or the configured default.
    @exception  None
    """
    candidate = str(manifest.get("target_language", config.DEFAULT_TRANSLATION_TARGET_LANGUAGE)).strip()
    if candidate in _TRANSLATION_LANGUAGE_LABELS:
        return candidate
    return config.DEFAULT_TRANSLATION_TARGET_LANGUAGE


@trace_function(_AI_TRANSLATION_LOGGER)
def load_translation_document(project_root: str | Path) -> TranslationDocumentPayload | None:
    """
    @brief      Load and strictly validate the authoritative translation document.
    @param[in]  project_root Active project root folder.
    @return     Loaded translation document.
    @exception  Exception Raised when the file is not valid JSON.
    """
    document_path = build_operation_output_path(
        project_root,
        "translation",
        config.TRANSLATED_CHUNKS_FILE_NAME,
    )
    if not document_path.is_file():
        return None
    try:
        payload = json.loads(document_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise incompatible_document_error("The file is not valid JSON.") from exc
    validate_translation_document(payload)
    return dict(payload)


@trace_function(_AI_TRANSLATION_LOGGER)
def write_translation_document(
    project_root: str | Path,
    document: TranslationDocumentPayload,
) -> Path:
    """
    @brief      Validate and atomically persist the authoritative translation document.
    @param[in]  project_root Active project root folder.
    @param[in]  document Authoritative operation document payload.
    @return     Resolved filesystem path.
    """
    validate_translation_document(document)
    document_path = build_operation_output_path(
        project_root,
        "translation",
        config.TRANSLATED_CHUNKS_FILE_NAME,
    )
    write_json_atomic(document_path, document)
    return document_path


@trace_function(_AI_TRANSLATION_LOGGER)
def load_translated_chunks(project_root: str | Path) -> list[dict[str, object]]:
    """
    @brief      Return minimal translated chunk records from the authoritative document.
    @param[in]  project_root Active project root folder.
    @return     Loaded translated chunks.
    """
    document = load_translation_document(project_root)
    if document is None:
        return []
    return aligned_chunks(chunking_document_service.load_chunks(project_root), document)


@trace_function(_AI_TRANSLATION_LOGGER)
def load_translation_summary(project_root: str | Path) -> dict[str, object]:
    """
    @brief      Build the effective translation summary without mutating project data.
    @param[in]  project_root Active project root folder.
    @return     Loaded translation summary.
    """
    source_chunks = chunking_document_service.load_chunks(project_root)
    return build_translation_summary(source_chunks, load_translation_document(project_root))


def translation_is_completed(project_root: str | Path) -> bool:
    """
    @brief      Return whether the strict translation document is fully approved.
    @param[in]  project_root Active project root folder.
    @return     True when every persisted translation is approved; otherwise False.
    """
    root = Path(project_root)
    target = manifest_target_language(project_workspace_service.load_manifest(root))
    return (
        resolve_approved_translation(
            chunking_document_service.load_chunks(root), load_translation_document(root), target
        )
        is not None
    )


@trace_function(_AI_TRANSLATION_LOGGER)
def sync_translation_after_chunk_change(
    project_root: str | Path,
    target_language: str,
    invalidated_chunk_ids: list[str] | tuple[str, ...] | set[str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    """
    @brief      Synchronize an existing translation document after canonical chunk changes.
    @param[in]  project_root Active project root folder.
    @param[in]  target_language Requested translation target language.
    @param[in]  invalidated_chunk_ids Canonical chunk identifiers invalidated by the change.
    @return     Synchronized source chunks, translation chunks, and summary payload.
    @exception  ValueError Raised when canonical source chunks are unavailable.
    @exception  Exception Raised when the saved target language differs from the project.
    """
    resolved_project_root = Path(project_root)
    source_chunks = chunking_document_service.load_chunks(resolved_project_root)
    if not source_chunks:
        raise ValueError("Run text chunking before synchronizing AI translation.")
    document = load_translation_document(resolved_project_root)
    if document is None:
        return source_chunks, [], build_translation_summary(source_chunks, None)
    if str(document["target_language"]) != target_language:
        raise incompatible_document_error("The saved target language differs from the project.")
    synchronized = synchronize_document_chunks(document, source_chunks, invalidated_chunk_ids)
    if synchronized:
        document["status"] = review_status(document["chunks"])
        write_translation_document(resolved_project_root, document)
    return (
        source_chunks,
        [dict(item) for item in document["chunks"]],
        build_translation_summary(
            source_chunks,
            document,
        ),
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
    """
    @brief      Translate empty canonical chunks and checkpoint only complete chunks.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  target_language Requested translation target language.
    @param[in]  progress_callback Optional callback receiving operation progress updates.
    @param[in]  cancel_requested Optional callback used to query cancellation state.
    @param[in]  additional_translation_instructions Optional operator-supplied translation rules.
    @return     Durable translation summary after processing available chunks.
    @exception  ValueError Raised when canonical source chunks are unavailable.
    @exception  TranslationDocumentError Raised when persisted translation rules are incompatible.
    @exception  Exception Raised when an AI request failure is propagated to the caller.
    """
    resolved_project_root = Path(project_root)
    _validate_translation_inputs(ai_profile_payload, target_language)
    source_chunks = canonical_source_chunks(chunking_document_service.load_chunks(resolved_project_root))
    if not source_chunks:
        raise ValueError("Run text chunking with nonempty text before starting AI translation.")
    existing_document = load_translation_document(resolved_project_root)
    if existing_document is None:
        instructions = _normalized_additional_translation_instructions(additional_translation_instructions)
        document = new_translation_document(source_chunks, target_language, instructions)
    else:
        document = existing_document
        if resolve_approved_translation(source_chunks, document, target_language) is not None:
            return build_translation_summary(source_chunks, document)
        if str(document["target_language"]) != target_language:
            raise incompatible_document_error("The saved target language differs from the project.")
        synchronize_document_chunks(document, source_chunks, ())
        if str(document["status"]) in _RESUMABLE_STATUSES or additional_translation_instructions is None:
            instructions = str(document["additional_translation_instructions"])
        else:
            instructions = _normalized_additional_translation_instructions(additional_translation_instructions)
    prompt_template_service.validate_required_prompts(["text_translation_system", "text_translation_user"])
    system_prompt = prompt_template_service.render_prompt("text_translation_system", {})
    budget_metadata = _build_budget_metadata(
        ai_profile_payload,
        target_language,
        system_prompt,
        instructions,
    )
    previous_policy = document.get("request_fingerprint")
    policy = request_fingerprint(ai_profile_payload, system_prompt, target_language, instructions, budget_metadata)
    document["request_fingerprint"] = policy
    document["budget_metadata"] = budget_metadata
    document["additional_translation_instructions"] = instructions
    document["status"] = TRANSLATION_STATUS_RUNNING
    token_usage = token_usage_service.restore_token_usage(document["token_usage"])
    document["token_usage"] = token_usage
    write_translation_document(resolved_project_root, document)
    try:
        log_path = _resolve_log_path(resolved_project_root)
        translated_count = _translated_count(document["chunks"])
        message = "AI translation in progress..."
        if previous_policy is not None and previous_policy != policy:
            message = "AI translation request settings changed. Existing translations were retained."
        _emit_progress(progress_callback, translated_count, len(source_chunks), message, token_usage)
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
                translated_chunk_count=translated_count,
                cancel_requested=cancel_requested,
            )
            translated_chunk["translated_text"] = translated_text
            translated_chunk["approved"] = False
            translated_chunk["source_fingerprint"] = source_fingerprint(source_chunk)
            document["token_usage"] = token_usage
            write_translation_document(resolved_project_root, document)
            translated_count += 1
            _emit_progress(
                progress_callback,
                translated_count,
                len(document["chunks"]),
                "AI translation in progress...",
                token_usage,
            )
        document["status"] = review_status(document["chunks"])
        return publish_translation(
            resolved_project_root, document, source_chunks, check_cancelled=lambda: raise_if_cancelled(cancel_requested)
        )
    except Exception as error:
        if not isinstance(error, ProjectFileRecoveryError):
            document["status"] = (
                TRANSLATION_STATUS_CANCELLED
                if isinstance(error, OperationCancelledError)
                else TRANSLATION_STATUS_FAILED
            )
            _record_batch_interruption(resolved_project_root, document, source_chunks)
        raise


def _record_batch_interruption(root, document, source_chunks) -> None:
    """@brief Preserve finished chunk checkpoints and report any secondary save failure."""
    try:
        publish_translation(root, document, source_chunks)
    except ProjectFileRecoveryError:
        raise
    except ValueError:
        _AI_TRANSLATION_LOGGER.exception("Could not safely publish the interrupted translation")
    except OSError:
        _AI_TRANSLATION_LOGGER.exception("Could not publish the interrupted translation summary")
        try:
            write_translation_document(root, document)
        except (OSError, ValueError):
            _AI_TRANSLATION_LOGGER.exception("Could not write the interrupted translation checkpoint")


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
    """
    @brief      Re-translate one chunk without clearing its prior text or approval first.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  target_language Requested translation target language.
    @param[in]  chunk_id Stable canonical chunk identifier.
    @param[in]  progress_callback Optional callback receiving operation progress updates.
    @param[in]  cancel_requested Optional callback used to query cancellation state.
    @param[in]  additional_translation_instructions Optional operator-supplied translation rules.
    @return     Durable translation summary after replacing the selected chunk translation.
    @exception  ValueError Raised when translation has not started or the chunk ID is unknown.
    @exception  TranslationDocumentError Raised when persisted translation rules are incompatible.
    @exception  Exception Raised when an AI request failure is propagated to the caller.
    """
    resolved_project_root = Path(project_root)
    _validate_translation_inputs(ai_profile_payload, target_language)
    source_chunks = canonical_source_chunks(chunking_document_service.load_chunks(resolved_project_root))
    document = load_translation_document(resolved_project_root)
    if document is None:
        raise ValueError("Start AI translation before re-translating a chunk.")
    if str(document["target_language"]) != target_language:
        raise incompatible_document_error("The saved target language differs from the project.")
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
    except Exception:
        _record_retranslation_interruption(resolved_project_root, document, source_chunks, token_usage)
        raise
    candidate = {**document, "chunks": aligned_chunks(source_chunks, document)}
    selected = _find_document_chunk(candidate, chunk_id)
    selected["translated_text"] = translated_text
    selected["approved"] = False
    selected["source_fingerprint"] = source_fingerprint(selected_source)
    candidate["budget_metadata"] = budget_metadata
    candidate["token_usage"] = token_usage
    candidate["status"] = review_status(candidate["chunks"])
    try:
        return publish_translation(
            resolved_project_root,
            candidate,
            source_chunks,
            check_cancelled=lambda: raise_if_cancelled(cancel_requested),
        )
    except OperationCancelledError:
        _record_retranslation_interruption(resolved_project_root, document, source_chunks, token_usage)
        raise


def _record_retranslation_interruption(root, document, source_chunks, token_usage) -> None:
    """@brief Record accrued usage while keeping original text and approvals available."""
    next_status = review_status(document["chunks"])
    if next_status != TRANSLATION_STATUS_COMPLETED:
        document["status"] = next_status
    document["token_usage"] = token_usage
    try:
        publish_translation(root, document, source_chunks)
    except ProjectFileRecoveryError:
        raise
    except (OSError, ValueError):
        _AI_TRANSLATION_LOGGER.exception("Could not record usage from interrupted selected translation")


@trace_function(_AI_TRANSLATION_LOGGER)
def update_translated_text(
    project_root: str | Path,
    chunk_id: str,
    translated_text: str,
) -> dict[str, object]:
    """
    @brief      Persist one manual edit and invalidate approval when text changed.
    @param[in]  project_root Active project root folder.
    @param[in]  chunk_id Stable canonical chunk identifier.
    @param[in]  translated_text Translated text associated with one canonical chunk.
    @return     Durable translation summary after the manual text edit.
    """
    document, source_chunks = _editable_translation_document(project_root)
    selected = _find_document_chunk(document, chunk_id)
    if str(selected["translated_text"]) != translated_text:
        selected["translated_text"] = translated_text
        selected["approved"] = False
        selected["source_fingerprint"] = _current_fingerprint(source_chunks, chunk_id)
    document["status"] = review_status(document["chunks"])
    return publish_translation(project_root, document, source_chunks)


@trace_function(_AI_TRANSLATION_LOGGER)
def approve_chunk(project_root: str | Path, chunk_id: str) -> dict[str, object]:
    """
    @brief      Approve one non-empty translated chunk in one atomic write.
    @param[in]  project_root Active project root folder.
    @param[in]  chunk_id Stable canonical chunk identifier.
    @return     Durable translation summary after approving the selected chunk.
    @exception  ValueError Raised when translate the selected chunk before approving it.
    """
    document, source_chunks = _editable_translation_document(project_root)
    selected = _find_document_chunk(document, chunk_id)
    if not str(selected["translated_text"]).strip():
        raise ValueError("Translate the selected chunk before approving it.")
    selected["source_fingerprint"] = _current_fingerprint(source_chunks, chunk_id)
    selected["approved"] = True
    document["status"] = review_status(document["chunks"])
    return publish_translation(project_root, document, source_chunks)


@trace_function(_AI_TRANSLATION_LOGGER)
def approve_all(project_root: str | Path) -> dict[str, object]:
    """
    @brief      Approve every non-empty translated chunk in one atomic write.
    @param[in]  project_root Active project root folder.
    @return     Durable translation summary after approving all translated chunks.
    """
    document, source_chunks = _editable_translation_document(project_root)
    for source, chunk in zip(source_chunks, document["chunks"], strict=True):
        if str(chunk["translated_text"]).strip():
            chunk["source_fingerprint"] = source_fingerprint(source)
            chunk["approved"] = True
    document["status"] = review_status(document["chunks"])
    return publish_translation(project_root, document, source_chunks)


@trace_function(_AI_TRANSLATION_LOGGER)
def reset_translation(project_root: str | Path) -> None:
    """@brief Recoverably reset Translation and invalidate dependents when their source changes."""
    publish_translation(project_root, None, chunking_document_service.load_chunks(project_root))


# LOCAL HELPERS


def _editable_translation_document(project_root: str | Path) -> tuple[TranslationDocumentPayload, list[dict]]:
    """
    @brief      Load the document or reject review actions before translation exists.
    @param[in]  project_root Active project root folder.
    @return     Validated authoritative translation document.
    @exception  ValueError Raised when start AI translation before reviewing translated chunks.
    """
    document = load_translation_document(project_root)
    if document is None:
        raise ValueError("Start AI translation before reviewing translated chunks.")
    if document["target_language"] != manifest_target_language(project_workspace_service.load_manifest(project_root)):
        raise incompatible_document_error("The saved target language differs from the project.")
    source_chunks = canonical_source_chunks(chunking_document_service.load_chunks(project_root))
    synchronize_document_chunks(document, source_chunks, ())
    return document, source_chunks


def _current_fingerprint(source_chunks, chunk_id: str) -> str:
    """@brief Bind an explicit edit or approval to the currently displayed source."""
    return source_fingerprint(next(source for source in source_chunks if source["chunk_id"] == chunk_id))


def _find_document_chunk(document: TranslationDocumentPayload, chunk_id: str) -> dict[str, object]:
    """
    @brief      Return one mutable chunk record by identifier.
    @param[in]  document Authoritative operation document payload.
    @param[in]  chunk_id Stable canonical chunk identifier.
    @return     Matching document chunk.
    @exception  ValueError Raised when the requested translation chunk is unknown.
    """
    for item in document["chunks"]:
        if str(item["chunk_id"]) == chunk_id:
            return item
    raise ValueError(f"Unknown translation chunk: {chunk_id}")


def _validate_translation_inputs(ai_profile_payload: dict[str, object], target_language: str) -> None:
    """
    @brief      Validate current profile and target language before an AI request.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  target_language Requested translation target language.
    @return     None.
    @exception  ValueError Raised when aI translation requires a valid target language.
    """
    required_profile_fields = ("id", "model_name", "base_url")
    if any(not str(ai_profile_payload.get(field, "")).strip() for field in required_profile_fields):
        raise ValueError("AI translation requires a valid enabled AI profile.")
    if target_language not in _TRANSLATION_LANGUAGE_LABELS:
        raise ValueError("AI translation requires a valid target language.")


def _translated_count(chunks: object) -> int:
    """Count non-empty translated chunks."""
    return sum(bool(str(item["translated_text"]).strip()) for item in list(chunks))


def _resolve_log_path(project_root: Path) -> Path:
    """
    @brief      Create an operation-local AI transaction log without persisting its path.
    @param[in]  project_root Active project root folder.
    @return     Resolved filesystem path.
    """
    timestamp_token = _utc_now_iso().replace("-", "").replace(":", "").replace("+", "_").replace(".", "")
    log_path = build_operation_output_path(
        project_root,
        "translation",
        config.ai_transaction_log_file_name("translation", timestamp_token),
    )
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")
    return log_path


# END OF FILE
