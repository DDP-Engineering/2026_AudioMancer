#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_operation_status_button.py
@brief Shell tests for the sidebar operation-status button.
@details Verifies the button follows the persisted run status of the current
         page's workflow operation and opens the modeless status dialog.
"""

# IMPORTS

from audiomancer.services import project_workspace_service, ui_state_service
from audiomancer.ui.main_window import MainWindow

# PUBLIC API


def test_operation_status_button_is_disabled_without_a_project(qtbot, default_settings_payload) -> None:
    """
    @brief      Verify the button is dead before any project is open.
    @details    Covers REQ-UX-2b482f01.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  default_settings_payload Default settings fixture.
    @return     None.
    @exception  None
    """
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)

    assert window._operation_status_button.isEnabled() is False


def test_operation_status_button_follows_the_current_page_operation_status(
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify enablement tracks the persisted status of the page's own operation.
    @details    Covers REQ-UX-2b482f01: a not-started operation leaves the button
                disabled, and every other persisted status enables it.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Default settings fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("StatusButtonProject", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, manifest)

    window.set_current_page("text_cleanup")
    assert window._operation_status_button.isEnabled() is False

    for status in ("running", "completed", "failed", "cancelled"):
        manifest["operations"]["cleanup"]["status"] = status
        window._activate_project(project_root, manifest)
        window.set_current_page("text_cleanup")
        assert window._operation_status_button.isEnabled() is True, status

    # A different page reads its own operation, which is still untouched.
    window.set_current_page("text_chunking")
    assert window._operation_status_button.isEnabled() is False


def test_operation_status_button_opens_the_dialog_and_follows_the_page(
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify the button shows the current page's status and tracks navigation.
    @details    Covers REQ-UX-1829f58e: pressing the button opens a modeless dialog
                carrying the page's own status text, and because it does not block
                the shell, switching page updates the text in place.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Default settings fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("StatusDialogProject", tmp_path)
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["chunking"]["status"] = "failed"
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, manifest)
    window.set_current_page("text_cleanup")

    window._operation_status_button.click()
    dialog = window._operation_status_dialog

    assert dialog.isVisible() is True
    assert dialog.isModal() is False
    assert dialog.status_text() == window._text_cleanup_page.operation_status_text()

    window.set_current_page("text_chunking")
    assert dialog.status_text() == window._text_chunking_page.operation_status_text()


def test_operation_status_button_label_localizes(qtbot, default_settings_payload) -> None:
    """
    @brief      Verify the button caption resolves from the UI catalog in both languages.
    @details    Covers REQ-UX-aa109e16 for the new persistent shell control.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  default_settings_payload Default settings fixture.
    @return     None.
    @exception  None
    """
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)

    assert window._operation_status_button.text() == ui_state_service.translate("sidebar.operation_status", "en")

    window.apply_language("ro")
    assert window._operation_status_button.text() == ui_state_service.translate("sidebar.operation_status", "ro")
    assert window._operation_status_dialog.windowTitle() == ui_state_service.translate(
        "dialog.operation_status_title",
        "ro",
    )


# END OF FILE
