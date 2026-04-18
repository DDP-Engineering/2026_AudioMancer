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
@brief Text chunking page for AudioMancer.
@details Provides deterministic chunk generation controls and renders the
         current cleaned-text reference plus persisted chunk previews.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.3.0
"""

# IMPORTS

from PySide6.QtCore import Signal
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

from audiomancer import config
from audiomancer.services import ui_state_service

# PUBLIC API


class TextChunkingPage(QWidget):
    """
    @brief      Display deterministic and AI-assisted chunking controls.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.2
    """

    chunk_requested = Signal()
    ai_chunk_requested = Signal(str, str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the chunking-aware text chunking page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.3.0
        """
        super().__init__(parent)
        self._chunks: list[dict[str, object]] = []
        self._project_active = False
        self._busy = False
        self._can_chunk = False
        self._can_ai_chunk = False
        self._has_ai_profiles = False

        layout = QVBoxLayout(self)
        header_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Text Chunking</h2>")
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)

        self._chunk_button = QPushButton("Deterministic Chunking")
        self._chunk_button.clicked.connect(self.chunk_requested.emit)
        header_row.addWidget(self._chunk_button)

        self._profile_label = QLabel("AI Profile")
        self._profile_label.setEnabled(False)
        header_row.addWidget(self._profile_label)

        self._profile_combo = QComboBox(self)
        self._profile_combo.addItem("(none)", None)
        header_row.addWidget(self._profile_combo)

        self._strategy_label = QLabel("AI Strategy")
        header_row.addWidget(self._strategy_label)

        self._strategy_combo = QComboBox(self)
        for strategy in config.AI_CHUNKING_STRATEGY_OPTIONS:
            self._strategy_combo.addItem(strategy.title(), strategy)
        header_row.addWidget(self._strategy_combo)

        self._ai_chunk_button = QPushButton("AI-Assisted Chunking")
        self._ai_chunk_button.clicked.connect(self._emit_ai_chunk_request)
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
        self._cleaned_text_edit.setPlainText("Cleaned text will appear here and serve as the chunking reference.")
        cleaned_layout.addWidget(self._cleaned_text_edit)
        left_layout.addWidget(cleaned_group, 5)

        chunk_list_group = QGroupBox("Chunk List", self)
        chunk_list_layout = QVBoxLayout(chunk_list_group)
        self._chunk_list = QListWidget(self)
        self._chunk_list.currentRowChanged.connect(self._show_selected_chunk)
        chunk_list_layout.addWidget(self._chunk_list)
        left_layout.addWidget(chunk_list_group, 2)
        top_splitter.addWidget(left_container)

        chunk_preview_group = QGroupBox("Selected Chunk", self)
        chunk_preview_layout = QVBoxLayout(chunk_preview_group)
        self._chunk_text_edit = QPlainTextEdit(self)
        self._chunk_text_edit.setReadOnly(True)
        self._chunk_text_edit.setPlainText("The full text of the selected chunk will appear here.")
        chunk_preview_layout.addWidget(self._chunk_text_edit)
        top_splitter.addWidget(chunk_preview_group)

        top_splitter.setStretchFactor(0, 3)
        top_splitter.setStretchFactor(1, 2)
        layout.addWidget(top_splitter, 6)

        notes_group = QGroupBox("Chunking Notes", self)
        notes_layout = QVBoxLayout(notes_group)
        self._notes_edit = QPlainTextEdit(self)
        self._notes_edit.setReadOnly(True)
        self._notes_edit.setPlainText(
            "Run cleanup before chunking.\n"
            "Deterministic and AI-assisted chunk generation will populate the chunk list and selected preview."
        )
        notes_layout.addWidget(self._notes_edit)
        notes_group.setMinimumHeight(96)
        notes_group.setMaximumHeight(112)
        layout.addWidget(notes_group, 0)
        self._cleaned_group = cleaned_group
        self._chunk_list_group = chunk_list_group
        self._chunk_preview_group = chunk_preview_group
        self._notes_group = notes_group
        self.set_project_active(False)
        self.set_processing_state(
            cleaned_text=None,
            chunks=[],
            notes=["Run cleanup before chunking."],
            can_chunk=False,
            can_ai_chunk=False,
        )

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Enable or disable the page based on project availability.
        @param[in]  is_active True when a project is open.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        self._project_active = is_active
        self._apply_button_state()

    def set_processing_state(
        self,
        cleaned_text: str | None,
        chunks: list[dict[str, object]],
        notes: list[str],
        can_chunk: bool,
        can_ai_chunk: bool | None = None,
        selected_strategy: str | None = None,
    ) -> None:
        """
        @brief      Refresh the chunking page from controller-provided state.
        @param[in]  cleaned_text Cleaned-text reference preview.
        @param[in]  chunks Persisted chunk payload list.
        @param[in]  notes Operator-facing chunking notes.
        @param[in]  can_chunk True when deterministic chunking may run.
        @param[in]  can_ai_chunk Optional explicit AI chunking enable flag.
        @param[in]  selected_strategy Optional strategy token to preselect.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        self._chunks = list(chunks)
        self._cleaned_text_edit.setPlainText(cleaned_text or "")
        self._can_chunk = can_chunk
        self._can_ai_chunk = can_chunk if can_ai_chunk is None else can_ai_chunk
        if selected_strategy is not None:
            self.set_default_ai_strategy(selected_strategy)
        self._chunk_list.clear()
        for chunk in self._chunks:
            chunk_text = str(chunk.get("text", ""))
            preview = chunk_text if len(chunk_text) <= 80 else chunk_text[:77] + "..."
            self._chunk_list.addItem(f"{chunk.get('chunk_id', '')} | {preview}")
        self._notes_edit.setPlainText("\n".join(notes))
        self._apply_button_state()
        self._show_selected_chunk(0 if self._chunks else -1)

    def set_default_ai_strategy(self, strategy: str) -> None:
        """
        @brief      Select the current AI chunking strategy in the combo box.
        @param[in]  strategy Strategy token to select.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        index = self._strategy_combo.findData(strategy)
        if index >= 0:
            self._strategy_combo.setCurrentIndex(index)

    def set_ai_profiles(
        self,
        entries: list[tuple[str, str | None]],
        selected_profile_id: str | None,
    ) -> None:
        """
        @brief      Populate the AI chunking profile selector.
        @param[in]  entries Ordered profile label/id entries for the selector.
        @param[in]  selected_profile_id Profile id that should be selected.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        if entries:
            for label, profile_id in entries:
                self._profile_combo.addItem(label, profile_id)
            selected_index = next(
                (index for index, (_label, profile_id) in enumerate(entries) if profile_id == selected_profile_id),
                0,
            )
            self._profile_combo.setCurrentIndex(selected_index)
        else:
            self._profile_combo.addItem("(none)", None)
            self._profile_combo.setCurrentIndex(0)
        self._profile_combo.blockSignals(False)
        self._has_ai_profiles = bool(entries)
        self._apply_button_state()

    def current_ai_strategy(self) -> str:
        """
        @brief      Return the currently selected AI chunking strategy token.
        @return     Strategy identifier from the combo box.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        return str(self._strategy_combo.currentData() or config.DEFAULT_AI_CHUNKING_STRATEGY)

    def current_ai_profile_id(self) -> str | None:
        """
        @brief      Return the selected AI-profile identifier.
        @return     Selected profile id or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        value = self._profile_combo.currentData()
        return None if value in (None, "") else str(value)

    def set_busy(self, is_busy: bool) -> None:
        """
        @brief      Disable page actions while another blocking task runs.
        @param[in]  is_busy True while the controller is running a blocking task.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        self._busy = is_busy
        self._apply_button_state()

    def _apply_button_state(self) -> None:
        """
        @brief      Apply the current page button states.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        enabled = self._project_active and not self._busy
        self._chunk_button.setEnabled(enabled and self._can_chunk)
        ai_selector_enabled = self._project_active and self._has_ai_profiles
        self._profile_label.setEnabled(ai_selector_enabled)
        self._profile_combo.setEnabled(ai_selector_enabled)
        self._strategy_label.setEnabled(self._project_active and (self._can_chunk or self._can_ai_chunk))
        self._strategy_combo.setEnabled(self._project_active and (self._can_chunk or self._can_ai_chunk))
        self._ai_chunk_button.setEnabled(enabled and self._can_ai_chunk and self.current_ai_profile_id() is not None)

    def _show_selected_chunk(self, row: int) -> None:
        """
        @brief      Display the currently selected chunk preview.
        @param[in]  row Current selected row in the chunk list.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        if row < 0 or row >= len(self._chunks):
            self._chunk_text_edit.clear()
            return
        self._chunk_text_edit.setPlainText(str(self._chunks[row].get("text", "")))

    def _emit_ai_chunk_request(self) -> None:
        """
        @brief      Emit one AI chunking request with the selected profile id.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        profile_id = self.current_ai_profile_id()
        if profile_id is not None:
            self.ai_chunk_requested.emit(profile_id, self.current_ai_strategy())

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
        self._title_label.setText(f"<h2>{ui_state_service.translate('text_chunking.title', language)}</h2>")
        self._profile_label.setText(ui_state_service.translate("text_chunking.ai_profile", language))
        self._strategy_label.setText(ui_state_service.translate("text_chunking.ai_strategy", language))
        self._chunk_button.setText(ui_state_service.translate("text_chunking.chunk", language))
        self._ai_chunk_button.setText(ui_state_service.translate("text_chunking.ai_chunk", language))
        self._cleaned_group.setTitle(ui_state_service.translate("text_chunking.cleaned_group", language))
        self._chunk_list_group.setTitle(ui_state_service.translate("text_chunking.chunk_list_group", language))
        self._chunk_preview_group.setTitle(ui_state_service.translate("text_chunking.selected_group", language))
        self._notes_group.setTitle(ui_state_service.translate("text_chunking.notes_group", language))
        if not self._has_ai_profiles:
            self._profile_combo.setItemText(
                0,
                ui_state_service.translate("ai_settings.none", language),
            )


# END OF FILE
