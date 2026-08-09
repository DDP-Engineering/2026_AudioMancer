#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_state_note_service.py
@brief Shared AI workflow state helpers.
@details Provides reusable LLM profile-selector construction and operator-facing
         note rendering for AI token usage persisted in workflow state.
"""

# IMPORTS

from audiomancer.services import token_usage_service, ui_state_service

# PUBLIC API


def build_llm_profile_selector_state(
    settings_payload: dict[str, object] | None,
    default_key: str,
    selected_profile_id: str | None = None,
) -> dict[str, object]:
    """
    @brief      Build one enabled LLM profile-selector state from application settings.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  default_key Workflow-specific configured-default setting key.
    @param[in]  selected_profile_id Preferred profile identifier if available.
    @return     Selector entries plus one resolved selected profile id.
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
    default_profile_id = settings_payload.get(default_key)
    resolved_selected_id = (
        selected_profile_id
        if selected_profile_id in enabled_ids
        else (
            str(default_profile_id) if default_profile_id in enabled_ids else (enabled_ids[0] if enabled_ids else None)
        )
    )
    return {"entries": entries, "selected_profile_id": resolved_selected_id}


def build_token_usage_notes(
    report_payload: dict[str, object] | None,
    operation_state: dict[str, object] | None,
    language: str,
) -> list[str]:
    """
    @brief      Build localized token-usage notes from report and operation-state payloads.
    @param[in]  report_payload Optional workflow report payload.
    @param[in]  operation_state Optional workflow operation-state payload.
    @param[in]  language Runtime UI language code.
    @return     Ordered token-usage notes.
    @exception  None
    """
    metadata = {}
    if isinstance(operation_state, dict):
        metadata = operation_state.get("metadata", {})
    metadata_token_usage = metadata.get("token_usage") if isinstance(metadata, dict) else None
    token_usage = token_usage_service.restore_token_usage(
        None if not isinstance(report_payload, dict) else report_payload.get("token_usage"),
        metadata_token_usage,
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
