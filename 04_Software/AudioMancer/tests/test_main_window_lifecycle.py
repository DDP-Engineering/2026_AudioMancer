#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_main_window_lifecycle.py
@brief Qt window tests for the copied AudioMancer main-window shell.
@details Validates that the DDP_Audiomancer-style toolbar, sidebar, and stacked
         pages are created without workflow functionality.
@author Eng. Dan Dumitru Pasare
@date 2026-04-16
@version 1.4.0
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
    QStatusBar,
    QToolBar,
)

from audiomancer import config
from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import settings_ui_controller, tts_settings_ui_controller
import audiomancer.ui.main_window as main_window_module
from audiomancer.ui.main_window import MainWindow

# PUBLIC API


def test_main_window_can_be_created(qtbot, default_settings_payload) -> None:
    """
    @brief      Verify the main window can be created in a Qt test context.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.4.0
    """
    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": None,
            "default_ai_chunking_strategy": "paragraph",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)

    assert window.windowTitle() == "AudioMancer | Transform written words into real audio experience!"
    assert window.centralWidget() is not None
    assert len(window.findChildren(QToolBar)) == 1
    assert len(window.findChildren(QListWidget)) >= 2
    assert window.findChild(QStackedWidget) is not None
    assert len(window.findChildren(QDialog)) == 3
    assert any(group_box.title() == "Project Summary" for group_box in window.findChildren(QGroupBox))
    assert any(group_box.title() == "Workflow Progress" for group_box in window.findChildren(QGroupBox))
    assert any(group_box.title() == "Narrator Profiles" for group_box in window.findChildren(QGroupBox))
    assert any(group_box.title() == "Voice Designer Prompt" for group_box in window.findChildren(QGroupBox))
    assert any(button.text() == "Deterministic Cleanup" for button in window.findChildren(QPushButton))
    assert any(button.text() == "Deterministic Chunking" for button in window.findChildren(QPushButton))
    assert any(button.text() == "Start Translation" for button in window.findChildren(QPushButton))
    assert any(button.text() == "Start Discovery" for button in window.findChildren(QPushButton))
    assert any(button.text() == "Preview" for button in window.findChildren(QPushButton))
    assert any(button.text() == "Delete Profile" for button in window.findChildren(QPushButton))
    assert any(button.text() == "Save AI Settings" for button in window.findChildren(QPushButton))
    assert any(button.text() == "Save TTS Settings" for button in window.findChildren(QPushButton))
    assert any(button.text() == "Connect" for button in window.findChildren(QPushButton))
    assert any(button.text() == "Test Connection" for button in window.findChildren(QPushButton))
    assert any(button.text() == "Save Settings" for button in window.findChildren(QPushButton))
    assert any(label.text() == "Interface Text Size" for label in window.findChildren(QLabel))
    assert window._sidebar.item(1).flags() == main_window_module.Qt.ItemFlag.NoItemFlags
    assert window._operation_progress_dialog is None
    assert window._status_bar is None


def test_main_window_show_message_does_not_create_status_bar(qtbot, default_settings_payload) -> None:
    """
    @brief      Verify transient shell messages do not recreate a bottom status bar.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": None,
            "default_ai_chunking_strategy": "paragraph",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)

    window.show_message("Transient shell message")

    assert window._status_bar is None
    assert not window.findChildren(QStatusBar)


def test_about_dialog_includes_license_text(qtbot, default_settings_payload) -> None:
    """
    @brief      Verify the About dialog exposes both license texts.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": None,
            "default_ai_chunking_strategy": "paragraph",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)

    dialog = window._build_about_dialog()
    text_box = dialog.findChild(QPlainTextEdit, "aboutLicenseTextBox")

    assert dialog.windowTitle() == "About"
    assert dialog.width() == 510
    assert text_box is not None
    assert any(
        label.text() == "Transform written words into real audio experience!" for label in dialog.findChildren(QLabel)
    )
    assert any(label.text() == "Version: 0.16.1" for label in dialog.findChildren(QLabel))
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in text_box.toPlainText()
    assert "Additional Non-Commercial Restriction" in text_box.toPlainText()


def test_about_dialog_loads_translated_license_text_for_romanian(qtbot, default_settings_payload) -> None:
    """
    @brief      Verify the About dialog loads the Romanian license companion files.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    window = MainWindow(
        settings_payload={
            "language": "ro",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": None,
            "default_ai_chunking_strategy": "paragraph",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)

    dialog = window._build_about_dialog()
    text_box = dialog.findChild(QPlainTextEdit, "aboutLicenseTextBox")

    assert dialog.windowTitle() == "Despre"
    assert text_box is not None
    assert any(label.text() == "Versiune: 0.16.1" for label in dialog.findChildren(QLabel))
    assert "LICENTA PUBLICA GENERALA AFFERO GNU" in text_box.toPlainText()
    assert "RESTRICTIE SUPLIMENTARA DE UTILIZARE NECOMERCIALA" in text_box.toPlainText()


def test_main_window_saves_settings_dialog_payload(monkeypatch, qtbot, default_settings_payload) -> None:
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
    persisted_payload = dict(default_settings_payload)
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
    assert window.windowTitle() == ("AudioMancer | Transforma cuvintele scrise intr-o experienta audio reala!")
    assert window._action_settings.text() == "Setari"
    assert window._action_tts_settings.text() == "Setari TTS"
    assert window._sidebar.item(0).text() == "Acasa / Proiect"
    assert window._settings_page._save_button.text() == "Salveaza Setarile"
    assert QApplication.instance().font().pointSizeF() > starting_font_size


def test_main_window_reloads_dialogs_and_discards_unsaved_changes(monkeypatch, qtbot, default_settings_payload) -> None:
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

    monkeypatch.setattr(
        settings_ui_controller.settings_service,
        "load_settings",
        lambda: dict(default_settings_payload),
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
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

    window.show_tts_settings_dialog()
    window._tts_settings_page._base_url_edit.setText("http://changed-runtime")
    window._tts_settings_page._cancel_button.click()
    window.show_tts_settings_dialog()
    assert window._tts_settings_page._base_url_edit.text() == default_settings_payload["tts_runtime_base_url"]


def test_main_window_saves_tts_settings_dialog_payload(monkeypatch, qtbot, tmp_path, default_settings_payload) -> None:
    """
    @brief      Verify saving TTS Settings persists runtime settings and the project-local TTS plan.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("TtsSaveProject", tmp_path)
    persisted_payload = dict(default_settings_payload)
    saved_payloads = []
    saved_tts_plans = []

    def _fake_load_settings():
        return dict(persisted_payload)

    def _fake_save_settings(payload):
        saved_payloads.append(dict(payload))
        persisted_payload.update(payload)

    monkeypatch.setattr(tts_settings_ui_controller.settings_service, "load_settings", _fake_load_settings)
    monkeypatch.setattr(tts_settings_ui_controller.settings_service, "save_settings", _fake_save_settings)
    monkeypatch.setattr(
        tts_settings_ui_controller.narrator_definition_service,
        "save_tts_plan",
        lambda project_root_path, plan_payload, discovered_models=None: (
            saved_tts_plans.append((project_root_path, dict(plan_payload), list(discovered_models or []))),
            dict(plan_payload),
        )[-1],
    )

    window = MainWindow(settings_payload=dict(persisted_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, manifest)

    window.show_tts_settings_dialog()
    window._tts_settings_page._base_url_edit.setText("http://127.0.0.1:9000")
    window._tts_settings_page.apply_probe_result(
        {
            "success": True,
            "message": "Connection successful. Discovered 1 models.",
            "discovered_models": [
                {
                    "model_id": "custom_model",
                    "status": "healthy",
                    "supported_generation_modes": ["custom_voice"],
                    "supported_presets": ["vivian"],
                    "speaker_count": 1,
                }
            ],
            "active_model_id": None,
            "device_diagnostics": {},
        }
    )
    window._tts_settings_page._save_button.click()

    assert saved_payloads
    assert persisted_payload["tts_runtime_base_url"] == "http://127.0.0.1:9000"
    assert persisted_payload["tts_runtime_probe_succeeded"] is True
    assert saved_tts_plans
    assert saved_tts_plans[0][0] == project_root
    assert saved_tts_plans[0][1]["voice_assignment_mode"] == config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE


def test_settings_dialog_reopens_with_translated_labels(monkeypatch, qtbot, default_settings_payload) -> None:
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
    persisted_payload = dict(default_settings_payload)
    persisted_payload["language"] = "ro"

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


# END OF FILE
