#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_settings_page.py
@brief Focused tests for the AudioMancer AI settings page.
@details Verifies AI settings-page loading, profile editing, profile mutation,
         and merged settings payload generation.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.2.2
"""

# IMPORTS

from audiomancer.services.ai_backend_service import ModelDescriptor, ProviderProbeResult
from audiomancer.ui.pages.ai_settings_page import AiSettingsPage


def test_ai_settings_page_loads_profiles_and_builds_merged_settings(qtbot) -> None:
    """
    @brief      Verify AI settings load into widgets and rebuild merged state.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)

    settings_payload = {
        "language": "en",
        "llm_profiles": [
            {
                "id": "profile_a",
                "label": "Profile A",
                "backend_kind": "ollama",
                "base_url": "http://localhost:11434/v1",
                "api_key": "secret",
                "model_name": "qwen3-8b",
                "context_window": 16384,
                "max_output_tokens": 2048,
                "request_timeout_seconds": 120,
                "temperature": 0.45,
                "supports_structured_output": True,
                "enabled": True,
            }
        ],
        "default_ai_cleanup_profile_id": "profile_a",
        "default_ai_chunking_profile_id": "profile_a",
        "default_ai_chunking_strategy": "scene",
        "default_character_extraction_profile_id": "profile_a",
        "ui_text_scale": "normal",
    }

    page.load_settings(settings_payload)

    assert page._profile_list.count() == 1
    assert page._label_edit.text() == "Profile A"
    assert page._backend_combo.currentText() == "ollama"
    assert page._default_cleanup_combo.currentData() == "profile_a"
    assert page._default_strategy_combo.currentData() == "scene"

    page._label_edit.setText("Profile A Updated")
    page._base_url_edit.setText("http://127.0.0.1:1234/v1")
    page._default_strategy_combo.setCurrentIndex(
        page._default_strategy_combo.findData("meaning")
    )

    rebuilt = page.build_settings({"language": "en"})

    assert rebuilt["llm_profiles"][0]["label"] == "Profile A Updated"
    assert rebuilt["llm_profiles"][0]["base_url"] == "http://127.0.0.1:1234/v1"
    assert rebuilt["default_ai_chunking_strategy"] == "meaning"
    assert rebuilt["default_ai_cleanup_profile_id"] == "profile_a"


def test_ai_settings_page_adds_and_removes_profiles(qtbot) -> None:
    """
    @brief      Verify the page can add and remove in-memory profiles.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)

    page.load_settings({"llm_profiles": []})

    assert page._profile_list.count() == 1

    page._add_profile()
    assert page._profile_list.count() == 2

    page._remove_selected_profile()
    assert page._profile_list.count() == 1


def test_ai_settings_page_applies_probe_result_and_updates_status(qtbot) -> None:
    """
    @brief      Verify probe results refresh discovered model options.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)

    page.load_settings({
        "language": "en",
        "llm_profiles": [{
            "id": "profile_a",
            "label": "Profile A",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234/v1",
            "api_key": "",
            "model_name": "missing-model",
            "context_window": 8192,
            "max_output_tokens": 1024,
            "request_timeout_seconds": 90,
            "temperature": 0.2,
            "supports_structured_output": True,
            "enabled": True,
        }],
    })

    page.apply_probe_result(ProviderProbeResult(
        success=True,
        message="Connection successful. Discovered 2 models.",
        discovered_models=[
            ModelDescriptor(id="qwen3-8b", label="qwen3-8b"),
            ModelDescriptor(id="llama-3.1-8b", label="llama-3.1-8b"),
        ],
        discovered_model_count=2,
        discovered_context_window=None,
        selected_model_valid=False,
    ))

    assert page._model_combo.count() == 2
    assert page._model_combo.currentText() == "qwen3-8b"


def test_ai_settings_page_marks_manual_overrides(qtbot) -> None:
    """
    @brief      Verify manual editor changes set the override flags.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)

    page.load_settings({
        "llm_profiles": [{
            "id": "profile_a",
            "label": "Profile A",
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
    })

    page._model_combo.setCurrentText("custom-model")
    page._context_window_spin.setValue(4096)

    profile_payload = page.build_current_profile_payload()

    assert profile_payload is not None
    assert profile_payload["user_overrode_model_name"] is True
    assert profile_payload["user_overrode_context_window"] is True


# END OF FILE
