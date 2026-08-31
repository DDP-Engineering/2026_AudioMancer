#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""Book Analysis page with one profile selector and Analyze/Reset actions."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import ui_state_service

_CONCISE_FIELDS = (
    "book_type",
    "genres",
    "subjects",
    "setting_time",
    "summary",
    "main_characters",
    "themes",
)
_DETAIL_FIELDS = (
    "detailed_summary",
    "supporting_characters",
    "narrative_perspective",
    "narrative_structure",
    "tone",
    "pacing",
    "diction",
    "emotional_range",
    "audiobook_guidance",
    "uncertainties",
    "source_evidence",
)


class BookAnalysisPage(QWidget):
    """Render a layered report and emit the two supported operator actions."""

    analyze_requested = Signal(str)
    reset_requested = Signal()
    profile_selection_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._language = config.DEFAULT_LANGUAGE
        self._project_active = False
        self._busy = False
        self._has_profiles = False
        self._can_analyze = False
        self._can_reset = False
        self._notes: list[str] = []

        root_layout = QVBoxLayout(self)
        header_row = QHBoxLayout()
        self._title_label = QLabel()
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)

        self._profile_label = QLabel()
        self._profile_combo = QComboBox()
        self._profile_combo.setObjectName("book_analysis_profile")
        self._analyze_button = QPushButton()
        self._reset_button = QPushButton()
        header_row.addWidget(self._profile_label)
        header_row.addWidget(self._profile_combo)
        header_row.addWidget(self._analyze_button)
        header_row.addWidget(self._reset_button)
        root_layout.addLayout(header_row)

        self._note_label = QLabel()
        self._note_label.setWordWrap(True)
        self._note_label.setTextFormat(Qt.TextFormat.PlainText)
        self._note_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root_layout.addWidget(self._note_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        report_widget = QWidget()
        report_layout = QVBoxLayout(report_widget)

        self._concise_group = QGroupBox()
        concise_form = QFormLayout(self._concise_group)
        self._concise_labels: dict[str, QLabel] = {}
        self._concise_values: dict[str, QLabel] = {}
        for field_name in _CONCISE_FIELDS:
            field_label = _report_field_label()
            value_label = _report_label()
            self._concise_labels[field_name] = field_label
            self._concise_values[field_name] = value_label
            concise_form.addRow(field_label, value_label)
        report_layout.addWidget(self._concise_group)

        self._details_group = QGroupBox()
        self._details_group.setObjectName("bookAnalysisDetails")
        self._details_group.setCheckable(True)
        self._details_group.setChecked(False)
        details_layout = QVBoxLayout(self._details_group)
        details_layout.setContentsMargins(concise_form.contentsMargins())
        self._details_content = QWidget()
        detail_form = QFormLayout(self._details_content)
        detail_form.setContentsMargins(0, 0, 0, 0)
        self._detail_labels: dict[str, QLabel] = {}
        self._detail_values: dict[str, QLabel] = {}
        for field_name in _DETAIL_FIELDS:
            field_label = _report_field_label()
            value_label = _report_label()
            self._detail_labels[field_name] = field_label
            self._detail_values[field_name] = value_label
            detail_form.addRow(field_label, value_label)
        details_layout.addWidget(self._details_content)
        self._details_expanded_maximum_height = self._details_group.maximumHeight()
        self._details_group.toggled.connect(self._set_details_expanded)
        self._set_details_expanded(False)
        report_layout.addWidget(self._details_group)
        report_layout.addStretch(1)
        scroll_area.setWidget(report_widget)
        root_layout.addWidget(scroll_area, 1)

        self._analyze_button.clicked.connect(self._emit_analyze_requested)
        self._reset_button.clicked.connect(self.reset_requested.emit)
        self._profile_combo.currentIndexChanged.connect(self._apply_button_state)
        self._profile_combo.currentIndexChanged.connect(self._emit_profile_selection_changed)
        self.apply_language(self._language)
        self._clear_report()
        self._apply_button_state()

    def set_project_active(self, is_active: bool) -> None:
        self._project_active = bool(is_active)
        self._apply_button_state()

    def set_ai_profiles(
        self,
        entries: list[tuple[str, str | None]],
        selected_profile_id: str | None,
    ) -> None:
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        for label, profile_id in entries:
            self._profile_combo.addItem(label, profile_id)
        if entries:
            selected_index = next(
                (
                    index
                    for index, (_label, profile_id) in enumerate(entries)
                    if profile_id == selected_profile_id
                ),
                0,
            )
            self._profile_combo.setCurrentIndex(selected_index)
        else:
            self._profile_combo.addItem(
                ui_state_service.translate("ai_settings.none", self._language),
                None,
            )
        self._profile_combo.blockSignals(False)
        self._has_profiles = bool(entries)
        self._apply_button_state()

    def set_analysis_state(
        self,
        *,
        state: str,
        notes: list[str],
        report: dict[str, object] | None,
        report_stale: bool,
        can_analyze: bool,
        can_reset: bool,
    ) -> None:
        _ = state
        self._notes = [str(note) for note in notes]
        self._can_analyze = bool(can_analyze)
        self._can_reset = bool(can_reset)
        note_lines = list(self._notes)
        if report_stale and not any("stale" in note.casefold() for note in note_lines):
            note_lines.append(ui_state_service.translate("book_analysis.note_stale", self._language))
        self._note_label.setText("\n".join(note_lines))
        if isinstance(report, dict):
            self._render_report(report)
        else:
            self._clear_report()
        self._apply_button_state()

    def set_busy(self, is_busy: bool) -> None:
        self._busy = bool(is_busy)
        self._apply_button_state()

    def current_profile_id(self) -> str | None:
        value = self._profile_combo.currentData()
        return None if value in (None, "") else str(value)

    def operation_status_text(self) -> str:
        return "\n".join(self._notes)

    def apply_language(self, language: str) -> None:
        self._language = language
        self._title_label.setText(
            f"<h2>{ui_state_service.translate('book_analysis.title', language)}</h2>"
        )
        self._profile_label.setText(ui_state_service.translate("book_analysis.ai_profile", language))
        self._analyze_button.setText(ui_state_service.translate("book_analysis.analyze", language))
        self._reset_button.setText(ui_state_service.translate("book_analysis.reset", language))
        self._concise_group.setTitle(
            ui_state_service.translate("book_analysis.concise_group", language)
        )
        self._details_group.setTitle(
            ui_state_service.translate("book_analysis.details_group", language)
        )
        for field_name, label in self._concise_labels.items():
            label.setText(ui_state_service.translate(f"book_analysis.field.{field_name}", language))
        for field_name, label in self._detail_labels.items():
            label.setText(ui_state_service.translate(f"book_analysis.field.{field_name}", language))
        if not self._has_profiles and self._profile_combo.count():
            self._profile_combo.setItemText(
                0,
                ui_state_service.translate("ai_settings.none", language),
            )

    def _emit_analyze_requested(self) -> None:
        profile_id = self.current_profile_id()
        if profile_id is not None:
            self.analyze_requested.emit(profile_id)

    def _emit_profile_selection_changed(self, _index: int) -> None:
        profile_id = self.current_profile_id()
        if profile_id is not None:
            self.profile_selection_changed.emit(profile_id)

    def _apply_button_state(self, *_args) -> None:
        profile_available = self._has_profiles and self.current_profile_id() is not None
        self._profile_label.setEnabled(self._project_active and not self._busy)
        self._profile_combo.setEnabled(self._project_active and not self._busy and self._has_profiles)
        self._analyze_button.setEnabled(
            self._project_active
            and not self._busy
            and self._can_analyze
            and profile_available
        )
        self._reset_button.setEnabled(self._project_active and self._can_reset)

    def _set_details_expanded(self, expanded: bool) -> None:
        self._details_group.setFlat(not expanded)
        self._details_group.setMaximumHeight(
            self._details_expanded_maximum_height
            if expanded
            else self._details_group.fontMetrics().height() + 10
        )
        self._details_content.setVisible(expanded)
        self._details_group.updateGeometry()

    def _clear_report(self) -> None:
        for label in (*self._concise_values.values(), *self._detail_values.values()):
            label.setText("—")

    def _render_report(self, report: dict[str, object]) -> None:
        concise = report.get("concise") if isinstance(report.get("concise"), dict) else {}
        details = report.get("details") if isinstance(report.get("details"), dict) else {}
        for field_name, label in self._concise_values.items():
            label.setText(_format_report_value(field_name, concise.get(field_name)))
        for field_name, label in self._detail_values.items():
            label.setText(_format_report_value(field_name, details.get(field_name)))


def _report_label() -> QLabel:
    label = QLabel("—")
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _report_field_label() -> QLabel:
    """Create a bold field label while inheriting the active application font."""
    label = QLabel()
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


def _format_report_value(field_name: str, value: object) -> str:
    if isinstance(value, str):
        return value or "—"
    if not isinstance(value, list) and not isinstance(value, dict):
        return "—"
    if field_name in {"main_characters", "supporting_characters"} and isinstance(value, list):
        lines = []
        for item in value:
            if not isinstance(item, dict):
                continue
            text = f"{item.get('name', '')} — {item.get('role', '')}"
            relationships = item.get("relationships")
            if isinstance(relationships, list) and relationships:
                text += f" ({'; '.join(str(entry) for entry in relationships)})"
            lines.append(text)
        return "\n".join(lines) or "—"
    if field_name == "audiobook_guidance" and isinstance(value, dict):
        notes = value.get("character_voice_notes")
        note_text = "; ".join(str(note) for note in notes) if isinstance(notes, list) else ""
        return "\n".join(
            part for part in (str(value.get("narration_style", "")), note_text) if part
        ) or "—"
    if field_name == "source_evidence" and isinstance(value, list):
        lines = []
        for item in value:
            if not isinstance(item, dict):
                continue
            chunk_ids = item.get("chunk_ids")
            chunks = ", ".join(str(chunk_id) for chunk_id in chunk_ids) if isinstance(chunk_ids, list) else ""
            lines.append(f"{chunks}: {item.get('note', '')}")
        return "\n".join(lines) or "—"
    if isinstance(value, list):
        return "\n".join(str(item) for item in value) or "—"
    return "—"


# END OF FILE
