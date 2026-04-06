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
@date 2026-04-06
@version 0.7.0
"""

# IMPORTS

from PySide6.QtWidgets import (
    QApplication,
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
from audiomancer.services import project_workspace_service
from audiomancer.ui.main_window import MainWindow

# PUBLIC API


def test_main_window_can_be_created(qtbot) -> None:
    """
    @brief      Verify the main window can be created in a Qt test context.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.4.0
    """
    window = MainWindow(settings_payload={
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": None,
    })
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
    assert window._sidebar.item(1).flags() == main_window_module.Qt.ItemFlag.NoItemFlags


def test_about_dialog_includes_license_text(qtbot) -> None:
    """
    @brief      Verify the About dialog exposes both license texts.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    window = MainWindow(settings_payload={
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": None,
    })
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


def test_about_dialog_loads_translated_license_text_for_romanian(qtbot) -> None:
    """
    @brief      Verify the About dialog loads the Romanian license companion files.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    window = MainWindow(settings_payload={
        "language": "ro",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": None,
    })
    qtbot.addWidget(window)

    dialog = window._build_about_dialog()
    text_box = dialog.findChild(QPlainTextEdit, "aboutLicenseTextBox")

    assert dialog.windowTitle() == "Despre"
    assert text_box is not None
    assert "LICENTA PUBLICA GENERALA AFFERO GNU" in text_box.toPlainText()
    assert "RESTRICTIE SUPLIMENTARA DE UTILIZARE NECOMERCIALA" in text_box.toPlainText()


def test_main_window_saves_settings_dialog_payload(monkeypatch, qtbot) -> None:
    """
    @brief      Verify saving Settings persists and reapplies runtime UI state.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
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
        """
        @brief      Return the current fake persisted settings payload.
        @return     Copy of the fake persisted settings payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        return dict(persisted_payload)

    def _fake_save_settings(payload):
        """
        @brief      Capture and merge one fake saved settings payload.
        @param[in]  payload Settings payload to persist.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        saved_payloads.append(dict(payload))
        persisted_payload.update(payload)

    monkeypatch.setattr(main_window_module.settings_service, "load_settings", _fake_load_settings)
    monkeypatch.setattr(main_window_module.settings_service, "save_settings", _fake_save_settings)

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)
    starting_font_size = QApplication.instance().font().pointSizeF()

    window.show_settings_dialog()
    window._settings_page._language_combo.setCurrentText("ro")
    window._settings_page._ui_text_scale_combo.setCurrentIndex(
        window._settings_page._ui_text_scale_combo.findData("large")
    )
    window._settings_page._completion_beep_checkbox.setChecked(True)
    window._settings_page._save_button.click()

    assert saved_payloads
    assert persisted_payload["language"] == "ro"
    assert persisted_payload["ui_text_scale"] == "large"
    assert persisted_payload["play_completion_beep"] is True
    assert window._settings_dialog.isVisible() is False
    assert window.windowTitle() == (
        "AudioMancer | Transforma cuvintele scrise intr-o experienta audio reala!"
    )
    assert window._action_settings.text() == "Setari"
    assert window._sidebar.item(0).text() == "Acasa / Proiect"
    assert (
        window._settings_page._save_button.text()
        == "Salveaza Setarile"
    )
    assert QApplication.instance().font().pointSizeF() > starting_font_size


def test_main_window_reloads_dialogs_and_discards_unsaved_changes(monkeypatch, qtbot) -> None:
    """
    @brief      Verify dialog cancel actions discard unsaved editor changes.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
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


def test_settings_dialog_reopens_with_translated_labels(monkeypatch, qtbot) -> None:
    """
    @brief      Verify reopened Settings labels respect the persisted language.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    persisted_payload = {
        "language": "ro",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": None,
    }

    monkeypatch.setattr(
        main_window_module.settings_service,
        "load_settings",
        lambda: dict(persisted_payload),
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)

    window.show_settings_dialog()

    assert window._settings_dialog.windowTitle() == "Setari"
    assert window._settings_page._language_label.text() == "Limba"
    assert window._settings_page._text_size_label.text() == "Dimensiune Text Interfata"


def test_main_window_connect_ai_profile_shows_success_popup(monkeypatch, qtbot) -> None:
    """
    @brief      Verify a successful AI connect shows translated popup feedback.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    persisted_payload = {
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [{
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
        }],
        "default_ai_cleanup_profile_id": "profile_1",
        "default_ai_chunking_profile_id": "profile_1",
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": "profile_1",
    }
    popup_calls = []

    monkeypatch.setattr(
        main_window_module.ai_backend_service,
        "probe_profile",
        lambda profile: {
            "success": True,
            "message": "Connection successful. Discovered 2 models.",
            "discovered_models": [
                {"id": "qwen3-8b", "label": "qwen3-8b"},
                {"id": "llama-3.1-8b", "label": "llama-3.1-8b"},
            ],
            "discovered_model_count": 2,
            "discovered_context_window": None,
            "selected_model_valid": True,
        },
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "information",
        lambda *args: popup_calls.append(args),
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)

    window.show_ai_settings_dialog()
    window._ai_settings_page._connect_button.click()

    assert popup_calls
    assert "Connection successful." in popup_calls[0][2]
    assert "Discovered models: 2" in popup_calls[0][2]


def test_main_window_connect_ai_profile_shows_failure_popup(monkeypatch, qtbot) -> None:
    """
    @brief      Verify a failed AI connect shows translated popup feedback.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    persisted_payload = {
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [{
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
        }],
        "default_ai_cleanup_profile_id": "profile_1",
        "default_ai_chunking_profile_id": "profile_1",
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": "profile_1",
    }
    popup_calls = []

    monkeypatch.setattr(
        main_window_module.ai_backend_service,
        "probe_profile",
        lambda profile: {
            "success": False,
            "message": "Connection failed: request timed out.",
            "discovered_models": [],
            "discovered_model_count": 0,
            "discovered_context_window": None,
            "selected_model_valid": False,
        },
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        lambda *args: popup_calls.append(args),
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)

    window.show_ai_settings_dialog()
    window._ai_settings_page._connect_button.click()

    assert popup_calls
    assert popup_calls[0][2] == (
        "Connection failed.\nConnection failed: request timed out."
    )


def test_main_window_creates_project_and_updates_shell(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify new-project creation activates the shell and project summary.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
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

    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        main_window_module.QInputDialog,
        "getText",
        lambda *args, **kwargs: ("Book5_CAL_CAL", True),
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)

    window._handle_new_project_requested()

    assert window._current_project_root == tmp_path / "Book5_CAL_CAL"
    assert window._current_manifest is not None
    assert window._current_manifest["display_name"] == "Book5_CAL_CAL"
    assert window._home_page._name_label.text() == "Project: Book5_CAL_CAL"
    assert window._sidebar.item(1).flags() != main_window_module.Qt.ItemFlag.NoItemFlags
    assert any(
        "Narrator Definition" in window._home_page._stage_list.item(index).text()
        for index in range(window._home_page._stage_list.count())
    )


def test_main_window_opens_project_from_child_folder(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify open-project resolves the project root from a child folder.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
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
    project_root, _manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )

    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(project_root / "40_character_discovery"),
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)

    window._handle_open_project_requested()

    assert window._current_project_root == project_root
    assert window._current_manifest is not None
    assert window._current_manifest["display_name"] == "Book5_CAL_CAL"
    assert window._home_page._path_label.text() == f"Path: {project_root}"


def test_main_window_offers_repair_and_opens_repaired_project(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify open-project offers repair for recoverable corruption.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
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
    project_root, _manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    (project_root / "40_character_discovery").rmdir()
    question_calls = []

    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(project_root),
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *args, **kwargs: (
            question_calls.append(args),
            main_window_module.QMessageBox.StandardButton.Yes,
        )[1],
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)

    window._handle_open_project_requested()

    assert question_calls
    assert window._current_project_root == project_root
    assert window._current_manifest is not None
    assert (project_root / "40_character_discovery").is_dir()
    assert window._current_manifest["current_stage"] == "project_created"
    assert window._home_page._stage_list.item(0).text() == "Source Selected | Not Started"


# END OF FILE
