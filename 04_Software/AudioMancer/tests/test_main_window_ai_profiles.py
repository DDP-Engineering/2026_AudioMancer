#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_main_window_ai_profiles.py
@brief Qt window tests for the copied AudioMancer main-window shell.
@details Validates that the DDP_Audiomancer-style toolbar, sidebar, and stacked
         pages are created without workflow functionality.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 1.3.0
"""

# IMPORTS

from audiomancer.ui.controllers import ai_settings_ui_controller
from audiomancer.ui.main_window import MainWindow

# PUBLIC API


def test_main_window_connect_ai_profile_shows_success_popup(monkeypatch, qtbot, default_settings_payload) -> None:
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

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)

    window.show_ai_settings_dialog()
    window._ai_settings_page._connect_button.click()

    assert popup_calls
    assert "Connection successful." in popup_calls[0][2]
    assert "Discovered models: 2" in popup_calls[0][2]


def test_main_window_connect_ai_profile_shows_failure_popup(monkeypatch, qtbot, default_settings_payload) -> None:
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

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)

    window.show_ai_settings_dialog()
    window._ai_settings_page._connect_button.click()

    assert popup_calls
    assert popup_calls[0][2] == ("Connection failed.\nConnection failed: request timed out.")
