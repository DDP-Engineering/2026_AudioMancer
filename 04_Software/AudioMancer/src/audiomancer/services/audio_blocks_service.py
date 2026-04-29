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
@author Eng. Dan Dumitru Pasare
@date 2026-04-23
@version 0.10.0
"""

# IMPORTS

import hashlib
import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import (
    audio_blocks_artifact_service,
    character_voices_service,
    narrator_definition_service,
    operation_runtime_service,
    speech_blocks_service,
    voiceweaver_runtime_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    build_operation_output_path,
    build_operation_state_payload,
    load_operation_state_payload,
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
from audiomancer.services.operation_runtime_service import (
    try_resolve_project_relative_path as _safe_project_artifact_path,
)
from audiomancer.services.persistence_service import write_json_atomic
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
_DEFAULT_APPROX_AUDIO_SECONDS_PER_TOKEN = 0.08
_SPLIT_SAFETY_FACTOR = 0.85
_WORDS_PER_AUDIO_SECOND = 2.5
_AUDIO_BLOCK_FINGERPRINT_VERSION = 1
_SPECIAL_BLOCK_STATUS_IMPLEMENTED = "implemented"
_SPECIAL_BLOCK_STATUS_NOT_IMPLEMENTED = "not_implemented"
_audio_artifact_file_stem = audio_blocks_artifact_service.audio_artifact_file_stem
_audio_artifact_paths = audio_blocks_artifact_service.audio_artifact_paths
_audio_part_artifact_path = audio_blocks_artifact_service.audio_part_artifact_path
_generated_audio_root = audio_blocks_artifact_service.generated_audio_root
_is_valid_wav_path = audio_blocks_artifact_service.is_valid_wav_path
_stitch_wav_parts = audio_blocks_artifact_service.stitch_wav_parts
_validate_wav_bytes = audio_blocks_artifact_service.validate_wav_bytes
normalize_speaker_name = audio_blocks_artifact_service.normalize_speaker_name

AudioBlockPayload = dict[str, object]
AudioBlocksReportPayload = dict[str, object]
OperationStatePayload = dict[str, object]
VoiceCloneProfilePayload = dict[str, object]


# PUBLIC API


@trace_function(_AUDIO_BLOCKS_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Load one optional Audio Blocks operation-state payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted operation-state payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    return load_operation_state_payload(project_root, "audio_blocks", config.AUDIO_BLOCKS_STATE_FILE_NAME)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def load_audio_blocks_report(project_root: str | Path) -> AudioBlocksReportPayload | None:
    """
    @brief      Load one optional Audio Blocks report payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted report payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    report_path = resolve_operation_path(project_root, "audio_blocks", config.AUDIO_BLOCKS_REPORT_FILE_NAME)
    payload = load_optional_json_artifact(report_path)
    if payload is None:
        return None
    return dict(payload)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def load_audio_blocks(project_root: str | Path) -> list[AudioBlockPayload]:
    """
    @brief      Load one optional persisted Audio Blocks output payload.
    @param[in]  project_root Active project root folder.
    @return     Ordered Audio Blocks payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.3.0
    """
    output_path = resolve_operation_path(project_root, "audio_blocks", config.AUDIO_BLOCKS_OUTPUT_FILE_NAME)
    payload = load_optional_json_artifact(output_path)
    if not isinstance(payload, list):
        return []
    return speech_blocks_service.sort_speech_blocks(
        [_normalize_persisted_audio_block(item) for item in payload if isinstance(item, dict)]
    )


@trace_function(_AUDIO_BLOCKS_LOGGER)
def load_voice_clone_profiles(project_root: str | Path) -> list[VoiceCloneProfilePayload]:
    """
    @brief      Load one optional persisted Audio Blocks direct-clone source profile list.
    @param[in]  project_root Active project root folder.
    @return     Ordered direct-clone source profile payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.5.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.1
    """
    generated_root = _generated_audio_root(Path(project_root))
    operation_state = load_operation_state(project_root)
    has_runtime_state = False
    if isinstance(operation_state, dict):
        has_runtime_state = str(operation_state.get("status", "")).strip() != AUDIO_BLOCKS_STAGE_NOT_STARTED or any(
            (
                bool(operation_state.get("input_paths")),
                bool(operation_state.get("output_paths")),
                bool(operation_state.get("artifact_paths")),
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
def has_persisted_audio_for_chunk(project_root: str | Path, chunk_id: str) -> bool:
    """
    @brief      Return whether one chunk has persisted Audio Blocks progress or generated artifacts.
    @param[in]  project_root Active project root folder.
    @param[in]  chunk_id Source chunk identifier.
    @return     `True` when the selected chunk has Audio Blocks records or files.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    normalized_chunk_id = str(chunk_id).strip()
    if not normalized_chunk_id:
        return False
    for block in load_audio_blocks(project_root):
        if str(block.get("chunk_id", "")).strip() != normalized_chunk_id:
            continue
        if any(
            (
                bool(block.get("generated", False)),
                bool(block.get("approved", False)),
                bool(_optional_string(block.get("audio_relative_path"))),
                bool(_optional_string(block.get("metadata_relative_path"))),
                bool(block.get("generated_part_relative_paths")),
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.3.3
    """
    resolved_project_root = Path(project_root)
    generation_context = _resolve_generation_context(resolved_project_root, manifest, runtime_settings)
    existing_state = load_operation_state(resolved_project_root) or {}
    reused_prompt_count = _metadata_int(existing_state, "reused_prompt_count", 0)
    regenerated_prompt_count = _metadata_int(existing_state, "regenerated_prompt_count", 0)
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

    report = _rebuild_report(
        existing_blocks,
        generation_context["voice_language"],
        generation_context["speech_blocks"],
        warning_records=[],
        prompt_count=len(existing_clone_profiles),
        reused_prompt_count=reused_prompt_count,
        regenerated_prompt_count=regenerated_prompt_count,
        current_phase=(_PROFILE_PHASE if profile_index < len(generation_context["voice_targets"]) else _GENERATE_PHASE),
    )
    _persist_state(
        resolved_project_root,
        generation_context["speech_blocks"],
        existing_blocks,
        existing_clone_profiles,
        report,
        _build_operation_state(
            resolved_project_root,
            generation_context["speech_blocks"],
            existing_blocks,
            existing_clone_profiles,
            status="running",
            started_at=started_at,
            completed_at=None,
            voice_language=generation_context["voice_language"],
            input_fingerprint=generation_context["input_fingerprint"],
            current_phase=(
                _PROFILE_PHASE if profile_index < len(generation_context["voice_targets"]) else _GENERATE_PHASE
            ),
            current_block_id=None,
            next_profile_index=profile_index,
            next_speech_block_index=block_index,
            reused_prompt_count=reused_prompt_count,
            regenerated_prompt_count=regenerated_prompt_count,
        ),
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
            profile_index,
            block_index,
            reused_prompt_count,
            regenerated_prompt_count,
        )
        raise
    generation_context.update(loaded_model_budget)
    generation_context["input_fingerprint"] = _build_input_fingerprint(
        generation_context["speech_blocks"],
        generation_context["voice_targets"],
        str(generation_context["voice_language"]),
        str(generation_context["clone_model_id"]),
        manifest,
        loaded_model_budget,
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
    block_index = _first_incomplete_block_index(existing_blocks)
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
                current_profile_index,
                block_index,
                reused_prompt_count,
                regenerated_prompt_count,
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
                current_profile_index,
                block_index,
                reused_prompt_count,
                regenerated_prompt_count,
            )
            raise
        if prompt_reused:
            reused_prompt_count += 1
            progress_message = f"Reused clone prompt for {voice_target['display_name']}."
        else:
            regenerated_prompt_count += 1
            progress_message = f"Prepared clone prompt for {voice_target['display_name']}."
        report = _rebuild_report(
            existing_blocks,
            generation_context["voice_language"],
            generation_context["speech_blocks"],
            warning_records=[],
            prompt_count=len(existing_clone_profiles),
            reused_prompt_count=reused_prompt_count,
            regenerated_prompt_count=regenerated_prompt_count,
            current_phase=_PROFILE_PHASE,
        )
        _persist_state(
            resolved_project_root,
            generation_context["speech_blocks"],
            existing_blocks,
            existing_clone_profiles,
            report,
            _build_operation_state(
                resolved_project_root,
                generation_context["speech_blocks"],
                existing_blocks,
                existing_clone_profiles,
                status="running",
                started_at=started_at,
                completed_at=None,
                voice_language=generation_context["voice_language"],
                input_fingerprint=generation_context["input_fingerprint"],
                current_phase=_PROFILE_PHASE,
                current_block_id=None,
                next_profile_index=current_profile_index + 1,
                next_speech_block_index=block_index,
                reused_prompt_count=reused_prompt_count,
                regenerated_prompt_count=regenerated_prompt_count,
            ),
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
    for current_block_index in range(block_index, len(existing_blocks)):
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
                len(generation_context["voice_targets"]),
                current_block_index,
                reused_prompt_count,
                regenerated_prompt_count,
            )
            raise
        current_block = dict(existing_blocks[current_block_index])
        current_block_id = str(current_block.get("speech_block_id", "")).strip()
        if not bool(current_block.get("speech_block_approved", False)):
            continue
        if bool(current_block.get("metadata_only", False)):
            continue
        clone_profile = clone_profiles_by_id.get(str(current_block.get("voice_target_id", "")).strip())
        if clone_profile is None:
            raise RuntimeError(f"Missing clone profile for voice target '{current_block.get('voice_target_id', '')}'.")
        try:
            generated_block = _generate_audio_block(
                resolved_project_root,
                current_block,
                clone_profile,
                generation_context,
                runtime_settings,
                cancel_requested=cancel_requested,
                checkpoint_callback=(
                    lambda checkpoint_block, next_split_part_index, active_block_index=current_block_index: (
                        _persist_split_checkpoint(
                            resolved_project_root,
                            generation_context,
                            existing_blocks,
                            existing_clone_profiles,
                            checkpoint_block,
                            active_block_index,
                            next_split_part_index,
                            started_at,
                            reused_prompt_count,
                            regenerated_prompt_count,
                        )
                    )
                ),
            )
        except operation_runtime_service.OperationCancelledError:
            latest_state = load_operation_state(resolved_project_root) or {}
            latest_blocks = _merge_existing_audio_blocks(
                generation_context["speech_blocks"],
                load_audio_blocks(resolved_project_root) or existing_blocks,
            )
            _persist_cancelled_state(
                resolved_project_root,
                generation_context,
                latest_blocks,
                existing_clone_profiles,
                started_at,
                _GENERATE_PHASE,
                current_block_id,
                len(generation_context["voice_targets"]),
                current_block_index,
                reused_prompt_count,
                regenerated_prompt_count,
                _resume_checkpoint_field(latest_state, "next_split_part_index", 0),
            )
            raise
        existing_blocks[current_block_index] = generated_block
        report = _rebuild_report(
            existing_blocks,
            generation_context["voice_language"],
            generation_context["speech_blocks"],
            warning_records=[],
            prompt_count=len(existing_clone_profiles),
            reused_prompt_count=reused_prompt_count,
            regenerated_prompt_count=regenerated_prompt_count,
            current_phase=_GENERATE_PHASE,
        )
        _persist_state(
            resolved_project_root,
            generation_context["speech_blocks"],
            existing_blocks,
            existing_clone_profiles,
            report,
            _build_operation_state(
                resolved_project_root,
                generation_context["speech_blocks"],
                existing_blocks,
                existing_clone_profiles,
                status="running",
                started_at=started_at,
                completed_at=None,
                voice_language=generation_context["voice_language"],
                input_fingerprint=generation_context["input_fingerprint"],
                current_phase=_GENERATE_PHASE,
                current_block_id=current_block_id,
                next_profile_index=len(generation_context["voice_targets"]),
                next_speech_block_index=current_block_index + 1,
                reused_prompt_count=reused_prompt_count,
                regenerated_prompt_count=regenerated_prompt_count,
            ),
        )
        _emit_progress(
            progress_callback,
            _generated_count(existing_blocks),
            len(generation_context["speech_blocks"]),
            f"Generated audio for {generated_block['speaker_display_name']}.",
        )

    completed_at = _utc_now_iso()
    report = _rebuild_report(
        existing_blocks,
        generation_context["voice_language"],
        generation_context["speech_blocks"],
        warning_records=[],
        updated_at=completed_at,
        prompt_count=len(existing_clone_profiles),
        reused_prompt_count=reused_prompt_count,
        regenerated_prompt_count=regenerated_prompt_count,
        current_phase=_GENERATE_PHASE,
    )
    final_status = (
        "completed"
        if str(report.get("audio_blocks_stage_status", "")).strip() == AUDIO_BLOCKS_STAGE_COMPLETED
        else "in_progress"
    )
    final_completed_at = completed_at if final_status == "completed" else None
    _persist_state(
        resolved_project_root,
        generation_context["speech_blocks"],
        existing_blocks,
        existing_clone_profiles,
        report,
        _build_operation_state(
            resolved_project_root,
            generation_context["speech_blocks"],
            existing_blocks,
            existing_clone_profiles,
            status=final_status,
            started_at=started_at,
            completed_at=final_completed_at,
            voice_language=generation_context["voice_language"],
            input_fingerprint=generation_context["input_fingerprint"],
            current_phase=_GENERATE_PHASE,
            current_block_id=None,
            next_profile_index=len(generation_context["voice_targets"]),
            next_speech_block_index=len(existing_blocks),
            reused_prompt_count=reused_prompt_count,
            regenerated_prompt_count=regenerated_prompt_count,
        ),
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
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
        if not bool(block.get("generated", False)):
            raise ValueError("Generate the selected audio block before approving it.")
        block["approved"] = True
        block["approved_at"] = _utc_now_iso()
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    audio_blocks = load_audio_blocks(resolved_project_root)
    if not audio_blocks:
        return _persist_report_update(resolved_project_root, [])
    approved_at = _utc_now_iso()
    for block in audio_blocks:
        if bool(block.get("generated", False)):
            block["approved"] = True
            block["approved_at"] = approved_at
    return _persist_report_update(resolved_project_root, audio_blocks)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def invalidate_audio_for_speech_block(project_root: str | Path, speech_block_id: str) -> AudioBlocksReportPayload:
    """
    @brief      Clear generated audio for one changed Speech Block.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Changed Speech Block identifier.
    @return     Updated Audio Blocks report payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    audio_blocks = load_audio_blocks(resolved_project_root)
    changed = False
    for block in audio_blocks:
        if str(block.get("speech_block_id", "")).strip() != str(speech_block_id).strip():
            continue
        _delete_audio_block_artifacts(resolved_project_root, block)
        block.update(_cleared_audio_fields())
        changed = True
        break
    if not changed:
        return load_audio_blocks_report(resolved_project_root) or _persist_report_update(resolved_project_root, [])
    return _persist_report_update(resolved_project_root, audio_blocks)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def reconcile_after_speech_blocks_resplit(project_root: str | Path, changed_chunk_id: str) -> AudioBlocksReportPayload:
    """
    @brief      Preserve safe Audio Blocks entries after one Speech Blocks chunk is re-split.
    @param[in]  project_root Active project root folder.
    @param[in]  changed_chunk_id Re-split source chunk identifier.
    @return     Updated Audio Blocks report payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    resolved_project_root = Path(project_root)
    speech_blocks = speech_blocks_service.sort_speech_blocks(
        speech_blocks_service.load_speech_blocks(resolved_project_root)
    )
    existing_audio_blocks = load_audio_blocks(resolved_project_root)
    if not existing_audio_blocks:
        return load_audio_blocks_report(resolved_project_root) or _persist_report_update(resolved_project_root, [])
    existing_by_chunk_order = {
        (str(block.get("chunk_id", "")).strip(), int(block.get("sequence_index", 0))): block
        for block in existing_audio_blocks
    }
    reconciled_blocks: list[AudioBlockPayload] = []
    for speech_block in speech_blocks:
        chunk_id = str(speech_block.get("chunk_id", "")).strip()
        new_block = _initialize_audio_blocks([speech_block])[0]
        if chunk_id == str(changed_chunk_id).strip():
            old_block = existing_by_chunk_order.get((chunk_id, int(speech_block.get("sequence_index", 0))))
            if old_block is not None:
                _delete_audio_block_artifacts(resolved_project_root, old_block)
            reconciled_blocks.append(new_block)
            continue
        old_block = existing_by_chunk_order.get((chunk_id, int(speech_block.get("sequence_index", 0))))
        if old_block is None:
            reconciled_blocks.append(new_block)
            continue
        old_block = _remap_audio_block_artifacts(resolved_project_root, old_block, new_block)
        new_block.update(
            {
                "audio_relative_path": old_block.get("audio_relative_path"),
                "metadata_relative_path": old_block.get("metadata_relative_path"),
                "special_block_status": old_block.get("special_block_status") or new_block.get("special_block_status"),
                "generated": bool(old_block.get("generated", False)),
                "approved": bool(old_block.get("approved", False)),
                "approved_at": old_block.get("approved_at"),
                "generated_at": old_block.get("generated_at"),
                "runtime_result_summary": str(old_block.get("runtime_result_summary", "")),
                "split_part_count": int(old_block.get("split_part_count", 1)),
                "split_strategy": str(old_block.get("split_strategy", "single")).strip() or "single",
                "model_token_budget": old_block.get("model_token_budget"),
                "model_audio_seconds_budget": old_block.get("model_audio_seconds_budget"),
                "generated_part_relative_paths": list(old_block.get("generated_part_relative_paths", []))
                if isinstance(old_block.get("generated_part_relative_paths"), list)
                else [],
                "generation_fingerprint": old_block.get("generation_fingerprint"),
                "split_plan_fingerprint": old_block.get("split_plan_fingerprint"),
                "warning_flags": _normalize_warning_flags(old_block.get("warning_flags")),
            }
        )
        reconciled_blocks.append(new_block)
    for old_block in existing_audio_blocks:
        key = (str(old_block.get("chunk_id", "")).strip(), int(old_block.get("sequence_index", 0)))
        if key not in {
            (str(block.get("chunk_id", "")).strip(), int(block.get("sequence_index", 0))) for block in speech_blocks
        }:
            _delete_audio_block_artifacts(resolved_project_root, old_block)
    return _persist_report_update(resolved_project_root, reconciled_blocks)


@trace_function(_AUDIO_BLOCKS_LOGGER)
def reset_audio_for_speech_chunk(project_root: str | Path, changed_chunk_id: str) -> AudioBlocksReportPayload:
    """
    @brief      Reset generated Audio Blocks data for one changed Speech Blocks chunk.
    @param[in]  project_root Active project root folder.
    @param[in]  changed_chunk_id Changed source chunk identifier.
    @return     Updated Audio Blocks report payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    return reconcile_after_speech_blocks_resplit(project_root, changed_chunk_id)


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.1
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
        loaded_model_budget,
    )
    if _requires_manual_reset(
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
    @brief      Delete Audio Blocks and downstream Audio Assembly runtime artifacts.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    operation_runtime_service.reset_operation_data(
        project_root,
        "audio_blocks",
        include_current=True,
        keep_input_snapshots=False,
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.4.1
    """
    speech_blocks = speech_blocks_service.sort_speech_blocks(speech_blocks_service.load_speech_blocks(project_root))
    if not speech_blocks:
        raise ValueError("Generate Speech Blocks before starting Audio Blocks.")
    approved_speech_blocks = [block for block in speech_blocks if _speech_block_is_approved(block)]
    if not approved_speech_blocks:
        raise ValueError("Approve at least one Speech Block before starting Audio Blocks.")
    speech_audio_blocks = [block for block in approved_speech_blocks if not _is_metadata_only_speech_block(block)]
    base_url = str(runtime_settings.get("base_url", "")).strip()
    timeout_seconds = int(runtime_settings.get("timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
    discovered_models = list(runtime_settings.get("discovered_models", []))
    if not base_url:
        raise ValueError("Configure TTS Settings and test the VoiceWeaver connection before generating Audio Blocks.")
    capability_matrix = voiceweaver_runtime_service.build_capability_matrix(discovered_models)
    clone_model = _first_model(
        capability_matrix.get("qwen_base_models", []),
        preferred_model_id=_PREFERRED_QWEN_CLONE_MODEL_ID,
    )
    if clone_model is None:
        raise ValueError("Cannot generate Audio Blocks because the required Qwen3 TTS base clone model is missing.")
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
    narrator_audio_path, _narrator_metadata_path = narrator_definition_service.selected_narrator_sample_paths(
        project_root
    )
    narrator_metadata: dict[str, object] = {}
    if speech_audio_blocks:
        if not narrator_audio_path.is_file():
            raise ValueError("Generate the selected narrator sample before starting Audio Blocks.")
        narrator_metadata = narrator_definition_service.load_selected_narrator_sample_metadata(project_root)
        if not isinstance(narrator_metadata, dict):
            raise ValueError("The selected narrator sample metadata is missing or invalid.")
        narrator_metadata = _resolve_selected_narrator_sample_metadata(project_root, narrator_metadata)

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
    model_budget = _resolve_model_budget({}, clone_model)
    input_fingerprint = _build_input_fingerprint(
        speech_blocks,
        voice_targets,
        voice_language,
        clone_model_id,
        manifest,
        model_budget,
    )
    return {
        "speech_blocks": speech_blocks,
        "voice_targets": voice_targets,
        "voice_language": voice_language,
        "clone_model_id": clone_model_id,
        "clone_model_payload": clone_model,
        "voice_assignment_mode": voice_assignment_mode,
        "original_language": str(manifest.get("original_language", "")).strip(),
        **model_budget,
        "base_url": base_url,
        "runtime_api_key": str(runtime_settings.get("runtime_api_key", "")),
        "timeout_seconds": timeout_seconds,
        "input_fingerprint": input_fingerprint,
    }


def _resolve_selected_narrator_sample_metadata(
    project_root: Path,
    selected_metadata: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Resolve selected narrator metadata, falling back to the selected profile sample.
    @param[in]  project_root Active project root folder.
    @param[in]  selected_metadata Persisted selected-narrator metadata or selection state.
    @return     Sample metadata with preview text when the selected profile provides it.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    resolved_metadata = dict(selected_metadata)
    if str(resolved_metadata.get("preview_text", "")).strip():
        return resolved_metadata

    selected_profile_id = str(
        resolved_metadata.get("selected_profile_id") or resolved_metadata.get("profile_id") or ""
    ).strip()
    if not selected_profile_id:
        selected_state = narrator_definition_service.load_selected_profile_state(project_root)
        selected_profile_id = str(selected_state.get("selected_profile_id", "") or "").strip()
    if not selected_profile_id:
        return resolved_metadata

    profile_metadata = narrator_definition_service.load_profile_sample_metadata(project_root, selected_profile_id)
    if not isinstance(profile_metadata, dict):
        return resolved_metadata
    resolved_metadata.update(dict(profile_metadata))
    resolved_metadata["selected_profile_id"] = selected_profile_id
    resolved_metadata["is_selected"] = True
    resolved_metadata.setdefault("role", "narrator")
    return resolved_metadata


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.1
    """
    fingerprint_payload = {
        "original_language": manifest.get("original_language"),
        "voice_language": voice_language,
        "clone_model_id": clone_model_id,
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
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
) -> dict[str, object]:
    """
    @brief      Resolve the clone-model generation budget used for Audio Blocks splitting.
    @param[in]  status_payload Current normalized VoiceWeaver status payload.
    @param[in]  clone_model_payload Discovered clone-model payload.
    @return     Budget payload including token and audio-seconds limits.
    @exception  ValueError Raised when no positive `max_new_tokens` budget can be resolved.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    budget_source_candidates = (
        ("runtime_effective", _status_effective_model_parameters(status_payload)),
        ("default_model_parameters", dict(clone_model_payload).get("default_model_parameters")),
        ("range_default", _parameter_range_default(dict(clone_model_payload).get("generation_parameter_ranges"))),
    )
    for budget_source, parameters in budget_source_candidates:
        token_budget = _positive_int_from_mapping(parameters, "max_new_tokens")
        if token_budget is None:
            continue
        audio_seconds_budget = token_budget * _DEFAULT_APPROX_AUDIO_SECONDS_PER_TOKEN
        return {
            "model_token_budget": token_budget,
            "model_audio_seconds_budget": audio_seconds_budget,
            "split_audio_seconds_budget": audio_seconds_budget * _SPLIT_SAFETY_FACTOR,
            "approx_audio_seconds_per_token": _DEFAULT_APPROX_AUDIO_SECONDS_PER_TOKEN,
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    operation_payload = status_payload.get("operation", {}) if isinstance(status_payload, dict) else {}
    if not isinstance(operation_payload, dict):
        return False
    operation_status = str(operation_payload.get("status", operation_payload.get("kind", "idle"))).strip().lower()
    return operation_status not in {"", "idle", "completed", "failed"}


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    base_url = str(runtime_settings.get("base_url", "")).strip()
    runtime_api_key = str(runtime_settings.get("runtime_api_key", ""))
    timeout_seconds = int(runtime_settings.get("timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
    _emit_progress(progress_callback, progress_current, progress_total, "Loading audio generation model...")
    raise_if_cancelled(cancel_requested)
    initial_status = voiceweaver_runtime_service.read_status(
        base_url,
        runtime_api_key,
        timeout_seconds=timeout_seconds,
    )
    raise_if_cancelled(cancel_requested)
    active_model_id = _active_model_id_from_status(initial_status)
    if _runtime_operation_is_busy(initial_status):
        raise RuntimeError(
            "VoiceWeaver is still busy with a previous operation. Wait for the current runtime operation to finish, "
            "then start Audio Blocks again."
        )
    initial_budget = _resolve_model_budget(initial_status, clone_model_payload)
    if active_model_id == clone_model_id and initial_budget.get("model_budget_source") == "runtime_effective":
        return initial_budget
    voiceweaver_runtime_service.load_model(
        base_url,
        runtime_api_key,
        clone_model_id,
        timeout_seconds=timeout_seconds,
    )
    final_status = voiceweaver_runtime_service.wait_for_terminal_operation(
        base_url,
        runtime_api_key,
        timeout_seconds=timeout_seconds,
        cancel_requested=cancel_requested,
    )
    final_operation = final_status.get("operation", {})
    if not isinstance(final_operation, dict) or str(final_operation.get("status", "")).strip().lower() != "completed":
        raise RuntimeError(voiceweaver_runtime_service.operation_failed_message(final_status))
    if _active_model_id_from_status(final_status) != clone_model_id:
        raise RuntimeError(f"VoiceWeaver did not activate the requested model '{clone_model_id}'.")
    loaded_status = voiceweaver_runtime_service.read_status(
        base_url,
        runtime_api_key,
        timeout_seconds=timeout_seconds,
    )
    return _resolve_model_budget(loaded_status, clone_model_payload)


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.5.0
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
    runtime_api_key = str(runtime_settings.get("runtime_api_key", ""))
    timeout_seconds = int(runtime_settings.get("timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
    raise_if_cancelled(cancel_requested)
    voiceweaver_runtime_service.create_voice_clone_prompt(
        base_url,
        runtime_api_key,
        sample_audio_path.read_bytes(),
        sample_text,
        sample_language,
        timeout_seconds=timeout_seconds,
    )
    final_status = voiceweaver_runtime_service.wait_for_terminal_operation(
        base_url,
        runtime_api_key,
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
    force_restart: bool = False,
) -> AudioBlockPayload:
    """
    @brief      Generate one WAV plus metadata pair for the selected speech block and reusable clone prompt.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_block Persisted Audio Blocks entry to regenerate.
    @param[in]  clone_profile Persisted reusable clone-prompt payload.
    @param[in]  generation_context Validated generation-context payload.
    @param[in]  runtime_settings Runtime connection plus discovered-model settings.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  checkpoint_callback Optional callback persisted after each completed split part.
    @param[in]  force_restart True to discard any prior split-part checkpoint for this block.
    @return     Updated Audio Blocks payload.
    @exception  RuntimeError Raised when VoiceWeaver does not expose downloadable audio.
    @exception  OperationCancelledError Raised when cancellation is requested.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.4.2
    """
    base_url = str(runtime_settings.get("base_url", "")).strip()
    runtime_api_key = str(runtime_settings.get("runtime_api_key", ""))
    timeout_seconds = int(runtime_settings.get("timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
    voice_clone_prompt = clone_profile.get("voice_clone_prompt")
    if voice_clone_prompt in (None, ""):
        raise RuntimeError("Audio Blocks could not resolve the required reusable clone prompt for generation.")
    split_plan = _plan_audio_block_splits(str(audio_block.get("text", "")), generation_context)
    audio_path, metadata_path = _audio_artifact_paths(
        project_root,
        str(audio_block.get("chunk_id", "")).strip(),
        int(audio_block.get("sequence_index", 0)),
        str(audio_block.get("normalized_speaker_name", "")),
    )
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    part_paths = _existing_part_paths(project_root, audio_block, split_plan, force_restart)
    if force_restart:
        _delete_audio_block_artifacts(project_root, audio_block)
    runtime_result_summary = ""
    for part_index in range(len(part_paths), len(split_plan["parts"])):
        part_text = str(split_plan["parts"][part_index])
        raise_if_cancelled(cancel_requested)
        voiceweaver_runtime_service.generate_voice_clone_from_prompt(
            base_url,
            runtime_api_key,
            voice_clone_prompt,
            str(generation_context.get("voice_language", "")),
            part_text,
            model_parameters={"max_new_tokens": int(generation_context.get("model_token_budget", 0))},
            timeout_seconds=timeout_seconds,
        )
        final_status = voiceweaver_runtime_service.wait_for_terminal_operation(
            base_url,
            runtime_api_key,
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
        audio_bytes = voiceweaver_runtime_service.download_generated_voice(
            base_url,
            runtime_api_key,
            timeout_seconds=timeout_seconds,
        )
        _validate_wav_bytes(audio_bytes)
        if len(split_plan["parts"]) == 1:
            audio_path.write_bytes(audio_bytes)
        else:
            part_path = _audio_part_artifact_path(project_root, audio_block, part_index)
            part_path.parent.mkdir(parents=True, exist_ok=True)
            part_path.write_bytes(audio_bytes)
            part_paths.append(part_path)
        runtime_result_summary = str(final_result.get("summary", "")).strip()
        if len(split_plan["parts"]) > 1 and callable(checkpoint_callback):
            checkpoint_callback(
                {
                    **dict(audio_block),
                    "split_part_count": len(split_plan["parts"]),
                    "split_strategy": split_plan["strategy"],
                    "model_token_budget": int(generation_context.get("model_token_budget", 0)),
                    "model_audio_seconds_budget": float(generation_context.get("model_audio_seconds_budget", 0.0)),
                    "generated_part_relative_paths": [relative_to_project(project_root, path) for path in part_paths],
                    "generation_fingerprint": _build_audio_block_fingerprint(audio_block, generation_context),
                    "split_plan_fingerprint": _split_plan_fingerprint(split_plan),
                    "runtime_result_summary": runtime_result_summary,
                },
                part_index + 1,
            )
    if len(split_plan["parts"]) > 1:
        _stitch_wav_parts(part_paths, audio_path)
    generated_at = _utc_now_iso()
    metadata_payload = {
        "speech_block_id": str(audio_block.get("speech_block_id", "")).strip(),
        "chunk_id": str(audio_block.get("chunk_id", "")).strip(),
        "sequence_index": int(audio_block.get("sequence_index", 0)),
        "speaker_display_name": str(audio_block.get("speaker_display_name", "")).strip(),
        "normalized_speaker_name": str(audio_block.get("normalized_speaker_name", "")).strip(),
        "text": str(audio_block.get("text", "")),
        "voice_target_id": str(audio_block.get("voice_target_id", "")).strip(),
        "voice_language": str(generation_context.get("voice_language", "")).strip(),
        "prompt_format": _optional_string(clone_profile.get("prompt_format")),
        "generated_at": generated_at,
        "runtime_result_summary": runtime_result_summary,
        "split_part_count": len(split_plan["parts"]),
        "split_strategy": split_plan["strategy"],
        "model_token_budget": int(generation_context.get("model_token_budget", 0)),
        "model_audio_seconds_budget": float(generation_context.get("model_audio_seconds_budget", 0.0)),
        "generated_part_relative_paths": [relative_to_project(project_root, path) for path in part_paths],
        "generation_fingerprint": _build_audio_block_fingerprint(audio_block, generation_context),
        "split_plan_fingerprint": _split_plan_fingerprint(split_plan),
    }
    write_json_atomic(metadata_path, metadata_payload)
    return {
        **dict(audio_block),
        "audio_relative_path": relative_to_project(project_root, audio_path),
        "metadata_relative_path": relative_to_project(project_root, metadata_path),
        "split_part_count": len(split_plan["parts"]),
        "split_strategy": split_plan["strategy"],
        "model_token_budget": int(generation_context.get("model_token_budget", 0)),
        "model_audio_seconds_budget": float(generation_context.get("model_audio_seconds_budget", 0.0)),
        "generated_part_relative_paths": [relative_to_project(project_root, path) for path in part_paths],
        "generation_fingerprint": _build_audio_block_fingerprint(audio_block, generation_context),
        "split_plan_fingerprint": _split_plan_fingerprint(split_plan),
        "generated": True,
        "approved": False,
        "approved_at": None,
        "generated_at": generated_at,
        "runtime_result_summary": runtime_result_summary,
        "warning_flags": _normalize_warning_flags(audio_block.get("warning_flags")),
    }


def _plan_audio_block_splits(text: str, generation_context: dict[str, object]) -> dict[str, object]:
    """
    @brief      Split one Audio Blocks text into generation parts that fit the resolved model budget.
    @param[in]  text Original speech-block text.
    @param[in]  generation_context Validated generation-context payload with model budget fields.
    @return     Split plan containing ordered text parts and strategy name.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.1
    """
    normalized_text = _normalize_split_text(text)
    if not normalized_text:
        return {"parts": [""], "strategy": "single"}
    max_words = max(1, int(float(generation_context.get("split_audio_seconds_budget", 0.0)) * _WORDS_PER_AUDIO_SECOND))
    if _estimated_word_count(normalized_text) <= max_words:
        return {"parts": [normalized_text], "strategy": "single"}
    for strategy, pattern in (
        ("sentence", r"(?<=[.!?])\s+"),
        ("clause", r"(?<=[,;:])\s+"),
    ):
        parts = _pack_text_units(re.split(pattern, normalized_text), max_words)
        if len(parts) > 1 and all(_estimated_word_count(part) <= max_words for part in parts):
            return {"parts": parts, "strategy": strategy}
    return {"parts": _split_by_word_groups(normalized_text, max_words), "strategy": "word_group"}


def _pack_text_units(units: list[str], max_words: int) -> list[str]:
    """
    @brief      Pack text units into budget-sized generation parts.
    @param[in]  units Ordered text units.
    @param[in]  max_words Maximum estimated words per generated part.
    @return     Packed text parts.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    parts: list[str] = []
    current_units: list[str] = []
    for unit in (_normalize_split_text(item) for item in units):
        if not unit:
            continue
        if _estimated_word_count(unit) > max_words:
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    words = text.split()
    return [" ".join(words[index : index + max_words]) for index in range(0, len(words), max_words)] or [""]


def _normalize_split_text(text: str) -> str:
    """
    @brief      Normalize whitespace for split planning and generation requests.
    @param[in]  text Candidate speech-block text.
    @return     Text with collapsed whitespace.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _estimated_word_count(text: str) -> int:
    """
    @brief      Estimate spoken length using whitespace-delimited words.
    @param[in]  text Candidate speech text.
    @return     Estimated word count.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    return len([word for word in str(text or "").split() if word])


def _existing_part_paths(
    project_root: Path,
    audio_block: AudioBlockPayload,
    split_plan: dict[str, object],
    force_restart: bool,
) -> list[Path]:
    """
    @brief      Resolve completed split-part paths that can be reused for resume.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_block Persisted Audio Blocks entry.
    @param[in]  split_plan Current split plan.
    @param[in]  force_restart True to ignore persisted part checkpoints.
    @return     Existing part paths in completed order.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.2
    """
    if force_restart or len(split_plan["parts"]) <= 1:
        return []
    persisted_split_fingerprint = str(audio_block.get("split_plan_fingerprint", "") or "").strip()
    if persisted_split_fingerprint != _split_plan_fingerprint(split_plan):
        return []
    existing_relative_paths = audio_block.get("generated_part_relative_paths")
    if not isinstance(existing_relative_paths, list):
        return []
    if len(existing_relative_paths) > len(split_plan["parts"]):
        return []
    existing_paths: list[Path] = []
    for part_index, relative_path in enumerate(existing_relative_paths):
        expected_path = _audio_part_artifact_path(project_root, audio_block, part_index)
        resolved_path = _safe_project_artifact_path(project_root, relative_path)
        if resolved_path is None:
            return []
        if resolved_path != expected_path or not resolved_path.is_file() or not _is_valid_wav_path(resolved_path):
            return []
        existing_paths.append(resolved_path)
    return existing_paths


def _split_plan_fingerprint(split_plan: dict[str, object]) -> str:
    """
    @brief      Build one stable fingerprint for a current split-generation plan.
    @param[in]  split_plan Split plan payload.
    @return     Hex-encoded split plan fingerprint.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.1
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.1
    """
    for field_name in ("audio_relative_path", "metadata_relative_path"):
        artifact_path = _safe_project_artifact_path(project_root, audio_block.get(field_name))
        if artifact_path is None:
            continue
        if artifact_path.is_file():
            artifact_path.unlink()
    part_paths = audio_block.get("generated_part_relative_paths")
    if isinstance(part_paths, list):
        for relative_path in part_paths:
            artifact_path = _safe_project_artifact_path(project_root, relative_path)
            if artifact_path is None:
                continue
            if artifact_path.is_file():
                artifact_path.unlink()


def _cleared_audio_fields() -> dict[str, object]:
    """
    @brief      Build cleared generated-audio fields for one invalidated Audio Block.
    @return     Cleared Audio Blocks field mapping.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.1
    """
    return {
        "audio_relative_path": None,
        "metadata_relative_path": None,
        "generated": False,
        "approved": False,
        "approved_at": None,
        "generated_at": None,
        "runtime_result_summary": "",
        "split_part_count": 1,
        "split_strategy": "single",
        "generated_part_relative_paths": [],
        "generation_fingerprint": None,
        "split_plan_fingerprint": None,
        "warning_flags": [],
    }


def _remap_audio_block_artifacts(
    project_root: Path,
    old_block: AudioBlockPayload,
    new_block: AudioBlockPayload,
) -> AudioBlockPayload:
    """
    @brief      Move generated artifacts when a preserved Audio Block sequence changes.
    @param[in]  project_root Active project root folder.
    @param[in]  old_block Existing generated Audio Block payload.
    @param[in]  new_block New Speech Block-aligned Audio Block payload.
    @return     Existing block updated with new identifiers and artifact paths.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.1
    """
    remapped_block = dict(old_block)
    remapped_block.update(
        {
            "speech_block_id": str(new_block.get("speech_block_id", "")).strip(),
            "sequence_index": int(new_block.get("sequence_index", 0)),
            "chunk_id": str(new_block.get("chunk_id", "")).strip(),
            "speaker_id": str(new_block.get("speaker_id", "")).strip(),
            "speaker_display_name": str(new_block.get("speaker_display_name", "")).strip(),
            "normalized_speaker_name": str(new_block.get("normalized_speaker_name", "")).strip(),
            "content_kind": str(new_block.get("content_kind", "")).strip(),
            "metadata_only": bool(new_block.get("metadata_only", False)),
            "special_block_status": new_block.get("special_block_status"),
            "text": str(new_block.get("text", "")),
            "voice_target_id": str(new_block.get("voice_target_id", "")).strip(),
            "voice_source_kind": str(new_block.get("voice_source_kind", "")).strip(),
        }
    )
    if not bool(remapped_block.get("generated", False)) or bool(remapped_block.get("metadata_only", False)):
        return remapped_block
    old_audio_relative_path = _optional_string(old_block.get("audio_relative_path"))
    old_metadata_relative_path = _optional_string(old_block.get("metadata_relative_path"))
    new_audio_path, new_metadata_path = _audio_artifact_paths(
        project_root,
        str(new_block.get("chunk_id", "")).strip(),
        int(new_block.get("sequence_index", 0)),
        str(new_block.get("normalized_speaker_name", "")),
    )
    if old_audio_relative_path:
        old_audio_path = _safe_project_artifact_path(project_root, old_audio_relative_path)
        if old_audio_path is not None and old_audio_path.is_file() and old_audio_path != new_audio_path:
            new_audio_path.parent.mkdir(parents=True, exist_ok=True)
            if new_audio_path.is_file():
                new_audio_path.unlink()
            old_audio_path.rename(new_audio_path)
            remapped_block["audio_relative_path"] = relative_to_project(project_root, new_audio_path)
    if old_metadata_relative_path:
        old_metadata_path = _safe_project_artifact_path(project_root, old_metadata_relative_path)
        if old_metadata_path is None:
            return remapped_block
        if old_metadata_path.is_file():
            metadata_payload = json.loads(old_metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata_payload, dict):
                metadata_payload = {}
            metadata_payload.update(
                {
                    "speech_block_id": str(new_block.get("speech_block_id", "")).strip(),
                    "chunk_id": str(new_block.get("chunk_id", "")).strip(),
                    "sequence_index": int(new_block.get("sequence_index", 0)),
                    "speaker_display_name": str(new_block.get("speaker_display_name", "")).strip(),
                    "normalized_speaker_name": str(new_block.get("normalized_speaker_name", "")).strip(),
                    "text": str(new_block.get("text", "")),
                    "voice_target_id": str(new_block.get("voice_target_id", "")).strip(),
                }
            )
            new_metadata_path.parent.mkdir(parents=True, exist_ok=True)
            if old_metadata_path != new_metadata_path:
                if new_metadata_path.is_file():
                    new_metadata_path.unlink()
                old_metadata_path.unlink()
            write_json_atomic(new_metadata_path, metadata_payload)
            remapped_block["metadata_relative_path"] = relative_to_project(project_root, new_metadata_path)
    return remapped_block


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
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
        "special_block_status": str(audio_block.get("special_block_status", "") or "").strip(),
        "pause_duration_ms": _optional_int(audio_block.get("pause_duration_ms"), None),
        "text": str(audio_block.get("text", "")),
        "voice_target_id": voice_target_id,
        "voice_source_kind": str(audio_block.get("voice_source_kind", "")).strip(),
        "voice_assignment_mode": str(generation_context.get("voice_assignment_mode", "")).strip(),
        "original_language": str(generation_context.get("original_language", "")).strip(),
        "voice_language": str(generation_context.get("voice_language", "")).strip(),
        "clone_model_id": str(generation_context.get("clone_model_id", "")).strip(),
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    normalized_kind = str(content_kind).strip()
    if normalized_kind == speech_blocks_service.CONTENT_KIND_PAUSE:
        return _SPECIAL_BLOCK_STATUS_IMPLEMENTED
    if normalized_kind in {
        speech_blocks_service.CONTENT_KIND_BACKGROUND_NOISE,
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.8.0
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
        metadata_only_completed = metadata_only and speech_block_approved
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
                "voice_target_id": _voice_target_id_for_block(speech_block, voice_assignment_mode),
                "voice_source_kind": _voice_source_kind_for_block(speech_block, voice_assignment_mode),
                "audio_relative_path": None,
                "metadata_relative_path": None,
                "generated": metadata_only_completed,
                "approved": metadata_only_completed,
                "approved_at": _utc_now_iso() if metadata_only_completed else None,
                "generated_at": None,
                "runtime_result_summary": _metadata_only_summary(special_block_status),
                "split_part_count": 1,
                "split_strategy": "single",
                "model_token_budget": None,
                "model_audio_seconds_budget": None,
                "generated_part_relative_paths": [],
                "generation_fingerprint": None,
                "split_plan_fingerprint": None,
                "warning_flags": [],
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.4.0
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
            if project_root is not None:
                _delete_audio_block_artifacts(project_root, existing_block)
            continue
        block.update(
            {
                "audio_relative_path": existing_block.get("audio_relative_path"),
                "metadata_relative_path": existing_block.get("metadata_relative_path"),
                "pause_duration_ms": existing_block.get("pause_duration_ms"),
                "special_block_status": existing_block.get("special_block_status") or block.get("special_block_status"),
                "generated": bool(existing_block.get("generated", False)),
                "approved": bool(existing_block.get("approved", False)),
                "approved_at": existing_block.get("approved_at"),
                "generated_at": existing_block.get("generated_at"),
                "runtime_result_summary": str(existing_block.get("runtime_result_summary", "")),
                "split_part_count": int(existing_block.get("split_part_count", 1)),
                "split_strategy": str(existing_block.get("split_strategy", "single")).strip() or "single",
                "model_token_budget": existing_block.get("model_token_budget"),
                "model_audio_seconds_budget": existing_block.get("model_audio_seconds_budget"),
                "generated_part_relative_paths": list(existing_block.get("generated_part_relative_paths", []))
                if isinstance(existing_block.get("generated_part_relative_paths"), list)
                else [],
                "generation_fingerprint": current_fingerprint or existing_block.get("generation_fingerprint"),
                "split_plan_fingerprint": existing_block.get("split_plan_fingerprint"),
                "warning_flags": _normalize_warning_flags(existing_block.get("warning_flags")),
            }
        )
    return merged_blocks


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.1
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
    @brief      Persist one report-only Audio Blocks update after approvals or single-block regeneration.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_blocks Updated Audio Blocks payload list.
    @param[in]  clone_profiles Optional updated direct-clone source profile list.
    @return     Updated report payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    existing_state = load_operation_state(project_root) or {}
    metadata = existing_state.get("metadata", {})
    voice_language = str(metadata.get("voice_language", "")).strip() if isinstance(metadata, dict) else ""
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    current_clone_profiles = load_voice_clone_profiles(project_root) if clone_profiles is None else clone_profiles
    report = _rebuild_report(
        audio_blocks,
        voice_language,
        speech_blocks,
        warning_records=[],
        prompt_count=len(current_clone_profiles),
        reused_prompt_count=_metadata_int(existing_state, "reused_prompt_count", 0),
        regenerated_prompt_count=_metadata_int(existing_state, "regenerated_prompt_count", 0),
        current_phase=str(metadata.get("current_phase", _GENERATE_PHASE)).strip() or _GENERATE_PHASE
        if isinstance(metadata, dict)
        else _GENERATE_PHASE,
    )
    persisted_state = _build_operation_state(
        project_root,
        speech_blocks,
        audio_blocks,
        current_clone_profiles,
        status=str(existing_state.get("status", "completed")).strip() or "completed",
        started_at=str(existing_state.get("started_at", "")).strip() or _utc_now_iso(),
        completed_at=str(existing_state.get("completed_at", "")).strip() or _utc_now_iso(),
        voice_language=voice_language,
        input_fingerprint=str(metadata.get("input_fingerprint", "")).strip(),
        current_phase=str(metadata.get("current_phase", _GENERATE_PHASE)).strip() or _GENERATE_PHASE,
        current_block_id=str(metadata.get("current_block_id", "")).strip() or None,
        next_profile_index=int(_resume_checkpoint_field(existing_state, "next_profile_index", 0)),
        next_speech_block_index=int(
            _resume_checkpoint_field(
                existing_state,
                "next_speech_block_index",
                len(audio_blocks),
            )
        ),
        reused_prompt_count=_metadata_int(existing_state, "reused_prompt_count", 0),
        regenerated_prompt_count=_metadata_int(existing_state, "regenerated_prompt_count", 0),
    )
    _persist_state(
        project_root,
        speech_blocks,
        audio_blocks,
        current_clone_profiles,
        report,
        persisted_state,
    )
    return report


def _persist_split_checkpoint(
    project_root: Path,
    generation_context: dict[str, object],
    audio_blocks: list[AudioBlockPayload],
    clone_profiles: list[VoiceCloneProfilePayload],
    checkpoint_block: AudioBlockPayload,
    active_block_index: int,
    next_split_part_index: int,
    started_at: str,
    reused_prompt_count: int,
    regenerated_prompt_count: int,
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
    @param[in]  reused_prompt_count Count of reused clone prompts.
    @param[in]  regenerated_prompt_count Count of regenerated clone prompts.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    checkpoint_blocks = list(audio_blocks)
    checkpoint_blocks[active_block_index] = _normalize_persisted_audio_block(dict(checkpoint_block))
    report = _rebuild_report(
        checkpoint_blocks,
        str(generation_context["voice_language"]),
        list(generation_context["speech_blocks"]),
        warning_records=[],
        prompt_count=len(clone_profiles),
        reused_prompt_count=reused_prompt_count,
        regenerated_prompt_count=regenerated_prompt_count,
        current_phase=_GENERATE_PHASE,
    )
    _persist_state(
        project_root,
        list(generation_context["speech_blocks"]),
        checkpoint_blocks,
        clone_profiles,
        report,
        _build_operation_state(
            project_root,
            list(generation_context["speech_blocks"]),
            checkpoint_blocks,
            clone_profiles,
            status="running",
            started_at=started_at,
            completed_at=None,
            voice_language=str(generation_context["voice_language"]),
            input_fingerprint=str(generation_context["input_fingerprint"]),
            current_phase=_GENERATE_PHASE,
            current_block_id=str(checkpoint_block.get("speech_block_id", "")).strip(),
            next_profile_index=len(generation_context["voice_targets"]),
            next_speech_block_index=active_block_index,
            reused_prompt_count=reused_prompt_count,
            regenerated_prompt_count=regenerated_prompt_count,
            next_split_part_index=next_split_part_index,
        ),
    )


def _persist_cancelled_state(
    project_root: Path,
    generation_context: dict[str, object],
    audio_blocks: list[AudioBlockPayload],
    clone_profiles: list[VoiceCloneProfilePayload],
    started_at: str,
    current_phase: str,
    current_block_id: str | None,
    next_profile_index: int,
    next_speech_block_index: int,
    reused_prompt_count: int,
    regenerated_prompt_count: int,
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
    @param[in]  next_profile_index Next voice-target profile index.
    @param[in]  next_speech_block_index Next speech-block index.
    @param[in]  reused_prompt_count Count of reused prompts.
    @param[in]  regenerated_prompt_count Count of regenerated prompts.
    @param[in]  next_split_part_index Next split-part index inside the current block.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    report = _rebuild_report(
        audio_blocks,
        str(generation_context["voice_language"]),
        list(generation_context["speech_blocks"]),
        warning_records=[],
        prompt_count=len(clone_profiles),
        reused_prompt_count=reused_prompt_count,
        regenerated_prompt_count=regenerated_prompt_count,
        current_phase=current_phase,
    )
    _persist_state(
        project_root,
        list(generation_context["speech_blocks"]),
        audio_blocks,
        clone_profiles,
        report,
        _build_operation_state(
            project_root,
            list(generation_context["speech_blocks"]),
            audio_blocks,
            clone_profiles,
            status="cancelled",
            started_at=started_at,
            completed_at=None,
            voice_language=str(generation_context["voice_language"]),
            input_fingerprint=str(generation_context["input_fingerprint"]),
            current_phase=current_phase,
            current_block_id=current_block_id,
            next_profile_index=next_profile_index,
            next_speech_block_index=next_speech_block_index,
            reused_prompt_count=reused_prompt_count,
            regenerated_prompt_count=regenerated_prompt_count,
            next_split_part_index=next_split_part_index,
        ),
    )


def _rebuild_report(
    audio_blocks: list[AudioBlockPayload],
    voice_language: str,
    speech_blocks: list[dict[str, object]],
    warning_records: list[dict[str, object]],
    updated_at: str | None = None,
    prompt_count: int = 0,
    reused_prompt_count: int = 0,
    regenerated_prompt_count: int = 0,
    current_phase: str | None = None,
) -> AudioBlocksReportPayload:
    """
    @brief      Recompute the Audio Blocks report from the current persisted state.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @param[in]  voice_language Selected character-voices voice language.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  warning_records Current warning entry list.
    @param[in]  updated_at Optional report timestamp override.
    @param[in]  prompt_count Current persisted prompt count.
    @param[in]  reused_prompt_count Count of reusable prompts reused from persisted project data.
    @param[in]  regenerated_prompt_count Count of reusable prompts freshly created in the current run.
    @param[in]  current_phase Optional resumable current-phase token.
    @return     Rebuilt Audio Blocks report payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    total_block_count = len(speech_blocks)
    generated_block_count = _generated_count(audio_blocks)
    approved_block_count = _approved_count(audio_blocks)
    if total_block_count <= 0:
        stage_status = AUDIO_BLOCKS_STAGE_NOT_STARTED
    elif approved_block_count >= total_block_count and generated_block_count >= total_block_count:
        stage_status = AUDIO_BLOCKS_STAGE_COMPLETED
    elif generated_block_count > 0 or approved_block_count > 0:
        stage_status = AUDIO_BLOCKS_STAGE_IN_PROGRESS
    else:
        stage_status = AUDIO_BLOCKS_STAGE_NOT_STARTED
    return {
        "voice_language": voice_language,
        "audio_blocks_stage_status": stage_status,
        "generated_block_count": generated_block_count,
        "approved_block_count": approved_block_count,
        "total_block_count": total_block_count,
        "prompt_count": max(int(prompt_count), 0),
        "reused_prompt_count": max(int(reused_prompt_count), 0),
        "regenerated_prompt_count": max(int(regenerated_prompt_count), 0),
        "current_phase": str(current_phase).strip() if current_phase else None,
        "warning_count": len(warning_records),
        "warnings": list(warning_records),
        "updated_at": updated_at or _utc_now_iso(),
    }


def _build_operation_state(
    project_root: Path,
    speech_blocks: list[dict[str, object]],
    audio_blocks: list[AudioBlockPayload],
    clone_profiles: list[VoiceCloneProfilePayload],
    status: str,
    started_at: str,
    completed_at: str | None,
    voice_language: str,
    input_fingerprint: str,
    current_phase: str,
    current_block_id: str | None,
    next_profile_index: int,
    next_speech_block_index: int,
    reused_prompt_count: int = 0,
    regenerated_prompt_count: int = 0,
    next_split_part_index: int = 0,
) -> OperationStatePayload:
    """
    @brief      Build one persisted Audio Blocks operation-state payload.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @param[in]  clone_profiles Current persisted direct-clone source profile list.
    @param[in]  status Persisted operation status token.
    @param[in]  started_at Operation start timestamp.
    @param[in]  completed_at Operation completion timestamp or `None`.
    @param[in]  voice_language Selected character-voices voice language.
    @param[in]  input_fingerprint Stable validated input fingerprint.
    @param[in]  current_phase Current resumable phase token.
    @param[in]  current_block_id Current generating speech-block id or `None`.
    @param[in]  next_profile_index Next voice-target profile index.
    @param[in]  next_speech_block_index Next speech-block index.
    @param[in]  reused_prompt_count Count of reusable prompts reused from persisted project data.
    @param[in]  regenerated_prompt_count Count of reusable prompts freshly created in the current run.
    @param[in]  next_split_part_index Next split part index for the current block.
    @return     Persisted operation-state payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.0
    """
    input_path = _speech_blocks_snapshot_path(project_root)
    output_path = build_operation_output_path(project_root, "audio_blocks", config.AUDIO_BLOCKS_OUTPUT_FILE_NAME)
    report_path = build_operation_output_path(project_root, "audio_blocks", config.AUDIO_BLOCKS_REPORT_FILE_NAME)
    clone_path = build_operation_output_path(
        project_root,
        "audio_blocks",
        config.AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME,
    )
    artifact_paths = [relative_to_project(project_root, report_path), relative_to_project(project_root, clone_path)]
    generated_root = _generated_audio_root(project_root)
    if generated_root.is_dir():
        artifact_paths.extend(relative_to_project(project_root, path) for path in sorted(generated_root.rglob("*")))
    return build_operation_state_payload(
        status=status,
        input_paths=[relative_to_project(project_root, input_path)],
        output_paths=[relative_to_project(project_root, output_path)],
        artifact_paths=artifact_paths,
        progress_current=_generated_count(audio_blocks),
        progress_total=len(speech_blocks),
        mode=_MODE,
        started_at=started_at,
        completed_at=completed_at,
        warning_count=0,
        metadata={
            "voice_language": voice_language,
            "input_fingerprint": input_fingerprint,
            "speech_block_count": len(speech_blocks),
            "generated_block_count": _generated_count(audio_blocks),
            "approved_block_count": _approved_count(audio_blocks),
            "clone_profile_count": len(clone_profiles),
            "prompt_count": len(clone_profiles),
            "reused_prompt_count": max(int(reused_prompt_count), 0),
            "regenerated_prompt_count": max(int(regenerated_prompt_count), 0),
            "current_phase": current_phase,
            "current_block_id": current_block_id,
            "model_id": _first_clone_model_id(clone_profiles),
            "model_token_budget": _first_present(audio_blocks, "model_token_budget"),
            "model_audio_seconds_budget": _first_present(audio_blocks, "model_audio_seconds_budget"),
        },
        resume_checkpoint={
            "next_profile_index": max(next_profile_index, 0),
            "next_speech_block_index": max(next_speech_block_index, 0),
            "next_split_part_index": max(next_split_part_index, 0),
        },
    )


def _persist_state(
    project_root: Path,
    speech_blocks: list[dict[str, object]],
    audio_blocks: list[AudioBlockPayload],
    clone_profiles: list[VoiceCloneProfilePayload],
    report: AudioBlocksReportPayload,
    operation_state: OperationStatePayload,
) -> None:
    """
    @brief      Persist the Audio Blocks snapshot, output, clone profiles, report, and state.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @param[in]  clone_profiles Current persisted direct-clone source profile list.
    @param[in]  report Current Audio Blocks report payload.
    @param[in]  operation_state Current Audio Blocks operation-state payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    _ = speech_blocks
    write_operation_json_artifact(project_root, "audio_blocks", config.AUDIO_BLOCKS_OUTPUT_FILE_NAME, audio_blocks)
    write_operation_json_artifact(
        project_root,
        "audio_blocks",
        config.AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME,
        clone_profiles,
    )
    write_operation_json_artifact(project_root, "audio_blocks", config.AUDIO_BLOCKS_REPORT_FILE_NAME, report)
    write_operation_json_artifact(
        project_root,
        "audio_blocks",
        config.AUDIO_BLOCKS_STATE_FILE_NAME,
        operation_state,
    )


def _speech_blocks_snapshot_path(project_root: Path) -> Path:
    """
    @brief      Resolve the Audio Blocks Speech Blocks snapshot path.
    @param[in]  project_root Active project root folder.
    @return     Absolute project-local snapshot path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    return project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    return str(speech_block.get("content_kind", "")).strip() in {
        speech_blocks_service.CONTENT_KIND_BACKGROUND_NOISE,
        speech_blocks_service.CONTENT_KIND_PAUSE,
        speech_blocks_service.CONTENT_KIND_INDICATION,
    }


def _speech_block_is_approved(speech_block: dict[str, object]) -> bool:
    """
    @brief      Return whether one Speech Block is approved for Audio Blocks generation.
    @param[in]  speech_block Persisted Speech Blocks payload.
    @return     `True` when the Speech Block approval flag is set.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return bool(speech_block.get("approved", False))


def _generated_count(audio_blocks: list[AudioBlockPayload]) -> int:
    """
    @brief      Count generated Audio Blocks entries.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @return     Number of entries with generated audio.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    return sum(1 for block in audio_blocks if bool(block.get("generated", False)))


def _first_incomplete_block_index(audio_blocks: list[AudioBlockPayload]) -> int:
    """
    @brief      Resolve the first block index that still needs generated audio.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @return     Zero-based first incomplete index, or list length when complete.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    for index, block in enumerate(audio_blocks):
        if bool(block.get("speech_block_approved", False)) and not bool(block.get("generated", False)):
            return index
    return len(audio_blocks)


def _approved_count(audio_blocks: list[AudioBlockPayload]) -> int:
    """
    @brief      Count approved Audio Blocks entries.
    @param[in]  audio_blocks Current Audio Blocks payload list.
    @return     Number of approved entries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    return sum(1 for block in audio_blocks if bool(block.get("approved", False)))


def _normalize_persisted_audio_block(payload: dict[str, object]) -> AudioBlockPayload:
    """
    @brief      Normalize one persisted Audio Blocks payload.
    @param[in]  payload Raw persisted payload.
    @return     Normalized Audio Blocks payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.4.0
    """
    if "chunk_sequence_index" in payload:
        raise ValueError(
            "Audio Blocks uses a legacy global-sequence schema. Reset and regenerate Audio Blocks for this project."
        )
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
        "voice_target_id": str(payload.get("voice_target_id", "")).strip(),
        "voice_source_kind": str(payload.get("voice_source_kind", "")).strip(),
        "audio_relative_path": _optional_string(payload.get("audio_relative_path")),
        "metadata_relative_path": _optional_string(payload.get("metadata_relative_path")),
        "generated": bool(payload.get("generated", False)),
        "approved": bool(payload.get("approved", False)),
        "approved_at": _optional_string(payload.get("approved_at")),
        "generated_at": _optional_string(payload.get("generated_at")),
        "runtime_result_summary": str(payload.get("runtime_result_summary", "")).strip(),
        "split_part_count": _optional_int(payload.get("split_part_count"), 1),
        "split_strategy": str(payload.get("split_strategy", "single")).strip() or "single",
        "model_token_budget": payload.get("model_token_budget"),
        "model_audio_seconds_budget": payload.get("model_audio_seconds_budget"),
        "generated_part_relative_paths": list(payload.get("generated_part_relative_paths", []))
        if isinstance(payload.get("generated_part_relative_paths"), list)
        else [],
        "generation_fingerprint": _optional_string(payload.get("generation_fingerprint")),
        "split_plan_fingerprint": _optional_string(payload.get("split_plan_fingerprint")),
        "warning_flags": _normalize_warning_flags(payload.get("warning_flags")),
    }


def _normalize_voice_clone_profile(payload: dict[str, object]) -> VoiceCloneProfilePayload:
    """
    @brief      Normalize one persisted Audio Blocks reusable clone-prompt payload.
    @param[in]  payload Raw persisted payload.
    @return     Normalized reusable clone-prompt payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.4.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    return hashlib.sha1(path.read_bytes()).hexdigest()  # noqa: S324


def _active_model_id_from_status(status_payload: dict[str, object]) -> str | None:
    """
    @brief      Resolve one active-model identifier from the normalized VoiceWeaver status payload.
    @param[in]  status_payload Current VoiceWeaver status payload.
    @return     Active model identifier or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
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
    @brief      Resolve the stable operation start timestamp for one Audio Blocks run.
    @param[in]  existing_state Existing operation-state payload.
    @return     Stable operation start timestamp.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    started_at_value = existing_state.get("started_at", "") if isinstance(existing_state, dict) else ""
    started_at = "" if started_at_value in (None, "") else str(started_at_value).strip()
    return started_at or _utc_now_iso()


def _resume_checkpoint_field(existing_state: dict[str, object], field_name: str, fallback: int) -> int:
    """
    @brief      Resolve one integer resume-checkpoint field from an operation-state payload.
    @param[in]  existing_state Existing operation-state payload.
    @param[in]  field_name Resume-checkpoint field name.
    @param[in]  fallback Fallback integer value.
    @return     Resolved integer checkpoint value.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
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


def _metadata_int(existing_state: dict[str, object], field_name: str, fallback: int = 0) -> int:
    """
    @brief      Resolve one integer metadata field from an operation-state payload.
    @param[in]  existing_state Existing operation-state payload.
    @param[in]  field_name Metadata field name.
    @param[in]  fallback Fallback integer value.
    @return     Resolved integer metadata value.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    if not isinstance(existing_state, dict):
        return fallback
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return fallback
    try:
        return int(metadata.get(field_name, fallback))
    except (TypeError, ValueError):
        return fallback


def _first_present(items: list[dict[str, object]], field_name: str) -> object:
    """
    @brief      Return the first non-empty field value from a list of payloads.
    @param[in]  items Payload list to inspect.
    @param[in]  field_name Field name to resolve.
    @return     First non-empty value, or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    for item in items:
        value = item.get(field_name)
        if value not in (None, ""):
            return value
    return None


def _first_clone_model_id(clone_profiles: list[VoiceCloneProfilePayload]) -> str | None:
    """
    @brief      Resolve the first persisted clone-model identifier from clone profiles.
    @param[in]  clone_profiles Current clone profile list.
    @return     Clone-model identifier or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    for profile in clone_profiles:
        model_id = _optional_string(profile.get("clone_model_id"))
        if model_id:
            return model_id
    return None


def _normalize_warning_flags(value: object) -> list[str]:
    """
    @brief      Normalize one warning-flag list payload.
    @param[in]  value Candidate warning-flag value.
    @return     Ordered warning-flag string list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    if not isinstance(value, list):
        return []
    normalized_flags: list[str] = []
    for item in value:
        normalized_item = str(item).strip()
        if normalized_item and normalized_item not in normalized_flags:
            normalized_flags.append(normalized_item)
    return normalized_flags


def _optional_int(value: object, fallback: int) -> int:
    """
    @brief      Normalize one optional integer payload field.
    @param[in]  value Candidate integer value.
    @param[in]  fallback Fallback value used when normalization fails.
    @return     Normalized integer.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
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
