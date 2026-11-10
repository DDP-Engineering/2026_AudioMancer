#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""Coordinate Book Analysis start/resume, status synchronization, and reset."""

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import (
    ai_budget_service,
    book_analysis_document_service,
    book_analysis_service,
    chunking_document_service,
    project_workspace_service,
    ui_state_service,
)
from audiomancer.ui.controllers import (
    misc_ui_controller,
    operation_runner_controller,
    workflow_controller_service,
)

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


def handle_analyze_requested(window: "MainWindow", profile_id: str) -> None:
    """Validate prerequisites and start or resume the selected candidate."""
    if window._active_operation_kind is not None:
        return
    if window._current_project_root is None or window._current_manifest is None:
        _show_warning(window, "project.error_no_active_project")
        return
    chunking_document = chunking_document_service.load_chunking_document(
        window._current_project_root
    )
    if not isinstance(chunking_document, dict) or chunking_document.get("status") != "completed":
        _show_warning(window, "project.error_missing_chunk_artifact")
        return
    profile = workflow_controller_service.resolve_enabled_ai_profile(
        window._settings_payload,
        profile_id,
    )
    if profile is None:
        _show_warning(window, "book_analysis.error_missing_profile")
        return
    if ai_budget_service.effective_context_window(profile, default=0) < config.BOOK_ANALYSIS_MIN_CONTEXT_TOKENS:
        _show_warning(window, "book_analysis.error_incompatible_profile")
        return
    target_language = str(window._current_manifest.get("target_language", "")).strip()
    if not target_language:
        _show_warning(window, "book_analysis.error_missing_target_language")
        return

    window._book_analysis_reset_pending = False
    _sync_running_summary(window)
    language = ui_state_service.current_language_from_settings(window._settings_payload)
    workflow_controller_service.start_operation(
        window,
        operation_kind="book_analysis",
        operation_name=ui_state_service.translate("book_analysis.analyze", language),
        initial_message=ui_state_service.translate("progress.book_analysis", language),
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            book_analysis_service.analyze_book(
                project_root,
                profile,
                str(manifest.get("target_language", "")).strip(),
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        ),
        set_busy=window._book_analysis_page.set_busy,
        success_handler=lambda result: _handle_success(window, result),
        failure_handler=lambda error: _handle_failure(window, error),
        cancel_handler=lambda message: _handle_cancelled(window, message),
    )
    refresh_page = getattr(window, "refresh_current_page_state", None)
    if callable(refresh_page):
        refresh_page()


def handle_reset_requested(window: "MainWindow") -> None:
    """Reset immediately when idle or cancel the active worker before deleting."""
    if window._current_project_root is None or window._current_manifest is None:
        return
    if window._active_operation_kind == "book_analysis":
        window._book_analysis_reset_pending = True
        operation_runner_controller.request_operation_cancel(window)
        return
    if window._active_operation_kind is not None:
        return
    _perform_reset(window)


def _handle_success(window: "MainWindow", result: object) -> None:
    _ = result
    if _perform_pending_reset(window):
        return
    _sync_from_document(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.book_analysis_completed",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def _handle_failure(window: "MainWindow", error: Exception) -> None:
    if _perform_pending_reset(window):
        return
    _sync_from_document(window)
    QMessageBox.warning(
        window,
        ui_state_service.translate(
            "dialog.project_error_title",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
        str(error),
    )


def _handle_cancelled(window: "MainWindow", message: str) -> None:
    _ = message
    if _perform_pending_reset(window):
        return
    _sync_from_document(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.operation_cancelled",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def _sync_running_summary(window: "MainWindow") -> None:
    updated = project_workspace_service.sync_manifest_operation_summary(
        window._current_project_root,
        "book_analysis",
        {
            "status": "running",
            "progress_current": 0,
            "progress_total": 1,
            "mode": "ai_assisted",
            "warning_count": 0,
        },
        current_stage=None,
    )
    window._current_manifest = updated
    refresh_status = getattr(window, "_refresh_operation_status_control", None)
    if callable(refresh_status):
        refresh_status(updated)


def _sync_from_document(window: "MainWindow") -> None:
    if window._current_project_root is None:
        return
    document = book_analysis_document_service.load_document(window._current_project_root)
    operation_state = book_analysis_document_service.derive_operation_state(document)
    project_workspace_service.sync_manifest_operation_summary(
        window._current_project_root,
        "book_analysis",
        operation_state,
        current_stage=None,
    )
    _reload_project_state(window)


def _perform_pending_reset(window: "MainWindow") -> bool:
    if not bool(getattr(window, "_book_analysis_reset_pending", False)):
        return False
    _perform_reset(window)
    return True


def _perform_reset(window: "MainWindow") -> None:
    if window._current_project_root is None:
        return
    book_analysis_service.reset_book_analysis(window._current_project_root)
    window._book_analysis_reset_pending = False
    project_workspace_service.sync_manifest_operation_summary(
        window._current_project_root,
        "book_analysis",
        None,
        current_stage=None,
    )
    _reload_project_state(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.book_analysis_reset",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def _reload_project_state(window: "MainWindow") -> None:
    if window._current_project_root is None:
        return
    manifest = project_workspace_service.load_manifest(window._current_project_root)
    show_project_state = getattr(window, "show_project_state", None)
    if callable(show_project_state):
        show_project_state(window._current_project_root, manifest)
    else:
        window._current_manifest = manifest


def _show_warning(window: "MainWindow", message_key: str) -> None:
    language = ui_state_service.current_language_from_settings(window._settings_payload)
    QMessageBox.warning(
        window,
        ui_state_service.translate("dialog.project_error_title", language),
        ui_state_service.translate(message_key, language),
    )


# END OF FILE
