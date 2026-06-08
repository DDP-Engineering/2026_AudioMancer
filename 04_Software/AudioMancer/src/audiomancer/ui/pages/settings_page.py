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
@brief Static settings page for AudioMancer.
@details Presents application settings, including runtime language, completion
         beep, and editable custom UI themes.
@author Eng. Dan Dumitru Pasare
@date 2026-05-23
@version 0.10.2
"""

# IMPORTS

import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import ui_state_service, ui_theme_service

# CONSTANTS

# @brief Editable color roles shown in the first Settings theme editor pass.
_EDITABLE_COLOR_ROLES = (
    ("window_background", "Window background"),
    ("panel_background", "Panel background"),
    ("text_primary", "Primary text"),
    ("text_muted", "Muted text"),
    ("accent", "Accent"),
    ("border", "Border"),
    ("success", "Success"),
    ("warning", "Warning"),
    ("danger", "Danger"),
)


# PUBLIC API


class SettingsPage(QWidget):
    """
    @brief      Display the static application settings form.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.10.1
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the cloned settings page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-23
        @version    0.10.2
        """
        super().__init__(parent)

        self._theme_catalog: list[dict[str, object]] = []
        self._custom_themes: list[dict[str, object]] = []
        self._selected_theme_id = config.DEFAULT_UI_THEME_ID
        self._loading_theme = False
        self._theme_font_family_explicit = False
        self._text_font_family_explicit = False
        self._color_buttons: dict[str, QPushButton] = {}
        self._color_role_labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)

        selector_row = QHBoxLayout()

        self._language_combo = QComboBox(self)
        self._language_combo.addItems(config.SUPPORTED_LANGUAGES)
        self._language_combo.setCurrentText(config.DEFAULT_LANGUAGE)
        self._language_combo.setMinimumWidth(96)

        self._language_label = QLabel("Language", self)
        selector_row.addWidget(self._language_label)
        selector_row.addWidget(self._language_combo)
        selector_row.addSpacing(24)
        self._completion_beep_checkbox = QCheckBox(
            "Play completion beep",
            self,
        )
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

        self._theme_group = QGroupBox("Theme", self)
        theme_outer_layout = QVBoxLayout(self._theme_group)
        theme_selector_row = QHBoxLayout()
        self._theme_label = QLabel("Theme", self)
        self._theme_combo = QComboBox(self)
        self._theme_new_button = QPushButton("New", self)
        self._theme_duplicate_button = QPushButton("Duplicate", self)
        self._theme_delete_button = QPushButton("Delete", self)
        self._theme_import_button = QPushButton("Import Theme", self)
        self._theme_export_button = QPushButton("Export Theme", self)
        theme_selector_row.addWidget(self._theme_label)
        theme_selector_row.addWidget(self._theme_combo, 1)
        theme_selector_row.addWidget(self._theme_new_button)
        theme_selector_row.addWidget(self._theme_duplicate_button)
        theme_selector_row.addWidget(self._theme_delete_button)
        theme_selector_row.addWidget(self._theme_import_button)
        theme_selector_row.addWidget(self._theme_export_button)
        theme_outer_layout.addLayout(theme_selector_row)

        editor_row = QHBoxLayout()
        left_editor_column = QVBoxLayout()
        editor_form = QFormLayout()
        self._theme_name_label = QLabel("Name", self)
        self._theme_name_edit = QLineEdit(self)
        self._theme_name_edit.setMaximumWidth(280)
        self._theme_name_edit.setMaxLength(ui_theme_service.MAX_DISPLAY_NAME_LENGTH)
        editor_form.addRow(self._theme_name_label, self._theme_name_edit)

        self._theme_font_family_label = QLabel("UI font family", self)
        self._theme_font_family_combo = QFontComboBox(self)
        self._theme_font_family_combo.setMaximumWidth(280)
        editor_form.addRow(self._theme_font_family_label, self._theme_font_family_combo)

        self._theme_font_size_spin = QDoubleSpinBox(self)
        self._theme_font_size_spin.setRange(ui_theme_service.MIN_FONT_POINT_SIZE, ui_theme_service.MAX_FONT_POINT_SIZE)
        self._theme_font_size_spin.setSingleStep(0.5)
        self._theme_font_size_spin.setDecimals(1)
        self._theme_font_size_spin.setMaximumWidth(120)
        self._theme_font_size_label = QLabel("UI font size", self)
        editor_form.addRow(self._theme_font_size_label, self._theme_font_size_spin)

        self._theme_text_font_family_label = QLabel("Text font family", self)
        self._theme_text_font_family_combo = QFontComboBox(self)
        self._theme_text_font_family_combo.setMaximumWidth(280)
        editor_form.addRow(self._theme_text_font_family_label, self._theme_text_font_family_combo)

        self._theme_text_font_size_spin = QDoubleSpinBox(self)
        self._theme_text_font_size_spin.setRange(
            ui_theme_service.MIN_FONT_POINT_SIZE,
            ui_theme_service.MAX_FONT_POINT_SIZE,
        )
        self._theme_text_font_size_spin.setSingleStep(0.5)
        self._theme_text_font_size_spin.setDecimals(1)
        self._theme_text_font_size_spin.setMaximumWidth(120)
        self._theme_text_font_size_label = QLabel("Text font size", self)
        editor_form.addRow(self._theme_text_font_size_label, self._theme_text_font_size_spin)

        left_editor_column.addLayout(editor_form)

        self._preview_group = QGroupBox("Preview", self)
        self._preview_group.setMaximumWidth(420)
        self._preview_group.setMaximumHeight(220)
        preview_layout = QVBoxLayout(self._preview_group)
        self._preview_label = QLabel("Sample text", self)
        self._preview_input = QPlainTextEdit(self)
        self._preview_input.setPlainText("Sample text window")
        self._preview_input.setMaximumHeight(82)
        self._preview_button = QPushButton("Sample button", self)
        self._preview_status = QLabel("Ready", self)
        preview_layout.addWidget(self._preview_label)
        preview_layout.addWidget(self._preview_input)
        preview_layout.addWidget(self._preview_button)
        preview_layout.addWidget(self._preview_status)
        left_editor_column.addWidget(self._preview_group)
        editor_row.addLayout(left_editor_column, 0)

        color_grid = QGridLayout()
        color_grid.setColumnStretch(0, 1)
        color_grid.setColumnStretch(1, 0)
        for row_index, (role_name, role_label) in enumerate(_EDITABLE_COLOR_ROLES):
            label = QLabel(role_label, self)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            button = QPushButton("#000000", self)
            button.setMinimumWidth(150)
            button.clicked.connect(lambda _checked=False, color_role=role_name: self._choose_color(color_role))
            color_grid.addWidget(label, row_index, 0)
            color_grid.addWidget(button, row_index, 1)
            self._color_role_labels[role_name] = label
            self._color_buttons[role_name] = button
        editor_row.addLayout(color_grid, 1)
        theme_outer_layout.addLayout(editor_row)

        self._theme_combo.currentIndexChanged.connect(lambda _index: self._handle_theme_selection_changed())
        self._theme_new_button.clicked.connect(lambda _checked=False: self._create_custom_theme())
        self._theme_duplicate_button.clicked.connect(lambda _checked=False: self._duplicate_selected_theme())
        self._theme_delete_button.clicked.connect(lambda _checked=False: self._delete_selected_theme())
        self._theme_name_edit.textChanged.connect(lambda _text: self._editor_value_changed())
        self._theme_font_family_combo.currentFontChanged.connect(lambda _font: self._handle_theme_font_changed())
        self._theme_font_size_spin.valueChanged.connect(lambda _value: self._editor_value_changed())
        self._theme_text_font_family_combo.currentFontChanged.connect(lambda _font: self._handle_text_font_changed())
        self._theme_text_font_size_spin.valueChanged.connect(lambda _value: self._editor_value_changed())

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self._theme_group)
        layout.addWidget(scroll_area, 1)

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

    def _refresh_theme_catalog(self) -> None:
        """
        @brief      Rebuild the theme selector from built-in and draft custom themes.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        self._theme_catalog = ui_theme_service.merged_theme_catalog(self._custom_themes)
        self._theme_combo.blockSignals(True)
        self._theme_combo.clear()
        for theme_payload in self._theme_catalog:
            marker = "" if theme_payload.get("built_in") else " *"
            self._theme_combo.addItem(f"{theme_payload['display_name']}{marker}", str(theme_payload["theme_id"]))
        selected_index = self._theme_combo.findData(self._selected_theme_id)
        if selected_index < 0:
            self._selected_theme_id = config.DEFAULT_UI_THEME_ID
            selected_index = self._theme_combo.findData(self._selected_theme_id)
        self._theme_combo.setCurrentIndex(max(0, selected_index))
        self._theme_combo.blockSignals(False)

    def _selected_theme_payload(self) -> dict[str, object]:
        """
        @brief      Return the currently selected theme from the draft catalog.
        @return     Selected theme payload or the default built-in theme.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        selected_theme_id = str(self._theme_combo.currentData() or self._selected_theme_id)
        return ui_theme_service.theme_by_id(selected_theme_id, self._custom_themes)

    def _selected_custom_theme_index(self, theme_id: str | None = None) -> int | None:
        """
        @brief      Resolve the selected custom theme index.
        @param[in]  theme_id Optional theme id to resolve; uses current selection when omitted.
        @return     Custom theme index or None when a built-in theme is selected.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        selected_theme_id = str(theme_id or self._theme_combo.currentData() or self._selected_theme_id)
        for index, theme_payload in enumerate(self._custom_themes):
            if theme_payload.get("theme_id") == selected_theme_id:
                return index
        return None

    def _load_theme_editor(self, theme_payload: dict[str, object]) -> None:
        """
        @brief      Load one theme payload into the editor widgets.
        @param[in]  theme_payload Theme payload to display.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.4.0
        """
        self._loading_theme = True
        font_payload = theme_payload.get("font")
        text_font_payload = theme_payload.get("text_font")
        colors_payload = theme_payload.get("colors")
        if not isinstance(font_payload, dict):
            font_payload = {}
        if not isinstance(text_font_payload, dict):
            text_font_payload = {}
        if not isinstance(colors_payload, dict):
            colors_payload = {}

        self._theme_name_edit.setText(str(theme_payload.get("display_name", "")))
        font_family = str(font_payload.get("family", "") or "")
        self._theme_font_family_explicit = bool(font_family)
        if font_family:
            self._theme_font_family_combo.setCurrentFont(QFont(font_family))
        point_size = font_payload.get("point_size")
        self._theme_font_size_spin.setValue(float(point_size) if isinstance(point_size, (int, float)) else 10.0)

        text_font_family = str(text_font_payload.get("family", "") or "")
        self._text_font_family_explicit = bool(text_font_family)
        if text_font_family:
            self._theme_text_font_family_combo.setCurrentFont(QFont(text_font_family))
        text_point_size = text_font_payload.get("point_size")
        self._theme_text_font_size_spin.setValue(
            float(text_point_size) if isinstance(text_point_size, (int, float)) else 10.0
        )
        for role_name, _role_label in _EDITABLE_COLOR_ROLES:
            self._set_color_button(role_name, str(colors_payload.get(role_name, "#000000")))
        self._loading_theme = False
        self._update_editor_enabled_state()
        self._update_theme_preview()

    def _update_editor_enabled_state(self) -> None:
        """
        @brief      Enable editing only when a custom theme is selected.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.4.0
        """
        is_custom_theme = self._selected_custom_theme_index() is not None
        self._theme_name_edit.setEnabled(is_custom_theme)
        self._theme_font_family_combo.setEnabled(is_custom_theme)
        self._theme_font_size_spin.setEnabled(is_custom_theme)
        self._theme_text_font_family_combo.setEnabled(is_custom_theme)
        self._theme_text_font_size_spin.setEnabled(is_custom_theme)
        self._theme_delete_button.setEnabled(is_custom_theme)
        self._theme_duplicate_button.setEnabled(True)
        self._theme_export_button.setEnabled(self._theme_combo.currentIndex() >= 0)
        for button in self._color_buttons.values():
            button.setEnabled(is_custom_theme)

    def _theme_from_editor(self, source_theme: dict[str, object]) -> dict[str, object]:
        """
        @brief      Build a normalized custom theme payload from editor fields.
        @param[in]  source_theme Existing selected custom theme payload.
        @return     Normalized custom theme payload.
        @exception  ValueError Raised when the edited payload is invalid.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.4.0
        """
        colors = copy.deepcopy(source_theme.get("colors", {}))
        if not isinstance(colors, dict):
            colors = {}
        for role_name in self._color_buttons:
            colors[role_name] = self._color_buttons[role_name].text()

        edited_theme = {
            "schema_version": config.UI_THEME_SCHEMA_VERSION,
            "theme_id": str(source_theme.get("theme_id", "")),
            "display_name": self._theme_name_edit.text().strip() or str(source_theme.get("display_name", "")),
            "built_in": False,
            "font": {
                "family": self._theme_font_family_combo.currentFont().family()
                if self._theme_font_family_explicit
                else "",
                "point_size": float(self._theme_font_size_spin.value()),
                "scale": config.DEFAULT_UI_TEXT_SCALE,
            },
            "text_font": {
                "family": self._theme_text_font_family_combo.currentFont().family()
                if self._text_font_family_explicit
                else "",
                "point_size": float(self._theme_text_font_size_spin.value()),
                "scale": config.DEFAULT_UI_TEXT_SCALE,
            },
            "colors": colors,
        }
        return ui_theme_service.validate_theme_payload(edited_theme)

    def _commit_selected_custom_theme(self) -> None:
        """
        @brief      Save editor changes into the in-dialog custom theme draft.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        selected_index = self._selected_custom_theme_index(self._selected_theme_id)
        if selected_index is None:
            return
        self._custom_themes[selected_index] = self._theme_from_editor(self._custom_themes[selected_index])
        self._selected_theme_id = str(self._custom_themes[selected_index]["theme_id"])

    def _handle_theme_selection_changed(self) -> None:
        """
        @brief      Load the newly selected theme while preserving custom draft edits.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        if self._loading_theme:
            return
        self._commit_selected_custom_theme()
        self._selected_theme_id = str(self._theme_combo.currentData() or config.DEFAULT_UI_THEME_ID)
        self._load_theme_editor(self._selected_theme_payload())

    def _handle_theme_font_changed(self) -> None:
        """
        @brief      Mark the theme font family as explicit after an operator edit.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        if not self._loading_theme:
            self._theme_font_family_explicit = True
        self._editor_value_changed()

    def _handle_text_font_changed(self) -> None:
        """
        @brief      Mark the text-window font family as explicit after an operator edit.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        if not self._loading_theme:
            self._text_font_family_explicit = True
        self._editor_value_changed()

    def _editor_value_changed(self) -> None:
        """
        @brief      Propagate editor changes into preview and the draft selected custom theme.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        if self._loading_theme:
            return
        if self._selected_custom_theme_index(self._selected_theme_id) is not None:
            self._commit_selected_custom_theme()
            self._refresh_theme_catalog()
        self._update_theme_preview()

    def _create_custom_theme(self) -> None:
        """
        @brief      Create a new custom theme from the default built-in theme.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        self._commit_selected_custom_theme()
        source_theme = ui_theme_service.theme_by_id(config.DEFAULT_UI_THEME_ID, [])
        source_theme.pop("theme_id", None)
        source_theme["display_name"] = "Custom Theme"
        source_theme["built_in"] = False
        new_theme = ui_theme_service.import_theme_payload(source_theme, self._custom_themes)
        self._custom_themes.append(new_theme)
        self._selected_theme_id = str(new_theme["theme_id"])
        self._refresh_theme_catalog()
        self._load_theme_editor(new_theme)

    def _duplicate_selected_theme(self) -> None:
        """
        @brief      Duplicate the selected theme as an editable custom theme.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        self._commit_selected_custom_theme()
        source_theme = self._selected_theme_payload()
        duplicate_name = f"{source_theme['display_name']} Copy"
        duplicate_theme = ui_theme_service.duplicate_theme(source_theme, duplicate_name)
        duplicate_theme = ui_theme_service.import_theme_payload(duplicate_theme, self._custom_themes)
        self._custom_themes.append(duplicate_theme)
        self._selected_theme_id = str(duplicate_theme["theme_id"])
        self._refresh_theme_catalog()
        self._load_theme_editor(duplicate_theme)

    def _delete_selected_theme(self) -> None:
        """
        @brief      Delete the selected custom theme and fall back to the default theme.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        selected_index = self._selected_custom_theme_index()
        if selected_index is None:
            return
        del self._custom_themes[selected_index]
        self._selected_theme_id = config.DEFAULT_UI_THEME_ID
        self._refresh_theme_catalog()
        self._load_theme_editor(self._selected_theme_payload())

    def add_imported_theme_payload(self, candidate_payload: object) -> dict[str, object]:
        """
        @brief      Import one theme payload into the in-dialog custom theme draft.
        @param[in]  candidate_payload Candidate decoded theme payload.
        @return     Imported custom theme payload.
        @exception  ValueError Raised when the candidate theme is invalid.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        self._commit_selected_custom_theme()
        imported_theme = ui_theme_service.import_theme_payload(candidate_payload, self._custom_themes)
        self._custom_themes.append(imported_theme)
        self._selected_theme_id = str(imported_theme["theme_id"])
        self._refresh_theme_catalog()
        self._load_theme_editor(imported_theme)
        return imported_theme

    def selected_theme_export_payload(self) -> dict[str, object]:
        """
        @brief      Return the selected theme as a portable export payload.
        @return     Normalized theme export payload.
        @exception  ValueError Raised when no selected theme can be exported.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        self._commit_selected_custom_theme()
        return ui_theme_service.export_theme_payload(self._selected_theme_payload())

    def selected_theme_export_file_name(self) -> str:
        """
        @brief      Build the default export filename for the selected theme.
        @return     JSON filename for the selected theme.
        @exception  ValueError Raised when no selected theme can be exported.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        export_payload = self.selected_theme_export_payload()
        return f"AudioMancer_{export_payload['theme_id']}_theme.json"

    def _choose_color(self, role_name: str) -> None:
        """
        @brief      Open a color picker for one editable color role.
        @param[in]  role_name Theme color role.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        current_color = QColor(self._color_buttons[role_name].text())
        selected_color = QColorDialog.getColor(current_color, self, self._color_role_labels[role_name].text())
        if selected_color.isValid():
            self._set_color_button(role_name, selected_color.name().upper())
            self._editor_value_changed()

    def _set_color_button(self, role_name: str, color_value: str) -> None:
        """
        @brief      Update one color button's displayed hex value and swatch.
        @param[in]  role_name Theme color role.
        @param[in]  color_value Hex RGB color value.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        normalized_color = color_value.upper()
        text_color = "#000000" if QColor(normalized_color).lightness() > 140 else "#FFFFFF"
        self._color_buttons[role_name].setText(normalized_color)
        self._color_buttons[role_name].setStyleSheet(f"background-color: {normalized_color}; color: {text_color};")

    def _update_theme_preview(self) -> None:
        """
        @brief      Apply the in-memory selected theme to the embedded preview widgets.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.1.0
        """
        try:
            preview_theme = (
                self._theme_from_editor(self._selected_theme_payload())
                if self._selected_custom_theme_index() is not None
                else self._selected_theme_payload()
            )
            self._preview_group.setStyleSheet(ui_state_service.build_theme_stylesheet(preview_theme))
        except ValueError:
            self._preview_group.setStyleSheet("")

    def load_settings(self, settings_payload: dict[str, object]) -> None:
        """
        @brief      Load one settings payload into the page widgets.
        @param[in]  settings_payload Combined application settings payload.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-14
        @version    0.4.1
        """
        self._language_combo.setCurrentText(str(settings_payload.get("language", config.DEFAULT_LANGUAGE)))
        self._completion_beep_checkbox.setChecked(
            bool(
                settings_payload.get(
                    "play_completion_beep",
                    config.DEFAULT_PLAY_COMPLETION_BEEP,
                )
            )
        )
        self._scroll_steps_spin.setValue(
            int(
                settings_payload.get(
                    "ui_scroll_steps_per_wheel_notch",
                    config.DEFAULT_UI_SCROLL_STEPS_PER_WHEEL_NOTCH,
                )
            )
        )
        self._custom_themes = ui_theme_service.normalize_theme_collection(settings_payload.get("ui_themes", []))
        self._selected_theme_id = str(settings_payload.get("ui_theme_id", config.DEFAULT_UI_THEME_ID))
        self._refresh_theme_catalog()
        self._load_theme_editor(self._selected_theme_payload())

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
        @date       2026-05-14
        @version    0.4.1
        """
        self._commit_selected_custom_theme()
        selected_theme = self._selected_theme_payload()
        merged_settings = dict(existing_settings_payload)
        merged_settings["language"] = self._language_combo.currentText()
        merged_settings.pop("ui_text_scale", None)
        merged_settings["ui_theme_id"] = str(selected_theme["theme_id"])
        merged_settings["ui_themes"] = ui_theme_service.normalize_theme_collection(copy.deepcopy(self._custom_themes))
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
        @date       2026-05-14
        @version    0.3.1
        """
        self._language_label.setText(ui_state_service.translate("settings.language", language))
        self._completion_beep_checkbox.setText(ui_state_service.translate("settings.play_beep", language))
        self._scroll_steps_label.setText(ui_state_service.translate("settings.scroll_steps", language))
        self._theme_group.setTitle(ui_state_service.translate("settings.theme_group", language))
        self._theme_label.setText(ui_state_service.translate("settings.theme", language))
        self._theme_new_button.setText(ui_state_service.translate("settings.theme_new", language))
        self._theme_duplicate_button.setText(ui_state_service.translate("settings.theme_duplicate", language))
        self._theme_delete_button.setText(ui_state_service.translate("settings.theme_delete", language))
        self._theme_import_button.setText(ui_state_service.translate("settings.theme_import", language))
        self._theme_export_button.setText(ui_state_service.translate("settings.theme_export", language))
        self._theme_name_label.setText(ui_state_service.translate("settings.theme_name", language))
        self._theme_font_family_label.setText(ui_state_service.translate("settings.theme_font_family", language))
        self._theme_font_size_label.setText(ui_state_service.translate("settings.theme_font_size", language))
        self._theme_text_font_family_label.setText(
            ui_state_service.translate("settings.theme_text_font_family", language)
        )
        self._theme_text_font_size_label.setText(ui_state_service.translate("settings.theme_text_font_size", language))
        self._preview_group.setTitle(ui_state_service.translate("settings.theme_preview", language))
        self._preview_label.setText(ui_state_service.translate("settings.theme_preview_label", language))
        self._preview_input.setPlainText(ui_state_service.translate("settings.theme_preview_input", language))
        self._preview_button.setText(ui_state_service.translate("settings.theme_preview_button", language))
        self._preview_status.setText(ui_state_service.translate("settings.theme_preview_status", language))
        for role_name, _role_label in _EDITABLE_COLOR_ROLES:
            self._color_role_labels[role_name].setText(
                ui_state_service.translate(f"settings.theme_color.{role_name}", language)
            )
        self._cancel_button.setText(ui_state_service.translate("settings.cancel", language))
        self._apply_button.setText(ui_state_service.translate("settings.apply", language))
        self._ok_button.setText(ui_state_service.translate("settings.ok", language))


# END OF FILE
