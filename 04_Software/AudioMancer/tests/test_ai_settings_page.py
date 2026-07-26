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
@author Eng. Dan Dumitru Pasare
@date 2026-04-21
@version 0.5.6
"""

# IMPORTS

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QFormLayout, QGridLayout

from audiomancer import config
from audiomancer.services import settings_service
from audiomancer.ui.pages.ai_settings_page import AiSettingsPage


def test_ai_settings_page_default_selectors_are_stacked_in_workflow_order(qtbot) -> None:
    """
    @brief      Verify default AI selector rows match the operator workflow.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.2.2
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
    assert page._save_button.text() == "Save"
    assert page._ok_button.text() == "OK"


def test_ai_settings_page_numeric_profile_options_use_two_column_grid(qtbot) -> None:
    """
    @brief      Verify compact numeric AI profile options are arranged in two columns.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.1
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
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
        "default_ai_translation_profile_id": "profile_a",
        "default_narrator_profile_generation_profile_id": "profile_a",
        "default_speech_blocks_profile_id": "profile_a",
        "default_ai_chunking_strategy": "scene",
        "default_character_extraction_profile_id": "profile_a",
        "ui_text_scale": "normal",
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-04
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-17
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
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


# END OF FILE


def test_model_selector_keeps_discovered_models_across_a_settings_round_trip(qtbot) -> None:
    """
    @brief      Verify probed endpoint models are still offered after settings are saved and reloaded.
    @details    The discovered list used to live only in memory, so a relaunched app showed three
                built-in placeholder names the endpoint may not serve while hiding the real ones.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """

    def _form_width(model_ids: list[str]) -> int:
        """
        @brief      Build one page for the given discovered models and return its width hint.
        @param[in]  model_ids Discovered model identifiers.
        @return     Preferred page width in pixels.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-26
        @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.2.0
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
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-26
        @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    page = AiSettingsPage()
    qtbot.addWidget(page)
    page.load_settings(
        {"llm_profiles": [{"id": "profile-1", "label": "Local", "backend_kind": "lmstudio"}]}
    )

    page._model_combo.lineEdit().setText("custom/not-advertised-model")

    assert page.build_current_profile_payload()["model_name"] == "custom/not-advertised-model"
