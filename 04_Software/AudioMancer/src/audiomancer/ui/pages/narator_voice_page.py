#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file narator_voice_page.py
@brief Narator Voice workflow page for AudioMancer.
@details Provides project-local narrator profile inspection, profile editing,
         sample generation, explicit narrator selection, and local sample
         preview controls for the fixed Qwen3-backed narrator workflow.
"""

# IMPORTS

from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import tts_budget_service, ui_state_service

_PROFILE_PANE_INITIAL_WIDTH = 400
_PROFILE_PANE_MAXIMUM_WIDTH = 560
_PROFILE_PANE_MINIMUM_WIDTH = 220
_PROFILE_PANE_MAXIMUM_WIDTH_FRACTION = 0.55


class NaratorVoicePage(QWidget):
    """
    @brief      Display the Narator Voice workflow page.
    @exception  None
    """

    create_profile_requested = Signal(dict)
    edit_profile_requested = Signal(str)
    save_profile_requested = Signal(dict)
    delete_profile_requested = Signal(str)
    selection_change_requested = Signal(object)
    preview_toggle_requested = Signal()
    generate_sample_requested = Signal(str)
    import_sample_requested = Signal(str)
    generate_profiles_requested = Signal(str)
    select_profile_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the Narator Voice workflow page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        """
        super().__init__(parent)
        self._project_active = False
        self._busy = False
        self._preview_active = False
        self._ui_language = "en"
        self._profiles: list[dict[str, object]] = []
        self._has_ai_profiles = False
        self._can_generate_profiles = False
        self._profile_row_ids: list[str | None] = []
        self._current_profile_id: str | None = None
        self._selected_profile_id: str | None = None
        self._current_language = ""
        self._selected_voice_language = ""
        self._loading_profile = False
        self._edit_mode = False
        self._dirty = False
        self._can_edit = False
        self._can_delete = False
        self._can_generate = False
        self._can_select = False
        self._preview_available = False
        self._original_profile: dict[str, object] | None = None
        self._preview_text_character_limit = config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT
        self._preview_text_safe_word_limit = 0
        self._enforcing_preview_text_limit = False

        layout = QVBoxLayout(self)
        header_layout = QVBoxLayout()
        title_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Narrator Voice</h2>")
        title_row.addWidget(self._title_label)
        title_row.addStretch(1)
        self._ai_profile_label = QLabel("AI Profile", self)
        self._ai_profile_label.setEnabled(False)
        title_row.addWidget(self._ai_profile_label)
        self._ai_profile_combo = QComboBox(self)
        self._ai_profile_combo.addItem("(none)", None)
        title_row.addWidget(self._ai_profile_combo)
        self._generate_profiles_button = QPushButton("Generate Narrators", self)
        self._generate_profiles_button.clicked.connect(self._emit_generate_profiles)
        title_row.addWidget(self._generate_profiles_button)
        header_layout.addLayout(title_row)

        layout.addLayout(header_layout)

        self._main_splitter = QSplitter(self)
        self._main_splitter.setChildrenCollapsible(False)

        self._profiles_group = QGroupBox("Narrator Voices", self)
        profiles_layout = QVBoxLayout(self._profiles_group)
        profiles_action_row = QHBoxLayout()
        self._select_profile_button = QPushButton("Select", self._profiles_group)
        self._select_profile_button.clicked.connect(self._emit_select_profile)
        self._import_sample_button = QPushButton("Import Sample", self._profiles_group)
        self._import_sample_button.clicked.connect(self._emit_import_sample)
        profiles_action_row.addStretch(1)
        profiles_action_row.addWidget(self._import_sample_button)
        profiles_action_row.addWidget(self._select_profile_button)
        profiles_layout.addLayout(profiles_action_row)
        self._profile_list = QListWidget(self)
        self._profile_list.currentRowChanged.connect(self._handle_profile_selection_changed)
        profiles_layout.addWidget(self._profile_list, 1)
        self._main_splitter.addWidget(self._profiles_group)

        self._editor_container = QWidget(self)
        editor_container = self._editor_container
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(10)

        self._profile_name_edit = QLineEdit(self)
        self._profile_name_edit.textChanged.connect(self._handle_editor_changed)
        self._profile_name_edit.hide()

        self._designer_group = QGroupBox("Voice Designer Prompt", self)
        designer_layout = QVBoxLayout(self._designer_group)
        self._designer_prompt = QPlainTextEdit(self)
        self._designer_prompt.setMinimumHeight(112)
        self._designer_prompt.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._designer_prompt.textChanged.connect(self._handle_editor_changed)
        designer_layout.addWidget(self._designer_prompt, 1)
        editor_layout.addWidget(self._designer_group, 1)

        self._preview_group = QGroupBox("Preview Text", self)
        preview_layout = QVBoxLayout(self._preview_group)
        self._preview_text_edit = QPlainTextEdit(self)
        self._preview_text_edit.setMinimumHeight(112)
        self._preview_text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._preview_text_edit.textChanged.connect(self._handle_preview_text_changed)
        preview_layout.addWidget(self._preview_text_edit, 1)
        self._preview_budget_label = QLabel("Preview budget: 0/0 safe budget units", self)
        preview_layout.addWidget(self._preview_budget_label)
        actions_row = QHBoxLayout()
        self._create_profile_button = QPushButton("Create", self)
        self._create_profile_button.clicked.connect(self._emit_create_profile)
        self._edit_profile_button = QPushButton("Edit", self)
        self._edit_profile_button.clicked.connect(self._emit_edit_profile)
        self._save_profile_button = QPushButton("Save", self)
        self._save_profile_button.clicked.connect(self._emit_save_profile)
        self._delete_profile_button = QPushButton("Delete", self)
        self._delete_profile_button.clicked.connect(self._emit_delete_profile)
        self._generate_sample_button = QPushButton("Generate Sample", self)
        self._generate_sample_button.clicked.connect(self._emit_generate_sample)
        self._preview_toggle_button = QPushButton("Preview", self)
        self._preview_toggle_button.clicked.connect(self.preview_toggle_requested.emit)
        actions_row.addWidget(self._create_profile_button)
        actions_row.addWidget(self._edit_profile_button)
        actions_row.addWidget(self._save_profile_button)
        actions_row.addWidget(self._delete_profile_button)
        actions_row.addWidget(self._generate_sample_button)
        actions_row.addWidget(self._preview_toggle_button)
        actions_row.addStretch(1)
        preview_layout.addLayout(actions_row)
        editor_layout.addWidget(self._preview_group, 1)

        self._main_splitter.addWidget(editor_container)
        self._main_splitter.setStretchFactor(0, 12)
        self._main_splitter.setStretchFactor(1, 48)
        self._profiles_group.setMaximumWidth(_PROFILE_PANE_MAXIMUM_WIDTH)
        self._main_splitter.setSizes([_PROFILE_PANE_INITIAL_WIDTH, 960])
        layout.addWidget(self._main_splitter, 1)
        self._apply_main_splitter_minimums()

        self._operation_status_text = ""

        self.set_project_active(False)

    def operation_status_text(self) -> str:
        """
        @brief      Return the operator status text for this page's operation.
        @return     Status text as last composed from persisted operation state.
        @exception  None
        """
        return self._operation_status_text

    def resizeEvent(self, event) -> None:  # noqa: N802
        """
        @brief      Keep Narator Voice main splitter panes from shrinking below one third of the content width.
        @param[in]  event Qt resize event.
        @return     None.
        @exception  None
        """
        super().resizeEvent(event)
        self._apply_main_splitter_minimums()

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Update the page active-state flag for project availability.
        @param[in]  is_active True when one project is currently loaded.
        @return     None.
        @exception  None
        """
        self._project_active = is_active
        self._apply_control_state()

    def set_busy(self, is_busy: bool) -> None:
        """
        @brief      Toggle busy-state handling while generation work is active.
        @param[in]  is_busy True while the controller is running a blocking task.
        @return     None.
        @exception  None
        """
        self._busy = is_busy
        self._apply_control_state()

    def set_preview_active(self, is_active: bool) -> None:
        """
        @brief      Toggle preview-active state and button labeling.
        @param[in]  is_active True while preview playback is active.
        @return     None.
        @exception  None
        """
        self._preview_active = is_active
        self._apply_control_state()

    def set_narator_voice_state(
        self,
        profiles: list[dict[str, object]],
        notes: list[str],
        current_profile_id: str | None,
        selected_profile_id: str | None,
        effective_language: str,
        selected_voice_language: str,
        profile_name: str,
        prompt_text: str,
        preview_text: str,
        is_editable: bool,
        can_edit: bool,
        can_delete: bool,
        can_generate: bool,
        can_select: bool,
        preview_available: bool,
        status_lines: list[str],
        preview_text_character_limit: int = config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT,
        preview_text_safe_word_limit: int = 0,
    ) -> None:
        """
        @brief      Apply one complete narrator-definition page state payload.
        @param[in]  profiles Narrator-profile payload list.
        @param[in]  notes Operator-facing page notes.
        @param[in]  current_profile_id Currently inspected narrator-profile identifier.
        @param[in]  selected_profile_id Explicitly selected narrator-profile identifier.
        @param[in]  effective_language Effective project narration language.
        @param[in]  selected_voice_language Current selected audiobook voice language code.
        @param[in]  profile_name Display name shown in the editor.
        @param[in]  prompt_text Narrator-definition prompt text.
        @param[in]  preview_text Stored preview text for the inspected profile.
        @param[in]  is_editable True when the inspected profile may be edited.
        @param[in]  can_edit True when edit mode may start.
        @param[in]  can_delete True when delete may run.
        @param[in]  can_generate True when sample generation may start.
        @param[in]  can_select True when the current profile may become the selected narator_voice.
        @param[in]  preview_available True when one stored preview sample may play.
        @param[in]  status_lines Bottom status-window lines.
        @param[in]  preview_text_character_limit Maximum preview text length in characters.
        @param[in]  preview_text_safe_word_limit Safe preview text word limit from the active TTS model budget.
        @return     None.
        @exception  None
        """
        _ = notes
        self._profiles = [deepcopy(profile) for profile in profiles]
        self._current_profile_id = current_profile_id
        self._selected_profile_id = selected_profile_id
        self._current_language = effective_language
        self._selected_voice_language = selected_voice_language
        self._can_edit = can_edit and is_editable
        self._can_delete = can_delete
        self._can_generate = can_generate
        self._can_select = can_select
        self._preview_available = preview_available
        self._preview_text_character_limit = _positive_character_limit(preview_text_character_limit)
        self._preview_text_safe_word_limit = max(0, int(preview_text_safe_word_limit))
        self._dirty = False
        self._edit_mode = False
        self._original_profile = None
        self._refresh_profile_list(current_profile_id)
        self._load_profile_into_editor(_display_profile_name(profile_name), prompt_text, preview_text)
        self._operation_status_text = "\n".join(line for line in status_lines if str(line).strip())
        self._apply_control_state()

    def set_ai_profiles(
        self,
        entries: list[tuple[str, str | None]],
        selected_profile_id: str | None,
        can_generate_profiles: bool,
    ) -> None:
        """
        @brief      Populate the narrator-profile generation AI selector.
        @param[in]  entries Ordered profile label/id entries for the selector.
        @param[in]  selected_profile_id Profile id that should be selected.
        @param[in]  can_generate_profiles True when the active project has usable source text.
        @return     None.
        @exception  None
        """
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
            self._ai_profile_combo.addItem(ui_state_service.translate("ai_settings.none", self._ui_language), None)
            self._ai_profile_combo.setCurrentIndex(0)
        self._ai_profile_combo.blockSignals(False)
        self._has_ai_profiles = bool(entries)
        self._can_generate_profiles = bool(can_generate_profiles)
        self._apply_control_state()

    def begin_edit_mode(self) -> None:
        """
        @brief      Enter explicit edit mode for the currently inspected profile.
        @return     None.
        @exception  None
        """
        if not self._can_edit:
            return
        self._edit_mode = True
        self._dirty = False
        self._original_profile = self.current_editor_payload()
        self._apply_control_state()

    def current_profile_id(self) -> str | None:
        """
        @brief      Read the currently selected narrator-profile identifier.
        @return     The selected narrator-profile identifier or `None`.
        @exception  None
        """
        return self._current_profile_id

    def current_voice_language(self) -> str:
        """
        @brief      Read the currently selected audiobook voice language code.
        @return     The selected audiobook voice language code.
        @exception  None
        """
        return self._selected_voice_language

    def current_ai_profile_id(self) -> str | None:
        """
        @brief      Return the selected AI profile identifier for narrator profile generation.
        @return     Selected AI profile id or `None`.
        @exception  None
        """
        value = self._ai_profile_combo.currentData()
        return None if value in (None, "") else str(value)

    def current_editor_payload(self) -> dict[str, object]:
        """
        @brief      Build one narrator-profile payload from the current editor values.
        @return     Narrator-profile payload derived from the editor widgets.
        @exception  None
        """
        current_profile = self._current_profile() or {}
        profile_kind = str(current_profile.get("profile_kind", "custom"))
        editable = bool(current_profile.get("editable", profile_kind == "custom"))
        return {
            "profile_id": str(current_profile.get("profile_id", self._current_profile_id or "")).strip(),
            "display_name": self._profile_name_edit.text().strip(),
            "language": str(current_profile.get("language", self._current_language)).strip() or self._current_language,
            "prompt_text": self._designer_prompt.toPlainText().strip(),
            "preview_text": self._preview_text_edit.toPlainText().strip(),
            "speaker_id": current_profile.get("speaker_id"),
            "source_model_id": current_profile.get("source_model_id"),
            "profile_kind": profile_kind,
            "profile_origin": str(current_profile.get("profile_origin", "")),
            "provider_family": str(current_profile.get("provider_family", "")),
            "editable": editable,
            "is_selected": bool(current_profile.get("is_selected", False)),
        }

    def is_edit_mode(self) -> bool:
        """
        @brief      Indicate whether the page is in explicit profile edit mode.
        @return     `True` when the editor is unlocked.
        @exception  None
        """
        return self._edit_mode

    def is_dirty(self) -> bool:
        """
        @brief      Indicate whether the editable profile has unsaved changes.
        @return     `True` when the active editor state differs from the saved profile.
        @exception  None
        """
        return self._dirty

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the Narator Voice page labels.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        """
        self._ui_language = language
        self._title_label.setText(f"<h2>{ui_state_service.translate('narator_voice.title', language)}</h2>")
        self._profiles_group.setTitle(ui_state_service.translate("narator_voice.profiles_group", language))
        self._designer_group.setTitle(ui_state_service.translate("narator_voice.designer_group", language))
        self._preview_group.setTitle(ui_state_service.translate("narator_voice.preview_group", language))
        self._select_profile_button.setText(ui_state_service.translate("narator_voice.select_profile", language))
        self._import_sample_button.setText(ui_state_service.translate("narator_voice.import_sample", language))
        self._ai_profile_label.setText(ui_state_service.translate("narator_voice.ai_profile", language))
        self._generate_profiles_button.setText(ui_state_service.translate("narator_voice.generate_profiles", language))
        self._create_profile_button.setText(ui_state_service.translate("narator_voice.create_profile", language))
        self._edit_profile_button.setText(ui_state_service.translate("narator_voice.edit_profile", language))
        self._save_profile_button.setText(ui_state_service.translate("narator_voice.save_profile", language))
        self._delete_profile_button.setText(ui_state_service.translate("narator_voice.delete_profile", language))
        self._generate_sample_button.setText(ui_state_service.translate("narator_voice.generate_sample", language))
        self._preview_toggle_button.setText(ui_state_service.translate(self._preview_label_key(), language))
        if not self._has_ai_profiles:
            self._ai_profile_combo.setItemText(0, ui_state_service.translate("ai_settings.none", language))
        self._refresh_profile_list(self._current_profile_id)
        self._update_preview_budget_label()

    def _apply_control_state(self) -> None:
        """
        @brief      Apply the control state.
        @return     None.
        """
        list_enabled = self._project_active and not self._busy and not self._preview_active and not self._edit_mode
        editor_enabled = self._project_active and not self._busy and not self._preview_active and self._edit_mode
        self._profile_list.setEnabled(list_enabled)
        ai_selector_enabled = (
            self._project_active and not self._busy and not self._preview_active and self._has_ai_profiles
        )
        self._ai_profile_label.setEnabled(ai_selector_enabled)
        self._ai_profile_combo.setEnabled(ai_selector_enabled)
        self._generate_profiles_button.setEnabled(
            self._project_active
            and not self._busy
            and not self._preview_active
            and not self._edit_mode
            and self._has_ai_profiles
            and self._can_generate_profiles
            and self.current_ai_profile_id() is not None
        )
        self._create_profile_button.setEnabled(list_enabled)
        self._edit_profile_button.setEnabled(
            self._project_active
            and not self._busy
            and not self._preview_active
            and self._can_edit
            and not self._edit_mode
        )
        self._save_profile_button.setEnabled(
            self._project_active and not self._busy and not self._preview_active and self._edit_mode
        )
        self._delete_profile_button.setEnabled(
            self._project_active
            and not self._busy
            and not self._preview_active
            and self._can_delete
            and not self._edit_mode
        )
        self._generate_sample_button.setEnabled(
            self._project_active
            and not self._busy
            and not self._preview_active
            and not self._edit_mode
            and self._can_generate
        )
        self._select_profile_button.setEnabled(
            self._project_active
            and not self._busy
            and not self._preview_active
            and not self._edit_mode
            and self._can_select
        )
        self._import_sample_button.setEnabled(
            self._project_active
            and not self._busy
            and not self._preview_active
            and not self._edit_mode
            and self._current_profile_id is not None
        )
        self._preview_toggle_button.setEnabled(
            self._project_active and self._preview_available and (not self._busy or self._preview_active)
        )
        self._preview_toggle_button.setText(ui_state_service.translate(self._preview_label_key(), self._ui_language))
        self._profile_name_edit.setReadOnly(not editor_enabled)
        self._designer_prompt.setReadOnly(not editor_enabled)
        self._preview_text_edit.setReadOnly(not editor_enabled)

    def _apply_main_splitter_minimums(self) -> None:
        """
        @brief      Set Narator Voice main pane minimum widths from the main splitter width.
        @return     None.
        @exception  None
        """
        required_attributes = ("_main_splitter", "_profiles_group", "_editor_container")
        if not all(hasattr(self, attribute_name) for attribute_name in required_attributes):
            return
        splitter_width = self._main_splitter.width()
        if splitter_width <= 0:
            return
        self._profiles_group.setMinimumWidth(_PROFILE_PANE_MINIMUM_WIDTH)
        maximum_profile_width = max(
            _PROFILE_PANE_MAXIMUM_WIDTH,
            int(splitter_width * _PROFILE_PANE_MAXIMUM_WIDTH_FRACTION),
        )
        self._profiles_group.setMaximumWidth(maximum_profile_width)
        self._editor_container.setMinimumWidth(splitter_width // 3)

    def _preview_label_key(self) -> str:
        """
        @brief      Resolve the preview label key.
        @return     Helper result.
        """
        return "narator_voice.stop_preview" if self._preview_active else "narator_voice.preview"

    def _refresh_profile_list(self, selected_profile_id: str | None) -> None:
        """
        @brief      Execute the refresh profile list helper.
        @param[in]  selected_profile_id Selected profile identifier.
        @return     None.
        """
        self._profile_list.blockSignals(True)
        self._profile_list.clear()
        self._profile_row_ids = []
        selected_row = -1
        for profile in self._profiles:
            profile_id = str(profile.get("profile_id", "")).strip()
            self._profile_list.addItem(_format_profile_list_item(profile, self._ui_language))
            self._profile_row_ids.append(profile_id)
            if profile_id == str(selected_profile_id or "").strip():
                selected_row = len(self._profile_row_ids) - 1
        if selected_row >= 0:
            self._profile_list.setCurrentRow(selected_row)
        self._profile_list.blockSignals(False)

    def _load_profile_into_editor(self, profile_name: str, prompt_text: str, preview_text: str) -> None:
        """
        @brief      Load the profile into editor.
        @param[in]  profile_name Value for `profile_name`.
        @param[in]  prompt_text Text value for `prompt_text`.
        @param[in]  preview_text Text value for `preview_text`.
        @return     None.
        """
        self._loading_profile = True
        self._profile_name_edit.setText(profile_name)
        self._designer_prompt.setPlainText(prompt_text)
        self._preview_text_edit.setPlainText(self._limited_preview_text(preview_text))
        self._loading_profile = False
        self._update_preview_budget_label()

    def _update_preview_budget_label(self) -> None:
        """
        @brief      Update the live preview-text word-budget label.
        @return     None.
        @exception  None
        """
        preview_budget_units = tts_budget_service.estimate_budget_units(self._preview_text_edit.toPlainText())
        safe_budget_units = max(0, int(self._preview_text_safe_word_limit))
        self._preview_budget_label.setText(
            ui_state_service.translate("narator_voice.preview_budget", self._ui_language).format(
                word_count=preview_budget_units,
                safe_word_count=safe_budget_units,
            )
        )

    def _limited_preview_text(self, preview_text: object) -> str:
        """
        @brief      Limit preview text to the configured character budget.
        @param[in]  preview_text Candidate preview text.
        @return     Preview text truncated to the configured maximum length.
        """
        return str(preview_text or "")[: self._preview_text_character_limit]

    def _current_profile(self) -> dict[str, object] | None:
        """
        @brief      Return the current profile.
        @return     Resolved helper result.
        """
        return next(
            (
                profile
                for profile in self._profiles
                if str(profile.get("profile_id", "")).strip() == str(self._current_profile_id or "").strip()
            ),
            None,
        )

    def _handle_profile_selection_changed(self, row: int) -> None:
        """
        @brief      Handle the profile selection changed.
        @param[in]  row Selected row index.
        @return     None.
        """
        if self._loading_profile or row < 0:
            return
        if row >= len(self._profile_row_ids):
            return
        target_profile_id = str(self._profile_row_ids[row] or "").strip()
        if not target_profile_id:
            return
        if target_profile_id == str(self._current_profile_id or "").strip():
            return
        self.selection_change_requested.emit(target_profile_id)

    def _handle_editor_changed(self) -> None:
        """
        @brief      Handle the editor changed.
        @return     None.
        """
        if self._loading_profile or not self._edit_mode:
            return
        self._dirty = self.current_editor_payload() != (self._original_profile or {})
        self._apply_control_state()

    def _handle_preview_text_changed(self) -> None:
        """
        @brief      Enforce the configured preview text character limit and mark editor changes.
        @return     None.
        """
        if self._enforcing_preview_text_limit:
            return
        preview_text = self._preview_text_edit.toPlainText()
        limited_text = self._limited_preview_text(preview_text)
        if limited_text != preview_text:
            self._enforcing_preview_text_limit = True
            cursor = self._preview_text_edit.textCursor()
            cursor_position = min(cursor.position(), len(limited_text))
            self._preview_text_edit.setPlainText(limited_text)
            cursor.setPosition(cursor_position)
            self._preview_text_edit.setTextCursor(cursor)
            self._enforcing_preview_text_limit = False
        self._update_preview_budget_label()
        self._handle_editor_changed()

    def _emit_create_profile(self) -> None:
        """
        @brief      Emit the create profile.
        @return     None.
        """
        self.create_profile_requested.emit(self.current_editor_payload())

    def _emit_edit_profile(self) -> None:
        """
        @brief      Emit the edit profile.
        @return     None.
        """
        if self._current_profile_id is not None:
            self.edit_profile_requested.emit(self._current_profile_id)

    def _emit_save_profile(self) -> None:
        """
        @brief      Emit the save profile.
        @return     None.
        """
        self.save_profile_requested.emit(self.current_editor_payload())

    def _emit_delete_profile(self) -> None:
        """
        @brief      Emit the delete profile.
        @return     None.
        """
        if self._current_profile_id is not None:
            self.delete_profile_requested.emit(self._current_profile_id)

    def _emit_generate_sample(self) -> None:
        """
        @brief      Emit the generate sample.
        @return     None.
        """
        if self._current_profile_id is not None:
            self.generate_sample_requested.emit(self._current_profile_id)

    def _emit_import_sample(self) -> None:
        """
        @brief      Emit the import sample request for the inspected profile.
        @return     None.
        @exception  None
        """
        if self._current_profile_id is not None:
            self.import_sample_requested.emit(self._current_profile_id)

    def _emit_generate_profiles(self) -> None:
        """
        @brief      Emit one AI narrator-profile generation request.
        @return     None.
        @exception  None
        """
        profile_id = self.current_ai_profile_id()
        if profile_id is not None:
            self.generate_profiles_requested.emit(profile_id)

    def _emit_select_profile(self) -> None:
        """
        @brief      Emit the select profile.
        @return     None.
        """
        if self._current_profile_id is not None:
            self.select_profile_requested.emit(self._current_profile_id)


def _format_profile_list_item(profile: dict[str, object], language: str) -> str:
    """
    @brief      Format the profile list item.
    @param[in]  profile Value for `profile`.
    @param[in]  language Runtime UI language code.
    @return     Derived helper result.
    """
    display_name = _display_profile_name(str(profile.get("display_name", "")))
    if bool(profile.get("is_selected", False)):
        selected_label = ui_state_service.translate("narator_voice.list_selected", language)
        return f"{display_name} | {selected_label}"
    return display_name


def _display_profile_name(display_name: str) -> str:
    """
    @brief      Execute the display profile name helper.
    @param[in]  display_name Value for `display_name`.
    @return     Helper result.
    """
    normalized_name = str(display_name).strip()
    return normalized_name


def _positive_character_limit(value: object) -> int:
    """
    @brief      Normalize a configured character limit.
    @param[in]  value Candidate character limit.
    @return     Positive character limit or the configured default.
    """
    try:
        resolved_value = int(value)
    except (TypeError, ValueError):
        return config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT
    return resolved_value if resolved_value > 0 else config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT


# END OF FILE
