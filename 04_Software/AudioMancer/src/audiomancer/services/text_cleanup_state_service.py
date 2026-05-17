#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file text_cleanup_state_service.py
@brief Text-cleanup page state helpers for AudioMancer.
@details Builds the extracted/cleaned preview state, operator notes, and
         manifest reset payloads used by the Text Cleanup page workflows,
         including manual cleaned-text edits.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.13.0
"""

# IMPORTS

from collections.abc import Iterable
import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    ai_state_note_service,
    cleanup_metadata_service,
    deterministic_cleanup_service,
    home_presenter_service,
    operation_runtime_service,
    project_workspace_service,
    text_extraction_service,
    ui_state_service,
)
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# PUBLIC API


def build_text_cleanup_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
) -> dict[str, object]:
    """
    @brief      Build the operator-facing state payload for the text cleanup page.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  language Current UI language code.
    @return     Keyword payload for `TextCleanupPage.set_processing_state`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.4
    """
    if project_root is None or manifest is None:
        return {
            "extracted_text": None,
            "cleaned_text": None,
            "notes": [ui_state_service.translate("text_cleanup.note_no_project", language)],
            "can_extract": False,
            "can_clean": False,
            "can_ai_clean": False,
        }

    extracted_text = read_optional_project_text(project_root, config.EXTRACTED_TEXT_FILE_NAME)
    extraction_report_payload = text_extraction_service.load_extraction_report(project_root)
    extraction_operation_state = text_extraction_service.load_operation_state(project_root)
    cleaned_text = read_optional_project_text(
        project_root,
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}",
    )
    cleanup_report_payload = deterministic_cleanup_service.load_cleanup_report(project_root)
    cleanup_operation_state = deterministic_cleanup_service.load_operation_state(project_root)
    return {
        "extracted_text": extracted_text,
        "cleaned_text": cleaned_text,
        "notes": build_text_cleanup_notes(
            manifest,
            extraction_report_payload,
            extraction_operation_state,
            cleanup_report_payload,
            cleanup_operation_state,
            language,
        ),
        "can_extract": home_presenter_service.source_document_name(manifest) is not None,
        "can_clean": extracted_text is not None,
        "can_ai_clean": extracted_text is not None,
    }


def build_ai_cleanup_profile_state(
    settings_payload: dict[str, object] | None,
) -> dict[str, object]:
    """
    @brief      Build the AI cleanup profile-selector state from app settings.
    @param[in]  settings_payload Active application settings payload.
    @return     Selector payload with ordered entries and one selected id.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.2
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
    preferred_profile_id = settings_payload.get("default_ai_cleanup_profile_id")
    selected_profile_id = (
        str(preferred_profile_id) if preferred_profile_id in enabled_ids else (enabled_ids[0] if enabled_ids else None)
    )
    return {
        "entries": entries,
        "selected_profile_id": selected_profile_id,
    }


def save_cleaned_text_edit(project_root: Path, manifest: dict[str, object], cleaned_text: str) -> dict[str, object]:
    """
    @brief      Persist one manual cleaned-text edit and reset downstream workflow state.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Current project manifest payload.
    @param[in]  cleaned_text Edited cleaned text content.
    @return     Updated manifest payload.
    @exception  ValueError Raised when the cleaned text artifact does not exist yet.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.4.0
    """
    cleaned_text_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    if not cleaned_text_path.is_file():
        raise ValueError("No cleaned text is available to edit.")
    cleaned_text_path.write_text(cleaned_text, encoding="utf-8")
    metadata_payload = cleanup_metadata_service.write_minimal_cleanup_metadata(
        project_root,
        cleaned_text,
        "manual_edit",
    )
    operation_runtime_service.reset_operation_data(
        project_root,
        "cleanup",
        include_current=False,
        keep_input_snapshots=False,
        preserve_operation_kinds=operation_runtime_service.TEXT_REVISION_PRESERVED_OPERATION_KINDS,
    )
    updated_manifest = build_manifest_after_cleanup_edit(manifest)
    project_workspace_service.save_manifest(updated_manifest, project_root)
    manual_state = _write_manual_cleanup_state(project_root, updated_manifest, metadata_payload)
    return project_workspace_service.sync_manifest_operation_summary(
        project_root,
        "cleanup",
        manual_state,
        current_stage="text_cleanup_ready",
    )


def build_manifest_after_cleanup_edit(manifest: dict[str, object]) -> dict[str, object]:
    """
    @brief      Build one manifest payload after a manual cleaned-text edit.
    @param[in]  manifest Current manifest payload before the edit.
    @return     Manifest with cleanup preserved and downstream operations reset.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.1
    """
    updated_manifest = dict(manifest)
    operations = normalized_manifest_operations(updated_manifest)
    default_operations = normalized_manifest_operations({})
    preserved_operation_kinds = operation_runtime_service.TEXT_REVISION_PRESERVED_OPERATION_KINDS
    for selected_kind in operation_runtime_service.downstream_operation_kinds("cleanup", include_current=False):
        if selected_kind in default_operations and selected_kind not in preserved_operation_kinds:
            operations[selected_kind] = default_operations[selected_kind]
    updated_manifest["operations"] = operations
    updated_manifest["current_stage"] = "text_cleanup_ready"
    return updated_manifest


def build_text_cleanup_notes(
    manifest: dict[str, object],
    extraction_report_payload: dict[str, object] | None,
    extraction_operation_state: dict[str, object] | None,
    cleanup_report_payload: dict[str, object] | None,
    cleanup_operation_state: dict[str, object] | None,
    language: str,
) -> list[str]:
    """
    @brief      Build operator-facing notes for extraction plus deterministic or AI cleanup.
    @param[in]  manifest Active project manifest payload.
    @param[in]  extraction_report_payload Optional extraction report payload.
    @param[in]  extraction_operation_state Optional extraction operation-state payload.
    @param[in]  cleanup_report_payload Optional cleanup report payload.
    @param[in]  cleanup_operation_state Optional cleanup operation-state payload.
    @param[in]  language Current UI language code.
    @return     Ordered notes list for the cleanup page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.1
    """
    notes: list[str] = []
    if home_presenter_service.source_document_name(manifest) is None:
        notes.append(ui_state_service.translate("text_cleanup.note_no_source", language))
        return notes

    extraction_status = (
        None
        if not isinstance(extraction_operation_state, dict)
        else str(extraction_operation_state.get("status", "not_started"))
    )
    if extraction_report_payload is not None:
        page_text = extraction_report_payload.get("page_count")
        page_summary = "n/a" if page_text in (None, "") else str(page_text)
        notes.append(
            ui_state_service.translate(
                "text_cleanup.note_report_summary",
                language,
            ).format(
                word_count=extraction_report_payload.get("word_count", 0),
                line_count=extraction_report_payload.get("line_count", 0),
                page_count=page_summary,
            )
        )
        warnings = list(extraction_report_payload.get("warnings", []))
        notes.extend(str(item) for item in warnings)
        if extraction_status == "completed":
            notes.append(ui_state_service.translate("text_cleanup.note_rerun_warning", language))
    elif extraction_status in {"running", "failed"}:
        progress_current = (
            0
            if not isinstance(extraction_operation_state, dict)
            else int(extraction_operation_state.get("progress_current", 0))
        )
        progress_total = (
            0
            if not isinstance(extraction_operation_state, dict)
            else int(extraction_operation_state.get("progress_total", 0))
        )
        notes.append(
            ui_state_service.translate("text_cleanup.note_resume", language).format(
                progress_current=progress_current,
                progress_total=progress_total,
            )
        )
        return notes

    cleanup_status = (
        None
        if not isinstance(cleanup_operation_state, dict)
        else str(cleanup_operation_state.get("status", "not_started"))
    )
    cleanup_mode = None
    if cleanup_report_payload is not None:
        cleanup_mode = str(cleanup_report_payload.get("cleanup_mode") or "")
        if not cleanup_mode and isinstance(cleanup_operation_state, dict):
            cleanup_mode = str(cleanup_operation_state.get("mode") or "")
    if cleanup_report_payload is not None:
        summary_key = (
            "text_cleanup.note_ai_cleanup_summary"
            if cleanup_mode == "ai_assisted"
            else "text_cleanup.note_cleanup_summary"
        )
        notes.append(
            ui_state_service.translate(summary_key, language).format(
                paragraph_count=cleanup_report_payload.get("paragraph_count", 0),
                removed_line_count=cleanup_report_payload.get("removed_line_count", 0),
                chapter_count=cleanup_report_payload.get("detected_chapter_count", 0),
            )
        )
        page_break_repair_count = int(cleanup_report_payload.get("page_break_repair_count", 0))
        weak_boundary_count = int(cleanup_report_payload.get("weak_boundary_count", 0))
        if page_break_repair_count > 0 or weak_boundary_count > 0:
            notes.append(
                ui_state_service.translate("text_cleanup.note_page_break_metadata", language).format(
                    page_break_repair_count=page_break_repair_count,
                    weak_boundary_count=weak_boundary_count,
                )
            )
        ai_profile_id = cleanup_report_payload.get("ai_profile_id")
        if cleanup_mode == "ai_assisted" and ai_profile_id not in (None, ""):
            notes.append(
                ui_state_service.translate(
                    "text_cleanup.note_ai_cleanup_profile",
                    language,
                ).format(profile_label=str(ai_profile_id))
            )
        if cleanup_mode == "ai_assisted":
            notes.extend(
                _build_token_usage_notes(
                    cleanup_report_payload,
                    cleanup_operation_state,
                    language,
                )
            )
        cleanup_warnings = [str(item) for item in list(cleanup_report_payload.get("warnings", [])) if str(item).strip()]
        if cleanup_mode == "ai_assisted" and cleanup_warnings:
            notes.append(
                ui_state_service.translate(
                    "text_cleanup.note_ai_cleanup_review_warning",
                    language,
                )
            )
        notes.extend(cleanup_warnings)
        if cleanup_status == "completed":
            rerun_key = (
                "text_cleanup.note_ai_cleanup_rerun_warning"
                if cleanup_mode == "ai_assisted"
                else "text_cleanup.note_cleanup_rerun_warning"
            )
            notes.append(ui_state_service.translate(rerun_key, language))
        return notes

    if cleanup_status in {"running", "failed", "cancelled"}:
        progress_current = (
            0
            if not isinstance(cleanup_operation_state, dict)
            else int(cleanup_operation_state.get("progress_current", 0))
        )
        progress_total = (
            0
            if not isinstance(cleanup_operation_state, dict)
            else int(cleanup_operation_state.get("progress_total", 0))
        )
        running_mode = (
            None if not isinstance(cleanup_operation_state, dict) else str(cleanup_operation_state.get("mode") or "")
        )
        ready_key = (
            "text_cleanup.note_ai_cleanup_ready" if running_mode == "ai_assisted" else "text_cleanup.note_cleanup_ready"
        )
        resume_key = (
            "text_cleanup.note_ai_cleanup_resume"
            if running_mode == "ai_assisted"
            else "text_cleanup.note_cleanup_resume"
        )
        notes.append(ui_state_service.translate(ready_key, language))
        notes.append(
            ui_state_service.translate(resume_key, language).format(
                progress_current=progress_current,
                progress_total=progress_total,
            )
        )
        if running_mode == "ai_assisted":
            notes.extend(
                _build_token_usage_notes(
                    cleanup_report_payload,
                    cleanup_operation_state,
                    language,
                )
            )
        return notes

    notes.append(ui_state_service.translate("text_cleanup.note_cleanup_ready", language))
    return notes


def _build_token_usage_notes(
    report_payload: dict[str, object] | None,
    operation_state: dict[str, object] | None,
    language: str,
) -> list[str]:
    """
    @brief      Build the token usage notes.
    @param[in]  report_payload Payload for `report_payload`.
    @param[in]  operation_state Value for `operation_state`.
    @param[in]  language Language code.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    return ai_state_note_service.build_token_usage_notes(report_payload, operation_state, language)


def normalized_manifest_operations(
    manifest: dict[str, object],
) -> dict[str, dict[str, object]]:
    """
    @brief      Ensure the manifest exposes every required operation entry.
    @param[in]  manifest Active manifest payload.
    @return     Normalized operations mapping.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.4.0
    """
    operations = manifest.get("operations")
    if not isinstance(operations, dict):
        operations = {}
    normalized: dict[str, dict[str, object]] = {}
    for operation_kind in (
        "extraction",
        "cleanup",
        "chunking",
        "translation",
        "character_discovery",
        "narrator_definition",
        "character_voices",
        "speech_blocks",
        "audio_blocks",
        "audio_assembly",
    ):
        candidate = operations.get(operation_kind)
        normalized[operation_kind] = project_workspace_service.project_manifest_operation_summary(
            operation_kind,
            candidate if isinstance(candidate, dict) else None,
        )
    return normalized


def build_manifest_after_extraction_reset(
    manifest: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Build one manifest payload after a confirmed extraction rerun reset.
    @param[in]  manifest Current manifest payload before reset.
    @return     Reset manifest payload ready for persistence.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    return build_manifest_after_operation_reset(manifest, "extraction")


def build_manifest_after_operation_reset(
    manifest: dict[str, object],
    operation_kind: str,
    preserve_operation_kinds: Iterable[str] | None = None,
) -> dict[str, object]:
    """
    @brief      Build one manifest payload after resetting one operation and its downstream state.
    @param[in]  manifest Current manifest payload before reset.
    @param[in]  operation_kind Operation-kind token that triggered the reset.
    @param[in]  preserve_operation_kinds Optional operation kinds excluded from reset.
    @return     Reset manifest payload ready for persistence.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.4.0
    """
    updated_manifest = dict(manifest)
    operations = normalized_manifest_operations(updated_manifest)
    default_operations = normalized_manifest_operations({})
    preserved_operation_kinds = {
        str(selected_kind).strip() for selected_kind in (preserve_operation_kinds or ()) if str(selected_kind).strip()
    }
    if operation_kind == "extraction":
        updated_manifest["extraction_warning_count"] = 0
        updated_manifest["current_stage"] = "source_selected"
        for selected_kind in operations:
            if selected_kind not in preserved_operation_kinds:
                operations[selected_kind] = default_operations[selected_kind]
    else:
        updated_manifest["current_stage"] = _stage_after_operation_reset(operation_kind)
        for selected_kind in operation_runtime_service.downstream_operation_kinds(
            operation_kind,
            include_current=True,
        ):
            if selected_kind in default_operations and selected_kind not in preserved_operation_kinds:
                operations[selected_kind] = default_operations[selected_kind]
    if "narrator_definition" not in preserved_operation_kinds and updated_manifest["current_stage"] not in {
        "narrator_definition_ready",
        "character_voices_ready",
        "speech_blocks_ready",
        "audio_blocks_ready",
        "audio_assembly_ready",
    }:
        updated_manifest["narrator_profile_name"] = None
        updated_manifest["narrator_language"] = None
    updated_manifest["operations"] = operations
    return updated_manifest


def read_optional_project_text(
    project_root: Path,
    relative_path: str | None,
) -> str | None:
    """
    @brief      Read one optional project-local text artifact.
    @param[in]  project_root Active project root folder.
    @param[in]  relative_path Optional project-relative text artifact path.
    @return     Decoded text content or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not relative_path:
        return None
    artifact_path = project_root / relative_path
    if not artifact_path.is_file():
        return None
    return artifact_path.read_text(encoding="utf-8")


def _write_manual_cleanup_state(
    project_root: Path,
    manifest: dict[str, object],
    metadata_payload: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Persist compact cleanup operation state for one manual cleaned-text edit.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Manifest payload after the edit reset.
    @param[in]  metadata_payload Newly persisted cleanup metadata payload.
    @return     Persisted operation-state payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-17
    @version    0.2.0
    """
    cleaned_text_path = operation_runtime_service.build_operation_output_path(
        project_root,
        "cleanup",
        config.CLEANED_TEXT_FILE_NAME,
    )
    metadata_path = cleanup_metadata_service.cleanup_metadata_path(project_root)
    state_path = operation_runtime_service.build_operation_output_path(
        project_root,
        "cleanup",
        config.CLEANUP_STATE_FILE_NAME,
    )
    report_path = operation_runtime_service.build_operation_output_path(
        project_root,
        "cleanup",
        config.CLEANUP_REPORT_FILE_NAME,
    )
    input_paths = []
    if (project_root / config.EXTRACTED_TEXT_FILE_NAME).is_file():
        input_paths.append(config.EXTRACTED_TEXT_FILE_NAME)
    output_paths = []
    if cleaned_text_path.is_file():
        output_paths.append(operation_runtime_service.relative_to_project(project_root, cleaned_text_path))
    if metadata_path.is_file():
        output_paths.append(operation_runtime_service.relative_to_project(project_root, metadata_path))
    artifact_paths = (
        [operation_runtime_service.relative_to_project(project_root, report_path)] if report_path.is_file() else []
    )
    paragraph_count = int(metadata_payload.get("paragraph_count", 0) or 0)
    timestamp = _utc_now_iso()
    state_payload = operation_runtime_service.build_operation_state_payload(
        status="completed",
        input_paths=input_paths,
        output_paths=output_paths,
        artifact_paths=artifact_paths,
        progress_current=paragraph_count,
        progress_total=paragraph_count,
        mode="manual_edit",
        started_at=timestamp,
        completed_at=timestamp,
        warning_count=0,
        metadata={
            "warnings": [],
            "detected_language": manifest.get("original_language"),
            "paragraph_count": paragraph_count,
            "detected_chapter_count": None,
        },
        resume_checkpoint=None,
    )
    state_path.write_text(
        json.dumps(state_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return state_payload


def _stage_after_operation_reset(operation_kind: str) -> str:
    """
    @brief      Execute the stage after operation reset helper.
    @param[in]  operation_kind Value for `operation_kind`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    if operation_kind == "cleanup":
        return "text_cleanup_ready"
    if operation_kind == "chunking":
        return "text_chunking_ready"
    if operation_kind == "translation":
        return "translation_ready"
    if operation_kind == "character_discovery":
        return "translation_ready"
    if operation_kind == "narrator_definition":
        return "character_discovery_ready"
    if operation_kind == "character_voices":
        return "narrator_definition_ready"
    if operation_kind == "speech_blocks":
        return "character_voices_ready"
    if operation_kind == "audio_blocks":
        return "speech_blocks_ready"
    if operation_kind == "audio_assembly":
        return "audio_blocks_ready"
    return "source_selected"


# END OF FILE
