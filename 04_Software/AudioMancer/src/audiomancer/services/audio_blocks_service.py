#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audio_blocks_service.py
@brief Resumable Audio Blocks generation helpers for AudioMancer.
@details Validates the persisted Speech Blocks plus narrator and character
         sample inputs, prepares reusable client-owned voice clone prompts,
         generates one WAV per speech block through the documented VoiceWeaver
         clone-from-prompt endpoint, and persists resumable approval-aware
         `80_audio_blocks` workflow artifacts.
"""

# IMPORTS

import hashlib
import json
from math import ceil
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import (
    audio_blocks_artifact_service,
    character_voices_service,
    narrator_definition_service,
    operation_runtime_service,
    project_workspace_service,
    speech_blocks_service,
    tts_budget_service,
    voiceweaver_runtime_service,
    workflow_impact_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    build_operation_state_payload,
    load_optional_json_artifact,
    raise_if_cancelled,
    relative_to_project,
    resolve_operation_path,
    write_operation_json_artifact,
)
from audiomancer.services.operation_runtime_service import (
    emit_progress_update as _emit_progress,
)
from audiomancer.services.operation_runtime_service import (
    optional_string as _optional_string,
)
from audiomancer.services.persistence_service import write_bytes_atomic
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

_AUDIO_BLOCKS_LOGGER = get_component_logger("audio_blocks")

AUDIO_BLOCKS_STAGE_NOT_STARTED = "not_started"
AUDIO_BLOCKS_STAGE_IN_PROGRESS = "in_progress"
AUDIO_BLOCKS_STAGE_COMPLETED = "completed"

_PROFILE_PHASE = "prepare_prompts"
_GENERATE_PHASE = "generate_blocks"
_MODE = "tts_generation"
_PREFERRED_QWEN_CLONE_MODEL_ID = "Qwen3-TTS-12Hz-1.7B-Base"
_DEFAULT_APPROX_AUDIO_SECONDS_PER_TOKEN = config.DEFAULT_TTS_APPROX_AUDIO_SECONDS_PER_TOKEN
_SPLIT_SAFETY_FACTOR = config.DEFAULT_TTS_SPLIT_SAFETY_FACTOR
_WORDS_PER_AUDIO_SECOND = config.DEFAULT_TTS_WORDS_PER_AUDIO_SECOND
_AUDIO_BLOCK_FINGERPRINT_VERSION = 2
_SPECIAL_BLOCK_STATUS_IMPLEMENTED = "implemented"
_SPECIAL_BLOCK_STATUS_NOT_IMPLEMENTED = "not_implemented"

# @brief Fixed root field set of the authoritative single Audio Blocks document.
_DOCUMENT_FIELDS = frozenset(
    (
        "status",
        "voice_language",
        "input_fingerprint",
        "checkpoint",
        "blocks",
    )
)

# @brief Persisted status tokens accepted by the single Audio Blocks document.
_DOCUMENT_STATUSES = frozenset(
    (
        AUDIO_BLOCKS_STAGE_NOT_STARTED,
        "running",
        AUDIO_BLOCKS_STAGE_IN_PROGRESS,
        "cancelled",
        "failed",
        AUDIO_BLOCKS_STAGE_COMPLETED,
    )
)

# @brief Required per-block field set inside the single Audio Blocks document.
_BLOCK_FIELDS = frozenset(
    (
        "speech_block_id",
        "voice_target_id",
        "generated",
        "approved",
        "audio_can_play",
        "audio_duration_seconds",
        "generation_fingerprint",
    )
)

# @brief Per-block fields persisted only when the block was actually split.
_SPLIT_BLOCK_FIELDS = frozenset(("split_part_count", "split_plan_fingerprint"))

# @brief Legacy Audio Blocks sidecars removed by the single-document consolidation.
_audio_artifact_file_stem = audio_blocks_artifact_service.audio_artifact_file_stem
_audio_artifact_path = audio_blocks_artifact_service.audio_artifact_path
_audio_part_artifact_path = audio_blocks_artifact_service.audio_part_artifact_path
_generated_audio_root = audio_blocks_artifact_service.generated_audio_root
_is_valid_wav_path = audio_blocks_artifact_service.is_valid_wav_path
_stitch_wav_parts = audio_blocks_artifact_service.stitch_wav_parts
_validate_wav_bytes = audio_blocks_artifact_service.validate_wav_bytes
_wav_duration_seconds = audio_blocks_artifact_service.wav_duration_seconds
normalize_speaker_name = audio_blocks_artifact_service.normalize_speaker_name

AudioBlockPayload = dict[str, object]
AudioBlocksReportPayload = dict[str, object]
AudioBlocksDocumentPayload = dict[str, object]
OperationStatePayload = dict[str, object]
VoiceCloneProfilePayload = dict[str, object]


# DATA MODELS / TYPEDEFINITIONS


class AudioBlocksDocumentError(ValueError):
    """
    @brief      Raised when the authoritative single Audio Blocks document is invalid.
    """


def _validate_audio_blocks_document(payload: object) -> None:
    """
    @brief      Validate the strict, hard-break single Audio Blocks document contract.
    @param[in]  payload Candidate document payload.
    @return     None.
    @exception  AudioBlocksDocumentError Raised when the payload violates the contract.
    """
    if not isinstance(payload, dict) or set(payload) != set(_DOCUMENT_FIELDS):
        raise AudioBlocksDocumentError("Audio Blocks data has an incompatible root contract.")
    if str(payload.get("status", "")) not in _DOCUMENT_STATUSES:
        raise AudioBlocksDocumentError("Audio Blocks data has an invalid status.")
    if not isinstance(payload.get("voice_language"), str):
        raise AudioBlocksDocumentError("Audio Blocks voice_language must be a string.")
    if not isinstance(payload.get("input_fingerprint"), str):
        raise AudioBlocksDocumentError("Audio Blocks input_fingerprint must be a string.")
    checkpoint = payload.get("checkpoint")
    if checkpoint is not None and not isinstance(checkpoint, dict):
        raise AudioBlocksDocumentError("Audio Blocks checkpoint must be null or an object.")
    blocks = payload.get("blocks")
    if not isinstance(blocks, list):
        raise AudioBlocksDocumentError("Audio Blocks blocks must be an array.")
    for block in blocks:
        if not isinstance(block, dict):
            raise AudioBlocksDocumentError("Every Audio Blocks entry must be an object.")
        block_fields = set(block)
        if not set(_BLOCK_FIELDS).issubset(block_fields):
            raise AudioBlocksDocumentError("An Audio Blocks entry is missing contracted fields.")
        if not block_fields.issubset(set(_BLOCK_FIELDS) | set(_SPLIT_BLOCK_FIELDS)):
            raise AudioBlocksDocumentError("An Audio Blocks entry carries fields outside the contract.")


# PUBLIC API


@trace_function(_AUDIO_BLOCKS_LOGGER)
def load_audio_blocks_document(project_root: str | Path) -> AudioBlocksDocumentPayload | None:
    """
    @brief      Load and strictly validate the authoritative single Audio Blocks document.
    @details    A missing file reads as not-started. Every existing unreadable,
                legacy, or contract-invalid document requires explicit reset.
                No legacy report or state artifact is consulted.
    @param[in]  project_root Active project root folder.
    @return     Document payload, or `None` when the optional document is missing.
    @exception  AudioBlocksDocumentError Raised when an existing document is unreadable or invalid.
    """
    document_path = resolve_operation_path(project_root, "audio_blocks", config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME)
    document_exists = document_path.exists()
    try:
        payload = load_optional_json_artifact(document_path)
    except (OSError, ValueError) as error:
        raise AudioBlocksDocumentError(
            f"Audio Blocks data is unreadable. Reset Audio Blocks to recover: {error}"
        ) from error
    if payload is None and not document_exists:
        return None
    try:
        _validate_audio_blocks_document(payload)
    except AudioBlocksDocumentError as error:
        raise AudioBlocksDocumentError(
            f"Audio Blocks data is invalid. Reset Audio Blocks to recover: {error}"
        ) from error
    assert isinstance(payload, dict)
    return dict(payload)


def write_audio_blocks_document(
    project_root: str | Path,
    document: AudioBlocksDocumentPayload,
) -> Path:
    """
    @brief      Strictly validate and atomically persist the single Audio Blocks document.
    @param[in]  project_root Active project root folder.
    @param[in]  document Complete Audio Blocks document payload.
    @return     Absolute project-local document path.
    @exception  AudioBlocksDocumentError Raised when the document violates the contract.
    """
    _validate_audio_blocks_document(document)
    write_operation_json_artifact(
        project_root,
        "audio_blocks",
        config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME,
        document,
    )
    return resolve_operation_path(project_root, "audio_blocks", config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Project the Audio Blocks operation state from the single document.
    @param[in]  project_root Active project root folder.
    @return     Projected operation-state payload or `None` when not started.
    @exception  AudioBlocksDocumentError Raised when the authoritative document exists but is unreadable or invalid.
    """
    document = load_audio_blocks_document(project_root)
    if document is None:
        return None
    return _project_operation_state(project_root, document)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def load_audio_blocks_report(project_root: str | Path) -> AudioBlocksReportPayload | None:
    """
    @brief      Project the Audio Blocks report from the single document.
    @param[in]  project_root Active project root folder.
    @return     Projected report payload or `None` when not started.
    @exception  AudioBlocksDocumentError Raised when the authoritative document exists but is unreadable or invalid.
    """
    document = load_audio_blocks_document(project_root)
    if document is None:
        return None
    return _project_audio_blocks_report(project_root, document)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def load_audio_blocks(project_root: str | Path) -> list[AudioBlockPayload]:
    """
    @brief      Load the persisted Audio Blocks entries from the single document.
    @param[in]  project_root Active project root folder.
    @return     Ordered Audio Blocks payload list.
    @exception  AudioBlocksDocumentError Raised when the authoritative document exists but is unreadable or invalid.
    """
    document = load_audio_blocks_document(project_root)
    if document is None:
        return []
    audio_blocks = [
        _normalize_persisted_audio_block(item) for item in document.get("blocks", []) if isinstance(item, dict)
    ]
    enriched_blocks = _attach_current_speech_block_fields(Path(project_root), audio_blocks)
    return speech_blocks_service.sort_speech_blocks(
        [_attach_derived_audio_path(Path(project_root), block) for block in enriched_blocks]
    )


@trace_function(_AUDIO_BLOCKS_LOGGER)
def reconcile_audio_playability(project_root: str | Path) -> bool:
    """
    @brief      Refresh persisted Audio Blocks playability flags from current project-local files.
    @param[in]  project_root Active project root folder.
    @return     True when the Audio Blocks artifact was updated.
    @exception  None
    """
    resolved_project_root = Path(project_root)
    audio_blocks = load_audio_blocks(resolved_project_root)
    if not audio_blocks:
        return False
    changed = False
    reconciled_blocks: list[AudioBlockPayload] = []
    for audio_block in audio_blocks:
        reconciled_block = dict(audio_block)
        audio_can_play = _filesystem_audio_can_play(resolved_project_root, reconciled_block)
        if bool(reconciled_block.get("audio_can_play", False)) != audio_can_play:
            reconciled_block["audio_can_play"] = audio_can_play
            changed = True
        reconciled_blocks.append(reconciled_block)
    if not changed:
        return False
    _persist_report_update(resolved_project_root, reconciled_blocks)
    return True


def is_generated(audio_block: dict[str, object]) -> bool:
    """
    @brief      Return whether one Audio Blocks entry has generated output.
    @param[in]  audio_block Audio Blocks payload.
    @return     True when the entry is flagged generated.
    @exception  None
    """
    return bool(audio_block.get("generated", False))


def audio_can_play(audio_block: dict[str, object]) -> bool:
    """
    @brief      Return the persisted playability flag for one Audio Blocks entry.
    @param[in]  audio_block Audio Blocks payload.
    @return     True when the entry is marked playable without filesystem probing.
    @exception  None
    """
    if bool(audio_block.get("metadata_only", False)):
        return is_generated(audio_block) and str(audio_block.get("content_kind", "")).strip() == (
            speech_blocks_service.CONTENT_KIND_PAUSE
        )
    return _persisted_audio_can_play(audio_block)


def audio_can_regenerate(audio_block: dict[str, object]) -> bool:
    """
    @brief      Return whether one Audio Blocks entry supports selected regeneration.
    @param[in]  audio_block Audio Blocks payload.
    @return     False for metadata-only pause and indication rows; otherwise True.
    @exception  None
    """
    content_kind = str(audio_block.get("content_kind", "")).strip()
    return not (
        bool(audio_block.get("metadata_only", False))
        and content_kind
        in {
            speech_blocks_service.CONTENT_KIND_PAUSE,
            speech_blocks_service.CONTENT_KIND_INDICATION,
        }
    )


def is_approved(audio_block: dict[str, object]) -> bool:
    """
    @brief      Return whether one Audio Blocks entry is approved.
    @param[in]  audio_block Audio Blocks payload.
    @return     True when the entry is flagged approved.
    @exception  None
    """
    return bool(audio_block.get("approved", False))


@trace_function(_AUDIO_BLOCKS_LOGGER)
def load_voice_clone_profiles(project_root: str | Path) -> list[VoiceCloneProfilePayload]:
    """
    @brief      Load one optional persisted Audio Blocks direct-clone source profile list.
    @param[in]  project_root Active project root folder.
    @return     Ordered direct-clone source profile payload list.
    @exception  None
    """
    clone_path = resolve_operation_path(
        project_root,
        "audio_blocks",
        config.AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME,
    )
    payload = load_optional_json_artifact(clone_path)
    if not isinstance(payload, list):
        return []
    return [_normalize_voice_clone_profile(item) for item in payload if isinstance(item, dict)]


@trace_function(_AUDIO_BLOCKS_LOGGER)
def has_persisted_audio_blocks(project_root: str | Path) -> bool:
    """
    @brief      Return whether the project already stores Audio Blocks progress or artifacts.
    @param[in]  project_root Active project root folder.
    @return     `True` when Audio Blocks artifacts or progress are present.
    @exception  None
    """
    generated_root = _generated_audio_root(Path(project_root))
    operation_state = load_operation_state(project_root)
    has_runtime_state = False
    if isinstance(operation_state, dict):
        has_runtime_state = str(operation_state.get("status", "")).strip() != AUDIO_BLOCKS_STAGE_NOT_STARTED or any(
            (
                int(operation_state.get("progress_current", 0) or 0) > 0,
                int(operation_state.get("progress_total", 0) or 0) > 0,
            )
        )
    return any(
        (
            bool(load_audio_blocks(project_root)),
            bool(load_audio_blocks_report(project_root)),
            has_runtime_state,
            bool(load_voice_clone_profiles(project_root)),
            generated_root.is_dir() and any(path.is_file() for path in generated_root.rglob("*")),
        )
    )


@trace_function(_AUDIO_BLOCKS_LOGGER)
def has_persisted_audio_for_speech_block(project_root: str | Path, speech_block_id: str) -> bool:
    """
    @brief      Return whether one Speech Block has generated Audio Blocks data.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Speech Block identifier to inspect.
    @return     `True` when the selected Speech Block has audio records or files.
    @exception  None
    """
    normalized_speech_block_id = str(speech_block_id).strip()
    if not normalized_speech_block_id:
        return False
    for block in load_audio_blocks(project_root):
        if str(block.get("speech_block_id", "")).strip() != normalized_speech_block_id:
            continue
        if any(
            (
                is_generated(block),
                is_approved(block),
                _audio_artifact_path(project_root, normalized_speech_block_id).is_file(),
            )
        ):
            return True
    return False


@trace_function(_AUDIO_BLOCKS_LOGGER)
def start_or_continue_generation(
    project_root: str | Path,
    manifest: dict[str, object],
    runtime_settings: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
) -> AudioBlocksReportPayload:
    """
    @brief      Run Audio Blocks generation for the active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  runtime_settings Runtime connection plus discovered-model settings.
    @param[in]  progress_callback Optional progress callback for modal UI updates.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Final Audio Blocks report payload.
    @exception  ValueError Raised when prerequisites or runtime settings are invalid.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    """
    resolved_project_root = Path(project_root)
    generation_context = _resolve_generation_context(resolved_project_root, manifest, runtime_settings)
    existing_state = load_operation_state(resolved_project_root) or {}
    started_at = _resolve_started_at(existing_state)
    existing_blocks, existing_clone_profiles, profile_index, block_index = _restore_resume_state(
        resolved_project_root,
        generation_context,
        existing_state,
    )
    persisted_audio_blocks = load_audio_blocks(resolved_project_root)
    if not existing_blocks:
        existing_blocks = persisted_audio_blocks or _initialize_audio_blocks(
            generation_context["speech_blocks"],
            str(generation_context.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)),
        )
    if not existing_clone_profiles:
        existing_clone_profiles = load_voice_clone_profiles(resolved_project_root)
    existing_blocks = _merge_existing_audio_blocks(
        generation_context["speech_blocks"],
        existing_blocks,
        str(generation_context.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)),
    )

    report = _persist_document(
        resolved_project_root,
        existing_blocks,
        existing_clone_profiles,
        status="running",
        voice_language=str(generation_context["voice_language"]),
        input_fingerprint=str(generation_context["input_fingerprint"]),
        run_token=started_at,
        current_phase=(_PROFILE_PHASE if profile_index < len(generation_context["voice_targets"]) else _GENERATE_PHASE),
        current_block_id=None,
        next_speech_block_index=block_index,
        total_block_count=len(generation_context["speech_blocks"]),
    )
    _emit_progress(
        progress_callback,
        _generated_count(existing_blocks),
        len(generation_context["speech_blocks"]),
        "Preparing reusable voice prompts...",
    )

    try:
        loaded_model_budget = _ensure_clone_model_loaded(
            runtime_settings,
            generation_context["clone_model_id"],
            dict(generation_context.get("clone_model_payload", {})),
            progress_callback,
            len(generation_context["speech_blocks"]),
            _generated_count(existing_blocks),
            cancel_requested=cancel_requested,
        )
    except operation_runtime_service.OperationCancelledError:
        _persist_cancelled_state(
            resolved_project_root,
            generation_context,
            existing_blocks,
            existing_clone_profiles,
            started_at,
            _PROFILE_PHASE if profile_index < len(generation_context["voice_targets"]) else _GENERATE_PHASE,
            None,
            block_index,
        )
        raise
    generation_context.update(loaded_model_budget)
    generation_context["input_fingerprint"] = _build_input_fingerprint(
        generation_context["speech_blocks"],
        generation_context["voice_targets"],
        str(generation_context["voice_language"]),
        str(generation_context["clone_model_id"]),
        manifest,
        {
            **loaded_model_budget,
            "generate_scene_ambience_audio": bool(generation_context.get("generate_scene_ambience_audio", False)),
            "sound_model_id": str(generation_context.get("sound_model_id", "")).strip(),
            "scene_ambience_duration_seconds": _optional_float(
                generation_context.get("scene_ambience_duration_seconds")
            ),
        },
    )
    if _requires_manual_reset(existing_state, generation_context["input_fingerprint"]):
        existing_state = {}
    restored_blocks, restored_clone_profiles, restored_profile_index, restored_block_index = _restore_resume_state(
        resolved_project_root,
        generation_context,
        existing_state,
    )
    voice_assignment_mode = str(
        generation_context.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)
    )
    if restored_blocks:
        existing_blocks = _merge_existing_audio_blocks(
            generation_context["speech_blocks"],
            restored_blocks,
            voice_assignment_mode,
            generation_context=generation_context,
            project_root=resolved_project_root,
        )
        existing_clone_profiles = restored_clone_profiles or existing_clone_profiles
        profile_index = restored_profile_index
    else:
        existing_blocks = _merge_existing_audio_blocks(
            generation_context["speech_blocks"],
            load_audio_blocks(resolved_project_root),
            voice_assignment_mode,
            generation_context=generation_context,
            project_root=resolved_project_root,
        )
    generation_order_indices = _audio_generation_order_indices(
        existing_blocks,
        bool(generation_context.get("generate_scene_ambience_audio", False)),
    )
    block_index = _first_incomplete_generation_order_index(
        existing_blocks,
        generation_order_indices,
        resolved_project_root,
    )
    existing_blocks = [_apply_model_budget_to_block(block, generation_context) for block in existing_blocks]

    for current_profile_index in range(profile_index, len(generation_context["voice_targets"])):
        try:
            raise_if_cancelled(cancel_requested)
        except operation_runtime_service.OperationCancelledError:
            _persist_cancelled_state(
                resolved_project_root,
                generation_context,
                existing_blocks,
                existing_clone_profiles,
                started_at,
                _PROFILE_PHASE,
                None,
                block_index,
            )
            raise
        voice_target = generation_context["voice_targets"][current_profile_index]
        try:
            existing_clone_profiles, prompt_reused = _prepare_clone_profile(
                generation_context,
                voice_target,
                existing_clone_profiles,
                runtime_settings,
                cancel_requested=cancel_requested,
            )
        except operation_runtime_service.OperationCancelledError:
            _persist_cancelled_state(
                resolved_project_root,
                generation_context,
                existing_blocks,
                existing_clone_profiles,
                started_at,
                _PROFILE_PHASE,
                None,
                block_index,
            )
            raise
        if prompt_reused:
            progress_message = f"Reused clone prompt for {voice_target['display_name']}."
        else:
            progress_message = f"Prepared clone prompt for {voice_target['display_name']}."
        report = _persist_document(
            resolved_project_root,
            existing_blocks,
            existing_clone_profiles,
            status="running",
            voice_language=str(generation_context["voice_language"]),
            input_fingerprint=str(generation_context["input_fingerprint"]),
            run_token=started_at,
            current_phase=_PROFILE_PHASE,
            current_block_id=None,
            next_speech_block_index=block_index,
            total_block_count=len(generation_context["speech_blocks"]),
        )
        _emit_progress(
            progress_callback,
            _generated_count(existing_blocks),
            len(generation_context["speech_blocks"]),
            progress_message,
        )

    clone_profiles_by_id = {
        str(profile.get("voice_target_id", "")).strip(): profile for profile in existing_clone_profiles
    }
    active_generation_model_id = str(generation_context["clone_model_id"]).strip()
    resume_metadata = existing_state.get("metadata", {}) if isinstance(existing_state, dict) else {}
    resume_block_id = (
        str(resume_metadata.get("current_block_id", "") or "").strip() if isinstance(resume_metadata, dict) else ""
    )
    resume_order_index = _resume_checkpoint_field(existing_state, "next_speech_block_index", -1)
    resume_split_part_index = _resume_checkpoint_field(existing_state, "next_split_part_index", 0)
    generation_order_indices = _audio_generation_order_indices(
        existing_blocks,
        bool(generation_context.get("generate_scene_ambience_audio", False)),
    )
    for current_order_index in range(block_index, len(generation_order_indices)):
        current_block_index = generation_order_indices[current_order_index]
        try:
            raise_if_cancelled(cancel_requested)
        except operation_runtime_service.OperationCancelledError:
            _persist_cancelled_state(
                resolved_project_root,
                generation_context,
                existing_blocks,
                existing_clone_profiles,
                started_at,
                _GENERATE_PHASE,
                None,
                current_order_index,
            )
            raise
        current_block = dict(existing_blocks[current_block_index])
        current_block_id = str(current_block.get("speech_block_id", "")).strip()
        if not bool(current_block.get("speech_block_approved", False)):
            continue
        if bool(current_block.get("metadata_only", False)):
            continue
        if _audio_block_has_reusable_audio(current_block, resolved_project_root):
            continue
        if str(current_block.get("content_kind", "")).strip() == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE:
            try:
                _ensure_sound_model_loaded(
                    runtime_settings,
                    str(generation_context.get("sound_model_id", "")),
                    progress_callback,
                    len(generation_context["speech_blocks"]),
                    _generated_count(existing_blocks),
                    cancel_requested=cancel_requested,
                )
                generated_block = _generate_scene_ambience_audio_block(
                    resolved_project_root,
                    current_block,
                    generation_context,
                    runtime_settings,
                    cancel_requested=cancel_requested,
                )
                active_generation_model_id = str(generation_context.get("sound_model_id", "")).strip()
            except operation_runtime_service.OperationCancelledError:
                _persist_cancelled_state(
                    resolved_project_root,
                    generation_context,
                    existing_blocks,
                    existing_clone_profiles,
                    started_at,
                    _GENERATE_PHASE,
                    current_block_id,
                    current_order_index,
                )
                raise
            existing_blocks[current_block_index] = generated_block
            report = _persist_document(
                resolved_project_root,
                existing_blocks,
                existing_clone_profiles,
                status="running",
                voice_language=str(generation_context["voice_language"]),
                input_fingerprint=str(generation_context["input_fingerprint"]),
                run_token=started_at,
                current_phase=_GENERATE_PHASE,
                current_block_id=current_block_id,
                next_speech_block_index=current_order_index + 1,
                total_block_count=len(generation_context["speech_blocks"]),
            )
            _emit_progress(
                progress_callback,
                _generated_count(existing_blocks),
                len(generation_context["speech_blocks"]),
                "Generated Scene Ambience audio.",
            )
            continue
        clone_model_id = str(generation_context["clone_model_id"]).strip()
        if active_generation_model_id != clone_model_id:
            _ensure_clone_model_loaded(
                runtime_settings,
                clone_model_id,
                dict(generation_context.get("clone_model_payload", {})),
                progress_callback,
                len(generation_context["speech_blocks"]),
                _generated_count(existing_blocks),
                cancel_requested=cancel_requested,
            )
            active_generation_model_id = clone_model_id
        clone_profile = clone_profiles_by_id.get(str(current_block.get("voice_target_id", "")).strip())
        if clone_profile is None:
            raise RuntimeError(f"Missing clone profile for voice target '{current_block.get('voice_target_id', '')}'.")

        def _checkpoint_current_spoken_block(
            checkpoint_block: AudioBlockPayload,
            next_split_part_index: int,
            active_block_index: int = current_block_index,
            active_order_index: int = current_order_index,
        ) -> None:
            """
            @brief      Persist a resumable checkpoint for the active spoken Speech Block.
            @param[in]  checkpoint_block Partially generated Audio Block payload.
            @param[in]  next_split_part_index Next TTS split part to generate.
            @param[in]  active_block_index Current generated-block index.
            @param[in]  active_order_index Current speech-block generation order index.
            @return     None.
            @exception  None
            """
            _persist_split_checkpoint(
                resolved_project_root,
                generation_context,
                existing_blocks,
                existing_clone_profiles,
                checkpoint_block,
                active_block_index,
                next_split_part_index,
                started_at,
                next_generation_order_index=active_order_index,
            )

        try:
            generated_block = _generate_audio_block(
                resolved_project_root,
                current_block,
                clone_profile,
                generation_context,
                runtime_settings,
                cancel_requested=cancel_requested,
                checkpoint_callback=_checkpoint_current_spoken_block,
                next_split_part_index=(
                    resume_split_part_index
                    if current_block_id == resume_block_id and current_order_index == resume_order_index
                    else 0
                ),
            )
        except operation_runtime_service.OperationCancelledError:
            latest_state = load_operation_state(resolved_project_root) or {}
            latest_blocks = _merge_existing_audio_blocks(
                generation_context["speech_blocks"],
                load_audio_blocks(resolved_project_root) or existing_blocks,
                voice_assignment_mode,
            )
            _persist_cancelled_state(
                resolved_project_root,
                generation_context,
                latest_blocks,
                existing_clone_profiles,
                started_at,
                _GENERATE_PHASE,
                current_block_id,
                current_order_index,
                _resume_checkpoint_field(latest_state, "next_split_part_index", 0),
            )
            raise
        existing_blocks[current_block_index] = generated_block
        report = _persist_document(
            resolved_project_root,
            existing_blocks,
            existing_clone_profiles,
            status="running",
            voice_language=str(generation_context["voice_language"]),
            input_fingerprint=str(generation_context["input_fingerprint"]),
            run_token=started_at,
            current_phase=_GENERATE_PHASE,
            current_block_id=current_block_id,
            next_speech_block_index=current_order_index + 1,
            total_block_count=len(generation_context["speech_blocks"]),
        )
        _emit_progress(
            progress_callback,
            _generated_count(existing_blocks),
            len(generation_context["speech_blocks"]),
            f"Generated audio for {generated_block['speaker_display_name']}.",
        )

    final_status = _derived_stage_status(len(generation_context["speech_blocks"]), existing_blocks)
    report = _persist_document(
        resolved_project_root,
        existing_blocks,
        existing_clone_profiles,
        status=(
            AUDIO_BLOCKS_STAGE_COMPLETED
            if final_status == AUDIO_BLOCKS_STAGE_COMPLETED
            else AUDIO_BLOCKS_STAGE_IN_PROGRESS
        ),
        voice_language=str(generation_context["voice_language"]),
        input_fingerprint=str(generation_context["input_fingerprint"]),
        run_token=started_at,
        current_phase=_GENERATE_PHASE,
        current_block_id=None,
        next_speech_block_index=len(existing_blocks),
        total_block_count=len(generation_context["speech_blocks"]),
    )
    _emit_progress(
        progress_callback,
        _generated_count(existing_blocks),
        len(generation_context["speech_blocks"]),
        "Audio Blocks generation completed."
        if final_status == "completed"
        else "Generated approved Audio Blocks. Approve more Speech Blocks to continue.",
    )
    return report


@trace_function(_AUDIO_BLOCKS_LOGGER)
def approve_audio_block(project_root: str | Path, speech_block_id: str) -> AudioBlocksReportPayload:
    """
    @brief      Approve one generated Audio Blocks entry without touching other entries.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Target speech-block identifier.
    @return     Updated Audio Blocks report payload.
    @exception  ValueError Raised when the block is missing or has no generated audio.
    """
    resolved_project_root = Path(project_root)
    audio_blocks = load_audio_blocks(resolved_project_root)
    if not audio_blocks:
        raise ValueError("Audio Blocks have not been generated yet.")
    normalized_block_id = str(speech_block_id).strip()
    updated = False
    for block in audio_blocks:
        if str(block.get("speech_block_id", "")).strip() != normalized_block_id:
            continue
        if not is_generated(block):
            raise ValueError("Generate the selected audio block before approving it.")
        block["approved"] = _utc_now_iso()
        updated = True
        break
    if not updated:
        raise ValueError("The selected audio block was not found.")
    return _persist_report_update(resolved_project_root, audio_blocks)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def unapprove_audio_block(project_root: str | Path, speech_block_id: str) -> AudioBlocksReportPayload:
    """
    @brief      Mark one generated Audio Blocks entry unapproved while preserving its WAV and metadata files.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Target speech-block identifier.
    @return     Updated Audio Blocks report payload.
    @exception  ValueError Raised when the block is missing or has no generated audio.
    """
    resolved_project_root = Path(project_root)
    audio_blocks = load_audio_blocks(resolved_project_root)
    if not audio_blocks:
        raise ValueError("Audio Blocks have not been generated yet.")
    normalized_block_id = str(speech_block_id).strip()
    updated = False
    for block in audio_blocks:
        if str(block.get("speech_block_id", "")).strip() != normalized_block_id:
            continue
        if not is_generated(block):
            raise ValueError("Generate the selected audio block before changing its approval.")
        block["approved"] = None
        updated = True
        break
    if not updated:
        raise ValueError("The selected audio block was not found.")
    return _persist_report_update(resolved_project_root, audio_blocks)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def approve_all_audio_blocks(project_root: str | Path) -> AudioBlocksReportPayload:
    """
    @brief      Approve every generated Audio Blocks entry without generating missing ones.
    @param[in]  project_root Active project root folder.
    @return     Updated Audio Blocks report payload.
    @exception  None
    """
    resolved_project_root = Path(project_root)
    audio_blocks = load_audio_blocks(resolved_project_root)
    if not audio_blocks:
        return _persist_report_update(resolved_project_root, [])
    approved_at = _utc_now_iso()
    for block in audio_blocks:
        if is_generated(block):
            block["approved"] = approved_at
    return _persist_report_update(resolved_project_root, audio_blocks)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def reconcile_after_speech_blocks_resplit(project_root: str | Path, changed_chunk_id: str) -> AudioBlocksReportPayload:
    """
    @brief      Preserve safe Audio Blocks entries after one Speech Blocks chunk is re-split.
    @param[in]  project_root Active project root folder.
    @param[in]  changed_chunk_id Re-split source chunk identifier.
    @return     Updated Audio Blocks report payload.
    @exception  None
    """
    resolved_project_root = Path(project_root)
    speech_blocks = speech_blocks_service.sort_speech_blocks(
        speech_blocks_service.load_speech_blocks(resolved_project_root)
    )
    existing_audio_blocks = load_audio_blocks(resolved_project_root)
    if not existing_audio_blocks:
        return load_audio_blocks_report(resolved_project_root) or _persist_report_update(resolved_project_root, [])
    tts_plan = narrator_definition_service.load_tts_plan(resolved_project_root)
    voice_assignment_mode = str(
        tts_plan.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)
    )
    existing_by_speech_block_id = {
        str(block.get("speech_block_id", "")).strip(): dict(block) for block in existing_audio_blocks
    }
    reconciled_blocks: list[AudioBlockPayload] = []
    for speech_block in speech_blocks:
        chunk_id = str(speech_block.get("chunk_id", "")).strip()
        new_block = _initialize_audio_blocks([speech_block], voice_assignment_mode)[0]
        if chunk_id == str(changed_chunk_id).strip():
            old_block = existing_by_speech_block_id.get(str(speech_block.get("speech_block_id", "")).strip())
            if old_block is not None:
                _delete_audio_block_artifacts(resolved_project_root, old_block)
            reconciled_blocks.append(new_block)
            continue
        old_block = existing_by_speech_block_id.get(str(speech_block.get("speech_block_id", "")).strip())
        if old_block is None:
            reconciled_blocks.append(new_block)
            continue
        new_block.update(
            {
                "audio_can_play": _persisted_audio_can_play(old_block),
                "audio_duration_seconds": old_block.get("audio_duration_seconds"),
                "special_block_status": old_block.get("special_block_status") or new_block.get("special_block_status"),
                "generated": is_generated(old_block),
                "approved": is_approved(old_block),
                "runtime_result_summary": str(old_block.get("runtime_result_summary", "")),
                "split_part_count": int(old_block.get("split_part_count", 1)),
                "generation_fingerprint": old_block.get("generation_fingerprint"),
                "split_plan_fingerprint": old_block.get("split_plan_fingerprint"),
            }
        )
        reconciled_blocks.append(new_block)
    for old_block in existing_audio_blocks:
        old_block_id = str(old_block.get("speech_block_id", "")).strip()
        if old_block_id not in {str(block.get("speech_block_id", "")).strip() for block in speech_blocks}:
            _delete_audio_block_artifacts(
                resolved_project_root,
                old_block,
            )
    return _persist_report_update(resolved_project_root, reconciled_blocks)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def reset_audio_for_speech_chunk(project_root: str | Path, changed_chunk_id: str) -> AudioBlocksReportPayload:
    """
    @brief      Reset generated Audio Blocks data for one changed Speech Blocks chunk.
    @param[in]  project_root Active project root folder.
    @param[in]  changed_chunk_id Changed source chunk identifier.
    @return     Updated Audio Blocks report payload.
    @exception  None
    """
    return reconcile_after_speech_blocks_resplit(project_root, changed_chunk_id)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def remove_audio_blocks_for_chunks(
    project_root: str | Path,
    chunk_ids: list[str] | tuple[str, ...] | set[str],
) -> tuple[AudioBlocksReportPayload | None, workflow_impact_service.ArtifactDeletionSummary]:
    """
    @brief      Remove Audio Blocks and generated files for selected source chunks.
    @param[in]  project_root Active project root folder.
    @param[in]  chunk_ids Source chunk identifiers whose audio must be reset.
    @return     Updated report, if Audio Blocks existed, plus artifact deletion summary.
    @exception  None
    """
    normalized_chunk_ids = {str(chunk_id).strip() for chunk_id in chunk_ids if str(chunk_id).strip()}
    if not normalized_chunk_ids:
        return load_audio_blocks_report(project_root), workflow_impact_service.ArtifactDeletionSummary()
    resolved_project_root = Path(project_root)
    audio_blocks = load_audio_blocks(resolved_project_root)
    if not audio_blocks:
        return load_audio_blocks_report(resolved_project_root), workflow_impact_service.ArtifactDeletionSummary()
    enriched_audio_blocks = [dict(block) for block in audio_blocks]
    artifact_summary = workflow_impact_service.delete_audio_block_artifacts(
        resolved_project_root,
        enriched_audio_blocks,
        chunk_ids=normalized_chunk_ids,
    )
    preserved_blocks = [
        block for block in audio_blocks if str(block.get("chunk_id", "")).strip() not in normalized_chunk_ids
    ]
    return _persist_report_update(resolved_project_root, preserved_blocks), artifact_summary


@trace_function(_AUDIO_BLOCKS_LOGGER)
def remove_audio_blocks_for_speech_blocks(
    project_root: str | Path,
    speech_block_ids: list[str] | tuple[str, ...] | set[str],
    voice_target_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    collect_preserved_paths: bool = True,
    preserve_invalidated_blocks: bool = False,
) -> tuple[AudioBlocksReportPayload | None, workflow_impact_service.ArtifactDeletionSummary]:
    """
    @brief      Remove Audio Blocks and generated files for selected Speech Blocks or voice targets.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_ids Speech Block identifiers whose audio must reset.
    @param[in]  voice_target_ids Optional voice target identifiers whose audio must reset.
    @param[in]  collect_preserved_paths True to check and report unaffected generated files.
    @param[in]  preserve_invalidated_blocks True to keep affected rows with generated-audio fields cleared.
    @return     Updated report, if Audio Blocks existed, plus artifact deletion summary.
    @exception  None
    """
    normalized_speech_block_ids = {
        str(speech_block_id).strip() for speech_block_id in speech_block_ids if str(speech_block_id).strip()
    }
    normalized_voice_target_ids = {
        str(voice_target_id).strip() for voice_target_id in (voice_target_ids or ()) if str(voice_target_id).strip()
    }
    if not normalized_speech_block_ids and not normalized_voice_target_ids:
        return load_audio_blocks_report(project_root), workflow_impact_service.ArtifactDeletionSummary()
    resolved_project_root = Path(project_root)
    audio_blocks = load_audio_blocks(resolved_project_root)
    clone_profiles = load_voice_clone_profiles(resolved_project_root)
    preserved_clone_profiles = [
        profile
        for profile in clone_profiles
        if str(profile.get("voice_target_id", "")).strip() not in normalized_voice_target_ids
    ]
    if not audio_blocks:
        return (
            _persist_report_update(resolved_project_root, [], preserved_clone_profiles),
            workflow_impact_service.ArtifactDeletionSummary(),
        )
    enriched_audio_blocks = [dict(block) for block in audio_blocks]
    artifact_summary = workflow_impact_service.delete_audio_block_artifacts(
        resolved_project_root,
        enriched_audio_blocks,
        speech_block_ids=normalized_speech_block_ids,
        voice_target_ids=normalized_voice_target_ids,
        collect_preserved_paths=collect_preserved_paths,
    )
    if preserve_invalidated_blocks:
        updated_blocks: list[AudioBlockPayload] = []
        for block in audio_blocks:
            if _audio_block_matches_invalidation(
                block,
                normalized_speech_block_ids,
                normalized_voice_target_ids,
            ):
                cleared_block = dict(block)
                cleared_block.update(_cleared_audio_fields())
                updated_blocks.append(cleared_block)
                continue
            updated_blocks.append(block)
        return _persist_report_update(resolved_project_root, updated_blocks, preserved_clone_profiles), artifact_summary
    preserved_blocks = [
        block
        for block in audio_blocks
        if str(block.get("speech_block_id", "")).strip() not in normalized_speech_block_ids
        and str(block.get("voice_target_id", "")).strip() not in normalized_voice_target_ids
    ]
    return _persist_report_update(resolved_project_root, preserved_blocks, preserved_clone_profiles), artifact_summary


@trace_function(_AUDIO_BLOCKS_LOGGER)
def regenerate_audio_block(
    project_root: str | Path,
    manifest: dict[str, object],
    speech_block_id: str,
    runtime_settings: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
) -> AudioBlocksReportPayload:
    """
    @brief      Re-generate one persisted Audio Blocks entry and clear its approval.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  speech_block_id Target speech-block identifier.
    @param[in]  runtime_settings Runtime connection plus discovered-model settings.
    @param[in]  progress_callback Optional progress callback for modal UI updates.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Updated Audio Blocks report payload.
    @exception  ValueError Raised when the block or its prerequisites are missing.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    """
    resolved_project_root = Path(project_root)
    generation_context = _resolve_generation_context(resolved_project_root, manifest, runtime_settings)
    audio_blocks = _merge_existing_audio_blocks(
        generation_context["speech_blocks"],
        load_audio_blocks(resolved_project_root),
        str(generation_context.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)),
    )
    target_block_id = str(speech_block_id).strip()
    target_index = next(
        (
            index
            for index, block in enumerate(audio_blocks)
            if str(block.get("speech_block_id", "")).strip() == target_block_id
        ),
        None,
    )
    if target_index is None:
        raise ValueError("The selected audio block was not found.")
    if not audio_can_regenerate(audio_blocks[target_index]):
        raise ValueError("The selected metadata-only audio block cannot be regenerated.")

    if (
        str(audio_blocks[target_index].get("content_kind", "")).strip()
        == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
    ):
        if not bool(generation_context.get("generate_scene_ambience_audio", False)):
            runtime_settings = {**runtime_settings, "generate_scene_ambience_audio": True}
            generation_context = _resolve_generation_context(resolved_project_root, manifest, runtime_settings)
        audio_blocks = _merge_existing_audio_blocks(
            generation_context["speech_blocks"],
            audio_blocks,
            str(generation_context.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)),
            generation_context=generation_context,
            project_root=resolved_project_root,
        )
        target_index = next(
            (
                index
                for index, block in enumerate(audio_blocks)
                if str(block.get("speech_block_id", "")).strip() == target_block_id
            ),
            None,
        )
        if target_index is None:
            raise ValueError("The selected audio block was not found.")
        audio_blocks = [_apply_model_budget_to_block(block, generation_context) for block in audio_blocks]
        _ensure_sound_model_loaded(
            runtime_settings,
            str(generation_context.get("sound_model_id", "")),
            progress_callback,
            len(audio_blocks),
            _generated_count(audio_blocks),
            cancel_requested=cancel_requested,
        )
        audio_blocks[target_index] = _generate_scene_ambience_audio_block(
            resolved_project_root,
            dict(audio_blocks[target_index]),
            generation_context,
            runtime_settings,
            cancel_requested=cancel_requested,
        )
        return _persist_report_update(
            resolved_project_root,
            audio_blocks,
            load_voice_clone_profiles(resolved_project_root),
        )

    loaded_model_budget = _ensure_clone_model_loaded(
        runtime_settings,
        str(generation_context["clone_model_id"]),
        dict(generation_context.get("clone_model_payload", {})),
        progress_callback,
        len(audio_blocks),
        _generated_count(audio_blocks),
        cancel_requested=cancel_requested,
    )
    generation_context.update(loaded_model_budget)
    generation_context["input_fingerprint"] = _build_input_fingerprint(
        generation_context["speech_blocks"],
        generation_context["voice_targets"],
        str(generation_context["voice_language"]),
        str(generation_context["clone_model_id"]),
        manifest,
        {
            **loaded_model_budget,
            "generate_scene_ambience_audio": bool(generation_context.get("generate_scene_ambience_audio", False)),
            "sound_model_id": str(generation_context.get("sound_model_id", "")).strip(),
            "scene_ambience_duration_seconds": _optional_float(
                generation_context.get("scene_ambience_duration_seconds")
            ),
        },
    )
    selected_block_needs_generation = not is_generated(audio_blocks[target_index])
    if not selected_block_needs_generation and _requires_manual_reset(
        load_operation_state(resolved_project_root) or {},
        generation_context["input_fingerprint"],
    ):
        raise ValueError("Audio Blocks inputs or model budget changed. Reset Audio Blocks before regenerating audio.")
    audio_blocks = _merge_existing_audio_blocks(
        generation_context["speech_blocks"],
        audio_blocks,
        str(generation_context.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)),
        generation_context=generation_context,
        project_root=resolved_project_root,
    )
    audio_blocks = [_apply_model_budget_to_block(block, generation_context) for block in audio_blocks]
    voice_target_id = str(audio_blocks[target_index].get("voice_target_id", "")).strip()
    voice_target = next(
        (
            dict(target)
            for target in generation_context["voice_targets"]
            if str(target.get("voice_target_id", "")).strip() == voice_target_id
        ),
        None,
    )
    if voice_target is None:
        raise ValueError("The selected block does not reference one valid voice target.")

    clone_profiles, _prompt_reused = _prepare_clone_profile(
        generation_context,
        voice_target,
        load_voice_clone_profiles(resolved_project_root),
        runtime_settings,
        cancel_requested=cancel_requested,
    )
    clone_profile = next(
        (
            dict(profile)
            for profile in clone_profiles
            if str(profile.get("voice_target_id", "")).strip() == voice_target_id
        ),
        None,
    )
    if clone_profile is None:
        raise RuntimeError("Failed to prepare the required reusable clone prompt for the selected audio block.")
    raise_if_cancelled(cancel_requested)
    audio_blocks[target_index] = _generate_audio_block(
        resolved_project_root,
        dict(audio_blocks[target_index]),
        clone_profile,
        generation_context,
        runtime_settings,
        cancel_requested=cancel_requested,
        force_restart=True,
    )
    return _persist_report_update(resolved_project_root, audio_blocks, clone_profiles)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def reset_audio_blocks(project_root: str | Path) -> None:
    """
    @brief      Delete Audio Blocks runtime artifacts.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    """
    operation_runtime_service.reset_operation_data(
        project_root,
        "audio_blocks",
        include_current=True,
    )


# LOCAL HELPERS


def _resolve_generation_context(
    project_root: Path,
    manifest: dict[str, object],
    runtime_settings: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Resolve the validated Audio Blocks generation context.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  runtime_settings Runtime connection plus discovered-model settings.
    @return     Validated generation-context payload.
    @exception  ValueError Raised when prerequisites or runtime settings are invalid.
    """
    speech_blocks = speech_blocks_service.sort_speech_blocks(speech_blocks_service.load_speech_blocks(project_root))
    if not speech_blocks:
        raise ValueError("Generate Speech Blocks before starting Audio Blocks.")
    approved_speech_blocks = [block for block in speech_blocks if _speech_block_is_approved(block)]
    if not approved_speech_blocks:
        raise ValueError("Approve at least one Speech Block before starting Audio Blocks.")
    generate_scene_ambience_audio = bool(runtime_settings.get("generate_scene_ambience_audio", False))
    scene_ambience_duration_seconds = _optional_float(runtime_settings.get("scene_ambience_duration_seconds")) or float(
        config.DEFAULT_SCENE_AMBIENCE_DURATION_SECONDS
    )
    approved_scene_ambience_blocks = [
        block
        for block in approved_speech_blocks
        if str(block.get("content_kind", "")).strip() == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
    ]
    speech_audio_blocks = [block for block in approved_speech_blocks if not _is_metadata_only_speech_block(block)]
    base_url = str(runtime_settings.get("base_url", "")).strip()
    timeout_seconds = int(runtime_settings.get("timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
    discovered_models = list(runtime_settings.get("discovered_models", []))
    if not base_url:
        raise ValueError("Configure TTS Settings and test the VoiceWeaver connection before generating Audio Blocks.")
    capability_matrix = voiceweaver_runtime_service.build_capability_matrix(discovered_models)
    clone_model = _first_model(
        capability_matrix.get("qwen_clone_models", []),
        preferred_model_id=_PREFERRED_QWEN_CLONE_MODEL_ID,
    )
    if clone_model is None:
        raise ValueError("Cannot generate Audio Blocks because the required Qwen3 TTS base clone model is missing.")
    sound_model = None
    if generate_scene_ambience_audio:
        sound_model = _first_model(capability_matrix.get("sound_prompt_models", []))
        if sound_model is None and approved_scene_ambience_blocks:
            raise ValueError(
                "Scene Ambience Audio was requested, but VoiceWeaver has no healthy sound_prompt model available."
            )
    clone_model_id = str(clone_model.get("model_id", "")).strip()
    if not clone_model_id or timeout_seconds <= 0:
        raise ValueError("Audio Blocks generation requires a valid runtime model and timeout configuration.")
    voice_assignment_mode = narrator_definition_service.load_tts_plan(project_root, discovered_models)[
        "voice_assignment_mode"
    ]

    voice_language = character_voices_service.load_selected_voice_language(
        project_root,
        narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
    )
    narrator_audio_path = narrator_definition_service.selected_narrator_sample_path(project_root)
    narrator_metadata: dict[str, object] = {}
    if speech_audio_blocks:
        if narrator_audio_path is None or not narrator_audio_path.is_file():
            raise ValueError("Generate the selected narrator sample before starting Audio Blocks.")
        selected_metadata = narrator_definition_service.load_selected_narrator_sample_metadata(project_root)
        if not isinstance(selected_metadata, dict):
            raise ValueError("The selected narrator sample metadata is missing or invalid.")
        narrator_metadata = selected_metadata

    voice_targets: list[dict[str, object]] = []
    voice_target_ids: set[str] = set()
    missing_characters: list[str] = []
    for speech_block in speech_audio_blocks:
        voice_target_id = _voice_target_id_for_block(speech_block, voice_assignment_mode)
        if voice_target_id in voice_target_ids:
            continue
        voice_target_ids.add(voice_target_id)
        if voice_target_id == character_voices_service.TARGET_ID_NARRATOR:
            sample_audio_path = narrator_audio_path
            sample_metadata = dict(narrator_metadata)
            display_name = str(speech_block.get("speaker_display_name", "Narrator")).strip() or "Narrator"
        else:
            sample_audio_path, metadata_path = character_voices_service.target_sample_paths(
                project_root,
                voice_target_id,
            )
            sample_metadata = character_voices_service.load_target_sample_metadata(project_root, voice_target_id)
            if not sample_audio_path.is_file() or not isinstance(sample_metadata, dict):
                missing_characters.append(str(speech_block.get("speaker_display_name", voice_target_id)).strip())
                continue
            display_name = str(speech_block.get("speaker_display_name", voice_target_id)).strip() or voice_target_id
        sample_text = str(sample_metadata.get("preview_text", "")).strip()
        if not sample_text:
            raise ValueError(f"Generate a sample with preview text for '{display_name}' before starting Audio Blocks.")
        sample_fingerprint = _file_sha1(sample_audio_path)
        voice_targets.append(
            {
                "voice_target_id": voice_target_id,
                "display_name": display_name,
                "sample_audio_path": sample_audio_path,
                "sample_relative_path": relative_to_project(project_root, sample_audio_path),
                "sample_fingerprint": sample_fingerprint,
                "sample_text": sample_text,
                "sample_metadata": dict(sample_metadata),
            }
        )
    if missing_characters:
        missing_summary = ", ".join(sorted({name for name in missing_characters if name}))
        raise ValueError(
            "Generate samples for every referenced character voice before starting Audio Blocks. Missing: "
            f"{missing_summary}"
        )
    model_budget = _resolve_model_budget(
        {},
        clone_model,
        tts_budget_service.resolve_generation_token_limit(runtime_settings),
    )
    fingerprint_budget = {
        **model_budget,
        "generate_scene_ambience_audio": generate_scene_ambience_audio,
        "sound_model_id": "" if sound_model is None else str(sound_model.get("model_id", "")).strip(),
        "scene_ambience_duration_seconds": scene_ambience_duration_seconds,
    }
    input_fingerprint = _build_input_fingerprint(
        speech_blocks,
        voice_targets,
        voice_language,
        clone_model_id,
        manifest,
        fingerprint_budget,
    )
    return {
        "speech_blocks": speech_blocks,
        "voice_targets": voice_targets,
        "voice_language": voice_language,
        "clone_model_id": clone_model_id,
        "clone_model_payload": clone_model,
        "sound_model_id": "" if sound_model is None else str(sound_model.get("model_id", "")).strip(),
        "sound_model_payload": {} if sound_model is None else dict(sound_model),
        "generate_scene_ambience_audio": generate_scene_ambience_audio,
        "scene_ambience_duration_seconds": scene_ambience_duration_seconds,
        "voice_assignment_mode": voice_assignment_mode,
        "original_language": str(manifest.get("original_language", "")).strip(),
        **model_budget,
        "base_url": base_url,
        "timeout_seconds": timeout_seconds,
        "input_fingerprint": input_fingerprint,
    }


def _build_input_fingerprint(
    speech_blocks: list[dict[str, object]],
    voice_targets: list[dict[str, object]],
    voice_language: str,
    clone_model_id: str,
    manifest: dict[str, object],
    model_budget: dict[str, object],
) -> str:
    """
    @brief      Build one stable fingerprint for the Audio Blocks generation inputs.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  voice_targets Current voice-target input list.
    @param[in]  voice_language Selected character-voices voice language.
    @param[in]  clone_model_id Active Qwen3 clone/base model identifier.
    @param[in]  manifest Active manifest payload.
    @param[in]  model_budget Resolved clone-model generation budget.
    @return     Hex-encoded fingerprint string.
    @exception  None
    """
    fingerprint_payload = {
        "original_language": manifest.get("original_language"),
        "voice_language": voice_language,
        "clone_model_id": clone_model_id,
        "generate_scene_ambience_audio": bool(model_budget.get("generate_scene_ambience_audio", False)),
        "sound_model_id": str(model_budget.get("sound_model_id", "")).strip(),
        "scene_ambience_duration_seconds": _optional_float(model_budget.get("scene_ambience_duration_seconds")),
        "model_token_budget": int(model_budget.get("model_token_budget", 0)),
        "model_audio_seconds_budget": float(model_budget.get("model_audio_seconds_budget", 0.0)),
        "model_budget_source": str(model_budget.get("model_budget_source", "")),
        "speech_blocks": [
            {
                "speech_block_id": str(block.get("speech_block_id", "")),
                "sequence_index": int(block.get("sequence_index", 0)),
                "chunk_id": str(block.get("chunk_id", "")),
                "speaker_id": str(block.get("speaker_id", "")),
                "speaker_display_name": str(block.get("speaker_display_name", "")),
                "content_kind": str(block.get("content_kind", "")),
                "approved": bool(block.get("approved", False)),
                "text": str(block.get("text", "")),
                "sound_prompt": str(block.get("sound_prompt", "")),
                "negative_prompt": str(block.get("negative_prompt", "")),
                "duration_seconds": block.get("duration_seconds"),
                "ambience_position": str(block.get("ambience_position", "")),
            }
            for block in speech_blocks
        ],
        "voice_targets": [
            {
                "voice_target_id": str(target.get("voice_target_id", "")),
                "sample_fingerprint": str(target.get("sample_fingerprint", "")),
                "sample_text": str(target.get("sample_text", "")),
                "source_model_id": str(dict(target.get("sample_metadata", {})).get("source_model_id", "")).strip()
                or None,
            }
            for target in voice_targets
        ],
    }
    return hashlib.sha1(  # noqa: S324
        json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _restore_resume_state(
    project_root: Path,
    generation_context: dict[str, object],
    existing_state: dict[str, object],
) -> tuple[list[AudioBlockPayload], list[VoiceCloneProfilePayload], int, int]:
    """
    @brief      Restore resumable Audio Blocks state when the persisted checkpoint is still valid.
    @param[in]  project_root Active project root folder.
    @param[in]  generation_context Validated generation-context payload.
    @param[in]  existing_state Existing operation-state payload.
    @return     Existing blocks, clone profiles, next profile index, and next block index.
    @exception  None
    """
    if not isinstance(existing_state, dict):
        return [], [], 0, 0
    if str(existing_state.get("status", "")).strip() not in {"running", "failed", "cancelled", "completed"}:
        return [], [], 0, 0
    metadata = existing_state.get("metadata", {})
    resume_checkpoint = existing_state.get("resume_checkpoint", {})
    if not isinstance(metadata, dict) or not isinstance(resume_checkpoint, dict):
        return [], [], 0, 0
    if str(metadata.get("input_fingerprint", "")).strip() != str(generation_context["input_fingerprint"]):
        return [], [], 0, 0
    return (
        load_audio_blocks(project_root),
        load_voice_clone_profiles(project_root),
        int(resume_checkpoint.get("next_profile_index", 0)),
        int(resume_checkpoint.get("next_speech_block_index", 0)),
    )


def _requires_manual_reset(existing_state: dict[str, object], input_fingerprint: str) -> bool:
    """
    @brief      Return whether one persisted Audio Blocks state belongs to different inputs and must be reset manually.
    @param[in]  existing_state Existing operation-state payload.
    @param[in]  input_fingerprint Current validated input fingerprint.
    @return     `True` when the persisted state cannot be resumed safely.
    @exception  None
    """
    if not isinstance(existing_state, dict):
        return False
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return False
    persisted_fingerprint = str(metadata.get("input_fingerprint", "")).strip()
    return bool(persisted_fingerprint) and persisted_fingerprint != input_fingerprint


def _resolve_model_budget(
    status_payload: dict[str, object],
    clone_model_payload: dict[str, object],
    max_generation_tokens: int = 0,
) -> dict[str, object]:
    """
    @brief      Resolve the clone-model generation budget used for Audio Blocks splitting.
    @details    The runtime advertises a recommended maximum per model and reports its loaded
                default as effective, so the recommended maximum is read first or it would be
                masked by the very default it is meant to replace. The operator ceiling is
                applied before anything is derived, and may only lower the result.
    @param[in]  status_payload Current normalized VoiceWeaver status payload.
    @param[in]  clone_model_payload Discovered clone-model payload.
    @param[in]  max_generation_tokens Operator token ceiling, or zero for none.
    @return     Budget payload including token and audio-seconds limits.
    @exception  ValueError Raised when no positive `max_new_tokens` budget can be resolved.
    """
    recommended_tokens, reported_seconds_per_token = tts_budget_service.model_generation_limits(clone_model_payload)
    reported_hard_maximum = tts_budget_service.model_hard_token_maximum(clone_model_payload)
    seconds_per_token = reported_seconds_per_token or _DEFAULT_APPROX_AUDIO_SECONDS_PER_TOKEN
    operator_token_maximum = max(0, int(max_generation_tokens))
    budget_source_candidates = (
        ("range_recommended_maximum", {"max_new_tokens": recommended_tokens or 0}),
        ("runtime_effective", _status_effective_model_parameters(status_payload)),
        ("default_model_parameters", dict(clone_model_payload).get("default_model_parameters")),
        ("range_default", _parameter_range_default(dict(clone_model_payload).get("generation_parameter_ranges"))),
    )
    for budget_source, parameters in budget_source_candidates:
        token_budget = _positive_int_from_mapping(parameters, "max_new_tokens")
        if token_budget is None:
            continue
        model_token_budget = token_budget
        if operator_token_maximum > 0:
            token_budget = min(token_budget, operator_token_maximum)
        hard_token_maximum = max(model_token_budget, int(reported_hard_maximum or 0))
        audio_seconds_budget = token_budget * seconds_per_token
        hard_split_audio_seconds_budget = hard_token_maximum * seconds_per_token * _SPLIT_SAFETY_FACTOR
        return {
            "operator_token_maximum": operator_token_maximum,
            "model_token_budget": token_budget,
            "hard_token_maximum": hard_token_maximum,
            "model_audio_seconds_budget": audio_seconds_budget,
            "split_audio_seconds_budget": audio_seconds_budget * _SPLIT_SAFETY_FACTOR,
            "hard_word_count": max(1, int(hard_split_audio_seconds_budget * _WORDS_PER_AUDIO_SECOND)),
            "approx_audio_seconds_per_token": seconds_per_token,
            "split_safety_factor": _SPLIT_SAFETY_FACTOR,
            "model_budget_source": budget_source,
        }
    raise ValueError("Cannot generate Audio Blocks because the clone model did not report a max_new_tokens budget.")


def _status_effective_model_parameters(status_payload: dict[str, object]) -> dict[str, object]:
    """
    @brief      Extract runtime effective model parameters from normalized status data.
    @param[in]  status_payload Current normalized VoiceWeaver status payload.
    @return     Effective parameter mapping, or an empty mapping.
    @exception  None
    """
    active_model = status_payload.get("active_model", {}) if isinstance(status_payload, dict) else {}
    containers = [status_payload, active_model] if isinstance(active_model, dict) else [status_payload]
    for container in containers:
        if not isinstance(container, dict):
            continue
        for field_name in ("effective_model_parameters", "effective_parameters", "model_parameters"):
            parameters = container.get(field_name)
            if isinstance(parameters, dict):
                return dict(parameters)
    return {}


def _parameter_range_default(value: object) -> dict[str, object]:
    """
    @brief      Extract parameter defaults from normalized generation-parameter ranges.
    @param[in]  value Candidate generation-parameter range mapping.
    @return     Default parameter mapping.
    @exception  None
    """
    if not isinstance(value, dict):
        return {}
    default_parameters: dict[str, object] = {}
    for parameter_name, range_payload in value.items():
        if isinstance(range_payload, dict) and "default" in range_payload:
            default_parameters[str(parameter_name)] = range_payload["default"]
    return default_parameters


def _positive_int_from_mapping(value: object, field_name: str) -> int | None:
    """
    @brief      Resolve one positive integer field from a mapping.
    @param[in]  value Candidate mapping.
    @param[in]  field_name Field name to resolve.
    @return     Positive integer value, or `None`.
    @exception  None
    """
    if not isinstance(value, dict):
        return None
    try:
        resolved_value = int(value.get(field_name, 0))
    except (TypeError, ValueError):
        return None
    return resolved_value if resolved_value > 0 else None


def _runtime_operation_is_busy(status_payload: dict[str, object]) -> bool:
    """
    @brief      Return whether VoiceWeaver is currently running an operation.
    @param[in]  status_payload Current normalized VoiceWeaver status payload.
    @return     True when the runtime reports a non-terminal operation.
    @exception  None
    """
    operation_payload = status_payload.get("operation", {}) if isinstance(status_payload, dict) else {}
    if not isinstance(operation_payload, dict):
        return False
    operation_status = str(operation_payload.get("status", operation_payload.get("kind", "idle"))).strip().lower()
    return operation_status not in {"", "idle", "completed", "failed"}


def _ensure_model_active(
    runtime_settings: dict[str, object],
    model_id: str,
    model_label: str,
    cancel_requested=None,
) -> dict[str, object]:
    """
    @brief      Load one VoiceWeaver model and verify its terminal active state.
    @param[in]  runtime_settings Runtime connection settings.
    @param[in]  model_id Required VoiceWeaver model identifier.
    @param[in]  model_label Operator-facing model kind used in verification errors.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Final normalized VoiceWeaver status payload.
    @exception  RuntimeError Raised when loading fails or activates the wrong model.
    @exception  OperationCancelledError Raised when cancellation is requested while waiting.
    """
    base_url = str(runtime_settings.get("base_url", "")).strip()
    timeout_seconds = int(runtime_settings.get("timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
    voiceweaver_runtime_service.load_model(
        base_url,
        model_id,
        timeout_seconds=timeout_seconds,
    )
    final_status = voiceweaver_runtime_service.wait_for_terminal_operation(
        base_url,
        timeout_seconds=timeout_seconds,
        cancel_requested=cancel_requested,
    )
    final_operation = final_status.get("operation", {})
    if not isinstance(final_operation, dict) or str(final_operation.get("status", "")).strip().lower() != "completed":
        raise RuntimeError(voiceweaver_runtime_service.operation_failed_message(final_status))
    if _active_model_id_from_status(final_status) != model_id:
        raise RuntimeError(f"VoiceWeaver did not activate the requested {model_label} '{model_id}'.")
    return final_status


def _ensure_clone_model_loaded(
    runtime_settings: dict[str, object],
    clone_model_id: str,
    clone_model_payload: dict[str, object],
    progress_callback,
    progress_total: int,
    progress_current: int,
    cancel_requested=None,
) -> dict[str, object]:
    """
    @brief      Ensure the required Qwen3 base/clone model is active before clone or generation requests.
    @param[in]  runtime_settings Runtime connection plus discovered-model settings.
    @param[in]  clone_model_id Active clone/base model identifier.
    @param[in]  clone_model_payload Discovered model payload used for fallback budget resolution.
    @param[in]  progress_callback Optional modal progress callback.
    @param[in]  progress_total Total speech-block count.
    @param[in]  progress_current Already generated speech-block count.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Resolved model-budget payload.
    @exception  RuntimeError Raised when VoiceWeaver fails to load the requested model.
    @exception  OperationCancelledError Raised when cancellation is requested.
    """
    base_url = str(runtime_settings.get("base_url", "")).strip()
    timeout_seconds = int(runtime_settings.get("timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
    _emit_progress(progress_callback, progress_current, progress_total, "Loading audio generation model...")
    raise_if_cancelled(cancel_requested)
    initial_status = voiceweaver_runtime_service.read_status(
        base_url,
        timeout_seconds=timeout_seconds,
    )
    raise_if_cancelled(cancel_requested)
    active_model_id = _active_model_id_from_status(initial_status)
    if _runtime_operation_is_busy(initial_status):
        raise RuntimeError(
            "VoiceWeaver is still busy with a previous operation. Wait for the current runtime operation to finish, "
            "then start Audio Blocks again."
        )
    operator_token_maximum = tts_budget_service.resolve_generation_token_limit(runtime_settings)
    initial_budget = _resolve_model_budget(initial_status, clone_model_payload, operator_token_maximum)
    # The live active-model identity is the whole question here. Gating on which source supplied
    # the token budget made this unreachable as soon as a runtime-reported budget outranked
    # `runtime_effective`, and every run then reloaded an already-loaded model.
    if active_model_id == clone_model_id:
        return initial_budget
    _ensure_model_active(
        runtime_settings,
        clone_model_id,
        "model",
        cancel_requested=cancel_requested,
    )
    loaded_status = voiceweaver_runtime_service.read_status(
        base_url,
        timeout_seconds=timeout_seconds,
    )
    return _resolve_model_budget(loaded_status, clone_model_payload, operator_token_maximum)


def _ensure_sound_model_loaded(
    runtime_settings: dict[str, object],
    sound_model_id: str,
    progress_callback,
    progress_total: int,
    progress_current: int,
    cancel_requested=None,
) -> None:
    """
    @brief      Ensure the configured VoiceWeaver sound_prompt model is active.
    @param[in]  runtime_settings Runtime connection plus discovered-model settings.
    @param[in]  sound_model_id Active sound model identifier.
    @param[in]  progress_callback Optional modal progress callback.
    @param[in]  progress_total Total speech-block count.
    @param[in]  progress_current Already generated speech-block count.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     None.
    @exception  RuntimeError Raised when VoiceWeaver fails to load the requested model.
    @exception  OperationCancelledError Raised when cancellation is requested.
    """
    normalized_sound_model_id = str(sound_model_id).strip()
    if not normalized_sound_model_id:
        raise RuntimeError(
            "Scene Ambience Audio was requested, but no healthy VoiceWeaver sound_prompt model is available."
        )
    base_url = str(runtime_settings.get("base_url", "")).strip()
    timeout_seconds = int(runtime_settings.get("timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
    _emit_progress(progress_callback, progress_current, progress_total, "Loading scene ambience sound model...")
    raise_if_cancelled(cancel_requested)
    initial_status = voiceweaver_runtime_service.read_status(
        base_url,
        timeout_seconds=timeout_seconds,
    )
    raise_if_cancelled(cancel_requested)
    if _runtime_operation_is_busy(initial_status):
        raise RuntimeError(
            "VoiceWeaver is still busy with a previous operation. Wait for the current runtime operation to finish, "
            "then start Audio Blocks again."
        )
    if _active_model_id_from_status(initial_status) == normalized_sound_model_id:
        return
    _ensure_model_active(
        runtime_settings,
        normalized_sound_model_id,
        "sound model",
        cancel_requested=cancel_requested,
    )


def _prepare_clone_profile(
    generation_context: dict[str, object],
    voice_target: dict[str, object],
    existing_clone_profiles: list[VoiceCloneProfilePayload],
    runtime_settings: dict[str, object],
    cancel_requested=None,
) -> tuple[list[VoiceCloneProfilePayload], bool]:
    """
    @brief      Reuse or create one persisted reusable clone-prompt payload for the selected target voice.
    @param[in]  generation_context Validated generation-context payload.
    @param[in]  voice_target Resolved voice-target payload.
    @param[in]  existing_clone_profiles Persisted reusable clone-prompt list.
    @param[in]  runtime_settings Runtime connection plus discovered-model settings.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Tuple of updated persisted reusable clone-prompt list and one reuse flag.
    @exception  RuntimeError Raised when prompt creation fails or the selected sample metadata is invalid.
    @exception  OperationCancelledError Raised when cancellation is requested.
    """
    normalized_target_id = str(voice_target.get("voice_target_id", "")).strip()
    matching_clone = next(
        (
            dict(profile)
            for profile in existing_clone_profiles
            if _clone_profile_matches(profile, voice_target, generation_context)
        ),
        None,
    )
    if matching_clone is not None:
        return _replace_clone_profile(existing_clone_profiles, matching_clone), True

    sample_audio_path = Path(voice_target.get("sample_audio_path", ""))
    sample_text = str(voice_target.get("sample_text", "")).strip()
    if not sample_text:
        raise RuntimeError(
            f"The sample metadata for voice target '{normalized_target_id}' has no preview_text for clone prompts."
        )
    if not sample_audio_path.is_file():
        raise RuntimeError(
            f"Audio Blocks could not find the required reference sample for voice target '{normalized_target_id}'."
        )
    sample_language = _voice_target_sample_language(voice_target)

    base_url = str(runtime_settings.get("base_url", "")).strip()
    timeout_seconds = int(runtime_settings.get("timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
    raise_if_cancelled(cancel_requested)
    voiceweaver_runtime_service.create_voice_clone_prompt(
        base_url,
        sample_audio_path.read_bytes(),
        sample_text,
        sample_language,
        timeout_seconds=timeout_seconds,
    )
    final_status = voiceweaver_runtime_service.wait_for_terminal_operation(
        base_url,
        timeout_seconds=timeout_seconds,
        cancel_requested=cancel_requested,
    )
    final_operation = final_status.get("operation", {})
    if not isinstance(final_operation, dict) or str(final_operation.get("status", "")).strip().lower() != "completed":
        raise RuntimeError(voiceweaver_runtime_service.operation_failed_message(final_status))
    voice_clone_prompt = _extract_voice_clone_prompt(final_status)

    sample_metadata = dict(voice_target.get("sample_metadata", {}))
    clone_profile = {
        "voice_target_id": normalized_target_id,
        "display_name": str(voice_target.get("display_name", "")).strip() or normalized_target_id,
        "source_sample_relative_path": str(voice_target.get("sample_relative_path", "")),
        "source_sample_fingerprint": str(voice_target.get("sample_fingerprint", "")),
        "source_model_id": str(sample_metadata.get("source_model_id", "")).strip() or None,
        "voice_language": sample_language,
        "sample_text": sample_text,
        "voice_clone_prompt": voice_clone_prompt,
        "prompt_format": _optional_string(
            str(voice_clone_prompt.get("format", "")).strip() if isinstance(voice_clone_prompt, dict) else ""
        ),
        "generated_at": _utc_now_iso(),
        "clone_model_id": str(generation_context.get("clone_model_id", "")).strip(),
    }
    return _replace_clone_profile(existing_clone_profiles, clone_profile), False


def _generate_audio_block(
    project_root: Path,
    audio_block: AudioBlockPayload,
    clone_profile: VoiceCloneProfilePayload,
    generation_context: dict[str, object],
    runtime_settings: dict[str, object],
    cancel_requested=None,
    checkpoint_callback=None,
    next_split_part_index: int = 0,
    force_restart: bool = False,
) -> AudioBlockPayload:
    """
    @brief      Generate one WAV and canonical Audio Blocks metadata for the selected speech block.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_block Persisted Audio Blocks entry to regenerate.
    @param[in]  clone_profile Persisted reusable clone-prompt payload.
    @param[in]  generation_context Validated generation-context payload.
    @param[in]  runtime_settings Runtime connection plus discovered-model settings.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  checkpoint_callback Optional callback persisted after each completed split part.
    @param[in]  next_split_part_index Persisted next split part to generate for resume.
    @param[in]  force_restart True to discard any prior split-part checkpoint for this block.
    @return     Updated Audio Blocks payload.
    @exception  RuntimeError Raised when VoiceWeaver does not expose downloadable audio.
    @exception  OperationCancelledError Raised when cancellation is requested.
    """
    base_url = str(runtime_settings.get("base_url", "")).strip()
    timeout_seconds = int(runtime_settings.get("timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
    voice_clone_prompt = clone_profile.get("voice_clone_prompt")
    if voice_clone_prompt in (None, ""):
        raise RuntimeError("Audio Blocks could not resolve the required reusable clone prompt for generation.")
    split_plan = _plan_audio_block_splits(str(audio_block.get("text", "")), generation_context)
    audio_path = _audio_artifact_path(
        project_root,
        str(audio_block.get("speech_block_id", "")).strip(),
    )
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    part_paths = _existing_part_paths(
        project_root,
        audio_block,
        split_plan,
        force_restart,
        next_split_part_index=next_split_part_index,
    )
    if force_restart:
        _delete_audio_block_artifacts(project_root, audio_block)
    runtime_result_summary = ""
    _AUDIO_BLOCKS_LOGGER.info(
        "Generating audio block chunk_id=%s sequence_index=%s parts=%s force_restart=%s",
        str(audio_block.get("chunk_id", "")).strip(),
        int(audio_block.get("sequence_index", 0)),
        len(split_plan["parts"]),
        force_restart,
    )
    for part_index in range(len(part_paths), len(split_plan["parts"])):
        part_text = str(split_plan["parts"][part_index])
        raise_if_cancelled(cancel_requested)
        _AUDIO_BLOCKS_LOGGER.debug(
            "Generating audio block part chunk_id=%s sequence_index=%s part=%s/%s",
            str(audio_block.get("chunk_id", "")).strip(),
            int(audio_block.get("sequence_index", 0)),
            part_index + 1,
            len(split_plan["parts"]),
        )
        voiceweaver_runtime_service.generate_voice_clone_from_prompt(
            base_url,
            voice_clone_prompt,
            str(generation_context.get("voice_language", "")),
            part_text,
            model_parameters={"max_new_tokens": _part_generation_token_budget(part_text, generation_context)},
            timeout_seconds=timeout_seconds,
        )
        final_status = voiceweaver_runtime_service.wait_for_terminal_operation(
            base_url,
            timeout_seconds=timeout_seconds,
            cancel_requested=cancel_requested,
        )
        final_operation = final_status.get("operation", {})
        if (
            not isinstance(final_operation, dict)
            or str(final_operation.get("status", "")).strip().lower() != "completed"
        ):
            raise RuntimeError(voiceweaver_runtime_service.operation_failed_message(final_status))
        final_result = final_status.get("result", {})
        if not isinstance(final_result, dict) or not bool(final_result.get("available", False)):
            raise RuntimeError("VoiceWeaver finished the request but did not report downloadable audio.")
        audio_bytes = voiceweaver_runtime_service.download_generated_audio(
            base_url,
            timeout_seconds=timeout_seconds,
        )
        _validate_wav_bytes(audio_bytes)
        if len(split_plan["parts"]) == 1:
            write_bytes_atomic(audio_path, audio_bytes)
        else:
            part_path = _audio_part_artifact_path(
                project_root,
                str(audio_block.get("speech_block_id", "")).strip(),
                part_index,
            )
            part_path.parent.mkdir(parents=True, exist_ok=True)
            write_bytes_atomic(part_path, audio_bytes)
            part_paths.append(part_path)
        runtime_result_summary = str(final_result.get("summary", "")).strip()
        if len(split_plan["parts"]) > 1 and callable(checkpoint_callback):
            checkpoint_callback(
                {
                    **dict(audio_block),
                    "split_part_count": len(split_plan["parts"]),
                    "generation_fingerprint": _build_audio_block_fingerprint(
                        audio_block,
                        generation_context,
                    ),
                    "split_plan_fingerprint": _split_plan_fingerprint(split_plan),
                    "runtime_result_summary": runtime_result_summary,
                },
                part_index + 1,
            )
    if len(split_plan["parts"]) > 1:
        _stitch_wav_parts(part_paths, audio_path)
        for part_path in part_paths:
            if part_path.is_file():
                part_path.unlink()
    generated_at = _utc_now_iso()
    audio_duration_seconds = _wav_duration_seconds(audio_path)
    _AUDIO_BLOCKS_LOGGER.info(
        "Generated audio block chunk_id=%s sequence_index=%s audio_path=%s",
        str(audio_block.get("chunk_id", "")).strip(),
        int(audio_block.get("sequence_index", 0)),
        relative_to_project(project_root, audio_path),
    )
    return {
        **dict(audio_block),
        "audio_can_play": True,
        "audio_duration_seconds": audio_duration_seconds,
        "voice_language": str(generation_context.get("voice_language", "")).strip(),
        "prompt_format": _optional_string(clone_profile.get("prompt_format")),
        "split_part_count": len(split_plan["parts"]),
        "model_token_budget": int(generation_context.get("model_token_budget", 0)),
        "model_audio_seconds_budget": float(generation_context.get("model_audio_seconds_budget", 0.0)),
        "generation_fingerprint": _build_audio_block_fingerprint(audio_block, generation_context),
        "split_plan_fingerprint": _split_plan_fingerprint(split_plan),
        "generated": generated_at,
        "approved": None,
        "approved_at": None,
        "generated_at": generated_at,
        "runtime_result_summary": runtime_result_summary,
    }


def _generate_scene_ambience_audio_block(
    project_root: Path,
    audio_block: AudioBlockPayload,
    generation_context: dict[str, object],
    runtime_settings: dict[str, object],
    cancel_requested=None,
) -> AudioBlockPayload:
    """
    @brief      Generate one Scene Ambience WAV and canonical Audio Blocks metadata.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_block Persisted Scene Ambience Audio Blocks entry.
    @param[in]  generation_context Validated generation-context payload.
    @param[in]  runtime_settings Runtime connection plus discovered-model settings.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Updated Audio Blocks payload.
    @exception  RuntimeError Raised when VoiceWeaver does not expose downloadable audio.
    @exception  OperationCancelledError Raised when cancellation is requested.
    """
    base_url = str(runtime_settings.get("base_url", "")).strip()
    timeout_seconds = int(runtime_settings.get("timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
    sound_prompt = str(audio_block.get("sound_prompt", audio_block.get("text", ""))).strip()
    if not sound_prompt:
        raise RuntimeError("Scene Ambience Audio generation requires a non-empty sound prompt.")
    duration_seconds = (
        _optional_float(runtime_settings.get("scene_ambience_duration_seconds"))
        or _optional_float(audio_block.get("duration_seconds"))
        or float(config.DEFAULT_SCENE_AMBIENCE_DURATION_SECONDS)
    )
    guidance_scale = _optional_float(runtime_settings.get("scene_ambience_guidance_scale"))
    if guidance_scale is None:
        guidance_scale = config.DEFAULT_SCENE_AMBIENCE_GUIDANCE_SCALE
    seed_value = runtime_settings.get("scene_ambience_seed")
    seed = None if seed_value is None else _optional_int(seed_value, config.DEFAULT_SCENE_AMBIENCE_SEED)
    audio_path = _audio_artifact_path(
        project_root,
        str(audio_block.get("speech_block_id", "")).strip(),
    )
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    _delete_audio_block_artifacts(project_root, audio_block)
    raise_if_cancelled(cancel_requested)
    _AUDIO_BLOCKS_LOGGER.info(
        "Generating Scene Ambience audio block chunk_id=%s sequence_index=%s duration_seconds=%.2f",
        str(audio_block.get("chunk_id", "")).strip(),
        int(audio_block.get("sequence_index", 0)),
        duration_seconds,
    )
    voiceweaver_runtime_service.generate_sound_prompt(
        base_url,
        sound_prompt,
        negative_prompt=str(audio_block.get("negative_prompt", "")).strip(),
        duration_seconds=duration_seconds,
        guidance_scale=guidance_scale,
        num_inference_steps=_optional_int(
            runtime_settings.get("scene_ambience_num_inference_steps"),
            config.DEFAULT_SCENE_AMBIENCE_NUM_INFERENCE_STEPS,
        ),
        seed=seed,
        timeout_seconds=timeout_seconds,
    )
    final_status = voiceweaver_runtime_service.wait_for_terminal_operation(
        base_url,
        timeout_seconds=timeout_seconds,
        cancel_requested=cancel_requested,
    )
    final_operation = final_status.get("operation", {})
    if not isinstance(final_operation, dict) or str(final_operation.get("status", "")).strip().lower() != "completed":
        raise RuntimeError(voiceweaver_runtime_service.operation_failed_message(final_status))
    final_result = final_status.get("result", {})
    if not isinstance(final_result, dict) or not bool(final_result.get("available", False)):
        raise RuntimeError("VoiceWeaver finished the sound request but did not report downloadable audio.")
    audio_bytes = voiceweaver_runtime_service.download_generated_audio(
        base_url,
        timeout_seconds=timeout_seconds,
    )
    _validate_wav_bytes(audio_bytes)
    write_bytes_atomic(audio_path, audio_bytes)
    generated_at = _utc_now_iso()
    _AUDIO_BLOCKS_LOGGER.info(
        "Generated Scene Ambience audio block chunk_id=%s sequence_index=%s audio_path=%s",
        str(audio_block.get("chunk_id", "")).strip(),
        int(audio_block.get("sequence_index", 0)),
        relative_to_project(project_root, audio_path),
    )
    return {
        **dict(audio_block),
        "duration_seconds": duration_seconds,
        "metadata_only": False,
        "special_block_status": None,
        "audio_can_play": True,
        "audio_duration_seconds": _wav_duration_seconds(audio_path),
        "voice_language": None,
        "prompt_format": "sound_prompt",
        "split_part_count": 1,
        "model_token_budget": None,
        "model_audio_seconds_budget": None,
        "generation_fingerprint": _build_audio_block_fingerprint(audio_block, generation_context),
        "split_plan_fingerprint": None,
        "generated": generated_at,
        "approved": None,
        "approved_at": None,
        "generated_at": generated_at,
        "runtime_result_summary": str(final_result.get("summary", "")).strip(),
    }


def _plan_audio_block_splits(text: str, generation_context: dict[str, object]) -> dict[str, object]:
    """
    @brief      Split one Audio Blocks text into generation parts that fit the resolved model budget.
    @details    The budget word count is a packing target, not a cut: a sentence longer than it is
                emitted whole while it stays inside the hard word count, because resuming a
                sentence in a fresh generation restarts its prosody mid-thought. Clause and
                word-group cuts survive only for text past the hard count.
    @param[in]  text Original speech-block text.
    @param[in]  generation_context Validated generation-context payload with model budget fields.
    @return     Split plan containing ordered text parts and strategy name.
    @exception  None
    """
    normalized_text = _normalize_split_text(text)
    if not normalized_text:
        return {"parts": [""], "strategy": "single"}
    max_words = max(1, int(float(generation_context.get("split_audio_seconds_budget", 0.0)) * _WORDS_PER_AUDIO_SECOND))
    hard_max_words = max(max_words, int(generation_context.get("hard_word_count", 0) or 0))
    word_count = _estimated_word_count(normalized_text)
    if word_count <= max_words:
        return {"parts": [normalized_text], "strategy": "single"}
    sentence_parts = _pack_text_units(re.split(r"(?<=[.!?])\s+", normalized_text), max_words, hard_max_words)
    if len(sentence_parts) > 1:
        return {"parts": sentence_parts, "strategy": "sentence"}
    if word_count <= hard_max_words:
        return {"parts": [normalized_text], "strategy": "single"}
    clause_parts = _pack_text_units(re.split(r"(?<=[,;:])\s+", normalized_text), hard_max_words, hard_max_words)
    if len(clause_parts) > 1:
        return {"parts": clause_parts, "strategy": "clause"}
    return {"parts": _split_by_word_groups(normalized_text, hard_max_words), "strategy": "word_group"}


def _part_generation_token_budget(part_text: str, generation_context: dict[str, object]) -> int:
    """
    @brief      Resolve the generation-token ceiling for one text part about to be sent.
    @details    The runtime stops at whatever ceiling it is handed, finished or not, so a part the
                splitter deliberately kept longer than the operator target needs a ceiling sized to
                it or its closing words are lost. Parts inside the target keep the target.
    @param[in]  part_text Text about to be generated.
    @param[in]  generation_context Validated generation-context payload with model budget fields.
    @return     Token ceiling for this part, never above the reported hard maximum.
    @exception  None
    """
    operator_token_budget = max(1, int(generation_context.get("model_token_budget", 0)))
    hard_token_maximum = max(operator_token_budget, int(generation_context.get("hard_token_maximum", 0) or 0))
    seconds_per_token = float(generation_context.get("approx_audio_seconds_per_token", 0.0))
    words_per_token = seconds_per_token * _SPLIT_SAFETY_FACTOR * _WORDS_PER_AUDIO_SECOND
    if words_per_token <= 0.0:
        return operator_token_budget
    required_tokens = ceil(_estimated_word_count(part_text) / words_per_token)
    return max(operator_token_budget, min(required_tokens, hard_token_maximum))


def _pack_text_units(units: list[str], max_words: int, hard_max_words: int) -> list[str]:
    """
    @brief      Pack text units into budget-sized generation parts.
    @param[in]  units Ordered text units.
    @param[in]  max_words Preferred maximum estimated words per generated part.
    @param[in]  hard_max_words Word count past which a single unit cannot be sent whole.
    @return     Packed text parts, or an empty list when one unit exceeds the hard maximum.
    @exception  None
    """
    parts: list[str] = []
    current_units: list[str] = []
    for unit in (_normalize_split_text(item) for item in units):
        if not unit:
            continue
        if _estimated_word_count(unit) > hard_max_words:
            return []
        candidate = _normalize_split_text(" ".join([*current_units, unit]))
        if current_units and _estimated_word_count(candidate) > max_words:
            parts.append(_normalize_split_text(" ".join(current_units)))
            current_units = [unit]
        else:
            current_units.append(unit)
    if current_units:
        parts.append(_normalize_split_text(" ".join(current_units)))
    return parts


def _split_by_word_groups(text: str, max_words: int) -> list[str]:
    """
    @brief      Split one overlong text by deterministic word groups.
    @param[in]  text Original normalized text.
    @param[in]  max_words Maximum words per part.
    @return     Word-group split parts.
    @exception  None
    """
    words = text.split()
    return [" ".join(words[index : index + max_words]) for index in range(0, len(words), max_words)] or [""]


def _normalize_split_text(text: str) -> str:
    """
    @brief      Normalize whitespace for split planning and generation requests.
    @param[in]  text Candidate speech-block text.
    @return     Text with collapsed whitespace.
    @exception  None
    """
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _estimated_word_count(text: str) -> int:
    """
    @brief      Estimate spoken length using whitespace-delimited words.
    @param[in]  text Candidate speech text.
    @return     Estimated word count.
    @exception  None
    """
    return len([word for word in str(text or "").split() if word])


def _existing_part_paths(
    project_root: Path,
    audio_block: AudioBlockPayload,
    split_plan: dict[str, object],
    force_restart: bool,
    next_split_part_index: int = 0,
) -> list[Path]:
    """
    @brief      Resolve completed split-part paths that can be reused for resume.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_block Persisted Audio Blocks entry.
    @param[in]  split_plan Current split plan.
    @param[in]  force_restart True to ignore persisted part checkpoints.
    @param[in]  next_split_part_index Persisted next split part to generate.
    @return     Existing part paths in completed order.
    @exception  None
    """
    if force_restart or len(split_plan["parts"]) <= 1:
        return []
    persisted_split_fingerprint = str(audio_block.get("split_plan_fingerprint", "") or "").strip()
    if persisted_split_fingerprint != _split_plan_fingerprint(split_plan):
        return []
    persisted_part_count = _optional_int(audio_block.get("split_part_count"), 0) or 0
    planned_part_count = len(split_plan["parts"])
    if persisted_part_count <= 1 or persisted_part_count != planned_part_count:
        return []
    if next_split_part_index <= 0 or next_split_part_index > planned_part_count:
        return []
    speech_block_id = str(audio_block.get("speech_block_id", "")).strip()
    existing_paths: list[Path] = []
    for part_index in range(next_split_part_index):
        expected_path = _audio_part_artifact_path(project_root, speech_block_id, part_index)
        if not expected_path.is_file() or not _is_valid_wav_path(expected_path):
            break
        existing_paths.append(expected_path)
    return existing_paths


def _split_plan_fingerprint(split_plan: dict[str, object]) -> str:
    """
    @brief      Build one stable fingerprint for a current split-generation plan.
    @param[in]  split_plan Split plan payload.
    @return     Hex-encoded split plan fingerprint.
    @exception  None
    """
    return hashlib.sha1(  # noqa: S324
        json.dumps(
            {
                "parts": [str(part) for part in split_plan.get("parts", [])],
                "strategy": str(split_plan.get("strategy", "")),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _delete_audio_block_artifacts(project_root: Path, audio_block: AudioBlockPayload) -> None:
    """
    @brief      Delete previous generated artifacts for one block before a forced regeneration.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_block Current Audio Blocks entry.
    @return     None.
    @exception  None
    """
    speech_block_id = str(audio_block.get("speech_block_id", "")).strip()
    if not speech_block_id:
        return
    audio_path = _audio_artifact_path(project_root, speech_block_id)
    if audio_path.is_file():
        audio_path.unlink()
    for part_index in range(max(_optional_int(audio_block.get("split_part_count"), 1) or 1, 1)):
        part_path = _audio_part_artifact_path(project_root, speech_block_id, part_index)
        if part_path.is_file():
            part_path.unlink()


def _audio_block_matches_invalidation(
    audio_block: AudioBlockPayload,
    speech_block_ids: set[str],
    voice_target_ids: set[str],
) -> bool:
    """
    @brief      Return whether one Audio Block should be invalidated by exact Speech Block or voice target ids.
    @param[in]  audio_block Candidate Audio Blocks payload.
    @param[in]  speech_block_ids Affected Speech Block identifiers.
    @param[in]  voice_target_ids Affected voice target identifiers.
    @return     True when the block matches either affected identity set.
    @exception  None
    """
    return (
        str(audio_block.get("speech_block_id", "")).strip() in speech_block_ids
        or str(audio_block.get("voice_target_id", "")).strip() in voice_target_ids
    )


def _cleared_audio_fields() -> dict[str, object]:
    """
    @brief      Build cleared generated-audio fields for one invalidated Audio Block.
    @return     Cleared Audio Blocks field mapping.
    @exception  None
    """
    return {
        "audio_can_play": False,
        "audio_duration_seconds": None,
        "generated": False,
        "approved": False,
        "runtime_result_summary": "",
        "split_part_count": 1,
        "generation_fingerprint": None,
        "split_plan_fingerprint": None,
    }


def _build_audio_block_fingerprint(
    audio_block: AudioBlockPayload,
    generation_context: dict[str, object] | None,
) -> str | None:
    """
    @brief      Build one stable generation fingerprint for a single Audio Block.
    @param[in]  audio_block Current Speech Block-aligned Audio Block payload.
    @param[in]  generation_context Validated Audio Blocks generation context.
    @return     Hex-encoded fingerprint, or `None` when context is unavailable.
    @exception  None
    """
    if not isinstance(generation_context, dict):
        return None
    voice_target_id = str(audio_block.get("voice_target_id", "")).strip()
    voice_target = next(
        (
            dict(target)
            for target in generation_context.get("voice_targets", [])
            if isinstance(target, dict) and str(target.get("voice_target_id", "")).strip() == voice_target_id
        ),
        {},
    )
    sample_metadata = dict(voice_target.get("sample_metadata", {})) if isinstance(voice_target, dict) else {}
    fingerprint_payload = {
        "fingerprint_version": _AUDIO_BLOCK_FINGERPRINT_VERSION,
        "speech_block_id": str(audio_block.get("speech_block_id", "")).strip(),
        "sequence_index": int(audio_block.get("sequence_index", 0)),
        "chunk_id": str(audio_block.get("chunk_id", "")).strip(),
        "speaker_id": str(audio_block.get("speaker_id", "")).strip(),
        "speaker_display_name": str(audio_block.get("speaker_display_name", "")).strip(),
        "content_kind": str(audio_block.get("content_kind", "")).strip(),
        "metadata_only": bool(audio_block.get("metadata_only", False)),
        "pause_duration_ms": _optional_int(audio_block.get("pause_duration_ms"), None),
        "text": str(audio_block.get("text", "")),
        "sound_prompt": str(audio_block.get("sound_prompt", "")),
        "negative_prompt": str(audio_block.get("negative_prompt", "")),
        "duration_seconds": _optional_float(audio_block.get("duration_seconds")),
        "ambience_position": str(audio_block.get("ambience_position", "")).strip(),
        "voice_target_id": voice_target_id,
        "voice_assignment_mode": str(generation_context.get("voice_assignment_mode", "")).strip(),
        "original_language": str(generation_context.get("original_language", "")).strip(),
        "voice_language": str(generation_context.get("voice_language", "")).strip(),
        "clone_model_id": str(generation_context.get("clone_model_id", "")).strip(),
        "generate_scene_ambience_audio": bool(generation_context.get("generate_scene_ambience_audio", False)),
        "sound_model_id": str(generation_context.get("sound_model_id", "")).strip(),
        "scene_ambience_duration_seconds": _optional_float(generation_context.get("scene_ambience_duration_seconds")),
        "model_token_budget": int(generation_context.get("model_token_budget", 0)),
        "model_audio_seconds_budget": float(generation_context.get("model_audio_seconds_budget", 0.0)),
        "split_audio_seconds_budget": float(generation_context.get("split_audio_seconds_budget", 0.0)),
        "model_budget_source": str(generation_context.get("model_budget_source", "")).strip(),
        "sample_fingerprint": str(voice_target.get("sample_fingerprint", "")).strip(),
        "sample_text": str(voice_target.get("sample_text", "")).strip(),
        "sample_source_model_id": str(sample_metadata.get("source_model_id", "")).strip(),
    }
    return hashlib.sha1(  # noqa: S324
        json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _special_block_status(content_kind: str) -> str | None:
    """
    @brief      Resolve the implementation status for a metadata-only special block.
    @param[in]  content_kind Speech Block content-kind token.
    @return     Implementation status token or `None` for normal speech blocks.
    @exception  None
    """
    normalized_kind = str(content_kind).strip()
    if normalized_kind == speech_blocks_service.CONTENT_KIND_PAUSE:
        return _SPECIAL_BLOCK_STATUS_IMPLEMENTED
    if normalized_kind in {
        speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
        speech_blocks_service.CONTENT_KIND_INDICATION,
    }:
        return _SPECIAL_BLOCK_STATUS_NOT_IMPLEMENTED
    return None


def _metadata_only_summary(special_block_status: str | None) -> str:
    """
    @brief      Build the persisted runtime summary for one metadata-only block.
    @param[in]  special_block_status Special-block implementation status.
    @return     Operator-readable metadata-only summary.
    @exception  None
    """
    if special_block_status == _SPECIAL_BLOCK_STATUS_IMPLEMENTED:
        return "Metadata-only pause block; silence is added during Audio Assembly."
    if special_block_status == _SPECIAL_BLOCK_STATUS_NOT_IMPLEMENTED:
        return "Special block functionality is not implemented; no speech audio generated."
    return ""


def _initialize_audio_blocks(
    speech_blocks: list[dict[str, object]],
    voice_assignment_mode: str = config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
) -> list[AudioBlockPayload]:
    """
    @brief      Build the initial Audio Blocks manifest from the persisted Speech Blocks list.
    @param[in]  speech_blocks Persisted Speech Blocks payload list.
    @param[in]  voice_assignment_mode Project-local voice assignment mode.
    @return     Initial ordered Audio Blocks payload list.
    @exception  None
    """
    audio_blocks: list[AudioBlockPayload] = []
    for speech_block in speech_blocks_service.sort_speech_blocks(speech_blocks):
        speaker_display_name = str(speech_block.get("speaker_display_name", "")).strip() or "Narrator"
        content_kind = str(speech_block.get("content_kind", speech_blocks_service.CONTENT_KIND_NARRATION)).strip()
        metadata_only = _is_metadata_only_speech_block(speech_block)
        special_block_status = _special_block_status(content_kind)
        pause_duration_ms = (
            speech_blocks_service.pause_duration_ms(speech_block.get("text", ""))
            if content_kind == speech_blocks_service.CONTENT_KIND_PAUSE
            else None
        )
        speech_block_approved = _speech_block_is_approved(speech_block)
        metadata_only_completed = metadata_only and (
            speech_block_approved or content_kind == speech_blocks_service.CONTENT_KIND_PAUSE
        )
        metadata_only_timestamp = _utc_now_iso() if metadata_only_completed else None
        audio_duration_seconds = None
        if content_kind == speech_blocks_service.CONTENT_KIND_PAUSE and pause_duration_ms is not None:
            audio_duration_seconds = pause_duration_ms / 1000.0
        audio_blocks.append(
            {
                "speech_block_id": str(speech_block.get("speech_block_id", "")).strip(),
                "sequence_index": int(speech_block.get("sequence_index", 0)),
                "chunk_id": str(speech_block.get("chunk_id", "")).strip(),
                "speaker_id": str(speech_block.get("speaker_id", "")).strip(),
                "speaker_display_name": speaker_display_name,
                "normalized_speaker_name": normalize_speaker_name(speaker_display_name),
                "content_kind": content_kind,
                "metadata_only": metadata_only,
                "special_block_status": special_block_status,
                "pause_duration_ms": pause_duration_ms,
                "speech_block_approved": speech_block_approved,
                "text": str(speech_block.get("text", "")),
                "sound_prompt": str(speech_block.get("sound_prompt", speech_block.get("text", ""))).strip()
                if content_kind == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
                else "",
                "negative_prompt": str(speech_block.get("negative_prompt", "")).strip(),
                "duration_seconds": _optional_float(speech_block.get("duration_seconds")),
                "ambience_position": str(speech_block.get("ambience_position", "")).strip(),
                "voice_target_id": _voice_target_id_for_block(speech_block, voice_assignment_mode),
                "voice_source_kind": _voice_source_kind_for_block(speech_block, voice_assignment_mode),
                "audio_duration_seconds": audio_duration_seconds,
                "generated": metadata_only_timestamp,
                "approved": metadata_only_timestamp,
                "approved_at": None,
                "generated_at": None,
                "runtime_result_summary": _metadata_only_summary(special_block_status),
                "split_part_count": 1,
                "model_token_budget": None,
                "model_audio_seconds_budget": None,
                "generation_fingerprint": None,
                "split_plan_fingerprint": None,
            }
        )
    return audio_blocks


def _merge_existing_audio_blocks(
    speech_blocks: list[dict[str, object]],
    existing_audio_blocks: list[AudioBlockPayload],
    voice_assignment_mode: str = config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
    generation_context: dict[str, object] | None = None,
    project_root: Path | None = None,
) -> list[AudioBlockPayload]:
    """
    @brief      Merge persisted Audio Blocks state onto the current Speech Blocks snapshot.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  existing_audio_blocks Persisted Audio Blocks payload list.
    @param[in]  voice_assignment_mode Project-local voice assignment mode.
    @return     Merged ordered Audio Blocks payload list.
    @exception  None
    """
    existing_by_id = {
        str(block.get("speech_block_id", "")).strip(): _normalize_persisted_audio_block(block)
        for block in existing_audio_blocks
    }
    merged_blocks = _initialize_audio_blocks(speech_blocks, voice_assignment_mode)
    for block in merged_blocks:
        existing_block = existing_by_id.get(str(block.get("speech_block_id", "")).strip())
        current_fingerprint = _build_audio_block_fingerprint(block, generation_context) if generation_context else None
        if current_fingerprint:
            block["generation_fingerprint"] = current_fingerprint
        if existing_block is None:
            continue
        if current_fingerprint and str(existing_block.get("generation_fingerprint", "") or "") != current_fingerprint:
            if _audio_block_has_reusable_audio(existing_block, project_root):
                existing_block["generation_fingerprint"] = current_fingerprint
            else:
                if project_root is not None:
                    _delete_audio_block_artifacts(project_root, existing_block)
                continue
        existing_generated_at = is_generated(existing_block)
        existing_approved_at = is_approved(existing_block)
        if str(block.get("content_kind", "")).strip() == speech_blocks_service.CONTENT_KIND_PAUSE and bool(
            block.get("metadata_only", False)
        ):
            existing_generated_at = existing_generated_at or is_generated(block)
            existing_approved_at = existing_approved_at or is_approved(block)
        block.update(
            {
                "metadata_only": bool(existing_block.get("metadata_only", block.get("metadata_only", False))),
                "audio_can_play": _persisted_audio_can_play(existing_block),
                "audio_duration_seconds": existing_block.get("audio_duration_seconds")
                if existing_block.get("audio_duration_seconds") is not None
                else block.get("audio_duration_seconds"),
                "pause_duration_ms": existing_block.get("pause_duration_ms"),
                "special_block_status": existing_block.get("special_block_status") or block.get("special_block_status"),
                "generated": existing_generated_at,
                "approved": existing_approved_at,
                "approved_at": None,
                "generated_at": None,
                "runtime_result_summary": str(existing_block.get("runtime_result_summary", "")),
                "sound_prompt": existing_block.get("sound_prompt") or block.get("sound_prompt"),
                "negative_prompt": existing_block.get("negative_prompt") or block.get("negative_prompt"),
                "duration_seconds": existing_block.get("duration_seconds")
                if existing_block.get("duration_seconds") is not None
                else block.get("duration_seconds"),
                "ambience_position": existing_block.get("ambience_position") or block.get("ambience_position"),
                "split_part_count": int(existing_block.get("split_part_count", 1)),
                "model_token_budget": existing_block.get("model_token_budget"),
                "model_audio_seconds_budget": existing_block.get("model_audio_seconds_budget"),
                "generation_fingerprint": current_fingerprint or existing_block.get("generation_fingerprint"),
                "split_plan_fingerprint": existing_block.get("split_plan_fingerprint"),
            }
        )
    return _apply_scene_ambience_audio_policy(merged_blocks, generation_context)


def _apply_scene_ambience_audio_policy(
    audio_blocks: list[AudioBlockPayload],
    generation_context: dict[str, object] | None,
) -> list[AudioBlockPayload]:
    """
    @brief      Apply Scene Ambience Audio generation policy to merged Audio Blocks.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @param[in]  generation_context Optional validated generation context.
    @return     Updated Audio Blocks payload list.
    @exception  None
    """
    if not generation_context:
        return audio_blocks
    generate_scene_ambience_audio = bool(generation_context.get("generate_scene_ambience_audio", False))
    updated_blocks: list[AudioBlockPayload] = []
    for audio_block in audio_blocks:
        block = dict(audio_block)
        if str(block.get("content_kind", "")).strip() != speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE:
            updated_blocks.append(block)
            continue
        fixed_duration_seconds = _optional_float(
            generation_context.get("scene_ambience_duration_seconds")
        ) or _optional_float(block.get("duration_seconds"))
        if fixed_duration_seconds is not None:
            block["duration_seconds"] = fixed_duration_seconds
        if generate_scene_ambience_audio:
            owns_generated_audio = is_generated(block) and not bool(block.get("metadata_only", False))
            block["metadata_only"] = False
            block["special_block_status"] = None
            if not owns_generated_audio:
                block["generated"] = None
                block["approved"] = None
                block["generated_at"] = None
                block["approved_at"] = None
                block["audio_can_play"] = False
                block["runtime_result_summary"] = ""
        else:
            owns_generated_audio = is_generated(block) and not bool(block.get("metadata_only", False))
            if owns_generated_audio:
                block["special_block_status"] = None
                block["audio_can_play"] = _persisted_audio_can_play(block)
            else:
                block["metadata_only"] = True
                block["audio_can_play"] = False
                block["special_block_status"] = _SPECIAL_BLOCK_STATUS_NOT_IMPLEMENTED
                block["runtime_result_summary"] = _metadata_only_summary(_SPECIAL_BLOCK_STATUS_NOT_IMPLEMENTED)
        updated_blocks.append(block)
    return updated_blocks


def _audio_block_has_reusable_audio(audio_block: AudioBlockPayload, project_root: Path | None = None) -> bool:
    """
    @brief      Return whether one Audio Blocks entry already has generated audio that should not be regenerated.
    @param[in]  audio_block Audio Blocks entry to inspect.
    @param[in]  project_root Optional active project root for WAV validation.
    @return     True when the entry is generated and its current audio artifact is reusable.
    @exception  None
    """
    if not is_generated(audio_block):
        return False
    if bool(audio_block.get("metadata_only", False)):
        return True
    if project_root is None:
        return True
    return _audio_block_owns_real_artifact(project_root, audio_block, require_valid=True)


def _apply_model_budget_to_block(
    audio_block: AudioBlockPayload,
    generation_context: dict[str, object],
) -> AudioBlockPayload:
    """
    @brief      Attach the resolved clone-model budget metadata to one Audio Blocks entry.
    @param[in]  audio_block Audio Blocks entry to update.
    @param[in]  generation_context Validated generation-context payload.
    @return     Updated Audio Blocks entry.
    @exception  None
    """
    return {
        **dict(audio_block),
        "model_token_budget": int(generation_context.get("model_token_budget", 0)),
        "model_audio_seconds_budget": float(generation_context.get("model_audio_seconds_budget", 0.0)),
        "generation_fingerprint": _build_audio_block_fingerprint(audio_block, generation_context),
    }


def _persist_report_update(
    project_root: Path,
    audio_blocks: list[AudioBlockPayload],
    clone_profiles: list[VoiceCloneProfilePayload] | None = None,
) -> AudioBlocksReportPayload:
    """
    @brief      Persist one document update after approvals or single-block regeneration.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_blocks Updated Audio Blocks payload list.
    @param[in]  clone_profiles Optional updated direct-clone source profile list.
    @return     Updated projected report payload.
    @exception  None
    """
    document = load_audio_blocks_document(project_root) or _empty_audio_blocks_document()
    checkpoint = document.get("checkpoint") if isinstance(document.get("checkpoint"), dict) else {}
    current_clone_profiles = load_voice_clone_profiles(project_root) if clone_profiles is None else clone_profiles
    total_block_count = len(speech_blocks_service.load_speech_blocks(project_root)) or len(audio_blocks)
    stage_status = _derived_stage_status(total_block_count, audio_blocks)
    return _persist_document(
        project_root,
        audio_blocks,
        current_clone_profiles,
        status=(
            AUDIO_BLOCKS_STAGE_COMPLETED
            if stage_status == AUDIO_BLOCKS_STAGE_COMPLETED
            else AUDIO_BLOCKS_STAGE_IN_PROGRESS
        ),
        voice_language=str(document.get("voice_language", "")),
        input_fingerprint=str(document.get("input_fingerprint", "")),
        run_token=str(checkpoint.get("run_token", "")),
        current_phase=str(checkpoint.get("current_phase", _GENERATE_PHASE)).strip() or _GENERATE_PHASE,
        current_block_id=_operation_optional_string(checkpoint.get("current_block_id")),
        next_speech_block_index=_checkpoint_int(checkpoint, "next_speech_block_index", len(audio_blocks)),
        total_block_count=total_block_count,
    )


def _operation_optional_string(value: object) -> str | None:
    """
    @brief      Normalize one optional operation string and reject null-like persisted text.
    @param[in]  value Candidate persisted value.
    @return     Normalized string or `None`.
    @exception  None
    """
    normalized_value = _optional_string(value)
    if normalized_value is None or operation_runtime_service.is_missing_runtime_value(normalized_value):
        return None
    return normalized_value


def _persist_split_checkpoint(
    project_root: Path,
    generation_context: dict[str, object],
    audio_blocks: list[AudioBlockPayload],
    clone_profiles: list[VoiceCloneProfilePayload],
    checkpoint_block: AudioBlockPayload,
    active_block_index: int,
    next_split_part_index: int,
    started_at: str,
    next_generation_order_index: int | None = None,
) -> None:
    """
    @brief      Persist a resumable checkpoint after one split part finishes.
    @param[in]  project_root Active project root folder.
    @param[in]  generation_context Validated generation-context payload.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @param[in]  clone_profiles Current persisted clone profile list.
    @param[in]  checkpoint_block Current partially generated Audio Blocks entry.
    @param[in]  active_block_index Zero-based active speech-block index.
    @param[in]  next_split_part_index Next split part to generate.
    @param[in]  started_at Operation start timestamp.
    @param[in]  next_generation_order_index Optional next generation-order index.
    @return     None.
    @exception  None
    """
    checkpoint_blocks = list(audio_blocks)
    checkpoint_blocks[active_block_index] = _normalize_persisted_audio_block(dict(checkpoint_block))
    _persist_document(
        project_root,
        checkpoint_blocks,
        clone_profiles,
        status="running",
        voice_language=str(generation_context["voice_language"]),
        input_fingerprint=str(generation_context["input_fingerprint"]),
        run_token=started_at,
        current_phase=_GENERATE_PHASE,
        current_block_id=str(checkpoint_block.get("speech_block_id", "")).strip(),
        next_speech_block_index=(
            active_block_index if next_generation_order_index is None else next_generation_order_index
        ),
        next_split_part_index=next_split_part_index,
        total_block_count=len(generation_context["speech_blocks"]),
    )


def _persist_cancelled_state(
    project_root: Path,
    generation_context: dict[str, object],
    audio_blocks: list[AudioBlockPayload],
    clone_profiles: list[VoiceCloneProfilePayload],
    started_at: str,
    current_phase: str,
    current_block_id: str | None,
    next_speech_block_index: int,
    next_split_part_index: int = 0,
) -> None:
    """
    @brief      Persist a resumable cancelled Audio Blocks operation state.
    @param[in]  project_root Active project root folder.
    @param[in]  generation_context Validated generation-context payload.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @param[in]  clone_profiles Current persisted clone profile list.
    @param[in]  started_at Operation start timestamp.
    @param[in]  current_phase Current resumable phase token.
    @param[in]  current_block_id Current block id or `None`.
    @param[in]  next_speech_block_index Next speech-block index.
    @param[in]  next_split_part_index Next split-part index inside the current block.
    @return     None.
    @exception  None
    """
    _persist_document(
        project_root,
        audio_blocks,
        clone_profiles,
        status="cancelled",
        voice_language=str(generation_context["voice_language"]),
        input_fingerprint=str(generation_context["input_fingerprint"]),
        run_token=started_at,
        current_phase=current_phase,
        current_block_id=current_block_id,
        next_speech_block_index=next_speech_block_index,
        next_split_part_index=next_split_part_index,
        total_block_count=len(generation_context["speech_blocks"]),
    )


def _empty_audio_blocks_document() -> AudioBlocksDocumentPayload:
    """
    @brief      Build one empty not-started Audio Blocks document.
    @return     Empty document payload matching the root contract.
    @exception  None
    """
    return {
        "status": AUDIO_BLOCKS_STAGE_NOT_STARTED,
        "voice_language": "",
        "input_fingerprint": "",
        "checkpoint": None,
        "blocks": [],
    }


def _persist_document(
    project_root: Path,
    audio_blocks: list[AudioBlockPayload],
    clone_profiles: list[VoiceCloneProfilePayload],
    status: str,
    voice_language: str,
    input_fingerprint: str,
    run_token: str,
    current_phase: str,
    current_block_id: str | None,
    next_speech_block_index: int,
    next_split_part_index: int = 0,
    total_block_count: int | None = None,
) -> AudioBlocksReportPayload:
    """
    @brief      Persist the authoritative Audio Blocks document and the clone-profile cache.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @param[in]  clone_profiles Current persisted direct-clone source profile list.
    @param[in]  status Persisted operation status token.
    @param[in]  voice_language Selected character-voices voice language.
    @param[in]  input_fingerprint Stable validated input fingerprint.
    @param[in]  run_token Operation start timestamp preserved in the checkpoint.
    @param[in]  current_phase Current resumable phase token.
    @param[in]  current_block_id Current generating speech-block id or `None`.
    @param[in]  next_speech_block_index Next speech-block index.
    @param[in]  next_split_part_index Next split part index for the current block.
    @param[in]  total_block_count Optional known Speech Blocks count for projections.
    @return     Projected report payload for the persisted document.
    @exception  None
    """
    document: AudioBlocksDocumentPayload = {
        "status": str(status),
        "voice_language": str(voice_language or ""),
        "input_fingerprint": str(input_fingerprint or ""),
        "checkpoint": {
            "run_token": str(run_token or ""),
            "current_phase": str(current_phase or _GENERATE_PHASE),
            "current_block_id": current_block_id,
            "next_speech_block_index": max(int(next_speech_block_index), 0),
            "next_split_part_index": max(int(next_split_part_index), 0),
        },
        "blocks": [_compact_audio_block_payload(block) for block in audio_blocks],
    }
    write_audio_blocks_document(project_root, document)
    write_operation_json_artifact(
        project_root,
        "audio_blocks",
        config.AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME,
        clone_profiles,
    )
    project_workspace_service.sync_manifest_operation_summary(
        project_root,
        "audio_blocks",
        _project_operation_state(
            project_root,
            document,
            total_block_count=total_block_count,
            prompt_count=len(clone_profiles),
        ),
        current_stage="audio_blocks_ready" if str(status) == AUDIO_BLOCKS_STAGE_COMPLETED else "speech_blocks_ready",
    )
    return _project_audio_blocks_report(
        project_root,
        document,
        total_block_count=total_block_count,
        prompt_count=len(clone_profiles),
    )


def _derived_stage_status(total_block_count: int, audio_blocks: list[AudioBlockPayload]) -> str:
    """
    @brief      Derive the Audio Blocks stage token from current counts.
    @param[in]  total_block_count Current Speech Blocks count.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @return     Derived Audio Blocks stage token.
    @exception  None
    """
    generated_block_count = _generated_count(audio_blocks)
    approved_block_count = _approved_count(audio_blocks)
    if total_block_count <= 0:
        return AUDIO_BLOCKS_STAGE_NOT_STARTED
    if approved_block_count >= total_block_count and generated_block_count >= total_block_count:
        return AUDIO_BLOCKS_STAGE_COMPLETED
    if generated_block_count > 0 or approved_block_count > 0:
        return AUDIO_BLOCKS_STAGE_IN_PROGRESS
    return AUDIO_BLOCKS_STAGE_NOT_STARTED


def _projection_counts(
    project_root: str | Path,
    document: AudioBlocksDocumentPayload,
    total_block_count: int | None,
    prompt_count: int | None,
) -> tuple[list[AudioBlockPayload], int, int]:
    """
    @brief      Resolve the shared inputs both Audio Blocks projections need.
    @param[in]  project_root Active project root folder.
    @param[in]  document Authoritative Audio Blocks document payload.
    @param[in]  total_block_count Optional known Speech Blocks count.
    @param[in]  prompt_count Optional known clone-profile count.
    @return     Tuple of document blocks, total block count, and prompt count.
    @exception  None
    """
    blocks = [dict(block) for block in document.get("blocks", []) if isinstance(block, dict)]
    resolved_total = (
        int(total_block_count)
        if total_block_count is not None
        else (len(speech_blocks_service.load_speech_blocks(project_root)) or len(blocks))
    )
    resolved_prompts = int(prompt_count) if prompt_count is not None else len(load_voice_clone_profiles(project_root))
    return blocks, resolved_total, resolved_prompts


def _project_audio_blocks_report(
    project_root: str | Path,
    document: AudioBlocksDocumentPayload,
    total_block_count: int | None = None,
    prompt_count: int | None = None,
) -> AudioBlocksReportPayload:
    """
    @brief      Project the report shape from the single Audio Blocks document.
    @param[in]  project_root Active project root folder.
    @param[in]  document Authoritative Audio Blocks document payload.
    @param[in]  total_block_count Optional known Speech Blocks count.
    @param[in]  prompt_count Optional known clone-profile count.
    @return     Projected Audio Blocks report payload.
    @exception  None
    """
    blocks, resolved_total, resolved_prompts = _projection_counts(
        project_root,
        document,
        total_block_count,
        prompt_count,
    )
    checkpoint = document.get("checkpoint") if isinstance(document.get("checkpoint"), dict) else {}
    persisted_status = str(document.get("status", "")).strip()
    stage_status = (
        persisted_status
        if persisted_status in {"running", "failed", "cancelled"}
        else _derived_stage_status(resolved_total, blocks)
    )
    return {
        "voice_language": str(document.get("voice_language", "")),
        "audio_blocks_stage_status": stage_status,
        "generated_block_count": _generated_count(blocks),
        "approved_block_count": _approved_count(blocks),
        "total_block_count": resolved_total,
        "prompt_count": max(resolved_prompts, 0),
        "current_phase": str(checkpoint.get("current_phase", "")).strip() or None,
    }


def _project_operation_state(
    project_root: str | Path,
    document: AudioBlocksDocumentPayload,
    total_block_count: int | None = None,
    prompt_count: int | None = None,
) -> OperationStatePayload:
    """
    @brief      Project the operation-state shape from the single Audio Blocks document.
    @param[in]  project_root Active project root folder.
    @param[in]  document Authoritative Audio Blocks document payload.
    @param[in]  total_block_count Optional known Speech Blocks count.
    @param[in]  prompt_count Optional known clone-profile count.
    @return     Projected Audio Blocks operation-state payload.
    @exception  None
    """
    blocks, resolved_total, resolved_prompts = _projection_counts(
        project_root,
        document,
        total_block_count,
        prompt_count,
    )
    checkpoint = document.get("checkpoint") if isinstance(document.get("checkpoint"), dict) else None
    return build_operation_state_payload(
        status=str(document.get("status", AUDIO_BLOCKS_STAGE_NOT_STARTED)),
        progress_current=_generated_count(blocks),
        progress_total=resolved_total,
        mode=_MODE,
        warning_count=0,
        metadata={
            "voice_language": str(document.get("voice_language", "")),
            "input_fingerprint": str(document.get("input_fingerprint", "")),
            "prompt_count": max(resolved_prompts, 0),
            "current_phase": str(checkpoint.get("current_phase", "")) if checkpoint else "",
            "current_block_id": checkpoint.get("current_block_id") if checkpoint else None,
        },
        resume_checkpoint=(
            {
                "run_token": str(checkpoint.get("run_token", "")),
                "next_speech_block_index": _checkpoint_int(checkpoint, "next_speech_block_index", 0),
                "next_split_part_index": _checkpoint_int(checkpoint, "next_split_part_index", 0),
            }
            if checkpoint
            else None
        ),
    )


def _checkpoint_int(checkpoint: object, field_name: str, fallback: int) -> int:
    """
    @brief      Read one non-negative integer from a persisted checkpoint mapping.
    @param[in]  checkpoint Candidate checkpoint mapping.
    @param[in]  field_name Checkpoint field name.
    @param[in]  fallback Fallback value used when the field is absent or invalid.
    @return     Non-negative integer checkpoint value.
    @exception  None
    """
    if not isinstance(checkpoint, dict):
        return max(int(fallback), 0)
    try:
        return max(int(checkpoint.get(field_name, fallback)), 0)
    except (TypeError, ValueError):
        return max(int(fallback), 0)


def _voice_target_id_for_block(
    speech_block: dict[str, object],
    voice_assignment_mode: str = config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
) -> str:
    """
    @brief      Resolve the character-voices target identifier used by one speech block.
    @param[in]  speech_block Persisted Speech Blocks payload.
    @param[in]  voice_assignment_mode Project-local voice assignment mode.
    @return     Character-voices target identifier.
    @exception  None
    """
    if (
        str(voice_assignment_mode).strip() == "same_narrator"
        or str(speech_block.get("speaker_kind", "")).strip() == speech_blocks_service.SPEAKER_KIND_NARRATOR
    ):
        return character_voices_service.TARGET_ID_NARRATOR
    return character_voices_service.character_target_id(str(speech_block.get("speaker_id", "")).strip())


def _voice_source_kind_for_block(
    speech_block: dict[str, object],
    voice_assignment_mode: str = config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
) -> str:
    """
    @brief      Resolve the voice-source kind label persisted for one audio block.
    @param[in]  speech_block Persisted Speech Blocks payload.
    @param[in]  voice_assignment_mode Project-local voice assignment mode.
    @return     Persisted voice-source kind label.
    @exception  None
    """
    return (
        "narrator_sample"
        if str(voice_assignment_mode).strip() == "same_narrator"
        or str(speech_block.get("speaker_kind", "")).strip() == speech_blocks_service.SPEAKER_KIND_NARRATOR
        else "character_sample"
    )


def _is_metadata_only_speech_block(speech_block: dict[str, object]) -> bool:
    """
    @brief      Return whether one Speech Block has no speech audio generation.
    @param[in]  speech_block Speech Blocks payload.
    @return     True for pause, background-noise, and indication blocks.
    @exception  None
    """
    return str(speech_block.get("content_kind", "")).strip() in {
        speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
        speech_blocks_service.CONTENT_KIND_PAUSE,
        speech_blocks_service.CONTENT_KIND_INDICATION,
    }


def _speech_block_is_approved(speech_block: dict[str, object]) -> bool:
    """
    @brief      Return whether one Speech Block is approved for Audio Blocks generation.
    @param[in]  speech_block Persisted Speech Blocks payload.
    @return     `True` when the Speech Block approval flag is set.
    @exception  None
    """
    return bool(speech_block.get("approved", False))


def _generated_count(audio_blocks: list[AudioBlockPayload]) -> int:
    """
    @brief      Count generated Audio Blocks entries.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @return     Number of entries with generated audio.
    @exception  None
    """
    return sum(1 for block in audio_blocks if is_generated(block))


def _audio_generation_order_indices(
    audio_blocks: list[AudioBlockPayload],
    generate_scene_ambience_audio: bool,
) -> list[int]:
    """
    @brief      Build the Audio Blocks generation order with spoken blocks before ambience in each chunk.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @param[in]  generate_scene_ambience_audio True when ambience WAV generation is enabled.
    @return     Ordered list indexes to visit during generation.
    @exception  None
    """
    if not generate_scene_ambience_audio:
        return list(range(len(audio_blocks)))
    chunk_order: list[str] = []
    indexes_by_chunk: dict[str, list[int]] = {}
    for index, audio_block in enumerate(audio_blocks):
        chunk_id = str(audio_block.get("chunk_id", "")).strip()
        if chunk_id not in indexes_by_chunk:
            indexes_by_chunk[chunk_id] = []
            chunk_order.append(chunk_id)
        indexes_by_chunk[chunk_id].append(index)
    ordered_indices: list[int] = []
    for chunk_id in chunk_order:
        chunk_indices = indexes_by_chunk[chunk_id]
        ordered_indices.extend(
            index
            for index in chunk_indices
            if str(audio_blocks[index].get("content_kind", "")).strip()
            != speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
        )
        ordered_indices.extend(
            index
            for index in chunk_indices
            if str(audio_blocks[index].get("content_kind", "")).strip()
            == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
        )
    return ordered_indices


def _first_incomplete_generation_order_index(
    audio_blocks: list[AudioBlockPayload],
    generation_order_indices: list[int],
    project_root: Path | None = None,
) -> int:
    """
    @brief      Resolve the first generation-order position that still needs generated audio.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @param[in]  generation_order_indices Ordered list indexes to inspect.
    @param[in]  project_root Optional active project root for WAV validation.
    @return     Zero-based generation-order position, or order length when complete.
    @exception  None
    """
    for order_index, block_index in enumerate(generation_order_indices):
        block = audio_blocks[block_index]
        if bool(block.get("speech_block_approved", False)) and not _audio_block_has_reusable_audio(
            block,
            project_root,
        ):
            return order_index
    return len(generation_order_indices)


def _approved_count(audio_blocks: list[AudioBlockPayload]) -> int:
    """
    @brief      Count approved Audio Blocks entries.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @return     Number of approved entries.
    @exception  None
    """
    return sum(1 for block in audio_blocks if is_approved(block))


def _compact_audio_block_payload(audio_block: AudioBlockPayload) -> AudioBlockPayload:
    """
    @brief      Build one persisted Audio Blocks entry limited to the document contract.
    @details    Identity, text, prompts, and per-run budgets are deliberately not
                persisted: they belong to the Speech Blocks document or are
                recomputed from settings on the next run.
    @param[in]  audio_block Rich in-memory Audio Blocks payload.
    @return     Persisted Audio Blocks entry.
    @exception  None
    """
    payload: AudioBlockPayload = {
        "speech_block_id": str(audio_block.get("speech_block_id", "")).strip(),
        "voice_target_id": str(audio_block.get("voice_target_id", "")).strip(),
        "generated": is_generated(audio_block),
        "approved": is_approved(audio_block),
        "audio_can_play": _persisted_audio_can_play(audio_block),
        "audio_duration_seconds": _optional_float(audio_block.get("audio_duration_seconds")),
        "generation_fingerprint": _optional_string(audio_block.get("generation_fingerprint")),
    }
    split_part_count = _optional_int(audio_block.get("split_part_count"), 1) or 1
    if split_part_count > 1:
        payload["split_part_count"] = split_part_count
        payload["split_plan_fingerprint"] = _optional_string(audio_block.get("split_plan_fingerprint"))
    return payload


def _attach_current_speech_block_fields(
    project_root: Path,
    audio_blocks: list[AudioBlockPayload],
) -> list[AudioBlockPayload]:
    """
    @brief      Attach derived Speech Blocks fields needed for ordering and display.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_blocks Persisted Audio Blocks payloads.
    @return     Audio Blocks payloads enriched from current Speech Blocks when available.
    @exception  None
    """
    speech_blocks_by_id = {
        str(block.get("speech_block_id", "")).strip(): dict(block)
        for block in speech_blocks_service.load_speech_blocks(project_root)
    }
    if not speech_blocks_by_id:
        return audio_blocks
    enriched_blocks: list[AudioBlockPayload] = []
    for audio_block in audio_blocks:
        speech_block = speech_blocks_by_id.get(str(audio_block.get("speech_block_id", "")).strip())
        if speech_block is None:
            enriched_blocks.append(audio_block)
            continue
        speaker_display_name = str(speech_block.get("speaker_display_name", "")).strip() or "Narrator"
        content_kind = str(speech_block.get("content_kind", audio_block.get("content_kind", ""))).strip()
        real_artifact_block = {**audio_block, "content_kind": content_kind, "metadata_only": False}
        if content_kind in {
            speech_blocks_service.CONTENT_KIND_PAUSE,
            speech_blocks_service.CONTENT_KIND_INDICATION,
        }:
            metadata_only = True
        elif content_kind == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE:
            metadata_only = not _audio_block_owns_real_artifact(project_root, real_artifact_block)
        else:
            metadata_only = bool(audio_block.get("metadata_only", False))
        enriched_block: AudioBlockPayload = {
            **audio_block,
            "special_block_status": _special_block_status(content_kind) if metadata_only else None,
            "pause_duration_ms": speech_blocks_service.pause_duration_ms(speech_block.get("text", ""))
            if content_kind == speech_blocks_service.CONTENT_KIND_PAUSE
            else None,
            "sequence_index": int(speech_block.get("sequence_index", 0)),
            "chunk_id": str(speech_block.get("chunk_id", audio_block.get("chunk_id", ""))).strip(),
            "speaker_id": str(speech_block.get("speaker_id", audio_block.get("speaker_id", ""))).strip(),
            "speaker_display_name": speaker_display_name,
            "normalized_speaker_name": normalize_speaker_name(speaker_display_name),
            "content_kind": content_kind,
            "metadata_only": metadata_only,
            "speech_block_approved": _speech_block_is_approved(speech_block),
            "text": str(speech_block.get("text", "")),
            "sound_prompt": str(speech_block.get("sound_prompt", speech_block.get("text", ""))).strip()
            if content_kind == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
            else "",
            "negative_prompt": str(speech_block.get("negative_prompt", "")).strip(),
            "duration_seconds": _optional_float(audio_block.get("duration_seconds"))
            if content_kind == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
            and audio_block.get("duration_seconds") is not None
            else _optional_float(speech_block.get("duration_seconds")),
            "ambience_position": str(speech_block.get("ambience_position", "")).strip(),
        }
        if metadata_only or content_kind == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE:
            enriched_block["audio_can_play"] = _filesystem_audio_can_play(project_root, enriched_block)
        enriched_blocks.append(enriched_block)
    return enriched_blocks


def _attach_derived_audio_path(project_root: Path, audio_block: AudioBlockPayload) -> AudioBlockPayload:
    """
    @brief      Attach the derived project-relative audio path to one loaded Audio Block.
    @details    The path is never persisted; it is a pure function of
                `speech_block_id` and is recomputed on every load so downstream
                consumers keep a ready-to-use relative path. It stays `None` for
                blocks that own no WAV, preserving the invariant that a set
                `audio_relative_path` means generated audio exists.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_block Audio Blocks payload enriched from Speech Blocks.
    @return     Audio Blocks payload carrying `audio_relative_path`.
    @exception  None
    """
    speech_block_id = str(audio_block.get("speech_block_id", "")).strip()
    if not speech_block_id or not _audio_block_owns_real_artifact(project_root, audio_block):
        return {**audio_block, "audio_relative_path": None}
    audio_path = _audio_artifact_path(project_root, speech_block_id)
    return {**audio_block, "audio_relative_path": relative_to_project(project_root, audio_path)}


def _normalize_persisted_audio_block(payload: dict[str, object]) -> AudioBlockPayload:
    """
    @brief      Normalize one persisted Audio Blocks entry into the in-memory payload.
    @param[in]  payload Raw persisted document entry.
    @return     Normalized Audio Blocks payload.
    @exception  None
    """
    return {
        "speech_block_id": str(payload.get("speech_block_id", "")).strip(),
        "sequence_index": int(payload.get("sequence_index", 0)),
        "chunk_id": str(payload.get("chunk_id", "")).strip(),
        "speaker_id": str(payload.get("speaker_id", "")).strip(),
        "speaker_display_name": str(payload.get("speaker_display_name", "")).strip(),
        "normalized_speaker_name": str(payload.get("normalized_speaker_name", "")).strip() or "speaker",
        "content_kind": str(payload.get("content_kind", speech_blocks_service.CONTENT_KIND_NARRATION)).strip(),
        "metadata_only": bool(payload.get("metadata_only", False)),
        "special_block_status": _optional_string(payload.get("special_block_status")),
        "pause_duration_ms": _optional_int(payload.get("pause_duration_ms"), None),
        "speech_block_approved": bool(payload.get("speech_block_approved", True)),
        "text": str(payload.get("text", "")),
        "sound_prompt": str(payload.get("sound_prompt", "")).strip(),
        "negative_prompt": str(payload.get("negative_prompt", "")).strip(),
        "duration_seconds": _optional_float(payload.get("duration_seconds")),
        "ambience_position": str(payload.get("ambience_position", "")).strip(),
        "voice_target_id": str(payload.get("voice_target_id", "")).strip(),
        "voice_source_kind": str(payload.get("voice_source_kind", "")).strip(),
        "audio_can_play": _persisted_audio_can_play(payload),
        "audio_duration_seconds": _optional_float(payload.get("audio_duration_seconds")),
        "generated": bool(payload.get("generated", False)),
        "approved": bool(payload.get("approved", False)),
        "runtime_result_summary": str(payload.get("runtime_result_summary", "")).strip(),
        "split_part_count": _optional_int(payload.get("split_part_count"), 1),
        "generation_fingerprint": _optional_string(payload.get("generation_fingerprint")),
        "split_plan_fingerprint": _optional_string(payload.get("split_plan_fingerprint")),
    }


def _persisted_audio_can_play(audio_block: dict[str, object]) -> bool:
    """
    @brief      Resolve persisted Audio Blocks playability without touching the filesystem.
    @param[in]  audio_block Candidate Audio Blocks payload.
    @return     True when the record should be considered playable by state builders.
    @exception  None
    """
    if "audio_can_play" in audio_block:
        return bool(audio_block.get("audio_can_play", False))
    if not is_generated(audio_block):
        return False
    return bool(audio_block.get("metadata_only", False))


def _filesystem_audio_can_play(project_root: Path, audio_block: dict[str, object]) -> bool:
    """
    @brief      Verify one Audio Blocks playability flag from current project-local files.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_block Candidate Audio Blocks payload.
    @return     True when the generated audio entry is playable.
    @exception  None
    """
    if bool(audio_block.get("metadata_only", False)):
        return is_generated(audio_block) and str(audio_block.get("content_kind", "")).strip() == (
            speech_blocks_service.CONTENT_KIND_PAUSE
        )
    return _audio_block_owns_real_artifact(project_root, audio_block, require_valid=True)


def _audio_block_owns_real_artifact(
    project_root: Path,
    audio_block: dict[str, object],
    *,
    require_valid: bool = False,
) -> bool:
    """
    @brief      Return whether one Audio Blocks row owns a generated WAV artifact.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_block Candidate Audio Blocks payload.
    @param[in]  require_valid True when the artifact must also pass WAV validation.
    @return     True only for generated non-metadata rows with the required artifact.
    @exception  None
    """
    if not is_generated(audio_block) or bool(audio_block.get("metadata_only", False)):
        return False
    speech_block_id = str(audio_block.get("speech_block_id", "")).strip()
    if not speech_block_id:
        return False
    audio_path = _audio_artifact_path(project_root, speech_block_id)
    return _is_valid_wav_path(audio_path) if require_valid else audio_path.is_file()


def _normalize_voice_clone_profile(payload: dict[str, object]) -> VoiceCloneProfilePayload:
    """
    @brief      Normalize one persisted Audio Blocks reusable clone-prompt payload.
    @param[in]  payload Raw persisted payload.
    @return     Normalized reusable clone-prompt payload.
    @exception  None
    """
    voice_clone_prompt = payload.get("voice_clone_prompt")
    prompt_format = str(payload.get("prompt_format", "")).strip()
    if not prompt_format and isinstance(voice_clone_prompt, dict):
        prompt_format = str(voice_clone_prompt.get("format", "")).strip()
    return {
        "voice_target_id": str(payload.get("voice_target_id", "")).strip(),
        "display_name": str(payload.get("display_name", "")).strip(),
        "source_sample_relative_path": str(payload.get("source_sample_relative_path", "")).strip(),
        "source_sample_fingerprint": str(payload.get("source_sample_fingerprint", "")).strip(),
        "source_model_id": _optional_string(payload.get("source_model_id")),
        "voice_language": str(payload.get("voice_language", "")).strip(),
        "sample_text": str(payload.get("sample_text", "")).strip(),
        "voice_clone_prompt": voice_clone_prompt,
        "prompt_format": _optional_string(prompt_format),
        "generated_at": _optional_string(payload.get("generated_at")),
        "clone_model_id": _optional_string(payload.get("clone_model_id")),
    }


def _clone_profile_matches(
    clone_profile: VoiceCloneProfilePayload,
    voice_target: dict[str, object],
    generation_context: dict[str, object],
) -> bool:
    """
    @brief      Return whether one persisted reusable clone prompt still matches the current target sample.
    @param[in]  clone_profile Persisted reusable clone-prompt payload.
    @param[in]  voice_target Current voice-target payload.
    @param[in]  generation_context Validated generation-context payload.
    @return     `True` when the stored reusable clone prompt can be reused safely.
    @exception  None
    """
    clone_language = str(clone_profile.get("voice_language", "")).strip()
    sample_language = _voice_target_sample_language(voice_target)
    clone_model_id = str(clone_profile.get("clone_model_id", "")).strip()
    context_model_id = str(generation_context.get("clone_model_id", "")).strip()
    return (
        str(clone_profile.get("voice_target_id", "")).strip() == str(voice_target.get("voice_target_id", "")).strip()
        and str(clone_profile.get("source_sample_fingerprint", "")).strip()
        == str(voice_target.get("sample_fingerprint", "")).strip()
        and narrator_definition_service.narrator_language_code(clone_language) == sample_language
        and clone_model_id == context_model_id
        and str(clone_profile.get("sample_text", "")).strip() != ""
        and clone_profile.get("voice_clone_prompt") not in (None, "")
    )


def _voice_target_sample_language(voice_target: dict[str, object]) -> str:
    """
    @brief      Resolve the language of one reference voice sample.
    @param[in]  voice_target Current voice-target payload.
    @return     Canonical language code for clone-prompt sample transcription.
    @exception  None
    """
    sample_metadata = voice_target.get("sample_metadata", {})
    if not isinstance(sample_metadata, dict):
        sample_metadata = {}
    return narrator_definition_service.narrator_language_code(
        sample_metadata.get("voice_language")
        or sample_metadata.get("language")
        or voice_target.get("voice_language")
        or narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE
    )


def _replace_clone_profile(
    clone_profiles: list[VoiceCloneProfilePayload],
    new_profile: VoiceCloneProfilePayload,
) -> list[VoiceCloneProfilePayload]:
    """
    @brief      Replace or append one clone profile by voice target identifier.
    @param[in]  clone_profiles Current direct-clone source profile payload list.
    @param[in]  new_profile Normalized direct-clone source profile payload.
    @return     Updated direct-clone source profile payload list.
    @exception  None
    """
    normalized_target_id = str(new_profile.get("voice_target_id", "")).strip()
    updated_profiles = [
        profile for profile in clone_profiles if str(profile.get("voice_target_id", "")).strip() != normalized_target_id
    ]
    updated_profiles.append(_normalize_voice_clone_profile(new_profile))
    return sorted(updated_profiles, key=lambda item: str(item.get("voice_target_id", "")))


def _extract_voice_clone_prompt(status_payload: dict[str, object]) -> dict[str, object]:
    """
    @brief      Extract one reusable voice clone prompt from a terminal VoiceWeaver status payload.
    @param[in]  status_payload Final VoiceWeaver status payload.
    @return     Extracted reusable voice clone prompt payload.
    @exception  RuntimeError Raised when the prompt payload is missing or invalid.
    """
    operation_payload = status_payload.get("operation", {})
    if not isinstance(operation_payload, dict):
        raise RuntimeError("VoiceWeaver did not return a valid clone-prompt operation payload.")
    result_payload = operation_payload.get("result", {})
    if not isinstance(result_payload, dict):
        raise RuntimeError("VoiceWeaver did not return clone-prompt result metadata.")
    voice_clone_prompt = result_payload.get("voice_clone_prompt")
    if not isinstance(voice_clone_prompt, dict):
        raise RuntimeError("VoiceWeaver completed clone-prompt creation without returning a reusable prompt payload.")
    return dict(voice_clone_prompt)


def _file_sha1(path: Path) -> str:
    """
    @brief      Compute one stable SHA-1 fingerprint for a local binary artifact.
    @param[in]  path Existing local file path.
    @return     Hex-encoded SHA-1 digest string.
    @exception  None
    """
    return hashlib.sha1(path.read_bytes()).hexdigest()  # noqa: S324


def _active_model_id_from_status(status_payload: dict[str, object]) -> str | None:
    """
    @brief      Resolve one active-model identifier from the normalized VoiceWeaver status payload.
    @param[in]  status_payload Current VoiceWeaver status payload.
    @return     Active model identifier or `None`.
    @exception  None
    """
    active_model = status_payload.get("active_model")
    if isinstance(active_model, dict):
        resolved_model_id = str(active_model.get("model_id", "")).strip()
        return resolved_model_id or None
    if active_model in (None, ""):
        return None
    resolved_model_id = str(active_model).strip()
    return resolved_model_id or None


def _resolve_started_at(existing_state: dict[str, object]) -> str:
    """
    @brief      Resolve the runtime token for one Audio Blocks run.
    @param[in]  existing_state Existing operation-state payload.
    @return     Stable runtime token.
    @exception  None
    """
    resume_checkpoint = existing_state.get("resume_checkpoint", {}) if isinstance(existing_state, dict) else {}
    if not isinstance(resume_checkpoint, dict):
        resume_checkpoint = {}
    run_token = str(resume_checkpoint.get("run_token", "") or "").strip()
    return run_token or _utc_now_iso()


def _resume_checkpoint_field(existing_state: dict[str, object], field_name: str, fallback: int) -> int:
    """
    @brief      Resolve one integer resume-checkpoint field from an operation-state payload.
    @param[in]  existing_state Existing operation-state payload.
    @param[in]  field_name Resume-checkpoint field name.
    @param[in]  fallback Fallback integer value.
    @return     Resolved integer checkpoint value.
    @exception  None
    """
    if not isinstance(existing_state, dict):
        return fallback
    resume_checkpoint = existing_state.get("resume_checkpoint", {})
    if not isinstance(resume_checkpoint, dict):
        return fallback
    try:
        return int(resume_checkpoint.get(field_name, fallback))
    except (TypeError, ValueError):
        return fallback


def _optional_int(value: object, fallback: int) -> int:
    """
    @brief      Normalize one optional integer payload field.
    @param[in]  value Candidate integer value.
    @param[in]  fallback Fallback value used when normalization fails.
    @return     Normalized integer.
    @exception  None
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _optional_float(value: object) -> float | None:
    """
    @brief      Normalize one optional floating-point payload field.
    @param[in]  value Candidate floating-point value.
    @return     Normalized non-negative float, or `None`.
    @exception  None
    """
    try:
        normalized_value = float(value)
    except (TypeError, ValueError):
        return None
    return normalized_value if normalized_value >= 0.0 else None


def _first_model(
    model_entries: list[dict[str, object]],
    preferred_model_id: str | None = None,
) -> dict[str, object] | None:
    """
    @brief      Return the preferred normalized runtime model entry when available.
    @param[in]  model_entries Current runtime model payload list.
    @param[in]  preferred_model_id Optional exact model identifier to prefer first.
    @return     Preferred runtime model payload or the first fallback entry, or `None`.
    @exception  None
    """
    if not model_entries:
        return None
    normalized_preferred_id = str(preferred_model_id or "").strip()
    if normalized_preferred_id:
        for model_entry in model_entries:
            if str(dict(model_entry).get("model_id", "")).strip() == normalized_preferred_id:
                return dict(model_entry)
    return dict(model_entries[0])


# END OF FILE
