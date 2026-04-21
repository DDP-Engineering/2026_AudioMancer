#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file speech_blocks_state_service.py
@brief Speech Blocks page state helpers for AudioMancer.
@details Builds Speech Blocks page state from Character Voices language
         selection, resolved chunk sources, persisted Speech Blocks output,
         current operation state, and enabled AI profile settings.
@author Eng. Dan Dumitru Pasare
@date 2026-04-21
@version 0.1.0
"""

# IMPORTS

from pathlib import Path

from audiomancer.services import (
    home_presenter_service,
    speech_blocks_service,
    token_usage_service,
    ui_state_service,
)


def build_speech_blocks_profile_state(
    settings_payload: dict[str, object] | None,
    selected_profile_id: str | None = None,
) -> dict[str, object]:
    """
    @brief      Build the enabled AI-profile selector state for Speech Blocks.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  selected_profile_id Preferred profile identifier if available.
    @return     Selector entries plus one resolved selected profile id.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not isinstance(settings_payload, dict):
        return {"entries": [], "selected_profile_id": None}
    raw_profiles = settings_payload.get("llm_profiles", [])
    if not isinstance(raw_profiles, list):
        return {"entries": [], "selected_profile_id": None}
    entries: list[tuple[str, str | None]] = []
    enabled_ids: list[str] = []
    for profile in raw_profiles:
        if not isinstance(profile, dict) or not bool(profile.get("enabled", True)):
            continue
        profile_id = str(profile.get("id", "")).strip()
        if not profile_id:
            continue
        entries.append((str(profile.get("label", "")).strip() or profile_id, profile_id))
        enabled_ids.append(profile_id)
    default_profile_id = settings_payload.get("default_speech_blocks_profile_id")
    resolved_selected_id = (
        selected_profile_id
        if selected_profile_id in enabled_ids
        else (
            str(default_profile_id) if default_profile_id in enabled_ids else (enabled_ids[0] if enabled_ids else None)
        )
    )
    return {"entries": entries, "selected_profile_id": resolved_selected_id}


def build_speech_blocks_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
    settings_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    """
    @brief      Build the Speech Blocks page state from project artifacts.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  language Runtime UI language code.
    @param[in]  settings_payload Persisted application settings payload.
    @return     Page-state payload consumed by the Speech Blocks page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if project_root is None or manifest is None:
        return {
            "source_chunks": [],
            "speech_blocks": [],
            "notes": [ui_state_service.translate("speech_blocks.note_no_project", language)],
            "selected_profile_id": None,
            "stage_status": speech_blocks_service.SPEECH_BLOCKS_STAGE_NOT_STARTED,
            "selected_source_language": "",
            "processed_chunk_count": 0,
            "total_chunk_count": 0,
        }

    report = speech_blocks_service.load_speech_blocks_report(project_root)
    operation_state = speech_blocks_service.load_operation_state(project_root)
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    selected_profile_id = _persisted_profile_id(report, operation_state)
    profile_state = build_speech_blocks_profile_state(settings_payload, selected_profile_id)

    try:
        source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)
        source_chunks = list(source_resolution["source_chunks"])
        selected_source_language = str(source_resolution["selected_source_language"])
    except ValueError:
        source_resolution = None
        source_chunks = []
        selected_source_language = _persisted_source_language(report, operation_state)

    return {
        "source_chunks": source_chunks,
        "speech_blocks": speech_blocks,
        "notes": build_speech_blocks_notes(
            manifest,
            source_chunks,
            report,
            operation_state,
            bool(profile_state["entries"]),
            language,
        ),
        "selected_profile_id": selected_profile_id or profile_state["selected_profile_id"],
        "stage_status": _speech_blocks_stage_status(report, operation_state),
        "selected_source_language": selected_source_language,
        "processed_chunk_count": 0 if report is None else int(report.get("processed_chunk_count", 0)),
        "total_chunk_count": len(source_chunks),
    }


def build_speech_blocks_notes(
    manifest: dict[str, object],
    source_chunks: list[dict[str, object]],
    report: dict[str, object] | None,
    operation_state: dict[str, object] | None,
    has_ai_profiles: bool,
    language: str,
) -> list[str]:
    """
    @brief      Build operator-facing Speech Blocks notes for the active project.
    @param[in]  manifest Active project manifest payload.
    @param[in]  source_chunks Resolved source chunk payloads.
    @param[in]  report Persisted Speech Blocks report or `None`.
    @param[in]  operation_state Persisted Speech Blocks operation state or `None`.
    @param[in]  has_ai_profiles True when at least one enabled AI profile exists.
    @param[in]  language Runtime UI language code.
    @return     Ordered Speech Blocks notes for the page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if home_presenter_service.source_document_name(manifest) is None:
        return [ui_state_service.translate("speech_blocks.note_no_source", language)]
    if not source_chunks:
        return [ui_state_service.translate("speech_blocks.note_missing_source", language)]

    stage_status = _speech_blocks_stage_status(report, operation_state)
    processed_chunk_count = 0 if report is None else int(report.get("processed_chunk_count", 0))
    speech_block_count = 0 if report is None else int(report.get("speech_block_count", 0))
    notes = [
        ui_state_service.translate("speech_blocks.note_summary", language).format(
            block_count=speech_block_count,
            processed_chunk_count=processed_chunk_count,
            total_chunk_count=len(source_chunks),
        )
    ]
    notes.extend(_build_token_usage_notes(report, operation_state, language))
    warning_count = 0 if report is None else int(report.get("warning_count", 0))
    if warning_count > 0:
        notes.append(
            ui_state_service.translate("speech_blocks.note_warning_summary", language).format(
                warning_count=warning_count
            )
        )
        for warning_entry in list(report.get("warnings", [])):
            if not isinstance(warning_entry, dict):
                continue
            notes.append(
                ui_state_service.translate("speech_blocks.note_warning_entry", language).format(
                    chunk_id=str(warning_entry.get("chunk_id", "")),
                    reason=str(warning_entry.get("reason", "")),
                )
            )
    if not has_ai_profiles:
        notes.append(ui_state_service.translate("speech_blocks.note_no_profile", language))
        return notes
    if stage_status == "running":
        notes.append(
            ui_state_service.translate("speech_blocks.note_in_progress", language).format(
                progress_current=0 if operation_state is None else int(operation_state.get("progress_current", 0)),
                progress_total=len(source_chunks)
                if operation_state is None
                else int(operation_state.get("progress_total", len(source_chunks))),
            )
        )
    elif stage_status == "failed":
        notes.append(
            ui_state_service.translate("speech_blocks.note_resume", language).format(
                progress_current=0 if operation_state is None else int(operation_state.get("progress_current", 0)),
                progress_total=len(source_chunks)
                if operation_state is None
                else int(operation_state.get("progress_total", len(source_chunks))),
            )
        )
    elif (
        report is not None
        and str(report.get("speech_blocks_stage_status", "")) == speech_blocks_service.SPEECH_BLOCKS_STAGE_COMPLETED
    ):
        notes.append(ui_state_service.translate("speech_blocks.note_rerun_warning", language))
    else:
        notes.append(ui_state_service.translate("speech_blocks.note_ready", language))
    return notes


def _build_token_usage_notes(
    report: dict[str, object] | None,
    operation_state: dict[str, object] | None,
    language: str,
) -> list[str]:
    """
    @brief      Build the token usage notes for Speech Blocks.
    @param[in]  report Persisted Speech Blocks report or `None`.
    @param[in]  operation_state Persisted Speech Blocks operation state or `None`.
    @param[in]  language Runtime UI language code.
    @return     Ordered token-usage notes.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    metadata = {} if not isinstance(operation_state, dict) else operation_state.get("metadata", {})
    token_usage = token_usage_service.restore_token_usage(
        None if not isinstance(report, dict) else report.get("token_usage"),
        metadata.get("token_usage") if isinstance(metadata, dict) else None,
    )
    if bool(token_usage.get("usage_available", False)):
        return [
            ui_state_service.translate("ai.note_token_usage_summary", language).format(
                input_tokens=format(int(token_usage["input_tokens"]), ","),
                output_tokens=format(int(token_usage["output_tokens"]), ","),
                total_tokens=format(int(token_usage["total_tokens"]), ","),
            )
        ]
    if (isinstance(report, dict) and "token_usage" in report) or (
        isinstance(metadata, dict) and "token_usage" in metadata
    ):
        return [ui_state_service.translate("ai.note_token_usage_unavailable", language)]
    return []


def _speech_blocks_stage_status(report: dict[str, object] | None, operation_state: dict[str, object] | None) -> str:
    """
    @brief      Resolve the effective Speech Blocks stage from report and runtime state.
    @param[in]  report Persisted Speech Blocks report or `None`.
    @param[in]  operation_state Persisted Speech Blocks operation state or `None`.
    @return     Effective Speech Blocks stage token.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if isinstance(operation_state, dict):
        operation_status = str(operation_state.get("status", "")).strip()
        if operation_status in {"running", "failed"}:
            return operation_status
    if isinstance(report, dict):
        return str(
            report.get(
                "speech_blocks_stage_status",
                speech_blocks_service.SPEECH_BLOCKS_STAGE_NOT_STARTED,
            )
        )
    return speech_blocks_service.SPEECH_BLOCKS_STAGE_NOT_STARTED


def _persisted_profile_id(report: dict[str, object] | None, operation_state: dict[str, object] | None) -> str | None:
    """
    @brief      Resolve the persisted Speech Blocks profile identifier if available.
    @param[in]  report Persisted Speech Blocks report or `None`.
    @param[in]  operation_state Persisted Speech Blocks operation state or `None`.
    @return     Persisted profile identifier or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if isinstance(report, dict):
        profile_id = report.get("ai_profile_id")
        if profile_id not in (None, ""):
            return str(profile_id)
    if isinstance(operation_state, dict):
        metadata = operation_state.get("metadata", {})
        if isinstance(metadata, dict):
            profile_id = metadata.get("ai_profile_id")
            if profile_id not in (None, ""):
                return str(profile_id)
    return None


def _persisted_source_language(report: dict[str, object] | None, operation_state: dict[str, object] | None) -> str:
    """
    @brief      Resolve the persisted Speech Blocks source language when available.
    @param[in]  report Persisted Speech Blocks report or `None`.
    @param[in]  operation_state Persisted Speech Blocks operation state or `None`.
    @return     Persisted source language code or one empty string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if isinstance(report, dict):
        source_language = str(report.get("source_language", "")).strip()
        if source_language:
            return source_language
    if isinstance(operation_state, dict):
        metadata = operation_state.get("metadata", {})
        if isinstance(metadata, dict):
            source_language = str(metadata.get("source_language", "")).strip()
            if source_language:
                return source_language
    return ""


# END OF FILE
