#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file operation_progress_dialog.py
@brief Reusable modal progress dialog for long-running workflow operations.
@details Shows one application-modal operation status, percent progress, and
         one cancel action while blocking access to the main shell.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.5.0
"""

# IMPORTS

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout

from audiomancer.services import token_usage_service, ui_state_service

_TOKEN_USAGE_UNSET = object()


class OperationProgressDialog(QDialog):
    """
    @brief      Display one reusable modal progress dialog for workflow operations.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.5.0
    """

    cancel_requested = Signal()

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the operation-progress dialog widgets.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.5.0
        """
        super().__init__(parent)
        self._current_language = "en"
        self._operation_name = ""
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._token_usage = token_usage_service.empty_token_usage()
        self._token_usage_visible = False

        layout = QVBoxLayout(self)
        self._status_label = QLabel("", self)
        self._status_label.setWordWrap(True)
        self._token_usage_label = QLabel("", self)
        self._token_usage_label.setWordWrap(True)
        self._token_usage_label.setVisible(False)
        self._progress_bar = QProgressBar(self)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("%p%")
        self._cancel_button = QPushButton("", self)
        self._cancel_button.clicked.connect(self._emit_cancel_requested)

        layout.addWidget(self._status_label)
        layout.addWidget(self._token_usage_label)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._cancel_button)
        self.apply_language(self._current_language)

    def start(self, operation_name: str, message: str, cancellable: bool = True) -> None:
        """
        @brief      Prepare and show the dialog for one active operation.
        @param[in]  operation_name Operator-facing operation label.
        @param[in]  message Initial progress status message.
        @param[in]  cancellable True to expose the cancel button.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.5.0
        """
        self._operation_name = operation_name
        self.setWindowTitle(
            ui_state_service.translate("dialog.operation_progress_title", self._current_language).format(
                operation_name=operation_name
            )
        )
        self._status_label.setText(message)
        self._set_token_usage(None)
        self._progress_bar.setValue(0)
        self._cancel_button.setEnabled(cancellable)
        self._cancel_button.setVisible(cancellable)
        self.show()
        self.raise_()
        self.activateWindow()
        self.repaint()

    def update_progress(
        self,
        percent: int,
        message: str,
        token_usage: object = _TOKEN_USAGE_UNSET,
    ) -> None:
        """
        @brief      Refresh the dialog progress widgets.
        @param[in]  percent Integer progress value in the 0-100 range.
        @param[in]  message Operator-facing progress status message.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.5.0
        """
        self._progress_bar.setValue(max(0, min(percent, 100)))
        self._status_label.setText(message)
        if token_usage is not _TOKEN_USAGE_UNSET:
            self._set_token_usage(token_usage)
        self.repaint()

    def finish(self) -> None:
        """
        @brief      Close the dialog after one successful operation.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.3.0
        """
        self.hide()

    def fail(self, message: str) -> None:
        """
        @brief      Update the failure message and close the dialog.
        @param[in]  message Operator-facing failure or cancellation message.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.3.0
        """
        self._status_label.setText(message)
        self.hide()

    def status_message(self) -> str:
        """
        @brief      Return the currently displayed operator-facing status text.
        @return     Current progress status text.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        return self._status_label.text()

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one runtime UI language to dialog labels.
        @param[in]  language Runtime UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.5.0
        """
        self._current_language = language
        if self._operation_name:
            self.setWindowTitle(
                ui_state_service.translate("dialog.operation_progress_title", language).format(
                    operation_name=self._operation_name
                )
            )
        self._cancel_button.setText(ui_state_service.translate("dialog.operation_progress_cancel", language))
        self._refresh_token_usage_label()

    def _emit_cancel_requested(self) -> None:
        """
        @brief      Disable repeat clicks and emit one cancellation request.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.3.0
        """
        self._cancel_button.setEnabled(False)
        self.cancel_requested.emit()

    def _set_token_usage(self, token_usage: object) -> None:
        if token_usage is None:
            self._token_usage = token_usage_service.empty_token_usage()
            self._token_usage_visible = False
        else:
            self._token_usage = token_usage_service.coerce_token_usage(token_usage)
            self._token_usage_visible = True
        self._refresh_token_usage_label()

    def _refresh_token_usage_label(self) -> None:
        if not self._token_usage_visible:
            self._token_usage_label.clear()
            self._token_usage_label.setVisible(False)
            return
        if bool(self._token_usage.get("usage_available", False)):
            self._token_usage_label.setText(
                ui_state_service.translate(
                    "dialog.operation_progress_token_usage",
                    self._current_language,
                ).format(
                    input_tokens=format(int(self._token_usage["input_tokens"]), ","),
                    output_tokens=format(int(self._token_usage["output_tokens"]), ","),
                    total_tokens=format(int(self._token_usage["total_tokens"]), ","),
                )
            )
        else:
            self._token_usage_label.setText(
                ui_state_service.translate(
                    "dialog.operation_progress_token_usage_unavailable",
                    self._current_language,
                )
            )
        self._token_usage_label.setVisible(True)


# END OF FILE
