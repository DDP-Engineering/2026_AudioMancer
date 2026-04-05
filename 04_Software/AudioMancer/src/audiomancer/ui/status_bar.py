#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file status_bar.py
@brief Status bar widget for AudioMancer.
@details Copies the shell status-bar structure used by DDP_Audiomancer so the
         first AudioMancer window matches the same layout.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.1.0
"""

# IMPORTS

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton, QStatusBar


# PUBLIC API


class AudiomancerStatusBar(QStatusBar):
    """
    @brief      Status bar used by the AudioMancer main window.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """

    stop_requested = Signal()

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the status bar widgets.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        super().__init__(parent)
        self._activity_label = QLabel("")
        self._activity_label.setMinimumWidth(190)
        self._progress_bar = QProgressBar(self)
        self._progress_bar.setMinimumWidth(340)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setStyleSheet("QProgressBar { min-height: 22px; }")
        self._progress_bar.setVisible(False)
        self._stop_button = QPushButton("Stop AI", self)
        self._stop_button.clicked.connect(self.stop_requested.emit)
        self._stop_button.setVisible(False)
        self._stage_label = QLabel("Stage: idle")
        self.addPermanentWidget(self._activity_label)
        self.addPermanentWidget(self._progress_bar)
        self.addPermanentWidget(self._stop_button)
        self.addPermanentWidget(self._stage_label)

    def set_stage(self, stage_name: str | None) -> None:
        """
        @brief      Update the workflow-stage label.
        @param[in]  stage_name Active workflow stage name or `None`.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        self._stage_label.setText(f"Stage: {stage_name or 'idle'}")


# END OF FILE
