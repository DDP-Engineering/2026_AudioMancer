#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_settings_page.py
@brief Focused tests for the AudioMancer settings page.
@details Verifies settings-page widget loading and merged settings payload
         generation for the operator-facing settings dialog.
@author Eng. Dan Dumitru Pasare
@date 2026-05-14
@version 0.6.1
"""

# IMPORTS

from PySide6.QtGui import QFont

from audiomancer import config
from audiomancer.services import ui_theme_service
from audiomancer.ui.pages.settings_page import SettingsPage


def test_settings_page_loads_and_builds_merged_settings(qtbot) -> None:
    """
    @brief      Verify the settings page loads and rebuilds persisted values.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.3.1
    """
    page = SettingsPage()
    qtbot.addWidget(page)

    existing_settings = {
        "language": "en",
        "ui_theme_id": config.DEFAULT_UI_THEME_ID,
        "ui_themes": [],
        "play_completion_beep": False,
        "ui_scroll_steps_per_wheel_notch": 1,
        "llm_profiles": [{"id": "kept"}],
    }

    page.load_settings(
        {
            "language": "ro",
            "ui_theme_id": config.DEFAULT_UI_THEME_ID,
            "ui_themes": [],
            "play_completion_beep": True,
            "ui_scroll_steps_per_wheel_notch": 4,
        }
    )

    assert page._language_combo.currentText() == "ro"
    assert page._language_combo.minimumWidth() >= 96
    assert page._completion_beep_checkbox.isChecked() is True
    assert page._scroll_steps_spin.value() == 4

    page._language_combo.setCurrentText("en")
    page._completion_beep_checkbox.setChecked(False)
    page._scroll_steps_spin.setValue(2)

    rebuilt = page.build_settings(existing_settings)

    assert rebuilt["language"] == "en"
    assert "ui_text_scale" not in rebuilt
    assert rebuilt["ui_theme_id"] == config.DEFAULT_UI_THEME_ID
    assert rebuilt["ui_themes"] == []
    assert rebuilt["play_completion_beep"] is False
    assert rebuilt["ui_scroll_steps_per_wheel_notch"] == 2
    assert rebuilt["llm_profiles"] == [{"id": "kept"}]


def test_settings_page_loads_selected_built_in_theme_and_disables_delete(qtbot) -> None:
    """
    @brief      Verify built-in theme selection loads and remains protected from deletion.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.2.0
    """
    page = SettingsPage()
    qtbot.addWidget(page)

    page.load_settings(
        {
            "language": "en",
            "ui_text_scale": "normal",
            "ui_theme_id": "warm_reading",
            "ui_themes": [],
            "play_completion_beep": False,
        }
    )

    assert page._theme_combo.currentData() == "warm_reading"
    assert page._theme_delete_button.isEnabled() is False
    assert page._theme_name_edit.isEnabled() is False


def test_settings_page_creates_custom_theme_in_built_payload(qtbot) -> None:
    """
    @brief      Verify creating a theme adds an editable custom theme to settings output.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    page.load_settings({"language": "en", "ui_text_scale": "normal", "ui_theme_id": "classic_light", "ui_themes": []})

    page._create_custom_theme()
    rebuilt = page.build_settings({"language": "en"})

    assert rebuilt["ui_theme_id"] == "custom_theme"
    assert len(rebuilt["ui_themes"]) == 1
    assert rebuilt["ui_themes"][0]["display_name"] == "Custom Theme"
    assert rebuilt["ui_themes"][0]["built_in"] is False


def test_settings_page_deletes_custom_theme_and_selects_fallback(qtbot) -> None:
    """
    @brief      Verify deleting a custom theme removes it and falls back to the default theme.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    custom_theme = ui_theme_service.import_theme_payload(
        {
            "schema_version": config.UI_THEME_SCHEMA_VERSION,
            "theme_id": "reading_theme",
            "display_name": "Reading Theme",
            "built_in": False,
            "font": {},
            "colors": {},
        },
        [],
    )
    page = SettingsPage()
    qtbot.addWidget(page)
    page.load_settings(
        {
            "language": "en",
            "ui_text_scale": "normal",
            "ui_theme_id": "reading_theme",
            "ui_themes": [custom_theme],
        }
    )

    page._delete_selected_theme()
    rebuilt = page.build_settings({"language": "en"})

    assert rebuilt["ui_theme_id"] == config.DEFAULT_UI_THEME_ID
    assert rebuilt["ui_themes"] == []


def test_settings_page_persists_edited_custom_theme_font_and_color(qtbot) -> None:
    """
    @brief      Verify edited custom UI/text font and color values appear in built settings.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.3.0
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    page.load_settings({"language": "en", "ui_text_scale": "normal", "ui_theme_id": "classic_light", "ui_themes": []})
    page._create_custom_theme()

    page._theme_name_edit.setText("Studio Theme")
    page._theme_font_family_combo.setCurrentFont(QFont("Courier New"))
    page._theme_font_size_spin.setValue(12.5)
    page._theme_text_font_family_combo.setCurrentFont(QFont("Georgia"))
    page._theme_text_font_size_spin.setValue(14.0)
    page._set_color_button("accent", "#ABCDEF")
    page._editor_value_changed()

    rebuilt = page.build_settings({"language": "en"})
    custom_theme = rebuilt["ui_themes"][0]

    assert custom_theme["display_name"] == "Studio Theme"
    assert custom_theme["font"]["family"] == "Courier New"
    assert custom_theme["font"]["point_size"] == 12.5
    assert custom_theme["font"]["scale"] == config.DEFAULT_UI_TEXT_SCALE
    assert custom_theme["text_font"]["family"] == "Georgia"
    assert custom_theme["text_font"]["point_size"] == 14.0
    assert custom_theme["text_font"]["scale"] == config.DEFAULT_UI_TEXT_SCALE
    assert custom_theme["colors"]["accent"] == "#ABCDEF"


def test_settings_page_imports_theme_payload_into_draft(qtbot) -> None:
    """
    @brief      Verify imported theme payloads become selected custom themes in settings output.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    page.load_settings({"language": "en", "ui_text_scale": "normal", "ui_theme_id": "classic_light", "ui_themes": []})
    imported_payload = {
        "schema_version": config.UI_THEME_SCHEMA_VERSION,
        "theme_id": "portable_theme",
        "display_name": "Portable Theme",
        "built_in": True,
        "font": {"family": "", "point_size": None, "scale": "small"},
        "colors": {"accent": "#123ABC"},
    }

    imported_theme = page.add_imported_theme_payload(imported_payload)
    rebuilt = page.build_settings({"language": "en"})

    assert imported_theme["theme_id"] == "portable_theme"
    assert imported_theme["built_in"] is False
    assert rebuilt["ui_theme_id"] == "portable_theme"
    assert rebuilt["ui_themes"][0]["theme_id"] == imported_theme["theme_id"]
    assert rebuilt["ui_themes"][0]["font"]["scale"] == config.DEFAULT_UI_TEXT_SCALE


def test_settings_page_exports_selected_built_in_as_portable_payload(qtbot) -> None:
    """
    @brief      Verify selected built-in themes export as portable custom-safe JSON payloads.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    page.load_settings({"language": "en", "ui_text_scale": "normal", "ui_theme_id": "warm_reading", "ui_themes": []})

    export_payload = page.selected_theme_export_payload()
    export_file_name = page.selected_theme_export_file_name()

    assert export_payload["theme_id"] == "warm_reading"
    assert export_payload["built_in"] is False
    assert export_file_name == "AudioMancer_warm_reading_theme.json"


# END OF FILE
