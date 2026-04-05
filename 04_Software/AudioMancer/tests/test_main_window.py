#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_main_window.py
@brief Qt window tests for the copied AudioMancer main-window shell.
@details Validates that the DDP_Audiomancer-style toolbar, sidebar, stacked
         pages, and status bar are created without workflow functionality.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.3.8
"""

# IMPORTS

from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QToolBar,
)

from audiomancer.ui.main_window import MainWindow

# PUBLIC API


def test_main_window_can_be_created(qtbot) -> None:
    """
    @brief      Verify the main window can be created in a Qt test context.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.3.8
    """
    window = MainWindow()
    qtbot.addWidget(window)

    assert (
        window.windowTitle()
        == "AudioMancer | Transform written words into real audio experience!"
    )
    assert window.centralWidget() is not None
    assert len(window.findChildren(QToolBar)) == 1
    assert len(window.findChildren(QListWidget)) >= 2
    assert window.findChild(QStackedWidget) is not None
    assert len(window.findChildren(QDialog)) == 2
    assert any(
        group_box.title() == "Project Summary"
        for group_box in window.findChildren(QGroupBox)
    )
    assert any(
        group_box.title() == "Workflow Progress"
        for group_box in window.findChildren(QGroupBox)
    )
    assert any(
        group_box.title() == "Narrator Profiles"
        for group_box in window.findChildren(QGroupBox)
    )
    assert any(
        group_box.title() == "Voice Designer Prompt"
        for group_box in window.findChildren(QGroupBox)
    )
    assert any(
        button.text() == "Deterministic Cleanup"
        for button in window.findChildren(QPushButton)
    )
    assert any(
        button.text() == "Deterministic Chunking"
        for button in window.findChildren(QPushButton)
    )
    assert any(
        button.text() == "Start Translation"
        for button in window.findChildren(QPushButton)
    )
    assert any(
        button.text() == "Start Discovery"
        for button in window.findChildren(QPushButton)
    )
    assert any(
        button.text() == "Preview"
        for button in window.findChildren(QPushButton)
    )
    assert any(
        button.text() == "Delete Profile"
        for button in window.findChildren(QPushButton)
    )


def test_about_dialog_includes_license_text(qtbot) -> None:
    """
    @brief      Verify the About dialog exposes both license texts.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    window = MainWindow()
    qtbot.addWidget(window)

    dialog = window._build_about_dialog()
    text_box = dialog.findChild(QPlainTextEdit, "aboutLicenseTextBox")

    assert (
        dialog.windowTitle()
        == "AudioMancer | Transform written words into real audio experience! | About"
    )
    assert dialog.width() == 510
    assert text_box is not None
    assert any(
        label.text() == "Transform written words into real audio experience!"
        for label in dialog.findChildren(QLabel)
    )
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in text_box.toPlainText()
    assert "Additional Non-Commercial Restriction" in text_box.toPlainText()


# END OF FILE
