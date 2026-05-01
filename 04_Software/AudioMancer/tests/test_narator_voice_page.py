#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_narator_voice_page.py
@brief Narator Voice page tests for AudioMancer.
@details Verifies the simplified Narator Voice page layout, edit-mode behavior,
         sample-dependent button enablement, and bottom status rendering.
@author Eng. Dan Dumitru Pasare
@date 2026-04-18
@version 3.3.9
"""

# IMPORTS

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit

from audiomancer.ui.pages.narator_voice_page import NaratorVoicePage


def test_narator_voice_page_uses_single_line_profile_name_and_no_summary_label(qtbot) -> None:
    """
    @brief      Verify the profile-name editor is single-line and the old subtitle label is gone.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    page = NaratorVoicePage()
    qtbot.addWidget(page)

    assert isinstance(page._profile_name_edit, QLineEdit)
    assert hasattr(page, "_summary_label") is False


def test_narator_voice_page_main_splitter_keeps_configured_minimum_widths(qtbot) -> None:
    """
    @brief      Verify Narator Voice main panes keep configured minimum splitter widths.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-01
    @version    0.2.0
    """
    page = NaratorVoicePage()
    qtbot.addWidget(page)
    page._main_splitter.resize(900, 600)
    page._apply_main_splitter_minimums()

    assert page._main_splitter.childrenCollapsible() is False
    assert page._profiles_group.minimumWidth() == 225
    assert page._editor_container.minimumWidth() == 300


def test_narator_voice_page_prompt_and_preview_editors_expose_scrollbars_and_limit(qtbot) -> None:
    """
    @brief      Verify narrator prompt and preview editors use scrollbars and enforce preview text length.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.3.1
    """
    page = NaratorVoicePage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_narator_voice_state(
        profiles=[
            {
                "profile_id": "custom_1",
                "display_name": "Custom One",
                "prompt_text": "Custom prompt.",
                "preview_text": "abcdef",
                "profile_kind": "custom",
                "editable": True,
                "is_selected": False,
            }
        ],
        notes=[],
        current_profile_id="custom_1",
        selected_profile_id=None,
        effective_language="en",
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="Unknown",
        translated_language="Not translated",
        profile_name="Custom One",
        prompt_text="Custom prompt.",
        preview_text="abcdef",
        is_editable=True,
        is_preset=False,
        can_edit=True,
        can_delete=True,
        can_generate=True,
        can_select=False,
        preview_available=False,
        status_lines=[],
        preview_text_character_limit=5,
    )

    assert page._designer_prompt.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    assert page._preview_text_edit.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    assert page._designer_prompt.minimumHeight() == 52
    assert page._designer_prompt.maximumHeight() == 72
    assert page._designer_group.maximumHeight() == 132
    assert page._preview_text_edit.minimumHeight() == 88
    assert page._preview_text_edit.maximumHeight() == 116
    assert page._preview_group.maximumHeight() == 184
    assert page._status_group.minimumHeight() == 96
    assert page._status_group.maximumHeight() == 112
    assert page._preview_text_edit.toPlainText() == "abcde"

    page.begin_edit_mode()
    page._preview_text_edit.setPlainText("123456789")

    assert page._preview_text_edit.toPlainText() == "12345"
    assert page.current_editor_payload()["preview_text"] == "12345"


def test_narator_voice_page_edit_mode_disables_list_and_enables_save_after_changes(qtbot) -> None:
    """
    @brief      Verify edit mode disables the profile list and enables Save immediately.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.2.0
    """
    page = NaratorVoicePage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_narator_voice_state(
        profiles=[
            {
                "profile_id": "custom_1",
                "display_name": "Custom One",
                "prompt_text": "Custom prompt.",
                "preview_text": "Preview text.",
                "profile_kind": "custom",
                "editable": True,
                "is_selected": False,
            }
        ],
        notes=["Custom selected."],
        current_profile_id="custom_1",
        selected_profile_id=None,
        effective_language="en",
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="Unknown",
        translated_language="Not translated",
        profile_name="Custom One",
        prompt_text="Custom prompt.",
        preview_text="Preview text.",
        is_editable=True,
        is_preset=False,
        can_edit=True,
        can_delete=True,
        can_generate=True,
        can_select=False,
        preview_available=False,
        status_lines=["Profiles: 1"],
    )

    page.begin_edit_mode()

    assert page.is_edit_mode() is True
    assert page._profile_list.isEnabled() is False
    assert page._profile_name_edit.isReadOnly() is False
    assert page._designer_prompt.isReadOnly() is False
    assert page._save_profile_button.isEnabled() is True


def test_narator_voice_page_preview_toggle_updates_label_and_select_enablement(qtbot) -> None:
    """
    @brief      Verify preview playback changes the button label and sample availability gates Select.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.1
    """
    page = NaratorVoicePage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.apply_language("en")
    page.set_narator_voice_state(
        profiles=[
            {
                "profile_id": "preset_1",
                "display_name": "Vivian",
                "prompt_text": "Preset prompt.",
                "preview_text": "Preview text.",
                "profile_kind": "preset",
                "editable": True,
                "is_selected": False,
            }
        ],
        notes=["Ready."],
        current_profile_id="preset_1",
        selected_profile_id=None,
        effective_language="en",
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="Unknown",
        translated_language="Not translated",
        profile_name="Vivian",
        prompt_text="Preset prompt.",
        preview_text="Preview text.",
        is_editable=True,
        is_preset=True,
        can_edit=True,
        can_delete=False,
        can_generate=True,
        can_select=True,
        preview_available=True,
        status_lines=["Profiles: 1"],
    )

    assert page._select_profile_button.isEnabled() is True
    page.set_preview_active(True)
    assert page._preview_toggle_button.text() == "Stop play"


def test_narator_voice_page_status_panel_and_language_labels_render_state(qtbot) -> None:
    """
    @brief      Verify Narator Voice status lines and read-only language labels are rendered on the page.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    page = NaratorVoicePage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_narator_voice_state(
        profiles=[],
        notes=["Ready."],
        current_profile_id=None,
        selected_profile_id=None,
        effective_language="ro",
        selected_voice_language="ro",
        language_entries=[("Romanian", "ro")],
        original_language="Italian",
        translated_language="Romanian",
        profile_name="",
        prompt_text="",
        preview_text="",
        is_editable=False,
        is_preset=False,
        can_edit=False,
        can_delete=False,
        can_generate=False,
        can_select=False,
        preview_available=False,
        status_lines=["Profiles: 3", "Profiles with samples: 1"],
    )

    assert page._original_language_group.title() == "Original language"
    assert page._translated_language_group.title() == "Translated language"
    assert page._voice_language_group.title() == "Voice language"
    assert page._original_language_value_label.text() == "Italian"
    assert page._translated_language_value_label.text() == "Romanian"
    assert page.current_voice_language() == "ro"
    assert "Profiles: 3" in page._status_edit.toPlainText()


# END OF FILE
