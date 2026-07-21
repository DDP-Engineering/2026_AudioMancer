#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_translation_state_service.py
@brief Read-only AI Translation page-state composition.
@details Derives page state from canonical chunks and the strict authoritative
         translation document without synchronizing or persisting artifacts.
@author Eng. Dan Dumitru Pasare
@date 2026-07-16
@version 0.8.0
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    ai_state_note_service,
    ai_translation_service,
    chunking_document_service,
    home_presenter_service,
    narrator_definition_service,
    ui_state_service,
)

# PUBLIC API


def build_ai_translation_profile_state(
    settings_payload: dict[str, object] | None,
    selected_profile_id: str | None = None,
) -> dict[str, object]:
    """Build enabled profile entries and prefer the current configured default."""
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
    default_profile_id = settings_payload.get("default_ai_translation_profile_id")
    resolved_default = str(default_profile_id) if default_profile_id in enabled_ids else None
    resolved_selected_id = (
        selected_profile_id
        if selected_profile_id in enabled_ids
        else (resolved_default if resolved_default is not None else (enabled_ids[0] if enabled_ids else None))
    )
    return {"entries": entries, "selected_profile_id": resolved_selected_id}


def build_ai_translation_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
    settings_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build page state without writing or repairing translation persistence."""
    profile_state = build_ai_translation_profile_state(settings_payload)
    if project_root is None or manifest is None:
        return _empty_state(
            [ui_state_service.translate("ai_translation.note_no_project", language)],
            language,
            profile_state["selected_profile_id"],
        )
    source_chunks = chunking_document_service.load_chunks(project_root)
    target_language = _persisted_target_language(manifest)
    try:
        document = ai_translation_service.load_translation_document(project_root)
    except ai_translation_service.TranslationDocumentError as exc:
        return {
            "source_chunks": source_chunks,
            "translated_chunks": [],
            "notes": [str(exc)],
            "original_language": _original_language_label(manifest, language),
            "target_language": target_language,
            "selected_profile_id": profile_state["selected_profile_id"],
            "stage_status": ai_translation_service.TRANSLATION_STATUS_INVALID,
            "translated_count": 0,
            "approved_count": 0,
            "total_count": len(source_chunks),
        }
    summary = ai_translation_service.build_translation_summary(source_chunks, document)
    translated_chunks = [] if document is None else [dict(item) for item in document["chunks"]]
    return {
        "source_chunks": source_chunks,
        "translated_chunks": translated_chunks,
        "notes": build_ai_translation_notes(
            manifest,
            source_chunks,
            document,
            summary,
            bool(profile_state["entries"]),
            language,
        ),
        "original_language": _original_language_label(manifest, language),
        "target_language": target_language,
        "selected_profile_id": profile_state["selected_profile_id"],
        "stage_status": summary["status"],
        "translated_count": summary["translated_count"],
        "approved_count": summary["approved_count"],
        "total_count": summary["total_count"],
    }


def build_ai_translation_notes(
    manifest: dict[str, object],
    source_chunks: list[dict[str, object]],
    document: dict[str, object] | None,
    summary: dict[str, object],
    has_ai_profiles: bool,
    language: str,
) -> list[str]:
    """Build concise notes from derived document state."""
    if home_presenter_service.source_document_name(manifest) is None:
        return [ui_state_service.translate("ai_translation.note_no_source", language)]
    if not source_chunks:
        return [ui_state_service.translate("ai_translation.note_missing_chunking", language)]
    notes = [
        ui_state_service.translate("ai_translation.note_summary", language).format(
            translated_count=int(summary["translated_count"]),
            approved_count=int(summary["approved_count"]),
            total_count=int(summary["total_count"]),
        )
    ]
    if document is not None:
        notes.extend(
            ai_state_note_service.build_token_usage_notes(
                {"token_usage": document["token_usage"]},
                None,
                language,
            )
        )
    if not has_ai_profiles:
        notes.append(ui_state_service.translate("ai_translation.note_no_profile", language))
        return notes
    status = str(summary["status"])
    if status == ai_translation_service.TRANSLATION_STATUS_RUNNING:
        notes.append(
            ui_state_service.translate("ai_translation.note_in_progress", language).format(
                progress_current=int(summary["translated_count"]),
                progress_total=int(summary["total_count"]),
            )
        )
    elif status in {
        ai_translation_service.TRANSLATION_STATUS_IN_PROGRESS,
        ai_translation_service.TRANSLATION_STATUS_CANCELLED,
        ai_translation_service.TRANSLATION_STATUS_FAILED,
    }:
        notes.append(
            ui_state_service.translate("ai_translation.note_resume", language).format(
                progress_current=int(summary["translated_count"]),
                progress_total=int(summary["total_count"]),
            )
        )
    elif status == ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING:
        notes.append(ui_state_service.translate("ai_translation.note_approval_pending", language))
    elif status == ai_translation_service.TRANSLATION_STATUS_COMPLETED:
        notes.append(ui_state_service.translate("ai_translation.note_completed_locked", language))
    else:
        notes.append(ui_state_service.translate("ai_translation.note_ready", language))
    return notes


# LOCAL HELPERS


def _empty_state(notes: list[str], language: str, selected_profile_id: object) -> dict[str, object]:
    """Build state for an absent active project."""
    return {
        "source_chunks": [],
        "translated_chunks": [],
        "notes": notes,
        "original_language": ui_state_service.translate("narator_voice.language_unknown", language),
        "target_language": config.DEFAULT_TRANSLATION_TARGET_LANGUAGE,
        "selected_profile_id": selected_profile_id,
        "stage_status": ai_translation_service.TRANSLATION_STATUS_NOT_STARTED,
        "translated_count": 0,
        "approved_count": 0,
        "total_count": 0,
    }


def _persisted_target_language(manifest: dict[str, object]) -> str:
    """Resolve the locked target language from the project manifest."""
    candidate = str(manifest.get("target_language", config.DEFAULT_TRANSLATION_TARGET_LANGUAGE)).strip()
    if candidate in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
        return candidate
    return config.DEFAULT_TRANSLATION_TARGET_LANGUAGE


def _manifest_original_language(manifest: dict[str, object]) -> str | None:
    """Resolve a supported source-language code from the manifest."""
    candidate = str(manifest.get("original_language", "") or "").strip()
    return candidate if candidate in dict(config.TRANSLATION_LANGUAGE_OPTIONS) else None


def _original_language_label(manifest: dict[str, object], language: str) -> str:
    """Resolve the operator-facing original-language label."""
    original_language = _manifest_original_language(manifest)
    if original_language is None:
        return ui_state_service.translate("narator_voice.language_unknown", language)
    return narrator_definition_service.narrator_language_label(original_language)


# END OF FILE
