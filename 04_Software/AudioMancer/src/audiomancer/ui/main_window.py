#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file main_window.py
@brief Minimal main window for the initial AudioMancer UI scaffold.
@details Provides a small Qt main window with a placeholder message so the
         application can be launched and validated end to end.
@author Eng. Dan Dumitru Pasare
@date 2026-04-04
@version 0.1.0
"""

# IMPORTS

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow

# CONSTANTS

WINDOW_TITLE = "AudioMancer"
WINDOW_WIDTH = 960
WINDOW_HEIGHT = 640
PLACEHOLDER_TEXT = "AudioMancer initial scaffold is running."

# PUBLIC API


class MainWindow(QMainWindow):
    """
    @brief Top-level application window for the initial AudioMancer shell.
    @details Hosts a placeholder central widget and establishes the first
             runnable desktop UI boundary for the project.
    @version 0.1.0
    """

    def __init__(self) -> None:
        """
        @brief Initialize the main window.
        @details Sets the window title, initial size, and placeholder central
                 widget used by the scaffold.
        @version 0.1.0
        """
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setCentralWidget(self._build_placeholder_label())

    # LOCAL HELPERS

    def _build_placeholder_label(self) -> QLabel:
        """
        @brief Build the placeholder label displayed in the main window.
        @return Configured Qt label instance.
        @version 0.1.0
        """
        label = QLabel(PLACEHOLDER_TEXT)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label


# END OF FILE
