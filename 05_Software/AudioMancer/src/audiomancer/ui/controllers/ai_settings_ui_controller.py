#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_settings_ui_controller.py
@brief AI Settings-dialog UI controller for AudioMancer.
@details Handles AI Settings dialog presentation, persistence, and operator
         feedback for AI backend connection probing.
"""

# IMPORTS

from PySide6.QtWidgets import QMessageBox

from audiomancer.services import ai_backend_service, settings_service, ui_state_service
from audiomancer.ui.controllers import misc_ui_controller

# PUBLIC API


def show_ai_settings_dialog(window) -> None:
    """
    @brief      Show the static AI settings dialog.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    """
    window._ai_settings_page.load_settings(window._settings_payload)
    window._ai_settings_dialog.show()
    window._ai_settings_dialog.raise_()
    window._ai_settings_dialog.activateWindow()


def _persist_ai_settings_from_dialog(window, *, close_dialog: bool) -> None:
    """
    @brief      Persist AI Settings changes and optionally close the dialog.
    @param[in]  window Active main window shell.
    @param[in]  close_dialog Whether the AI Settings dialog should close after saving.
    @return     None.
    @exception  None
    """
    merged_settings = window._ai_settings_page.build_settings(window._settings_payload)
    settings_service.save_settings(merged_settings)
    window._settings_payload = settings_service.load_settings()
    window.refresh_current_page_state()
    if close_dialog:
        window._ai_settings_dialog.close()
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.saved_ai_settings",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def apply_ai_settings_from_dialog(window) -> None:
    """
    @brief      Save AI Settings changes without closing the AI Settings dialog.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    """
    _persist_ai_settings_from_dialog(window, close_dialog=False)


def save_ai_settings_from_dialog(window) -> None:
    """
    @brief      Persist AI settings-page changes through the settings service.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    """
    _persist_ai_settings_from_dialog(window, close_dialog=True)


def connect_ai_profile_from_dialog(window) -> None:
    """
    @brief      Probe the selected AI profile and show operator feedback.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    current_profile = window._ai_settings_page.build_current_profile_payload()
    if current_profile is None:
        return

    probe_result = ai_backend_service.probe_profile(current_profile)
    window._ai_settings_page.apply_probe_result(probe_result)

    if bool(probe_result.get("success", False)):
        QMessageBox.information(
            window._ai_settings_dialog,
            ui_state_service.translate(
                "ai_settings.popup_success_title",
                current_language,
            ),
            (
                f"{ui_state_service.translate('ai_settings.popup_success_message', current_language)}\n"
                f"{ui_state_service.translate('ai_settings.popup_discovered_models', current_language)}: "
                f"{probe_result.get('discovered_model_count', 0)}"
            ),
        )
        return

    QMessageBox.warning(
        window._ai_settings_dialog,
        ui_state_service.translate(
            "ai_settings.popup_failure_title",
            current_language,
        ),
        (
            f"{ui_state_service.translate('ai_settings.popup_failure_message', current_language)}\n"
            f"{probe_result.get('message', '')}"
        ),
    )


# END OF FILE
