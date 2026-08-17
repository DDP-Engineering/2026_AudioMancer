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
"""

# IMPORTS

from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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
        """
        super().__init__(parent)
        self._project_active = False
        self._busy = False
        self._preview_active = False
        self._ui_language = "en"
        self._targets: list[dict[str, object]] = []
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
        title_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Character Voices</h2>")
        title_row.addWidget(self._title_label)
        title_row.addStretch(1)
        self._generate_missing_samples_button = QPushButton("Generate Character Samples", self)
        self._generate_missing_samples_button.clicked.connect(self.generate_missing_samples_requested.emit)
        title_row.addWidget(self._generate_missing_samples_button)
        layout.addLayout(title_row)

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
        self._edit_prompt_button = QPushButton("Edit", self)
        self._edit_prompt_button.clicked.connect(self._emit_edit_prompt)
        self._save_prompt_button = QPushButton("Save", self)
        self._save_prompt_button.clicked.connect(self._emit_save_prompt)
        self._generate_sample_button = QPushButton("Generate Sample", self)
        self._generate_sample_button.clicked.connect(self._emit_generate_sample)
        self._preview_toggle_button = QPushButton("Preview", self)
        self._preview_toggle_button.clicked.connect(self.preview_toggle_requested.emit)
        actions_row.addWidget(self._edit_prompt_button)
        actions_row.addWidget(self._save_prompt_button)
        actions_row.addWidget(self._import_sample_button)
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
        @brief      Keep Character Voices main splitter panes from shrinking below one third of the content width.
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
        @brief      Toggle busy-state handling while generation or sync work is active.
        @param[in]  is_busy True while one blocking controller task is active.
        @return     None.
        @exception  None
        """
        self._busy = is_busy
        self._apply_control_state()

    def set_preview_active(self, is_active: bool) -> None:
        """
        @brief      Toggle preview-active state and button labeling.
        @param[in]  is_active True while local preview playback is active.
        @return     None.
        @exception  None
        """
        self._preview_active = is_active
        self._apply_control_state()

    def set_character_voices_state(
        self,
        targets: list[dict[str, object]],
        notes: list[str],
        current_target_id: str | None,
        selected_voice_language: str,
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
        self._operation_status_text = "\n".join(line for line in status_lines if str(line).strip())
        self._apply_control_state()

    def begin_edit_mode(self) -> None:
        """
            @brief      Enter explicit prompt edit mode for the currently inspected voice target.
            @return     None.
            @exception  None
        """
        if not self._can_edit_prompt:
            return
        self._edit_mode = True
        self._dirty = False
        self._original_payload = self.current_editor_payload()
        self._apply_control_state()

    def current_target_id(self) -> str | None:
        """
            @brief      Read the currently selected character-voices target identifier.
            @return     The selected character-voices target identifier or `None`.
            @exception  None
        """
        return self._current_target_id

    def current_voice_language(self) -> str:
        """
        @brief      Read the currently selected character-voices voice language code.
        @return     The selected character-voices voice language code.
        @exception  None
        """
        return self._selected_voice_language

    def current_editor_payload(self) -> dict[str, object]:
        """
        @brief      Build one character-voices target payload from the current editor values.
        @return     Character-voices target payload derived from the editor widgets.
        @exception  None
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
        """
        return self._edit_mode

    def is_dirty(self) -> bool:
        """
        @brief      Indicate whether the editable character-voices prompt has unsaved changes.
        @return     `True` when the active editor state differs from the saved target payload.
        @exception  None
        """
        return self._dirty

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the Character Voices page labels.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        """
        self._ui_language = language
        self._title_label.setText(f"<h2>{ui_state_service.translate('character_voices.title', language)}</h2>")
        self._generate_missing_samples_button.setText(
            ui_state_service.translate("character_voices.generate_missing_samples", language)
        )
        self._targets_group.setTitle(ui_state_service.translate("character_voices.list_group", language))
        self._prompt_group.setTitle(ui_state_service.translate("character_voices.prompt_group", language))
        self._preview_group.setTitle(ui_state_service.translate("character_voices.preview_group", language))
        self._import_sample_button.setText(ui_state_service.translate("character_voices.import_sample", language))
        self._edit_prompt_button.setText(ui_state_service.translate("character_voices.edit_prompt", language))
        self._save_prompt_button.setText(ui_state_service.translate("character_voices.save_prompt", language))
        self._generate_sample_button.setText(ui_state_service.translate("character_voices.generate_sample", language))
        self._preview_toggle_button.setText(ui_state_service.translate(self._preview_label_key(), language))
        self._refresh_target_list(self._current_target_id)

    def _apply_control_state(self) -> None:
        """
        @brief      Apply the control state.
        @return     None.
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
            self._project_active and not self._busy and not self._preview_active and self._edit_mode
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
        """
        return "character_voices.stop_preview" if self._preview_active else "character_voices.preview"

    def _refresh_target_list(self, current_target_id: str | None) -> None:
        """
        @brief      Execute the refresh target list helper.
        @param[in]  current_target_id Currently selected target identifier.
        @return     None.
        """
        self._target_list.blockSignals(True)
        self._target_list.clear()
        selected_row = -1
        for index, target_payload in enumerate(self._targets):
            self._target_list.addItem(_format_target_list_item(target_payload, self._ui_language))
            if str(target_payload.get("target_id", "")).strip() == str(current_target_id or "").strip():
                selected_row = index
        if selected_row >= 0:
            self._target_list.setCurrentRow(selected_row)
        self._target_list.blockSignals(False)

    def _load_editor(self, prompt_text: str, preview_text: str) -> None:
        """
        @brief      Load the editor.
        @param[in]  prompt_text Text value for `prompt_text`.
        @param[in]  preview_text Text value for `preview_text`.
        @return     None.
        """
        self._loading_state = True
        self._prompt_edit.setPlainText(prompt_text)
        self._preview_text_edit.setPlainText(preview_text)
        self._loading_state = False

    def _current_target(self) -> dict[str, object] | None:
        """
        @brief      Return the current target.
        @return     Resolved helper result.
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
        """
        if self._loading_state or not self._edit_mode:
            return
        self._dirty = self.current_editor_payload() != (self._original_payload or {})
        self._apply_control_state()

    def _emit_import_sample(self) -> None:
        """
        @brief      Emit the import sample request.
        @return     None.
        """
        if self._current_target_id is not None:
            self.import_sample_requested.emit(self._current_target_id)

    def _emit_edit_prompt(self) -> None:
        """
        @brief      Emit the edit prompt.
        @return     None.
        """
        if self._current_target_id is not None:
            self.edit_prompt_requested.emit(self._current_target_id)

    def _emit_save_prompt(self) -> None:
        """
        @brief      Emit the save prompt.
        @return     None.
        """
        self.save_prompt_requested.emit(self.current_editor_payload())

    def _emit_generate_sample(self) -> None:
        """
        @brief      Emit the generate sample.
        @return     None.
        """
        if self._current_target_id is not None:
            self.generate_sample_requested.emit(self._current_target_id)


def _format_target_list_item(target_payload: dict[str, object], language: str) -> str:
    """
    @brief      Format the target list item.
    @param[in]  target_payload Payload for `target_payload`.
    @param[in]  language Runtime UI language code.
    @return     Derived helper result.
    """
    sample_key = (
        "character_voices.sample_present"
        if bool(target_payload.get("has_sample", False))
        else "character_voices.sample_missing"
    )
    sample_label = ui_state_service.translate(sample_key, language)
    return f"{str(target_payload.get('display_name', '')).strip()} | {sample_label}"


def _has_generatable_character_targets(targets: list[dict[str, object]]) -> bool:
    """
    @brief      Return whether a batch character-sample generation run has generatable character targets available.
    @param[in]  targets Current Character Voices target payload list.
    @return     True when at least one current character target can generate a sample.
    @exception  None
    """
    return any(
        str(target.get("target_kind", "")).strip() == "character" and bool(target.get("can_generate_sample", False))
        for target in targets
    )


# END OF FILE
