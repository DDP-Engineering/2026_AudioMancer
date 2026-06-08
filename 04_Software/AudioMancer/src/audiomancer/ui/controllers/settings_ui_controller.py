#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file settings_ui_controller.py
@brief Settings-dialog UI controller for AudioMancer.
@details Handles Settings dialog presentation, persistence, and application of
         runtime language and UI-theme changes to the shell.
@author Eng. Dan Dumitru Pasare
@date 2026-05-14
@version 0.5.1
"""

# IMPORTS

import json
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from audiomancer import config
from audiomancer.services import persistence_service, settings_service, ui_scroll_service, ui_state_service
from audiomancer.ui.controllers import misc_ui_controller

# CONSTANTS

# @brief Maximum accepted imported theme JSON size in bytes.
MAX_THEME_IMPORT_BYTES = 256 * 1024

# @brief File dialog filter for portable AudioMancer theme files.
THEME_JSON_FILTER = "JSON Files (*.json)"

# PUBLIC API


def show_settings_dialog(window) -> None:
    """
    @brief      Show the static settings dialog.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
    """
    window._settings_page.load_settings(window._settings_payload)
    window._settings_dialog.show()
    window._settings_dialog.raise_()
    window._settings_dialog.activateWindow()


def _persist_settings_from_dialog(window, *, close_dialog: bool) -> None:
    """
    @brief      Persist settings-page changes and apply them to the running shell.
    @param[in]  window Active main window shell.
    @param[in]  close_dialog Whether the Settings dialog should close after saving.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    merged_settings = window._settings_page.build_settings(window._settings_payload)
    settings_service.save_settings(merged_settings)
    window._settings_payload = settings_service.load_settings()
    apply_current_ui_settings(window)
    if close_dialog:
        window._settings_dialog.close()
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.saved_settings",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def apply_settings_from_dialog(window) -> None:
    """
    @brief      Apply Settings changes without closing the Settings dialog.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    _persist_settings_from_dialog(window, close_dialog=False)


def save_settings_from_dialog(window) -> None:
    """
    @brief      Persist Settings changes and close the Settings dialog.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    _persist_settings_from_dialog(window, close_dialog=True)


def import_theme_from_dialog(window) -> None:
    """
    @brief      Import one theme JSON file into the Settings dialog draft.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    selected_path, _selected_filter = QFileDialog.getOpenFileName(
        window,
        ui_state_service.translate("dialog.theme_import_title", current_language),
        str(config.APP_ROOT),
        THEME_JSON_FILTER,
    )
    if not selected_path:
        return

    theme_path = Path(selected_path)
    try:
        if theme_path.stat().st_size > MAX_THEME_IMPORT_BYTES:
            raise ValueError(ui_state_service.translate("settings.theme_import_too_large", current_language))
        imported_payload = json.loads(theme_path.read_text(encoding="utf-8"))
        imported_theme = window._settings_page.add_imported_theme_payload(imported_payload)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.theme_import_title", current_language),
            f"{ui_state_service.translate('settings.theme_import_failed', current_language)}\n\n{error}",
        )
        return

    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("settings.theme_imported", current_language).format(
            theme_name=imported_theme["display_name"]
        ),
    )


def export_theme_from_dialog(window) -> None:
    """
    @brief      Export the selected Settings theme to one portable JSON file.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    try:
        export_payload = window._settings_page.selected_theme_export_payload()
        default_file_name = window._settings_page.selected_theme_export_file_name()
    except ValueError as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.theme_export_title", current_language),
            str(error),
        )
        return

    selected_path, _selected_filter = QFileDialog.getSaveFileName(
        window,
        ui_state_service.translate("dialog.theme_export_title", current_language),
        str(config.APP_ROOT / default_file_name),
        THEME_JSON_FILTER,
    )
    if not selected_path:
        return

    export_path = Path(selected_path)
    if export_path.suffix.lower() != ".json":
        export_path = export_path.with_suffix(".json")

    try:
        persistence_service.write_json_atomic(export_path, export_payload)
    except (OSError, TypeError) as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.theme_export_title", current_language),
            f"{ui_state_service.translate('settings.theme_export_failed', current_language)}\n\n{error}",
        )
        return

    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("settings.theme_exported", current_language).format(path=str(export_path)),
    )


def apply_current_ui_settings(window) -> None:
    """
    @brief      Apply persisted runtime UI settings to the current shell.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
    """
    ui_scroll_service.install_global_scroll_step_filter(
        QApplication.instance(),
        int(
            window._settings_payload.get(
                "ui_scroll_steps_per_wheel_notch",
                config.DEFAULT_UI_SCROLL_STEPS_PER_WHEEL_NOTCH,
            )
        ),
    )
    ui_state_service.apply_ui_settings(
        QApplication.instance(),
        window,
        window._settings_payload,
    )


def apply_language(window, language: str) -> None:
    """
    @brief      Apply one UI language across the visible shell widgets.
    @param[in]  window Active main window shell.
    @param[in]  language Target UI language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.2.1
    """
    window.setWindowTitle(ui_state_service.translate("window_title.main", language))
    window._action_new_project.setText(ui_state_service.translate("toolbar.new_project", language))
    window._action_open_project.setText(ui_state_service.translate("toolbar.open_project", language))
    window._action_settings.setText(ui_state_service.translate("toolbar.settings", language))
    window._action_ai_settings.setText(ui_state_service.translate("toolbar.ai_settings", language))
    window._action_tts_settings.setText(ui_state_service.translate("toolbar.tts_settings", language))
    window._action_help.setText(ui_state_service.translate("toolbar.help", language))
    window._action_about.setText(ui_state_service.translate("toolbar.about", language))
    window._sidebar.apply_language(language)
    window._settings_dialog.setWindowTitle(ui_state_service.translate("dialog.settings_title", language))
    window._ai_settings_dialog.setWindowTitle(ui_state_service.translate("dialog.ai_settings_title", language))
    window._tts_settings_dialog.setWindowTitle(ui_state_service.translate("dialog.tts_settings_title", language))
    if window._operation_progress_dialog is not None:
        window._operation_progress_dialog.apply_language(language)
    for widget in (
        window._settings_page,
        window._ai_settings_page,
        window._tts_settings_page,
        *window._page_registry.values(),
    ):
        if hasattr(widget, "apply_language"):
            widget.apply_language(language)


# END OF FILE
