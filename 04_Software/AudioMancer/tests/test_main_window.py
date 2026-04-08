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
@details Validates that the DDP_Audiomancer-style toolbar, sidebar, and stacked
         pages are created without workflow functionality.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 1.3.0
"""

# IMPORTS

import json
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGroupBox,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QToolBar,
)

import audiomancer.ui.main_window as main_window_module
from audiomancer import config
from audiomancer.services import deterministic_chunking_service
from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import ai_translation_ui_controller
from audiomancer.ui.controllers import ai_settings_ui_controller
from audiomancer.ui.controllers import home_ui_controller
from audiomancer.ui.controllers import settings_ui_controller
from audiomancer.ui.controllers import text_chunking_ui_controller
from audiomancer.ui.controllers import text_cleanup_ui_controller
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
    assert window._operation_progress_dialog is None
    assert window._status_bar is None


def test_main_window_show_message_does_not_create_status_bar(qtbot) -> None:
    """
    @brief      Verify transient shell messages do not recreate a bottom status bar.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
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

    window.show_message("Transient shell message")

    assert window._status_bar is None
    assert not window.findChildren(QStatusBar)


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

    monkeypatch.setattr(settings_ui_controller.settings_service, "load_settings", _fake_load_settings)
    monkeypatch.setattr(settings_ui_controller.settings_service, "save_settings", _fake_save_settings)

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
        settings_ui_controller.settings_service,
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
        settings_ui_controller.settings_service,
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
        ai_settings_ui_controller.ai_backend_service,
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
        ai_settings_ui_controller.QMessageBox,
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
        ai_settings_ui_controller.ai_backend_service,
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
        ai_settings_ui_controller.QMessageBox,
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
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        home_ui_controller.QInputDialog,
        "getText",
        lambda *args, **kwargs: ("Book5_CAL_CAL", True),
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)

    window._action_new_project.trigger()

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
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(project_root / "40_character_discovery"),
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)

    window._action_open_project.trigger()

    assert window._current_project_root == project_root
    assert window._current_manifest is not None
    assert window._current_manifest["display_name"] == "Book5_CAL_CAL"
    assert window._home_page._path_label.text() == f"Path: {project_root}"


def test_main_window_imports_source_and_locks_selection(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify source import updates the manifest, summary, and lock state.
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
    source_path = tmp_path / "story.epub"
    source_path.write_text("content", encoding="utf-8")

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(source_path), ""),
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    window._home_page.import_requested.emit()

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "source_selected"
    assert window._current_manifest["source_document"]["original_name"] == "story.epub"
    assert window._home_page._source_label.text() == "Source: story.epub"
    assert window._home_page._stage_list.item(0).text() == "Source Selected | Finished"
    assert window._home_page._import_button.isEnabled() is False


def test_main_window_extracts_text_and_updates_cleanup_page(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify extraction updates the manifest, preview, and completed extraction state.
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
    project_root, manifest = project_workspace_service.create_project(
        "ExtractProject",
        tmp_path,
    )
    source_path = project_root / "story.txt"
    source_path.write_text("Story body", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    project_workspace_service.save_manifest(manifest, project_root)

    extraction_state = {
        "folder_relative_path": "00_extraction",
        "status": "completed",
        "input_paths": ["00_extraction/input_story.txt"],
        "output_paths": [f"00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}"],
        "artifact_paths": [f"00_extraction/{config.EXTRACTION_REPORT_FILE_NAME}"],
        "progress_current": 1,
        "progress_total": 1,
        "mode": "deterministic",
        "started_at": "2026-04-06T12:00:00+00:00",
        "completed_at": "2026-04-06T12:01:00+00:00",
        "updated_at": "2026-04-06T12:01:00+00:00",
        "warning_count": 0,
        "metadata": {"warnings": [], "source_type": "txt"},
        "resume_checkpoint": None,
    }

    def _fake_extract_text(*args, **kwargs):
        """
        @brief      Persist fake extraction artifacts for the main-window test.
        @return     Fake extraction report payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        extraction_root = project_root / "00_extraction"
        extraction_root.mkdir(exist_ok=True)
        (extraction_root / "input_story.txt").write_text("Story body", encoding="utf-8")
        (extraction_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
            "Story body\n",
            encoding="utf-8",
        )
        (extraction_root / config.EXTRACTION_REPORT_FILE_NAME).write_text(
            (
                "{\n"
                '  "source_relative_path": "00_extraction/input_story.txt",\n'
                '  "source_type": "txt",\n'
                f'  "extracted_text_relative_path": "00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}",\n'
                '  "extracted_at": "2026-04-06T12:01:00+00:00",\n'
                '  "page_count": null,\n'
                '  "warnings": [],\n'
                '  "character_count": 10,\n'
                '  "word_count": 2,\n'
                '  "line_count": 1\n'
                "}\n"
            ),
            encoding="utf-8",
        )
        (extraction_root / config.OPERATION_STATE_FILE_NAME).write_text(
            json.dumps(extraction_state, indent=2) + "\n",
            encoding="utf-8",
        )
        return {
            "source_relative_path": "00_extraction/input_story.txt",
            "source_type": "txt",
            "extracted_text_relative_path": f"00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}",
            "extracted_at": "2026-04-06T12:01:00+00:00",
            "page_count": None,
            "warnings": [],
            "character_count": 10,
            "word_count": 2,
            "line_count": 1,
        }

    monkeypatch.setattr(
        text_cleanup_ui_controller.text_extraction_service,
        "extract_text",
        _fake_extract_text,
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    monkeypatch.setattr(
        text_cleanup_ui_controller,
        "start_operation",
        lambda _window, **kwargs: kwargs["success_handler"](
            kwargs["worker_callable"](
                _window._current_project_root,
                dict(_window._current_manifest),
                progress_callback=lambda *_args: None,
                cancel_requested=lambda: False,
            )
        ),
    )

    window._text_cleanup_page.extract_requested.emit()

    assert window._current_manifest is not None
    assert window._current_manifest["extracted_text_relative_path"] == (
        f"00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}"
    )
    assert window._current_manifest["operations"]["extraction"]["status"] == "completed"
    assert window._home_page._stage_list.item(1).text() == "Text Cleanup | In Progress"
    assert window._text_cleanup_page._extracted_text_edit.toPlainText() == "Story body\n"
    assert "Extracted 2 words across 1 lines." in window._text_cleanup_page._notes_edit.toPlainText()


def test_main_window_restarts_completed_extraction_only_after_confirmation(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify completed extraction reruns only after operator confirmation.
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
    project_root, manifest = project_workspace_service.create_project(
        "RerunProject",
        tmp_path,
    )
    source_path = project_root / "story.txt"
    source_path.write_text("Story body", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["extracted_text_relative_path"] = f"00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}"
    manifest["extraction_report_relative_path"] = f"00_extraction/{config.EXTRACTION_REPORT_FILE_NAME}"
    manifest["operations"]["extraction"]["status"] = "completed"
    manifest["operations"]["cleanup"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)

    question_calls = []
    reset_calls = []
    extract_calls = []

    monkeypatch.setattr(
        text_cleanup_ui_controller.QMessageBox,
        "question",
        lambda *args, **kwargs: (
            question_calls.append(args),
            QMessageBox.StandardButton.No,
        )[1],
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_extraction_service,
        "reset_extraction_and_downstream",
        lambda root: reset_calls.append(root),
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_extraction_service,
        "extract_text",
        lambda *args, **kwargs: extract_calls.append(args),
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    window._text_cleanup_page.extract_requested.emit()

    assert question_calls
    assert reset_calls == []
    assert extract_calls == []


def test_main_window_continues_unfinished_extraction_without_confirmation(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify unfinished extraction reruns continue directly without destructive confirmation.
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
    project_root, manifest = project_workspace_service.create_project(
        "ResumeWindowProject",
        tmp_path,
    )
    source_path = project_root / "story.txt"
    source_path.write_text("Story body", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["operations"]["extraction"]["status"] = "failed"
    manifest["operations"]["extraction"]["progress_current"] = 1
    manifest["operations"]["extraction"]["progress_total"] = 3
    project_workspace_service.save_manifest(manifest, project_root)

    question_calls = []
    extract_calls = []

    monkeypatch.setattr(
        text_cleanup_ui_controller.QMessageBox,
        "question",
        lambda *args, **kwargs: question_calls.append(args),
    )

    def _fake_extract_text(*args, **kwargs):
        """
        @brief      Record one resumed extraction call and return a minimal report.
        @return     Minimal extraction report payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        extract_calls.append(args)
        extraction_root = project_root / "00_extraction"
        extraction_root.mkdir(exist_ok=True)
        (extraction_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("Story body\n", encoding="utf-8")
        (extraction_root / config.EXTRACTION_REPORT_FILE_NAME).write_text(
            "{}\n",
            encoding="utf-8",
        )
        (extraction_root / config.OPERATION_STATE_FILE_NAME).write_text(
            json.dumps({
                "folder_relative_path": "00_extraction",
                "status": "completed",
                "input_paths": [],
                "output_paths": [f"00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}"],
                "artifact_paths": [f"00_extraction/{config.EXTRACTION_REPORT_FILE_NAME}"],
                "progress_current": 1,
                "progress_total": 1,
                "mode": "deterministic",
                "started_at": "2026-04-06T12:00:00+00:00",
                "completed_at": "2026-04-06T12:01:00+00:00",
                "updated_at": "2026-04-06T12:01:00+00:00",
                "warning_count": 0,
                "metadata": {"warnings": []},
                "resume_checkpoint": None,
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        return {
            "source_relative_path": "00_extraction/input_story.txt",
            "source_type": "txt",
            "extracted_text_relative_path": f"00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}",
            "extracted_at": "2026-04-06T12:01:00+00:00",
            "page_count": None,
            "warnings": [],
            "character_count": 10,
            "word_count": 2,
            "line_count": 1,
        }

    monkeypatch.setattr(
        text_cleanup_ui_controller.text_extraction_service,
        "extract_text",
        _fake_extract_text,
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    monkeypatch.setattr(
        text_cleanup_ui_controller,
        "start_operation",
        lambda _window, **kwargs: kwargs["success_handler"](
            kwargs["worker_callable"](
                _window._current_project_root,
                dict(_window._current_manifest),
                progress_callback=lambda *_args: None,
                cancel_requested=lambda: False,
            )
        ),
    )

    window._text_cleanup_page.extract_requested.emit()

    assert question_calls == []
    assert len(extract_calls) == 1


def test_main_window_exposes_modal_progress_dialog_and_cancel_signal(qtbot) -> None:
    """
    @brief      Verify the reusable operation-progress dialog is modal and emits cancellation.
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
    window._operation_progress_dialog = main_window_module.OperationProgressDialog(window)
    cancel_calls = []
    window._operation_progress_dialog.cancel_requested.connect(
        lambda: cancel_calls.append(True)
    )
    window._operation_progress_dialog.start("Extract Text", "Text extraction in progress...")

    assert window._operation_progress_dialog.windowModality() == main_window_module.Qt.WindowModality.ApplicationModal
    assert window._operation_progress_dialog.isVisible() is True
    cancel_button = window._operation_progress_dialog.findChild(QPushButton)
    assert cancel_button is not None
    qtbot.mouseClick(
        cancel_button,
        main_window_module.Qt.MouseButton.LeftButton,
    )

    assert cancel_calls == [True]


def test_main_window_closes_progress_dialog_after_synchronous_completion(
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify one synchronous modal operation closes the progress dialog after completion.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("SynchronousProgressProject", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("Story body", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    project_workspace_service.save_manifest(manifest, project_root)

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
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    success_payloads = []

    def _worker_callable(_project_root, _manifest, progress_callback=None, cancel_requested=None):
        progress_callback(0, 1, 0, "Starting...")
        assert cancel_requested() is False
        progress_callback(1, 1, 100, "Completed.")
        return {"status": "ok"}

    text_cleanup_ui_controller.start_operation(
        window,
        operation_kind="extraction",
        operation_name="Extract Text",
        initial_message="Text extraction in progress...",
        worker_callable=_worker_callable,
        success_handler=lambda payload: success_payloads.append(payload),
        failure_handler=lambda error: (_ for _ in ()).throw(error),
    )

    assert success_payloads == [{"status": "ok"}]
    assert window._operation_progress_dialog is None
    assert window._active_operation_kind is None


def test_main_window_runs_deterministic_cleanup_and_updates_preview(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify deterministic cleanup updates the manifest-facing UI state and cleaned preview.
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
    project_root, manifest = project_workspace_service.create_project("CleanupWindowProject", tmp_path)
    source_path = project_root / "story.pdf"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.pdf",
        "stored_relative_path": "story.pdf",
        "file_type": "pdf",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["extracted_text_relative_path"] = "00_extraction/output_raw_text.txt"
    manifest["operations"]["extraction"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    extraction_root = project_root / "00_extraction"
    extraction_root.mkdir(exist_ok=True)
    (extraction_root / "output_raw_text.txt").write_text("Chapter I\n\nParagraph one.", encoding="utf-8")

    def _fake_clean_text(*_args, progress_callback=None, cancel_requested=None, **_kwargs):
        progress_callback(1, 1, 100, "Deterministic cleanup completed.")
        cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
        cleanup_root.mkdir(exist_ok=True)
        (cleanup_root / "input_story.pdf").write_text("Chapter I\n\nParagraph one.", encoding="utf-8")
        (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text("Chapter I\n\nParagraph one.\n", encoding="utf-8")
        (cleanup_root / config.CLEANUP_REPORT_FILE_NAME).write_text(
            json.dumps({
                "input_relative_path": f"{config.CLEANUP_FOLDER_NAME}/input_story.pdf",
                "cleaned_text_relative_path": f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}",
                "cleaned_at": "2026-04-06T12:02:00+00:00",
                "detected_language": "en",
                "warnings": [],
                "paragraph_count": 2,
                "removed_line_count": 0,
                "removed_header_footer_line_count": 0,
                "removed_page_number_line_count": 0,
                "detected_chapter_count": 1,
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        (cleanup_root / "state_operation.json").write_text(
            json.dumps({
                "folder_relative_path": config.CLEANUP_FOLDER_NAME,
                "status": "completed",
                "input_paths": [f"{config.CLEANUP_FOLDER_NAME}/input_story.pdf"],
                "output_paths": [f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"],
                "artifact_paths": [f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANUP_REPORT_FILE_NAME}"],
                "progress_current": 1,
                "progress_total": 1,
                "mode": "deterministic",
                "started_at": "2026-04-06T12:00:00+00:00",
                "completed_at": "2026-04-06T12:02:00+00:00",
                "updated_at": "2026-04-06T12:02:00+00:00",
                "warning_count": 0,
                "metadata": {"warnings": []},
                "resume_checkpoint": None,
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        assert cancel_requested() is False
        return {"paragraph_count": 2}

    monkeypatch.setattr(text_cleanup_ui_controller.deterministic_cleanup_service, "clean_text", _fake_clean_text)

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    monkeypatch.setattr(
        text_cleanup_ui_controller,
        "start_operation",
        lambda _window, **kwargs: kwargs["success_handler"](
            kwargs["worker_callable"](
                _window._current_project_root,
                dict(_window._current_manifest),
                progress_callback=lambda *_args: None,
                cancel_requested=lambda: False,
            )
        ),
    )

    window._text_cleanup_page.clean_requested.emit()

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "text_chunking_ready"
    assert window._text_cleanup_page._cleaned_text_edit.toPlainText() == "Chapter I\n\nParagraph one.\n"
    assert "Cleanup produced 2 paragraphs" in window._text_cleanup_page._notes_edit.toPlainText()


def test_main_window_runs_deterministic_chunking_and_updates_preview(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify deterministic chunking updates the manifest-facing UI state and chunk preview.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
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
    project_root, manifest = project_workspace_service.create_project("ChunkWindowProject", tmp_path)
    source_path = project_root / "story.pdf"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.pdf",
        "stored_relative_path": "story.pdf",
        "file_type": "pdf",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"]
    project_workspace_service.save_manifest(manifest, project_root)
    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
    cleanup_root.mkdir(exist_ok=True)
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text("Chapter I\n\nParagraph one.\n", encoding="utf-8")

    def _fake_chunk_text(*_args, progress_callback=None, cancel_requested=None, **_kwargs):
        progress_callback(1, 1, 100, "Deterministic chunking completed.")
        chunk_root = project_root / "20_chunking"
        chunk_root.mkdir(exist_ok=True)
        (chunk_root / "input_story.pdf").write_text("Chapter I\n\nParagraph one.\n", encoding="utf-8")
        (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
            json.dumps([
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": "Chapter I",
                    "text": "Chapter I",
                    "source_start_line": 1,
                    "source_end_line": 1,
                    "chunking_mode": "deterministic",
                    "semantic_strategy": None,
                    "scene_note": None,
                },
                {
                    "chunk_id": "chunk-0002",
                    "sequence_index": 2,
                    "chapter_label": "Chapter I",
                    "text": "Paragraph one.",
                    "source_start_line": 3,
                    "source_end_line": 3,
                    "chunking_mode": "deterministic",
                    "semantic_strategy": None,
                    "scene_note": None,
                },
            ], indent=2) + "\n",
            encoding="utf-8",
        )
        (chunk_root / config.CHUNKING_REPORT_FILE_NAME).write_text(
            json.dumps({
                "input_relative_path": "20_chunking/input_story.pdf",
                "chunk_artifact_relative_path": f"20_chunking/{config.CHUNK_ARTIFACT_FILE_NAME}",
                "chunked_at": "2026-04-07T12:02:00+00:00",
                "warnings": [],
                "chunk_count": 2,
                "detected_chapter_count": 1,
                "chunking_mode": "deterministic",
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        (chunk_root / config.OPERATION_STATE_FILE_NAME).write_text(
            json.dumps({
                "folder_relative_path": "20_chunking",
                "status": "completed",
                "input_paths": ["20_chunking/input_story.pdf"],
                "output_paths": [f"20_chunking/{config.CHUNK_ARTIFACT_FILE_NAME}"],
                "artifact_paths": [f"20_chunking/{config.CHUNKING_REPORT_FILE_NAME}"],
                "progress_current": 2,
                "progress_total": 2,
                "mode": "deterministic",
                "started_at": "2026-04-07T12:00:00+00:00",
                "completed_at": "2026-04-07T12:02:00+00:00",
                "updated_at": "2026-04-07T12:02:00+00:00",
                "warning_count": 0,
                "metadata": {"warnings": [], "chunk_count": 2, "detected_chapter_count": 1},
                "resume_checkpoint": None,
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        assert cancel_requested() is False
        return {"chunk_count": 2}

    monkeypatch.setattr(text_chunking_ui_controller.deterministic_chunking_service, "chunk_text", _fake_chunk_text)

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    monkeypatch.setattr(
        text_chunking_ui_controller,
        "start_operation",
        lambda _window, **kwargs: kwargs["success_handler"](
            kwargs["worker_callable"](
                _window._current_project_root,
                dict(_window._current_manifest),
                progress_callback=lambda *_args: None,
                cancel_requested=lambda: False,
            )
        ),
    )

    window._text_chunking_page.chunk_requested.emit()

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "translation_ready"
    assert window._text_chunking_page._chunk_list.count() >= 2
    assert window._text_chunking_page._chunk_text_edit.toPlainText() == "Chapter I"
    assert "Chunking produced 2 chunks" in window._text_chunking_page._notes_edit.toPlainText()


def test_main_window_runs_ai_chunking_and_updates_preview(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify the main window wires AI-assisted chunking and refreshes the chunk preview after success.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    persisted_payload = {
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [{
            "id": "profile_1",
            "label": "Chunking Profile",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": 4096,
            "max_output_tokens": 512,
            "request_timeout_seconds": 30,
            "temperature": 0.2,
            "supports_structured_output": False,
            "enabled": True,
        }],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": "profile_1",
        "default_ai_chunking_strategy": "scene",
        "default_character_extraction_profile_id": None,
    }
    project_root, manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 4,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"
    ]
    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
    cleanup_root.mkdir(parents=True, exist_ok=True)
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "Chapter I\n\nParagraph one.\n\nParagraph two.\n",
        encoding="utf-8",
    )
    project_workspace_service.save_manifest(manifest, project_root)

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    monkeypatch.setattr(
        text_chunking_ui_controller,
        "start_operation",
        lambda _window, **kwargs: kwargs["success_handler"](
            kwargs["worker_callable"](
                _window._current_project_root,
                dict(_window._current_manifest),
                progress_callback=lambda *_args: None,
                cancel_requested=lambda: False,
            )
        ),
    )
    monkeypatch.setattr(
        text_chunking_ui_controller.ai_chunking_service,
        "chunk_text",
        lambda project_root, manifest, _profile, _strategy, progress_callback=None, cancel_requested=None: (
            deterministic_chunking_service.chunk_text(
                project_root,
                manifest,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
            | {
                "chunking_mode": "ai_assisted",
                "semantic_strategy": "scene",
            }
        ),
    )

    window._text_chunking_page.ai_chunk_requested.emit("profile_1", "scene")

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "translation_ready"
    assert window._text_chunking_page._chunk_list.count() >= 2
    assert window._text_chunking_page._ai_chunk_button.isEnabled() is True


def test_main_window_runs_ai_translation_and_updates_preview(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify the main window wires AI translation and refreshes the translated preview after success.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    persisted_payload = {
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [{
            "id": "profile_1",
            "label": "Translation Profile",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": 4096,
            "max_output_tokens": 512,
            "request_timeout_seconds": 30,
            "temperature": 0.2,
            "supports_structured_output": False,
            "enabled": True,
        }],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": None,
    }
    project_root, manifest = project_workspace_service.create_project(
        "TranslationWindowProject",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 4,
    }
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [
        f"20_chunking/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root / "20_chunking"
    chunk_root.mkdir(parents=True, exist_ok=True)
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps([
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "chapter_label": None,
                "text": "Original one",
                "source_start_line": 1,
                "source_end_line": 1,
                "chunking_mode": "deterministic",
                "semantic_strategy": None,
                "scene_note": None,
            }
        ], indent=2) + "\n",
        encoding="utf-8",
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    monkeypatch.setattr(
        ai_translation_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: ai_translation_ui_controller._sync_manifest_after_translation(
            _window,
            kwargs["worker_callable"](
                _window._current_project_root,
                dict(_window._current_manifest),
                progress_callback=lambda *_args: None,
                cancel_requested=lambda: False,
            ),
        ),
    )
    monkeypatch.setattr(
        ai_translation_ui_controller.ai_translation_service,
        "start_or_continue_translation",
        lambda project_root, _manifest, _profile, target_language, progress_callback=None, cancel_requested=None: (
            (project_root / config.TRANSLATION_FOLDER_NAME).mkdir(parents=True, exist_ok=True),
            (project_root / config.TRANSLATION_FOLDER_NAME / "input_story.json").write_text("[]\n", encoding="utf-8"),
            (project_root / config.TRANSLATION_FOLDER_NAME / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
                json.dumps([{
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "source_text": "Original one",
                    "translated_text": "Tradus unu",
                    "approved": False,
                    "approved_at": None,
                    "translated_at": "2026-04-07T12:01:00+00:00",
                    "translation_profile_id": "profile_1",
                    "target_language": target_language,
                    "status": "translated",
                }], indent=2) + "\n",
                encoding="utf-8",
            ),
            (project_root / config.TRANSLATION_FOLDER_NAME / config.TRANSLATION_REPORT_FILE_NAME).write_text(
                json.dumps({
                    "target_language": target_language,
                    "translation_profile_id_last_used": "profile_1",
                    "translation_stage_status": "completed",
                    "translated_chunk_count": 1,
                    "approved_chunk_count": 0,
                    "total_chunk_count": 1,
                    "updated_at": "2026-04-07T12:02:00+00:00",
                    "warnings": [],
                }, indent=2) + "\n",
                encoding="utf-8",
            ),
            (project_root / config.TRANSLATION_FOLDER_NAME / config.OPERATION_STATE_FILE_NAME).write_text(
                json.dumps({
                    "folder_relative_path": config.TRANSLATION_FOLDER_NAME,
                    "status": "completed",
                    "input_paths": [f"{config.TRANSLATION_FOLDER_NAME}/input_story.json"],
                    "output_paths": [f"{config.TRANSLATION_FOLDER_NAME}/{config.TRANSLATED_CHUNKS_FILE_NAME}"],
                    "artifact_paths": [f"{config.TRANSLATION_FOLDER_NAME}/{config.TRANSLATION_REPORT_FILE_NAME}"],
                    "progress_current": 1,
                    "progress_total": 1,
                    "mode": "ai_assisted",
                    "started_at": "2026-04-07T12:00:00+00:00",
                    "completed_at": "2026-04-07T12:02:00+00:00",
                    "updated_at": "2026-04-07T12:02:00+00:00",
                    "warning_count": 0,
                    "metadata": {
                        "target_language": target_language,
                        "translation_profile_id": "profile_1",
                        "translated_chunk_count": 1,
                        "approved_chunk_count": 0,
                        "total_chunk_count": 1,
                        "warnings": [],
                        "translated_chunks": [],
                        "source_chunk_count": 1,
                        "log_relative_path": None,
                    },
                    "resume_checkpoint": None,
                }, indent=2) + "\n",
                encoding="utf-8",
            ),
            {
                "target_language": target_language,
                "translation_profile_id_last_used": "profile_1",
                "translation_stage_status": "completed",
                "translated_chunk_count": 1,
                "approved_chunk_count": 0,
                "total_chunk_count": 1,
                "updated_at": "2026-04-07T12:02:00+00:00",
                "warnings": [],
            },
        )[-1],
    )

    window._ai_translation_page.start_translation_requested.emit("profile_1", "ro")
    window.show_project_state(project_root, project_workspace_service.load_manifest(project_root))

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "translation_ready"
    assert window._ai_translation_page._chunk_list.count() == 1
    assert window._ai_translation_page._translated_text_edit.toPlainText() == "Tradus unu"


def test_main_window_loads_character_discovery_state_into_characters_page(
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify the main window refreshes the Characters page from persisted discovery artifacts.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    persisted_payload = {
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [{
            "id": "profile_1",
            "label": "Character Profile",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": 4096,
            "max_output_tokens": 512,
            "request_timeout_seconds": 30,
            "temperature": 0.2,
            "supports_structured_output": False,
            "enabled": True,
        }],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": "profile_1",
    }
    project_root, manifest = project_workspace_service.create_project(
        "CharactersWindowProject",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-08T12:00:00+00:00",
        "size_bytes": 4,
    }
    manifest["current_stage"] = "character_discovery_ready"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [
        f"20_chunking/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    manifest["operations"]["character_discovery"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root / "20_chunking"
    discovery_root = project_root / "40_character_discovery"
    chunk_root.mkdir(parents=True, exist_ok=True)
    discovery_root.mkdir(parents=True, exist_ok=True)
    chunk_payload = [{
        "chunk_id": "chunk-0001",
        "sequence_index": 1,
        "chapter_label": None,
        "text": '"Hello there," said Alice.',
        "source_start_line": 1,
        "source_end_line": 1,
        "chunking_mode": "deterministic",
        "semantic_strategy": None,
        "scene_note": None,
    }]
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(chunk_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / f"input_{config.CHUNK_ARTIFACT_FILE_NAME}").write_text(
        json.dumps(chunk_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.CHARACTER_PROFILE_FILE_NAME).write_text(
        json.dumps([{
            "character_id": "alice",
            "canonical_name": "Alice",
            "aliases": ["Al"],
            "gender_hint": "",
            "age_band": "",
            "role_summary": "Lead speaker",
            "description": "Confident.",
            "temperament": "",
            "social_status": "",
            "speaking_style": "",
            "accent_or_dialect_hints": "",
            "voice_notes": "",
            "relationship_hints": [],
            "confidence": "high",
            "evidence": [{
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "source_excerpt": '"Hello there," said Alice.',
                "reason": "Alice speaks.",
            }],
            "updated_at": "2026-04-08T12:01:00+00:00",
        }], indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.CHARACTER_DISCOVERY_REPORT_FILE_NAME).write_text(
        json.dumps({
            "input_chunk_count": 1,
            "analyzed_window_count": 1,
            "merged_candidate_count": 1,
            "character_count": 1,
            "character_discovery_mode": "ai_assisted",
            "character_profile_id_last_used": "profile_1",
            "window_size": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE,
            "window_overlap": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
            "warning_count": 0,
            "warnings": [],
            "generated_at": "2026-04-08T12:01:00+00:00",
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.OPERATION_STATE_FILE_NAME).write_text(
        json.dumps({
            "folder_relative_path": "40_character_discovery",
            "status": "completed",
            "input_paths": [],
            "output_paths": [f"40_character_discovery/{config.CHARACTER_PROFILE_FILE_NAME}"],
            "artifact_paths": [f"40_character_discovery/{config.CHARACTER_DISCOVERY_REPORT_FILE_NAME}"],
            "progress_current": 1,
            "progress_total": 1,
            "mode": "ai_assisted",
            "started_at": "2026-04-08T12:00:00+00:00",
            "completed_at": "2026-04-08T12:01:00+00:00",
            "updated_at": "2026-04-08T12:01:00+00:00",
            "warning_count": 0,
            "metadata": {"ai_profile_id": "profile_1"},
            "resume_checkpoint": None,
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    assert window._characters_page._character_list.count() == 1
    assert window._characters_page._start_button.isEnabled() is False
    assert window._characters_page._reset_button.isEnabled() is True
    assert window._characters_page._evidence_preview.toPlainText() == '"Hello there," said Alice.'


def test_main_window_prevents_reimport_when_source_is_locked(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify importing again shows an error when the source is already locked.
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
    project_root, manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 4,
    }
    manifest["current_stage"] = "source_selected"
    project_workspace_service.save_manifest(manifest, project_root)
    popup_calls = []

    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "warning",
        lambda *args, **kwargs: popup_calls.append(args),
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    window._home_page.import_requested.emit()

    assert popup_calls
    assert "locked source file" in popup_calls[0][2]


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
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(project_root),
    )
    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "question",
        lambda *args, **kwargs: (
            question_calls.append(args),
            QMessageBox.StandardButton.Yes,
        )[1],
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)

    window._action_open_project.trigger()

    assert question_calls
    assert window._current_project_root == project_root
    assert window._current_manifest is not None
    assert (project_root / "40_character_discovery").is_dir()
    assert window._current_manifest["current_stage"] == "project_created"
    assert window._home_page._stage_list.item(0).text() == "Source Selected | Not Started"


# END OF FILE
