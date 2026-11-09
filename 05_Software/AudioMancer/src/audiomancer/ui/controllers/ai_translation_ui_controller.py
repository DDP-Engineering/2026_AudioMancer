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
"""

# IMPORTS

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    chunking_document_service,
    project_workspace_service,
    ui_state_service,
)
from audiomancer.services.persistence_service import ProjectFileRecoveryError
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
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._active_operation_kind is not None:
        return
    if window._current_project_root is None or window._current_manifest is None:
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
    if translation_document is None or str(translation_document["status"]) == (
        ai_translation_service.TRANSLATION_STATUS_NOT_STARTED
    ):
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
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    if not misc_ui_controller.confirm_question(
        window,
        current_language,
        "dialog.confirm_translation_reset_title",
        "project.confirm_translation_reset",
    ):
        return
    try:
        ai_translation_service.reset_translation(window._current_project_root)
    except (OSError, ValueError) as error:
        _show_translation_error(window, error)
        return
    _refresh_project(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.translation_reset", current_language),
    )


def handle_approve_all_requested(window: "MainWindow") -> None:
    """
    @brief      Approve every translated chunk that is still pending review.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    try:
        ai_translation_service.approve_all(window._current_project_root)
    except (OSError, ValueError) as error:
        _show_translation_error(window, error)
        return
    _refresh_project(window)


def handle_approve_selected_requested(window: "MainWindow", chunk_id: str) -> None:
    """
    @brief      Approve one selected translated chunk.
    @param[in]  window Active main window instance.
    @param[in]  chunk_id Selected chunk identifier.
    @return     None.
    @exception  None
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    try:
        ai_translation_service.approve_chunk(window._current_project_root, chunk_id)
    except (OSError, ValueError) as error:
        _show_translation_error(window, error)
        return
    _refresh_project(window)
    window._ai_translation_page.advance_to_next_chunk()


def handle_translated_text_changed(window: "MainWindow", chunk_id: str, translated_text: str) -> None:
    """
    @brief      Persist one user edit to the translated text of a chunk.
    @param[in]  window Active main window instance.
    @param[in]  chunk_id Selected chunk identifier.
    @param[in]  translated_text Edited translated text.
    @return     None.
    @exception  None
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    try:
        ai_translation_service.update_translated_text(window._current_project_root, chunk_id, translated_text)
    except (OSError, ValueError) as error:
        window._ai_translation_page.retain_unsaved_edit(chunk_id, translated_text)
        _show_translation_error(window, error)
        return
    _refresh_project(window)


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
    """
    assert isinstance(result_payload, dict)
    _refresh_project(window)
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
    """
    _show_translation_error(window, error)
    if not isinstance(error, ProjectFileRecoveryError):
        _refresh_project(window)


def _handle_translation_cancelled(window: "MainWindow", message: str) -> None:
    """
    @brief      Refresh translation UI state after a cancelled worker run.
    @param[in]  window Active main window instance.
    @param[in]  message Cancellation message.
    @return     None.
    @exception  None
    """
    _ = message
    _refresh_project(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.operation_cancelled",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def _refresh_project(window: "MainWindow") -> None:
    """@brief Refresh from the service-published manifest."""
    if window._current_project_root is not None:
        window.show_project_state(
            window._current_project_root,
            project_workspace_service.load_manifest(window._current_project_root),
        )


def _show_translation_error(window: "MainWindow", error: Exception) -> None:
    """@brief Report a failed translation operation or edit."""
    QMessageBox.warning(
        window,
        ui_state_service.translate(
            "dialog.project_error_title", ui_state_service.current_language_from_settings(window._settings_payload)
        ),
        str(error),
    )


def _resolve_ai_profile(settings_payload: dict[str, object] | None, profile_id: str | None) -> dict[str, object] | None:
    """
    @brief      Resolve one enabled AI profile payload from settings by id.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  profile_id Requested profile identifier.
    @return     Resolved profile payload or `None`.
    @exception  None
    """
    return workflow_controller_service.resolve_enabled_ai_profile(settings_payload, profile_id)


def prompt_ai_translation_instructions(window: "MainWindow", language: str) -> str | None:
    """
    @brief      Ask the operator for optional extra AI translation prompt rules.
    @param[in]  window Active main window shell.
    @param[in]  language Runtime UI language code.
    @return     Extra translation instructions, an empty string, or None when cancelled.
    @exception  None
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
    """
    if isinstance(window._current_manifest, dict):
        target_language = str(
            window._current_manifest.get("target_language", config.DEFAULT_TRANSLATION_TARGET_LANGUAGE)
        ).strip()
        if target_language in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
            return target_language
    return config.DEFAULT_TRANSLATION_TARGET_LANGUAGE


# END OF FILE
