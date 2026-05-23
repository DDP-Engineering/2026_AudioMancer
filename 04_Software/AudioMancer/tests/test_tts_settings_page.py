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
@version 1.4.6
"""

# IMPORTS

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QStyle, QStyleOptionSpinBox

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
    @version    1.3.3
    """
    page = TtsSettingsPage()
    qtbot.addWidget(page)

    settings_payload = dict(default_settings_payload)
    settings_payload["tts_runtime_probe_succeeded"] = True
    settings_payload["tts_runtime_probe_message"] = "Connection successful. Discovered 2 models."
    settings_payload["tts_runtime_discovered_models"] = _minimum_qwen_models()
    settings_payload["tts_audio_preview_timeout_seconds"] = 75
    settings_payload["tts_audio_generation_timeout_seconds"] = 420
    settings_payload["tts_preview_text_character_limit"] = 640
    settings_payload["scene_ambience_max_blocks_per_sequence"] = 4
    settings_payload["scene_ambience_guidance_scale"] = 8.5
    settings_payload["scene_ambience_num_inference_steps"] = 80
    settings_payload["scene_ambience_seed"] = 1234

    page.load_state(
        settings_payload,
        {"voice_assignment_mode": "narrator_and_characters"},
        True,
    )

    assert page._model_list.count() == 2
    assert hasattr(page, "_voice_assignment_combo") is False
    assert page._preview_timeout_spin.value() == 75
    assert page._generation_timeout_spin.value() == 420
    assert page._preview_text_limit_spin.value() == 640
    assert page._scene_ambience_max_blocks_spin.value() == 4
    assert page._scene_ambience_guidance_spin.value() == 8.5
    assert page._scene_ambience_steps_spin.value() == 80
    assert page._scene_ambience_seed_spin.value() == 1234
    assert [page._scene_ambience_placement_combo.itemData(index) for index in range(3)] == [
        "none",
        "openers_and_closers",
        "openers_closers_and_scene_changes",
    ]
    assert page._scene_ambience_placement_combo.count() == 3
    assert page._scene_ambience_placement_combo.itemData(0) == "none"
    assert page._scene_ambience_placement_combo.currentData() == "none"
    assert page.build_tts_plan_payload() is None
    assert page.build_settings(default_settings_payload)["tts_audio_preview_timeout_seconds"] == 75
    assert page.build_settings(default_settings_payload)["tts_audio_generation_timeout_seconds"] == 420
    assert page.build_settings(default_settings_payload)["tts_preview_text_character_limit"] == 640
    assert page.build_settings(default_settings_payload)["scene_ambience_guidance_scale"] == 8.5
    assert page.build_settings(default_settings_payload)["scene_ambience_max_blocks_per_sequence"] == 4
    assert page.build_settings(default_settings_payload)["scene_ambience_num_inference_steps"] == 80
    assert page.build_settings(default_settings_payload)["scene_ambience_seed"] == 1234
    assert page.build_settings(default_settings_payload)["scene_ambience_placement"] == "none"
    assert "scene_ambience_generation_enabled" not in page.build_settings(default_settings_payload)
    assert "scene_ambience_audio_generation_enabled" not in page.build_settings(default_settings_payload)
    assert page._cancel_button.text() == "Cancel"
    assert page._save_button.text() == "Save"
    assert page._ok_button.text() == "OK"


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


def test_tts_settings_page_uses_compact_runtime_limit_controls(qtbot) -> None:
    """
    @brief      Verify numeric runtime controls do not expand across the dialog.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-20
    @version    0.2.0
    """
    page = TtsSettingsPage()
    qtbot.addWidget(page)
    page.resize(1100, 650)
    page.show()
    page.load_state({}, {}, False)
    qtbot.wait(0)

    compact_spinboxes = (
        page._preview_timeout_spin,
        page._generation_timeout_spin,
        page._preview_text_limit_spin,
        page._scene_ambience_duration_spin,
        page._scene_ambience_max_blocks_spin,
        page._scene_ambience_guidance_spin,
        page._scene_ambience_steps_spin,
        page._scene_ambience_seed_spin,
    )
    for spinbox in compact_spinboxes:
        assert spinbox.maximumWidth() <= 104
        assert spinbox.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed

    numeric_labels = (
        page._preview_timeout_label,
        page._generation_timeout_label,
        page._preview_text_limit_label,
    )
    for label in numeric_labels:
        assert label.minimumWidth() >= 200

    assert page._planning_columns_layout.spacing() >= 44
    assert page._ambience_limits_column.geometry().left() > page._numeric_limits_column.geometry().right()
    assert page._scene_ambience_placement_combo.maximumWidth() <= 420
    assert hasattr(page, "_scene_ambience_enabled_checkbox") is False
    assert hasattr(page, "_scene_ambience_audio_enabled_checkbox") is False
    assert page._ok_button.geometry().bottom() >= page.height() - 40


def test_tts_settings_page_numeric_increment_arrows_change_values(qtbot) -> None:
    """
    @brief      Verify compact TTS numeric controls use their actual arrow boxes.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-23
    @version    0.4.0
    """
    page = TtsSettingsPage()
    qtbot.addWidget(page)
    page.show()
    page.load_state({}, {}, False)
    qtbot.wait(0)

    spinboxes = (
        page._preview_timeout_spin,
        page._generation_timeout_spin,
        page._preview_text_limit_spin,
        page._scene_ambience_duration_spin,
        page._scene_ambience_max_blocks_spin,
        page._scene_ambience_guidance_spin,
        page._scene_ambience_steps_spin,
        page._scene_ambience_seed_spin,
    )
    for spinbox in spinboxes:
        old_value = spinbox.value()
        option = QStyleOptionSpinBox()
        spinbox.initStyleOption(option)
        up_button_rect = spinbox.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxUp,
            spinbox,
        )
        down_button_rect = spinbox.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxDown,
            spinbox,
        )

        qtbot.mouseClick(
            spinbox,
            Qt.MouseButton.LeftButton,
            pos=up_button_rect.center(),
        )

        assert spinbox.value() > old_value

        incremented_value = spinbox.value()
        qtbot.mouseClick(
            spinbox,
            Qt.MouseButton.LeftButton,
            pos=down_button_rect.center(),
        )

        assert spinbox.value() < incremented_value


def _minimum_qwen_models() -> list[dict[str, object]]:
    """
    @brief      Provide the minimum qwen models test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    return [
        {
            "model_id": "qwen-base",
            "backend_name": "qwen3-tts-base",
            "status": "healthy",
            "supported_generation_modes": ["base", "clone"],
        },
        {
            "model_id": "qwen-designer",
            "backend_name": "qwen3-tts-voice-designer",
            "status": "healthy",
            "supported_generation_modes": ["definition", "voice_designer"],
        },
    ]


# END OF FILE
