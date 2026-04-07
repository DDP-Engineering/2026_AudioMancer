#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file text_chunking_ui_controller.py
@brief Text Chunking page UI controller for AudioMancer.
@details Handles deterministic chunking workflows, including progress dialog
         lifecycle, resumable reruns, destructive confirmation, and manifest
         synchronization for the Text Chunking page.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.1.0
"""

# IMPORTS

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from audiomancer.services import deterministic_chunking_service
from audiomancer.services import home_presenter_service
from audiomancer.services import operation_runtime_service
from audiomancer.services import project_workspace_service
from audiomancer.services import text_cleanup_state_service
from audiomancer.services import ui_state_service
from audiomancer.ui.controllers import misc_ui_controller

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


# PUBLIC API


def handle_deterministic_chunking_requested(window: "MainWindow") -> None:
    """
    @brief      Run deterministic text chunking for the active project.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    current_language = ui_state_service.current_language_from_settings(
        window._settings_payload
    )
    if window._active_operation_kind is not None:
        return
    if window._current_project_root is None or window._current_manifest is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_no_active_project", current_language),
        )
        return

    cleanup_operation = home_presenter_service.manifest_operation(
        window._current_manifest,
        "cleanup",
    )
    cleanup_output_paths = cleanup_operation.get("output_paths", [])
    if not isinstance(cleanup_output_paths, list) or not cleanup_output_paths:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_missing_cleaned_text", current_language),
        )
        return

    chunking_operation = home_presenter_service.manifest_operation(
        window._current_manifest,
        "chunking",
    )
    if str(chunking_operation.get("status", "not_started")) == "completed":
        if not confirm_chunking_rerun(window, current_language):
            return
        operation_runtime_service.reset_operation_data(
            window._current_project_root,
            "chunking",
            include_current=True,
            keep_input_snapshots=False,
        )
        reset_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
            window._current_manifest,
            "chunking",
        )
        project_workspace_service.save_manifest(reset_manifest, window._current_project_root)
        window._current_manifest = project_workspace_service.load_manifest(
            window._current_project_root
        )

    start_operation(
        window,
        operation_kind="chunking",
        operation_name=ui_state_service.translate("text_chunking.chunk", current_language),
        initial_message=ui_state_service.translate("progress.chunking", current_language),
        worker_callable=deterministic_chunking_service.chunk_text,
        success_handler=lambda result_payload: handle_chunking_success(window, result_payload),
        failure_handler=lambda error: handle_chunking_failure(window, error),
    )


def start_operation(
    window: "MainWindow",
    operation_kind: str,
    operation_name: str,
    initial_message: str,
    worker_callable,
    success_handler,
    failure_handler,
) -> None:
    """
    @brief      Run one cancelable long-running chunking operation synchronously with a modal progress dialog.
    @param[in]  window Active main window shell.
    @param[in]  operation_kind Operation-kind token.
    @param[in]  operation_name Operator-facing operation name.
    @param[in]  initial_message First progress status message.
    @param[in]  worker_callable Service callable that performs the operation.
    @param[in]  success_handler Callback invoked with the worker result payload.
    @param[in]  failure_handler Callback invoked with the raised exception.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    window._text_chunking_page.set_busy(True)
    window._active_operation_kind = operation_kind
    window._active_operation_name = operation_name
    window._operation_cancel_requested = False
    misc_ui_controller.create_progress_dialog(
        window,
        operation_name,
        initial_message,
        lambda: cancel_active_operation(window),
    )
    try:
        result_payload = worker_callable(
            window._current_project_root,
            dict(window._current_manifest),
            progress_callback=lambda progress_current, progress_total, percent, message: (
                handle_operation_progress(
                    window,
                    progress_current,
                    progress_total,
                    percent,
                    message,
                )
            ),
            cancel_requested=lambda: is_cancel_requested(window),
        )
    except operation_runtime_service.OperationCancelledError as error:
        handle_operation_cancelled(window, str(error))
    except Exception as error:
        handle_operation_failure(window, failure_handler, error)
    else:
        handle_operation_success(window, success_handler, result_payload)
    finally:
        clear_active_operation(window)


def handle_operation_progress(
    window: "MainWindow",
    progress_current: int,
    progress_total: int,
    percent: int,
    message: str,
) -> None:
    """
    @brief      Refresh the modal progress dialog for one running operation.
    @param[in]  window Active main window shell.
    @param[in]  progress_current Completed work units.
    @param[in]  progress_total Total work units.
    @param[in]  percent Current progress percent.
    @param[in]  message Current operator-facing status message.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    _ = progress_current
    _ = progress_total
    misc_ui_controller.update_progress_dialog(window, percent, message)


def cancel_active_operation(window: "MainWindow") -> None:
    """
    @brief      Request cooperative cancellation for the active synchronous operation.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if window._active_operation_kind is not None:
        window._operation_cancel_requested = True


def is_cancel_requested(window: "MainWindow") -> bool:
    """
    @brief      Return whether the active modal operation was asked to cancel.
    @param[in]  window Active main window shell.
    @return     True when cooperative cancellation was requested.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    misc_ui_controller.process_pending_ui_events()
    return window._operation_cancel_requested


def handle_operation_success(window: "MainWindow", success_handler, result_payload: object) -> None:
    """
    @brief      Finalize one successful long-running operation.
    @param[in]  window Active main window shell.
    @param[in]  success_handler Callback invoked with the worker result payload.
    @param[in]  result_payload Worker result payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if window._operation_progress_dialog is not None:
        misc_ui_controller.update_progress_dialog(
            window,
            100,
            window._operation_progress_dialog.status_message(),
        )
    misc_ui_controller.finish_progress_dialog(window)
    success_handler(result_payload)


def handle_operation_failure(window: "MainWindow", failure_handler, error: Exception) -> None:
    """
    @brief      Finalize one failed long-running operation.
    @param[in]  window Active main window shell.
    @param[in]  failure_handler Callback invoked with the raised exception.
    @param[in]  error Raised operation exception.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    misc_ui_controller.update_progress_dialog(window, 100, str(error))
    misc_ui_controller.fail_progress_dialog(window, str(error))
    failure_handler(error)


def handle_operation_cancelled(window: "MainWindow", message: str) -> None:
    """
    @brief      Finalize one cooperatively cancelled operation.
    @param[in]  window Active main window shell.
    @param[in]  message Operator-facing cancellation message.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    misc_ui_controller.update_progress_dialog(window, 100, message)
    misc_ui_controller.fail_progress_dialog(window, message)
    sync_manifest_after_unsuccessful_operation(window)
    if window._current_project_root is not None:
        window.show_project_state(
            window._current_project_root,
            project_workspace_service.load_manifest(window._current_project_root),
        )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.operation_cancelled",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def clear_active_operation(window: "MainWindow") -> None:
    """
    @brief      Clear the current synchronous-operation bookkeeping after one run stops.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    window._text_chunking_page.set_busy(False)
    misc_ui_controller.clear_progress_dialog(window)
    window._active_operation_kind = None
    window._active_operation_name = None
    window._operation_cancel_requested = False


def handle_chunking_success(window: "MainWindow", result_payload: object) -> None:
    """
    @brief      Persist manifest state after one successful chunking run.
    @param[in]  window Active main window shell.
    @param[in]  result_payload Successful chunking result payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    _ = result_payload
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    updated_manifest = dict(window._current_manifest)
    updated_manifest["current_stage"] = "translation_ready"
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operations["chunking"] = (
        deterministic_chunking_service.load_operation_state(window._current_project_root)
        or operations["chunking"]
    )
    updated_manifest["operations"] = operations
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.text_chunked",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def handle_chunking_failure(window: "MainWindow", error: Exception) -> None:
    """
    @brief      Persist failed chunking state and show one operator error popup.
    @param[in]  window Active main window shell.
    @param[in]  error Raised chunking exception.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    sync_manifest_after_unsuccessful_operation(window)
    QMessageBox.warning(
        window,
        ui_state_service.translate(
            "dialog.project_error_title",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
        str(error),
    )


def sync_manifest_after_unsuccessful_operation(window: "MainWindow") -> None:
    """
    @brief      Persist resumable chunking state after one failed or cancelled run.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if window._current_manifest is None or window._current_project_root is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operations["chunking"] = (
        deterministic_chunking_service.load_operation_state(window._current_project_root)
        or operations["chunking"]
    )
    updated_manifest["operations"] = operations
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def confirm_chunking_rerun(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator whether one completed chunking run should be rerun destructively.
    @param[in]  window Active main window shell.
    @param[in]  language Current UI language code.
    @return     True when the operator accepts the rerun reset.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    decision = QMessageBox.question(
        window,
        ui_state_service.translate("dialog.confirm_chunking_rerun_title", language),
        ui_state_service.translate("project.confirm_chunking_rerun", language),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return decision == QMessageBox.StandardButton.Yes


# END OF FILE
