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
         and persistence of global runtime settings plus active-project TTS plan
         normalization.
"""

# IMPORTS

from PySide6.QtWidgets import QMessageBox

from audiomancer.services import (
    narrator_definition_service,
    settings_service,
    ui_state_service,
    voiceweaver_runtime_service,
)
from audiomancer.ui.controllers import audio_blocks_ui_controller, misc_ui_controller


def show_tts_settings_dialog(window) -> None:
    """
    @brief      Show the static TTS settings dialog.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
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


def _persist_tts_settings_from_dialog(window, *, close_dialog: bool) -> None:
    """
    @brief      Persist TTS runtime settings and optionally close the dialog.
    @param[in]  window Active main window shell.
    @param[in]  close_dialog Whether the TTS Settings dialog should close after saving.
    @return     None.
    @exception  None
    """
    merged_settings = window._tts_settings_page.build_settings(window._settings_payload)
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    previous_active_model_id = str(window._settings_payload.get("tts_runtime_active_model_id", "")).strip()
    requested_active_model_id = str(merged_settings.get("tts_runtime_active_model_id", "")).strip()
    global_voice_model_changed = bool(previous_active_model_id and requested_active_model_id) and (
        previous_active_model_id != requested_active_model_id
    )
    if (
        window._current_project_root is not None
        and global_voice_model_changed
        and not audio_blocks_ui_controller.confirm_global_voice_settings_invalidation(window, current_language)
    ):
        return
    settings_service.save_settings(merged_settings)
    window._settings_payload = settings_service.load_settings()
    if window._current_project_root is not None:
        discovered_models = [
            dict(model)
            for model in window._settings_payload.get("tts_runtime_discovered_models", [])
            if isinstance(model, dict)
        ]
        project_plan_payload = narrator_definition_service.load_tts_plan(
            window._current_project_root,
            discovered_models,
        )
        narrator_definition_service.save_tts_plan(
            window._current_project_root,
            project_plan_payload,
            discovered_models,
        )
        if global_voice_model_changed:
            audio_blocks_ui_controller.invalidate_all_audio_blocks_after_voice_settings_change(window)
    window.show_project_state(window._current_project_root, window._current_manifest)
    if close_dialog:
        window._tts_settings_dialog.close()
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.saved_tts_settings",
            current_language,
        ),
    )


def apply_tts_settings_from_dialog(window) -> None:
    """
    @brief      Save TTS Settings changes without closing the TTS Settings dialog.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    """
    _persist_tts_settings_from_dialog(window, close_dialog=False)


def save_tts_settings_from_dialog(window) -> None:
    """
    @brief      Persist TTS runtime settings.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    """
    _persist_tts_settings_from_dialog(window, close_dialog=True)


def test_runtime_connection_from_dialog(window) -> None:
    """
    @brief      Probe the configured VoiceWeaver runtime and refresh the page state.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
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
