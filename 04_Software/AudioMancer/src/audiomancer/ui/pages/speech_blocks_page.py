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
@details Provides read-only chunk review, generated speech-block inspection,
         AI profile selection, and generation controls for the Speech Blocks
         workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-21
@version 0.1.1
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

from audiomancer.services import speech_blocks_service, ui_state_service


class SpeechBlocksPage(QWidget):
    """
    @brief      Display the Speech Blocks workflow surface.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.1
    """

    generate_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the Speech Blocks page widgets.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.1
        """
        super().__init__(parent)
        self._current_language = "en"
        self._project_active = False
        self._busy = False
        self._stage_status = speech_blocks_service.SPEECH_BLOCKS_STAGE_NOT_STARTED
        self._source_chunks: list[dict[str, object]] = []
        self._speech_blocks: list[dict[str, object]] = []
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
        layout.addLayout(header_row)

        top_splitter = QSplitter(self)

        self._chunk_group = QGroupBox("Chunk List", self)
        chunk_layout = QVBoxLayout(self._chunk_group)
        self._chunk_list = QListWidget(self)
        self._chunk_list.currentRowChanged.connect(self._show_selected_chunk)
        chunk_layout.addWidget(self._chunk_list)
        top_splitter.addWidget(self._chunk_group)

        self._source_group = QGroupBox("Selected Chunk", self)
        source_layout = QVBoxLayout(self._source_group)
        self._source_text_edit = QPlainTextEdit(self)
        self._source_text_edit.setReadOnly(True)
        source_layout.addWidget(self._source_text_edit)
        top_splitter.addWidget(self._source_group)

        self._blocks_group = QGroupBox("Speech Blocks", self)
        blocks_layout = QVBoxLayout(self._blocks_group)
        self._speech_block_list = QListWidget(self)
        self._speech_block_list.currentRowChanged.connect(self._show_selected_block)
        blocks_layout.addWidget(self._speech_block_list, 4)
        self._speech_block_details = QPlainTextEdit(self)
        self._speech_block_details.setReadOnly(True)
        blocks_layout.addWidget(self._speech_block_details, 5)
        top_splitter.addWidget(self._blocks_group)
        top_splitter.setStretchFactor(0, 3)
        top_splitter.setStretchFactor(1, 4)
        top_splitter.setStretchFactor(2, 5)
        layout.addWidget(top_splitter, 1)

        self._notes_group = QGroupBox("Speech Blocks Notes", self)
        notes_layout = QVBoxLayout(self._notes_group)
        self._notes_edit = QPlainTextEdit(self)
        self._notes_edit.setReadOnly(True)
        notes_layout.addWidget(self._notes_edit)
        self._notes_group.setMinimumHeight(96)
        self._notes_group.setMaximumHeight(132)
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
            self._profile_combo.addItem("(none)", None)
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
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        _ = selected_source_language
        _ = processed_chunk_count
        _ = total_chunk_count
        self._source_chunks = sorted(source_chunks, key=lambda item: int(item.get("sequence_index", 0)))
        self._speech_blocks = sorted(speech_blocks, key=lambda item: int(item.get("sequence_index", 0)))
        self._stage_status = stage_status
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

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one translated UI language to the page widgets.
        @param[in]  language Runtime UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self._current_language = language
        self._title_label.setText(f"<h2>{ui_state_service.translate('speech_blocks.title', language)}</h2>")
        self._profile_label.setText(ui_state_service.translate("speech_blocks.ai_profile", language))
        self._generate_button.setText(ui_state_service.translate("speech_blocks.generate", language))
        self._chunk_group.setTitle(ui_state_service.translate("speech_blocks.chunk_list_group", language))
        self._source_group.setTitle(ui_state_service.translate("speech_blocks.selected_group", language))
        self._blocks_group.setTitle(ui_state_service.translate("speech_blocks.blocks_group", language))
        self._notes_group.setTitle(ui_state_service.translate("speech_blocks.notes_group", language))
        if self._profile_combo.count() > 0 and self._profile_combo.itemData(0) in (None, ""):
            self._profile_combo.setItemText(0, ui_state_service.translate("ai_settings.none", language))
        current_row = self._speech_block_list.currentRow()
        if current_row >= 0:
            self._show_selected_block(current_row)

    def _apply_control_state(self) -> None:
        """
        @brief      Apply the current Speech Blocks page button and widget states.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        can_generate = (
            self._project_active
            and not self._busy
            and bool(self._source_chunks)
            and self.current_profile_id() is not None
        )
        self._profile_combo.setEnabled(self._project_active and not self._busy)
        self._generate_button.setEnabled(can_generate)
        self._chunk_list.setEnabled(self._project_active)
        self._speech_block_list.setEnabled(self._project_active)

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

    def _show_selected_chunk(self, row: int) -> None:
        """
        @brief      Display the currently selected source chunk and its generated blocks.
        @param[in]  row Selected chunk-list row.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self._speech_block_list.clear()
        self._speech_block_details.clear()
        self._current_block_id = None
        if row < 0 or row >= len(self._source_chunks):
            self._current_chunk_id = None
            self._source_text_edit.clear()
            self._apply_control_state()
            return
        selected_chunk = self._source_chunks[row]
        self._current_chunk_id = str(selected_chunk.get("chunk_id", ""))
        self._source_text_edit.setPlainText(str(selected_chunk.get("text", "")))
        blocks_for_chunk = [
            block for block in self._speech_blocks if str(block.get("chunk_id", "")) == self._current_chunk_id
        ]
        for block in blocks_for_chunk:
            self._speech_block_list.addItem(_format_speech_block_list_item(block))
        if blocks_for_chunk:
            self._speech_block_list.setCurrentRow(0)
        self._apply_control_state()

    def _show_selected_block(self, row: int) -> None:
        """
        @brief      Display the selected speech block details in the read-only panel.
        @param[in]  row Selected speech-block list row.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        if self._current_chunk_id is None:
            self._current_block_id = None
            self._speech_block_details.clear()
            return
        blocks_for_chunk = [
            block for block in self._speech_blocks if str(block.get("chunk_id", "")) == self._current_chunk_id
        ]
        if row < 0 or row >= len(blocks_for_chunk):
            self._current_block_id = None
            self._speech_block_details.clear()
            return
        selected_block = blocks_for_chunk[row]
        self._current_block_id = str(selected_block.get("speech_block_id", ""))
        content_kind = str(selected_block.get("content_kind", ""))
        content_kind_label = ui_state_service.translate(
            "speech_blocks.content_dialogue"
            if content_kind == speech_blocks_service.CONTENT_KIND_DIALOGUE
            else "speech_blocks.content_narration",
            self._current_language,
        )
        detail_lines = [
            (
                f"{ui_state_service.translate('speech_blocks.detail_speaker', self._current_language)}: "
                f"{selected_block.get('speaker_display_name', '')}"
            ),
            (
                f"{ui_state_service.translate('speech_blocks.detail_block_id', self._current_language)}: "
                f"{selected_block.get('speech_block_id', '')}"
            ),
            (
                f"{ui_state_service.translate('speech_blocks.detail_content_kind', self._current_language)}: "
                f"{content_kind_label}"
            ),
            (
                f"{ui_state_service.translate('speech_blocks.detail_warning_flags', self._current_language)}: "
                f"{', '.join(selected_block.get('warning_flags', [])) or ui_state_service.translate('speech_blocks.detail_none', self._current_language)}"
            ),
            "",
            str(selected_block.get("text", "")),
        ]
        self._speech_block_details.setPlainText("\n".join(detail_lines))


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
    if len(preview) > 56:
        preview = preview[:53] + "..."
    return f"[{block_count_by_chunk.get(chunk_id, 0)}] {chunk_id} | {preview}"


def _format_speech_block_list_item(speech_block: dict[str, object]) -> str:
    """
    @brief      Format one generated speech-block row label.
    @param[in]  speech_block Speech Blocks payload.
    @return     Human-readable speech-block row label.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    preview = str(speech_block.get("text", ""))
    if len(preview) > 56:
        preview = preview[:53] + "..."
    return f"{speech_block.get('speaker_display_name', '')} | {speech_block.get('speech_block_id', '')} | {preview}"


# END OF FILE
