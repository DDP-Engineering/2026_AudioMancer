#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file operation_status_dialog.py
@brief Reusable modeless dialog showing one workflow operation's status.
@details Presents the operator status text a workflow page composes for its own
         operation, in a resizable window that leaves the shell usable.
"""

# IMPORTS

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QPushButton, QVBoxLayout

from audiomancer.services import ui_state_service

# PUBLIC API


class OperationStatusDialog(QDialog):
    """
    @brief      Display one workflow operation's status without blocking the shell.
    @exception  None
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the operation-status dialog widgets.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        """
        super().__init__(parent)
        self._current_language = "en"
        # Deliberately not modal: the status is read against the page behind it,
        # and the application-modal slot belongs to the operation-progress dialog,
        # which owns cancellation of a running operation.
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setMinimumSize(480, 260)

        layout = QVBoxLayout(self)
        self._status_edit = QPlainTextEdit(self)
        self._status_edit.setReadOnly(True)
        self._status_edit.setProperty(
            ui_state_service.CONTROL_TEXT_FONT_ROLE_PROPERTY,
            ui_state_service.CONTROL_TEXT_FONT_ROLE_VALUE,
        )
        layout.addWidget(self._status_edit, 1)
        self._close_button = QPushButton("", self)
        self._close_button.clicked.connect(self.close)
        layout.addWidget(self._close_button, 0)
        self.apply_language(self._current_language)

    def set_status_text(self, status_text: str) -> None:
        """
        @brief      Show one operation's status text.
        @param[in]  status_text Operator-facing status text, already composed.
        @return     None.
        @exception  None
        """
        self._status_edit.setPlainText(status_text or "")

    def status_text(self) -> str:
        """
        @brief      Return the status text currently displayed.
        @return     Displayed status text.
        @exception  None
        """
        return self._status_edit.toPlainText()

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the dialog captions.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        """
        self._current_language = language
        self.setWindowTitle(ui_state_service.translate("dialog.operation_status_title", language))
        self._close_button.setText(ui_state_service.translate("dialog.close", language))


# END OF FILE
