#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_character_voices_page.py
@brief Character Voices page tests for AudioMancer.
@details Verifies preview-only Narator Voice behavior, explicit edit mode, and
         bottom status rendering for the Character Voices page.
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 1.3.1
"""

# IMPORTS

from audiomancer.ui.pages.character_voices_page import CharacterVoicesPage


def test_character_voices_page_narrator_target_is_preview_only(qtbot) -> None:
    """
    @brief      Verify the Narator Voice row is preview-only when a sample exists.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.1
    """
    page = CharacterVoicesPage()
    qtbot.addWidget(page)
    page.apply_language("en")
    page.set_project_active(True)
    page.set_character_voices_state(
        targets=[
            {
                "target_id": "narrator",
                "target_kind": "narrator",
                "display_name": "Narator Voice",
                "sample_status_label": "Sample present",
                "has_sample": True,
            }
        ],
        notes=["Ready."],
        current_target_id="narrator",
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="English",
        translated_language="Not translated",
        assignment_mode_label="Narrator + character voices",
        target_name="Narator Voice",
        target_kind_label="Narator Voice",
        prompt_text="",
        preview_text="Narator Voice preview text.",
        is_editable=False,
        can_reset_prompt=False,
        can_edit_prompt=False,
        can_generate_sample=False,
        preview_available=True,
        status_lines=["Total targets: 1"],
        missing_narrator_sample=False,
    )

    assert page._reset_prompt_button.isEnabled() is False
    assert page._edit_prompt_button.isEnabled() is False
    assert page._generate_sample_button.isEnabled() is False
    assert page._preview_toggle_button.isEnabled() is True
    assert hasattr(page, "_target_name_edit") is False
    assert hasattr(page, "_target_kind_edit") is False


def test_character_voices_page_edit_mode_disables_list_and_enables_save_after_changes(qtbot) -> None:
    """
    @brief      Verify edit mode disables the target list and enables Save after prompt changes.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    page = CharacterVoicesPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_character_voices_state(
        targets=[
            {
                "target_id": "character_alice",
                "target_kind": "character",
                "display_name": "Alice",
                "sample_status_label": "Sample missing",
                "has_sample": False,
            }
        ],
        notes=["Ready."],
        current_target_id="character_alice",
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="English",
        translated_language="Not translated",
        assignment_mode_label="Narrator + character voices",
        target_name="Alice",
        target_kind_label="Character",
        prompt_text="Original prompt.",
        preview_text="Line one.\nLine two.",
        is_editable=True,
        can_reset_prompt=True,
        can_edit_prompt=True,
        can_generate_sample=True,
        preview_available=False,
        status_lines=["Total targets: 1"],
        missing_narrator_sample=False,
    )

    page.begin_edit_mode()
    page._prompt_edit.setPlainText("Changed prompt.")

    assert page.is_edit_mode() is True
    assert page._target_list.isEnabled() is False
    assert page._prompt_edit.isReadOnly() is False
    assert page._preview_text_edit.isReadOnly() is False
    assert page._save_prompt_button.isEnabled() is True


def test_character_voices_page_editor_payload_includes_preview_text(qtbot) -> None:
    """
    @brief      Verify the Character Voices editor payload includes the editable preview text.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    page = CharacterVoicesPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_character_voices_state(
        targets=[
            {
                "target_id": "character_alice",
                "target_kind": "character",
                "display_name": "Alice",
                "sample_status_label": "Sample missing",
                "has_sample": False,
            }
        ],
        notes=["Ready."],
        current_target_id="character_alice",
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="English",
        translated_language="Not translated",
        assignment_mode_label="Narrator + character voices",
        target_name="Alice",
        target_kind_label="Character",
        prompt_text="Original prompt.",
        preview_text="Line one.\nLine two.",
        is_editable=True,
        can_reset_prompt=True,
        can_edit_prompt=True,
        can_generate_sample=True,
        preview_available=False,
        status_lines=["Total targets: 1"],
        missing_narrator_sample=False,
    )

    assert page.current_editor_payload()["preview_text"] == "Line one.\nLine two."


def test_character_voices_page_header_indicators_render_languages_and_assignment_mode(qtbot) -> None:
    """
    @brief      Verify the boxed header indicators render original language, translated language, and assignment mode.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    page = CharacterVoicesPage()
    qtbot.addWidget(page)
    page.apply_language("en")
    page.set_project_active(True)
    page.set_character_voices_state(
        targets=[],
        notes=["Ready."],
        current_target_id=None,
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="Italian",
        translated_language="Romanian",
        assignment_mode_label="Narrator + character voices",
        target_name="",
        target_kind_label="",
        prompt_text="",
        preview_text="",
        is_editable=False,
        can_reset_prompt=False,
        can_edit_prompt=False,
        can_generate_sample=False,
        preview_available=False,
        status_lines=["Total targets: 0"],
        missing_narrator_sample=False,
    )

    assert page._original_language_group.title() == "Original language"
    assert page._translated_language_group.title() == "Translated language"
    assert page._assignment_mode_group.title() == "Voice assignment"
    assert page._voice_language_group.title() == "Voice language"
    assert page._original_language_value_label.text() == "Italian"
    assert page._translated_language_value_label.text() == "Romanian"
    assert page._assignment_mode_value_label.text() == "Narrator + character voices"


# END OF FILE

