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
from tempfile import TemporaryDirectory

from audiomancer import config
from audiomancer.services import (
    audio_blocks_artifact_service,
    audio_blocks_generation_service,
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
from audiomancer.services.persistence_service import replace_project_files, validate_publication_path, write_json_atomic
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
_AUDIO_BLOCK_FINGERPRINT_VERSION = 3
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

# @brief Optional provenance and split-plan fields.
_OPTIONAL_BLOCK_FIELDS = frozenset(("split_part_count", "split_plan_fingerprint", "audio_stale",
                                    "configured_fingerprint"))

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
        if not block_fields.issubset(set(_BLOCK_FIELDS) | set(_OPTIONAL_BLOCK_FIELDS)):
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
    resolved_project_root = Path(project_root).resolve()
    context = _resolve_generation_context(resolved_project_root, manifest, runtime_settings)
    existing_state = load_operation_state(resolved_project_root) or {}
    started_at = _resolve_started_at(existing_state)
    clone_profiles = load_voice_clone_profiles(resolved_project_root)
    saved_blocks = load_audio_blocks(resolved_project_root)
    voice_assignment_mode = str(context["voice_assignment_mode"])
    blocks = _merge_existing_audio_blocks(context["speech_blocks"], saved_blocks, voice_assignment_mode)
    total = len(context["speech_blocks"])
    checkpoint_id = (existing_state.get("metadata") or {}).get("current_block_id")
    checkpoint_index = _resume_checkpoint_field(existing_state, "next_speech_block_index", 0)
    checkpoint_part = _resume_checkpoint_field(existing_state, "next_split_part_index", 0)

    def persist(
        status: str,
        phase: str,
        block_id: str | None,
        order_index: int,
        next_part: int = 0,
        snapshot: list[AudioBlockPayload] | None = None,
        wav_replacement: tuple[Path, Path] | None = None,
    ) -> AudioBlocksReportPayload:
        """
        @brief      Save the current batch snapshot and optional completed WAV.
        @param[in]  status Batch status.
        @param[in]  phase Generation phase.
        @param[in]  block_id Active block identifier.
        @param[in]  order_index Next position in the generation order.
        @param[in]  next_part Next part for the active block.
        @param[in]  snapshot Optional partial block snapshot.
        @param[in]  wav_replacement Optional candidate and canonical WAV paths.
        @return     Published Audio Blocks report.
        """
        return _persist_document(
            resolved_project_root,
            blocks if snapshot is None else snapshot,
            clone_profiles,
            status=status,
            voice_language=str(context["voice_language"]),
            input_fingerprint=str(context["input_fingerprint"]),
            run_token=started_at,
            current_phase=phase,
            current_block_id=block_id,
            next_speech_block_index=order_index,
            next_split_part_index=next_part,
            total_block_count=total,
            wav_replacement=wav_replacement,
        )

    if not existing_state:
        persist("running", _PROFILE_PHASE, None, 0)
    _emit_progress(progress_callback, _generated_count(blocks), total, "Preparing reusable voice prompts...")
    clone_model_id = str(context["clone_model_id"])
    try:
        if context["needs_clone"]:
            context.update(_ensure_clone_model_loaded(
                runtime_settings, clone_model_id, dict(context["clone_model_payload"]),
                progress_callback, total, _generated_count(blocks), cancel_requested=cancel_requested,
            ))
        context["input_fingerprint"] = _build_input_fingerprint(
            context["speech_blocks"], context["voice_targets"], str(context["voice_language"]),
            clone_model_id, manifest, context,
        )
        blocks = _merge_existing_audio_blocks(
            context["speech_blocks"], saved_blocks, voice_assignment_mode,
            generation_context=context, project_root=resolved_project_root,
            cached_clone_inputs=not context["needs_clone"],
        )
        generation_order = _audio_generation_order_indices(blocks, bool(context["generate_scene_ambience_audio"]))
        pending = [
            (order_index, block_index)
            for order_index, block_index in enumerate(generation_order)
            if bool(blocks[block_index].get("speech_block_approved", False))
            and not bool(blocks[block_index].get("metadata_only", False))
            and not _audio_block_has_reusable_audio(blocks[block_index], resolved_project_root)
        ]
        if checkpoint_part > 0:
            active = next(
                (position for position in pending if blocks[position[1]]["speech_block_id"] == checkpoint_id),
                None,
            )
            previous = next((block for block in saved_blocks if block["speech_block_id"] == checkpoint_id), {})
            previous_fingerprint = previous.get("generation_fingerprint")
            if (
                active is not None and previous_fingerprint
                and previous_fingerprint == blocks[active[1]].get("generation_fingerprint")
            ):
                pending.remove(active)
                pending.insert(0, active)
                checkpoint_index = active[0]
            else:
                checkpoint_id, checkpoint_part = None, 0

        targets_needed = {
            str(blocks[block_index]["voice_target_id"]) for _, block_index in pending
            if blocks[block_index]["content_kind"] != speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
        }
        for voice_target in context["voice_targets"]:
            if str(voice_target["voice_target_id"]) not in targets_needed:
                continue
            raise_if_cancelled(cancel_requested)
            clone_profiles, reused = _prepare_clone_profile(
                context, voice_target, clone_profiles, runtime_settings, cancel_requested=cancel_requested,
            )
            persist("running", _PROFILE_PHASE, checkpoint_id, checkpoint_index, checkpoint_part)
            action = "Reused" if reused else "Prepared"
            _emit_progress(
                progress_callback, _generated_count(blocks), total,
                f"{action} clone prompt for {voice_target['display_name']}.",
            )
        clones_by_id = {str(profile["voice_target_id"]): profile for profile in clone_profiles}
        active_model_id = clone_model_id
        for order_index, block_index in pending:
            raise_if_cancelled(cancel_requested)
            current = blocks[block_index]
            block_id = str(current["speech_block_id"])
            audio_path = _audio_artifact_path(resolved_project_root, block_id)
            if block_id != checkpoint_id or not checkpoint_part:
                persist("running", _GENERATE_PHASE, block_id, order_index)

            def save_part(
                partial: AudioBlockPayload,
                next_part: int,
                position: int = block_index,
                order: int = order_index,
            ) -> None:
                """
                @brief      Checkpoint a validated part of the current block.
                @param[in]  partial Audio Block snapshot.
                @param[in]  next_part Index of the next part.
                @param[in]  position Block index in the book.
                @param[in]  order Block index in the generation order.
                """
                snapshot = list(blocks)
                snapshot[position] = partial
                persist("running", _GENERATE_PHASE, str(partial["speech_block_id"]), order, next_part, snapshot)

            with TemporaryDirectory(prefix=".audio-block-stage-", dir=resolved_project_root) as stage:
                candidate = Path(stage) / audio_path.name
                if current["content_kind"] == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE:
                    active_model_id = str(context["sound_model_id"])
                    _ensure_sound_model_loaded(
                        runtime_settings, active_model_id, progress_callback, total,
                        _generated_count(blocks), cancel_requested=cancel_requested,
                    )
                    generated = _generate_scene_ambience_audio_block(
                        resolved_project_root, current, context, runtime_settings,
                        cancel_requested=cancel_requested, output_path=candidate,
                    )
                else:
                    if active_model_id != clone_model_id:
                        _ensure_clone_model_loaded(
                            runtime_settings, clone_model_id, dict(context["clone_model_payload"]),
                            progress_callback, total, _generated_count(blocks), cancel_requested=cancel_requested,
                        )
                        active_model_id = clone_model_id
                    clone_profile = clones_by_id.get(str(current["voice_target_id"]))
                    if clone_profile is None:
                        raise RuntimeError(f"Missing clone profile for voice target '{current['voice_target_id']}'.")
                    generated = _generate_audio_block(
                        resolved_project_root, current, clone_profile, context, runtime_settings,
                        cancel_requested=cancel_requested, checkpoint_callback=save_part,
                        next_split_part_index=checkpoint_part if block_id == checkpoint_id else 0,
                        output_path=candidate,
                    )
                raise_if_cancelled(cancel_requested)
                blocks[block_index] = generated
                persist("running", _GENERATE_PHASE, None, order_index + 1, wav_replacement=(candidate, audio_path))
            _remove_published_parts(resolved_project_root, generated)
            _emit_progress(
                progress_callback, _generated_count(blocks), total,
                f"Generated audio for {generated['speaker_display_name']}.",
            )
        raise_if_cancelled(cancel_requested)
    except operation_runtime_service.OperationCancelledError:
        _mark_audio_blocks_cancelled(resolved_project_root)
        raise

    stage_status = _derived_stage_status(total, blocks)
    completed = stage_status == AUDIO_BLOCKS_STAGE_COMPLETED
    report = persist(
        AUDIO_BLOCKS_STAGE_COMPLETED if completed else AUDIO_BLOCKS_STAGE_IN_PROGRESS,
        _GENERATE_PHASE, None, len(blocks),
    )
    _emit_progress(
        progress_callback, _generated_count(blocks), total,
        "Audio Blocks generation completed." if completed else "Generated audio for the approved Speech Blocks.",
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
                "configured_fingerprint": old_block.get("configured_fingerprint"),
                "audio_stale": old_block.get("audio_stale", False),
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
    resolved_project_root = Path(project_root).resolve()
    target_block_id = str(speech_block_id).strip()
    generation_context = _resolve_generation_context(
        resolved_project_root, manifest, runtime_settings, selected_block_id=target_block_id,
    )
    audio_blocks = _merge_existing_audio_blocks(
        generation_context["speech_blocks"],
        load_audio_blocks(resolved_project_root),
        str(generation_context.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)),
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
    if not audio_can_regenerate(audio_blocks[target_index]):
        raise ValueError("The selected metadata-only audio block cannot be regenerated.")

    if (
        str(audio_blocks[target_index].get("content_kind", "")).strip()
        == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
    ):
        _ensure_sound_model_loaded(
            runtime_settings,
            str(generation_context.get("sound_model_id", "")),
            progress_callback,
            len(audio_blocks),
            _generated_count(audio_blocks),
            cancel_requested=cancel_requested,
        )
        old_block = audio_blocks[target_index]
        audio_path = _audio_artifact_path(resolved_project_root, target_block_id)
        with TemporaryDirectory(prefix=".audio-block-stage-", dir=resolved_project_root) as stage:
            candidate = Path(stage) / audio_path.name
            audio_blocks[target_index] = _generate_scene_ambience_audio_block(
                resolved_project_root, old_block, generation_context, runtime_settings,
                cancel_requested=cancel_requested, output_path=candidate,
            )
            raise_if_cancelled(cancel_requested)
            report = _persist_report_update(
                resolved_project_root, audio_blocks, wav_replacement=(candidate, audio_path),
            )
        _remove_published_parts(resolved_project_root, old_block)
        return report

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
    old_block = audio_blocks[target_index]
    audio_path = _audio_artifact_path(resolved_project_root, target_block_id)
    with TemporaryDirectory(prefix=".audio-block-stage-", dir=resolved_project_root) as stage:
        candidate = Path(stage) / audio_path.name
        audio_blocks[target_index] = _generate_audio_block(
            resolved_project_root, old_block, clone_profile, generation_context, runtime_settings,
            cancel_requested=cancel_requested, force_restart=True, output_path=candidate,
        )
        raise_if_cancelled(cancel_requested)
        report = _persist_report_update(
            resolved_project_root, audio_blocks, clone_profiles, wav_replacement=(candidate, audio_path),
        )
    _remove_published_parts(resolved_project_root, old_block)
    return report


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


def pending_speech_blocks(
    project_root: Path,
    speech_blocks: list[dict[str, object]],
    audio_blocks: list[AudioBlockPayload],
    generate_ambience: bool,
) -> list[dict[str, object]]:
    """
    @brief      Return approved rows whose requested output is missing or unusable.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_blocks Current Speech Blocks.
    @param[in]  audio_blocks Persisted generated state.
    @param[in]  generate_ambience Whether sound cues are requested.
    @return     Rows needing metadata or audio generation.
    """
    existing = {str(block["speech_block_id"]): block for block in audio_blocks}
    pending = []
    for speech in speech_blocks:
        if not _speech_block_is_approved(speech):
            continue
        block = existing.get(str(speech["speech_block_id"]), {})
        if speech["content_kind"] == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE:
            if generate_ambience and not _audio_block_owns_real_artifact(project_root, block, require_valid=True):
                pending.append(speech)
        elif not _audio_block_has_reusable_audio(block, project_root):
            pending.append(speech)
    return pending


def requires_runtime(speech_blocks: list[dict[str, object]]) -> bool:
    """
    @brief      Return whether the requested work needs speech or sound synthesis.
    @param[in]  speech_blocks Already selected pending Speech Blocks.
    @return     True when VoiceWeaver is needed.
    """
    return any(
        block["content_kind"] not in {
            speech_blocks_service.CONTENT_KIND_PAUSE, speech_blocks_service.CONTENT_KIND_INDICATION,
        }
        for block in speech_blocks
    )


def _resolve_generation_context(
    project_root: Path,
    manifest: dict[str, object],
    runtime_settings: dict[str, object],
    *,
    selected_block_id: str | None = None,
) -> dict[str, object]:
    """
    @brief      Resolve voice references and models for the requested Audio Blocks work.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @param[in]  runtime_settings Runtime connection and discovered models.
    @param[in]  selected_block_id Explicit block to regenerate, or None for a batch.
    @return     Validated generation context with all rows and the requested resources.
    @exception  ValueError Raised when a requested resource is unavailable.
    """
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root, generation_manifest=manifest)
    if not speech_blocks:
        raise ValueError("Generate Speech Blocks before starting Audio Blocks.")
    generate_ambience = bool(runtime_settings.get("generate_scene_ambience_audio", False))
    if selected_block_id is None:
        scope = [block for block in speech_blocks if _speech_block_is_approved(block)]
        if not scope:
            raise ValueError("Approve at least one Speech Block before starting Audio Blocks.")
        requested = pending_speech_blocks(project_root, scope, load_audio_blocks(project_root), generate_ambience)
    else:
        selected = next((block for block in speech_blocks if block["speech_block_id"] == selected_block_id), None)
        if selected is None:
            raise ValueError("The selected audio block was not found.")
        if selected["content_kind"] in {
            speech_blocks_service.CONTENT_KIND_PAUSE, speech_blocks_service.CONTENT_KIND_INDICATION,
        }:
            raise ValueError("The selected metadata-only audio block cannot be regenerated.")
        if not _speech_block_is_approved(selected):
            raise ValueError("Approve the selected Speech Block before generating its audio.")
        scope = requested = [selected]
        generate_ambience |= selected["content_kind"] == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE

    context = _build_generation_context(project_root, manifest, runtime_settings, scope, requested, generate_ambience)
    context["speech_blocks"] = speech_blocks
    context["input_fingerprint"] = _build_input_fingerprint(
        speech_blocks, context["voice_targets"], str(context["voice_language"]),
        str(context["clone_model_id"]), manifest, context,
    )
    return context


def audio_blocks_for_review(
    project_root: Path,
    manifest: dict[str, object],
    speech_blocks: list[dict[str, object]],
    audio_blocks: list[AudioBlockPayload],
    runtime_settings: dict[str, object],
) -> list[AudioBlockPayload]:
    """
    @brief      Compare existing audio against locally available synthesis inputs.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Current project manifest.
    @param[in]  speech_blocks Current Speech Blocks.
    @param[in]  audio_blocks Persisted Audio Blocks.
    @param[in]  runtime_settings Settings and cached model descriptions.
    @return     Audio Blocks with review markers computed without a runtime call.
    @exception  None
    """
    review_ids = {
        block["speech_block_id"] for block in audio_blocks
        if is_generated(block) and not block.get("metadata_only") and block.get("generation_fingerprint")
    }
    if not review_ids or not runtime_settings.get("discovered_models"):
        return audio_blocks
    scope = [block for block in speech_blocks if block["speech_block_id"] in review_ids]
    context = _build_generation_context(project_root, manifest, runtime_settings, scope, [], False)
    current_blocks = {
        block["speech_block_id"]: block
        for block in _initialize_audio_blocks(scope, str(context["voice_assignment_mode"]))
    }
    reviewed_blocks = []
    for block in audio_blocks:
        current = current_blocks.get(block["speech_block_id"])
        stale = bool(block.get("audio_stale", False))
        if current is not None:
            spoken = current["content_kind"] != speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
            changed = _synthesis_inputs_changed(block, current, context, configured_only=spoken)
            if changed is not None:
                stale = (stale or changed) if spoken else changed
        reviewed_blocks.append({**block, "audio_stale": stale})
    return reviewed_blocks


def _build_generation_context(
    project_root: Path,
    manifest: dict[str, object],
    runtime_settings: dict[str, object],
    scope: list[dict[str, object]],
    requested: list[dict[str, object]],
    generate_ambience: bool,
) -> dict[str, object]:
    """
    @brief      Resolve mandatory synthesis resources and available comparison inputs.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Current project manifest.
    @param[in]  runtime_settings Runtime connection and model descriptions.
    @param[in]  scope Rows to consider for current input fingerprints.
    @param[in]  requested Rows that require new output.
    @param[in]  generate_ambience Whether this run generates ambience.
    @return     Shared synthesis and comparison context.
    @exception  ValueError Raised when a required resource is unavailable.
    """
    voice_assignment_mode = speech_blocks_service.voice_assignment_mode(manifest)
    needed_voices = {
        _voice_target_id_for_block(block, voice_assignment_mode)
        for block in requested if not _is_metadata_only_speech_block(block)
    }
    needs_sound = any(block["content_kind"] == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE for block in requested)
    base_url = str(runtime_settings.get("base_url", "")).strip()
    timeout_seconds = int(runtime_settings.get("timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
    if (needed_voices or needs_sound) and not base_url:
        raise ValueError("Configure TTS Settings and test the VoiceWeaver connection before generating Audio Blocks.")
    if (needed_voices or needs_sound) and timeout_seconds <= 0:
        raise ValueError("Audio Blocks generation requires a valid runtime timeout configuration.")
    models = list(runtime_settings.get("discovered_models", []))
    capabilities = voiceweaver_runtime_service.build_capability_matrix(models)
    clone_model = _first_model(
        capabilities.get("qwen_clone_models", []), preferred_model_id=_PREFERRED_QWEN_CLONE_MODEL_ID,
    )
    if needed_voices and clone_model is None:
        raise ValueError("Cannot generate Audio Blocks because the required Qwen3 TTS base clone model is missing.")
    sound_model = _first_model(capabilities.get("sound_prompt_models", []))
    if needs_sound and sound_model is None:
        raise ValueError(
            "Scene Ambience Audio was requested, but VoiceWeaver has no healthy sound_prompt model available."
        )

    voice_language = character_voices_service.load_selected_voice_language(
        project_root, narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
    )
    operator_token_maximum = tts_budget_service.resolve_generation_token_limit(runtime_settings)
    model_budget = {}
    if clone_model is not None:
        try:
            model_budget = _resolve_model_budget({}, clone_model, operator_token_maximum)
        except ValueError:
            if needed_voices:
                raise
    voice_targets = (
        _resolve_audio_voice_targets(project_root, scope, voice_assignment_mode, needed_voices)
        if clone_model is not None else []
    )
    clone_model_id = "" if clone_model is None else str(clone_model["model_id"]).strip()
    sound_model_id = "" if sound_model is None else str(sound_model["model_id"]).strip()
    return {
        **model_budget,
        "operator_token_maximum": operator_token_maximum,
        "voice_targets": voice_targets,
        "voice_language": voice_language,
        "clone_model_id": clone_model_id,
        "needs_clone": bool(needed_voices),
        "clone_model_payload": clone_model or {},
        "sound_model_id": sound_model_id,
        "sound_model_payload": sound_model or {},
        "generate_scene_ambience_audio": generate_ambience,
        "scene_ambience_duration_seconds": runtime_settings.get("scene_ambience_duration_seconds"),
        "scene_ambience_guidance_scale": runtime_settings.get("scene_ambience_guidance_scale"),
        "scene_ambience_num_inference_steps": runtime_settings.get("scene_ambience_num_inference_steps"),
        "scene_ambience_seed": runtime_settings.get("scene_ambience_seed"),
        "voice_assignment_mode": voice_assignment_mode,
        "original_language": str(manifest.get("original_language", "")).strip(),
        "clone_model_parameters": _clone_model_parameters(runtime_settings),
        "base_url": base_url,
        "timeout_seconds": timeout_seconds,
    }


def _resolve_audio_voice_targets(
    project_root: Path,
    speech_blocks: list[dict[str, object]],
    voice_assignment_mode: str,
    needed_voices: set[str],
) -> list[dict[str, object]]:
    """
    @brief      Read references for synthesis and available completed-audio provenance.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_blocks Approved Speech Blocks within the operation scope.
    @param[in]  voice_assignment_mode Project voice assignment mode.
    @param[in]  needed_voices Voice targets actually needed to generate missing audio.
    @return     Resolved reference pairs.
    @exception  ValueError Raised when a required reference pair is missing.
    """
    targets = []
    seen = set()
    missing_characters = []
    voice_plan = None
    for block in speech_blocks:
        if _is_metadata_only_speech_block(block):
            continue
        target_id = _voice_target_id_for_block(block, voice_assignment_mode)
        if target_id in seen:
            continue
        seen.add(target_id)
        display_name = str(block.get("speaker_display_name", target_id)).strip() or target_id
        is_narrator = target_id == character_voices_service.TARGET_ID_NARRATOR
        required = target_id in needed_voices
        try:
            if is_narrator:
                path = narrator_definition_service.selected_narrator_sample_path(project_root)
                metadata = narrator_definition_service.load_selected_narrator_sample_metadata(project_root)
            else:
                if voice_plan is None:
                    plan_path = project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME
                    voice_plan = character_voices_service.load_voice_plan(project_root) if plan_path.is_file() else []
                path, _ = character_voices_service.target_sample_paths(project_root, target_id, voice_plan)
                metadata = character_voices_service.load_target_sample_metadata(project_root, target_id, voice_plan)
            sample_relative_path = relative_to_project(project_root, path) if path is not None else None
            sample_fingerprint = _file_sha1(path) if path is not None and path.is_file() else None
        except (OSError, ValueError):
            if required:
                raise
            _AUDIO_BLOCKS_LOGGER.debug("Could not compare reference for %s", target_id, exc_info=True)
            continue
        if sample_fingerprint is None or not isinstance(metadata, dict):
            if required and is_narrator:
                if sample_fingerprint is None:
                    raise ValueError("Generate the selected narrator sample before starting Audio Blocks.")
                raise ValueError("The selected narrator sample metadata is missing or invalid.")
            if required:
                missing_characters.append(display_name)
            continue
        transcript = str(metadata.get("preview_text", "")).strip()
        if not transcript:
            if required:
                raise ValueError(
                    f"Generate a sample with preview text for '{display_name}' before starting Audio Blocks."
                )
            continue
        targets.append({
            "voice_target_id": target_id,
            "display_name": display_name,
            "sample_audio_path": path,
            "sample_relative_path": sample_relative_path,
            "sample_fingerprint": sample_fingerprint,
            "sample_text": transcript,
            "sample_metadata": dict(metadata),
        })
    if missing_characters:
        names = ", ".join(sorted(set(missing_characters)))
        raise ValueError(
            f"Generate samples for every referenced character voice before starting Audio Blocks. Missing: {names}"
        )
    return targets


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
    @details    `/status` reports the most recent operation and latches its terminal status until the
                next one starts, so every terminal status, cancelled included, means the runtime is
                free rather than busy.
    @param[in]  status_payload Current normalized VoiceWeaver status payload.
    @return     True when the runtime reports a non-terminal operation.
    @exception  None
    """
    operation_payload = status_payload.get("operation", {}) if isinstance(status_payload, dict) else {}
    if not isinstance(operation_payload, dict):
        return False
    operation_status = str(operation_payload.get("status", operation_payload.get("kind", "idle"))).strip().lower()
    return operation_status not in {"", "idle", "completed", "cancelled", "failed"}


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
    *,
    output_path: Path,
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
    @param[in]  force_restart True to render isolated parts for selected regeneration.
    @param[in]  output_path Staged candidate WAV path.
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
    block_id = str(audio_block["speech_block_id"])
    parts_root = output_path.parent if force_restart else project_root
    part_paths = _existing_part_paths(
        project_root, audio_block, split_plan, force_restart, next_split_part_index=next_split_part_index,
    )
    fingerprint = _build_audio_block_fingerprint(audio_block, generation_context)

    def submit_part(part_text: str) -> object:
        """
        @brief      Submit one spoken part using the selected clone prompt and budget.
        @param[in]  part_text Planned spoken text.
        @return     VoiceWeaver request result.
        """
        return voiceweaver_runtime_service.generate_voice_clone_from_prompt(
            base_url,
            voice_clone_prompt,
            str(generation_context.get("voice_language", "")),
            part_text,
            model_parameters={
                **_clone_model_parameters(generation_context),
                "max_new_tokens": _part_generation_token_budget(part_text, generation_context),
            },
            timeout_seconds=timeout_seconds,
        )

    def persist_part(next_part: int, summary: str) -> None:
        """
        @brief      Record a completed prefix with its actual generation inputs.
        @param[in]  next_part Index of the next part.
        @param[in]  summary Provider result summary.
        """
        checkpoint_callback(
            {
                **audio_block,
                "split_part_count": len(split_plan["parts"]),
                "generation_fingerprint": fingerprint,
                "split_plan_fingerprint": _split_plan_fingerprint(split_plan),
                "runtime_result_summary": summary,
            },
            next_part,
        )

    runtime_result_summary = audio_blocks_generation_service.render_spoken_wav(
        output_path,
        split_plan["parts"],
        part_paths,
        lambda index: _audio_part_artifact_path(parts_root, block_id, index),
        submit_part,
        base_url,
        timeout_seconds,
        cancel_requested,
        persist_part if checkpoint_callback is not None else None,
    )
    generated_at = _utc_now_iso()
    audio_duration_seconds = _wav_duration_seconds(output_path)
    _AUDIO_BLOCKS_LOGGER.info(
        "Generated audio block chunk_id=%s sequence_index=%s audio_path=%s",
        str(audio_block.get("chunk_id", "")).strip(),
        int(audio_block.get("sequence_index", 0)),
        relative_to_project(project_root, output_path),
    )
    return {
        **dict(audio_block),
        "audio_can_play": True,
        "audio_stale": False,
        "audio_duration_seconds": audio_duration_seconds,
        "voice_language": str(generation_context.get("voice_language", "")).strip(),
        "prompt_format": _optional_string(clone_profile.get("prompt_format")),
        "split_part_count": len(split_plan["parts"]),
        "model_token_budget": int(generation_context.get("model_token_budget", 0)),
        "model_audio_seconds_budget": float(generation_context.get("model_audio_seconds_budget", 0.0)),
        "generation_fingerprint": fingerprint,
        "configured_fingerprint": _build_audio_block_fingerprint(audio_block, generation_context, configured_only=True),
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
    *,
    output_path: Path,
) -> AudioBlockPayload:
    """
    @brief      Generate one Scene Ambience WAV and canonical Audio Blocks metadata.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_block Persisted Scene Ambience Audio Blocks entry.
    @param[in]  generation_context Validated generation-context payload.
    @param[in]  runtime_settings Runtime connection plus discovered-model settings.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  output_path Staged candidate WAV path.
    @return     Updated Audio Blocks payload.
    @exception  RuntimeError Raised when VoiceWeaver does not expose downloadable audio.
    @exception  OperationCancelledError Raised when cancellation is requested.
    """
    base_url = str(runtime_settings.get("base_url", "")).strip()
    timeout_seconds = int(runtime_settings.get("timeout_seconds", config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS))
    sound_prompt, parameters = _sound_request_inputs(audio_block, generation_context)
    if not sound_prompt:
        raise RuntimeError("Scene Ambience Audio generation requires a non-empty sound prompt.")
    raise_if_cancelled(cancel_requested)
    _AUDIO_BLOCKS_LOGGER.info(
        "Generating Scene Ambience audio block chunk_id=%s sequence_index=%s duration_seconds=%.2f",
        str(audio_block.get("chunk_id", "")).strip(),
        int(audio_block.get("sequence_index", 0)),
        parameters["duration_seconds"],
    )
    voiceweaver_runtime_service.generate_sound_prompt(
        base_url, sound_prompt, **parameters, timeout_seconds=timeout_seconds,
    )
    runtime_result_summary = audio_blocks_generation_service.download_wav(
        output_path, base_url, timeout_seconds, cancel_requested,
    )
    generated_at = _utc_now_iso()
    _AUDIO_BLOCKS_LOGGER.info(
        "Generated Scene Ambience audio block chunk_id=%s sequence_index=%s audio_path=%s",
        str(audio_block.get("chunk_id", "")).strip(),
        int(audio_block.get("sequence_index", 0)),
        relative_to_project(project_root, output_path),
    )
    return {
        **dict(audio_block),
        "duration_seconds": parameters["duration_seconds"],
        "metadata_only": False,
        "special_block_status": None,
        "audio_can_play": True,
        "audio_stale": False,
        "audio_duration_seconds": _wav_duration_seconds(output_path),
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
        "runtime_result_summary": runtime_result_summary,
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


def _clone_model_parameters(payload: dict[str, object]) -> dict[str, object]:
    """
    @brief      Read the operator clone sampling parameters carried by runtime settings or a generation context.
    @param[in]  payload Runtime-settings or generation-context payload.
    @return     Sampling parameter mapping, empty when the payload carries none.
    @exception  None
    """
    parameters = payload.get("clone_model_parameters")
    return dict(parameters) if isinstance(parameters, dict) else {}


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
    @brief      Delete the WAV and split parts for an invalidated block.
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


def _sound_request_inputs(
    audio_block: AudioBlockPayload,
    context: dict[str, object],
) -> tuple[str, dict[str, object]]:
    """
    @brief      Resolve the effective prompt and parameters shared by sound synthesis and provenance.
    @param[in]  audio_block Current Scene Ambience cue.
    @param[in]  context Current synthesis settings.
    @return     Sound prompt and normalized provider parameters.
    @exception  None
    """
    duration = (
        _optional_float(context.get("scene_ambience_duration_seconds"))
        or _optional_float(audio_block.get("duration_seconds"))
        or float(config.DEFAULT_SCENE_AMBIENCE_DURATION_SECONDS)
    )
    guidance = _optional_float(context.get("scene_ambience_guidance_scale"))
    seed = context.get("scene_ambience_seed")
    return str(audio_block.get("sound_prompt") or audio_block.get("text", "")).strip(), {
        "negative_prompt": str(audio_block.get("negative_prompt", "")).strip(),
        "duration_seconds": min(duration, config.MAX_SOUND_PROMPT_DURATION_SECONDS),
        "guidance_scale": config.DEFAULT_SCENE_AMBIENCE_GUIDANCE_SCALE if guidance is None else guidance,
        "num_inference_steps": _optional_int(
            context.get("scene_ambience_num_inference_steps"), config.DEFAULT_SCENE_AMBIENCE_NUM_INFERENCE_STEPS,
        ),
        "seed": None if seed is None else _optional_int(seed, config.DEFAULT_SCENE_AMBIENCE_SEED),
    }


def _build_audio_block_fingerprint(
    audio_block: AudioBlockPayload,
    generation_context: dict[str, object] | None,
    *,
    configured_only: bool = False,
) -> str | None:
    """
    @brief      Build one stable generation fingerprint for a single Audio Block.
    @param[in]  audio_block Current Speech Block-aligned Audio Block payload.
    @param[in]  generation_context Validated Audio Blocks generation context.
    @param[in]  configured_only Compare configured inputs without a live model budget.
    @return     Hex-encoded fingerprint, or `None` when context is unavailable.
    @exception  None
    """
    if not isinstance(generation_context, dict):
        return None
    content_kind = str(audio_block.get("content_kind", "")).strip()
    fingerprint_payload = {
        "fingerprint_version": _AUDIO_BLOCK_FINGERPRINT_VERSION,
        "content_kind": content_kind,
    }
    if content_kind == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE:
        if not generation_context.get("sound_model_id"):
            return None
        sound_prompt, parameters = _sound_request_inputs(audio_block, generation_context)
        fingerprint_payload.update({
            "sound_model_id": generation_context["sound_model_id"], "sound_prompt": sound_prompt, **parameters,
        })
    else:
        target_id = str(audio_block.get("voice_target_id", "")).strip()
        targets = generation_context.get("voice_targets", [])
        target = next((target for target in targets if target["voice_target_id"] == target_id), None)
        if target is None or not generation_context.get("clone_model_id"):
            return None
        fingerprint_payload.update({
            "text": _normalize_split_text(str(audio_block.get("text", ""))),
            "voice_target_id": target_id,
            "voice_language": generation_context.get("voice_language"),
            "clone_model_id": generation_context["clone_model_id"],
            "sample_fingerprint": target["sample_fingerprint"],
            "sample_text": target["sample_text"],
            "sample_language": _voice_target_sample_language(target),
            "clone_model_parameters": _clone_model_parameters(generation_context),
        })
        if configured_only:
            fingerprint_payload["operator_token_maximum"] = generation_context.get("operator_token_maximum")
        else:
            fingerprint_payload.update({
                "model_token_budget": generation_context.get("model_token_budget"),
                "hard_token_maximum": generation_context.get("hard_token_maximum"),
                "split_audio_seconds_budget": generation_context.get("split_audio_seconds_budget"),
                "hard_word_count": generation_context.get("hard_word_count"),
            })
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


def _synthesis_inputs_changed(
    block: AudioBlockPayload,
    current_block: AudioBlockPayload,
    context: dict[str, object],
    *,
    configured_only: bool = False,
) -> bool | None:
    """
    @brief      Compare the WAV's synthesis inputs when both fingerprints are available.
    @param[in]  block Persisted Audio Block.
    @param[in]  current_block Current Speech Blocks-derived inputs.
    @param[in]  context Current synthesis settings and reference identity.
    @param[in]  configured_only True to compare speech without the effective runtime budget.
    @return     Whether inputs differ, or None when there is no comparable fingerprint.
    @exception  None
    """
    previous = block.get("configured_fingerprint" if configured_only else "generation_fingerprint")
    if not previous:
        return None
    current = _build_audio_block_fingerprint(current_block, context, configured_only=configured_only)
    return None if current is None else previous != current


def _merge_existing_audio_blocks(
    speech_blocks: list[dict[str, object]],
    existing_audio_blocks: list[AudioBlockPayload],
    voice_assignment_mode: str = config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
    generation_context: dict[str, object] | None = None,
    project_root: Path | None = None,
    *,
    cached_clone_inputs: bool = False,
) -> list[AudioBlockPayload]:
    """
    @brief      Merge persisted Audio Blocks state onto the current Speech Blocks snapshot.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  existing_audio_blocks Persisted Audio Blocks payload list.
    @param[in]  voice_assignment_mode Project-local voice assignment mode.
    @param[in]  generation_context Optional synthesis or comparison inputs.
    @param[in]  project_root Active project root for checking reusable WAVs.
    @param[in]  cached_clone_inputs Whether only configured clone inputs are available.
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
        if existing_block is None:
            continue
        previous_fingerprint = existing_block.get("generation_fingerprint")
        reusable = _audio_block_has_reusable_audio(existing_block, project_root)
        if generation_context and not reusable:
            current_fingerprint = _build_audio_block_fingerprint(block, generation_context)
            if is_generated(existing_block) or (current_fingerprint and previous_fingerprint != current_fingerprint):
                continue
        stale = bool(existing_block.get("audio_stale", False))
        spoken = not _is_metadata_only_speech_block(block)
        if reusable and generation_context and spoken and not cached_clone_inputs:
            configured_changed = _synthesis_inputs_changed(
                existing_block, block, generation_context, configured_only=True,
            )
            # The review page compares configured inputs afresh. Persist only mismatches
            # that need a live comparison, including older rows without a configured fingerprint.
            if configured_changed is not True:
                exact_changed = _synthesis_inputs_changed(existing_block, block, generation_context)
                if exact_changed is not None:
                    stale = exact_changed
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
                "generation_fingerprint": previous_fingerprint,
                "configured_fingerprint": existing_block.get("configured_fingerprint"),
                "audio_stale": stale,
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


def _persist_report_update(
    project_root: Path,
    audio_blocks: list[AudioBlockPayload],
    clone_profiles: list[VoiceCloneProfilePayload] | None = None,
    wav_replacement: tuple[Path, Path] | None = None,
) -> AudioBlocksReportPayload:
    """
    @brief      Persist one document update after approvals or single-block regeneration.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_blocks Updated Audio Blocks payload list.
    @param[in]  clone_profiles Optional updated direct-clone source profile list.
    @param[in]  wav_replacement Optional staged and canonical WAV paths.
    @return     Updated projected report payload.
    @exception  None
    """
    document = load_audio_blocks_document(project_root) or _empty_audio_blocks_document()
    checkpoint = document.get("checkpoint") if isinstance(document.get("checkpoint"), dict) else {}
    active_id = _operation_optional_string(checkpoint.get("current_block_id"))
    next_part = _checkpoint_int(checkpoint, "next_split_part_index", 0)
    if next_part and not any(
        block["speech_block_id"] == active_id
        and not is_generated(block)
        and block.get("split_plan_fingerprint")
        for block in audio_blocks
    ):
        active_id, next_part = None, 0
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
        current_block_id=active_id,
        next_split_part_index=next_part,
        next_speech_block_index=_checkpoint_int(checkpoint, "next_speech_block_index", len(audio_blocks)),
        total_block_count=total_block_count,
        wav_replacement=wav_replacement,
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


def _mark_audio_blocks_cancelled(project_root: Path) -> None:
    """
    @brief      Mark cancellation without replacing the last durable generation checkpoint.
    @param[in]  project_root Active project root folder.
    """
    document = load_audio_blocks_document(project_root)
    if document is None:
        return
    document["status"] = "cancelled"
    write_audio_blocks_document(project_root, document)
    project_workspace_service.sync_manifest_operation_summary(
        project_root, "audio_blocks", _project_operation_state(project_root, document),
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
    wav_replacement: tuple[Path, Path] | None = None,
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
    @param[in]  wav_replacement Optional candidate and canonical WAV paths.
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
    operation_state = _project_operation_state(project_root, document, total_block_count, len(clone_profiles))
    stage = "audio_blocks_ready" if status == AUDIO_BLOCKS_STAGE_COMPLETED else "speech_blocks_ready"
    if wav_replacement is None:
        write_audio_blocks_document(project_root, document)
        write_operation_json_artifact(
            project_root, "audio_blocks", config.AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME, clone_profiles,
        )
        project_workspace_service.sync_manifest_operation_summary(project_root, "audio_blocks", operation_state, stage)
    else:
        _publish_audio_block(project_root, document, clone_profiles, operation_state, stage, *wav_replacement)
    return _project_audio_blocks_report(
        project_root,
        document,
        total_block_count=total_block_count,
        prompt_count=len(clone_profiles),
    )


def _publish_audio_block(
    project_root: Path,
    document: AudioBlocksDocumentPayload,
    clone_profiles: list[VoiceCloneProfilePayload],
    operation_state: OperationStatePayload,
    stage: str,
    candidate_wav: Path,
    audio_path: Path,
) -> None:
    """
    @brief      Publish the staged WAV, review document, clone cache and project summary.
    @param[in]  project_root Active project root folder.
    @param[in]  document Replacement Audio Blocks document.
    @param[in]  clone_profiles Replacement clone-profile cache.
    @param[in]  operation_state Summary for the project manifest.
    @param[in]  stage Reached milestone for the project manifest.
    @param[in]  candidate_wav Complete staged WAV.
    @param[in]  audio_path Canonical WAV destination.
    """
    _validate_audio_blocks_document(document)
    root = project_root.resolve()
    document_path = resolve_operation_path(root, "audio_blocks", config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME)
    clone_path = resolve_operation_path(root, "audio_blocks", config.AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME)
    staged_document = candidate_wav.with_name(document_path.name)
    staged_clones = candidate_wav.with_name(clone_path.name)
    write_json_atomic(staged_document, document)
    write_json_atomic(staged_clones, clone_profiles)
    manifest_path = root / config.PROJECT_MANIFEST_FILE_NAME
    original_manifest = manifest_path.read_bytes()
    manifest = project_workspace_service.manifest_with_operation_summary(
        project_workspace_service.load_manifest(root), "audio_blocks", operation_state, stage,
    )
    project_workspace_service.save_manifest(manifest, candidate_wav.parent)
    replace_project_files(
        root,
        {
            audio_path.relative_to(root): candidate_wav,
            document_path.relative_to(root): staged_document,
            clone_path.relative_to(root): staged_clones,
            Path(manifest_path.name): candidate_wav.with_name(manifest_path.name),
        },
        manifest_path,
        original_manifest,
        "audio-block",
    )


def _remove_published_parts(project_root: Path, block: AudioBlockPayload) -> None:
    """
    @brief      Clean up local split parts after their final WAV and review metadata are durable.
    @param[in]  project_root Active project root folder.
    @param[in]  block Published Audio Block.
    """
    block_id = str(block["speech_block_id"])
    root = project_root.resolve()
    parts_folder = _audio_part_artifact_path(root, block_id, 0).parent
    try:
        validate_publication_path(root, parts_folder, "audio-block split cleanup")
    except (OSError, RuntimeError, ValueError):
        _AUDIO_BLOCKS_LOGGER.warning("Could not validate split directory %s for cleanup", parts_folder, exc_info=True)
        return
    for path in parts_folder.glob(f"{_audio_artifact_file_stem(block_id)}_part*.wav"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            _AUDIO_BLOCKS_LOGGER.warning("Could not remove published Audio Block part %s", path, exc_info=True)


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
    if audio_block.get("audio_stale"):
        payload["audio_stale"] = True
    configured_fingerprint = _optional_string(audio_block.get("configured_fingerprint"))
    if configured_fingerprint:
        payload["configured_fingerprint"] = configured_fingerprint
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
        "audio_stale": bool(payload.get("audio_stale", False)),
        "configured_fingerprint": _optional_string(payload.get("configured_fingerprint")),
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
        and str(clone_profile.get("sample_text", "")).strip() == str(voice_target.get("sample_text", "")).strip()
        and bool(str(voice_target.get("sample_text", "")).strip())
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
