#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.2.0
"""

# IMPORTS

import copy
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
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

# CONSTANTS

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
    "discovered_context_window": None,
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.2.0
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the AI settings page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.2.0
        """
        super().__init__(parent)
        self._profiles: list[dict[str, object]] = []
        self._loading_profile = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>AI Settings</h2>"))

        content_row = QHBoxLayout()

        profile_column = QWidget(self)
        profile_column_layout = QVBoxLayout(profile_column)
        profile_column_layout.setContentsMargins(0, 0, 0, 0)

        self._profile_list = QListWidget(self)
        self._profile_list.currentRowChanged.connect(
            self._load_selected_profile_into_editor
        )
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
        form_layout = QFormLayout()

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
        self._model_combo.addItems((
            "qwen3-8b",
            "qwen2.5-7b-instruct",
            "llama-3.1-8b-instruct",
        ))

        self._context_window_spin = QSpinBox(self)
        self._context_window_spin.setRange(1, 1_000_000)

        self._max_output_spin = QSpinBox(self)
        self._max_output_spin.setRange(1, 1_000_000)

        self._timeout_spin = QSpinBox(self)
        self._timeout_spin.setRange(1, 3600)

        self._temperature_spin = QDoubleSpinBox(self)
        self._temperature_spin.setRange(0.0, 2.0)
        self._temperature_spin.setDecimals(2)
        self._temperature_spin.setSingleStep(0.05)

        self._supports_structured_checkbox = QCheckBox(
            "Structured output supported"
        )

        form_layout.addRow("Profile Name", profile_name_row)
        form_layout.addRow("Backend Kind", backend_row)
        form_layout.addRow("Base URL", self._base_url_edit)
        form_layout.addRow("API Key", self._api_key_edit)
        form_layout.addRow("Model Name", self._model_combo)
        form_layout.addRow("Context Window", self._context_window_spin)
        form_layout.addRow("Max Output Tokens", self._max_output_spin)
        form_layout.addRow("Timeout (s)", self._timeout_spin)
        form_layout.addRow("Temperature", self._temperature_spin)
        editor_layout.addLayout(form_layout)
        editor_layout.addWidget(self._supports_structured_checkbox)

        defaults_group = QWidget(self)
        defaults_layout = QFormLayout(defaults_group)
        defaults_layout.setContentsMargins(0, 0, 0, 0)

        self._default_cleanup_combo = QComboBox(self)
        self._default_chunking_combo = QComboBox(self)
        self._default_strategy_combo = QComboBox(self)
        for strategy in config.AI_CHUNKING_STRATEGY_OPTIONS:
            self._default_strategy_combo.addItem(strategy.title(), strategy)

        self._default_character_combo = QComboBox(self)

        defaults_layout.addRow(
            "Default Cleanup Profile", self._default_cleanup_combo
        )
        defaults_layout.addRow(
            "Default Chunking Profile", self._default_chunking_combo
        )
        defaults_layout.addRow(
            "Default AI Chunking Strategy", self._default_strategy_combo
        )
        defaults_layout.addRow(
            "Default Character Extraction Profile",
            self._default_character_combo,
        )
        editor_layout.addWidget(defaults_group)

        content_row.addWidget(editor_container, 2)
        layout.addLayout(content_row, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._cancel_button = QPushButton("Cancel", self)
        self._save_button = QPushButton("Save AI Settings", self)
        button_row.addWidget(self._cancel_button)
        button_row.addWidget(self._save_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.load_settings({
            "llm_profiles": [],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": None,
            "default_ai_chunking_strategy": config.DEFAULT_AI_CHUNKING_STRATEGY,
            "default_character_extraction_profile_id": None,
        })

    def load_settings(self, settings_payload: dict[str, object]) -> None:
        """
        @brief      Load one persisted settings payload into the page widgets.
        @param[in]  settings_payload Combined application settings payload.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        source_profiles = settings_payload.get("llm_profiles", [])
        if not isinstance(source_profiles, list):
            source_profiles = []

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
            self._default_strategy_combo,
            settings_payload.get("default_ai_chunking_strategy"),
        )
        self._set_optional_combo(
            self._default_character_combo,
            settings_payload.get("default_character_extraction_profile_id"),
        )
        self._profile_list.setCurrentRow(0)

    def build_settings(
        self,
        existing_settings_payload: dict[str, object],
    ) -> dict[str, object]:
        """
        @brief      Merge the page-owned fields into one settings payload.
        @param[in]  existing_settings_payload Existing application settings.
        @return     Merged settings payload containing AI settings changes.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        self._sync_editor_to_current_profile()
        merged_settings = copy.deepcopy(existing_settings_payload)
        merged_settings["llm_profiles"] = [
            copy.deepcopy(profile) for profile in self._profiles
        ]
        merged_settings["default_ai_cleanup_profile_id"] = (
            self._optional_combo_value(self._default_cleanup_combo)
        )
        merged_settings["default_ai_chunking_profile_id"] = (
            self._optional_combo_value(self._default_chunking_combo)
        )
        merged_settings["default_ai_chunking_strategy"] = (
            self._optional_combo_value(self._default_strategy_combo)
            or config.DEFAULT_AI_CHUNKING_STRATEGY
        )
        merged_settings["default_character_extraction_profile_id"] = (
            self._optional_combo_value(self._default_character_combo)
        )
        return merged_settings

    # LOCAL HELPERS

    def _create_default_profile(self, label: str) -> dict[str, object]:
        profile = copy.deepcopy(_DEFAULT_PROFILE_TEMPLATE)
        profile["id"] = self._generate_profile_id()
        profile["label"] = label
        profile["backend_kind"] = config.LLM_BACKEND_OPTIONS[0]
        profile["base_url"] = "http://127.0.0.1:1234/v1"
        profile["model_name"] = "qwen3-8b"
        return profile

    def _generate_profile_id(self) -> str:
        return f"llm_profile_{uuid4().hex[:12]}"

    def _reload_profile_list(self) -> None:
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
        self._profile_list.blockSignals(False)
        if self._profiles:
            self._profile_list.setCurrentRow(current_row)

    def _reload_default_profile_combos(self) -> None:
        current_cleanup = self._optional_combo_value(self._default_cleanup_combo)
        current_chunking = self._optional_combo_value(self._default_chunking_combo)
        current_character = self._optional_combo_value(self._default_character_combo)

        for combo in (
            self._default_cleanup_combo,
            self._default_chunking_combo,
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
        self._set_optional_combo(self._default_character_combo, current_character)

    def _load_selected_profile_into_editor(self, row: int) -> None:
        if self._loading_profile:
            return
        if row < 0 or row >= len(self._profiles):
            return
        self._load_profile_into_editor(self._profiles[row])

    def _load_profile_into_editor(self, profile: dict[str, object]) -> None:
        self._loading_profile = True
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
        self._supports_structured_checkbox.setChecked(
            bool(profile["supports_structured_output"])
        )
        self._loading_profile = False

    def _sync_editor_to_current_profile(self) -> None:
        current_profile = self._current_profile()
        if current_profile is None or self._loading_profile:
            return
        current_profile["label"] = self._label_edit.text().strip() or "Unnamed Profile"
        current_profile["enabled"] = self._enabled_checkbox.isChecked()
        current_profile["backend_kind"] = self._backend_combo.currentText()
        current_profile["base_url"] = self._base_url_edit.text().strip()
        current_profile["api_key"] = self._api_key_edit.text()
        current_profile["model_name"] = self._model_combo.currentText().strip()
        current_profile["context_window"] = self._context_window_spin.value()
        current_profile["max_output_tokens"] = self._max_output_spin.value()
        current_profile["request_timeout_seconds"] = self._timeout_spin.value()
        current_profile["temperature"] = self._temperature_spin.value()
        current_profile["supports_structured_output"] = (
            self._supports_structured_checkbox.isChecked()
        )
        self._reload_profile_list()
        self._reload_default_profile_combos()

    def _current_profile(self) -> dict[str, object] | None:
        row = self._profile_list.currentRow()
        if row < 0 or row >= len(self._profiles):
            return None
        return self._profiles[row]

    def _current_profile_id(self) -> str | None:
        current_item = self._profile_list.currentItem()
        if current_item is None:
            return None
        value = current_item.data(Qt.ItemDataRole.UserRole)
        return None if value in (None, "") else str(value)

    def _set_optional_combo(self, combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(0 if index < 0 else index)

    def _optional_combo_value(self, combo: QComboBox) -> str | None:
        value = combo.currentData()
        return None if value in (None, "") else str(value)

    def _add_profile(self) -> None:
        self._sync_editor_to_current_profile()
        self._profiles.append(
            self._create_default_profile(f"AI Profile {len(self._profiles) + 1}")
        )
        self._reload_profile_list()
        self._reload_default_profile_combos()
        self._profile_list.setCurrentRow(len(self._profiles) - 1)

    def _remove_selected_profile(self) -> None:
        row = self._profile_list.currentRow()
        if row < 0 or len(self._profiles) <= 1:
            return
        removed_profile = self._profiles.pop(row)
        removed_profile_id = str(removed_profile["id"])
        for combo in (
            self._default_cleanup_combo,
            self._default_chunking_combo,
            self._default_character_combo,
        ):
            if self._optional_combo_value(combo) == removed_profile_id:
                combo.setCurrentIndex(0)
        self._reload_profile_list()
        self._reload_default_profile_combos()
        self._profile_list.setCurrentRow(max(0, row - 1))


# END OF FILE
