#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file character_voices_page.py
@brief Character Voices workflow page for AudioMancer.
@details Provides project-local character voice prompt inspection, explicit
         voice-language selection, per-character sample generation, and local
         sample preview controls for the Character Voices workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 1.6.2
"""

# IMPORTS

from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from audiomancer.services import ui_state_service


class CharacterVoicesPage(QWidget):
    """
    @brief      Display the Character Voices workflow page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """

    selection_change_requested = Signal(object)
    import_sample_requested = Signal(str)
    edit_prompt_requested = Signal(str)
    save_prompt_requested = Signal(dict)
    generate_sample_requested = Signal(str)
    generate_missing_samples_requested = Signal()
    preview_toggle_requested = Signal()

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the Character Voices workflow page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-09
        @version    1.1.3
        """
        super().__init__(parent)
        self._project_active = False
        self._busy = False
        self._preview_active = False
        self._ui_language = "en"
        self._targets: list[dict[str, object]] = []
        self._has_ai_profiles = False
        self._current_target_id: str | None = None
        self._selected_voice_language = ""
        self._loading_state = False
        self._edit_mode = False
        self._dirty = False
        self._can_import_sample = False
        self._can_edit_prompt = False
        self._can_generate_sample = False
        self._can_generate_missing_samples = False
        self._preview_available = False
        self._current_target_is_editable = False
        self._original_payload: dict[str, object] | None = None

        layout = QVBoxLayout(self)
        header_layout = QVBoxLayout()
        title_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Character Voices</h2>")
        title_row.addWidget(self._title_label)
        title_row.addStretch(1)
        self._ai_profile_label = QLabel("AI Profile", self)
        self._ai_profile_label.setEnabled(False)
        title_row.addWidget(self._ai_profile_label)
        self._ai_profile_combo = QComboBox(self)
        self._ai_profile_combo.addItem("(none)", None)
        title_row.addWidget(self._ai_profile_combo)
        self._generate_missing_samples_button = QPushButton("Generate Character Samples", self)
        self._generate_missing_samples_button.clicked.connect(self.generate_missing_samples_requested.emit)
        title_row.addWidget(self._generate_missing_samples_button)
        header_layout.addLayout(title_row)

        indicator_row = QHBoxLayout()
        indicator_row.setSpacing(12)
        self._original_language_group = QGroupBox("Original language", self)
        original_layout = QVBoxLayout(self._original_language_group)
        self._original_language_value_label = QLabel("Unknown", self)
        original_layout.addWidget(self._original_language_value_label)
        self._translated_language_group = QGroupBox("Translated language", self)
        translated_layout = QVBoxLayout(self._translated_language_group)
        self._translated_language_value_label = QLabel("Not translated", self)
        translated_layout.addWidget(self._translated_language_value_label)
        self._assignment_mode_group = QGroupBox("Voice assignment", self)
        assignment_layout = QVBoxLayout(self._assignment_mode_group)
        self._assignment_mode_value_label = QLabel("", self)
        assignment_layout.addWidget(self._assignment_mode_value_label)
        self._voice_language_group = QGroupBox("Voice language", self)
        voice_language_layout = QVBoxLayout(self._voice_language_group)
        self._voice_language_value_label = QLabel("", self)
        voice_language_layout.addWidget(self._voice_language_value_label)
        indicator_row.addWidget(self._original_language_group, 1)
        indicator_row.addWidget(self._translated_language_group, 1)
        indicator_row.addWidget(self._assignment_mode_group, 1)
        indicator_row.addWidget(self._voice_language_group, 1)
        header_layout.addLayout(indicator_row)
        layout.addLayout(header_layout)

        self._main_splitter = QSplitter(self)
        self._main_splitter.setChildrenCollapsible(False)

        self._targets_group = QGroupBox("Voice Targets", self)
        targets_layout = QVBoxLayout(self._targets_group)
        self._target_list = QListWidget(self)
        self._target_list.currentRowChanged.connect(self._handle_target_selection_changed)
        targets_layout.addWidget(self._target_list)
        self._main_splitter.addWidget(self._targets_group)

        self._editor_container = QWidget(self)
        editor_container = self._editor_container
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(10)

        self._prompt_group = QGroupBox("Voice Designer Prompt", self)
        prompt_layout = QVBoxLayout(self._prompt_group)
        self._prompt_edit = QPlainTextEdit(self)
        self._prompt_edit.setMinimumHeight(112)
        self._prompt_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._prompt_edit.textChanged.connect(self._handle_editor_changed)
        prompt_layout.addWidget(self._prompt_edit)
        editor_layout.addWidget(self._prompt_group, 1)

        self._preview_group = QGroupBox("Preview Text", self)
        preview_layout = QVBoxLayout(self._preview_group)
        self._preview_text_edit = QPlainTextEdit(self)
        self._preview_text_edit.setMinimumHeight(92)
        self._preview_text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._preview_text_edit.textChanged.connect(self._handle_editor_changed)
        preview_layout.addWidget(self._preview_text_edit)
        actions_row = QHBoxLayout()
        self._import_sample_button = QPushButton("Import Sample", self)
        self._import_sample_button.clicked.connect(self._emit_import_sample)
        self._edit_prompt_button = QPushButton("Edit Voice Prompt", self)
        self._edit_prompt_button.clicked.connect(self._emit_edit_prompt)
        self._save_prompt_button = QPushButton("Save Voice Prompt", self)
        self._save_prompt_button.clicked.connect(self._emit_save_prompt)
        self._generate_sample_button = QPushButton("Generate Sample", self)
        self._generate_sample_button.clicked.connect(self._emit_generate_sample)
        self._preview_toggle_button = QPushButton("Preview", self)
        self._preview_toggle_button.clicked.connect(self.preview_toggle_requested.emit)
        actions_row.addWidget(self._import_sample_button)
        actions_row.addWidget(self._edit_prompt_button)
        actions_row.addWidget(self._save_prompt_button)
        actions_row.addWidget(self._generate_sample_button)
        actions_row.addWidget(self._preview_toggle_button)
        actions_row.addStretch(1)
        preview_layout.addLayout(actions_row)
        editor_layout.addWidget(self._preview_group, 1)

        self._main_splitter.addWidget(editor_container)
        self._main_splitter.setStretchFactor(0, 18)
        self._main_splitter.setStretchFactor(1, 40)
        self._main_splitter.setSizes([360, 860])
        layout.addWidget(self._main_splitter, 1)
        self._apply_main_splitter_minimums()

        self._status_group = QWidget(self)
        status_layout = QVBoxLayout(self._status_group)
        status_layout.setContentsMargins(0, 0, 0, 0)
        self._status_edit = QPlainTextEdit(self)
        self._status_edit.setReadOnly(True)
        self._status_edit.setProperty(
            ui_state_service.CONTROL_TEXT_FONT_ROLE_PROPERTY,
            ui_state_service.CONTROL_TEXT_FONT_ROLE_VALUE,
        )
        status_layout.addWidget(self._status_edit)
        self._status_group.setFixedHeight(ui_state_service.operator_status_pane_height(self._status_edit))
        layout.addWidget(self._status_group, 0)

        self.set_project_active(False)

    def resizeEvent(self, event) -> None:  # noqa: N802
        """
        @brief      Keep Character Voices main splitter panes from shrinking below one third of the content width.
        @param[in]  event Qt resize event.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-01
        @version    0.1.0
        """
        super().resizeEvent(event)
        self._apply_main_splitter_minimums()

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Update the page active-state flag for project availability.
        @param[in]  is_active True when one project is currently loaded.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-20
        @version    1.0.0
        """
        self._project_active = is_active
        self._apply_control_state()

    def set_busy(self, is_busy: bool) -> None:
        """
        @brief      Toggle busy-state handling while generation or sync work is active.
        @param[in]  is_busy True while one blocking controller task is active.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-20
        @version    1.0.0
        """
        self._busy = is_busy
        self._apply_control_state()

    def set_preview_active(self, is_active: bool) -> None:
        """
        @brief      Toggle preview-active state and button labeling.
        @param[in]  is_active True while local preview playback is active.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-20
        @version    1.0.0
        """
        self._preview_active = is_active
        self._apply_control_state()

    def set_character_voices_state(
        self,
        targets: list[dict[str, object]],
        notes: list[str],
        current_target_id: str | None,
        selected_voice_language: str,
        language_entries: list[tuple[str, str]],
        original_language: str,
        translated_language: str,
        assignment_mode_label: str,
        target_name: str,
        target_kind_label: str,
        prompt_text: str,
        preview_text: str,
        is_editable: bool,
        can_import_sample: bool,
        can_edit_prompt: bool,
        can_generate_sample: bool,
        preview_available: bool,
        status_lines: list[str],
        missing_narrator_sample: bool,
    ) -> None:
        """
            @brief      Apply one complete Character Voices page state payload.
            @param[in]  targets Character-voices target payload list.
            @param[in]  notes Operator-facing page notes.
            @param[in]  current_target_id Currently inspected target identifier.
            @param[in]  selected_voice_language Current selected character-voices voice language code.
            @param[in]  language_entries Selectable voice-language entries as `(label, value)`.
            @param[in]  original_language Source-book original language label.
            @param[in]  translated_language Translation target label or fallback text.
            @param[in]  assignment_mode_label Operator-facing voice-assignment mode label.
            @param[in]  target_name Selected target display name.
            @param[in]  target_kind_label Selected target kind label.
            @param[in]  prompt_text Selected target prompt text.
            @param[in]  preview_text Selected target preview text.
            @param[in]  is_editable True when the selected target may be edited.
            @param[in]  can_import_sample True when the selected target may import one WAV sample.
            @param[in]  can_edit_prompt True when edit mode may start.
            @param[in]  can_generate_sample True when sample generation may start.
            @param[in]  preview_available True when one stored preview sample may play.
            @param[in]  status_lines Bottom status-window lines.
            @param[in]  missing_narrator_sample True when the selected narrator sample is missing.
            @return     None.
            @exception  None
            @author     Eng. Dan Dumitru Pasare
            @date       2026-04-20
        @version    1.6.0
        """
        _ = notes
        _ = missing_narrator_sample
        self._targets = [deepcopy(target) for target in targets]
        self._current_target_id = current_target_id
        self._selected_voice_language = selected_voice_language
        self._current_target_is_editable = is_editable
        self._can_import_sample = can_import_sample
        self._can_edit_prompt = can_edit_prompt
        self._can_generate_sample = can_generate_sample
        self._can_generate_missing_samples = _has_generatable_character_targets(self._targets)
        self._preview_available = preview_available
        self._edit_mode = False
        self._dirty = False
        self._original_payload = None
        self._refresh_target_list(current_target_id)
        self._load_editor(prompt_text, preview_text)
        self._set_language_labels(original_language, translated_language)
        self._assignment_mode_value_label.setText(assignment_mode_label)
        self._set_voice_language_label(language_entries, selected_voice_language)
        self._status_edit.setPlainText("\n".join(line for line in status_lines if str(line).strip()))
        self._apply_control_state()

    def set_ai_profiles(
        self,
        entries: list[tuple[str, str | None]],
        selected_profile_id: str | None,
    ) -> None:
        """
        @brief      Populate the Character Voices AI-profile selector.
        @param[in]  entries Ordered profile label/id entries for the selector.
        @param[in]  selected_profile_id Profile id that should be selected.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-23
        @version    0.1.0
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
        self._apply_control_state()

    def current_ai_profile_id(self) -> str | None:
        """
        @brief      Return the selected Character Voices AI profile id.
        @return     Selected AI profile id or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-23
        @version    0.1.0
        """
        value = self._ai_profile_combo.currentData()
        return None if value in (None, "") else str(value)

    def begin_edit_mode(self) -> None:
        """
            @brief      Enter explicit prompt edit mode for the currently inspected voice target.
            @return     None.
            @exception  None
            @author     Eng. Dan Dumitru Pasare
            @date       2026-04-20
        @version    1.1.1
        """
        if not self._can_edit_prompt:
            return
        self._edit_mode = True
        self._dirty = False
        self._original_payload = self.current_editor_payload()
        self._apply_control_state()

    def apply_selected_target(self, target_id: str | None) -> None:
        """
        @brief      Apply one selected character-voices target to the current editor view.
        @param[in]  target_id Selected character-voices target identifier.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-20
        @version    1.1.1
        """
        self._current_target_id = target_id
        target_payload = self._current_target()
        self._edit_mode = False
        self._dirty = False
        self._original_payload = None
        if target_payload is None:
            self._load_editor("", "")
        else:
            self._load_editor(
                str(target_payload.get("prompt_text", "") or ""),
                str(target_payload.get("preview_text", "") or ""),
            )
            self._current_target_is_editable = bool(target_payload.get("editable", False))
            self._can_import_sample = bool(target_payload.get("can_import_sample", False))
            self._can_edit_prompt = bool(target_payload.get("can_edit_prompt", False))
            self._can_generate_sample = bool(target_payload.get("can_generate_sample", False))
            self._preview_available = bool(target_payload.get("can_preview", False))
        self._apply_control_state()

    def current_target_id(self) -> str | None:
        """
            @brief      Read the currently selected character-voices target identifier.
            @return     The selected character-voices target identifier or `None`.
            @exception  None
            @author     Eng. Dan Dumitru Pasare
            @date       2026-04-20
        @version    1.1.0
        """
        return self._current_target_id

    def current_voice_language(self) -> str:
        """
        @brief      Read the currently selected character-voices voice language code.
        @return     The selected character-voices voice language code.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-20
        @version    1.3.0
        """
        return self._selected_voice_language

    def current_editor_payload(self) -> dict[str, object]:
        """
        @brief      Build one character-voices target payload from the current editor values.
        @return     Character-voices target payload derived from the editor widgets.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-20
        @version    1.1.0
        """
        current_target = self._current_target() or {}
        return {
            "target_id": str(current_target.get("target_id", self._current_target_id or "")).strip(),
            "target_kind": str(current_target.get("target_kind", "")).strip(),
            "display_name": str(current_target.get("display_name", "")).strip(),
            "prompt_text": self._prompt_edit.toPlainText().strip(),
            "preview_text": self._preview_text_edit.toPlainText().strip(),
            "default_prompt_text": current_target.get("default_prompt_text"),
            "editable": bool(current_target.get("editable", False)),
            "voice_language": self.current_voice_language(),
        }

    def is_edit_mode(self) -> bool:
        """
        @brief      Indicate whether the page is in explicit prompt edit mode.
        @return     `True` when the prompt editor is unlocked.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-20
        @version    1.0.0
        """
        return self._edit_mode

    def is_dirty(self) -> bool:
        """
        @brief      Indicate whether the editable character-voices prompt has unsaved changes.
        @return     `True` when the active editor state differs from the saved target payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-20
        @version    1.0.0
        """
        return self._dirty

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the Character Voices page labels.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-09
        @version    1.1.1
        """
        self._ui_language = language
        self._title_label.setText(f"<h2>{ui_state_service.translate('character_voices.title', language)}</h2>")
        self._ai_profile_label.setText(ui_state_service.translate("character_voices.ai_profile", language))
        self._generate_missing_samples_button.setText(
            ui_state_service.translate("character_voices.generate_missing_samples", language)
        )
        self._targets_group.setTitle(ui_state_service.translate("character_voices.list_group", language))
        self._prompt_group.setTitle(ui_state_service.translate("character_voices.prompt_group", language))
        self._preview_group.setTitle(ui_state_service.translate("character_voices.preview_group", language))
        self._original_language_group.setTitle(self._language_indicator_title("character_voices.original_language"))
        self._translated_language_group.setTitle(self._language_indicator_title("character_voices.translated_language"))
        self._assignment_mode_group.setTitle(ui_state_service.translate("character_voices.assignment_mode", language))
        self._voice_language_group.setTitle(ui_state_service.translate("character_voices.voice_language", language))
        self._import_sample_button.setText(ui_state_service.translate("character_voices.import_sample", language))
        self._edit_prompt_button.setText(ui_state_service.translate("character_voices.edit_prompt", language))
        self._save_prompt_button.setText(ui_state_service.translate("character_voices.save_prompt", language))
        self._generate_sample_button.setText(ui_state_service.translate("character_voices.generate_sample", language))
        self._preview_toggle_button.setText(ui_state_service.translate(self._preview_label_key(), language))
        if not self._has_ai_profiles:
            self._ai_profile_combo.setItemText(0, ui_state_service.translate("ai_settings.none", language))
        self._set_language_labels(self._current_original_language_text(), self._current_translated_language_text())

    def _apply_control_state(self) -> None:
        """
        @brief      Apply the control state.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.4.1
        """
        list_enabled = self._project_active and not self._busy and not self._preview_active and not self._edit_mode
        editor_enabled = (
            self._project_active
            and not self._busy
            and not self._preview_active
            and self._edit_mode
            and self._current_target_is_editable
        )
        self._target_list.setEnabled(list_enabled)
        ai_selector_enabled = (
            self._project_active and not self._busy and not self._preview_active and not self._edit_mode
        )
        self._ai_profile_label.setEnabled(ai_selector_enabled and self._has_ai_profiles)
        self._ai_profile_combo.setEnabled(ai_selector_enabled and self._has_ai_profiles)
        self._import_sample_button.setEnabled(
            self._project_active
            and not self._busy
            and not self._preview_active
            and not self._edit_mode
            and self._can_import_sample
        )
        self._edit_prompt_button.setEnabled(
            self._project_active
            and not self._busy
            and not self._preview_active
            and not self._edit_mode
            and self._can_edit_prompt
        )
        self._save_prompt_button.setEnabled(
            self._project_active and not self._busy and not self._preview_active and self._edit_mode and self._dirty
        )
        self._generate_sample_button.setEnabled(
            self._project_active
            and not self._busy
            and not self._preview_active
            and not self._edit_mode
            and self._can_generate_sample
        )
        self._generate_missing_samples_button.setEnabled(
            self._project_active
            and not self._busy
            and not self._preview_active
            and not self._edit_mode
            and self._can_generate_missing_samples
        )
        self._preview_toggle_button.setEnabled(
            self._project_active and self._preview_available and (not self._busy or self._preview_active)
        )
        self._preview_toggle_button.setText(ui_state_service.translate(self._preview_label_key(), self._ui_language))
        self._prompt_edit.setReadOnly(not editor_enabled)
        self._preview_text_edit.setReadOnly(not editor_enabled)

    def _apply_main_splitter_minimums(self) -> None:
        """
        @brief      Set Character Voices main pane minimum widths from the main splitter width.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-01
        @version    0.2.0
        """
        required_attributes = ("_main_splitter", "_targets_group", "_editor_container")
        if not all(hasattr(self, attribute_name) for attribute_name in required_attributes):
            return
        splitter_width = self._main_splitter.width()
        if splitter_width <= 0:
            return
        self._targets_group.setMinimumWidth(splitter_width // 4)
        self._editor_container.setMinimumWidth(splitter_width // 3)

    def _preview_label_key(self) -> str:
        """
        @brief      Resolve the preview label key.
        @return     Helper result.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        return "character_voices.stop_preview" if self._preview_active else "character_voices.preview"

    def _refresh_target_list(self, current_target_id: str | None) -> None:
        """
        @brief      Execute the refresh target list helper.
        @param[in]  current_target_id Currently selected target identifier.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self._target_list.blockSignals(True)
        self._target_list.clear()
        selected_row = -1
        for index, target_payload in enumerate(self._targets):
            self._target_list.addItem(_format_target_list_item(target_payload))
            if str(target_payload.get("target_id", "")).strip() == str(current_target_id or "").strip():
                selected_row = index
        if selected_row >= 0:
            self._target_list.setCurrentRow(selected_row)
        self._target_list.blockSignals(False)

    def _set_voice_language_label(self, language_entries: list[tuple[str, str]], selected_voice_language: str) -> None:
        """
        @brief      Set the read-only voice-language label.
        @param[in]  language_entries Value for `language_entries`.
        @param[in]  selected_voice_language Value for `selected_voice_language`.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-26
        @version    0.2.0
        """
        display_label = str(selected_voice_language or "").strip()
        for label, value in language_entries:
            if str(value).strip() == str(selected_voice_language).strip():
                display_label = str(label).strip()
                break
        self._voice_language_value_label.setText(display_label)

    def _load_editor(self, prompt_text: str, preview_text: str) -> None:
        """
        @brief      Load the editor.
        @param[in]  prompt_text Text value for `prompt_text`.
        @param[in]  preview_text Text value for `preview_text`.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self._loading_state = True
        self._prompt_edit.setPlainText(prompt_text)
        self._preview_text_edit.setPlainText(preview_text)
        self._loading_state = False

    def _set_language_labels(self, original_language: str, translated_language: str) -> None:
        """
        @brief      Set the language labels.
        @param[in]  original_language Value for `original_language`.
        @param[in]  translated_language Value for `translated_language`.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self._original_language_value_label.setText(original_language)
        self._translated_language_value_label.setText(translated_language)

    def _current_original_language_text(self) -> str:
        """
        @brief      Return the current original language text.
        @return     Resolved helper result.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        return self._original_language_value_label.text().strip()

    def _current_translated_language_text(self) -> str:
        """
        @brief      Return the current translated language text.
        @return     Resolved helper result.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        return self._translated_language_value_label.text().strip()

    def _language_indicator_title(self, translation_key: str) -> str:
        """
        @brief      Build the boxed language-indicator title from one translated label template.
        @param[in]  translation_key Translation key for the formatted language label.
        @return     Group-box title without the trailing value placeholder.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        translated_label = ui_state_service.translate(translation_key, self._ui_language)
        title = translated_label.split("{language_label}", maxsplit=1)[0]
        return title.rstrip(": ").strip()

    def _current_target(self) -> dict[str, object] | None:
        """
        @brief      Return the current target.
        @return     Resolved helper result.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        return next(
            (
                target_payload
                for target_payload in self._targets
                if str(target_payload.get("target_id", "")).strip() == str(self._current_target_id or "").strip()
            ),
            None,
        )

    def _handle_target_selection_changed(self, row: int) -> None:
        """
        @brief      Handle the target selection changed.
        @param[in]  row Selected row index.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        if self._loading_state or row < 0 or row >= len(self._targets):
            return
        target_id = str(self._targets[row].get("target_id", "")).strip()
        if target_id == str(self._current_target_id or "").strip():
            return
        self.selection_change_requested.emit(target_id)

    def _handle_editor_changed(self) -> None:
        """
        @brief      Handle the editor changed.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        if self._loading_state or not self._edit_mode:
            return
        self._dirty = self.current_editor_payload() != (self._original_payload or {})
        self._apply_control_state()

    def _emit_import_sample(self) -> None:
        """
        @brief      Emit the import sample request.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-15
        @version    0.1.0
        """
        if self._current_target_id is not None:
            self.import_sample_requested.emit(self._current_target_id)

    def _emit_edit_prompt(self) -> None:
        """
        @brief      Emit the edit prompt.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        if self._current_target_id is not None:
            self.edit_prompt_requested.emit(self._current_target_id)

    def _emit_save_prompt(self) -> None:
        """
        @brief      Emit the save prompt.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self.save_prompt_requested.emit(self.current_editor_payload())

    def _emit_generate_sample(self) -> None:
        """
        @brief      Emit the generate sample.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        if self._current_target_id is not None:
            self.generate_sample_requested.emit(self._current_target_id)


def _format_target_list_item(target_payload: dict[str, object]) -> str:
    """
    @brief      Format the target list item.
    @param[in]  target_payload Payload for `target_payload`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    sample_label = str(target_payload.get("sample_status_label", "")).strip()
    if not sample_label:
        sample_label = "Sample present" if bool(target_payload.get("has_sample", False)) else "Sample missing"
    return f"{str(target_payload.get('display_name', '')).strip()} | {sample_label}"


def _has_generatable_character_targets(targets: list[dict[str, object]]) -> bool:
    """
    @brief      Return whether a batch character-sample generation run has generatable character targets available.
    @param[in]  targets Current Character Voices target payload list.
    @return     True when at least one current character target can generate a sample.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-01
    @version    0.2.0
    """
    return any(
        str(target.get("target_kind", "")).strip() == "character" and bool(target.get("can_generate_sample", False))
        for target in targets
    )


# END OF FILE
