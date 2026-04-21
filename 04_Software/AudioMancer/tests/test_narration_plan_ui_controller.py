#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_narration_plan_ui_controller.py
@brief Narration Plan UI controller tests for AudioMancer.
@details Verifies destructive prompt-edit handling and missing narrator-sample
         page-entry warnings for the Narration Plan workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 1.2.1
"""

# IMPORTS

from PySide6.QtWidgets import QMessageBox

from audiomancer.services import (
    character_discovery_service,
    narration_plan_service,
    narrator_definition_service,
    project_workspace_service,
)
from audiomancer.ui.controllers import narration_plan_ui_controller
from audiomancer.ui.main_window import MainWindow


def test_narration_plan_ui_controller_edit_prompt_clears_sample_and_enters_edit_mode(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify editing a character prompt deletes the existing sample and enters edit mode.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "NarrationPlanControllerEdit")
    target_payload = narration_plan_service.voice_target_by_id(project_root, "character_alice")
    assert target_payload is not None
    narration_plan_service.store_target_sample(
        project_root,
        target_payload,
        "en",
        "Preview text.",
        {
            "generation_mode": "definition",
            "source_model_id": "qwen-designer",
        },
        "Character sample ready.",
        b"RIFF-character",
    )
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        narration_plan_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    narration_plan_ui_controller.handle_edit_prompt_requested(window, "character_alice")

    assert narration_plan_service.has_target_sample(project_root, "character_alice") is False
    assert window._narration_plan_page.is_edit_mode() is True


def test_narration_plan_ui_controller_page_activation_warns_when_narrator_sample_is_missing(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify entering the page warns once when the selected Narator Voice sample is missing.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.1
    """
    project_root = _create_project_with_character_and_selected_narrator(
        tmp_path,
        "NarrationPlanControllerWarning",
        store_narrator_sample=False,
    )
    window = _build_window(qtbot, project_root)
    warning_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        narration_plan_ui_controller.QMessageBox,
        "warning",
        lambda *args, **kwargs: warning_calls.append(args),
    )

    narration_plan_ui_controller.handle_page_activated(window)
    narration_plan_ui_controller.handle_page_activated(window)

    assert len(warning_calls) == 1
    assert window._narration_plan_missing_narrator_popup_shown is True


def test_narration_plan_ui_controller_save_prompt_persists_preview_text(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify Save Voice Prompt persists the edited preview text together with the voice prompt.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "NarrationPlanControllerSave")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        narration_plan_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args, **kwargs: None,
    )

    narration_plan_ui_controller.handle_save_prompt_requested(
        window,
        {
            "target_id": "character_alice",
            "prompt_text": "Updated prompt.",
            "preview_text": "Preview line one.\nPreview line two.",
        },
    )

    target_payload = narration_plan_service.voice_target_by_id(project_root, "character_alice")
    assert target_payload is not None
    assert target_payload["preview_text"] == "Preview line one.\nPreview line two."


def test_narration_plan_ui_controller_generate_stops_preview_before_deleting_sample(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify sample regeneration stops preview playback before deleting the old WAV.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "NarrationPlanControllerGenerate")
    window = _build_window(qtbot, project_root)
    call_order: list[str] = []
    monkeypatch.setattr(narration_plan_ui_controller, "_confirm_generate_sample", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        narration_plan_ui_controller,
        "_probe_runtime_and_persist_cache",
        lambda *_args, **_kwargs: {
            "success": True,
            "discovered_models": [],
            "capability_matrix": {"minimum_qwen_ready": True},
        },
    )
    monkeypatch.setattr(
        narration_plan_service,
        "voice_target_generation_request",
        lambda *_args, **_kwargs: {
            "can_generate": True,
            "language": "en",
            "generation_mode": "definition",
            "model_id": "qwen-designer",
            "source_model_id": "qwen-designer",
            "model_parameters": {},
        },
    )
    monkeypatch.setattr(
        narration_plan_ui_controller,
        "_stop_preview_playback",
        lambda *_args, **_kwargs: call_order.append("stop"),
    )
    monkeypatch.setattr(
        narration_plan_service,
        "delete_target_sample",
        lambda *_args, **_kwargs: call_order.append("delete"),
    )
    monkeypatch.setattr(
        narration_plan_ui_controller.misc_ui_controller,
        "create_progress_dialog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        narration_plan_ui_controller.misc_ui_controller,
        "finish_progress_dialog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        narration_plan_ui_controller.misc_ui_controller,
        "clear_progress_dialog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        narration_plan_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        narration_plan_ui_controller,
        "_generate_and_store_sample",
        lambda *args, **kwargs: None,
    )

    narration_plan_ui_controller.handle_generate_sample_requested(window, "character_alice")

    assert call_order[:2] == ["stop", "delete"]


def test_narration_plan_progress_messages_hide_model_id(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify narration-plan generation progress text does not disclose the concrete runtime model id.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    1.0.0
    """
    project_root = _create_project_with_character_and_selected_narrator(
        tmp_path,
        "NarrationPlanControllerProgressPrivacy",
    )
    window = _build_window(qtbot, project_root)
    observed_updates: list[tuple[int, str]] = []
    monkeypatch.setattr(
        narration_plan_ui_controller.misc_ui_controller,
        "update_progress_dialog",
        lambda _window, percent, message, token_usage=None: observed_updates.append((percent, message)),
    )

    narration_plan_ui_controller._update_load_progress(
        window,
        {
            "operation": {
                "progress_percent": 40,
                "stage": "Loaded Qwen3-TTS-VoiceDesigner model qwen-designer.",
            }
        },
    )
    narration_plan_ui_controller._update_generation_progress(
        window,
        {
            "operation": {
                "progress_percent": 50,
                "stage": "Generating with qwen-designer.",
            }
        },
    )

    assert observed_updates[0][1] == "Loading voice generation model..."
    assert observed_updates[1][1] == "Generating character sample..."
    assert all("qwen" not in message.casefold() for _percent, message in observed_updates)


def _create_project_with_character_and_selected_narrator(
    tmp_path,
    name: str,
    store_narrator_sample: bool = True,
):
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-20T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["current_stage"] = "narrator_definition_ready"
    manifest["voice_assignment_mode"] = "narrator_and_characters"
    project_workspace_service.save_manifest(manifest, project_root)

    narrator_profile = narrator_definition_service.load_profiles(project_root)[0]
    if store_narrator_sample:
        narrator_definition_service.store_profile_sample(
            project_root,
            narrator_profile,
            "Preview text.",
            {
                "generation_mode": "custom_voice",
                "source_model_id": "qwen-custom",
                "language": "en",
            },
            "Narator voice sample ready.",
            b"RIFF-narrator",
        )
    narrator_definition_service.select_narrator_profile(project_root, narrator_profile["profile_id"], "en")
    if store_narrator_sample:
        narrator_definition_service.copy_selected_narrator_sample(project_root, narrator_profile["profile_id"])

    character_discovery_service.add_character_profile(project_root, "Alice")
    alice_profile = character_discovery_service.load_character_profiles(project_root)[0]
    character_discovery_service.update_character_profile(
        project_root,
        {
            **dict(alice_profile),
            "canonical_name": "Alice",
            "role_summary": "young observer",
            "description": "reserved but curious",
            "speaking_style": "soft and thoughtful",
            "voice_notes": "gentle warmth",
        },
    )
    selected_narrator = narrator_definition_service.profile_by_id(project_root, narrator_profile["profile_id"])
    assert selected_narrator is not None
    narration_plan_service.sync_voice_plan(
        project_root,
        character_discovery_service.load_character_profiles(project_root),
        selected_narrator,
    )
    return project_root


def _build_window(qtbot, project_root):
    window = MainWindow(settings_payload=_default_settings_payload())
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    return window


def _default_settings_payload() -> dict[str, object]:
    return {
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_translation_profile_id": None,
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": None,
        "tts_runtime_base_url": "http://127.0.0.1:8059",
        "tts_runtime_api_key": "",
        "tts_runtime_probe_succeeded": False,
        "tts_runtime_probe_message": "",
        "tts_runtime_discovered_models": [],
        "tts_runtime_active_model_id": None,
        "tts_runtime_device_diagnostics": {},
        "tts_audio_preview_timeout_seconds": 60,
        "tts_audio_generation_timeout_seconds": 300,
    }


# END OF FILE
