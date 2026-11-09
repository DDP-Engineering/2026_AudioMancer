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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from audiomancer import config
from audiomancer.services import (
    audio_blocks_service,
    operation_runtime_service,
    project_export_service,
    project_options_service,
    project_snapshot_service,
    project_workspace_service,
    speech_blocks_service,
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
    if getattr(window, "_active_operation_kind", None) is not None:
        return
    if window._ai_translation_page.flush_pending_translation_edit() is False:
        return
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

    selected_file, _selected_filter = QFileDialog.getOpenFileName(
        window,
        ui_state_service.translate("dialog.select_source_title", current_language),
        selected_parent,
        ui_state_service.translate("dialog.select_source_filter", current_language),
    )
    if not selected_file:
        return

    try:
        project_root, manifest = project_options_service.create_project_with_source(
            project_name,
            selected_parent,
            selected_file,
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
    if window._ai_translation_page.flush_pending_translation_edit() is False:
        return
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
    @brief      Import the first book for an existing source-less project.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None.
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if getattr(window, "_active_operation_kind", None) is not None:
        return
    if window._current_project_root is None or window._current_manifest is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_no_active_project", current_language),
        )
        return
    if isinstance(window._current_manifest.get("source_document"), dict):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_locked_source", current_language),
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
        target_language, voice_assignment_mode = window._home_page.selected_project_options()
        manifest = project_options_service.import_initial_source(
            window._current_project_root, selected_file, target_language, voice_assignment_mode
        )
    except (OSError, ValueError) as error:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            str(error),
        )
        return
    window.show_project_state(window._current_project_root, manifest)
    misc_ui_controller.show_message(window, ui_state_service.translate("status.source_imported", current_language))


def handle_project_options_change_requested(
    window: "MainWindow", target_language: str, voice_assignment_mode: str
) -> None:
    """
    @brief      Confirm actual dependent losses and automatically save Home options.
    @param[in]  window Active main window shell.
    @param[in]  target_language Requested translation and voice language.
    @param[in]  voice_assignment_mode Requested narration mode.
    @return     None.
    @exception  None.
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    if getattr(window, "_active_operation_kind", None) is not None:
        _restore_project_option_selection(window)
        return
    language = ui_state_service.current_language_from_settings(window._settings_payload)
    try:
        # Settle the existing manual-save timer before its document can be reset.
        if window._ai_translation_page.flush_pending_translation_edit() is False:
            _restore_project_option_selection(window)
            return
        plan = project_options_service.plan_project_options_change(
            window._current_project_root, target_language, voice_assignment_mode
        )
        if not plan.changed or (
            plan.requires_confirmation and not confirm_project_options_change(window, plan, language)
        ):
            _restore_project_option_selection(window)
            return
        window.stop_all_audio_playback()
        manifest = project_options_service.apply_project_options_change(plan)
    except (OSError, ValueError) as error:
        _restore_project_option_selection(window)
        QMessageBox.warning(window, ui_state_service.translate("dialog.project_error_title", language), str(error))
        return
    window.show_project_state(window._current_project_root, manifest)
    misc_ui_controller.show_message(window, ui_state_service.translate("status.project_options_saved", language))


def build_project_options_confirmation_message(
    plan: project_options_service.ProjectOptionsChange, language: str
) -> str:
    """
    @brief      Explain the exact planned reset and its preservation boundary.
    @param[in]  plan Read-only option change shown to the operator.
    @param[in]  language Current interface language.
    @return     Localized plain-text confirmation body.
    @exception  None.
    """
    key = "project.options_change_language" if plan.language_changed else "project.options_change_mode"
    value = (
        ui_state_service.translate(f"language.{plan.target_language}", language)
        if plan.language_changed
        else ui_state_service.translate(f"home.mode_{plan.voice_assignment_mode}", language)
    )
    lines = [ui_state_service.translate(key, language).format(value=value)]
    if plan.affected_operations:
        lines += ["", ui_state_service.translate("project.options_reset_header", language)]
        lines += [
            ui_state_service.translate(f"project.options_reset.{kind}", language) for kind in plan.affected_operations
        ]
        if plan.artifact_paths:
            file_message = ui_state_service.translate("project.options_file_count", language)
            lines.append(file_message.format(count=len(plan.artifact_paths)))
        else:
            lines += [ui_state_service.translate("project.options_progress_only", language)]
    else:
        lines += ["", ui_state_service.translate("project.options_no_results", language)]
    preserve_key = "project.options_preserve_language" if plan.language_changed else "project.options_preserve_mode"
    lines += ["", ui_state_service.translate(preserve_key, language)]
    return "\n".join(lines)


def confirm_project_options_change(
    window: "MainWindow", plan: project_options_service.ProjectOptionsChange, language: str
) -> bool:
    """
    @brief      Present a cancellable change action with actual impact details.
    @param[in]  window Parent window.
    @param[in]  plan Exact change to confirm.
    @param[in]  language Current interface language.
    @return     True only for the explicitly labelled apply action.
    @exception  None.
    """
    dialog = QMessageBox(window)
    dialog.setIcon(QMessageBox.Icon.Warning if plan.affected_operations else QMessageBox.Icon.Question)
    dialog.setWindowTitle(ui_state_service.translate("dialog.confirm_project_options_change_title", language))
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    dialog.setText(build_project_options_confirmation_message(plan, language))
    if plan.artifact_paths:
        dialog.setDetailedText("\n".join(str(path.relative_to(plan.project_root)) for path in plan.artifact_paths))
        details_button = next(
            button for button in dialog.buttons() if dialog.buttonRole(button) == QMessageBox.ButtonRole.ActionRole
        )
        details_button.setText(ui_state_service.translate("project.options_show_details", language))

        def update_details_label() -> None:
            """@brief Apply the app locale after Qt toggles its built-in details panel."""
            expanded = not bool(details_button.property("details_expanded"))
            details_button.setProperty("details_expanded", expanded)
            key = "project.options_hide_details" if expanded else "project.options_show_details"
            details_button.setText(ui_state_service.translate(key, language))

        details_button.clicked.connect(update_details_label)
    action_key = "project.options_apply_reset" if plan.affected_operations else "project.options_apply"
    apply_button = dialog.addButton(ui_state_service.translate(action_key, language), QMessageBox.ButtonRole.AcceptRole)
    cancel_button = dialog.addButton(
        ui_state_service.translate("project.options_cancel", language), QMessageBox.ButtonRole.RejectRole
    )
    dialog.setDefaultButton(cancel_button)
    dialog.setEscapeButton(cancel_button)
    dialog.exec()
    return dialog.clickedButton() is apply_button


def _restore_project_option_selection(window: "MainWindow") -> None:
    """@brief Restore persisted selector values without emitting another change request."""
    manifest = window._current_manifest
    window._home_page.set_project_options(
        bool(manifest.get("project_options_locked", False)),
        str(manifest["target_language"]),
        str(manifest["voice_assignment_mode"]),
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
    if window._ai_translation_page.flush_pending_translation_edit() is False:
        return
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
    window._current_project_root = project_root
    window._current_manifest = manifest
    window.set_current_page("home")


def _confirm_cleanup_draft_discard(window: "MainWindow", language: str) -> bool:
    """
    @brief      Confirm discarding a modified Cleanup draft before project selection.
    @param[in]  window Active main window instance.
    @param[in]  language Current UI language code.
    @return     True when no draft is modified or the operator confirms its discard.
    @exception  None
    """
    if not window._text_cleanup_page.has_modified_cleaned_text_draft():
        return True
    return misc_ui_controller.confirm_question(
        window,
        language,
        "dialog.confirm_cleanup_draft_discard_title",
        "project.confirm_cleanup_draft_discard",
    )


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
