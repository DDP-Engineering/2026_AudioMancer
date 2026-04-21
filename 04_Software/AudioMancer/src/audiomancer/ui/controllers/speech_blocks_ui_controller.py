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
@version 0.1.0
"""

# IMPORTS

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from audiomancer.services import (
    operation_runtime_service,
    project_workspace_service,
    speech_blocks_service,
    text_cleanup_state_service,
    ui_state_service,
)
from audiomancer.ui.controllers import misc_ui_controller

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

    speech_blocks_operation = text_cleanup_state_service.normalized_manifest_operations(window._current_manifest).get(
        "speech_blocks",
        {},
    )
    if str(speech_blocks_operation.get("status", "not_started")) == "completed":
        if not _confirm_speech_blocks_rerun(window, current_language):
            return
        _reset_speech_blocks_and_downstream(window)
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
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        ),
    )


def _start_operation(window: "MainWindow", operation_name: str, initial_message: str, worker_callable) -> None:
    """
    @brief      Run one Speech Blocks operation with modal progress handling.
    @param[in]  window Active main window instance.
    @param[in]  operation_name Operator-facing operation label.
    @param[in]  initial_message Initial progress-dialog message text.
    @param[in]  worker_callable Callable that performs the operation.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    window._speech_blocks_page.set_busy(True)
    window._active_operation_kind = "speech_blocks"
    window._active_operation_name = operation_name
    window._operation_cancel_requested = False
    misc_ui_controller.create_progress_dialog(
        window,
        operation_name,
        initial_message,
        lambda: _cancel_active_operation(window),
    )
    try:
        worker_callable(
            window._current_project_root,
            dict(window._current_manifest),
            progress_callback=lambda current, total, percent, message, token_usage=None: (
                misc_ui_controller.update_progress_dialog(window, percent, message, token_usage)
            ),
            cancel_requested=lambda: _is_cancel_requested(window),
        )
    except operation_runtime_service.OperationCancelledError as error:
        misc_ui_controller.update_progress_dialog(window, 100, str(error))
        misc_ui_controller.fail_progress_dialog(window, str(error))
        _sync_manifest_from_disk(window)
        misc_ui_controller.show_message(
            window,
            ui_state_service.translate("status.operation_cancelled", current_language_from_window(window)),
        )
    except Exception as error:
        misc_ui_controller.update_progress_dialog(window, 100, str(error))
        misc_ui_controller.fail_progress_dialog(window, str(error))
        _sync_manifest_from_disk(window)
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language_from_window(window)),
            str(error),
        )
    else:
        misc_ui_controller.finish_progress_dialog(window)
        _sync_manifest_after_success(window)
        misc_ui_controller.show_message(
            window,
            ui_state_service.translate("status.speech_blocks_generated", current_language_from_window(window)),
        )
    finally:
        window._speech_blocks_page.set_busy(False)
        misc_ui_controller.clear_progress_dialog(window)
        window._active_operation_kind = None
        window._active_operation_name = None
        window._operation_cancel_requested = False


def _sync_manifest_after_success(window: "MainWindow") -> None:
    """
    @brief      Persist the latest Speech Blocks operation summary into the manifest.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    operation_state = speech_blocks_service.load_operation_state(window._current_project_root)
    if operation_state is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operations["speech_blocks"] = project_workspace_service.project_manifest_operation_summary(
        "speech_blocks",
        operation_state,
    )
    updated_manifest["operations"] = operations
    updated_manifest["current_stage"] = "speech_blocks_ready"
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
    @brief      Reset Speech Blocks and downstream runtime data before one rerun.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    operation_runtime_service.reset_operation_data(
        window._current_project_root,
        "speech_blocks",
        include_current=True,
        keep_input_snapshots=False,
    )
    reset_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
        window._current_manifest,
        "speech_blocks",
    )
    project_workspace_service.save_manifest(reset_manifest, window._current_project_root)
    window._current_manifest = project_workspace_service.load_manifest(window._current_project_root)


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
    @version    0.1.0
    """
    misc_ui_controller.process_pending_ui_events()
    return bool(window._operation_cancel_requested)


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


def _confirm_speech_blocks_rerun(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator whether one completed Speech Blocks run should be rerun destructively.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when the operator accepts the rerun reset.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
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
