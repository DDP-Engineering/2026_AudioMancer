#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
@version 0.8.9
"""

# IMPORTS

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor

from audiomancer.services import character_discovery_service
from audiomancer.ui.pages.characters_page import CharactersPage


def test_characters_page_fields_are_read_only_by_default(qtbot) -> None:
    """
    @brief      Validate characters page fields are read only by default.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.6.2
    """
    page = _build_page(qtbot)

    assert page._edit_character_button.isEnabled() is True
    assert page._save_character_button.isEnabled() is False
    assert page._canonical_name_edit.isReadOnly() is True
    assert page._gender_confidence_edit.isReadOnly() is True
    assert page._age_hint_edit.isReadOnly() is True
    assert page._age_confidence_edit.isReadOnly() is True
    assert page._voice_definition_prompt_edit.isReadOnly() is True
    assert page._gender_hint_edit.parentWidget() == page._gender_row_widget
    assert page._gender_confidence_edit.parentWidget() == page._gender_row_widget
    assert page._age_hint_edit.parentWidget() == page._age_row_widget
    assert page._age_confidence_edit.parentWidget() == page._age_row_widget
    assert page._gender_row_widget.maximumHeight() == 30
    assert page._age_row_widget.maximumHeight() == 30
    assert page._gender_row_widget.layout().stretch(page._gender_row_widget.layout().count() - 1) == 1
    assert page._age_row_widget.layout().stretch(page._age_row_widget.layout().count() - 1) == 1
    assert page._gender_confidence_label.minimumWidth() == page._age_confidence_label.minimumWidth()
    assert page._gender_confidence_label.maximumWidth() == page._age_confidence_label.maximumWidth()
    assert page._gender_hint_edit.maximumWidth() == 360
    assert page._age_hint_edit.maximumWidth() == 360
    assert page._list_group.minimumHeight() == page._list_group.maximumHeight()
    assert page._list_group.minimumHeight() > page._character_actions_widget.sizeHint().height()
    assert hasattr(page, "_summary_label") is False
    assert page._evidence_splitter.orientation() == Qt.Orientation.Vertical
    assert page._evidence_splitter.count() == 2
    assert page._status_edit.toPlainText() == "Completed."


def test_characters_page_evidence_splitter_keeps_twenty_percent_minimums(qtbot) -> None:
    """
    @brief      Verify Evidence list and preview keep a twenty-percent splitter minimum.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.2.0
    """
    page = _build_page(qtbot)

    page._evidence_splitter.resize(320, 500)
    page._apply_evidence_splitter_minimums()

    assert page._evidence_list.minimumHeight() == 100
    assert page._evidence_preview.minimumHeight() == 100

    page._evidence_splitter.setSizes([1, 499])
    page._clamp_evidence_splitter_sizes()
    top_size, bottom_size = page._evidence_splitter.sizes()

    assert top_size >= (top_size + bottom_size) // 5

    page._evidence_splitter.setSizes([499, 1])
    page._clamp_evidence_splitter_sizes()
    top_size, bottom_size = page._evidence_splitter.sizes()

    assert bottom_size >= (top_size + bottom_size) // 5


def test_characters_page_edit_mode_enables_save_after_change(qtbot) -> None:
    """
    @brief      Validate characters page edit mode enables save after change.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.2.0
    """
    page = _build_page(qtbot)

    page.begin_edit_mode()

    assert page._canonical_name_edit.isReadOnly() is False
    assert page._gender_confidence_edit.isReadOnly() is False
    assert page._age_hint_edit.isReadOnly() is False
    assert page._age_confidence_edit.isReadOnly() is False
    assert page._save_character_button.isEnabled() is True

    page._voice_definition_prompt_edit.setPlainText("Updated voice prompt")

    assert page.is_edit_mode() is True
    assert page.is_dirty() is True
    assert page._save_character_button.isEnabled() is True


def test_characters_page_demographic_fields_load_and_save(qtbot) -> None:
    """
    @brief      Verify demographic editors load and emit draft payload changes.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.2.0
    """
    page = _build_page(qtbot)
    requested_payloads = []
    page.save_character_requested.connect(lambda payload: requested_payloads.append(payload))

    assert page._gender_hint_edit.text() == "female"
    assert page._gender_confidence_edit.text() == "high"
    assert page._age_hint_edit.text() == "adult"
    assert page._age_confidence_edit.text() == "medium"

    page.begin_edit_mode()
    page._gender_confidence_edit.setText("medium")
    page._age_hint_edit.setText("old")
    page._age_confidence_edit.setText("high")
    page._emit_save_character()

    assert requested_payloads[0]["gender_confidence"] == "medium"
    assert requested_payloads[0]["age_hint"] == "old"
    assert requested_payloads[0]["age_confidence"] == "high"


def test_characters_page_save_without_changes_exits_edit_mode(qtbot) -> None:
    """
    @brief      Validate characters page save without changes exits edit mode.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    page = _build_page(qtbot)
    requested_payloads = []
    page.save_character_requested.connect(lambda payload: requested_payloads.append(payload))

    page.begin_edit_mode()
    page._emit_save_character()

    assert page.is_edit_mode() is False
    assert page.is_dirty() is False
    assert requested_payloads == []


def test_characters_page_add_mode_creates_draft_row_and_manual_evidence(qtbot) -> None:
    """
    @brief      Validate characters page add mode creates draft row and manual evidence.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    page = _build_page(qtbot)

    page.begin_add_mode(_manual_draft_payload())

    assert page.is_add_mode() is True
    assert page.is_dirty() is True
    assert page._character_list.count() == 2
    assert page._character_list.currentItem().text() == "Manual Bob"
    assert page._save_character_button.isEnabled() is True
    assert page._evidence_preview.toPlainText() == (character_discovery_service.MANUAL_CHARACTER_EVIDENCE_NOTE)


def test_characters_page_selection_change_emits_requested_character_id(qtbot) -> None:
    """
    @brief      Validate characters page selection change emits requested character id.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.3.0
    """
    page = _build_page(qtbot, profiles=[_profile_payload(), _second_profile_payload()])
    requested = []
    page.selection_change_requested.connect(lambda payload: requested.append(payload))

    page.begin_edit_mode()
    page._voice_definition_prompt_edit.setPlainText("Updated voice prompt")
    page._character_list.setCurrentRow(1)

    assert requested == ["bob"]
    assert page.current_character_id() == "alice"


def test_characters_page_evidence_preview_supports_find_next_wraparound(qtbot) -> None:
    """
    @brief      Validate characters page evidence preview supports find next wraparound.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    page = _build_page(qtbot)
    page._evidence_preview.setPlainText("Alice speaks.\nBob answers.\nAlice replies.")

    assert page._evidence_preview.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu

    cursor = page._evidence_preview.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    page._evidence_preview.setTextCursor(cursor)

    page._evidence_find_text_by_editor_id[id(page._evidence_preview)] = "Alice"
    page._find_next_evidence_text(page._evidence_preview)

    assert page._evidence_preview.textCursor().selectedText() == "Alice"


def _build_page(qtbot, profiles=None) -> CharactersPage:
    """
    @brief      Provide the build page test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
    """
    @brief      Provide the profile payload test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.2.0
    """
    return character_discovery_service.regenerate_character_voice_definition(
        {
            "character_id": "alice",
            "canonical_name": "Alice",
            "aliases": ["Al"],
            "gender_hint": "female",
            "gender_confidence": "high",
            "age_hint": "adult",
            "age_confidence": "medium",
            "voice_definition_prompt": "Create a consistent spoken voice for Alice.",
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
    """
    @brief      Provide the second profile payload test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.3.0
    """
    payload = dict(_profile_payload())
    payload["character_id"] = "bob"
    payload["canonical_name"] = "Bob"
    payload["voice_definition_prompt"] = "Create a consistent spoken voice for Bob."
    return payload


def _manual_draft_payload() -> dict[str, object]:
    """
    @brief      Provide the manual draft payload test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.2.0
    """
    return character_discovery_service.regenerate_character_voice_definition(
        {
            "character_id": "draft_manual_bob",
            "canonical_name": "Manual Bob",
            "aliases": [],
            "gender_hint": "",
            "gender_confidence": "",
            "age_hint": "",
            "age_confidence": "",
            "voice_definition_prompt": "Create a consistent spoken voice for Manual Bob.",
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
