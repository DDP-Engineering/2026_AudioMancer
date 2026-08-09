#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file home_ui_controller.py
@brief Home-page UI controller for AudioMancer.
@details Handles project creation, opening, repair confirmation, activation,
         and source import workflows owned by the Home page.
"""

# IMPORTS

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from audiomancer import config
from audiomancer.services import (
    audio_blocks_service,
    home_presenter_service,
    import_service,
    operation_runtime_service,
    project_export_service,
    project_snapshot_service,
    project_workspace_service,
    speech_blocks_service,
    text_cleanup_state_service,
    text_extraction_service,
    ui_state_service,
)
from audiomancer.ui.controllers import misc_ui_controller, operation_runner_controller

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


# PUBLIC API


def handle_new_project_requested(window: "MainWindow") -> None:
    """
    @brief      Collect inputs and create a new project workspace.
    @details    The parent-folder picker starts at the active project's parent
                when one is open, and at the per-user documents root otherwise.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if not _confirm_cleanup_draft_discard(window, current_language):
        return
    selected_parent = QFileDialog.getExistingDirectory(
        window,
        ui_state_service.translate(
            "dialog.select_project_parent_title",
            current_language,
        ),
        str(window._current_project_root.parent)
        if window._current_project_root is not None
        else str(config.resolve_user_documents_root()),
    )
    if not selected_parent:
        return

    project_name, accepted = QInputDialog.getText(
        window,
        ui_state_service.translate("dialog.new_project_title", current_language),
        ui_state_service.translate("project.project_name", current_language),
    )
    if not accepted:
        return

    project_name = project_name.strip()
    if not project_name:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_missing_name", current_language),
        )
        return

    try:
        project_root, manifest = project_workspace_service.create_project(
            project_name,
            selected_parent,
        )
    except (OSError, ValueError) as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return

    activate_project(window, project_root, manifest)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.project_created", current_language),
    )


def handle_open_project_requested(window: "MainWindow") -> None:
    """
    @brief      Let the operator select and open one existing project folder.
    @details    The folder picker starts at the active project root when one is
                open, and at the per-user documents root otherwise. Expected
                validation and filesystem failures use the existing localized
                project-error warning instead of escaping the Qt slot.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if not _confirm_cleanup_draft_discard(window, current_language):
        return
    selected_folder = QFileDialog.getExistingDirectory(
        window,
        ui_state_service.translate("dialog.open_project_title", current_language),
        str(window._current_project_root or config.resolve_user_documents_root()),
    )
    if not selected_folder:
        return

    try:
        open_result = project_workspace_service.open_project(selected_folder)
    except (OSError, ValueError) as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return

    if str(open_result.get("status")) == "repair_required":
        show_project_open_recovery(window, open_result, current_language)
        if not confirm_project_repair(window, open_result, current_language):
            return
        try:
            repaired_result = project_workspace_service.repair_project(open_result)
        except (OSError, ValueError) as error:
            QMessageBox.warning(
                window,
                ui_state_service.translate("dialog.project_error_title", current_language),
                str(error),
            )
            return
        project_root = Path(str(repaired_result["project_root"]))
        manifest = dict(repaired_result["manifest"])
        activate_project(window, project_root, manifest)
        misc_ui_controller.show_message(
            window,
            ui_state_service.translate("status.project_repaired", current_language),
        )
        return

    project_root = Path(str(open_result["project_root"]))
    manifest = dict(open_result["manifest"])
    activate_project(window, project_root, manifest)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.project_opened", current_language),
    )
    show_project_open_recovery(window, open_result, current_language)


def show_project_open_recovery(
    window: "MainWindow",
    open_result: dict[str, object],
    language: str,
) -> None:
    """
    @brief      Show one operator message for automatic project recovery.
    @param[in]  window Active main window shell.
    @param[in]  open_result Tagged project-open result dictionary.
    @param[in]  language Current UI language code.
    @return     None.
    @exception  None
    """
    recovered_operations = open_result.get("recovered_operations")
    if not isinstance(recovered_operations, list) or "chunking" not in recovered_operations:
        return
    QMessageBox.information(
        window,
        ui_state_service.translate("dialog.project_recovery_title", language),
        ui_state_service.translate("project.chunking_self_heal_message", language),
    )


def handle_import_source_requested(window: "MainWindow") -> None:
    """
    @brief      Let the operator select and import one source file.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_no_active_project", current_language),
        )
        return

    if bool(window._current_manifest.get("project_options_locked", False)):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_project_already_started", current_language),
        )
        return

    selected_file, _selected_filter = QFileDialog.getOpenFileName(
        window,
        ui_state_service.translate("dialog.select_source_title", current_language),
        str(window._current_project_root),
        ui_state_service.translate("dialog.select_source_filter", current_language),
    )
    if not selected_file:
        return

    try:
        previous_source_document = window._current_manifest.get("source_document")
        if import_service.is_same_source_selection(
            window._current_project_root,
            selected_file,
            previous_source_document if isinstance(previous_source_document, dict) else None,
        ):
            return
        source_document = import_service.import_source(
            window._current_project_root,
            selected_file,
            previous_source_document if isinstance(previous_source_document, dict) else None,
        )
    except (OSError, ValueError) as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return

    replacing_source = isinstance(previous_source_document, dict)
    updated_manifest = dict(window._current_manifest)
    updated_manifest["source_document"] = source_document
    if replacing_source:
        text_extraction_service.reset_extraction_and_downstream(
            window._current_project_root,
        )
        updated_manifest = text_cleanup_state_service.build_manifest_after_extraction_reset(
            updated_manifest,
        )
    else:
        updated_manifest["current_stage"] = "source_selected"
    if not replacing_source and not bool(updated_manifest.get("project_options_locked", False)):
        target_language, voice_assignment_mode = window._home_page.selected_project_options()
        updated_manifest["target_language"] = target_language
        updated_manifest["selected_voice_language"] = target_language
        updated_manifest["voice_assignment_mode"] = voice_assignment_mode
    project_workspace_service.save_manifest(
        updated_manifest,
        window._current_project_root,
    )
    reloaded_manifest = project_workspace_service.load_manifest(window._current_project_root)
    window.show_project_state(window._current_project_root, reloaded_manifest)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.source_imported", current_language),
    )


def handle_project_options_lock_requested(
    window: "MainWindow",
    target_language: str,
    voice_assignment_mode: str,
) -> None:
    """
    @brief      Confirm and lock project-level audiobook options.
    @param[in]  window Active main window shell.
    @param[in]  target_language Requested project target language.
    @param[in]  voice_assignment_mode Requested narration mode.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_no_active_project", current_language),
        )
        return
    if bool(window._current_manifest.get("project_options_locked", False)):
        return
    if home_presenter_service.source_document_name(window._current_manifest) is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_start_project_missing_source", current_language),
        )
        return
    decision = QMessageBox.question(
        window,
        ui_state_service.translate("dialog.confirm_project_options_title", current_language),
        ui_state_service.translate("project.confirm_project_options_lock", current_language),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if decision != QMessageBox.StandardButton.Yes:
        return
    try:
        manifest = project_workspace_service.lock_project_options(
            window._current_project_root,
            target_language,
            voice_assignment_mode,
        )
    except ValueError as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return
    window.show_project_state(window._current_project_root, manifest)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.project_options_locked", current_language),
    )


def handle_export_requested(window: "MainWindow", export_kind: str, export_format: str) -> None:
    """
    @brief      Export one ready project artifact to a user-selected external file.
    @param[in]  window Active main window shell.
    @param[in]  export_kind Stable export kind token.
    @param[in]  export_format Stable export format token.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_no_active_project", current_language),
        )
        return

    export_states = project_export_service.build_export_states(window._current_project_root, window._current_manifest)
    selected_state = next(
        (state for state in export_states if str(state.get("export_kind", "")) == str(export_kind)),
        None,
    )
    if selected_state is None or not bool(selected_state.get("can_export", False)):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("home.export_not_ready_message", current_language),
        )
        return

    try:
        default_file_name = project_export_service.default_export_file_name(
            window._current_manifest,
            export_kind,
            export_format,
        )
        required_extension = project_export_service.export_extension(export_format)
    except ValueError as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return

    selected_path, _selected_filter = QFileDialog.getSaveFileName(
        window,
        ui_state_service.translate("dialog.export_title", current_language),
        str(window._current_project_root.parent / default_file_name),
        _export_dialog_filter(export_format, current_language),
    )
    if not selected_path:
        return

    export_path = operation_runtime_service.append_required_extension(
        selected_path,
        required_extension,
    )
    if project_export_service.is_path_inside_project(window._current_project_root, export_path):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("home.export_inside_project_message", current_language),
        )
        return

    try:
        export_path.parent.mkdir(parents=True, exist_ok=True)
        if export_format == project_export_service.EXPORT_FORMAT_ZIP:
            project_export_service.create_archive_export(
                window._current_project_root,
                window._current_manifest,
                export_kind,
                export_path,
            )
        else:
            export_content = project_export_service.render_export(
                window._current_project_root,
                window._current_manifest,
                export_kind,
                export_format,
            )
            export_path.write_text(export_content, encoding="utf-8")
    except (OSError, ValueError) as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return

    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.project_exported", current_language),
    )


def handle_project_snapshot_requested(window: "MainWindow") -> None:
    """
    @brief      Export one complete project ZIP snapshot to an external path.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_no_active_project", current_language),
        )
        return

    if window._active_operation_kind is not None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("home.snapshot_active_operation_message", current_language),
        )
        return

    default_file_name = project_snapshot_service.default_snapshot_file_name(
        window._current_project_root,
        window._current_manifest,
    )
    selected_path, _selected_filter = QFileDialog.getSaveFileName(
        window,
        ui_state_service.translate("dialog.snapshot_title", current_language),
        str(window._current_project_root.parent / default_file_name),
        ui_state_service.translate("dialog.snapshot_filter_zip", current_language),
    )
    if not selected_path:
        return

    snapshot_path = project_snapshot_service.ensure_snapshot_extension(selected_path)
    if project_snapshot_service.is_path_inside_project(window._current_project_root, snapshot_path):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("home.snapshot_inside_project_message", current_language),
        )
        return

    operation_runner_controller.start_threaded_operation(
        window,
        operation_kind="project_snapshot",
        operation_name=ui_state_service.translate("home.export_project_zip", current_language),
        initial_message=ui_state_service.translate("progress.project_snapshot", current_language),
        worker_callable=lambda project_root, _manifest, progress_callback=None, cancel_requested=None: (
            project_snapshot_service.create_project_snapshot(
                project_root,
                snapshot_path,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        ),
        set_busy=lambda _busy: None,
        success_handler=lambda _result_payload: _handle_project_snapshot_success(window),
        failure_handler=lambda error: _handle_project_snapshot_failure(window, error),
        cancel_handler=lambda _message: _handle_project_snapshot_cancelled(window),
        cancellable=True,
    )


def _handle_project_snapshot_success(window: "MainWindow") -> None:
    """
    @brief      Show the operator-facing success message after ZIP snapshot export.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.project_snapshot_exported", current_language),
    )


def _handle_project_snapshot_failure(window: "MainWindow", error: Exception) -> None:
    """
    @brief      Show the operator-facing failure message after ZIP snapshot export.
    @param[in]  window Active main window shell.
    @param[in]  error Raised snapshot export exception.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    QMessageBox.warning(
        window,
        ui_state_service.translate("dialog.project_error_title", current_language),
        f"{ui_state_service.translate('home.snapshot_failure_message', current_language)}\n\n{error}",
    )


def _handle_project_snapshot_cancelled(window: "MainWindow") -> None:
    """
    @brief      Show the operator-facing cancellation message after ZIP snapshot export.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.project_snapshot_cancelled", current_language),
    )


def confirm_project_repair(
    window: "MainWindow",
    repair_result: dict[str, object],
    language: str,
) -> bool:
    """
    @brief      Ask the operator whether one recoverable project should be repaired.
    @param[in]  window Active main window shell.
    @param[in]  repair_result Recoverable project repair result payload.
    @param[in]  language Current UI language code.
    @return     True when the operator accepts the repair.
    @exception  None
    """
    if bool(repair_result.get("metadata_only", False)):
        repair_detail = ui_state_service.translate(
            "project.repair_metadata_only",
            language,
        )
        change_lines = _repair_summary_lines(
            repair_result.get("changes"),
            ui_state_service.translate("project.repair_changes_header", language),
        )
        warning_lines = _repair_summary_lines(
            repair_result.get("warnings"),
            ui_state_service.translate("project.repair_warnings_header", language),
        )
        if change_lines:
            repair_detail = f"{repair_detail}\n\n{change_lines}"
        if warning_lines:
            repair_detail = f"{repair_detail}\n\n{warning_lines}"
    else:
        repair_detail = (
            f"{ui_state_service.translate('project.repair_step_prefix', language)} "
            f"{repair_result.get('corrupted_step')}. "
            f"{ui_state_service.translate('project.repair_reset_suffix', language)}"
        )
    decision = QMessageBox.question(
        window,
        ui_state_service.translate("dialog.project_repair_title", language),
        (
            f"{repair_result.get('message')}\n\n"
            f"{repair_detail}\n"
            f"{ui_state_service.translate('project.repair_confirm', language)}"
        ),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    return decision == QMessageBox.StandardButton.Yes


def _repair_summary_lines(value: object, header_text: str) -> str:
    """
    @brief      Format repair report lines for the confirmation dialog.
    @param[in]  value Candidate repair report list.
    @param[in]  header_text Localized section header.
    @return     Dialog-ready text block, or an empty string.
    @exception  None
    """
    if not isinstance(value, list) or not value:
        return ""
    return "\n".join((f"{header_text}:", *(f"- {item}" for item in value)))


def activate_project(
    window: "MainWindow",
    project_root: Path,
    manifest: dict[str, object],
) -> None:
    """
    @brief      Apply one active project into the current shell state.
    @param[in]  window Active main window shell.
    @param[in]  project_root Resolved active project root.
    @param[in]  manifest Loaded active project manifest.
    @return     None.
    @exception  None
    """
    window.stop_all_audio_playback()
    try:
        speech_blocks_service.load_speech_blocks_document(project_root)
        audio_blocks_service.reconcile_audio_playability(project_root)
    except (speech_blocks_service.SpeechBlocksDocumentError, audio_blocks_service.AudioBlocksDocumentError) as error:
        current_language = ui_state_service.current_language_from_settings(window._settings_payload)
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
    window._text_cleanup_page.discard_cleaned_text_edit()
    window.set_project_active(True)
    window._current_page_id = "home"
    home_page = window._page_registry.get("home")
    if home_page is not None:
        window._stack.setCurrentWidget(home_page)
        window._sidebar.set_current_page("home")
    window.show_project_state(project_root, manifest)


def _confirm_cleanup_draft_discard(window: "MainWindow", language: str) -> bool:
    """Confirm discarding a modified Cleanup draft before project selection."""
    if not window._text_cleanup_page.has_modified_cleaned_text_draft():
        return True
    decision = QMessageBox.question(
        window,
        ui_state_service.translate("dialog.confirm_cleanup_draft_discard_title", language),
        ui_state_service.translate("project.confirm_cleanup_draft_discard", language),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return decision == QMessageBox.StandardButton.Yes


def _export_dialog_filter(export_format: str, language: str) -> str:
    """
    @brief      Build the save-file dialog filter for one export format.
    @param[in]  export_format Stable export format token.
    @param[in]  language Current UI language code.
    @return     QFileDialog filter string.
    @exception  None
    """
    if export_format == project_export_service.EXPORT_FORMAT_ZIP:
        return ui_state_service.translate("dialog.snapshot_filter_zip", language)
    if export_format == project_export_service.EXPORT_FORMAT_MARKDOWN:
        return ui_state_service.translate("dialog.export_filter_markdown", language)
    return ui_state_service.translate("dialog.export_filter_txt", language)


# END OF FILE
