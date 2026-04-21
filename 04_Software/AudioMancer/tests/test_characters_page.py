#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_characters_page.py
@brief Focused Qt tests for the AudioMancer Characters page.
@details Verifies guarded edit mode, manual draft mode, selection-change
         signaling, and evidence preview behavior for discovered characters.
@author Eng. Dan Dumitru Pasare
@date 2026-04-08
@version 0.4.0
"""

# IMPORTS

from audiomancer.services import character_discovery_service
from audiomancer.ui.pages.characters_page import CharactersPage


def test_characters_page_fields_are_read_only_by_default(qtbot) -> None:
    page = _build_page(qtbot)

    assert page._edit_character_button.isEnabled() is True
    assert page._save_character_button.isEnabled() is False
    assert page._canonical_name_edit.isReadOnly() is True
    assert page._description_edit.isReadOnly() is True


def test_characters_page_edit_mode_enables_save_after_change(qtbot) -> None:
    page = _build_page(qtbot)

    page.begin_edit_mode()

    assert page._canonical_name_edit.isReadOnly() is False
    assert page._save_character_button.isEnabled() is True

    page._description_edit.setPlainText("Updated description")

    assert page.is_edit_mode() is True
    assert page.is_dirty() is True
    assert page._save_character_button.isEnabled() is True


def test_characters_page_save_without_changes_exits_edit_mode(qtbot) -> None:
    page = _build_page(qtbot)
    requested_payloads = []
    page.save_character_requested.connect(lambda payload: requested_payloads.append(payload))

    page.begin_edit_mode()
    page._emit_save_character()

    assert page.is_edit_mode() is False
    assert page.is_dirty() is False
    assert requested_payloads == []


def test_characters_page_add_mode_creates_draft_row_and_manual_evidence(qtbot) -> None:
    page = _build_page(qtbot)

    page.begin_add_mode(_manual_draft_payload())

    assert page.is_add_mode() is True
    assert page.is_dirty() is True
    assert page._character_list.count() == 2
    assert page._character_list.currentItem().text() == "Manual Bob"
    assert page._save_character_button.isEnabled() is True
    assert page._evidence_preview.toPlainText() == (character_discovery_service.MANUAL_CHARACTER_EVIDENCE_NOTE)


def test_characters_page_selection_change_emits_requested_character_id(qtbot) -> None:
    page = _build_page(qtbot, profiles=[_profile_payload(), _second_profile_payload()])
    requested = []
    page.selection_change_requested.connect(lambda payload: requested.append(payload))

    page.begin_edit_mode()
    page._description_edit.setPlainText("Updated description")
    page._character_list.setCurrentRow(1)

    assert requested == ["bob"]
    assert page.current_character_id() == "alice"


def test_characters_page_marks_voice_definition_stale_when_facts_change(qtbot) -> None:
    page = _build_page(qtbot)

    page.begin_edit_mode()
    page._description_edit.setPlainText("Updated literary description")

    assert page.current_draft_payload()["voice_definition_stale"] is True
    assert "stale" in page._voice_definition_status_label.text().casefold()


def test_characters_page_regenerate_voice_definition_emits_current_draft(qtbot) -> None:
    page = _build_page(qtbot)
    requested_payloads = []
    page.regenerate_voice_definition_requested.connect(lambda payload: requested_payloads.append(payload))

    page.begin_edit_mode()
    page._description_edit.setPlainText("Updated literary description")
    page._emit_regenerate_voice_definition()

    assert len(requested_payloads) == 1
    assert requested_payloads[0]["description"] == "Updated literary description"
    assert "voice_definition_prompt" in requested_payloads[0]


def _build_page(qtbot, profiles=None) -> CharactersPage:
    page = CharactersPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_character_state(
        profiles=[_profile_payload()] if profiles is None else profiles,
        notes=["Completed."],
        selected_profile_id="profile-1",
        stage_status="completed",
        character_count=1 if profiles is None else len(profiles),
        source_chunk_map={
            "chunk-0001": '"Hello there," said Alice.',
            "manual": character_discovery_service.MANUAL_CHARACTER_EVIDENCE_NOTE,
        },
        can_start=False,
        can_reset=True,
        can_add=True,
        can_edit=True,
        can_save=False,
        can_delete=True,
        edit_mode=False,
        dirty=False,
    )
    return page


def _profile_payload() -> dict[str, object]:
    return character_discovery_service.regenerate_character_voice_definition(
        {
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
    )


def _second_profile_payload() -> dict[str, object]:
    payload = dict(_profile_payload())
    payload["character_id"] = "bob"
    payload["canonical_name"] = "Bob"
    payload["role_summary"] = "Supporting speaker"
    return payload


def _manual_draft_payload() -> dict[str, object]:
    return character_discovery_service.regenerate_character_voice_definition(
        {
            "character_id": "draft_manual_bob",
            "canonical_name": "Manual Bob",
            "aliases": [],
            "gender_hint": "",
            "age_band": "",
            "role_summary": "",
            "description": "",
            "temperament": "",
            "social_status": "",
            "speaking_style": "",
            "accent_or_dialect_hints": "",
            "voice_notes": "",
            "relationship_hints": [],
            "confidence": "",
            "evidence": [
                {
                    "chunk_id": "manual",
                    "sequence_index": 0,
                    "source_excerpt": character_discovery_service.MANUAL_CHARACTER_EVIDENCE_NOTE,
                    "reason": character_discovery_service.MANUAL_CHARACTER_EVIDENCE_NOTE,
                }
            ],
            "updated_at": None,
        }
    )


# END OF FILE
