#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file character_discovery_state_service.py
@brief Character Discovery page state helpers for AudioMancer.
@details Builds Characters-page selector state, notes, evidence previews, and
         manual-maintenance enablement flags from persisted project artifacts
         and settings.
"""

# IMPORTS

from pathlib import Path

from audiomancer.services import (
    ai_state_note_service,
    character_discovery_service,
    home_presenter_service,
    ui_state_service,
)


def build_character_discovery_profile_state(
    settings_payload: dict[str, object] | None,
    selected_profile_id: str | None = None,
) -> dict[str, object]:
    """
    @brief      Build the enabled AI-profile selector state for character discovery.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  selected_profile_id Preferred profile identifier if available.
    @return     Selector entries plus resolved selected profile id.
    @exception  None
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
    default_profile_id = settings_payload.get("default_character_extraction_profile_id")
    resolved_selected_id = (
        selected_profile_id
        if selected_profile_id in enabled_ids
        else (
            str(default_profile_id) if default_profile_id in enabled_ids else (enabled_ids[0] if enabled_ids else None)
        )
    )
    return {"entries": entries, "selected_profile_id": resolved_selected_id}


def build_character_discovery_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
    settings_payload: dict[str, object] | None = None,
    selected_profile_id: str | None = None,
) -> dict[str, object]:
    """
    @brief      Build the full Characters page state from project artifacts.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  language Runtime UI language code.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  selected_profile_id Currently live Characters-page profile selection.
    @return     Page-state payload consumed by the Characters page.
    @exception  None
    """
    if project_root is None or manifest is None:
        profile_state = build_character_discovery_profile_state(settings_payload, selected_profile_id)
        return {
            "profiles": [],
            "notes": [ui_state_service.translate("characters.note_no_project", language)],
            "selected_profile_id": profile_state["selected_profile_id"],
            "stage_status": character_discovery_service.CHARACTER_DISCOVERY_STAGE_NOT_STARTED,
            "character_count": 0,
            "source_chunk_map": {},
            "can_start": False,
            "can_reset": False,
            "can_add": False,
            "can_edit": False,
            "can_save": False,
            "can_delete": False,
            "edit_mode": False,
            "dirty": False,
        }
    source_chunks = character_discovery_service.load_input_chunks(project_root)
    source_chunk_map = {
        str(chunk.get("chunk_id", "")): str(chunk.get("text", ""))
        for chunk in source_chunks
        if str(chunk.get("chunk_id", "")).strip()
    }
    profile_state = build_character_discovery_profile_state(
        settings_payload,
        selected_profile_id,
    )
    try:
        document = character_discovery_service.load_character_document(project_root)
        profiles = character_discovery_service.load_character_profiles(project_root)
    except character_discovery_service.CharacterDocumentError:
        return _invalid_character_document_state(
            source_chunk_map,
            profile_state,
            language,
        )
    enabled_profile_ids = {profile_id for _label, profile_id in profile_state["entries"]}
    preferred_profile_id = (
        selected_profile_id
        if selected_profile_id in enabled_profile_ids
        else _persisted_profile_id(document)
    )
    profile_state = build_character_discovery_profile_state(settings_payload, preferred_profile_id)
    operation_state = (
        None
        if document is None
        else character_discovery_service.character_operation_summary(document, len(source_chunks))
    )
    if operation_state is not None and document is not None:
        operation_state["metadata"] = {"token_usage": dict(document["token_usage"])}
    report = (
        None
        if document is None or document.get("status") != character_discovery_service.CHARACTER_DISCOVERY_STAGE_COMPLETED
        else {
            "token_usage": dict(document["token_usage"]),
            "warnings": _rejected_candidate_warning_notes(document, language),
        }
    )
    stage_status = _character_discovery_stage_status(report, operation_state)
    has_ai_profiles = bool(profile_state["entries"])
    has_chunking_output = bool(source_chunks)
    has_discovery_result = document is not None
    can_start = (
        has_chunking_output
        and has_ai_profiles
        and stage_status != character_discovery_service.CHARACTER_DISCOVERY_STAGE_COMPLETED
    )
    can_reset = has_discovery_result
    can_add = has_discovery_result
    can_edit = bool(profiles)
    can_delete = bool(profiles)
    notes = build_character_discovery_notes(
        manifest,
        source_chunks,
        report,
        operation_state,
        profiles,
        has_ai_profiles,
        language,
    )
    if document is not None and report is None:
        notes.extend(_rejected_candidate_warning_notes(document, language))
    return {
        "profiles": profiles,
        "notes": notes,
        "selected_profile_id": profile_state["selected_profile_id"],
        "stage_status": stage_status,
        "character_count": len(profiles),
        "source_chunk_map": source_chunk_map,
        "can_start": can_start,
        "can_reset": can_reset,
        "can_add": can_add,
        "can_edit": can_edit,
        "can_save": False,
        "can_delete": can_delete,
        "edit_mode": False,
        "dirty": False,
    }


def _invalid_character_document_state(
    source_chunk_map: dict[str, str],
    profile_state: dict[str, object],
    language: str,
) -> dict[str, object]:
    """
    @brief      Build the read-only recovery state for a strict-invalid document.
    @param[in]  source_chunk_map Valid chunk text keyed by `chunk_id`.
    @param[in]  profile_state Resolved available AI-profile selector state.
    @param[in]  language Runtime UI language code.
    @return     Complete Characters page recovery payload.
    @exception  None
    """
    return {
        "profiles": [],
        "notes": [ui_state_service.translate("characters.note_invalid_document", language)],
        "selected_profile_id": profile_state["selected_profile_id"],
        "stage_status": "failed",
        "character_count": 0,
        "source_chunk_map": source_chunk_map,
        "can_start": False,
        "can_reset": True,
        "can_add": False,
        "can_edit": False,
        "can_save": False,
        "can_delete": False,
        "edit_mode": False,
        "dirty": False,
    }


def build_character_discovery_notes(
    manifest: dict[str, object],
    source_chunks: list[dict[str, object]],
    report: dict[str, object] | None,
    operation_state: dict[str, object] | None,
    profiles: list[dict[str, object]],
    has_ai_profiles: bool,
    language: str,
) -> list[str]:
    """
    @brief      Build operator-facing notes for the active character-discovery page.
    @param[in]  manifest Active project manifest payload.
    @param[in]  source_chunks Canonical source chunks from chunking.
    @param[in]  report Persisted character-discovery report or `None`.
    @param[in]  operation_state Persisted operation state or `None`.
    @param[in]  profiles Persisted character profile payload list.
    @param[in]  has_ai_profiles True when at least one enabled AI profile exists.
    @param[in]  language Runtime UI language code.
    @return     Ordered notes for the Characters page.
    @exception  None
    """
    if home_presenter_service.source_document_name(manifest) is None:
        return [ui_state_service.translate("characters.note_no_source", language)]
    if not source_chunks:
        return [ui_state_service.translate("characters.note_missing_chunking", language)]
    notes = []
    if report is not None:
        notes.append(
            ui_state_service.translate("characters.note_summary", language).format(
                character_count=len(profiles),
            )
        )
        notes.extend(_build_token_usage_notes(report, operation_state, language))
        notes.extend(str(item) for item in list(report.get("warnings", [])) if str(item).strip())
        notes.append(ui_state_service.translate("characters.note_rerun_replaces_manual", language))
    elif operation_state is not None:
        notes.extend(_build_token_usage_notes(report, operation_state, language))
    if not has_ai_profiles:
        notes.append(ui_state_service.translate("characters.note_no_profile", language))
        return notes
    stage_status = _character_discovery_stage_status(report, operation_state)
    if stage_status == "running":
        progress_current = 0 if operation_state is None else int(operation_state.get("progress_current", 0))
        progress_total = (
            len(source_chunks)
            if operation_state is None
            else int(operation_state.get("progress_total", len(source_chunks)))
        )
        notes.append(
            ui_state_service.translate("characters.note_in_progress", language).format(
                progress_current=progress_current,
                progress_total=progress_total,
            )
        )
    elif stage_status in {"failed", "cancelled"}:
        progress_current = 0 if operation_state is None else int(operation_state.get("progress_current", 0))
        progress_total = (
            len(source_chunks)
            if operation_state is None
            else int(operation_state.get("progress_total", len(source_chunks)))
        )
        notes.append(
            ui_state_service.translate("characters.note_resume", language).format(
                progress_current=progress_current,
                progress_total=progress_total,
            )
        )
    elif report is not None:
        notes.append(ui_state_service.translate("characters.note_completed_locked", language))
    else:
        notes.append(ui_state_service.translate("characters.note_ready", language))
    return notes


def _build_token_usage_notes(
    report: dict[str, object] | None,
    operation_state: dict[str, object] | None,
    language: str,
) -> list[str]:
    """
    @brief      Build the token usage notes.
    @param[in]  report Value for `report`.
    @param[in]  operation_state Value for `operation_state`.
    @param[in]  language Language code.
    @return     Derived helper result.
    """
    return ai_state_note_service.build_token_usage_notes(report, operation_state, language)


def _rejected_candidate_warning_notes(document: dict[str, object], language: str) -> list[str]:
    """Build localized, privacy-preserving rejection-warning groups from persisted diagnostics."""
    rejected_candidates = document.get("rejected_candidates")
    if not isinstance(rejected_candidates, list):
        return []
    counts_by_reason: dict[str, int] = {}
    for diagnostic in rejected_candidates:
        if not isinstance(diagnostic, dict):
            continue
        reason = str(diagnostic.get("reason", ""))
        counts_by_reason[reason] = counts_by_reason.get(reason, 0) + 1
    localization_keys = {
        "missing_evidence": "characters.note_rejected_missing_evidence",
        "missing_spoken_dialogue_evidence": "characters.note_rejected_missing_spoken_dialogue_evidence",
    }
    return [
        ui_state_service.translate(localization_keys[reason], language).format(candidate_count=counts_by_reason[reason])
        for reason in sorted(counts_by_reason)
        if reason in localization_keys
    ]


def _character_discovery_stage_status(
    report: dict[str, object] | None,
    operation_state: dict[str, object] | None,
) -> str:
    """
    @brief      Resolve the effective character-discovery stage token.
    @param[in]  report Persisted character-discovery report or `None`.
    @param[in]  operation_state Persisted operation state or `None`.
    @return     Effective stage token for the Characters page state.
    @exception  None
    """
    if isinstance(operation_state, dict):
        operation_status = str(operation_state.get("status", ""))
        if operation_status in {"running", "failed", "cancelled"}:
            return operation_status
        if operation_status == "completed":
            return character_discovery_service.CHARACTER_DISCOVERY_STAGE_COMPLETED
    if isinstance(report, dict):
        return character_discovery_service.CHARACTER_DISCOVERY_STAGE_COMPLETED
    return character_discovery_service.CHARACTER_DISCOVERY_STAGE_NOT_STARTED


def _persisted_profile_id(
    document: dict[str, object] | None,
) -> str | None:
    """
    @brief      Read the last-used AI profile id from persisted discovery artifacts.
    @param[in]  document Persisted authoritative character document or `None`.
    @return     Persisted AI profile identifier or `None`.
    @exception  None
    """
    if not isinstance(document, dict):
        return None
    profile_id = document.get("character_profile_id_last_used")
    return str(profile_id) if profile_id not in (None, "") else None


# END OF FILE
