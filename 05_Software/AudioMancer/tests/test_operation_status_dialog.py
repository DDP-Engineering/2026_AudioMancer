#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_operation_status_dialog.py
@brief Tests for the reusable modeless operation-status dialog.
@details Verifies the dialog carries operator status text, stays out of the
         shell's way, and follows the active UI language.
"""

# IMPORTS

from PySide6.QtCore import Qt

from audiomancer.services import ui_state_service
from audiomancer.ui.operation_status_dialog import OperationStatusDialog

# PUBLIC API


def test_operation_status_dialog_is_modeless(qtbot) -> None:
    """
    @brief      Verify the dialog never seizes the shell.
    @details    Covers REQ-UX-1829f58e: the operator reads the status against the
                page behind it, so the dialog must not be modal in either sense.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    dialog = OperationStatusDialog()
    qtbot.addWidget(dialog)

    assert dialog.isModal() is False
    assert dialog.windowModality() == Qt.WindowModality.NonModal


def test_operation_status_dialog_shows_the_supplied_status_text(qtbot) -> None:
    """
    @brief      Verify the dialog renders exactly the status text it is given.
    @details    Covers REQ-UX-1829f58e.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    dialog = OperationStatusDialog()
    qtbot.addWidget(dialog)

    dialog.set_status_text("Cleanup status: completed (done).\nWords: 7412.")

    assert dialog.status_text() == "Cleanup status: completed (done).\nWords: 7412."


def test_operation_status_dialog_editor_uses_the_ui_font_role(qtbot) -> None:
    """
    @brief      Verify the status editor follows the interface font, not the content font.
    @details    Covers REQ-UX-2f024851.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    dialog = OperationStatusDialog()
    qtbot.addWidget(dialog)

    assert (
        dialog._status_edit.property(ui_state_service.CONTROL_TEXT_FONT_ROLE_PROPERTY)
        == ui_state_service.CONTROL_TEXT_FONT_ROLE_VALUE
    )


def test_operation_status_dialog_localizes_title_and_close(qtbot) -> None:
    """
    @brief      Verify dialog captions resolve from the UI catalog.
    @details    Covers REQ-UX-aa109e16 for the new dialog surface.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    dialog = OperationStatusDialog()
    qtbot.addWidget(dialog)

    dialog.apply_language("ro")

    assert dialog.windowTitle() == ui_state_service.translate("dialog.operation_status_title", "ro")
    assert dialog._close_button.text() == ui_state_service.translate("dialog.close", "ro")


# END OF FILE
