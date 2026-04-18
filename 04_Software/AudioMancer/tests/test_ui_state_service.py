#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ui_state_service.py
@brief Focused tests for the runtime UI-state service.
@details Verifies translated string lookup and application-wide text-scale
         changes used by the settings-backed runtime UI behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.1.0
"""

# IMPORTS

from PySide6.QtWidgets import QApplication

from audiomancer.services import ui_state_service


def test_translate_returns_expected_english_and_romanian_strings() -> None:
    """
    @brief      Verify the UI string catalog resolves EN and RO labels.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    assert ui_state_service.translate("toolbar.settings", "en") == "Settings"
    assert ui_state_service.translate("toolbar.settings", "ro") == "Setari"
    assert ui_state_service.translate("sidebar.text_chunking", "ro") == "Segmentare Text"


def test_apply_text_scale_updates_application_font(qtbot) -> None:
    """
    @brief      Verify one UI text-scale preset updates the application font.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    application = QApplication.instance()
    ui_state_service.apply_text_scale(application, "normal")
    normal_size = application.font().pointSizeF()

    ui_state_service.apply_text_scale(application, "very_large")
    large_size = application.font().pointSizeF()

    assert large_size > normal_size


# END OF FILE
