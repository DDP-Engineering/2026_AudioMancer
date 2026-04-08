#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file characters_page.py
@brief Character Discovery workflow page for AudioMancer.
@details Provides AI profile selection, character review, editable profile
         fields, and evidence preview for discovered speaking characters.
@author Eng. Dan Dumitru Pasare
@date 2026-04-08
@version 0.1.0
"""

# IMPORTS

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from audiomancer.services import character_discovery_service
from audiomancer.services import ui_state_service


# PUBLIC API


class CharactersPage(QWidget):
    """
    @brief      Display the Character Discovery workflow page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """

    start_discovery_requested = Signal(str)
    reset_discovery_requested = Signal()
    profile_changed = Signal(dict)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the Character Discovery workflow page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        super().__init__(parent)
        self._project_active = False
        self._busy = False
        self._stage_status = character_discovery_service.CHARACTER_DISCOVERY_STAGE_NOT_STARTED
        self._profiles: list[dict[str, object]] = []
        self._source_chunk_map: dict[str, str] = {}
        self._current_character_id: str | None = None
        self._loading_profile = False
        self._can_start = False
        self._can_reset = False

        layout = QVBoxLayout(self)
        header_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Characters</h2>")
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)

        self._profile_label = QLabel("AI Profile")
        header_row.addWidget(self._profile_label)
        self._profile_combo = QComboBox(self)
        self._profile_combo.addItem("(none)", None)
        header_row.addWidget(self._profile_combo)

        self._start_button = QPushButton("Start Discovery")
        self._start_button.clicked.connect(self._emit_start_discovery)
        header_row.addWidget(self._start_button)

        self._reset_button = QPushButton("Reset Discovery")
        self._reset_button.clicked.connect(self.reset_discovery_requested.emit)
        header_row.addWidget(self._reset_button)
        layout.addLayout(header_row)

        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(False)
        layout.addWidget(self._summary_label)

        self._main_splitter = QSplitter(self)
        self._left_splitter = QSplitter(self)
        self._left_splitter.setOrientation(Qt.Orientation.Vertical)

        self._list_group = QGroupBox("Character List", self)
        self._list_group.setMinimumHeight(190)
        list_layout = QVBoxLayout(self._list_group)
        self._character_list = QListWidget(self)
        self._character_list.currentRowChanged.connect(self._show_selected_profile)
        list_layout.addWidget(self._character_list)
        self._left_splitter.addWidget(self._list_group)

        self._editor_group = QGroupBox("Character Profile", self)
        self._editor_group.setMinimumHeight(340)
        editor_group_layout = QVBoxLayout(self._editor_group)
        editor_group_layout.setContentsMargins(6, 12, 6, 6)
        self._editor_scroll_area = QScrollArea(self._editor_group)
        self._editor_scroll_area.setWidgetResizable(True)
        self._editor_scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._editor_scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._editor_form_widget = QWidget(self._editor_scroll_area)
        editor_layout = QFormLayout(self._editor_form_widget)
        editor_layout.setContentsMargins(4, 4, 4, 4)
        editor_layout.setHorizontalSpacing(12)
        editor_layout.setVerticalSpacing(8)

        self._canonical_name_edit = QLineEdit(self)
        self._aliases_edit = QLineEdit(self)
        self._gender_hint_edit = QLineEdit(self)
        self._age_band_edit = QLineEdit(self)
        self._role_summary_edit = QPlainTextEdit(self)
        self._description_edit = QPlainTextEdit(self)
        self._temperament_edit = QPlainTextEdit(self)
        self._social_status_edit = QPlainTextEdit(self)
        self._speaking_style_edit = QPlainTextEdit(self)
        self._accent_edit = QLineEdit(self)
        self._voice_notes_edit = QPlainTextEdit(self)
        self._relationships_edit = QPlainTextEdit(self)
        self._confidence_edit = QLineEdit(self)

        self._editor_widgets = [
            self._canonical_name_edit,
            self._aliases_edit,
            self._gender_hint_edit,
            self._age_band_edit,
            self._role_summary_edit,
            self._description_edit,
            self._temperament_edit,
            self._social_status_edit,
            self._speaking_style_edit,
            self._accent_edit,
            self._voice_notes_edit,
            self._relationships_edit,
            self._confidence_edit,
        ]

        for widget in (
            self._canonical_name_edit,
            self._aliases_edit,
            self._gender_hint_edit,
            self._age_band_edit,
            self._accent_edit,
            self._confidence_edit,
        ):
            widget.setMinimumHeight(30)
            widget.editingFinished.connect(self._emit_profile_changed)
        for widget in (
            self._role_summary_edit,
            self._description_edit,
            self._temperament_edit,
            self._social_status_edit,
            self._speaking_style_edit,
            self._voice_notes_edit,
            self._relationships_edit,
        ):
            widget.setMinimumHeight(62)
            widget.setMaximumHeight(82)
            widget.textChanged.connect(self._emit_profile_changed)

        self._canonical_name_label = QLabel("Canonical Name", self)
        self._aliases_label = QLabel("Aliases", self)
        self._gender_hint_label = QLabel("Gender Hint", self)
        self._age_band_label = QLabel("Age Band", self)
        self._role_summary_label = QLabel("Role Summary", self)
        self._description_label = QLabel("Description", self)
        self._temperament_label = QLabel("Temperament", self)
        self._social_status_label = QLabel("Social Status", self)
        self._speaking_style_label = QLabel("Speaking Style", self)
        self._accent_label = QLabel("Accent / Dialect", self)
        self._voice_notes_label = QLabel("Voice Notes", self)
        self._relationships_label = QLabel("Relationship Hints", self)
        self._confidence_label = QLabel("Confidence", self)

        editor_layout.addRow(self._canonical_name_label, self._canonical_name_edit)
        editor_layout.addRow(self._aliases_label, self._aliases_edit)
        editor_layout.addRow(self._gender_hint_label, self._gender_hint_edit)
        editor_layout.addRow(self._age_band_label, self._age_band_edit)
        editor_layout.addRow(self._role_summary_label, self._role_summary_edit)
        editor_layout.addRow(self._description_label, self._description_edit)
        editor_layout.addRow(self._temperament_label, self._temperament_edit)
        editor_layout.addRow(self._social_status_label, self._social_status_edit)
        editor_layout.addRow(self._speaking_style_label, self._speaking_style_edit)
        editor_layout.addRow(self._accent_label, self._accent_edit)
        editor_layout.addRow(self._voice_notes_label, self._voice_notes_edit)
        editor_layout.addRow(self._relationships_label, self._relationships_edit)
        editor_layout.addRow(self._confidence_label, self._confidence_edit)
        self._editor_scroll_area.setWidget(self._editor_form_widget)
        editor_group_layout.addWidget(self._editor_scroll_area)
        self._left_splitter.addWidget(self._editor_group)

        self._evidence_group = QGroupBox("Evidence", self)
        self._evidence_group.setMinimumWidth(280)
        evidence_layout = QVBoxLayout(self._evidence_group)
        self._evidence_list = QListWidget(self)
        self._evidence_list.currentRowChanged.connect(self._show_selected_evidence)
        self._evidence_preview = QPlainTextEdit(self)
        self._evidence_preview.setReadOnly(True)
        evidence_layout.addWidget(self._evidence_list)
        evidence_layout.addWidget(self._evidence_preview)

        self._main_splitter.addWidget(self._left_splitter)
        self._main_splitter.addWidget(self._evidence_group)
        self._left_splitter.setStretchFactor(0, 2)
        self._left_splitter.setStretchFactor(1, 6)
        self._left_splitter.setSizes([240, 620])
        self._main_splitter.setStretchFactor(0, 7)
        self._main_splitter.setStretchFactor(1, 3)
        self._main_splitter.setSizes([900, 300])
        layout.addWidget(self._main_splitter, 1)

        self.set_project_active(False)
        self.set_ai_profiles([], None)
        self.set_character_state(
            profiles=[],
            notes=["Run text chunking before Character Discovery."],
            selected_profile_id=None,
            stage_status=character_discovery_service.CHARACTER_DISCOVERY_STAGE_NOT_STARTED,
            character_count=0,
            source_chunk_map={},
            can_start=False,
            can_reset=False,
        )

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Enable or disable the page based on project availability.
        @param[in]  is_active True when a project is currently open.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        self._project_active = is_active
        self._apply_control_state()

    def set_ai_profiles(
        self,
        entries: list[tuple[str, str | None]],
        selected_profile_id: str | None,
    ) -> None:
        """
        @brief      Populate the character-discovery AI profile selector.
        @param[in]  entries Ordered enabled profile label/id pairs.
        @param[in]  selected_profile_id Preferred selected profile id.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        if entries:
            for label, profile_id in entries:
                self._profile_combo.addItem(label, profile_id)
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
            self._profile_combo.addItem("(none)", None)
            self._profile_combo.setCurrentIndex(0)
        self._profile_combo.blockSignals(False)
        self._apply_control_state()

    def set_character_state(
        self,
        profiles: list[dict[str, object]],
        notes: list[str],
        selected_profile_id: str | None,
        stage_status: str,
        character_count: int,
        source_chunk_map: dict[str, str],
        can_start: bool,
        can_reset: bool,
    ) -> None:
        """
        @brief      Refresh the Characters page from controller-provided state.
        @param[in]  profiles Persisted character profile payloads.
        @param[in]  notes Operator-facing page notes.
        @param[in]  selected_profile_id Selected discovery AI profile id.
        @param[in]  stage_status Effective discovery stage token.
        @param[in]  character_count Number of discovered profiles.
        @param[in]  source_chunk_map Chunk-id to source-text map for evidence preview.
        @param[in]  can_start True when the workflow may start or continue.
        @param[in]  can_reset True when persisted character-discovery data exists.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        del character_count
        current_character_id = self._current_character_id
        self._profiles = sorted(list(profiles), key=_profile_sort_key)
        self._source_chunk_map = dict(source_chunk_map)
        self._stage_status = stage_status
        self._can_start = can_start
        self._can_reset = can_reset
        if selected_profile_id is not None:
            profile_index = self._profile_combo.findData(selected_profile_id)
            if profile_index >= 0:
                self._profile_combo.setCurrentIndex(profile_index)
        self._summary_label.setText(_build_summary_text(notes))
        self._character_list.clear()
        for profile in self._profiles:
            self._character_list.addItem(_format_profile_item(profile))
        row_to_select = 0
        if current_character_id is not None:
            for index, profile in enumerate(self._profiles):
                if str(profile.get("character_id", "")) == current_character_id:
                    row_to_select = index
                    break
        if self._profiles:
            self._character_list.setCurrentRow(row_to_select)
        else:
            self._show_selected_profile(-1)
        self._apply_control_state()

    def set_busy(self, is_busy: bool) -> None:
        """
        @brief      Disable page actions while another blocking task runs.
        @param[in]  is_busy True while the controller is running a blocking task.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        self._busy = is_busy
        self._apply_control_state()

    def current_profile_id(self) -> str | None:
        """
        @brief      Return the selected AI discovery profile id.
        @return     Selected profile identifier or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        value = self._profile_combo.currentData()
        return None if value in (None, "") else str(value)

    def _apply_control_state(self) -> None:
        selectors_enabled = self._project_active and not self._busy and self._can_start
        selected_profile = self._current_profile()
        self._profile_label.setEnabled(self._project_active)
        self._profile_combo.setEnabled(selectors_enabled)
        self._start_button.setEnabled(
            self._project_active
            and not self._busy
            and self._can_start
            and self.current_profile_id() is not None
        )
        self._reset_button.setEnabled(
            self._project_active
            and not self._busy
            and self._can_reset
        )
        self._character_list.setEnabled(self._project_active)
        self._evidence_list.setEnabled(self._project_active and selected_profile is not None)
        for widget in self._editor_widgets:
            widget.setEnabled(
                self._project_active
                and not self._busy
                and selected_profile is not None
            )

    def _show_selected_profile(self, row: int) -> None:
        if row < 0 or row >= len(self._profiles):
            self._current_character_id = None
            self._loading_profile = True
            self._canonical_name_edit.clear()
            self._aliases_edit.clear()
            self._gender_hint_edit.clear()
            self._age_band_edit.clear()
            self._role_summary_edit.clear()
            self._description_edit.clear()
            self._temperament_edit.clear()
            self._social_status_edit.clear()
            self._speaking_style_edit.clear()
            self._accent_edit.clear()
            self._voice_notes_edit.clear()
            self._relationships_edit.clear()
            self._confidence_edit.clear()
            self._evidence_list.clear()
            self._evidence_preview.clear()
            self._loading_profile = False
            self._apply_control_state()
            return
        profile = dict(self._profiles[row])
        self._current_character_id = str(profile.get("character_id", ""))
        self._loading_profile = True
        self._canonical_name_edit.setText(str(profile.get("canonical_name", "")))
        self._aliases_edit.setText(", ".join(list(profile.get("aliases", []))))
        self._gender_hint_edit.setText(str(profile.get("gender_hint", "")))
        self._age_band_edit.setText(str(profile.get("age_band", "")))
        self._role_summary_edit.setPlainText(str(profile.get("role_summary", "")))
        self._description_edit.setPlainText(str(profile.get("description", "")))
        self._temperament_edit.setPlainText(str(profile.get("temperament", "")))
        self._social_status_edit.setPlainText(str(profile.get("social_status", "")))
        self._speaking_style_edit.setPlainText(str(profile.get("speaking_style", "")))
        self._accent_edit.setText(str(profile.get("accent_or_dialect_hints", "")))
        self._voice_notes_edit.setPlainText(str(profile.get("voice_notes", "")))
        self._relationships_edit.setPlainText(
            "\n".join(list(profile.get("relationship_hints", [])))
        )
        self._confidence_edit.setText(str(profile.get("confidence", "")))
        self._evidence_list.clear()
        for evidence in list(profile.get("evidence", [])):
            self._evidence_list.addItem(
                f"{evidence.get('chunk_id', '')} | {evidence.get('reason', '')}"
            )
        if self._evidence_list.count() > 0:
            self._evidence_list.setCurrentRow(0)
        else:
            self._evidence_preview.clear()
        self._loading_profile = False
        self._apply_control_state()

    def _show_selected_evidence(self, row: int) -> None:
        profile = self._current_profile()
        if profile is None:
            self._evidence_preview.clear()
            return
        evidence_list = list(profile.get("evidence", []))
        if row < 0 or row >= len(evidence_list):
            self._evidence_preview.clear()
            return
        evidence = dict(evidence_list[row])
        source_text = self._source_chunk_map.get(
            str(evidence.get("chunk_id", "")),
            str(evidence.get("source_excerpt", "")),
        )
        self._evidence_preview.setPlainText(source_text)

    def _emit_start_discovery(self) -> None:
        profile_id = self.current_profile_id()
        if profile_id is not None:
            self.start_discovery_requested.emit(profile_id)

    def _emit_profile_changed(self) -> None:
        if self._loading_profile:
            return
        profile = self._current_profile()
        if profile is None:
            return
        self.profile_changed.emit(
            {
                "character_id": str(profile.get("character_id", "")),
                "canonical_name": self._canonical_name_edit.text().strip(),
                "aliases": [
                    item.strip()
                    for item in self._aliases_edit.text().split(",")
                    if item.strip()
                ],
                "gender_hint": self._gender_hint_edit.text().strip(),
                "age_band": self._age_band_edit.text().strip(),
                "role_summary": self._role_summary_edit.toPlainText().strip(),
                "description": self._description_edit.toPlainText().strip(),
                "temperament": self._temperament_edit.toPlainText().strip(),
                "social_status": self._social_status_edit.toPlainText().strip(),
                "speaking_style": self._speaking_style_edit.toPlainText().strip(),
                "accent_or_dialect_hints": self._accent_edit.text().strip(),
                "voice_notes": self._voice_notes_edit.toPlainText().strip(),
                "relationship_hints": [
                    item.strip()
                    for item in self._relationships_edit.toPlainText().splitlines()
                    if item.strip()
                ],
                "confidence": self._confidence_edit.text().strip(),
                "evidence": [dict(item) for item in list(profile.get("evidence", []))],
                "updated_at": profile.get("updated_at"),
            }
        )

    def _current_profile(self) -> dict[str, object] | None:
        if self._current_character_id is None:
            return None
        return next(
            (
                profile
                for profile in self._profiles
                if str(profile.get("character_id", "")) == self._current_character_id
            ),
            None,
        )

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one translated UI language to the page widgets.
        @param[in]  language Runtime UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        self._title_label.setText(
            f"<h2>{ui_state_service.translate('characters.title', language)}</h2>"
        )
        self._profile_label.setText(
            ui_state_service.translate("characters.ai_profile", language)
        )
        self._start_button.setText(
            ui_state_service.translate("characters.start", language)
        )
        self._reset_button.setText(
            ui_state_service.translate("characters.reset", language)
        )
        self._list_group.setTitle(
            ui_state_service.translate("characters.list_group", language)
        )
        self._editor_group.setTitle(
            ui_state_service.translate("characters.profile_group", language)
        )
        self._evidence_group.setTitle(
            ui_state_service.translate("characters.evidence_group", language)
        )
        self._canonical_name_label.setText(
            ui_state_service.translate("characters.canonical_name", language)
        )
        self._aliases_label.setText(
            ui_state_service.translate("characters.aliases", language)
        )
        self._gender_hint_label.setText(
            ui_state_service.translate("characters.gender_hint", language)
        )
        self._age_band_label.setText(
            ui_state_service.translate("characters.age_band", language)
        )
        self._role_summary_label.setText(
            ui_state_service.translate("characters.role_summary", language)
        )
        self._description_label.setText(
            ui_state_service.translate("characters.description", language)
        )
        self._temperament_label.setText(
            ui_state_service.translate("characters.temperament", language)
        )
        self._social_status_label.setText(
            ui_state_service.translate("characters.social_status", language)
        )
        self._speaking_style_label.setText(
            ui_state_service.translate("characters.speaking_style", language)
        )
        self._accent_label.setText(
            ui_state_service.translate("characters.accent", language)
        )
        self._voice_notes_label.setText(
            ui_state_service.translate("characters.voice_notes", language)
        )
        self._relationships_label.setText(
            ui_state_service.translate("characters.relationship_hints", language)
        )
        self._confidence_label.setText(
            ui_state_service.translate("characters.confidence", language)
        )
        if self._profile_combo.count() == 1 and self._profile_combo.currentData() is None:
            self._profile_combo.setItemText(
                0,
                ui_state_service.translate("ai_settings.none", language),
            )


# HELPER FUNCTIONS


def _profile_sort_key(profile: dict[str, object]) -> tuple[int, str]:
    evidence = list(profile.get("evidence", []))
    if not evidence:
        return 999999, str(profile.get("canonical_name", "")).casefold()
    return (
        min(int(item.get("sequence_index", 0)) for item in evidence),
        str(profile.get("canonical_name", "")).casefold(),
    )


def _format_profile_item(profile: dict[str, object]) -> str:
    role_summary = str(profile.get("role_summary", "")).strip()
    role_suffix = f" | {role_summary}" if role_summary else ""
    return f"{str(profile.get('canonical_name', ''))}{role_suffix}"


def _build_summary_text(notes: list[str]) -> str:
    if not notes:
        return ""
    return " ".join(str(item).strip() for item in notes if str(item).strip())


# END OF FILE
