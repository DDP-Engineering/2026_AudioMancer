#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file narrator_page.py
@brief Static narrator profile page for AudioMancer.
@details Provides the presentational shell for narrator voice profile
         selection, creation from description, and preview area without adding
         any functionality.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.1.0
"""

# IMPORTS

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# PUBLIC API


class NarratorPage(QWidget):
    """
    @brief      Render the static narrator profile configuration page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the narrator page shell.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Narrator</h2>"))

        selection_group = QGroupBox("Narrator Voice Profile", self)
        selection_layout = QVBoxLayout(selection_group)
        selection_layout.addWidget(QLabel(
            "Select one predefined narrator profile or prepare a new one from "
            "a written voice description."
        ))

        selector_row = QHBoxLayout()
        self._profile_selector = QComboBox(self)
        self._profile_selector.addItems((
            "Classic Neutral Narrator",
            "Warm Storyteller",
            "Documentary Voice",
            "Create New Profile From Description",
        ))
        selector_row.addWidget(QLabel("Profile:"))
        selector_row.addWidget(self._profile_selector, 1)
        selection_layout.addLayout(selector_row)

        description_label = QLabel("New Profile Description")
        selection_layout.addWidget(description_label)

        self._description_editor = QTextEdit(self)
        self._description_editor.setPlaceholderText(
            "Describe tone, cadence, age, accent, pacing, emotional range, "
            "and other narrator voice traits."
        )
        selection_layout.addWidget(self._description_editor)

        button_row = QHBoxLayout()
        button_row.addWidget(QPushButton("Create Profile", self))
        button_row.addWidget(QPushButton("Preview Voice", self))
        button_row.addStretch(1)
        selection_layout.addLayout(button_row)
        layout.addWidget(selection_group)

        preview_group = QGroupBox("Preview / Workspace", self)
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.addWidget(QLabel(
            "Reserved area for voice preview, sample text, waveform, or "
            "future narrator controls."
        ))

        self._preview_frame = QFrame(self)
        self._preview_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._preview_frame.setMinimumHeight(260)
        preview_layout.addWidget(self._preview_frame, 1)
        layout.addWidget(preview_group, 1)


# END OF FILE
