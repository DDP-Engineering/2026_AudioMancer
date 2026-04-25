#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file misc_ui_controller.py
@brief Shared shell UI helpers for AudioMancer.
@details Hosts cross-window UI helpers such as status messages, help/about
         dialogs, the common modal progress popup, and title-bar helpers.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.8.1
"""

# IMPORTS

from pathlib import Path
import sys
import tomllib
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from audiomancer import config
from audiomancer.services import ui_state_service
from audiomancer.ui.operation_progress_dialog import OperationProgressDialog

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


# CONSTANTS

# @brief Operator-facing application tagline shown in window and About UI.
TAGLINE_TEXT = "Transform written words into real audio experience!"
# @brief Default main license file path used by the About dialog.
LICENSE_PATH = config.APP_ROOT / "LICENSE.txt"
# @brief Default non-commercial addendum file path used by the About dialog.
LICENSE_NC_PATH = config.APP_ROOT / "LICENSE_NC.txt"
# @brief Optional translated license file pairs keyed by runtime UI language.
LICENSE_TRANSLATED_PATHS = {
    "ro": (
        config.APP_ROOT / "LICENSE_ro.txt",
        config.APP_ROOT / "LICENSE_NC_ro.txt",
    ),
}
# @brief Project metadata file used to resolve the current application version.
PYPROJECT_PATH = config.APP_ROOT / "pyproject.toml"


# PUBLIC API


def show_message(
    window: "MainWindow",
    message: str,
    timeout_ms: int = 5000,
) -> None:
    """
    @brief      Accept one transient shell message without rendering bottom shell UI.
    @param[in]  window Active main window shell.
    @param[in]  message Operator-facing message text.
    @param[in]  timeout_ms Legacy timeout in milliseconds.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.4.0
    """
    _ = window
    _ = message
    _ = timeout_ms


def show_help(window: "MainWindow") -> None:
    """
    @brief      Open the packaged offline user guide in the system browser.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.1
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    help_index_path = resolve_help_index_path(current_language)
    if help_index_path is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.help_error_title", current_language),
            ui_state_service.translate("help.missing_file", current_language),
        )
        return
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(help_index_path))):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.help_error_title", current_language),
            ui_state_service.translate("help.open_failed", current_language).format(path=str(help_index_path)),
        )


def resolve_help_index_path(language: str | None = None) -> Path | None:
    """
    @brief      Resolve the offline user-guide entry point for one UI language.
    @param[in]  language Preferred UI language code.
    @return     Existing help index path or `None` when unavailable.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    candidate_languages = [language or config.DEFAULT_LANGUAGE]
    if config.DEFAULT_LANGUAGE not in candidate_languages:
        candidate_languages.append(config.DEFAULT_LANGUAGE)
    for candidate_language in candidate_languages:
        for candidate_path in _candidate_help_index_paths(candidate_language):
            if candidate_path.is_file():
                return candidate_path
    return None


def show_about_dialog(window: "MainWindow") -> None:
    """
    @brief      Build and show the About dialog.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    build_about_dialog(window).exec()


def build_about_dialog(window: "MainWindow") -> QDialog:
    """
    @brief      Build the About dialog for the AudioMancer shell.
    @param[in]  window Active main window shell.
    @return     Configured Qt dialog instance.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    dialog = QDialog(window)
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    application_version = current_application_version()
    dialog.setWindowTitle(ui_state_service.translate("dialog.about_title", current_language))
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

    subtitle = QLabel(ui_state_service.translate("about.subtitle", current_language))
    subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    subtitle.setWordWrap(True)
    layout.addWidget(subtitle)
    version_label = QLabel(
        ui_state_service.translate("about.version", current_language).format(version=application_version)
    )
    version_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    layout.addWidget(version_label)
    layout.addSpacing(12)

    details = QLabel(ui_state_service.translate("about.details", current_language))
    details.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    layout.addWidget(details)
    layout.addSpacing(12)

    license_label = QLabel(ui_state_service.translate("about.license", current_language))
    layout.addWidget(license_label)

    license_text_box = QPlainTextEdit(dialog)
    license_text_box.setObjectName("aboutLicenseTextBox")
    license_text_box.setReadOnly(True)
    license_text_box.setPlainText(load_about_license_text(current_language))
    layout.addWidget(license_text_box, 1)

    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, dialog)
    button_box.accepted.connect(dialog.accept)
    button_layout = QHBoxLayout()
    button_layout.addStretch(1)
    button_layout.addWidget(button_box)
    button_layout.addStretch(1)
    layout.addLayout(button_layout)
    return dialog


def current_application_version() -> str:
    """
    @brief      Resolve the current application version from project metadata.
    @return     Current application version string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not PYPROJECT_PATH.is_file():
        return "unknown"
    payload = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    project_payload = payload.get("project", {})
    if not isinstance(project_payload, dict):
        return "unknown"
    version = str(project_payload.get("version", "") or "").strip()
    return version or "unknown"


def create_progress_dialog(
    window: "MainWindow",
    operation_name: str,
    initial_message: str,
    cancel_callback,
    cancellable: bool = True,
) -> None:
    """
    @brief      Create and show the shared modal progress dialog for one running operation.
    @param[in]  window Active main window shell.
    @param[in]  operation_name Operator-facing operation name.
    @param[in]  initial_message First progress status message.
    @param[in]  cancel_callback Callback invoked when the cancel button is pressed.
    @param[in]  cancellable True when the cancel button should be available.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
    """
    window._operation_progress_dialog = OperationProgressDialog(window)
    window._operation_progress_dialog.cancel_requested.connect(cancel_callback)
    window._operation_progress_dialog.start(
        operation_name,
        initial_message,
        cancellable=cancellable,
    )


def update_progress_dialog(
    window: "MainWindow",
    percent: int,
    message: str,
    token_usage=None,
) -> None:
    """
    @brief      Update the shared modal progress dialog when present.
    @param[in]  window Active main window shell.
    @param[in]  percent Current progress percent.
    @param[in]  message Current operator-facing status message.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.1
    """
    if window._operation_progress_dialog is not None:
        window._operation_progress_dialog.update_progress(
            percent,
            message,
            token_usage,
        )


def process_pending_ui_events() -> None:
    """
    @brief      Flush pending Qt events so modal progress interactions remain responsive.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    QApplication.processEvents()


def finish_progress_dialog(window: "MainWindow") -> None:
    """
    @brief      Mark the shared modal progress dialog as finished when present.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if window._operation_progress_dialog is not None:
        window._operation_progress_dialog.finish()


def fail_progress_dialog(window: "MainWindow", message: str) -> None:
    """
    @brief      Mark the shared modal progress dialog as failed when present.
    @param[in]  window Active main window shell.
    @param[in]  message Operator-facing failure message.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if window._operation_progress_dialog is not None:
        window._operation_progress_dialog.fail(message)


def clear_progress_dialog(window: "MainWindow") -> None:
    """
    @brief      Destroy the shared modal progress dialog when present.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if window._operation_progress_dialog is not None:
        window._operation_progress_dialog.deleteLater()
        window._operation_progress_dialog = None


def load_about_license_text(language: str) -> str:
    """
    @brief      Load the main and addendum license text for the About dialog.
    @param[in]  language Target UI language code.
    @return     Combined operator-facing license text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    main_license_path, addendum_path = resolve_license_paths(language)
    return read_text_file(main_license_path) + "\n\n" + "=" * 78 + "\n\n" + read_text_file(addendum_path)


def resolve_license_paths(language: str) -> tuple[Path, Path]:
    """
    @brief      Resolve the localized license-file pair for one UI language.
    @param[in]  language Target UI language code.
    @return     Tuple of main-license path and addendum-license path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    localized_pair = LICENSE_TRANSLATED_PATHS.get(language)
    if localized_pair is None:
        return LICENSE_PATH, LICENSE_NC_PATH
    main_license_path, addendum_path = localized_pair
    if main_license_path.exists() and addendum_path.exists():
        return main_license_path, addendum_path
    return LICENSE_PATH, LICENSE_NC_PATH


def read_text_file(path: Path) -> str:
    """
    @brief      Read a UTF-8 text file for UI display.
    @param[in]  path Absolute file path to read.
    @return     Decoded text or a fallback message when unavailable.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not path.exists():
        return f"File not found: {path}"
    return path.read_text(encoding="utf-8").strip()


def build_window_title(context: str | None = None) -> str:
    """
    @brief      Build the shared title-bar text for AudioMancer windows.
    @param[in]  context Optional trailing window-specific context.
    @return     Formatted title-bar text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    title = f"{config.APP_NAME} | {TAGLINE_TEXT}"
    if context:
        return f"{title} | {context}"
    return title


# LOCAL HELPERS


def _candidate_help_index_paths(language: str | None) -> list[Path]:
    """
    @brief      Build ordered candidate locations for one offline user guide.
    @param[in]  language Preferred UI language code.
    @return     Candidate help index paths in runtime precedence order.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    executable_folder = Path(sys.executable).resolve().parent
    resolved_language = language if language in config.APP_HELP_INDEX_RELATIVE_PATHS else config.DEFAULT_LANGUAGE
    packaged_relative_path = config.APP_HELP_INDEX_RELATIVE_PATHS[resolved_language]
    source_index_path = config.APP_HELP_SOURCE_INDEX_PATHS[resolved_language]
    return [
        executable_folder / packaged_relative_path,
        Path.cwd().resolve() / packaged_relative_path,
        config.APP_ROOT / packaged_relative_path,
        source_index_path,
    ]


# END OF FILE
