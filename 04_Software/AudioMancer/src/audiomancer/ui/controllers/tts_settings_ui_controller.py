#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file tts_settings_ui_controller.py
@brief TTS Settings-dialog UI controller for AudioMancer.
@details Handles TTS Settings dialog presentation, VoiceWeaver runtime probing,
         and persistence of global runtime settings.
@author Eng. Dan Dumitru Pasare
@date 2026-04-16
@version 0.2.0
"""

# IMPORTS

from PySide6.QtWidgets import QMessageBox

from audiomancer.services import (
    narrator_definition_service,
    settings_service,
    ui_state_service,
    voiceweaver_runtime_service,
)
from audiomancer.ui.controllers import misc_ui_controller, settings_ui_controller


def show_tts_settings_dialog(window) -> None:
    """
    @brief      Show the static TTS settings dialog.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    project_plan_payload = None
    if window._current_project_root is not None:
        project_plan_payload = narrator_definition_service.load_tts_plan(
            window._current_project_root,
            window._settings_payload.get("tts_runtime_discovered_models", []),
        )
    window._tts_settings_page.load_state(
        window._settings_payload,
        project_plan_payload,
        window._current_project_root is not None,
    )
    window._tts_settings_dialog.show()
    window._tts_settings_dialog.raise_()
    window._tts_settings_dialog.activateWindow()


def save_tts_settings_from_dialog(window) -> None:
    """
    @brief      Persist TTS runtime settings.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.2.0
    """
    merged_settings = window._tts_settings_page.build_settings(window._settings_payload)
    settings_service.save_settings(merged_settings)
    window._settings_payload = settings_service.load_settings()
    settings_ui_controller.apply_current_ui_settings(window)
    window.show_project_state(window._current_project_root, window._current_manifest)
    window._tts_settings_dialog.close()
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.saved_tts_settings",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def test_runtime_connection_from_dialog(window) -> None:
    """
    @brief      Probe the configured VoiceWeaver runtime and refresh the page state.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    probe_result = voiceweaver_runtime_service.probe_runtime(
        window._tts_settings_page._base_url_edit.text().strip(),
        window._tts_settings_page._api_key_edit.text(),
    )
    window._tts_settings_page.apply_probe_result(probe_result)
    if bool(probe_result.get("success", False)):
        QMessageBox.information(
            window._tts_settings_dialog,
            ui_state_service.translate("tts_settings.popup_success_title", current_language),
            (
                f"{ui_state_service.translate('tts_settings.popup_success_message', current_language)}\n"
                f"{ui_state_service.translate('tts_settings.popup_discovered_models', current_language)}: "
                f"{probe_result.get('discovered_model_count', 0)}"
            ),
        )
        return
    QMessageBox.warning(
        window._tts_settings_dialog,
        ui_state_service.translate("tts_settings.popup_failure_title", current_language),
        (
            f"{ui_state_service.translate('tts_settings.popup_failure_message', current_language)}\n"
            f"{probe_result.get('message', '')}"
        ),
    )


# END OF FILE
