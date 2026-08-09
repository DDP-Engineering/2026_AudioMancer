#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_state_note_service.py
@brief Focused tests for shared AI workflow state-note helpers.
@details Verifies token usage note rendering shared by AI workflow state services.
"""

# IMPORTS

from audiomancer.services import ai_state_note_service


def test_build_token_usage_notes_renders_summary_from_report() -> None:
    """
    @brief      Verify available token usage renders one localized summary note.
    @return     None.
    @exception  None
    """
    notes = ai_state_note_service.build_token_usage_notes(
        {"token_usage": {"input_tokens": 1000, "output_tokens": 25, "total_tokens": 1025, "usage_available": True}},
        None,
        "en",
    )

    assert notes == ["Input tokens: 1,000 | Output tokens: 25 | Total: 1,025"]


def test_build_token_usage_notes_renders_unavailable_only_when_usage_was_persisted() -> None:
    """
    @brief      Verify unavailable token usage is shown only when a usage payload exists.
    @return     None.
    @exception  None
    """
    assert ai_state_note_service.build_token_usage_notes({}, None, "en") == []
    assert ai_state_note_service.build_token_usage_notes(
        None,
        {"metadata": {"token_usage": {"usage_available": False}}},
        "en",
    ) == ["Token usage was not reported by the backend."]


def test_build_token_usage_notes_ignores_noncanonical_top_level_operation_usage() -> None:
    """
    @brief      Verify canonical operation metadata wins over a noncanonical top-level usage field.
    @return     None.
    @exception  None
    """
    notes = ai_state_note_service.build_token_usage_notes(
        None,
        {
            "token_usage": {
                "input_tokens": 90,
                "output_tokens": 9,
                "total_tokens": 99,
                "usage_available": True,
            },
            "metadata": {
                "token_usage": {
                    "input_tokens": 2,
                    "output_tokens": 1,
                    "total_tokens": 3,
                    "usage_available": True,
                }
            },
        },
        "en",
    )

    assert notes == ["Input tokens: 2 | Output tokens: 1 | Total: 3"]


# END OF FILE
