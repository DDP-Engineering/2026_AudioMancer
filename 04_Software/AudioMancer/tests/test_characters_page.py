#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_characters_page.py
@brief Focused Qt tests for the AudioMancer Characters page.
@details Verifies discovery-page button enablement, evidence preview, and
         immediate profile-change emission for discovered characters.
@author Eng. Dan Dumitru Pasare
@date 2026-04-08
@version 0.1.0
"""

# IMPORTS

from audiomancer.ui.pages.characters_page import CharactersPage


def test_characters_page_locks_start_after_completed_discovery(qtbot) -> None:
    """
    @brief      Verify completed discovery disables start and keeps reset available.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    page = CharactersPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_character_state(
        profiles=[_profile_payload()],
        notes=["Completed."],
        selected_profile_id="profile-1",
        stage_status="completed",
        character_count=1,
        source_chunk_map={"chunk-0001": '"Hello there," said Alice.'},
        can_start=False,
        can_reset=True,
    )

    assert page._start_button.isEnabled() is False
    assert page._reset_button.isEnabled() is True
    assert page._character_list.count() == 1


def test_characters_page_renders_evidence_preview(qtbot) -> None:
    """
    @brief      Verify selected evidence shows the stored source chunk text.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    page = CharactersPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_character_state(
        profiles=[_profile_payload()],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="in_progress",
        character_count=1,
        source_chunk_map={"chunk-0001": '"Hello there," said Alice.'},
        can_start=True,
        can_reset=True,
    )

    assert page._evidence_list.count() == 1
    assert page._evidence_preview.toPlainText() == '"Hello there," said Alice.'


def test_characters_page_emits_profile_changes_immediately(qtbot) -> None:
    """
    @brief      Verify editor changes emit one updated character payload immediately.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    page = CharactersPage()
    qtbot.addWidget(page)
    emitted = []
    page.profile_changed.connect(lambda payload: emitted.append(payload))
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_character_state(
        profiles=[_profile_payload()],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="in_progress",
        character_count=1,
        source_chunk_map={"chunk-0001": '"Hello there," said Alice.'},
        can_start=True,
        can_reset=True,
    )

    page._description_edit.setPlainText("Updated description")

    assert emitted
    assert emitted[-1]["character_id"] == "alice"
    assert emitted[-1]["description"] == "Updated description"


def _profile_payload() -> dict[str, object]:
    return {
        "character_id": "alice",
        "canonical_name": "Alice",
        "aliases": ["Al"],
        "gender_hint": "",
        "age_band": "",
        "role_summary": "Lead speaker",
        "description": "Original description",
        "temperament": "",
        "social_status": "",
        "speaking_style": "",
        "accent_or_dialect_hints": "",
        "voice_notes": "",
        "relationship_hints": ["Knows Bob."],
        "confidence": "high",
        "evidence": [
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "source_excerpt": '"Hello there," said Alice.',
                "reason": "Alice speaks.",
            }
        ],
        "updated_at": "2026-04-08T12:01:00+00:00",
    }


# END OF FILE
