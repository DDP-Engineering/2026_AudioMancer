#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
"""
@file text_cleanup_page.py
@brief Unified Text Extraction and Cleanup V2 page.
@details Exposes one Cleanup action with an optional AI profile, split source
         and result previews, and optional operator Edit/Save/Cancel controls.
"""

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

from audiomancer import config
from audiomancer.services import ui_state_service


class TextCleanupPage(QWidget):
    """Display the single hybrid Cleanup workflow for the active project."""

    extract_requested = Signal()
    cleanup_requested = Signal(object)
    reset_cleanup_requested = Signal()
    save_cleaned_text_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._project_active = False
        self._busy = False
        self._can_extract = False
        self._can_clean = False
        self._can_reset_cleanup = False
        self._has_cleaned_text = False
        self._editing_cleaned_text = False
        self._language = config.DEFAULT_LANGUAGE

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self._title_label = QLabel("<h2>Text Cleanup</h2>", self)
        header.addWidget(self._title_label)
        header.addStretch(1)
        self._extract_button = QPushButton("Extract Text", self)
        self._extract_button.clicked.connect(self.extract_requested.emit)
        header.addWidget(self._extract_button)
        self._ai_profile_label = QLabel("AI Profile (optional)", self)
        header.addWidget(self._ai_profile_label)
        self._ai_profile_combo = QComboBox(self)
        self._ai_profile_combo.addItem("No AI", None)
        header.addWidget(self._ai_profile_combo)
        self._cleanup_button = QPushButton("Cleanup", self)
        self._cleanup_button.clicked.connect(self._emit_cleanup_requested)
        header.addWidget(self._cleanup_button)
        self._reset_cleanup_button = QPushButton("Reset Cleanup", self)
        self._reset_cleanup_button.clicked.connect(self.reset_cleanup_requested.emit)
        header.addWidget(self._reset_cleanup_button)
        layout.addLayout(header)

        self._preview_splitter = QSplitter(self)
        self._preview_splitter.setChildrenCollapsible(False)
        self._extracted_group = QGroupBox("Extracted Text Preview", self)
        extracted_layout = QVBoxLayout(self._extracted_group)
        self._extracted_text_edit = QPlainTextEdit(self)
        self._extracted_text_edit.setReadOnly(True)
        extracted_layout.addWidget(self._extracted_text_edit)
        self._cleaned_group = QGroupBox("Cleaned Text Preview", self)
        cleaned_layout = QVBoxLayout(self._cleaned_group)
        self._cleaned_text_edit = QPlainTextEdit(self)
        self._cleaned_text_edit.setReadOnly(True)
        cleaned_layout.addWidget(self._cleaned_text_edit)
        edit_row = QHBoxLayout()
        edit_row.addStretch(1)
        self._edit_cleaned_button = QPushButton("Edit", self)
        self._edit_cleaned_button.clicked.connect(self._begin_cleaned_text_edit)
        edit_row.addWidget(self._edit_cleaned_button)
        self._save_cleaned_button = QPushButton("Save", self)
        self._save_cleaned_button.clicked.connect(self._emit_save_cleaned_text_requested)
        edit_row.addWidget(self._save_cleaned_button)
        self._cancel_edit_button = QPushButton("Cancel", self)
        self._cancel_edit_button.clicked.connect(self._cancel_cleaned_text_edit)
        edit_row.addWidget(self._cancel_edit_button)
        cleaned_layout.addLayout(edit_row)
        self._preview_splitter.addWidget(self._extracted_group)
        self._preview_splitter.addWidget(self._cleaned_group)
        self._preview_splitter.setStretchFactor(0, 1)
        self._preview_splitter.setStretchFactor(1, 2)
        layout.addWidget(self._preview_splitter, 6)

        self._status_edit = QPlainTextEdit(self)
        self._status_edit.setReadOnly(True)
        self._status_edit.setProperty(
            ui_state_service.CONTROL_TEXT_FONT_ROLE_PROPERTY,
            ui_state_service.CONTROL_TEXT_FONT_ROLE_VALUE,
        )
        self._status_edit.setFixedHeight(ui_state_service.operator_status_pane_height(self._status_edit))
        layout.addWidget(self._status_edit)
        self._saved_cleaned_text = ""
        self.set_processing_state(None, None, ["Import a source to begin text extraction."], False, False)

    def set_project_active(self, is_active: bool) -> None:
        self._project_active = bool(is_active)
        self._apply_button_state()

    def set_processing_state(
        self,
        extracted_text: str | None,
        cleaned_text: str | None,
        notes: list[str],
        can_extract: bool,
        can_clean: bool,
        can_reset_cleanup: bool = False,
        validation_state: str = "not_started",
        uncertainty_count: int = 0,
    ) -> None:
        """Refresh previews and terminal Cleanup status."""
        self._can_extract = bool(can_extract)
        self._can_clean = bool(can_clean)
        self._can_reset_cleanup = bool(can_reset_cleanup)
        self._has_cleaned_text = bool((cleaned_text or "").strip())
        self._editing_cleaned_text = False
        self._saved_cleaned_text = cleaned_text or ""
        self._extracted_text_edit.setPlainText(extracted_text or "")
        self._cleaned_text_edit.setPlainText(cleaned_text or "")
        self._cleaned_text_edit.setReadOnly(True)
        status_notes = list(notes)
        if validation_state in {"passed", "passed_with_warnings"}:
            status_notes.append(
                f"Validation: {validation_state}; "
                f"low-confidence boundaries: {int(uncertainty_count)}."
            )
        self._status_edit.setPlainText("\n".join(status_notes))
        self._apply_button_state()

    def set_ai_profiles(
        self,
        entries: list[tuple[str, str | None]],
        selected_profile_id: str | None,
    ) -> None:
        """Populate an optional selector; deterministic Cleanup remains available."""
        self._ai_profile_combo.blockSignals(True)
        self._ai_profile_combo.clear()
        self._ai_profile_combo.addItem(
            ui_state_service.translate("ai_settings.none", self._language),
            None,
        )
        for label, profile_id in entries:
            self._ai_profile_combo.addItem(label, profile_id)
        selected_index = next(
            (
                index
                for index in range(self._ai_profile_combo.count())
                if self._ai_profile_combo.itemData(index) == selected_profile_id
            ),
            0,
        )
        self._ai_profile_combo.setCurrentIndex(selected_index)
        self._ai_profile_combo.blockSignals(False)

    def current_ai_profile_id(self) -> str | None:
        value = self._ai_profile_combo.currentData()
        return None if value in (None, "") else str(value)

    def preview_scroll_state(self) -> dict[str, tuple[int, int]]:
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

    def restore_preview_scroll_state(self, state: dict[str, tuple[int, int]]) -> None:
        for name, editor in (
            ("extracted", self._extracted_text_edit),
            ("cleaned", self._cleaned_text_edit),
        ):
            position = state.get(name)
            if position is not None:
                editor.verticalScrollBar().setValue(position[0])
                editor.horizontalScrollBar().setValue(position[1])

    def set_busy(self, is_busy: bool, operation_name: str | None = None) -> None:
        self._busy = bool(is_busy)
        _ = operation_name
        self._apply_button_state()

    def apply_language(self, language: str) -> None:
        self._language = language
        self._title_label.setText(f"<h2>{ui_state_service.translate('text_cleanup.title', language)}</h2>")
        self._extract_button.setText(ui_state_service.translate("text_cleanup.extract", language))
        self._cleanup_button.setText(ui_state_service.translate("text_cleanup.clean", language))
        self._ai_profile_label.setText(ui_state_service.translate("text_cleanup.ai_profile", language))
        self._reset_cleanup_button.setText(ui_state_service.translate("text_cleanup.reset", language))
        self._edit_cleaned_button.setText(ui_state_service.translate("text_cleanup.edit_cleaned", language))
        self._save_cleaned_button.setText(ui_state_service.translate("text_cleanup.save_cleaned", language))
        self._cancel_edit_button.setText(ui_state_service.translate("text_cleanup.cancel_edit", language))
        self._extracted_group.setTitle(ui_state_service.translate("text_cleanup.extracted_group", language))
        self._cleaned_group.setTitle(ui_state_service.translate("text_cleanup.cleaned_group", language))
        self._ai_profile_combo.setItemText(0, ui_state_service.translate("ai_settings.none", language))
        if not self._project_active:
            self._status_edit.setPlainText(ui_state_service.translate("text_cleanup.initial_note", language))

    def _emit_cleanup_requested(self) -> None:
        self.cleanup_requested.emit(self.current_ai_profile_id())

    def _begin_cleaned_text_edit(self) -> None:
        self._saved_cleaned_text = self._cleaned_text_edit.toPlainText()
        self._editing_cleaned_text = True
        self._cleaned_text_edit.setReadOnly(False)
        self._cleaned_text_edit.setFocus()
        self._apply_button_state()

    def _cancel_cleaned_text_edit(self) -> None:
        self._cleaned_text_edit.setPlainText(self._saved_cleaned_text)
        self._editing_cleaned_text = False
        self._cleaned_text_edit.setReadOnly(True)
        self._apply_button_state()

    def _emit_save_cleaned_text_requested(self) -> None:
        self.save_cleaned_text_requested.emit(self._cleaned_text_edit.toPlainText())

    def _apply_button_state(self) -> None:
        enabled = self._project_active and not self._busy
        self._extract_button.setEnabled(enabled and self._can_extract)
        self._cleanup_button.setEnabled(enabled and self._can_clean)
        self._ai_profile_label.setEnabled(enabled)
        self._ai_profile_combo.setEnabled(enabled)
        self._reset_cleanup_button.setEnabled(enabled and self._can_reset_cleanup)
        self._edit_cleaned_button.setEnabled(enabled and self._has_cleaned_text and not self._editing_cleaned_text)
        self._save_cleaned_button.setEnabled(enabled and self._has_cleaned_text and self._editing_cleaned_text)
        self._cancel_edit_button.setEnabled(enabled and self._has_cleaned_text and self._editing_cleaned_text)
