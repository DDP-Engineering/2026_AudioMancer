#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audio_assembly_state_service.py
@brief Audio Assembly page state helpers for AudioMancer.
@details Builds operator-facing Audio Assembly state from project settings,
         approved Audio Blocks, resumable composition state, and generated
         audiobook output records, including on-demand Scene Ambience mix
         previews.
"""

# IMPORTS

from pathlib import Path

from audiomancer.services import audio_assembly_service, audio_blocks_service, speech_blocks_service, ui_state_service


def build_audio_assembly_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
) -> dict[str, object]:
    """
    @brief      Build Audio Assembly page state for the active project.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active manifest or `None`.
    @param[in]  language Runtime UI language code.
    @return     Page-state payload consumed by Audio Assembly page.
    @exception  None
    """
    if project_root is None or manifest is None:
        return _empty_state(language)
    settings = audio_assembly_service.normalize_audio_assembly_settings(manifest.get("audio_assembly_settings"))
    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    report = audio_assembly_service.load_audio_assembly_report(project_root)
    operation_state = audio_assembly_service.load_operation_state(project_root)
    outputs = audio_assembly_service.load_generated_outputs(project_root)
    scene_mix_groups = audio_assembly_service.list_scene_mix_groups(project_root, audio_blocks)
    include_scene_ambience = bool(settings["include_scene_ambience"])
    assembly_blocks = _filter_assembly_policy_blocks(audio_blocks, include_scene_ambience)
    total_blocks = len(assembly_blocks)
    approved_blocks = sum(1 for block in assembly_blocks if bool(block.get("approved", False)))
    generated_outputs = len(outputs)
    planned_outputs = int(report.get("planned_output_count", generated_outputs) if isinstance(report, dict) else 0)
    progress_current = generated_outputs if operation_state is None else int(operation_state.get("progress_current", 0))
    progress_total = planned_outputs if operation_state is None else int(operation_state.get("progress_total", 0))
    progress_percent = 0 if progress_total <= 0 else int((progress_current / max(progress_total, 1)) * 100)
    notes = _build_notes(total_blocks, approved_blocks, report, operation_state, language)
    total_duration = float(report.get("total_duration_seconds", 0.0)) if isinstance(report, dict) else 0.0
    status_lines = [
        ui_state_service.translate("audio_assembly.status_blocks", language).format(
            approved_blocks=approved_blocks,
            total_blocks=total_blocks,
        ),
        ui_state_service.translate("audio_assembly.status_outputs", language).format(
            generated_outputs=generated_outputs,
            planned_outputs=planned_outputs,
        ),
        ui_state_service.translate("audio_assembly.status_duration", language).format(
            duration=_format_duration(total_duration)
        ),
        ui_state_service.translate("audio_assembly.status_mode", language).format(
            mode=ui_state_service.translate(f"audio_assembly.mode.{settings['output_mode']}", language)
        ),
    ]
    return {
        "settings": settings,
        "outputs": outputs,
        "scene_mix_groups": scene_mix_groups,
        "current_output_key": outputs[0]["output_key"] if outputs else None,
        "current_scene_mix_key": scene_mix_groups[0]["group_key"] if scene_mix_groups else None,
        "notes": notes,
        "status_lines": status_lines,
        "progress_current": progress_current,
        "progress_total": progress_total,
        "progress_percent": progress_percent,
        "stage_status": _stage_status(report, operation_state),
        "can_generate": bool(audio_blocks) and total_blocks == approved_blocks,
        "can_reset": audio_assembly_service.has_persisted_audio_assembly(project_root),
        "can_play_selected": bool(outputs),
        "can_generate_scene_mix": any(bool(group.get("can_generate_preview", False)) for group in scene_mix_groups),
        "can_play_scene_mix": any(bool(group.get("can_play_preview", False)) for group in scene_mix_groups),
    }


def _empty_state(language: str) -> dict[str, object]:
    """
    @brief      Build Audio Assembly state for no active project.
    @param[in]  language Runtime UI language code.
    @return     Empty page-state payload.
    @exception  None
    """
    return {
        "settings": audio_assembly_service.default_audio_assembly_settings(),
        "outputs": [],
        "scene_mix_groups": [],
        "current_output_key": None,
        "current_scene_mix_key": None,
        "notes": [ui_state_service.translate("audio_assembly.note_no_project", language)],
        "status_lines": [],
        "progress_current": 0,
        "progress_total": 0,
        "progress_percent": 0,
        "stage_status": audio_assembly_service.AUDIO_ASSEMBLY_STAGE_NOT_STARTED,
        "can_generate": False,
        "can_reset": False,
        "can_play_selected": False,
        "can_generate_scene_mix": False,
        "can_play_scene_mix": False,
    }


def _build_notes(
    total_blocks: int,
    approved_blocks: int,
    report: dict[str, object] | None,
    operation_state: dict[str, object] | None,
    language: str,
) -> list[str]:
    """
    @brief      Build Audio Assembly notes from current readiness and report state.
    @param[in]  total_blocks Total Audio Blocks count.
    @param[in]  approved_blocks Approved Audio Blocks count.
    @param[in]  report Optional Audio Assembly report.
    @param[in]  operation_state Optional persisted operation state.
    @param[in]  language Runtime UI language code.
    @return     Operator-facing notes.
    @exception  None
    """
    if total_blocks <= 0:
        return [ui_state_service.translate("audio_assembly.note_missing_audio_blocks", language)]
    if approved_blocks < total_blocks:
        return [
            ui_state_service.translate("audio_assembly.note_missing_approvals", language).format(
                approved_blocks=approved_blocks,
                total_blocks=total_blocks,
            )
        ]
    status = _stage_status(report, operation_state)
    if status == "cancelled":
        return [ui_state_service.translate("audio_assembly.note_resume", language)]
    if status == audio_assembly_service.AUDIO_ASSEMBLY_STAGE_COMPLETED:
        return [ui_state_service.translate("audio_assembly.note_completed", language)]
    return [ui_state_service.translate("audio_assembly.note_ready", language)]


def _filter_assembly_policy_blocks(
    audio_blocks: list[dict[str, object]],
    include_scene_ambience: bool,
) -> list[dict[str, object]]:
    """
    @brief      Filter Audio Blocks by Audio Assembly Scene Ambience inclusion policy.
    @param[in]  audio_blocks Full Audio Blocks payload.
    @param[in]  include_scene_ambience True when Scene Ambience blocks count toward assembly.
    @return     Blocks relevant for current Audio Assembly readiness and status.
    @exception  None
    """
    if include_scene_ambience:
        return list(audio_blocks)
    return [
        block
        for block in audio_blocks
        if str(block.get("content_kind", "")).strip() != speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
    ]


def _stage_status(report: dict[str, object] | None, operation_state: dict[str, object] | None) -> str:
    """
    @brief      Resolve the effective Audio Assembly page-stage status.
    @param[in]  report Optional persisted Audio Assembly report.
    @param[in]  operation_state Optional persisted Audio Assembly state.
    @return     Stage status token.
    @exception  None
    """
    if isinstance(operation_state, dict) and str(operation_state.get("status", "")).strip() == "cancelled":
        return "cancelled"
    if isinstance(report, dict):
        return (
            str(report.get("audio_assembly_stage_status", "")).strip()
            or audio_assembly_service.AUDIO_ASSEMBLY_STAGE_NOT_STARTED
        )
    return audio_assembly_service.AUDIO_ASSEMBLY_STAGE_NOT_STARTED


def _format_duration(duration_seconds: float) -> str:
    """
    @brief      Format duration seconds for the Audio Assembly status panel.
    @param[in]  duration_seconds Duration in seconds.
    @return     `MM:SS` or `HH:MM:SS` duration text.
    @exception  None
    """
    total_seconds = max(int(duration_seconds), 0)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


# END OF FILE
