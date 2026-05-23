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
@version 0.8.6
"""

# IMPORTS

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from audiomancer.services import speech_blocks_service, ui_state_service

# CONSTANTS

_CHUNK_ACTION_TOP_MARGIN_PX = 2
_SOURCE_ACTION_CONTROL_MIN_WIDTH_PX = 180
_SPEAKER_LABEL_WIDTH_PX = 58
_SPEAKER_COMBO_MIN_WIDTH_PX = 88
_SPEAKER_COMBO_MAX_WIDTH_PX = 104
_CONTENT_KIND_LABEL_WIDTH_PX = 88
_CONTENT_KIND_COMBO_MIN_WIDTH_PX = 126
_CONTENT_KIND_COMBO_MAX_WIDTH_PX = 150
_AI_PROFILE_COMBO_MIN_WIDTH_PX = 260
_GENERATE_HEADER_BUTTON_MIN_WIDTH_PX = 140
_RESET_HEADER_BUTTON_MIN_WIDTH_PX = 96
_APPROVE_ALL_HEADER_BUTTON_MIN_WIDTH_PX = 132


class SpeechBlocksPage(QWidget):
    """
    @brief      Display the Speech Blocks workflow surface.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.6.2
    """

    generate_requested = Signal(str)
    reset_generation_requested = Signal()
    approve_all_requested = Signal()
    resplit_selected_requested = Signal(str)
    insert_block_requested = Signal(str, str)
    delete_block_requested = Signal(str)
    edit_started = Signal(str)
    save_block_requested = Signal(str, str, str, object)
    approve_block_requested = Signal(str)
    generate_audio_selected_requested = Signal(str)
    selected_audio_playback_toggle_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the Speech Blocks page widgets.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.7.3
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
        self._voice_assignment_mode = "narrator_and_characters"
        self._processed_chunk_count = 0
        self._total_chunk_count = 0
        self._can_reset = False
        self._can_approve_all = False
        self._can_resplit_selected = False
        self._selected_text_character_limit = 0
        self._current_chunk_id: str | None = None
        self._current_block_id: str | None = None
        self._selected_audio_playback_active = False

        layout = QVBoxLayout(self)
        header_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Speech Blocks</h2>")
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)
        self._profile_label = QLabel("AI Profile")
        header_row.addWidget(self._profile_label)
        self._profile_combo = QComboBox(self)
        self._profile_combo.setMinimumWidth(_AI_PROFILE_COMBO_MIN_WIDTH_PX)
        self._profile_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._profile_combo.addItem("(none)", None)
        header_row.addWidget(self._profile_combo, 1)
        self._generate_button = QPushButton("Generate All")
        self._generate_button.setMinimumWidth(_GENERATE_HEADER_BUTTON_MIN_WIDTH_PX)
        self._generate_button.clicked.connect(self._emit_generate_requested)
        header_row.addWidget(self._generate_button)
        self._reset_generation_button = QPushButton("Reset")
        self._reset_generation_button.setMinimumWidth(_RESET_HEADER_BUTTON_MIN_WIDTH_PX)
        self._reset_generation_button.clicked.connect(self.reset_generation_requested.emit)
        header_row.addWidget(self._reset_generation_button)
        self._approve_all_button = QPushButton("Approve All")
        self._approve_all_button.setMinimumWidth(_APPROVE_ALL_HEADER_BUTTON_MIN_WIDTH_PX)
        self._approve_all_button.clicked.connect(self.approve_all_requested.emit)
        header_row.addWidget(self._approve_all_button)
        layout.addLayout(header_row)

        body_content_layout = QVBoxLayout()
        chunk_row = QHBoxLayout()
        self._chunk_group = QGroupBox("Chunk List", self)
        chunk_layout = QVBoxLayout(self._chunk_group)
        self._chunk_list = QListWidget(self)
        self._chunk_list.currentRowChanged.connect(self._show_selected_chunk)
        chunk_layout.addWidget(self._chunk_list)
        self._chunk_actions_grid_layout = QGridLayout()
        self._chunk_actions_grid_layout.setContentsMargins(0, 0, 0, 0)
        self._insert_block_button = QPushButton("Insert")
        self._insert_block_button.clicked.connect(self._emit_insert_block)
        self._chunk_actions_grid_layout.addWidget(self._insert_block_button, 0, 0)
        self._delete_block_button = QPushButton("Delete")
        self._delete_block_button.clicked.connect(self._emit_delete_block)
        self._chunk_actions_grid_layout.addWidget(self._delete_block_button, 0, 1)
        self._edit_button = QPushButton("Edit")
        self._edit_button.clicked.connect(self._begin_editing)
        self._chunk_actions_grid_layout.addWidget(self._edit_button, 1, 0)
        self._save_button = QPushButton("Save")
        self._save_button.clicked.connect(self._emit_save_block)
        self._chunk_actions_grid_layout.addWidget(self._save_button, 1, 1)
        self._approve_block_button = QPushButton("Approve")
        self._approve_block_button.clicked.connect(self._emit_approve_block)
        self._chunk_actions_grid_layout.addWidget(self._approve_block_button, 2, 0)
        self._character_count_edit = QLineEdit(self)
        self._character_count_edit.setReadOnly(True)
        self._character_count_edit.setMinimumWidth(96)
        self._chunk_actions_grid_layout.addWidget(self._character_count_edit, 2, 1)
        self._generate_audio_button = QPushButton("Generate Audio")
        self._generate_audio_button.clicked.connect(self._emit_generate_audio_selected)
        self._chunk_actions_grid_layout.addWidget(self._generate_audio_button, 3, 0)
        self._selected_audio_playback_button = QPushButton("Play")
        self._selected_audio_playback_button.clicked.connect(self._emit_selected_audio_playback_toggle)
        self._chunk_actions_grid_layout.addWidget(self._selected_audio_playback_button, 3, 1)
        self._chunk_actions_column = QWidget(self)
        self._chunk_actions_column_layout = QVBoxLayout(self._chunk_actions_column)
        self._chunk_actions_column_layout.setContentsMargins(0, 0, 0, 0)
        self._chunk_actions_column_layout.addLayout(self._chunk_actions_grid_layout)
        self._chunk_actions_column_layout.addStretch(1)
        self._apply_chunk_action_top_margin()
        chunk_row.addWidget(self._chunk_group, 1)
        chunk_row.addWidget(self._chunk_actions_column)
        self._chunk_group.setMinimumHeight(94)
        self._chunk_group.setMaximumHeight(130)
        body_content_layout.addLayout(chunk_row)

        self._lower_splitter = QSplitter(self)
        self._lower_splitter.setChildrenCollapsible(False)
        self._source_group = QGroupBox("Selected Chunk", self)
        self._source_layout = QVBoxLayout(self._source_group)
        self._source_text_edit = QPlainTextEdit(self)
        self._source_text_edit.setReadOnly(True)
        self._source_layout.addWidget(self._source_text_edit)
        self._source_action_row = QHBoxLayout()
        self._source_action_row.setContentsMargins(0, 0, 2, 0)
        self._resplit_button = QPushButton("Split Chunk")
        self._resplit_button.setMinimumWidth(_SOURCE_ACTION_CONTROL_MIN_WIDTH_PX)
        self._resplit_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._resplit_button.clicked.connect(self._emit_resplit_selected)
        self._source_action_row.addWidget(self._resplit_button, 1)
        self._source_layout.addLayout(self._source_action_row)
        self._lower_splitter.addWidget(self._source_group)

        self._blocks_group = QGroupBox("Speech Blocks", self)
        blocks_layout = QVBoxLayout(self._blocks_group)
        self._speech_block_list = QListWidget(self)
        self._speech_block_list.currentRowChanged.connect(self._show_selected_block)
        blocks_layout.addWidget(self._speech_block_list, 6)
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        self._speaker_label = QLabel("Speaker")
        self._speaker_label.setFixedWidth(_SPEAKER_LABEL_WIDTH_PX)
        meta_row.addWidget(self._speaker_label)
        self._speaker_combo = QComboBox(self)
        self._speaker_combo.setMinimumWidth(_SPEAKER_COMBO_MIN_WIDTH_PX)
        self._speaker_combo.setMaximumWidth(_SPEAKER_COMBO_MAX_WIDTH_PX)
        self._speaker_combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        meta_row.addWidget(self._speaker_combo)
        self._warning_label = QLabel("")
        self._warning_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        meta_row.addWidget(self._warning_label)
        meta_row.addStretch(1)
        self._content_kind_label = QLabel("Content Kind")
        self._content_kind_label.setFixedWidth(_CONTENT_KIND_LABEL_WIDTH_PX)
        meta_row.addWidget(self._content_kind_label)
        self._content_kind_combo = QComboBox(self)
        self._content_kind_combo.setMinimumWidth(_CONTENT_KIND_COMBO_MIN_WIDTH_PX)
        self._content_kind_combo.setMaximumWidth(_CONTENT_KIND_COMBO_MAX_WIDTH_PX)
        self._content_kind_combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._content_kind_combo.currentIndexChanged.connect(self._refresh_block_detail_editor)
        meta_row.addWidget(self._content_kind_combo)
        blocks_layout.addLayout(meta_row)
        self._speech_block_text_edit = QPlainTextEdit(self)
        self._speech_block_text_edit.textChanged.connect(self._update_selected_text_character_count)
        blocks_layout.addWidget(self._speech_block_text_edit, 5)
        self._ambience_detail_widget = QWidget(self)
        ambience_detail_layout = QFormLayout(self._ambience_detail_widget)
        ambience_detail_layout.setContentsMargins(0, 0, 0, 0)
        ambience_detail_layout.setSpacing(4)
        self._ambient_prompt_side_widget = QWidget(self)
        ambient_prompt_side_layout = QVBoxLayout(self._ambient_prompt_side_widget)
        ambient_prompt_side_layout.setContentsMargins(0, 0, 0, 0)
        ambient_prompt_side_layout.setSpacing(6)
        self._ambient_prompt_label = QLabel("Prompt", self)
        ambient_prompt_side_layout.addWidget(self._ambient_prompt_label)
        ambient_prompt_side_layout.addStretch(1)
        self._ambient_duration_label = QLabel("Duration (s)", self)
        self._ambient_duration_spin = QDoubleSpinBox(self)
        self._ambient_duration_spin.setRange(0.1, 300.0)
        self._ambient_duration_spin.setDecimals(1)
        self._ambient_duration_spin.setSingleStep(0.5)
        self._ambient_duration_spin.setMaximumWidth(128)
        ambient_prompt_side_layout.addWidget(self._ambient_duration_label)
        ambient_prompt_side_layout.addWidget(self._ambient_duration_spin)
        self._ambient_prompt_edit = QPlainTextEdit(self)
        self._ambient_prompt_edit.textChanged.connect(self._update_selected_text_character_count)
        ambience_detail_layout.addRow(self._ambient_prompt_side_widget, self._ambient_prompt_edit)
        self._ambient_negative_prompt_label = QLabel("Negative Prompt", self)
        self._ambient_negative_prompt_edit = QPlainTextEdit(self)
        ambience_detail_layout.addRow(self._ambient_negative_prompt_label, self._ambient_negative_prompt_edit)
        blocks_layout.addWidget(self._ambience_detail_widget, 5)
        self._ambience_detail_widget.hide()
        self._lower_splitter.addWidget(self._blocks_group)
        self._lower_splitter.setStretchFactor(0, 1)
        self._lower_splitter.setStretchFactor(1, 1)
        body_content_layout.addWidget(self._lower_splitter, 1)
        layout.addLayout(body_content_layout, 1)
        self._apply_lower_splitter_minimums()

        self._status_group = QGroupBox("Speech Blocks Status", self)
        status_layout = QVBoxLayout(self._status_group)
        self._status_edit = QPlainTextEdit(self)
        self._status_edit.setReadOnly(True)
        self._status_edit.setProperty(
            ui_state_service.CONTROL_TEXT_FONT_ROLE_PROPERTY,
            ui_state_service.CONTROL_TEXT_FONT_ROLE_VALUE,
        )
        status_layout.addWidget(self._status_edit)
        self._status_group.setMinimumHeight(96)
        self._status_group.setMaximumHeight(112)
        layout.addWidget(self._status_group)

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

    def resizeEvent(self, event) -> None:  # noqa: N802
        """
        @brief      Keep Speech Blocks lower splitter panes from shrinking below one third of its width.
        @param[in]  event Qt resize event.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-01
        @version    0.1.3
        """
        super().resizeEvent(event)
        self._apply_chunk_action_top_margin()
        self._apply_lower_splitter_minimums()

    def _apply_chunk_action_top_margin(self) -> None:
        """
        @brief      Align the chunk action column with the content area inside the Chunk List frame.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-16
        @version    0.1.1
        """
        if not hasattr(self, "_chunk_actions_column_layout"):
            return
        self._chunk_actions_column_layout.setContentsMargins(0, _CHUNK_ACTION_TOP_MARGIN_PX, 0, 0)

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
        voice_assignment_mode: str = "narrator_and_characters",
        can_reset: bool = False,
        can_approve_all: bool = False,
        can_resplit_selected: bool = False,
        selected_text_character_limit: int = 0,
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
        @param[in]  voice_assignment_mode Current project voice-assignment mode.
        @param[in]  can_reset Controller-resolved reset enablement flag.
        @param[in]  can_approve_all Controller-resolved approve-all enablement flag.
        @param[in]  can_resplit_selected Controller-resolved selected re-split enablement flag.
        @param[in]  selected_text_character_limit Approximate selected speech text limit in characters.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.4.1
        """
        _ = selected_source_language
        _ = approved_block_count
        _ = total_block_count
        self._source_chunks = sorted(source_chunks, key=lambda item: int(item.get("sequence_index", 0)))
        self._speech_blocks = speech_blocks_service.sort_speech_blocks(speech_blocks)
        self._speaker_catalog = list(speaker_catalog or [])
        self._content_kind_options = list(content_kind_options or [])
        self._voice_assignment_mode = str(voice_assignment_mode).strip() or "narrator_and_characters"
        self._stage_status = stage_status
        self._processed_chunk_count = max(0, int(processed_chunk_count))
        self._total_chunk_count = max(0, int(total_chunk_count))
        self._can_reset = can_reset
        self._can_approve_all = can_approve_all
        self._can_resplit_selected = can_resplit_selected
        self._selected_text_character_limit = max(0, int(selected_text_character_limit))
        current_block_id = self._current_block_id
        current_review_position = self.review_position()
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
        self._status_edit.setPlainText("\n".join(notes))
        if self._source_chunks:
            selected_row = 0
            if current_chunk_id is not None:
                for index, chunk in enumerate(self._source_chunks):
                    if str(chunk.get("chunk_id", "")) == current_chunk_id:
                        selected_row = index
                        break
            self._chunk_list.setCurrentRow(selected_row)
            self._select_block_by_id(current_block_id)
            self.restore_review_position(current_review_position)
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

    def set_selected_audio_playback_active(self, is_active: bool) -> None:
        """
        @brief      Reflect selected Audio Block playback state on the Speech Blocks page.
        @param[in]  is_active True while selected-block audio playback is active.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-04
        @version    0.1.0
        """
        self._selected_audio_playback_active = bool(is_active)
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

    def review_position(self) -> dict[str, object]:
        """
        @brief      Return the current Speech Blocks review selection and scroll positions.
        @return     Review-position payload suitable for later restoration.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-16
        @version    0.1.0
        """
        return {
            "chunk_id": self.selected_chunk_id(),
            "block_id": self.selected_block_id(),
            "source_scroll": self.source_scroll_position(),
            "chunk_list_scroll": int(self._chunk_list.verticalScrollBar().value()),
            "block_list_scroll": int(self._speech_block_list.verticalScrollBar().value()),
        }

    def replacement_block_id_after_delete(self, speech_block_id: str) -> str | None:
        """
        @brief      Return the block that should be selected after deleting one visible Speech Block.
        @param[in]  speech_block_id Speech Block identifier being deleted.
        @return     Next visible Speech Block id, previous id when deleting the last row, or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-08
        @version    0.1.0
        """
        normalized_id = str(speech_block_id).strip()
        blocks_for_chunk = self._blocks_for_current_chunk()
        for index, block in enumerate(blocks_for_chunk):
            if str(block.get("speech_block_id", "")).strip() != normalized_id:
                continue
            if len(blocks_for_chunk) <= 1:
                return None
            replacement_index = min(index + 1, len(blocks_for_chunk) - 1)
            if replacement_index == index:
                replacement_index = index - 1
            return str(blocks_for_chunk[replacement_index].get("speech_block_id", "")).strip() or None
        return None

    def restore_source_scroll_position(self, scroll_position: int) -> None:
        """
        @brief      Restore the selected-chunk text vertical scroll position.
        @param[in]  scroll_position Vertical scrollbar value to restore.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.3.0
        """
        self._restore_source_scroll_position(scroll_position)
        QTimer.singleShot(0, lambda: self._restore_source_scroll_position(scroll_position))

    def restore_review_position(self, review_position: dict[str, object]) -> None:
        """
        @brief      Restore the Speech Blocks review selection and scroll positions.
        @param[in]  review_position Payload returned by `review_position`.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-16
        @version    0.1.0
        """
        block_id = str(review_position.get("block_id", "") or "").strip()
        chunk_id = str(review_position.get("chunk_id", "") or "").strip()
        if block_id:
            self.select_speech_block(block_id)
        elif chunk_id:
            self._select_chunk_by_id(chunk_id)
        source_scroll_position = int(review_position.get("source_scroll", 0) or 0)
        chunk_list_scroll_position = int(review_position.get("chunk_list_scroll", 0) or 0)
        block_list_scroll_position = int(review_position.get("block_list_scroll", 0) or 0)
        self._restore_review_scroll_positions(
            source_scroll_position,
            chunk_list_scroll_position,
            block_list_scroll_position,
        )
        QTimer.singleShot(
            0,
            lambda: self._restore_review_scroll_positions(
                source_scroll_position,
                chunk_list_scroll_position,
                block_list_scroll_position,
            ),
        )

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
        @version    0.4.3
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
        self._ambient_prompt_label.setText(ui_state_service.translate("speech_blocks.ambient_prompt", language))
        self._ambient_negative_prompt_label.setText(
            ui_state_service.translate("speech_blocks.ambient_negative_prompt", language)
        )
        self._ambient_duration_label.setText(ui_state_service.translate("speech_blocks.ambient_duration", language))
        self._resplit_button.setText(ui_state_service.translate("speech_blocks.resplit_selected", language))
        self._edit_button.setText(ui_state_service.translate("speech_blocks.edit_block", language))
        self._save_button.setText(ui_state_service.translate("speech_blocks.save_block", language))
        self._approve_block_button.setText(ui_state_service.translate(self._approval_button_label_key(), language))
        self._generate_audio_button.setText(
            ui_state_service.translate("speech_blocks.generate_audio_selected", language)
        )
        self._selected_audio_playback_button.setText(
            ui_state_service.translate(self._selected_audio_playback_label_key(), language)
        )
        self._status_group.setTitle(ui_state_service.translate("speech_blocks.status_group", language))
        if self._profile_combo.count() > 0 and self._profile_combo.itemData(0) in (None, ""):
            self._profile_combo.setItemText(0, ui_state_service.translate("ai_settings.none", language))
        self._apply_chunk_action_top_margin()
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
        @version    0.2.0
        """
        self._speaker_combo.blockSignals(True)
        self._speaker_combo.clear()
        speaker_entries = self._speaker_catalog
        if self._voice_assignment_mode == "same_narrator":
            speaker_entries = [
                speaker_entry
                for speaker_entry in self._speaker_catalog
                if str(speaker_entry.get("speaker_id", "")).strip() == speech_blocks_service.SPEAKER_KIND_NARRATOR
            ]
        for speaker_entry in speaker_entries:
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
        @version    0.6.2
        """
        selected_block = self._current_display_block()
        generated_all_chunks = (
            bool(self._speech_blocks)
            and self._total_chunk_count > 0
            and (self._processed_chunk_count >= self._total_chunk_count)
        )
        can_generate = (
            self._project_active
            and not self._busy
            and bool(self._source_chunks)
            and self.current_profile_id() is not None
            and not generated_all_chunks
        )
        can_edit_selected = self._project_active and not self._busy and selected_block is not None
        can_toggle_approval_selected = can_edit_selected
        can_generate_audio_selected = (
            can_edit_selected
            and not self._editing
            and bool(selected_block.get("approved", False))
            and not bool(selected_block.get("audio_metadata_only", False))
        )
        can_stop_selected_audio = self._project_active and self._selected_audio_playback_active
        can_play_selected_audio = (
            self._project_active
            and not self._busy
            and selected_block is not None
            and bool(selected_block.get("audio_can_play", False))
            and not self._editing
        )
        can_insert_block = self._project_active and not self._busy and self._current_chunk_id is not None
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
        self._speaker_combo.setEnabled(
            can_edit_selected and self._editing and self._voice_assignment_mode != "same_narrator"
        )
        self._content_kind_combo.setEnabled(can_edit_selected and self._editing)
        self._speech_block_text_edit.setReadOnly(not (can_edit_selected and self._editing))
        ambience_editor_enabled = (
            can_edit_selected
            and self._editing
            and str(self._content_kind_combo.currentData() or "") == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
        )
        self._ambient_prompt_edit.setReadOnly(not ambience_editor_enabled)
        self._ambient_negative_prompt_edit.setReadOnly(not ambience_editor_enabled)
        self._ambient_duration_spin.setEnabled(ambience_editor_enabled)
        self._edit_button.setEnabled(can_edit_selected and not self._editing)
        self._generate_audio_button.setEnabled(can_generate_audio_selected)
        self._save_button.setEnabled(can_edit_selected and self._editing)
        self._approve_block_button.setText(
            ui_state_service.translate(self._approval_button_label_key(), self._current_language)
        )
        self._approve_block_button.setEnabled(can_toggle_approval_selected and not self._editing)
        self._selected_audio_playback_button.setText(
            ui_state_service.translate(self._selected_audio_playback_label_key(), self._current_language)
        )
        self._selected_audio_playback_button.setEnabled(can_stop_selected_audio or can_play_selected_audio)

    def _apply_lower_splitter_minimums(self) -> None:
        """
        @brief      Set each Speech Blocks lower pane minimum width to one third of the lower splitter width.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-01
        @version    0.1.1
        """
        required_attributes = ("_lower_splitter", "_source_group", "_blocks_group")
        if not all(hasattr(self, attribute_name) for attribute_name in required_attributes):
            return
        self._source_group.setMinimumWidth(0)
        self._blocks_group.setMinimumWidth(0)

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

    def _emit_generate_audio_selected(self) -> None:
        """
        @brief      Emit selected Speech Block audio generation request.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-04
        @version    0.1.0
        """
        block_id = self.selected_block_id()
        if block_id is not None:
            self.generate_audio_selected_requested.emit(block_id)

    def _emit_selected_audio_playback_toggle(self) -> None:
        """
        @brief      Emit selected Speech Block audio playback toggle request.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-04
        @version    0.1.0
        """
        block_id = self.selected_block_id()
        if block_id is not None:
            self.selected_audio_playback_toggle_requested.emit(block_id)

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

    def _refresh_block_detail_editor(self) -> None:
        """
        @brief      Show the editor matching the selected content kind.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-21
        @version    0.1.0
        """
        is_scene_ambience = (
            str(self._content_kind_combo.currentData() or "") == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
        )
        self._speech_block_text_edit.setVisible(not is_scene_ambience)
        self._ambience_detail_widget.setVisible(is_scene_ambience)
        self._update_selected_text_character_count()
        self._apply_control_state()

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
        self._ambient_prompt_edit.setPlainText(str(selected_block.get("sound_prompt", selected_block.get("text", ""))))
        self._ambient_negative_prompt_edit.setPlainText(str(selected_block.get("negative_prompt", "")))
        self._ambient_duration_spin.setValue(float(selected_block.get("duration_seconds", 1.0) or 1.0))
        self._refresh_block_detail_editor()
        self._update_selected_text_character_count()
        self._warning_label.setText(_format_warning_label(selected_block, self._current_language))
        self._apply_control_state()

    def _clear_block_details(self) -> None:
        """
        @brief      Clear the selected Speech Block detail controls.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.2.0
        """
        self._current_block_id = None
        self._speech_block_text_edit.clear()
        self._ambient_prompt_edit.clear()
        self._ambient_negative_prompt_edit.clear()
        self._ambient_duration_spin.setValue(1.0)
        self._refresh_block_detail_editor()
        self._update_selected_text_character_count()
        self._warning_label.clear()

    def _begin_editing(self) -> None:
        """
        @brief      Request selected-block editing through the controller.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.1
        """
        block_id = self.selected_block_id()
        if block_id is None:
            return
        self.edit_started.emit(block_id)

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
        edit_payload: object
        selected_content_kind = str(self._content_kind_combo.currentData() or "")
        if selected_content_kind == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE:
            edit_payload = {
                "sound_prompt": self._ambient_prompt_edit.toPlainText(),
                "negative_prompt": self._ambient_negative_prompt_edit.toPlainText(),
                "duration_seconds": self._ambient_duration_spin.value(),
            }
        else:
            edit_payload = self._speech_block_text_edit.toPlainText()
        self.save_block_requested.emit(
            block_id,
            selected_content_kind
            if selected_content_kind
            in {
                speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
                speech_blocks_service.CONTENT_KIND_PAUSE,
                speech_blocks_service.CONTENT_KIND_INDICATION,
            }
            else str(self._speaker_combo.currentData() or ""),
            selected_content_kind,
            edit_payload,
        )
        self._apply_control_state()

    def _emit_approve_block(self) -> None:
        """
        @brief      Emit the selected-block approval toggle request.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.2.0
        """
        block_id = self.selected_block_id()
        if block_id is not None:
            self.approve_block_requested.emit(block_id)

    def _update_selected_text_character_count(self) -> None:
        """
        @brief      Refresh the selected Speech Block text character counter.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-05
        @version    0.1.0
        """
        if str(self._content_kind_combo.currentData() or "") == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE:
            selected_length = len(self._ambient_prompt_edit.toPlainText())
        else:
            selected_length = len(self._speech_block_text_edit.toPlainText())
        if self._selected_text_character_limit <= 0:
            self._character_count_edit.setText(f"{selected_length} / -")
            return
        self._character_count_edit.setText(f"{selected_length} / {self._selected_text_character_limit}")

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

    def _approval_button_label_key(self) -> str:
        """
        @brief      Return the selected-block approval toggle label key.
        @return     Translation key for the approval toggle button.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-05
        @version    0.1.0
        """
        selected_block = self._current_display_block()
        if selected_block is not None and bool(selected_block.get("approved", False)):
            return "speech_blocks.unapprove_block"
        return "speech_blocks.approve_block"

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

    def _select_chunk_by_id(self, chunk_id: str) -> None:
        """
        @brief      Restore one source-chunk selection in the chunk list.
        @param[in]  chunk_id Source chunk identifier to restore.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-16
        @version    0.1.0
        """
        normalized_id = str(chunk_id).strip()
        for index, chunk in enumerate(self._source_chunks):
            if str(chunk.get("chunk_id", "")).strip() == normalized_id:
                self._chunk_list.setCurrentRow(index)
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

    def _restore_review_scroll_positions(
        self,
        source_scroll_position: int,
        chunk_list_scroll_position: int,
        block_list_scroll_position: int,
    ) -> None:
        """
        @brief      Restore all Speech Blocks review scroll positions after a refresh.
        @param[in]  source_scroll_position Selected-chunk text scroll value.
        @param[in]  chunk_list_scroll_position Chunk-list scroll value.
        @param[in]  block_list_scroll_position Speech-block-list scroll value.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-16
        @version    0.1.0
        """
        self._restore_source_scroll_position(source_scroll_position)
        self._restore_scroll_bar_position(self._chunk_list.verticalScrollBar(), chunk_list_scroll_position)
        self._restore_scroll_bar_position(self._speech_block_list.verticalScrollBar(), block_list_scroll_position)

    @staticmethod
    def _restore_scroll_bar_position(scroll_bar, scroll_position: int) -> None:
        """
        @brief      Restore one scrollbar within its current bounds.
        @param[in]  scroll_bar Scrollbar to update.
        @param[in]  scroll_position Requested scroll position.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-16
        @version    0.1.0
        """
        bounded_position = max(scroll_bar.minimum(), min(int(scroll_position), scroll_bar.maximum()))
        scroll_bar.setValue(bounded_position)

    def _selected_audio_playback_label_key(self) -> str:
        """
        @brief      Return the selected audio playback button label key.
        @return     Runtime UI translation key.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-04
        @version    0.1.0
        """
        return "audio_blocks.stop_playback" if self._selected_audio_playback_active else "audio_blocks.play_selected"


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
    @version    0.2.1
    """
    warning_marker = "!" if speech_block.get("warning_flags", []) else " "
    approval_marker = "ok" if bool(speech_block.get("approved", False)) else "--"
    if str(speech_block.get("content_kind", "")).strip() == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE:
        duration = float(speech_block.get("duration_seconds", 0.0) or 0.0)
        sound_prompt = speech_block.get("sound_prompt", speech_block.get("text", ""))
        preview = f"Scene Ambience | {sound_prompt}"
        if duration > 0.0:
            preview = f"{preview} | {duration:.1f}s"
        if len(preview) > 70:
            preview = preview[:67] + "..."
        return f"[{approval_marker}] [{warning_marker}] {speech_block.get('speech_block_id', '')} | {preview}"
    else:
        preview = str(speech_block.get("text", ""))
    if len(preview) > 52:
        preview = preview[:49] + "..."
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
