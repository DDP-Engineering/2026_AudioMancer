#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audio_assembly_service.py
@brief WAV audiobook composition helpers for AudioMancer.
@details Builds final audiobook WAV deliverables from approved Audio Blocks,
         persists per-project assembly settings, and supports resumable output
         generation through root-level state and report artifacts. Scene
         Ambience prompt WAVs can be mixed into grouped ambience beds for
         preview and final assembly.
"""

# IMPORTS

from contextlib import ExitStack, suppress
from functools import partial
import hashlib
import json
from pathlib import Path
import wave

from audiomancer import config
from audiomancer.services import (
    audio_blocks_service,
    operation_runtime_service,
    pcm_codec,
    project_workspace_service,
    speech_blocks_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    build_operation_output_path,
    build_operation_state_payload,
    emit_progress_update,
    load_operation_state_payload,
    raise_if_cancelled,
    relative_to_project,
    resolve_operation_path,
)
from audiomancer.services.operation_runtime_service import (
    try_resolve_project_relative_path as _safe_project_artifact_path,
)
from audiomancer.services.persistence_service import write_json_atomic
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

_AUDIO_ASSEMBLY_LOGGER = get_component_logger("audio_assembly")
_emit_progress = partial(emit_progress_update, include_token_usage=False)

AUDIO_ASSEMBLY_STAGE_NOT_STARTED = "not_started"
AUDIO_ASSEMBLY_STAGE_IN_PROGRESS = "in_progress"
AUDIO_ASSEMBLY_STAGE_COMPLETED = "completed"

OUTPUT_MODE_PER_CHUNK = "per_chunk"
OUTPUT_MODE_TIME_LIMIT = "time_limit"
OUTPUT_MODE_WHOLE_BOOK = "whole_book"
OUTPUT_FORMAT_WAV = "wav"

_MODE = "audio_composition"
_TEMP_SUFFIX = ".tmp"
_SCENE_MIX_PREVIEW_FOLDER_NAME = "scene_mix_previews"
_SCENE_MIX_KEY_PREFIX = "scene_mix"
_WAV_COPY_FRAME_CHUNK_SIZE = 65_536
_RIFF_UINT32_MAX = (1 << 32) - 1
_WAV_RIFF_DATA_OVERHEAD_BYTES = 36
_WAV_MAX_DATA_BYTES = _RIFF_UINT32_MAX - _WAV_RIFF_DATA_OVERHEAD_BYTES
# Signed-PCM sample widths Audio Assembly can stitch. One-byte PCM is excluded on
# purpose: WAV stores 8-bit samples unsigned, while this module and `pcm_codec` read
# every width as signed, so an 8-bit render would write silence as a full negative-rail
# DC offset instead of quiet. Rejecting the width is honest; rendering it is not.
_WAV_SAMPLE_WIDTH_BY_FORMAT = {
    2: 2,
    3: 3,
    4: 4,
}

AudioAssemblySettings = dict[str, object]
AudioAssemblyReport = dict[str, object]
AudioAssemblyState = dict[str, object]
SceneMixGroup = dict[str, object]


# PUBLIC API


@trace_function(_AUDIO_ASSEMBLY_LOGGER)
def default_audio_assembly_settings() -> AudioAssemblySettings:
    """
    @brief      Build the default per-project Audio Assembly settings payload.
    @return     Default Audio Assembly settings.
    @exception  None
    """
    return {
        "output_mode": config.DEFAULT_AUDIO_ASSEMBLY_OUTPUT_MODE,
        "max_duration_minutes": config.DEFAULT_AUDIO_ASSEMBLY_MAX_DURATION_MINUTES,
        "output_format": config.DEFAULT_AUDIO_ASSEMBLY_OUTPUT_FORMAT,
        "inter_block_silence_ms": config.DEFAULT_AUDIO_ASSEMBLY_INTER_BLOCK_SILENCE_MS,
        "inter_chunk_silence_ms": config.DEFAULT_AUDIO_ASSEMBLY_INTER_CHUNK_SILENCE_MS,
        "include_scene_ambience": config.DEFAULT_AUDIO_ASSEMBLY_INCLUDE_SCENE_AMBIENCE,
    }


@trace_function(_AUDIO_ASSEMBLY_LOGGER)
def normalize_audio_assembly_settings(value: object) -> AudioAssemblySettings:
    """
    @brief      Normalize one user or manifest Audio Assembly settings payload.
    @param[in]  value Candidate settings mapping.
    @return     Normalized Audio Assembly settings.
    @exception  None
    """
    defaults = default_audio_assembly_settings()
    payload = value if isinstance(value, dict) else {}
    output_mode = str(payload.get("output_mode", defaults["output_mode"])).strip()
    if output_mode not in config.AUDIO_ASSEMBLY_OUTPUT_MODE_OPTIONS:
        output_mode = str(defaults["output_mode"])
    output_format = str(payload.get("output_format", defaults["output_format"])).strip().lower()
    if output_format not in config.AUDIO_ASSEMBLY_OUTPUT_FORMAT_OPTIONS:
        output_format = str(defaults["output_format"])
    return {
        "output_mode": output_mode,
        "max_duration_minutes": _bounded_int(
            payload.get("max_duration_minutes", defaults["max_duration_minutes"]),
            1,
            24 * 60,
            int(defaults["max_duration_minutes"]),
        ),
        "output_format": output_format,
        "inter_block_silence_ms": _bounded_int(
            payload.get("inter_block_silence_ms", defaults["inter_block_silence_ms"]),
            0,
            60_000,
            int(defaults["inter_block_silence_ms"]),
        ),
        "inter_chunk_silence_ms": _bounded_int(
            payload.get("inter_chunk_silence_ms", defaults["inter_chunk_silence_ms"]),
            0,
            60_000,
            int(defaults["inter_chunk_silence_ms"]),
        ),
        "include_scene_ambience": bool(payload.get("include_scene_ambience", defaults["include_scene_ambience"])),
    }


@trace_function(_AUDIO_ASSEMBLY_LOGGER)
def save_audio_assembly_settings(
    project_root: str | Path,
    manifest: dict[str, object],
    settings: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Persist normalized Audio Assembly settings in `project.json`.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Current manifest payload.
    @param[in]  settings Candidate Audio Assembly settings.
    @return     Reloaded normalized manifest.
    @exception  None
    """
    updated_manifest = dict(manifest)
    updated_manifest["audio_assembly_settings"] = normalize_audio_assembly_settings(settings)
    project_workspace_service.save_manifest(updated_manifest, project_root)
    return project_workspace_service.load_manifest(project_root)


@trace_function(_AUDIO_ASSEMBLY_LOGGER)
def load_operation_state(project_root: str | Path) -> AudioAssemblyState | None:
    """
    @brief      Load one optional Audio Assembly operation-state payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted state payload or `None`.
    @exception  None
    """
    return load_operation_state_payload(project_root, "audio_assembly", config.AUDIO_ASSEMBLY_STATE_FILE_NAME)


@trace_function(_AUDIO_ASSEMBLY_LOGGER)
def load_audio_assembly_report(project_root: str | Path) -> AudioAssemblyReport | None:
    """
    @brief      Load one optional Audio Assembly report payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted report payload or `None`.
    @exception  None
    """
    report_path = resolve_operation_path(project_root, "audio_assembly", config.AUDIO_ASSEMBLY_REPORT_FILE_NAME)
    if not report_path.is_file():
        return None
    return dict(json.loads(report_path.read_text(encoding="utf-8")))


@trace_function(_AUDIO_ASSEMBLY_LOGGER)
def load_generated_outputs(project_root: str | Path) -> list[dict[str, object]]:
    """
    @brief      Load generated Audio Assembly output records from the report.
    @param[in]  project_root Active project root folder.
    @return     Ordered output record list.
    @exception  None
    """
    report = load_audio_assembly_report(project_root)
    if not isinstance(report, dict):
        return []
    outputs = report.get("outputs", [])
    if not isinstance(outputs, list):
        return []
    return [_normalize_output_record(output) for output in outputs if isinstance(output, dict)]


@trace_function(_AUDIO_ASSEMBLY_LOGGER)
def list_scene_mix_groups(project_root: str | Path) -> list[SceneMixGroup]:
    """
    @brief      Build current Scene Ambience mix-preview groups.
    @param[in]  project_root Active project root folder.
    @return     Ordered Scene Ambience group records.
    @exception  None
    """
    resolved_project_root = Path(project_root)
    audio_blocks = speech_blocks_service.sort_speech_blocks(
        audio_blocks_service.load_audio_blocks(resolved_project_root)
    )
    return _scene_mix_groups_from_blocks(resolved_project_root, audio_blocks, include_blocks=False)


@trace_function(_AUDIO_ASSEMBLY_LOGGER)
def generate_scene_mix_preview(
    project_root: str | Path,
    group_key: str,
    progress_callback=None,
    cancel_requested=None,
) -> SceneMixGroup:
    """
    @brief      Generate or refresh one selected Scene Ambience mix-preview WAV.
    @param[in]  project_root Active project root folder.
    @param[in]  group_key Stable Scene Ambience group key.
    @param[in]  progress_callback Optional progress callback for modal UI updates.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Refreshed Scene Ambience group record.
    @exception  ValueError Raised when the group is unavailable or incomplete.
    """
    resolved_project_root = Path(project_root)
    _emit_progress(progress_callback, 0, 3, "Preparing Scene Mix preview.")
    groups = _scene_mix_groups_from_blocks(
        resolved_project_root,
        speech_blocks_service.sort_speech_blocks(audio_blocks_service.load_audio_blocks(resolved_project_root)),
        include_blocks=True,
    )
    target_group = next((group for group in groups if str(group.get("group_key", "")) == str(group_key).strip()), None)
    if target_group is None:
        raise ValueError("The selected Scene Ambience mix is no longer available.")
    if not bool(target_group.get("can_generate_preview", False)):
        raise ValueError("Generate and approve every source Scene Ambience Audio Block before previewing the mix.")
    _emit_progress(progress_callback, 1, 3, f"Mixing {target_group.get('label', 'Scene Mix preview')}.")
    _write_scene_mix_group(
        resolved_project_root,
        target_group,
        progress_callback=progress_callback,
        progress_start=1,
        progress_end=2,
        progress_total=3,
        cancel_requested=cancel_requested,
    )
    _emit_progress(progress_callback, 2, 3, "Refreshing Scene Mix preview.")
    refreshed_groups = _scene_mix_groups_from_blocks(
        resolved_project_root,
        speech_blocks_service.sort_speech_blocks(audio_blocks_service.load_audio_blocks(resolved_project_root)),
        include_blocks=False,
    )
    refreshed_group = next(
        (group for group in refreshed_groups if str(group.get("group_key", "")) == str(group_key).strip()),
        _strip_scene_mix_blocks(target_group),
    )
    _emit_progress(progress_callback, 3, 3, "Scene Mix preview completed.")
    return refreshed_group


@trace_function(_AUDIO_ASSEMBLY_LOGGER)
def has_persisted_audio_assembly(project_root: str | Path) -> bool:
    """
    @brief      Return whether Audio Assembly state or output artifacts exist.
    @param[in]  project_root Active project root folder.
    @return     True when persisted assembly data exists.
    @exception  None
    """
    output_root = Path(project_root) / config.AUDIOBOOK_OUTPUT_FOLDER_NAME
    operation_state = load_operation_state(project_root)
    has_runtime_state = False
    if isinstance(operation_state, dict):
        has_runtime_state = str(operation_state.get("status", "")).strip() != AUDIO_ASSEMBLY_STAGE_NOT_STARTED or any(
            (
                int(operation_state.get("progress_current", 0) or 0) > 0,
                int(operation_state.get("progress_total", 0) or 0) > 0,
            )
        )
    return any(
        (
            load_audio_assembly_report(project_root) is not None,
            has_runtime_state,
            output_root.is_dir() and any(path.is_file() for path in output_root.rglob("*")),
        )
    )


@trace_function(_AUDIO_ASSEMBLY_LOGGER)
def reset_audio_assembly(project_root: str | Path) -> None:
    """
    @brief      Delete persisted Audio Assembly state and generated audiobook files.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    """
    operation_runtime_service.reset_operation_data(project_root, "audio_assembly", include_current=True)


@trace_function(_AUDIO_ASSEMBLY_LOGGER)
def start_or_continue_composition(
    project_root: str | Path,
    manifest: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
) -> AudioAssemblyReport:
    """
    @brief      Compose approved Audio Blocks into final audiobook WAV output files.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Current project manifest payload.
    @param[in]  progress_callback Optional progress callback for modal UI updates.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Final or current Audio Assembly report payload.
    @exception  ValueError Raised when prerequisites are missing or stale data requires reset.
    @exception  RuntimeError Raised when source WAV files cannot be composed.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    """
    resolved_project_root = Path(project_root)
    settings = normalize_audio_assembly_settings(manifest.get("audio_assembly_settings"))
    approved_blocks = _load_approved_audio_blocks(
        resolved_project_root,
        include_scene_ambience=bool(settings["include_scene_ambience"]),
    )
    input_fingerprint = _build_input_fingerprint(resolved_project_root, approved_blocks, settings)
    existing_state = load_operation_state(resolved_project_root) or {}
    if _requires_manual_reset(existing_state, input_fingerprint):
        raise ValueError("Audio Assembly inputs or settings changed. Reset Audio Assembly before continuing.")

    output_plan = _build_output_plan(resolved_project_root, approved_blocks, settings)
    completed_records = _completed_records_for_resume(resolved_project_root, existing_state, input_fingerprint)
    _validate_pending_output_wav_sizes(
        resolved_project_root,
        output_plan,
        settings,
        completed_records,
    )
    started_at = _resolve_started_at(existing_state)
    warnings = _warnings_for_output_plan(output_plan)
    report = _build_report(
        settings,
        approved_blocks,
        output_plan,
        completed_records,
        warnings,
        input_fingerprint,
        status="running",
        started_at=started_at,
        completed_at=None,
    )
    _persist_state(resolved_project_root, report, _build_operation_state(resolved_project_root, report, output_plan))
    _emit_progress(progress_callback, len(completed_records), len(output_plan), "Audio Assembly started.")

    try:
        for output_item in output_plan:
            if output_item["output_key"] in {str(record.get("output_key", "")) for record in completed_records}:
                continue
            raise_if_cancelled(cancel_requested)
            output_record = _compose_output_file(resolved_project_root, output_item, settings, cancel_requested)
            completed_records.append(output_record)
            report = _build_report(
                settings,
                approved_blocks,
                output_plan,
                completed_records,
                warnings,
                input_fingerprint,
                status="running",
                started_at=started_at,
                completed_at=None,
            )
            _persist_state(
                resolved_project_root,
                report,
                _build_operation_state(resolved_project_root, report, output_plan),
            )
            _emit_progress(
                progress_callback,
                len(completed_records),
                len(output_plan),
                f"Composed {output_record['file_name']}.",
            )
    except operation_runtime_service.OperationCancelledError:
        cancelled_report = _build_report(
            settings,
            approved_blocks,
            output_plan,
            completed_records,
            warnings,
            input_fingerprint,
            status="cancelled",
            started_at=started_at,
            completed_at=None,
        )
        _persist_state(
            resolved_project_root,
            cancelled_report,
            _build_operation_state(resolved_project_root, cancelled_report, output_plan),
        )
        raise

    completed_at = _utc_now_iso()
    final_report = _build_report(
        settings,
        approved_blocks,
        output_plan,
        completed_records,
        warnings,
        input_fingerprint,
        status="completed",
        started_at=started_at,
        completed_at=completed_at,
    )
    completed_state = _build_operation_state(resolved_project_root, final_report, output_plan)
    _persist_state(
        resolved_project_root,
        final_report,
        completed_state,
    )
    project_workspace_service.sync_manifest_operation_summary(
        resolved_project_root,
        "audio_assembly",
        completed_state,
        current_stage="audio_assembly_ready",
    )
    _emit_progress(progress_callback, len(output_plan), len(output_plan), "Audio Assembly completed.")
    return final_report


# LOCAL HELPERS


def _load_approved_audio_blocks(project_root: Path, include_scene_ambience: bool) -> list[dict[str, object]]:
    """
    @brief      Load and validate approved Audio Blocks for composition.
    @param[in]  project_root Active project root folder.
    @param[in]  include_scene_ambience True when Scene Ambience contributes.
    @return     Approved generated Audio Blocks.
    @exception  ValueError Raised when prerequisites are not satisfied.
    @exception  RuntimeError Raised when a source WAV format is unsupported.
    """
    audio_blocks = speech_blocks_service.sort_speech_blocks(audio_blocks_service.load_audio_blocks(project_root))
    if not audio_blocks:
        raise ValueError("Generate and approve Audio Blocks before running Audio Assembly.")
    candidate_blocks = [
        block for block in audio_blocks if _is_included_scene_ambience_block(block, include_scene_ambience)
    ]
    unapproved = [block for block in candidate_blocks if not audio_blocks_service.is_approved(block)]
    if unapproved:
        raise ValueError("Approve every generated Audio Block before running Audio Assembly.")
    composition_sources = [
        block
        for block in candidate_blocks
        if _is_assembly_block(block, include_scene_ambience) and not _is_pause_block(block)
    ]
    if not composition_sources:
        raise ValueError("Audio Assembly requires at least one generated speech audio block.")
    for block in composition_sources:
        audio_path = _audio_path(project_root, block)
        if audio_path is None or not audio_path.is_file():
            raise ValueError("Every approved Audio Block must reference an existing WAV file.")
    _validate_compatible_wav_inputs(project_root, composition_sources)
    return audio_blocks


def _build_composition_blocks(
    project_root: Path,
    audio_blocks: list[dict[str, object]],
    include_scene_ambience: bool,
) -> list[dict[str, object]]:
    """
    @brief      Build ordered final-composition blocks with mixed Scene Ambience groups.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_blocks Approved Audio Blocks.
    @param[in]  include_scene_ambience True when Scene Ambience contributes to output.
    @return     Ordered blocks for output planning and WAV composition.
    @exception  None
    """
    blocks = [
        _enrich_block_duration(project_root, block)
        for block in audio_blocks
        if _is_assembly_block(block, include_scene_ambience)
    ]
    if not include_scene_ambience:
        return blocks
    scene_blocks_by_key: dict[str, list[dict[str, object]]] = {}
    for block in blocks:
        if _is_scene_ambience_block(block):
            scene_blocks_by_key.setdefault(_scene_mix_group_key(block), []).append(block)
    grouped_blocks: list[dict[str, object]] = []
    emitted_scene_keys: set[str] = set()
    for block in blocks:
        if not _is_scene_ambience_block(block):
            grouped_blocks.append(block)
            continue
        group_key = _scene_mix_group_key(block)
        if group_key in emitted_scene_keys:
            continue
        grouped_blocks.append(_scene_mix_virtual_block(project_root, scene_blocks_by_key[group_key]))
        emitted_scene_keys.add(group_key)
    return grouped_blocks


def _scene_mix_groups_from_blocks(
    project_root: Path,
    audio_blocks: list[dict[str, object]],
    *,
    include_blocks: bool,
) -> list[SceneMixGroup]:
    """
    @brief      Convert Scene Ambience Audio Blocks into preview group records.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_blocks Current Audio Blocks payloads.
    @param[in]  include_blocks True to include source block payloads.
    @return     Ordered Scene Ambience mix group records.
    @exception  None
    """
    groups_by_key: dict[str, list[dict[str, object]]] = {}
    for block in audio_blocks:
        if not _is_scene_ambience_block(block):
            continue
        groups_by_key.setdefault(_scene_mix_group_key(block), []).append(dict(block))
    groups = []
    for blocks in groups_by_key.values():
        group = _scene_mix_group_record(project_root, blocks, include_blocks=include_blocks)
        if group["block_count"] > 0:
            groups.append(group)
    return groups


def _scene_mix_group_record(
    project_root: Path,
    source_blocks: list[dict[str, object]],
    *,
    include_blocks: bool,
) -> SceneMixGroup:
    """
    @brief      Build one Scene Ambience mix group record.
    @param[in]  project_root Active project root folder.
    @param[in]  source_blocks Source Scene Ambience Audio Blocks.
    @param[in]  include_blocks True to include source block payloads.
    @return     Scene Ambience group record.
    @exception  None
    """
    ordered_blocks = speech_blocks_service.sort_speech_blocks([dict(block) for block in source_blocks])
    first_block = ordered_blocks[0] if ordered_blocks else {}
    duration_seconds = _scene_mix_duration_seconds(project_root, ordered_blocks)
    output_path = _scene_mix_output_path(project_root, ordered_blocks, duration_seconds)
    source_paths = [_audio_path(project_root, block) for block in ordered_blocks]
    has_source_audio = all(path is not None and path.is_file() for path in source_paths)
    is_approved = all(audio_blocks_service.is_approved(block) for block in ordered_blocks)
    group: SceneMixGroup = {
        "group_key": _scene_mix_group_key(first_block),
        "label": _scene_mix_label(first_block),
        "chunk_id": str(first_block.get("chunk_id", "")).strip(),
        "ambience_position": str(first_block.get("ambience_position", "")).strip(),
        "after_speech_block_id": str(first_block.get("after_speech_block_id", "")).strip(),
        "speech_block_ids": [str(block.get("speech_block_id", "")).strip() for block in ordered_blocks],
        "block_count": len(ordered_blocks),
        "duration_seconds": duration_seconds,
        "audio_relative_path": relative_to_project(project_root, output_path),
        "can_generate_preview": bool(ordered_blocks) and is_approved and has_source_audio,
        "can_play_preview": output_path.is_file(),
        "generated": output_path.is_file(),
        "output_format": OUTPUT_FORMAT_WAV,
    }
    if include_blocks:
        group["_source_blocks"] = ordered_blocks
    return group


def _strip_scene_mix_blocks(group: SceneMixGroup) -> SceneMixGroup:
    """
    @brief      Return one Scene Ambience group record without private source blocks.
    @param[in]  group Scene Ambience group record.
    @return     Public group record.
    @exception  None
    """
    public_group = dict(group)
    public_group.pop("_source_blocks", None)
    return public_group


def _scene_mix_virtual_block(project_root: Path, source_blocks: list[dict[str, object]]) -> dict[str, object]:
    """
    @brief      Build one virtual Audio Block representing a mixed Scene Ambience group.
    @param[in]  project_root Active project root folder.
    @param[in]  source_blocks Source Scene Ambience Audio Blocks.
    @return     Virtual Audio Block consumed by final composition.
    @exception  None
    """
    group = _scene_mix_group_record(project_root, source_blocks, include_blocks=True)
    first_block = dict(source_blocks[0])
    return {
        **first_block,
        "speech_block_id": str(group["group_key"]),
        "speaker_display_name": str(group["label"]),
        "text": str(group["label"]),
        "audio_relative_path": str(group["audio_relative_path"]),
        "duration_seconds": float(group["duration_seconds"]),
        "audio_duration_seconds": float(group["duration_seconds"]),
        "scene_mix_group_key": str(group["group_key"]),
        "scene_mix_source_blocks": list(group.get("_source_blocks", [])),
        "scene_mix_source_block_count": int(group["block_count"]),
        "metadata_only": False,
    }


def _build_output_plan(
    project_root: Path,
    audio_blocks: list[dict[str, object]],
    settings: AudioAssemblySettings,
) -> list[dict[str, object]]:
    """
    @brief      Build ordered output-file composition groups from Audio Blocks and settings.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_blocks Approved Audio Blocks.
    @param[in]  settings Normalized Audio Assembly settings.
    @return     Ordered output plan entries.
    @exception  ValueError Raised when no playable blocks exist.
    """
    playable_blocks = _build_composition_blocks(project_root, audio_blocks, bool(settings["include_scene_ambience"]))
    if not playable_blocks:
        raise ValueError("Audio Assembly requires at least one generated speech audio block.")
    output_mode = str(settings["output_mode"])
    if output_mode == OUTPUT_MODE_PER_CHUNK:
        return _with_reference_audio_path(_plan_per_chunk_outputs(playable_blocks), playable_blocks)
    if output_mode == OUTPUT_MODE_TIME_LIMIT:
        return _with_reference_audio_path(
            _plan_time_limited_outputs(playable_blocks, int(settings["max_duration_minutes"]), settings),
            playable_blocks,
        )
    return _with_reference_audio_path(
        [
            {
                "output_key": "audiobook",
                "file_name": "audiobook.wav",
                "blocks": playable_blocks,
                "chunk_ids": sorted({str(block.get("chunk_id", "")) for block in playable_blocks}),
                "over_limit_warning": False,
            }
        ],
        playable_blocks,
    )


def _plan_per_chunk_outputs(blocks: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Build one output file per text chunk.
    @param[in]  blocks Playable Audio Blocks.
    @return     Ordered per-chunk output plan.
    @exception  None
    """
    grouped: dict[str, list[dict[str, object]]] = {}
    for block in blocks:
        grouped.setdefault(str(block.get("chunk_id", "")).strip(), []).append(block)
    output_plan = []
    for output_index, chunk_id in enumerate(grouped, start=1):
        output_plan.append(
            {
                "output_key": f"chunk-{output_index:04d}",
                "file_name": f"chunk-{output_index:04d}.wav",
                "blocks": grouped[chunk_id],
                "chunk_ids": [chunk_id],
                "over_limit_warning": False,
            }
        )
    return output_plan


def _plan_time_limited_outputs(
    blocks: list[dict[str, object]],
    max_minutes: int,
    settings: AudioAssemblySettings,
) -> list[dict[str, object]]:
    """
    @brief      Pack sequential blocks into duration-limited output parts.
    @param[in]  blocks Playable Audio Blocks.
    @param[in]  max_minutes Maximum requested part duration.
    @param[in]  settings Normalized Audio Assembly settings.
    @return     Ordered time-limited output plan.
    @exception  None
    """
    max_seconds = max(1, int(max_minutes) * 60)
    output_plan: list[dict[str, object]] = []
    current_blocks: list[dict[str, object]] = []
    current_seconds = 0.0
    for block in blocks:
        block_seconds = float(block.get("duration_seconds", 0.0))
        added_seconds = block_seconds
        if current_blocks:
            added_seconds += _automatic_gap_ms(current_blocks[-1], block, settings) / 1000.0
        if current_blocks and current_seconds + added_seconds > max_seconds:
            output_plan.append(_time_part_record(len(output_plan) + 1, current_blocks, False))
            current_blocks = []
            current_seconds = 0.0
            added_seconds = block_seconds
        current_blocks.append(block)
        current_seconds += added_seconds
        if block_seconds > max_seconds:
            output_plan.append(_time_part_record(len(output_plan) + 1, current_blocks, True))
            current_blocks = []
            current_seconds = 0.0
    if current_blocks:
        output_plan.append(_time_part_record(len(output_plan) + 1, current_blocks, False))
    return output_plan


def _time_part_record(
    output_index: int,
    blocks: list[dict[str, object]],
    over_limit_warning: bool,
) -> dict[str, object]:
    """
    @brief      Build one time-limited output plan record.
    @param[in]  output_index Sequential output index.
    @param[in]  blocks Blocks assigned to the output.
    @param[in]  over_limit_warning True when one block exceeds the limit.
    @return     Output plan record.
    @exception  None
    """
    return {
        "output_key": f"part-{output_index:04d}",
        "file_name": f"part-{output_index:04d}.wav",
        "blocks": list(blocks),
        "chunk_ids": sorted({str(block.get("chunk_id", "")) for block in blocks}),
        "over_limit_warning": over_limit_warning,
    }


def _with_reference_audio_path(
    output_plan: list[dict[str, object]],
    blocks: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Add a fallback source WAV reference to planned outputs.
    @param[in]  output_plan Planned output records.
    @param[in]  blocks Full composable Audio Block list.
    @return     Output plan with optional reference audio paths.
    @exception  None
    """
    reference_path = next(
        (
            str(block.get("audio_relative_path", "")).strip()
            for block in blocks
            if str(block.get("audio_relative_path", "") or "").strip()
        ),
        "",
    )
    for output_item in output_plan:
        output_item["reference_audio_relative_path"] = reference_path
    return output_plan


def _warnings_for_output_plan(output_plan: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Build deterministic warning records from one output plan.
    @param[in]  output_plan Planned output records.
    @return     Warning records for the planned outputs.
    @exception  None
    """
    return [
        {
            "code": "single_block_exceeds_limit",
            "message": "One source audio block exceeds the configured time limit.",
            "output_key": str(output_item.get("output_key", "")),
        }
        for output_item in output_plan
        if bool(output_item.get("over_limit_warning", False))
    ]


def _validate_pending_output_wav_sizes(
    project_root: Path,
    output_plan: list[dict[str, object]],
    settings: AudioAssemblySettings,
    completed_records: list[dict[str, object]],
) -> None:
    """
    @brief      Reject pending output-plan items too large for classic WAV.
    @param[in]  project_root Active project root folder.
    @param[in]  output_plan Planned output records.
    @param[in]  settings Normalized Audio Assembly settings.
    @param[in]  completed_records Resume-safe outputs that need no rewrite.
    @return     None.
    @exception  RuntimeError Raised when one pending output exceeds the limit.
    """
    completed_keys = {str(record.get("output_key", "")) for record in completed_records}
    for output_item in output_plan:
        if str(output_item.get("output_key", "")) in completed_keys:
            continue
        blocks = [dict(block) for block in output_item.get("blocks", []) if isinstance(block, dict)]
        reference_params = _planned_reference_wav_params(
            project_root,
            blocks,
            str(output_item.get("reference_audio_relative_path", "")),
        )
        planned_frames = _planned_output_frame_count(project_root, blocks, settings, reference_params)
        _validate_classic_wav_data_size(
            str(output_item.get("file_name", "output.wav")),
            planned_frames,
            reference_params,
        )


def _planned_reference_wav_params(
    project_root: Path,
    blocks: list[dict[str, object]],
    fallback_relative_path: str,
) -> wave._wave_params:
    """
    @brief      Resolve output parameters without materializing virtual Scene Mix WAVs.
    @param[in]  project_root Active project root folder.
    @param[in]  blocks Planned output Audio Blocks.
    @param[in]  fallback_relative_path Existing fallback-source path.
    @return     Reference WAV parameters chosen by the composition policy.
    @exception  RuntimeError Raised when no source WAV is available.
    """
    preferred_blocks = [block for block in blocks if not _is_scene_ambience_block(block)]
    for candidate_blocks in (preferred_blocks, blocks):
        for block in candidate_blocks:
            source_path = _planned_block_reference_path(project_root, block)
            if source_path is None:
                continue
            with wave.open(str(source_path), "rb") as source_wav:
                return source_wav.getparams()
    fallback_path = _safe_project_artifact_path(project_root, fallback_relative_path)
    if fallback_path is not None and fallback_path.is_file():
        with wave.open(str(fallback_path), "rb") as source_wav:
            return source_wav.getparams()
    raise RuntimeError("Audio Assembly cannot write an output file without at least one source WAV.")


def _planned_block_reference_path(project_root: Path, block: dict[str, object]) -> Path | None:
    """
    @brief      Resolve a real source path for direct or virtual composition blocks.
    @param[in]  project_root Active project root folder.
    @param[in]  block Planned composition block.
    @return     Safe source path or `None` for a synthesized pause.
    @exception  None
    """
    if not _is_scene_mix_virtual_block(block):
        return _audio_path(project_root, block)
    source_blocks = [dict(item) for item in block.get("scene_mix_source_blocks", []) if isinstance(item, dict)]
    return _audio_path(project_root, source_blocks[0]) if source_blocks else None


def _planned_output_frame_count(
    project_root: Path,
    blocks: list[dict[str, object]],
    settings: AudioAssemblySettings,
    reference_params,
) -> int:
    """
    @brief      Conservatively count frames one final output writer can emit.
    @param[in]  project_root Active project root folder.
    @param[in]  blocks Planned composition blocks.
    @param[in]  settings Normalized Audio Assembly settings.
    @param[in]  reference_params Selected output WAV parameters.
    @return     Conservative output frame count.
    @exception  RuntimeError Raised when a source frame rate is invalid.
    """
    output_rate = int(reference_params.framerate)
    planned_frames = 0
    previous_block = None
    for block_index, block in enumerate(blocks):
        if block_index > 0 and previous_block is not None:
            planned_frames += _silence_frame_count(
                output_rate,
                _automatic_gap_ms(previous_block, block, settings),
            )
        if _is_pause_block(block):
            planned_frames += _silence_frame_count(output_rate, _pause_duration_ms(block))
        else:
            planned_frames += _planned_block_output_frame_count(project_root, block, output_rate)
        previous_block = block
    return planned_frames


def _planned_block_output_frame_count(project_root: Path, block: dict[str, object], output_rate: int) -> int:
    """
    @brief      Count or bound final-output frames for one source block.
    @param[in]  project_root Active project root folder.
    @param[in]  block Planned direct or virtual composition block.
    @param[in]  output_rate Final output sample rate.
    @return     Conservative output frame count for the block.
    @exception  RuntimeError Raised when source audio is unavailable.
    """
    if _is_scene_mix_virtual_block(block):
        source_blocks = [dict(item) for item in block.get("scene_mix_source_blocks", []) if isinstance(item, dict)]
        source_paths = [_audio_path(project_root, item) for item in source_blocks]
        if not source_paths or any(path is None for path in source_paths):
            raise RuntimeError("Audio Assembly cannot size Scene Ambience without source WAV files.")
        with ExitStack() as stack:
            source_wavs = [stack.enter_context(wave.open(str(path), "rb")) for path in source_paths if path is not None]
            source_rate = int(source_wavs[0].getframerate())
            source_frames = _scene_mix_target_frames(
                source_wavs,
                source_rate,
                float(block.get("duration_seconds", 0.0) or 0.0),
            )
        return _conservative_resampled_frame_count(source_frames, source_rate, output_rate)
    source_path = _audio_path(project_root, block)
    if source_path is None:
        raise RuntimeError("Audio Assembly cannot size an output source without a WAV file.")
    with wave.open(str(source_path), "rb") as source_wav:
        return _conservative_resampled_frame_count(
            int(source_wav.getnframes()),
            int(source_wav.getframerate()),
            output_rate,
        )


def _conservative_resampled_frame_count(source_frames: int, source_rate: int, output_rate: int) -> int:
    """
    @brief      Bound resampled frames using ceiling integer arithmetic.
    @param[in]  source_frames Declared source frame count.
    @param[in]  source_rate Source sample rate.
    @param[in]  output_rate Output sample rate.
    @return     Exact same-rate count or conservative converted count.
    @exception  RuntimeError Raised when a sample rate is not positive.
    """
    if source_rate <= 0 or output_rate <= 0:
        raise RuntimeError("Audio Assembly requires positive WAV sample rates.")
    if source_frames <= 0 or source_rate == output_rate:
        return max(source_frames, 0)
    return (source_frames * output_rate + source_rate - 1) // source_rate


def _validate_classic_wav_data_size(file_name: str, planned_frames: int, reference_params) -> None:
    """
    @brief      Reject PCM payloads whose RIFF length cannot fit unsigned 32-bit fields.
    @param[in]  file_name Operator-facing output file name.
    @param[in]  planned_frames Conservative final-output frame count.
    @param[in]  reference_params Selected output WAV parameters.
    @return     None.
    @exception  RuntimeError Raised when the planned PCM payload is too large.
    """
    frame_size = int(reference_params.nchannels) * int(reference_params.sampwidth)
    planned_data_bytes = planned_frames * frame_size
    if planned_data_bytes > _WAV_MAX_DATA_BYTES:
        raise RuntimeError(
            f"Audio Assembly cannot create {file_name}: this output would exceed the 4 GB classic WAV limit. "
            "Use Per text chunk or Time limit output mode."
        )


def _automatic_gap_ms(
    previous_block: dict[str, object],
    current_block: dict[str, object],
    settings: AudioAssemblySettings,
) -> int:
    """
    @brief      Resolve automatic silence inserted between two adjacent blocks.
    @param[in]  previous_block Previous planned Audio Block.
    @param[in]  current_block Current planned Audio Block.
    @param[in]  settings Normalized Audio Assembly settings.
    @return     Automatic gap in milliseconds.
    @exception  None
    """
    if _is_pause_block(previous_block) or _is_pause_block(current_block):
        return 0
    if str(current_block.get("chunk_id", "")) != str(previous_block.get("chunk_id", "")):
        return int(settings["inter_chunk_silence_ms"])
    return int(settings["inter_block_silence_ms"])


def _compose_output_file(
    project_root: Path,
    output_item: dict[str, object],
    settings: AudioAssemblySettings,
    cancel_requested=None,
) -> dict[str, object]:
    """
    @brief      Write one final WAV output file from its assigned source blocks.
    @param[in]  project_root Active project root folder.
    @param[in]  output_item Output plan item.
    @param[in]  settings Normalized Audio Assembly settings.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Completed output record.
    @exception  RuntimeError Raised when source WAV files are invalid.
    """
    output_root = project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / str(output_item["file_name"])
    temp_path = output_path.with_name(output_path.name + _TEMP_SUFFIX)
    if temp_path.is_file():
        temp_path.unlink()
    blocks = [dict(block) for block in output_item.get("blocks", []) if isinstance(block, dict)]
    blocks = [_materialize_scene_mix_block(project_root, block, cancel_requested) for block in blocks]
    reference_params = _reference_wav_params(
        project_root,
        blocks,
        str(output_item.get("reference_audio_relative_path", "")),
    )
    total_frames = 0
    try:
        with wave.open(str(temp_path), "wb") as output_wav:
            output_wav.setparams(reference_params)
            previous_block = None
            for block_index, block in enumerate(blocks):
                raise_if_cancelled(cancel_requested)
                source_path = _audio_path(project_root, block)
                if source_path is None and not _is_pause_block(block):
                    continue
                if block_index > 0 and previous_block is not None:
                    gap_ms = _automatic_gap_ms(previous_block, block, settings)
                    silence_frames = _write_silence(output_wav, gap_ms, reference_params)
                    total_frames += silence_frames
                if _is_pause_block(block):
                    pause_frames = _write_silence(output_wav, _pause_duration_ms(block), reference_params)
                    total_frames += pause_frames
                    previous_block = block
                    continue
                assert source_path is not None
                with wave.open(str(source_path), "rb") as source_wav:
                    params = source_wav.getparams()
                    if params.sampwidth not in _WAV_SAMPLE_WIDTH_BY_FORMAT:
                        raise RuntimeError("Audio Assembly supports uncompressed PCM WAV source files only.")
                    total_frames += _copy_or_convert_wav_frames(
                        source_wav,
                        output_wav,
                        reference_params,
                        cancel_requested,
                    )
                    previous_block = block
    except Exception:
        with suppress(OSError):
            if temp_path.is_file():
                temp_path.unlink()
        raise
    if output_path.is_file():
        output_path.unlink()
    temp_path.replace(output_path)
    sample_rate = int(reference_params.framerate)
    duration_seconds = 0.0 if sample_rate <= 0 else total_frames / sample_rate
    return {
        "output_key": str(output_item["output_key"]),
        "file_name": output_path.name,
        "audio_relative_path": relative_to_project(project_root, output_path),
        "block_count": sum(_composition_block_count(block) for block in blocks),
        "chunk_ids": list(output_item.get("chunk_ids", [])),
        "duration_seconds": duration_seconds,
        "generated": True,
        "output_format": OUTPUT_FORMAT_WAV,
    }


def _materialize_scene_mix_block(
    project_root: Path,
    block: dict[str, object],
    cancel_requested=None,
) -> dict[str, object]:
    """
    @brief      Ensure one virtual Scene Ambience mix block has a WAV source.
    @param[in]  project_root Active project root folder.
    @param[in]  block Composition block.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Composition block with a materialized audio path.
    @exception  RuntimeError Raised when Scene Ambience sources cannot be mixed.
    """
    if not _is_scene_mix_virtual_block(block):
        return block
    source_blocks = [dict(item) for item in block.get("scene_mix_source_blocks", []) if isinstance(item, dict)]
    if not source_blocks:
        raise RuntimeError("Audio Assembly cannot mix Scene Ambience without source audio blocks.")
    group = _scene_mix_group_record(project_root, source_blocks, include_blocks=True)
    output_path = _write_scene_mix_group(project_root, group, cancel_requested=cancel_requested)
    materialized_block = dict(block)
    materialized_block["audio_relative_path"] = relative_to_project(project_root, output_path)
    materialized_block["duration_seconds"] = _wav_duration_seconds(output_path)
    materialized_block["audio_duration_seconds"] = materialized_block["duration_seconds"]
    return materialized_block


def _write_scene_mix_group(
    project_root: Path,
    group: SceneMixGroup,
    progress_callback=None,
    progress_start: int = 0,
    progress_end: int = 1,
    progress_total: int = 1,
    cancel_requested=None,
) -> Path:
    """
    @brief      Mix one Scene Ambience group into its deterministic WAV path.
    @param[in]  project_root Active project root folder.
    @param[in]  group Scene Ambience group record with source blocks.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  progress_start Completed progress units before mixing starts.
    @param[in]  progress_end Completed progress units after mixing ends.
    @param[in]  progress_total Total progress units for the parent operation.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Generated scene mix WAV path.
    @exception  RuntimeError Raised when source WAV files are missing or invalid.
    """
    source_blocks = [dict(item) for item in group.get("_source_blocks", []) if isinstance(item, dict)]
    source_paths = [_audio_path(project_root, block) for block in source_blocks]
    if not source_paths or any(path is None or not path.is_file() for path in source_paths):
        raise RuntimeError("Scene Ambience mix requires generated source WAV files.")
    output_path = _safe_project_artifact_path(project_root, group.get("audio_relative_path"))
    if output_path is None:
        output_path = _scene_mix_output_path(project_root, source_blocks, float(group.get("duration_seconds", 0.0)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(output_path.name + _TEMP_SUFFIX)
    if temp_path.is_file():
        temp_path.unlink()
    assert all(path is not None for path in source_paths)
    _mix_wav_sources(
        [path for path in source_paths if path is not None],
        temp_path,
        float(group.get("duration_seconds", 0.0) or 0.0),
        progress_callback=progress_callback,
        progress_start=progress_start,
        progress_end=progress_end,
        progress_total=progress_total,
        progress_message=f"Mixing {group.get('label', 'Scene Mix preview')}.",
        cancel_requested=cancel_requested,
    )
    if output_path.is_file():
        output_path.unlink()
    temp_path.replace(output_path)
    return output_path


def _mix_wav_sources(
    source_paths: list[Path],
    output_path: Path,
    duration_seconds: float,
    progress_callback=None,
    progress_start: int = 0,
    progress_end: int = 1,
    progress_total: int = 1,
    progress_message: str = "Mixing Scene Mix preview.",
    cancel_requested=None,
) -> None:
    """
    @brief      Overlay compatible PCM WAV sources into one fixed-duration WAV.
    @param[in]  source_paths Source WAV files.
    @param[in]  output_path Destination WAV file path.
    @param[in]  duration_seconds Target mix duration in seconds.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  progress_start Completed progress units before mixing starts.
    @param[in]  progress_end Completed progress units after mixing ends.
    @param[in]  progress_total Total progress units for the parent operation.
    @param[in]  progress_message Operator-facing progress message.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     None.
    @exception  RuntimeError Raised when source WAV files are incompatible.
    """
    if not source_paths:
        raise RuntimeError("Scene Ambience mix requires at least one source WAV.")
    with ExitStack() as stack:
        sources = [stack.enter_context(wave.open(str(path), "rb")) for path in source_paths]
        reference_params = sources[0].getparams()
        expected_params = reference_params[:3], reference_params[4:]
        if reference_params.sampwidth not in _WAV_SAMPLE_WIDTH_BY_FORMAT:
            raise RuntimeError("Audio Assembly supports uncompressed PCM WAV source files only.")
        for source_wav in sources[1:]:
            params = source_wav.getparams()
            if params.sampwidth not in _WAV_SAMPLE_WIDTH_BY_FORMAT:
                raise RuntimeError("Audio Assembly supports uncompressed PCM WAV source files only.")
            if (params[:3], params[4:]) != expected_params:
                raise RuntimeError("Audio Assembly found incompatible source WAV parameters.")
        target_frames = _scene_mix_target_frames(sources, reference_params.framerate, duration_seconds)
        last_progress_unit = -1
        with wave.open(str(output_path), "wb") as output_wav:
            output_wav.setparams(reference_params)
            remaining_frames = target_frames
            while remaining_frames > 0:
                raise_if_cancelled(cancel_requested)
                written_frames = target_frames - remaining_frames
                progress_unit = progress_start
                if target_frames > 0 and progress_end > progress_start:
                    progress_unit = progress_start + int(
                        ((progress_end - progress_start) * written_frames) / target_frames
                    )
                if progress_unit != last_progress_unit:
                    _emit_progress(progress_callback, progress_unit, progress_total, progress_message)
                    last_progress_unit = progress_unit
                frame_count = min(remaining_frames, _WAV_COPY_FRAME_CHUNK_SIZE)
                chunks = [_read_or_pad_wav_frames(source_wav, frame_count, reference_params) for source_wav in sources]
                output_wav.writeframes(_mix_pcm_chunks(chunks, frame_count, reference_params))
                remaining_frames -= frame_count
        _emit_progress(progress_callback, progress_end, progress_total, progress_message)


def _scene_mix_target_frames(sources: list[wave.Wave_read], frame_rate: int, duration_seconds: float) -> int:
    """
    @brief      Resolve the fixed frame count for one Scene Ambience mix.
    @param[in]  sources Open source WAV readers.
    @param[in]  frame_rate Mix frame rate.
    @param[in]  duration_seconds Requested target duration.
    @return     Target frame count.
    @exception  None
    """
    if frame_rate > 0 and duration_seconds > 0.0:
        return max(1, int(round(frame_rate * duration_seconds)))
    return max((int(source.getnframes()) for source in sources), default=1)


def _read_or_pad_wav_frames(source_wav: wave.Wave_read, frame_count: int, params) -> bytes:
    """
    @brief      Read WAV frames and pad short sources with silence.
    @param[in]  source_wav Open source WAV reader.
    @param[in]  frame_count Requested frame count.
    @param[in]  params Reference WAV parameters.
    @return     Exactly `frame_count` frames of PCM bytes.
    @exception  None
    """
    frame_size = max(int(params.nchannels) * int(params.sampwidth), 1)
    data = source_wav.readframes(frame_count)
    expected_size = frame_count * frame_size
    if len(data) >= expected_size:
        return data[:expected_size]
    silence_byte = b"\x80" if int(params.sampwidth) == 1 else b"\x00"
    return data + (silence_byte * (expected_size - len(data)))


def _mix_pcm_chunks(chunks: list[bytes], frame_count: int, params) -> bytes:
    """
    @brief      Mix same-format PCM chunks with conservative gain reduction.
    @param[in]  chunks Source PCM chunks.
    @param[in]  frame_count Number of frames in each chunk.
    @param[in]  params Reference WAV parameters.
    @return     Mixed PCM byte chunk.
    @exception  None
    """
    channels = int(params.nchannels)
    sample_width = int(params.sampwidth)
    sample_count = frame_count * channels
    scale = 1.0 / max(len(chunks), 1)
    output = bytearray()
    for sample_index in range(sample_count):
        mixed_value = 0
        offset = sample_index * sample_width
        for chunk in chunks:
            mixed_value += _decode_pcm_sample(chunk[offset : offset + sample_width], sample_width)
        output.extend(_encode_pcm_sample(int(round(mixed_value * scale)), sample_width))
    return bytes(output)


def _decode_pcm_sample(sample_bytes: bytes, sample_width: int) -> int:
    """
    @brief      Decode one PCM sample to a signed integer.
    @param[in]  sample_bytes Raw PCM sample bytes.
    @param[in]  sample_width Sample width in bytes.
    @return     Signed sample value.
    @exception  None
    """
    if sample_width == 1:
        return int.from_bytes(sample_bytes or b"\x80", "little", signed=False) - 128
    return int.from_bytes(sample_bytes.ljust(sample_width, b"\x00"), "little", signed=True)


def _encode_pcm_sample(sample_value: int, sample_width: int) -> bytes:
    """
    @brief      Encode one signed integer as a clipped PCM sample.
    @param[in]  sample_value Signed sample value.
    @param[in]  sample_width Sample width in bytes.
    @return     Raw PCM sample bytes.
    @exception  None
    """
    if sample_width == 1:
        return int(max(0, min(sample_value + 128, 255))).to_bytes(1, "little", signed=False)
    minimum = -(1 << (8 * sample_width - 1))
    maximum = (1 << (8 * sample_width - 1)) - 1
    return int(max(minimum, min(sample_value, maximum))).to_bytes(sample_width, "little", signed=True)


def _scene_mix_group_key(block: dict[str, object]) -> str:
    """
    @brief      Build one stable Scene Ambience group key.
    @param[in]  block Scene Ambience Audio Block payload.
    @return     Stable group key.
    @exception  None
    """
    chunk_id = str(block.get("chunk_id", "")).strip()
    position = str(block.get("ambience_position", "")).strip() or "scene"
    after_id = str(block.get("after_speech_block_id", "")).strip() if position == "scene_change" else ""
    return f"{_SCENE_MIX_KEY_PREFIX}:{chunk_id}:{position}:{after_id}"


def _scene_mix_label(block: dict[str, object]) -> str:
    """
    @brief      Build an operator-facing Scene Ambience mix label.
    @param[in]  block Scene Ambience Audio Block payload.
    @return     Display label.
    @exception  None
    """
    chunk_id = str(block.get("chunk_id", "")).strip() or "chunk"
    position = str(block.get("ambience_position", "")).strip() or "scene"
    after_id = str(block.get("after_speech_block_id", "")).strip()
    if position == "scene_change" and after_id:
        return f"{chunk_id} scene mix after {after_id}"
    return f"{chunk_id} {position.replace('_', ' ')} scene mix"


def _scene_mix_duration_seconds(project_root: Path, source_blocks: list[dict[str, object]]) -> float:
    """
    @brief      Resolve one Scene Ambience group duration.
    @param[in]  project_root Active project root folder.
    @param[in]  source_blocks Source Scene Ambience blocks.
    @return     Target group duration in seconds.
    @exception  None
    """
    durations: list[float] = []
    for block in source_blocks:
        with suppress(TypeError, ValueError):
            durations.append(float(block.get("duration_seconds", 0.0) or 0.0))
        audio_path = _audio_path(project_root, block)
        if audio_path is not None and audio_path.is_file():
            durations.append(_wav_duration_seconds(audio_path))
    return max([duration for duration in durations if duration > 0.0], default=0.0)


def _scene_mix_output_path(project_root: Path, source_blocks: list[dict[str, object]], duration_seconds: float) -> Path:
    """
    @brief      Build the deterministic output path for one Scene Ambience mix.
    @param[in]  project_root Active project root folder.
    @param[in]  source_blocks Source Scene Ambience blocks.
    @param[in]  duration_seconds Target group duration.
    @return     Scene mix WAV path.
    @exception  None
    """
    first_block = source_blocks[0] if source_blocks else {}
    group_digest = hashlib.sha1(_scene_mix_group_key(first_block).encode("utf-8")).hexdigest()[:10]  # noqa: S324
    source_digest = _scene_mix_source_fingerprint(project_root, source_blocks, duration_seconds)[:10]
    return (
        project_root
        / config.AUDIOBOOK_OUTPUT_FOLDER_NAME
        / _SCENE_MIX_PREVIEW_FOLDER_NAME
        / f"scene_mix_{group_digest}_{source_digest}.wav"
    )


def _scene_mix_source_fingerprint(
    project_root: Path,
    source_blocks: list[dict[str, object]],
    duration_seconds: float,
) -> str:
    """
    @brief      Build a fingerprint for Scene Ambience mix source audio.
    @param[in]  project_root Active project root folder.
    @param[in]  source_blocks Source Scene Ambience blocks.
    @param[in]  duration_seconds Target group duration.
    @return     SHA-1 hex digest.
    @exception  None
    """
    payload = {
        "duration_seconds": duration_seconds,
        "sources": [
            {
                "speech_block_id": str(block.get("speech_block_id", "")).strip(),
                "audio_relative_path": str(block.get("audio_relative_path", "")).strip(),
                "file_sha1": _file_sha1(_audio_path(project_root, block)),
            }
            for block in source_blocks
        ],
    }
    return hashlib.sha1(  # noqa: S324
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _is_scene_mix_virtual_block(block: dict[str, object]) -> bool:
    """
    @brief      Return whether one block is a virtual Scene Ambience mix.
    @param[in]  block Composition block.
    @return     True when the block represents a mixed Scene Ambience group.
    @exception  None
    """
    return bool(str(block.get("scene_mix_group_key", "")).strip())


def _composition_block_count(block: dict[str, object]) -> int:
    """
    @brief      Resolve how many source Audio Blocks one composition block represents.
    @param[in]  block Composition block.
    @return     Source Audio Block count.
    @exception  None
    """
    if _is_scene_mix_virtual_block(block):
        return _bounded_int(block.get("scene_mix_source_block_count", 1), 1, 1_000_000, 1)
    return 1


def _write_silence(output_wav: wave.Wave_write, gap_ms: int, params) -> int:
    """
    @brief      Write PCM silence frames into one output WAV stream.
    @details    Zero bytes are silence only for signed PCM. That holds for every width
                in `_WAV_SAMPLE_WIDTH_BY_FORMAT`, which excludes unsigned 8-bit for
                exactly this reason; do not re-admit one-byte PCM without also giving
                this function an unsigned zero level of 0x80.
    @param[in]  output_wav Active output WAV writer.
    @param[in]  gap_ms Gap length in milliseconds.
    @param[in]  params WAV params from the current source file.
    @return     Number of frames written.
    @exception  None
    """
    if gap_ms <= 0:
        return 0
    channels = int(params.nchannels)
    sample_width = int(params.sampwidth)
    frame_rate = int(params.framerate)
    frame_count = _silence_frame_count(frame_rate, gap_ms)
    if frame_count <= 0:
        return 0
    output_wav.writeframes(b"\x00" * frame_count * channels * sample_width)
    return frame_count


def _silence_frame_count(frame_rate: int, duration_ms: int) -> int:
    """
    @brief      Convert silence milliseconds to exact whole PCM frames.
    @param[in]  frame_rate Output sample rate.
    @param[in]  duration_ms Silence duration in milliseconds.
    @return     Whole silence frame count using floor semantics.
    @exception  None
    """
    if frame_rate <= 0 or duration_ms <= 0:
        return 0
    return frame_rate * duration_ms // 1000


def _copy_wav_frames(source_wav, output_wav: wave.Wave_write, cancel_requested=None) -> int:
    """
    @brief      Copy source WAV frames to the output in bounded chunks.
    @param[in]  source_wav Active source WAV reader.
    @param[in]  output_wav Active output WAV writer.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Number of frames copied.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    """
    frame_size = max(int(source_wav.getnchannels()) * int(source_wav.getsampwidth()), 1)
    remaining_frames = int(source_wav.getnframes())
    copied_frames = 0
    while remaining_frames > 0:
        raise_if_cancelled(cancel_requested)
        frames_to_read = min(remaining_frames, _WAV_COPY_FRAME_CHUNK_SIZE)
        frame_data = source_wav.readframes(frames_to_read)
        if not frame_data:
            break
        output_wav.writeframes(frame_data)
        frames_read = len(frame_data) // frame_size
        copied_frames += frames_read
        remaining_frames -= frames_read
        if frames_read <= 0:
            break
    return copied_frames


def _copy_or_convert_wav_frames(
    source_wav,
    output_wav: wave.Wave_write,
    target_params,
    cancel_requested=None,
) -> int:
    """
    @brief      Copy or convert source WAV frames to the output WAV format.
    @param[in]  source_wav Active source WAV reader.
    @param[in]  output_wav Active output WAV writer.
    @param[in]  target_params Output WAV parameters.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Number of output frames written.
    @exception  RuntimeError Raised when source conversion is unsupported.
    """
    source_params = source_wav.getparams()
    if (source_params[:3], source_params[4:]) == (target_params[:3], target_params[4:]):
        return _copy_wav_frames(source_wav, output_wav, cancel_requested)
    if (
        source_params.sampwidth not in _WAV_SAMPLE_WIDTH_BY_FORMAT
        or target_params.sampwidth not in _WAV_SAMPLE_WIDTH_BY_FORMAT
    ):
        raise RuntimeError("Audio Assembly supports uncompressed PCM WAV source files only.")
    rate_state = None
    remaining_frames = int(source_wav.getnframes())
    output_frame_size = max(int(target_params.nchannels) * int(target_params.sampwidth), 1)
    source_frame_size = max(int(source_params.nchannels) * int(source_params.sampwidth), 1)
    written_frames = 0
    while remaining_frames > 0:
        raise_if_cancelled(cancel_requested)
        frames_to_read = min(remaining_frames, _WAV_COPY_FRAME_CHUNK_SIZE)
        frame_data = source_wav.readframes(frames_to_read)
        if not frame_data:
            break
        converted_data, rate_state = _convert_wav_frame_chunk(frame_data, source_params, target_params, rate_state)
        if converted_data:
            output_wav.writeframes(converted_data)
            written_frames += len(converted_data) // output_frame_size
        frames_read = len(frame_data) // source_frame_size
        remaining_frames -= frames_read
        if frames_read <= 0:
            break
    return written_frames


def _convert_wav_frame_chunk(frame_data: bytes, source_params, target_params, rate_state) -> tuple[bytes, object]:
    """
    @brief      Convert one PCM frame chunk between compatible WAV layouts.
    @param[in]  frame_data Source PCM bytes.
    @param[in]  source_params Source WAV parameters.
    @param[in]  target_params Target WAV parameters.
    @param[in]  rate_state Running resampler state from `pcm_codec.convert_frame_rate`.
    @return     Tuple of converted PCM bytes and updated rate-conversion state.
    @exception  RuntimeError Raised when channel conversion is unsupported.
    """
    converted_data = frame_data
    current_sample_width = int(source_params.sampwidth)
    current_channels = int(source_params.nchannels)
    target_sample_width = int(target_params.sampwidth)
    target_channels = int(target_params.nchannels)
    if current_sample_width != target_sample_width:
        converted_data = pcm_codec.convert_sample_width(converted_data, current_sample_width, target_sample_width)
        current_sample_width = target_sample_width
    converted_data = _convert_wav_channels(
        converted_data,
        current_sample_width,
        current_channels,
        target_channels,
    )
    current_channels = target_channels
    if int(source_params.framerate) != int(target_params.framerate):
        converted_data, rate_state = pcm_codec.convert_frame_rate(
            converted_data,
            current_sample_width,
            current_channels,
            int(source_params.framerate),
            int(target_params.framerate),
            rate_state,
        )
    return converted_data, rate_state


def _convert_wav_channels(frame_data: bytes, sample_width: int, source_channels: int, target_channels: int) -> bytes:
    """
    @brief      Convert PCM frame data between mono and stereo channel layouts.
    @param[in]  frame_data Source PCM bytes.
    @param[in]  sample_width Sample width in bytes.
    @param[in]  source_channels Source channel count.
    @param[in]  target_channels Target channel count.
    @return     PCM bytes with the target channel count.
    @exception  RuntimeError Raised when the channel conversion is unsupported.
    """
    if source_channels == target_channels:
        return frame_data
    if source_channels == 1 and target_channels == 2:
        return pcm_codec.mono_to_stereo(frame_data, sample_width, 1.0, 1.0)
    if source_channels == 2 and target_channels == 1:
        return pcm_codec.stereo_to_mono(frame_data, sample_width, 0.5, 0.5)
    raise RuntimeError("Audio Assembly supports WAV channel conversion only between mono and stereo.")


def _build_report(
    settings: AudioAssemblySettings,
    audio_blocks: list[dict[str, object]],
    output_plan: list[dict[str, object]],
    outputs: list[dict[str, object]],
    warnings: list[dict[str, object]],
    input_fingerprint: str,
    status: str,
    started_at: str,
    completed_at: str | None,
) -> AudioAssemblyReport:
    """
    @brief      Build one Audio Assembly report from current composition state.
    @param[in]  settings Normalized Audio Assembly settings.
    @param[in]  audio_blocks Approved Audio Blocks.
    @param[in]  output_plan Planned output files.
    @param[in]  outputs Completed output records.
    @param[in]  warnings Warning records.
    @param[in]  input_fingerprint Stable composition input fingerprint.
    @param[in]  status Current operation status.
    @param[in]  started_at Operation start timestamp.
    @param[in]  completed_at Optional completion timestamp.
    @return     Report payload.
    @exception  None
    """
    included_audio_block_count = sum(
        1
        for block in audio_blocks
        if _is_included_scene_ambience_block(block, bool(settings["include_scene_ambience"]))
    )
    planned_count = len(output_plan)
    completed_count = len(outputs)
    if planned_count > 0 and completed_count >= planned_count:
        stage_status = AUDIO_ASSEMBLY_STAGE_COMPLETED
    elif completed_count > 0 or status in {"running", "cancelled"}:
        stage_status = AUDIO_ASSEMBLY_STAGE_IN_PROGRESS
    else:
        stage_status = AUDIO_ASSEMBLY_STAGE_NOT_STARTED
    return {
        "audio_assembly_stage_status": stage_status,
        "operation_status": status,
        "settings": normalize_audio_assembly_settings(settings),
        "input_fingerprint": input_fingerprint,
        "total_audio_block_count": included_audio_block_count,
        "composed_audio_block_count": sum(int(output.get("block_count", 0)) for output in outputs),
        "planned_output_count": planned_count,
        "generated_output_count": completed_count,
        "total_duration_seconds": sum(float(output.get("duration_seconds", 0.0)) for output in outputs),
        "outputs": [_normalize_output_record(output) for output in outputs],
        "warning_count": len(warnings),
        "warnings": list(warnings),
    }


def _build_operation_state(
    project_root: Path,
    report: AudioAssemblyReport,
    output_plan: list[dict[str, object]],
) -> AudioAssemblyState:
    """
    @brief      Build one persisted Audio Assembly operation-state payload.
    @param[in]  project_root Active project root folder.
    @param[in]  report Current Audio Assembly report.
    @param[in]  output_plan Planned output files.
    @return     Operation-state payload.
    @exception  None
    """
    _ = project_root
    return build_operation_state_payload(
        status=str(report.get("operation_status", "not_started")),
        progress_current=int(report.get("generated_output_count", 0)),
        progress_total=len(output_plan),
        mode=_MODE,
        warning_count=int(report.get("warning_count", 0)),
        metadata={
            "input_fingerprint": str(report.get("input_fingerprint", "")),
            "output_mode": str(dict(report.get("settings", {})).get("output_mode", "")),
            "output_format": OUTPUT_FORMAT_WAV,
            "total_duration_seconds": float(report.get("total_duration_seconds", 0.0)),
        },
        resume_checkpoint=None,
    )


def _persist_state(project_root: Path, report: AudioAssemblyReport, operation_state: AudioAssemblyState) -> None:
    """
    @brief      Persist Audio Assembly report and operation state.
    @param[in]  project_root Active project root folder.
    @param[in]  report Current report payload.
    @param[in]  operation_state Current state payload.
    @return     None.
    @exception  None
    """
    write_json_atomic(
        build_operation_output_path(project_root, "audio_assembly", config.AUDIO_ASSEMBLY_REPORT_FILE_NAME),
        report,
    )
    write_json_atomic(
        build_operation_output_path(project_root, "audio_assembly", config.AUDIO_ASSEMBLY_STATE_FILE_NAME),
        operation_state,
    )


def _completed_records_for_resume(
    project_root: Path,
    existing_state: dict[str, object],
    input_fingerprint: str,
) -> list[dict[str, object]]:
    """
    @brief      Return completed output records that are safe to reuse.
    @param[in]  project_root Active project root folder.
    @param[in]  existing_state Persisted operation state.
    @param[in]  input_fingerprint Current input fingerprint.
    @return     Reusable completed output records.
    @exception  None
    """
    metadata = existing_state.get("metadata", {}) if isinstance(existing_state, dict) else {}
    if not isinstance(metadata, dict) or str(metadata.get("input_fingerprint", "")) != input_fingerprint:
        return []
    records = []
    for output in load_generated_outputs(project_root):
        audio_path = _safe_project_artifact_path(project_root, output.get("audio_relative_path"))
        if audio_path is not None and audio_path.is_file():
            records.append(output)
    return records


def _requires_manual_reset(existing_state: dict[str, object], input_fingerprint: str) -> bool:
    """
    @brief      Return whether existing persisted state belongs to different inputs.
    @param[in]  existing_state Persisted state payload.
    @param[in]  input_fingerprint Current input fingerprint.
    @return     True when operator reset is required.
    @exception  None
    """
    if not existing_state:
        return False
    status = str(existing_state.get("status", "")).strip()
    try:
        progress_current = int(existing_state.get("progress_current", 0) or 0)
        progress_total = int(existing_state.get("progress_total", 0) or 0)
    except (TypeError, ValueError):
        progress_current = 0
        progress_total = 0
    has_runtime_artifacts = any(
        (
            progress_current > 0,
            progress_total > 0,
        )
    )
    if status in {"", AUDIO_ASSEMBLY_STAGE_NOT_STARTED} and not has_runtime_artifacts:
        return False
    metadata = existing_state.get("metadata", {}) if isinstance(existing_state, dict) else {}
    if not isinstance(metadata, dict):
        return True
    persisted = str(metadata.get("input_fingerprint", "")).strip()
    return not persisted or persisted != input_fingerprint


def _audio_path(project_root: Path, audio_block: dict[str, object]) -> Path | None:
    """
    @brief      Resolve one Audio Block audio path from its project-relative metadata.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_block Audio Block payload.
    @return     Absolute audio path or `None` when no path is stored.
    @exception  None
    """
    return _safe_project_artifact_path(project_root, audio_block.get("audio_relative_path"))


def _is_assembly_block(audio_block: dict[str, object], include_scene_ambience: bool) -> bool:
    """
    @brief      Return whether one Audio Block contributes to final composition.
    @param[in]  audio_block Audio Block payload.
    @param[in]  include_scene_ambience True when Scene Ambience contributes.
    @return     True for generated audio blocks and metadata-only pause blocks.
    @exception  None
    """
    if _is_scene_ambience_block(audio_block):
        return bool(include_scene_ambience) and bool(str(audio_block.get("audio_relative_path", "") or "").strip())
    return bool(str(audio_block.get("audio_relative_path", "") or "").strip()) or _is_pause_block(audio_block)


def _is_included_scene_ambience_block(audio_block: dict[str, object], include_scene_ambience: bool) -> bool:
    """
    @brief      Return whether one block passes the Scene Ambience inclusion policy.
    @param[in]  audio_block Audio Block payload.
    @param[in]  include_scene_ambience True when Scene Ambience audio should be included.
    @return     False only for Scene Ambience blocks excluded by settings.
    @exception  None
    """
    return bool(include_scene_ambience) or not _is_scene_ambience_block(audio_block)


def _is_scene_ambience_block(audio_block: dict[str, object]) -> bool:
    """
    @brief      Return whether one Audio Block is generated Scene Ambience.
    @param[in]  audio_block Audio Block payload.
    @return     True for Scene Ambience content-kind blocks.
    @exception  None
    """
    return str(audio_block.get("content_kind", "")).strip() == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE


def _is_pause_block(audio_block: dict[str, object]) -> bool:
    """
    @brief      Return whether one Audio Block represents metadata-only pause silence.
    @param[in]  audio_block Audio Block payload.
    @return     True for pause content-kind blocks.
    @exception  None
    """
    return (
        bool(audio_block.get("metadata_only", False))
        and str(audio_block.get("content_kind", "")).strip() == speech_blocks_service.CONTENT_KIND_PAUSE
    )


def _pause_duration_ms(audio_block: dict[str, object]) -> int:
    """
    @brief      Resolve one metadata-only pause block duration.
    @param[in]  audio_block Audio Block payload.
    @return     Positive pause duration in milliseconds.
    @exception  None
    """
    value = audio_block.get("pause_duration_ms")
    try:
        duration_ms = int(value)
    except (TypeError, ValueError):
        return config.DEFAULT_SPEECH_BLOCK_PAUSE_DURATION_MS
    if duration_ms <= 0:
        return config.DEFAULT_SPEECH_BLOCK_PAUSE_DURATION_MS
    return duration_ms


def _enrich_block_duration(project_root: Path, block: dict[str, object]) -> dict[str, object]:
    """
    @brief      Add measured WAV or pause duration to one Audio Block payload copy.
    @param[in]  project_root Active project root folder.
    @param[in]  block Audio Block payload.
    @return     Audio Block payload copy with `duration_seconds`.
    @exception  wave.Error Raised when the source file is not a readable WAV.
    """
    enriched = dict(block)
    if _is_pause_block(enriched):
        enriched["duration_seconds"] = _pause_duration_ms(enriched) / 1000.0
        return enriched
    audio_path = _audio_path(project_root, block)
    enriched["duration_seconds"] = 0.0 if audio_path is None else _wav_duration_seconds(audio_path)
    return enriched


def _reference_wav_params(
    project_root: Path,
    blocks: list[dict[str, object]],
    fallback_relative_path: str,
) -> wave._wave_params:
    """
    @brief      Resolve the WAV params used to write an output containing pauses.
    @param[in]  project_root Active project root folder.
    @param[in]  blocks Output Audio Blocks.
    @param[in]  fallback_relative_path Project-relative WAV used when output only contains pauses.
    @return     Reference WAV params from a speech-preferred playable source block.
    @exception  RuntimeError Raised when no source WAV exists for the output.
    """
    preferred_blocks = [block for block in blocks if not _is_scene_ambience_block(block)]
    for candidate_blocks in (preferred_blocks, blocks):
        for block in candidate_blocks:
            source_path = _audio_path(project_root, block)
            if source_path is None:
                continue
            with wave.open(str(source_path), "rb") as source_wav:
                return source_wav.getparams()
    fallback_path = _safe_project_artifact_path(project_root, fallback_relative_path)
    if fallback_path is not None and fallback_path.is_file():
        with wave.open(str(fallback_path), "rb") as source_wav:
            return source_wav.getparams()
    raise RuntimeError("Audio Assembly cannot write an output file without at least one source WAV.")


def _wav_duration_seconds(path: Path) -> float:
    """
    @brief      Measure one WAV file duration in seconds.
    @param[in]  path Source WAV file path.
    @return     Duration in seconds.
    @exception  wave.Error Raised when the source file is not a readable WAV.
    """
    with wave.open(str(path), "rb") as wav_file:
        frame_rate = wav_file.getframerate()
        if frame_rate <= 0:
            return 0.0
        return wav_file.getnframes() / frame_rate


def _validate_compatible_wav_inputs(project_root: Path, audio_blocks: list[dict[str, object]]) -> None:
    """
    @brief      Validate that all playable Audio Blocks can be stitched together.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_blocks Playable Audio Block payloads.
    @return     None.
    @exception  ValueError Raised when a source is not a readable WAV.
    @exception  RuntimeError Raised when WAV parameters are unsupported or incompatible.
    """
    for block in audio_blocks:
        audio_path = _audio_path(project_root, block)
        assert audio_path is not None
        try:
            with wave.open(str(audio_path), "rb") as wav_file:
                params = wav_file.getparams()
                if params.sampwidth not in _WAV_SAMPLE_WIDTH_BY_FORMAT:
                    raise RuntimeError("Audio Assembly supports uncompressed PCM WAV source files only.")
        except (EOFError, OSError, wave.Error) as exc:
            raise ValueError("Every approved Audio Block must reference an existing readable WAV file.") from exc


def _build_input_fingerprint(
    project_root: Path,
    audio_blocks: list[dict[str, object]],
    settings: AudioAssemblySettings,
) -> str:
    """
    @brief      Build a stable fingerprint for current Audio Assembly inputs.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_blocks Approved Audio Block payloads.
    @param[in]  settings Normalized Audio Assembly settings.
    @return     SHA-1 fingerprint token used for resume validation.
    @exception  None
    """
    payload = {
        "settings": normalize_audio_assembly_settings(settings),
        "audio_blocks": [
            {
                "speech_block_id": str(block.get("speech_block_id", "")),
                "sequence_index": int(block.get("sequence_index", 0)),
                "chunk_id": str(block.get("chunk_id", "")),
                "content_kind": str(block.get("content_kind", "")),
                "pause_duration_ms": block.get("pause_duration_ms"),
                "audio_relative_path": block.get("audio_relative_path"),
                "file_sha1": _file_sha1(_audio_path(project_root, block)) if _audio_path(project_root, block) else None,
            }
            for block in audio_blocks
            if _is_included_scene_ambience_block(block, bool(settings["include_scene_ambience"]))
        ],
    }
    return hashlib.sha1(  # noqa: S324
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _file_sha1(path: Path | None) -> str | None:
    """
    @brief      Compute a SHA-1 digest for one local file.
    @param[in]  path Candidate file path.
    @return     Hex digest or `None` when the path is missing.
    @exception  None
    """
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha1()  # noqa: S324
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_output_record(payload: dict[str, object]) -> dict[str, object]:
    return {
        "output_key": str(payload.get("output_key", "")).strip(),
        "file_name": str(payload.get("file_name", "")).strip(),
        "audio_relative_path": str(payload.get("audio_relative_path", "")).strip(),
        "block_count": _bounded_int(payload.get("block_count", 0), 0, 1_000_000, 0),
        "chunk_ids": list(payload.get("chunk_ids", [])) if isinstance(payload.get("chunk_ids"), list) else [],
        "duration_seconds": float(payload.get("duration_seconds", 0.0) or 0.0),
        "generated": bool(payload.get("generated", False)),
        "output_format": str(payload.get("output_format", OUTPUT_FORMAT_WAV)).strip() or OUTPUT_FORMAT_WAV,
    }


def _bounded_int(value: object, minimum: int, maximum: int, fallback: int) -> int:
    """
    @brief      Convert one value to an integer clamped to a range.
    @param[in]  value Candidate integer value.
    @param[in]  minimum Minimum accepted value.
    @param[in]  maximum Maximum accepted value.
    @param[in]  fallback Fallback value for invalid input.
    @return     Bounded integer value.
    @exception  None
    """
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(resolved, maximum))


def _resolve_started_at(existing_state: dict[str, object]) -> str:
    """
    @brief      Resolve the runtime token for a resumed or fresh run.
    @param[in]  existing_state Existing operation-state payload.
    @return     Existing runtime token or the current UTC timestamp.
    @exception  None
    """
    resume_checkpoint = existing_state.get("resume_checkpoint", {}) if isinstance(existing_state, dict) else {}
    if not isinstance(resume_checkpoint, dict):
        resume_checkpoint = {}
    run_token = str(resume_checkpoint.get("run_token", "") or "").strip()
    return run_token or _utc_now_iso()


# END OF FILE
