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
"""

# IMPORTS

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import (
    audio_assembly_service,
    audio_blocks_artifact_service,
    audio_blocks_service,
    audio_blocks_state_service,
    project_workspace_service,
    speech_blocks_service,
    text_cleanup_state_service,
    ui_state_service,
    workflow_impact_service,
)
from audiomancer.ui.controllers import (
    misc_ui_controller,
    operation_runner_controller,
    tts_runtime_ui_support,
    workflow_controller_service,
)

_ = operation_runner_controller

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


def handle_start_generation_requested(window: "MainWindow") -> None:
    """
    @brief      Validate and start or continue one Audio Blocks run.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
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

    scene_ambience_audio_enabled = window._audio_blocks_page.scene_ambience_audio_enabled()
    report = audio_blocks_service.load_audio_blocks_report(window._current_project_root)
    if _has_fully_generated_run(window._current_project_root, report, scene_ambience_audio_enabled):
        return

    probe_result = tts_runtime_ui_support.probe_runtime_and_persist_cache(window)
    if not bool(probe_result.get("success", False)):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(probe_result.get("message", "")),
        )
        return
    runtime_settings = _runtime_settings(window, probe_result, scene_ambience_audio_enabled)
    if not _confirm_generation(window, current_language):
        return
    if scene_ambience_audio_enabled and not _confirm_scene_ambience_audio_blocks(window, current_language):
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
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    if not _confirm_audio_approval_change(window, current_language):
        return
    audio_blocks_service.approve_all_audio_blocks(window._current_project_root)
    _reset_audio_assembly_after_audio_blocks_change(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.audio_blocks_approved_all", current_language),
    )


def handle_approve_selected_requested(window: "MainWindow", speech_block_id: str) -> None:
    """
    @brief      Toggle approval for one generated Audio Blocks entry.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Selected speech-block identifier.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    audio_block = _audio_block_by_id(window, speech_block_id)
    was_approved = audio_blocks_service.is_approved(audio_block) if isinstance(audio_block, dict) else False
    if not _confirm_audio_approval_change(window, current_language):
        return
    try:
        if was_approved:
            audio_blocks_service.unapprove_audio_block(window._current_project_root, speech_block_id)
        else:
            audio_blocks_service.approve_audio_block(window._current_project_root, speech_block_id)
    except ValueError as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return
    _reset_audio_assembly_after_audio_blocks_change(window, refresh_page=False)
    _refresh_audio_blocks_incremental_state(window, speech_block_id)
    if was_approved:
        window._audio_blocks_page.select_block_id(str(speech_block_id).strip())
        message_key = "status.audio_block_unapproved"
    else:
        window._audio_blocks_page.advance_to_next_block()
        message_key = "status.audio_block_approved"
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(message_key, current_language),
    )


def handle_regenerate_selected_requested(window: "MainWindow", speech_block_id: str) -> None:
    """
    @brief      Re-generate one selected Audio Blocks entry through VoiceWeaver.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Selected speech-block identifier.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._active_operation_kind is not None:
        return
    if window._current_project_root is None or window._current_manifest is None:
        return
    if not _confirm_selected_audio_block_regeneration(window, current_language):
        return
    probe_result = tts_runtime_ui_support.probe_runtime_and_persist_cache(window)
    if not bool(probe_result.get("success", False)):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(probe_result.get("message", "")),
        )
        return
    scene_ambience_audio_enabled = window._audio_blocks_page.scene_ambience_audio_enabled()
    runtime_settings = _runtime_settings(window, probe_result, scene_ambience_audio_enabled)
    speech_blocks_review_position = _speech_blocks_review_position(window)
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
        preserved_speech_blocks_review_position=speech_blocks_review_position,
    )


def handle_selected_playback_toggle_requested(window: "MainWindow", speech_block_id: str) -> None:
    """
    @brief      Start or stop playback of the selected generated Audio Block WAV.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Selected speech-block identifier.
    @return     None.
    @exception  None
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
    _set_speech_blocks_selected_audio_playback_active(window, True)
    window._audio_blocks_audio_player.play()


def handle_audiobook_playback_toggle_requested(window: "MainWindow") -> None:
    """
    @brief      Start or stop sequential playback from the selected generated Audio Block.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
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
    """
    if window._audio_blocks_audio_player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
        return
    if window._audio_blocks_playback_mode is None:
        window._audio_blocks_page.set_selected_playback_active(False)
        window._audio_blocks_page.set_audiobook_playback_active(False)
        _set_speech_blocks_selected_audio_playback_active(window, False)


def handle_media_status_changed(window: "MainWindow", media_status: QMediaPlayer.MediaStatus) -> None:
    """
    @brief      Advance audiobook playback when one Audio Block reaches the end.
    @param[in]  window Active main window instance.
    @param[in]  media_status Current Qt media status.
    @return     None.
    @exception  None
    """
    if media_status != QMediaPlayer.MediaStatus.EndOfMedia:
        return
    if window._audio_blocks_playback_mode == "audiobook":
        _play_audio_block_at_index(window, window._audio_blocks_playback_index + 1)
    elif window._audio_blocks_playback_mode == "selected":
        _stop_audio_blocks_playback(window, preserved_block_id=_current_audio_blocks_playback_block_id(window))


def confirm_single_voice_target_invalidation(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask whether one character voice-target change may reset matching generated audio.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the upstream mutation may continue.
    @exception  None
    """
    return _confirm_persisted_audio_blocks_invalidation(
        window,
        language,
        "dialog.confirm_single_voice_target_invalidation_title",
        "project.confirm_single_voice_target_invalidation",
    )


def confirm_narrator_voice_invalidation(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask whether a narrator-voice change may reset matching generated audio.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the upstream mutation may continue.
    @exception  None
    """
    return _confirm_persisted_audio_blocks_invalidation(
        window,
        language,
        "dialog.confirm_narrator_voice_invalidation_title",
        "project.confirm_narrator_voice_invalidation",
    )


def confirm_global_voice_settings_invalidation(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask whether a global voice setting change may reset all generated audio.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the upstream mutation may continue.
    @exception  None
    """
    return _confirm_persisted_audio_blocks_invalidation(
        window,
        language,
        "dialog.confirm_global_voice_settings_invalidation_title",
        "project.confirm_global_voice_settings_invalidation",
    )


def invalidate_audio_blocks_for_voice_targets(
    window: "MainWindow",
    voice_target_ids: list[str] | tuple[str, ...] | set[str],
    *,
    collect_preserved_paths: bool = True,
    progress_callback=None,
) -> None:
    """
    @brief      Reset only Audio Blocks that use selected voice targets and reset Audio Assembly.
    @param[in]  window Active main window instance.
    @param[in]  voice_target_ids Voice target identifiers whose generated audio is stale.
    @param[in]  collect_preserved_paths True to check and report unaffected generated files.
    @param[in]  progress_callback Optional callback accepting percent and translation key.
    @return     None.
    @exception  None
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    normalized_voice_target_ids = {
        str(voice_target_id).strip() for voice_target_id in voice_target_ids if str(voice_target_id).strip()
    }
    if not normalized_voice_target_ids:
        return
    existing_blocks = audio_blocks_service.load_audio_blocks(window._current_project_root)
    existing_clone_profiles = audio_blocks_service.load_voice_clone_profiles(window._current_project_root)
    has_affected_audio_input = any(
        str(block.get("voice_target_id", "")).strip() in normalized_voice_target_ids for block in existing_blocks
    ) or any(
        str(profile.get("voice_target_id", "")).strip() in normalized_voice_target_ids
        for profile in existing_clone_profiles
    )
    if not has_affected_audio_input:
        return

    _emit_voice_invalidation_progress(progress_callback, 55, "progress.narator_voice_change_audio_blocks")
    _stop_audio_blocks_and_assembly_playback(window)
    audio_blocks_service.remove_audio_blocks_for_speech_blocks(
        window._current_project_root,
        (),
        voice_target_ids=normalized_voice_target_ids,
        collect_preserved_paths=collect_preserved_paths,
        preserve_invalidated_blocks=True,
    )
    _emit_voice_invalidation_progress(progress_callback, 75, "progress.narator_voice_change_audio_assembly")
    workflow_impact_service.reset_audio_assembly_outputs(window._current_project_root)
    _emit_voice_invalidation_progress(progress_callback, 85, "progress.narator_voice_change_manifest")
    _sync_manifest_after_selective_audio_invalidation(window)
    _emit_voice_invalidation_progress(progress_callback, 95, "progress.narator_voice_change_refresh")
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _emit_voice_invalidation_progress(progress_callback, percent: int, message_key: str) -> None:
    """
    @brief      Emit one optional synchronous voice-invalidation progress update.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  percent Progress percentage.
    @param[in]  message_key Runtime UI translation key.
    @return     None.
    @exception  None
    """
    if progress_callback is not None:
        progress_callback(percent, message_key)


def invalidate_all_audio_blocks_after_voice_settings_change(window: "MainWindow") -> None:
    """
    @brief      Reset all generated Audio Blocks and Audio Assembly after a global voice setting change.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    """
    if window._current_project_root is None:
        return
    if window._current_manifest is None or not audio_blocks_service.has_persisted_audio_blocks(
        window._current_project_root
    ):
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
    preserved_speech_blocks_review_position: dict[str, object] | None = None,
) -> None:
    """
    @brief      Start one Audio Blocks operation on a worker thread.
    @param[in]  window Active main window instance.
    @param[in]  operation_name Operator-facing operation label.
    @param[in]  initial_message Initial progress-dialog message text.
    @param[in]  worker_callable Callable that performs the operation.
    @param[in]  success_message_key UI string key emitted after success.
    @param[in]  preserved_block_id Optional speech-block id to reselect after page refresh.
    @param[in]  preserved_speech_blocks_review_position Optional Speech Blocks review position to restore.
    @return     None.
    @exception  None
    """
    _stop_audio_blocks_playback(window)
    workflow_controller_service.start_operation(
        window,
        operation_kind="audio_blocks",
        operation_name=operation_name,
        initial_message=initial_message,
        worker_callable=worker_callable,
        set_busy=lambda is_busy: _set_audio_blocks_busy(window, is_busy),
        success_handler=lambda result_payload: _handle_audio_blocks_success(
            window,
            result_payload,
            success_message_key,
            preserved_block_id,
            preserved_speech_blocks_review_position,
        ),
        failure_handler=lambda error: _handle_audio_blocks_failure(
            window,
            error,
            preserved_block_id,
            preserved_speech_blocks_review_position,
        ),
        cancel_handler=lambda message: _handle_audio_blocks_cancelled(
            window,
            message,
            preserved_block_id,
            preserved_speech_blocks_review_position,
        ),
    )


def _handle_audio_blocks_success(
    window: "MainWindow",
    result_payload: object,
    success_message_key: str,
    preserved_block_id: str | None,
    preserved_speech_blocks_review_position: dict[str, object] | None,
) -> None:
    """
    @brief      Refresh Audio Blocks UI state after a successful worker run.
    @param[in]  window Active main window instance.
    @param[in]  result_payload Worker result payload.
    @param[in]  success_message_key UI string key emitted after success.
    @param[in]  preserved_block_id Optional speech-block id to reselect.
    @param[in]  preserved_speech_blocks_review_position Optional Speech Blocks review position to restore.
    @return     None.
    @exception  None
    """
    _ = result_payload
    _reset_audio_assembly_after_audio_blocks_change(window)
    _restore_audio_blocks_selection(window, preserved_block_id)
    _restore_speech_blocks_review_position(window, preserved_speech_blocks_review_position)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(success_message_key, current_language_from_window(window)),
    )


def _handle_audio_blocks_failure(
    window: "MainWindow",
    error: Exception,
    preserved_block_id: str | None,
    preserved_speech_blocks_review_position: dict[str, object] | None,
) -> None:
    """
    @brief      Refresh Audio Blocks UI state after a failed worker run.
    @param[in]  window Active main window instance.
    @param[in]  error Raised operation exception.
    @param[in]  preserved_block_id Optional speech-block id to reselect.
    @param[in]  preserved_speech_blocks_review_position Optional Speech Blocks review position to restore.
    @return     None.
    @exception  None
    """
    _sync_manifest_from_disk(window)
    _restore_audio_blocks_selection(window, preserved_block_id)
    _restore_speech_blocks_review_position(window, preserved_speech_blocks_review_position)
    QMessageBox.warning(
        window,
        ui_state_service.translate("dialog.project_error_title", current_language_from_window(window)),
        str(error),
    )


def _handle_audio_blocks_cancelled(
    window: "MainWindow",
    message: str,
    preserved_block_id: str | None,
    preserved_speech_blocks_review_position: dict[str, object] | None,
) -> None:
    """
    @brief      Refresh Audio Blocks UI state after a cancelled worker run.
    @param[in]  window Active main window instance.
    @param[in]  message Cancellation message.
    @param[in]  preserved_block_id Optional speech-block id to reselect.
    @param[in]  preserved_speech_blocks_review_position Optional Speech Blocks review position to restore.
    @return     None.
    @exception  None
    """
    _ = message
    _sync_manifest_from_disk(window)
    _restore_audio_blocks_selection(window, preserved_block_id)
    _restore_speech_blocks_review_position(window, preserved_speech_blocks_review_position)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.operation_cancelled", current_language_from_window(window)),
    )


def _sync_manifest_from_disk(window: "MainWindow") -> None:
    """
    @brief      Reload persisted Audio Blocks state from disk after failure or cancel.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    """
    workflow_controller_service.sync_manifest_operation_from_disk(
        window,
        "audio_blocks",
        audio_blocks_service.load_operation_state,
    )


def _reset_audio_blocks_and_downstream(window: "MainWindow") -> None:
    """
    @brief      Reset Audio Blocks plus Audio Assembly runtime folders and manifest summaries.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    """
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    _stop_audio_blocks_and_assembly_playback(window)
    audio_blocks_service.reset_audio_blocks(window._current_project_root)
    workflow_impact_service.reset_audio_assembly_outputs(window._current_project_root)
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


def _reset_audio_assembly_after_audio_blocks_change(window: "MainWindow", refresh_page: bool = True) -> None:
    """
    @brief      Clear only Audio Assembly outputs after an Audio Blocks state change.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    _stop_audio_blocks_and_assembly_playback(window)
    workflow_impact_service.reset_audio_assembly_outputs(window._current_project_root)
    _sync_manifest_after_selective_audio_invalidation(window)
    reloaded_manifest = project_workspace_service.load_manifest(window._current_project_root)
    if refresh_page:
        window.show_project_state(window._current_project_root, reloaded_manifest)
    else:
        window.refresh_project_summary(window._current_project_root, reloaded_manifest)


def _sync_manifest_after_selective_audio_invalidation(window: "MainWindow") -> None:
    """
    @brief      Refresh manifest summaries after voice-target Audio Blocks invalidation.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    """
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    default_operations = text_cleanup_state_service.normalized_manifest_operations({})
    operation_state = audio_blocks_service.load_operation_state(window._current_project_root)
    if operation_state is None:
        operations["audio_blocks"] = default_operations["audio_blocks"]
    else:
        operations["audio_blocks"] = project_workspace_service.project_manifest_operation_summary(
            "audio_blocks",
            operation_state,
        )
    operations["audio_assembly"] = default_operations["audio_assembly"]
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
    window._current_manifest = project_workspace_service.load_manifest(window._current_project_root)


def _stop_audio_blocks_and_assembly_playback(window: "MainWindow") -> None:
    """
    @brief      Stop Audio Blocks and Audio Assembly playback before deleting audio artifacts.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    """
    _stop_audio_blocks_playback(window)
    audio_assembly_player = getattr(window, "_audio_assembly_audio_player", None)
    if audio_assembly_player is not None:
        audio_assembly_player.stop()
    if hasattr(window, "_audio_assembly_page"):
        window._audio_assembly_page.set_playback_active(False)
    if hasattr(window, "_audio_assembly_playback_output_key"):
        window._audio_assembly_playback_output_key = None


def _confirm_persisted_audio_blocks_invalidation(
    window: "MainWindow",
    language: str,
    title_key: str,
    message_key: str,
) -> bool:
    """
    @brief      Ask one localized confirmation only when Audio Blocks data exists.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @param[in]  title_key UI title translation key.
    @param[in]  message_key UI message translation key.
    @return     True when no persisted audio exists or the operator confirms.
    @exception  None
    """
    if window._current_project_root is None:
        return True
    if not audio_blocks_service.has_persisted_audio_blocks(window._current_project_root):
        return True
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate(title_key, language),
            ui_state_service.translate(message_key, language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_audio_approval_change(window: "MainWindow", language: str) -> bool:
    """
    @brief      Confirm approval changes when existing Audio Assembly outputs will be reset.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the approval change may continue.
    @exception  None
    """
    if window._current_project_root is None:
        return True
    if not audio_assembly_service.has_persisted_audio_assembly(window._current_project_root):
        return True
    return _confirm_question(
        window,
        language,
        "dialog.confirm_audio_block_approval_title",
        "project.confirm_audio_block_approval_change",
    )


def _confirm_selected_audio_block_regeneration(window: "MainWindow", language: str) -> bool:
    """
    @brief      Confirm replacement of one selected Audio Block and downstream assembly reset.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when regeneration may continue.
    @exception  None
    """
    return _confirm_question(
        window,
        language,
        "dialog.confirm_audio_block_regeneration_title",
        "project.confirm_audio_block_regeneration",
    )


def _confirm_question(window: "MainWindow", language: str, title_key: str, message_key: str) -> bool:
    """
    @brief      Ask one localized yes/no confirmation.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @param[in]  title_key Translation key for the dialog title.
    @param[in]  message_key Translation key for the dialog body.
    @return     True when the operator confirms.
    @exception  None
    """
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate(title_key, language),
            ui_state_service.translate(message_key, language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def _runtime_settings(
    window: "MainWindow",
    probe_result: dict[str, object],
    scene_ambience_audio_enabled: bool = False,
) -> dict[str, object]:
    """
    @brief      Build the runtime-settings payload required by the Audio Blocks service.
    @param[in]  window Active main window instance.
    @param[in]  probe_result Normalized VoiceWeaver probe result.
    @return     Audio Blocks runtime-settings payload.
    @exception  None
    """
    timeout_value = window._settings_payload.get(
        "tts_audio_generation_timeout_seconds",
        config.DEFAULT_TTS_AUDIO_GENERATION_TIMEOUT_SECONDS,
    )
    timeout_seconds = timeout_value if isinstance(timeout_value, int) and timeout_value > 0 else 300
    scene_ambience_seed = window._settings_payload.get("scene_ambience_seed", config.DEFAULT_SCENE_AMBIENCE_SEED)
    return {
        "base_url": str(window._settings_payload.get("tts_runtime_base_url", "")).strip(),
        "runtime_api_key": str(window._settings_payload.get("tts_runtime_api_key", "")),
        "timeout_seconds": timeout_seconds,
        "discovered_models": list(probe_result.get("discovered_models", [])),
        "generate_scene_ambience_audio": bool(scene_ambience_audio_enabled),
        "scene_ambience_duration_seconds": float(
            window._settings_payload.get(
                "scene_ambience_duration_seconds",
                config.DEFAULT_SCENE_AMBIENCE_DURATION_SECONDS,
            )
        ),
        "scene_ambience_guidance_scale": float(
            window._settings_payload.get(
                "scene_ambience_guidance_scale",
                config.DEFAULT_SCENE_AMBIENCE_GUIDANCE_SCALE,
            )
        ),
        "scene_ambience_num_inference_steps": int(
            window._settings_payload.get(
                "scene_ambience_num_inference_steps",
                config.DEFAULT_SCENE_AMBIENCE_NUM_INFERENCE_STEPS,
            )
        ),
        "scene_ambience_seed": scene_ambience_seed if isinstance(scene_ambience_seed, int) else None,
    }


def _has_fully_generated_run(
    project_root: str | Path,
    report: dict[str, object] | None,
    scene_ambience_audio_enabled: bool = False,
) -> bool:
    """
    @brief      Return whether Audio Blocks already generated every speech-block WAV for the current inputs.
    @param[in]  project_root Active project root folder.
    @param[in]  report Persisted Audio Blocks report or `None`.
    @return     `True` when generation is fully complete even if approvals are pending.
    @exception  None
    """
    if not isinstance(report, dict):
        return False
    speech_blocks = speech_blocks_service.sort_speech_blocks(speech_blocks_service.load_speech_blocks(project_root))
    audio_by_speech_block_id = {
        str(block.get("speech_block_id", "")).strip(): block
        for block in audio_blocks_service.load_audio_blocks(project_root)
    }
    approved_block_ids = [
        str(block.get("speech_block_id", "")).strip()
        for block in speech_blocks
        if bool(block.get("approved", False))
        and str(block.get("speech_block_id", "")).strip()
        and (
            scene_ambience_audio_enabled
            or str(block.get("content_kind", "")).strip() != speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
        )
    ]
    if not approved_block_ids:
        return False
    return all(
        audio_blocks_service.is_generated(audio_by_speech_block_id.get(block_id, {})) for block_id in approved_block_ids
    )


def _confirm_generation(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator whether one Audio Blocks generation should start or continue.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the operator confirms the run.
    @exception  None
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


def _confirm_scene_ambience_audio_blocks(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask before enabling Scene Ambience sound generation.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the operator confirms ambience sound generation.
    @exception  None
    """
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.confirm_scene_ambience_audio_blocks_title", language),
            ui_state_service.translate("project.confirm_scene_ambience_audio_blocks", language),
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
    """
    if window._current_project_root is None:
        return None
    normalized_block_id = str(speech_block_id).strip()
    audio_block = next(
        (
            block
            for block in audio_blocks_service.load_audio_blocks(window._current_project_root)
            if str(block.get("speech_block_id", "")).strip() == normalized_block_id
        ),
        None,
    )
    if audio_block is not None:
        return audio_block
    return next(
        (
            _preview_pause_block_from_speech_block(speech_block)
            for speech_block in speech_blocks_service.load_speech_blocks(window._current_project_root)
            if str(speech_block.get("speech_block_id", "")).strip() == normalized_block_id
        ),
        None,
    )


def _refresh_audio_blocks_incremental_state(window: "MainWindow", speech_block_id: str) -> None:
    """
    @brief      Refresh one Audio Blocks row plus notes and progress without rebuilding the list widget.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Changed Speech Block identifier.
    @return     None.
    @exception  None
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    state = audio_blocks_state_service.build_audio_blocks_state(
        window._current_project_root,
        window._current_manifest,
        current_language,
        window._settings_payload,
    )
    normalized_block_id = str(speech_block_id).strip()
    updated_block = next(
        (
            block
            for block in state.get("speech_blocks", [])
            if isinstance(block, dict) and str(block.get("speech_block_id", "")).strip() == normalized_block_id
        ),
        None,
    )
    if isinstance(updated_block, dict):
        window._audio_blocks_page.update_audio_block_item(updated_block)
    window._audio_blocks_page.set_review_summary(
        list(state.get("notes", [])),
        list(state.get("status_lines", [])),
        int(state.get("progress_current", 0)),
        int(state.get("progress_total", 0)),
        int(state.get("progress_percent", 0)),
        can_approve_all=bool(state.get("can_approve_all", False)),
        can_reset=bool(state.get("can_reset", False)),
    )


def _playable_audio_blocks(window: "MainWindow") -> list[dict[str, object]]:
    """
    @brief      Load all generated Audio Blocks that contribute to Audio Blocks preview playback.
    @param[in]  window Active main window instance.
    @return     Ordered playable WAV and metadata-only pause Audio Blocks payload list.
    @exception  None
    """
    if window._current_project_root is None:
        return []
    playable_blocks: list[dict[str, object]] = []
    for audio_block in _audio_blocks_for_playback(window):
        if _audio_path_for_block(window, audio_block) is not None or _is_preview_pause_block(audio_block):
            playable_blocks.append(audio_block)
    return playable_blocks


def _audio_blocks_for_playback(window: "MainWindow") -> list[dict[str, object]]:
    """
    @brief      Merge persisted Audio Blocks with current metadata-only pauses for playback.
    @param[in]  window Active main window instance.
    @return     Ordered Audio Blocks payload list for audiobook preview.
    @exception  None
    """
    if window._current_project_root is None:
        return []
    persisted_blocks = audio_blocks_service.load_audio_blocks(window._current_project_root)
    persisted_by_id = {str(block.get("speech_block_id", "")).strip(): dict(block) for block in persisted_blocks}
    playback_blocks: list[dict[str, object]] = []
    for speech_block in speech_blocks_service.sort_speech_blocks(
        speech_blocks_service.load_speech_blocks(window._current_project_root)
    ):
        speech_block_id = str(speech_block.get("speech_block_id", "")).strip()
        if not speech_block_id:
            continue
        persisted_block = persisted_by_id.get(speech_block_id)
        if persisted_block is not None:
            playback_blocks.append(persisted_block)
            continue
        preview_pause_block = _preview_pause_block_from_speech_block(speech_block)
        if preview_pause_block is not None:
            playback_blocks.append(preview_pause_block)
    return speech_blocks_service.sort_speech_blocks(playback_blocks)


def _preview_pause_block_from_speech_block(speech_block: dict[str, object]) -> dict[str, object] | None:
    """
    @brief      Build a metadata-only Audio Blocks preview entry from one current pause Speech Block.
    @param[in]  speech_block Speech Blocks payload.
    @return     Preview-ready pause Audio Block payload, or `None` for non-pause input.
    @exception  None
    """
    content_kind = str(speech_block.get("content_kind", "")).strip()
    if content_kind != speech_blocks_service.CONTENT_KIND_PAUSE:
        return None
    pause_duration_ms = speech_blocks_service.pause_duration_ms(speech_block.get("text", ""))
    if pause_duration_ms <= 0:
        pause_duration_ms = config.DEFAULT_SPEECH_BLOCK_PAUSE_DURATION_MS
    speaker_display_name = str(speech_block.get("speaker_display_name", "")).strip() or "Narrator"
    return {
        "speech_block_id": str(speech_block.get("speech_block_id", "")).strip(),
        "sequence_index": int(speech_block.get("sequence_index", 0)),
        "chunk_id": str(speech_block.get("chunk_id", "")).strip(),
        "speaker_id": str(speech_block.get("speaker_id", "")).strip(),
        "speaker_display_name": speaker_display_name,
        "normalized_speaker_name": audio_blocks_service.normalize_speaker_name(speaker_display_name),
        "content_kind": speech_blocks_service.CONTENT_KIND_PAUSE,
        "metadata_only": True,
        "special_block_status": "implemented",
        "pause_duration_ms": pause_duration_ms,
        "speech_block_approved": bool(speech_block.get("approved", False)),
        "text": str(speech_block.get("text", "")),
        "voice_target_id": "",
        "voice_source_kind": "",
        "audio_duration_seconds": pause_duration_ms / 1000.0,
        "generated": True,
        "approved": True,
        "runtime_result_summary": "Metadata-only pause block; silence is added during Audio Blocks playback.",
    }


def _is_preview_pause_block(audio_block: dict[str, object] | None) -> bool:
    """
    @brief      Return whether one Audio Blocks entry should preview as timed silence.
    @param[in]  audio_block Candidate Audio Blocks payload.
    @return     True when the entry is a generated metadata-only pause block.
    @exception  None
    """
    if not isinstance(audio_block, dict) or not audio_blocks_service.is_generated(audio_block):
        return False
    return (
        bool(audio_block.get("metadata_only", False))
        and str(audio_block.get("content_kind", "")).strip() == speech_blocks_service.CONTENT_KIND_PAUSE
    )


def _preview_pause_duration_ms(audio_block: dict[str, object]) -> int:
    """
    @brief      Resolve the Audio Blocks preview pause duration.
    @param[in]  audio_block Pause Audio Blocks payload.
    @return     Positive pause duration in milliseconds.
    @exception  None
    """
    try:
        duration_ms = int(audio_block.get("pause_duration_ms"))
    except (TypeError, ValueError):
        duration_ms = config.DEFAULT_SPEECH_BLOCK_PAUSE_DURATION_MS
    return duration_ms if duration_ms > 0 else config.DEFAULT_SPEECH_BLOCK_PAUSE_DURATION_MS


def _audio_path_for_block(window: "MainWindow", audio_block: dict[str, object] | None) -> Path | None:
    """
    @brief      Resolve the existing local WAV path for one Audio Blocks payload.
    @param[in]  window Active main window instance.
    @param[in]  audio_block Candidate Audio Blocks payload.
    @return     Existing audio path or `None`.
    @exception  None
    """
    if window._current_project_root is None or not isinstance(audio_block, dict):
        return None
    if not audio_blocks_service.is_generated(audio_block):
        return None
    speech_block_id = str(audio_block.get("speech_block_id", "")).strip()
    if not speech_block_id:
        return None
    audio_path = audio_blocks_artifact_service.audio_artifact_path(
        window._current_project_root,
        speech_block_id,
    )
    return audio_path if audio_path.is_file() else None


def _playback_start_index(playable_blocks: list[dict[str, object]], selected_block_id: str | None) -> int:
    """
    @brief      Resolve the audiobook start index from the selected block.
    @param[in]  playable_blocks Ordered playable Audio Blocks payload list.
    @param[in]  selected_block_id Currently selected speech-block identifier.
    @return     Zero-based playable block index.
    @exception  None
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
    """
    if playback_index < 0 or playback_index >= len(window._audio_blocks_playback_block_ids):
        _stop_audio_blocks_playback(window)
        return
    speech_block_id = window._audio_blocks_playback_block_ids[playback_index]
    audio_block = _audio_block_by_id(window, speech_block_id)
    if _is_preview_pause_block(audio_block):
        window._audio_blocks_playback_index = playback_index
        window._audio_blocks_page.select_block_id(speech_block_id)
        QTimer.singleShot(
            _preview_pause_duration_ms(audio_block),
            lambda expected_index=playback_index: _continue_audiobook_after_pause(window, expected_index),
        )
        return
    audio_path = _audio_path_for_block(window, audio_block)
    if audio_path is None:
        _play_audio_block_at_index(window, playback_index + 1)
        return
    window._audio_blocks_playback_index = playback_index
    window._audio_blocks_page.select_block_id(speech_block_id)
    window._audio_blocks_audio_player.setSource(QUrl.fromLocalFile(str(audio_path)))
    window._audio_blocks_audio_player.play()


def _continue_audiobook_after_pause(window: "MainWindow", expected_index: int) -> None:
    """
    @brief      Continue Audio Blocks audiobook preview after one metadata-only pause.
    @param[in]  window Active main window instance.
    @param[in]  expected_index Playback index that scheduled the pause.
    @return     None.
    @exception  None
    """
    if window._audio_blocks_playback_mode != "audiobook":
        return
    if int(window._audio_blocks_playback_index) != int(expected_index):
        return
    _play_audio_block_at_index(window, expected_index + 1)


def _current_audio_blocks_playback_block_id(window: "MainWindow") -> str | None:
    """
    @brief      Resolve the currently playing Audio Blocks speech-block id.
    @param[in]  window Active main window instance.
    @return     Current playback speech-block id, or `None`.
    @exception  None
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
    """
    window._audio_blocks_playback_mode = None
    window._audio_blocks_playback_block_ids = []
    window._audio_blocks_playback_index = -1
    window._audio_blocks_audio_player.stop()
    window._audio_blocks_audio_player.setSource(QUrl())
    window._audio_blocks_page.set_selected_playback_active(False)
    window._audio_blocks_page.set_audiobook_playback_active(False)
    _set_speech_blocks_selected_audio_playback_active(window, False)
    _restore_audio_blocks_selection(window, preserved_block_id)


def _set_audio_blocks_busy(window: "MainWindow", is_busy: bool) -> None:
    """
    @brief      Mirror Audio Blocks operation busy state on pages that expose audio controls.
    @param[in]  window Active main window instance.
    @param[in]  is_busy True while an Audio Blocks operation is running.
    @return     None.
    @exception  None
    """
    window._audio_blocks_page.set_busy(is_busy)
    if hasattr(window, "_speech_blocks_page"):
        window._speech_blocks_page.set_busy(is_busy)


def _set_speech_blocks_selected_audio_playback_active(window: "MainWindow", is_active: bool) -> None:
    """
    @brief      Mirror selected Audio Block playback state on the Speech Blocks page when present.
    @param[in]  window Active main window instance.
    @param[in]  is_active True while selected-block playback is active.
    @return     None.
    @exception  None
    """
    if hasattr(window, "_speech_blocks_page"):
        window._speech_blocks_page.set_selected_audio_playback_active(is_active)


def _restore_audio_blocks_selection(window: "MainWindow", speech_block_id: str | None) -> None:
    """
    @brief      Restore one Audio Blocks row selection when the id is available.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Speech-block identifier to restore.
    @return     None.
    @exception  None
    """
    normalized_block_id = str(speech_block_id or "").strip()
    if normalized_block_id:
        window._audio_blocks_page.select_block_id(normalized_block_id)
        if window._audio_blocks_page.selected_block_id() != normalized_block_id and hasattr(
            window._audio_blocks_page,
            "_current_block_id",
        ):
            window._audio_blocks_page._current_block_id = normalized_block_id  # noqa: SLF001


def _speech_blocks_review_position(window: "MainWindow") -> dict[str, object] | None:
    """
    @brief      Capture Speech Blocks review position when the page exists.
    @param[in]  window Active main window instance.
    @return     Speech Blocks review-position payload or `None`.
    @exception  None
    """
    if not hasattr(window, "_speech_blocks_page"):
        return None
    return window._speech_blocks_page.review_position()


def _restore_speech_blocks_review_position(
    window: "MainWindow",
    review_position: dict[str, object] | None,
) -> None:
    """
    @brief      Restore Speech Blocks review position when the page exists.
    @param[in]  window Active main window instance.
    @param[in]  review_position Review-position payload to restore.
    @return     None.
    @exception  None
    """
    if review_position is None or not hasattr(window, "_speech_blocks_page"):
        return
    window._speech_blocks_page.restore_review_position(review_position)


def _stop_other_audio_previews(window: "MainWindow") -> None:
    """
    @brief      Stop narrator and character voice previews before Audio Blocks playback starts.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    """
    window._narator_voice_audio_player.stop()
    window._character_voices_audio_player.stop()


def current_language_from_window(window: "MainWindow") -> str:
    """
    @brief      Resolve the active UI language from one main window instance.
    @param[in]  window Active main window instance.
    @return     Current UI language code.
    @exception  None
    """
    return ui_state_service.current_language_from_settings(window._settings_payload)


def _stage_rank(stage_token: str) -> int:
    """
    @brief      Convert one stage token into its sortable workflow order index.
    @param[in]  stage_token Stage token to resolve.
    @return     Zero-based stage order index or `-1` when unsupported.
    @exception  None
    """
    if stage_token not in config.PROJECT_WORKFLOW_STAGES:
        return -1
    return config.PROJECT_WORKFLOW_STAGES.index(stage_token)


# END OF FILE
