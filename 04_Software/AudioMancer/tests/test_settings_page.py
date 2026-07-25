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
@brief Focused tests for the simplified AudioMancer settings (Appearance) page.
@details Verifies theme selection, interface/text font-size step selectors, merged
         settings output, and the removal of the color/custom-theme editor.
@author Eng. Dan Dumitru Pasare
@date 2026-07-25
@version 0.7.0
"""

# IMPORTS

from audiomancer import config
from audiomancer.ui.pages.settings_page import SettingsPage

# PUBLIC API


def test_settings_page_loads_and_builds_merged_settings(qtbot) -> None:
    """
    @brief      Verify the settings page loads and rebuilds persisted values.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.4.0
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
            "ui_font_size_step": "large",
            "text_font_size_step": "very_large",
        }
    )

    assert page._language_combo.currentText() == "ro"
    assert page._language_combo.minimumWidth() >= 96
    assert page._completion_beep_checkbox.isChecked() is True
    assert page._scroll_steps_spin.value() == 4
    assert page._ui_font_size_combo.currentData() == "large"
    assert page._text_font_size_combo.currentData() == "very_large"

    page._language_combo.setCurrentText("en")
    page._completion_beep_checkbox.setChecked(False)
    page._scroll_steps_spin.setValue(2)

    rebuilt = page.build_settings(existing_settings)

    assert rebuilt["language"] == "en"
    assert "ui_text_scale" not in rebuilt
    assert rebuilt["ui_theme_id"] == config.DEFAULT_UI_THEME_ID
    assert rebuilt["play_completion_beep"] is False
    assert rebuilt["ui_scroll_steps_per_wheel_notch"] == 2
    assert rebuilt["ui_font_size_step"] == "large"
    assert rebuilt["text_font_size_step"] == "very_large"
    assert rebuilt["llm_profiles"] == [{"id": "kept"}]


def test_settings_page_theme_selector_loads_and_persists(qtbot) -> None:
    """
    @brief      Verify the theme selector reflects the loaded id and persists a new choice.
    @details    Covers REQ-UX-8e33d3cf-f881-4dbb-86d2-2f97f05b0669 / SPEC-SET-THEME.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    page.load_settings({"language": "en", "ui_theme_id": "warm_reading"})

    assert page._theme_combo.currentData() == "warm_reading"

    high_contrast_index = page._theme_combo.findData("high_contrast")
    assert high_contrast_index >= 0
    page._theme_combo.setCurrentIndex(high_contrast_index)

    rebuilt = page.build_settings({"language": "en"})
    assert rebuilt["ui_theme_id"] == "high_contrast"


def test_settings_page_interface_font_size_selector_persists(qtbot) -> None:
    """
    @brief      Verify the interface font-size selector loads and persists a step.
    @details    Covers REQ-UX-bcc4485f-102b-4e39-9f48-c5bde30b99f3 / SPEC-SET-UIFONT.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    page.load_settings({"language": "en", "ui_font_size_step": "small"})

    assert page._ui_font_size_combo.currentData() == "small"
    assert page._ui_font_size_combo.count() == len(config.UI_FONT_SIZE_STEPS)

    page._ui_font_size_combo.setCurrentIndex(page._ui_font_size_combo.findData("huge"))
    rebuilt = page.build_settings({"language": "en"})
    assert rebuilt["ui_font_size_step"] == "huge"


def test_settings_page_text_font_size_selector_persists(qtbot) -> None:
    """
    @brief      Verify the text-window font-size selector loads and persists a step.
    @details    Covers REQ-UX-a3f0f73c-54ea-4ddd-9ec7-4ab8a84d57b1 / SPEC-SET-TEXTFONT.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    page.load_settings({"language": "en", "text_font_size_step": "medium"})

    assert page._text_font_size_combo.currentData() == "medium"
    assert page._text_font_size_combo.count() == len(config.UI_FONT_SIZE_STEPS)

    page._text_font_size_combo.setCurrentIndex(page._text_font_size_combo.findData("extra_small"))
    rebuilt = page.build_settings({"language": "en"})
    assert rebuilt["text_font_size_step"] == "extra_small"


# END OF FILE
