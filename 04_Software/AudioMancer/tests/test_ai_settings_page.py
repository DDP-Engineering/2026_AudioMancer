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
@version 0.1.0
"""

# IMPORTS

from audiomancer.ui.pages.ai_settings_page import AiSettingsPage


def test_ai_settings_page_loads_profiles_and_builds_merged_settings(qtbot) -> None:
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
    page = AiSettingsPage()
    qtbot.addWidget(page)

    page.load_settings({"llm_profiles": []})

    assert page._profile_list.count() == 1

    page._add_profile()
    assert page._profile_list.count() == 2

    page._remove_selected_profile()
    assert page._profile_list.count() == 1


# END OF FILE
