#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_main_window.py
@brief Qt window tests for the AudioMancer scaffold.
@details Validates that the initial main window can be instantiated and shown.
@author Eng. Dan Dumitru Pasare
@date 2026-04-04
@version 0.1.0
"""

# IMPORTS

from audiomancer.ui.main_window import MainWindow

# PUBLIC API


def test_main_window_can_be_created(qtbot) -> None:
    """
    @brief      Verify the main window can be created in a Qt test context.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "AudioMancer"
    assert window.centralWidget() is not None


# END OF FILE