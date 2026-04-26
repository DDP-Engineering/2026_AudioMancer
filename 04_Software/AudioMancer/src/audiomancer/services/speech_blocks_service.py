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
@author Eng. Dan Dumitru Pasare
@date 2026-04-21
@version 0.6.0
"""

# IMPORTS

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    character_discovery_service,
    character_voices_service,
    deterministic_chunking_service,
    llm_provider_service,
    narrator_definition_service,
    prompt_template_service,
    token_usage_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    build_operation_output_path,
    progress_percent,
    raise_if_cancelled,
    relative_to_project,
    reset_operation_data,
    resolve_operation_path,
)

# CONSTANTS

_SPEECH_BLOCKS_LOGGER = get_component_logger("speech_blocks")

SPEECH_BLOCKS_STAGE_NOT_STARTED = "not_started"
SPEECH_BLOCKS_STAGE_IN_PROGRESS = "in_progress"
SPEECH_BLOCKS_STAGE_COMPLETED = "completed"

SPEAKER_KIND_NARRATOR = "narrator"
SPEAKER_KIND_CHARACTER = "character"
SPEAKER_KIND_OPERATION = "operation"
CONTENT_KIND_NARRATION = "narration"
CONTENT_KIND_DIALOGUE = "dialogue"
CONTENT_KIND_BACKGROUND_NOISE = "background_noise"
CONTENT_KIND_PAUSE = "pause"
CONTENT_KIND_INDICATION = "indication"

SPEECH_BLOCK_CONTENT_KINDS = (
    CONTENT_KIND_NARRATION,
    CONTENT_KIND_DIALOGUE,
    CONTENT_KIND_BACKGROUND_NOISE,
    CONTENT_KIND_PAUSE,
    CONTENT_KIND_INDICATION,
)

_NARRATOR_SPEAKER_ID = "narrator"
_NARRATOR_DISPLAY_NAME = "Narrator"

SpeechBlockPayload = dict[str, object]
SpeechBlocksReportPayload = dict[str, object]
OperationStatePayload = dict[str, object]


# PUBLIC API


@trace_function(_SPEECH_BLOCKS_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Load one optional Speech Blocks operation-state payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted operation-state payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    state_path = resolve_operation_path(project_root, "speech_blocks", config.SPEECH_BLOCKS_STATE_FILE_NAME)
    if not state_path.is_file():
        return None
    return dict(json.loads(state_path.read_text(encoding="utf-8")))


@trace_function(_SPEECH_BLOCKS_LOGGER)
def load_speech_blocks_report(project_root: str | Path) -> SpeechBlocksReportPayload | None:
    """
    @brief      Load one optional Speech Blocks report payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted report payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    report_path = resolve_operation_path(project_root, "speech_blocks", config.SPEECH_BLOCKS_REPORT_FILE_NAME)
    if not report_path.is_file():
        return None
    return dict(json.loads(report_path.read_text(encoding="utf-8")))


@trace_function(_SPEECH_BLOCKS_LOGGER)
def load_input_source_chunks(project_root: str | Path) -> list[dict[str, object]]:
    """
    @brief      Load one optional Speech Blocks source payload from operation state.
    @param[in]  project_root Active project root folder.
    @return     Ordered source-chunk snapshot payloads.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    operation_state = load_operation_state(project_root) or {}
    metadata = operation_state.get("metadata", {}) if isinstance(operation_state, dict) else {}
    if not isinstance(metadata, dict):
        return []
    payload = metadata.get("source_chunks")
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


@trace_function(_SPEECH_BLOCKS_LOGGER)
def load_speech_blocks(project_root: str | Path) -> list[SpeechBlockPayload]:
    """
    @brief      Load one optional persisted Speech Blocks output payload.
    @param[in]  project_root Active project root folder.
    @return     Ordered Speech Blocks payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    output_path = resolve_operation_path(project_root, "speech_blocks", config.SPEECH_BLOCKS_OUTPUT_FILE_NAME)
    if not output_path.is_file():
        return []
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return sort_speech_blocks([_normalize_persisted_speech_block(item) for item in payload if isinstance(item, dict)])


@trace_function(_SPEECH_BLOCKS_LOGGER)
def resolve_source_chunks(
    project_root: str | Path,
    manifest: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Resolve the source chunk set currently selected through Character Voices.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @return     Source-resolution payload with normalized source chunks.
    @exception  ValueError Raised when chunking or the selected language source is unavailable.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    original_chunks = sorted(
        deterministic_chunking_service.load_chunks(resolved_project_root),
        key=lambda item: int(item.get("sequence_index", 0)),
    )
    if not original_chunks:
        raise ValueError("Run text chunking before starting Speech Blocks.")

    selected_voice_language = character_voices_service.load_selected_voice_language(
        resolved_project_root,
        narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
    )
    original_language = narrator_definition_service.narrator_language_code(
        manifest.get("original_language", narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE)
    )
    if selected_voice_language == original_language:
        return {
            "selected_source_language": selected_voice_language,
            "source_kind": "original",
            "source_chunks": [
                {
                    "chunk_id": str(chunk.get("chunk_id", "")),
                    "sequence_index": int(chunk.get("sequence_index", 0)),
                    "text": str(chunk.get("text", "")),
                }
                for chunk in original_chunks
            ],
        }

    translation_report = ai_translation_service.load_translation_report(resolved_project_root)
    if not isinstance(translation_report, dict):
        raise ValueError("The selected Character Voices language is not available for Speech Blocks yet.")
    translated_language = str(translation_report.get("target_language", "")).strip()
    total_chunk_count = int(translation_report.get("total_chunk_count", 0))
    approved_chunk_count = int(translation_report.get("approved_chunk_count", 0))
    if selected_voice_language != translated_language:
        raise ValueError("The selected Character Voices language is not available for Speech Blocks yet.")
    if total_chunk_count <= 0 or total_chunk_count != approved_chunk_count:
        raise ValueError("Approve all translated chunks before generating Speech Blocks in the translated language.")

    translated_by_id = {
        str(chunk.get("chunk_id", "")): dict(chunk)
        for chunk in ai_translation_service.load_translated_chunks(resolved_project_root)
        if isinstance(chunk, dict) and str(chunk.get("chunk_id", "")).strip()
    }
    source_chunks: list[dict[str, object]] = []
    for original_chunk in original_chunks:
        chunk_id = str(original_chunk.get("chunk_id", "")).strip()
        translated_chunk = translated_by_id.get(chunk_id)
        translated_text = "" if translated_chunk is None else str(translated_chunk.get("translated_text", ""))
        if not translated_text.strip():
            raise ValueError(
                "Approve all translated chunks before generating Speech Blocks in the translated language."
            )
        source_chunks.append(
            {
                "chunk_id": chunk_id,
                "sequence_index": int(original_chunk.get("sequence_index", 0)),
                "text": translated_text,
            }
        )
    return {
        "selected_source_language": selected_voice_language,
        "source_kind": "translated",
        "source_chunks": source_chunks,
    }


@trace_function(_SPEECH_BLOCKS_LOGGER)
def start_or_continue_generation(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
) -> SpeechBlocksReportPayload:
    """
    @brief      Run Speech Blocks generation for the active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Final Speech Blocks report payload.
    @exception  ValueError Raised when prerequisites or profile data are invalid.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    profile_id = str(ai_profile_payload.get("id", "")).strip()
    model_name = str(ai_profile_payload.get("model_name", "")).strip()
    base_url = str(ai_profile_payload.get("base_url", "")).strip()
    if not profile_id or not model_name or not base_url:
        raise ValueError("Speech Blocks generation requires a valid enabled AI profile.")

    source_resolution = resolve_source_chunks(resolved_project_root, manifest)
    source_chunks = list(source_resolution["source_chunks"])
    source_language = str(source_resolution["selected_source_language"])
    source_kind = str(source_resolution["source_kind"])
    prompt_template_service.validate_required_prompts(["speech_blocks_system", "speech_blocks_user"])

    speaker_catalog = _speaker_catalog(character_discovery_service.load_character_profiles(resolved_project_root))
    input_fingerprint = _build_source_fingerprint(source_chunks, source_language, source_kind)
    existing_state = load_operation_state(resolved_project_root) or {}
    existing_report = load_speech_blocks_report(resolved_project_root)
    started_at = _resolve_started_at(existing_state)
    log_path = _resolve_log_path(resolved_project_root, started_at)
    token_usage = token_usage_service.restore_token_usage(
        None if existing_report is None else existing_report.get("token_usage"),
        _metadata_token_usage(existing_state),
    )
    existing_blocks, warning_records, start_chunk_index = _restore_resume_state(
        resolved_project_root,
        existing_state,
        input_fingerprint,
        profile_id,
        source_language,
    )

    _persist_state(
        resolved_project_root,
        source_chunks,
        existing_blocks,
        _rebuild_report(
            existing_blocks,
            source_language,
            source_kind,
            profile_id,
            len(source_chunks),
            start_chunk_index,
            warning_records,
            token_usage,
        ),
        _build_operation_state(
            resolved_project_root,
            source_chunks,
            existing_blocks,
            status="running",
            started_at=started_at,
            completed_at=None,
            source_language=source_language,
            source_kind=source_kind,
            profile_id=profile_id,
            warning_records=warning_records,
            input_fingerprint=input_fingerprint,
            log_path=log_path,
            token_usage=token_usage,
            next_chunk_index=start_chunk_index,
        ),
    )
    _emit_progress(
        progress_callback,
        start_chunk_index,
        len(source_chunks),
        "Speech Blocks generation in progress...",
        token_usage,
    )

    system_prompt = prompt_template_service.render_prompt("speech_blocks_system", {})
    all_blocks = list(existing_blocks)
    warning_entries = list(warning_records)
    for chunk_index in range(start_chunk_index, len(source_chunks)):
        raise_if_cancelled(cancel_requested)
        source_chunk = dict(source_chunks[chunk_index])
        user_prompt = _chunk_user_prompt(source_chunk, source_language, speaker_catalog)
        try:
            response_result = llm_provider_service.chat_json(
                ai_profile_payload,
                system_prompt,
                user_prompt,
                log_path=log_path,
                log_context={
                    "operation_kind": "speech_blocks",
                    "stage_label": "speech_blocks_chunk",
                    "profile_id": profile_id,
                    "chunk_index": chunk_index + 1,
                    "chunk_total": len(source_chunks),
                    "chunk_id": str(source_chunk.get("chunk_id", "")),
                },
                cancel_requested=cancel_requested,
            )
        except OperationCancelledError as error:
            raise OperationCancelledError(
                "Speech Blocks generation cancelled while waiting for the model response."
            ) from error
        token_usage = token_usage_service.merge_token_usage(token_usage, response_result.get("usage"))
        chunk_blocks, chunk_warnings = _normalize_chunk_blocks(
            source_chunk,
            dict(response_result.get("payload", {})),
            speaker_catalog,
            source_language,
        )
        all_blocks.extend(chunk_blocks)
        warning_entries.extend(chunk_warnings)
        report = _rebuild_report(
            all_blocks,
            source_language,
            source_kind,
            profile_id,
            len(source_chunks),
            chunk_index + 1,
            warning_entries,
            token_usage,
        )
        _persist_state(
            resolved_project_root,
            source_chunks,
            all_blocks,
            report,
            _build_operation_state(
                resolved_project_root,
                source_chunks,
                all_blocks,
                status="running",
                started_at=started_at,
                completed_at=None,
                source_language=source_language,
                source_kind=source_kind,
                profile_id=profile_id,
                warning_records=warning_entries,
                input_fingerprint=input_fingerprint,
                log_path=log_path,
                token_usage=token_usage,
                next_chunk_index=chunk_index + 1,
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
    report = _rebuild_report(
        all_blocks,
        source_language,
        source_kind,
        profile_id,
        len(source_chunks),
        len(source_chunks),
        warning_entries,
        token_usage,
        updated_at=completed_at,
    )
    _persist_state(
        resolved_project_root,
        source_chunks,
        all_blocks,
        report,
        _build_operation_state(
            resolved_project_root,
            source_chunks,
            all_blocks,
            status="review_pending",
            started_at=started_at,
            completed_at=completed_at,
            source_language=source_language,
            source_kind=source_kind,
            profile_id=profile_id,
            warning_records=warning_entries,
            input_fingerprint=input_fingerprint,
            log_path=log_path,
            token_usage=token_usage,
            next_chunk_index=None,
        ),
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    return list(_speaker_catalog(character_discovery_service.load_character_profiles(Path(project_root))).values())


def speech_block_book_sort_key(speech_block: dict[str, object]) -> tuple[int, int, str]:
    """
    @brief      Build the canonical book-order sort key for one Speech Block.
    @param[in]  speech_block Speech Block or Audio Block payload.
    @return     Tuple of chunk order, chunk-local sequence index, and identifier.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return sorted(speech_blocks, key=speech_block_book_sort_key)


def pause_duration_ms(text: object) -> int:
    """
    @brief      Parse a pause Speech Block duration from free-form text.
    @param[in]  text Candidate pause text.
    @return     Positive duration in milliseconds, or the configured default.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    reset_operation_data(project_root, "speech_blocks", include_current=True, keep_input_snapshots=False)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def insert_speech_block(
    project_root: str | Path,
    chunk_id: str,
    before_speech_block_id: str | None = None,
) -> tuple[SpeechBlocksReportPayload, str]:
    """
    @brief      Insert one manual Speech Block into a selected chunk.
    @param[in]  project_root Active project root folder.
    @param[in]  chunk_id Source chunk that receives the new block.
    @param[in]  before_speech_block_id Optional block id before which to insert.
    @return     Updated report payload and final inserted Speech Block id.
    @exception  ValueError Raised when Speech Blocks state, chunk, or before-block is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    selected_chunk_id = str(chunk_id).strip()
    source_chunks = load_input_source_chunks(resolved_project_root)
    if not source_chunks:
        raise ValueError("Generate Speech Blocks before inserting a Speech Block.")
    if not any(str(chunk.get("chunk_id", "")).strip() == selected_chunk_id for chunk in source_chunks):
        raise ValueError("The selected chunk was not found.")
    speech_blocks = load_speech_blocks(resolved_project_root)
    if not speech_blocks:
        raise ValueError("Generate Speech Blocks before inserting a Speech Block.")
    blocks_for_chunk = [block for block in speech_blocks if str(block.get("chunk_id", "")).strip() == selected_chunk_id]
    insertion_index = 1
    normalized_before_id = str(before_speech_block_id or "").strip()
    if normalized_before_id:
        before_block = _speech_block_by_id(blocks_for_chunk, normalized_before_id)
        if before_block is None:
            raise ValueError("The selected Speech Block was not found in the selected chunk.")
        insertion_index = int(before_block.get("sequence_index", 1))
    for block in speech_blocks:
        if (
            str(block.get("chunk_id", "")).strip() == selected_chunk_id
            and int(block.get("sequence_index", 0)) >= insertion_index
        ):
            block["sequence_index"] = int(block.get("sequence_index", 0)) + 1
    temporary_id = _speech_block_id(selected_chunk_id, insertion_index)
    speech_blocks.append(_manual_inserted_speech_block(selected_chunk_id, insertion_index, temporary_id))
    updated_report = _persist_report_update(resolved_project_root, speech_blocks)
    inserted_block = _manual_inserted_block_by_temporary_id(
        load_speech_blocks(resolved_project_root),
        selected_chunk_id,
        temporary_id,
        insertion_index,
    )
    if inserted_block is None:
        raise ValueError("The inserted Speech Block could not be reloaded.")
    return updated_report, str(inserted_block.get("speech_block_id", ""))


@trace_function(_SPEECH_BLOCKS_LOGGER)
def delete_speech_block(project_root: str | Path, speech_block_id: str) -> SpeechBlocksReportPayload:
    """
    @brief      Delete one selected Speech Block and renumber its chunk.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Target Speech Block identifier.
    @return     Updated Speech Blocks report payload.
    @exception  ValueError Raised when the block is unknown.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
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
def approve_all_speech_blocks(project_root: str | Path) -> SpeechBlocksReportPayload:
    """
    @brief      Approve every generated Speech Block.
    @param[in]  project_root Active project root folder.
    @return     Updated Speech Blocks report payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    approved_at = _utc_now_iso()
    for block in speech_blocks:
        block["approved"] = True
        block["approved_at"] = approved_at
    return _persist_report_update(resolved_project_root, speech_blocks)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def approve_speech_block(project_root: str | Path, speech_block_id: str) -> SpeechBlocksReportPayload:
    """
    @brief      Approve one generated Speech Block.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Target Speech Block identifier.
    @return     Updated Speech Blocks report payload.
    @exception  ValueError Raised when the block is unknown.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    selected_block = _speech_block_by_id(speech_blocks, speech_block_id)
    if selected_block is None:
        raise ValueError("The selected Speech Block was not found.")
    selected_block["approved"] = True
    selected_block["approved_at"] = _utc_now_iso()
    return _persist_report_update(resolved_project_root, speech_blocks)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def update_speech_block(
    project_root: str | Path,
    speech_block_id: str,
    speaker_id: str,
    content_kind: str,
    text: str,
) -> SpeechBlocksReportPayload:
    """
    @brief      Save one manually edited Speech Block and clear its warning indicator.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Target Speech Block identifier.
    @param[in]  speaker_id Selected speaker identifier.
    @param[in]  content_kind Selected content-kind token.
    @param[in]  text Edited block text.
    @return     Updated Speech Blocks report payload.
    @exception  ValueError Raised when the block or speaker is unknown.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    selected_block = _speech_block_by_id(speech_blocks, speech_block_id)
    if selected_block is None:
        raise ValueError("The selected Speech Block was not found.")
    normalized_content_kind = _normalize_content_kind(content_kind)
    if _is_operation_content_kind(normalized_content_kind):
        speaker_entry = _operation_speaker_entry(normalized_content_kind)
    else:
        speaker_catalog = _speaker_catalog(character_discovery_service.load_character_profiles(resolved_project_root))
        speaker_entry = speaker_catalog.get(str(speaker_id).strip())
        if speaker_entry is None:
            raise ValueError("The selected speaker was not found.")
    selected_block["speaker_kind"] = str(speaker_entry.get("speaker_kind", SPEAKER_KIND_NARRATOR))
    selected_block["speaker_id"] = str(speaker_entry.get("speaker_id", _NARRATOR_SPEAKER_ID))
    selected_block["speaker_display_name"] = str(speaker_entry.get("display_name", _NARRATOR_DISPLAY_NAME))
    selected_block["content_kind"] = normalized_content_kind
    selected_block["text"] = str(text)
    selected_block["warning_flags"] = []
    selected_block["approved"] = False
    selected_block["approved_at"] = None
    return _persist_report_update(resolved_project_root, speech_blocks)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def reset_speech_block_to_ai_baseline(
    project_root: str | Path,
    speech_block_id: str,
) -> SpeechBlocksReportPayload:
    """
    @brief      Restore one Speech Block's editable fields from the AI baseline.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Target Speech Block identifier.
    @return     Updated Speech Blocks report payload.
    @exception  ValueError Raised when the block is unknown.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    selected_block = _speech_block_by_id(speech_blocks, speech_block_id)
    if selected_block is None:
        raise ValueError("The selected Speech Block was not found.")
    selected_block["speaker_kind"] = str(selected_block.get("ai_speaker_kind", SPEAKER_KIND_NARRATOR))
    selected_block["speaker_id"] = str(selected_block.get("ai_speaker_id", _NARRATOR_SPEAKER_ID))
    selected_block["speaker_display_name"] = str(selected_block.get("ai_speaker_display_name", _NARRATOR_DISPLAY_NAME))
    selected_block["content_kind"] = _normalize_content_kind(
        selected_block.get("ai_content_kind", CONTENT_KIND_NARRATION)
    )
    selected_block["source_text"] = str(selected_block.get("ai_source_text", selected_block.get("source_text", "")))
    selected_block["text"] = str(selected_block.get("ai_text", ""))
    selected_block["approved"] = False
    selected_block["approved_at"] = None
    return _persist_report_update(resolved_project_root, speech_blocks)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def regenerate_chunk_speech_blocks(
    project_root: str | Path,
    manifest: dict[str, object],
    chunk_id: str,
    ai_profile_payload: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
) -> SpeechBlocksReportPayload:
    """
    @brief      Re-run Speech Blocks splitting for one selected source chunk.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  chunk_id Source chunk identifier to regenerate.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Updated Speech Blocks report payload.
    @exception  ValueError Raised when prerequisites or target chunk are invalid.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    profile_id = str(ai_profile_payload.get("id", "")).strip()
    model_name = str(ai_profile_payload.get("model_name", "")).strip()
    base_url = str(ai_profile_payload.get("base_url", "")).strip()
    if not profile_id or not model_name or not base_url:
        raise ValueError("Speech Blocks generation requires a valid enabled AI profile.")
    source_resolution = resolve_source_chunks(resolved_project_root, manifest)
    source_chunks = list(source_resolution["source_chunks"])
    source_language = str(source_resolution["selected_source_language"])
    source_kind = str(source_resolution["source_kind"])
    selected_chunk = next(
        (chunk for chunk in source_chunks if str(chunk.get("chunk_id", "")).strip() == chunk_id),
        None,
    )
    if selected_chunk is None:
        raise ValueError("The selected chunk was not found.")
    prompt_template_service.validate_required_prompts(["speech_blocks_system", "speech_blocks_user"])
    existing_report = load_speech_blocks_report(resolved_project_root)
    existing_state = load_operation_state(resolved_project_root) or {}
    token_usage = token_usage_service.restore_token_usage(
        None if existing_report is None else existing_report.get("token_usage"),
        _metadata_token_usage(existing_state),
    )
    started_at = _resolve_started_at(existing_state)
    log_path = _resolve_log_path(resolved_project_root, started_at)
    speaker_catalog = _speaker_catalog(character_discovery_service.load_character_profiles(resolved_project_root))
    system_prompt = prompt_template_service.render_prompt("speech_blocks_system", {})
    raise_if_cancelled(cancel_requested)
    user_prompt = _chunk_user_prompt(selected_chunk, source_language, speaker_catalog)
    try:
        response_result = llm_provider_service.chat_json(
            ai_profile_payload,
            system_prompt,
            user_prompt,
            log_path=log_path,
            log_context={
                "operation_kind": "speech_blocks",
                "stage_label": "speech_blocks_chunk_resplit",
                "profile_id": profile_id,
                "chunk_id": str(selected_chunk.get("chunk_id", "")),
            },
            cancel_requested=cancel_requested,
        )
    except OperationCancelledError as error:
        raise OperationCancelledError(
            "Speech Blocks re-splitting cancelled while waiting for the model response."
        ) from error
    token_usage = token_usage_service.merge_token_usage(token_usage, response_result.get("usage"))
    existing_blocks = [
        block
        for block in load_speech_blocks(resolved_project_root)
        if str(block.get("chunk_id", "")).strip() != chunk_id
    ]
    new_blocks, _chunk_warnings = _normalize_chunk_blocks(
        dict(selected_chunk),
        dict(response_result.get("payload", {})),
        speaker_catalog,
        source_language,
    )
    all_blocks = _renumber_speech_blocks(source_chunks, [*existing_blocks, *new_blocks])
    input_fingerprint = _build_source_fingerprint(source_chunks, source_language, source_kind)
    completed_at = _utc_now_iso()
    report = _rebuild_report(
        all_blocks,
        source_language,
        source_kind,
        profile_id,
        len(source_chunks),
        len({str(block.get("chunk_id", "")).strip() for block in all_blocks}),
        [],
        token_usage,
        updated_at=completed_at,
    )
    _persist_state(
        resolved_project_root,
        source_chunks,
        all_blocks,
        report,
        _build_operation_state(
            resolved_project_root,
            source_chunks,
            all_blocks,
            status="review_pending",
            started_at=started_at,
            completed_at=completed_at,
            source_language=source_language,
            source_kind=source_kind,
            profile_id=profile_id,
            warning_records=[],
            input_fingerprint=input_fingerprint,
            log_path=log_path,
            token_usage=token_usage,
            next_chunk_index=None,
        ),
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
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
        }
    return catalog


def _chunk_user_prompt(
    source_chunk: dict[str, object],
    source_language: str,
    speaker_catalog: dict[str, dict[str, object]],
) -> str:
    """
    @brief      Render the chunk-specific Speech Blocks user prompt.
    @param[in]  source_chunk Source chunk payload.
    @param[in]  source_language Active source language code.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @return     Rendered prompt text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    return prompt_template_service.render_prompt(
        "speech_blocks_user",
        {
            "source_language": narrator_definition_service.narrator_language_label(source_language),
            "chunk_id": str(source_chunk.get("chunk_id", "")),
            "chunk_text": str(source_chunk.get("text", "")),
            "speaker_catalog_json": json.dumps(list(speaker_catalog.values()), indent=2, ensure_ascii=False),
        },
    )


def _normalize_chunk_blocks(
    source_chunk: dict[str, object],
    response_payload: dict[str, object],
    speaker_catalog: dict[str, dict[str, object]],
    source_language: str,
) -> tuple[list[SpeechBlockPayload], list[dict[str, object]]]:
    """
    @brief      Normalize one AI response into persisted Speech Blocks payloads.
    @param[in]  source_chunk Current source chunk payload.
    @param[in]  response_payload Raw model response payload.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  source_language Active source language code.
    @return     Tuple of normalized chunk blocks and warning entries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.5.0
    """
    chunk_id = str(source_chunk.get("chunk_id", "")).strip()
    chunk_text = str(source_chunk.get("text", ""))
    candidate_blocks = response_payload.get("speech_blocks", response_payload.get("blocks", []))
    if not isinstance(candidate_blocks, list):
        candidate_blocks = []

    ai_blocks: list[dict[str, object]] = []
    for candidate_block in candidate_blocks:
        if not isinstance(candidate_block, dict):
            continue
        ai_block = _normalize_ai_block(candidate_block, speaker_catalog)
        if str(ai_block.get("text", "")).strip():
            ai_blocks.append(ai_block)

    normalized_blocks: list[SpeechBlockPayload] = []
    if not ai_blocks:
        fallback_flags = ["ambiguous_speaker", "source_coverage_mismatch"]
        return (
            [
                _build_speech_block_payload(
                    chunk_id,
                    1,
                    source_language,
                    SPEAKER_KIND_NARRATOR,
                    _NARRATOR_SPEAKER_ID,
                    _NARRATOR_DISPLAY_NAME,
                    CONTENT_KIND_NARRATION,
                    chunk_text,
                    fallback_flags,
                    source_text=chunk_text,
                )
            ],
            [
                {
                    "chunk_id": chunk_id,
                    "reason": "The model response did not contain usable Speech Blocks and fell back to narrator.",
                }
            ],
        )

    warning_entries = _validate_ai_block_source_spans(chunk_id, chunk_text, ai_blocks)
    for local_sequence_index, ai_block in enumerate(ai_blocks, start=1):
        text = str(ai_block.get("text", ""))
        content_kind = str(ai_block.get("content_kind", CONTENT_KIND_NARRATION))
        warning_flags = list(ai_block.get("warning_flags", []))
        source_text = str(ai_block.get("source_text", text))
        normalized_blocks.append(
            _build_speech_block_payload(
                chunk_id,
                local_sequence_index,
                source_language,
                str(ai_block.get("speaker_kind", SPEAKER_KIND_NARRATOR)),
                str(ai_block.get("speaker_id", _NARRATOR_SPEAKER_ID)),
                str(ai_block.get("speaker_display_name", _NARRATOR_DISPLAY_NAME)),
                content_kind,
                text,
                warning_flags,
                source_text=source_text,
            )
        )

    return normalized_blocks, warning_entries


def _build_speech_block_payload(
    chunk_id: str,
    sequence_index: int,
    source_language: str,
    speaker_kind: str,
    speaker_id: str,
    speaker_display_name: str,
    content_kind: str,
    text: str,
    warning_flags: list[str],
    source_text: str | None = None,
) -> SpeechBlockPayload:
    """
    @brief      Build one persisted Speech Blocks payload with AI baseline fields.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  sequence_index Chunk-local block index.
    @param[in]  source_language Active source language code.
    @param[in]  speaker_kind Current speaker kind token.
    @param[in]  speaker_id Current speaker identifier.
    @param[in]  speaker_display_name Current speaker display label.
    @param[in]  content_kind Current content-kind token.
    @param[in]  text Current block text.
    @param[in]  warning_flags Current warning flags.
    @param[in]  source_text Exact source text span represented by this block.
    @return     Persisted Speech Blocks payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.5.0
    """
    normalized_content_kind = _normalize_content_kind(content_kind)
    normalized_warning_flags = _normalize_warning_flags(warning_flags)
    if _is_operation_content_kind(normalized_content_kind):
        speaker_entry = _operation_speaker_entry(normalized_content_kind)
        normalized_speaker_kind = str(speaker_entry["speaker_kind"])
        normalized_speaker_id = str(speaker_entry["speaker_id"])
        normalized_speaker_display_name = str(speaker_entry["display_name"])
    else:
        normalized_speaker_kind = str(speaker_kind).strip() or SPEAKER_KIND_NARRATOR
        normalized_speaker_id = str(speaker_id).strip() or _NARRATOR_SPEAKER_ID
        normalized_speaker_display_name = str(speaker_display_name).strip() or _NARRATOR_DISPLAY_NAME
    normalized_text = str(text)
    normalized_source_text = normalized_text if source_text is None else str(source_text)
    return {
        "speech_block_id": _speech_block_id(chunk_id, sequence_index),
        "sequence_index": int(sequence_index),
        "chunk_id": str(chunk_id).strip(),
        "source_language": str(source_language).strip(),
        "speaker_kind": normalized_speaker_kind,
        "speaker_id": normalized_speaker_id,
        "speaker_display_name": normalized_speaker_display_name,
        "content_kind": normalized_content_kind,
        "source_text": normalized_source_text,
        "text": normalized_text,
        "ai_speaker_kind": normalized_speaker_kind,
        "ai_speaker_id": normalized_speaker_id,
        "ai_speaker_display_name": normalized_speaker_display_name,
        "ai_content_kind": normalized_content_kind,
        "ai_source_text": normalized_source_text,
        "ai_text": normalized_text,
        "warning_flags": normalized_warning_flags,
        "approved": False,
        "approved_at": None,
    }


def _normalize_ai_block(
    candidate_block: dict[str, object],
    speaker_catalog: dict[str, dict[str, object]],
) -> dict[str, object]:
    """
    @brief      Normalize one model-supplied Speech Blocks payload before source-span reconciliation.
    @param[in]  candidate_block Raw model-supplied block payload.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @return     Normalized AI block with resolved speaker metadata.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.5.0
    """
    content_kind = _normalize_content_kind(candidate_block.get("content_kind", CONTENT_KIND_NARRATION))
    source_text = str(candidate_block.get("source_text", candidate_block.get("text", "")))
    raw_text = str(candidate_block.get("text", source_text))
    if not raw_text.strip():
        raw_text = source_text
    text = _normalize_block_text(raw_text, content_kind)
    if _is_operation_content_kind(content_kind):
        speaker_entry = _operation_speaker_entry(content_kind)
        return {
            "speaker_kind": str(speaker_entry["speaker_kind"]),
            "speaker_id": str(speaker_entry["speaker_id"]),
            "speaker_display_name": str(speaker_entry["display_name"]),
            "content_kind": content_kind,
            "source_text": source_text,
            "text": text,
            "warning_flags": _normalize_warning_flags(candidate_block.get("warning_flags")),
        }
    requested_speaker_id = str(candidate_block.get("speaker_id", "")).strip()
    speaker_entry, ambiguous_speaker = _resolve_speaker_entry(requested_speaker_id, speaker_catalog)
    warning_flags = _normalize_warning_flags(candidate_block.get("warning_flags"))
    if ambiguous_speaker:
        _append_warning_flag(warning_flags, "ambiguous_speaker")
    return {
        "speaker_kind": str(speaker_entry.get("speaker_kind", SPEAKER_KIND_NARRATOR)),
        "speaker_id": str(speaker_entry.get("speaker_id", _NARRATOR_SPEAKER_ID)),
        "speaker_display_name": str(speaker_entry.get("display_name", _NARRATOR_DISPLAY_NAME)),
        "content_kind": content_kind,
        "source_text": source_text,
        "text": text,
        "warning_flags": warning_flags,
    }


def _validate_ai_block_source_spans(
    chunk_id: str,
    chunk_text: str,
    ai_blocks: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Validate AI-owned source spans without replacing model block boundaries.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  chunk_text Full source chunk text.
    @param[in]  ai_blocks Normalized AI blocks to validate and annotate.
    @return     Human-readable warning entries for the chunk.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    warning_entries: list[dict[str, object]] = []
    cursor = 0
    for ai_block in ai_blocks:
        source_text = str(ai_block.get("source_text", ""))
        text = str(ai_block.get("text", ""))
        content_kind = str(ai_block.get("content_kind", CONTENT_KIND_NARRATION))
        warning_flags = list(ai_block.get("warning_flags", []))

        if not source_text.strip():
            _append_warning_flag(warning_flags, "source_coverage_mismatch")
        else:
            ordered_index = chunk_text.find(source_text, cursor)
            if ordered_index >= 0:
                if chunk_text[cursor:ordered_index].strip():
                    _append_warning_flag(warning_flags, "source_coverage_mismatch")
                cursor = ordered_index + len(source_text)
            elif chunk_text.find(source_text) >= 0:
                _append_warning_flag(warning_flags, "source_order_mismatch")
            else:
                _append_warning_flag(warning_flags, "source_coverage_mismatch")

        expected_audio_text = _normalize_block_text(source_text, content_kind)
        if _block_text_key(text) != _block_text_key(expected_audio_text):
            _append_warning_flag(warning_flags, "model_text_modified")

        ai_block["warning_flags"] = warning_flags

    if ai_blocks and chunk_text[cursor:].strip():
        warning_flags = list(ai_blocks[-1].get("warning_flags", []))
        _append_warning_flag(warning_flags, "source_coverage_mismatch")
        ai_blocks[-1]["warning_flags"] = warning_flags

    if _block_text_key(" ".join(str(block.get("source_text", "")) for block in ai_blocks)) != _block_text_key(
        chunk_text
    ):
        warning_flags = list(ai_blocks[-1].get("warning_flags", []))
        _append_warning_flag(warning_flags, "source_coverage_mismatch")
        ai_blocks[-1]["warning_flags"] = warning_flags

    for ai_block in ai_blocks:
        for warning_flag in _normalize_warning_flags(ai_block.get("warning_flags")):
            warning_entries.append({"chunk_id": chunk_id, "reason": _speech_block_warning_reason(warning_flag)})
    return warning_entries


def _normalize_source_unit_blocks(
    chunk_id: str,
    source_units: list[dict[str, object]],
    ai_blocks: list[dict[str, object]],
    speaker_catalog: dict[str, dict[str, object]],
    source_language: str,
) -> tuple[list[SpeechBlockPayload], list[dict[str, object]]]:
    """
    @brief      Build persisted blocks from deterministic source spans and AI speaker hints.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  source_units Deterministic source text spans.
    @param[in]  ai_blocks Normalized AI blocks used only as speaker hints.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  source_language Active source language code.
    @return     Tuple of normalized chunk blocks and warning entries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
    """
    ai_lookup = _build_ai_block_lookup(ai_blocks)
    normalized_blocks: list[SpeechBlockPayload] = []
    warning_entries: list[dict[str, object]] = []
    for local_sequence_index, source_unit in enumerate(source_units, start=1):
        content_kind = str(source_unit.get("content_kind", CONTENT_KIND_NARRATION))
        text = str(source_unit.get("text", ""))
        speaker_entry = speaker_catalog[_NARRATOR_SPEAKER_ID]
        warning_flags: list[str] = []
        if content_kind == CONTENT_KIND_DIALOGUE:
            ai_match = _pop_ai_block_match(ai_lookup, text, content_kind)
            if ai_match is not None:
                speaker_entry = {
                    "speaker_kind": str(ai_match.get("speaker_kind", SPEAKER_KIND_NARRATOR)),
                    "speaker_id": str(ai_match.get("speaker_id", _NARRATOR_SPEAKER_ID)),
                    "display_name": str(ai_match.get("speaker_display_name", _NARRATOR_DISPLAY_NAME)),
                }
                warning_flags = list(ai_match.get("warning_flags", []))
            else:
                speaker_entry = _infer_dialogue_speaker(source_units, local_sequence_index - 1, speaker_catalog)
                if str(speaker_entry.get("speaker_id", _NARRATOR_SPEAKER_ID)) == _NARRATOR_SPEAKER_ID:
                    _append_warning_flag(warning_flags, "ambiguous_speaker")
            if str(speaker_entry.get("speaker_id", _NARRATOR_SPEAKER_ID)) == _NARRATOR_SPEAKER_ID:
                _append_warning_flag(warning_flags, "ambiguous_speaker")
        normalized_blocks.append(
            _build_speech_block_payload(
                chunk_id,
                local_sequence_index,
                source_language,
                str(speaker_entry.get("speaker_kind", SPEAKER_KIND_NARRATOR)),
                str(speaker_entry.get("speaker_id", _NARRATOR_SPEAKER_ID)),
                str(speaker_entry.get("display_name", _NARRATOR_DISPLAY_NAME)),
                content_kind,
                text,
                warning_flags,
            )
        )
        if "ambiguous_speaker" in warning_flags:
            warning_entries.append(
                {
                    "chunk_id": chunk_id,
                    "reason": "Speaker attribution was ambiguous and fell back to narrator.",
                }
            )
    return normalized_blocks, warning_entries


def _split_source_text_units(text: str) -> list[dict[str, object]]:
    """
    @brief      Split source text into deterministic narration and quoted-dialogue spans.
    @param[in]  text Source chunk text.
    @return     Ordered source-unit payloads covering all non-empty source text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    source_units: list[dict[str, object]] = []
    cursor = 0
    unit_index = 1
    in_dialogue = False
    span_start = 0
    while cursor < len(text):
        if text[cursor] != '"':
            cursor += 1
            continue
        if in_dialogue:
            unit_index = _append_source_unit(
                source_units,
                unit_index,
                CONTENT_KIND_DIALOGUE,
                text[span_start:cursor],
            )
            in_dialogue = False
            span_start = cursor + 1
        else:
            unit_index = _append_source_unit(
                source_units,
                unit_index,
                CONTENT_KIND_NARRATION,
                text[span_start:cursor],
            )
            in_dialogue = True
            span_start = cursor + 1
        cursor += 1
    unit_index = _append_source_unit(
        source_units,
        unit_index,
        CONTENT_KIND_DIALOGUE if in_dialogue else CONTENT_KIND_NARRATION,
        text[span_start:],
    )
    return source_units


def _append_source_unit(
    source_units: list[dict[str, object]],
    unit_index: int,
    content_kind: str,
    text: str,
) -> int:
    """
    @brief      Append one non-empty deterministic source unit.
    @param[in]  source_units Target source-unit list.
    @param[in]  unit_index Next source-unit sequence number.
    @param[in]  content_kind Unit content kind.
    @param[in]  text Unit text.
    @return     Next source-unit sequence number.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized_text = text.strip()
    if not normalized_text:
        return unit_index
    source_units.append(
        {
            "source_unit_id": f"source-unit-{unit_index:04d}",
            "content_kind": content_kind,
            "text": normalized_text,
        }
    )
    return unit_index + 1


def _build_ai_block_lookup(ai_blocks: list[dict[str, object]]) -> dict[tuple[str, str], list[dict[str, object]]]:
    """
    @brief      Build a text lookup for model blocks used as speaker hints.
    @param[in]  ai_blocks Normalized model blocks.
    @return     Lookup keyed by content kind and normalized text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    lookup: dict[tuple[str, str], list[dict[str, object]]] = {}
    for ai_block in ai_blocks:
        text_key = _block_text_key(str(ai_block.get("text", "")))
        if not text_key:
            continue
        content_kind = str(ai_block.get("content_kind", CONTENT_KIND_NARRATION))
        lookup.setdefault((content_kind, text_key), []).append(ai_block)
        lookup.setdefault(("", text_key), []).append(ai_block)
    return lookup


def _pop_ai_block_match(
    ai_lookup: dict[tuple[str, str], list[dict[str, object]]],
    text: str,
    content_kind: str,
) -> dict[str, object] | None:
    """
    @brief      Pop one model block whose text matches a deterministic source unit.
    @param[in]  ai_lookup Model-block lookup.
    @param[in]  text Deterministic source-unit text.
    @param[in]  content_kind Source-unit content kind.
    @return     Matching model block or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    text_key = _block_text_key(text)
    for lookup_key in ((content_kind, text_key), ("", text_key)):
        matches = ai_lookup.get(lookup_key, [])
        if matches:
            matched_block = matches.pop(0)
            for sibling_lookup_key in ((content_kind, text_key), ("", text_key)):
                if sibling_lookup_key == lookup_key:
                    continue
                sibling_matches = ai_lookup.get(sibling_lookup_key, [])
                if matched_block in sibling_matches:
                    sibling_matches.remove(matched_block)
            return matched_block
    return None


def _block_text_key(text: str) -> str:
    """
    @brief      Normalize text for exact source-span matching.
    @param[in]  text Candidate text.
    @return     Matching key.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return " ".join(text.strip().split()).casefold()


def _resolve_speaker_entry(
    requested_speaker_id: str,
    speaker_catalog: dict[str, dict[str, object]],
) -> tuple[dict[str, object], bool]:
    """
    @brief      Resolve one model-requested speaker id against the allowed catalog.
    @param[in]  requested_speaker_id Candidate model speaker id.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @return     Speaker entry and ambiguity flag.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized_request = _speaker_match_key(requested_speaker_id)
    if not normalized_request:
        return speaker_catalog[_NARRATOR_SPEAKER_ID], False
    for speaker_id, speaker_entry in speaker_catalog.items():
        if normalized_request == _speaker_match_key(speaker_id):
            return speaker_entry, False
    display_matches = [
        speaker_entry
        for speaker_entry in speaker_catalog.values()
        if normalized_request == _speaker_match_key(str(speaker_entry.get("display_name", "")))
    ]
    if len(display_matches) == 1:
        return display_matches[0], False
    suffix_matches = [
        speaker_entry
        for speaker_entry in speaker_catalog.values()
        if normalized_request
        and normalized_request in _speaker_match_key(str(speaker_entry.get("display_name", ""))).split()
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0], False
    if normalized_request == _NARRATOR_SPEAKER_ID:
        return speaker_catalog[_NARRATOR_SPEAKER_ID], False
    return speaker_catalog[_NARRATOR_SPEAKER_ID], True


def _infer_dialogue_speaker(
    source_units: list[dict[str, object]],
    unit_index: int,
    speaker_catalog: dict[str, dict[str, object]],
) -> dict[str, object]:
    """
    @brief      Infer a dialogue speaker from nearby named narration attribution.
    @param[in]  source_units Deterministic source units.
    @param[in]  unit_index Index of the dialogue unit.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @return     Inferred speaker entry or narrator when no safe inference exists.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    context_parts: list[str] = []
    for neighbor_index in (unit_index + 1, unit_index - 1):
        if 0 <= neighbor_index < len(source_units):
            neighbor = source_units[neighbor_index]
            if str(neighbor.get("content_kind", "")) == CONTENT_KIND_NARRATION:
                context_parts.append(str(neighbor.get("text", "")))
    context = " ".join(context_parts).casefold()
    if not any(verb in context for verb in (" said", " asked", " snapped", " demanded", " replied", " sneered")):
        return speaker_catalog[_NARRATOR_SPEAKER_ID]
    matches: list[dict[str, object]] = []
    for speaker_id, speaker_entry in speaker_catalog.items():
        if speaker_id == _NARRATOR_SPEAKER_ID:
            continue
        display_name = str(speaker_entry.get("display_name", "")).strip()
        name_parts = [part.casefold() for part in display_name.replace("_", " ").split() if part.strip()]
        if display_name.casefold() in context or any(part in context.split() for part in name_parts):
            matches.append(speaker_entry)
    if len(matches) == 1:
        return matches[0]
    return speaker_catalog[_NARRATOR_SPEAKER_ID]


def _speaker_match_key(value: str) -> str:
    """
    @brief      Build a conservative speaker matching key.
    @param[in]  value Candidate speaker id or display name.
    @return     Normalized speaker matching key.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return " ".join(str(value).strip().replace("_", " ").replace("-", " ").casefold().split())


def _append_warning_flag(warning_flags: list[str], warning_flag: str) -> None:
    """
    @brief      Append one warning flag when it is not present already.
    @param[in]  warning_flags Warning flag list to mutate.
    @param[in]  warning_flag Warning flag token.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if warning_flag not in warning_flags:
        warning_flags.append(warning_flag)


def _speech_block_warning_reason(warning_flag: str) -> str:
    """
    @brief      Resolve a report note for one Speech Blocks warning flag.
    @param[in]  warning_flag Warning flag token.
    @return     Human-readable warning reason.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return {
        "ambiguous_speaker": "Speaker attribution was ambiguous and fell back to narrator.",
        "source_coverage_mismatch": "Model source spans do not fully cover the chunk in reading order.",
        "source_order_mismatch": "Model source spans are not in chunk reading order.",
        "model_text_modified": "Model audio text differs from the source span beyond delimiter cleanup.",
    }.get(str(warning_flag).strip(), str(warning_flag).strip() or "Speech Block warning.")


def _normalize_block_text(text: str, content_kind: str) -> str:
    """
    @brief      Normalize one Speech Blocks text span without changing wording.
    @param[in]  text Candidate block text.
    @param[in]  content_kind Block content-kind token.
    @return     Persisted block text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    if content_kind != CONTENT_KIND_DIALOGUE:
        return text
    normalized_text = text.strip()
    normalized_text = re.sub(r"^[-–—]\s+", "", normalized_text, count=1)
    for opening_quote, closing_quote in (('"', '"'), ("“", "”"), ("‘", "’"), ("«", "»")):
        if (
            len(normalized_text) >= 2
            and normalized_text.startswith(opening_quote)
            and normalized_text.endswith(closing_quote)
        ):
            return normalized_text[1:-1].strip()
    return normalized_text


def _normalize_content_kind(value: object) -> str:
    """
    @brief      Normalize one Speech Blocks content-kind token.
    @param[in]  value Candidate content-kind value.
    @return     Supported content-kind token.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    normalized = str(value).strip().casefold().replace(" ", "_").replace("-", "_")
    if normalized in SPEECH_BLOCK_CONTENT_KINDS:
        return normalized
    return CONTENT_KIND_NARRATION


def _is_operation_content_kind(content_kind: str) -> bool:
    """
    @brief      Return whether one content kind is represented as an operation row.
    @param[in]  content_kind Normalized content-kind token.
    @return     True for metadata-only operation content kinds.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return str(content_kind).strip() in {
        CONTENT_KIND_BACKGROUND_NOISE,
        CONTENT_KIND_PAUSE,
        CONTENT_KIND_INDICATION,
    }


def _operation_speaker_entry(content_kind: str) -> dict[str, object]:
    """
    @brief      Build the persisted speaker fields for one metadata-only operation.
    @param[in]  content_kind Normalized operation content-kind token.
    @return     Speaker-like operation entry used by JSON and list rendering.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    normalized_content_kind = _normalize_content_kind(content_kind)
    return {
        "speaker_kind": SPEAKER_KIND_OPERATION,
        "speaker_id": normalized_content_kind,
        "display_name": _operation_display_name(normalized_content_kind),
    }


def _operation_display_name(content_kind: str) -> str:
    """
    @brief      Resolve the stable persisted display name for a metadata-only operation.
    @param[in]  content_kind Normalized operation content-kind token.
    @return     Operator-facing operation name.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return {
        CONTENT_KIND_BACKGROUND_NOISE: "Background Noise",
        CONTENT_KIND_PAUSE: "Pause",
        CONTENT_KIND_INDICATION: "Indication",
    }.get(str(content_kind).strip(), "Operation")


def _speech_block_id(chunk_id: str, sequence_index: int) -> str:
    """
    @brief      Build the persisted `CCCC-BBBBBB` Speech Block identifier.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  sequence_index Chunk-local Speech Block sequence index.
    @return     Stable Speech Block identifier.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    chunk_number = _chunk_order_from_id(chunk_id)
    return f"{chunk_number:04d}-{max(int(sequence_index), 0):06d}"


def _chunk_order_from_id(chunk_id: str) -> int:
    """
    @brief      Resolve a numeric chunk-order token from one chunk identifier.
    @param[in]  chunk_id Source chunk identifier.
    @return     Positive chunk-order value or zero when no digits are present.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    digits = "".join(character for character in str(chunk_id) if character.isdigit())
    return int(digits[-4:] or "0")


def _normalize_warning_flags(value: object) -> list[str]:
    """
    @brief      Normalize one warning-flag list payload.
    @param[in]  value Candidate warning-flag value.
    @return     Ordered warning-flag string list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not isinstance(value, list):
        return []
    normalized_flags: list[str] = []
    for item in value:
        flag = str(item).strip()
        if flag and flag not in normalized_flags:
            normalized_flags.append(flag)
    return normalized_flags


def _normalize_persisted_speech_block(payload: dict[str, object]) -> SpeechBlockPayload:
    """
    @brief      Normalize one persisted Speech Blocks payload.
    @param[in]  payload Raw persisted payload.
    @return     Normalized Speech Blocks payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
    """
    if "chunk_sequence_index" in payload:
        raise ValueError(
            "Speech Blocks uses a legacy global-sequence schema. Reset and regenerate Speech Blocks for this project."
        )
    sequence_index = int(payload.get("sequence_index", 0))
    chunk_id = str(payload.get("chunk_id", "")).strip()
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
    ai_speaker_kind = str(payload.get("ai_speaker_kind", speaker_kind)).strip() or speaker_kind
    ai_speaker_id = str(payload.get("ai_speaker_id", speaker_id)).strip() or speaker_id
    ai_speaker_display_name = str(payload.get("ai_speaker_display_name", speaker_display_name)).strip()
    if not ai_speaker_display_name:
        ai_speaker_display_name = speaker_display_name
    ai_content_kind = _normalize_content_kind(payload.get("ai_content_kind", content_kind))
    if _is_operation_content_kind(ai_content_kind):
        operation_entry = _operation_speaker_entry(ai_content_kind)
        ai_speaker_kind = str(operation_entry["speaker_kind"])
        ai_speaker_id = str(operation_entry["speaker_id"])
        ai_speaker_display_name = str(operation_entry["display_name"])
    ai_source_text = str(payload.get("ai_source_text", source_text))
    ai_text = str(payload.get("ai_text", text))
    return {
        "speech_block_id": _speech_block_id(chunk_id, sequence_index),
        "sequence_index": sequence_index,
        "chunk_id": chunk_id,
        "source_language": str(payload.get("source_language", "")).strip(),
        "speaker_kind": speaker_kind,
        "speaker_id": speaker_id,
        "speaker_display_name": speaker_display_name,
        "content_kind": content_kind,
        "source_text": source_text,
        "text": text,
        "ai_speaker_kind": ai_speaker_kind,
        "ai_speaker_id": ai_speaker_id,
        "ai_speaker_display_name": ai_speaker_display_name,
        "ai_content_kind": ai_content_kind,
        "ai_source_text": ai_source_text,
        "ai_text": ai_text,
        "warning_flags": _normalize_warning_flags(payload.get("warning_flags")),
        "approved": bool(payload.get("approved", False)),
        "approved_at": None if payload.get("approved_at") in (None, "") else str(payload.get("approved_at")),
    }


def _rebuild_report(
    speech_blocks: list[SpeechBlockPayload],
    source_language: str,
    source_kind: str,
    profile_id: str,
    total_chunk_count: int,
    processed_chunk_count: int,
    warning_records: list[dict[str, object]],
    token_usage: dict[str, object],
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
    @param[in]  updated_at Optional report timestamp override.
    @return     Rebuilt Speech Blocks report payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    _ = warning_records
    approved_block_count = _approved_block_count(speech_blocks)
    total_block_count = len(speech_blocks)
    warning_entries = _warning_records_from_blocks(speech_blocks)
    if total_chunk_count > 0 and processed_chunk_count >= total_chunk_count and total_block_count > 0:
        stage_status = (
            SPEECH_BLOCKS_STAGE_COMPLETED
            if approved_block_count >= total_block_count
            else SPEECH_BLOCKS_STAGE_IN_PROGRESS
        )
    elif processed_chunk_count > 0 or speech_blocks:
        stage_status = SPEECH_BLOCKS_STAGE_IN_PROGRESS
    else:
        stage_status = SPEECH_BLOCKS_STAGE_NOT_STARTED
    return {
        "source_language": source_language,
        "source_kind": source_kind,
        "ai_profile_id": profile_id,
        "speech_blocks_stage_status": stage_status,
        "processed_chunk_count": processed_chunk_count,
        "total_chunk_count": total_chunk_count,
        "speech_block_count": total_block_count,
        "approved_block_count": approved_block_count,
        "total_block_count": total_block_count,
        "warning_count": len(warning_entries),
        "warnings": warning_entries,
        "updated_at": updated_at or _utc_now_iso(),
        "token_usage": token_usage_service.coerce_token_usage(token_usage),
    }


def _approved_block_count(speech_blocks: list[SpeechBlockPayload]) -> int:
    """
    @brief      Count approved Speech Blocks.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @return     Number of approved Speech Blocks.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    return sum(1 for block in speech_blocks if bool(block.get("approved", False)))


def _warning_records_from_blocks(speech_blocks: list[SpeechBlockPayload]) -> list[dict[str, object]]:
    """
    @brief      Build report warning entries from current block warning flags.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @return     Ordered report warning entries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    records: list[dict[str, object]] = []
    for block in speech_blocks:
        warning_flags = _normalize_warning_flags(block.get("warning_flags"))
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


def _build_operation_state(
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
    @return     Persisted operation-state payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    _ = warning_records
    input_path = _source_chunks_input_path(project_root, source_kind)
    output_path = build_operation_output_path(project_root, "speech_blocks", config.SPEECH_BLOCKS_OUTPUT_FILE_NAME)
    report_path = build_operation_output_path(project_root, "speech_blocks", config.SPEECH_BLOCKS_REPORT_FILE_NAME)
    processed_chunk_count = len({str(block.get("chunk_id", "")).strip() for block in speech_blocks})
    warning_entries = _warning_records_from_blocks(speech_blocks)
    return {
        "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        "status": status,
        "input_paths": [relative_to_project(project_root, input_path)],
        "output_paths": [relative_to_project(project_root, output_path)],
        "artifact_paths": [
            relative_to_project(project_root, report_path),
            relative_to_project(project_root, log_path),
        ],
        "progress_current": processed_chunk_count,
        "progress_total": len(source_chunks),
        "mode": "ai_assisted",
        "started_at": started_at,
        "completed_at": completed_at,
        "updated_at": _utc_now_iso(),
        "warning_count": len(warning_entries),
        "metadata": {
            "source_language": source_language,
            "source_kind": source_kind,
            "ai_profile_id": profile_id,
            "processed_chunk_count": processed_chunk_count,
            "total_chunk_count": len(source_chunks),
            "speech_block_count": len(speech_blocks),
            "approved_block_count": _approved_block_count(speech_blocks),
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
        },
        "resume_checkpoint": (
            None
            if next_chunk_index is None
            else {
                "next_chunk_index": next_chunk_index,
                "source_snapshot_fingerprint": input_fingerprint,
                "source_language": source_language,
                "ai_profile_id": profile_id,
            }
        ),
    }


def _persist_state(
    project_root: Path,
    source_chunks: list[dict[str, object]],
    speech_blocks: list[SpeechBlockPayload],
    report: SpeechBlocksReportPayload,
    operation_state: OperationStatePayload,
) -> None:
    """
    @brief      Persist the Speech Blocks output, report, and state.
    @param[in]  project_root Active project root folder.
    @param[in]  source_chunks Source snapshot payload list.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  report Current Speech Blocks report payload.
    @param[in]  operation_state Current Speech Blocks operation-state payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    _ = source_chunks
    build_operation_output_path(project_root, "speech_blocks", config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(speech_blocks, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    build_operation_output_path(project_root, "speech_blocks", config.SPEECH_BLOCKS_REPORT_FILE_NAME).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    build_operation_output_path(project_root, "speech_blocks", config.SPEECH_BLOCKS_STATE_FILE_NAME).write_text(
        json.dumps(operation_state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _persist_report_update(
    project_root: Path,
    speech_blocks: list[SpeechBlockPayload],
) -> SpeechBlocksReportPayload:
    """
    @brief      Persist a review-only Speech Blocks update.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_blocks Updated Speech Blocks payload list.
    @return     Updated report payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    source_chunks = load_input_source_chunks(project_root)
    report = load_speech_blocks_report(project_root) or {}
    operation_state = load_operation_state(project_root) or {}
    metadata = operation_state.get("metadata", {}) if isinstance(operation_state, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    source_language = str(report.get("source_language", metadata.get("source_language", ""))).strip()
    source_kind = str(report.get("source_kind", metadata.get("source_kind", ""))).strip()
    profile_id = str(report.get("ai_profile_id", metadata.get("ai_profile_id", ""))).strip()
    token_usage = token_usage_service.restore_token_usage(report.get("token_usage"), metadata.get("token_usage"))
    input_fingerprint = str(metadata.get("source_snapshot_fingerprint", "")).strip()
    if not input_fingerprint and source_chunks and source_language and source_kind:
        input_fingerprint = _build_source_fingerprint(source_chunks, source_language, source_kind)
    started_at = str(operation_state.get("started_at", "")).strip() or _utc_now_iso()
    completed_at = str(operation_state.get("completed_at", "")).strip() or _utc_now_iso()
    log_path = _resolve_log_path(project_root, started_at)
    renumbered_blocks = _renumber_speech_blocks(source_chunks, speech_blocks)
    updated_report = _rebuild_report(
        renumbered_blocks,
        source_language,
        source_kind,
        profile_id,
        len(source_chunks),
        len({str(block.get("chunk_id", "")).strip() for block in renumbered_blocks}),
        [],
        token_usage,
    )
    status = (
        "completed"
        if str(updated_report.get("speech_blocks_stage_status", "")).strip() == SPEECH_BLOCKS_STAGE_COMPLETED
        else "review_pending"
    )
    _persist_state(
        project_root,
        source_chunks,
        renumbered_blocks,
        updated_report,
        _build_operation_state(
            project_root,
            source_chunks,
            renumbered_blocks,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            source_language=source_language,
            source_kind=source_kind,
            profile_id=profile_id,
            warning_records=[],
            input_fingerprint=input_fingerprint,
            log_path=log_path,
            token_usage=token_usage,
            next_chunk_index=None,
        ),
    )
    return updated_report


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
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
    for block in ordered_blocks:
        chunk_id = str(block.get("chunk_id", "")).strip()
        local_counts[chunk_id] = local_counts.get(chunk_id, 0) + 1
        sequence_index = local_counts[chunk_id]
        renumbered_block = dict(block)
        renumbered_block["sequence_index"] = sequence_index
        renumbered_block.pop("chunk_sequence_index", None)
        renumbered_block["speech_block_id"] = _speech_block_id(chunk_id, sequence_index)
        renumbered_blocks.append(renumbered_block)
    return renumbered_blocks


def _manual_inserted_speech_block(chunk_id: str, sequence_index: int, speech_block_id: str) -> SpeechBlockPayload:
    """
    @brief      Build the default payload for a manually inserted Speech Block.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  sequence_index Requested chunk-local insertion index.
    @param[in]  speech_block_id Temporary Speech Block identifier.
    @return     New unapproved narrator narration Speech Block payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
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
        "ai_speaker_kind": SPEAKER_KIND_NARRATOR,
        "ai_speaker_id": _NARRATOR_SPEAKER_ID,
        "ai_speaker_display_name": _NARRATOR_DISPLAY_NAME,
        "ai_content_kind": CONTENT_KIND_NARRATION,
        "ai_source_text": "",
        "ai_text": "",
        "warning_flags": [],
        "approved": False,
        "approved_at": None,
    }


def _manual_inserted_block_by_temporary_id(
    speech_blocks: list[SpeechBlockPayload],
    chunk_id: str,
    temporary_id: str,
    insertion_index: int,
) -> SpeechBlockPayload | None:
    """
    @brief      Resolve the final inserted block after chunk-local renumbering.
    @param[in]  speech_blocks Reloaded Speech Blocks payload list.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  temporary_id Pre-renumber inserted Speech Block id.
    @param[in]  insertion_index Requested insertion sequence index.
    @return     Matching inserted block or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return next(
        (
            block
            for block in speech_blocks
            if str(block.get("chunk_id", "")).strip() == chunk_id
            and int(block.get("sequence_index", 0)) == insertion_index
            and str(block.get("ai_text", "")) == ""
            and str(block.get("text", "")) == ""
            and str(block.get("ai_speaker_id", "")).strip() == _NARRATOR_SPEAKER_ID
            and str(block.get("speech_block_id", "")).strip()
            in {temporary_id, _speech_block_id(chunk_id, insertion_index)}
        ),
        None,
    )


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    normalized_id = str(speech_block_id).strip()
    return next(
        (block for block in speech_blocks if str(block.get("speech_block_id", "")).strip() == normalized_id),
        None,
    )


def _source_chunks_input_path(project_root: Path, source_kind: str) -> Path:
    """
    @brief      Resolve the upstream Speech Blocks source artifact path.
    @param[in]  project_root Active project root folder.
    @param[in]  source_kind Active source-kind token.
    @return     Absolute project-local source artifact path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    if str(source_kind).strip() == "translated":
        return project_root / config.TRANSLATED_CHUNKS_FILE_NAME
    return project_root / config.CHUNK_ARTIFACT_FILE_NAME


def _build_source_fingerprint(source_chunks: list[dict[str, object]], source_language: str, source_kind: str) -> str:
    """
    @brief      Build one stable fingerprint for the Speech Blocks source snapshot.
    @param[in]  source_chunks Source snapshot payload list.
    @param[in]  source_language Active source language code.
    @param[in]  source_kind Active source-kind token.
    @return     Hex-encoded fingerprint string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
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
    profile_id: str,
    source_language: str,
) -> tuple[list[SpeechBlockPayload], list[dict[str, object]], int]:
    """
    @brief      Restore resumable Speech Blocks state when the persisted checkpoint is still valid.
    @param[in]  project_root Active project root folder.
    @param[in]  existing_state Existing operation-state payload.
    @param[in]  input_fingerprint Current source snapshot fingerprint.
    @param[in]  profile_id Active AI profile identifier.
    @param[in]  source_language Active source language code.
    @return     Existing blocks, warning entries, and the next chunk index.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not isinstance(existing_state, dict):
        return [], [], 0
    if str(existing_state.get("status", "")).strip() not in {"running", "failed"}:
        return [], [], 0
    metadata = existing_state.get("metadata", {})
    resume_checkpoint = existing_state.get("resume_checkpoint", {})
    if not isinstance(metadata, dict) or not isinstance(resume_checkpoint, dict):
        return [], [], 0
    if str(metadata.get("source_snapshot_fingerprint", "")).strip() != input_fingerprint:
        return [], [], 0
    if str(metadata.get("ai_profile_id", "")).strip() != profile_id:
        return [], [], 0
    if str(metadata.get("source_language", "")).strip() != source_language:
        return [], [], 0
    next_chunk_index = int(resume_checkpoint.get("next_chunk_index", 0))
    warnings = metadata.get("warnings", [])
    return (
        load_speech_blocks(project_root),
        [dict(item) for item in warnings if isinstance(item, dict)],
        max(next_chunk_index, 0),
    )


def _resolve_started_at(existing_state: dict[str, object]) -> str:
    """
    @brief      Resolve the stable operation start timestamp for one run.
    @param[in]  existing_state Existing operation-state payload.
    @return     Stable operation start timestamp.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    started_at = str(existing_state.get("started_at", "")).strip() if isinstance(existing_state, dict) else ""
    return started_at or _utc_now_iso()


def _resolve_log_path(project_root: Path, started_at: str) -> Path:
    """
    @brief      Resolve or create the AI transaction log path for Speech Blocks.
    @param[in]  project_root Active project root folder.
    @param[in]  started_at Stable operation start timestamp.
    @return     Operation-local AI transaction log path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not isinstance(existing_state, dict):
        return None
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return None
    payload = metadata.get("token_usage")
    return payload if isinstance(payload, dict) else None


def _emit_progress(
    progress_callback,
    progress_current: int,
    progress_total: int,
    message: str,
    token_usage: dict[str, object] | None = None,
) -> None:
    """
    @brief      Emit one Speech Blocks progress update.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  progress_current Completed work-unit count.
    @param[in]  progress_total Total work-unit count.
    @param[in]  message Operator-facing progress text.
    @param[in]  token_usage Current token-usage payload.
    @return     None.
    @exception  None
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


def _utc_now_iso() -> str:
    """
    @brief      Build one current UTC timestamp in stable ISO-8601 format.
    @return     UTC timestamp string without microseconds.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# END OF FILE
