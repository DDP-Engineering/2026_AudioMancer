#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_operation_progress_dialog.py
@brief Focused interaction coverage for the shared operation-progress dialog.
@details Verifies localized rendering and the active-dialog contract that turns
         dismissal into one visible cooperative-cancellation request.
"""

# IMPORTS

from PySide6.QtCore import Qt

from audiomancer.services import ui_state_service
from audiomancer.ui.operation_progress_dialog import OperationProgressDialog

# PUBLIC API


def test_progress_dialog_localizes_title_cancel_and_token_usage(qtbot) -> None:
    """
    @brief      Verify runtime dialog localization includes title, cancel text, and token usage.
    @return     None.
    @exception  None.
    """
    dialog = OperationProgressDialog()
    qtbot.addWidget(dialog)

    dialog.apply_language("ro")
    dialog.start("Traducere", "Se pregateste", cancellable=True)
    dialog.update_progress(
        135,
        "In lucru",
        {"input_tokens": 1200, "output_tokens": 34, "total_tokens": 1234, "usage_available": True},
    )

    assert dialog.windowTitle() == ui_state_service.translate(
        "dialog.operation_progress_title", "ro"
    ).format(operation_name="Traducere")
    assert dialog._cancel_button.text() == ui_state_service.translate(  # noqa: SLF001
        "dialog.operation_progress_cancel", "ro"
    )
    assert dialog._progress_bar.value() == 100  # noqa: SLF001
    assert dialog.status_message() == "In lucru"
    assert dialog._token_usage_label.text() == ui_state_service.translate(  # noqa: SLF001
        "dialog.operation_progress_token_usage", "ro"
    ).format(input_tokens="1,200", output_tokens="34", total_tokens="1,234")
    assert dialog._token_usage_label.isVisible()  # noqa: SLF001


def test_escape_requests_cancellation_without_hiding_active_dialog(qtbot) -> None:
    """
    @brief      Verify Escape requests cancellation while retaining the active modal dialog.
    @return     None.
    @exception  None.
    """
    dialog = _start_dialog(qtbot, cancellable=True)
    requests = _record_cancel_requests(dialog)

    qtbot.keyClick(dialog, Qt.Key.Key_Escape)

    assert requests == [True]
    assert dialog.isVisible()
    assert dialog.windowModality() == Qt.WindowModality.ApplicationModal
    assert not dialog._cancel_button.isEnabled()  # noqa: SLF001


def test_close_requests_cancellation_without_hiding_active_dialog(qtbot) -> None:
    """
    @brief      Verify a close request cannot bypass active-dialog cancellation handling.
    @return     None.
    @exception  None.
    """
    dialog = _start_dialog(qtbot, cancellable=True)
    requests = _record_cancel_requests(dialog)

    dialog.close()

    assert requests == [True]
    assert dialog.isVisible()
    assert dialog.windowModality() == Qt.WindowModality.ApplicationModal
    assert not dialog._cancel_button.isEnabled()  # noqa: SLF001


def test_repeated_active_dialog_dismissal_attempts_emit_one_cancellation_request(qtbot) -> None:
    """
    @brief      Verify dismissal and button paths share one idempotent cancellation request.
    @return     None.
    @exception  None.
    """
    dialog = _start_dialog(qtbot, cancellable=True)
    requests = _record_cancel_requests(dialog)

    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    dialog.close()
    dialog._cancel_button.click()  # noqa: SLF001

    assert requests == [True]
    assert dialog.isVisible()


def test_non_cancellable_active_dialog_ignores_escape_and_close(qtbot) -> None:
    """
    @brief      Verify non-cancellable active dialogs remain visible without a cancellation signal.
    @return     None.
    @exception  None.
    """
    dialog = _start_dialog(qtbot, cancellable=False)
    requests = _record_cancel_requests(dialog)

    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    dialog.close()

    assert requests == []
    assert dialog.isVisible()


def test_cancel_button_requests_cancellation_once_without_hiding_active_dialog(qtbot) -> None:
    """
    @brief      Verify the existing Cancel control retains idempotent visible behavior.
    @return     None.
    @exception  None.
    """
    dialog = _start_dialog(qtbot, cancellable=True)
    requests = _record_cancel_requests(dialog)

    dialog._cancel_button.click()  # noqa: SLF001
    dialog._cancel_button.click()  # noqa: SLF001

    assert requests == [True]
    assert dialog.isVisible()
    assert not dialog._cancel_button.isEnabled()  # noqa: SLF001


def test_terminal_dialog_lifecycle_hides_after_finish_and_failure(qtbot) -> None:
    """
    @brief      Verify terminal lifecycle methods retain their normal hide behavior.
    @return     None.
    @exception  None.
    """
    dialog = _start_dialog(qtbot, cancellable=True)

    dialog.finish()

    assert not dialog.isVisible()

    dialog.start("Operation", "Running", cancellable=True)
    dialog.fail("Cancelled")

    assert dialog.status_message() == "Cancelled"
    assert not dialog.isVisible()


# HELPER FUNCTIONS


def _start_dialog(qtbot, cancellable: bool) -> OperationProgressDialog:
    """
    @brief      Create and display one active operation-progress dialog.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  cancellable True when the Cancel control is available.
    @return     Active dialog instance.
    @exception  None.
    """
    dialog = OperationProgressDialog()
    qtbot.addWidget(dialog)
    dialog.start("Operation", "Running", cancellable=cancellable)
    return dialog


def _record_cancel_requests(dialog: OperationProgressDialog) -> list[bool]:
    """
    @brief      Capture cancellation requests emitted by one dialog.
    @param[in]  dialog Dialog being observed.
    @return     Mutable request recorder.
    @exception  None.
    """
    requests: list[bool] = []
    dialog.cancel_requested.connect(lambda: requests.append(True))
    return requests


# END OF FILE
