#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_translation_ui_controller.py
@brief AI Translation page UI controller for AudioMancer.
@details Handles translation start/continue, reset, approvals, chunk edits,
         selected-chunk retranslation, and modal progress lifecycle.
@author Eng. Dan Dumitru Pasare
@date 2026-04-22
@version 0.6.0
"""

# IMPORTS

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    deterministic_chunking_service,
    project_workspace_service,
    text_cleanup_state_service,
    ui_state_service,
)
from audiomancer.ui.controllers import misc_ui_controller, operation_runner_controller

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


# PUBLIC API


def handle_start_translation_requested(
    window: "MainWindow",
    profile_id: str,
) -> None:
    """
    @brief      Validate and start or continue one AI translation run.
    @param[in]  window Active main window instance.
    @param[in]  profile_id Selected enabled AI profile identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
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
    if not _has_chunking_output(window._current_project_root):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_missing_chunk_artifact", current_language),
        )
        return
    target_language = _manifest_target_language(window)
    profile_payload = _resolve_ai_profile(window._settings_payload, profile_id)
    if profile_payload is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_missing_ai_translation_profile", current_language),
        )
        return
    _start_operation(
        window,
        operation_name=ui_state_service.translate("ai_translation.start", current_language),
        initial_message=ui_state_service.translate("progress.ai_translation", current_language),
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            ai_translation_service.start_or_continue_translation(
                project_root,
                manifest,
                profile_payload,
                target_language,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        ),
    )


def handle_retranslate_selected_requested(
    window: "MainWindow",
    profile_id: str,
    chunk_id: str,
) -> None:
    """
    @brief      Re-translate one selected chunk through the AI workflow.
    @param[in]  window Active main window instance.
    @param[in]  profile_id Selected enabled AI profile identifier.
    @param[in]  chunk_id Selected chunk identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.3.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._active_operation_kind is not None:
        return
    if window._current_project_root is None or window._current_manifest is None:
        return
    target_language = _manifest_target_language(window)
    profile_payload = _resolve_ai_profile(window._settings_payload, profile_id)
    if profile_payload is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_missing_ai_translation_profile", current_language),
        )
        return
    _start_operation(
        window,
        operation_name=ui_state_service.translate("ai_translation.retranslate", current_language),
        initial_message=ui_state_service.translate("progress.ai_translation_retranslate", current_language),
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            ai_translation_service.retranslate_chunk(
                project_root,
                manifest,
                profile_payload,
                target_language,
                chunk_id,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        ),
    )


def handle_reset_translation_requested(window: "MainWindow") -> None:
    """
    @brief      Confirm and reset all persisted translation runtime data.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    decision = QMessageBox.question(
        window,
        ui_state_service.translate("dialog.confirm_translation_reset_title", current_language),
        ui_state_service.translate("project.confirm_translation_reset", current_language),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if decision != QMessageBox.StandardButton.Yes:
        return
    ai_translation_service.reset_translation(window._current_project_root)
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operations["translation"] = text_cleanup_state_service.normalized_manifest_operations({})["translation"]
    updated_manifest["operations"] = operations
    updated_manifest["current_stage"] = "translation_ready"
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.translation_reset", current_language),
    )


def _translation_manifest_stage(report: dict[str, object]) -> str:
    """
    @brief      Resolve the manifest stage implied by the current translation report.
    @param[in]  report Latest translation report payload.
    @return     Workflow stage that remains valid after the translation update.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    total_chunk_count = int(report.get("total_chunk_count", 0) or 0)
    approved_chunk_count = int(report.get("approved_chunk_count", 0) or 0)
    if total_chunk_count > 0 and approved_chunk_count == total_chunk_count:
        return "character_discovery_ready"
    return "translation_ready"


def handle_approve_all_requested(window: "MainWindow") -> None:
    """
    @brief      Approve every translated chunk that is still pending review.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.2.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    report = ai_translation_service.approve_all(
        window._current_project_root,
        _persisted_target_language(window),
        _persisted_profile_id(window),
    )
    _sync_manifest_after_translation(window, report)


def handle_approve_selected_requested(window: "MainWindow", chunk_id: str) -> None:
    """
    @brief      Approve one selected translated chunk.
    @param[in]  window Active main window instance.
    @param[in]  chunk_id Selected chunk identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    report = ai_translation_service.approve_chunk(
        window._current_project_root,
        chunk_id,
        _persisted_target_language(window),
        _persisted_profile_id(window),
    )
    _sync_manifest_after_translation(window, report)
    window._ai_translation_page.advance_to_next_chunk()


def handle_translated_text_changed(window: "MainWindow", chunk_id: str, translated_text: str) -> None:
    """
    @brief      Persist one user edit to the translated text of a chunk.
    @param[in]  window Active main window instance.
    @param[in]  chunk_id Selected chunk identifier.
    @param[in]  translated_text Edited translated text.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    report = ai_translation_service.update_translated_text(
        window._current_project_root,
        chunk_id,
        translated_text,
        _persisted_target_language(window),
        _persisted_profile_id(window),
    )
    _sync_manifest_after_translation(window, report)


# LOCAL HELPERS


def _start_operation(window: "MainWindow", operation_name: str, initial_message: str, worker_callable) -> None:
    """
    @brief      Start one translation operation on a worker thread.
    @param[in]  window Active main window instance.
    @param[in]  operation_name Operator-facing operation label.
    @param[in]  initial_message Initial progress-dialog message text.
    @param[in]  worker_callable Callable that performs the operation.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    operation_runner_controller.start_threaded_operation(
        window,
        "translation",
        operation_name,
        initial_message,
        worker_callable,
        set_busy=lambda is_busy: window._ai_translation_page.set_busy(is_busy),
        success_handler=lambda result_payload: _handle_translation_success(window, result_payload),
        failure_handler=lambda error: _handle_translation_failure(window, error),
        cancel_handler=lambda message: _handle_translation_cancelled(window, message),
    )


def _handle_translation_success(window: "MainWindow", result_payload: object) -> None:
    """
    @brief      Refresh translation UI state after a successful worker run.
    @param[in]  window Active main window instance.
    @param[in]  result_payload Worker result payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    assert isinstance(result_payload, dict)
    _sync_manifest_after_translation(window, result_payload)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.text_translated",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def _handle_translation_failure(window: "MainWindow", error: Exception) -> None:
    """
    @brief      Refresh translation UI state after a failed worker run.
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
        ui_state_service.translate(
            "dialog.project_error_title",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
        str(error),
    )


def _handle_translation_cancelled(window: "MainWindow", message: str) -> None:
    """
    @brief      Refresh translation UI state after a cancelled worker run.
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
        ui_state_service.translate(
            "status.operation_cancelled",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def _sync_manifest_after_translation(window: "MainWindow", report: dict[str, object]) -> None:
    """
    @brief      Persist the latest translation operation state into the manifest.
    @param[in]  window Active main window instance.
    @param[in]  report Latest translation report payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    operation_state = ai_translation_service.load_operation_state(window._current_project_root)
    if operation_state is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operations["translation"] = project_workspace_service.project_manifest_operation_summary(
        "translation",
        operation_state,
    )
    updated_manifest["operations"] = operations
    updated_manifest["current_stage"] = _translation_manifest_stage(report)
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _sync_manifest_from_disk(window: "MainWindow") -> None:
    """
    @brief      Reload persisted translation state from disk after failure or cancel.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.2.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operation_state = ai_translation_service.load_operation_state(window._current_project_root)
    if operation_state is not None:
        operations["translation"] = project_workspace_service.project_manifest_operation_summary(
            "translation",
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
    @date       2026-04-07
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


def _has_chunking_output(project_root: str | None) -> bool:
    """
    @brief      Determine whether chunking output exists for translation input.
    @param[in]  project_root Active project root path.
    @return     True when chunking output records can be loaded from disk.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if not project_root:
        return False
    return bool(deterministic_chunking_service.load_chunks(project_root))


def _persisted_target_language(window: "MainWindow") -> str:
    """
    @brief      Resolve the translation target language from the locked project options.
    @param[in]  window Active main window instance.
    @return     Persisted target language code.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    manifest_language = _manifest_target_language(window)
    if manifest_language:
        return manifest_language
    if window._current_project_root is None:
        return config.DEFAULT_TRANSLATION_TARGET_LANGUAGE
    report = ai_translation_service.load_translation_report(window._current_project_root)
    if isinstance(report, dict):
        target_language = str(report.get("target_language", "")).strip()
        if target_language:
            return target_language
    return config.DEFAULT_TRANSLATION_TARGET_LANGUAGE


def _manifest_target_language(window: "MainWindow") -> str:
    """
    @brief      Resolve the locked target language from the active manifest.
    @param[in]  window Active main window instance.
    @return     Supported target language code.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    if isinstance(window._current_manifest, dict):
        target_language = str(
            window._current_manifest.get("target_language", config.DEFAULT_TRANSLATION_TARGET_LANGUAGE)
        ).strip()
        if target_language in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
            return target_language
    return config.DEFAULT_TRANSLATION_TARGET_LANGUAGE


def _persisted_profile_id(window: "MainWindow") -> str | None:
    """
    @brief      Resolve the translation profile id from persisted state or UI.
    @param[in]  window Active main window instance.
    @return     Persisted or currently selected profile id.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if window._current_project_root is not None:
        report = ai_translation_service.load_translation_report(window._current_project_root)
        if isinstance(report, dict):
            profile_id = report.get("translation_profile_id_last_used")
            if profile_id not in (None, ""):
                return str(profile_id)
    return window._ai_translation_page.current_profile_id()


def _cancel_active_operation(window: "MainWindow") -> None:
    """
    @brief      Mark the active translation operation for cancellation.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    if window._active_operation_kind is not None:
        window._operation_cancel_requested = True


def _is_cancel_requested(window: "MainWindow") -> bool:
    """
    @brief      Check whether the current translation operation should cancel.
    @param[in]  window Active main window instance.
    @return     True when cancellation was requested.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.1
    """
    return window._operation_cancel_requested


# END OF FILE
