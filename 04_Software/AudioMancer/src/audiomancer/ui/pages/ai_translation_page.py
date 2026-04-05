#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_translation_page.py
@brief Static AI Translation page for AudioMancer.
@details Clones the DDP_Audiomancer AI translation page layout as a purely
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
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import ui_state_service


# CONSTANTS

_TRANSLATION_LANGUAGE_OPTIONS = list(config.TRANSLATION_LANGUAGE_OPTIONS)


# PUBLIC API


class AiTranslationPage(QWidget):
    """
    @brief      Display the static AI translation shell page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the cloned AI translation page.
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
        self._title_label = QLabel("<h2>AI Translation</h2>")
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)

        self._language_label = QLabel("Target Language")
        header_row.addWidget(self._language_label)

        self._language_combo = QComboBox(self)
        for code, label in _TRANSLATION_LANGUAGE_OPTIONS:
            self._language_combo.addItem(label, code)
        self._language_combo.setCurrentIndex(0)
        self._language_combo.setEnabled(False)
        header_row.addWidget(self._language_combo)

        self._profile_label = QLabel("AI Profile")
        header_row.addWidget(self._profile_label)

        self._profile_combo = QComboBox(self)
        self._profile_combo.addItem("(no profiles)", None)
        self._profile_combo.setEnabled(False)
        header_row.addWidget(self._profile_combo)

        layout.addLayout(header_row)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        chunk_list_group = QGroupBox("Chunk List", self)
        chunk_list_layout = QVBoxLayout(chunk_list_group)
        self._chunk_list = QListWidget(self)
        self._chunk_list.addItems((
            "[Pending] chunk_001 | Example first source chunk preview...",
            "[Translated] chunk_002 | Example second source chunk preview...",
            "[Approved] chunk_003 | Example third source chunk preview...",
        ))
        chunk_list_layout.addWidget(self._chunk_list)
        chunk_list_group.setMinimumHeight(136)
        chunk_list_group.setMaximumHeight(176)
        top_row.addWidget(chunk_list_group, 5)

        top_actions_widget = QWidget(self)
        top_actions_layout = QVBoxLayout(top_actions_widget)
        top_actions_layout.setContentsMargins(0, 0, 0, 0)
        top_actions_layout.setSpacing(8)

        self._start_button = QPushButton("Start Translation")
        self._start_button.setEnabled(False)
        top_actions_layout.addWidget(self._start_button)

        self._clear_button = QPushButton("Reset Translation")
        self._clear_button.setEnabled(False)
        top_actions_layout.addWidget(self._clear_button)

        self._approve_all_button = QPushButton("Approve All")
        self._approve_all_button.setEnabled(False)
        top_actions_layout.addWidget(self._approve_all_button)

        top_actions_layout.addStretch(1)
        top_row.addWidget(top_actions_widget, 2)
        layout.addLayout(top_row)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        source_group = QGroupBox("Original Chunk", self)
        source_layout = QVBoxLayout(source_group)
        self._source_text_edit = QPlainTextEdit(self)
        self._source_text_edit.setReadOnly(True)
        self._source_text_edit.setPlainText(
            "The source chunk selected from the list will appear here."
        )
        source_layout.addWidget(self._source_text_edit)

        self._approved_progress_label = QLabel("Approved chunks: 0/0")
        source_layout.addWidget(self._approved_progress_label)

        self._approved_progress_bar = QProgressBar(self)
        self._approved_progress_bar.setTextVisible(True)
        self._approved_progress_bar.setFormat("%p%")
        self._approved_progress_bar.setRange(0, 1)
        self._approved_progress_bar.setValue(0)
        source_layout.addWidget(self._approved_progress_bar)
        bottom_row.addWidget(source_group, 1)

        translated_group = QGroupBox("Translated Chunk", self)
        translated_layout = QVBoxLayout(translated_group)
        self._translated_text_edit = QPlainTextEdit(self)
        self._translated_text_edit.setPlainText(
            "Translated text for the selected chunk will appear here."
        )
        translated_layout.addWidget(self._translated_text_edit)

        action_row = QHBoxLayout()
        self._retranslate_button = QPushButton("Re-Translate Selected")
        self._retranslate_button.setEnabled(False)
        action_row.addWidget(self._retranslate_button)

        self._approve_selected_button = QPushButton("Approve Selected")
        self._approve_selected_button.setEnabled(False)
        action_row.addWidget(self._approve_selected_button)
        translated_layout.addLayout(action_row)
        bottom_row.addWidget(translated_group, 1)

        layout.addLayout(bottom_row, 1)
        self._chunk_list_group = chunk_list_group
        self._source_group = source_group
        self._translated_group = translated_group

    def apply_language(self, language: str) -> None:
        self._title_label.setText(
            f"<h2>{ui_state_service.translate('ai_translation.title', language)}</h2>"
        )
        self._language_label.setText(
            ui_state_service.translate("ai_translation.target_language", language)
        )
        self._profile_label.setText(
            ui_state_service.translate("ai_translation.ai_profile", language)
        )
        self._chunk_list_group.setTitle(
            ui_state_service.translate("ai_translation.chunk_list_group", language)
        )
        self._start_button.setText(
            ui_state_service.translate("ai_translation.start", language)
        )
        self._clear_button.setText(
            ui_state_service.translate("ai_translation.reset", language)
        )
        self._approve_all_button.setText(
            ui_state_service.translate("ai_translation.approve_all", language)
        )
        self._source_group.setTitle(
            ui_state_service.translate("ai_translation.original_group", language)
        )
        self._translated_group.setTitle(
            ui_state_service.translate("ai_translation.translated_group", language)
        )
        self._approved_progress_label.setText(
            ui_state_service.translate("ai_translation.approved_chunks", language)
        )
        self._retranslate_button.setText(
            ui_state_service.translate("ai_translation.retranslate", language)
        )
        self._approve_selected_button.setText(
            ui_state_service.translate("ai_translation.approve_selected", language)
        )
        self._source_text_edit.setPlainText(
            ui_state_service.translate("ai_translation.source_note", language)
        )
        self._translated_text_edit.setPlainText(
            ui_state_service.translate("ai_translation.translated_note", language)
        )


# END OF FILE
