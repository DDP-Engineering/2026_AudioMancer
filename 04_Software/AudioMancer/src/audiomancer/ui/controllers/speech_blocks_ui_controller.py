#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file speech_blocks_ui_controller.py
@brief Speech Blocks page UI controller for AudioMancer.
@details Handles Speech Blocks generation confirmations, modal progress
         lifecycle, resumable run synchronization, and manifest updates for the
         Speech Blocks workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-21
@version 0.4.1
"""

# IMPORTS

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import (
    audio_assembly_service,
    audio_blocks_service,
    project_workspace_service,
    speech_blocks_service,
    text_cleanup_state_service,
    ui_state_service,
)
from audiomancer.ui.controllers import misc_ui_controller, operation_runner_controller

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


def handle_generate_requested(window: "MainWindow", profile_id: str) -> None:
    """
    @brief      Validate and start or continue one Speech Blocks run.
    @param[in]  window Active main window instance.
    @param[in]  profile_id Selected enabled AI profile identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
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
    try:
        speech_blocks_service.resolve_source_chunks(window._current_project_root, window._current_manifest)
    except ValueError as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            _translated_source_error_message(str(error), current_language),
        )
        return
    profile_payload = _resolve_ai_profile(window._settings_payload, profile_id)
    if profile_payload is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_missing_speech_blocks_profile", current_language),
        )
        return

    if not _confirm_generation(window, current_language):
        return

    _start_operation(
        window,
        operation_name=ui_state_service.translate("speech_blocks.generate", current_language),
        initial_message=ui_state_service.translate("progress.speech_blocks", current_language),
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            speech_blocks_service.start_or_continue_generation(
                project_root,
                manifest,
                profile_payload,
                settings_payload=window._settings_payload,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        ),
    )


def handle_reset_generation_requested(window: "MainWindow") -> None:
    """
    @brief      Confirm and reset persisted Speech Blocks plus downstream data.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    if not _confirm_speech_blocks_reset(window, current_language):
        return
    _reset_speech_blocks_and_downstream(window)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.speech_blocks_reset", current_language),
    )


def handle_approve_all_requested(window: "MainWindow") -> None:
    """
    @brief      Approve every Speech Block and advance the workflow when complete.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    speech_blocks_service.approve_all_speech_blocks(window._current_project_root)
    _sync_manifest_after_speech_blocks_update(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.speech_blocks_approved_all", current_language),
    )


def handle_approve_block_requested(window: "MainWindow", speech_block_id: str) -> None:
    """
    @brief      Approve one selected Speech Block and refresh workflow state.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Selected Speech Block identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    chunk_id = _chunk_id_for_speech_block(window, speech_block_id)
    if not _confirm_chunk_audio_reset_if_needed(window, chunk_id, current_language):
        return
    try:
        speech_blocks_service.approve_speech_block(window._current_project_root, speech_block_id)
    except ValueError as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return
    _sync_manifest_after_speech_blocks_update(window)
    _reset_audio_blocks_after_speech_chunk_change(window, chunk_id)
    window._speech_blocks_page.advance_to_next_block()
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.speech_block_approved", current_language),
    )


def handle_insert_block_requested(window: "MainWindow", chunk_id: str, before_speech_block_id: str) -> None:
    """
    @brief      Insert one manual Speech Block at the selected chunk position.
    @param[in]  window Active main window instance.
    @param[in]  chunk_id Selected source chunk identifier.
    @param[in]  before_speech_block_id Optional selected Speech Block before the new block.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    if not _confirm_chunk_audio_reset_if_needed(window, chunk_id, current_language):
        return
    try:
        _report, inserted_block_id = speech_blocks_service.insert_speech_block(
            window._current_project_root,
            chunk_id,
            before_speech_block_id or None,
        )
    except ValueError as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return
    _sync_manifest_after_speech_blocks_update(window)
    _reset_audio_blocks_after_speech_chunk_change(window, chunk_id)
    window._speech_blocks_page.select_speech_block(inserted_block_id)
    window._speech_blocks_page.begin_editing_selected_block()
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.speech_block_inserted", current_language),
    )


def handle_delete_block_requested(window: "MainWindow", speech_block_id: str) -> None:
    """
    @brief      Confirm and delete one selected Speech Block.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Selected Speech Block identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    chunk_id = _chunk_id_for_speech_block(window, speech_block_id)
    if not _confirm_delete_speech_block(window, current_language):
        return
    if not _confirm_chunk_audio_reset_if_needed(window, chunk_id, current_language):
        return
    try:
        speech_blocks_service.delete_speech_block(window._current_project_root, speech_block_id)
    except ValueError as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return
    _sync_manifest_after_speech_blocks_update(window)
    _reset_audio_blocks_after_speech_chunk_change(window, chunk_id)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.speech_block_deleted", current_language),
    )


def handle_edit_started(window: "MainWindow", speech_block_id: str) -> None:
    """
    @brief      Clear one selected Speech Block warning as soon as editing starts.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Selected Speech Block identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    selected_block = next(
        (
            block
            for block in speech_blocks_service.load_speech_blocks(window._current_project_root)
            if str(block.get("speech_block_id", "")).strip() == str(speech_block_id).strip()
        ),
        None,
    )
    if selected_block is None:
        return
    speech_blocks_service.update_speech_block(
        window._current_project_root,
        speech_block_id,
        str(selected_block.get("speaker_id", "")),
        str(selected_block.get("content_kind", "")),
        str(selected_block.get("text", "")),
    )


def handle_save_block_requested(
    window: "MainWindow",
    speech_block_id: str,
    speaker_id: str,
    content_kind: str,
    text: str,
) -> None:
    """
    @brief      Save one manually edited Speech Block.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Selected Speech Block identifier.
    @param[in]  speaker_id Selected speaker identifier.
    @param[in]  content_kind Selected content-kind token.
    @param[in]  text Edited Speech Block text.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    chunk_id = _chunk_id_for_speech_block(window, speech_block_id)
    if not _confirm_chunk_audio_reset_if_needed(window, chunk_id, current_language):
        return
    source_scroll_position = window._speech_blocks_page.source_scroll_position()
    try:
        speech_blocks_service.update_speech_block(
            window._current_project_root,
            speech_block_id,
            speaker_id,
            content_kind,
            text,
        )
    except ValueError as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return
    _sync_manifest_after_speech_blocks_update(window)
    _reset_audio_blocks_after_speech_chunk_change(window, chunk_id)
    window._speech_blocks_page.restore_source_scroll_position(source_scroll_position)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.speech_block_saved", current_language),
    )


def handle_reset_block_requested(window: "MainWindow", speech_block_id: str) -> None:
    """
    @brief      Reset one Speech Block to its AI-extracted baseline.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Selected Speech Block identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    chunk_id = _chunk_id_for_speech_block(window, speech_block_id)
    if not _confirm_chunk_audio_reset_if_needed(window, chunk_id, current_language):
        return
    source_scroll_position = window._speech_blocks_page.source_scroll_position()
    try:
        speech_blocks_service.reset_speech_block_to_ai_baseline(window._current_project_root, speech_block_id)
    except ValueError as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return
    _sync_manifest_after_speech_blocks_update(window)
    _reset_audio_blocks_after_speech_chunk_change(window, chunk_id)
    window._speech_blocks_page.restore_source_scroll_position(source_scroll_position)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.speech_block_reset", current_language),
    )


def handle_resplit_selected_requested(window: "MainWindow", chunk_id: str) -> None:
    """
    @brief      Confirm and re-run Speech Blocks splitting for one selected chunk.
    @param[in]  window Active main window instance.
    @param[in]  chunk_id Selected source chunk identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._active_operation_kind is not None:
        return
    if window._current_project_root is None or window._current_manifest is None:
        return
    profile_payload = _resolve_ai_profile(window._settings_payload, window._speech_blocks_page.current_profile_id())
    if profile_payload is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_missing_speech_blocks_profile", current_language),
        )
        return
    if not _confirm_speech_blocks_resplit(window, current_language):
        return
    _start_operation(
        window,
        operation_name=ui_state_service.translate("speech_blocks.resplit_selected", current_language),
        initial_message=ui_state_service.translate("progress.speech_blocks_resplit", current_language),
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            speech_blocks_service.regenerate_chunk_speech_blocks(
                project_root,
                manifest,
                chunk_id,
                profile_payload,
                settings_payload=window._settings_payload,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        ),
        success_message_key="status.speech_blocks_resplit",
        changed_chunk_id=chunk_id,
    )


def _start_operation(
    window: "MainWindow",
    operation_name: str,
    initial_message: str,
    worker_callable,
    success_message_key: str = "status.speech_blocks_generated",
    changed_chunk_id: str | None = None,
) -> None:
    """
    @brief      Start one Speech Blocks operation on a worker thread.
    @param[in]  window Active main window instance.
    @param[in]  operation_name Operator-facing operation label.
    @param[in]  initial_message Initial progress-dialog message text.
    @param[in]  worker_callable Callable that performs the operation.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
    """
    operation_runner_controller.start_threaded_operation(
        window,
        "speech_blocks",
        operation_name,
        initial_message,
        worker_callable,
        set_busy=lambda is_busy: window._speech_blocks_page.set_busy(is_busy),
        success_handler=lambda result_payload: _handle_speech_blocks_success(
            window,
            result_payload,
            success_message_key,
            changed_chunk_id,
        ),
        failure_handler=lambda error: _handle_speech_blocks_failure(window, error),
        cancel_handler=lambda message: _handle_speech_blocks_cancelled(window, message),
    )


def _handle_speech_blocks_success(
    window: "MainWindow",
    result_payload: object,
    success_message_key: str,
    changed_chunk_id: str | None,
) -> None:
    """
    @brief      Refresh Speech Blocks UI state after a successful worker run.
    @param[in]  window Active main window instance.
    @param[in]  result_payload Worker result payload.
    @param[in]  success_message_key UI string key emitted after success.
    @param[in]  changed_chunk_id Optional chunk id that was regenerated.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    _ = result_payload
    _sync_manifest_after_speech_blocks_update(window)
    if changed_chunk_id is not None:
        _reconcile_audio_blocks_after_resplit(window, changed_chunk_id)
    else:
        _reset_downstream_after_speech_blocks_structure_change(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(success_message_key, current_language_from_window(window)),
    )


def _handle_speech_blocks_failure(window: "MainWindow", error: Exception) -> None:
    """
    @brief      Refresh Speech Blocks UI state after a failed worker run.
    @param[in]  window Active main window instance.
    @param[in]  error Raised operation exception.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    _sync_manifest_from_disk(window)
    QMessageBox.warning(
        window,
        ui_state_service.translate("dialog.project_error_title", current_language_from_window(window)),
        str(error),
    )


def _handle_speech_blocks_cancelled(window: "MainWindow", message: str) -> None:
    """
    @brief      Refresh Speech Blocks UI state after a cancelled worker run.
    @param[in]  window Active main window instance.
    @param[in]  message Cancellation message.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    _ = message
    _sync_manifest_from_disk(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.operation_cancelled", current_language_from_window(window)),
    )


def _sync_manifest_after_speech_blocks_update(window: "MainWindow") -> None:
    """
    @brief      Persist the latest Speech Blocks summary and advance only after approval.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    operation_state = speech_blocks_service.load_operation_state(window._current_project_root)
    report = speech_blocks_service.load_speech_blocks_report(window._current_project_root)
    if operation_state is None and not isinstance(report, dict):
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operations["speech_blocks"] = _speech_blocks_manifest_operation_summary(operation_state, report)
    updated_manifest["operations"] = operations
    if (
        isinstance(report, dict)
        and str(report.get("speech_blocks_stage_status", "")).strip()
        == speech_blocks_service.SPEECH_BLOCKS_STAGE_COMPLETED
    ):
        updated_manifest["current_stage"] = "speech_blocks_ready"
    elif _stage_rank(str(updated_manifest.get("current_stage", "")).strip()) > _stage_rank("character_voices_ready"):
        updated_manifest["current_stage"] = "character_voices_ready"
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _sync_manifest_from_disk(window: "MainWindow") -> None:
    """
    @brief      Reload persisted Speech Blocks state from disk after failure or cancel.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operation_state = speech_blocks_service.load_operation_state(window._current_project_root)
    if operation_state is not None:
        operations["speech_blocks"] = project_workspace_service.project_manifest_operation_summary(
            "speech_blocks",
            operation_state,
        )
    updated_manifest["operations"] = operations
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _resolve_ai_profile(settings_payload: dict[str, object] | None, profile_id: str | None) -> dict[str, object] | None:
    """
    @brief      Resolve one enabled AI profile payload from settings by id.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  profile_id Requested profile identifier.
    @return     Resolved profile payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not isinstance(settings_payload, dict) or not profile_id:
        return None
    raw_profiles = settings_payload.get("llm_profiles", [])
    if not isinstance(raw_profiles, list):
        return None
    for profile in raw_profiles:
        if not isinstance(profile, dict) or not bool(profile.get("enabled", True)):
            continue
        if str(profile.get("id", "")).strip() == str(profile_id).strip():
            return dict(profile)
    return None


def _reset_speech_blocks_and_downstream(window: "MainWindow") -> None:
    """
    @brief      Reset Speech Blocks and downstream runtime data.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.0
    """
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    audio_blocks_service.reset_audio_blocks(window._current_project_root)
    audio_assembly_service.reset_audio_assembly(window._current_project_root)
    speech_blocks_service.reset_speech_blocks(window._current_project_root)
    reset_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
        window._current_manifest,
        "speech_blocks",
    )
    project_workspace_service.save_manifest(reset_manifest, window._current_project_root)
    window._current_manifest = project_workspace_service.load_manifest(window._current_project_root)


def _chunk_id_for_speech_block(window: "MainWindow", speech_block_id: str) -> str | None:
    """
    @brief      Resolve the chunk identifier for one Speech Block.
    @param[in]  window Active main window instance.
    @param[in]  speech_block_id Selected Speech Block identifier.
    @return     Source chunk identifier or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    if window._current_project_root is None:
        return None
    normalized_block_id = str(speech_block_id).strip()
    for block in speech_blocks_service.load_speech_blocks(window._current_project_root):
        if str(block.get("speech_block_id", "")).strip() == normalized_block_id:
            return str(block.get("chunk_id", "")).strip() or None
    return None


def _reset_audio_blocks_after_speech_chunk_change(window: "MainWindow", chunk_id: str | None) -> None:
    """
    @brief      Reset stale Audio Blocks entries after one Speech Blocks chunk changes.
    @param[in]  window Active main window instance.
    @param[in]  chunk_id Changed source chunk identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.3.0
    """
    if window._current_project_root is None or not chunk_id:
        return
    audio_player = getattr(window, "_audio_blocks_audio_player", None)
    if audio_player is not None:
        audio_player.stop()
    audio_blocks_service.reset_audio_for_speech_chunk(window._current_project_root, chunk_id)
    audio_assembly_service.reset_audio_assembly(window._current_project_root)
    _sync_audio_blocks_manifest_summary(window)


def _reconcile_audio_blocks_after_resplit(window: "MainWindow", changed_chunk_id: str) -> None:
    """
    @brief      Preserve safe Audio Blocks records after one selected chunk re-split.
    @param[in]  window Active main window instance.
    @param[in]  changed_chunk_id Re-split source chunk identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    if window._current_project_root is None:
        return
    _reset_audio_blocks_after_speech_chunk_change(window, changed_chunk_id)


def _reset_downstream_after_speech_blocks_structure_change(window: "MainWindow") -> None:
    """
    @brief      Reset Audio Blocks and Audio Assembly after Speech Block insert/delete.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    audio_blocks_service.reset_audio_blocks(window._current_project_root)
    audio_assembly_service.reset_audio_assembly(window._current_project_root)
    reset_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
        window._current_manifest,
        "audio_blocks",
    )
    report = speech_blocks_service.load_speech_blocks_report(window._current_project_root)
    if not (
        isinstance(report, dict)
        and str(report.get("speech_blocks_stage_status", "")).strip()
        == speech_blocks_service.SPEECH_BLOCKS_STAGE_COMPLETED
    ):
        reset_manifest["current_stage"] = "character_voices_ready"
    operation_state = speech_blocks_service.load_operation_state(window._current_project_root)
    operations = text_cleanup_state_service.normalized_manifest_operations(reset_manifest)
    operations["speech_blocks"] = _speech_blocks_manifest_operation_summary(operation_state, report)
    reset_manifest["operations"] = operations
    project_workspace_service.save_manifest(reset_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _sync_audio_blocks_manifest_summary(window: "MainWindow") -> None:
    """
    @brief      Refresh the compact Audio Blocks manifest summary after Speech Block changes.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    default_operations = text_cleanup_state_service.normalized_manifest_operations({})
    operation_state = audio_blocks_service.load_operation_state(window._current_project_root)
    if operation_state is not None:
        operations["audio_blocks"] = project_workspace_service.project_manifest_operation_summary(
            "audio_blocks",
            operation_state,
        )
    operations["audio_assembly"] = default_operations["audio_assembly"]
    updated_manifest["operations"] = operations
    if _stage_rank(str(updated_manifest.get("current_stage", "")).strip()) > _stage_rank("speech_blocks_ready"):
        updated_manifest["current_stage"] = "speech_blocks_ready"
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _cancel_active_operation(window: "MainWindow") -> None:
    """
    @brief      Mark the active Speech Blocks operation for cancellation.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if window._active_operation_kind is not None:
        window._operation_cancel_requested = True


def _is_cancel_requested(window: "MainWindow") -> bool:
    """
    @brief      Check whether the current Speech Blocks operation should cancel.
    @param[in]  window Active main window instance.
    @return     True when cancellation was requested.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.1
    """
    return bool(window._operation_cancel_requested)


def _speech_blocks_manifest_operation_summary(
    operation_state: dict[str, object] | None,
    report: dict[str, object] | None,
) -> dict[str, object]:
    """
    @brief      Build the manifest summary for Speech Blocks from approval-aware report state.
    @param[in]  operation_state Persisted Speech Blocks runtime state.
    @param[in]  report Persisted Speech Blocks report payload.
    @return     Compact manifest operation summary.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    summary = project_workspace_service.project_manifest_operation_summary("speech_blocks", operation_state)
    if not isinstance(report, dict):
        return summary
    stage_status = str(report.get("speech_blocks_stage_status", "")).strip()
    if stage_status == speech_blocks_service.SPEECH_BLOCKS_STAGE_COMPLETED:
        summary["status"] = "completed"
    elif stage_status == speech_blocks_service.SPEECH_BLOCKS_STAGE_IN_PROGRESS and str(summary.get("status")) not in {
        "running",
        "failed",
    }:
        summary["status"] = "review_pending"
    return summary


def _confirm_generation(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator whether one Speech Blocks generation should start or continue.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the operator confirms the run.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.confirm_speech_blocks_title", language),
            ui_state_service.translate("project.confirm_speech_blocks", language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_speech_blocks_reset(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask whether persisted Speech Blocks data should be reset.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the operator accepts the rerun reset.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.confirm_speech_blocks_rerun_title", language),
            ui_state_service.translate("project.confirm_speech_blocks_rerun", language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_chunk_audio_reset_if_needed(window: "MainWindow", chunk_id: str | None, language: str) -> bool:
    """
    @brief      Ask before resetting generated Audio Blocks data for one changed Speech Blocks chunk.
    @param[in]  window Active main window instance.
    @param[in]  chunk_id Changed source chunk identifier.
    @param[in]  language Current UI language code.
    @return     True when the operation may continue.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    if window._current_project_root is None or not chunk_id:
        return True
    if not audio_blocks_service.has_persisted_audio_for_chunk(window._current_project_root, chunk_id):
        return True
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.confirm_speech_block_audio_reset_title", language),
            ui_state_service.translate("project.confirm_speech_block_audio_reset", language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_speech_blocks_resplit(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask whether one selected chunk should be re-split through AI.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the operator accepts the selected-chunk re-split.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.confirm_speech_blocks_resplit_title", language),
            ui_state_service.translate("project.confirm_speech_blocks_resplit", language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_delete_speech_block(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask whether one selected Speech Block should be deleted.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the operator accepts the deletion.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.confirm_delete_speech_block_title", language),
            ui_state_service.translate("project.confirm_delete_speech_block", language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def _stage_rank(stage: str) -> int:
    """
    @brief      Resolve one workflow stage rank.
    @param[in]  stage Workflow stage token.
    @return     Zero-based workflow rank or -1 for unknown stages.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    try:
        return config.PROJECT_WORKFLOW_STAGES.index(stage)
    except ValueError:
        return -1


def current_language_from_window(window: "MainWindow") -> str:
    """
    @brief      Resolve the active UI language from one main window instance.
    @param[in]  window Active main window instance.
    @return     Current UI language code.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return ui_state_service.current_language_from_settings(window._settings_payload)


def _translated_source_error_message(error_text: str, language: str) -> str:
    """
    @brief      Translate one known Speech Blocks prerequisite error into the runtime UI language.
    @param[in]  error_text Raw source error text.
    @param[in]  language Current UI language code.
    @return     Translated operator-facing error message.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if error_text == "Run text chunking before starting Speech Blocks.":
        return ui_state_service.translate("project.error_missing_chunk_artifact", language)
    if error_text in {
        "The selected Character Voices language is not available for Speech Blocks yet.",
        "Approve all translated chunks before generating Speech Blocks in the translated language.",
    }:
        return ui_state_service.translate("speech_blocks.note_missing_source", language)
    return error_text


# END OF FILE
