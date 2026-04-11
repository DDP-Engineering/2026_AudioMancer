#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_translation_service.py
@brief AI-assisted translation helpers for AudioMancer.
@details Persists translated chunk review records in `30_translation` and
         executes resumable translation over canonical chunking output.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.3.0
"""

# IMPORTS

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from audiomancer import config
from audiomancer.services import deterministic_chunking_service
from audiomancer.services import llm_provider_service
from audiomancer.services import prompt_template_service
from audiomancer.services import project_workspace_service
from audiomancer.services import token_usage_service
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    build_operation_artifact_path,
    build_operation_input_snapshot_path,
    build_operation_output_path,
    progress_percent,
    raise_if_cancelled,
    relative_to_project,
)


# CONSTANTS


# @brief Component logger used by the AI translation workflow service.
_AI_TRANSLATION_LOGGER = get_component_logger("ai_translation")

# @brief Translation stage token used before any chunk was translated.
TRANSLATION_STAGE_NOT_STARTED = "not_started"
# @brief Translation stage token used while translation work remains incomplete.
TRANSLATION_STAGE_IN_PROGRESS = "in_progress"
# @brief Translation stage token used when all chunks were translated.
TRANSLATION_STAGE_COMPLETED = "completed"
# @brief Translated-chunk status token used before a chunk receives translated text.
TRANSLATED_CHUNK_STATUS_NOT_STARTED = "not_started"
# @brief Translated-chunk status token used after a chunk receives translated text.
TRANSLATED_CHUNK_STATUS_TRANSLATED = "translated"
# @brief Translated-chunk status token used after a translated chunk is approved.
TRANSLATED_CHUNK_STATUS_APPROVED = "approved"
# @brief Mapping from translation language codes to display labels.
_TRANSLATION_LANGUAGE_LABELS = dict(config.TRANSLATION_LANGUAGE_OPTIONS)
TokenUsagePayload = dict[str, object]


# PUBLIC API


@trace_function(_AI_TRANSLATION_LOGGER)
def load_operation_state(project_root: str | Path) -> dict[str, object] | None:
    """
    @brief      Load the persisted translation operation state from disk.
    @param[in]  project_root Active project root path.
    @return     Translation operation state payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.1
    """
    state_path = build_operation_output_path(
        project_root,
        "translation",
        config.OPERATION_STATE_FILE_NAME,
    )
    if not state_path.is_file():
        return None
    return dict(json.loads(state_path.read_text(encoding="utf-8")))


@trace_function(_AI_TRANSLATION_LOGGER)
def load_translation_report(project_root: str | Path) -> dict[str, object] | None:
    """
    @brief      Load the persisted translation report from disk.
    @param[in]  project_root Active project root path.
    @return     Translation report payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    report_path = build_operation_artifact_path(
        project_root,
        "translation",
        config.TRANSLATION_REPORT_FILE_NAME,
    )
    if not report_path.is_file():
        return None
    return dict(json.loads(report_path.read_text(encoding="utf-8")))


@trace_function(_AI_TRANSLATION_LOGGER)
def load_translated_chunks(project_root: str | Path) -> list[dict[str, object]]:
    """
    @brief      Load persisted translated chunk records from disk.
    @param[in]  project_root Active project root path.
    @return     Persisted translated chunk payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    translated_path = build_operation_output_path(
        project_root,
        "translation",
        config.TRANSLATED_CHUNKS_FILE_NAME,
    )
    if not translated_path.is_file():
        return []
    payload = json.loads(translated_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


@trace_function(_AI_TRANSLATION_LOGGER)
def ensure_translation_records(
    project_root: str | Path,
    target_language: str,
    profile_id: str | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    """
    @brief      Synchronize translated records against the current source chunks.
    @param[in]  project_root Active project root path.
    @param[in]  target_language Active target language code.
    @param[in]  profile_id Active translation profile identifier or `None`.
    @return     Source chunks, translated chunk records, and translation report.
    @exception  ValueError When chunking output is missing.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    project_root = Path(project_root)
    source_chunks = deterministic_chunking_service.load_chunks(project_root)
    if not source_chunks:
        raise ValueError("Run text chunking before starting AI translation.")
    existing_by_id = {
        str(chunk.get("chunk_id", "")): dict(chunk)
        for chunk in load_translated_chunks(project_root)
        if str(chunk.get("chunk_id", "")).strip()
    }
    translated_chunks: list[dict[str, object]] = []
    synchronized = False
    for source_chunk in sorted(source_chunks, key=lambda item: int(item.get("sequence_index", 0))):
        chunk_id = str(source_chunk.get("chunk_id", "")).strip()
        existing_chunk = existing_by_id.get(chunk_id)
        if existing_chunk is None:
            translated_chunks.append(_build_default_translated_chunk(source_chunk, target_language, profile_id))
            synchronized = True
            continue
        existing_chunk["sequence_index"] = int(source_chunk.get("sequence_index", 0))
        existing_chunk["source_text"] = str(source_chunk.get("text", ""))
        existing_chunk["target_language"] = target_language
        if profile_id not in (None, ""):
            existing_chunk["translation_profile_id"] = profile_id
        translated_chunks.append(_normalize_translated_chunk(existing_chunk, target_language))
    if len(existing_by_id) != len(translated_chunks):
        synchronized = True
    existing_operation_state = load_operation_state(project_root)
    existing_report = load_translation_report(project_root)
    report = _rebuild_report(
        translated_chunks,
        target_language,
        profile_id,
        warnings=(
            ["Source chunk set changed since translation started. Translation records were synchronized."]
            if synchronized else []
        ),
        token_usage=_restore_persisted_token_usage(existing_report, existing_operation_state),
    )
    _persist_translation_state(
        project_root,
        source_chunks,
        translated_chunks,
        report,
        operation_state=existing_operation_state,
    )
    return source_chunks, translated_chunks, report


@trace_function(_AI_TRANSLATION_LOGGER)
def start_or_continue_translation(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    target_language: str,
    progress_callback=None,
    cancel_requested=None,
) -> dict[str, object]:
    """
    @brief      Translate all remaining untranslated chunks for the active project.
    @param[in]  project_root Active project root path.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Enabled AI profile payload.
    @param[in]  target_language Requested target language code.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Final translation report payload.
    @exception  ValueError When inputs are invalid or the model returns empty text.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    project_root = Path(project_root)
    profile_id = str(ai_profile_payload.get("id", "")).strip()
    model_name = str(ai_profile_payload.get("model_name", "")).strip()
    base_url = str(ai_profile_payload.get("base_url", "")).strip()
    if not profile_id or not model_name or not base_url:
        raise ValueError("AI translation requires a valid enabled AI profile.")
    if target_language not in _TRANSLATION_LANGUAGE_LABELS:
        raise ValueError("AI translation requires a valid target language.")
    source_chunks, translated_chunks, report = ensure_translation_records(
        project_root,
        target_language,
        profile_id,
    )
    prompt_template_service.validate_required_prompts(
        ["text_translation_system", "text_translation_user"]
    )
    started_at = str((load_operation_state(project_root) or {}).get("started_at") or _utc_now_iso())
    log_path = _resolve_log_path(project_root, started_at)
    token_usage = _restore_persisted_token_usage(report, load_operation_state(project_root))
    system_prompt = prompt_template_service.render_prompt(
        "text_translation_system",
        {"target_language": _language_label(target_language)},
    )
    _write_running_state(
        project_root,
        source_chunks,
        translated_chunks,
        started_at,
        target_language,
        profile_id,
        log_path,
        token_usage,
    )
    _emit_progress(
        progress_callback,
        _translated_count(translated_chunks),
        len(translated_chunks),
        "AI translation in progress...",
        token_usage,
    )
    for chunk in translated_chunks:
        raise_if_cancelled(cancel_requested)
        if str(chunk.get("translated_text", "")).strip():
            continue
        translated_text, token_usage = _translate_text_in_budgeted_segments(
            project_root,
            manifest,
            ai_profile_payload,
            str(chunk.get("source_text", "")),
            target_language,
            system_prompt,
            int(chunk.get("sequence_index", 0)),
            len(translated_chunks),
            log_path,
            token_usage,
            progress_callback=progress_callback,
            translated_chunk_count=_translated_count(translated_chunks),
            cancel_requested=cancel_requested,
        )
        if not translated_text.strip():
            raise ValueError(
                f"AI translation returned an empty translated_text for {chunk.get('chunk_id', '')}."
            )
        chunk["translated_text"] = translated_text
        chunk["approved"] = False
        chunk["approved_at"] = None
        chunk["translated_at"] = _utc_now_iso()
        chunk["translation_profile_id"] = profile_id
        chunk["target_language"] = target_language
        chunk["status"] = TRANSLATED_CHUNK_STATUS_TRANSLATED
        report = _rebuild_report(
            translated_chunks,
            target_language,
            profile_id,
            warnings=list(report.get("warnings", [])),
            token_usage=token_usage,
        )
        _write_running_state(
            project_root,
            source_chunks,
            translated_chunks,
            started_at,
            target_language,
            profile_id,
            log_path,
            token_usage,
        )
        _persist_translation_state(project_root, source_chunks, translated_chunks, report, operation_state=load_operation_state(project_root))
        _emit_progress(
            progress_callback,
            _translated_count(translated_chunks),
            len(translated_chunks),
            "AI translation in progress...",
            token_usage,
        )
    completed_at = _utc_now_iso()
    report = _rebuild_report(
        translated_chunks,
        target_language,
        profile_id,
        warnings=list(report.get("warnings", [])),
        updated_at=completed_at,
        token_usage=token_usage,
    )
    operation_state = _build_operation_state(
        project_root,
        source_chunks,
        translated_chunks,
        report,
        status="completed",
        started_at=started_at,
        completed_at=completed_at,
        profile_id=profile_id,
        target_language=target_language,
        log_path=log_path,
        resume_checkpoint=None,
        token_usage=token_usage,
    )
    _persist_translation_state(project_root, source_chunks, translated_chunks, report, operation_state=operation_state)
    _emit_progress(
        progress_callback,
        len(translated_chunks),
        len(translated_chunks),
        "AI translation completed.",
        token_usage,
    )
    return report


@trace_function(_AI_TRANSLATION_LOGGER)
def retranslate_chunk(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    target_language: str,
    chunk_id: str,
    progress_callback=None,
    cancel_requested=None,
) -> dict[str, object]:
    """
    @brief      Re-translate one selected chunk and persist the new result.
    @param[in]  project_root Active project root path.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Enabled AI profile payload.
    @param[in]  target_language Requested target language code.
    @param[in]  chunk_id Selected chunk identifier.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Updated translation report payload.
    @exception  ValueError When the selected chunk is unknown or translation is empty.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    project_root = Path(project_root)
    profile_id = str(ai_profile_payload.get("id", "")).strip()
    source_chunks, translated_chunks, report = ensure_translation_records(project_root, target_language, profile_id)
    selected = next((item for item in translated_chunks if str(item.get("chunk_id", "")) == str(chunk_id)), None)
    if selected is None:
        raise ValueError(f"Unknown translation chunk id: {chunk_id}")
    prompt_template_service.validate_required_prompts(
        ["text_translation_system", "text_translation_user"]
    )
    started_at = str((load_operation_state(project_root) or {}).get("started_at") or _utc_now_iso())
    log_path = _resolve_log_path(project_root, started_at)
    token_usage = _restore_persisted_token_usage(report, load_operation_state(project_root))
    system_prompt = prompt_template_service.render_prompt(
        "text_translation_system",
        {"target_language": _language_label(target_language)},
    )
    selected["translated_text"] = ""
    selected["approved"] = False
    selected["approved_at"] = None
    selected["translated_at"] = None
    selected["translation_profile_id"] = profile_id
    selected["target_language"] = target_language
    selected["status"] = TRANSLATED_CHUNK_STATUS_NOT_STARTED
    _write_running_state(
        project_root,
        source_chunks,
        translated_chunks,
        started_at,
        target_language,
        profile_id,
        log_path,
        token_usage,
    )
    translated_text, token_usage = _translate_text_in_budgeted_segments(
        project_root,
        manifest,
        ai_profile_payload,
        str(selected.get("source_text", "")),
        target_language,
        system_prompt,
        int(selected.get("sequence_index", 0)),
        len(translated_chunks),
        log_path,
        token_usage,
        progress_callback=progress_callback,
        translated_chunk_count=max(0, _translated_count(translated_chunks)),
        cancel_requested=cancel_requested,
    )
    if not translated_text.strip():
        raise ValueError(
            f"AI translation returned an empty translated_text for {selected.get('chunk_id', '')}."
        )
    selected["translated_text"] = translated_text
    selected["approved"] = False
    selected["approved_at"] = None
    selected["translated_at"] = _utc_now_iso()
    selected["translation_profile_id"] = profile_id
    selected["target_language"] = target_language
    selected["status"] = TRANSLATED_CHUNK_STATUS_TRANSLATED
    report = _rebuild_report(
        translated_chunks,
        target_language,
        profile_id,
        warnings=list(report.get("warnings", [])),
        token_usage=token_usage,
    )
    operation_state = _build_operation_state(
        project_root,
        source_chunks,
        translated_chunks,
        report,
        status=str(report["translation_stage_status"]),
        started_at=started_at,
        completed_at=_utc_now_iso(),
        profile_id=profile_id,
        target_language=target_language,
        log_path=log_path,
        resume_checkpoint=None,
        token_usage=token_usage,
    )
    _persist_translation_state(project_root, source_chunks, translated_chunks, report, operation_state=operation_state)
    _emit_progress(
        progress_callback,
        1,
        1,
        "Selected chunk re-translation completed.",
        token_usage,
    )
    return report


@trace_function(_AI_TRANSLATION_LOGGER)
def update_translated_text(
    project_root: str | Path,
    chunk_id: str,
    translated_text: str,
    target_language: str,
    profile_id: str | None,
) -> dict[str, object]:
    """
    @brief      Persist one manual edit to the translated text of a chunk.
    @param[in]  project_root Active project root path.
    @param[in]  chunk_id Selected chunk identifier.
    @param[in]  translated_text Edited translated text.
    @param[in]  target_language Active target language code.
    @param[in]  profile_id Active translation profile identifier or `None`.
    @return     Updated translation report payload.
    @exception  ValueError When the selected chunk is unknown.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    project_root = Path(project_root)
    source_chunks, translated_chunks, report = ensure_translation_records(project_root, target_language, profile_id)
    selected = next((item for item in translated_chunks if str(item.get("chunk_id", "")) == str(chunk_id)), None)
    if selected is None:
        raise ValueError(f"Unknown translation chunk id: {chunk_id}")
    previous_text = str(selected.get("translated_text", ""))
    selected["translated_text"] = translated_text
    selected["translation_profile_id"] = profile_id
    selected["target_language"] = target_language
    if translated_text.strip():
        if translated_text != previous_text:
            selected["approved"] = False
            selected["approved_at"] = None
        selected["translated_at"] = selected.get("translated_at") or _utc_now_iso()
        selected["status"] = TRANSLATED_CHUNK_STATUS_APPROVED if bool(selected.get("approved", False)) else TRANSLATED_CHUNK_STATUS_TRANSLATED
    else:
        selected["approved"] = False
        selected["approved_at"] = None
        selected["translated_at"] = None
        selected["status"] = TRANSLATED_CHUNK_STATUS_NOT_STARTED
    report = _rebuild_report(
        translated_chunks,
        target_language,
        profile_id,
        warnings=list(report.get("warnings", [])),
        token_usage=_restore_persisted_token_usage(
            report,
            load_operation_state(project_root),
        ),
    )
    _persist_translation_state(project_root, source_chunks, translated_chunks, report, operation_state=load_operation_state(project_root))
    return report


@trace_function(_AI_TRANSLATION_LOGGER)
def approve_chunk(
    project_root: str | Path,
    chunk_id: str,
    target_language: str,
    profile_id: str | None,
) -> dict[str, object]:
    """
    @brief      Approve one translated chunk for manual review completion.
    @param[in]  project_root Active project root path.
    @param[in]  chunk_id Selected chunk identifier.
    @param[in]  target_language Active target language code.
    @param[in]  profile_id Active translation profile identifier or `None`.
    @return     Updated translation report payload.
    @exception  ValueError When the chunk is unknown or still untranslated.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    project_root = Path(project_root)
    source_chunks, translated_chunks, report = ensure_translation_records(project_root, target_language, profile_id)
    selected = next((item for item in translated_chunks if str(item.get("chunk_id", "")) == str(chunk_id)), None)
    if selected is None:
        raise ValueError(f"Unknown translation chunk id: {chunk_id}")
    if not str(selected.get("translated_text", "")).strip():
        raise ValueError("Translate the selected chunk before approving it.")
    selected["approved"] = True
    selected["approved_at"] = _utc_now_iso()
    selected["status"] = TRANSLATED_CHUNK_STATUS_APPROVED
    report = _rebuild_report(
        translated_chunks,
        target_language,
        profile_id,
        warnings=list(report.get("warnings", [])),
        token_usage=_restore_persisted_token_usage(
            report,
            load_operation_state(project_root),
        ),
    )
    _persist_translation_state(project_root, source_chunks, translated_chunks, report, operation_state=load_operation_state(project_root))
    return report


@trace_function(_AI_TRANSLATION_LOGGER)
def approve_all(
    project_root: str | Path,
    target_language: str,
    profile_id: str | None,
) -> dict[str, object]:
    """
    @brief      Approve every translated chunk that still needs review approval.
    @param[in]  project_root Active project root path.
    @param[in]  target_language Active target language code.
    @param[in]  profile_id Active translation profile identifier or `None`.
    @return     Updated translation report payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    project_root = Path(project_root)
    source_chunks, translated_chunks, report = ensure_translation_records(project_root, target_language, profile_id)
    approved_at = _utc_now_iso()
    for chunk in translated_chunks:
        if not str(chunk.get("translated_text", "")).strip():
            continue
        chunk["approved"] = True
        chunk["approved_at"] = approved_at
        chunk["status"] = TRANSLATED_CHUNK_STATUS_APPROVED
    report = _rebuild_report(
        translated_chunks,
        target_language,
        profile_id,
        warnings=list(report.get("warnings", [])),
        token_usage=_restore_persisted_token_usage(
            report,
            load_operation_state(project_root),
        ),
    )
    _persist_translation_state(project_root, source_chunks, translated_chunks, report, operation_state=load_operation_state(project_root))
    return report


@trace_function(_AI_TRANSLATION_LOGGER)
def reset_translation(project_root: str | Path) -> None:
    """
    @brief      Remove all persisted translation artifacts for the project.
    @param[in]  project_root Active project root path.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    translation_root = Path(project_root) / config.TRANSLATION_FOLDER_NAME
    translation_root.mkdir(parents=True, exist_ok=True)
    for child in list(translation_root.iterdir()):
        if child.is_file():
            child.unlink()


# HELPER FUNCTIONS


def _build_default_translated_chunk(source_chunk: dict[str, object], target_language: str, profile_id: str | None) -> dict[str, object]:
    """
    @brief      Build the default untranslated record for one source chunk.
    @param[in]  source_chunk Source chunk payload.
    @param[in]  target_language Active target language code.
    @param[in]  profile_id Active translation profile identifier or `None`.
    @return     Default translated-chunk payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    return {
        "chunk_id": str(source_chunk.get("chunk_id", "")),
        "sequence_index": int(source_chunk.get("sequence_index", 0)),
        "source_text": str(source_chunk.get("text", "")),
        "translated_text": "",
        "approved": False,
        "translated_at": None,
        "approved_at": None,
        "translation_profile_id": profile_id,
        "target_language": target_language,
        "status": TRANSLATED_CHUNK_STATUS_NOT_STARTED,
    }


def _normalize_translated_chunk(payload: dict[str, object], target_language: str) -> dict[str, object]:
    """
    @brief      Normalize one persisted translated-chunk payload.
    @param[in]  payload Raw translated-chunk payload.
    @param[in]  target_language Active target language fallback code.
    @return     Normalized translated-chunk payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    return {
        "chunk_id": str(payload.get("chunk_id", "")),
        "sequence_index": int(payload.get("sequence_index", 0)),
        "source_text": str(payload.get("source_text", "")),
        "translated_text": str(payload.get("translated_text", "")),
        "approved": bool(payload.get("approved", False)),
        "translated_at": None if payload.get("translated_at") in (None, "") else str(payload.get("translated_at")),
        "approved_at": None if payload.get("approved_at") in (None, "") else str(payload.get("approved_at")),
        "translation_profile_id": None if payload.get("translation_profile_id") in (None, "") else str(payload.get("translation_profile_id")),
        "target_language": str(payload.get("target_language", target_language) or target_language),
        "status": str(payload.get("status", TRANSLATED_CHUNK_STATUS_NOT_STARTED)),
    }


def _rebuild_report(
    translated_chunks: list[dict[str, object]],
    target_language: str,
    profile_id: str | None,
    warnings: list[str] | None = None,
    updated_at: str | None = None,
    token_usage: TokenUsagePayload | None = None,
) -> dict[str, object]:
    """
    @brief      Recompute the translation report from the current chunk records.
    @param[in]  translated_chunks Current translated chunk payloads.
    @param[in]  target_language Active target language code.
    @param[in]  profile_id Active translation profile identifier or `None`.
    @param[in]  warnings Optional warning list to persist in the report.
    @param[in]  updated_at Optional report timestamp override.
    @return     Rebuilt translation report payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    translated_count = _translated_count(translated_chunks)
    approved_count = sum(1 for chunk in translated_chunks if bool(chunk.get("approved", False)))
    if translated_count <= 0:
        stage_status = TRANSLATION_STAGE_NOT_STARTED
    elif translated_count >= len(translated_chunks):
        stage_status = TRANSLATION_STAGE_COMPLETED
    else:
        stage_status = TRANSLATION_STAGE_IN_PROGRESS
    return {
        "target_language": target_language,
        "translation_profile_id_last_used": profile_id,
        "translation_stage_status": stage_status,
        "translated_chunk_count": translated_count,
        "approved_chunk_count": approved_count,
        "total_chunk_count": len(translated_chunks),
        "updated_at": updated_at or _utc_now_iso(),
        "warnings": list(warnings or []),
        "token_usage": token_usage_service.coerce_token_usage(token_usage),
    }


def _translated_count(translated_chunks: list[dict[str, object]]) -> int:
    """
    @brief      Count translated chunks with non-empty translated text.
    @param[in]  translated_chunks Current translated chunk payloads.
    @return     Number of translated chunks.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    return sum(1 for chunk in translated_chunks if str(chunk.get("translated_text", "")).strip())


def _persist_translation_state(
    project_root: Path,
    source_chunks: list[dict[str, object]],
    translated_chunks: list[dict[str, object]],
    report: dict[str, object],
    operation_state: dict[str, object] | None,
) -> None:
    """
    @brief      Persist the translation input snapshot, outputs, report, and state.
    @param[in]  project_root Active project root path.
    @param[in]  source_chunks Source chunk payloads.
    @param[in]  translated_chunks Persisted translated chunk payloads.
    @param[in]  report Current translation report payload.
    @param[in]  operation_state Current operation state payload or `None`.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    input_path = _translation_input_snapshot_path(project_root)
    input_path.write_text(
        json.dumps(source_chunks, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    translated_path = build_operation_output_path(
        project_root,
        "translation",
        config.TRANSLATED_CHUNKS_FILE_NAME,
    )
    translated_path.write_text(
        json.dumps(translated_chunks, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_path = build_operation_artifact_path(
        project_root,
        "translation",
        config.TRANSLATION_REPORT_FILE_NAME,
    )
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if operation_state is not None:
        state_path = build_operation_output_path(
            project_root,
            "translation",
            config.OPERATION_STATE_FILE_NAME,
        )
        state_path.write_text(
            json.dumps(operation_state, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def _write_running_state(
    project_root: Path,
    source_chunks: list[dict[str, object]],
    translated_chunks: list[dict[str, object]],
    started_at: str,
    target_language: str,
    profile_id: str,
    log_path: Path,
    token_usage: TokenUsagePayload,
) -> None:
    """
    @brief      Persist the translation operation in the running state.
    @param[in]  project_root Active project root path.
    @param[in]  source_chunks Source chunk payloads.
    @param[in]  translated_chunks Current translated chunk payloads.
    @param[in]  started_at Operation start timestamp.
    @param[in]  target_language Active target language code.
    @param[in]  profile_id Active translation profile identifier.
    @param[in]  log_path Operation-local AI transaction log path.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    report = _rebuild_report(
        translated_chunks,
        target_language,
        profile_id,
        token_usage=token_usage,
    )
    operation_state = _build_operation_state(
        project_root,
        source_chunks,
        translated_chunks,
        report,
        status="running",
        started_at=started_at,
        completed_at=None,
        profile_id=profile_id,
        target_language=target_language,
        log_path=log_path,
        token_usage=token_usage,
        resume_checkpoint={
            "next_untranslated_chunk_id": _next_untranslated_chunk_id(translated_chunks),
            "translated_chunk_count": report["translated_chunk_count"],
            "total_chunk_count": report["total_chunk_count"],
        },
    )
    _persist_translation_state(
        project_root,
        source_chunks,
        translated_chunks,
        report,
        operation_state,
    )


def _build_operation_state(
    project_root: Path,
    source_chunks: list[dict[str, object]],
    translated_chunks: list[dict[str, object]],
    report: dict[str, object],
    status: str,
    started_at: str,
    completed_at: str | None,
    profile_id: str | None,
    target_language: str,
    log_path: Path,
    token_usage: TokenUsagePayload,
    resume_checkpoint: dict[str, object] | None,
) -> dict[str, object]:
    """
    @brief      Build the persisted translation operation state payload.
    @param[in]  project_root Active project root path.
    @param[in]  source_chunks Source chunk payloads.
    @param[in]  translated_chunks Current translated chunk payloads.
    @param[in]  report Current translation report payload.
    @param[in]  status Persisted operation status token.
    @param[in]  started_at Operation start timestamp.
    @param[in]  completed_at Operation completion timestamp or `None`.
    @param[in]  profile_id Active translation profile identifier or `None`.
    @param[in]  target_language Active target language code.
    @param[in]  log_path Operation-local AI transaction log path.
    @param[in]  resume_checkpoint Resume checkpoint payload or `None`.
    @return     Persisted operation state payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    input_path = _translation_input_snapshot_path(project_root)
    output_path = build_operation_output_path(
        project_root,
        "translation",
        config.TRANSLATED_CHUNKS_FILE_NAME,
    )
    report_path = build_operation_artifact_path(
        project_root,
        "translation",
        config.TRANSLATION_REPORT_FILE_NAME,
    )
    return {
        "folder_relative_path": config.TRANSLATION_FOLDER_NAME,
        "status": status,
        "input_paths": [relative_to_project(project_root, input_path)],
        "output_paths": [relative_to_project(project_root, output_path)],
        "artifact_paths": [
            relative_to_project(project_root, report_path),
            relative_to_project(project_root, log_path),
        ],
        "progress_current": report["translated_chunk_count"],
        "progress_total": report["total_chunk_count"],
        "mode": "ai_assisted",
        "started_at": started_at,
        "completed_at": completed_at,
        "updated_at": report["updated_at"],
        "warning_count": len(list(report.get("warnings", []))),
        "metadata": {
            "target_language": target_language,
            "translation_profile_id": profile_id,
            "translated_chunk_count": report["translated_chunk_count"],
            "approved_chunk_count": report["approved_chunk_count"],
            "total_chunk_count": report["total_chunk_count"],
            "warnings": list(report.get("warnings", [])),
            "translated_chunks": translated_chunks,
            "source_chunk_count": len(source_chunks),
            "log_relative_path": relative_to_project(project_root, log_path),
            "token_usage": token_usage_service.coerce_token_usage(token_usage),
        },
        "resume_checkpoint": None if resume_checkpoint is None else dict(resume_checkpoint),
    }


def _next_untranslated_chunk_id(translated_chunks: list[dict[str, object]]) -> str | None:
    """
    @brief      Return the next untranslated chunk id for resume state.
    @param[in]  translated_chunks Current translated chunk payloads.
    @return     Next untranslated chunk id or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    for chunk in translated_chunks:
        if not str(chunk.get("translated_text", "")).strip():
            return str(chunk.get("chunk_id", ""))
    return None


def _resolve_log_path(project_root: Path, started_at: str) -> Path:
    """
    @brief      Resolve or create the AI transaction log path for translation.
    @param[in]  project_root Active project root path.
    @param[in]  started_at Operation start timestamp.
    @return     Operation-local AI transaction log path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    existing_state = load_operation_state(project_root) or {}
    for artifact_path in list(existing_state.get("artifact_paths", [])):
        relative_path = str(artifact_path)
        if Path(relative_path).name.startswith(config.AI_TRANSACTION_LOG_FILE_PREFIX):
            resolved_path = project_root / relative_path
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            if not resolved_path.exists():
                resolved_path.write_text("", encoding="utf-8")
            return resolved_path
    timestamp_token = (
        started_at.replace("-", "")
        .replace(":", "")
        .replace("+", "_")
        .replace(".", "")
    )
    log_path = build_operation_output_path(
        project_root,
        "translation",
        f"{config.AI_TRANSACTION_LOG_FILE_PREFIX}{timestamp_token}.log",
    )
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")
    return log_path


def _translation_input_snapshot_path(project_root: Path) -> Path:
    existing_state = load_operation_state(project_root) or {}
    input_paths = existing_state.get("input_paths", [])
    if isinstance(input_paths, list):
        for relative_path in input_paths:
            if not isinstance(relative_path, str):
                continue
            resolved_path = project_root / relative_path
            if (
                resolved_path.is_file()
                and resolved_path.suffix.casefold() == ".json"
                and resolved_path.name.startswith(config.OPERATION_INPUT_FILE_PREFIX)
            ):
                return resolved_path
    return build_operation_input_snapshot_path(
        project_root,
        "translation",
        f"{_translation_source_snapshot_base_name(project_root)}.json",
    )


def _translation_source_snapshot_base_name(project_root: Path) -> str:
    try:
        manifest = project_workspace_service.load_manifest(project_root)
    except Exception:
        manifest = None
    if isinstance(manifest, dict):
        source_document = manifest.get("source_document", {})
        if isinstance(source_document, dict):
            original_name = str(source_document.get("original_name", "")).strip()
            if original_name:
                return Path(original_name).stem
    return Path(config.CHUNK_ARTIFACT_FILE_NAME).stem


def _restore_persisted_token_usage(
    report: dict[str, object] | None,
    operation_state: dict[str, object] | None,
) -> TokenUsagePayload:
    metadata = {}
    if isinstance(operation_state, dict):
        metadata = operation_state.get("metadata", {})
    return token_usage_service.restore_token_usage(
        None if not isinstance(report, dict) else report.get("token_usage"),
        metadata.get("token_usage") if isinstance(metadata, dict) else None,
    )


def _translate_text_in_budgeted_segments(
    project_root: Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    source_text: str,
    target_language: str,
    system_prompt: str,
    chunk_sequence_index: int,
    total_chunks: int,
    log_path: Path,
    token_usage: TokenUsagePayload,
    progress_callback=None,
    translated_chunk_count: int = 0,
    cancel_requested=None,
) -> tuple[str, TokenUsagePayload]:
    """
    @brief      Translate one source chunk in budgeted AI request segments.
    @param[in]  project_root Active project root path.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Enabled AI profile payload.
    @param[in]  source_text Source text to translate.
    @param[in]  target_language Requested target language code.
    @param[in]  system_prompt Rendered translation system prompt.
    @param[in]  chunk_sequence_index Sequence index of the translated chunk.
    @param[in]  total_chunks Total number of source chunks.
    @param[in]  log_path Operation-local AI transaction log path.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Concatenated translated text plus updated cumulative token usage.
    @exception  ValueError When any translated segment is empty.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    usable_input_budget = _usable_input_budget(ai_profile_payload)
    translated_segments: list[str] = []
    for segment_index, source_segment in enumerate(
        _split_translation_source_text(source_text, usable_input_budget),
        start=1,
    ):
        raise_if_cancelled(cancel_requested)
        user_prompt = prompt_template_service.render_prompt(
            "text_translation_user",
            {
                "target_language": _language_label(target_language),
                "source_text": source_segment,
            },
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
        token_usage = token_usage_service.merge_token_usage(
            token_usage,
            response_result.get("usage"),
        )
        _emit_progress(
            progress_callback,
            translated_chunk_count,
            total_chunks,
            "AI translation in progress...",
            token_usage,
        )
        payload = dict(response_result.get("payload", {}))
        translated_text = str(payload.get("translated_text", "")).strip()
        if not translated_text:
            raise ValueError("AI translation returned an empty translated_text segment.")
        translated_segments.append(translated_text)
    return (
        "\n\n".join(segment for segment in translated_segments if segment.strip()),
        token_usage,
    )


def _emit_progress(
    progress_callback,
    progress_current: int,
    progress_total: int,
    message: str,
    token_usage: TokenUsagePayload | None = None,
) -> None:
    """
    @brief      Emit one normalized translation progress callback update.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  progress_current Current completed unit count.
    @param[in]  progress_total Total unit count.
    @param[in]  message Operator-facing progress message.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    if callable(progress_callback):
        progress_callback(
            progress_current,
            progress_total,
            progress_percent(progress_current, progress_total),
            message,
            token_usage,
        )


def _usable_input_budget(ai_profile_payload: dict[str, object]) -> int:
    """
    @brief      Compute the safe input budget for one translation request.
    @param[in]  ai_profile_payload Enabled AI profile payload.
    @return     Safe estimated input-token budget.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    context_window = max(
        1024,
        int(ai_profile_payload.get("context_window", config.DEFAULT_LLM_CONTEXT_WINDOW)),
    )
    max_output_tokens = max(
        256,
        int(
            ai_profile_payload.get(
                "max_output_tokens",
                config.DEFAULT_LLM_MAX_OUTPUT_TOKENS,
            )
        ),
    )
    return max(512, context_window - max_output_tokens - 768)


def _split_translation_source_text(source_text: str, usable_input_budget: int) -> list[str]:
    """
    @brief      Split source text into translation segments within the budget.
    @param[in]  source_text Source text to translate.
    @param[in]  usable_input_budget Safe estimated input-token budget.
    @return     Ordered translation source segments.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
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
    """
    @brief      Split one oversized paragraph into budget-safe translation parts.
    @param[in]  paragraph Source paragraph text.
    @param[in]  usable_input_budget Safe estimated input-token budget.
    @return     Ordered paragraph parts that fit the budget.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
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
    """
    @brief      Split one paragraph into approximate sentence units.
    @param[in]  paragraph Source paragraph text.
    @return     Ordered list of sentence-like text units.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    normalized = paragraph.strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=(?:[\"'A-Z0-9]))", normalized)
    return [part.strip() for part in parts if part.strip()]


def _split_translation_sentence_by_words(text: str, usable_input_budget: int) -> list[str]:
    """
    @brief      Split one oversized sentence into word-based budget-safe parts.
    @param[in]  text Source sentence text.
    @param[in]  usable_input_budget Safe estimated input-token budget.
    @return     Ordered sentence parts.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
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
    """
    @brief      Estimate token count from text length using a simple heuristic.
    @param[in]  text Source text value.
    @return     Estimated token count.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    return max(1, len(text) // 4)


def _language_label(language_code: str) -> str:
    """
    @brief      Resolve the display label for one translation language code.
    @param[in]  language_code Translation language code.
    @return     Human-readable language label or the original code.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    return _TRANSLATION_LANGUAGE_LABELS.get(language_code, language_code)


def _utc_now_iso() -> str:
    """
    @brief      Return the current UTC timestamp as an ISO-8601 string.
    @return     Current UTC timestamp string without microseconds.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# END OF FILE
