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

import audiomancer.ui.main_window as main_window_module
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
    assert any(
        button.text() == "Save AI Settings"
        for button in window.findChildren(QPushButton)
    )
    assert any(
        button.text() == "Connect"
        for button in window.findChildren(QPushButton)
    )
    assert any(
        button.text() == "Save Settings"
        for button in window.findChildren(QPushButton)
    )
    assert any(
        label.text() == "Interface Text Size"
        for label in window.findChildren(QLabel)
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
        == "About"
    )
    assert dialog.width() == 510
    assert text_box is not None
    assert any(
        label.text() == "Transform written words into real audio experience!"
        for label in dialog.findChildren(QLabel)
    )
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in text_box.toPlainText()
    assert "Additional Non-Commercial Restriction" in text_box.toPlainText()


def test_main_window_saves_settings_dialog_payload(monkeypatch, qtbot) -> None:
    persisted_payload = {
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": None,
    }
    saved_payloads = []

    def _fake_load_settings():
        return dict(persisted_payload)

    def _fake_save_settings(payload):
        saved_payloads.append(dict(payload))
        persisted_payload.update(payload)

    monkeypatch.setattr(main_window_module.settings_service, "load_settings", _fake_load_settings)
    monkeypatch.setattr(main_window_module.settings_service, "save_settings", _fake_save_settings)

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)

    window.show_settings_dialog()
    window._settings_page._language_combo.setCurrentText("ro")
    window._settings_page._completion_beep_checkbox.setChecked(True)
    window._settings_page._save_button.click()

    assert saved_payloads
    assert persisted_payload["language"] == "ro"
    assert persisted_payload["play_completion_beep"] is True
    assert window._settings_dialog.isVisible() is False


def test_main_window_reloads_dialogs_and_discards_unsaved_changes(monkeypatch, qtbot) -> None:
    persisted_payload = {
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [
            {
                "id": "profile_1",
                "label": "Stored Profile",
                "backend_kind": "lmstudio",
                "base_url": "http://127.0.0.1:1234/v1",
                "api_key": "",
                "model_name": "qwen3-8b",
                "context_window": 8192,
                "max_output_tokens": 1024,
                "request_timeout_seconds": 90,
                "temperature": 0.2,
                "supports_structured_output": False,
                "enabled": True,
            }
        ],
        "default_ai_cleanup_profile_id": "profile_1",
        "default_ai_chunking_profile_id": "profile_1",
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": "profile_1",
    }

    monkeypatch.setattr(
        main_window_module.settings_service,
        "load_settings",
        lambda: dict(persisted_payload),
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)

    window.show_settings_dialog()
    window._settings_page._language_combo.setCurrentText("ro")
    window._settings_page._cancel_button.click()
    window.show_settings_dialog()
    assert window._settings_page._language_combo.currentText() == "en"

    window.show_ai_settings_dialog()
    window._ai_settings_page._label_edit.setText("Unsaved Profile Name")
    window._ai_settings_page._cancel_button.click()
    window.show_ai_settings_dialog()
    assert window._ai_settings_page._label_edit.text() == "Stored Profile"


# END OF FILE
