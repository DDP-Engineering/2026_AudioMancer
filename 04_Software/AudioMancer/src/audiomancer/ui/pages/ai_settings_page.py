#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_settings_page.py
@brief AI settings page for AudioMancer.
@details Renders the operator-facing AI settings dialog and exposes load/build
         helpers so the main window can coordinate persistence through the
         settings service.
"""

# IMPORTS

import copy
from uuid import uuid4

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import ui_state_service

# CONSTANTS

# @brief Characters the model selector reserves room for before it starts eliding.
_MODEL_COMBO_MINIMUM_CONTENTS_LENGTH = 28

# @brief Hard width ceiling for the model selector, so one long model id cannot widen the dialog.
# @details Kept above the width the reserved character count implies, so the ceiling never
#          contradicts the control's own minimum size hint.
_MODEL_COMBO_MAX_WIDTH_PX = 420

# @brief Default LLM profile scaffold used when the operator creates a new AI profile.
_DEFAULT_PROFILE_TEMPLATE = {
    "id": "",
    "label": "",
    "backend_kind": config.LLM_BACKEND_OPTIONS[0],
    "base_url": "",
    "api_key": "",
    "model_name": "",
    "context_window": config.DEFAULT_LLM_CONTEXT_WINDOW,
    "max_output_tokens": config.DEFAULT_LLM_MAX_OUTPUT_TOKENS,
    "request_timeout_seconds": config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
    "temperature": config.DEFAULT_LLM_TEMPERATURE,
    "supports_structured_output": False,
    "enabled": True,
    "discovered_model_name": "",
    "discovered_model_names": [],
    "discovered_context_window": None,
    "discovered_context_model_name": "",
    "discovery_succeeded": False,
    "discovery_message": "",
    "user_overrode_model_name": False,
    "user_overrode_context_window": False,
}


# PUBLIC API


class AiSettingsPage(QWidget):
    """
    @brief      Display and edit AI settings for AudioMancer.
    @exception  None
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the AI settings page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        """
        super().__init__(parent)
        self._profiles: list[dict[str, object]] = []
        self._loading_profile = False
        self._editor_profile_id: str | None = None
        self._current_language = config.DEFAULT_LANGUAGE
        self._discovered_model_options: dict[str, list[tuple[str, str]]] = {}
        self._suspend_override_tracking = False

        layout = QVBoxLayout(self)
        self._title_label = QLabel("<h2>AI Settings</h2>")
        layout.addWidget(self._title_label)

        content_row = QHBoxLayout()

        profile_column = QWidget(self)
        profile_column_layout = QVBoxLayout(profile_column)
        profile_column_layout.setContentsMargins(0, 0, 0, 0)

        self._profile_list = QListWidget(self)
        self._profile_list.currentRowChanged.connect(self._load_selected_profile_into_editor)
        profile_column_layout.addWidget(self._profile_list, 1)

        profile_button_row = QHBoxLayout()
        self._add_profile_button = QPushButton("Add Profile", self)
        self._remove_profile_button = QPushButton("Remove Profile", self)
        self._add_profile_button.clicked.connect(self._add_profile)
        self._remove_profile_button.clicked.connect(self._remove_selected_profile)
        profile_button_row.addWidget(self._add_profile_button)
        profile_button_row.addWidget(self._remove_profile_button)
        profile_column_layout.addLayout(profile_button_row)

        content_row.addWidget(profile_column, 1)

        editor_container = QWidget(self)
        editor_layout = QVBoxLayout(editor_container)
        top_form_layout = QFormLayout()
        top_form_layout.setContentsMargins(0, 0, 0, 0)
        top_form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        bottom_form_layout = QFormLayout()
        bottom_form_layout.setContentsMargins(0, 0, 0, 0)

        self._label_edit = QLineEdit(self)
        profile_name_row = QHBoxLayout()
        profile_name_row.addWidget(self._label_edit, 1)

        self._enabled_checkbox = QCheckBox("Profile enabled")
        profile_name_row.addWidget(self._enabled_checkbox)

        self._backend_combo = QComboBox(self)
        self._backend_combo.addItems(config.LLM_BACKEND_OPTIONS)
        backend_row = QHBoxLayout()
        backend_row.addWidget(self._backend_combo, 1)

        self._connect_button = QPushButton("Connect", self)
        self._connect_button.setMinimumWidth(112)
        backend_row.addWidget(self._connect_button)

        self._base_url_edit = QLineEdit(self)

        self._api_key_edit = QLineEdit(self)
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText("optional-for-local-provider")

        self._model_combo = QComboBox(self)
        self._model_combo.setEditable(True)
        # Model identifiers can be very long. Left at the default policy the combo demands room
        # for its longest entry, which stretches the whole settings form on the X axis depending
        # on what the endpoint happens to serve. The popup list still shows full names.
        self._model_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._model_combo.setMinimumContentsLength(_MODEL_COMBO_MINIMUM_CONTENTS_LENGTH)
        self._model_combo.setMaximumWidth(_MODEL_COMBO_MAX_WIDTH_PX)
        # An editable combo only opens its list from the small arrow, so clicking the field
        # looks like the discovered models are missing. Clicking the text opens the list too.
        self._model_combo.lineEdit().installEventFilter(self)
        self._model_combo.addItems(
            (
                "qwen3-8b",
                "qwen2.5-7b-instruct",
                "llama-3.1-8b-instruct",
            )
        )

        self._context_window_spin = QSpinBox(self)
        self._context_window_spin.setRange(1, 1_000_000)

        self._max_output_spin = QSpinBox(self)
        self._max_output_spin.setRange(1, 1_000_000)

        self._timeout_spin = QSpinBox(self)
        self._timeout_spin.setRange(1, 65535)

        self._temperature_spin = QDoubleSpinBox(self)
        self._temperature_spin.setRange(0.0, 2.0)
        self._temperature_spin.setDecimals(2)
        self._temperature_spin.setSingleStep(0.05)

        self._supports_structured_checkbox = QCheckBox("Structured output")

        self._profile_name_label = QLabel("Profile Name", self)
        self._backend_kind_label = QLabel("Backend Kind", self)
        self._base_url_label = QLabel("Base URL", self)
        self._api_key_label = QLabel("API Key", self)
        self._model_name_label = QLabel("Model Name", self)
        self._context_window_label = QLabel("Context Window", self)
        self._max_output_label = QLabel("Max Output Tokens", self)
        self._timeout_label = QLabel("Timeout (s)", self)
        self._temperature_label = QLabel("Temperature", self)

        model_name_row = QHBoxLayout()
        model_name_row.addWidget(self._model_combo, 1)
        model_name_row.addWidget(self._supports_structured_checkbox)

        numeric_settings_grid = QGridLayout()
        numeric_settings_grid.setContentsMargins(0, 0, 0, 0)
        numeric_settings_grid.setHorizontalSpacing(12)
        numeric_settings_grid.setVerticalSpacing(6)
        numeric_settings_grid.addWidget(self._context_window_label, 0, 0)
        numeric_settings_grid.addWidget(self._context_window_spin, 0, 1)
        numeric_settings_grid.addWidget(self._max_output_label, 0, 2)
        numeric_settings_grid.addWidget(self._max_output_spin, 0, 3)
        numeric_settings_grid.addWidget(self._timeout_label, 1, 0)
        numeric_settings_grid.addWidget(self._timeout_spin, 1, 1)
        numeric_settings_grid.addWidget(self._temperature_label, 1, 2)
        numeric_settings_grid.addWidget(self._temperature_spin, 1, 3)
        numeric_settings_grid.setColumnStretch(1, 1)
        numeric_settings_grid.setColumnStretch(3, 1)

        top_form_layout.addRow(self._profile_name_label, profile_name_row)
        top_form_layout.addRow(self._backend_kind_label, backend_row)
        top_form_layout.addRow(self._base_url_label, self._base_url_edit)
        top_form_layout.addRow(self._api_key_label, self._api_key_edit)
        top_form_layout.addRow(self._model_name_label, model_name_row)
        bottom_form_layout.addRow(numeric_settings_grid)

        self._default_cleanup_combo = QComboBox(self)
        self._default_chunking_combo = QComboBox(self)
        self._default_strategy_combo = QComboBox(self)
        for strategy in config.AI_CHUNKING_STRATEGY_OPTIONS:
            self._default_strategy_combo.addItem(strategy.title(), strategy)
        self._default_context_mode_combo = QComboBox(self)
        self._reload_context_mode_combo(config.DEFAULT_LANGUAGE)

        self._default_translation_combo = QComboBox(self)
        self._default_narrator_generation_combo = QComboBox(self)
        self._default_character_combo = QComboBox(self)
        self._default_speech_blocks_combo = QComboBox(self)

        self._default_cleanup_label = QLabel("Default Cleanup Profile", self)
        self._default_chunking_label = QLabel("Default Chunking Profile", self)
        self._default_strategy_label = QLabel("Default AI Chunking Strategy", self)
        self._default_context_mode_label = QLabel("Chunking Context Mode", self)
        self._default_translation_label = QLabel("Default Translation Profile", self)
        self._default_narrator_generation_label = QLabel("Default Narrator Generation Profile", self)
        self._default_character_label = QLabel(
            "Default Character Extraction Profile",
            self,
        )
        self._default_speech_blocks_label = QLabel("Default Speech Blocks Profile", self)

        bottom_form_layout.addRow(self._default_cleanup_label, self._default_cleanup_combo)
        bottom_form_layout.addRow(self._default_chunking_label, self._default_chunking_combo)
        bottom_form_layout.addRow(self._default_strategy_label, self._default_strategy_combo)
        bottom_form_layout.addRow(self._default_context_mode_label, self._default_context_mode_combo)
        bottom_form_layout.addRow(self._default_translation_label, self._default_translation_combo)
        bottom_form_layout.addRow(self._default_narrator_generation_label, self._default_narrator_generation_combo)
        bottom_form_layout.addRow(
            self._default_character_label,
            self._default_character_combo,
        )
        bottom_form_layout.addRow(self._default_speech_blocks_label, self._default_speech_blocks_combo)
        editor_layout.addLayout(top_form_layout)
        editor_layout.addLayout(bottom_form_layout)

        content_row.addWidget(editor_container, 2)
        layout.addLayout(content_row, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._cancel_button = QPushButton("Cancel", self)
        self._save_button = QPushButton("Save", self)
        self._ok_button = QPushButton("OK", self)
        button_row.addWidget(self._cancel_button)
        button_row.addWidget(self._save_button)
        button_row.addWidget(self._ok_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self._model_combo.currentTextChanged.connect(self._on_model_name_edited)
        self._context_window_spin.valueChanged.connect(self._on_context_window_edited)

        self.load_settings(
            {
                "llm_profiles": [],
                "default_ai_cleanup_profile_id": None,
                "default_ai_chunking_profile_id": None,
                "default_ai_translation_profile_id": None,
                "default_narrator_profile_generation_profile_id": None,
                "default_speech_blocks_profile_id": None,
                "default_ai_chunking_strategy": config.DEFAULT_AI_CHUNKING_STRATEGY,
                "default_ai_chunking_context_mode": config.DEFAULT_AI_CHUNKING_CONTEXT_MODE,
                "default_character_extraction_profile_id": None,
            }
        )

    def load_settings(self, settings_payload: dict[str, object]) -> None:
        """
        @brief      Load one persisted settings payload into the page widgets.
        @param[in]  settings_payload Combined application settings payload.
        @return     None.
        @exception  None
        """
        source_profiles = settings_payload.get("llm_profiles", [])
        if not isinstance(source_profiles, list):
            source_profiles = []

        self._editor_profile_id = None
        self._discovered_model_options = {}
        self._profiles = []
        for profile in source_profiles:
            if isinstance(profile, dict):
                normalized_profile = copy.deepcopy(_DEFAULT_PROFILE_TEMPLATE)
                normalized_profile.update(profile)
                if not normalized_profile["id"]:
                    normalized_profile["id"] = self._generate_profile_id()
                self._profiles.append(normalized_profile)

        if not self._profiles:
            self._profiles = [self._create_default_profile("AI Profile 1")]

        self._reload_profile_list()
        self._reload_default_profile_combos()
        self._set_optional_combo(
            self._default_cleanup_combo,
            settings_payload.get("default_ai_cleanup_profile_id"),
        )
        self._set_optional_combo(
            self._default_chunking_combo,
            settings_payload.get("default_ai_chunking_profile_id"),
        )
        self._set_optional_combo(
            self._default_translation_combo,
            settings_payload.get("default_ai_translation_profile_id"),
        )
        self._set_optional_combo(
            self._default_narrator_generation_combo,
            settings_payload.get("default_narrator_profile_generation_profile_id"),
        )
        self._set_optional_combo(
            self._default_speech_blocks_combo,
            settings_payload.get("default_speech_blocks_profile_id"),
        )
        self._set_optional_combo(
            self._default_strategy_combo,
            settings_payload.get("default_ai_chunking_strategy"),
        )
        self._set_optional_combo(
            self._default_context_mode_combo,
            settings_payload.get("default_ai_chunking_context_mode", config.DEFAULT_AI_CHUNKING_CONTEXT_MODE),
        )
        self._set_optional_combo(
            self._default_character_combo,
            settings_payload.get("default_character_extraction_profile_id"),
        )
        self._profile_list.setCurrentRow(0)
        self._load_profile_into_editor(self._profiles[0])
        self.apply_language(str(settings_payload.get("language", config.DEFAULT_LANGUAGE)))

    def build_settings(
        self,
        existing_settings_payload: dict[str, object],
    ) -> dict[str, object]:
        """
        @brief      Merge the page-owned fields into one settings payload.
        @param[in]  existing_settings_payload Existing application settings.
        @return     Merged settings payload containing AI settings changes.
        @exception  None
        """
        self._sync_editor_to_owner_profile()
        merged_settings = copy.deepcopy(existing_settings_payload)
        merged_settings["llm_profiles"] = [copy.deepcopy(profile) for profile in self._profiles]
        merged_settings["default_ai_cleanup_profile_id"] = self._optional_combo_value(self._default_cleanup_combo)
        merged_settings["default_ai_chunking_profile_id"] = self._optional_combo_value(self._default_chunking_combo)
        merged_settings["default_ai_translation_profile_id"] = self._optional_combo_value(
            self._default_translation_combo
        )
        merged_settings["default_narrator_profile_generation_profile_id"] = self._optional_combo_value(
            self._default_narrator_generation_combo
        )
        merged_settings["default_speech_blocks_profile_id"] = self._optional_combo_value(
            self._default_speech_blocks_combo
        )
        merged_settings["default_ai_chunking_strategy"] = (
            self._optional_combo_value(self._default_strategy_combo) or config.DEFAULT_AI_CHUNKING_STRATEGY
        )
        merged_settings["default_ai_chunking_context_mode"] = (
            self._optional_combo_value(self._default_context_mode_combo) or config.DEFAULT_AI_CHUNKING_CONTEXT_MODE
        )
        merged_settings["default_character_extraction_profile_id"] = self._optional_combo_value(
            self._default_character_combo
        )
        return merged_settings

    def build_current_profile_payload(self) -> dict[str, object] | None:
        """
        @brief      Build one payload snapshot from the selected profile editor.
        @return     Copy of the selected profile payload or None.
        @exception  None
        """
        self._sync_editor_to_owner_profile()
        current_profile = self._current_profile()
        if current_profile is None:
            return None
        return copy.deepcopy(current_profile)

    def apply_probe_result(self, probe_result: dict[str, object]) -> None:
        """
        @brief      Apply one backend probe result to the selected profile.
        @param[in]  probe_result Normalized backend probe result payload.
        @return     None.
        @exception  None
        """
        current_profile = self._current_profile()
        if current_profile is None:
            return

        probe_succeeded = bool(probe_result.get("success", False))
        current_profile["discovery_succeeded"] = probe_succeeded
        current_profile["discovery_message"] = str(probe_result.get("message", ""))
        if not probe_succeeded:
            return

        model_options = [
            (str(model.get("id", "")), str(model.get("label", "")))
            for model in probe_result.get("discovered_models", [])
            if isinstance(model, dict) and str(model.get("id", "")).strip()
        ]
        self._discovered_model_options[str(current_profile["id"])] = model_options
        # Persist the discovered ids so the selector still offers real models on the next launch
        # instead of falling back to placeholder names the endpoint may not serve at all.
        current_profile["discovered_model_names"] = [model_id for model_id, _label in model_options]

        if model_options:
            selected_model_name = str(current_profile.get("model_name", "")).strip()
            if not bool(current_profile.get("user_overrode_model_name", False)) and not bool(
                probe_result.get("selected_model_valid", False)
            ):
                selected_model_name = model_options[0][0]
                current_profile["model_name"] = selected_model_name
            if bool(probe_result.get("selected_model_valid", False)) and selected_model_name:
                current_profile["discovered_model_name"] = selected_model_name
            else:
                current_profile["discovered_model_name"] = model_options[0][0]
        else:
            current_profile["discovered_model_name"] = ""

        discovered_context_window = probe_result.get("discovered_context_window")
        discovered_context_model_name = str(
            probe_result.get("discovered_context_model_name", "") or ""
        ).strip()
        effective_model_name = str(current_profile.get("model_name", "")).strip()
        context_is_valid = (
            not isinstance(discovered_context_window, bool)
            and isinstance(discovered_context_window, int)
            and 0 < discovered_context_window <= self._context_window_spin.maximum()
            and discovered_context_model_name == effective_model_name
        )
        if context_is_valid:
            current_profile["discovered_context_window"] = discovered_context_window
            current_profile["discovered_context_model_name"] = discovered_context_model_name
            if not bool(current_profile.get("user_overrode_context_window", False)):
                current_profile["context_window"] = discovered_context_window
        else:
            current_profile["discovered_context_window"] = None
            current_profile["discovered_context_model_name"] = ""

        self._load_profile_into_editor(current_profile)

    # LOCAL HELPERS

    def _create_default_profile(self, label: str) -> dict[str, object]:
        """
        @brief      Build a new default AI profile payload for the editor.
        @param[in]  label Initial operator-facing profile label.
        @return     Default profile payload ready for insertion.
        @exception  None
        """
        profile = copy.deepcopy(_DEFAULT_PROFILE_TEMPLATE)
        profile["id"] = self._generate_profile_id()
        profile["label"] = label
        profile["backend_kind"] = config.LLM_BACKEND_OPTIONS[0]
        profile["base_url"] = "http://127.0.0.1:1234/v1"
        profile["model_name"] = "qwen3-8b"
        return profile

    def _generate_profile_id(self) -> str:
        """
        @brief      Generate one stable-looking unique profile identifier.
        @return     Generated profile identifier string.
        @exception  None
        """
        return f"llm_profile_{uuid4().hex[:12]}"

    def _load_model_options_for_profile(self, profile: dict[str, object]) -> None:
        """
        @brief      Reload the model selector choices for one profile.
        @details    Prefers models discovered in this session, then the ones persisted by the
                    last successful probe. The built-in names are only a last resort for a
                    profile that has never been probed, because they are guesses that a given
                    endpoint may not serve.
        @param[in]  profile Target profile payload.
        @return     None.
        @exception  None
        """
        selected_model_name = str(profile.get("model_name", "")).strip()
        discovered_options = self._discovered_model_options.get(str(profile["id"]), [])
        if not discovered_options:
            discovered_options = [
                (str(model_name).strip(), str(model_name).strip())
                for model_name in profile.get("discovered_model_names", [])
                if str(model_name).strip()
            ]
        self._suspend_override_tracking = True
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        if discovered_options:
            for model_id, label in discovered_options:
                self._model_combo.addItem(label, model_id)
        else:
            self._model_combo.addItems(
                (
                    "qwen3-8b",
                    "qwen2.5-7b-instruct",
                    "llama-3.1-8b-instruct",
                )
            )
        self._model_combo.setCurrentText(selected_model_name)
        self._model_combo.blockSignals(False)
        self._suspend_override_tracking = False

    def _reload_profile_list(self) -> None:
        """
        @brief      Rebuild the profile-list widget from the in-memory payload.
        @return     None.
        @exception  None
        """
        current_profile_id = self._current_profile_id()
        self._profile_list.blockSignals(True)
        self._profile_list.clear()
        current_row = 0
        for index, profile in enumerate(self._profiles):
            item = QListWidgetItem(str(profile["label"]) or f"AI Profile {index + 1}")
            item.setData(Qt.ItemDataRole.UserRole, profile["id"])
            self._profile_list.addItem(item)
            if profile["id"] == current_profile_id:
                current_row = index
        if self._profiles:
            self._profile_list.setCurrentRow(current_row)
        self._profile_list.blockSignals(False)

    def _reload_default_profile_combos(self) -> None:
        """
        @brief      Rebuild the default-profile selectors from enabled profiles.
        @return     None.
        @exception  None
        """
        current_cleanup = self._optional_combo_value(self._default_cleanup_combo)
        current_chunking = self._optional_combo_value(self._default_chunking_combo)
        current_translation = self._optional_combo_value(self._default_translation_combo)
        current_narrator_generation = self._optional_combo_value(self._default_narrator_generation_combo)
        current_speech_blocks = self._optional_combo_value(self._default_speech_blocks_combo)
        current_character = self._optional_combo_value(self._default_character_combo)

        for combo in (
            self._default_cleanup_combo,
            self._default_chunking_combo,
            self._default_translation_combo,
            self._default_narrator_generation_combo,
            self._default_speech_blocks_combo,
            self._default_character_combo,
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(none)", None)
            for profile in self._profiles:
                if bool(profile.get("enabled", True)):
                    combo.addItem(str(profile["label"]), profile["id"])
            combo.blockSignals(False)

        self._set_optional_combo(self._default_cleanup_combo, current_cleanup)
        self._set_optional_combo(self._default_chunking_combo, current_chunking)
        self._set_optional_combo(self._default_translation_combo, current_translation)
        self._set_optional_combo(self._default_narrator_generation_combo, current_narrator_generation)
        self._set_optional_combo(self._default_speech_blocks_combo, current_speech_blocks)
        self._set_optional_combo(self._default_character_combo, current_character)

    def _load_selected_profile_into_editor(self, row: int) -> None:
        """
        @brief      Load the selected list-row profile into the editor widgets.
        @param[in]  row Selected profile-list row index.
        @return     None.
        @exception  None
        """
        if self._loading_profile:
            return
        if row < 0 or row >= len(self._profiles):
            return
        self._sync_editor_to_owner_profile()
        self._load_profile_into_editor(self._profiles[row])

    def _load_profile_into_editor(self, profile: dict[str, object]) -> None:
        """
        @brief      Populate the editor widgets from one profile payload.
        @param[in]  profile Source profile payload.
        @return     None.
        @exception  None
        """
        self._loading_profile = True
        self._editor_profile_id = str(profile["id"])
        self._load_model_options_for_profile(profile)
        self._label_edit.setText(str(profile["label"]))
        self._enabled_checkbox.setChecked(bool(profile["enabled"]))
        self._backend_combo.setCurrentText(str(profile["backend_kind"]))
        self._base_url_edit.setText(str(profile["base_url"]))
        self._api_key_edit.setText(str(profile["api_key"]))
        self._model_combo.setCurrentText(str(profile["model_name"]))
        self._context_window_spin.setValue(int(profile["context_window"]))
        self._max_output_spin.setValue(int(profile["max_output_tokens"]))
        self._timeout_spin.setValue(int(profile["request_timeout_seconds"]))
        self._temperature_spin.setValue(float(profile["temperature"]))
        self._supports_structured_checkbox.setChecked(bool(profile["supports_structured_output"]))
        self._loading_profile = False

    def _sync_editor_to_owner_profile(self) -> None:
        """
        @brief      Copy the editor state back into the stable profile that owns it.
        @return     None.
        @exception  None
        """
        owner_profile = self._editor_profile()
        if owner_profile is None or self._loading_profile:
            return
        owner_profile["label"] = self._label_edit.text().strip() or "Unnamed Profile"
        owner_profile["enabled"] = self._enabled_checkbox.isChecked()
        owner_profile["backend_kind"] = self._backend_combo.currentText()
        owner_profile["base_url"] = self._base_url_edit.text().strip()
        owner_profile["api_key"] = self._api_key_edit.text()
        owner_profile["model_name"] = self._model_combo.currentText().strip()
        owner_profile["context_window"] = self._context_window_spin.value()
        owner_profile["max_output_tokens"] = self._max_output_spin.value()
        owner_profile["request_timeout_seconds"] = self._timeout_spin.value()
        owner_profile["temperature"] = self._temperature_spin.value()
        owner_profile["supports_structured_output"] = self._supports_structured_checkbox.isChecked()
        self._reload_profile_list()
        self._reload_default_profile_combos()

    def _on_model_name_edited(self, _value: str) -> None:
        """
        @brief      Mark the selected model name as manually overridden.
        @param[in]  _value Ignored current model text.
        @return     None.
        @exception  None
        """
        if self._loading_profile or self._suspend_override_tracking:
            return
        owner_profile = self._editor_profile()
        if owner_profile is not None:
            owner_profile["user_overrode_model_name"] = True

    def _on_context_window_edited(self, _value: int) -> None:
        """
        @brief      Mark the selected context window as manually overridden.
        @param[in]  _value Ignored current numeric value.
        @return     None.
        @exception  None
        """
        if self._loading_profile or self._suspend_override_tracking:
            return
        owner_profile = self._editor_profile()
        if owner_profile is not None:
            owner_profile["user_overrode_context_window"] = True

    def _editor_profile(self) -> dict[str, object] | None:
        """
        @brief      Return the stable profile currently represented by the editor.
        @return     Editor-owner profile or `None`.
        @exception  None
        """
        if self._editor_profile_id is None:
            return None
        for profile in self._profiles:
            if str(profile.get("id", "")) == self._editor_profile_id:
                return profile
        return None

    def _current_profile(self) -> dict[str, object] | None:
        """
        @brief      Return the currently selected profile payload when available.
        @return     Selected profile payload or `None`.
        @exception  None
        """
        row = self._profile_list.currentRow()
        if row < 0 or row >= len(self._profiles):
            return None
        return self._profiles[row]

    def _current_profile_id(self) -> str | None:
        """
        @brief      Return the identifier of the selected profile-list item.
        @return     Selected profile identifier or `None`.
        @exception  None
        """
        current_item = self._profile_list.currentItem()
        if current_item is None:
            return None
        value = current_item.data(Qt.ItemDataRole.UserRole)
        return None if value in (None, "") else str(value)

    def _set_optional_combo(self, combo: QComboBox, value: object) -> None:
        """
        @brief      Select one optional combo-box value with fallback to `(none)`.
        @param[in]  combo Target combo box.
        @param[in]  value Desired stored value.
        @return     None.
        @exception  None
        """
        index = combo.findData(value)
        combo.setCurrentIndex(0 if index < 0 else index)

    def _optional_combo_value(self, combo: QComboBox) -> str | None:
        """
        @brief      Read one optional combo-box value normalized for persistence.
        @param[in]  combo Source combo box.
        @return     Selected string value or `None`.
        @exception  None
        """
        value = combo.currentData()
        return None if value in (None, "") else str(value)

    def _reload_context_mode_combo(self, language: str) -> None:
        """
        @brief      Rebuild the chunking context-mode selector labels for one language.
        @param[in]  language Active UI language.
        @return     None.
        @exception  None
        """
        current_mode = self._optional_combo_value(self._default_context_mode_combo)
        self._default_context_mode_combo.blockSignals(True)
        self._default_context_mode_combo.clear()
        self._default_context_mode_combo.addItem(
            ui_state_service.translate("ai_settings.context_mode_balanced", language),
            config.AI_CHUNKING_CONTEXT_MODE_BALANCED,
        )
        self._default_context_mode_combo.addItem(
            ui_state_service.translate("ai_settings.context_mode_wide_scene", language),
            config.AI_CHUNKING_CONTEXT_MODE_WIDE_SCENE,
        )
        self._default_context_mode_combo.addItem(
            ui_state_service.translate("ai_settings.context_mode_maximum", language),
            config.AI_CHUNKING_CONTEXT_MODE_MAXIMUM,
        )
        self._default_context_mode_combo.blockSignals(False)
        self._set_optional_combo(
            self._default_context_mode_combo,
            current_mode or config.DEFAULT_AI_CHUNKING_CONTEXT_MODE,
        )

    def _add_profile(self) -> None:
        """
        @brief      Append one new editable profile to the in-memory list.
        @return     None.
        @exception  None
        """
        self._sync_editor_to_owner_profile()
        self._profiles.append(self._create_default_profile(f"AI Profile {len(self._profiles) + 1}"))
        self._reload_profile_list()
        self._reload_default_profile_combos()
        self._profile_list.setCurrentRow(len(self._profiles) - 1)

    def _remove_selected_profile(self) -> None:
        """
        @brief      Remove the selected profile and repair dependent selectors.
        @return     None.
        @exception  None
        """
        self._sync_editor_to_owner_profile()
        row = self._profile_list.currentRow()
        if row < 0 or len(self._profiles) <= 1:
            return
        removed_profile = self._profiles.pop(row)
        removed_profile_id = str(removed_profile["id"])
        for combo in (
            self._default_cleanup_combo,
            self._default_chunking_combo,
            self._default_translation_combo,
            self._default_narrator_generation_combo,
            self._default_speech_blocks_combo,
            self._default_character_combo,
        ):
            if self._optional_combo_value(combo) == removed_profile_id:
                combo.setCurrentIndex(0)
        self._reload_profile_list()
        self._reload_default_profile_combos()
        target_row = max(0, row - 1)
        self._profile_list.setCurrentRow(target_row)
        self._load_profile_into_editor(self._profiles[target_row])

    def eventFilter(self, watched: object, event: object) -> bool:
        """
        @brief      Open the model list when the operator clicks the editable model field.
        @details    An editable combo box normally only drops down from its arrow, so clicking
                    the field reads as "the discovered models are not there". The field stays
                    editable, so a model name that was never advertised can still be typed.
                    The popup opens on button release, and only once the current event has been
                    delivered: opening it during the press makes the popup grab the mouse, and
                    the release that follows immediately dismisses it again.
        @param[in]  watched Object receiving the event.
        @param[in]  event Event delivered to the object.
        @return     True when the event was handled locally.
        @exception  None
        """
        if (
            watched is self._model_combo.lineEdit()
            and event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
            and self._model_combo.isEnabled()
            and self._model_combo.count() > 0
            and not self._model_combo.view().isVisible()
        ):
            QTimer.singleShot(0, self._show_model_popup)
        return super().eventFilter(watched, event)

    def _show_model_popup(self) -> None:
        """
        @brief      Drop down the model list unless it is already open.
        @return     None.
        @exception  None
        """
        if self._model_combo.isEnabled() and not self._model_combo.view().isVisible():
            self._model_combo.showPopup()

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the AI settings page labels.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        """
        self._current_language = language
        self._title_label.setText(f"<h2>{ui_state_service.translate('ai_settings.title', language)}</h2>")
        self._profile_name_label.setText(ui_state_service.translate("ai_settings.profile_name", language))
        self._enabled_checkbox.setText(ui_state_service.translate("ai_settings.profile_enabled", language))
        self._backend_kind_label.setText(ui_state_service.translate("ai_settings.backend_kind", language))
        self._base_url_label.setText(ui_state_service.translate("ai_settings.base_url", language))
        self._api_key_label.setText(ui_state_service.translate("ai_settings.api_key", language))
        self._api_key_edit.setPlaceholderText(ui_state_service.translate("ai_settings.api_key_placeholder", language))
        self._model_name_label.setText(ui_state_service.translate("ai_settings.model_name", language))
        self._context_window_label.setText(ui_state_service.translate("ai_settings.context_window", language))
        self._max_output_label.setText(ui_state_service.translate("ai_settings.max_output_tokens", language))
        self._timeout_label.setText(ui_state_service.translate("ai_settings.timeout", language))
        self._temperature_label.setText(ui_state_service.translate("ai_settings.temperature", language))
        self._supports_structured_checkbox.setText(
            ui_state_service.translate("ai_settings.structured_output", language)
        )
        self._default_cleanup_label.setText(ui_state_service.translate("ai_settings.default_cleanup", language))
        self._default_chunking_label.setText(ui_state_service.translate("ai_settings.default_chunking", language))
        self._default_translation_label.setText(ui_state_service.translate("ai_settings.default_translation", language))
        self._default_narrator_generation_label.setText(
            ui_state_service.translate("ai_settings.default_narrator_generation", language)
        )
        self._default_speech_blocks_label.setText(
            ui_state_service.translate("ai_settings.default_speech_blocks", language)
        )
        self._default_strategy_label.setText(ui_state_service.translate("ai_settings.default_strategy", language))
        for index in range(self._default_strategy_combo.count()):
            strategy = str(self._default_strategy_combo.itemData(index) or "")
            self._default_strategy_combo.setItemText(
                index,
                ui_state_service.translate(f"chunking.strategy.{strategy}", language),
            )
        self._default_context_mode_label.setText(
            ui_state_service.translate("ai_settings.default_context_mode", language)
        )
        self._reload_context_mode_combo(language)
        self._default_character_label.setText(ui_state_service.translate("ai_settings.default_character", language))
        self._add_profile_button.setText(ui_state_service.translate("ai_settings.add_profile", language))
        self._remove_profile_button.setText(ui_state_service.translate("ai_settings.remove_profile", language))
        self._connect_button.setText(ui_state_service.translate("ai_settings.connect", language))
        self._cancel_button.setText(ui_state_service.translate("ai_settings.cancel", language))
        self._save_button.setText(ui_state_service.translate("settings.apply", language))
        self._ok_button.setText(ui_state_service.translate("ai_settings.ok", language))
        for combo in (
            self._default_cleanup_combo,
            self._default_chunking_combo,
            self._default_translation_combo,
            self._default_narrator_generation_combo,
            self._default_speech_blocks_combo,
            self._default_character_combo,
        ):
            if combo.count() > 0:
                combo.setItemText(
                    0,
                    ui_state_service.translate("ai_settings.none", language),
                )


# END OF FILE
