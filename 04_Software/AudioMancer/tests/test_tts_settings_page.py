#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_tts_settings_page.py
@brief Focused tests for the AudioMancer TTS settings page.
@details Verifies the simplified runtime layout, connection-status labeling,
         discovered-model rendering, and runtime limit persistence.
@author Eng. Dan Dumitru Pasare
@date 2026-04-17
@version 1.2.0
"""

# IMPORTS

from audiomancer import config
from audiomancer.ui.pages.tts_settings_page import TtsSettingsPage


def test_tts_settings_page_loads_runtime_limits_without_project_plan(qtbot, default_settings_payload) -> None:
    """
    @brief      Verify the page loads persisted runtime settings without exposing project voice assignment.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  default_settings_payload Shared default settings fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.2.0
    """
    page = TtsSettingsPage()
    qtbot.addWidget(page)

    settings_payload = dict(default_settings_payload)
    settings_payload["tts_runtime_probe_succeeded"] = True
    settings_payload["tts_runtime_probe_message"] = "Connection successful. Discovered 3 models."
    settings_payload["tts_runtime_discovered_models"] = _minimum_qwen_models()
    settings_payload["tts_audio_preview_timeout_seconds"] = 75
    settings_payload["tts_audio_generation_timeout_seconds"] = 420
    settings_payload["tts_preview_text_character_limit"] = 640

    page.load_state(
        settings_payload,
        {"voice_assignment_mode": "narrator_and_characters"},
        True,
    )

    assert page._model_list.count() == 3
    assert hasattr(page, "_voice_assignment_combo") is False
    assert page._preview_timeout_spin.value() == 75
    assert page._generation_timeout_spin.value() == 420
    assert page._preview_text_limit_spin.value() == 640
    assert page.build_tts_plan_payload() is None
    assert page.build_settings(default_settings_payload)["tts_audio_preview_timeout_seconds"] == 75
    assert page.build_settings(default_settings_payload)["tts_audio_generation_timeout_seconds"] == 420
    assert page.build_settings(default_settings_payload)["tts_preview_text_character_limit"] == 640


def test_tts_settings_page_exposes_simple_connection_status_states(qtbot) -> None:
    """
    @brief      Verify the runtime status label uses the simplified not connected / connected / failed states.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    page = TtsSettingsPage()
    qtbot.addWidget(page)
    page.load_state({}, {}, True)
    assert page._runtime_status_label.text() == "Not connected"

    page.apply_probe_result(
        {
            "success": True,
            "message": "Connection successful.",
            "discovered_models": _minimum_qwen_models(),
            "active_model_id": None,
            "device_diagnostics": {},
        }
    )
    assert page._runtime_status_label.text() == "Connected"

    page.apply_probe_result(
        {
            "success": False,
            "message": "Connection failed: timed out.",
            "discovered_models": [],
            "active_model_id": None,
            "device_diagnostics": {},
        }
    )
    assert page._runtime_status_label.text() == "Connection failed"


def test_tts_settings_page_removed_old_model_role_controls(qtbot) -> None:
    """
    @brief      Verify the old preferred-mechanism and per-role model selectors are no longer present.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.0.0
    """
    page = TtsSettingsPage()
    qtbot.addWidget(page)

    assert hasattr(page, "_preferred_mechanism_combo") is False
    assert hasattr(page, "_custom_voice_model_combo") is False
    assert hasattr(page, "_definition_model_combo") is False
    assert hasattr(page, "_clone_model_combo") is False
    assert page._preview_timeout_spin.value() == config.DEFAULT_TTS_AUDIO_PREVIEW_TIMEOUT_SECONDS
    assert page._generation_timeout_spin.value() == config.DEFAULT_TTS_AUDIO_GENERATION_TIMEOUT_SECONDS
    assert page._preview_text_limit_spin.value() == config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT
    assert page._model_list.maximumHeight() == 148


def test_tts_settings_page_omits_redundant_title_label(qtbot) -> None:
    """
    @brief      Verify the dialog body does not repeat the window title.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    page = TtsSettingsPage()
    qtbot.addWidget(page)

    assert hasattr(page, "_title_label") is False


def test_tts_settings_page_keeps_runtime_limits_available_without_project(qtbot) -> None:
    """
    @brief      Verify runtime audio limits remain editable when no project is open.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    page = TtsSettingsPage()
    qtbot.addWidget(page)

    page.load_state({}, {}, False)

    assert page._planning_group.isEnabled() is True
    assert hasattr(page, "_voice_assignment_combo") is False
    assert page.build_tts_plan_payload() is None


def _minimum_qwen_models() -> list[dict[str, object]]:
    return [
        {
            "model_id": "qwen-base",
            "backend_name": "qwen3-tts-base",
            "status": "healthy",
            "supported_generation_modes": ["base", "clone"],
            "supported_presets": [],
            "speaker_count": 0,
        },
        {
            "model_id": "qwen-designer",
            "backend_name": "qwen3-tts-voice-designer",
            "status": "healthy",
            "supported_generation_modes": ["definition", "voice_designer"],
            "supported_presets": [],
            "speaker_count": 0,
        },
        {
            "model_id": "qwen-custom",
            "backend_name": "qwen3-tts-customvoice",
            "status": "healthy",
            "supported_generation_modes": ["custom_voice"],
            "supported_presets": ["vivian", "serena", "anna"],
            "speaker_count": 3,
        },
    ]


# END OF FILE
