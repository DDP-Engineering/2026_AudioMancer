#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
"""Read-only UI state and shared manifest reset helpers for Cleanup."""

from collections.abc import Iterable
from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    home_presenter_service,
    project_workspace_service,
    source_ledger_service,
    text_cleanup_service,
    text_extraction_service,
    ui_state_service,
)


def build_text_cleanup_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
) -> dict[str, object]:
    """Build the unified Text Cleanup page state without creating artifacts."""
    if project_root is None or manifest is None:
        return {
            "extracted_text": None,
            "cleaned_text": None,
            "notes": [ui_state_service.translate("text_cleanup.note_no_project", language)],
            "can_extract": False,
            "can_clean": False,
            "can_reset_cleanup": False,
            "validation_state": "not_started",
            "uncertainty_count": 0,
        }

    extraction_invalid = False
    extraction_metadata: dict[str, object] | None = None
    try:
        extraction_metadata = text_extraction_service.load_extraction_metadata(project_root)
    except (OSError, ValueError):
        extraction_invalid = True
    extracted_text = None if extraction_invalid else read_optional_project_text(
        project_root,
        config.EXTRACTED_TEXT_FILE_NAME,
    )
    cleaned_text = read_optional_project_text(project_root, config.CLEANED_TEXT_FILE_NAME)
    cleanup_invalid = False
    cleanup_document: dict[str, object] | None = None
    try:
        cleanup_document = text_cleanup_service.load_cleanup_document(project_root)
    except (OSError, ValueError):
        cleanup_invalid = True

    notes: list[str] = []
    if extraction_invalid:
        notes.append(ui_state_service.translate("text_cleanup.note_extraction_invalid", language))
    elif isinstance(extraction_metadata, dict) and extraction_metadata.get("status") == "completed":
        notes.append(
            ui_state_service.translate("text_cleanup.note_report_summary", language).format(
                word_count=extraction_metadata.get("word_count", 0),
                line_count=extraction_metadata.get("line_count", 0),
                page_count=extraction_metadata.get("page_count") or "n/a",
            )
        )
    elif home_presenter_service.source_document_name(manifest) is None:
        notes.append(ui_state_service.translate("text_cleanup.note_no_source", language))
    else:
        notes.append(ui_state_service.translate("text_cleanup.note_cleanup_ready", language))
    if cleanup_invalid:
        notes.append("Cleanup data is invalid. Reset Cleanup and run it again.")
    elif cleanup_document is not None:
        notes.extend(str(item) for item in cleanup_document["warnings"])
        if cleanup_document["status"] == "completed":
            notes.append("Cleanup passed and Text Chunking is available.")
        elif cleanup_document["status"] == "paused":
            notes.append("Cleanup is paused and can resume from its checkpoint.")
        else:
            notes.append(
                f"Cleanup status: {cleanup_document['status']} "
                f"({cleanup_document['phase']})."
            )

    extraction_complete = (
        extracted_text is not None
        and isinstance(extraction_metadata, dict)
        and extraction_metadata.get("status") == "completed"
    )
    if extraction_complete:
        try:
            source_ledger_service.load_source_ledger(project_root)
        except (OSError, ValueError):
            extraction_complete = False
    cleanup_artifacts = (
        config.CLEANUP_DOCUMENT_FILE_NAME,
        config.CLEANED_TEXT_FILE_NAME,
    )
    quality_report = (
        cleanup_document.get("quality_report")
        if isinstance(cleanup_document, dict)
        else None
    )
    return {
        "extracted_text": extracted_text,
        "cleaned_text": cleaned_text,
        "notes": notes,
        "can_extract": home_presenter_service.source_document_name(manifest) is not None,
        "can_clean": extraction_complete,
        "can_reset_cleanup": any((project_root / name).exists() for name in cleanup_artifacts),
        "validation_state": (
            "invalid"
            if cleanup_invalid
            else "passed"
            if (cleanup_document or {}).get("status") == "completed"
            else str((cleanup_document or {}).get("status", "not_started"))
        ),
        "uncertainty_count": (
            int(quality_report.get("low_confidence_count", 0))
            if isinstance(quality_report, dict)
            else 0
        ),
    }


def build_ai_cleanup_profile_state(
    settings_payload: dict[str, object] | None,
) -> dict[str, object]:
    """Build enabled optional AI-profile entries for Cleanup."""
    if not isinstance(settings_payload, dict) or not isinstance(settings_payload.get("llm_profiles"), list):
        return {"entries": [], "selected_profile_id": None}
    entries: list[tuple[str, str | None]] = []
    enabled_ids: list[str] = []
    for profile in settings_payload["llm_profiles"]:
        if not isinstance(profile, dict) or not bool(profile.get("enabled", True)):
            continue
        profile_id = str(profile.get("id") or "").strip()
        if not profile_id:
            continue
        entries.append((str(profile.get("label") or profile_id), profile_id))
        enabled_ids.append(profile_id)
    preferred = settings_payload.get("default_ai_cleanup_profile_id")
    selected = str(preferred) if preferred in enabled_ids else (enabled_ids[0] if enabled_ids else None)
    return {"entries": entries, "selected_profile_id": selected}


def save_cleaned_text_edit(
    project_root: Path,
    cleaned_text: str,
) -> dict[str, object]:
    """Persist an optional operator correction and keep Chunking immediately ready."""
    text_cleanup_service.save_user_cleaned_text(project_root, cleaned_text)
    return project_workspace_service.load_manifest(project_root)


def reset_cleanup(project_root: Path, manifest: dict[str, object]) -> dict[str, object]:
    """Delete Cleanup and downstream artifacts, then reset their manifest summaries."""
    text_cleanup_service.reset_cleanup_and_downstream(project_root)
    updated = build_manifest_after_operation_reset(manifest, "cleanup")
    project_workspace_service.save_manifest(updated, project_root)
    return project_workspace_service.load_manifest(project_root)


def normalized_manifest_operations(
    manifest: dict[str, object],
) -> dict[str, dict[str, object]]:
    """Return every required compact manifest operation summary."""
    operations = manifest.get("operations")
    if not isinstance(operations, dict):
        operations = {}
    normalized: dict[str, dict[str, object]] = {}
    for operation_kind in config.WORKFLOW_OPERATION_ORDER:
        candidate = operations.get(operation_kind)
        normalized[operation_kind] = project_workspace_service.project_manifest_operation_summary(
            operation_kind,
            candidate if isinstance(candidate, dict) else None,
        )
    return normalized


def build_manifest_after_extraction_reset(manifest: dict[str, object]) -> dict[str, object]:
    """Reset all generated operation summaries after a fresh Extraction request."""
    return project_workspace_service.build_manifest_after_operation_reset(
        manifest,
        "extraction",
    )


def build_manifest_after_operation_reset(
    manifest: dict[str, object],
    operation_kind: str,
    preserve_operation_kinds: Iterable[str] | None = None,
) -> dict[str, object]:
    """Delegate shared compact-summary reset construction to Project Lifecycle."""
    return project_workspace_service.build_manifest_after_operation_reset(
        manifest,
        operation_kind,
        preserve_operation_kinds,
    )


def read_optional_project_text(project_root: Path, relative_path: str | None) -> str | None:
    """Read one optional project-root UTF-8 text artifact."""
    if not relative_path:
        return None
    artifact_path = project_root / relative_path
    return artifact_path.read_text(encoding="utf-8") if artifact_path.is_file() else None


# END OF FILE
