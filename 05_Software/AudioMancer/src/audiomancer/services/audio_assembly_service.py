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

from collections.abc import Callable
from contextlib import suppress
from functools import lru_cache, partial
import hashlib
import json
from pathlib import Path
import wave

from audiomancer import config
from audiomancer.services import (
    audio_assembly_plan,
    audio_assembly_wav,
    audio_blocks_artifact_service,
    audio_blocks_service,
    operation_runtime_service,
    project_workspace_service,
    speech_blocks_service,
)
from audiomancer.services.audio_assembly_plan import (
    OUTPUT_MODE_PER_CHUNK as OUTPUT_MODE_PER_CHUNK,
)
from audiomancer.services.audio_assembly_plan import (
    OUTPUT_MODE_TIME_LIMIT as OUTPUT_MODE_TIME_LIMIT,
)
from audiomancer.services.audio_assembly_plan import (
    OUTPUT_MODE_WHOLE_BOOK as OUTPUT_MODE_WHOLE_BOOK,
)
from audiomancer.services.audio_assembly_plan import (
    AudioAssemblySettings,
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

OUTPUT_FORMAT_WAV = "wav"

_MODE = "audio_composition"
_SCENE_MIX_PREVIEW_FOLDER_NAME = "scene_mix_previews"
_SCENE_MIX_KEY_PREFIX = "scene_mix"
# The stat identity in `_cached_file_sha1` invalidates changed sources. The
# finite `lru_cache` retains only digest strings and supplies synchronized cache
# access for refreshes from UI or worker threads; source audio bytes are never
# retained. Keep the bound explicit so tests can prove and clear the cache.
_FILE_SHA1_CACHE_MAXSIZE = 256
_RIFF_UINT32_MAX = (1 << 32) - 1
_WAV_RIFF_DATA_OVERHEAD_BYTES = 36
_WAV_MAX_DATA_BYTES = _RIFF_UINT32_MAX - _WAV_RIFF_DATA_OVERHEAD_BYTES
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
def list_scene_mix_groups(
    project_root: str | Path,
    audio_blocks: list[dict[str, object]] | None = None,
) -> list[SceneMixGroup]:
    """
    @brief      Build current Scene Ambience mix-preview groups.
    @details    Callers that already hold the loaded Audio Blocks pass them in
                so one page refresh reads the document once; omitting them
                loads the document here, as every existing caller expects.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_blocks Already-loaded Audio Blocks payloads, or `None` to load them.
    @return     Ordered Scene Ambience group records.
    @exception  None
    """
    resolved_project_root = Path(project_root).resolve()
    loaded_blocks = (
        audio_blocks_service.load_audio_blocks(resolved_project_root) if audio_blocks is None else audio_blocks
    )
    return _scene_mix_groups_from_blocks(
        resolved_project_root,
        speech_blocks_service.sort_speech_blocks(loaded_blocks),
        include_blocks=False,
    )


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
    resolved_project_root = Path(project_root).resolve()
    _emit_progress(progress_callback, 0, 3, "Preparing Scene Mix preview.")
    groups = _scene_mix_groups_from_blocks(
        resolved_project_root,
        speech_blocks_service.sort_speech_blocks(audio_blocks_service.load_audio_blocks(resolved_project_root)),
        include_blocks=True,
    )
    target_group = next((group for group in groups if str(group.get("group_key", "")) == str(group_key).strip()), None)
    if target_group is None:
        raise ValueError("The selected Scene Ambience mix is no longer available.")
    sources = target_group["_source_blocks"]
    if not sources or any(
        not audio_blocks_service.is_approved(block) or not _requires_source_wav(block, True) for block in sources
    ):
        raise ValueError("Generate and approve every source Scene Ambience Audio Block before previewing the mix.")
    _validate_compatible_wav_inputs(resolved_project_root, sources)
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
    resolved_project_root = Path(project_root).resolve()
    speech_blocks_service.validate_current_translated_speech_source(resolved_project_root, manifest)
    settings = normalize_audio_assembly_settings(manifest.get("audio_assembly_settings"))
    approved_blocks = _load_approved_audio_blocks(
        resolved_project_root,
        include_scene_ambience=bool(settings["include_scene_ambience"]),
    )
    input_fingerprint = _build_input_fingerprint(resolved_project_root, approved_blocks, settings)
    existing_state = load_operation_state(resolved_project_root) or {}
    existing_report = load_audio_assembly_report(resolved_project_root) or {}
    if _requires_manual_reset(existing_state, input_fingerprint):
        raise ValueError("Audio Assembly inputs or settings changed. Reset Audio Assembly before continuing.")

    output_plan = _build_output_plan(resolved_project_root, approved_blocks, settings)
    completed_records = _completed_records_for_resume(
        resolved_project_root, existing_state, existing_report, input_fingerprint, output_plan,
    )
    planned_output_keys = {str(output.get("output_key", "")) for output in output_plan}
    completed_by_key = {output["output_key"]: output for output in completed_records}
    was_already_completed = (
        str(existing_state.get("status", "")).strip() == "completed"
        and bool(planned_output_keys)
        and planned_output_keys.issubset(completed_by_key)
    )
    existing_completed_at = str(existing_report.get("completed_at", "") or "").strip()
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
            if output_item["output_key"] in completed_by_key:
                continue
            raise_if_cancelled(cancel_requested)
            output_record = _compose_output_file(resolved_project_root, output_item, settings, cancel_requested)
            completed_by_key[output_item["output_key"]] = output_record
            completed_records = [
                completed_by_key[item["output_key"]] for item in output_plan if item["output_key"] in completed_by_key
            ]
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

    completed_at = existing_completed_at if was_already_completed and existing_completed_at else _utc_now_iso()
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
    recorded_ids = {block["speech_block_id"] for block in candidate_blocks}
    for speech_block in speech_blocks_service.load_speech_blocks(project_root):
        required = _is_required_speech(speech_block) or (
            speech_block["content_kind"] == speech_blocks_service.CONTENT_KIND_PAUSE
        )
        if required and speech_block["speech_block_id"] not in recorded_ids:
            raise ValueError(f"Generate and approve Audio Block {speech_block['speech_block_id']} before assembly.")
    composition_sources = [
        block
        for block in candidate_blocks
        if _requires_source_wav(block, include_scene_ambience)
    ]
    if not composition_sources:
        raise ValueError("Audio Assembly requires at least one generated speech audio block.")
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
        dict(block) if _is_scene_ambience_block(block) else _enrich_block_duration(project_root, block)
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
        sources = [block for block in blocks if _requires_source_wav(block, include_scene_ambience=True)]
        group = _scene_mix_group_record(project_root, sources or blocks, include_blocks=include_blocks)
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
    valid_preview = _valid_scene_mix(project_root, output_path, first_block, duration_seconds)
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
        "audio_relative_path": output_path.relative_to(project_root).as_posix(),
        "can_generate_preview": bool(ordered_blocks) and is_approved and has_source_audio,
        "can_play_preview": valid_preview,
        "generated": valid_preview,
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
    @brief      Resolve source durations and build the ordered output plan.
    @param[in]  project_root Active project root.
    @param[in]  audio_blocks Approved Audio Blocks.
    @param[in]  settings Normalized Audio Assembly settings.
    @return     Planned WAV files.
    """
    blocks = _build_composition_blocks(project_root, audio_blocks, bool(settings["include_scene_ambience"]))
    return audio_assembly_plan.build_output_plan(blocks, settings)


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
        reference_params = _reference_wav_params(
            project_root,
            blocks,
            str(output_item.get("reference_audio_relative_path", "")),
            path_resolver=_planned_block_reference_path,
        )
        planned_frames = _planned_output_frame_count(project_root, blocks, settings, reference_params)
        _validate_classic_wav_data_size(
            str(output_item.get("file_name", "output.wav")),
            planned_frames,
            reference_params,
        )


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
            planned_frames += audio_assembly_wav.silence_frame_count(
                output_rate,
                audio_assembly_plan.automatic_gap_ms(previous_block, block, settings),
            )
        if audio_assembly_plan.is_pause_block(block):
            pause_ms = audio_assembly_plan.pause_duration_ms(block)
            planned_frames += audio_assembly_wav.silence_frame_count(output_rate, pause_ms)
        else:
            planned_frames += _planned_block_output_frame_count(project_root, block, reference_params)
        previous_block = block
    return planned_frames


def _planned_block_output_frame_count(
    project_root: Path,
    block: dict[str, object],
    reference_params: wave._wave_params,
) -> int:
    """
    @brief      Size one source and verify that its channels can reach the output layout.
    @param[in]  project_root Active project root folder.
    @param[in]  block Planned direct or virtual composition block.
    @param[in]  reference_params Planned output WAV parameters.
    @return     Conservative output frame count for the block.
    @exception  RuntimeError Raised when a source or channel conversion is unavailable.
    """
    source_blocks = block.get("scene_mix_source_blocks")
    source_block = source_blocks[0] if source_blocks else block
    source_path = _audio_path(project_root, source_block)
    block_id = source_block.get("speech_block_id", "")
    if source_path is None:
        raise RuntimeError(f"Audio Assembly cannot size Block {block_id} without a WAV file.")
    with wave.open(str(source_path), "rb") as source_wav:
        params = source_wav.getparams()
        if not audio_assembly_wav.can_convert_channels(params.nchannels, reference_params.nchannels):
            raise RuntimeError(
                f"Audio Assembly supports WAV channel conversion only between mono and stereo. Block {block_id}."
            )
        frames = params.nframes
        if source_blocks:
            frames = audio_assembly_wav.scene_mix_target_frames(
                [source_wav], params.framerate, float(block.get("duration_seconds", 0.0) or 0.0),
            )
    return _conservative_resampled_frame_count(frames, params.framerate, reference_params.framerate)


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
    output_path = output_root / str(output_item["file_name"])
    blocks = [dict(block) for block in output_item.get("blocks", []) if isinstance(block, dict)]
    blocks = [_materialize_scene_mix_block(project_root, block, cancel_requested) for block in blocks]
    reference_params = _reference_wav_params(
        project_root,
        blocks,
        str(output_item.get("reference_audio_relative_path", "")),
    )
    total_frames = 0

    def render(temp_path: Path) -> None:
        """@brief Write the final PCM stream to the unpublished candidate."""
        nonlocal total_frames
        with wave.open(str(temp_path), "wb") as output_wav:
            output_wav.setparams(reference_params)
            previous_block = None
            for block_index, block in enumerate(blocks):
                raise_if_cancelled(cancel_requested)
                source_path = _audio_path(project_root, block)
                if source_path is None and not audio_assembly_plan.is_pause_block(block):
                    raise ValueError(f"Audio Assembly cannot open the WAV for Block {block['speech_block_id']}.")
                if block_index > 0 and previous_block is not None:
                    gap_ms = audio_assembly_plan.automatic_gap_ms(previous_block, block, settings)
                    silence_frames = audio_assembly_wav.append_silence(
                        output_wav, gap_ms, reference_params, cancel_requested,
                    )
                    total_frames += silence_frames
                if audio_assembly_plan.is_pause_block(block):
                    pause_frames = audio_assembly_wav.append_silence(
                        output_wav, audio_assembly_plan.pause_duration_ms(block), reference_params, cancel_requested,
                    )
                    total_frames += pause_frames
                    previous_block = block
                    continue
                assert source_path is not None
                with wave.open(str(source_path), "rb") as source_wav:
                    params = source_wav.getparams()
                    if params.sampwidth not in audio_assembly_wav.SUPPORTED_SAMPLE_WIDTHS:
                        raise RuntimeError("Audio Assembly supports uncompressed PCM WAV source files only.")
                    total_frames += audio_assembly_wav.copy_or_convert_wav_frames(
                        source_wav,
                        output_wav,
                        reference_params,
                        cancel_requested,
                    )
                    previous_block = block

    audio_assembly_wav.publish_wav(project_root, output_path, render, cancel_requested)
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
    output_path = project_root / str(block["audio_relative_path"])
    if not _valid_scene_mix(project_root, output_path, source_blocks[0], float(block["duration_seconds"])):
        group = _scene_mix_group_record(project_root, source_blocks, include_blocks=True)
        output_path = _write_scene_mix_group(project_root, group, cancel_requested=cancel_requested)
    materialized_block = dict(block)
    materialized_block["audio_relative_path"] = relative_to_project(project_root, output_path)
    materialized_block["duration_seconds"] = _wav_duration_seconds(output_path)
    materialized_block["audio_duration_seconds"] = materialized_block["duration_seconds"]
    return materialized_block


def _valid_scene_mix(
    project_root: Path,
    output_path: Path,
    first_source: dict[str, object],
    duration_seconds: float,
) -> bool:
    """
    @brief      Check a cached mix against the group's expected PCM layout and length.
    @param[in]  project_root Active project root.
    @param[in]  output_path Deterministic Scene Mix WAV path.
    @param[in]  first_source Source block that defines the mix layout.
    @param[in]  duration_seconds Planned group length.
    @return     True when the cached mix is complete and matches the plan.
    """
    params = _completed_wav_params(output_path)
    if params is None or params.nframes != max(1, round(duration_seconds * params.framerate)):
        return False
    source_path = _audio_path(project_root, first_source)
    if source_path is None:
        return False
    try:
        with wave.open(str(source_path), "rb") as source:
            return source.getparams()[:3] == params[:3]
    except (EOFError, OSError, wave.Error):
        return False


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
    output_path = project_root / str(group["audio_relative_path"])

    def render(temp_path: Path) -> None:
        """@brief Render the preview or final Scene Mix before publication."""
        audio_assembly_wav.mix_wav_sources(
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

    audio_assembly_wav.publish_wav(project_root, output_path, render, cancel_requested)
    return output_path


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
            with suppress(EOFError, OSError, wave.Error):
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
        "started_at": started_at,
        "completed_at": completed_at,
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
        resume_checkpoint={"run_token": str(report["started_at"])},
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
    report: AudioAssemblyReport,
    input_fingerprint: str,
    output_plan: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Return valid completed outputs in canonical plan order.
    @param[in]  project_root Active project root folder.
    @param[in]  existing_state Persisted operation state.
    @param[in]  report Persisted output report.
    @param[in]  input_fingerprint Current input fingerprint.
    @param[in]  output_plan Canonical planned output records.
    @return     Reusable completed output records.
    @exception  None
    """
    metadata = existing_state.get("metadata", {})
    if (
        not isinstance(metadata, dict)
        or metadata.get("input_fingerprint") != input_fingerprint
        or report.get("input_fingerprint") != input_fingerprint
    ):
        return []
    outputs = report.get("outputs", [])
    if not isinstance(outputs, list):
        return []
    by_key = {
        str(output.get("output_key", "")): output
        for output in outputs
        if isinstance(output, dict) and output.get("generated") is True
    }
    records = []
    for item in output_plan:
        output = by_key.get(str(item["output_key"]))
        if output is None:
            continue
        expected_path = project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME / str(item["file_name"])
        actual_path = _safe_project_artifact_path(project_root, output.get("audio_relative_path"))
        if actual_path != expected_path or output.get("file_name") != item["file_name"]:
            continue
        params = _completed_wav_params(expected_path)
        if params is None:
            continue
        try:
            record = _normalize_output_record(output)
        except (TypeError, ValueError):
            continue
        if record["duration_seconds"] == params.nframes / params.framerate:
            records.append(record)
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


def _requires_source_wav(block: dict[str, object], include_scene_ambience: bool) -> bool:
    """
    @brief      Require speech WAVs and included ambience known to have been synthesized.
    @param[in]  block Approved Audio Block.
    @param[in]  include_scene_ambience Whether scene sounds belong to the output.
    @return     True when the absence of a WAV would omit audio.
    """
    if _is_scene_ambience_block(block):
        return include_scene_ambience and bool(
            block.get("audio_relative_path")
            or (audio_blocks_service.is_generated(block) and block.get("generation_fingerprint"))
        )
    return _is_required_speech(block)


def _is_assembly_block(audio_block: dict[str, object], include_scene_ambience: bool) -> bool:
    """
    @brief      Return whether one Audio Block contributes to final composition.
    @param[in]  audio_block Audio Block payload.
    @param[in]  include_scene_ambience True when Scene Ambience contributes.
    @return     True for generated audio blocks and metadata-only pause blocks.
    @exception  None
    """
    if _is_scene_ambience_block(audio_block):
        return include_scene_ambience and bool(audio_block.get("audio_relative_path"))
    return _is_required_speech(audio_block) or audio_assembly_plan.is_pause_block(audio_block)


def _is_required_speech(block: dict[str, object]) -> bool:
    """
    @brief      Identify spoken blocks that require an approved WAV.
    @param[in]  block Speech Block or enriched Audio Block.
    @return     True for narration or dialogue.
    """
    return block.get("content_kind") in {
        speech_blocks_service.CONTENT_KIND_NARRATION, speech_blocks_service.CONTENT_KIND_DIALOGUE,
    }


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


def _enrich_block_duration(project_root: Path, block: dict[str, object]) -> dict[str, object]:
    """
    @brief      Add measured WAV or pause duration to one Audio Block payload copy.
    @param[in]  project_root Active project root folder.
    @param[in]  block Audio Block payload.
    @return     Audio Block payload copy with `duration_seconds`.
    @exception  wave.Error Raised when the source file is not a readable WAV.
    """
    enriched = dict(block)
    if audio_assembly_plan.is_pause_block(enriched):
        enriched["duration_seconds"] = audio_assembly_plan.pause_duration_ms(enriched) / 1000.0
        return enriched
    audio_path = _audio_path(project_root, block)
    enriched["duration_seconds"] = 0.0 if audio_path is None else _wav_duration_seconds(audio_path)
    return enriched


def _reference_wav_params(
    project_root: Path,
    blocks: list[dict[str, object]],
    fallback_relative_path: str,
    *,
    path_resolver: Callable[[Path, dict[str, object]], Path | None] | None = None,
) -> wave._wave_params:
    """
    @brief      Resolve the WAV params used to write an output containing pauses.
    @param[in]  project_root Active project root folder.
    @param[in]  blocks Output Audio Blocks.
    @param[in]  fallback_relative_path Project-relative WAV used when output only contains pauses.
    @param[in]  path_resolver Optional block-to-path resolver selected by the caller.
    @return     Reference WAV params from a speech-preferred playable source block.
    @exception  RuntimeError Raised when no source WAV exists for the output.
    """
    resolve_path = _audio_path if path_resolver is None else path_resolver
    preferred_blocks = [block for block in blocks if not _is_scene_ambience_block(block)]
    for candidate_blocks in (preferred_blocks, blocks):
        for block in candidate_blocks:
            source_path = resolve_path(project_root, block)
            if source_path is None:
                continue
            with wave.open(str(source_path), "rb") as source_wav:
                return source_wav.getparams()
    fallback_path = _safe_project_artifact_path(project_root, fallback_relative_path)
    if fallback_path is not None and fallback_path.is_file():
        with wave.open(str(fallback_path), "rb") as source_wav:
            return source_wav.getparams()
    raise RuntimeError("Audio Assembly cannot write an output file without at least one source WAV.")


def _completed_wav_params(path: Path) -> wave._wave_params | None:
    """
    @brief      Return supported complete PCM parameters for a canonical published WAV.
    @param[in]  path Planned local WAV path.
    @return     Verified WAV parameters or None when the file cannot be reused.
    """
    try:
        if path.resolve() != path or not path.is_file():
            return None
        with wave.open(str(path), "rb") as wav:
            params = wav.getparams()
            if (
                params.sampwidth in audio_assembly_wav.SUPPORTED_SAMPLE_WIDTHS
                and audio_blocks_artifact_service.has_complete_frames(wav)
            ):
                return params
    except (EOFError, OSError, RuntimeError, wave.Error):
        return None
    return None


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
    scene_formats: dict[str, tuple[int, int, int]] = {}
    for block in audio_blocks:
        audio_path = _audio_path(project_root, block)
        block_id = str(block.get("speech_block_id", ""))
        error_message = f"Every approved Audio Block must reference an existing readable WAV file. Block {block_id}."
        if audio_path is None or not audio_path.is_file():
            raise ValueError(error_message)
        try:
            with wave.open(str(audio_path), "rb") as wav_file:
                params = wav_file.getparams()
                if params.sampwidth not in audio_assembly_wav.SUPPORTED_SAMPLE_WIDTHS:
                    raise RuntimeError(
                        f"Audio Assembly supports uncompressed PCM WAV source files only. Block {block_id}."
                    )
                if not audio_blocks_artifact_service.has_complete_frames(wav_file):
                    raise ValueError(error_message)
                if _is_scene_ambience_block(block):
                    layout = (params.nchannels, params.sampwidth, params.framerate)
                    first_layout = scene_formats.setdefault(_scene_mix_group_key(block), layout)
                    if layout != first_layout:
                        raise ValueError(f"Scene Mix sources must use the same PCM format. Block {block_id}.")
        except (EOFError, OSError, wave.Error) as exc:
            raise ValueError(error_message) from exc


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
                **({
                    "ambience_group": _scene_mix_group_key(block),
                    "ambience_duration_seconds": block.get("duration_seconds"),
                } if _is_scene_ambience_block(block) else {}),
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
    resolved_path = path.resolve()
    file_stat = resolved_path.stat()
    return _cached_file_sha1(
        str(resolved_path),
        file_stat.st_mtime_ns,
        file_stat.st_size,
    )


@lru_cache(maxsize=_FILE_SHA1_CACHE_MAXSIZE)
def _cached_file_sha1(resolved_path: str, modified_time_ns: int, file_size: int) -> str:
    """
    @brief      Reuse one content digest for an unchanged resolved file identity.
    @details    The resolved path, nanosecond modification time, and byte size
                form the cache key. The finite `lru_cache` synchronizes cache
                access, and exceptions from the byte reader are not cached.
    @param[in]  resolved_path Canonical local source path.
    @param[in]  modified_time_ns Source modification time in nanoseconds.
    @param[in]  file_size Source size in bytes.
    @return     SHA-1 hex digest.
    @exception  OSError Raised when the source cannot be read.
    """
    _ = (modified_time_ns, file_size)
    return _hash_file_contents(Path(resolved_path))


def _hash_file_contents(path: Path) -> str:
    """
    @brief      Compute a SHA-1 digest from one complete local file read.
    @param[in]  path Existing resolved source path.
    @return     SHA-1 hex digest.
    @exception  OSError Raised when the source cannot be read.
    """
    digest = hashlib.sha1()  # noqa: S324
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clear_file_sha1_cache() -> None:
    """
    @brief      Clear cached file digests for deterministic test isolation.
    @return     None.
    @exception  None
    """
    _cached_file_sha1.cache_clear()


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
