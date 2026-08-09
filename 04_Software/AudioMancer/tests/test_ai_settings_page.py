#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
"""

# IMPORTS

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QFormLayout, QGridLayout

from audiomancer import config
from audiomancer.services import settings_service
from audiomancer.ui.pages.ai_settings_page import AiSettingsPage


def _test_profile(profile_id: str, label: str, **overrides: object) -> dict[str, object]:
    """
    @brief      Build one complete AI profile payload for focused page tests.
    @param[in]  profile_id Stable profile identifier.
    @param[in]  label Operator-facing profile label.
    @param[in]  overrides Field values to replace in the default test payload.
    @return     Complete profile dictionary.
    @exception  None
    """
    profile: dict[str, object] = {
        "id": profile_id,
        "label": label,
        "backend_kind": "lmstudio",
        "base_url": f"http://127.0.0.1:1234/{profile_id}/v1",
        "api_key": f"key-{profile_id}",
        "model_name": f"model-{profile_id}",
        "context_window": 8192,
        "max_output_tokens": 1024,
        "request_timeout_seconds": 90,
        "temperature": 0.2,
        "supports_structured_output": False,
        "enabled": True,
    }
    profile.update(overrides)
    return profile


def test_ai_settings_page_default_selectors_are_stacked_in_workflow_order(qtbot) -> None:
    """
    @brief      Verify default AI selector rows match the operator workflow.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)

    editor_container = page._default_cleanup_combo.parentWidget()
    editor_layout = editor_container.layout()
    form_layout = editor_layout.itemAt(1).layout()

    assert isinstance(form_layout, QFormLayout)

    row_labels = []
    for row in range(form_layout.rowCount()):
        label_item = form_layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
        if label_item is not None:
            row_labels.append(label_item.widget())
    default_label_order = [
        label.text()
        for label in row_labels
        if label
        in (
            page._default_cleanup_label,
            page._default_chunking_label,
            page._default_strategy_label,
            page._default_translation_label,
            page._default_narrator_generation_label,
            page._default_character_label,
            page._default_speech_blocks_label,
        )
    ]

    assert default_label_order == [
        "Default Cleanup Profile",
        "Default Chunking Profile",
        "Default AI Chunking Strategy",
        "Default Translation Profile",
        "Default Narator Generation Profile",
        "Default Character Extraction Profile",
        "Default Speech Blocks Profile",
    ]
    assert page._cancel_button.text() == "Cancel"
    assert page._save_button.text() == "Apply"
    assert page._ok_button.text() == "OK"
    page.apply_language("ro")
    assert page._save_button.text() == "Aplica"


def test_ai_settings_page_numeric_profile_options_use_two_column_grid(qtbot) -> None:
    """
    @brief      Verify compact numeric AI profile options are arranged in two columns.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)

    editor_container = page._default_cleanup_combo.parentWidget()
    editor_layout = editor_container.layout()
    form_layout = editor_layout.itemAt(1).layout()
    numeric_layout = None
    for index in range(form_layout.count()):
        candidate = form_layout.itemAt(index)
        if candidate is not None and isinstance(candidate.layout(), QGridLayout):
            numeric_layout = candidate.layout()
            break

    assert numeric_layout is not None
    assert numeric_layout.itemAtPosition(0, 0).widget() is page._context_window_label
    assert numeric_layout.itemAtPosition(0, 1).widget() is page._context_window_spin
    assert numeric_layout.itemAtPosition(0, 2).widget() is page._max_output_label
    assert numeric_layout.itemAtPosition(0, 3).widget() is page._max_output_spin
    assert numeric_layout.itemAtPosition(1, 0).widget() is page._timeout_label
    assert numeric_layout.itemAtPosition(1, 1).widget() is page._timeout_spin
    assert numeric_layout.itemAtPosition(1, 2).widget() is page._temperature_label
    assert numeric_layout.itemAtPosition(1, 3).widget() is page._temperature_spin


def test_ai_settings_page_structured_output_is_in_model_name_row(qtbot) -> None:
    """
    @brief      Verify the structured-output checkbox shares the model-name row.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)

    editor_container = page._default_cleanup_combo.parentWidget()
    editor_layout = editor_container.layout()
    form_layout = editor_layout.itemAt(0).layout()
    model_row_layout = None
    for row in range(form_layout.rowCount()):
        label_item = form_layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
        field_item = form_layout.itemAt(row, QFormLayout.ItemRole.FieldRole)
        if label_item is not None and label_item.widget() is page._model_name_label:
            model_row_layout = field_item.layout() if field_item is not None else None
            break

    assert model_row_layout is not None
    assert model_row_layout.itemAt(0).widget() is page._model_combo
    assert model_row_layout.itemAt(1).widget() is page._supports_structured_checkbox
    assert page._supports_structured_checkbox.text() == "Structured output"


def test_ai_settings_page_loads_profiles_and_builds_merged_settings(qtbot) -> None:
    """
    @brief      Verify AI settings load into widgets and rebuild merged state.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
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
        "default_ai_translation_profile_id": "profile_a",
        "default_narrator_profile_generation_profile_id": "profile_a",
        "default_speech_blocks_profile_id": "profile_a",
        "default_ai_chunking_strategy": "scene",
        "default_character_extraction_profile_id": "profile_a",
    }

    page.load_settings(settings_payload)

    assert page._profile_list.count() == 1
    assert page._label_edit.text() == "Profile A"
    assert page._backend_combo.currentText() == "ollama"
    assert page._default_cleanup_combo.currentData() == "profile_a"
    assert page._default_translation_combo.currentData() == "profile_a"
    assert page._default_narrator_generation_combo.currentData() == "profile_a"
    assert page._default_speech_blocks_combo.currentData() == "profile_a"
    assert page._default_strategy_combo.currentData() == "scene"

    page._label_edit.setText("Profile A Updated")
    page._base_url_edit.setText("http://127.0.0.1:1234/v1")
    page._default_strategy_combo.setCurrentIndex(page._default_strategy_combo.findData("meaning"))

    rebuilt = page.build_settings({"language": "en"})

    assert rebuilt["llm_profiles"][0]["label"] == "Profile A Updated"
    assert rebuilt["llm_profiles"][0]["base_url"] == "http://127.0.0.1:1234/v1"
    assert rebuilt["default_ai_chunking_strategy"] == "meaning"
    assert rebuilt["default_ai_cleanup_profile_id"] == "profile_a"
    assert rebuilt["default_ai_translation_profile_id"] == "profile_a"
    assert rebuilt["default_narrator_profile_generation_profile_id"] == "profile_a"
    assert rebuilt["default_speech_blocks_profile_id"] == "profile_a"


def test_ai_settings_page_timeout_accepts_65535_seconds(qtbot) -> None:
    """
    @brief      Verify S-0001 and REQ-UX-035 preserve the overnight AI timeout cap.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)

    page.load_settings(
        {
            "language": "en",
            "llm_profiles": [
                {
                    "id": "profile_a",
                    "label": "Profile A",
                    "backend_kind": "lmstudio",
                    "base_url": "http://127.0.0.1:1234/v1",
                    "api_key": "",
                    "model_name": "qwen3-8b",
                    "context_window": 16384,
                    "max_output_tokens": 8192,
                    "request_timeout_seconds": 65535,
                    "temperature": 0.2,
                    "supports_structured_output": True,
                    "enabled": True,
                }
            ],
        }
    )

    assert page._timeout_spin.maximum() == 65535
    assert page._timeout_spin.value() == 65535

    rebuilt = page.build_settings({"language": "en"})

    assert rebuilt["llm_profiles"][0]["request_timeout_seconds"] == 65535


def test_ai_settings_page_loads_and_builds_chunking_context_mode(qtbot) -> None:
    """
    @brief      Verify S-0001 and REQ-UX-034 persist the AI chunking context mode selector.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)

    page.load_settings(
        {
            "language": "en",
            "llm_profiles": [],
            "default_ai_chunking_strategy": "scene",
            "default_ai_chunking_context_mode": config.AI_CHUNKING_CONTEXT_MODE_WIDE_SCENE,
        }
    )

    assert page._default_context_mode_label.text() == "Chunking Context Mode"
    assert page._default_context_mode_combo.currentData() == config.AI_CHUNKING_CONTEXT_MODE_WIDE_SCENE

    page._default_context_mode_combo.setCurrentIndex(
        page._default_context_mode_combo.findData(config.AI_CHUNKING_CONTEXT_MODE_MAXIMUM)
    )
    rebuilt = page.build_settings({"language": "en"})

    assert rebuilt["default_ai_chunking_context_mode"] == config.AI_CHUNKING_CONTEXT_MODE_MAXIMUM


def test_ai_settings_page_adds_and_removes_profiles(qtbot) -> None:
    """
    @brief      Verify the page can add and remove in-memory profiles.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)

    page.load_settings({"llm_profiles": []})

    assert page._profile_list.count() == 1

    page._add_profile()
    assert page._profile_list.count() == 2

    page._remove_selected_profile()
    assert page._profile_list.count() == 1


def test_switching_profiles_preserves_outgoing_editor_values(qtbot) -> None:
    """
    @brief      Verify selection changes retain every field owned by the outgoing profile.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)
    profile_a = _test_profile("profile-a", "Profile A", enabled=False)
    profile_b = _test_profile("profile-b", "Profile B", backend_kind="ollama")
    page.load_settings(
        {
            "llm_profiles": [profile_a, profile_b],
            "default_ai_cleanup_profile_id": "profile-a",
        }
    )

    expected_a = {
        "id": "profile-a",
        "label": "Profile A edited",
        "enabled": True,
        "backend_kind": "openai_compatible",
        "base_url": "https://example.test/v1",
        "api_key": "edited-secret",
        "model_name": "edited-model",
        "context_window": 65536,
        "max_output_tokens": 4096,
        "request_timeout_seconds": 321,
        "temperature": 0.75,
        "supports_structured_output": True,
    }
    page._label_edit.setText(str(expected_a["label"]))
    page._enabled_checkbox.setChecked(bool(expected_a["enabled"]))
    page._backend_combo.setCurrentText(str(expected_a["backend_kind"]))
    page._base_url_edit.setText(str(expected_a["base_url"]))
    page._api_key_edit.setText(str(expected_a["api_key"]))
    page._model_combo.setCurrentText(str(expected_a["model_name"]))
    page._context_window_spin.setValue(int(expected_a["context_window"]))
    page._max_output_spin.setValue(int(expected_a["max_output_tokens"]))
    page._timeout_spin.setValue(int(expected_a["request_timeout_seconds"]))
    page._temperature_spin.setValue(float(expected_a["temperature"]))
    page._supports_structured_checkbox.setChecked(bool(expected_a["supports_structured_output"]))

    page._profile_list.setCurrentRow(1)
    connect_payload = page.build_current_profile_payload()
    assert connect_payload is not None
    assert connect_payload["id"] == "profile-b"
    assert connect_payload["base_url"] == profile_b["base_url"]

    page._profile_list.setCurrentRow(0)
    assert page._label_edit.text() == expected_a["label"]
    assert page._enabled_checkbox.isChecked() is expected_a["enabled"]
    assert page._backend_combo.currentText() == expected_a["backend_kind"]
    assert page._base_url_edit.text() == expected_a["base_url"]
    assert page._api_key_edit.text() == expected_a["api_key"]
    assert page._model_combo.currentText() == expected_a["model_name"]
    assert page._context_window_spin.value() == expected_a["context_window"]
    assert page._max_output_spin.value() == expected_a["max_output_tokens"]
    assert page._timeout_spin.value() == expected_a["request_timeout_seconds"]
    assert page._temperature_spin.value() == expected_a["temperature"]
    assert page._supports_structured_checkbox.isChecked() is expected_a["supports_structured_output"]

    page._profile_list.setCurrentRow(1)
    page._profile_list.setCurrentRow(0)
    saved_profiles = page.build_settings({})["llm_profiles"]
    saved_a = saved_profiles[0]
    saved_b = saved_profiles[1]
    assert {key: saved_a[key] for key in expected_a} == expected_a
    assert {key: saved_b[key] for key in profile_b} == profile_b
    assert page._profile_list.item(0).text() == "Profile A edited"
    cleanup_index = page._default_cleanup_combo.findData("profile-a")
    assert page._default_cleanup_combo.itemText(cleanup_index) == "Profile A edited"


def test_profile_add_remove_operations_do_not_redirect_editor_values(qtbot) -> None:
    """
    @brief      Verify list mutations never copy one profile editor into another profile.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)
    profile_a = _test_profile("profile-a", "Profile A")
    profile_b = _test_profile("profile-b", "Profile B")
    page.load_settings({"llm_profiles": [profile_a, profile_b]})

    page._label_edit.setText("Profile A edited")
    page._add_profile()
    assert page._profiles[0]["label"] == "Profile A edited"
    added_id = str(page._profiles[2]["id"])
    assert added_id not in {"profile-a", "profile-b"}

    page._profile_list.setCurrentRow(1)
    page._label_edit.setText("Profile B transient edit")
    page._remove_selected_profile()
    saved_profiles = page.build_settings({})["llm_profiles"]
    assert [profile["id"] for profile in saved_profiles] == ["profile-a", added_id]
    assert saved_profiles[0]["label"] == "Profile A edited"
    assert saved_profiles[1]["label"] != "Profile B transient edit"


def test_ai_settings_page_applies_probe_result_and_updates_status(qtbot) -> None:
    """
    @brief      Verify probe results refresh discovered model options.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)

    page.load_settings(
        {
            "language": "en",
            "llm_profiles": [
                {
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
                }
            ],
        }
    )

    page.apply_probe_result(
        {
            "success": True,
            "message": "Connection successful. Discovered 2 models.",
            "discovered_models": [
                {"id": "qwen3-8b", "label": "qwen3-8b"},
                {"id": "llama-3.1-8b", "label": "llama-3.1-8b"},
            ],
            "discovered_model_count": 2,
            "discovered_context_window": None,
            "selected_model_valid": False,
        }
    )

    assert page._model_combo.count() == 2
    assert page._model_combo.currentText() == "qwen3-8b"


def test_ai_settings_page_marks_manual_overrides(qtbot) -> None:
    """
    @brief      Verify manual editor changes set the override flags.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)

    page.load_settings(
        {
            "llm_profiles": [
                {
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
                }
            ],
        }
    )

    page._model_combo.setCurrentText("custom-model")
    page._context_window_spin.setValue(4096)

    profile_payload = page.build_current_profile_payload()

    assert profile_payload is not None
    assert profile_payload["user_overrode_model_name"] is True
    assert profile_payload["user_overrode_context_window"] is True


def test_failed_probe_preserves_successful_discovery_after_round_trip(qtbot) -> None:
    """
    @brief      Verify a failed probe retains profile-local successful discovery metadata.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)
    page.load_settings(
        {
            "llm_profiles": [
                _test_profile("profile-a", "Profile A", model_name="model-a"),
                _test_profile(
                    "profile-b",
                    "Profile B",
                    discovered_model_names=["model-b"],
                    discovered_model_name="model-b",
                    discovered_context_window=32768,
                    discovered_context_model_name="model-b",
                ),
            ]
        }
    )
    successful_result = {
        "success": True,
        "message": "Connection successful.",
        "discovered_models": [
            {"id": "model-a", "label": "model-a"},
            {"id": "model-a-alt", "label": "model-a-alt"},
        ],
        "selected_model_valid": True,
        "discovered_context_window": 65536,
        "discovered_context_model_name": "model-a",
    }
    page.apply_probe_result(successful_result)
    page._model_combo.setCurrentText("typed-model-a")
    page._context_window_spin.setValue(24576)
    assert page.build_current_profile_payload() is not None

    page.apply_probe_result(
        {
            "success": False,
            "message": "Connection failed: transport error.",
            "discovered_models": [],
            "selected_model_valid": False,
            "discovered_context_window": None,
            "discovered_context_model_name": None,
        }
    )
    saved = settings_service.validate_settings(page.build_settings({}))
    reloaded_page = AiSettingsPage()
    qtbot.addWidget(reloaded_page)
    reloaded_page.load_settings(saved)

    profile_a = reloaded_page._profiles[0]
    assert profile_a["discovery_succeeded"] is False
    assert profile_a["discovery_message"] == "Connection failed: transport error."
    assert profile_a["discovered_model_names"] == ["model-a", "model-a-alt"]
    assert profile_a["discovered_model_name"] == "model-a"
    assert profile_a["discovered_context_window"] == 65536
    assert profile_a["discovered_context_model_name"] == "model-a"
    assert profile_a["model_name"] == "typed-model-a"
    assert profile_a["context_window"] == 24576
    assert [
        reloaded_page._model_combo.itemText(index)
        for index in range(reloaded_page._model_combo.count())
    ] == ["model-a", "model-a-alt"]
    assert reloaded_page._profiles[1]["discovered_model_names"] == ["model-b"]
    assert reloaded_page._profiles[1]["discovered_context_window"] == 32768


def test_context_discovery_autofills_then_preserves_manual_override(qtbot) -> None:
    """
    @brief      Verify exact-model context auto-fill does not replace a later manual value.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)
    page.load_settings(
        {"llm_profiles": [_test_profile("profile-a", "Profile A", model_name="model-a")]}
    )
    base_result = {
        "success": True,
        "message": "Connection successful.",
        "discovered_models": [{"id": "model-a", "label": "model-a"}],
        "selected_model_valid": True,
        "discovered_context_window": 65536,
        "discovered_context_model_name": "model-a",
    }

    mismatched_result = dict(base_result)
    mismatched_result["discovered_context_window"] = 99999
    mismatched_result["discovered_context_model_name"] = "model-b"
    page.apply_probe_result(mismatched_result)
    assert page._context_window_spin.value() == 8192

    page.apply_probe_result(base_result)
    auto_filled = page.build_current_profile_payload()
    assert auto_filled is not None
    assert auto_filled["context_window"] == 65536
    assert auto_filled["user_overrode_context_window"] is False

    page._context_window_spin.setValue(32768)
    assert page.build_current_profile_payload() is not None
    later_result = dict(base_result)
    later_result["discovered_context_window"] = 131072
    page.apply_probe_result(later_result)
    saved = settings_service.validate_settings(page.build_settings({}))

    assert saved["llm_profiles"][0]["context_window"] == 32768
    assert saved["llm_profiles"][0]["user_overrode_context_window"] is True
    assert saved["llm_profiles"][0]["discovered_context_window"] == 131072
    assert saved["llm_profiles"][0]["discovered_context_model_name"] == "model-a"


# END OF FILE


def test_model_selector_keeps_discovered_models_across_a_settings_round_trip(qtbot) -> None:
    """
    @brief      Verify probed endpoint models are still offered after settings are saved and reloaded.
    @details    The discovered list used to live only in memory, so a relaunched app showed three
                built-in placeholder names the endpoint may not serve while hiding the real ones.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)
    page.load_settings(
        {
            "llm_profiles": [
                {
                    "id": "profile-1",
                    "label": "Local",
                    "backend_kind": "openai_compatible",
                    "base_url": "http://127.0.0.1:1234/v1",
                    "model_name": "qwen3-8b",
                }
            ]
        }
    )
    discovered_ids = ["qwen/qwen3-30b-a3b-2507", "google/gemma-3-27b"]

    page.apply_probe_result(
        {
            "success": True,
            "message": "Connection successful.",
            "discovered_models": [{"id": model_id, "label": model_id} for model_id in discovered_ids],
            "selected_model_valid": False,
            "discovered_context_window": 65536,
        }
    )
    saved_settings = settings_service.validate_settings(page.build_settings({}))

    reloaded_page = AiSettingsPage()
    qtbot.addWidget(reloaded_page)
    reloaded_page.load_settings(saved_settings)

    combo = reloaded_page._model_combo
    assert [combo.itemText(index) for index in range(combo.count())] == discovered_ids
    assert combo.currentText() == discovered_ids[0]


def test_model_selector_falls_back_to_built_in_names_when_never_probed(qtbot) -> None:
    """
    @brief      Verify a profile that has never been probed still offers starting suggestions.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)

    page.load_settings(
        {"llm_profiles": [{"id": "profile-1", "label": "New", "backend_kind": "openai_compatible"}]}
    )

    assert page._model_combo.count() > 0


def test_long_model_identifiers_do_not_widen_the_settings_form(qtbot) -> None:
    """
    @brief      Verify one long model id cannot stretch the AI settings form on the X axis.
    @details    The selector used the default size-adjust policy, so it demanded room for its
                longest entry and the whole form grew depending on what the endpoint served.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """

    def _form_width(model_ids: list[str]) -> int:
        """
        @brief      Build one page for the given discovered models and return its width hint.
        @param[in]  model_ids Discovered model identifiers.
        @return     Preferred page width in pixels.
        @exception  None
        """
        page = AiSettingsPage()
        qtbot.addWidget(page)
        page.load_settings(
            {
                "llm_profiles": [
                    {
                        "id": "profile-1",
                        "label": "Local",
                        "backend_kind": "openai_compatible",
                        "model_name": model_ids[0],
                    }
                ]
            }
        )
        page.apply_probe_result(
            {
                "success": True,
                "message": "Connection successful.",
                "discovered_models": [{"id": model_id, "label": model_id} for model_id in model_ids],
                "selected_model_valid": True,
                "discovered_context_window": 65536,
            }
        )
        return page.sizeHint().width()

    short_width = _form_width(["qwen3-8b"])
    long_width = _form_width(
        ["publisher/some-extremely-long-model-identifier-with-many-qualifiers-v3.1-instruct-gguf-q8"]
    )

    assert long_width == short_width


def test_clicking_the_model_field_opens_the_discovered_model_list(qtbot) -> None:
    """
    @brief      Verify clicking the editable model field drops down the discovered models.
    @details    An editable combo only opens from its arrow, so operators clicking the text
                concluded the models discovered at the endpoint were missing. The list must
                also survive the button release: opening the popup during the press makes it
                grab the mouse, and the release then dismisses it immediately. The offscreen
                test platform does not emulate that grab, so the press is asserted separately
                to pin down which event is allowed to open the list.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)
    page.load_settings(
        {
            "llm_profiles": [
                {
                    "id": "profile-1",
                    "label": "Local",
                    "backend_kind": "lmstudio",
                    "base_url": "http://127.0.0.1:1234/v1",
                    "model_name": "vendor/model-1",
                }
            ]
        }
    )
    page.apply_probe_result(
        {
            "success": True,
            "message": "Connection successful.",
            "discovered_models": [
                {"id": f"vendor/model-{index}", "label": f"vendor/model-{index}"} for index in (1, 2)
            ],
            "selected_model_valid": True,
            "discovered_context_window": None,
        }
    )
    page.show()
    combo = page._model_combo
    line_edit = combo.lineEdit()
    position = QPointF(10, 8)

    def _send(event_type: QEvent.Type) -> None:
        """
        @brief      Deliver one left-button mouse event to the model field.
        @param[in]  event_type Mouse event type to deliver.
        @return     None.
        @exception  None
        """
        QApplication.sendEvent(
            line_edit,
            QMouseEvent(
                event_type,
                position,
                position,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )

    assert combo.view().isVisible() is False

    _send(QEvent.Type.MouseButtonPress)
    QApplication.processEvents()
    assert combo.view().isVisible() is False, "the press must not open the popup, or the release closes it again"

    _send(QEvent.Type.MouseButtonRelease)
    QApplication.processEvents()
    QApplication.processEvents()

    assert combo.view().isVisible() is True
    assert combo.count() == 2


def test_model_field_still_accepts_a_hand_typed_model_name(qtbot) -> None:
    """
    @brief      Verify the model field stays editable for endpoints that do not advertise models.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)
    page.load_settings(
        {"llm_profiles": [{"id": "profile-1", "label": "Local", "backend_kind": "lmstudio"}]}
    )

    page._model_combo.lineEdit().setText("custom/not-advertised-model")

    assert page.build_current_profile_payload()["model_name"] == "custom/not-advertised-model"
