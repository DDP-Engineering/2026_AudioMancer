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
@version 0.10.0
"""

# IMPORTS

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    chunking_document_service,
    operation_runtime_service,
    project_workspace_service,
    text_cleanup_state_service,
    ui_state_service,
)
from audiomancer.ui.controllers import misc_ui_controller, workflow_controller_service

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
    @date       2026-05-12
    @version    0.5.0
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
    try:
        translation_document = ai_translation_service.load_translation_document(window._current_project_root)
    except ai_translation_service.TranslationDocumentError as exc:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(exc),
        )
        return
    translation_status = (
        ai_translation_service.TRANSLATION_STATUS_NOT_STARTED
        if translation_document is None
        else str(translation_document["status"])
    )
    additional_translation_instructions = None
    if translation_status in {
        ai_translation_service.TRANSLATION_STATUS_RUNNING,
        ai_translation_service.TRANSLATION_STATUS_IN_PROGRESS,
        ai_translation_service.TRANSLATION_STATUS_CANCELLED,
        ai_translation_service.TRANSLATION_STATUS_FAILED,
    }:
        pass
    else:
        additional_translation_instructions = prompt_ai_translation_instructions(window, current_language)
        if additional_translation_instructions is None:
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
                additional_translation_instructions=additional_translation_instructions,
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
    @date       2026-05-12
    @version    0.4.0
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
    additional_translation_instructions = prompt_ai_translation_instructions(window, current_language)
    if additional_translation_instructions is None:
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
                additional_translation_instructions=additional_translation_instructions,
            )
        ),
    )


def handle_reset_translation_requested(window: "MainWindow") -> None:
    """
    @brief      Confirm and reset translation runtime data while preserving narrator profiles.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.4.0
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
    updated_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
        window._current_manifest,
        "translation",
        preserve_operation_kinds=operation_runtime_service.NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS,
    )
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.translation_reset", current_language),
    )


def _translation_manifest_stage(summary: dict[str, object]) -> str:
    """
    @brief      Resolve the manifest stage implied by the current translation report.
    @param[in]  report Latest translation report payload.
    @return     Workflow stage that remains valid after the translation update.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    if str(summary.get("status", "")) == ai_translation_service.TRANSLATION_STATUS_COMPLETED:
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
    report = ai_translation_service.approve_all(window._current_project_root)
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
    @version    0.3.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    report = ai_translation_service.approve_chunk(window._current_project_root, chunk_id)
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
    workflow_controller_service.start_operation(
        window,
        operation_kind="translation",
        operation_name=operation_name,
        initial_message=initial_message,
        worker_callable=worker_callable,
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
    @version    0.2.0
    """
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    if _translation_manifest_stage(report) == "translation_ready":
        operation_runtime_service.reset_operation_data(
            window._current_project_root,
            "translation",
            include_current=False,
            preserve_operation_kinds=operation_runtime_service.NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS,
        )
        default_operations = text_cleanup_state_service.normalized_manifest_operations({})
        preserved_operation_kinds = operation_runtime_service.NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS
        for selected_kind in operation_runtime_service.downstream_operation_kinds(
            "translation",
            include_current=False,
        ):
            if selected_kind in default_operations and selected_kind not in preserved_operation_kinds:
                operations[selected_kind] = default_operations[selected_kind]
    operations["translation"] = {
        "status": str(report.get("status", ai_translation_service.TRANSLATION_STATUS_NOT_STARTED)),
        "progress_current": int(report.get("translated_count", 0) or 0),
        "progress_total": int(report.get("total_count", 0) or 0),
        "mode": "ai_assisted",
        "warning_count": int(report.get("warning_count", 0) or 0),
    }
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
    if window._current_project_root is None:
        return
    try:
        summary = ai_translation_service.load_translation_summary(window._current_project_root)
    except ai_translation_service.TranslationDocumentError:
        window.show_project_state(
            window._current_project_root,
            project_workspace_service.load_manifest(window._current_project_root),
        )
        return
    _sync_manifest_after_translation(window, summary)


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
    return workflow_controller_service.resolve_enabled_ai_profile(settings_payload, profile_id)


def prompt_ai_translation_instructions(window: "MainWindow", language: str) -> str | None:
    """
    @brief      Ask the operator for optional extra AI translation prompt rules.
    @param[in]  window Active main window shell.
    @param[in]  language Runtime UI language code.
    @return     Extra translation instructions, an empty string, or None when cancelled.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    instructions = misc_ui_controller.prompt_multiline_text(
        window,
        ui_state_service.translate("dialog.ai_translation_extra_prompt_title", language),
        ui_state_service.translate("dialog.ai_translation_extra_prompt_label", language),
        "",
    )
    if instructions is None:
        return None
    return instructions.strip()


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
    return bool(chunking_document_service.load_chunks(project_root))


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
# END OF FILE
