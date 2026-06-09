#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
         current cleaned-text reference plus editable persisted chunk previews
         with local text search.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.5.5
"""

# IMPORTS

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
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
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.4.1
    """

    chunk_requested = Signal()
    ai_chunk_requested = Signal(str, str)
    save_chunk_requested = Signal(str, str)
    insert_chunk_requested = Signal(str)
    delete_chunk_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the chunking-aware text chunking page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-09
        @version    0.5.4
        """
        super().__init__(parent)
        self._chunks: list[dict[str, object]] = []
        self._project_active = False
        self._busy = False
        self._can_chunk = False
        self._can_ai_chunk = False
        self._editing_chunk = False
        self._has_ai_profiles = False
        self._language = config.DEFAULT_LANGUAGE
        self._preview_find_text_by_editor_id: dict[int, str] = {}

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

        self._preview_splitter = QSplitter(self)
        self._preview_splitter.setChildrenCollapsible(False)

        left_container = QWidget(self)
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        cleaned_group = QGroupBox("Cleaned Text Reference", self)
        cleaned_layout = QVBoxLayout(cleaned_group)
        self._cleaned_text_edit = QPlainTextEdit(self)
        self._cleaned_text_edit.setReadOnly(True)
        self._install_preview_find_context_menu(self._cleaned_text_edit)
        self._cleaned_text_edit.setPlainText("Cleaned text will appear here and serve as the chunking reference.")
        cleaned_layout.addWidget(self._cleaned_text_edit)
        left_layout.addWidget(cleaned_group, 5)

        chunk_list_group = QGroupBox("Chunk List", self)
        chunk_list_layout = QVBoxLayout(chunk_list_group)
        self._chunk_list = QListWidget(self)
        self._chunk_list.setMinimumHeight(132)
        self._chunk_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._chunk_list.currentRowChanged.connect(self._show_selected_chunk)
        chunk_list_layout.addWidget(self._chunk_list)
        left_layout.addWidget(chunk_list_group, 3)
        self._preview_splitter.addWidget(left_container)

        chunk_preview_group = QGroupBox("Selected Chunk", self)
        chunk_preview_layout = QVBoxLayout(chunk_preview_group)
        self._chunk_text_edit = QPlainTextEdit(self)
        self._chunk_text_edit.setReadOnly(True)
        self._install_preview_find_context_menu(self._chunk_text_edit)
        self._chunk_text_edit.setPlainText("The full text of the selected chunk will appear here.")
        chunk_preview_layout.addWidget(self._chunk_text_edit)
        chunk_action_row = QHBoxLayout()
        chunk_action_row.addStretch(1)
        self._insert_chunk_button = QPushButton("Insert")
        self._insert_chunk_button.clicked.connect(self._emit_insert_chunk_requested)
        chunk_action_row.addWidget(self._insert_chunk_button)
        self._delete_chunk_button = QPushButton("Delete")
        self._delete_chunk_button.clicked.connect(self._emit_delete_chunk_requested)
        chunk_action_row.addWidget(self._delete_chunk_button)
        self._edit_chunk_button = QPushButton("Edit")
        self._edit_chunk_button.clicked.connect(self._begin_chunk_edit)
        chunk_action_row.addWidget(self._edit_chunk_button)
        self._save_chunk_button = QPushButton("Save")
        self._save_chunk_button.clicked.connect(self._emit_save_chunk_requested)
        chunk_action_row.addWidget(self._save_chunk_button)
        chunk_preview_layout.addLayout(chunk_action_row)
        self._preview_splitter.addWidget(chunk_preview_group)

        self._preview_splitter.setStretchFactor(0, 3)
        self._preview_splitter.setStretchFactor(1, 2)
        layout.addWidget(self._preview_splitter, 7)

        status_group = QWidget(self)
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(0, 0, 0, 0)
        self._status_edit = QPlainTextEdit(self)
        self._status_edit.setReadOnly(True)
        self._status_edit.setProperty(
            ui_state_service.CONTROL_TEXT_FONT_ROLE_PROPERTY,
            ui_state_service.CONTROL_TEXT_FONT_ROLE_VALUE,
        )
        self._status_edit.setPlainText(
            "Run cleanup before chunking.\n"
            "Deterministic and AI-assisted chunk generation will populate the chunk list and selected preview."
        )
        status_layout.addWidget(self._status_edit)
        status_group.setFixedHeight(ui_state_service.operator_status_pane_height(self._status_edit))
        layout.addWidget(status_group, 0)
        self._cleaned_group = cleaned_group
        self._chunk_list_group = chunk_list_group
        self._left_preview_container = left_container
        self._chunk_preview_group = chunk_preview_group
        self._status_group = status_group
        self._apply_preview_splitter_minimums()
        self.set_project_active(False)
        self.set_processing_state(
            cleaned_text=None,
            chunks=[],
            notes=["Run cleanup before chunking."],
            can_chunk=False,
            can_ai_chunk=False,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        """
        @brief      Keep chunking preview splitter panes from shrinking below one third of the preview width.
        @param[in]  event Qt resize event.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-01
        @version    0.1.0
        """
        super().resizeEvent(event)
        self._apply_preview_splitter_minimums()

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Enable or disable the page based on project availability.
        @param[in]  is_active True when a project is open.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-07
        @version    0.1.2
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
        @version    0.1.1
        """
        self._chunks = list(chunks)
        self._editing_chunk = False
        self._chunk_text_edit.setReadOnly(True)
        self._cleaned_text_edit.setPlainText(cleaned_text or "")
        self._can_chunk = can_chunk
        self._can_ai_chunk = can_chunk if can_ai_chunk is None else can_ai_chunk
        if selected_strategy is not None:
            self.set_default_ai_strategy(selected_strategy)
        self._chunk_list.clear()
        for chunk in self._chunks:
            self._chunk_list.addItem(_format_chunk_list_item(chunk))
        self._status_edit.setPlainText("\n".join(notes))
        if self._chunks:
            self._chunk_list.setCurrentRow(0)
        else:
            self._show_selected_chunk(-1)
        self._apply_button_state()

    def preview_scroll_state(self) -> dict[str, int]:
        """
        @brief      Return current cleaned-reference and chunk-list scroll state.
        @return     Mapping of local scroll and selection values.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        return {
            "cleaned_vertical": self._cleaned_text_edit.verticalScrollBar().value(),
            "cleaned_horizontal": self._cleaned_text_edit.horizontalScrollBar().value(),
            "chunk_list_vertical": self._chunk_list.verticalScrollBar().value(),
            "chunk_list_horizontal": self._chunk_list.horizontalScrollBar().value(),
            "chunk_list_row": self._chunk_list.currentRow(),
        }

    def restore_preview_scroll_state(self, scroll_state: dict[str, int]) -> None:
        """
        @brief      Restore cleaned-reference and chunk-list scroll state after refresh.
        @param[in]  scroll_state Scroll state returned by `preview_scroll_state`.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        row = scroll_state.get("chunk_list_row", -1)
        if 0 <= row < self._chunk_list.count():
            self._chunk_list.setCurrentRow(row)
        self._cleaned_text_edit.verticalScrollBar().setValue(scroll_state.get("cleaned_vertical", 0))
        self._cleaned_text_edit.horizontalScrollBar().setValue(scroll_state.get("cleaned_horizontal", 0))
        self._chunk_list.verticalScrollBar().setValue(scroll_state.get("chunk_list_vertical", 0))
        self._chunk_list.horizontalScrollBar().setValue(scroll_state.get("chunk_list_horizontal", 0))

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
        @version    0.3.0
        """
        enabled = self._project_active and not self._busy
        self._chunk_button.setEnabled(enabled and self._can_chunk)
        ai_selector_enabled = self._project_active and self._has_ai_profiles
        self._profile_label.setEnabled(ai_selector_enabled)
        self._profile_combo.setEnabled(ai_selector_enabled)
        self._strategy_label.setEnabled(self._project_active and (self._can_chunk or self._can_ai_chunk))
        self._strategy_combo.setEnabled(self._project_active and (self._can_chunk or self._can_ai_chunk))
        self._ai_chunk_button.setEnabled(enabled and self._can_ai_chunk and self.current_ai_profile_id() is not None)
        chunk_selected = 0 <= self._chunk_list.currentRow() < len(self._chunks)
        can_insert_chunk = chunk_selected or (self._can_chunk and not self._chunks)
        self._insert_chunk_button.setEnabled(enabled and can_insert_chunk and not self._editing_chunk)
        self._delete_chunk_button.setEnabled(
            enabled and chunk_selected and len(self._chunks) > 1 and not self._editing_chunk
        )
        self._edit_chunk_button.setEnabled(enabled and chunk_selected and not self._editing_chunk)
        self._save_chunk_button.setEnabled(enabled and chunk_selected and self._editing_chunk)

    def _apply_preview_splitter_minimums(self) -> None:
        """
        @brief      Set each chunking preview pane minimum width to one third of the preview splitter width.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-01
        @version    0.1.0
        """
        required_attributes = ("_preview_splitter", "_left_preview_container", "_chunk_preview_group")
        if not all(hasattr(self, attribute_name) for attribute_name in required_attributes):
            return
        splitter_width = self._preview_splitter.width()
        if splitter_width <= 0:
            return
        minimum_preview_width = splitter_width // 3
        self._left_preview_container.setMinimumWidth(minimum_preview_width)
        self._chunk_preview_group.setMinimumWidth(minimum_preview_width)

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
            self._chunk_text_edit.setReadOnly(True)
            self._editing_chunk = False
            self._apply_button_state()
            return
        self._chunk_text_edit.setPlainText(str(self._chunks[row].get("text", "")))
        self._chunk_text_edit.setReadOnly(True)
        self._editing_chunk = False
        self._apply_button_state()

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
        @date       2026-06-09
        @version    0.3.2
        """
        self._language = language
        self._title_label.setText(f"<h2>{ui_state_service.translate('text_chunking.title', language)}</h2>")
        self._profile_label.setText(ui_state_service.translate("text_chunking.ai_profile", language))
        self._strategy_label.setText(ui_state_service.translate("text_chunking.ai_strategy", language))
        self._chunk_button.setText(ui_state_service.translate("text_chunking.chunk", language))
        self._ai_chunk_button.setText(ui_state_service.translate("text_chunking.ai_chunk", language))
        self._cleaned_group.setTitle(ui_state_service.translate("text_chunking.cleaned_group", language))
        self._chunk_list_group.setTitle(ui_state_service.translate("text_chunking.chunk_list_group", language))
        self._chunk_preview_group.setTitle(ui_state_service.translate("text_chunking.selected_group", language))
        self._insert_chunk_button.setText(ui_state_service.translate("text_chunking.insert_chunk", language))
        self._delete_chunk_button.setText(ui_state_service.translate("text_chunking.delete_chunk", language))
        self._edit_chunk_button.setText(ui_state_service.translate("text_chunking.edit_chunk", language))
        self._save_chunk_button.setText(ui_state_service.translate("text_chunking.save_chunk", language))
        if not self._has_ai_profiles:
            self._profile_combo.setItemText(
                0,
                ui_state_service.translate("ai_settings.none", language),
            )

    def _install_preview_find_context_menu(self, editor: QPlainTextEdit) -> None:
        """
        @brief      Install right-click Find actions on one text preview.
        @param[in]  editor Preview editor receiving the custom context menu.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        editor.customContextMenuRequested.connect(
            lambda position, target_editor=editor: self._show_preview_menu(target_editor, position)
        )

    def _show_preview_menu(self, editor: QPlainTextEdit, position: QPoint) -> None:
        """
        @brief      Show one preview editor context menu with Find commands.
        @param[in]  editor Preview editor that opened the menu.
        @param[in]  position Local menu position inside the editor.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        menu = editor.createStandardContextMenu()
        menu.addSeparator()
        find_action = menu.addAction(ui_state_service.translate("text_chunking.find", self._current_language()))
        find_action.triggered.connect(
            lambda _checked=False, target_editor=editor: self._prompt_preview_find(target_editor)
        )
        find_next_action = menu.addAction(
            ui_state_service.translate("text_chunking.find_next", self._current_language())
        )
        find_next_action.setEnabled(bool(self._preview_find_text_by_editor_id.get(id(editor), "")))
        find_next_action.triggered.connect(
            lambda _checked=False, target_editor=editor: self._find_next_preview_text(target_editor)
        )
        menu.exec(editor.mapToGlobal(position))

    def _prompt_preview_find(self, editor: QPlainTextEdit) -> None:
        """
        @brief      Prompt for one search string and select the next preview match.
        @param[in]  editor Preview editor that should be searched.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        search_text, accepted = QInputDialog.getText(
            self,
            ui_state_service.translate("text_chunking.find_title", self._current_language()),
            ui_state_service.translate("text_chunking.find_prompt", self._current_language()),
        )
        if not accepted or not search_text:
            return
        self._preview_find_text_by_editor_id[id(editor)] = search_text
        if self._find_preview_text(editor, search_text):
            return
        self._show_find_not_found_message(search_text)

    def _find_next_preview_text(self, editor: QPlainTextEdit) -> None:
        """
        @brief      Select the next match for the current preview search text.
        @param[in]  editor Preview editor that should be searched.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        search_text = self._preview_find_text_by_editor_id.get(id(editor), "")
        if not search_text:
            self._prompt_preview_find(editor)
            return
        if self._find_preview_text(editor, search_text):
            return
        self._show_find_not_found_message(search_text)

    def _find_preview_text(self, editor: QPlainTextEdit, search_text: str) -> bool:
        """
        @brief      Find the next preview match, wrapping once from the document start.
        @param[in]  editor Preview editor to search.
        @param[in]  search_text Text to find.
        @return     True when one match was selected.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        if editor.find(search_text):
            return True
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        editor.setTextCursor(cursor)
        return editor.find(search_text)

    def _show_find_not_found_message(self, search_text: str) -> None:
        """
        @brief      Show one translated message for a missing preview search term.
        @param[in]  search_text Text that was not found in the preview.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        QMessageBox.information(
            self,
            ui_state_service.translate("text_chunking.find_title", self._current_language()),
            ui_state_service.translate("text_chunking.find_not_found", self._current_language()).format(
                search_text=search_text
            ),
        )

    def _begin_chunk_edit(self) -> None:
        """
        @brief      Enable editing for the selected chunk preview.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.2.0
        """
        if not (0 <= self._chunk_list.currentRow() < len(self._chunks)):
            return
        if not self._confirm_chunk_edit():
            return
        self._editing_chunk = True
        self._chunk_text_edit.setReadOnly(False)
        self._chunk_text_edit.setFocus()
        self._apply_button_state()

    def _confirm_chunk_edit(self) -> bool:
        """
        @brief      Confirm downstream impact before entering selected-chunk edit mode.
        @return     True when the operator confirms the edit impact.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-05
        @version    0.1.0
        """
        decision = QMessageBox.question(
            self,
            ui_state_service.translate("dialog.confirm_chunk_edit_title", self._current_language()),
            ui_state_service.translate("project.confirm_chunk_edit", self._current_language()),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return decision == QMessageBox.StandardButton.Yes

    def _emit_insert_chunk_requested(self) -> None:
        """
        @brief      Emit one request to insert a new chunk after the selection.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-04
        @version    0.2.0
        """
        row = self._chunk_list.currentRow()
        if self._editing_chunk:
            return
        if not self._chunks and self._can_chunk:
            self.insert_chunk_requested.emit("")
            return
        if row < 0 or row >= len(self._chunks):
            return
        self.insert_chunk_requested.emit(str(self._chunks[row].get("chunk_id", "")))

    def _emit_delete_chunk_requested(self) -> None:
        """
        @brief      Emit one request to delete the selected chunk.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-04
        @version    0.1.0
        """
        row = self._chunk_list.currentRow()
        if row < 0 or row >= len(self._chunks) or self._editing_chunk or len(self._chunks) <= 1:
            return
        self.delete_chunk_requested.emit(str(self._chunks[row].get("chunk_id", "")))

    def _emit_save_chunk_requested(self) -> None:
        """
        @brief      Emit one selected chunk text save request.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.2
        """
        row = self._chunk_list.currentRow()
        if not self._editing_chunk or row < 0 or row >= len(self._chunks):
            return
        self._editing_chunk = False
        self._chunk_text_edit.setReadOnly(True)
        chunk_id = str(self._chunks[row].get("chunk_id", ""))
        edited_text = self._chunk_text_edit.toPlainText()
        self._chunks[row]["text"] = edited_text
        self._chunk_list.item(row).setText(_format_chunk_list_item(self._chunks[row]))
        self.save_chunk_requested.emit(chunk_id, edited_text)
        self._apply_button_state()

    def _current_language(self) -> str:
        """
        @brief      Return the runtime language currently applied to the page.
        @return     Runtime UI language code.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        return str(getattr(self, "_language", config.DEFAULT_LANGUAGE))


def _format_chunk_list_item(chunk: dict[str, object]) -> str:
    """
    @brief      Format one chunk as a single-line list preview.
    @param[in]  chunk Chunk payload with chunk id and text.
    @return     Single-line chunk-list label.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-23
    @version    0.1.0
    """
    chunk_text = str(chunk.get("text", ""))
    preview_line = next((line.strip() for line in chunk_text.splitlines() if line.strip()), "")
    preview = " ".join(preview_line.split())
    return f"{chunk.get('chunk_id', '')} | {preview}"


# END OF FILE
