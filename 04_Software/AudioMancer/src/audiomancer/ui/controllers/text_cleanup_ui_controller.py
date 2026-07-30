#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
"""
@file text_cleanup_ui_controller.py
@brief UI orchestration for Extraction and the single hybrid Cleanup action.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from audiomancer.services import (
    project_workspace_service,
    text_cleanup_service,
    text_cleanup_state_service,
    text_extraction_service,
    ui_state_service,
)
from audiomancer.ui.controllers import misc_ui_controller, operation_runner_controller

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


def handle_extract_text_requested(window: MainWindow) -> None:
    """Start a fresh structural Extraction run."""
    if window._current_project_root is None or window._current_manifest is None:
        return
    language = ui_state_service.current_language_from_settings(window._settings_payload)
    if _completed_extraction_available(window._current_project_root):
        if not _confirm(
            window,
            ui_state_service.translate("dialog.confirm_extraction_rerun_title", language),
            ui_state_service.translate("project.confirm_extraction_rerun", language),
        ):
            return
        text_extraction_service.reset_extraction_and_downstream(window._current_project_root)
        window._current_manifest = text_cleanup_state_service.build_manifest_after_extraction_reset(
            window._current_manifest
        )
        project_workspace_service.save_manifest(window._current_manifest, window._current_project_root)
    start_operation(
        window,
        "extraction",
        ui_state_service.translate("text_cleanup.operation_extraction", language),
        ui_state_service.translate("text_cleanup.progress_extraction_start", language),
        text_extraction_service.extract_text,
        partial(handle_extraction_success, window),
        partial(handle_operation_failure, window),
    )


def handle_cleanup_requested(window: MainWindow, profile_id: str | None) -> None:
    """Run Cleanup with an optional compatible AI profile."""
    if window._current_project_root is None or window._current_manifest is None:
        return
    language = ui_state_service.current_language_from_settings(window._settings_payload)
    if not _completed_extraction_available(window._current_project_root):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", language),
            ui_state_service.translate("text_cleanup.error_extraction_required", language),
        )
        return
    try:
        existing = text_cleanup_service.load_cleanup_document(window._current_project_root)
    except ValueError:
        existing = None
    if existing is not None and not _confirm(
        window,
        ui_state_service.translate("dialog.confirm_cleanup_rerun_title", language),
        ui_state_service.translate("project.confirm_cleanup_rerun", language),
    ):
        return
    profile = _resolve_ai_profile(window._settings_payload, profile_id)
    start_operation(
        window,
        "cleanup",
        ui_state_service.translate("text_cleanup.operation_cleanup", language),
        ui_state_service.translate("text_cleanup.progress_cleanup_start", language),
        partial(
            text_cleanup_service.clean_text,
            ai_profile_payload=profile,
        ),
        partial(handle_cleanup_success, window),
        partial(handle_operation_failure, window),
    )


def handle_reset_cleanup_requested(window: MainWindow) -> None:
    """Reset Cleanup and downstream results after explicit confirmation."""
    if window._current_project_root is None or window._current_manifest is None:
        return
    language = ui_state_service.current_language_from_settings(window._settings_payload)
    if not _confirm(
        window,
        ui_state_service.translate("dialog.confirm_cleanup_reset_title", language),
        ui_state_service.translate("project.confirm_cleanup_reset", language),
    ):
        return
    updated_manifest = text_cleanup_state_service.reset_cleanup(
        window._current_project_root,
        window._current_manifest,
    )
    window.show_project_state(window._current_project_root, updated_manifest)
    misc_ui_controller.show_message(window, ui_state_service.translate("status.cleanup_reset", language))


def handle_save_cleaned_text_requested(window: MainWindow, cleaned_text: str) -> None:
    """Persist an optional operator correction and invalidate downstream text work."""
    if window._current_project_root is None or window._current_manifest is None:
        return
    language = ui_state_service.current_language_from_settings(window._settings_payload)
    scroll_state = window._text_cleanup_page.preview_scroll_state()
    try:
        updated_manifest = text_cleanup_state_service.save_cleaned_text_edit(
            window._current_project_root,
            window._current_manifest,
            cleaned_text,
        )
    except ValueError as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", language),
            str(error),
        )
        return
    window.show_project_state(window._current_project_root, updated_manifest)
    window._text_cleanup_page.restore_preview_scroll_state(scroll_state)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.cleaned_text_saved", language),
    )


def start_operation(
    window: MainWindow,
    operation_kind: str,
    operation_name: str,
    initial_message: str,
    worker_callable,
    success_handler,
    failure_handler,
) -> None:
    """Start one cancellable Extraction or Cleanup worker."""
    operation_runner_controller.start_threaded_operation(
        window,
        operation_kind,
        operation_name,
        initial_message,
        worker_callable,
        set_busy=lambda busy: window._text_cleanup_page.set_busy(
            busy,
            operation_name if busy else None,
        ),
        success_handler=success_handler,
        failure_handler=failure_handler,
        cancel_handler=lambda message: handle_operation_cancelled(window, message),
    )


def handle_extraction_success(window: MainWindow, result_payload: object) -> None:
    _ = result_payload
    assert window._current_project_root is not None
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


def handle_cleanup_success(window: MainWindow, result_payload: object) -> None:
    _ = result_payload
    assert window._current_project_root is not None
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.text_cleaned",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def handle_operation_failure(window: MainWindow, error: Exception) -> None:
    QMessageBox.warning(
        window,
        ui_state_service.translate(
            "dialog.project_error_title",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
        str(error),
    )


def handle_operation_cancelled(window: MainWindow, message: str) -> None:
    _ = message
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


def _resolve_ai_profile(
    settings_payload: dict[str, object],
    profile_id: str | None,
) -> dict[str, object] | None:
    if not profile_id:
        return None
    profiles = settings_payload.get("llm_profiles", [])
    if not isinstance(profiles, list):
        return None
    return next(
        (
            dict(profile)
            for profile in profiles
            if isinstance(profile, dict)
            and bool(profile.get("enabled", True))
            and str(profile.get("id") or "") == profile_id
        ),
        None,
    )


def _completed_extraction_available(project_root) -> bool:
    try:
        metadata = text_extraction_service.load_extraction_metadata(project_root)
    except (OSError, ValueError):
        return False
    return isinstance(metadata, dict) and metadata.get("status") == "completed"


def _confirm(window: MainWindow, title: str, message: str) -> bool:
    decision = QMessageBox.question(
        window,
        title,
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return decision == QMessageBox.StandardButton.Yes
