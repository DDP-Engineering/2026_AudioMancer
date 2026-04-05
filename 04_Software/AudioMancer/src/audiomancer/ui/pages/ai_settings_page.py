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
@brief Static AI settings page for AudioMancer.
@details Clones the DDP_Audiomancer AI settings dialog layout as a purely
         presentational page without any connected functionality.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.1.0
"""

# IMPORTS

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config


# PUBLIC API


class AiSettingsPage(QWidget):
    """
    @brief      Display the static AI settings shell page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the cloned AI settings page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>AI Settings</h2>"))

        content_row = QHBoxLayout()

        profile_column = QWidget(self)
        profile_column_layout = QVBoxLayout(profile_column)
        profile_column_layout.setContentsMargins(0, 0, 0, 0)

        self._profile_list = QListWidget(self)
        self._profile_list.addItems((
            "Local Analysis",
            "LM Studio",
            "OpenAI Compatible",
        ))
        profile_column_layout.addWidget(self._profile_list, 1)

        profile_button_row = QHBoxLayout()
        self._add_profile_button = QPushButton("Add Profile", self)
        self._remove_profile_button = QPushButton("Remove Profile", self)
        profile_button_row.addWidget(self._add_profile_button)
        profile_button_row.addWidget(self._remove_profile_button)
        profile_column_layout.addLayout(profile_button_row)

        content_row.addWidget(profile_column, 1)

        editor_container = QWidget(self)
        editor_layout = QVBoxLayout(editor_container)
        form_layout = QFormLayout()

        self._label_edit = QLineEdit(self)
        self._label_edit.setText("Local Analysis")
        profile_name_row = QHBoxLayout()
        profile_name_row.addWidget(self._label_edit, 1)

        self._enabled_checkbox = QCheckBox("Profile enabled")
        self._enabled_checkbox.setChecked(True)
        profile_name_row.addWidget(self._enabled_checkbox)

        self._backend_combo = QComboBox(self)
        self._backend_combo.addItems(config.LLM_BACKEND_OPTIONS)
        self._backend_combo.setCurrentText("lmstudio")
        backend_row = QHBoxLayout()
        backend_row.addWidget(self._backend_combo, 1)

        self._connect_button = QPushButton("Connect", self)
        self._connect_button.setMinimumWidth(112)
        backend_row.addWidget(self._connect_button)

        self._base_url_edit = QLineEdit(self)
        self._base_url_edit.setText("http://127.0.0.1:1234/v1")

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
        self._model_combo.setCurrentText("qwen3-8b")

        self._context_window_spin = QSpinBox(self)
        self._context_window_spin.setRange(1, 1_000_000)
        self._context_window_spin.setValue(config.DEFAULT_LLM_CONTEXT_WINDOW)

        self._max_output_spin = QSpinBox(self)
        self._max_output_spin.setRange(1, 1_000_000)
        self._max_output_spin.setValue(config.DEFAULT_LLM_MAX_OUTPUT_TOKENS)

        self._timeout_spin = QSpinBox(self)
        self._timeout_spin.setRange(1, 3600)
        self._timeout_spin.setValue(config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS)

        self._temperature_spin = QDoubleSpinBox(self)
        self._temperature_spin.setRange(0.0, 2.0)
        self._temperature_spin.setDecimals(2)
        self._temperature_spin.setSingleStep(0.05)
        self._temperature_spin.setValue(config.DEFAULT_LLM_TEMPERATURE)

        self._supports_structured_checkbox = QCheckBox(
            "Structured output supported"
        )
        self._supports_structured_checkbox.setChecked(True)

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
        self._default_cleanup_combo.addItems((
            "(none)",
            "Local Analysis",
            "LM Studio",
        ))

        self._default_chunking_combo = QComboBox(self)
        self._default_chunking_combo.addItems((
            "(none)",
            "Local Analysis",
            "LM Studio",
        ))

        self._default_strategy_combo = QComboBox(self)
        for strategy in config.AI_CHUNKING_STRATEGY_OPTIONS:
            self._default_strategy_combo.addItem(strategy.title())

        self._default_character_combo = QComboBox(self)
        self._default_character_combo.addItems((
            "(none)",
            "Local Analysis",
            "LM Studio",
        ))

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


# END OF FILE
