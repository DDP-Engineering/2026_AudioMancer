#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file text_chunking_state_service.py
@brief Text-chunking page state helpers for AudioMancer.
@details Builds the cleaned-text preview, persisted chunk state, AI profile
         selectors, and operator notes used by the Text Chunking page.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.1.0
"""

# IMPORTS

from pathlib import Path

from audiomancer.services import deterministic_chunking_service
from audiomancer.services import home_presenter_service
from audiomancer.services import text_cleanup_state_service
from audiomancer.services import ui_state_service


# PUBLIC API


def build_text_chunking_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
) -> dict[str, object]:
    """
    @brief      Build the operator-facing state payload for the text chunking page.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  language Current UI language code.
    @return     Keyword payload for `TextChunkingPage.set_processing_state`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if project_root is None or manifest is None:
        return {
            "cleaned_text": None,
            "chunks": [],
            "notes": [ui_state_service.translate("text_chunking.note_no_project", language)],
            "can_chunk": False,
            "can_ai_chunk": False,
            "selected_strategy": None,
        }

    cleanup_operation = home_presenter_service.manifest_operation(manifest, "cleanup")
    cleaned_text_relative_path = None
    output_paths = cleanup_operation.get("output_paths", [])
    if isinstance(output_paths, list) and output_paths:
        cleaned_text_relative_path = str(output_paths[0])
    cleaned_text = text_cleanup_state_service.read_optional_project_text(
        project_root,
        cleaned_text_relative_path,
    )
    chunking_report_payload = deterministic_chunking_service.load_chunking_report(project_root)
    chunking_operation_state = deterministic_chunking_service.load_operation_state(project_root)
    chunks = deterministic_chunking_service.load_chunks(project_root)
    has_cleaned_text = cleaned_text is not None and bool(cleaned_text.strip())
    return {
        "cleaned_text": cleaned_text,
        "chunks": chunks,
        "notes": build_text_chunking_notes(
            manifest,
            cleaned_text if has_cleaned_text else None,
            chunking_report_payload,
            chunking_operation_state,
            language,
        ),
        "can_chunk": has_cleaned_text,
        "can_ai_chunk": False,
        "selected_strategy": None,
    }


def build_ai_chunking_profile_state(
    settings_payload: dict[str, object] | None,
) -> dict[str, object]:
    """
    @brief      Build the AI chunking profile-selector state from app settings.
    @param[in]  settings_payload Active application settings payload.
    @return     Selector payload with ordered entries and one selected id.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
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
        if not isinstance(profile, dict):
            continue
        if not bool(profile.get("enabled", True)):
            continue
        profile_id = str(profile.get("id", "")).strip()
        if not profile_id:
            continue
        profile_label = str(profile.get("label", "")).strip() or profile_id
        entries.append((profile_label, profile_id))
        enabled_ids.append(profile_id)
    preferred_profile_id = settings_payload.get("default_ai_chunking_profile_id")
    selected_profile_id = (
        str(preferred_profile_id)
        if preferred_profile_id in enabled_ids
        else (enabled_ids[0] if enabled_ids else None)
    )
    return {
        "entries": entries,
        "selected_profile_id": selected_profile_id,
    }


def build_text_chunking_notes(
    manifest: dict[str, object],
    cleaned_text: str | None,
    chunking_report_payload: dict[str, object] | None,
    chunking_operation_state: dict[str, object] | None,
    language: str,
) -> list[str]:
    """
    @brief      Build operator-facing notes for deterministic chunking.
    @param[in]  manifest Active project manifest payload.
    @param[in]  cleaned_text Optional cleaned-text preview payload.
    @param[in]  chunking_report_payload Optional chunking report payload.
    @param[in]  chunking_operation_state Optional chunking operation-state payload.
    @param[in]  language Current UI language code.
    @return     Ordered notes list for the chunking page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    notes: list[str] = []
    if home_presenter_service.source_document_name(manifest) is None:
        notes.append(ui_state_service.translate("text_chunking.note_no_source", language))
        return notes
    if cleaned_text is None:
        notes.append(ui_state_service.translate("text_chunking.note_missing_cleanup", language))
        return notes

    chunking_status = (
        None
        if not isinstance(chunking_operation_state, dict)
        else str(chunking_operation_state.get("status", "not_started"))
    )
    if chunking_report_payload is not None:
        notes.append(
            ui_state_service.translate(
                "text_chunking.note_summary",
                language,
            ).format(
                chunk_count=chunking_report_payload.get("chunk_count", 0),
                chapter_count=chunking_report_payload.get("detected_chapter_count", 0),
            )
        )
        notes.extend(str(item) for item in list(chunking_report_payload.get("warnings", [])))
        if chunking_status == "completed":
            notes.append(ui_state_service.translate("text_chunking.note_rerun_warning", language))
        return notes

    if chunking_status in {"running", "failed"}:
        progress_current = (
            0
            if not isinstance(chunking_operation_state, dict)
            else int(chunking_operation_state.get("progress_current", 0))
        )
        progress_total = (
            0
            if not isinstance(chunking_operation_state, dict)
            else int(chunking_operation_state.get("progress_total", 0))
        )
        notes.append(ui_state_service.translate("text_chunking.note_ready", language))
        notes.append(
            ui_state_service.translate("text_chunking.note_resume", language).format(
                progress_current=progress_current,
                progress_total=progress_total,
            )
        )
        return notes

    notes.append(ui_state_service.translate("text_chunking.note_ready", language))
    return notes


# END OF FILE
