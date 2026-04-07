#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file settings_page.py
@brief Static settings page for AudioMancer.
@details Clones the operator-facing settings dialog layout as a purely
         presentational page without any connected functionality.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.3.0
"""

# IMPORTS

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import ui_state_service

# CONSTANTS

# @brief Operator-facing labels for the supported UI text-scale presets.
_UI_TEXT_SCALE_LABELS = {
    "very_small": "Very Small",
    "small": "Small",
    "normal": "Normal",
    "large": "Large",
    "very_large": "Very Large",
}


# PUBLIC API


class SettingsPage(QWidget):
    """
    @brief      Display the static application settings form.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.3.0
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the cloned settings page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.3.0
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)

        selector_row = QHBoxLayout()

        self._language_combo = QComboBox(self)
        self._language_combo.addItems(config.SUPPORTED_LANGUAGES)
        self._language_combo.setCurrentText(config.DEFAULT_LANGUAGE)

        self._ui_text_scale_combo = QComboBox(self)
        for value, label in _UI_TEXT_SCALE_LABELS.items():
            self._ui_text_scale_combo.addItem(label, value)
        self._ui_text_scale_combo.setCurrentText("Normal")

        selector_row.addWidget(QLabel("Language"))
        selector_row.addWidget(self._language_combo)
        selector_row.addSpacing(24)
        selector_row.addWidget(QLabel("Interface Text Size"))
        selector_row.addWidget(self._ui_text_scale_combo)
        selector_row.addStretch(1)
        layout.addLayout(selector_row)

        self._completion_beep_checkbox = QCheckBox(
            "Play completion beep",
            self,
        )
        self._completion_beep_checkbox.setChecked(
            config.DEFAULT_PLAY_COMPLETION_BEEP
        )
        layout.addWidget(self._completion_beep_checkbox)

        layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._cancel_button = QPushButton("Cancel", self)
        self._save_button = QPushButton("Save Settings", self)
        button_row.addWidget(self._cancel_button)
        button_row.addWidget(self._save_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        self._language_label = selector_row.itemAt(0).widget()
        self._text_size_label = selector_row.itemAt(3).widget()

    def load_settings(self, settings_payload: dict[str, object]) -> None:
        """
        @brief      Load one settings payload into the page widgets.
        @param[in]  settings_payload Combined application settings payload.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        self._language_combo.setCurrentText(
            str(settings_payload.get("language", config.DEFAULT_LANGUAGE))
        )
        ui_text_scale = str(
            settings_payload.get("ui_text_scale", config.DEFAULT_UI_TEXT_SCALE)
        )
        index = self._ui_text_scale_combo.findData(ui_text_scale)
        self._ui_text_scale_combo.setCurrentIndex(0 if index < 0 else index)
        self._completion_beep_checkbox.setChecked(
            bool(
                settings_payload.get(
                    "play_completion_beep",
                    config.DEFAULT_PLAY_COMPLETION_BEEP,
                )
            )
        )

    def build_settings(
        self,
        existing_settings_payload: dict[str, object],
    ) -> dict[str, object]:
        """
        @brief      Merge the page-owned fields into one settings payload.
        @param[in]  existing_settings_payload Existing application settings.
        @return     Merged settings payload containing settings-page changes.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        merged_settings = dict(existing_settings_payload)
        merged_settings["language"] = self._language_combo.currentText()
        merged_settings["ui_text_scale"] = str(
            self._ui_text_scale_combo.currentData()
        )
        merged_settings["play_completion_beep"] = (
            self._completion_beep_checkbox.isChecked()
        )
        return merged_settings

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the settings page labels.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        self._language_label.setText(
            ui_state_service.translate("settings.language", language)
        )
        self._text_size_label.setText(
            ui_state_service.translate("settings.text_size", language)
        )
        self._completion_beep_checkbox.setText(
            ui_state_service.translate("settings.play_beep", language)
        )
        self._cancel_button.setText(
            ui_state_service.translate("settings.cancel", language)
        )
        self._save_button.setText(
            ui_state_service.translate("settings.save", language)
        )
        self._ui_text_scale_combo.setItemText(
            self._ui_text_scale_combo.findData("very_small"),
            ui_state_service.translate("settings.scale.very_small", language),
        )
        self._ui_text_scale_combo.setItemText(
            self._ui_text_scale_combo.findData("small"),
            ui_state_service.translate("settings.scale.small", language),
        )
        self._ui_text_scale_combo.setItemText(
            self._ui_text_scale_combo.findData("normal"),
            ui_state_service.translate("settings.scale.normal", language),
        )
        self._ui_text_scale_combo.setItemText(
            self._ui_text_scale_combo.findData("large"),
            ui_state_service.translate("settings.scale.large", language),
        )
        self._ui_text_scale_combo.setItemText(
            self._ui_text_scale_combo.findData("very_large"),
            ui_state_service.translate("settings.scale.very_large", language),
        )


# END OF FILE
