#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file text_cleanup_page.py
@brief Static text extraction and cleanup page for AudioMancer.
@details Clones the DDP_Audiomancer text-cleanup page layout as a purely
         presentational page without any connected functionality.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.1.0
"""

# IMPORTS

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


# PUBLIC API


class TextCleanupPage(QWidget):
    """
    @brief      Display the static extraction and cleanup shell page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the cloned text-cleanup page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)
        header_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Text Cleanup</h2>")
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)

        self._extract_button = QPushButton("Extract Text")
        self._extract_button.setEnabled(False)
        header_row.addWidget(self._extract_button)

        self._clean_button = QPushButton("Deterministic Cleanup")
        self._clean_button.setEnabled(False)
        header_row.addWidget(self._clean_button)

        self._ai_profile_label = QLabel("AI Profile")
        self._ai_profile_label.setEnabled(False)
        header_row.addWidget(self._ai_profile_label)

        self._ai_profile_combo = QComboBox(self)
        self._ai_profile_combo.addItem("(none)", None)
        self._ai_profile_combo.setEnabled(False)
        header_row.addWidget(self._ai_profile_combo)

        self._ai_clean_button = QPushButton("AI-Assisted Cleanup")
        self._ai_clean_button.setEnabled(False)
        header_row.addWidget(self._ai_clean_button)

        layout.addLayout(header_row)

        splitter = QSplitter(self)

        extracted_group = QGroupBox("Extracted Text Preview", self)
        extracted_layout = QVBoxLayout(extracted_group)
        self._extracted_text_edit = QPlainTextEdit(self)
        self._extracted_text_edit.setReadOnly(True)
        self._extracted_text_edit.setPlainText(
            "Raw extracted text will appear here after source processing."
        )
        extracted_layout.addWidget(self._extracted_text_edit)

        cleaned_group = QGroupBox("Cleaned Text Preview", self)
        cleaned_layout = QVBoxLayout(cleaned_group)
        self._cleaned_text_edit = QPlainTextEdit(self)
        self._cleaned_text_edit.setReadOnly(True)
        self._cleaned_text_edit.setPlainText(
            "Deterministic or AI-assisted cleanup output will appear here."
        )
        cleaned_layout.addWidget(self._cleaned_text_edit)

        splitter.addWidget(extracted_group)
        splitter.addWidget(cleaned_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 3)

        notes_group = QGroupBox("Cleanup Notes", self)
        notes_layout = QVBoxLayout(notes_group)
        self._notes_edit = QPlainTextEdit(self)
        self._notes_edit.setReadOnly(True)
        self._notes_edit.setPlainText(
            "Import a source to begin text extraction.\n"
            "Deterministic cleanup and AI-assisted cleanup are not wired yet."
        )
        notes_layout.addWidget(self._notes_edit)
        notes_group.setMaximumHeight(180)
        layout.addWidget(notes_group, 0)


# END OF FILE
