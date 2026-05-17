#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file text_cleanup_ui_controller.py
@brief Text Cleanup page UI controller for AudioMancer.
@details Handles extraction, deterministic cleanup, and AI-assisted cleanup
         workflows, including manual cleaned-text saves, progress dialog
         lifecycle, cancellation, rerun confirmations, and manifest
         synchronization for the Text Cleanup page.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.8.2
"""

# IMPORTS

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import (
    ai_cleanup_service,
    deterministic_cleanup_service,
    home_presenter_service,
    operation_runtime_service,
    project_workspace_service,
    text_cleanup_state_service,
    text_extraction_service,
    ui_state_service,
)
from audiomancer.ui.controllers import misc_ui_controller, operation_runner_controller

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


# PUBLIC API


def handle_extract_text_requested(window: "MainWindow") -> None:
    """
    @brief      Run deterministic source-text extraction for the active project.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
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
    if home_presenter_service.source_document_name(window._current_manifest) is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_missing_source", current_language),
        )
        return

    extraction_operation = home_presenter_service.manifest_operation(
        window._current_manifest,
        "extraction",
    )
    if str(extraction_operation.get("status", "not_started")) == "completed":
        if not confirm_extraction_rerun(window, current_language):
            return
        text_extraction_service.reset_extraction_and_downstream(window._current_project_root)
        reset_manifest = text_cleanup_state_service.build_manifest_after_extraction_reset(window._current_manifest)
        project_workspace_service.save_manifest(reset_manifest, window._current_project_root)
        window._current_manifest = project_workspace_service.load_manifest(window._current_project_root)

    start_operation(
        window,
        operation_kind="extraction",
        operation_name=ui_state_service.translate("text_cleanup.extract", current_language),
        initial_message=ui_state_service.translate("progress.extracting", current_language),
        worker_callable=text_extraction_service.extract_text,
        success_handler=lambda result_payload: handle_extraction_success(window, result_payload),
        failure_handler=lambda error: handle_extraction_failure(window, error),
    )


def handle_deterministic_cleanup_requested(window: "MainWindow") -> None:
    """
    @brief      Run deterministic cleanup for the active project.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.3
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
    if not window._current_manifest.get("extracted_text_relative_path"):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate(
                "project.error_missing_extracted_text",
                current_language,
            ),
        )
        return

    cleanup_operation = home_presenter_service.manifest_operation(
        window._current_manifest,
        "cleanup",
    )
    if str(cleanup_operation.get("status", "not_started")) == "completed":
        if not confirm_cleanup_rerun(window, current_language):
            return
        operation_runtime_service.reset_operation_data(
            window._current_project_root,
            "cleanup",
            include_current=True,
            keep_input_snapshots=False,
            preserve_operation_kinds=operation_runtime_service.TEXT_REVISION_PRESERVED_OPERATION_KINDS,
        )
        reset_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
            window._current_manifest,
            "cleanup",
            preserve_operation_kinds=operation_runtime_service.TEXT_REVISION_PRESERVED_OPERATION_KINDS,
        )
        project_workspace_service.save_manifest(reset_manifest, window._current_project_root)
        window._current_manifest = project_workspace_service.load_manifest(window._current_project_root)

    start_operation(
        window,
        operation_kind="cleanup",
        operation_name=ui_state_service.translate("text_cleanup.clean", current_language),
        initial_message=ui_state_service.translate("progress.cleaning", current_language),
        worker_callable=deterministic_cleanup_service.clean_text,
        success_handler=lambda result_payload: handle_cleanup_success(window, result_payload),
        failure_handler=lambda error: handle_cleanup_failure(window, error),
    )


def handle_ai_cleanup_requested(window: "MainWindow", profile_id: str) -> None:
    """
    @brief      Run AI-assisted cleanup for the active project and selected profile.
    @param[in]  window Active main window shell.
    @param[in]  profile_id Selected AI cleanup profile id.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.5.1
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
    if not window._current_manifest.get("extracted_text_relative_path"):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate(
                "project.error_missing_extracted_text",
                current_language,
            ),
        )
        return

    cleanup_operation = home_presenter_service.manifest_operation(
        window._current_manifest,
        "cleanup",
    )
    cleanup_status = str(cleanup_operation.get("status", "not_started"))
    cleanup_mode = str(cleanup_operation.get("mode") or "")
    selected_profile = _resolve_ai_profile(
        window._settings_payload,
        profile_id,
    )
    if selected_profile is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_missing_ai_profile", current_language),
        )
        return

    additional_cleanup_instructions = None
    if cleanup_status in {"running", "failed", "cancelled"} and cleanup_mode == "ai_assisted":
        pass
    else:
        if not confirm_ai_cleanup_start(window, current_language):
            return
        additional_cleanup_instructions = prompt_ai_cleanup_instructions(window, current_language)
        if additional_cleanup_instructions is None:
            return
        if cleanup_status == "completed":
            if not confirm_ai_cleanup_rerun(window, current_language):
                return
            operation_runtime_service.reset_operation_data(
                window._current_project_root,
                "cleanup",
                include_current=True,
                keep_input_snapshots=False,
                preserve_operation_kinds=operation_runtime_service.TEXT_REVISION_PRESERVED_OPERATION_KINDS,
            )
            reset_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
                window._current_manifest,
                "cleanup",
                preserve_operation_kinds=operation_runtime_service.TEXT_REVISION_PRESERVED_OPERATION_KINDS,
            )
            project_workspace_service.save_manifest(reset_manifest, window._current_project_root)
            window._current_manifest = project_workspace_service.load_manifest(window._current_project_root)

    start_operation(
        window,
        operation_kind="cleanup",
        operation_name=ui_state_service.translate("text_cleanup.ai_clean", current_language),
        initial_message=ui_state_service.translate("progress.ai_cleaning", current_language),
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            ai_cleanup_service.clean_text(
                project_root,
                manifest,
                selected_profile,
                additional_cleanup_instructions=additional_cleanup_instructions,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        ),
        success_handler=lambda result_payload: handle_cleanup_success(window, result_payload),
        failure_handler=lambda error: handle_cleanup_failure(window, error),
    )


def handle_save_cleaned_text_requested(window: "MainWindow", cleaned_text: str) -> None:
    """
    @brief      Persist manual cleaned-text edits and refresh downstream workflow state.
    @param[in]  window Active main window shell.
    @param[in]  cleaned_text Edited cleaned text content.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    preview_scroll_state = window._text_cleanup_page.preview_scroll_state()
    try:
        updated_manifest = text_cleanup_state_service.save_cleaned_text_edit(
            window._current_project_root,
            window._current_manifest,
            cleaned_text,
        )
    except ValueError as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return
    window.show_project_state(
        window._current_project_root,
        updated_manifest,
    )
    window._text_cleanup_page.restore_preview_scroll_state(preview_scroll_state)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.cleaned_text_saved", current_language),
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
    @brief      Start one cancelable long-running operation on a worker thread.
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
    @date       2026-04-06
    @version    0.2.0
    """
    operation_runner_controller.start_threaded_operation(
        window,
        operation_kind,
        operation_name,
        initial_message,
        worker_callable,
        set_busy=lambda is_busy: window._text_cleanup_page.set_busy(
            is_busy,
            operation_name if is_busy else None,
        ),
        success_handler=success_handler,
        failure_handler=failure_handler,
        cancel_handler=lambda message: handle_operation_cancelled(window, message),
    )


def handle_operation_progress(
    window: "MainWindow",
    progress_current: int,
    progress_total: int,
    percent: int,
    message: str,
    token_usage=None,
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
    @date       2026-04-06
    @version    0.2.0
    """
    _ = progress_current
    _ = progress_total
    misc_ui_controller.update_progress_dialog(window, percent, message, token_usage)


def cancel_active_operation(window: "MainWindow") -> None:
    """
    @brief      Request cooperative cancellation for the active synchronous operation.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
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
    @date       2026-04-06
    @version    0.1.3
    """
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
    @date       2026-04-06
    @version    0.1.1
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
    @date       2026-04-06
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
    @date       2026-04-06
    @version    0.1.1
    """
    sync_manifest_after_unsuccessful_operation(window, window._active_operation_kind or "")
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
    @date       2026-04-06
    @version    0.1.0
    """
    window._text_cleanup_page.set_busy(False)
    misc_ui_controller.clear_progress_dialog(window)
    window._active_operation_kind = None
    window._active_operation_name = None
    window._operation_cancel_requested = False


def handle_extraction_success(window: "MainWindow", result_payload: object) -> None:
    """
    @brief      Persist manifest state after one successful extraction run.
    @param[in]  window Active main window shell.
    @param[in]  result_payload Successful extraction result payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    assert isinstance(result_payload, dict)
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    updated_manifest = dict(window._current_manifest)
    updated_manifest["extracted_text_relative_path"] = str(result_payload["extracted_text_relative_path"])
    updated_manifest["extraction_report_relative_path"] = (
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.EXTRACTION_REPORT_FILE_NAME}"
    )
    updated_manifest["extraction_warning_count"] = len(list(result_payload.get("warnings", [])))
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operations["extraction"] = project_workspace_service.project_manifest_operation_summary(
        "extraction",
        text_extraction_service.load_operation_state(window._current_project_root),
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
            "status.text_extracted",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def handle_extraction_failure(window: "MainWindow", error: Exception) -> None:
    """
    @brief      Persist failed extraction state and show one operator error popup.
    @param[in]  window Active main window shell.
    @param[in]  error Raised extraction exception.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    sync_manifest_after_unsuccessful_operation(window, "extraction")
    QMessageBox.warning(
        window,
        ui_state_service.translate(
            "dialog.project_error_title",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
        str(error),
    )


def handle_cleanup_success(window: "MainWindow", result_payload: object) -> None:
    """
    @brief      Persist manifest state after one successful cleanup run.
    @param[in]  window Active main window shell.
    @param[in]  result_payload Successful cleanup result payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.2.0
    """
    cleanup_mode = None
    if isinstance(result_payload, dict):
        cleanup_mode = str(result_payload.get("cleanup_mode") or "")
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    updated_manifest = dict(window._current_manifest)
    updated_manifest["current_stage"] = "text_chunking_ready"
    if isinstance(result_payload, dict):
        detected_language = str(result_payload.get("detected_language", "") or "").strip()
        if detected_language:
            updated_manifest["original_language"] = detected_language
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operations["cleanup"] = project_workspace_service.project_manifest_operation_summary(
        "cleanup",
        ai_cleanup_service.load_operation_state(window._current_project_root)
        or deterministic_cleanup_service.load_operation_state(window._current_project_root),
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
            "status.text_ai_cleaned" if cleanup_mode == "ai_assisted" else "status.text_cleaned",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def handle_cleanup_failure(window: "MainWindow", error: Exception) -> None:
    """
    @brief      Persist failed cleanup state and show one operator error popup.
    @param[in]  window Active main window shell.
    @param[in]  error Raised cleanup exception.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.2.0
    """
    sync_manifest_after_unsuccessful_operation(window, "cleanup")
    QMessageBox.warning(
        window,
        ui_state_service.translate(
            "dialog.project_error_title",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
        str(error),
    )


def sync_manifest_after_unsuccessful_operation(window: "MainWindow", operation_kind: str) -> None:
    """
    @brief      Persist resumable operation state after one failed or cancelled run.
    @param[in]  window Active main window shell.
    @param[in]  operation_kind Operation-kind token that failed or was cancelled.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if window._current_manifest is None or window._current_project_root is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    if operation_kind == "cleanup":
        operations["cleanup"] = project_workspace_service.project_manifest_operation_summary(
            "cleanup",
            ai_cleanup_service.load_operation_state(window._current_project_root)
            or deterministic_cleanup_service.load_operation_state(window._current_project_root),
        )
    elif operation_kind == "extraction":
        operations["extraction"] = project_workspace_service.project_manifest_operation_summary(
            "extraction",
            text_extraction_service.load_operation_state(window._current_project_root),
        )
    updated_manifest["operations"] = operations
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def confirm_extraction_rerun(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator whether one completed extraction should be rerun destructively.
    @param[in]  window Active main window shell.
    @param[in]  language Current UI language code.
    @return     True when the operator accepts the rerun reset.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    decision = QMessageBox.question(
        window,
        ui_state_service.translate("dialog.confirm_extraction_rerun_title", language),
        ui_state_service.translate("project.confirm_extraction_rerun", language),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return decision == QMessageBox.StandardButton.Yes


def confirm_cleanup_rerun(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator whether one completed cleanup should be rerun destructively.
    @param[in]  window Active main window shell.
    @param[in]  language Current UI language code.
    @return     True when the operator accepts the rerun reset.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    decision = QMessageBox.question(
        window,
        ui_state_service.translate("dialog.confirm_cleanup_rerun_title", language),
        ui_state_service.translate("project.confirm_cleanup_rerun", language),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return decision == QMessageBox.StandardButton.Yes


def confirm_ai_cleanup_start(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator whether one AI-assisted cleanup should start.
    @param[in]  window Active main window shell.
    @param[in]  language Current UI language code.
    @return     True when the operator accepts the longer AI run.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    decision = QMessageBox.question(
        window,
        ui_state_service.translate("dialog.confirm_ai_cleanup_title", language),
        ui_state_service.translate("project.confirm_ai_cleanup", language),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return decision == QMessageBox.StandardButton.Yes


def confirm_ai_cleanup_rerun(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator whether one completed cleanup should be replaced by AI cleanup.
    @param[in]  window Active main window shell.
    @param[in]  language Current UI language code.
    @return     True when the operator accepts the destructive AI rerun.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    decision = QMessageBox.question(
        window,
        ui_state_service.translate("dialog.confirm_ai_cleanup_rerun_title", language),
        ui_state_service.translate("project.confirm_ai_cleanup_rerun", language),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return decision == QMessageBox.StandardButton.Yes


def prompt_ai_cleanup_instructions(window: "MainWindow", language: str) -> str | None:
    """
    @brief      Ask the operator for optional extra AI cleanup prompt rules.
    @param[in]  window Active main window shell.
    @param[in]  language Runtime UI language code.
    @return     Extra cleanup instructions, an empty string, or None when cancelled.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    instructions = misc_ui_controller.prompt_multiline_text(
        window,
        ui_state_service.translate("dialog.ai_cleanup_extra_prompt_title", language),
        ui_state_service.translate("dialog.ai_cleanup_extra_prompt_label", language),
        "",
    )
    if instructions is None:
        return None
    return instructions.strip()


def _resolve_ai_profile(
    settings_payload: dict[str, object],
    profile_id: str | None,
) -> dict[str, object] | None:
    """
    @brief      Resolve the ai profile.
    @param[in]  settings_payload Payload for `settings_payload`.
    @param[in]  profile_id Profile identifier.
    @return     Derived helper result.
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
        if not isinstance(profile, dict):
            continue
        if not bool(profile.get("enabled", True)):
            continue
        if str(profile.get("id", "")).strip() == str(profile_id).strip():
            return dict(profile)
    return None


# END OF FILE
