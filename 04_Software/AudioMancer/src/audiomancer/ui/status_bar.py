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
@version 0.3.0
"""

# IMPORTS

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton, QStatusBar

from audiomancer.services import ui_state_service


# PUBLIC API


class AudiomancerStatusBar(QStatusBar):
    """
    @brief      Status bar used by the AudioMancer main window.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.3.0
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
        self._current_language = "en"
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
        @version    0.2.0
        """
        stage_text = stage_name or ui_state_service.translate(
            "status.idle", self._current_language
        )
        self._stage_label.setText(
            f"{ui_state_service.translate('status.stage_prefix', self._current_language)}: {stage_text}"
        )

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the status-bar static labels.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.2.0
        """
        self._current_language = language
        self._stop_button.setText(
            ui_state_service.translate("status.stop_ai", language)
        )
        stage_text = self._stage_label.text().split(":", maxsplit=1)
        current_stage = stage_text[1].strip() if len(stage_text) == 2 else ""
        if current_stage in ("idle", "inactiva"):
            current_stage = ui_state_service.translate("status.idle", language)
        self._stage_label.setText(
            f"{ui_state_service.translate('status.stage_prefix', language)}: {current_stage}"
        )


# END OF FILE
