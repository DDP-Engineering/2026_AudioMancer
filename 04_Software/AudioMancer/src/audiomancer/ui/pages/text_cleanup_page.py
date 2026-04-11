#!/usr/bin/env python3
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
         state for the current text-processing slice.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.5.0
"""

# IMPORTS

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from audiomancer.services import ui_state_service

# PUBLIC API


class TextCleanupPage(QWidget):
    """
    @brief      Display extraction and cleanup controls for the active project.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.3.0
    """

    extract_requested = Signal()
    clean_requested = Signal()
    ai_clean_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the extraction-aware text cleanup page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.4.0
        """
        super().__init__(parent)
        self._project_active = False
        self._busy = False
        self._can_extract = False
        self._can_clean = False
        self._can_ai_clean = False
        self._has_ai_profiles = False
        self._busy_operation_name = None
        self._ai_profile_entries: list[tuple[str, str | None]] = []

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
        extracted_layout.addWidget(self._extracted_text_edit)

        cleaned_group = QGroupBox("Cleaned Text Preview", self)
        cleaned_layout = QVBoxLayout(cleaned_group)
        self._cleaned_text_edit = QPlainTextEdit(self)
        self._cleaned_text_edit.setReadOnly(True)
        cleaned_layout.addWidget(self._cleaned_text_edit)

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
        @version    0.3.1
        """
        self._can_extract = can_extract
        self._can_clean = can_clean
        self._can_ai_clean = can_ai_clean
        self._apply_button_state()
        self._extracted_text_edit.setPlainText(extracted_text or "")
        self._cleaned_text_edit.setPlainText(cleaned_text or "")
        self._notes_edit.setPlainText("\n".join(notes))

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
        @version    0.3.1
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

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one translated UI language to the page widgets.
        @param[in]  language Runtime UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.3.1
        """
        self._title_label.setText(f"<h2>{ui_state_service.translate('text_cleanup.title', language)}</h2>")
        self._extract_button.setText(ui_state_service.translate("text_cleanup.extract", language))
        self._clean_button.setText(ui_state_service.translate("text_cleanup.clean", language))
        self._ai_profile_label.setText(ui_state_service.translate("text_cleanup.ai_profile", language))
        self._ai_clean_button.setText(ui_state_service.translate("text_cleanup.ai_clean", language))
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


# END OF FILE
