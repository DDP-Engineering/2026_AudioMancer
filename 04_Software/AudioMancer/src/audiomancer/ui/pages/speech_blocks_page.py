#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file speech_blocks_page.py
@brief Speech Blocks workflow page for AudioMancer.
@details Provides chunk review, approval-aware speech-block editing, AI profile
         selection, whole-run generation controls, and selected-chunk re-split
         controls for the Speech Blocks workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.3.2
"""

# IMPORTS

from PySide6.QtCore import QTimer, Signal
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

from audiomancer.services import speech_blocks_service, ui_state_service


class SpeechBlocksPage(QWidget):
    """
    @brief      Display the Speech Blocks workflow surface.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.2
    """

    generate_requested = Signal(str)
    reset_generation_requested = Signal()
    approve_all_requested = Signal()
    resplit_selected_requested = Signal(str)
    insert_block_requested = Signal(str, str)
    delete_block_requested = Signal(str)
    edit_started = Signal(str)
    save_block_requested = Signal(str, str, str, str)
    reset_block_requested = Signal(str)
    approve_block_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the Speech Blocks page widgets.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.3.0
        """
        super().__init__(parent)
        self._current_language = "en"
        self._project_active = False
        self._busy = False
        self._editing = False
        self._stage_status = speech_blocks_service.SPEECH_BLOCKS_STAGE_NOT_STARTED
        self._source_chunks: list[dict[str, object]] = []
        self._speech_blocks: list[dict[str, object]] = []
        self._speaker_catalog: list[dict[str, object]] = []
        self._content_kind_options: list[tuple[str, str]] = []
        self._can_reset = False
        self._can_approve_all = False
        self._can_resplit_selected = False
        self._current_chunk_id: str | None = None
        self._current_block_id: str | None = None

        layout = QVBoxLayout(self)
        header_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Speech Blocks</h2>")
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)
        self._profile_label = QLabel("AI Profile")
        header_row.addWidget(self._profile_label)
        self._profile_combo = QComboBox(self)
        self._profile_combo.addItem("(none)", None)
        header_row.addWidget(self._profile_combo)
        self._generate_button = QPushButton("Generate Speech Blocks")
        self._generate_button.clicked.connect(self._emit_generate_requested)
        header_row.addWidget(self._generate_button)
        self._reset_generation_button = QPushButton("Reset Speech Blocks")
        self._reset_generation_button.clicked.connect(self.reset_generation_requested.emit)
        header_row.addWidget(self._reset_generation_button)
        self._approve_all_button = QPushButton("Approve All Speech Blocks")
        self._approve_all_button.clicked.connect(self.approve_all_requested.emit)
        header_row.addWidget(self._approve_all_button)
        layout.addLayout(header_row)

        self._chunk_group = QGroupBox("Chunk List", self)
        chunk_layout = QHBoxLayout(self._chunk_group)
        self._chunk_list = QListWidget(self)
        self._chunk_list.currentRowChanged.connect(self._show_selected_chunk)
        chunk_layout.addWidget(self._chunk_list, 1)
        chunk_actions_layout = QVBoxLayout()
        self._insert_block_button = QPushButton("Insert Speech Block")
        self._insert_block_button.clicked.connect(self._emit_insert_block)
        chunk_actions_layout.addWidget(self._insert_block_button)
        self._delete_block_button = QPushButton("Delete Speech Block")
        self._delete_block_button.clicked.connect(self._emit_delete_block)
        chunk_actions_layout.addWidget(self._delete_block_button)
        chunk_actions_layout.addStretch(1)
        chunk_layout.addLayout(chunk_actions_layout)
        self._chunk_group.setMinimumHeight(94)
        self._chunk_group.setMaximumHeight(130)
        layout.addWidget(self._chunk_group)

        lower_splitter = QSplitter(self)
        self._source_group = QGroupBox("Selected Chunk", self)
        source_layout = QVBoxLayout(self._source_group)
        self._source_text_edit = QPlainTextEdit(self)
        self._source_text_edit.setReadOnly(True)
        source_layout.addWidget(self._source_text_edit)
        self._resplit_button = QPushButton("Re-Split Selected Chunk")
        self._resplit_button.clicked.connect(self._emit_resplit_selected)
        source_layout.addWidget(self._resplit_button)
        lower_splitter.addWidget(self._source_group)

        self._blocks_group = QGroupBox("Speech Blocks", self)
        blocks_layout = QVBoxLayout(self._blocks_group)
        self._speech_block_list = QListWidget(self)
        self._speech_block_list.currentRowChanged.connect(self._show_selected_block)
        blocks_layout.addWidget(self._speech_block_list, 6)
        meta_row = QHBoxLayout()
        self._speaker_label = QLabel("Speaker")
        meta_row.addWidget(self._speaker_label)
        self._speaker_combo = QComboBox(self)
        meta_row.addWidget(self._speaker_combo, 4)
        self._content_kind_label = QLabel("Content Kind")
        meta_row.addWidget(self._content_kind_label)
        self._content_kind_combo = QComboBox(self)
        meta_row.addWidget(self._content_kind_combo, 3)
        self._warning_label = QLabel("")
        meta_row.addWidget(self._warning_label, 2)
        blocks_layout.addLayout(meta_row)
        self._speech_block_text_edit = QPlainTextEdit(self)
        blocks_layout.addWidget(self._speech_block_text_edit, 3)
        action_row = QHBoxLayout()
        self._reset_block_button = QPushButton("Reset")
        self._reset_block_button.clicked.connect(self._emit_reset_block)
        action_row.addWidget(self._reset_block_button)
        self._edit_button = QPushButton("Edit")
        self._edit_button.clicked.connect(self._begin_editing)
        action_row.addWidget(self._edit_button)
        self._save_button = QPushButton("Save")
        self._save_button.clicked.connect(self._emit_save_block)
        action_row.addWidget(self._save_button)
        self._approve_block_button = QPushButton("Approve")
        self._approve_block_button.clicked.connect(self._emit_approve_block)
        action_row.addWidget(self._approve_block_button)
        blocks_layout.addLayout(action_row)
        lower_splitter.addWidget(self._blocks_group)
        lower_splitter.setStretchFactor(0, 1)
        lower_splitter.setStretchFactor(1, 1)
        layout.addWidget(lower_splitter, 1)

        self._notes_group = QGroupBox("Speech Blocks Notes", self)
        notes_layout = QVBoxLayout(self._notes_group)
        self._notes_edit = QPlainTextEdit(self)
        self._notes_edit.setReadOnly(True)
        notes_layout.addWidget(self._notes_edit)
        self._notes_group.setMinimumHeight(96)
        self._notes_group.setMaximumHeight(112)
        layout.addWidget(self._notes_group)

        self.apply_language(self._current_language)
        self.set_project_active(False)
        self.set_speech_blocks_state(
            [],
            [],
            [ui_state_service.translate("speech_blocks.note_no_project", self._current_language)],
            None,
            speech_blocks_service.SPEECH_BLOCKS_STAGE_NOT_STARTED,
            "",
            0,
            0,
        )

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Enable or disable page interactions based on project state.
        @param[in]  is_active True when a project is currently open.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self._project_active = is_active
        self._apply_control_state()

    def set_ai_profiles(self, entries: list[tuple[str, str | None]], selected_profile_id: str | None) -> None:
        """
        @brief      Populate the Speech Blocks AI-profile selector.
        @param[in]  entries Ordered label/id pairs for enabled profiles.
        @param[in]  selected_profile_id Preferred selected profile id.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        if entries:
            for label, profile_id in entries:
                self._profile_combo.addItem(label, profile_id)
            selected_index = next((index for index, entry in enumerate(entries) if entry[1] == selected_profile_id), 0)
            self._profile_combo.setCurrentIndex(selected_index)
        else:
            self._profile_combo.addItem(ui_state_service.translate("ai_settings.none", self._current_language), None)
        self._profile_combo.blockSignals(False)
        self._apply_control_state()

    def set_speech_blocks_state(
        self,
        source_chunks: list[dict[str, object]],
        speech_blocks: list[dict[str, object]],
        notes: list[str],
        selected_profile_id: str | None,
        stage_status: str,
        selected_source_language: str,
        processed_chunk_count: int,
        total_chunk_count: int,
        approved_block_count: int = 0,
        total_block_count: int = 0,
        speaker_catalog: list[dict[str, object]] | None = None,
        content_kind_options: list[tuple[str, str]] | None = None,
        can_reset: bool = False,
        can_approve_all: bool = False,
        can_resplit_selected: bool = False,
        **_extra_state,
    ) -> None:
        """
        @brief      Refresh the Speech Blocks page from controller-provided state.
        @param[in]  source_chunks Current source chunk payload list.
        @param[in]  speech_blocks Current Speech Blocks payload list.
        @param[in]  notes Operator-facing page notes.
        @param[in]  selected_profile_id Selected AI profile identifier or `None`.
        @param[in]  stage_status Effective Speech Blocks stage token.
        @param[in]  selected_source_language Active source language code.
        @param[in]  processed_chunk_count Number of processed chunks.
        @param[in]  total_chunk_count Total source chunk count.
        @param[in]  approved_block_count Number of approved Speech Blocks.
        @param[in]  total_block_count Total Speech Block count.
        @param[in]  speaker_catalog Ordered speaker selector entries.
        @param[in]  content_kind_options Ordered content-kind selector entries.
        @param[in]  can_reset Controller-resolved reset enablement flag.
        @param[in]  can_approve_all Controller-resolved approve-all enablement flag.
        @param[in]  can_resplit_selected Controller-resolved selected re-split enablement flag.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.2.2
        """
        _ = selected_source_language
        _ = processed_chunk_count
        _ = total_chunk_count
        _ = approved_block_count
        _ = total_block_count
        self._source_chunks = sorted(source_chunks, key=lambda item: int(item.get("sequence_index", 0)))
        self._speech_blocks = speech_blocks_service.sort_speech_blocks(speech_blocks)
        self._speaker_catalog = list(speaker_catalog or [])
        self._content_kind_options = list(content_kind_options or [])
        self._stage_status = stage_status
        self._can_reset = can_reset
        self._can_approve_all = can_approve_all
        self._can_resplit_selected = can_resplit_selected
        current_block_id = self._current_block_id
        current_source_scroll_position = self._source_text_edit.verticalScrollBar().value()
        self._editing = False
        self._populate_selectors()
        if selected_profile_id is not None:
            selected_index = self._profile_combo.findData(selected_profile_id)
            if selected_index >= 0:
                self._profile_combo.setCurrentIndex(selected_index)
        current_chunk_id = self._current_chunk_id
        self._chunk_list.clear()
        block_count_by_chunk = _block_count_by_chunk(self._speech_blocks)
        for source_chunk in self._source_chunks:
            self._chunk_list.addItem(_format_chunk_list_item(source_chunk, block_count_by_chunk))
        self._notes_edit.setPlainText("\n".join(notes))
        if self._source_chunks:
            selected_row = 0
            if current_chunk_id is not None:
                for index, chunk in enumerate(self._source_chunks):
                    if str(chunk.get("chunk_id", "")) == current_chunk_id:
                        selected_row = index
                        break
            self._chunk_list.setCurrentRow(selected_row)
            self._select_block_by_id(current_block_id)
            self.restore_source_scroll_position(current_source_scroll_position)
        else:
            self._show_selected_chunk(-1)
        self._apply_control_state()

    def set_busy(self, is_busy: bool) -> None:
        """
        @brief      Disable page actions while a blocking Speech Blocks task runs.
        @param[in]  is_busy True while the page is busy.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self._busy = is_busy
        self._apply_control_state()

    def current_profile_id(self) -> str | None:
        """
        @brief      Return the currently selected Speech Blocks profile id.
        @return     Selected profile identifier or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        value = self._profile_combo.currentData()
        return None if value in (None, "") else str(value)

    def selected_chunk_id(self) -> str | None:
        """
        @brief      Return the identifier of the currently selected source chunk.
        @return     Selected chunk id or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        return self._current_chunk_id

    def selected_block_id(self) -> str | None:
        """
        @brief      Return the identifier of the currently selected speech block.
        @return     Selected speech-block id or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        return self._current_block_id

    def source_scroll_position(self) -> int:
        """
        @brief      Return the selected-chunk text vertical scroll position.
        @return     Current vertical scrollbar value.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        return int(self._source_text_edit.verticalScrollBar().value())

    def restore_source_scroll_position(self, scroll_position: int) -> None:
        """
        @brief      Restore the selected-chunk text vertical scroll position.
        @param[in]  scroll_position Vertical scrollbar value to restore.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.2.0
        """
        self._restore_source_scroll_position(scroll_position)
        QTimer.singleShot(0, lambda: self._restore_source_scroll_position(scroll_position))

    def advance_to_next_block(self) -> None:
        """
        @brief      Move the visible Speech Block selection one row forward when possible.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        current_row = self._speech_block_list.currentRow()
        if current_row < 0:
            return
        next_row = current_row + 1
        if next_row < self._speech_block_list.count():
            self._speech_block_list.setCurrentRow(next_row)

    def select_speech_block(self, speech_block_id: str) -> None:
        """
        @brief      Select one Speech Block and its owning chunk in the page lists.
        @param[in]  speech_block_id Speech Block identifier to select.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        normalized_id = str(speech_block_id).strip()
        selected_block = next(
            (block for block in self._speech_blocks if str(block.get("speech_block_id", "")).strip() == normalized_id),
            None,
        )
        if selected_block is None:
            return
        selected_chunk_id = str(selected_block.get("chunk_id", "")).strip()
        for chunk_index, chunk in enumerate(self._source_chunks):
            if str(chunk.get("chunk_id", "")).strip() == selected_chunk_id:
                self._chunk_list.setCurrentRow(chunk_index)
                break
        self._select_block_by_id(normalized_id)

    def begin_editing_selected_block(self) -> None:
        """
        @brief      Enable edit mode for the currently selected Speech Block.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        if self.selected_block_id() is None:
            return
        self._editing = True
        self._warning_label.clear()
        self._apply_control_state()

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one translated UI language to the page widgets.
        @param[in]  language Runtime UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.3.0
        """
        self._current_language = language
        self._title_label.setText(f"<h2>{ui_state_service.translate('speech_blocks.title', language)}</h2>")
        self._profile_label.setText(ui_state_service.translate("speech_blocks.ai_profile", language))
        self._generate_button.setText(ui_state_service.translate("speech_blocks.generate", language))
        self._reset_generation_button.setText(ui_state_service.translate("speech_blocks.reset_generation", language))
        self._approve_all_button.setText(ui_state_service.translate("speech_blocks.approve_all", language))
        self._chunk_group.setTitle(ui_state_service.translate("speech_blocks.chunk_list_group", language))
        self._insert_block_button.setText(ui_state_service.translate("speech_blocks.insert_block", language))
        self._delete_block_button.setText(ui_state_service.translate("speech_blocks.delete_block", language))
        self._source_group.setTitle(ui_state_service.translate("speech_blocks.selected_group", language))
        self._blocks_group.setTitle(ui_state_service.translate("speech_blocks.blocks_group", language))
        self._speaker_label.setText(ui_state_service.translate("speech_blocks.detail_speaker", language))
        self._content_kind_label.setText(ui_state_service.translate("speech_blocks.detail_content_kind", language))
        self._resplit_button.setText(ui_state_service.translate("speech_blocks.resplit_selected", language))
        self._reset_block_button.setText(ui_state_service.translate("speech_blocks.reset_block", language))
        self._edit_button.setText(ui_state_service.translate("speech_blocks.edit_block", language))
        self._save_button.setText(ui_state_service.translate("speech_blocks.save_block", language))
        self._approve_block_button.setText(ui_state_service.translate("speech_blocks.approve_block", language))
        self._notes_group.setTitle(ui_state_service.translate("speech_blocks.notes_group", language))
        if self._profile_combo.count() > 0 and self._profile_combo.itemData(0) in (None, ""):
            self._profile_combo.setItemText(0, ui_state_service.translate("ai_settings.none", language))
        current_row = self._speech_block_list.currentRow()
        if current_row >= 0:
            self._show_selected_block(current_row)

    def _populate_selectors(self) -> None:
        """
        @brief      Refresh speaker and content-kind selector values.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        self._speaker_combo.blockSignals(True)
        self._speaker_combo.clear()
        for speaker_entry in self._speaker_catalog:
            self._speaker_combo.addItem(
                str(speaker_entry.get("display_name", "")),
                str(speaker_entry.get("speaker_id", "")),
            )
        self._speaker_combo.blockSignals(False)
        self._content_kind_combo.blockSignals(True)
        self._content_kind_combo.clear()
        for content_kind, label in self._content_kind_options:
            self._content_kind_combo.addItem(label, content_kind)
        self._content_kind_combo.blockSignals(False)

    def _apply_control_state(self) -> None:
        """
        @brief      Apply the current Speech Blocks page button and widget states.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.3.0
        """
        selected_block = self._current_display_block()
        can_generate = (
            self._project_active
            and not self._busy
            and bool(self._source_chunks)
            and self.current_profile_id() is not None
        )
        can_edit_selected = self._project_active and not self._busy and selected_block is not None
        can_approve_selected = can_edit_selected and not bool(selected_block.get("approved", False))
        can_insert_block = (
            self._project_active and not self._busy and bool(self._speech_blocks) and self._current_chunk_id is not None
        )
        self._profile_combo.setEnabled(self._project_active and not self._busy)
        self._generate_button.setEnabled(can_generate)
        self._reset_generation_button.setEnabled(self._project_active and not self._busy and self._can_reset)
        self._approve_all_button.setEnabled(self._project_active and not self._busy and self._can_approve_all)
        self._resplit_button.setEnabled(
            self._project_active
            and not self._busy
            and self._can_resplit_selected
            and self._current_chunk_id is not None
            and self.current_profile_id() is not None
        )
        self._chunk_list.setEnabled(self._project_active and not self._busy)
        self._insert_block_button.setEnabled(can_insert_block and not self._editing)
        self._delete_block_button.setEnabled(can_edit_selected and not self._editing)
        self._speech_block_list.setEnabled(self._project_active and not self._busy and not self._editing)
        self._speaker_combo.setEnabled(can_edit_selected and self._editing)
        self._content_kind_combo.setEnabled(can_edit_selected and self._editing)
        self._speech_block_text_edit.setReadOnly(not (can_edit_selected and self._editing))
        self._reset_block_button.setEnabled(can_edit_selected and not self._editing)
        self._edit_button.setEnabled(can_edit_selected and not self._editing)
        self._save_button.setEnabled(can_edit_selected and self._editing)
        self._approve_block_button.setEnabled(can_approve_selected and not self._editing)

    def _emit_generate_requested(self) -> None:
        """
        @brief      Emit the Speech Blocks generation request for the selected profile.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        profile_id = self.current_profile_id()
        if profile_id is not None:
            self.generate_requested.emit(profile_id)

    def _emit_resplit_selected(self) -> None:
        """
        @brief      Emit the selected-chunk re-split request.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        chunk_id = self.selected_chunk_id()
        if chunk_id is not None:
            self.resplit_selected_requested.emit(chunk_id)

    def _emit_insert_block(self) -> None:
        """
        @brief      Emit the selected-position Speech Block insertion request.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        chunk_id = self.selected_chunk_id()
        if chunk_id is None:
            return
        self.insert_block_requested.emit(chunk_id, self.selected_block_id() or "")

    def _emit_delete_block(self) -> None:
        """
        @brief      Emit the selected Speech Block deletion request.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        block_id = self.selected_block_id()
        if block_id is not None:
            self.delete_block_requested.emit(block_id)

    def _show_selected_chunk(self, row: int) -> None:
        """
        @brief      Display the currently selected source chunk and its generated blocks.
        @param[in]  row Selected chunk-list row.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.2.0
        """
        self._editing = False
        self._speech_block_list.clear()
        self._clear_block_details()
        if row < 0 or row >= len(self._source_chunks):
            self._current_chunk_id = None
            self._source_text_edit.clear()
            self._apply_control_state()
            return
        selected_chunk = self._source_chunks[row]
        self._current_chunk_id = str(selected_chunk.get("chunk_id", ""))
        self._source_text_edit.setPlainText(str(selected_chunk.get("text", "")))
        blocks_for_chunk = self._blocks_for_current_chunk()
        for block in blocks_for_chunk:
            self._speech_block_list.addItem(_format_speech_block_list_item(block))
        if blocks_for_chunk:
            self._speech_block_list.setCurrentRow(0)
        self._apply_control_state()

    def _show_selected_block(self, row: int) -> None:
        """
        @brief      Display the selected speech block details.
        @param[in]  row Selected speech-block list row.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.2.0
        """
        self._editing = False
        blocks_for_chunk = self._blocks_for_current_chunk()
        if row < 0 or row >= len(blocks_for_chunk):
            self._clear_block_details()
            self._apply_control_state()
            return
        selected_block = blocks_for_chunk[row]
        self._current_block_id = str(selected_block.get("speech_block_id", ""))
        self._set_combo_value(self._speaker_combo, str(selected_block.get("speaker_id", "")))
        self._set_combo_value(self._content_kind_combo, str(selected_block.get("content_kind", "")))
        self._speech_block_text_edit.setPlainText(str(selected_block.get("text", "")))
        self._warning_label.setText(_format_warning_label(selected_block, self._current_language))
        self._apply_control_state()

    def _clear_block_details(self) -> None:
        """
        @brief      Clear the selected Speech Block detail controls.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        self._current_block_id = None
        self._speech_block_text_edit.clear()
        self._warning_label.clear()

    def _begin_editing(self) -> None:
        """
        @brief      Enable selected-block editing and clear the warning indicator.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        block_id = self.selected_block_id()
        if block_id is None:
            return
        self._editing = True
        self._warning_label.clear()
        self.edit_started.emit(block_id)
        self._apply_control_state()

    def _emit_save_block(self) -> None:
        """
        @brief      Emit the selected-block save request.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        block_id = self.selected_block_id()
        if block_id is None:
            return
        self._editing = False
        self.save_block_requested.emit(
            block_id,
            str(self._speaker_combo.currentData() or ""),
            str(self._content_kind_combo.currentData() or ""),
            self._speech_block_text_edit.toPlainText(),
        )
        self._apply_control_state()

    def _emit_reset_block(self) -> None:
        """
        @brief      Emit the selected-block AI-baseline reset request.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        block_id = self.selected_block_id()
        if block_id is not None:
            self.reset_block_requested.emit(block_id)

    def _emit_approve_block(self) -> None:
        """
        @brief      Emit the selected-block approval request.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        block_id = self.selected_block_id()
        if block_id is not None:
            self.approve_block_requested.emit(block_id)

    def _blocks_for_current_chunk(self) -> list[dict[str, object]]:
        """
        @brief      Return Speech Blocks belonging to the selected source chunk.
        @return     Ordered Speech Blocks for the selected chunk.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        if self._current_chunk_id is None:
            return []
        return [block for block in self._speech_blocks if str(block.get("chunk_id", "")) == self._current_chunk_id]

    def _current_display_block(self) -> dict[str, object] | None:
        """
        @brief      Return the currently selected Speech Block payload.
        @return     Selected block or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        if self._current_block_id is None:
            return None
        return next(
            (
                block
                for block in self._speech_blocks
                if str(block.get("speech_block_id", "")).strip() == self._current_block_id
            ),
            None,
        )

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        """
        @brief      Select one combo entry by data value when present.
        @param[in]  combo Target combo box.
        @param[in]  value Desired item data value.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        index = combo.findData(value)
        combo.setCurrentIndex(0 if index < 0 else index)

    def _select_block_by_id(self, speech_block_id: str | None) -> None:
        """
        @brief      Restore one Speech Block selection in the visible block list.
        @param[in]  speech_block_id Speech Block identifier to restore.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        if speech_block_id is None:
            return
        for index, block in enumerate(self._blocks_for_current_chunk()):
            if str(block.get("speech_block_id", "")).strip() == speech_block_id:
                self._speech_block_list.setCurrentRow(index)
                return

    def _restore_source_scroll_position(self, scroll_position: int) -> None:
        """
        @brief      Restore the selected-chunk text vertical scroll position after refresh.
        @param[in]  scroll_position Previous vertical scrollbar value.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        scroll_bar = self._source_text_edit.verticalScrollBar()
        bounded_position = max(scroll_bar.minimum(), min(scroll_position, scroll_bar.maximum()))
        scroll_bar.setValue(bounded_position)


def _block_count_by_chunk(speech_blocks: list[dict[str, object]]) -> dict[str, int]:
    """
    @brief      Count generated blocks by chunk identifier.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @return     Mapping from chunk id to block count.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    counts: dict[str, int] = {}
    for block in speech_blocks:
        chunk_id = str(block.get("chunk_id", "")).strip()
        if not chunk_id:
            continue
        counts[chunk_id] = counts.get(chunk_id, 0) + 1
    return counts


def _format_chunk_list_item(source_chunk: dict[str, object], block_count_by_chunk: dict[str, int]) -> str:
    """
    @brief      Format one chunk row label for the Speech Blocks chunk list.
    @param[in]  source_chunk Source chunk payload.
    @param[in]  block_count_by_chunk Mapping from chunk id to block count.
    @return     Human-readable chunk row label.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    chunk_id = str(source_chunk.get("chunk_id", ""))
    preview = str(source_chunk.get("text", ""))
    if len(preview) > 86:
        preview = preview[:83] + "..."
    return f"[{block_count_by_chunk.get(chunk_id, 0)}] {chunk_id} | {preview}"


def _format_speech_block_list_item(speech_block: dict[str, object]) -> str:
    """
    @brief      Format one generated speech-block row label.
    @param[in]  speech_block Speech Blocks payload.
    @return     Human-readable speech-block row label.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    preview = str(speech_block.get("text", ""))
    if len(preview) > 52:
        preview = preview[:49] + "..."
    warning_marker = "!" if speech_block.get("warning_flags", []) else " "
    approval_marker = "ok" if bool(speech_block.get("approved", False)) else "--"
    return (
        f"[{approval_marker}] [{warning_marker}] {speech_block.get('speech_block_id', '')} | "
        f"{speech_block.get('speaker_display_name', '')} | {preview}"
    )


def _format_warning_label(speech_block: dict[str, object], language: str) -> str:
    """
    @brief      Format the selected-block warning indicator text.
    @param[in]  speech_block Selected Speech Block payload.
    @param[in]  language Runtime UI language code.
    @return     Warning label text or empty string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    warning_flags = [str(flag) for flag in speech_block.get("warning_flags", [])]
    if not warning_flags:
        return ""
    return ui_state_service.translate("speech_blocks.warning_indicator", language).format(
        warning_flags=", ".join(warning_flags)
    )


# END OF FILE
