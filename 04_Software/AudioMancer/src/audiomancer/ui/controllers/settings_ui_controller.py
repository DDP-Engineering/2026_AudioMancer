#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
         runtime language and UI-scale changes to the shell.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.2.0
"""

# IMPORTS

from PySide6.QtWidgets import QApplication

from audiomancer.services import settings_service
from audiomancer.services import ui_state_service
from audiomancer.ui.controllers import misc_ui_controller


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


def save_settings_from_dialog(window) -> None:
    """
    @brief      Persist settings-page changes through the settings service.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    merged_settings = window._settings_page.build_settings(window._settings_payload)
    settings_service.save_settings(merged_settings)
    window._settings_payload = settings_service.load_settings()
    apply_current_ui_settings(window)
    window._settings_dialog.close()
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.saved_settings",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def apply_current_ui_settings(window) -> None:
    """
    @brief      Apply persisted runtime UI settings to the current shell.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
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
    @date       2026-04-06
    @version    0.1.0
    """
    window.setWindowTitle(ui_state_service.translate("window_title.main", language))
    window._action_new_project.setText(
        ui_state_service.translate("toolbar.new_project", language)
    )
    window._action_open_project.setText(
        ui_state_service.translate("toolbar.open_project", language)
    )
    window._action_settings.setText(
        ui_state_service.translate("toolbar.settings", language)
    )
    window._action_ai_settings.setText(
        ui_state_service.translate("toolbar.ai_settings", language)
    )
    window._action_help.setText(
        ui_state_service.translate("toolbar.help", language)
    )
    window._action_about.setText(
        ui_state_service.translate("toolbar.about", language)
    )
    window._sidebar.apply_language(language)
    window._status_bar.apply_language(language)
    window._settings_dialog.setWindowTitle(
        ui_state_service.translate("dialog.settings_title", language)
    )
    window._ai_settings_dialog.setWindowTitle(
        ui_state_service.translate("dialog.ai_settings_title", language)
    )
    if window._operation_progress_dialog is not None:
        window._operation_progress_dialog.apply_language(language)
    for widget in (
        window._settings_page,
        window._ai_settings_page,
        *window._page_registry.values(),
    ):
        if hasattr(widget, "apply_language"):
            widget.apply_language(language)

# END OF FILE
