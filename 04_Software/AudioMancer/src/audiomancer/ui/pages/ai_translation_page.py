#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_translation_page.py
@brief AI Translation workflow page for AudioMancer.
@details Provides locked-language indicators, translation profile selection,
         chunk review, manual edits, approval controls, and progress display.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.6.4
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
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import ai_translation_service, ui_state_service


class AiTranslationPage(QWidget):
    """
    @brief      Display the functional AI Translation workflow surface.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.3.0
    """

    start_translation_requested = Signal(str)
    reset_translation_requested = Signal()
    approve_all_requested = Signal()
    approve_selected_requested = Signal(str)
    retranslate_selected_requested = Signal(str, str)
    translated_text_changed = Signal(str, str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the functional AI Translation workflow page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.4.3
        """
        super().__init__(parent)
        self._project_active = False
        self._busy = False
        self._stage_status = ai_translation_service.TRANSLATION_STAGE_NOT_STARTED
        self._source_chunks: list[dict[str, object]] = []
        self._display_chunks: list[dict[str, object]] = []
        self._current_chunk_id: str | None = None
        self._loading_translation_text = False
        self._target_language = config.DEFAULT_TRANSLATION_TARGET_LANGUAGE
        self._original_language = "Unknown"

        layout = QVBoxLayout(self)
        header_row = QHBoxLayout()
        self._title_label = QLabel("<h2>AI Translation</h2>")
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)
        self._original_language_label = QLabel("Original Language")
        header_row.addWidget(self._original_language_label)
        self._original_language_value_label = QLabel("Unknown")
        header_row.addWidget(self._original_language_value_label)
        self._target_language_label = QLabel("Target Language")
        header_row.addWidget(self._target_language_label)
        self._target_language_value_label = QLabel("English")
        header_row.addWidget(self._target_language_value_label)
        self._profile_label = QLabel("AI Profile")
        header_row.addWidget(self._profile_label)
        self._profile_combo = QComboBox(self)
        self._profile_combo.addItem("(none)", None)
        header_row.addWidget(self._profile_combo)
        layout.addLayout(header_row)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        self._chunk_list_group = QGroupBox("Chunk List", self)
        chunk_list_layout = QHBoxLayout(self._chunk_list_group)
        chunk_list_layout.setContentsMargins(6, 12, 6, 6)
        self._chunk_list = QListWidget(self)
        self._chunk_list.currentRowChanged.connect(self._show_selected_chunk)
        chunk_list_layout.addWidget(self._chunk_list, 1)
        self._chunk_list_group.setMinimumHeight(150)
        self._chunk_list_group.setMaximumHeight(176)

        self._translation_actions_widget = QWidget(self._chunk_list_group)
        actions_layout = QVBoxLayout(self._translation_actions_widget)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        self._start_button = QPushButton("Start Translation")
        self._start_button.clicked.connect(self._emit_start_translation)
        actions_layout.addWidget(self._start_button)
        self._reset_button = QPushButton("Reset Translation")
        self._reset_button.clicked.connect(self.reset_translation_requested.emit)
        actions_layout.addWidget(self._reset_button)
        self._approve_all_button = QPushButton("Approve All")
        self._approve_all_button.clicked.connect(self.approve_all_requested.emit)
        actions_layout.addWidget(self._approve_all_button)
        chunk_list_layout.addWidget(self._translation_actions_widget, 0)
        top_row.addWidget(self._chunk_list_group, 1)
        layout.addLayout(top_row, 1)

        self._chunk_text_splitter = QSplitter(self)
        self._chunk_text_splitter.setChildrenCollapsible(False)
        self._source_group = QGroupBox("Original Chunk", self)
        source_layout = QVBoxLayout(self._source_group)
        self._source_text_edit = QPlainTextEdit(self)
        self._source_text_edit.setReadOnly(True)
        source_layout.addWidget(self._source_text_edit)
        self._approved_progress_label = QLabel("Approved chunks: 0/0")
        source_layout.addWidget(self._approved_progress_label)
        self._approved_progress_bar = QProgressBar(self)
        self._approved_progress_bar.setTextVisible(True)
        self._approved_progress_bar.setFormat("%p%")
        source_layout.addWidget(self._approved_progress_bar)
        self._chunk_text_splitter.addWidget(self._source_group)

        self._translated_group = QGroupBox("Translated Chunk", self)
        translated_layout = QVBoxLayout(self._translated_group)
        self._translated_text_edit = QPlainTextEdit(self)
        self._translated_text_edit.textChanged.connect(self._handle_translated_text_changed)
        translated_layout.addWidget(self._translated_text_edit)
        action_row = QHBoxLayout()
        self._retranslate_button = QPushButton("Re-Translate Selected")
        self._retranslate_button.clicked.connect(self._emit_retranslate_selected)
        action_row.addWidget(self._retranslate_button)
        self._approve_selected_button = QPushButton("Approve Selected")
        self._approve_selected_button.clicked.connect(self._emit_approve_selected)
        action_row.addWidget(self._approve_selected_button)
        translated_layout.addLayout(action_row)
        self._chunk_text_splitter.addWidget(self._translated_group)
        self._chunk_text_splitter.setStretchFactor(0, 1)
        self._chunk_text_splitter.setStretchFactor(1, 1)
        self._chunk_text_splitter.setSizes([600, 600])
        layout.addWidget(self._chunk_text_splitter, 7)
        self._apply_chunk_text_splitter_minimums()

        self._status_group = QGroupBox("Translation Status", self)
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
        layout.addWidget(self._status_group, 0)
        self.set_project_active(False)
        self.set_translation_state(
            [],
            [],
            ["Run text chunking before AI Translation."],
            "Unknown",
            config.DEFAULT_TRANSLATION_TARGET_LANGUAGE,
            None,
            ai_translation_service.TRANSLATION_STAGE_NOT_STARTED,
            0,
            0,
            0,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        """
        @brief      Keep original and translated chunk panes from shrinking below thirty percent of splitter width.
        @param[in]  event Qt resize event.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-06
        @version    0.1.0
        """
        super().resizeEvent(event)
        self._apply_chunk_text_splitter_minimums()

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Enable or disable translation interactions for project state.
        @param[in]  is_active True when a project is currently open.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        self._project_active = is_active
        self._apply_control_state()

    def set_ai_profiles(self, entries: list[tuple[str, str | None]], selected_profile_id: str | None) -> None:
        """
        @brief      Populate the translation AI-profile selector.
        @param[in]  entries Ordered label/id pairs for enabled profiles.
        @param[in]  selected_profile_id Preferred selected profile id.
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
                (index for index, _entry in enumerate(entries) if entries[index][1] == selected_profile_id), 0
            )
            self._profile_combo.setCurrentIndex(selected_index)
        else:
            self._profile_combo.addItem("(none)", None)
            self._profile_combo.setCurrentIndex(0)
        self._profile_combo.blockSignals(False)
        self._apply_control_state()

    def set_translation_state(
        self,
        source_chunks: list[dict[str, object]],
        translated_chunks: list[dict[str, object]],
        notes: list[str],
        original_language: str,
        target_language: str,
        selected_profile_id: str | None,
        stage_status: str,
        translated_count: int,
        approved_count: int,
        total_count: int,
    ) -> None:
        """
        @brief      Refresh the translation page from controller-provided state.
        @param[in]  source_chunks Source chunk payloads from chunking.
        @param[in]  translated_chunks Persisted translated chunk payloads.
        @param[in]  notes Operator-facing translation notes.
        @param[in]  original_language Source language label.
        @param[in]  target_language Active target language code.
        @param[in]  selected_profile_id Active profile identifier or `None`.
        @param[in]  stage_status Effective translation stage token.
        @param[in]  translated_count Number of translated chunks.
        @param[in]  approved_count Number of approved chunks.
        @param[in]  total_count Total number of chunks.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.2.1
        """
        self._source_chunks = sorted(source_chunks, key=lambda item: int(item.get("sequence_index", 0)))
        self._display_chunks = _build_display_chunks(self._source_chunks, translated_chunks)
        self._stage_status = stage_status
        self._original_language = str(original_language)
        self._target_language = str(target_language or config.DEFAULT_TRANSLATION_TARGET_LANGUAGE)
        self._original_language_value_label.setText(self._original_language)
        self._target_language_value_label.setText(_language_label(self._target_language))
        if selected_profile_id is not None:
            profile_index = self._profile_combo.findData(selected_profile_id)
            if profile_index >= 0:
                self._profile_combo.setCurrentIndex(profile_index)
        current_chunk_id = self.selected_chunk_id()
        self._chunk_list.clear()
        for translated_chunk in self._display_chunks:
            self._chunk_list.addItem(_format_chunk_list_item(translated_chunk))
        self._approved_progress_bar.setRange(0, max(total_count, 1))
        self._approved_progress_bar.setValue(min(approved_count, max(total_count, 1)))
        self._approved_progress_label.setText(f"Approved chunks: {approved_count}/{total_count}")
        self._status_edit.setPlainText("\n".join(notes))
        row_to_select = 0
        if current_chunk_id is not None:
            for index, chunk in enumerate(self._display_chunks):
                if str(chunk.get("chunk_id", "")) == current_chunk_id:
                    row_to_select = index
                    break
        if self._display_chunks:
            self._chunk_list.setCurrentRow(row_to_select)
        else:
            self._show_selected_chunk(-1)
        self._apply_control_state()

    def set_busy(self, is_busy: bool) -> None:
        """
        @brief      Disable page actions while a blocking translation task runs.
        @param[in]  is_busy True while the page is busy.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        self._busy = is_busy
        self._apply_control_state()

    def current_profile_id(self) -> str | None:
        """
        @brief      Return the currently selected AI translation profile id.
        @return     Selected profile identifier or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        value = self._profile_combo.currentData()
        return None if value in (None, "") else str(value)

    def current_target_language(self) -> str:
        """
        @brief      Return the currently selected target language code.
        @return     Selected target language code.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        return self._target_language

    def selected_chunk_id(self) -> str | None:
        """
        @brief      Return the identifier of the currently selected chunk.
        @return     Selected chunk id or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        return self._current_chunk_id

    def advance_to_next_chunk(self) -> None:
        """
        @brief      Move the chunk selection one row forward when a next row exists.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        current_row = self._chunk_list.currentRow()
        if current_row < 0:
            return
        next_row = current_row + 1
        if next_row < self._chunk_list.count():
            self._chunk_list.setCurrentRow(next_row)

    def _apply_control_state(self) -> None:
        """
        @brief      Apply the current translation-page button and editor states.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.2.1
        """
        has_source_chunks = bool(self._source_chunks)
        has_started_translation = self._stage_status in {
            "running",
            "failed",
            ai_translation_service.TRANSLATION_STAGE_IN_PROGRESS,
            ai_translation_service.TRANSLATION_STAGE_TRANSLATED,
            ai_translation_service.TRANSLATION_STAGE_APPROVED,
        }
        has_translated_chunks = any(str(chunk.get("translated_text", "")).strip() for chunk in self._display_chunks)
        has_untranslated_chunks = any(
            not str(chunk.get("translated_text", "")).strip() for chunk in self._display_chunks
        )
        selected_chunk = self._current_display_chunk()
        has_selected_translation = selected_chunk is not None and bool(
            str(selected_chunk.get("translated_text", "")).strip()
        )
        selected_profile_id = self.current_profile_id()
        _ = has_started_translation
        _ = has_translated_chunks
        self._profile_combo.setEnabled(self._project_active and not self._busy)
        self._start_button.setEnabled(
            self._project_active
            and has_source_chunks
            and not self._busy
            and has_untranslated_chunks
            and self._stage_status != ai_translation_service.TRANSLATION_STAGE_APPROVED
            and selected_profile_id is not None
        )
        self._reset_button.setEnabled(
            self._project_active and not self._busy and (has_started_translation or has_translated_chunks)
        )
        self._approve_all_button.setEnabled(
            self._project_active
            and not self._busy
            and any(
                str(chunk.get("translated_text", "")).strip() and not bool(chunk.get("approved", False))
                for chunk in self._display_chunks
            )
        )
        self._retranslate_button.setEnabled(
            self._project_active and not self._busy and selected_chunk is not None and selected_profile_id is not None
        )
        self._approve_selected_button.setEnabled(
            self._project_active
            and not self._busy
            and has_selected_translation
            and not bool(selected_chunk.get("approved", False))
        )
        self._translated_text_edit.setReadOnly(not self._project_active or self._busy or selected_chunk is None)
        self._chunk_list.setEnabled(self._project_active)

    def _apply_chunk_text_splitter_minimums(self) -> None:
        """
        @brief      Set original and translated chunk pane minimum widths to thirty percent of splitter width.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-06
        @version    0.1.0
        """
        required_attributes = ("_chunk_text_splitter", "_source_group", "_translated_group")
        if not all(hasattr(self, attribute_name) for attribute_name in required_attributes):
            return
        splitter_width = self._chunk_text_splitter.width()
        if splitter_width <= 0:
            return
        minimum_pane_width = int(splitter_width * 0.3)
        self._source_group.setMinimumWidth(minimum_pane_width)
        self._translated_group.setMinimumWidth(minimum_pane_width)

    def _show_selected_chunk(self, row: int) -> None:
        """
        @brief      Display the currently selected source and translated chunk texts.
        @param[in]  row Currently selected list row.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        if row < 0 or row >= len(self._display_chunks):
            self._current_chunk_id = None
            self._source_text_edit.clear()
            self._loading_translation_text = True
            self._translated_text_edit.clear()
            self._loading_translation_text = False
            self._apply_control_state()
            return
        selected_chunk = self._display_chunks[row]
        self._current_chunk_id = str(selected_chunk.get("chunk_id", ""))
        self._source_text_edit.setPlainText(str(selected_chunk.get("source_text", "")))
        self._loading_translation_text = True
        self._translated_text_edit.setPlainText(str(selected_chunk.get("translated_text", "")))
        self._loading_translation_text = False
        self._apply_control_state()

    def _emit_start_translation(self) -> None:
        """
        @brief      Emit the start-or-continue translation request signal.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        profile_id = self.current_profile_id()
        if profile_id is not None:
            self.start_translation_requested.emit(profile_id)

    def _emit_retranslate_selected(self) -> None:
        """
        @brief      Emit the retranslation request for the currently selected chunk.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        profile_id = self.current_profile_id()
        chunk_id = self.selected_chunk_id()
        if profile_id is not None and chunk_id is not None:
            self.retranslate_selected_requested.emit(profile_id, chunk_id)

    def _emit_approve_selected(self) -> None:
        """
        @brief      Emit the approve-selected signal for the active chunk.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        chunk_id = self.selected_chunk_id()
        if chunk_id is not None:
            self.approve_selected_requested.emit(chunk_id)

    def _handle_translated_text_changed(self) -> None:
        """
        @brief      Persist and locally reflect edits to the translated text editor.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        if self._loading_translation_text:
            return
        chunk_id = self.selected_chunk_id()
        if chunk_id is None:
            return
        translated_text = self._translated_text_edit.toPlainText()
        self.translated_text_changed.emit(chunk_id, translated_text)
        selected_chunk = self._current_display_chunk()
        if selected_chunk is not None:
            previous_text = str(selected_chunk.get("translated_text", ""))
            selected_chunk["translated_text"] = translated_text
            if translated_text.strip():
                if translated_text != previous_text:
                    selected_chunk["approved"] = False
                    selected_chunk["approved_at"] = None
                selected_chunk["status"] = (
                    ai_translation_service.TRANSLATED_CHUNK_STATUS_APPROVED
                    if bool(selected_chunk.get("approved", False))
                    else ai_translation_service.TRANSLATED_CHUNK_STATUS_TRANSLATED
                )
            else:
                selected_chunk["approved"] = False
                selected_chunk["approved_at"] = None
                selected_chunk["status"] = ai_translation_service.TRANSLATED_CHUNK_STATUS_NOT_STARTED
            current_item = self._chunk_list.currentItem()
            if current_item is not None:
                current_item.setText(_format_chunk_list_item(selected_chunk))
        self._apply_control_state()

    def _current_display_chunk(self) -> dict[str, object] | None:
        """
        @brief      Return the display-model payload for the selected chunk.
        @return     Selected display-chunk payload or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.0
        """
        if self._current_chunk_id is None:
            return None
        return next(
            (chunk for chunk in self._display_chunks if str(chunk.get("chunk_id", "")) == self._current_chunk_id), None
        )

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one translated UI language to the page widgets.
        @param[in]  language Runtime UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.1
        """
        self._title_label.setText(f"<h2>{ui_state_service.translate('ai_translation.title', language)}</h2>")
        self._original_language_label.setText(ui_state_service.translate("ai_translation.original_language", language))
        self._target_language_label.setText(ui_state_service.translate("ai_translation.target_language", language))
        self._profile_label.setText(ui_state_service.translate("ai_translation.ai_profile", language))
        self._chunk_list_group.setTitle(ui_state_service.translate("ai_translation.chunk_list_group", language))
        self._start_button.setText(ui_state_service.translate("ai_translation.start", language))
        self._reset_button.setText(ui_state_service.translate("ai_translation.reset", language))
        self._approve_all_button.setText(ui_state_service.translate("ai_translation.approve_all", language))
        self._source_group.setTitle(ui_state_service.translate("ai_translation.original_group", language))
        self._translated_group.setTitle(ui_state_service.translate("ai_translation.translated_group", language))
        self._status_group.setTitle(ui_state_service.translate("ai_translation.status_group", language))
        self._retranslate_button.setText(ui_state_service.translate("ai_translation.retranslate", language))
        self._approve_selected_button.setText(ui_state_service.translate("ai_translation.approve_selected", language))


# HELPER FUNCTIONS


def _build_display_chunks(
    source_chunks: list[dict[str, object]], translated_chunks: list[dict[str, object]]
) -> list[dict[str, object]]:
    """
    @brief      Merge source chunks with persisted translated records for display.
    @param[in]  source_chunks Source chunk payloads from chunking.
    @param[in]  translated_chunks Persisted translated chunk payloads.
    @return     Display-model chunk payloads ordered by source chunk sequence.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    translated_by_id = {str(chunk.get("chunk_id", "")): dict(chunk) for chunk in translated_chunks}
    display_chunks: list[dict[str, object]] = []
    for source_chunk in source_chunks:
        chunk_id = str(source_chunk.get("chunk_id", ""))
        translated_chunk = translated_by_id.get(chunk_id)
        if translated_chunk is None:
            display_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "sequence_index": int(source_chunk.get("sequence_index", 0)),
                    "source_text": str(source_chunk.get("text", "")),
                    "translated_text": "",
                    "approved": False,
                    "approved_at": None,
                    "translated_at": None,
                    "translation_profile_id": None,
                    "target_language": config.DEFAULT_TRANSLATION_TARGET_LANGUAGE,
                    "status": ai_translation_service.TRANSLATED_CHUNK_STATUS_NOT_STARTED,
                }
            )
            continue
        translated_chunk["sequence_index"] = int(source_chunk.get("sequence_index", 0))
        translated_chunk["source_text"] = str(source_chunk.get("text", ""))
        display_chunks.append(translated_chunk)
    return display_chunks


def _language_label(language_code: object) -> str:
    """
    @brief      Resolve one translation-language label.
    @param[in]  language_code Candidate language code.
    @return     Operator-facing language label.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    normalized_code = str(language_code or "").strip()
    return str(dict(config.TRANSLATION_LANGUAGE_OPTIONS).get(normalized_code, normalized_code or "-"))


def _format_chunk_list_item(chunk: dict[str, object]) -> str:
    """
    @brief      Format one translated-chunk row label for the chunk list.
    @param[in]  chunk Display-model chunk payload.
    @return     Human-readable list item label.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if bool(chunk.get("approved", False)):
        status_label = "Approved"
    elif str(chunk.get("translated_text", "")).strip():
        status_label = "Translated"
    else:
        status_label = "Pending"
    source_text = str(chunk.get("source_text", ""))
    preview = source_text if len(source_text) <= 60 else source_text[:57] + "..."
    return f"[{status_label}] {chunk.get('chunk_id', '')} | {preview}"


# END OF FILE
