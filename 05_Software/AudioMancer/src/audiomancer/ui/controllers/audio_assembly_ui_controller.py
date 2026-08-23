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
         threaded operation lifecycle, Scene Ambience mix previews,
         generated-output playback, and manifest synchronization for the Audio
         Assembly workflow.
"""

# IMPORTS

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QMessageBox

from audiomancer.services import (
    audio_assembly_service,
    operation_runtime_service,
    project_workspace_service,
    text_cleanup_state_service,
    ui_state_service,
    workflow_impact_service,
)
from audiomancer.ui.controllers import (
    misc_ui_controller,
    operation_runner_controller,
    workflow_controller_service,
)

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


def handle_settings_changed(window: "MainWindow", settings: dict[str, object]) -> None:
    """
    @brief      Persist Audio Assembly page settings into the active manifest.
    @param[in]  window Active main window instance.
    @param[in]  settings Candidate Audio Assembly settings.
    @return     None.
    @exception  None
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    _save_audio_assembly_settings(window, settings, current_language)


def handle_generate_requested(window: "MainWindow", settings: dict[str, object]) -> None:
    """
    @brief      Confirm and start or continue Audio Assembly composition.
    @param[in]  window Active main window instance.
    @param[in]  settings Candidate Audio Assembly settings.
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
    if not _save_audio_assembly_settings(window, settings, current_language):
        return
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
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    if not _confirm_audio_assembly_reset(window, current_language):
        return
    _stop_audio_assembly_playback(window)
    workflow_impact_service.reset_audio_assembly_outputs(window._current_project_root)
    _sync_manifest_after_audio_assembly_reset(window)
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
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if _is_audio_assembly_playback_active(window):
        _stop_audio_assembly_playback(window)
        return
    _start_audio_assembly_playback(window, output_key, current_language)


def handle_playback_restart_requested(window: "MainWindow", output_key: str) -> None:
    """
    @brief      Restart playback from the beginning of one generated output file.
    @param[in]  window Active main window instance.
    @param[in]  output_key Selected output key.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if _is_audio_assembly_playback_active(window):
        _stop_audio_assembly_playback(window)
    _start_audio_assembly_playback(window, output_key, current_language)


def handle_scene_mix_generate_requested(window: "MainWindow", group_key: str) -> None:
    """
    @brief      Generate or refresh one Scene Ambience mix preview.
    @param[in]  window Active main window instance.
    @param[in]  group_key Selected Scene Ambience mix key.
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
    _stop_audio_assembly_playback(window)
    operation_runner_controller.start_threaded_operation(
        window,
        "audio_assembly_scene_mix",
        ui_state_service.translate("audio_assembly.generate_scene_mix", current_language),
        ui_state_service.translate("progress.scene_mix_preview", current_language),
        lambda project_root, _manifest, progress_callback=None, cancel_requested=None: (
            audio_assembly_service.generate_scene_mix_preview(
                project_root,
                group_key,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        ),
        set_busy=lambda is_busy: window._audio_assembly_page.set_busy(is_busy),
        success_handler=lambda result_payload: _handle_scene_mix_success(window, result_payload),
        failure_handler=lambda error: _handle_failure(window, error),
        cancel_handler=lambda message: _handle_cancelled(window, message),
    )


def handle_scene_mix_playback_toggle_requested(window: "MainWindow", group_key: str) -> None:
    """
    @brief      Start or stop playback of one generated Scene Ambience mix preview.
    @param[in]  window Active main window instance.
    @param[in]  group_key Selected Scene Ambience mix key.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if _is_audio_assembly_playback_active(window):
        _stop_audio_assembly_playback(window)
        return
    _start_scene_mix_playback(window, group_key, current_language)


def _start_audio_assembly_playback(window: "MainWindow", output_key: str, current_language: str) -> None:
    """
    @brief      Start playback of one generated Audio Assembly output from the beginning.
    @param[in]  window Active main window instance.
    @param[in]  output_key Selected output key.
    @param[in]  current_language Runtime UI language code.
    @return     None.
    @exception  None
    """
    normalized_output_key = str(output_key).strip()
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
        window._audio_assembly_page.set_playback_progress(0, _output_duration_ms(output_record))
        window._audio_assembly_audio_player.setPosition(0)
        window._audio_assembly_audio_player.play()
    finally:
        window._audio_assembly_playback_starting = False


def _start_scene_mix_playback(window: "MainWindow", group_key: str, current_language: str) -> None:
    """
    @brief      Start playback of one generated Scene Ambience mix preview.
    @param[in]  window Active main window instance.
    @param[in]  group_key Selected Scene Ambience mix key.
    @param[in]  current_language Runtime UI language code.
    @return     None.
    @exception  None
    """
    normalized_group_key = str(group_key).strip()
    if window._current_project_root is None:
        return
    group_record = _scene_mix_by_key(window, normalized_group_key)
    output_path = _scene_mix_audio_path(window, group_record)
    if output_path is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("audio_assembly.error_missing_scene_mix", current_language),
        )
        return
    _stop_other_audio_previews(window)
    window._audio_assembly_playback_output_key = f"scene_mix:{normalized_group_key}"
    window._audio_assembly_playback_starting = True
    try:
        window._audio_assembly_audio_player.setSource(QUrl.fromLocalFile(str(output_path)))
        window._audio_assembly_page.set_playback_active(True)
        window._audio_assembly_page.set_playback_progress(0, _output_duration_ms(group_record))
        window._audio_assembly_audio_player.setPosition(0)
        window._audio_assembly_audio_player.play()
    finally:
        window._audio_assembly_playback_starting = False


def handle_playback_state_changed(window: "MainWindow") -> None:
    """
    @brief      Refresh Audio Assembly playback state after local playback changes.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    """
    if bool(getattr(window, "_audio_assembly_playback_starting", False)):
        return
    if window._audio_assembly_audio_player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
        return
    window._audio_assembly_playback_output_key = None
    window._audio_assembly_page.set_playback_active(False)
    window._audio_assembly_page.set_playback_progress(0, _media_duration_ms(window._audio_assembly_audio_player))


def handle_playback_position_changed(window: "MainWindow", position_ms: int) -> None:
    """
    @brief      Refresh Audio Assembly page progress after player position changes.
    @param[in]  window Active main window instance.
    @param[in]  position_ms Current media position in milliseconds.
    @return     None.
    @exception  None
    """
    player = getattr(window, "_audio_assembly_audio_player", None)
    page = getattr(window, "_audio_assembly_page", None)
    if player is None or page is None:
        return
    page.set_playback_progress(position_ms, _media_duration_ms(player))


def handle_playback_duration_changed(window: "MainWindow", duration_ms: int) -> None:
    """
    @brief      Refresh Audio Assembly page progress after player duration changes.
    @param[in]  window Active main window instance.
    @param[in]  duration_ms Current media duration in milliseconds.
    @return     None.
    @exception  None
    """
    player = getattr(window, "_audio_assembly_audio_player", None)
    page = getattr(window, "_audio_assembly_page", None)
    if player is None or page is None:
        return
    page.set_playback_progress(_media_position_ms(player), duration_ms)


def handle_playback_seek_requested(window: "MainWindow", position_ms: int) -> None:
    """
    @brief      Seek the current Audio Assembly player to an absolute position.
    @param[in]  window Active main window instance.
    @param[in]  position_ms Requested playback position in milliseconds.
    @return     None.
    @exception  None
    """
    player = getattr(window, "_audio_assembly_audio_player", None)
    if player is None:
        return
    player.setPosition(_clamped_position_ms(position_ms, _media_duration_ms(player)))


def handle_playback_skip_requested(window: "MainWindow", delta_ms: int) -> None:
    """
    @brief      Seek the current Audio Assembly player by a relative offset.
    @param[in]  window Active main window instance.
    @param[in]  delta_ms Requested relative offset in milliseconds.
    @return     None.
    @exception  None
    """
    player = getattr(window, "_audio_assembly_audio_player", None)
    if player is None:
        return
    player.setPosition(_clamped_position_ms(_media_position_ms(player) + int(delta_ms), _media_duration_ms(player)))


def _handle_success(window: "MainWindow", result_payload: object) -> None:
    """
    @brief      Refresh state after successful Audio Assembly composition.
    @param[in]  window Active main window instance.
    @param[in]  result_payload Worker result payload.
    @return     None.
    @exception  None
    """
    _ = result_payload
    _sync_manifest_after_audio_assembly_update(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.audio_assembly_generated",
            workflow_controller_service.current_language_from_window(window),
        ),
    )


def _handle_scene_mix_success(window: "MainWindow", result_payload: object) -> None:
    """
    @brief      Refresh state after successful Scene Mix preview generation.
    @param[in]  window Active main window instance.
    @param[in]  result_payload Worker result payload.
    @return     None.
    @exception  None
    """
    _ = result_payload
    if window._current_project_root is None:
        return
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.audio_assembly_scene_mix_generated",
            workflow_controller_service.current_language_from_window(window),
        ),
    )


def _handle_failure(window: "MainWindow", error: Exception) -> None:
    """
    @brief      Refresh state and show an Audio Assembly operation failure.
    @param[in]  window Active main window instance.
    @param[in]  error Raised worker exception.
    @return     None.
    @exception  None
    """
    _sync_manifest_from_disk(window)
    QMessageBox.warning(
        window,
        ui_state_service.translate(
            "dialog.project_error_title",
            workflow_controller_service.current_language_from_window(window),
        ),
        str(error),
    )


def _handle_cancelled(window: "MainWindow", message: str) -> None:
    """
    @brief      Refresh state after Audio Assembly cancellation.
    @param[in]  window Active main window instance.
    @param[in]  message Cancellation message.
    @return     None.
    @exception  None
    """
    _ = message
    _sync_manifest_from_disk(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.operation_cancelled",
            workflow_controller_service.current_language_from_window(window),
        ),
    )


def _sync_manifest_after_audio_assembly_update(window: "MainWindow") -> None:
    """
    @brief      Synchronize manifest summary after an Audio Assembly data change.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
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
    elif workflow_controller_service.stage_rank(
        str(updated_manifest.get("current_stage", "")).strip(),
        unknown_rank=0,
    ) > workflow_controller_service.stage_rank("audio_blocks_ready", unknown_rank=0):
        updated_manifest["current_stage"] = "audio_blocks_ready"
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _sync_manifest_after_audio_assembly_reset(window: "MainWindow") -> None:
    """
    @brief      Synchronize manifest summary after Audio Assembly outputs are reset.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    default_operations = text_cleanup_state_service.normalized_manifest_operations({})
    operations["audio_assembly"] = default_operations["audio_assembly"]
    updated_manifest["operations"] = operations
    if workflow_controller_service.stage_rank(
        str(updated_manifest.get("current_stage", "")).strip(),
        unknown_rank=0,
    ) > workflow_controller_service.stage_rank("audio_blocks_ready", unknown_rank=0):
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


def _save_audio_assembly_settings(window: "MainWindow", settings: dict[str, object], language: str) -> bool:
    """
    @brief      Persist Audio Assembly settings and reset assembly outputs when changed settings stale them.
    @param[in]  window Active main window instance.
    @param[in]  settings Candidate Audio Assembly settings.
    @param[in]  language Current UI language code.
    @return     True when settings were saved or unchanged.
    @exception  None
    """
    if window._current_project_root is None or window._current_manifest is None:
        return False
    current_settings = audio_assembly_service.normalize_audio_assembly_settings(
        window._current_manifest.get("audio_assembly_settings")
    )
    candidate_settings = audio_assembly_service.normalize_audio_assembly_settings(settings)
    settings_changed = current_settings != candidate_settings
    if (
        settings_changed
        and audio_assembly_service.has_persisted_audio_assembly(window._current_project_root)
        and not _confirm_audio_assembly_settings_change(window, language)
    ):
        window.show_project_state(window._current_project_root, window._current_manifest)
        return False
    window._current_manifest = audio_assembly_service.save_audio_assembly_settings(
        window._current_project_root,
        window._current_manifest,
        candidate_settings,
    )
    if settings_changed and audio_assembly_service.has_persisted_audio_assembly(window._current_project_root):
        _stop_audio_assembly_playback(window)
        workflow_impact_service.reset_audio_assembly_outputs(window._current_project_root)
        _sync_manifest_after_audio_assembly_reset(window)
        misc_ui_controller.show_message(
            window,
            ui_state_service.translate("status.audio_assembly_settings_saved_reset", language),
        )
        return True
    window.refresh_audio_assembly_page_state()
    return True


def _confirm_audio_assembly(window: "MainWindow", language: str) -> bool:
    return misc_ui_controller.confirm_question(
        window,
        language,
        "dialog.confirm_audio_assembly_title",
        "project.confirm_audio_assembly",
    )


def _confirm_audio_assembly_reset(window: "MainWindow", language: str) -> bool:
    return misc_ui_controller.confirm_question(
        window,
        language,
        "dialog.confirm_audio_assembly_reset_title",
        "project.confirm_audio_assembly_reset",
    )


def _confirm_audio_assembly_settings_change(window: "MainWindow", language: str) -> bool:
    """
    @brief      Confirm that changed assembly settings should clear existing assembly outputs.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when settings may be saved and assembly outputs reset.
    @exception  None
    """
    return misc_ui_controller.confirm_question(
        window,
        language,
        "dialog.confirm_audio_assembly_settings_change_title",
        "project.confirm_audio_assembly_settings_change",
    )


def _scene_mix_by_key(window: "MainWindow", group_key: str) -> dict[str, object] | None:
    """
    @brief      Find one Scene Ambience mix group by key.
    @param[in]  window Active main window instance.
    @param[in]  group_key Scene Ambience mix group key.
    @return     Group record or `None`.
    @exception  None
    """
    if window._current_project_root is None:
        return None
    normalized_group_key = str(group_key).strip()
    return next(
        (
            group
            for group in audio_assembly_service.list_scene_mix_groups(window._current_project_root)
            if str(group.get("group_key", "")).strip() == normalized_group_key
        ),
        None,
    )


def _scene_mix_audio_path(window: "MainWindow", group_record: dict[str, object] | None) -> Path | None:
    """
    @brief      Resolve one Scene Ambience mix record to an existing audio file.
    @param[in]  window Active main window instance.
    @param[in]  group_record Optional Scene Ambience mix record.
    @return     Absolute audio path or `None`.
    @exception  None
    """
    return _project_audio_path_from_record(window, group_record)


def _output_by_key(window: "MainWindow", output_key: str) -> dict[str, object] | None:
    """
    @brief      Find one generated Audio Assembly output by key.
    @param[in]  window Active main window instance.
    @param[in]  output_key Output key to locate.
    @return     Output record or `None`.
    @exception  None
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
    """
    return _project_audio_path_from_record(window, output_record)


def _project_audio_path_from_record(window: "MainWindow", record: dict[str, object] | None) -> Path | None:
    """
    @brief      Resolve a record audio path under the active project.
    @param[in]  window Active main window instance.
    @param[in]  record Optional record containing `audio_relative_path`.
    @return     Existing absolute path or `None`.
    @exception  None
    """
    if window._current_project_root is None or not isinstance(record, dict):
        return None
    relative_path = str(record.get("audio_relative_path", "")).strip()
    if not relative_path:
        return None
    audio_path = operation_runtime_service.try_resolve_project_relative_path(
        window._current_project_root,
        relative_path,
    )
    return audio_path if audio_path is not None and audio_path.is_file() else None


def _stop_audio_assembly_playback(window: "MainWindow") -> None:
    """
    @brief      Stop Audio Assembly playback and clear page playback state.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    """
    window._audio_assembly_playback_starting = False
    duration_ms = 0
    if hasattr(window, "_audio_assembly_audio_player"):
        duration_ms = _media_duration_ms(window._audio_assembly_audio_player)
        window._audio_assembly_audio_player.stop()
        window._audio_assembly_audio_player.setSource(QUrl())
    if hasattr(window, "_audio_assembly_page"):
        window._audio_assembly_page.set_playback_active(False)
        window._audio_assembly_page.set_playback_progress(0, duration_ms)
    window._audio_assembly_playback_output_key = None


def _is_audio_assembly_playback_active(window: "MainWindow") -> bool:
    """
    @brief      Return whether Audio Assembly playback should be treated as active.
    @param[in]  window Active main window instance.
    @return     True when playback is starting, playing, paused, or tracked as active.
    @exception  None
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
    """
    for attr_name in (
        "_narator_voice_audio_player",
        "_character_voices_audio_player",
        "_audio_blocks_audio_player",
    ):
        player = getattr(window, attr_name, None)
        if player is not None:
            player.stop()


def _output_duration_ms(output_record: dict[str, object] | None) -> int:
    """
    @brief      Resolve one audio assembly output duration to milliseconds.
    @param[in]  output_record Optional generated-output record.
    @return     Non-negative duration in milliseconds.
    @exception  None
    """
    if not isinstance(output_record, dict):
        return 0
    return max(0, int(float(output_record.get("duration_seconds", 0.0) or 0.0) * 1000))


def _media_position_ms(player) -> int:
    """
    @brief      Read the current Qt media-player position in milliseconds.
    @param[in]  player Media player object or compatible test double.
    @return     Non-negative playback position in milliseconds.
    @exception  None
    """
    position = getattr(player, "position", None)
    return max(0, int(position())) if callable(position) else 0


def _media_duration_ms(player) -> int:
    """
    @brief      Read the current Qt media-player duration in milliseconds.
    @param[in]  player Media player object or compatible test double.
    @return     Non-negative media duration in milliseconds.
    @exception  None
    """
    duration = getattr(player, "duration", None)
    return max(0, int(duration())) if callable(duration) else 0


def _clamped_position_ms(position_ms: int, duration_ms: int) -> int:
    """
    @brief      Clamp one playback position to the available media duration.
    @param[in]  position_ms Candidate playback position in milliseconds.
    @param[in]  duration_ms Media duration in milliseconds.
    @return     Playback position constrained to the media duration.
    @exception  None
    """
    resolved_duration = max(0, int(duration_ms))
    if resolved_duration <= 0:
        return 0
    return max(0, min(int(position_ms), resolved_duration))


# END OF FILE
