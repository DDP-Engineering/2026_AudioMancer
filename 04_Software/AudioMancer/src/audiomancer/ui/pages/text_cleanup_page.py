#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file text_cleanup_page.py
@brief Text extraction and cleanup page for AudioMancer.
@details Provides the operator-facing extraction and deterministic cleanup
         state plus manual cleaned-text editing for the current
         text-processing slice, including local preview text search.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.8.0
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


class TextCleanupPage(QWidget):
    """
    @brief      Display extraction and cleanup controls for the active project.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.6.0
    """

    extract_requested = Signal()
    clean_requested = Signal()
    ai_clean_requested = Signal(str)
    save_cleaned_text_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the extraction-aware text cleanup page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.7.0
        """
        super().__init__(parent)
        self._project_active = False
        self._busy = False
        self._can_extract = False
        self._can_clean = False
        self._can_ai_clean = False
        self._has_cleaned_text = False
        self._editing_cleaned_text = False
        self._has_ai_profiles = False
        self._busy_operation_name = None
        self._language = config.DEFAULT_LANGUAGE
        self._ai_profile_entries: list[tuple[str, str | None]] = []
        self._preview_find_text_by_editor_id: dict[int, str] = {}

        layout = QVBoxLayout(self)
        header_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Text Cleanup</h2>")
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)

        self._extract_button = QPushButton("Extract Text")
        self._extract_button.clicked.connect(self.extract_requested.emit)
        header_row.addWidget(self._extract_button)

        self._clean_button = QPushButton("Deterministic Cleanup")
        self._clean_button.clicked.connect(self.clean_requested.emit)
        header_row.addWidget(self._clean_button)

        self._ai_profile_label = QLabel("AI Profile")
        self._ai_profile_label.setEnabled(False)
        header_row.addWidget(self._ai_profile_label)

        self._ai_profile_combo = QComboBox(self)
        self._ai_profile_combo.addItem("(none)", None)
        self._ai_profile_combo.setEnabled(False)
        header_row.addWidget(self._ai_profile_combo)

        self._ai_clean_button = QPushButton("AI-Assisted Cleanup")
        self._ai_clean_button.setEnabled(False)
        self._ai_clean_button.clicked.connect(self._emit_ai_clean_requested)
        header_row.addWidget(self._ai_clean_button)

        layout.addLayout(header_row)

        splitter = QSplitter(self)

        extracted_group = QGroupBox("Extracted Text Preview", self)
        extracted_layout = QVBoxLayout(extracted_group)
        self._extracted_text_edit = QPlainTextEdit(self)
        self._extracted_text_edit.setReadOnly(True)
        self._install_preview_find_context_menu(self._extracted_text_edit)
        extracted_layout.addWidget(self._extracted_text_edit)

        cleaned_group = QGroupBox("Cleaned Text Preview", self)
        cleaned_layout = QVBoxLayout(cleaned_group)
        self._cleaned_text_edit = QPlainTextEdit(self)
        self._cleaned_text_edit.setReadOnly(True)
        self._install_preview_find_context_menu(self._cleaned_text_edit)
        cleaned_layout.addWidget(self._cleaned_text_edit)
        cleaned_action_row = QHBoxLayout()
        cleaned_action_row.addStretch(1)
        self._edit_cleaned_button = QPushButton("Edit")
        self._edit_cleaned_button.clicked.connect(self._begin_cleaned_text_edit)
        cleaned_action_row.addWidget(self._edit_cleaned_button)
        self._save_cleaned_button = QPushButton("Save")
        self._save_cleaned_button.clicked.connect(self._emit_save_cleaned_text_requested)
        cleaned_action_row.addWidget(self._save_cleaned_button)
        cleaned_layout.addLayout(cleaned_action_row)

        splitter.addWidget(extracted_group)
        splitter.addWidget(cleaned_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 6)

        notes_group = QGroupBox("Cleanup Notes", self)
        notes_layout = QVBoxLayout(notes_group)
        self._notes_edit = QPlainTextEdit(self)
        self._notes_edit.setReadOnly(True)
        notes_layout.addWidget(self._notes_edit)
        notes_group.setMinimumHeight(96)
        notes_group.setMaximumHeight(112)
        layout.addWidget(notes_group, 0)

        self._extracted_group = extracted_group
        self._cleaned_group = cleaned_group
        self._notes_group = notes_group

        self.set_project_active(False)
        self.set_processing_state(
            extracted_text=None,
            cleaned_text=None,
            notes=["Import a source to begin text extraction."],
            can_extract=False,
            can_clean=False,
            can_ai_clean=False,
        )

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Enable or disable extraction controls based on project availability.
        @param[in]  is_active True when a project is open.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.1
        """
        self._project_active = is_active
        self._apply_button_state()

    def set_processing_state(
        self,
        extracted_text: str | None,
        cleaned_text: str | None,
        notes: list[str],
        can_extract: bool,
        can_clean: bool,
        can_ai_clean: bool,
    ) -> None:
        """
        @brief      Refresh the page from extraction-state inputs.
        @param[in]  extracted_text Extracted text preview or `None`.
        @param[in]  cleaned_text Cleaned text preview or `None`.
        @param[in]  notes Operator-facing cleanup/extraction notes.
        @param[in]  can_extract True when extraction may run.
        @param[in]  can_clean True when deterministic cleanup may run.
        @param[in]  can_ai_clean True when AI-assisted cleanup may run.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.4.0
        """
        self._can_extract = can_extract
        self._can_clean = can_clean
        self._can_ai_clean = can_ai_clean
        self._has_cleaned_text = bool((cleaned_text or "").strip())
        self._editing_cleaned_text = False
        self._extracted_text_edit.setPlainText(extracted_text or "")
        self._cleaned_text_edit.setPlainText(cleaned_text or "")
        self._cleaned_text_edit.setReadOnly(True)
        self._notes_edit.setPlainText("\n".join(notes))
        self._apply_button_state()

    def preview_scroll_state(self) -> dict[str, tuple[int, int]]:
        """
        @brief      Return current preview editor scrollbar positions.
        @return     Mapping of preview names to vertical and horizontal scrollbar positions.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        return {
            "extracted": (
                self._extracted_text_edit.verticalScrollBar().value(),
                self._extracted_text_edit.horizontalScrollBar().value(),
            ),
            "cleaned": (
                self._cleaned_text_edit.verticalScrollBar().value(),
                self._cleaned_text_edit.horizontalScrollBar().value(),
            ),
        }

    def restore_preview_scroll_state(self, scroll_state: dict[str, tuple[int, int]]) -> None:
        """
        @brief      Restore preview editor scrollbar positions after a project-state refresh.
        @param[in]  scroll_state Preview scrollbar positions returned by `preview_scroll_state`.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        extracted_position = scroll_state.get("extracted")
        if extracted_position is not None:
            self._extracted_text_edit.verticalScrollBar().setValue(extracted_position[0])
            self._extracted_text_edit.horizontalScrollBar().setValue(extracted_position[1])
        cleaned_position = scroll_state.get("cleaned")
        if cleaned_position is not None:
            self._cleaned_text_edit.verticalScrollBar().setValue(cleaned_position[0])
            self._cleaned_text_edit.horizontalScrollBar().setValue(cleaned_position[1])

    def set_ai_profiles(
        self,
        entries: list[tuple[str, str | None]],
        selected_profile_id: str | None,
    ) -> None:
        """
        @brief      Populate the AI cleanup profile selector.
        @param[in]  entries Ordered profile label/id entries for the selector.
        @param[in]  selected_profile_id Profile id that should be selected.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.1
        """
        self._ai_profile_entries = list(entries)
        self._has_ai_profiles = bool(entries)
        self._ai_profile_combo.blockSignals(True)
        self._ai_profile_combo.clear()
        if entries:
            for label, profile_id in entries:
                self._ai_profile_combo.addItem(label, profile_id)
            selected_index = next(
                (index for index, (_label, profile_id) in enumerate(entries) if profile_id == selected_profile_id),
                0,
            )
            self._ai_profile_combo.setCurrentIndex(selected_index)
        else:
            self._ai_profile_combo.addItem("(none)", None)
            self._ai_profile_combo.setCurrentIndex(0)
        self._ai_profile_combo.blockSignals(False)
        self._apply_button_state()

    def current_ai_profile_id(self) -> str | None:
        """
        @brief      Return the currently selected AI cleanup profile id.
        @return     Selected AI profile id or None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        current_value = self._ai_profile_combo.currentData()
        return None if current_value in (None, "") else str(current_value)

    def set_busy(self, is_busy: bool, operation_name: str | None = None) -> None:
        """
        @brief      Disable page actions while one long-running operation is active.
        @param[in]  is_busy True while the page operation is running.
        @param[in]  operation_name Optional operator-facing busy operation label.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.2.0
        """
        self._busy = is_busy
        self._busy_operation_name = operation_name if is_busy else None
        self._apply_button_state()

    def _apply_button_state(self) -> None:
        """
        @brief      Apply the current page button states.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.4.0
        """
        self._extract_button.setEnabled(self._project_active and self._can_extract and not self._busy)
        self._clean_button.setEnabled(self._project_active and self._can_clean and not self._busy)
        ai_selector_enabled = self._project_active and self._has_ai_profiles and not self._busy
        self._ai_profile_label.setEnabled(ai_selector_enabled)
        self._ai_profile_combo.setEnabled(ai_selector_enabled)
        self._ai_clean_button.setEnabled(
            self._project_active
            and self._can_ai_clean
            and self._has_ai_profiles
            and self.current_ai_profile_id() is not None
            and not self._busy
        )
        self._edit_cleaned_button.setEnabled(
            self._project_active and self._has_cleaned_text and not self._busy and not self._editing_cleaned_text
        )
        self._save_cleaned_button.setEnabled(
            self._project_active and self._has_cleaned_text and not self._busy and self._editing_cleaned_text
        )

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one translated UI language to the page widgets.
        @param[in]  language Runtime UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.5.0
        """
        self._language = language
        self._title_label.setText(f"<h2>{ui_state_service.translate('text_cleanup.title', language)}</h2>")
        self._extract_button.setText(ui_state_service.translate("text_cleanup.extract", language))
        self._clean_button.setText(ui_state_service.translate("text_cleanup.clean", language))
        self._ai_profile_label.setText(ui_state_service.translate("text_cleanup.ai_profile", language))
        self._ai_clean_button.setText(ui_state_service.translate("text_cleanup.ai_clean", language))
        self._edit_cleaned_button.setText(ui_state_service.translate("text_cleanup.edit_cleaned", language))
        self._save_cleaned_button.setText(ui_state_service.translate("text_cleanup.save_cleaned", language))
        self._extracted_group.setTitle(ui_state_service.translate("text_cleanup.extracted_group", language))
        self._cleaned_group.setTitle(ui_state_service.translate("text_cleanup.cleaned_group", language))
        self._notes_group.setTitle(ui_state_service.translate("text_cleanup.notes_group", language))
        if not self._has_ai_profiles:
            self._ai_profile_combo.setItemText(
                0,
                ui_state_service.translate("ai_settings.none", language),
            )

    def _emit_ai_clean_requested(self) -> None:
        """
        @brief      Emit one AI-cleanup request with the selected profile id.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        profile_id = self.current_ai_profile_id()
        if profile_id is not None:
            self.ai_clean_requested.emit(profile_id)

    def _install_preview_find_context_menu(self, editor: QPlainTextEdit) -> None:
        """
        @brief      Install one right-click Find action on a preview editor.
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
        @version    0.2.0
        """
        menu = editor.createStandardContextMenu()
        menu.addSeparator()
        find_action = menu.addAction(ui_state_service.translate("text_cleanup.find", self._current_language()))
        find_action.triggered.connect(
            lambda _checked=False, target_editor=editor: self._prompt_preview_find(target_editor)
        )
        find_next_action = menu.addAction(
            ui_state_service.translate("text_cleanup.find_next", self._current_language())
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
        @version    0.2.0
        """
        search_text, accepted = QInputDialog.getText(
            self,
            ui_state_service.translate("text_cleanup.find_title", self._current_language()),
            ui_state_service.translate("text_cleanup.find_prompt", self._current_language()),
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
            ui_state_service.translate("text_cleanup.find_title", self._current_language()),
            ui_state_service.translate("text_cleanup.find_not_found", self._current_language()).format(
                search_text=search_text
            ),
        )

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

    def _begin_cleaned_text_edit(self) -> None:
        """
        @brief      Enable manual editing for the cleaned text preview.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        if not self._has_cleaned_text:
            return
        self._editing_cleaned_text = True
        self._cleaned_text_edit.setReadOnly(False)
        self._cleaned_text_edit.setFocus()
        self._apply_button_state()

    def _emit_save_cleaned_text_requested(self) -> None:
        """
        @brief      Emit the edited cleaned text save request.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        if not self._editing_cleaned_text:
            return
        self._editing_cleaned_text = False
        self._cleaned_text_edit.setReadOnly(True)
        self._has_cleaned_text = bool(self._cleaned_text_edit.toPlainText().strip())
        self.save_cleaned_text_requested.emit(self._cleaned_text_edit.toPlainText())
        self._apply_button_state()


# END OF FILE
