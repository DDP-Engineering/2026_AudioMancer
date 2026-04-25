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
@version 0.3.0
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
    project_workspace_service,
    ui_state_service,
)
from audiomancer.ui.controllers import misc_ui_controller

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
    @version    0.1.1
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
    @version    0.1.1
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
    @version    0.1.1
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_no_active_project", current_language),
        )
        return

    if home_presenter_service.source_document_name(window._current_manifest) is not None:
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
        source_document = import_service.import_source(
            window._current_project_root,
            selected_file,
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
    @version    0.1.0
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
        export_content = project_export_service.render_export(
            window._current_project_root,
            window._current_manifest,
            export_kind,
            export_format,
        )
        export_path.parent.mkdir(parents=True, exist_ok=True)
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
    @version    0.1.0
    """
    if bool(repair_result.get("metadata_only", False)):
        repair_detail = ui_state_service.translate(
            "project.repair_metadata_only",
            language,
        )
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
    @version    0.1.0
    """
    window.set_project_active(True)
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
    @version    0.1.0
    """
    if export_format == project_export_service.EXPORT_FORMAT_MARKDOWN:
        return ui_state_service.translate("dialog.export_filter_markdown", language)
    return ui_state_service.translate("dialog.export_filter_txt", language)


# END OF FILE
