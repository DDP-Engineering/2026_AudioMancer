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
@details Implements the sidebar-driven Qt shell while delegating page/window
         behavior to dedicated UI controllers and page-specific state services
         so the window remains a thin coordinator.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 1.13.0
"""

# IMPORTS

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import home_presenter_service
from audiomancer.services import settings_service
from audiomancer.services import text_cleanup_state_service
from audiomancer.services import ui_state_service
from audiomancer.ui.controllers import ai_settings_ui_controller
from audiomancer.ui.controllers import home_ui_controller
from audiomancer.ui.controllers import misc_ui_controller
from audiomancer.ui.controllers import settings_ui_controller
from audiomancer.ui.controllers import text_cleanup_ui_controller
from audiomancer.ui.navigation_sidebar import NavigationSidebar
from audiomancer.ui.operation_progress_dialog import OperationProgressDialog
from audiomancer.ui.pages.ai_settings_page import AiSettingsPage
from audiomancer.ui.pages.ai_translation_page import AiTranslationPage
from audiomancer.ui.pages.characters_page import CharactersPage
from audiomancer.ui.pages.home_page import HomeProjectPage
from audiomancer.ui.pages.narrator_page import NarratorPage
from audiomancer.ui.pages.placeholder_page import PlaceholderPage
from audiomancer.ui.pages.settings_page import SettingsPage
from audiomancer.ui.pages.text_chunking_page import TextChunkingPage
from audiomancer.ui.pages.text_cleanup_page import TextCleanupPage
from audiomancer.ui.status_bar import AudiomancerStatusBar


# CONSTANTS

WINDOW_WIDTH = config.DEFAULT_MAIN_WINDOW_WIDTH
WINDOW_HEIGHT = config.DEFAULT_MAIN_WINDOW_HEIGHT
WINDOW_MIN_WIDTH = config.DEFAULT_MAIN_WINDOW_MIN_WIDTH
WINDOW_MIN_HEIGHT = config.DEFAULT_MAIN_WINDOW_MIN_HEIGHT


# PUBLIC API


class MainWindow(QMainWindow):
    """
    @brief      Render the sidebar-driven AudioMancer desktop shell.
    @details    Owns the visible Qt shell and delegates page/window behavior to
                dedicated UI controllers plus page-specific state services.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.12.0
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
        @version    0.13.0
        """
        super().__init__(parent)
        self.setWindowTitle(misc_ui_controller.build_window_title())
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self._page_registry: dict[str, QWidget] = {}
        self._current_manifest: dict[str, object] | None = None
        self._current_project_root: Path | None = None
        self._operation_progress_dialog: OperationProgressDialog | None = None
        self._active_operation_kind: str | None = None
        self._active_operation_name: str | None = None
        self._operation_cancel_requested = False
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
        @version    0.4.0
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
        @version    0.4.0
        """
        self._current_project_root = project_root
        self._current_manifest = manifest
        current_language = ui_state_service.current_language_from_settings(
            self._settings_payload
        )
        display_name = (
            None if manifest is None else str(manifest.get("display_name") or "")
        )
        stage_name = (
            None if manifest is None else str(manifest.get("current_stage") or "")
        )
        source_name = home_presenter_service.source_document_name(manifest)
        self._home_page.set_project_state(
            display_name,
            None if project_root is None else str(project_root),
            stage_name,
        )
        self._home_page.set_source_summary(source_name)
        self._home_page.set_source_locked(source_name is not None, source_name)
        self._home_page.set_stage_statuses(
            home_presenter_service.build_stage_statuses(
                manifest,
                current_language,
            )
        )
        self._status_bar.set_stage(stage_name)
        self._text_cleanup_page.set_project_active(project_root is not None)
        self._text_cleanup_page.set_ai_profiles(
            **text_cleanup_state_service.build_ai_cleanup_profile_state(
                self._settings_payload
            )
        )
        self._text_cleanup_page.set_processing_state(
            **text_cleanup_state_service.build_text_cleanup_state(
                project_root,
                manifest,
                current_language,
            )
        )

    def show_settings_dialog(self) -> None:
        """
        @brief      Show the static settings dialog.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.3.0
        """
        settings_ui_controller.show_settings_dialog(self)

    def show_ai_settings_dialog(self) -> None:
        """
        @brief      Show the static AI settings dialog.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.3.0
        """
        ai_settings_ui_controller.show_ai_settings_dialog(self)

    def show_about_dialog(self) -> None:
        """
        @brief      Build and show the About dialog.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.3.0
        """
        misc_ui_controller.show_about_dialog(self)

    def show_message(self, message: str, timeout_ms: int = 5000) -> None:
        """
        @brief      Show a transient status-bar message.
        @param[in]  message Operator-facing message text.
        @param[in]  timeout_ms Status-bar timeout in milliseconds.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.4.0
        """
        misc_ui_controller.show_message(self, message, timeout_ms)

    # LOCAL HELPERS

    def _build_toolbar(self) -> QToolBar:
        """
        @brief      Build the source-matched main toolbar.
        @return     Configured Qt toolbar.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.3.0
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
        self._action_settings.triggered.connect(
            lambda _checked=False: settings_ui_controller.show_settings_dialog(self)
        )
        self._action_ai_settings.triggered.connect(
            lambda _checked=False: ai_settings_ui_controller.show_ai_settings_dialog(self)
        )
        self._action_new_project.triggered.connect(
            lambda _checked=False: home_ui_controller.handle_new_project_requested(self)
        )
        self._action_open_project.triggered.connect(
            lambda _checked=False: home_ui_controller.handle_open_project_requested(self)
        )
        self._action_help.triggered.connect(
            lambda _checked=False: misc_ui_controller.show_help_placeholder(self)
        )
        self._action_about.triggered.connect(
            lambda _checked=False: misc_ui_controller.show_about_dialog(self)
        )
        return toolbar

    def _build_pages(self) -> None:
        """
        @brief      Build and register the stacked shell pages.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.8.1
        """
        current_language = ui_state_service.current_language_from_settings(
            self._settings_payload
        )
        home_page = HomeProjectPage(self)
        self._home_page = home_page
        home_page.set_project_state(
            display_name=None,
            project_path=None,
            stage_name=None,
        )
        home_page.set_source_summary(None)
        home_page.set_source_locked(False, None)
        home_page.set_stage_statuses(
            home_presenter_service.build_stage_statuses(None, current_language)
        )
        home_page.import_requested.connect(
            lambda: home_ui_controller.handle_import_source_requested(self)
        )

        self._text_cleanup_page = TextCleanupPage(self)
        self._text_cleanup_page.extract_requested.connect(
            lambda: text_cleanup_ui_controller.handle_extract_text_requested(self)
        )
        self._text_cleanup_page.clean_requested.connect(
            lambda: text_cleanup_ui_controller.handle_deterministic_cleanup_requested(self)
        )
        self._text_cleanup_page.ai_clean_requested.connect(
            lambda profile_id: text_cleanup_ui_controller.handle_ai_cleanup_requested(
                self,
                profile_id,
            )
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
        @brief      Build static shell dialogs for the copied window.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.5.0
        """
        current_language = ui_state_service.current_language_from_settings(
            self._settings_payload
        )

        self._settings_dialog = QDialog(self)
        self._settings_dialog.setWindowTitle(
            ui_state_service.translate("dialog.settings_title", current_language)
        )
        self._settings_dialog.resize(680, 560)
        settings_layout = QVBoxLayout(self._settings_dialog)
        self._settings_page = SettingsPage(self._settings_dialog)
        self._settings_page._cancel_button.clicked.connect(self._settings_dialog.close)
        self._settings_page._save_button.clicked.connect(
            lambda _checked=False: settings_ui_controller.save_settings_from_dialog(self)
        )
        self._settings_page.load_settings(self._settings_payload)
        settings_layout.addWidget(self._settings_page)

        self._ai_settings_dialog = QDialog(self)
        self._ai_settings_dialog.setWindowTitle(
            ui_state_service.translate("dialog.ai_settings_title", current_language)
        )
        self._ai_settings_dialog.resize(920, 640)
        ai_layout = QVBoxLayout(self._ai_settings_dialog)
        self._ai_settings_page = AiSettingsPage(self._ai_settings_dialog)
        self._ai_settings_page._connect_button.clicked.connect(
            lambda _checked=False: ai_settings_ui_controller.connect_ai_profile_from_dialog(self)
        )
        self._ai_settings_page._cancel_button.clicked.connect(
            self._ai_settings_dialog.close
        )
        self._ai_settings_page._save_button.clicked.connect(
            lambda _checked=False: ai_settings_ui_controller.save_ai_settings_from_dialog(self)
        )
        self._ai_settings_page.load_settings(self._settings_payload)
        ai_layout.addWidget(self._ai_settings_page)

    def _apply_current_ui_settings(self) -> None:
        """
        @brief      Apply persisted runtime UI settings to the current shell.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.4.0
        """
        settings_ui_controller.apply_current_ui_settings(self)

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language across the visible shell widgets.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.3.0
        """
        settings_ui_controller.apply_language(self, language)

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
        @version    0.3.0
        """
        home_ui_controller.activate_project(self, project_root, manifest)

    def _build_about_dialog(self) -> QDialog:
        """
        @brief      Build the About dialog for the AudioMancer shell.
        @return     Configured Qt dialog instance.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.3.0
        """
        return misc_ui_controller.build_about_dialog(self)

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


# END OF FILE
