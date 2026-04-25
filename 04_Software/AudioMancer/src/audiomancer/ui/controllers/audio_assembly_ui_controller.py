#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audio_assembly_ui_controller.py
@brief Audio Assembly page UI controller for AudioMancer.
@details Handles final audiobook composition confirmation, settings persistence,
         threaded operation lifecycle, generated-output playback, and manifest
         synchronization for the Audio Assembly workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.2.0
"""

# IMPORTS

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QMessageBox

from audiomancer.services import (
    audio_assembly_service,
    project_workspace_service,
    text_cleanup_state_service,
    ui_state_service,
)
from audiomancer.ui.controllers import misc_ui_controller, operation_runner_controller

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


def handle_settings_changed(window: "MainWindow", settings: dict[str, object]) -> None:
    """
    @brief      Persist Audio Assembly page settings into the active manifest.
    @param[in]  window Active main window instance.
    @param[in]  settings Candidate Audio Assembly settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    window._current_manifest = audio_assembly_service.save_audio_assembly_settings(
        window._current_project_root,
        window._current_manifest,
        settings,
    )
    window.show_project_state(window._current_project_root, window._current_manifest)


def handle_generate_requested(window: "MainWindow", settings: dict[str, object]) -> None:
    """
    @brief      Confirm and start or continue Audio Assembly composition.
    @param[in]  window Active main window instance.
    @param[in]  settings Candidate Audio Assembly settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._active_operation_kind is not None:
        return
    if window._current_project_root is None or window._current_manifest is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_no_active_project", current_language),
        )
        return
    window._current_manifest = audio_assembly_service.save_audio_assembly_settings(
        window._current_project_root,
        window._current_manifest,
        settings,
    )
    if not _confirm_audio_assembly(window, current_language):
        window.show_project_state(window._current_project_root, window._current_manifest)
        return
    _stop_audio_assembly_playback(window)
    operation_runner_controller.start_threaded_operation(
        window,
        "audio_assembly",
        ui_state_service.translate("audio_assembly.generate", current_language),
        ui_state_service.translate("progress.audio_assembly", current_language),
        lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            audio_assembly_service.start_or_continue_composition(
                project_root,
                manifest,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        ),
        set_busy=lambda is_busy: window._audio_assembly_page.set_busy(is_busy),
        success_handler=lambda result_payload: _handle_success(window, result_payload),
        failure_handler=lambda error: _handle_failure(window, error),
        cancel_handler=lambda message: _handle_cancelled(window, message),
    )


def handle_reset_requested(window: "MainWindow") -> None:
    """
    @brief      Confirm and reset persisted Audio Assembly data.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    if not _confirm_audio_assembly_reset(window, current_language):
        return
    _stop_audio_assembly_playback(window)
    audio_assembly_service.reset_audio_assembly(window._current_project_root)
    _sync_manifest_after_audio_assembly_update(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.audio_assembly_reset", current_language),
    )


def handle_playback_toggle_requested(window: "MainWindow", output_key: str) -> None:
    """
    @brief      Start or stop playback of one generated audiobook output file.
    @param[in]  window Active main window instance.
    @param[in]  output_key Selected output key.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    normalized_output_key = str(output_key).strip()
    if _is_audio_assembly_playback_active(window):
        _stop_audio_assembly_playback(window)
        return
    if window._current_project_root is None:
        return
    output_record = _output_by_key(window, normalized_output_key)
    output_path = _output_audio_path(window, output_record)
    if output_path is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("audio_assembly.error_missing_audio", current_language),
        )
        return
    _stop_other_audio_previews(window)
    window._audio_assembly_playback_output_key = normalized_output_key
    window._audio_assembly_playback_starting = True
    try:
        window._audio_assembly_audio_player.setSource(QUrl.fromLocalFile(str(output_path)))
        window._audio_assembly_page.set_playback_active(True)
        window._audio_assembly_audio_player.play()
    finally:
        window._audio_assembly_playback_starting = False


def handle_playback_state_changed(window: "MainWindow") -> None:
    """
    @brief      Refresh Audio Assembly playback state after local playback changes.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    if bool(getattr(window, "_audio_assembly_playback_starting", False)):
        return
    if window._audio_assembly_audio_player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
        return
    window._audio_assembly_playback_output_key = None
    window._audio_assembly_page.set_playback_active(False)


def _handle_success(window: "MainWindow", result_payload: object) -> None:
    """
    @brief      Refresh state after successful Audio Assembly composition.
    @param[in]  window Active main window instance.
    @param[in]  result_payload Worker result payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    _ = result_payload
    _sync_manifest_after_audio_assembly_update(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.audio_assembly_generated", current_language_from_window(window)),
    )


def _handle_failure(window: "MainWindow", error: Exception) -> None:
    """
    @brief      Refresh state and show an Audio Assembly operation failure.
    @param[in]  window Active main window instance.
    @param[in]  error Raised worker exception.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    _sync_manifest_from_disk(window)
    QMessageBox.warning(
        window,
        ui_state_service.translate("dialog.project_error_title", current_language_from_window(window)),
        str(error),
    )


def _handle_cancelled(window: "MainWindow", message: str) -> None:
    """
    @brief      Refresh state after Audio Assembly cancellation.
    @param[in]  window Active main window instance.
    @param[in]  message Cancellation message.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    _ = message
    _sync_manifest_from_disk(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.operation_cancelled", current_language_from_window(window)),
    )


def _sync_manifest_after_audio_assembly_update(window: "MainWindow") -> None:
    """
    @brief      Synchronize manifest summary after an Audio Assembly data change.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operation_state = audio_assembly_service.load_operation_state(window._current_project_root)
    if operation_state is not None:
        operations["audio_assembly"] = project_workspace_service.project_manifest_operation_summary(
            "audio_assembly",
            operation_state,
        )
    updated_manifest["operations"] = operations
    report = audio_assembly_service.load_audio_assembly_report(window._current_project_root)
    if (
        isinstance(report, dict)
        and str(report.get("audio_assembly_stage_status", "")).strip()
        == audio_assembly_service.AUDIO_ASSEMBLY_STAGE_COMPLETED
    ):
        updated_manifest["current_stage"] = "audio_assembly_ready"
    elif _stage_rank(str(updated_manifest.get("current_stage", "")).strip()) > _stage_rank("audio_blocks_ready"):
        updated_manifest["current_stage"] = "audio_blocks_ready"
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _sync_manifest_from_disk(window: "MainWindow") -> None:
    """
    @brief      Reload persisted Audio Assembly state into the manifest summary.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operation_state = audio_assembly_service.load_operation_state(window._current_project_root)
    if operation_state is not None:
        operations["audio_assembly"] = project_workspace_service.project_manifest_operation_summary(
            "audio_assembly",
            operation_state,
        )
    updated_manifest["operations"] = operations
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _confirm_audio_assembly(window: "MainWindow", language: str) -> bool:
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.confirm_audio_assembly_title", language),
            ui_state_service.translate("project.confirm_audio_assembly", language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_audio_assembly_reset(window: "MainWindow", language: str) -> bool:
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.confirm_audio_assembly_reset_title", language),
            ui_state_service.translate("project.confirm_audio_assembly_reset", language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def _output_by_key(window: "MainWindow", output_key: str) -> dict[str, object] | None:
    """
    @brief      Find one generated Audio Assembly output by key.
    @param[in]  window Active main window instance.
    @param[in]  output_key Output key to locate.
    @return     Output record or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if window._current_project_root is None:
        return None
    normalized_output_key = str(output_key).strip()
    return next(
        (
            output
            for output in audio_assembly_service.load_generated_outputs(window._current_project_root)
            if str(output.get("output_key", "")).strip() == normalized_output_key
        ),
        None,
    )


def _output_audio_path(window: "MainWindow", output_record: dict[str, object] | None) -> Path | None:
    """
    @brief      Resolve one generated output record to an existing audio file.
    @param[in]  window Active main window instance.
    @param[in]  output_record Optional generated-output record.
    @return     Absolute audio path or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if window._current_project_root is None or not isinstance(output_record, dict):
        return None
    relative_path = str(output_record.get("audio_relative_path", "")).strip()
    if not relative_path:
        return None
    audio_path = Path(window._current_project_root) / relative_path
    return audio_path if audio_path.is_file() else None


def _stop_audio_assembly_playback(window: "MainWindow") -> None:
    """
    @brief      Stop Audio Assembly playback and clear page playback state.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    window._audio_assembly_playback_starting = False
    if hasattr(window, "_audio_assembly_audio_player"):
        window._audio_assembly_audio_player.stop()
        window._audio_assembly_audio_player.setSource(QUrl())
    if hasattr(window, "_audio_assembly_page"):
        window._audio_assembly_page.set_playback_active(False)
    window._audio_assembly_playback_output_key = None


def _is_audio_assembly_playback_active(window: "MainWindow") -> bool:
    """
    @brief      Return whether Audio Assembly playback should be treated as active.
    @param[in]  window Active main window instance.
    @return     True when playback is starting, playing, paused, or tracked as active.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if bool(getattr(window, "_audio_assembly_playback_starting", False)):
        return True
    if str(getattr(window, "_audio_assembly_playback_output_key", "") or "").strip():
        return True
    player = getattr(window, "_audio_assembly_audio_player", None)
    return player is not None and player.playbackState() != QMediaPlayer.PlaybackState.StoppedState


def _stop_other_audio_previews(window: "MainWindow") -> None:
    """
    @brief      Stop other page audio preview players before Audio Assembly playback.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    for attr_name in (
        "_narator_voice_audio_player",
        "_character_voices_audio_player",
        "_audio_blocks_audio_player",
    ):
        player = getattr(window, attr_name, None)
        if player is not None:
            player.stop()


def current_language_from_window(window: "MainWindow") -> str:
    """
    @brief      Resolve the current runtime language from the main window.
    @param[in]  window Active main window instance.
    @return     Runtime language code.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return ui_state_service.current_language_from_settings(window._settings_payload)


def _stage_rank(stage: str) -> int:
    """
    @brief      Resolve one workflow stage token to an ordering rank.
    @param[in]  stage Workflow stage token.
    @return     Zero-based stage rank or zero for unknown stages.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    stages = (
        "project_created",
        "source_selected",
        "text_cleanup_ready",
        "text_chunking_ready",
        "translation_ready",
        "character_discovery_ready",
        "narrator_definition_ready",
        "character_voices_ready",
        "speech_blocks_ready",
        "audio_blocks_ready",
        "audio_assembly_ready",
    )
    try:
        return stages.index(stage)
    except ValueError:
        return 0


# END OF FILE
