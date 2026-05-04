#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audio_blocks_page.py
@brief Audio Blocks workflow page for AudioMancer.
@details Provides resumable per-speech-block audio generation, approval, and
         review controls for the Audio Blocks workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-23
@version 0.4.0
"""

# IMPORTS

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from audiomancer.services import audio_blocks_service, speech_blocks_service, ui_state_service


class AudioBlocksPage(QWidget):
    """
    @brief      Display the Audio Blocks workflow surface.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """

    start_generation_requested = Signal()
    reset_generation_requested = Signal()
    approve_all_requested = Signal()
    audiobook_playback_toggle_requested = Signal()
    regenerate_selected_requested = Signal(str)
    approve_selected_requested = Signal(str)
    unapprove_selected_requested = Signal(str)
    reset_selected_requested = Signal(str)
    selected_playback_toggle_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the Audio Blocks page widgets.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-23
        @version    0.4.0
        """
        super().__init__(parent)
        self._current_language = "en"
        self._project_active = False
        self._busy = False
        self._selected_playback_active = False
        self._audiobook_playback_active = False
        self._stage_status = audio_blocks_service.AUDIO_BLOCKS_STAGE_NOT_STARTED
        self._speech_blocks: list[dict[str, object]] = []
        self._current_block_id: str | None = None

        layout = QVBoxLayout(self)
        header_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Audio Blocks</h2>")
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)
        self._start_button = QPushButton("Start Audio Generation")
        self._start_button.clicked.connect(self.start_generation_requested.emit)
        header_row.addWidget(self._start_button)
        self._audiobook_playback_button = QPushButton("Play Audiobook")
        self._audiobook_playback_button.clicked.connect(self.audiobook_playback_toggle_requested.emit)
        header_row.addWidget(self._audiobook_playback_button)
        self._reset_button = QPushButton("Reset Audio Generation")
        self._reset_button.clicked.connect(self.reset_generation_requested.emit)
        header_row.addWidget(self._reset_button)
        self._approve_all_button = QPushButton("Approve All Generation")
        self._approve_all_button.clicked.connect(self.approve_all_requested.emit)
        header_row.addWidget(self._approve_all_button)
        layout.addLayout(header_row)

        self._progress_label = QLabel("0/0")
        layout.addWidget(self._progress_label)
        self._progress_bar = QProgressBar(self)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("%p%")
        layout.addWidget(self._progress_bar)

        self._main_splitter = QSplitter(self)
        self._main_splitter.setChildrenCollapsible(False)

        self._source_group = QGroupBox("Source Text", self)
        source_layout = QVBoxLayout(self._source_group)
        self._source_text_edit = QPlainTextEdit(self)
        self._source_text_edit.setReadOnly(True)
        source_layout.addWidget(self._source_text_edit)
        self._main_splitter.addWidget(self._source_group)

        self._right_splitter = QSplitter(self)
        self._right_splitter.setOrientation(Qt.Orientation.Vertical)

        self._blocks_group = QGroupBox("Speech Blocks", self)
        blocks_layout = QVBoxLayout(self._blocks_group)
        self._speech_block_list = QListWidget(self)
        self._speech_block_list.currentRowChanged.connect(self._show_selected_block)
        blocks_layout.addWidget(self._speech_block_list)
        self._right_splitter.addWidget(self._blocks_group)

        self._detail_group = QGroupBox("Selected Block", self)
        detail_layout = QVBoxLayout(self._detail_group)
        detail_meta_row = QHBoxLayout()
        self._speaker_label = QLabel("")
        detail_meta_row.addWidget(self._speaker_label)
        detail_meta_row.addStretch(1)
        self._approval_status_label = QLabel("")
        detail_meta_row.addWidget(self._approval_status_label)
        detail_layout.addLayout(detail_meta_row)
        self._block_text_edit = QPlainTextEdit(self)
        self._block_text_edit.setReadOnly(True)
        detail_layout.addWidget(self._block_text_edit)
        action_row = QHBoxLayout()
        self._regenerate_button = QPushButton("Re-Generate Audio")
        self._regenerate_button.clicked.connect(self._emit_regenerate_selected)
        action_row.addWidget(self._regenerate_button)
        self._selected_playback_button = QPushButton("Play")
        self._selected_playback_button.clicked.connect(self._emit_selected_playback_toggle)
        action_row.addWidget(self._selected_playback_button)
        self._approve_button = QPushButton("Approve")
        self._approve_button.clicked.connect(self._emit_approve_selected)
        action_row.addWidget(self._approve_button)
        self._unapprove_button = QPushButton("Unapprove")
        self._unapprove_button.clicked.connect(self._emit_unapprove_selected)
        action_row.addWidget(self._unapprove_button)
        self._reset_selected_button = QPushButton("Reset Selected")
        self._reset_selected_button.clicked.connect(self._emit_reset_selected)
        action_row.addWidget(self._reset_selected_button)
        detail_layout.addLayout(action_row)
        self._right_splitter.addWidget(self._detail_group)
        self._right_splitter.setStretchFactor(0, 4)
        self._right_splitter.setStretchFactor(1, 5)
        self._main_splitter.addWidget(self._right_splitter)
        self._main_splitter.setStretchFactor(0, 4)
        self._main_splitter.setStretchFactor(1, 4)
        self._main_splitter.setSizes([480, 620])
        layout.addWidget(self._main_splitter, 1)
        self._apply_main_splitter_minimums()

        self._status_group = QGroupBox("Audio Blocks Status", self)
        status_layout = QVBoxLayout(self._status_group)
        self._status_edit = QPlainTextEdit(self)
        self._status_edit.setReadOnly(True)
        status_layout.addWidget(self._status_edit)
        self._status_group.setMinimumHeight(96)
        self._status_group.setMaximumHeight(112)
        layout.addWidget(self._status_group)

        self.apply_language(self._current_language)
        self.set_project_active(False)
        self.set_audio_blocks_state(
            full_source_text="",
            speech_blocks=[],
            current_block_id=None,
            current_block_speaker="",
            current_block_text="",
            notes=[ui_state_service.translate("audio_blocks.note_no_project", self._current_language)],
            status_lines=[],
            progress_current=0,
            progress_total=0,
            progress_percent=0,
            stage_status=audio_blocks_service.AUDIO_BLOCKS_STAGE_NOT_STARTED,
            can_start_or_continue=False,
            can_reset=False,
            can_approve_all=False,
            can_regenerate_selected=False,
            can_approve_selected=False,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        """
        @brief      Keep Audio Blocks main splitter panes from shrinking below one third of the content width.
        @param[in]  event Qt resize event.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-01
        @version    0.2.0
        """
        super().resizeEvent(event)
        self._apply_main_splitter_minimums()

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Enable or disable page interactions based on project state.
        @param[in]  is_active True when a project is currently open.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-23
        @version    0.2.0
        """
        self._project_active = is_active
        self._apply_control_state()

    def set_audio_blocks_state(
        self,
        full_source_text: str,
        speech_blocks: list[dict[str, object]],
        current_block_id: str | None,
        current_block_speaker: str,
        current_block_text: str,
        notes: list[str],
        status_lines: list[str],
        progress_current: int,
        progress_total: int,
        progress_percent: int,
        stage_status: str,
        can_start_or_continue: bool,
        can_reset: bool,
        can_approve_all: bool,
        can_regenerate_selected: bool,
        can_approve_selected: bool,
        **_extra_state,
    ) -> None:
        """
        @brief      Refresh the Audio Blocks page from controller-provided state.
        @param[in]  full_source_text Read-only reconstructed source text.
        @param[in]  speech_blocks Current merged Speech Blocks plus Audio Blocks display list.
        @param[in]  current_block_id Preferred current speech-block identifier or `None`.
        @param[in]  current_block_speaker Preferred current speaker label.
        @param[in]  current_block_text Preferred current block text.
        @param[in]  notes Operator-facing note lines.
        @param[in]  status_lines Operator-facing status lines.
        @param[in]  progress_current Current generated-block count.
        @param[in]  progress_total Total speech-block count.
        @param[in]  progress_percent Current integer progress percent.
        @param[in]  stage_status Effective Audio Blocks stage token.
        @param[in]  can_start_or_continue Controller-resolved start/continue enablement flag.
        @param[in]  can_reset Controller-resolved reset enablement flag.
        @param[in]  can_approve_all Controller-resolved approve-all enablement flag.
        @param[in]  can_regenerate_selected Controller-resolved selected regenerate enablement flag.
        @param[in]  can_approve_selected Controller-resolved selected approve enablement flag.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-23
        @version    0.3.0
        """
        self._speech_blocks = speech_blocks_service.sort_speech_blocks(speech_blocks)
        self._stage_status = stage_status
        self._can_start_or_continue = can_start_or_continue
        self._can_reset = can_reset
        self._can_approve_all = can_approve_all
        self._can_regenerate_selected = can_regenerate_selected
        self._can_approve_selected = can_approve_selected
        self._source_text_edit.setPlainText(full_source_text)
        self._progress_bar.setValue(max(0, min(int(progress_percent), 100)))
        self._progress_label.setText(
            ui_state_service.translate("audio_blocks.progress_label", self._current_language).format(
                progress_current=progress_current,
                progress_total=progress_total,
            )
        )
        self._status_edit.setPlainText("\n".join([*notes, "", *status_lines]).strip())
        previously_selected_id = self._current_block_id
        self._speech_block_list.clear()
        for speech_block in self._speech_blocks:
            self._speech_block_list.addItem(_format_audio_block_list_item(speech_block, self._current_language))
        row_to_select = 0
        desired_block_id = current_block_id or previously_selected_id
        if desired_block_id is not None:
            for index, speech_block in enumerate(self._speech_blocks):
                if str(speech_block.get("speech_block_id", "")).strip() == desired_block_id:
                    row_to_select = index
                    break
        if self._speech_blocks:
            self._speech_block_list.setCurrentRow(row_to_select)
        else:
            self._current_block_id = current_block_id
            self._speaker_label.setText(current_block_speaker)
            self._block_text_edit.setPlainText(current_block_text)
        self._apply_control_state()

    def set_busy(self, is_busy: bool) -> None:
        """
        @brief      Disable page actions while a blocking Audio Blocks task runs.
        @param[in]  is_busy True while the page is busy.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-23
        @version    0.2.0
        """
        self._busy = is_busy
        self._apply_control_state()

    def set_selected_playback_active(self, is_active: bool) -> None:
        """
        @brief      Toggle selected-block playback state and button labeling.
        @param[in]  is_active True while selected-block playback is active.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        self._selected_playback_active = is_active
        if is_active:
            self._audiobook_playback_active = False
        self._apply_control_state()

    def set_audiobook_playback_active(self, is_active: bool) -> None:
        """
        @brief      Toggle audiobook playback state and button labeling.
        @param[in]  is_active True while audiobook playback is active.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        self._audiobook_playback_active = is_active
        if is_active:
            self._selected_playback_active = False
        self._apply_control_state()

    def selected_block_id(self) -> str | None:
        """
        @brief      Return the identifier of the currently selected speech block.
        @return     Selected speech-block id or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-23
        @version    0.2.0
        """
        return self._current_block_id

    def select_block_id(self, speech_block_id: str) -> None:
        """
        @brief      Select one speech block row by identifier.
        @param[in]  speech_block_id Speech-block identifier to select.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        normalized_block_id = str(speech_block_id).strip()
        for row, speech_block in enumerate(self._speech_blocks):
            if str(speech_block.get("speech_block_id", "")).strip() == normalized_block_id:
                self._speech_block_list.setCurrentRow(row)
                return

    def advance_to_next_block(self) -> None:
        """
        @brief      Move the Audio Blocks speech-block selection one row forward when possible.
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

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one translated UI language to the page widgets.
        @param[in]  language Runtime UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-23
        @version    0.1.0
        """
        self._current_language = language
        self._title_label.setText(f"<h2>{ui_state_service.translate('audio_blocks.title', language)}</h2>")
        self._start_button.setText(ui_state_service.translate("audio_blocks.start_generation", language))
        self._audiobook_playback_button.setText(
            ui_state_service.translate(self._audiobook_playback_label_key(), language)
        )
        self._reset_button.setText(ui_state_service.translate("audio_blocks.reset_generation", language))
        self._approve_all_button.setText(ui_state_service.translate("audio_blocks.approve_all", language))
        self._source_group.setTitle(ui_state_service.translate("audio_blocks.source_group", language))
        self._blocks_group.setTitle(ui_state_service.translate("audio_blocks.blocks_group", language))
        self._detail_group.setTitle(ui_state_service.translate("audio_blocks.selected_group", language))
        self._regenerate_button.setText(ui_state_service.translate("audio_blocks.regenerate_selected", language))
        self._selected_playback_button.setText(
            ui_state_service.translate(self._selected_playback_label_key(), language)
        )
        self._approve_button.setText(ui_state_service.translate("audio_blocks.approve_selected", language))
        self._unapprove_button.setText(ui_state_service.translate("audio_blocks.unapprove_selected", language))
        self._reset_selected_button.setText(ui_state_service.translate("audio_blocks.reset_selected", language))
        self._status_group.setTitle(ui_state_service.translate("audio_blocks.status_group", language))
        current_row = self._speech_block_list.currentRow()
        if current_row >= 0:
            self._show_selected_block(current_row)

    def _apply_control_state(self) -> None:
        """
        @brief      Apply the current Audio Blocks page button and widget states.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-23
        @version    0.2.0
        """
        selected_block = self._current_display_block()
        self._start_button.setEnabled(self._project_active and not self._busy and self._can_start_or_continue)
        self._audiobook_playback_button.setEnabled(
            self._project_active
            and any(bool(block.get("can_play", False)) for block in self._speech_blocks)
            and (not self._busy or self._audiobook_playback_active)
        )
        self._audiobook_playback_button.setText(
            ui_state_service.translate(self._audiobook_playback_label_key(), self._current_language)
        )
        self._reset_button.setEnabled(self._project_active and not self._busy and self._can_reset)
        self._approve_all_button.setEnabled(self._project_active and not self._busy and self._can_approve_all)
        self._regenerate_button.setEnabled(self._project_active and not self._busy and selected_block is not None)
        self._selected_playback_button.setEnabled(
            self._project_active
            and selected_block is not None
            and bool(selected_block.get("can_play", False))
            and (not self._busy or self._selected_playback_active)
        )
        self._selected_playback_button.setText(
            ui_state_service.translate(self._selected_playback_label_key(), self._current_language)
        )
        self._approve_button.setEnabled(
            self._project_active
            and not self._busy
            and selected_block is not None
            and bool(selected_block.get("generated", False))
            and not bool(selected_block.get("approved", False))
        )
        self._unapprove_button.setEnabled(
            self._project_active
            and not self._busy
            and selected_block is not None
            and bool(selected_block.get("generated", False))
            and bool(selected_block.get("approved", False))
        )
        self._reset_selected_button.setEnabled(
            self._project_active
            and not self._busy
            and selected_block is not None
            and bool(selected_block.get("generated", False))
        )
        self._speech_block_list.setEnabled(self._project_active and not self._busy)

    def _apply_main_splitter_minimums(self) -> None:
        """
        @brief      Set each Audio Blocks main pane minimum width to one third of the main splitter width.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-01
        @version    0.1.0
        """
        required_attributes = ("_main_splitter", "_source_group", "_right_splitter")
        if not all(hasattr(self, attribute_name) for attribute_name in required_attributes):
            return
        splitter_width = self._main_splitter.width()
        if splitter_width <= 0:
            return
        minimum_pane_width = splitter_width // 3
        self._source_group.setMinimumWidth(minimum_pane_width)
        self._right_splitter.setMinimumWidth(minimum_pane_width)

    def _selected_playback_label_key(self) -> str:
        """
        @brief      Resolve the selected-block playback button translation key.
        @return     Translation key for the current selected-block playback state.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        return "audio_blocks.stop_playback" if self._selected_playback_active else "audio_blocks.play_selected"

    def _audiobook_playback_label_key(self) -> str:
        """
        @brief      Resolve the audiobook playback button translation key.
        @return     Translation key for the current audiobook playback state.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        return "audio_blocks.stop_audiobook" if self._audiobook_playback_active else "audio_blocks.play_audiobook"

    def _show_selected_block(self, row: int) -> None:
        """
        @brief      Display the selected speech block details in the read-only panel.
        @param[in]  row Selected speech-block list row.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-23
        @version    0.2.0
        """
        if row < 0 or row >= len(self._speech_blocks):
            self._current_block_id = None
            self._speaker_label.clear()
            self._approval_status_label.clear()
            self._block_text_edit.clear()
            self._apply_control_state()
            return
        selected_block = self._speech_blocks[row]
        self._current_block_id = str(selected_block.get("speech_block_id", "")).strip()
        self._speaker_label.setText(
            ui_state_service.translate("audio_blocks.detail_speaker", self._current_language).format(
                speaker_label=str(selected_block.get("speaker_display_name", ""))
            )
        )
        status_key = (
            "audio_blocks.approval_status_approved"
            if bool(selected_block.get("approved", False))
            else ("audio_blocks.approval_status_pending")
        )
        self._approval_status_label.setText(
            ui_state_service.translate("audio_blocks.detail_approval_status", self._current_language).format(
                status_label=ui_state_service.translate(status_key, self._current_language)
            )
        )
        self._block_text_edit.setPlainText(str(selected_block.get("text", "")))
        self._apply_control_state()

    def _current_display_block(self) -> dict[str, object] | None:
        """
        @brief      Return the display-model payload for the selected speech block.
        @return     Selected display-block payload or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-23
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

    def _emit_regenerate_selected(self) -> None:
        """
        @brief      Emit the regenerate-selected signal for the active speech block.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-23
        @version    0.1.0
        """
        speech_block_id = self.selected_block_id()
        if speech_block_id is not None:
            self.regenerate_selected_requested.emit(speech_block_id)

    def _emit_approve_selected(self) -> None:
        """
        @brief      Emit the approve-selected signal for the active speech block.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-23
        @version    0.1.0
        """
        speech_block_id = self.selected_block_id()
        if speech_block_id is not None:
            self.approve_selected_requested.emit(speech_block_id)

    def _emit_unapprove_selected(self) -> None:
        """
        @brief      Emit the unapprove-selected signal for the active speech block.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-04
        @version    0.1.0
        """
        speech_block_id = self.selected_block_id()
        if speech_block_id is not None:
            self.unapprove_selected_requested.emit(speech_block_id)

    def _emit_reset_selected(self) -> None:
        """
        @brief      Emit the reset-selected signal for the active speech block.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-04
        @version    0.1.0
        """
        speech_block_id = self.selected_block_id()
        if speech_block_id is not None:
            self.reset_selected_requested.emit(speech_block_id)

    def _emit_selected_playback_toggle(self) -> None:
        """
        @brief      Emit the selected playback toggle signal for the active speech block.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        speech_block_id = self.selected_block_id()
        if speech_block_id is not None:
            self.selected_playback_toggle_requested.emit(speech_block_id)


def _format_audio_block_list_item(audio_block: dict[str, object], language: str) -> str:
    """
    @brief      Format one Audio Blocks row label with generated, approved, and current-state markers.
    @param[in]  audio_block Audio Blocks display payload.
    @param[in]  language Runtime UI language code.
    @return     Human-readable Audio Blocks list row label.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.3.0
    """
    approval_label = ui_state_service.translate(
        "audio_blocks.marker_approved" if bool(audio_block.get("approved", False)) else "audio_blocks.marker_pending",
        language,
    )
    duration_label = _format_duration_label(audio_block.get("audio_duration_seconds"), language)
    audio_file_name = str(audio_block.get("audio_file_name", "")).strip()
    file_label = (
        audio_file_name
        or str(audio_block.get("speaker_display_name", "")).strip()
        or (ui_state_service.translate("audio_blocks.marker_missing", language))
    )
    preview = str(audio_block.get("text", ""))
    if len(preview) > 52:
        preview = preview[:49] + "..."
    return f"[{approval_label}] {duration_label} | {file_label} | {preview}"


def _format_duration_label(duration_seconds: object, language: str) -> str:
    """
    @brief      Format one optional audio duration for the Audio Blocks list.
    @param[in]  duration_seconds Optional duration value in seconds.
    @param[in]  language Runtime UI language code.
    @return     Human-readable duration label.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    try:
        duration_value = float(duration_seconds)
    except (TypeError, ValueError):
        return ui_state_service.translate("audio_blocks.duration_unknown", language)
    return ui_state_service.translate("audio_blocks.duration_seconds", language).format(duration_seconds=duration_value)


# END OF FILE
