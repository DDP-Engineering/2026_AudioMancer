#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file characters_page.py
@brief Static Character Discovery page for AudioMancer.
@details Clones the DDP_Audiomancer characters page layout as a purely
         presentational page without any connected functionality.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.1.0
"""

# IMPORTS

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


# PUBLIC API


class CharactersPage(QWidget):
    """
    @brief      Display the static Character Discovery shell page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the cloned characters page.
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
        header_row.addWidget(QLabel("<h2>Characters</h2>"))
        header_row.addStretch(1)

        self._profile_label = QLabel("AI Profile")
        header_row.addWidget(self._profile_label)

        self._profile_combo = QComboBox(self)
        self._profile_combo.addItem("(no profiles)", None)
        self._profile_combo.setEnabled(False)
        header_row.addWidget(self._profile_combo)

        self._start_button = QPushButton("Start Discovery")
        self._start_button.setEnabled(False)
        header_row.addWidget(self._start_button)

        self._clear_button = QPushButton("Reset Discovery")
        self._clear_button.setEnabled(False)
        header_row.addWidget(self._clear_button)
        layout.addLayout(header_row)

        self._summary_label = QLabel(
            "Run text chunking before Character Discovery."
        )
        self._summary_label.setWordWrap(False)
        layout.addWidget(self._summary_label)

        self._main_splitter = QSplitter(self)
        self._left_splitter = QSplitter(self)
        self._left_splitter.setOrientation(Qt.Orientation.Vertical)

        list_group = QGroupBox("Character List", self)
        list_group.setMinimumHeight(190)
        list_layout = QVBoxLayout(list_group)
        self._character_list = QListWidget(self)
        self._character_list.addItems((
            "Narrator | Central narration voice",
            "Protagonist | Main point-of-view character",
            "Companion | Supporting dialogue role",
        ))
        list_layout.addWidget(self._character_list)
        self._left_splitter.addWidget(list_group)

        editor_group = QGroupBox("Character Profile", self)
        editor_group.setMinimumHeight(340)
        editor_group_layout = QVBoxLayout(editor_group)
        editor_group_layout.setContentsMargins(6, 12, 6, 6)
        self._editor_scroll_area = QScrollArea(editor_group)
        self._editor_scroll_area.setWidgetResizable(True)
        self._editor_scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._editor_scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._editor_form_widget = QWidget(self._editor_scroll_area)
        editor_layout = QFormLayout(self._editor_form_widget)
        editor_layout.setContentsMargins(4, 4, 4, 4)
        editor_layout.setHorizontalSpacing(12)
        editor_layout.setVerticalSpacing(8)

        self._canonical_name_edit = QLineEdit(self)
        self._canonical_name_edit.setText("Narrator")
        self._aliases_edit = QLineEdit(self)
        self._aliases_edit.setText("Story voice, Main narrator")
        self._gender_hint_edit = QLineEdit(self)
        self._gender_hint_edit.setText("Neutral")
        self._age_band_edit = QLineEdit(self)
        self._age_band_edit.setText("Adult")
        self._role_summary_edit = QPlainTextEdit(self)
        self._role_summary_edit.setPlainText("Main narration voice guiding the story.")
        self._description_edit = QPlainTextEdit(self)
        self._description_edit.setPlainText("Stable central voice used for exposition and flow.")
        self._temperament_edit = QPlainTextEdit(self)
        self._temperament_edit.setPlainText("Calm, observant, expressive.")
        self._social_status_edit = QPlainTextEdit(self)
        self._social_status_edit.setPlainText("Context-dependent narrator role.")
        self._speaking_style_edit = QPlainTextEdit(self)
        self._speaking_style_edit.setPlainText("Clear phrasing with controlled dramatic emphasis.")
        self._accent_edit = QLineEdit(self)
        self._accent_edit.setText("Standard")
        self._voice_notes_edit = QPlainTextEdit(self)
        self._voice_notes_edit.setPlainText("Reserved for future voice profile notes.")
        self._relationships_edit = QPlainTextEdit(self)
        self._relationships_edit.setPlainText("Connected to all scenes as narrator.")
        self._confidence_edit = QLineEdit(self)
        self._confidence_edit.setText("0.85")

        for widget in (
            self._canonical_name_edit,
            self._aliases_edit,
            self._gender_hint_edit,
            self._age_band_edit,
            self._accent_edit,
            self._confidence_edit,
        ):
            widget.setMinimumHeight(30)

        for widget in (
            self._role_summary_edit,
            self._description_edit,
            self._temperament_edit,
            self._social_status_edit,
            self._speaking_style_edit,
            self._voice_notes_edit,
            self._relationships_edit,
        ):
            widget.setMinimumHeight(62)
            widget.setMaximumHeight(82)

        editor_layout.addRow("Canonical Name", self._canonical_name_edit)
        editor_layout.addRow("Aliases", self._aliases_edit)
        editor_layout.addRow("Gender Hint", self._gender_hint_edit)
        editor_layout.addRow("Age Band", self._age_band_edit)
        editor_layout.addRow("Role Summary", self._role_summary_edit)
        editor_layout.addRow("Description", self._description_edit)
        editor_layout.addRow("Temperament", self._temperament_edit)
        editor_layout.addRow("Social Status", self._social_status_edit)
        editor_layout.addRow("Speaking Style", self._speaking_style_edit)
        editor_layout.addRow("Accent / Dialect", self._accent_edit)
        editor_layout.addRow("Voice Notes", self._voice_notes_edit)
        editor_layout.addRow("Relationship Hints", self._relationships_edit)
        editor_layout.addRow("Confidence", self._confidence_edit)
        self._editor_scroll_area.setWidget(self._editor_form_widget)
        editor_group_layout.addWidget(self._editor_scroll_area)
        self._left_splitter.addWidget(editor_group)

        evidence_group = QGroupBox("Evidence", self)
        evidence_group.setMinimumWidth(280)
        evidence_layout = QVBoxLayout(evidence_group)
        self._evidence_list = QListWidget(self)
        self._evidence_list.addItems((
            "chunk_001 | Narration framing language",
            "chunk_004 | Consistent exposition tone",
            "chunk_007 | Scene transition phrasing",
        ))
        self._evidence_preview = QPlainTextEdit(self)
        self._evidence_preview.setReadOnly(True)
        self._evidence_preview.setPlainText(
            "Selected source evidence excerpt will appear here."
        )
        evidence_layout.addWidget(self._evidence_list)
        evidence_layout.addWidget(self._evidence_preview)

        self._main_splitter.addWidget(self._left_splitter)
        self._main_splitter.addWidget(evidence_group)
        self._left_splitter.setStretchFactor(0, 2)
        self._left_splitter.setStretchFactor(1, 6)
        self._left_splitter.setSizes([240, 620])
        self._main_splitter.setStretchFactor(0, 7)
        self._main_splitter.setStretchFactor(1, 3)
        self._main_splitter.setSizes([900, 300])
        layout.addWidget(self._main_splitter, 1)


# END OF FILE
