#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file characters_page.py
@brief Character Discovery workflow page for AudioMancer.
@details Provides AI profile selection, guarded manual character maintenance,
         explicit edit mode, and source-evidence preview for discovered and
         manually added speaking characters.
@author Eng. Dan Dumitru Pasare
@date 2026-04-08
@version 0.5.0
"""

# IMPORTS

from copy import deepcopy

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from audiomancer.services import character_discovery_service, ui_state_service

CHARACTER_PAGE_MODE_VIEW = "view"
CHARACTER_PAGE_MODE_EDIT = "edit"
CHARACTER_PAGE_MODE_ADD = "add"


class CharactersPage(QWidget):
    """
    @brief      Display the Character Discovery workflow page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.5.0
    """

    start_discovery_requested = Signal(str)
    reset_discovery_requested = Signal()
    add_character_requested = Signal()
    edit_character_requested = Signal(str)
    save_character_requested = Signal(dict)
    delete_character_requested = Signal(str)
    selection_change_requested = Signal(object)
    regenerate_voice_definition_requested = Signal(dict)

    def __init__(self, parent=None) -> None:
        """
            @brief      Initialize the Character Discovery workflow page.
            @param[in]  parent Optional parent widget.
            @return     None.
            @exception  None
            @author     Eng. Dan Dumitru Pasare
            @date       2026-04-08
        @version    0.5.0
        """
        super().__init__(parent)
        self._project_active = False
        self._busy = False
        self._stage_status = character_discovery_service.CHARACTER_DISCOVERY_STAGE_NOT_STARTED
        self._profiles: list[dict[str, object]] = []
        self._source_chunk_map: dict[str, str] = {}
        self._current_character_id: str | None = None
        self._loading_profile = False
        self._selection_guard = False
        self._mode = CHARACTER_PAGE_MODE_VIEW
        self._dirty = False
        self._draft_profile: dict[str, object] | None = None
        self._original_profile: dict[str, object] | None = None
        self._can_start = False
        self._can_reset = False
        self._can_add = False
        self._can_edit = False
        self._can_delete = False
        self._ui_language = "en"
        self._evidence_find_text_by_editor_id: dict[int, str] = {}

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
        list_layout = QHBoxLayout(self._list_group)
        list_layout.setContentsMargins(6, 12, 6, 6)

        self._character_list = QListWidget(self)
        self._character_list.currentRowChanged.connect(self._handle_character_selection_changed)
        list_layout.addWidget(self._character_list, 1)

        button_column = QVBoxLayout()
        self._add_character_button = QPushButton("Add Character", self)
        self._add_character_button.clicked.connect(self.add_character_requested.emit)
        button_column.addWidget(self._add_character_button)
        self._edit_character_button = QPushButton("Edit Character", self)
        self._edit_character_button.clicked.connect(self._emit_edit_character)
        button_column.addWidget(self._edit_character_button)
        self._save_character_button = QPushButton("Save Character", self)
        self._save_character_button.clicked.connect(self._emit_save_character)
        button_column.addWidget(self._save_character_button)
        self._delete_character_button = QPushButton("Delete Character", self)
        self._delete_character_button.clicked.connect(self._emit_delete_character)
        button_column.addWidget(self._delete_character_button)
        button_column.addStretch(1)
        list_layout.addLayout(button_column)
        self._left_splitter.addWidget(self._list_group)

        self._editor_group = QGroupBox("Character Profile", self)
        self._editor_group.setMinimumHeight(340)
        editor_group_layout = QVBoxLayout(self._editor_group)
        editor_group_layout.setContentsMargins(6, 12, 6, 6)
        self._editor_scroll_area = QScrollArea(self._editor_group)
        self._editor_scroll_area.setWidgetResizable(True)
        self._editor_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
            widget.textChanged.connect(self._handle_editor_changed)
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
            widget.textChanged.connect(self._handle_editor_changed)

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
        self._voice_definition_group = QGroupBox("Voice Definition", self._editor_form_widget)
        voice_definition_layout = QVBoxLayout(self._voice_definition_group)
        voice_definition_form = QFormLayout()
        self._voice_persona_summary_edit = QPlainTextEdit(self)
        self._voice_timbre_and_range_edit = QPlainTextEdit(self)
        self._voice_pacing_and_rhythm_edit = QPlainTextEdit(self)
        self._voice_emotional_baseline_edit = QPlainTextEdit(self)
        self._voice_articulation_and_pronunciation_edit = QPlainTextEdit(self)
        self._voice_delivery_constraints_edit = QPlainTextEdit(self)
        self._voice_definition_prompt_edit = QPlainTextEdit(self)
        self._voice_definition_widgets = [
            self._voice_persona_summary_edit,
            self._voice_timbre_and_range_edit,
            self._voice_pacing_and_rhythm_edit,
            self._voice_emotional_baseline_edit,
            self._voice_articulation_and_pronunciation_edit,
            self._voice_delivery_constraints_edit,
            self._voice_definition_prompt_edit,
        ]
        self._editor_widgets.extend(self._voice_definition_widgets)
        for widget in self._voice_definition_widgets[:-1]:
            widget.setMinimumHeight(58)
            widget.setMaximumHeight(82)
            widget.textChanged.connect(self._handle_editor_changed)
        self._voice_definition_prompt_edit.setMinimumHeight(96)
        self._voice_definition_prompt_edit.setMaximumHeight(130)
        self._voice_definition_prompt_edit.textChanged.connect(self._handle_editor_changed)
        self._voice_persona_summary_label = QLabel("Voice Persona Summary", self)
        self._voice_timbre_and_range_label = QLabel("Timbre / Range", self)
        self._voice_pacing_and_rhythm_label = QLabel("Pacing / Rhythm", self)
        self._voice_emotional_baseline_label = QLabel("Emotional Baseline", self)
        self._voice_articulation_and_pronunciation_label = QLabel("Articulation / Pronunciation", self)
        self._voice_delivery_constraints_label = QLabel("Delivery Constraints", self)
        self._voice_definition_prompt_label = QLabel("Voice Definition Prompt", self)
        voice_definition_form.addRow(self._voice_persona_summary_label, self._voice_persona_summary_edit)
        voice_definition_form.addRow(self._voice_timbre_and_range_label, self._voice_timbre_and_range_edit)
        voice_definition_form.addRow(self._voice_pacing_and_rhythm_label, self._voice_pacing_and_rhythm_edit)
        voice_definition_form.addRow(self._voice_emotional_baseline_label, self._voice_emotional_baseline_edit)
        voice_definition_form.addRow(
            self._voice_articulation_and_pronunciation_label,
            self._voice_articulation_and_pronunciation_edit,
        )
        voice_definition_form.addRow(self._voice_delivery_constraints_label, self._voice_delivery_constraints_edit)
        voice_definition_form.addRow(self._voice_definition_prompt_label, self._voice_definition_prompt_edit)
        voice_definition_layout.addLayout(voice_definition_form)
        voice_definition_button_row = QHBoxLayout()
        self._regenerate_voice_definition_button = QPushButton("Regenerate Voice Definition", self)
        self._regenerate_voice_definition_button.clicked.connect(self._emit_regenerate_voice_definition)
        voice_definition_button_row.addWidget(self._regenerate_voice_definition_button)
        voice_definition_button_row.addStretch(1)
        voice_definition_layout.addLayout(voice_definition_button_row)
        self._voice_definition_status_label = QLabel("", self)
        self._voice_definition_status_label.setWordWrap(True)
        voice_definition_layout.addWidget(self._voice_definition_status_label)
        editor_layout.addRow(self._voice_definition_group)
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
        self._install_evidence_find_context_menu(self._evidence_preview)
        evidence_layout.addWidget(self._evidence_list)
        evidence_layout.addWidget(self._evidence_preview)

        self._main_splitter.addWidget(self._left_splitter)
        self._main_splitter.addWidget(self._evidence_group)
        self._left_splitter.setStretchFactor(0, 2)
        self._left_splitter.setStretchFactor(1, 6)
        self._left_splitter.setSizes([220, 640])
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
            stage_status=(character_discovery_service.CHARACTER_DISCOVERY_STAGE_NOT_STARTED),
            character_count=0,
            source_chunk_map={},
            can_start=False,
            can_reset=False,
            can_add=False,
            can_edit=False,
            can_save=False,
            can_delete=False,
            edit_mode=False,
            dirty=False,
        )

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Update the page active-state flag for project availability.
        @param[in]  is_active True when one project is currently loaded.
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
        @brief      Populate the AI-profile selector for character discovery.
        @param[in]  entries Ordered selector entries as `(label, profile_id)`.
        @param[in]  selected_profile_id Preferred selected profile identifier.
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
                (index for index, (_label, profile_id) in enumerate(entries) if profile_id == selected_profile_id),
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
        can_add: bool,
        can_edit: bool,
        can_save: bool,
        can_delete: bool,
        edit_mode: bool,
        dirty: bool,
    ) -> None:
        """
            @brief      Apply one complete character-discovery page state payload.
            @param[in]  profiles Persisted character profile payload list.
            @param[in]  notes Operator-facing summary and status notes.
            @param[in]  selected_profile_id Resolved AI profile identifier.
            @param[in]  stage_status Current discovery stage token.
            @param[in]  character_count Unused summary count from the state service.
            @param[in]  source_chunk_map Chunk text keyed by `chunk_id`.
            @param[in]  can_start True when discovery may start or continue.
            @param[in]  can_reset True when reset may run.
            @param[in]  can_add True when manual add may start.
            @param[in]  can_edit True when edit mode may start.
            @param[in]  can_save Unused explicit save flag from the state service.
            @param[in]  can_delete True when delete may run.
            @param[in]  edit_mode Unused edit-mode flag from the state service.
            @param[in]  dirty Unused dirty flag from the state service.
            @return     None.
            @exception  None
            @author     Eng. Dan Dumitru Pasare
            @date       2026-04-08
        @version    0.3.0
        """
        del character_count
        del can_save
        del edit_mode
        del dirty
        current_character_id = self._current_character_id
        self._profiles = sorted([_normalize_page_profile(profile) for profile in profiles], key=_profile_sort_key)
        self._source_chunk_map = dict(source_chunk_map)
        self._stage_status = stage_status
        self._can_start = can_start
        self._can_reset = can_reset
        self._can_add = can_add
        self._can_edit = can_edit
        self._can_delete = can_delete
        self._mode = CHARACTER_PAGE_MODE_VIEW
        self._dirty = False
        self._draft_profile = None
        self._original_profile = None
        if selected_profile_id is not None:
            profile_index = self._profile_combo.findData(selected_profile_id)
            if profile_index >= 0:
                self._profile_combo.setCurrentIndex(profile_index)
        self._summary_label.setText(_build_summary_text(notes))
        preferred_character_id = current_character_id
        if preferred_character_id is None and self._profiles:
            preferred_character_id = str(self._profiles[0].get("character_id", ""))
        if preferred_character_id is not None and not any(
            str(profile.get("character_id", "")) == preferred_character_id for profile in self._profiles
        ):
            preferred_character_id = None if not self._profiles else str(self._profiles[0].get("character_id", ""))
        self._refresh_character_list(preferred_character_id)
        self.apply_selected_character(preferred_character_id)
        self._apply_control_state()

    def set_busy(self, is_busy: bool) -> None:
        """
        @brief      Toggle busy-state handling for long-running operations.
        @param[in]  is_busy True while discovery work is active.
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
        @brief      Read the currently selected AI profile identifier.
        @return     The selected profile identifier or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        value = self._profile_combo.currentData()
        return None if value in (None, "") else str(value)

    def current_character_id(self) -> str | None:
        """
        @brief      Read the currently selected character identifier.
        @return     The active character identifier or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        return self._current_character_id

    def current_draft_payload(self) -> dict[str, object] | None:
        """
        @brief      Return one detached copy of the current editable draft.
        @return     Draft payload copy or `None` when no draft exists.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        if self._draft_profile is None:
            return None
        return deepcopy(self._draft_profile)

    def is_dirty(self) -> bool:
        """
        @brief      Indicate whether the current draft has unsaved changes.
        @return     `True` when the active draft differs from persisted data.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        return self._dirty

    def is_add_mode(self) -> bool:
        """
        @brief      Indicate whether the page is editing a newly added character.
        @return     `True` when the page is in add mode.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        return self._mode == CHARACTER_PAGE_MODE_ADD

    def is_edit_mode(self) -> bool:
        """
        @brief      Indicate whether the page is editing one persisted character.
        @return     `True` when the page is in edit mode.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        return self._mode == CHARACTER_PAGE_MODE_EDIT

    def begin_edit_mode(self) -> None:
        """
            @brief      Enter guarded edit mode for the selected persisted profile.
            @return     None.
            @exception  None
            @author     Eng. Dan Dumitru Pasare
            @date       2026-04-08
        @version    0.3.0
        """
        profile = self._current_profile()
        if profile is None:
            return
        self._mode = CHARACTER_PAGE_MODE_EDIT
        self._original_profile = deepcopy(profile)
        self._draft_profile = deepcopy(profile)
        self._dirty = False
        self._load_profile_into_editor(self._draft_profile)
        self._apply_control_state()

    def begin_add_mode(self, draft_profile: dict[str, object]) -> None:
        """
            @brief      Enter add mode with one temporary manual-character draft.
            @param[in]  draft_profile New manual profile draft payload.
            @return     None.
            @exception  None
            @author     Eng. Dan Dumitru Pasare
            @date       2026-04-08
        @version    0.3.0
        """
        self._mode = CHARACTER_PAGE_MODE_ADD
        self._dirty = True
        self._original_profile = None
        self._draft_profile = deepcopy(draft_profile)
        self._profiles = [
            profile
            for profile in self._profiles
            if str(profile.get("character_id", "")) != str(draft_profile.get("character_id", ""))
        ]
        self._profiles.append(deepcopy(draft_profile))
        draft_character_id = str(draft_profile.get("character_id", ""))
        self._refresh_character_list(draft_character_id)
        self.apply_selected_character(draft_character_id)
        self._apply_control_state()

    def apply_selected_character(self, character_id: str | None) -> None:
        """
            @brief      Switch the active character selection and refresh the editor.
            @param[in]  character_id Target character identifier or `None`.
            @return     None.
            @exception  None
            @author     Eng. Dan Dumitru Pasare
            @date       2026-04-08
        @version    0.3.0
        """
        if character_id is None:
            self._current_character_id = None
            self._mode = CHARACTER_PAGE_MODE_VIEW
            self._dirty = False
            self._draft_profile = None
            self._original_profile = None
            self._select_list_row(-1)
            self._clear_editor()
            self._apply_control_state()
            return
        if not any(str(profile.get("character_id", "")) == character_id for profile in self._profiles):
            character_id = None if not self._profiles else str(self._profiles[0].get("character_id", ""))
            if character_id is None:
                self.apply_selected_character(None)
                return
        self._current_character_id = character_id
        if self._mode == CHARACTER_PAGE_MODE_VIEW:
            self._dirty = False
            self._draft_profile = None
            self._original_profile = None
        self._select_list_row(_row_for_character_id(self._profiles, character_id))
        active_profile = self._active_profile()
        if active_profile is None:
            self._clear_editor()
        else:
            self._load_profile_into_editor(active_profile)
        self._apply_control_state()

    def restore_current_selection(self) -> None:
        """
        @brief      Reapply the current selection after a cancelled guard action.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        self._select_list_row(_row_for_character_id(self._profiles, self._current_character_id))

    def discard_changes(self) -> None:
        """
        @brief      Discard the active draft and restore view mode.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.3.0
        """
        current_character_id = self._current_character_id
        if self._mode == CHARACTER_PAGE_MODE_ADD and current_character_id is not None:
            self._profiles = [
                profile for profile in self._profiles if str(profile.get("character_id", "")) != current_character_id
            ]
            fallback_character_id = None if not self._profiles else str(self._profiles[0].get("character_id", ""))
            self._refresh_character_list(fallback_character_id)
            self._mode = CHARACTER_PAGE_MODE_VIEW
            self._dirty = False
            self._draft_profile = None
            self._original_profile = None
            self.apply_selected_character(fallback_character_id)
            return
        self._mode = CHARACTER_PAGE_MODE_VIEW
        self._dirty = False
        self._draft_profile = None
        self._original_profile = None
        self.apply_selected_character(current_character_id)

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply translated operator-facing text to the page widgets.
        @param[in]  language Runtime UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.3.0
        """
        self._title_label.setText(f"<h2>{ui_state_service.translate('characters.title', language)}</h2>")
        self._ui_language = language
        self._profile_label.setText(ui_state_service.translate("characters.ai_profile", language))
        self._start_button.setText(ui_state_service.translate("characters.start", language))
        self._reset_button.setText(ui_state_service.translate("characters.reset", language))
        self._add_character_button.setText(ui_state_service.translate("characters.add_character", language))
        self._edit_character_button.setText(ui_state_service.translate("characters.edit_character", language))
        self._save_character_button.setText(ui_state_service.translate("characters.save_character", language))
        self._delete_character_button.setText(ui_state_service.translate("characters.delete_character", language))
        self._list_group.setTitle(ui_state_service.translate("characters.list_group", language))
        self._editor_group.setTitle(ui_state_service.translate("characters.profile_group", language))
        self._evidence_group.setTitle(ui_state_service.translate("characters.evidence_group", language))
        self._canonical_name_label.setText(ui_state_service.translate("characters.canonical_name", language))
        self._aliases_label.setText(ui_state_service.translate("characters.aliases", language))
        self._gender_hint_label.setText(ui_state_service.translate("characters.gender_hint", language))
        self._age_band_label.setText(ui_state_service.translate("characters.age_band", language))
        self._role_summary_label.setText(ui_state_service.translate("characters.role_summary", language))
        self._description_label.setText(ui_state_service.translate("characters.description", language))
        self._temperament_label.setText(ui_state_service.translate("characters.temperament", language))
        self._social_status_label.setText(ui_state_service.translate("characters.social_status", language))
        self._speaking_style_label.setText(ui_state_service.translate("characters.speaking_style", language))
        self._accent_label.setText(ui_state_service.translate("characters.accent", language))
        self._voice_notes_label.setText(ui_state_service.translate("characters.voice_notes", language))
        self._relationships_label.setText(ui_state_service.translate("characters.relationship_hints", language))
        self._confidence_label.setText(ui_state_service.translate("characters.confidence", language))
        self._voice_definition_group.setTitle(ui_state_service.translate("characters.voice_definition_group", language))
        self._voice_persona_summary_label.setText(
            ui_state_service.translate("characters.voice_persona_summary", language)
        )
        self._voice_timbre_and_range_label.setText(
            ui_state_service.translate("characters.voice_timbre_and_range", language)
        )
        self._voice_pacing_and_rhythm_label.setText(
            ui_state_service.translate("characters.voice_pacing_and_rhythm", language)
        )
        self._voice_emotional_baseline_label.setText(
            ui_state_service.translate("characters.voice_emotional_baseline", language)
        )
        self._voice_articulation_and_pronunciation_label.setText(
            ui_state_service.translate("characters.voice_articulation_and_pronunciation", language)
        )
        self._voice_delivery_constraints_label.setText(
            ui_state_service.translate("characters.voice_delivery_constraints", language)
        )
        self._voice_definition_prompt_label.setText(
            ui_state_service.translate("characters.voice_definition_prompt", language)
        )
        self._regenerate_voice_definition_button.setText(
            ui_state_service.translate("characters.regenerate_voice_definition", language)
        )
        self._refresh_voice_definition_status_label()
        if self._profile_combo.count() == 1 and self._profile_combo.currentData() is None:
            self._profile_combo.setItemText(
                0,
                ui_state_service.translate("ai_settings.none", language),
            )

    def _install_evidence_find_context_menu(self, editor: QPlainTextEdit) -> None:
        """
        @brief      Install right-click Find actions on the evidence preview.
        @param[in]  editor Evidence preview editor receiving the context menu.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        editor.customContextMenuRequested.connect(
            lambda position, target_editor=editor: self._show_evidence_preview_menu(target_editor, position)
        )

    def _show_evidence_preview_menu(self, editor: QPlainTextEdit, position: QPoint) -> None:
        """
        @brief      Show the evidence preview context menu with Find commands.
        @param[in]  editor Evidence preview editor that opened the menu.
        @param[in]  position Local menu position inside the editor.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        menu = editor.createStandardContextMenu()
        menu.addSeparator()
        find_action = menu.addAction(ui_state_service.translate("characters.find", self._ui_language))
        find_action.triggered.connect(
            lambda _checked=False, target_editor=editor: self._prompt_evidence_find(target_editor)
        )
        find_next_action = menu.addAction(ui_state_service.translate("characters.find_next", self._ui_language))
        find_next_action.setEnabled(bool(self._evidence_find_text_by_editor_id.get(id(editor), "")))
        find_next_action.triggered.connect(
            lambda _checked=False, target_editor=editor: self._find_next_evidence_text(target_editor)
        )
        menu.exec(editor.mapToGlobal(position))

    def _prompt_evidence_find(self, editor: QPlainTextEdit) -> None:
        """
        @brief      Prompt for one search string and select the next evidence match.
        @param[in]  editor Evidence preview editor that should be searched.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        search_text, accepted = QInputDialog.getText(
            self,
            ui_state_service.translate("characters.find_title", self._ui_language),
            ui_state_service.translate("characters.find_prompt", self._ui_language),
        )
        if not accepted or not search_text:
            return
        self._evidence_find_text_by_editor_id[id(editor)] = search_text
        if self._find_evidence_text(editor, search_text):
            return
        self._show_find_not_found_message(search_text)

    def _find_next_evidence_text(self, editor: QPlainTextEdit) -> None:
        """
        @brief      Select the next match for the current evidence search text.
        @param[in]  editor Evidence preview editor that should be searched.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        search_text = self._evidence_find_text_by_editor_id.get(id(editor), "")
        if not search_text:
            self._prompt_evidence_find(editor)
            return
        if self._find_evidence_text(editor, search_text):
            return
        self._show_find_not_found_message(search_text)

    def _find_evidence_text(self, editor: QPlainTextEdit, search_text: str) -> bool:
        """
        @brief      Find the next evidence match, wrapping once from the document start.
        @param[in]  editor Evidence preview editor to search.
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
        @brief      Show one translated message for a missing evidence search term.
        @param[in]  search_text Text that was not found in the evidence preview.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        QMessageBox.information(
            self,
            ui_state_service.translate("characters.find_title", self._ui_language),
            ui_state_service.translate("characters.find_not_found", self._ui_language).format(search_text=search_text),
        )

    def _apply_control_state(self) -> None:
        """
        @brief      Recompute widget enablement from the current page state.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.4.0
        """
        ai_selector_enabled = (
            self._project_active and not self._busy and self._can_start and self._mode == CHARACTER_PAGE_MODE_VIEW
        )
        has_selected_character = self._active_profile() is not None
        editor_enabled = (
            self._project_active
            and not self._busy
            and self._mode in {CHARACTER_PAGE_MODE_ADD, CHARACTER_PAGE_MODE_EDIT}
            and has_selected_character
        )
        self._profile_label.setEnabled(self._project_active)
        self._profile_combo.setEnabled(ai_selector_enabled)
        self._start_button.setEnabled(
            self._project_active and not self._busy and self._can_start and self.current_profile_id() is not None
        )
        self._reset_button.setEnabled(self._project_active and not self._busy and self._can_reset)
        self._add_character_button.setEnabled(
            self._project_active and not self._busy and self._can_add and self._mode == CHARACTER_PAGE_MODE_VIEW
        )
        self._edit_character_button.setEnabled(
            self._project_active
            and not self._busy
            and self._can_edit
            and has_selected_character
            and self._mode == CHARACTER_PAGE_MODE_VIEW
        )
        self._save_character_button.setEnabled(
            self._project_active
            and not self._busy
            and (
                (self._mode == CHARACTER_PAGE_MODE_ADD and self._dirty)
                or (self._mode == CHARACTER_PAGE_MODE_EDIT and has_selected_character)
            )
        )
        self._delete_character_button.setEnabled(
            self._project_active
            and not self._busy
            and self._can_delete
            and has_selected_character
            and self._mode == CHARACTER_PAGE_MODE_VIEW
        )
        self._regenerate_voice_definition_button.setEnabled(editor_enabled and has_selected_character)
        self._character_list.setEnabled(self._project_active and not self._busy)
        self._evidence_list.setEnabled(self._project_active and has_selected_character)
        for widget in self._editor_widgets:
            widget.setEnabled(editor_enabled)
            if hasattr(widget, "setReadOnly"):
                widget.setReadOnly(not editor_enabled)

    def _refresh_voice_definition_status_label(self, profile: dict[str, object] | None = None) -> None:
        """
        @brief      Refresh the voice-definition status note for the currently displayed profile.
        @param[in]  profile Optional profile payload to inspect instead of the active profile.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-20
        @version    1.0.0
        """
        active_profile = _normalize_page_profile(profile or self._active_profile() or {})
        if not active_profile.get("character_id"):
            self._voice_definition_status_label.clear()
            return
        if bool(active_profile.get("voice_definition_stale", False)):
            self._voice_definition_status_label.setText(
                ui_state_service.translate(
                    "characters.voice_definition_note_stale",
                    self._ui_language,
                )
            )
            return
        self._voice_definition_status_label.setText(
            ui_state_service.translate(
                "characters.voice_definition_note_current",
                self._ui_language,
            )
        )

    def _emit_start_discovery(self) -> None:
        """
        @brief      Emit the start-discovery request for the selected AI profile.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        profile_id = self.current_profile_id()
        if profile_id is not None:
            self.start_discovery_requested.emit(profile_id)

    def _emit_edit_character(self) -> None:
        """
        @brief      Emit an edit request for the selected character.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        if self._current_character_id is not None:
            self.edit_character_requested.emit(self._current_character_id)

    def _emit_save_character(self) -> None:
        """
        @brief      Emit one save request for the active draft payload.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.2.0
        """
        if self._mode == CHARACTER_PAGE_MODE_EDIT and not self._dirty:
            self.discard_changes()
            return
        draft_payload = self.current_draft_payload()
        if draft_payload is not None:
            self.save_character_requested.emit(draft_payload)

    def _emit_delete_character(self) -> None:
        """
        @brief      Emit a delete request for the selected character.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        if self._current_character_id is not None:
            self.delete_character_requested.emit(self._current_character_id)

    def _emit_regenerate_voice_definition(self) -> None:
        """
        @brief      Emit one regenerate request for the active editable draft.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-20
        @version    1.0.0
        """
        if self._mode not in {CHARACTER_PAGE_MODE_ADD, CHARACTER_PAGE_MODE_EDIT}:
            return
        self.regenerate_voice_definition_requested.emit(self._build_profile_from_editor())

    def _handle_character_selection_changed(self, row: int) -> None:
        """
        @brief      Forward list-selection changes through the guarded controller flow.
        @param[in]  row Newly selected list row index.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.2.0
        """
        if self._selection_guard or self._loading_profile:
            return
        requested_character_id = (
            None if row < 0 or row >= len(self._profiles) else str(self._profiles[row].get("character_id", ""))
        )
        if requested_character_id == self._current_character_id:
            return
        self.selection_change_requested.emit(requested_character_id)

    def _handle_editor_changed(self) -> None:
        """
        @brief      Rebuild the active draft and dirty-state after editor changes.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.2.0
        """
        if self._loading_profile:
            return
        if self._mode not in {CHARACTER_PAGE_MODE_ADD, CHARACTER_PAGE_MODE_EDIT}:
            return
        self._draft_profile = self._build_profile_from_editor()
        if self._mode == CHARACTER_PAGE_MODE_ADD:
            self._dirty = True
        else:
            self._dirty = not _profiles_equal(
                self._draft_profile,
                self._original_profile,
            )
        current_row = _row_for_character_id(self._profiles, self._current_character_id)
        current_item = None if current_row < 0 else self._character_list.item(current_row)
        if current_item is not None and self._draft_profile is not None:
            current_item.setText(_format_profile_item(self._draft_profile))
        self._refresh_voice_definition_status_label(self._draft_profile)
        self._apply_control_state()

    def _load_profile_into_editor(self, profile: dict[str, object]) -> None:
        """
        @brief      Load one profile payload into the read-only or editable widgets.
        @param[in]  profile Character profile payload to display.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.3.0
        """
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
        self._voice_persona_summary_edit.setPlainText(str(profile.get("voice_persona_summary", "")))
        self._voice_timbre_and_range_edit.setPlainText(str(profile.get("voice_timbre_and_range", "")))
        self._voice_pacing_and_rhythm_edit.setPlainText(str(profile.get("voice_pacing_and_rhythm", "")))
        self._voice_emotional_baseline_edit.setPlainText(str(profile.get("voice_emotional_baseline", "")))
        self._voice_articulation_and_pronunciation_edit.setPlainText(
            str(profile.get("voice_articulation_and_pronunciation", ""))
        )
        self._voice_delivery_constraints_edit.setPlainText(str(profile.get("voice_delivery_constraints", "")))
        self._voice_definition_prompt_edit.setPlainText(str(profile.get("voice_definition_prompt", "")))
        self._relationships_edit.setPlainText("\n".join(list(profile.get("relationship_hints", []))))
        self._confidence_edit.setText(str(profile.get("confidence", "")))
        self._refresh_voice_definition_status_label(profile)
        self._evidence_list.clear()
        for evidence in list(profile.get("evidence", [])):
            self._evidence_list.addItem(f"{evidence.get('chunk_id', '')} | {evidence.get('reason', '')}")
        if self._evidence_list.count() > 0:
            self._evidence_list.setCurrentRow(0)
        else:
            self._evidence_preview.clear()
        self._loading_profile = False

    def _clear_editor(self) -> None:
        """
        @brief      Clear the editor and evidence widgets when no profile is active.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.2.0
        """
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
        self._voice_persona_summary_edit.clear()
        self._voice_timbre_and_range_edit.clear()
        self._voice_pacing_and_rhythm_edit.clear()
        self._voice_emotional_baseline_edit.clear()
        self._voice_articulation_and_pronunciation_edit.clear()
        self._voice_delivery_constraints_edit.clear()
        self._voice_definition_prompt_edit.clear()
        self._relationships_edit.clear()
        self._confidence_edit.clear()
        self._voice_definition_status_label.clear()
        self._evidence_list.clear()
        self._evidence_preview.clear()
        self._loading_profile = False

    def _show_selected_evidence(self, row: int) -> None:
        """
        @brief      Show the source chunk or synthetic note for one evidence row.
        @param[in]  row Selected evidence-row index.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.2.0
        """
        profile = self._active_profile()
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

    def _select_list_row(self, row: int) -> None:
        """
        @brief      Select one list row while suppressing recursive selection handling.
        @param[in]  row Target list row index.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
        self._selection_guard = True
        self._character_list.setCurrentRow(row)
        self._selection_guard = False

    def _refresh_character_list(self, preferred_character_id: str | None = None) -> None:
        """
        @brief      Rebuild the character list from the current profile collection.
        @param[in]  preferred_character_id Character identifier to select afterwards.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.2.0
        """
        self._selection_guard = True
        self._character_list.clear()
        for profile in self._profiles:
            display_profile = (
                self._draft_profile
                if (
                    self._draft_profile is not None
                    and str(profile.get("character_id", "")) == str(self._draft_profile.get("character_id", ""))
                )
                else profile
            )
            self._character_list.addItem(_format_profile_item(display_profile))
        if preferred_character_id is not None:
            self._character_list.setCurrentRow(_row_for_character_id(self._profiles, preferred_character_id))
        self._selection_guard = False

    def _build_profile_from_editor(self) -> dict[str, object]:
        """
        @brief      Normalize one editable draft payload from the UI widgets.
        @return     The normalized character profile payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.4.0
        """
        base_profile = self._active_profile() or {}
        draft_profile = {
            "character_id": str(base_profile.get("character_id", "")),
            "canonical_name": self._canonical_name_edit.text().strip(),
            "aliases": [item.strip() for item in self._aliases_edit.text().split(",") if item.strip()],
            "gender_hint": self._gender_hint_edit.text().strip(),
            "age_band": self._age_band_edit.text().strip(),
            "role_summary": self._role_summary_edit.toPlainText().strip(),
            "description": self._description_edit.toPlainText().strip(),
            "temperament": self._temperament_edit.toPlainText().strip(),
            "social_status": self._social_status_edit.toPlainText().strip(),
            "speaking_style": self._speaking_style_edit.toPlainText().strip(),
            "accent_or_dialect_hints": self._accent_edit.text().strip(),
            "voice_notes": self._voice_notes_edit.toPlainText().strip(),
            "voice_persona_summary": self._voice_persona_summary_edit.toPlainText().strip(),
            "voice_timbre_and_range": self._voice_timbre_and_range_edit.toPlainText().strip(),
            "voice_pacing_and_rhythm": self._voice_pacing_and_rhythm_edit.toPlainText().strip(),
            "voice_emotional_baseline": self._voice_emotional_baseline_edit.toPlainText().strip(),
            "voice_articulation_and_pronunciation": (
                self._voice_articulation_and_pronunciation_edit.toPlainText().strip()
            ),
            "voice_delivery_constraints": self._voice_delivery_constraints_edit.toPlainText().strip(),
            "voice_definition_prompt": self._voice_definition_prompt_edit.toPlainText().strip(),
            "voice_definition_source_signature": str(base_profile.get("voice_definition_source_signature", "")).strip(),
            "voice_definition_stale": bool(base_profile.get("voice_definition_stale", False)),
            "relationship_hints": [
                item.strip() for item in self._relationships_edit.toPlainText().splitlines() if item.strip()
            ],
            "confidence": self._confidence_edit.text().strip(),
            "evidence": [dict(item) for item in list(base_profile.get("evidence", []))],
            "updated_at": base_profile.get("updated_at"),
        }
        draft_profile["voice_definition_stale"] = _voice_definition_stale_for_draft(base_profile, draft_profile)
        return draft_profile

    def apply_regenerated_voice_definition(self, profile_payload: dict[str, object]) -> None:
        """
        @brief      Apply regenerated voice-definition fields to the active draft without leaving edit mode.
        @param[in]  profile_payload Updated draft payload with regenerated voice-definition fields.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-20
        @version    1.0.0
        """
        if self._mode not in {CHARACTER_PAGE_MODE_ADD, CHARACTER_PAGE_MODE_EDIT}:
            return
        self._draft_profile = _normalize_page_profile(profile_payload)
        self._load_profile_into_editor(self._draft_profile)
        if self._mode == CHARACTER_PAGE_MODE_ADD:
            self._dirty = True
        else:
            self._dirty = not _profiles_equal(
                self._draft_profile,
                self._original_profile,
            )
        current_row = _row_for_character_id(self._profiles, self._current_character_id)
        current_item = None if current_row < 0 else self._character_list.item(current_row)
        if current_item is not None:
            current_item.setText(_format_profile_item(self._draft_profile))
        self._apply_control_state()

    def _current_profile(self) -> dict[str, object] | None:
        """
        @brief      Resolve the persisted profile matching the current selection.
        @return     The persisted profile payload or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.1.0
        """
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

    def _active_profile(self) -> dict[str, object] | None:
        """
        @brief      Resolve the currently displayed profile, preferring the draft copy.
        @return     Active draft or persisted profile payload, or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-08
        @version    0.2.0
        """
        if (
            self._mode in {CHARACTER_PAGE_MODE_ADD, CHARACTER_PAGE_MODE_EDIT}
            and self._draft_profile is not None
            and str(self._draft_profile.get("character_id", "")) == str(self._current_character_id or "")
        ):
            return self._draft_profile
        return self._current_profile()


def _row_for_character_id(
    profiles: list[dict[str, object]],
    character_id: str | None,
) -> int:
    """
    @brief      Resolve the list row for one character identifier.
    @param[in]  profiles Ordered character profile payload list.
    @param[in]  character_id Target character identifier or `None`.
    @return     Matching row index or `-1`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    if character_id is None:
        return -1
    return next(
        (index for index, profile in enumerate(profiles) if str(profile.get("character_id", "")) == character_id),
        -1,
    )


def _profile_sort_key(profile: dict[str, object]) -> tuple[int, str]:
    """
    @brief      Build the stable list sort key for one character profile.
    @param[in]  profile Character profile payload.
    @return     Sort key based on first evidence order and canonical name.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    evidence = list(profile.get("evidence", []))
    if not evidence:
        return 999999, str(profile.get("canonical_name", "")).casefold()
    return (
        min(int(item.get("sequence_index", 0)) for item in evidence),
        str(profile.get("canonical_name", "")).casefold(),
    )


def _format_profile_item(profile: dict[str, object]) -> str:
    """
    @brief      Build one compact list label for a character profile.
    @param[in]  profile Character profile payload.
    @return     Display label for the character list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    canonical_name = str(profile.get("canonical_name", "")).strip()
    role_summary = str(profile.get("role_summary", "")).strip()
    role_suffix = f" | {role_summary}" if role_summary else ""
    return f"{canonical_name}{role_suffix}".strip()


def _build_summary_text(notes: list[str]) -> str:
    """
    @brief      Join page notes into the compact summary line text.
    @param[in]  notes Ordered note string list.
    @return     One single-line summary string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    if not notes:
        return ""
    return " ".join(str(item).strip() for item in notes if str(item).strip())


def _profiles_equal(
    left_profile: dict[str, object] | None,
    right_profile: dict[str, object] | None,
) -> bool:
    """
    @brief      Compare two profile payloads for user-edit dirty-state checks.
    @param[in]  left_profile First profile payload or `None`.
    @param[in]  right_profile Second profile payload or `None`.
    @return     `True` when all editable fields are equal.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.2.0
    """
    if left_profile is None or right_profile is None:
        return left_profile is right_profile
    comparable_keys = (
        "canonical_name",
        "aliases",
        "gender_hint",
        "age_band",
        "role_summary",
        "description",
        "temperament",
        "social_status",
        "speaking_style",
        "accent_or_dialect_hints",
        "voice_notes",
        "voice_persona_summary",
        "voice_timbre_and_range",
        "voice_pacing_and_rhythm",
        "voice_emotional_baseline",
        "voice_articulation_and_pronunciation",
        "voice_delivery_constraints",
        "voice_definition_prompt",
        "relationship_hints",
        "confidence",
        "evidence",
    )
    return {key: left_profile.get(key) for key in comparable_keys} == {
        key: right_profile.get(key) for key in comparable_keys
    }


def _normalize_page_profile(profile: dict[str, object]) -> dict[str, object]:
    """
    @brief      Apply UI-safe defaults to one character profile payload.
    @param[in]  profile Raw or partial character profile payload.
    @return     Normalized page profile payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    normalized_profile = dict(profile)
    normalized_profile.setdefault("aliases", [])
    normalized_profile.setdefault("relationship_hints", [])
    normalized_profile.setdefault("voice_persona_summary", "")
    normalized_profile.setdefault("voice_timbre_and_range", "")
    normalized_profile.setdefault("voice_pacing_and_rhythm", "")
    normalized_profile.setdefault("voice_emotional_baseline", "")
    normalized_profile.setdefault("voice_articulation_and_pronunciation", "")
    normalized_profile.setdefault("voice_delivery_constraints", "")
    normalized_profile.setdefault("voice_definition_prompt", "")
    normalized_profile.setdefault("voice_definition_source_signature", "")
    normalized_profile.setdefault("voice_definition_stale", False)
    return normalized_profile


def _voice_definition_stale_for_draft(
    base_profile: dict[str, object],
    draft_profile: dict[str, object],
) -> bool:
    """
    @brief      Determine whether the draft voice definition is stale against the edited character facts.
    @param[in]  base_profile Persisted or regenerated profile used as the draft base.
    @param[in]  draft_profile Current draft profile from the editor widgets.
    @return     `True` when the raw character facts changed without updating the voice-definition block.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    stored_signature = str(base_profile.get("voice_definition_source_signature", "")).strip()
    if not stored_signature:
        return False
    if not _voice_definition_block_equal(base_profile, draft_profile):
        return False
    current_signature = character_discovery_service.voice_definition_source_signature(draft_profile)
    return stored_signature != current_signature


def _voice_definition_block_equal(
    left_profile: dict[str, object],
    right_profile: dict[str, object],
) -> bool:
    """
    @brief      Compare the editable voice-definition block between two profile payloads.
    @param[in]  left_profile First profile payload.
    @param[in]  right_profile Second profile payload.
    @return     `True` when all voice-definition brief fields and the final prompt match.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    comparable_fields = (
        "voice_persona_summary",
        "voice_timbre_and_range",
        "voice_pacing_and_rhythm",
        "voice_emotional_baseline",
        "voice_articulation_and_pronunciation",
        "voice_delivery_constraints",
        "voice_definition_prompt",
    )
    return all(
        str(left_profile.get(field_name, "")).strip() == str(right_profile.get(field_name, "")).strip()
        for field_name in comparable_fields
    )


# END OF FILE
