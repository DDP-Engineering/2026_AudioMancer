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
@author Eng. Dan Dumitru Pasare
@date 2026-04-17
@version 3.2.0
"""

# IMPORTS

from copy import deepcopy

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
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

from audiomancer.services import ui_state_service


class NaratorVoicePage(QWidget):
    """
    @brief      Display the Narator Voice workflow page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """

    create_profile_requested = Signal(dict)
    edit_profile_requested = Signal(str)
    save_profile_requested = Signal(dict)
    delete_profile_requested = Signal(str)
    selection_change_requested = Signal(object)
    preview_toggle_requested = Signal()
    generate_sample_requested = Signal(str)
    select_profile_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the Narator Voice workflow page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.1.0
        """
        super().__init__(parent)
        self._project_active = False
        self._busy = False
        self._preview_active = False
        self._ui_language = "en"
        self._profiles: list[dict[str, object]] = []
        self._current_profile_id: str | None = None
        self._selected_profile_id: str | None = None
        self._current_language = ""
        self._loading_profile = False
        self._edit_mode = False
        self._dirty = False
        self._can_edit = False
        self._can_delete = False
        self._can_generate = False
        self._can_select = False
        self._preview_available = False
        self._original_profile: dict[str, object] | None = None

        layout = QVBoxLayout(self)
        header_layout = QVBoxLayout()
        title_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Narator Voice</h2>")
        title_row.addWidget(self._title_label)
        title_row.addStretch(1)
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
        indicator_row.addWidget(self._original_language_group, 1)
        indicator_row.addWidget(self._translated_language_group, 1)
        header_layout.addLayout(indicator_row)
        layout.addLayout(header_layout)

        self._main_splitter = QSplitter(self)

        self._profiles_group = QGroupBox("Narator Voice Profiles", self)
        profiles_layout = QVBoxLayout(self._profiles_group)
        self._profile_list = QListWidget(self)
        self._profile_list.currentRowChanged.connect(self._handle_profile_selection_changed)
        profiles_layout.addWidget(self._profile_list)
        self._main_splitter.addWidget(self._profiles_group)

        editor_container = QWidget(self)
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)

        self._setup_group = QGroupBox("Profile Setup", self)
        setup_layout = QFormLayout(self._setup_group)
        self._profile_name_label = QLabel("Profile Name", self)
        self._profile_name_edit = QLineEdit(self)
        self._profile_name_edit.textChanged.connect(self._handle_editor_changed)
        profile_name_row = QHBoxLayout()
        profile_name_row.addWidget(self._profile_name_edit, 1)
        self._select_profile_button = QPushButton("Select", self)
        self._select_profile_button.clicked.connect(self._emit_select_profile)
        profile_name_row.addWidget(self._select_profile_button)
        setup_layout.addRow(self._profile_name_label, profile_name_row)
        editor_layout.addWidget(self._setup_group)

        self._designer_group = QGroupBox("Voice Designer Prompt", self)
        designer_layout = QVBoxLayout(self._designer_group)
        self._designer_prompt = QPlainTextEdit(self)
        self._designer_prompt.setMinimumHeight(220)
        self._designer_prompt.textChanged.connect(self._handle_editor_changed)
        designer_layout.addWidget(self._designer_prompt)
        editor_layout.addWidget(self._designer_group)

        self._preview_group = QGroupBox("Preview Text", self)
        preview_layout = QVBoxLayout(self._preview_group)
        self._preview_text_edit = QPlainTextEdit(self)
        self._preview_text_edit.setMinimumHeight(92)
        self._preview_text_edit.textChanged.connect(self._handle_editor_changed)
        preview_layout.addWidget(self._preview_text_edit)
        actions_row = QHBoxLayout()
        self._create_profile_button = QPushButton("Create Profile", self)
        self._create_profile_button.clicked.connect(self._emit_create_profile)
        self._edit_profile_button = QPushButton("Edit Profile", self)
        self._edit_profile_button.clicked.connect(self._emit_edit_profile)
        self._save_profile_button = QPushButton("Save Profile", self)
        self._save_profile_button.clicked.connect(self._emit_save_profile)
        self._delete_profile_button = QPushButton("Delete Profile", self)
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
        editor_layout.addWidget(self._preview_group)

        self._main_splitter.addWidget(editor_container)
        self._main_splitter.setStretchFactor(0, 18)
        self._main_splitter.setStretchFactor(1, 40)
        self._main_splitter.setSizes([360, 860])
        layout.addWidget(self._main_splitter, 1)

        self._status_group = QGroupBox("Narator Voice Status", self)
        status_layout = QVBoxLayout(self._status_group)
        self._status_edit = QPlainTextEdit(self)
        self._status_edit.setReadOnly(True)
        status_layout.addWidget(self._status_edit)
        self._status_group.setMinimumHeight(96)
        self._status_group.setMaximumHeight(120)
        layout.addWidget(self._status_group, 0)

        self.set_project_active(False)

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Update the page active-state flag for project availability.
        @param[in]  is_active True when one project is currently loaded.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.1.0
        """
        self._project_active = is_active
        self._apply_control_state()

    def set_busy(self, is_busy: bool) -> None:
        """
        @brief      Toggle busy-state handling while generation work is active.
        @param[in]  is_busy True while the controller is running a blocking task.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.0.0
        """
        self._busy = is_busy
        self._apply_control_state()

    def set_preview_active(self, is_active: bool) -> None:
        """
        @brief      Toggle preview-active state and button labeling.
        @param[in]  is_active True while preview playback is active.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.0.0
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
        original_language: str,
        translated_language: str,
        profile_name: str,
        prompt_text: str,
        preview_text: str,
        is_editable: bool,
        is_preset: bool,
        can_edit: bool,
        can_delete: bool,
        can_generate: bool,
        can_select: bool,
        preview_available: bool,
        status_lines: list[str],
    ) -> None:
        """
        @brief      Apply one complete narrator-definition page state payload.
        @param[in]  profiles Narrator-profile payload list.
        @param[in]  notes Operator-facing page notes.
        @param[in]  current_profile_id Currently inspected narrator-profile identifier.
        @param[in]  selected_profile_id Explicitly selected narrator-profile identifier.
        @param[in]  effective_language Effective project narration language.
        @param[in]  original_language Source-book original language label.
        @param[in]  translated_language Translation target label or fallback text.
        @param[in]  profile_name Display name shown in the editor.
        @param[in]  prompt_text Narrator-definition prompt text.
        @param[in]  preview_text Stored preview text for the inspected profile.
        @param[in]  is_editable True when the inspected profile may be edited.
        @param[in]  is_preset True when the inspected profile is one seeded preset.
        @param[in]  can_edit True when edit mode may start.
        @param[in]  can_delete True when delete may run.
        @param[in]  can_generate True when sample generation may start.
        @param[in]  can_select True when the current profile may become the selected narator_voice.
        @param[in]  preview_available True when one stored preview sample may play.
        @param[in]  status_lines Bottom status-window lines.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.0.0
        """
        _ = notes
        _ = is_preset
        self._profiles = [deepcopy(profile) for profile in profiles]
        self._current_profile_id = current_profile_id
        self._selected_profile_id = selected_profile_id
        self._current_language = effective_language
        self._can_edit = can_edit and is_editable
        self._can_delete = can_delete
        self._can_generate = can_generate
        self._can_select = can_select
        self._preview_available = preview_available
        self._dirty = False
        self._edit_mode = False
        self._original_profile = None
        self._refresh_profile_list(current_profile_id)
        self._load_profile_into_editor(_display_profile_name(profile_name), prompt_text, preview_text)
        self._set_language_labels(original_language, translated_language)
        self._status_edit.setPlainText("\n".join(line for line in status_lines if str(line).strip()))
        self._apply_control_state()

    def begin_edit_mode(self) -> None:
        """
        @brief      Enter explicit edit mode for the currently inspected profile.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.0.0
        """
        if not self._can_edit:
            return
        self._edit_mode = True
        self._dirty = False
        self._original_profile = self.current_editor_payload()
        self._apply_control_state()

    def apply_selected_profile(self, profile_id: str | None) -> None:
        """
        @brief      Apply one selected profile to the current editor view.
        @param[in]  profile_id Selected narrator-profile identifier.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.0.0
        """
        self._current_profile_id = profile_id
        profile = self._current_profile()
        self._dirty = False
        self._edit_mode = False
        self._original_profile = None
        if profile is None:
            self._load_profile_into_editor("", "", "")
        else:
            self._load_profile_into_editor(
                _display_profile_name(str(profile.get("display_name", ""))),
                str(profile.get("prompt_text", "")),
                str(profile.get("preview_text", "")),
            )
        self._apply_control_state()

    def current_profile_id(self) -> str | None:
        """
        @brief      Read the currently selected narrator-profile identifier.
        @return     The selected narrator-profile identifier or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.0.0
        """
        return self._current_profile_id

    def current_editor_payload(self) -> dict[str, object]:
        """
        @brief      Build one narrator-profile payload from the current editor values.
        @return     Narrator-profile payload derived from the editor widgets.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.0.0
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
            "protected": bool(current_profile.get("protected", False)),
            "is_selected": bool(current_profile.get("is_selected", False)),
            "updated_at": current_profile.get("updated_at"),
        }

    def is_edit_mode(self) -> bool:
        """
        @brief      Indicate whether the page is in explicit profile edit mode.
        @return     `True` when the editor is unlocked.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.0.0
        """
        return self._edit_mode

    def is_dirty(self) -> bool:
        """
        @brief      Indicate whether the editable profile has unsaved changes.
        @return     `True` when the active editor state differs from the saved profile.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.0.0
        """
        return self._dirty

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the Narator Voice page labels.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.1.0
        """
        self._ui_language = language
        self._title_label.setText(f"<h2>{ui_state_service.translate('narator_voice.title', language)}</h2>")
        self._profiles_group.setTitle(ui_state_service.translate("narator_voice.profiles_group", language))
        self._setup_group.setTitle(ui_state_service.translate("narator_voice.setup_group", language))
        self._profile_name_label.setText(ui_state_service.translate("narator_voice.profile_name", language))
        self._designer_group.setTitle(ui_state_service.translate("narator_voice.designer_group", language))
        self._preview_group.setTitle(ui_state_service.translate("narator_voice.preview_group", language))
        self._original_language_group.setTitle(self._language_indicator_title("narator_voice.original_language"))
        self._translated_language_group.setTitle(self._language_indicator_title("narator_voice.translated_language"))
        self._status_group.setTitle(ui_state_service.translate("narator_voice.status_group", language))
        self._select_profile_button.setText(ui_state_service.translate("narator_voice.select_profile", language))
        self._create_profile_button.setText(ui_state_service.translate("narator_voice.create_profile", language))
        self._edit_profile_button.setText(ui_state_service.translate("narator_voice.edit_profile", language))
        self._save_profile_button.setText(ui_state_service.translate("narator_voice.save_profile", language))
        self._delete_profile_button.setText(ui_state_service.translate("narator_voice.delete_profile", language))
        self._generate_sample_button.setText(ui_state_service.translate("narator_voice.generate_sample", language))
        self._preview_toggle_button.setText(ui_state_service.translate(self._preview_label_key(), language))
        self._set_language_labels(self._current_original_language_text(), self._current_translated_language_text())

    def _apply_control_state(self) -> None:
        """
        @brief      Apply the control state.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        list_enabled = self._project_active and not self._busy and not self._preview_active and not self._edit_mode
        editor_enabled = self._project_active and not self._busy and not self._preview_active and self._edit_mode
        self._profile_list.setEnabled(list_enabled)
        self._create_profile_button.setEnabled(list_enabled)
        self._edit_profile_button.setEnabled(
            self._project_active
            and not self._busy
            and not self._preview_active
            and self._can_edit
            and not self._edit_mode
        )
        self._save_profile_button.setEnabled(
            self._project_active and not self._busy and not self._preview_active and self._edit_mode and self._dirty
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
        self._preview_toggle_button.setEnabled(
            self._project_active and self._preview_available and (not self._busy or self._preview_active)
        )
        self._preview_toggle_button.setText(ui_state_service.translate(self._preview_label_key(), self._ui_language))
        self._profile_name_edit.setReadOnly(not editor_enabled)
        self._designer_prompt.setReadOnly(not editor_enabled)
        self._preview_text_edit.setReadOnly(not editor_enabled)

    def _preview_label_key(self) -> str:
        """
        @brief      Resolve the preview label key.
        @return     Helper result.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        return "narator_voice.stop_preview" if self._preview_active else "narator_voice.preview"

    def _refresh_profile_list(self, selected_profile_id: str | None) -> None:
        """
        @brief      Execute the refresh profile list helper.
        @param[in]  selected_profile_id Selected profile identifier.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self._profile_list.blockSignals(True)
        self._profile_list.clear()
        selected_row = -1
        for index, profile in enumerate(self._profiles):
            self._profile_list.addItem(_format_profile_list_item(profile))
            if str(profile.get("profile_id", "")).strip() == str(selected_profile_id or "").strip():
                selected_row = index
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
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self._loading_profile = True
        self._profile_name_edit.setText(profile_name)
        self._designer_prompt.setPlainText(prompt_text)
        self._preview_text_edit.setPlainText(preview_text)
        self._loading_profile = False

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

    def _current_profile(self) -> dict[str, object] | None:
        """
        @brief      Return the current profile.
        @return     Resolved helper result.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
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
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        if self._loading_profile or row < 0 or row >= len(self._profiles):
            return
        target_profile_id = str(self._profiles[row].get("profile_id", "")).strip()
        if target_profile_id == str(self._current_profile_id or "").strip():
            return
        self.selection_change_requested.emit(target_profile_id)

    def _handle_editor_changed(self) -> None:
        """
        @brief      Handle the editor changed.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        if self._loading_profile or not self._edit_mode:
            return
        self._dirty = self.current_editor_payload() != (self._original_profile or {})
        self._apply_control_state()

    def _emit_create_profile(self) -> None:
        """
        @brief      Emit the create profile.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self.create_profile_requested.emit(self.current_editor_payload())

    def _emit_edit_profile(self) -> None:
        """
        @brief      Emit the edit profile.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        if self._current_profile_id is not None:
            self.edit_profile_requested.emit(self._current_profile_id)

    def _emit_save_profile(self) -> None:
        """
        @brief      Emit the save profile.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self.save_profile_requested.emit(self.current_editor_payload())

    def _emit_delete_profile(self) -> None:
        """
        @brief      Emit the delete profile.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        if self._current_profile_id is not None:
            self.delete_profile_requested.emit(self._current_profile_id)

    def _emit_generate_sample(self) -> None:
        """
        @brief      Emit the generate sample.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        if self._current_profile_id is not None:
            self.generate_sample_requested.emit(self._current_profile_id)

    def _emit_select_profile(self) -> None:
        """
        @brief      Emit the select profile.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        if self._current_profile_id is not None:
            self.select_profile_requested.emit(self._current_profile_id)


def _format_profile_list_item(profile: dict[str, object]) -> str:
    """
    @brief      Format the profile list item.
    @param[in]  profile Value for `profile`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    kind_label = str(profile.get("profile_kind_label", "")).strip() or (
        "Preset" if str(profile.get("profile_kind", "")).strip() == "preset" else "Custom"
    )
    display_name = _display_profile_name(str(profile.get("display_name", "")))
    if bool(profile.get("is_selected", False)):
        selected_label = str(profile.get("selected_label", "")).strip() or "Selected"
        return f"{display_name} | {kind_label} | {selected_label}"
    return f"{display_name} | {kind_label}"


def _display_profile_name(display_name: str) -> str:
    """
    @brief      Execute the display profile name helper.
    @param[in]  display_name Value for `display_name`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized_name = str(display_name).strip()
    if normalized_name.startswith("CustomVoice | "):
        return normalized_name.removeprefix("CustomVoice | ").strip()
    return normalized_name


# END OF FILE
