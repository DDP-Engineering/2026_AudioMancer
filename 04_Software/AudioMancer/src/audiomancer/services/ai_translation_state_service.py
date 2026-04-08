#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_translation_state_service.py
@brief Translation page state helpers for AudioMancer.
@details Builds AI Translation page state from chunking artifacts, translated
         chunk records, translation reports, and current operation state.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.2.0
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import ai_translation_service
from audiomancer.services import deterministic_chunking_service
from audiomancer.services import home_presenter_service
from audiomancer.services import ui_state_service


# PUBLIC API


def build_ai_translation_profile_state(
    settings_payload: dict[str, object] | None,
    selected_profile_id: str | None = None,
) -> dict[str, object]:
    """
    @brief      Build the enabled AI-profile selector state for translation.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  selected_profile_id Preferred profile identifier if available.
    @return     Selector entries plus resolved selected profile id.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.1
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
    default_profile_id = None
    if isinstance(settings_payload, dict):
        candidate_default_profile_id = settings_payload.get(
            "default_ai_translation_profile_id"
        )
        if candidate_default_profile_id in enabled_ids:
            default_profile_id = str(candidate_default_profile_id)
    resolved_selected_id = (
        selected_profile_id
        if selected_profile_id in enabled_ids
        else (default_profile_id if default_profile_id is not None else (enabled_ids[0] if enabled_ids else None))
    )
    return {"entries": entries, "selected_profile_id": resolved_selected_id}


def build_ai_translation_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
    settings_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    """
    @brief      Build the full AI Translation page state from project artifacts.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  language Runtime UI language code.
    @param[in]  settings_payload Persisted application settings payload.
    @return     Page-state payload consumed by the translation page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if project_root is None or manifest is None:
        return {
            "source_chunks": [],
            "translated_chunks": [],
            "notes": [ui_state_service.translate("ai_translation.note_no_project", language)],
            "target_language": config.DEFAULT_TRANSLATION_TARGET_LANGUAGE,
            "selected_profile_id": None,
            "stage_status": ai_translation_service.TRANSLATION_STAGE_NOT_STARTED,
            "translated_count": 0,
            "approved_count": 0,
            "total_count": 0,
        }
    source_chunks = deterministic_chunking_service.load_chunks(project_root)
    report = ai_translation_service.load_translation_report(project_root)
    operation_state = ai_translation_service.load_operation_state(project_root)
    translated_chunks = ai_translation_service.load_translated_chunks(project_root)
    persisted_target_language = _persisted_target_language(report, operation_state)
    persisted_profile_id = _persisted_profile_id(report, operation_state)
    profile_state = build_ai_translation_profile_state(settings_payload, persisted_profile_id)
    if source_chunks:
        source_chunks, translated_chunks, report = ai_translation_service.ensure_translation_records(
            project_root,
            persisted_target_language,
            persisted_profile_id,
        )
        operation_state = ai_translation_service.load_operation_state(project_root)
    translated_count = 0 if report is None else int(report.get("translated_chunk_count", 0))
    approved_count = 0 if report is None else int(report.get("approved_chunk_count", 0))
    total_count = len(source_chunks)
    stage_status = _translation_stage_status(report, operation_state)
    return {
        "source_chunks": source_chunks,
        "translated_chunks": translated_chunks,
        "notes": build_ai_translation_notes(
            manifest,
            source_chunks,
            report,
            operation_state,
            bool(profile_state["entries"]),
            language,
        ),
        "target_language": persisted_target_language,
        "selected_profile_id": persisted_profile_id or profile_state["selected_profile_id"],
        "stage_status": stage_status,
        "translated_count": translated_count,
        "approved_count": approved_count,
        "total_count": total_count,
    }


def build_ai_translation_notes(
    manifest: dict[str, object],
    source_chunks: list[dict[str, object]],
    report: dict[str, object] | None,
    operation_state: dict[str, object] | None,
    has_ai_profiles: bool,
    language: str,
) -> list[str]:
    """
    @brief      Build operator-facing translation notes for the active project.
    @param[in]  manifest Active project manifest payload.
    @param[in]  source_chunks Canonical source chunks from chunking.
    @param[in]  report Persisted translation report or `None`.
    @param[in]  operation_state Persisted translation operation state or `None`.
    @param[in]  has_ai_profiles True when at least one enabled profile exists.
    @param[in]  language Runtime UI language code.
    @return     Ordered list of translation notes for the page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if home_presenter_service.source_document_name(manifest) is None:
        return [ui_state_service.translate("ai_translation.note_no_source", language)]
    if not source_chunks:
        return [ui_state_service.translate("ai_translation.note_missing_chunking", language)]
    stage_status = _translation_stage_status(report, operation_state)
    notes = [
        ui_state_service.translate("ai_translation.note_summary", language).format(
            translated_count=0 if report is None else int(report.get("translated_chunk_count", 0)),
            approved_count=0 if report is None else int(report.get("approved_chunk_count", 0)),
            total_count=len(source_chunks),
        )
    ]
    if report is not None:
        warnings = [str(item) for item in list(report.get("warnings", [])) if str(item).strip()]
        notes.extend(warnings)
    if not has_ai_profiles:
        notes.append(ui_state_service.translate("ai_translation.note_no_profile", language))
        return notes
    if stage_status == "running":
        progress_current = 0 if operation_state is None else int(operation_state.get("progress_current", 0))
        progress_total = len(source_chunks) if operation_state is None else int(operation_state.get("progress_total", len(source_chunks)))
        notes.append(
            ui_state_service.translate("ai_translation.note_in_progress", language).format(
                progress_current=progress_current,
                progress_total=progress_total,
            )
        )
    elif stage_status == "failed":
        progress_current = 0 if operation_state is None else int(operation_state.get("progress_current", 0))
        progress_total = len(source_chunks) if operation_state is None else int(operation_state.get("progress_total", len(source_chunks)))
        notes.append(
            ui_state_service.translate("ai_translation.note_resume", language).format(
                progress_current=progress_current,
                progress_total=progress_total,
            )
        )
    elif report is not None and str(report.get("translation_stage_status", "")) == ai_translation_service.TRANSLATION_STAGE_COMPLETED:
        notes.append(ui_state_service.translate("ai_translation.note_completed_locked", language))
    else:
        notes.append(ui_state_service.translate("ai_translation.note_ready", language))
    return notes


# HELPER FUNCTIONS


def _translation_stage_status(report: dict[str, object] | None, operation_state: dict[str, object] | None) -> str:
    """
    @brief      Resolve the effective translation stage from report and runtime state.
    @param[in]  report Persisted translation report or `None`.
    @param[in]  operation_state Persisted operation state or `None`.
    @return     Effective translation stage token.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if isinstance(operation_state, dict):
        operation_status = str(operation_state.get("status", ""))
        if operation_status in {"running", "failed"}:
            return operation_status
    if isinstance(report, dict):
        return str(
            report.get(
                "translation_stage_status",
                ai_translation_service.TRANSLATION_STAGE_NOT_STARTED,
            )
        )
    return ai_translation_service.TRANSLATION_STAGE_NOT_STARTED


def _persisted_target_language(report: dict[str, object] | None, operation_state: dict[str, object] | None) -> str:
    """
    @brief      Resolve the persisted target language for the translation page.
    @param[in]  report Persisted translation report or `None`.
    @param[in]  operation_state Persisted translation operation state or `None`.
    @return     Valid persisted target language or the application default.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if isinstance(report, dict):
        target_language = str(report.get("target_language", "")).strip()
        if target_language in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
            return target_language
    if isinstance(operation_state, dict):
        metadata = operation_state.get("metadata", {})
        if isinstance(metadata, dict):
            target_language = str(metadata.get("target_language", "")).strip()
            if target_language in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
                return target_language
    return config.DEFAULT_TRANSLATION_TARGET_LANGUAGE


def _persisted_profile_id(report: dict[str, object] | None, operation_state: dict[str, object] | None) -> str | None:
    """
    @brief      Resolve the persisted translation profile identifier if available.
    @param[in]  report Persisted translation report or `None`.
    @param[in]  operation_state Persisted translation operation state or `None`.
    @return     Persisted profile identifier or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if isinstance(report, dict):
        profile_id = report.get("translation_profile_id_last_used")
        if profile_id not in (None, ""):
            return str(profile_id)
    if isinstance(operation_state, dict):
        metadata = operation_state.get("metadata", {})
        if isinstance(metadata, dict):
            profile_id = metadata.get("translation_profile_id")
            if profile_id not in (None, ""):
                return str(profile_id)
    return None


# END OF FILE
