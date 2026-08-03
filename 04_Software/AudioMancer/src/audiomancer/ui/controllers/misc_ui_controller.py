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
         dialogs, the common modal progress popup, the operator completion
         beep, and title-bar helpers.
"""

# IMPORTS

from importlib import metadata
from pathlib import Path
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
    """
    _ = window
    _ = message
    _ = timeout_ms


def play_completion_beep(window: "MainWindow") -> None:
    """
    @brief      Play the operator completion beep when the active settings enable it.
    @details    Called from operation terminal outcomes the operator did not request,
                so an operator who left the machine hears that the run is over.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
    """
    settings_payload = getattr(window, "_settings_payload", None)
    if ui_state_service.completion_beep_enabled_from_settings(settings_payload):
        QApplication.beep()


def show_help(window: "MainWindow") -> None:
    """
    @brief      Open the packaged offline user guide in the system browser.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
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
    """
    build_about_dialog(window).exec()


def prompt_multiline_text(
    window: "MainWindow",
    title: str,
    label: str,
    initial_text: str = "",
) -> str | None:
    """
    @brief      Ask the operator for optional multi-line text with word wrapping.
    @param[in]  window Active main window shell.
    @param[in]  title Dialog title.
    @param[in]  label Dialog explanatory label.
    @param[in]  initial_text Initial text box value.
    @return     Entered text, or None when cancelled.
    @exception  None
    """
    dialog = QDialog(window)
    dialog.setWindowTitle(title)
    dialog.resize(560, 340)

    layout = QVBoxLayout(dialog)
    prompt_label = QLabel(label, dialog)
    prompt_label.setWordWrap(True)
    layout.addWidget(prompt_label)

    text_edit = QPlainTextEdit(dialog)
    text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
    text_edit.setPlainText(initial_text)
    layout.addWidget(text_edit, 1)

    button_box = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        dialog,
    )
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)
    layout.addWidget(button_box)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return text_edit.toPlainText()


def build_about_dialog(window: "MainWindow") -> QDialog:
    """
    @brief      Build the About dialog for the AudioMancer shell.
    @param[in]  window Active main window shell.
    @return     Configured Qt dialog instance.
    @exception  None
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
    """
    if PYPROJECT_PATH.is_file():
        payload = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
        project_payload = payload.get("project", {})
        if isinstance(project_payload, dict):
            version = str(project_payload.get("version", "") or "").strip()
            if version:
                return version
    try:
        return metadata.version(config.PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return "unknown"


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
    """
    current_language = ui_state_service.current_language_from_settings(
        getattr(window, "_settings_payload", None)
    )
    window._operation_progress_dialog = OperationProgressDialog(window)
    window._operation_progress_dialog.apply_language(current_language)
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
    """
    QApplication.processEvents()


def finish_progress_dialog(window: "MainWindow") -> None:
    """
    @brief      Mark the shared modal progress dialog as finished when present.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
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
    """
    if window._operation_progress_dialog is not None:
        window._operation_progress_dialog.fail(message)


def clear_progress_dialog(window: "MainWindow") -> None:
    """
    @brief      Destroy the shared modal progress dialog when present.
    @param[in]  window Active main window shell.
    @return     None.
    @exception  None
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
    """
    main_license_path, addendum_path = resolve_license_paths(language)
    return read_text_file(main_license_path) + "\n\n" + "=" * 78 + "\n\n" + read_text_file(addendum_path)


def resolve_license_paths(language: str) -> tuple[Path, Path]:
    """
    @brief      Resolve the localized license-file pair for one UI language.
    @param[in]  language Target UI language code.
    @return     Tuple of main-license path and addendum-license path.
    @exception  None
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
    """
    resolved_language = language if language in config.APP_HELP_INDEX_RELATIVE_PATHS else config.DEFAULT_LANGUAGE
    packaged_relative_path = config.APP_HELP_INDEX_RELATIVE_PATHS[resolved_language]
    source_index_path = config.APP_HELP_SOURCE_INDEX_PATHS[resolved_language]
    return [
        config.APP_ROOT / packaged_relative_path,
        Path.cwd().resolve() / packaged_relative_path,
        source_index_path,
    ]


# END OF FILE
