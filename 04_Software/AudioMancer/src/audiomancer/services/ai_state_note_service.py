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
@brief Shared AI workflow state-note helpers.
@details Provides reusable operator-facing note rendering for AI token usage
         persisted in reports or operation-state metadata.
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.1.0
"""

# IMPORTS

from audiomancer.services import token_usage_service, ui_state_service

# PUBLIC API


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
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
