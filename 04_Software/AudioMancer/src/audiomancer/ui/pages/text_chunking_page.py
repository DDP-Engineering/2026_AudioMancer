#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file text_chunking_page.py
@brief Static text chunking page for AudioMancer.
@details Clones the DDP_Audiomancer text-chunking page layout as a purely
         presentational page without any connected functionality.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.1.1
"""

# IMPORTS

from audiomancer import config
from audiomancer.services import ui_state_service
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


# PUBLIC API


class TextChunkingPage(QWidget):
    """
    @brief      Display the static deterministic and AI chunking shell page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the cloned text-chunking page.
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
        self._title_label = QLabel("<h2>Text Chunking</h2>")
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)

        self._profile_label = QLabel("AI Profile")
        self._profile_label.setEnabled(False)
        header_row.addWidget(self._profile_label)

        self._profile_combo = QComboBox(self)
        self._profile_combo.addItem("(none)", None)
        self._profile_combo.setEnabled(False)
        header_row.addWidget(self._profile_combo)

        self._strategy_label = QLabel("AI Strategy")
        self._strategy_label.setEnabled(False)
        header_row.addWidget(self._strategy_label)

        self._strategy_combo = QComboBox(self)
        for strategy in config.AI_CHUNKING_STRATEGY_OPTIONS:
            self._strategy_combo.addItem(strategy.title(), strategy)
        self._strategy_combo.setEnabled(False)
        header_row.addWidget(self._strategy_combo)

        self._chunk_button = QPushButton("Deterministic Chunking")
        self._chunk_button.setEnabled(False)
        header_row.addWidget(self._chunk_button)

        self._ai_chunk_button = QPushButton("AI-Assisted Chunking")
        self._ai_chunk_button.setEnabled(False)
        header_row.addWidget(self._ai_chunk_button)

        layout.addLayout(header_row)

        top_splitter = QSplitter(self)

        left_container = QWidget(self)
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        cleaned_group = QGroupBox("Cleaned Text Reference", self)
        cleaned_layout = QVBoxLayout(cleaned_group)
        self._cleaned_text_edit = QPlainTextEdit(self)
        self._cleaned_text_edit.setReadOnly(True)
        self._cleaned_text_edit.setPlainText(
            "Cleaned text will appear here and serve as the chunking reference."
        )
        cleaned_layout.addWidget(self._cleaned_text_edit)
        left_layout.addWidget(cleaned_group, 3)

        chunk_list_group = QGroupBox("Chunk List", self)
        chunk_list_layout = QVBoxLayout(chunk_list_group)
        self._chunk_list = QListWidget(self)
        self._chunk_list.addItems((
            "chunk_001 | Example first chunk preview...",
            "chunk_002 | Example second chunk preview...",
            "chunk_003 | Example third chunk preview...",
        ))
        chunk_list_layout.addWidget(self._chunk_list)
        left_layout.addWidget(chunk_list_group, 3)
        top_splitter.addWidget(left_container)

        chunk_preview_group = QGroupBox("Selected Chunk", self)
        chunk_preview_layout = QVBoxLayout(chunk_preview_group)
        self._chunk_text_edit = QPlainTextEdit(self)
        self._chunk_text_edit.setReadOnly(True)
        self._chunk_text_edit.setPlainText(
            "The full text of the selected chunk will appear here."
        )
        chunk_preview_layout.addWidget(self._chunk_text_edit)
        top_splitter.addWidget(chunk_preview_group)

        top_splitter.setStretchFactor(0, 3)
        top_splitter.setStretchFactor(1, 2)
        layout.addWidget(top_splitter, 4)

        notes_group = QGroupBox("Chunking Notes", self)
        notes_layout = QVBoxLayout(notes_group)
        self._notes_edit = QPlainTextEdit(self)
        self._notes_edit.setReadOnly(True)
        self._notes_edit.setPlainText(
            "Run cleanup before chunking.\n"
            "Deterministic and AI-assisted chunk generation are not wired yet."
        )
        notes_layout.addWidget(self._notes_edit)
        notes_group.setMaximumHeight(140)
        layout.addWidget(notes_group, 0)
        self._cleaned_group = cleaned_group
        self._chunk_list_group = chunk_list_group
        self._chunk_preview_group = chunk_preview_group
        self._notes_group = notes_group

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one translated UI language to the page widgets.
        @param[in]  language Runtime UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        self._title_label.setText(
            f"<h2>{ui_state_service.translate('text_chunking.title', language)}</h2>"
        )
        self._profile_label.setText(
            ui_state_service.translate("text_chunking.ai_profile", language)
        )
        self._strategy_label.setText(
            ui_state_service.translate("text_chunking.ai_strategy", language)
        )
        self._chunk_button.setText(
            ui_state_service.translate("text_chunking.chunk", language)
        )
        self._ai_chunk_button.setText(
            ui_state_service.translate("text_chunking.ai_chunk", language)
        )
        self._cleaned_group.setTitle(
            ui_state_service.translate("text_chunking.cleaned_group", language)
        )
        self._chunk_list_group.setTitle(
            ui_state_service.translate("text_chunking.chunk_list_group", language)
        )
        self._chunk_preview_group.setTitle(
            ui_state_service.translate("text_chunking.selected_group", language)
        )
        self._notes_group.setTitle(
            ui_state_service.translate("text_chunking.notes_group", language)
        )
        self._cleaned_text_edit.setPlainText(
            ui_state_service.translate("text_chunking.cleaned_note", language)
        )
        self._chunk_text_edit.setPlainText(
            ui_state_service.translate("text_chunking.selected_note", language)
        )
        self._notes_edit.setPlainText(
            ui_state_service.translate("text_chunking.notes_text", language)
        )


# END OF FILE
