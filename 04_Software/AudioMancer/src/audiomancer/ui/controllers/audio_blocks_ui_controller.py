#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audio_blocks_ui_controller.py
@brief Audio Blocks page UI controller for AudioMancer.
@details Handles Audio Blocks generation confirmations, modal progress
         lifecycle, approval actions, resumable manifest synchronization, and
         targeted downstream invalidation when upstream voice inputs change.
@author Eng. Dan Dumitru Pasare
@date 2026-04-23
@version 0.2.4
"""

# IMPORTS

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import (
    audio_blocks_service,
    project_workspace_service,
    speech_blocks_service,
    text_cleanup_state_service,
    ui_state_service,
)
from audiomancer.ui.controllers import misc_ui_controller, operation_runner_controller, tts_runtime_ui_support

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


def handle_start_generation_requested(window: "MainWindow") -> None:
    """
    @brief      Validate and start or continue one Audio Blocks run.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
        @version    0.2.0
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

    probe_result = tts_runtime_ui_support.probe_runtime_and_persist_cache(window)
    if not bool(probe_result.get("success", False)):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(probe_result.get("message", "")),
        )
        return
    runtime_settings = _runtime_settings(window, probe_result)
    report = audio_blocks_service.load_audio_blocks_report(window._current_project_root)
    if _has_fully_generated_run(report) and not _confirm_audio_blocks_rerun(window, current_language):
        return
    if _has_fully_generated_run(report):
        _reset_audio_blocks_and_downstream(window)
    if not _confirm_generation(window, current_language):
        return

    _start_operation(
        window,
        operation_name=ui_state_service.translate("audio_blocks.start_generation", current_language),
        initial_message=ui_state_service.translate("progress.audio_blocks", current_language),
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            audio_blocks_service.start_or_continue_generation(
                project_root,
                manifest,
                runtime_settings,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        ),
    )


def handle_reset_generation_requested(window: "MainWindow") -> None:
    """
    @brief      Confirm and reset persisted Audio Blocks plus downstream Audio Assembly data.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    if not _confirm_audio_blocks_reset(window, current_language):
        return
    _reset_audio_blocks_and_downstream(window)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.audio_blocks_reset", current_language),
    )


def handle_approve_all_requested(window: "MainWindow") -> None:
    """
    @brief      Approve every generated Audio Blocks entry without generating missing audio.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    audio_blocks_service.approve_all_audio_blocks(window._current_project_root)
    _sync_manifest_after_audio_blocks_update(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.audio_blocks_approved_all", current_language),
    )


def handle_approve_selected_requested(window: "MainWindow", speech_block_id: str) -> None:
    """
    @brief      Approve one generated Audio Blocks entry.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Selected speech-block identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    try:
        audio_blocks_service.approve_audio_block(window._current_project_root, speech_block_id)
    except ValueError as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return
    _sync_manifest_after_audio_blocks_update(window)
    window._audio_blocks_page.advance_to_next_block()
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.audio_block_approved", current_language),
    )


def handle_regenerate_selected_requested(window: "MainWindow", speech_block_id: str) -> None:
    """
    @brief      Re-generate one selected Audio Blocks entry through VoiceWeaver.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Selected speech-block identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.1
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._active_operation_kind is not None:
        return
    if window._current_project_root is None or window._current_manifest is None:
        return
    probe_result = tts_runtime_ui_support.probe_runtime_and_persist_cache(window)
    if not bool(probe_result.get("success", False)):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(probe_result.get("message", "")),
        )
        return
    runtime_settings = _runtime_settings(window, probe_result)
    _start_operation(
        window,
        operation_name=ui_state_service.translate("audio_blocks.regenerate_selected", current_language),
        initial_message=ui_state_service.translate("progress.audio_block_regeneration", current_language),
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            audio_blocks_service.regenerate_audio_block(
                project_root,
                manifest,
                speech_block_id,
                runtime_settings,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        ),
        success_message_key="status.audio_block_regenerated",
        preserved_block_id=str(speech_block_id).strip(),
    )


def handle_selected_playback_toggle_requested(window: "MainWindow", speech_block_id: str) -> None:
    """
    @brief      Start or stop playback of the selected generated Audio Block WAV.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Selected speech-block identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._audio_blocks_playback_mode == "selected":
        preserved_block_id = _current_audio_blocks_playback_block_id(window) or str(speech_block_id).strip()
        _stop_audio_blocks_playback(window, preserved_block_id=preserved_block_id)
        return
    if window._current_project_root is None:
        return
    audio_block = _audio_block_by_id(window, speech_block_id)
    audio_path = _audio_path_for_block(window, audio_block)
    if audio_path is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("audio_blocks.error_missing_audio", current_language),
        )
        return
    _stop_other_audio_previews(window)
    window._audio_blocks_playback_mode = "selected"
    window._audio_blocks_playback_block_ids = [str(speech_block_id).strip()]
    window._audio_blocks_playback_index = 0
    window._audio_blocks_page.select_block_id(str(speech_block_id))
    window._audio_blocks_audio_player.setSource(QUrl.fromLocalFile(str(audio_path)))
    window._audio_blocks_page.set_selected_playback_active(True)
    window._audio_blocks_audio_player.play()


def handle_audiobook_playback_toggle_requested(window: "MainWindow") -> None:
    """
    @brief      Start or stop sequential playback from the selected generated Audio Block.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._audio_blocks_playback_mode == "audiobook":
        _stop_audio_blocks_playback(window)
        return
    if window._current_project_root is None:
        return
    playable_blocks = _playable_audio_blocks(window)
    if not playable_blocks:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("audio_blocks.error_missing_audio", current_language),
        )
        return
    selected_block_id = window._audio_blocks_page.selected_block_id()
    start_index = _playback_start_index(playable_blocks, selected_block_id)
    _stop_other_audio_previews(window)
    window._audio_blocks_playback_mode = "audiobook"
    window._audio_blocks_playback_block_ids = [
        block_id
        for block_id in (str(block.get("speech_block_id", "")).strip() for block in playable_blocks)
        if block_id
    ]
    window._audio_blocks_playback_index = start_index
    window._audio_blocks_page.set_audiobook_playback_active(True)
    _play_audio_block_at_index(window, start_index)


def handle_playback_state_changed(window: "MainWindow") -> None:
    """
    @brief      Refresh Audio Blocks playback buttons after local playback state changes.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    if window._audio_blocks_audio_player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
        return
    if window._audio_blocks_playback_mode is None:
        window._audio_blocks_page.set_selected_playback_active(False)
        window._audio_blocks_page.set_audiobook_playback_active(False)


def handle_media_status_changed(window: "MainWindow", media_status: QMediaPlayer.MediaStatus) -> None:
    """
    @brief      Advance audiobook playback when one Audio Block reaches the end.
    @param[in]  window Active main window instance.
    @param[in]  media_status Current Qt media status.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    if media_status != QMediaPlayer.MediaStatus.EndOfMedia:
        return
    if window._audio_blocks_playback_mode == "audiobook":
        _play_audio_block_at_index(window, window._audio_blocks_playback_index + 1)
    elif window._audio_blocks_playback_mode == "selected":
        _stop_audio_blocks_playback(window, preserved_block_id=_current_audio_blocks_playback_block_id(window))


def confirm_audio_blocks_invalidation(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator whether upstream voice changes may invalidate persisted Audio Blocks data.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     `True` when the upstream mutation may continue.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    if window._current_project_root is None:
        return True
    if not audio_blocks_service.has_persisted_audio_blocks(window._current_project_root):
        return True
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.confirm_audio_blocks_invalidation_title", language),
            ui_state_service.translate("project.confirm_audio_blocks_invalidation", language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def invalidate_audio_blocks_after_upstream_change(window: "MainWindow") -> None:
    """
    @brief      Reset Audio Blocks plus Audio Assembly after a confirmed upstream mutation.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    if not audio_blocks_service.has_persisted_audio_blocks(window._current_project_root):
        return
    _reset_audio_blocks_and_downstream(window)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _start_operation(
    window: "MainWindow",
    operation_name: str,
    initial_message: str,
    worker_callable,
    success_message_key: str = "status.audio_blocks_generated",
    preserved_block_id: str | None = None,
) -> None:
    """
    @brief      Start one Audio Blocks operation on a worker thread.
    @param[in]  window Active main window instance.
    @param[in]  operation_name Operator-facing operation label.
    @param[in]  initial_message Initial progress-dialog message text.
    @param[in]  worker_callable Callable that performs the operation.
    @param[in]  success_message_key UI string key emitted after success.
    @param[in]  preserved_block_id Optional speech-block id to reselect after page refresh.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.3.0
    """
    _stop_audio_blocks_playback(window)
    operation_runner_controller.start_threaded_operation(
        window,
        "audio_blocks",
        operation_name,
        initial_message,
        worker_callable,
        set_busy=lambda is_busy: window._audio_blocks_page.set_busy(is_busy),
        success_handler=lambda result_payload: _handle_audio_blocks_success(
            window,
            result_payload,
            success_message_key,
            preserved_block_id,
        ),
        failure_handler=lambda error: _handle_audio_blocks_failure(window, error, preserved_block_id),
        cancel_handler=lambda message: _handle_audio_blocks_cancelled(window, message, preserved_block_id),
    )


def _handle_audio_blocks_success(
    window: "MainWindow",
    result_payload: object,
    success_message_key: str,
    preserved_block_id: str | None,
) -> None:
    """
    @brief      Refresh Audio Blocks UI state after a successful worker run.
    @param[in]  window Active main window instance.
    @param[in]  result_payload Worker result payload.
    @param[in]  success_message_key UI string key emitted after success.
    @param[in]  preserved_block_id Optional speech-block id to reselect.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    _ = result_payload
    _sync_manifest_after_audio_blocks_update(window)
    _restore_audio_blocks_selection(window, preserved_block_id)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(success_message_key, current_language_from_window(window)),
    )


def _handle_audio_blocks_failure(
    window: "MainWindow",
    error: Exception,
    preserved_block_id: str | None,
) -> None:
    """
    @brief      Refresh Audio Blocks UI state after a failed worker run.
    @param[in]  window Active main window instance.
    @param[in]  error Raised operation exception.
    @param[in]  preserved_block_id Optional speech-block id to reselect.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    _sync_manifest_from_disk(window)
    _restore_audio_blocks_selection(window, preserved_block_id)
    QMessageBox.warning(
        window,
        ui_state_service.translate("dialog.project_error_title", current_language_from_window(window)),
        str(error),
    )


def _handle_audio_blocks_cancelled(
    window: "MainWindow",
    message: str,
    preserved_block_id: str | None,
) -> None:
    """
    @brief      Refresh Audio Blocks UI state after a cancelled worker run.
    @param[in]  window Active main window instance.
    @param[in]  message Cancellation message.
    @param[in]  preserved_block_id Optional speech-block id to reselect.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    _ = message
    _sync_manifest_from_disk(window)
    _restore_audio_blocks_selection(window, preserved_block_id)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.operation_cancelled", current_language_from_window(window)),
    )


def _sync_manifest_after_audio_blocks_update(window: "MainWindow") -> None:
    """
    @brief      Persist the latest Audio Blocks summary into the manifest and
                advance the stage only when fully approved.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.1
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operation_state = audio_blocks_service.load_operation_state(window._current_project_root)
    if operation_state is not None:
        operations["audio_blocks"] = project_workspace_service.project_manifest_operation_summary(
            "audio_blocks",
            operation_state,
        )
    updated_manifest["operations"] = operations
    report = audio_blocks_service.load_audio_blocks_report(window._current_project_root)
    if (
        isinstance(report, dict)
        and str(report.get("audio_blocks_stage_status", "")).strip()
        == audio_blocks_service.AUDIO_BLOCKS_STAGE_COMPLETED
    ):
        updated_manifest["current_stage"] = "audio_blocks_ready"
    elif _stage_rank(str(updated_manifest.get("current_stage", "")).strip()) > _stage_rank("speech_blocks_ready"):
        updated_manifest["current_stage"] = "speech_blocks_ready"
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _sync_manifest_from_disk(window: "MainWindow") -> None:
    """
    @brief      Reload persisted Audio Blocks state from disk after failure or cancel.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operation_state = audio_blocks_service.load_operation_state(window._current_project_root)
    if operation_state is not None:
        operations["audio_blocks"] = project_workspace_service.project_manifest_operation_summary(
            "audio_blocks",
            operation_state,
        )
    updated_manifest["operations"] = operations
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _reset_audio_blocks_and_downstream(window: "MainWindow") -> None:
    """
    @brief      Reset Audio Blocks plus Audio Assembly runtime folders and manifest summaries.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    _stop_audio_blocks_playback(window)
    audio_assembly_player = getattr(window, "_audio_assembly_audio_player", None)
    if audio_assembly_player is not None:
        audio_assembly_player.stop()
    if hasattr(window, "_audio_assembly_page"):
        window._audio_assembly_page.set_playback_active(False)
    if hasattr(window, "_audio_assembly_playback_output_key"):
        window._audio_assembly_playback_output_key = None
    audio_blocks_service.reset_audio_blocks(window._current_project_root)
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    default_operations = text_cleanup_state_service.normalized_manifest_operations({})
    for operation_kind in ("audio_blocks", "audio_assembly"):
        operations[operation_kind] = default_operations[operation_kind]
    updated_manifest["operations"] = operations
    if _stage_rank(str(updated_manifest.get("current_stage", "")).strip()) > _stage_rank("speech_blocks_ready"):
        updated_manifest["current_stage"] = "speech_blocks_ready"
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window._current_manifest = project_workspace_service.load_manifest(window._current_project_root)


def _runtime_settings(window: "MainWindow", probe_result: dict[str, object]) -> dict[str, object]:
    """
    @brief      Build the runtime-settings payload required by the Audio Blocks service.
    @param[in]  window Active main window instance.
    @param[in]  probe_result Normalized VoiceWeaver probe result.
    @return     Audio Blocks runtime-settings payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    timeout_value = window._settings_payload.get(
        "tts_audio_generation_timeout_seconds",
        config.DEFAULT_TTS_AUDIO_GENERATION_TIMEOUT_SECONDS,
    )
    timeout_seconds = timeout_value if isinstance(timeout_value, int) and timeout_value > 0 else 300
    return {
        "base_url": str(window._settings_payload.get("tts_runtime_base_url", "")).strip(),
        "runtime_api_key": str(window._settings_payload.get("tts_runtime_api_key", "")),
        "timeout_seconds": timeout_seconds,
        "discovered_models": list(probe_result.get("discovered_models", [])),
    }


def _has_fully_generated_run(report: dict[str, object] | None) -> bool:
    """
    @brief      Return whether Audio Blocks already generated every speech-block WAV for the current inputs.
    @param[in]  report Persisted Audio Blocks report or `None`.
    @return     `True` when generation is fully complete even if approvals are pending.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    if not isinstance(report, dict):
        return False
    total_count = int(report.get("total_block_count", 0))
    generated_count = int(report.get("generated_block_count", 0))
    return total_count > 0 and generated_count >= total_count


def _cancel_active_operation(window: "MainWindow") -> None:
    """
    @brief      Mark the active Audio Blocks operation for cancellation.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    if window._active_operation_kind is not None:
        window._operation_cancel_requested = True


def _is_cancel_requested(window: "MainWindow") -> bool:
    """
    @brief      Check whether the current Audio Blocks operation should cancel.
    @param[in]  window Active main window instance.
    @return     True when cancellation was requested.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.1
    """
    return bool(window._operation_cancel_requested)


def _confirm_generation(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator whether one Audio Blocks generation should start or continue.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the operator confirms the run.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.confirm_audio_blocks_title", language),
            ui_state_service.translate("project.confirm_audio_blocks", language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_audio_blocks_rerun(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator whether one completed Audio Blocks generation should rerun destructively.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the operator accepts the rerun reset.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.confirm_audio_blocks_rerun_title", language),
            ui_state_service.translate("project.confirm_audio_blocks_rerun", language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_audio_blocks_reset(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator whether persisted Audio Blocks data should be reset.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the operator confirms the reset.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.confirm_audio_blocks_reset_title", language),
            ui_state_service.translate("project.confirm_audio_blocks_reset", language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def _audio_block_by_id(window: "MainWindow", speech_block_id: str) -> dict[str, object] | None:
    """
    @brief      Resolve one persisted Audio Blocks payload by speech-block identifier.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Speech-block identifier to resolve.
    @return     Audio Blocks payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    if window._current_project_root is None:
        return None
    normalized_block_id = str(speech_block_id).strip()
    return next(
        (
            block
            for block in audio_blocks_service.load_audio_blocks(window._current_project_root)
            if str(block.get("speech_block_id", "")).strip() == normalized_block_id
        ),
        None,
    )


def _playable_audio_blocks(window: "MainWindow") -> list[dict[str, object]]:
    """
    @brief      Load all generated Audio Blocks that have an existing WAV file.
    @param[in]  window Active main window instance.
    @return     Ordered playable Audio Blocks payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    if window._current_project_root is None:
        return []
    playable_blocks: list[dict[str, object]] = []
    for audio_block in speech_blocks_service.sort_speech_blocks(
        audio_blocks_service.load_audio_blocks(window._current_project_root)
    ):
        if _audio_path_for_block(window, audio_block) is not None:
            playable_blocks.append(audio_block)
    return playable_blocks


def _audio_path_for_block(window: "MainWindow", audio_block: dict[str, object] | None) -> Path | None:
    """
    @brief      Resolve the existing local WAV path for one Audio Blocks payload.
    @param[in]  window Active main window instance.
    @param[in]  audio_block Candidate Audio Blocks payload.
    @return     Existing audio path or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    if window._current_project_root is None or not isinstance(audio_block, dict):
        return None
    if not bool(audio_block.get("generated", False)):
        return None
    relative_path = str(audio_block.get("audio_relative_path", "")).strip()
    if not relative_path:
        return None
    audio_path = window._current_project_root / relative_path
    return audio_path if audio_path.is_file() else None


def _playback_start_index(playable_blocks: list[dict[str, object]], selected_block_id: str | None) -> int:
    """
    @brief      Resolve the audiobook start index from the selected block.
    @param[in]  playable_blocks Ordered playable Audio Blocks payload list.
    @param[in]  selected_block_id Currently selected speech-block identifier.
    @return     Zero-based playable block index.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    normalized_selected_id = str(selected_block_id or "").strip()
    if not normalized_selected_id:
        return 0
    for block in playable_blocks:
        if str(block.get("speech_block_id", "")).strip() == normalized_selected_id:
            return playable_blocks.index(block)
    selected_sequence = _selected_sequence_from_id(normalized_selected_id)
    if selected_sequence is None:
        return 0
    for index, block in enumerate(playable_blocks):
        if int(block.get("sequence_index", 0)) >= selected_sequence:
            return index
    return 0


def _selected_sequence_from_id(selected_block_id: str) -> int | None:
    """
    @brief      Resolve one selected sequence index when the selected block is not playable.
    @param[in]  selected_block_id Currently selected speech-block identifier.
    @return     Sequence index or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    try:
        return int(str(selected_block_id).rsplit("-", maxsplit=1)[-1])
    except ValueError:
        return None


def _play_audio_block_at_index(window: "MainWindow", playback_index: int) -> None:
    """
    @brief      Start playback of one Audio Blocks sequence entry by playback-list index.
    @param[in]  window Active main window instance.
    @param[in]  playback_index Zero-based playback-list index.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    if playback_index < 0 or playback_index >= len(window._audio_blocks_playback_block_ids):
        _stop_audio_blocks_playback(window)
        return
    speech_block_id = window._audio_blocks_playback_block_ids[playback_index]
    audio_block = _audio_block_by_id(window, speech_block_id)
    audio_path = _audio_path_for_block(window, audio_block)
    if audio_path is None:
        _play_audio_block_at_index(window, playback_index + 1)
        return
    window._audio_blocks_playback_index = playback_index
    window._audio_blocks_page.select_block_id(speech_block_id)
    window._audio_blocks_audio_player.setSource(QUrl.fromLocalFile(str(audio_path)))
    window._audio_blocks_audio_player.play()


def _current_audio_blocks_playback_block_id(window: "MainWindow") -> str | None:
    """
    @brief      Resolve the currently playing Audio Blocks speech-block id.
    @param[in]  window Active main window instance.
    @return     Current playback speech-block id, or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    playback_index = int(window._audio_blocks_playback_index)
    if playback_index < 0 or playback_index >= len(window._audio_blocks_playback_block_ids):
        return None
    return str(window._audio_blocks_playback_block_ids[playback_index]).strip() or None


def _stop_audio_blocks_playback(window: "MainWindow", preserved_block_id: str | None = None) -> None:
    """
    @brief      Stop Audio Blocks playback and reset page playback buttons.
    @param[in]  window Active main window instance.
    @param[in]  preserved_block_id Optional speech-block id to keep selected.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    window._audio_blocks_playback_mode = None
    window._audio_blocks_playback_block_ids = []
    window._audio_blocks_playback_index = -1
    window._audio_blocks_audio_player.stop()
    window._audio_blocks_audio_player.setSource(QUrl())
    window._audio_blocks_page.set_selected_playback_active(False)
    window._audio_blocks_page.set_audiobook_playback_active(False)
    _restore_audio_blocks_selection(window, preserved_block_id)


def _restore_audio_blocks_selection(window: "MainWindow", speech_block_id: str | None) -> None:
    """
    @brief      Restore one Audio Blocks row selection when the id is available.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Speech-block identifier to restore.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    normalized_block_id = str(speech_block_id or "").strip()
    if normalized_block_id:
        window._audio_blocks_page.select_block_id(normalized_block_id)


def _stop_other_audio_previews(window: "MainWindow") -> None:
    """
    @brief      Stop narrator and character voice previews before Audio Blocks playback starts.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    window._narator_voice_audio_player.stop()
    window._character_voices_audio_player.stop()


def current_language_from_window(window: "MainWindow") -> str:
    """
    @brief      Resolve the active UI language from one main window instance.
    @param[in]  window Active main window instance.
    @return     Current UI language code.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    return ui_state_service.current_language_from_settings(window._settings_payload)


def _stage_rank(stage_token: str) -> int:
    """
    @brief      Convert one stage token into its sortable workflow order index.
    @param[in]  stage_token Stage token to resolve.
    @return     Zero-based stage order index or `-1` when unsupported.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    if stage_token not in config.PROJECT_WORKFLOW_STAGES:
        return -1
    return config.PROJECT_WORKFLOW_STAGES.index(stage_token)


# END OF FILE
