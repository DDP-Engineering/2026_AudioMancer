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

import pytest

from audiomancer.services import (
    ai_state_note_service,
    ai_translation_state_service,
    character_discovery_state_service,
    narrator_definition_state_service,
    speech_blocks_state_service,
    text_chunking_state_service,
)

# CONSTANTS

_PROFILE_WRAPPER_CASES = (
    (
        text_chunking_state_service.build_ai_chunking_profile_state,
        "default_ai_chunking_profile_id",
        False,
    ),
    (
        ai_translation_state_service.build_ai_translation_profile_state,
        "default_ai_translation_profile_id",
        True,
    ),
    (
        speech_blocks_state_service.build_speech_blocks_profile_state,
        "default_speech_blocks_profile_id",
        True,
    ),
    (
        character_discovery_state_service.build_character_discovery_profile_state,
        "default_character_extraction_profile_id",
        True,
    ),
    (
        narrator_definition_state_service.build_narrator_profile_generation_profile_state,
        "default_narrator_profile_generation_profile_id",
        True,
    ),
)


def test_build_llm_profile_selector_state_preserves_filtering_and_precedence() -> None:
    """
    @brief      Verify shared selector construction preserves filtering and fallback order.
    @return     None.
    @exception  None
    """
    settings_payload = {
        "llm_profiles": [
            "invalid",
            {"id": "", "label": "Missing id", "enabled": True},
            {"id": "disabled", "label": "Disabled", "enabled": False},
            {"id": " profile-a ", "label": "   ", "enabled": True},
            {"id": "profile-b", "label": " Profile B ", "enabled": True},
        ],
        "workflow_default": "profile-b",
    }

    explicit_state = ai_state_note_service.build_llm_profile_selector_state(
        settings_payload,
        "workflow_default",
        "profile-a",
    )
    default_state = ai_state_note_service.build_llm_profile_selector_state(
        settings_payload,
        "workflow_default",
        "missing",
    )
    settings_payload["workflow_default"] = "missing"
    first_enabled_state = ai_state_note_service.build_llm_profile_selector_state(
        settings_payload,
        "workflow_default",
    )

    assert explicit_state == {
        "entries": [("profile-a", "profile-a"), ("Profile B", "profile-b")],
        "selected_profile_id": "profile-a",
    }
    assert default_state["selected_profile_id"] == "profile-b"
    assert first_enabled_state["selected_profile_id"] == "profile-a"


def test_build_llm_profile_selector_state_returns_empty_for_invalid_payloads() -> None:
    """
    @brief      Verify invalid settings and profile collections retain the empty-state contract.
    @return     None.
    @exception  None
    """
    expected = {"entries": [], "selected_profile_id": None}

    assert ai_state_note_service.build_llm_profile_selector_state(None, "workflow_default") == expected
    assert ai_state_note_service.build_llm_profile_selector_state([], "workflow_default") == expected
    assert (
        ai_state_note_service.build_llm_profile_selector_state(
            {"llm_profiles": "invalid"},
            "workflow_default",
        )
        == expected
    )


@pytest.mark.parametrize(("builder", "default_key", "accepts_selection"), _PROFILE_WRAPPER_CASES)
def test_llm_profile_selector_wrappers_preserve_default_and_selection_contracts(
    builder,
    default_key: str,
    accepts_selection: bool,
) -> None:
    """
    @brief      Verify every participating public wrapper preserves its selector mapping.
    @param[in]  builder Public workflow-specific selector builder.
    @param[in]  default_key Workflow-specific configured-default key.
    @param[in]  accepts_selection Whether the wrapper accepts an explicit selection.
    @return     None.
    @exception  None
    """
    settings_payload = {
        "llm_profiles": [
            {"id": "profile-a", "label": "   ", "enabled": True},
            {"id": "profile-b", "label": " Profile B ", "enabled": True},
            {"id": "disabled", "label": "Disabled", "enabled": False},
        ],
        default_key: "profile-b",
    }

    state = (
        builder(settings_payload, selected_profile_id="profile-a")
        if accepts_selection
        else builder(settings_payload)
    )

    assert state["entries"] == [("profile-a", "profile-a"), ("Profile B", "profile-b")]
    assert state["selected_profile_id"] == ("profile-a" if accepts_selection else "profile-b")
    if builder is narrator_definition_state_service.build_narrator_profile_generation_profile_state:
        assert state["can_generate_profiles"] is False


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
