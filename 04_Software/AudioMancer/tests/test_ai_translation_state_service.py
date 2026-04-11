#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_translation_state_service.py
@brief Focused tests for the AudioMancer AI translation state service.
@details Verifies translation-profile state shaping respects enabled profiles
         and the persisted default AI translation profile selection.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.2.0
"""

# IMPORTS

from audiomancer.services import ai_translation_state_service


# PUBLIC API


def test_build_ai_translation_profile_state_prefers_default_translation_profile() -> None:
    """
    @brief      Verify translation profile state prefers the configured default translation profile.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    profile_state = ai_translation_state_service.build_ai_translation_profile_state(
        {
            "llm_profiles": [
                {"id": "profile_a", "label": "Profile A", "enabled": True},
                {"id": "profile_b", "label": "Profile B", "enabled": True},
            ],
            "default_ai_translation_profile_id": "profile_b",
        }
    )

    assert profile_state["entries"] == [
        ("Profile A", "profile_a"),
        ("Profile B", "profile_b"),
    ]
    assert profile_state["selected_profile_id"] == "profile_b"


def test_build_ai_translation_notes_include_persisted_token_usage() -> None:
    """
    @brief      Verify translation notes show one persisted token-usage summary.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    notes = ai_translation_state_service.build_ai_translation_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        source_chunks=[{"chunk_id": "chunk-0001"}],
        report={
            "translated_chunk_count": 1,
            "approved_chunk_count": 0,
            "warnings": [],
            "token_usage": {
                "input_tokens": 220,
                "output_tokens": 80,
                "total_tokens": 300,
                "usage_available": True,
            },
        },
        operation_state={
            "status": "completed",
            "metadata": {},
        },
        has_ai_profiles=True,
        language="en",
    )

    assert any("Input tokens: 220 | Output tokens: 80 | Total: 300" in note for note in notes)


# END OF FILE
