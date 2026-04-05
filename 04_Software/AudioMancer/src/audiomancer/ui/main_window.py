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
@date 2026-04-05
@version 0.3.5
"""

# IMPORTS

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.ui.navigation_sidebar import NavigationSidebar
from audiomancer.ui.pages.home_page import HomeProjectPage
from audiomancer.ui.pages.narrator_page import NarratorPage
from audiomancer.ui.pages.placeholder_page import PlaceholderPage
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


# PUBLIC API


class MainWindow(QMainWindow):
    """
    @brief      Render the sidebar-driven AudioMancer desktop shell.
    @details    Mirrors the DDP_Audiomancer main-window structure with a top
                toolbar, navigation sidebar, stacked content pages, and a
                status bar, but intentionally leaves all actions unbound.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.3.5
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

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the copied main-window shell.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.3.5
        """
        super().__init__(parent)
        self.setWindowTitle(_build_window_title())
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self._page_registry: dict[str, QWidget] = {}

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

    def set_current_page(self, page_id: str) -> None:
        """
        @brief      Switch the shell to the requested placeholder page.
        @param[in]  page_id Registered page identifier.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.1
        """
        page = self._page_registry.get(page_id)
        if page is None:
            return
        self._stack.setCurrentWidget(page)
        self._sidebar.set_current_page(page_id)

    def show_settings_dialog(self) -> None:
        """
        @brief      Show the static settings dialog.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.1
        """
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
        @version    0.1.0
        """
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
        @version    0.1.0
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
        @version    0.1.0
        """
        self.statusBar().showMessage(message, timeout_ms)

    # LOCAL HELPERS

    def _build_toolbar(self) -> QToolBar:
        """
        @brief      Build the source-matched main toolbar.
        @return     Configured Qt toolbar.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
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
        self._action_help.triggered.connect(
            lambda: self.show_message(
                "Help placeholder. This shell mirrors DDP_Audiomancer only.",
            )
        )
        self._action_about.triggered.connect(self.show_about_dialog)
        return toolbar

    def _build_pages(self) -> None:
        """
        @brief      Build and register the stacked shell pages.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        home_page = HomeProjectPage(self)
        home_page.set_project_state(
            display_name=None,
            project_path=None,
            stage_name=None,
        )
        home_page.set_source_summary(None)
        home_page.set_source_locked(False, None)
        home_page.set_stage_statuses([
            {"label": "Source Selected", "status": "not_started",
             "note": "Create or open a project first."},
            {"label": "Text Cleanup", "status": "not_started",
             "note": "Import a source first."},
            {"label": "Text Chunking", "status": "not_started",
             "note": "Run cleanup first."},
            {"label": "AI Translation", "status": "not_started",
             "note": "Run chunking first."},
            {"label": "Characters", "status": "not_started",
             "note": "Chunks are not ready yet."},
            {"label": "Narration Plan", "status": "not_started",
             "note": "Characters are not ready yet."},
            {"label": "Generation", "status": "not_started",
             "note": "Narration plan is not ready yet."},
            {"label": "Export", "status": "not_started",
             "note": "Generated audio is not ready yet."},
        ])

        pages = {
            "home": home_page,
            "text_cleanup": TextCleanupPage(self),
            "text_chunking": PlaceholderPage(
                "Text Chunking",
                "This page matches the copied shell only. Chunking behavior is "
                "not implemented in AudioMancer yet.",
                self,
            ),
            "ai_translation": PlaceholderPage(
                "AI Translation",
                "This page matches the copied shell only. Translation behavior "
                "is not implemented in AudioMancer yet.",
                self,
            ),
            "characters": PlaceholderPage(
                "Characters",
                "This page matches the copied shell only. Character discovery "
                "behavior is not implemented in AudioMancer yet.",
                self,
            ),
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
            self._sidebar.add_page(page_id, label, enabled=True)

    def _build_dialogs(self) -> None:
        """
        @brief      Build static placeholder dialogs for the copied shell.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        self._settings_dialog = QDialog(self)
        self._settings_dialog.setWindowTitle(_build_window_title("Settings"))
        self._settings_dialog.resize(680, 560)
        settings_layout = QVBoxLayout(self._settings_dialog)
        settings_layout.addWidget(PlaceholderPage(
            "Settings",
            "The DDP_Audiomancer settings dialog shell is reserved here. "
            "No settings behavior is wired in AudioMancer yet.",
            self._settings_dialog,
        ))

        self._ai_settings_dialog = QDialog(self)
        self._ai_settings_dialog.setWindowTitle(
            _build_window_title("AI Settings")
        )
        self._ai_settings_dialog.resize(920, 640)
        ai_layout = QVBoxLayout(self._ai_settings_dialog)
        ai_layout.addWidget(PlaceholderPage(
            "AI Settings",
            "The DDP_Audiomancer AI settings dialog shell is reserved here. "
            "No AI settings behavior is wired in AudioMancer yet.",
            self._ai_settings_dialog,
        ))

    def _build_about_dialog(self) -> QDialog:
        """
        @brief      Build the About dialog for the AudioMancer shell.
        @return     Configured Qt dialog instance.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        dialog = QDialog(self)
        dialog.setWindowTitle(_build_window_title("About"))
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

        subtitle = QLabel("Transform written words into real audio experience!")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        details = QLabel(
            "Eng. Dipl. Dan Dumitru Pasare\n"
            "pasaredan1979@gmail.com"
        )
        details.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(details)
        layout.addSpacing(12)

        license_label = QLabel("License")
        layout.addWidget(license_label)

        license_text_box = QPlainTextEdit(dialog)
        license_text_box.setObjectName("aboutLicenseTextBox")
        license_text_box.setReadOnly(True)
        license_text_box.setPlainText(self._load_about_license_text())
        layout.addWidget(license_text_box, 1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, dialog)
        button_box.accepted.connect(dialog.accept)
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(button_box)
        button_layout.addStretch(1)
        layout.addLayout(button_layout)
        return dialog

    def _load_about_license_text(self) -> str:
        """
        @brief      Load the main and addendum license text for the About dialog.
        @return     Combined operator-facing license text.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        return (
            _read_text_file(LICENSE_PATH)
            + "\n\n"
            + "=" * 78
            + "\n\n"
            + _read_text_file(LICENSE_NC_PATH)
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """
        @brief      Handle window close for the static shell.
        @param[in]  event Qt close event.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
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


# END OF FILE
