#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file text_chunking_state_service.py
@brief Text-chunking page state helpers for AudioMancer.
@details Projects cleaned text, published chunks, replacement checkpoint notes and AI
         selectors. Existing mutation entry points delegate to chunking_edit_service.
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    ai_state_note_service,
    chunking_document_service,
    chunking_edit_service,
    home_presenter_service,
    text_cleanup_state_service,
    ui_state_service,
)
from audiomancer.services.logging_service import get_component_logger

# CONSTANTS

# @brief Component logger used for Text Chunking state mutations.
_TEXT_CHUNKING_STATE_LOGGER = get_component_logger("deterministic_chunking")
_RESUMABLE_CHUNKING_MUTATION_MESSAGE = "Finish, resume, or reset the current Chunking run before editing chunks."

# PUBLIC API


def build_text_chunking_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
    settings_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    """
    @brief      Build the operator-facing state payload for the text chunking page.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  language Current UI language code.
    @param[in]  settings_payload Validated application settings payload.
    @return     Keyword payload for `TextChunkingPage.set_processing_state`.
    @exception  ValueError Raised when cleaned text is unavailable for manual chunk insertion.
    """
    if project_root is None or manifest is None:
        return {
            "cleaned_text": None,
            "chunks": [],
            "notes": [ui_state_service.translate("text_chunking.note_no_project", language)],
            "can_chunk": False,
            "can_ai_chunk": False,
            "selected_strategy": _selected_ai_strategy(settings_payload),
        }

    cleaned_text = text_cleanup_state_service.read_optional_project_text(
        project_root,
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}",
    )
    chunking_document = chunking_document_service.load_chunking_document(project_root)
    chunking_report_payload = (
        None if chunking_document is None else chunking_document_service.derive_report(chunking_document)
    )
    chunking_operation_state = (
        None if chunking_document is None else chunking_document_service.derive_operation_state(chunking_document)
    )
    chunks = [] if chunking_document is None else list(chunking_document["chunks"])
    checkpoint = chunking_document_service.load_checkpoint(project_root)
    if checkpoint is not None:
        chunking_report_payload = chunking_document_service.derive_report(checkpoint)
        chunking_operation_state = chunking_document_service.derive_operation_state(checkpoint)
        chunking_document = checkpoint
    has_cleaned_text = cleaned_text is not None and bool(cleaned_text.strip())
    has_ai_profiles = bool(build_ai_chunking_profile_state(settings_payload)["entries"])
    return {
        "cleaned_text": cleaned_text,
        "chunks": chunks,
        "notes": build_text_chunking_notes(
            manifest,
            cleaned_text if has_cleaned_text else None,
            chunking_report_payload,
            chunking_operation_state,
            has_ai_profiles,
            language,
        ),
        "can_chunk": has_cleaned_text,
        "can_ai_chunk": has_cleaned_text and has_ai_profiles,
        "selected_strategy": (
            str(chunking_document["semantic_strategy"])
            if chunking_document is not None
            and chunking_document["mode"] == "ai_assisted"
            and chunking_document["status"] in chunking_document_service.RESUMABLE_STATUSES
            else _selected_ai_strategy(settings_payload)
        ),
    }


def build_ai_chunking_profile_state(
    settings_payload: dict[str, object] | None,
) -> dict[str, object]:
    """
    @brief      Build the AI chunking profile-selector state from app settings.
    @param[in]  settings_payload Active application settings payload.
    @return     Selector payload with ordered entries and one selected id.
    @exception  None
    """
    return ai_state_note_service.build_llm_profile_selector_state(
        settings_payload,
        "default_ai_chunking_profile_id",
    )


# Stable entry points used by the page controller; mutations belong to the edit service.
save_chunk_text_edit = chunking_edit_service.save_chunk_text_edit
insert_chunk_after_selected = chunking_edit_service.insert_chunk_after_selected
delete_selected_chunk = chunking_edit_service.delete_selected_chunk
_build_inserted_chunk_payload = chunking_edit_service._build_inserted_chunk_payload


def build_text_chunking_notes(
    manifest: dict[str, object],
    cleaned_text: str | None,
    chunking_report_payload: dict[str, object] | None,
    chunking_operation_state: dict[str, object] | None,
    has_ai_profiles: bool,
    language: str,
) -> list[str]:
    """
    @brief      Build operator-facing notes for deterministic and AI chunking.
    @param[in]  manifest Active project manifest payload.
    @param[in]  cleaned_text Optional cleaned-text preview payload.
    @param[in]  chunking_report_payload Optional chunking report payload.
    @param[in]  chunking_operation_state Optional chunking operation-state payload.
    @param[in]  has_ai_profiles True when one enabled AI profile is available.
    @param[in]  language Current UI language code.
    @return     Ordered notes list for the chunking page.
    @exception  None
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
    chunking_mode = (
        "" if not isinstance(chunking_operation_state, dict) else str(chunking_operation_state.get("mode") or "")
    )
    if chunking_status == "running":
        in_progress_key = (
            "text_chunking.note_ai_in_progress" if chunking_mode == "ai_assisted" else "text_chunking.note_in_progress"
        )
        notes.append(
            ui_state_service.translate(in_progress_key, language).format(
                strategy=_chunking_state_strategy(chunking_operation_state or {}),
            )
        )
        if chunking_mode == "ai_assisted":
            notes.extend(
                ai_state_note_service.build_token_usage_notes(
                    chunking_report_payload,
                    chunking_operation_state,
                    language,
                )
            )
        if chunking_report_payload is not None:
            notes.extend(str(item) for item in list(chunking_report_payload.get("warnings", [])))
        return notes

    if chunking_status in {"failed", "cancelled"}:
        resume_key = "text_chunking.note_ai_resume" if chunking_mode == "ai_assisted" else "text_chunking.note_resume"
        notes.append(
            ui_state_service.translate(resume_key, language).format(
                strategy=_chunking_state_strategy(chunking_operation_state or {}),
            )
        )
        if chunking_mode == "ai_assisted":
            notes.extend(
                ai_state_note_service.build_token_usage_notes(
                    chunking_report_payload,
                    chunking_operation_state,
                    language,
                )
            )
        if chunking_report_payload is not None:
            notes.extend(str(item) for item in list(chunking_report_payload.get("warnings", [])))
        return notes

    if chunking_report_payload is not None:
        chunking_mode = str(chunking_report_payload.get("chunking_mode") or chunking_mode)
        summary_key = (
            "text_chunking.note_ai_summary" if chunking_mode == "ai_assisted" else "text_chunking.note_summary"
        )
        notes.append(
            ui_state_service.translate(summary_key, language).format(
                chunk_count=chunking_report_payload.get("chunk_count", 0),
                chapter_count=chunking_report_payload.get("detected_chapter_count", 0),
                strategy=chunking_report_payload.get(
                    "semantic_strategy",
                    config.DEFAULT_AI_CHUNKING_STRATEGY,
                ),
            )
        )
        if chunking_mode == "ai_assisted":
            notes.extend(
                ai_state_note_service.build_token_usage_notes(
                    chunking_report_payload,
                    chunking_operation_state,
                    language,
                )
            )
        notes.extend(str(item) for item in list(chunking_report_payload.get("warnings", [])))
        rerun_key = (
            "text_chunking.note_ai_rerun_warning"
            if chunking_mode == "ai_assisted"
            else "text_chunking.note_rerun_warning"
        )
        notes.append(ui_state_service.translate(rerun_key, language))
        return notes

    notes.append(ui_state_service.translate("text_chunking.note_ready", language))
    if has_ai_profiles:
        notes.append(ui_state_service.translate("text_chunking.note_ai_ready", language))
    else:
        notes.append(ui_state_service.translate("text_chunking.note_no_ai_profile", language))
    return notes


def _selected_ai_strategy(settings_payload: dict[str, object] | None) -> str:
    """
    @brief      Execute the selected ai strategy helper.
    @param[in]  settings_payload Payload for `settings_payload`.
    @return     Helper result.
    """
    if not isinstance(settings_payload, dict):
        return config.DEFAULT_AI_CHUNKING_STRATEGY
    candidate = str(
        settings_payload.get(
            "default_ai_chunking_strategy",
            config.DEFAULT_AI_CHUNKING_STRATEGY,
        )
    )
    if candidate not in config.AI_CHUNKING_STRATEGY_OPTIONS:
        return config.DEFAULT_AI_CHUNKING_STRATEGY
    return candidate


def _chunking_state_strategy(chunking_operation_state: dict[str, object]) -> str:
    """
    @brief      Resolve the AI chunking strategy from a resumable state payload.
    @param[in]  chunking_operation_state Persisted chunking operation state.
    @return     Valid semantic strategy or the configured default.
    @exception  None
    """
    metadata = chunking_operation_state.get("metadata")
    if isinstance(metadata, dict):
        semantic_strategy = str(metadata.get("semantic_strategy", "")).strip()
        if semantic_strategy in config.AI_CHUNKING_STRATEGY_OPTIONS:
            return semantic_strategy
    return config.DEFAULT_AI_CHUNKING_STRATEGY


# END OF FILE
