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
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.9.5
"""

# IMPORTS

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from audiomancer import config
from audiomancer.services import (
    home_presenter_service,
    import_service,
    project_export_service,
    project_snapshot_service,
    project_workspace_service,
    ui_state_service,
)
from audiomancer.ui.controllers import misc_ui_controller, operation_runner_controller

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


# PUBLIC API


def handle_new_project_requested(window: "MainWindow") -> None:
    """
    @brief      Collect inputs and create a new project workspace.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.4.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    selected_parent = QFileDialog.getExistingDirectory(
        window,
        ui_state_service.translate(
            "dialog.select_project_parent_title",
            current_language,
        ),
        str(window._current_project_root.parent) if window._current_project_root is not None else str(config.APP_ROOT),
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
    except (FileExistsError, FileNotFoundError, ValueError) as error:
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
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    selected_folder = QFileDialog.getExistingDirectory(
        window,
        ui_state_service.translate("dialog.open_project_title", current_language),
        str(window._current_project_root or config.APP_ROOT),
    )
    if not selected_folder:
        return

    try:
        open_result = project_workspace_service.open_project(selected_folder)
    except (FileNotFoundError, ValueError) as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return

    if str(open_result.get("status")) == "repair_required":
        if not confirm_project_repair(window, open_result, current_language):
            return
        repaired_result = project_workspace_service.repair_project(open_result)
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


def handle_import_source_requested(window: "MainWindow") -> None:
    """
    @brief      Let the operator select and import one source file.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.2
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
        source_document = import_service.import_source(
            window._current_project_root,
            selected_file,
            previous_source_document if isinstance(previous_source_document, dict) else None,
        )
    except (FileNotFoundError, ValueError) as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return

    updated_manifest = dict(window._current_manifest)
    updated_manifest["source_document"] = source_document
    updated_manifest["current_stage"] = "source_selected"
    if not bool(updated_manifest.get("project_options_locked", False)):
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
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

    export_path = Path(selected_path)
    if export_path.suffix.lower() != required_extension:
        export_path = export_path.with_suffix(required_extension)
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.3.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.1
    """
    window.stop_all_audio_playback()
    window.set_project_active(True)
    window._current_page_id = "home"
    home_page = window._page_registry.get("home")
    if home_page is not None:
        window._stack.setCurrentWidget(home_page)
        window._sidebar.set_current_page("home")
    window.show_project_state(project_root, manifest)


def _export_dialog_filter(export_format: str, language: str) -> str:
    """
    @brief      Build the save-file dialog filter for one export format.
    @param[in]  export_format Stable export format token.
    @param[in]  language Current UI language code.
    @return     QFileDialog filter string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    if export_format == project_export_service.EXPORT_FORMAT_ZIP:
        return ui_state_service.translate("dialog.snapshot_filter_zip", language)
    if export_format == project_export_service.EXPORT_FORMAT_MARKDOWN:
        return ui_state_service.translate("dialog.export_filter_markdown", language)
    return ui_state_service.translate("dialog.export_filter_txt", language)


# END OF FILE
