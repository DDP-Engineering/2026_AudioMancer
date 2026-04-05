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
@version 0.2.0
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

from audiomancer.services import ui_state_service


# PUBLIC API


class CharactersPage(QWidget):
    """
    @brief      Display the static Character Discovery shell page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.2.0
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the cloned characters page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.2.0
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)
        header_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Characters</h2>")
        header_row.addWidget(self._title_label)
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

        self._canonical_name_label = QLabel("Canonical Name", self)
        self._aliases_label = QLabel("Aliases", self)
        self._gender_hint_label = QLabel("Gender Hint", self)
        self._age_band_label = QLabel("Age Band", self)
        self._role_summary_label = QLabel("Role Summary", self)
        self._description_label = QLabel("Description", self)
        self._temperament_label = QLabel("Temperament", self)
        self._social_status_label = QLabel("Social Status", self)
        self._speaking_style_label = QLabel("Speaking Style", self)
        self._accent_label = QLabel("Accent / Dialect", self)
        self._voice_notes_label = QLabel("Voice Notes", self)
        self._relationships_label = QLabel("Relationship Hints", self)
        self._confidence_label = QLabel("Confidence", self)

        editor_layout.addRow(self._canonical_name_label, self._canonical_name_edit)
        editor_layout.addRow(self._aliases_label, self._aliases_edit)
        editor_layout.addRow(self._gender_hint_label, self._gender_hint_edit)
        editor_layout.addRow(self._age_band_label, self._age_band_edit)
        editor_layout.addRow(self._role_summary_label, self._role_summary_edit)
        editor_layout.addRow(self._description_label, self._description_edit)
        editor_layout.addRow(self._temperament_label, self._temperament_edit)
        editor_layout.addRow(self._social_status_label, self._social_status_edit)
        editor_layout.addRow(self._speaking_style_label, self._speaking_style_edit)
        editor_layout.addRow(self._accent_label, self._accent_edit)
        editor_layout.addRow(self._voice_notes_label, self._voice_notes_edit)
        editor_layout.addRow(self._relationships_label, self._relationships_edit)
        editor_layout.addRow(self._confidence_label, self._confidence_edit)
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
        self._list_group = list_group
        self._editor_group = editor_group
        self._evidence_group = evidence_group

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the characters page labels.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        self._title_label.setText(
            f"<h2>{ui_state_service.translate('characters.title', language)}</h2>"
        )
        self._profile_label.setText(
            ui_state_service.translate("characters.ai_profile", language)
        )
        self._start_button.setText(
            ui_state_service.translate("characters.start", language)
        )
        self._clear_button.setText(
            ui_state_service.translate("characters.reset", language)
        )
        self._summary_label.setText(
            ui_state_service.translate("characters.summary", language)
        )
        self._list_group.setTitle(
            ui_state_service.translate("characters.list_group", language)
        )
        self._editor_group.setTitle(
            ui_state_service.translate("characters.profile_group", language)
        )
        self._evidence_group.setTitle(
            ui_state_service.translate("characters.evidence_group", language)
        )
        self._canonical_name_label.setText(
            ui_state_service.translate("characters.canonical_name", language)
        )
        self._aliases_label.setText(
            ui_state_service.translate("characters.aliases", language)
        )
        self._gender_hint_label.setText(
            ui_state_service.translate("characters.gender_hint", language)
        )
        self._age_band_label.setText(
            ui_state_service.translate("characters.age_band", language)
        )
        self._role_summary_label.setText(
            ui_state_service.translate("characters.role_summary", language)
        )
        self._description_label.setText(
            ui_state_service.translate("characters.description", language)
        )
        self._temperament_label.setText(
            ui_state_service.translate("characters.temperament", language)
        )
        self._social_status_label.setText(
            ui_state_service.translate("characters.social_status", language)
        )
        self._speaking_style_label.setText(
            ui_state_service.translate("characters.speaking_style", language)
        )
        self._accent_label.setText(
            ui_state_service.translate("characters.accent", language)
        )
        self._voice_notes_label.setText(
            ui_state_service.translate("characters.voice_notes", language)
        )
        self._relationships_label.setText(
            ui_state_service.translate("characters.relationship_hints", language)
        )
        self._confidence_label.setText(
            ui_state_service.translate("characters.confidence", language)
        )
        self._evidence_preview.setPlainText(
            ui_state_service.translate("characters.evidence_note", language)
        )


# END OF FILE
