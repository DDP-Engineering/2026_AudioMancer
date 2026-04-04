#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file app.py
@brief Desktop application bootstrap for AudioMancer.
@details Creates the Qt application instance, opens the main window, and
         starts the event loop for the initial UI scaffold.
@author Eng. Dan Dumitru Pasare
@date 2026-04-04
@version 0.1.0
@example
    uv run audiomancer
"""

# IMPORTS

import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow

# CONSTANTS

APPLICATION_NAME = "AudioMancer"

# PUBLIC API


def main() -> int:
    """
    @brief      Start the AudioMancer desktop application.
    @return     Process exit code returned by QApplication.exec().
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    application = QApplication(sys.argv)
    application.setApplicationName(APPLICATION_NAME)

    window = MainWindow()
    window.show()

    return application.exec()


# END OF FILE