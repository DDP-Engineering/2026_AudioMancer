#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
@date 2026-04-05
@version 0.1.0
"""

# IMPORTS

from audiomancer.ui.pages.settings_page import SettingsPage


def test_settings_page_loads_and_builds_merged_settings(qtbot) -> None:
    page = SettingsPage()
    qtbot.addWidget(page)

    existing_settings = {
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [{"id": "kept"}],
    }

    page.load_settings({
        "language": "ro",
        "ui_text_scale": "large",
        "play_completion_beep": True,
    })

    assert page._language_combo.currentText() == "ro"
    assert page._ui_text_scale_combo.currentData() == "large"
    assert page._completion_beep_checkbox.isChecked() is True

    page._language_combo.setCurrentText("en")
    page._ui_text_scale_combo.setCurrentIndex(
        page._ui_text_scale_combo.findData("small")
    )
    page._completion_beep_checkbox.setChecked(False)

    rebuilt = page.build_settings(existing_settings)

    assert rebuilt["language"] == "en"
    assert rebuilt["ui_text_scale"] == "small"
    assert rebuilt["play_completion_beep"] is False
    assert rebuilt["llm_profiles"] == [{"id": "kept"}]


# END OF FILE
