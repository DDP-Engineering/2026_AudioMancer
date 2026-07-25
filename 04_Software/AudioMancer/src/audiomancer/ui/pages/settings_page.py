#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file settings_page.py
@brief Simplified appearance settings page for AudioMancer.
@details Presents runtime language, completion beep, scroll steps, a built-in theme
         selector, and two font-size step selectors (interface controls and text
         windows). Colour/custom-theme editing has been intentionally removed.
@author Eng. Dan Dumitru Pasare
@date 2026-07-25
@version 0.11.0
"""

# IMPORTS

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import ui_state_service, ui_theme_service

# CONSTANTS

# @brief Operator-facing labels for each font-size step (fallback English display names).
_FONT_SIZE_STEP_LABELS = {
    "extra_small": "Extra small",
    "small": "Small",
    "medium": "Medium",
    "normal": "Normal",
    "large": "Large",
    "very_large": "Very large",
    "huge": "Huge",
}

# @brief Nominal base point size used only for the settings-page font preview.
_PREVIEW_BASE_POINT_SIZE = 10.0


# PUBLIC API


class SettingsPage(QWidget):
    """
    @brief      Display the simplified appearance settings form.
    @details    Exposes language, completion beep, scroll steps, a built-in theme
                selector, and independent interface/text font-size step selectors.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.11.0
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the simplified settings page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-25
        @version    0.11.0
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)

        selector_row = QHBoxLayout()
        self._language_label = QLabel("Language", self)
        self._language_combo = QComboBox(self)
        self._language_combo.addItems(config.SUPPORTED_LANGUAGES)
        self._language_combo.setCurrentText(config.DEFAULT_LANGUAGE)
        self._language_combo.setMinimumWidth(96)
        selector_row.addWidget(self._language_label)
        selector_row.addWidget(self._language_combo)
        selector_row.addSpacing(24)
        self._completion_beep_checkbox = QCheckBox("Play completion beep", self)
        self._completion_beep_checkbox.setChecked(config.DEFAULT_PLAY_COMPLETION_BEEP)
        selector_row.addWidget(self._completion_beep_checkbox)
        selector_row.addSpacing(24)
        self._scroll_steps_label = QLabel("Scroll steps", self)
        self._scroll_steps_spin = QSpinBox(self)
        self._scroll_steps_spin.setRange(
            config.MIN_UI_SCROLL_STEPS_PER_WHEEL_NOTCH,
            config.MAX_UI_SCROLL_STEPS_PER_WHEEL_NOTCH,
        )
        self._scroll_steps_spin.setValue(config.DEFAULT_UI_SCROLL_STEPS_PER_WHEEL_NOTCH)
        self._scroll_steps_spin.setMaximumWidth(72)
        selector_row.addWidget(self._scroll_steps_label)
        selector_row.addWidget(self._scroll_steps_spin)
        selector_row.addStretch(1)
        layout.addLayout(selector_row)

        self._theme_group = QGroupBox("Appearance", self)
        appearance_layout = QVBoxLayout(self._theme_group)
        appearance_form = QFormLayout()

        self._theme_label = QLabel("Theme", self)
        self._theme_combo = QComboBox(self)
        for theme_payload in ui_theme_service.built_in_themes():
            self._theme_combo.addItem(str(theme_payload["display_name"]), str(theme_payload["theme_id"]))
        appearance_form.addRow(self._theme_label, self._theme_combo)

        self._ui_font_size_label = QLabel("Interface font size", self)
        self._ui_font_size_combo = self._build_font_size_combo()
        appearance_form.addRow(self._ui_font_size_label, self._ui_font_size_combo)

        self._text_font_size_label = QLabel("Text window font size", self)
        self._text_font_size_combo = self._build_font_size_combo()
        appearance_form.addRow(self._text_font_size_label, self._text_font_size_combo)

        appearance_layout.addLayout(appearance_form)

        self._preview_group = QGroupBox("Preview", self)
        self._preview_group.setMaximumWidth(460)
        preview_layout = QVBoxLayout(self._preview_group)
        self._preview_label = QLabel("Sample interface label", self)
        self._preview_button = QPushButton("Sample button", self)
        self._preview_input = QPlainTextEdit(self)
        self._preview_input.setReadOnly(True)
        self._preview_input.setPlainText("Sample text window content")
        self._preview_input.setMaximumHeight(90)
        preview_layout.addWidget(self._preview_label)
        preview_layout.addWidget(self._preview_button)
        preview_layout.addWidget(self._preview_input)
        appearance_layout.addWidget(self._preview_group)
        appearance_layout.addStretch(1)

        layout.addWidget(self._theme_group, 1)

        self._theme_combo.currentIndexChanged.connect(lambda _index: self._update_preview())
        self._ui_font_size_combo.currentIndexChanged.connect(lambda _index: self._update_preview())
        self._text_font_size_combo.currentIndexChanged.connect(lambda _index: self._update_preview())

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._cancel_button = QPushButton("Cancel", self)
        self._apply_button = QPushButton("Apply", self)
        self._ok_button = QPushButton("OK", self)
        self._save_button = self._ok_button
        button_row.addWidget(self._cancel_button)
        button_row.addWidget(self._apply_button)
        button_row.addWidget(self._ok_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self._select_theme(config.DEFAULT_UI_THEME_ID)
        self._select_step(self._ui_font_size_combo, config.DEFAULT_UI_FONT_SIZE_STEP)
        self._select_step(self._text_font_size_combo, config.DEFAULT_TEXT_FONT_SIZE_STEP)
        self._update_preview()

    def _build_font_size_combo(self) -> QComboBox:
        """
        @brief      Build a combo box populated with the seven font-size steps.
        @return     Configured font-size step combo box.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-25
        @version    0.1.0
        """
        combo = QComboBox(self)
        for step in config.UI_FONT_SIZE_STEPS:
            combo.addItem(_FONT_SIZE_STEP_LABELS.get(step, step), step)
        combo.setMinimumWidth(150)
        return combo

    def _select_theme(self, theme_id: str) -> None:
        """
        @brief      Select the given theme id in the theme combo, falling back to the default.
        @param[in]  theme_id Candidate theme identifier.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-25
        @version    0.1.0
        """
        index = self._theme_combo.findData(theme_id)
        if index < 0:
            index = self._theme_combo.findData(config.DEFAULT_UI_THEME_ID)
        self._theme_combo.setCurrentIndex(max(0, index))

    def _select_step(self, combo: QComboBox, step: str) -> None:
        """
        @brief      Select the given font-size step in a combo, falling back to normal.
        @param[in]  combo Target font-size combo box.
        @param[in]  step Candidate font-size step.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-25
        @version    0.1.0
        """
        index = combo.findData(step)
        if index < 0:
            index = combo.findData(config.DEFAULT_UI_FONT_SIZE_STEP)
        combo.setCurrentIndex(max(0, index))

    def _update_preview(self) -> None:
        """
        @brief      Update the preview widgets with the selected theme colours and font sizes.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-25
        @version    0.1.0
        """
        theme_payload = ui_theme_service.theme_by_id(self._theme_combo.currentData(), [])
        try:
            self._preview_group.setStyleSheet(ui_state_service.build_theme_stylesheet(theme_payload))
        except ValueError:
            self._preview_group.setStyleSheet("")

        ui_step = str(self._ui_font_size_combo.currentData() or config.DEFAULT_UI_FONT_SIZE_STEP)
        text_step = str(self._text_font_size_combo.currentData() or config.DEFAULT_TEXT_FONT_SIZE_STEP)
        ui_point = ui_state_service.resolve_font_point_size(ui_step, _PREVIEW_BASE_POINT_SIZE)
        text_point = ui_state_service.resolve_font_point_size(text_step, _PREVIEW_BASE_POINT_SIZE)
        for widget in (self._preview_label, self._preview_button):
            control_font = QFont(widget.font())
            control_font.setPointSizeF(ui_point)
            widget.setFont(control_font)
        text_font = QFont(self._preview_input.font())
        text_font.setPointSizeF(text_point)
        self._preview_input.setFont(text_font)

    def load_settings(self, settings_payload: dict[str, object]) -> None:
        """
        @brief      Load one settings payload into the page widgets.
        @param[in]  settings_payload Combined application settings payload.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-25
        @version    0.5.0
        """
        self._language_combo.setCurrentText(str(settings_payload.get("language", config.DEFAULT_LANGUAGE)))
        self._completion_beep_checkbox.setChecked(
            bool(settings_payload.get("play_completion_beep", config.DEFAULT_PLAY_COMPLETION_BEEP))
        )
        self._scroll_steps_spin.setValue(
            int(
                settings_payload.get(
                    "ui_scroll_steps_per_wheel_notch",
                    config.DEFAULT_UI_SCROLL_STEPS_PER_WHEEL_NOTCH,
                )
            )
        )
        self._select_theme(str(settings_payload.get("ui_theme_id", config.DEFAULT_UI_THEME_ID)))
        self._select_step(
            self._ui_font_size_combo,
            str(settings_payload.get("ui_font_size_step", config.DEFAULT_UI_FONT_SIZE_STEP)),
        )
        self._select_step(
            self._text_font_size_combo,
            str(settings_payload.get("text_font_size_step", config.DEFAULT_TEXT_FONT_SIZE_STEP)),
        )
        self._update_preview()

    def build_settings(self, existing_settings_payload: dict[str, object]) -> dict[str, object]:
        """
        @brief      Merge the page-owned appearance fields into one settings payload.
        @param[in]  existing_settings_payload Existing application settings.
        @return     Merged settings payload containing settings-page changes.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-25
        @version    0.5.0
        """
        merged_settings = dict(existing_settings_payload)
        merged_settings.pop("ui_text_scale", None)
        merged_settings["language"] = self._language_combo.currentText()
        merged_settings["ui_theme_id"] = str(self._theme_combo.currentData() or config.DEFAULT_UI_THEME_ID)
        merged_settings["ui_font_size_step"] = str(
            self._ui_font_size_combo.currentData() or config.DEFAULT_UI_FONT_SIZE_STEP
        )
        merged_settings["text_font_size_step"] = str(
            self._text_font_size_combo.currentData() or config.DEFAULT_TEXT_FONT_SIZE_STEP
        )
        merged_settings["play_completion_beep"] = self._completion_beep_checkbox.isChecked()
        merged_settings["ui_scroll_steps_per_wheel_notch"] = self._scroll_steps_spin.value()
        return merged_settings

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the settings page labels.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-25
        @version    0.4.0
        """
        self._language_label.setText(ui_state_service.translate("settings.language", language))
        self._completion_beep_checkbox.setText(ui_state_service.translate("settings.play_beep", language))
        self._scroll_steps_label.setText(ui_state_service.translate("settings.scroll_steps", language))
        self._theme_group.setTitle(ui_state_service.translate("settings.theme_group", language))
        self._theme_label.setText(ui_state_service.translate("settings.theme", language))
        self._preview_group.setTitle(ui_state_service.translate("settings.theme_preview", language))
        self._cancel_button.setText(ui_state_service.translate("settings.cancel", language))
        self._apply_button.setText(ui_state_service.translate("settings.apply", language))
        self._ok_button.setText(ui_state_service.translate("settings.ok", language))


# END OF FILE
