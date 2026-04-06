#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
         manifest reset payloads used by the Text Cleanup page workflows.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.2.0
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import deterministic_cleanup_service
from audiomancer.services import home_presenter_service
from audiomancer.services import operation_runtime_service
from audiomancer.services import text_extraction_service
from audiomancer.services import ui_state_service


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
    @version    0.1.1
    """
    if project_root is None or manifest is None:
        return {
            "extracted_text": None,
            "cleaned_text": None,
            "notes": [
                ui_state_service.translate("text_cleanup.note_no_project", language)
            ],
            "can_extract": False,
            "can_clean": False,
        }

    extracted_text = read_optional_project_text(
        project_root,
        home_presenter_service.optional_manifest_string(
            manifest.get("extracted_text_relative_path")
        ),
    )
    extraction_report_payload = text_extraction_service.load_extraction_report(
        project_root
    )
    extraction_operation_state = text_extraction_service.load_operation_state(
        project_root
    )
    cleanup_operation = home_presenter_service.manifest_operation(manifest, "cleanup")
    cleanup_output_paths = cleanup_operation.get("output_paths", [])
    cleaned_text_relative_path = None
    if isinstance(cleanup_output_paths, list) and cleanup_output_paths:
        cleaned_text_relative_path = str(cleanup_output_paths[0])
    cleaned_text = read_optional_project_text(project_root, cleaned_text_relative_path)
    cleanup_report_payload = deterministic_cleanup_service.load_cleanup_report(
        project_root
    )
    cleanup_operation_state = deterministic_cleanup_service.load_operation_state(
        project_root
    )
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
    }


def build_text_cleanup_notes(
    manifest: dict[str, object],
    extraction_report_payload: dict[str, object] | None,
    extraction_operation_state: dict[str, object] | None,
    cleanup_report_payload: dict[str, object] | None,
    cleanup_operation_state: dict[str, object] | None,
    language: str,
) -> list[str]:
    """
    @brief      Build operator-facing notes for extraction and deterministic cleanup.
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
    @version    0.1.0
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
            notes.append(
                ui_state_service.translate("text_cleanup.note_rerun_warning", language)
            )
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
    if cleanup_report_payload is not None:
        notes.append(
            ui_state_service.translate(
                "text_cleanup.note_cleanup_summary",
                language,
            ).format(
                paragraph_count=cleanup_report_payload.get("paragraph_count", 0),
                removed_line_count=cleanup_report_payload.get("removed_line_count", 0),
                chapter_count=cleanup_report_payload.get("detected_chapter_count", 0),
            )
        )
        notes.extend(
            str(item) for item in list(cleanup_report_payload.get("warnings", []))
        )
        if cleanup_status == "completed":
            notes.append(
                ui_state_service.translate(
                    "text_cleanup.note_cleanup_rerun_warning",
                    language,
                )
            )
        return notes

    if cleanup_status in {"running", "failed"}:
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
        notes.append(ui_state_service.translate("text_cleanup.note_cleanup_ready", language))
        notes.append(
            ui_state_service.translate("text_cleanup.note_cleanup_resume", language).format(
                progress_current=progress_current,
                progress_total=progress_total,
            )
        )
        return notes

    notes.append(ui_state_service.translate("text_cleanup.note_cleanup_ready", language))
    return notes

def normalized_manifest_operations(
    manifest: dict[str, object],
) -> dict[str, dict[str, object]]:
    """
    @brief      Ensure the manifest exposes every required operation entry.
    @param[in]  manifest Active manifest payload.
    @return     Normalized operations mapping.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    operations = manifest.get("operations")
    if not isinstance(operations, dict):
        operations = {}
    normalized: dict[str, dict[str, object]] = {}
    for operation_kind, folder_name in (
        ("extraction", config.EXTRACTION_FOLDER_NAME),
        ("cleanup", config.CLEANUP_FOLDER_NAME),
        ("chunking", "20_chunking"),
        ("translation", "30_translation"),
        ("character_discovery", "40_character_discovery"),
    ):
        candidate = operations.get(operation_kind)
        if isinstance(candidate, dict):
            normalized[operation_kind] = dict(candidate)
            normalized[operation_kind].setdefault("folder_relative_path", folder_name)
            normalized[operation_kind].setdefault("status", "not_started")
        else:
            normalized[operation_kind] = {
                "folder_relative_path": folder_name,
                "status": "not_started",
                "input_paths": [],
                "output_paths": [],
                "artifact_paths": [],
                "progress_current": 0,
                "progress_total": 0,
                "mode": None,
                "started_at": None,
                "completed_at": None,
                "updated_at": None,
                "warning_count": 0,
                "metadata": {},
                "resume_checkpoint": None,
            }
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
    @version    0.1.0
    """
    return build_manifest_after_operation_reset(manifest, "extraction")


def build_manifest_after_operation_reset(
    manifest: dict[str, object],
    operation_kind: str,
) -> dict[str, object]:
    """
    @brief      Build one manifest payload after resetting one operation and its downstream state.
    @param[in]  manifest Current manifest payload before reset.
    @param[in]  operation_kind Operation-kind token that triggered the reset.
    @return     Reset manifest payload ready for persistence.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    updated_manifest = dict(manifest)
    operations = normalized_manifest_operations(updated_manifest)
    default_operations = normalized_manifest_operations({})
    if operation_kind == "extraction":
        updated_manifest["extracted_text_relative_path"] = None
        updated_manifest["extraction_report_relative_path"] = None
        updated_manifest["extraction_warning_count"] = 0
        updated_manifest["current_stage"] = "source_selected"
        for selected_kind in operations:
            operations[selected_kind] = default_operations[selected_kind]
    else:
        updated_manifest["current_stage"] = "source_selected"
        for selected_kind in operation_runtime_service.downstream_operation_kinds(
            operation_kind,
            include_current=True,
        ):
            operations[selected_kind] = default_operations[selected_kind]
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


# END OF FILE
