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
@brief Text extraction and cleanup page for AudioMancer.
@details Provides the operator-facing extraction UI state for the first
         deterministic text-processing slice while cleanup actions remain
         unavailable.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.2.0
"""

# IMPORTS

from PySide6.QtCore import Signal
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

from audiomancer.services import ui_state_service


# PUBLIC API


class TextCleanupPage(QWidget):
    """
    @brief      Display extraction and placeholder cleanup controls for the active project.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """

    extract_requested = Signal()

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the extraction-aware text cleanup page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.1
        """
        super().__init__(parent)
        self._project_active = False
        self._busy = False
        self._can_extract = False

        layout = QVBoxLayout(self)
        header_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Text Cleanup</h2>")
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)

        self._extract_button = QPushButton("Extract Text")
        self._extract_button.clicked.connect(self.extract_requested.emit)
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
        extracted_layout.addWidget(self._extracted_text_edit)

        cleaned_group = QGroupBox("Cleaned Text Preview", self)
        cleaned_layout = QVBoxLayout(cleaned_group)
        self._cleaned_text_edit = QPlainTextEdit(self)
        self._cleaned_text_edit.setReadOnly(True)
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
        notes_layout.addWidget(self._notes_edit)
        notes_group.setMaximumHeight(120)
        layout.addWidget(notes_group, 0)

        self._extracted_group = extracted_group
        self._cleaned_group = cleaned_group
        self._notes_group = notes_group

        self.set_project_active(False)
        self.set_processing_state(
            extracted_text=None,
            cleaned_text=None,
            notes=["Import a source to begin text extraction."],
            can_extract=False,
        )

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Enable or disable extraction controls based on project availability.
        @param[in]  is_active True when a project is open.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        self._project_active = is_active
        self._apply_button_state()

    def set_processing_state(
        self,
        extracted_text: str | None,
        cleaned_text: str | None,
        notes: list[str],
        can_extract: bool,
    ) -> None:
        """
        @brief      Refresh the page from extraction-state inputs.
        @param[in]  extracted_text Extracted text preview or `None`.
        @param[in]  cleaned_text Cleaned text preview or `None`.
        @param[in]  notes Operator-facing cleanup/extraction notes.
        @param[in]  can_extract True when extraction may run.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        self._can_extract = can_extract
        self._apply_button_state()
        self._extracted_text_edit.setPlainText(extracted_text or "")
        self._cleaned_text_edit.setPlainText(cleaned_text or "")
        self._notes_edit.setPlainText("\n".join(notes))

    def set_busy(self, is_busy: bool) -> None:
        """
        @brief      Disable extraction actions while the extraction handler is busy.
        @param[in]  is_busy True while extraction is running.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        self._busy = is_busy
        self._apply_button_state()

    def _apply_button_state(self) -> None:
        """
        @brief      Apply the current extraction-button state.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        self._extract_button.setEnabled(
            self._project_active and self._can_extract and not self._busy
        )

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one translated UI language to the page widgets.
        @param[in]  language Runtime UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.2.0
        """
        self._title_label.setText(
            f"<h2>{ui_state_service.translate('text_cleanup.title', language)}</h2>"
        )
        self._extract_button.setText(
            ui_state_service.translate("text_cleanup.extract", language)
        )
        self._clean_button.setText(
            ui_state_service.translate("text_cleanup.clean", language)
        )
        self._ai_profile_label.setText(
            ui_state_service.translate("text_cleanup.ai_profile", language)
        )
        self._ai_clean_button.setText(
            ui_state_service.translate("text_cleanup.ai_clean", language)
        )
        self._extracted_group.setTitle(
            ui_state_service.translate("text_cleanup.extracted_group", language)
        )
        self._cleaned_group.setTitle(
            ui_state_service.translate("text_cleanup.cleaned_group", language)
        )
        self._notes_group.setTitle(
            ui_state_service.translate("text_cleanup.notes_group", language)
        )


# END OF FILE
