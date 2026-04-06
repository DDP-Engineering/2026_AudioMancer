#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file main_window.py
@brief Main window shell copied from DDP_Audiomancer for AudioMancer.
@details Implements the same toolbar, sidebar, stacked-page shell, status bar,
         and dialogs as the DDP_Audiomancer main window, while keeping the
         pages presentational only and free of workflow behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 1.8.0
"""

# IMPORTS

import zipfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import ai_backend_service
from audiomancer.services import import_service
from audiomancer.services import project_workspace_service
from audiomancer.services import settings_service
from audiomancer.services import text_extraction_service
from audiomancer.services import ui_state_service
from audiomancer.ui.navigation_sidebar import NavigationSidebar
from audiomancer.ui.pages.ai_translation_page import AiTranslationPage
from audiomancer.ui.pages.ai_settings_page import AiSettingsPage
from audiomancer.ui.pages.characters_page import CharactersPage
from audiomancer.ui.pages.home_page import HomeProjectPage
from audiomancer.ui.pages.narrator_page import NarratorPage
from audiomancer.ui.pages.placeholder_page import PlaceholderPage
from audiomancer.ui.pages.settings_page import SettingsPage
from audiomancer.ui.pages.text_chunking_page import TextChunkingPage
from audiomancer.ui.pages.text_cleanup_page import TextCleanupPage
from audiomancer.ui.status_bar import AudiomancerStatusBar

# CONSTANTS

WINDOW_TITLE = config.APP_NAME
WINDOW_WIDTH = config.DEFAULT_MAIN_WINDOW_WIDTH
WINDOW_HEIGHT = config.DEFAULT_MAIN_WINDOW_HEIGHT
WINDOW_MIN_WIDTH = config.DEFAULT_MAIN_WINDOW_MIN_WIDTH
WINDOW_MIN_HEIGHT = config.DEFAULT_MAIN_WINDOW_MIN_HEIGHT
TAGLINE_TEXT = "Transform written words into real audio experience!"
LICENSE_PATH = config.APP_ROOT / "LICENSE.txt"
LICENSE_NC_PATH = config.APP_ROOT / "LICENSE_NC.txt"
LICENSE_TRANSLATED_PATHS = {
    "ro": (
        config.APP_ROOT / "LICENSE_ro.txt",
        config.APP_ROOT / "LICENSE_NC_ro.txt",
    ),
}


# PUBLIC API


class MainWindow(QMainWindow):
    """
    @brief      Render the sidebar-driven AudioMancer desktop shell.
    @details    Mirrors the DDP_Audiomancer main-window structure with a top
                toolbar, navigation sidebar, stacked content pages, a status
                bar, and the first project new/open workflow.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.8.0
    """

    PAGE_ORDER = (
        ("home", "Home / Project"),
        ("text_cleanup", "Text Cleanup"),
        ("text_chunking", "Text Chunking"),
        ("ai_translation", "AI Translation"),
        ("characters", "Characters"),
        ("narrator", "Narrator"),
        ("narration_plan", "Narration Plan"),
        ("generation", "Generation"),
        ("export", "Export"),
    )

    def __init__(
        self,
        settings_payload: dict[str, object] | None = None,
        parent=None,
    ) -> None:
        """
        @brief      Initialize the copied main-window shell.
        @param[in]  settings_payload Optional preloaded application settings.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.9.0
        """
        super().__init__(parent)
        self.setWindowTitle(_build_window_title())
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self._page_registry: dict[str, QWidget] = {}
        self._current_manifest: dict[str, object] | None = None
        self._current_project_root: Path | None = None
        self._settings_payload = (
            dict(settings_payload)
            if isinstance(settings_payload, dict)
            else settings_service.load_settings()
        )

        self._toolbar = self._build_toolbar()
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._toolbar)
        self._sidebar = NavigationSidebar(self)
        self._stack = QStackedWidget(self)
        self._status_bar = AudiomancerStatusBar(self)
        self.setStatusBar(self._status_bar)

        self._build_pages()
        self._build_dialogs()

        central_widget = QWidget(self)
        central_layout = QHBoxLayout(central_widget)
        central_layout.addWidget(self._sidebar)
        central_layout.addWidget(self._stack, 1)
        self.setCentralWidget(central_widget)

        self._sidebar.page_selected.connect(self.set_current_page)
        self._sidebar.set_current_page("home")
        self.set_current_page("home")
        self._apply_current_ui_settings()
        self.set_project_active(False)
        self.show_project_state(None, None)

    def set_current_page(self, page_id: str) -> None:
        """
        @brief      Switch the shell to the requested placeholder page.
        @param[in]  page_id Registered page identifier.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.1
        """
        page = self._page_registry.get(page_id)
        if page is None:
            return
        self._stack.setCurrentWidget(page)
        self._sidebar.set_current_page(page_id)

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Enable or disable workflow pages based on project availability.
        @param[in]  is_active True when a project is open.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.3.0
        """
        for page_id, _label in self.PAGE_ORDER:
            enabled = is_active or page_id == "home"
            self._sidebar.set_page_enabled(page_id, enabled)
        if not is_active:
            self._sidebar.set_current_page("home")
            self.set_current_page("home")
        for widget in self._page_registry.values():
            if hasattr(widget, "set_project_active"):
                widget.set_project_active(is_active)

    def show_project_state(
        self,
        project_root: Path | None,
        manifest: dict[str, object] | None,
    ) -> None:
        """
        @brief      Refresh shell-level project labels and workflow status state.
        @param[in]  project_root Active project root or `None`.
        @param[in]  manifest Active project manifest or `None`.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.2.0
        """
        self._current_project_root = project_root
        self._current_manifest = manifest
        display_name = (
            None if manifest is None else str(manifest.get("display_name") or "")
        )
        stage_name = (
            None if manifest is None else str(manifest.get("current_stage") or "")
        )
        source_name = (
            None
            if manifest is None
            else _source_document_name(manifest)
        )
        self._home_page.set_project_state(
            display_name,
            None if project_root is None else str(project_root),
            stage_name,
        )
        self._home_page.set_source_summary(source_name)
        self._home_page.set_source_locked(source_name is not None, source_name)
        self._home_page.set_stage_statuses(self._build_stage_statuses(manifest))
        self._status_bar.set_stage(stage_name)
        self._text_cleanup_page.set_project_active(project_root is not None)
        self._text_cleanup_page.set_processing_state(
            **self._build_text_cleanup_state(project_root, manifest)
        )

    def show_settings_dialog(self) -> None:
        """
        @brief      Show the static settings dialog.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.1
        """
        self._settings_page.load_settings(self._settings_payload)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def show_ai_settings_dialog(self) -> None:
        """
        @brief      Show the static AI settings dialog.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.2.0
        """
        self._ai_settings_page.load_settings(self._settings_payload)
        self._ai_settings_dialog.show()
        self._ai_settings_dialog.raise_()
        self._ai_settings_dialog.activateWindow()

    def show_about_dialog(self) -> None:
        """
        @brief      Show the customized about dialog with license text.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.2.0
        """
        self._build_about_dialog().exec()

    def show_message(self, message: str, timeout_ms: int = 5000) -> None:
        """
        @brief      Show a transient status-bar message.
        @param[in]  message Operator-facing message text.
        @param[in]  timeout_ms Status-bar timeout in milliseconds.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.2.0
        """
        self.statusBar().showMessage(message, timeout_ms)

    # LOCAL HELPERS

    def _build_toolbar(self) -> QToolBar:
        """
        @brief      Build the source-matched main toolbar.
        @return     Configured Qt toolbar.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.2.1
        """
        toolbar = QToolBar("Main Toolbar", self)
        self._action_new_project = toolbar.addAction("New Project")
        self._action_open_project = toolbar.addAction("Open Project")
        toolbar.addSeparator()
        self._action_settings = toolbar.addAction("Settings")
        self._action_ai_settings = toolbar.addAction("AI Settings")
        toolbar.addSeparator()
        self._action_help = toolbar.addAction("Help")
        self._action_about = toolbar.addAction("About")
        self._action_settings.triggered.connect(self.show_settings_dialog)
        self._action_ai_settings.triggered.connect(self.show_ai_settings_dialog)
        self._action_new_project.triggered.connect(
            self._handle_new_project_requested
        )
        self._action_open_project.triggered.connect(
            self._handle_open_project_requested
        )
        self._action_help.triggered.connect(
            self._show_help_placeholder
        )
        self._action_about.triggered.connect(self.show_about_dialog)
        return toolbar

    def _build_pages(self) -> None:
        """
        @brief      Build and register the stacked shell pages.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.5.0
        """
        home_page = HomeProjectPage(self)
        self._home_page = home_page
        home_page.set_project_state(
            display_name=None,
            project_path=None,
            stage_name=None,
        )
        home_page.set_source_summary(None)
        home_page.set_source_locked(False, None)
        home_page.set_stage_statuses(self._build_stage_statuses(None))
        home_page.import_requested.connect(self._handle_import_source_requested)

        self._text_cleanup_page = TextCleanupPage(self)
        self._text_cleanup_page.extract_requested.connect(
            self._handle_extract_text_requested
        )

        pages = {
            "home": home_page,
            "text_cleanup": self._text_cleanup_page,
            "text_chunking": TextChunkingPage(self),
            "ai_translation": AiTranslationPage(self),
            "characters": CharactersPage(self),
            "narrator": NarratorPage(self),
            "narration_plan": PlaceholderPage(
                "Narration Plan",
                "Narration planning is not implemented yet.",
                self,
            ),
            "generation": PlaceholderPage(
                "Generation",
                "Generation is not implemented yet.",
                self,
            ),
            "export": PlaceholderPage(
                "Export",
                "Export is not implemented yet.",
                self,
            ),
        }

        for page_id, label in self.PAGE_ORDER:
            page = pages[page_id]
            self._page_registry[page_id] = page
            self._stack.addWidget(page)
            self._sidebar.add_page(page_id, label, enabled=page_id == "home")

    def _build_dialogs(self) -> None:
        """
        @brief      Build static placeholder dialogs for the copied shell.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.2.0
        """
        self._settings_dialog = QDialog(self)
        self._settings_dialog.setWindowTitle(
            ui_state_service.translate(
                "dialog.settings_title",
                str(self._settings_payload.get("language", config.DEFAULT_LANGUAGE)),
            )
        )
        self._settings_dialog.resize(680, 560)
        settings_layout = QVBoxLayout(self._settings_dialog)
        self._settings_page = SettingsPage(self._settings_dialog)
        self._settings_page._cancel_button.clicked.connect(
            self._settings_dialog.close
        )
        self._settings_page._save_button.clicked.connect(
            self._save_settings_from_dialog
        )
        self._settings_page.load_settings(self._settings_payload)
        settings_layout.addWidget(self._settings_page)

        self._ai_settings_dialog = QDialog(self)
        self._ai_settings_dialog.setWindowTitle(
            ui_state_service.translate(
                "dialog.ai_settings_title",
                str(self._settings_payload.get("language", config.DEFAULT_LANGUAGE)),
            )
        )
        self._ai_settings_dialog.resize(920, 640)
        ai_layout = QVBoxLayout(self._ai_settings_dialog)
        self._ai_settings_page = AiSettingsPage(self._ai_settings_dialog)
        self._ai_settings_page._connect_button.clicked.connect(
            self._connect_ai_profile_from_dialog
        )
        self._ai_settings_page._cancel_button.clicked.connect(
            self._ai_settings_dialog.close
        )
        self._ai_settings_page._save_button.clicked.connect(
            self._save_ai_settings_from_dialog
        )
        self._ai_settings_page.load_settings(self._settings_payload)
        ai_layout.addWidget(self._ai_settings_page)

    def _save_settings_from_dialog(self) -> None:
        """
        @brief      Persist settings-page changes through the settings service.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.2.0
        """
        merged_settings = self._settings_page.build_settings(self._settings_payload)
        settings_service.save_settings(merged_settings)
        self._settings_payload = settings_service.load_settings()
        self._apply_current_ui_settings()
        self._settings_dialog.close()
        self.show_message(
            ui_state_service.translate(
                "status.saved_settings",
                str(self._settings_payload.get("language", config.DEFAULT_LANGUAGE)),
            )
        )

    def _save_ai_settings_from_dialog(self) -> None:
        """
        @brief      Persist AI settings-page changes through the settings service.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.2.0
        """
        merged_settings = self._ai_settings_page.build_settings(
            self._settings_payload
        )
        settings_service.save_settings(merged_settings)
        self._settings_payload = settings_service.load_settings()
        self._apply_current_ui_settings()
        self._ai_settings_dialog.close()
        self.show_message(
            ui_state_service.translate(
                "status.saved_ai_settings",
                str(self._settings_payload.get("language", config.DEFAULT_LANGUAGE)),
            )
        )

    def _connect_ai_profile_from_dialog(self) -> None:
        """
        @brief      Probe the selected AI profile and show operator feedback.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.2.0
        """
        current_language = str(
            self._settings_payload.get("language", config.DEFAULT_LANGUAGE)
        )
        current_profile = self._ai_settings_page.build_current_profile_payload()
        if current_profile is None:
            return

        probe_result = ai_backend_service.probe_profile(current_profile)
        self._ai_settings_page.apply_probe_result(probe_result)

        if bool(probe_result.get("success", False)):
            QMessageBox.information(
                self._ai_settings_dialog,
                ui_state_service.translate(
                    "ai_settings.popup_success_title",
                    current_language,
                ),
                (
                    f"{ui_state_service.translate('ai_settings.popup_success_message', current_language)}\n"
                    f"{ui_state_service.translate('ai_settings.popup_discovered_models', current_language)}: "
                    f"{probe_result.get('discovered_model_count', 0)}"
                ),
            )
            return

        QMessageBox.warning(
            self._ai_settings_dialog,
            ui_state_service.translate(
                "ai_settings.popup_failure_title",
                current_language,
            ),
            (
                f"{ui_state_service.translate('ai_settings.popup_failure_message', current_language)}\n"
                f"{probe_result.get('message', '')}"
            ),
        )

    def _apply_current_ui_settings(self) -> None:
        """
        @brief      Apply persisted runtime UI settings to the current shell.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.2.0
        """
        ui_state_service.apply_ui_settings(
            QApplication.instance(),
            self,
            self._settings_payload,
        )

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language across the visible shell widgets.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.1
        """
        self.setWindowTitle(ui_state_service.translate("window_title.main", language))
        self._action_new_project.setText(
            ui_state_service.translate("toolbar.new_project", language)
        )
        self._action_open_project.setText(
            ui_state_service.translate("toolbar.open_project", language)
        )
        self._action_settings.setText(
            ui_state_service.translate("toolbar.settings", language)
        )
        self._action_ai_settings.setText(
            ui_state_service.translate("toolbar.ai_settings", language)
        )
        self._action_help.setText(
            ui_state_service.translate("toolbar.help", language)
        )
        self._action_about.setText(
            ui_state_service.translate("toolbar.about", language)
        )
        self._sidebar.apply_language(language)
        self._status_bar.apply_language(language)
        self._settings_dialog.setWindowTitle(
            ui_state_service.translate("dialog.settings_title", language)
        )
        self._ai_settings_dialog.setWindowTitle(
            ui_state_service.translate("dialog.ai_settings_title", language)
        )
        for widget in (
            self._settings_page,
            self._ai_settings_page,
            *self._page_registry.values(),
        ):
            if hasattr(widget, "apply_language"):
                widget.apply_language(language)

    def _show_help_placeholder(self) -> None:
        """
        @brief      Show the translated shell help placeholder message.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        self.show_message(
            ui_state_service.translate(
                "help.placeholder",
                str(self._settings_payload.get("language", config.DEFAULT_LANGUAGE)),
            )
        )

    def _handle_new_project_requested(self) -> None:
        """
        @brief      Collect inputs and create a new project workspace.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        current_language = str(
            self._settings_payload.get("language", config.DEFAULT_LANGUAGE)
        )
        selected_parent = QFileDialog.getExistingDirectory(
            self,
            ui_state_service.translate(
                "dialog.select_project_parent_title",
                current_language,
            ),
            str(self._current_project_root.parent)
            if self._current_project_root is not None
            else str(config.APP_ROOT),
        )
        if not selected_parent:
            return

        project_name, accepted = QInputDialog.getText(
            self,
            ui_state_service.translate("dialog.new_project_title", current_language),
            ui_state_service.translate("project.project_name", current_language),
        )
        if not accepted:
            return

        project_name = project_name.strip()
        if not project_name:
            QMessageBox.warning(
                self,
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
                self,
                ui_state_service.translate("dialog.project_error_title", current_language),
                str(error),
            )
            return

        self._activate_project(project_root, manifest)
        self.show_message(
            ui_state_service.translate(
                "status.project_created",
                current_language,
            )
        )

    def _handle_open_project_requested(self) -> None:
        """
        @brief      Let the operator select and open one existing project folder.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        current_language = str(
            self._settings_payload.get("language", config.DEFAULT_LANGUAGE)
        )
        selected_folder = QFileDialog.getExistingDirectory(
            self,
            ui_state_service.translate("dialog.open_project_title", current_language),
            str(self._current_project_root or config.APP_ROOT),
        )
        if not selected_folder:
            return

        try:
            open_result = project_workspace_service.open_project(selected_folder)
        except (FileNotFoundError, ValueError) as error:
            QMessageBox.warning(
                self,
                ui_state_service.translate("dialog.project_error_title", current_language),
                str(error),
            )
            return

        if str(open_result.get("status")) == "repair_required":
            if not self._confirm_project_repair(open_result, current_language):
                return
            repaired_result = project_workspace_service.repair_project(open_result)
            project_root = Path(str(repaired_result["project_root"]))
            manifest = dict(repaired_result["manifest"])
            self._activate_project(project_root, manifest)
            self.show_message(
                ui_state_service.translate(
                    "status.project_repaired",
                    current_language,
                )
            )
            return

        project_root = Path(str(open_result["project_root"]))
        manifest = dict(open_result["manifest"])

        self._activate_project(project_root, manifest)
        self.show_message(
            ui_state_service.translate(
                "status.project_opened",
                current_language,
            )
        )

    def _handle_import_source_requested(self) -> None:
        """
        @brief      Let the operator select and import one source file.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        current_language = str(
            self._settings_payload.get("language", config.DEFAULT_LANGUAGE)
        )
        if self._current_project_root is None or self._current_manifest is None:
            QMessageBox.warning(
                self,
                ui_state_service.translate("dialog.project_error_title", current_language),
                ui_state_service.translate("project.error_no_active_project", current_language),
            )
            return

        if _source_document_name(self._current_manifest) is not None:
            QMessageBox.warning(
                self,
                ui_state_service.translate("dialog.project_error_title", current_language),
                ui_state_service.translate("project.error_locked_source", current_language),
            )
            return

        selected_file, _selected_filter = QFileDialog.getOpenFileName(
            self,
            ui_state_service.translate("dialog.select_source_title", current_language),
            str(self._current_project_root),
            ui_state_service.translate("dialog.select_source_filter", current_language),
        )
        if not selected_file:
            return

        try:
            source_document = import_service.import_source(
                self._current_project_root,
                selected_file,
            )
        except (FileNotFoundError, ValueError) as error:
            QMessageBox.warning(
                self,
                ui_state_service.translate("dialog.project_error_title", current_language),
                str(error),
            )
            return

        updated_manifest = dict(self._current_manifest)
        updated_manifest["source_document"] = source_document
        updated_manifest["current_stage"] = "source_selected"
        project_workspace_service.save_manifest(updated_manifest, self._current_project_root)
        reloaded_manifest = project_workspace_service.load_manifest(self._current_project_root)
        self.show_project_state(self._current_project_root, reloaded_manifest)
        self.show_message(
            ui_state_service.translate("status.source_imported", current_language)
        )

    def _handle_extract_text_requested(self) -> None:
        """
        @brief      Run deterministic source-text extraction for the active project.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        current_language = str(
            self._settings_payload.get("language", config.DEFAULT_LANGUAGE)
        )
        if self._current_project_root is None or self._current_manifest is None:
            QMessageBox.warning(
                self,
                ui_state_service.translate("dialog.project_error_title", current_language),
                ui_state_service.translate("project.error_no_active_project", current_language),
            )
            return
        if _source_document_name(self._current_manifest) is None:
            QMessageBox.warning(
                self,
                ui_state_service.translate("dialog.project_error_title", current_language),
                ui_state_service.translate("project.error_missing_source", current_language),
            )
            return

        extraction_operation = _manifest_operation(self._current_manifest, "extraction")
        if str(extraction_operation.get("status", "not_started")) == "completed":
            if not self._confirm_extraction_rerun(current_language):
                return
            text_extraction_service.reset_extraction_and_downstream(
                self._current_project_root
            )
            reset_manifest = _build_manifest_after_extraction_reset(self._current_manifest)
            project_workspace_service.save_manifest(
                reset_manifest,
                self._current_project_root,
            )
            self._current_manifest = project_workspace_service.load_manifest(
                self._current_project_root
            )

        self._text_cleanup_page.set_busy(True)
        try:
            report_payload = text_extraction_service.extract_text(
                self._current_project_root,
                self._current_manifest,
            )
        except (FileNotFoundError, ValueError, zipfile.BadZipFile) as error:
            failed_manifest = _update_manifest_after_failed_extraction(
                self._current_manifest,
                self._current_project_root,
            )
            project_workspace_service.save_manifest(
                failed_manifest,
                self._current_project_root,
            )
            self.show_project_state(
                self._current_project_root,
                project_workspace_service.load_manifest(self._current_project_root),
            )
            QMessageBox.warning(
                self,
                ui_state_service.translate("dialog.project_error_title", current_language),
                str(error),
            )
            return
        finally:
            self._text_cleanup_page.set_busy(False)

        updated_manifest = dict(self._current_manifest)
        updated_manifest["extracted_text_relative_path"] = str(
            report_payload["extracted_text_relative_path"]
        )
        updated_manifest["extraction_report_relative_path"] = (
            f"{config.EXTRACTION_FOLDER_NAME}/{config.EXTRACTION_REPORT_FILE_NAME}"
        )
        updated_manifest["extraction_warning_count"] = len(
            list(report_payload.get("warnings", []))
        )
        operations = _normalized_manifest_operations(updated_manifest)
        operations["extraction"] = (
            text_extraction_service.load_operation_state(self._current_project_root)
            or operations["extraction"]
        )
        updated_manifest["operations"] = operations
        project_workspace_service.save_manifest(
            updated_manifest,
            self._current_project_root,
        )
        self.show_project_state(
            self._current_project_root,
            project_workspace_service.load_manifest(self._current_project_root),
        )
        self.show_message(
            ui_state_service.translate("status.text_extracted", current_language)
        )

    def _confirm_project_repair(
        self,
        repair_result: dict[str, object],
        language: str,
    ) -> bool:
        """
        @brief      Ask the operator whether one recoverable project should be repaired.
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
            self,
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

    def _confirm_extraction_rerun(self, language: str) -> bool:
        """
        @brief      Ask the operator whether one completed extraction should be rerun destructively.
        @param[in]  language Current UI language code.
        @return     True when the operator accepts the rerun reset.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        decision = QMessageBox.question(
            self,
            ui_state_service.translate("dialog.confirm_extraction_rerun_title", language),
            ui_state_service.translate("project.confirm_extraction_rerun", language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return decision == QMessageBox.StandardButton.Yes

    def _activate_project(
        self,
        project_root: Path,
        manifest: dict[str, object],
    ) -> None:
        """
        @brief      Apply one active project into the current shell state.
        @param[in]  project_root Resolved active project root.
        @param[in]  manifest Loaded active project manifest.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        self.set_project_active(True)
        self.show_project_state(project_root, manifest)

    def _build_stage_statuses(
        self,
        manifest: dict[str, object] | None,
    ) -> list[dict[str, str]]:
        """
        @brief      Build the home-page workflow progress list for one manifest.
        @param[in]  manifest Active project manifest or `None`.
        @return     Ordered stage-status entries for the home page.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.2.0
        """
        current_language = str(
            self._settings_payload.get("language", config.DEFAULT_LANGUAGE)
        )
        stage_tokens = _visible_workflow_stage_tokens()
        if manifest is None:
            return [
                {
                    "label": ui_state_service.translate(
                        f"home.stage_label.{token}",
                        current_language,
                    ),
                    "status": "not_started",
                    "note": ui_state_service.translate(
                        f"home.stage_note.inactive.{token}",
                        current_language,
                    ),
                }
                for token in stage_tokens
            ]

        reached_index = _stage_reached_index(
            str(manifest.get("current_stage", config.DEFAULT_WORKFLOW_STAGE))
        )
        statuses: list[dict[str, str]] = []
        for index, token in enumerate(stage_tokens):
            statuses.append({
                "label": ui_state_service.translate(
                    f"home.stage_label.{token}",
                    current_language,
                ),
                "status": "finished" if reached_index >= index else "not_started",
                "note": ui_state_service.translate(
                    f"home.stage_note.active.{token}",
                    current_language,
                ),
            })
        extraction_status = str(
            _manifest_operation(manifest, "extraction").get("status", "not_started")
        )
        if (
            _source_document_name(manifest) is not None
            and extraction_status in {"running", "failed", "completed"}
            and reached_index < 1
        ):
            statuses[0]["status"] = "finished"
            statuses[1]["status"] = "in_progress"
        return statuses

    def _build_text_cleanup_state(
        self,
        project_root: Path | None,
        manifest: dict[str, object] | None,
    ) -> dict[str, object]:
        """
        @brief      Build the operator-facing state payload for the text cleanup page.
        @param[in]  project_root Active project root or `None`.
        @param[in]  manifest Active project manifest or `None`.
        @return     Keyword payload for `TextCleanupPage.set_processing_state`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        current_language = str(
            self._settings_payload.get("language", config.DEFAULT_LANGUAGE)
        )
        if project_root is None or manifest is None:
            return {
                "extracted_text": None,
                "cleaned_text": None,
                "notes": [
                    ui_state_service.translate("text_cleanup.note_no_project", current_language)
                ],
                "can_extract": False,
            }

        extracted_text = _read_optional_project_text(
            project_root,
            _optional_manifest_string(manifest.get("extracted_text_relative_path")),
        )
        report_payload = text_extraction_service.load_extraction_report(project_root)
        operation_state = text_extraction_service.load_operation_state(project_root)
        return {
            "extracted_text": extracted_text,
            "cleaned_text": None,
            "notes": _build_text_cleanup_notes(
                manifest,
                report_payload,
                operation_state,
                current_language,
            ),
            "can_extract": _source_document_name(manifest) is not None,
        }

    def _build_about_dialog(self) -> QDialog:
        """
        @brief      Build the About dialog for the AudioMancer shell.
        @return     Configured Qt dialog instance.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        dialog = QDialog(self)
        current_language = str(
            self._settings_payload.get("language", config.DEFAULT_LANGUAGE)
        )
        dialog.setWindowTitle(
            ui_state_service.translate("dialog.about_title", current_language)
        )
        dialog.resize(510, 620)

        layout = QVBoxLayout(dialog)

        title_label = QLabel(
            "<div style='text-align:center;'>"
            "<span style='font-size:18pt; font-weight:700;'>AudioMancer</span>"
            "<span style='font-size:11pt; vertical-align:super;'> @2026</span>"
            "</div>"
        )
        title_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(title_label)

        subtitle = QLabel(
            ui_state_service.translate("about.subtitle", current_language)
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        details = QLabel(ui_state_service.translate("about.details", current_language))
        details.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(details)
        layout.addSpacing(12)

        license_label = QLabel(
            ui_state_service.translate("about.license", current_language)
        )
        layout.addWidget(license_label)

        license_text_box = QPlainTextEdit(dialog)
        license_text_box.setObjectName("aboutLicenseTextBox")
        license_text_box.setReadOnly(True)
        license_text_box.setPlainText(
            self._load_about_license_text(current_language)
        )
        layout.addWidget(license_text_box, 1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, dialog)
        button_box.accepted.connect(dialog.accept)
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(button_box)
        button_layout.addStretch(1)
        layout.addLayout(button_layout)
        return dialog

    def _load_about_license_text(self, language: str) -> str:
        """
        @brief      Load the main and addendum license text for the About dialog.
        @param[in]  language Target UI language code.
        @return     Combined operator-facing license text.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.2.0
        """
        main_license_path, addendum_path = _resolve_license_paths(language)
        return (
            _read_text_file(main_license_path)
            + "\n\n"
            + "=" * 78
            + "\n\n"
            + _read_text_file(addendum_path)
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """
        @brief      Handle window close for the static shell.
        @param[in]  event Qt close event.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        super().closeEvent(event)


def _read_text_file(path: Path) -> str:
    """
    @brief      Read a UTF-8 text file for UI display.
    @param[in]  path Absolute file path to read.
    @return     Decoded text or a fallback message when unavailable.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    if not path.exists():
        return f"File not found: {path}"
    return path.read_text(encoding="utf-8").strip()


def _resolve_license_paths(language: str) -> tuple[Path, Path]:
    """
    @brief      Resolve the localized license-file pair for one UI language.
    @param[in]  language Target UI language code.
    @return     Tuple of main-license path and addendum-license path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    localized_pair = LICENSE_TRANSLATED_PATHS.get(language)
    if localized_pair is None:
        return LICENSE_PATH, LICENSE_NC_PATH
    main_license_path, addendum_path = localized_pair
    if main_license_path.exists() and addendum_path.exists():
        return main_license_path, addendum_path
    return LICENSE_PATH, LICENSE_NC_PATH


def _build_window_title(context: str | None = None) -> str:
    """
    @brief      Build the shared title-bar text for AudioMancer windows.
    @param[in]  context Optional trailing window-specific context.
    @return     Formatted title-bar text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    title = f"{WINDOW_TITLE} | {TAGLINE_TEXT}"
    if context:
        return f"{title} | {context}"
    return title


def _stage_reached_index(current_stage: str | None) -> int:
    """
    @brief      Resolve one workflow-stage token into the home progress index.
    @param[in]  current_stage Current manifest stage token.
    @return     Zero-based reached stage index.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    stage_sequence = config.PROJECT_WORKFLOW_STAGES
    if current_stage not in stage_sequence:
        return -1
    return stage_sequence.index(current_stage) - 1


def _visible_workflow_stage_tokens() -> tuple[str, ...]:
    """
    @brief      Return the visible workflow stages derived from shared config.
    @return     Ordered stage tokens shown in the home workflow progress list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    return tuple(
        stage_token
        for stage_token in config.PROJECT_WORKFLOW_STAGES
        if stage_token != config.DEFAULT_WORKFLOW_STAGE
    )


def _optional_manifest_string(value: object) -> str | None:
    """
    @brief      Normalize one optional manifest string used by the UI shell.
    @param[in]  value Raw manifest field value.
    @return     Normalized string or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if value in (None, ""):
        return None
    return str(value)


def _source_document_name(manifest: dict[str, object] | None) -> str | None:
    """
    @brief      Extract the display name of one persisted source document.
    @param[in]  manifest Active manifest payload or `None`.
    @return     Imported source display name or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not isinstance(manifest, dict):
        return None
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        return None
    return _optional_manifest_string(source_document.get("original_name"))


def _manifest_operation(
    manifest: dict[str, object] | None,
    operation_kind: str,
) -> dict[str, object]:
    """
    @brief      Return one normalized operation payload from the manifest.
    @param[in]  manifest Active manifest payload or `None`.
    @param[in]  operation_kind Operation-kind token to resolve.
    @return     Operation payload or an empty default mapping.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not isinstance(manifest, dict):
        return {}
    operations = manifest.get("operations")
    if not isinstance(operations, dict):
        return {}
    operation_payload = operations.get(operation_kind)
    return dict(operation_payload) if isinstance(operation_payload, dict) else {}


def _normalized_manifest_operations(
    manifest: dict[str, object],
) -> dict[str, dict[str, object]]:
    """
    @brief      Ensure the manifest exposes every required operation entry.
    @param[in]  manifest Active manifest payload.
    @return     Normalized operations mapping.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    operations = manifest.get("operations")
    if not isinstance(operations, dict):
        operations = {}
    normalized: dict[str, dict[str, object]] = {}
    for operation_kind, folder_name in (
        ("extraction", config.EXTRACTION_FOLDER_NAME),
        ("cleanup", "10_cleanup"),
        ("chunking", "20_chunking"),
        ("translation", "30_translation"),
        ("character_discovery", "40_character_discovery"),
    ):
        candidate = operations.get(operation_kind)
        if isinstance(candidate, dict):
            normalized[operation_kind] = dict(candidate)
            normalized[operation_kind].setdefault("folder_relative_path", folder_name)
            normalized[operation_kind].setdefault("status", "not_started")
        else:
            normalized[operation_kind] = {
                "folder_relative_path": folder_name,
                "status": "not_started",
                "input_paths": [],
                "output_paths": [],
                "artifact_paths": [],
                "progress_current": 0,
                "progress_total": 0,
                "mode": None,
                "started_at": None,
                "completed_at": None,
                "updated_at": None,
                "warning_count": 0,
                "metadata": {},
                "resume_checkpoint": None,
            }
    return normalized


def _build_manifest_after_extraction_reset(
    manifest: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Build one manifest payload after a confirmed extraction rerun reset.
    @param[in]  manifest Current manifest payload before reset.
    @return     Reset manifest payload ready for persistence.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    updated_manifest = dict(manifest)
    updated_manifest["extracted_text_relative_path"] = None
    updated_manifest["extraction_report_relative_path"] = None
    updated_manifest["extraction_warning_count"] = 0
    operations = _normalized_manifest_operations(updated_manifest)
    for operation_kind in operations:
        operations[operation_kind] = _normalized_manifest_operations({})[operation_kind]
    updated_manifest["operations"] = operations
    return updated_manifest


def _update_manifest_after_failed_extraction(
    manifest: dict[str, object],
    project_root: Path,
) -> dict[str, object]:
    """
    @brief      Build one manifest payload after extraction fails or remains unfinished.
    @param[in]  manifest Current manifest payload.
    @param[in]  project_root Active project root folder.
    @return     Updated manifest payload with failed extraction-state data.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    updated_manifest = dict(manifest)
    operations = _normalized_manifest_operations(updated_manifest)
    operations["extraction"] = (
        text_extraction_service.load_operation_state(project_root)
        or operations["extraction"]
    )
    updated_manifest["operations"] = operations
    return updated_manifest


def _read_optional_project_text(project_root: Path, relative_path: str | None) -> str | None:
    """
    @brief      Read one optional project-local text artifact.
    @param[in]  project_root Active project root folder.
    @param[in]  relative_path Optional project-relative text artifact path.
    @return     Decoded text content or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not relative_path:
        return None
    artifact_path = project_root / relative_path
    if not artifact_path.is_file():
        return None
    return artifact_path.read_text(encoding="utf-8")


def _build_text_cleanup_notes(
    manifest: dict[str, object],
    report_payload: dict[str, object] | None,
    operation_state: dict[str, object] | None,
    language: str,
) -> list[str]:
    """
    @brief      Build operator-facing notes for the extraction slice of the cleanup page.
    @param[in]  manifest Active project manifest payload.
    @param[in]  report_payload Optional extraction report payload.
    @param[in]  operation_state Optional extraction operation-state payload.
    @param[in]  language Current UI language code.
    @return     Ordered notes list for the cleanup page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    notes: list[str] = []
    if _source_document_name(manifest) is None:
        notes.append(ui_state_service.translate("text_cleanup.note_no_source", language))
        return notes

    operation_status = None if not isinstance(operation_state, dict) else str(operation_state.get("status", "not_started"))
    if report_payload is not None:
        page_text = report_payload.get("page_count")
        page_summary = "n/a" if page_text in (None, "") else str(page_text)
        notes.append(
            ui_state_service.translate("text_cleanup.note_report_summary", language).format(
                word_count=report_payload.get("word_count", 0),
                line_count=report_payload.get("line_count", 0),
                page_count=page_summary,
            )
        )
        warnings = list(report_payload.get("warnings", []))
        notes.extend(str(item) for item in warnings)
        if operation_status == "completed":
            notes.append(ui_state_service.translate("text_cleanup.note_rerun_warning", language))
        return notes

    if operation_status in {"running", "failed"}:
        progress_current = 0 if not isinstance(operation_state, dict) else int(operation_state.get("progress_current", 0))
        progress_total = 0 if not isinstance(operation_state, dict) else int(operation_state.get("progress_total", 0))
        notes.append(
            ui_state_service.translate("text_cleanup.note_resume", language).format(
                progress_current=progress_current,
                progress_total=progress_total,
            )
        )
        return notes

    notes.append(ui_state_service.translate("text_cleanup.note_ready", language))
    return notes


# END OF FILE
