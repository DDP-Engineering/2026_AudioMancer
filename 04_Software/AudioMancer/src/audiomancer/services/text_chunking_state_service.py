#!/usr/bin/env python3
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
@version 0.4.0
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    deterministic_chunking_service,
    home_presenter_service,
    text_cleanup_state_service,
    token_usage_service,
    ui_state_service,
)

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
    @return     Keyword payload for `TextChunkingPage.set_processing_state`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.3.0
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
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}",
    )
    chunking_report_payload = deterministic_chunking_service.load_chunking_report(project_root)
    chunking_operation_state = deterministic_chunking_service.load_operation_state(project_root)
    chunks = deterministic_chunking_service.load_chunks(project_root)
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
        "selected_strategy": _selected_ai_strategy(settings_payload),
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
        str(preferred_profile_id) if preferred_profile_id in enabled_ids else (enabled_ids[0] if enabled_ids else None)
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.3.0
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
    if chunking_report_payload is not None:
        chunking_mode = str(chunking_report_payload.get("chunking_mode") or chunking_mode)
        summary_key = (
            "text_chunking.note_ai_summary" if chunking_mode == "ai_assisted" else "text_chunking.note_summary"
        )
        notes.append(
            ui_state_service.translate(
                summary_key,
                language,
            ).format(
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
                _build_token_usage_notes(
                    chunking_report_payload,
                    chunking_operation_state,
                    language,
                )
            )
        notes.extend(str(item) for item in list(chunking_report_payload.get("warnings", [])))
        if chunking_status == "completed":
            rerun_key = (
                "text_chunking.note_ai_rerun_warning"
                if chunking_mode == "ai_assisted"
                else "text_chunking.note_rerun_warning"
            )
            notes.append(ui_state_service.translate(rerun_key, language))
        return notes

    if chunking_status == "running":
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
        in_progress_key = (
            "text_chunking.note_ai_in_progress" if chunking_mode == "ai_assisted" else "text_chunking.note_in_progress"
        )
        notes.append(
            ui_state_service.translate(in_progress_key, language).format(
                progress_current=progress_current,
                progress_total=progress_total,
                strategy=(
                    chunking_operation_state.get("metadata", {})
                    if isinstance(chunking_operation_state.get("metadata"), dict)
                    else {}
                ).get("semantic_strategy", config.DEFAULT_AI_CHUNKING_STRATEGY),
            )
        )
        if chunking_mode == "ai_assisted":
            notes.extend(
                _build_token_usage_notes(
                    chunking_report_payload,
                    chunking_operation_state,
                    language,
                )
            )
        return notes

    if chunking_status == "failed":
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
        resume_key = "text_chunking.note_ai_resume" if chunking_mode == "ai_assisted" else "text_chunking.note_resume"
        notes.append(
            ui_state_service.translate(resume_key, language).format(
                progress_current=progress_current,
                progress_total=progress_total,
                strategy=(
                    chunking_operation_state.get("metadata", {})
                    if isinstance(chunking_operation_state.get("metadata"), dict)
                    else {}
                ).get("semantic_strategy", config.DEFAULT_AI_CHUNKING_STRATEGY),
            )
        )
        if chunking_mode == "ai_assisted":
            notes.extend(
                _build_token_usage_notes(
                    chunking_report_payload,
                    chunking_operation_state,
                    language,
                )
            )
        return notes

    notes.append(ui_state_service.translate("text_chunking.note_ready", language))
    if has_ai_profiles:
        notes.append(ui_state_service.translate("text_chunking.note_ai_ready", language))
    else:
        notes.append(ui_state_service.translate("text_chunking.note_no_ai_profile", language))
    return notes


def _selected_ai_strategy(settings_payload: dict[str, object] | None) -> str:
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


def _build_token_usage_notes(
    report_payload: dict[str, object] | None,
    operation_state: dict[str, object] | None,
    language: str,
) -> list[str]:
    metadata = {}
    if isinstance(operation_state, dict):
        metadata = operation_state.get("metadata", {})
    token_usage = token_usage_service.restore_token_usage(
        None if not isinstance(report_payload, dict) else report_payload.get("token_usage"),
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
    if (isinstance(report_payload, dict) and "token_usage" in report_payload) or (
        isinstance(metadata, dict) and "token_usage" in metadata
    ):
        return [ui_state_service.translate("ai.note_token_usage_unavailable", language)]
    return []


# END OF FILE
