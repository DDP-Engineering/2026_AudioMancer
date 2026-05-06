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
@version 0.15.0
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
    character_voices_service,
    deterministic_chunking_service,
    llm_provider_service,
    narrator_definition_service,
    project_workspace_service,
    prompt_template_service,
    speech_blocks_normalization_service,
    speech_blocks_report_state_service,
    speech_blocks_text_split_service,
    token_usage_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    build_operation_output_path,
    load_operation_state_payload,
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
    is_missing_runtime_value as _is_missing_runtime_value,
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
CONTENT_KIND_BACKGROUND_NOISE = speech_blocks_normalization_service.CONTENT_KIND_BACKGROUND_NOISE
CONTENT_KIND_PAUSE = speech_blocks_normalization_service.CONTENT_KIND_PAUSE
CONTENT_KIND_INDICATION = speech_blocks_normalization_service.CONTENT_KIND_INDICATION

SPEECH_BLOCK_CONTENT_KINDS = speech_blocks_normalization_service.SPEECH_BLOCK_CONTENT_KINDS

_NARRATOR_SPEAKER_ID = speech_blocks_normalization_service.NARRATOR_SPEAKER_ID
_NARRATOR_DISPLAY_NAME = speech_blocks_normalization_service.NARRATOR_DISPLAY_NAME
_append_warning_flag = speech_blocks_normalization_service.append_warning_flag
_approved_block_count = speech_blocks_report_state_service.approved_block_count
_block_text_key = speech_blocks_normalization_service.block_text_key
_build_speech_block_payload = speech_blocks_normalization_service.build_speech_block_payload
_build_operation_state = speech_blocks_report_state_service.build_operation_state
_chunk_order_from_id = speech_blocks_normalization_service.chunk_order_from_id
_is_operation_content_kind = speech_blocks_normalization_service.is_operation_content_kind
_hard_split_text_by_characters = speech_blocks_normalization_service.hard_split_text_by_characters
_hard_split_text_for_tts_budget = speech_blocks_normalization_service.hard_split_text_for_tts_budget
_normalize_ai_block = speech_blocks_normalization_service.normalize_ai_block
_normalize_block_text = speech_blocks_normalization_service.normalize_block_text
_normalize_chunk_blocks = speech_blocks_normalization_service.normalize_chunk_blocks
_normalize_content_kind = speech_blocks_normalization_service.normalize_content_kind
_normalize_warning_flags = speech_blocks_normalization_service.normalize_warning_flags
_operation_display_name = speech_blocks_normalization_service.operation_display_name
_operation_speaker_entry = speech_blocks_normalization_service.operation_speaker_entry
_pack_tts_split_parts = speech_blocks_normalization_service.pack_tts_split_parts
_rebuild_report = speech_blocks_report_state_service.rebuild_report
_resolve_narrator_only_budget = speech_blocks_normalization_service.resolve_narrator_only_budget
_resolve_speaker_entry = speech_blocks_normalization_service.resolve_speaker_entry
_safe_tts_word_count = speech_blocks_normalization_service.safe_tts_word_count
_source_chunks_input_path = speech_blocks_report_state_service.source_chunks_input_path
_speaker_match_key = speech_blocks_normalization_service.speaker_match_key
_split_over_budget_ai_blocks = speech_blocks_normalization_service.split_over_budget_ai_blocks
_split_paragraph_spans = speech_blocks_normalization_service.split_paragraph_spans
_split_sentence_spans = speech_blocks_normalization_service.split_sentence_spans
_split_text_for_tts_budget = speech_blocks_normalization_service.split_text_for_tts_budget
_speech_block_id = speech_blocks_normalization_service.speech_block_id
_speech_block_warning_reason = speech_blocks_normalization_service.speech_block_warning_reason
_tts_budget_unit_count = speech_blocks_normalization_service.tts_budget_unit_count
_validate_ai_block_source_spans = speech_blocks_normalization_service.validate_ai_block_source_spans
_validate_narrator_only_budget = speech_blocks_normalization_service.validate_narrator_only_budget
_warning_records_from_blocks = speech_blocks_report_state_service.warning_records_from_blocks
_ai_paragraph_spans = speech_blocks_text_split_service.ai_paragraph_spans
_ai_sentence_spans = speech_blocks_text_split_service.ai_sentence_spans
_ai_word_spans = speech_blocks_text_split_service.ai_word_spans
_hard_split_text_for_ai_context_budget = speech_blocks_text_split_service.hard_split_text_for_ai_context_budget
_split_text_for_ai_context_budget = speech_blocks_text_split_service.split_text_for_ai_context_budget

SpeechBlockPayload = dict[str, object]
SpeechBlocksReportPayload = dict[str, object]
OperationStatePayload = dict[str, object]
TokenUsagePayload = dict[str, object]
BudgetMetadataPayload = dict[str, int]


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
    @version    0.4.0
    """
    return load_operation_state_payload(project_root, "speech_blocks", config.SPEECH_BLOCKS_STATE_FILE_NAME)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def load_speech_blocks_report(project_root: str | Path) -> SpeechBlocksReportPayload | None:
    """
    @brief      Load one optional Speech Blocks report payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted report payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
    """
    report_path = resolve_operation_path(project_root, "speech_blocks", config.SPEECH_BLOCKS_REPORT_FILE_NAME)
    payload = load_optional_json_artifact(report_path)
    if payload is None:
        return None
    return dict(payload)


@trace_function(_SPEECH_BLOCKS_LOGGER)
def load_input_source_chunks(project_root: str | Path) -> list[dict[str, object]]:
    """
    @brief      Load one optional Speech Blocks source payload from operation state.
    @param[in]  project_root Active project root folder.
    @return     Ordered source-chunk snapshot payloads.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.1
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
    @version    0.2.0
    """
    output_path = resolve_operation_path(project_root, "speech_blocks", config.SPEECH_BLOCKS_OUTPUT_FILE_NAME)
    payload = load_optional_json_artifact(output_path)
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
    @version    0.1.1
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
    settings_payload: dict[str, object] | None = None,
    progress_callback=None,
    cancel_requested=None,
) -> SpeechBlocksReportPayload:
    """
    @brief      Run Speech Blocks generation for the active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  settings_payload Optional application settings payload for cached TTS model budgets.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Final Speech Blocks report payload.
    @exception  ValueError Raised when prerequisites or profile data are invalid.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
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
    voice_assignment_mode = _voice_assignment_mode(manifest)
    prompt_names = _prompt_names_for_mode(voice_assignment_mode)
    prompt_template_service.validate_required_prompts(list(prompt_names))
    tts_budget = _resolve_narrator_only_budget(settings_payload)

    speaker_catalog = _speaker_catalog(character_discovery_service.load_character_profiles(resolved_project_root))
    system_prompt = prompt_template_service.render_prompt(prompt_names[0], {})
    budget_metadata = _build_budget_metadata(
        ai_profile_payload,
        system_prompt,
        prompt_names[1],
        source_language,
        speaker_catalog,
        voice_assignment_mode,
        tts_budget,
    )
    input_fingerprint = _build_source_fingerprint(source_chunks, source_language, source_kind)
    existing_state = load_operation_state(resolved_project_root) or {}
    existing_report = load_speech_blocks_report(resolved_project_root)
    started_at = _resolve_started_at(existing_state)
    log_path = _resolve_log_path(resolved_project_root, started_at)
    existing_blocks, warning_records, start_chunk_index = _restore_resume_state(
        resolved_project_root,
        existing_state,
        input_fingerprint,
        source_language,
    )
    token_usage = (
        token_usage_service.restore_token_usage(
            None if existing_report is None else existing_report.get("token_usage"),
            _metadata_token_usage(existing_state),
        )
        if start_chunk_index > 0 or existing_blocks
        else token_usage_service.empty_token_usage()
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
            budget_metadata,
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
            budget_metadata=budget_metadata,
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
    warning_entries = list(warning_records)
    for chunk_index in range(start_chunk_index, len(source_chunks)):
        raise_if_cancelled(cancel_requested)
        source_chunk = dict(source_chunks[chunk_index])
        chunk_blocks, chunk_warnings, chunk_token_usage = _generate_budgeted_chunk_blocks(
            ai_profile_payload,
            system_prompt,
            source_chunk,
            source_language,
            speaker_catalog,
            voice_assignment_mode,
            tts_budget,
            prompt_names[1],
            budget_metadata,
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
        )
        token_usage = token_usage_service.merge_token_usage(token_usage, chunk_token_usage)
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
            budget_metadata,
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
                budget_metadata=budget_metadata,
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
        budget_metadata,
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
            budget_metadata=budget_metadata,
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
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
def mark_speech_blocks_for_character_review(
    project_root: str | Path,
    character_id: str,
    display_name: str | None = None,
) -> tuple[SpeechBlocksReportPayload | None, tuple[str, ...]]:
    """
    @brief      Mark Speech Blocks assigned to one character as needing review.
    @param[in]  project_root Active project root folder.
    @param[in]  character_id Character identifier whose assignments changed.
    @param[in]  display_name Optional refreshed speaker display name.
    @return     Updated report, if Speech Blocks existed, plus affected block ids.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    normalized_character_id = str(character_id).strip()
    if not normalized_character_id:
        return load_speech_blocks_report(project_root), ()
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    if not speech_blocks:
        return load_speech_blocks_report(resolved_project_root), ()
    normalized_display_name = None if display_name is None else str(display_name).strip()
    affected_block_ids: list[str] = []
    updated_blocks: list[SpeechBlockPayload] = []
    for block in speech_blocks:
        updated_block = dict(block)
        if _is_character_speech_block(updated_block, normalized_character_id):
            affected_block_ids.append(str(updated_block.get("speech_block_id", "")).strip())
            updated_block["approved"] = False
            updated_block["approved_at"] = None
            if normalized_display_name:
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
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
    @version    0.2.0
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
    inserted_id = _next_unused_speech_block_id(selected_chunk_id, _used_speech_block_ids(speech_blocks))
    speech_blocks.append(_manual_inserted_speech_block(selected_chunk_id, insertion_index, inserted_id))
    updated_report = _persist_report_update(resolved_project_root, speech_blocks)
    inserted_block = _speech_block_by_id(load_speech_blocks(resolved_project_root), inserted_id)
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
    @version    0.2.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    selected_block = _speech_block_by_id(speech_blocks, speech_block_id)
    if selected_block is None:
        raise ValueError("The selected Speech Block was not found.")
    selected_block["warning_flags"] = []
    return _persist_report_update(resolved_project_root, speech_blocks)


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
def unapprove_speech_block(project_root: str | Path, speech_block_id: str) -> SpeechBlocksReportPayload:
    """
    @brief      Clear approval for one generated Speech Block.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Target Speech Block identifier.
    @return     Updated Speech Blocks report payload.
    @exception  ValueError Raised when the block is unknown.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-05
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    selected_block = _speech_block_by_id(speech_blocks, speech_block_id)
    if selected_block is None:
        raise ValueError("The selected Speech Block was not found.")
    selected_block["approved"] = False
    selected_block["approved_at"] = None
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
    @version    0.3.0
    """
    resolved_project_root = Path(project_root)
    speech_blocks = load_speech_blocks(resolved_project_root)
    selected_block = _speech_block_by_id(speech_blocks, speech_block_id)
    if selected_block is None:
        raise ValueError("The selected Speech Block was not found.")
    normalized_content_kind = _normalize_content_kind(content_kind)
    manifest = project_workspace_service.load_manifest(resolved_project_root)
    narrator_only = _voice_assignment_mode(manifest) == "same_narrator"
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
    selected_block["content_kind"] = normalized_content_kind
    selected_block["text"] = str(text)
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
    @return     Updated Speech Blocks report payload.
    @exception  ValueError Raised when prerequisites or target chunk are invalid.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.0
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
    voice_assignment_mode = _voice_assignment_mode(manifest)
    prompt_names = _prompt_names_for_mode(voice_assignment_mode)
    tts_budget = _resolve_narrator_only_budget(settings_payload)
    selected_chunk = next(
        (chunk for chunk in source_chunks if str(chunk.get("chunk_id", "")).strip() == chunk_id),
        None,
    )
    if selected_chunk is None:
        raise ValueError("The selected chunk was not found.")
    prompt_template_service.validate_required_prompts(list(prompt_names))
    existing_report = load_speech_blocks_report(resolved_project_root)
    existing_state = load_operation_state(resolved_project_root) or {}
    token_usage = token_usage_service.restore_token_usage(
        None if existing_report is None else existing_report.get("token_usage"),
        _metadata_token_usage(existing_state),
    )
    started_at = _resolve_started_at(existing_state)
    log_path = _resolve_log_path(resolved_project_root, started_at)
    speaker_catalog = _speaker_catalog(character_discovery_service.load_character_profiles(resolved_project_root))
    system_prompt = prompt_template_service.render_prompt(prompt_names[0], {})
    budget_metadata = _build_budget_metadata(
        ai_profile_payload,
        system_prompt,
        prompt_names[1],
        source_language,
        speaker_catalog,
        voice_assignment_mode,
        tts_budget,
    )
    raise_if_cancelled(cancel_requested)
    new_blocks, _chunk_warnings, chunk_token_usage = _generate_budgeted_chunk_blocks(
        ai_profile_payload,
        system_prompt,
        dict(selected_chunk),
        source_language,
        speaker_catalog,
        voice_assignment_mode,
        tts_budget,
        prompt_names[1],
        budget_metadata,
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
    existing_blocks = [
        block
        for block in load_speech_blocks(resolved_project_root)
        if str(block.get("chunk_id", "")).strip() != chunk_id
    ]
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
        budget_metadata,
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
            budget_metadata=budget_metadata,
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


def _voice_assignment_mode(manifest: dict[str, object]) -> str:
    """
    @brief      Resolve the active Speech Blocks generation mode.
    @param[in]  manifest Active project manifest payload.
    @return     Supported voice-assignment mode.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    mode = str(manifest.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)).strip()
    if mode in config.TTS_VOICE_ASSIGNMENT_MODE_OPTIONS:
        return mode
    return config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE


def _prompt_names_for_mode(voice_assignment_mode: str) -> tuple[str, str]:
    """
    @brief      Resolve the Speech Blocks prompt pair for one narration mode.
    @param[in]  voice_assignment_mode Active project voice-assignment mode.
    @return     `(system_prompt_name, user_prompt_name)`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    if str(voice_assignment_mode).strip() == "same_narrator":
        return "speech_blocks_narrator_only_system", "speech_blocks_narrator_only_user"
    return "speech_blocks_system", "speech_blocks_user"


def _chunk_user_prompt(
    source_chunk: dict[str, object],
    source_language: str,
    speaker_catalog: dict[str, dict[str, object]],
    voice_assignment_mode: str = config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
    tts_budget: dict[str, object] | None = None,
    prompt_name: str = "speech_blocks_user",
) -> str:
    """
    @brief      Render the chunk-specific Speech Blocks user prompt.
    @param[in]  source_chunk Source chunk payload.
    @param[in]  source_language Active source language code.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  voice_assignment_mode Active project voice-assignment mode.
    @param[in]  tts_budget Optional narrator-only TTS budget metadata.
    @param[in]  prompt_name Prompt template name.
    @return     Rendered prompt text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.0
    """
    budget_payload = tts_budget or _resolve_narrator_only_budget(None)
    return prompt_template_service.render_prompt(
        prompt_name,
        {
            "source_language": narrator_definition_service.narrator_language_label(source_language),
            "chunk_id": str(source_chunk.get("chunk_id", "")),
            "chunk_text": str(source_chunk.get("text", "")),
            "speaker_catalog_json": json.dumps(list(speaker_catalog.values()), indent=2, ensure_ascii=False),
            "voice_assignment_mode": voice_assignment_mode,
            "max_tts_tokens": str(int(budget_payload.get("model_token_budget", 0))),
            "safe_tts_words": str(int(budget_payload.get("safe_word_count", 0))),
            "tts_budget_source": str(budget_payload.get("model_budget_source", "")),
        },
    )


def _build_budget_metadata(
    ai_profile_payload: dict[str, object],
    system_prompt: str,
    prompt_name: str,
    source_language: str,
    speaker_catalog: dict[str, dict[str, object]],
    voice_assignment_mode: str,
    tts_budget: dict[str, object] | None,
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
    @return     Context-budget metadata used for source chunk segmentation.
    @exception  ValueError Raised when context and output settings leave too little input room.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    prompt_shell = _chunk_user_prompt(
        {"chunk_id": "", "text": ""},
        source_language,
        speaker_catalog,
        voice_assignment_mode,
        tts_budget,
        prompt_name,
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
    log_path: Path,
    log_context: dict[str, object],
    cancel_requested,
    cancellation_message: str,
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
    @param[in]  log_path Operation-local AI transaction log path.
    @param[in]  log_context Base AI transaction log context.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  cancellation_message Message used when the request is cancelled.
    @return     Generated Speech Blocks, warning entries, and provider token usage for this chunk.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    chunk_segments = _budgeted_source_chunk_segments(source_chunk, budget_metadata)
    combined_blocks: list[SpeechBlockPayload] = []
    combined_warnings: list[dict[str, object]] = []
    chunk_token_usage = token_usage_service.empty_token_usage()
    for segment_index, segment_chunk in enumerate(chunk_segments, start=1):
        user_prompt = _chunk_user_prompt(
            segment_chunk,
            source_language,
            speaker_catalog,
            voice_assignment_mode,
            tts_budget,
            prompt_name,
        )
        try:
            response_result = llm_provider_service.chat_json(
                ai_profile_payload,
                system_prompt,
                user_prompt,
                log_path=log_path,
                log_context={
                    **dict(log_context),
                    "segment_index": segment_index,
                    "segment_total": len(chunk_segments),
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
        combined_warnings.extend(segment_warnings)
    return (
        _renumber_single_chunk_blocks(str(source_chunk.get("chunk_id", "")).strip(), combined_blocks),
        combined_warnings,
        chunk_token_usage,
    )


def _budgeted_source_chunk_segments(
    source_chunk: dict[str, object],
    budget_metadata: BudgetMetadataPayload,
) -> list[dict[str, object]]:
    """
    @brief      Split one source chunk into AI-context-budgeted request segment payloads.
    @param[in]  source_chunk Full source chunk payload.
    @param[in]  budget_metadata Context-budget metadata.
    @return     Ordered source chunk segment payloads using the original chunk id.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    text_budget_tokens = int(budget_metadata["text_budget_tokens"])
    source_text = str(source_chunk.get("text", ""))
    text_segments = _split_text_for_ai_context_budget(source_text, text_budget_tokens)
    if not text_segments:
        return [dict(source_chunk)]
    return [{**dict(source_chunk), "text": text_segment} for text_segment in text_segments]


def _estimate_text_tokens(text: str) -> int:
    """
    @brief      Estimate token usage for local budget checks.
    @param[in]  text Value for `text`.
    @return     Estimated token count.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.1
    """
    return ai_budget_service.estimate_text_tokens(text)


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
    return {
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
    @version    0.3.0
    """
    _ = source_chunks
    write_operation_json_artifact(project_root, "speech_blocks", config.SPEECH_BLOCKS_OUTPUT_FILE_NAME, speech_blocks)
    write_operation_json_artifact(project_root, "speech_blocks", config.SPEECH_BLOCKS_REPORT_FILE_NAME, report)
    write_operation_json_artifact(project_root, "speech_blocks", config.SPEECH_BLOCKS_STATE_FILE_NAME, operation_state)


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
    @version    0.2.0
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
    budget_metadata = _restore_persisted_budget_metadata(report, operation_state)
    input_fingerprint = str(metadata.get("source_snapshot_fingerprint", "")).strip()
    if not input_fingerprint and source_chunks and source_language and source_kind:
        input_fingerprint = _build_source_fingerprint(source_chunks, source_language, source_kind)
    started_at = _valid_runtime_value(operation_state.get("started_at") if isinstance(operation_state, dict) else "")
    started_at = started_at or _utc_now_iso()
    completed_at_value = operation_state.get("completed_at") if isinstance(operation_state, dict) else ""
    completed_at = _valid_runtime_value(completed_at_value)
    completed_at = completed_at or _utc_now_iso()
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
        budget_metadata,
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
            budget_metadata=budget_metadata,
        ),
    )
    return updated_report


def _is_character_speech_block(block: SpeechBlockPayload, character_id: str) -> bool:
    """
    @brief      Return whether one Speech Block is assigned to the selected character speaker.
    @param[in]  block Speech Block payload.
    @param[in]  character_id Character identifier to match.
    @return     True when the block currently uses that character as speaker.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.0
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
        renumbered_block.pop("chunk_sequence_index", None)
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.2.0
    """
    normalized_chunk_id = str(chunk_id).strip()
    renumbered_blocks: list[SpeechBlockPayload] = []
    used_ids: set[str] = set()
    for sequence_index, block in enumerate(speech_blocks, start=1):
        renumbered_block = dict(block)
        renumbered_block["sequence_index"] = sequence_index
        renumbered_block.pop("chunk_sequence_index", None)
        renumbered_block["chunk_id"] = normalized_chunk_id
        renumbered_block["speech_block_id"] = _stable_speech_block_id(renumbered_block, normalized_chunk_id, used_ids)
        renumbered_blocks.append(renumbered_block)
    return renumbered_blocks


def _stable_speech_block_id(block: SpeechBlockPayload, chunk_id: str, used_ids: set[str]) -> str:
    """
    @brief      Preserve one existing Speech Block id or allocate a new stable id.
    @param[in]  block Speech Block payload being renumbered.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  used_ids Speech Block ids already emitted in this renumbering pass.
    @return     Stable Speech Block identifier.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    return {
        str(block.get("speech_block_id", "")).strip()
        for block in speech_blocks
        if str(block.get("speech_block_id", "")).strip()
    }


def _next_unused_speech_block_id(chunk_id: str, used_ids: set[str]) -> str:
    """
    @brief      Allocate the next chunk-local Speech Block id without reusing historical ids.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  used_ids Speech Block ids already present or emitted.
    @return     Unused Speech Block identifier.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
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
    @version    0.2.0
    """
    return next(
        (
            block
            for block in speech_blocks
            if str(block.get("chunk_id", "")).strip() == chunk_id
            and int(block.get("sequence_index", 0)) == insertion_index
            and str(block.get("text", "")) == ""
            and str(block.get("source_text", "")) == ""
            and str(block.get("speaker_id", "")).strip() == _NARRATOR_SPEAKER_ID
            and str(block.get("content_kind", "")).strip() == CONTENT_KIND_NARRATION
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
    source_language: str,
) -> tuple[list[SpeechBlockPayload], list[dict[str, object]], int]:
    """
    @brief      Restore resumable Speech Blocks state when the persisted checkpoint is still valid.
    @param[in]  project_root Active project root folder.
    @param[in]  existing_state Existing operation-state payload.
    @param[in]  input_fingerprint Current source snapshot fingerprint.
    @param[in]  source_language Active source language code.
    @return     Existing blocks, warning entries, and the next chunk index.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
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
    @version    0.2.0
    """
    started_at = _valid_runtime_value(existing_state.get("started_at") if isinstance(existing_state, dict) else "")
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
    @version    0.2.0
    """
    existing_state = load_operation_state(project_root) or {}
    for artifact_path in list(existing_state.get("artifact_paths", [])):
        relative_path = str(artifact_path)
        if Path(relative_path).name.startswith(config.AI_TRANSACTION_LOG_FILE_PREFIX):
            if any(_is_missing_runtime_value(part) for part in Path(relative_path).stem.split("_")):
                continue
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
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
