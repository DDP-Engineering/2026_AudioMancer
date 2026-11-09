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
from audiomancer.translation.document import canonical_source_chunks

# PUBLIC API


def build_ai_translation_profile_state(
    settings_payload: dict[str, object] | None,
    selected_profile_id: str | None = None,
) -> dict[str, object]:
    """
    @brief      Build enabled profile entries and prefer the current configured default.
    @param[in]  settings_payload Validated application settings payload.
    @param[in]  selected_profile_id Optional identifier of the currently selected AI profile.
    @return     Constructed ai translation profile state.
    """
    return ai_state_note_service.build_llm_profile_selector_state(
        settings_payload,
        "default_ai_translation_profile_id",
        selected_profile_id,
    )


def build_ai_translation_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
    settings_payload: dict[str, object] | None = None,
    selected_profile_id: str | None = None,
) -> dict[str, object]:
    """
    @brief      Build page state without writing or repairing translation persistence.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  language Active user-interface language token.
    @param[in]  settings_payload Validated application settings payload.
    @param[in]  selected_profile_id Optional live AI-profile selection from the page.
    @return     Constructed ai translation state.
    """
    profile_state = build_ai_translation_profile_state(settings_payload, selected_profile_id)
    if project_root is None or manifest is None:
        return _empty_state(
            [ui_state_service.translate("ai_translation.note_no_project", language)],
            language,
            profile_state["selected_profile_id"],
        )
    source_chunks = canonical_source_chunks(chunking_document_service.load_chunks(project_root))
    target_language = ai_translation_service.manifest_target_language(manifest)
    try:
        document = ai_translation_service.load_translation_document(project_root)
        if document is not None and document["target_language"] != target_language:
            raise ai_translation_service.TranslationDocumentError(
                ui_state_service.translate("ai_translation.note_target_mismatch", language)
            )
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
    translated_chunks = [] if document is None else ai_translation_service.aligned_chunks(source_chunks, document)
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
    """
    @brief      Build concise notes from derived document state.
    @param[in]  manifest Active project manifest payload.
    @param[in]  source_chunks Ordered canonical source-chunk records.
    @param[in]  document Authoritative operation document payload.
    @param[in]  summary Derived operation summary used by the interface.
    @param[in]  has_ai_profiles Whether at least one usable AI profile is configured.
    @param[in]  language Active user-interface language token.
    @return     Constructed ai translation notes.
    """
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
        if any(
            row["translated_text"].strip() and row.get("source_fingerprint") is None
            for row in ai_translation_service.aligned_chunks(source_chunks, document)
        ):
            notes.append(ui_state_service.translate("ai_translation.note_legacy_review", language))
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


def _manifest_original_language(manifest: dict[str, object]) -> str | None:
    """
    @brief      Resolve a supported source-language code from the manifest.
    @param[in]  manifest Active project manifest payload.
    @return     Original-language token from the manifest, or None when unavailable.
    """
    candidate = str(manifest.get("original_language", "") or "").strip()
    return candidate if candidate in dict(config.TRANSLATION_LANGUAGE_OPTIONS) else None


def _original_language_label(manifest: dict[str, object], language: str) -> str:
    """
    @brief      Resolve the operator-facing original-language label.
    @param[in]  manifest Active project manifest payload.
    @param[in]  language Active user-interface language token.
    @return     Operator-facing original-language label.
    """
    original_language = _manifest_original_language(manifest)
    if original_language is None:
        return ui_state_service.translate("narator_voice.language_unknown", language)
    return narrator_definition_service.narrator_language_label(original_language)


# END OF FILE
