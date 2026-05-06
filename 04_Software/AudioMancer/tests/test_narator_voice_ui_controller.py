#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_narator_voice_ui_controller.py
@brief Narator Voice UI controller tests for AudioMancer.
@details Verifies narrator profile creation, edit-mode sample invalidation,
         explicit narrator selection, and Qwen3-backed sample generation.
@author Eng. Dan Dumitru Pasare
@date 2026-04-18
@version 3.2.0
"""

# IMPORTS

import json

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import narrator_definition_service, project_workspace_service
from audiomancer.ui.controllers import narator_voice_ui_controller
from audiomancer.ui.main_window import MainWindow


def test_narator_voice_create_profile_does_not_change_selected_narrator(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify creating a profile adds it to the project without selecting a narrator by default.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerCreate")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        narator_voice_ui_controller.QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("My Narrator", True),
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args, **kwargs: None,
    )
    narator_voice_ui_controller.handle_create_profile_requested(
        window,
        window._narator_voice_page.current_editor_payload(),
    )

    assert any(
        profile["display_name"] == "My Narrator" for profile in narrator_definition_service.load_profiles(project_root)
    )
    assert project_workspace_service.load_manifest(project_root)["narrator_profile_name"] is None
    assert narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"] is None


def test_narator_voice_edit_selected_profile_clears_sample_and_selection(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify editing a selected profile clears its sample and manifest selection summary.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerEdit")
    window = _build_window(qtbot, project_root)
    profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Edit Narrator",
        "English",
        "Prompt.",
        "Preview text.",
    )
    narrator_definition_service.store_profile_sample(
        project_root,
        profile,
        "Preview text.",
        {
            "generation_mode": "definition",
            "model_id": "qwen-designer",
            "source_model_id": "qwen-designer",
            "language": "en",
        },
        "Generated sample.",
        b"RIFF-selected",
    )
    narrator_definition_service.select_narrator_profile(project_root, profile["profile_id"], "en")
    project_manifest = project_workspace_service.load_manifest(project_root)
    project_manifest["narrator_profile_name"] = "Edit Narrator"
    project_manifest["narrator_language"] = "English"
    project_workspace_service.save_manifest(project_manifest, project_root)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    monkeypatch.setattr(
        narator_voice_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    narator_voice_ui_controller.handle_edit_profile_requested(window, profile["profile_id"])

    assert narrator_definition_service.has_profile_sample(project_root, profile["profile_id"]) is False
    assert narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"] is None
    assert project_workspace_service.load_manifest(project_root)["narrator_profile_name"] is None
    assert window._narator_voice_page.is_edit_mode() is True


def test_narator_voice_ui_controller_select_profile_with_sample_updates_manifest(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify explicit narrator selection persists when a profile sample exists.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.2.0
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerSelect")
    created_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "My Narrator",
        "English",
        "Prompt.",
        "Preview text.",
    )
    narrator_definition_service.store_profile_sample(
        project_root,
        created_profile,
        "Preview text.",
        {
            "generation_mode": "definition",
            "model_id": "qwen-designer",
            "source_model_id": "qwen-designer",
            "speaker_id": None,
            "language": "en",
        },
        "Generated custom sample.",
        b"RIFF-selected",
    )
    window = _build_window(
        qtbot,
        project_root,
        settings_payload={
            **_default_settings_payload(),
            "tts_runtime_probe_succeeded": True,
            "tts_runtime_discovered_models": _minimum_qwen_models(),
        },
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.audio_blocks_ui_controller,
        "confirm_narrator_voice_invalidation",
        lambda *_args, **_kwargs: True,
    )

    narator_voice_ui_controller.handle_select_profile_requested(window, created_profile["profile_id"])
    selected_audio_path, selected_metadata_path = narrator_definition_service.selected_narrator_sample_paths(
        project_root
    )

    assert (
        narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"]
        == (created_profile["profile_id"])
    )
    assert project_workspace_service.load_manifest(project_root)["narrator_profile_name"] == "My Narrator"
    assert selected_audio_path.read_bytes() == b"RIFF-selected"
    assert "selected_profile_id" in selected_metadata_path.read_text(encoding="utf-8")


def test_narator_voice_ui_controller_select_profile_without_sample_updates_manifest(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify explicit narrator selection may persist before sample generation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-05
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerSelectUnsampled")
    created_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Unsampled Narrator",
        "English",
        "Prompt.",
        "Preview text.",
    )
    window = _build_window(
        qtbot,
        project_root,
        settings_payload={
            **_default_settings_payload(),
            "tts_runtime_probe_succeeded": True,
            "tts_runtime_discovered_models": _minimum_qwen_models(),
        },
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.audio_blocks_ui_controller,
        "confirm_narrator_voice_invalidation",
        lambda *_args, **_kwargs: True,
    )

    narator_voice_ui_controller.handle_select_profile_requested(window, created_profile["profile_id"])
    selected_audio_path, selected_metadata_path = narrator_definition_service.selected_narrator_sample_paths(
        project_root
    )

    assert (
        narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"]
        == created_profile["profile_id"]
    )
    assert project_workspace_service.load_manifest(project_root)["narrator_profile_name"] == "Unsampled Narrator"
    assert selected_audio_path.exists() is False
    assert selected_metadata_path.exists() is False


def test_narator_voice_ui_controller_selection_change_refreshes_delete_state(qtbot, tmp_path) -> None:
    """
    @brief      Verify switching the inspected narrator profile refreshes delete enablement for the new profile.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerSelectionRefresh")
    custom_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "My Narrator",
        "English",
        "Prompt.",
        "Preview text.",
    )
    profiles_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.NARRATOR_PROFILE_FILE_NAME
    profiles_path.write_text(
        json.dumps(
            [
                {
                    "profile_id": "default_narrator_profile",
                    "display_name": "Default1",
                    "language": "English",
                    "prompt_text": "Warm narrator prompt.",
                    "preview_text": "Preview text.",
                    "profile_kind": "custom",
                    "profile_origin": "default_custom",
                    "provider_family": "project_default",
                    "editable": True,
                    "protected": True,
                    "is_selected": True,
                },
                custom_profile,
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    narrator_definition_service.load_profiles(project_root)
    narrator_definition_service.select_narrator_profile(project_root, "default_narrator_profile", "English")
    window = _build_window(qtbot, project_root)

    assert window._narator_voice_page.current_profile_id() == "default_narrator_profile"
    assert window._narator_voice_page._delete_profile_button.isEnabled() is True

    narator_voice_ui_controller.handle_selection_change_requested(window, custom_profile["profile_id"])

    assert window._narator_voice_page.current_profile_id() == custom_profile["profile_id"]
    assert window._narator_voice_page._delete_profile_button.isEnabled() is True


def test_narator_voice_generate_sample_reprobes_runtime_and_stores_audio(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify Generate Sample confirms, reprobes runtime, and stores the returned audio artifacts.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerGenerate")
    profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Generated Narrator",
        "English",
        "Generated prompt.",
        "Preview text.",
    )
    window = _build_window(
        qtbot,
        project_root,
        settings_payload={
            **_default_settings_payload(),
            "tts_runtime_base_url": "http://voiceweaver.local:8059",
        },
    )
    window._narator_voice_inspected_profile_id = profile["profile_id"]
    persisted_settings = dict(window._settings_payload)
    observed_timeouts: dict[str, object] = {"wait_for_terminal_operation": []}
    monkeypatch.setattr(
        narator_voice_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.misc_ui_controller,
        "create_progress_dialog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.misc_ui_controller,
        "update_progress_dialog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.misc_ui_controller,
        "finish_progress_dialog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.misc_ui_controller,
        "clear_progress_dialog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.settings_service,
        "save_settings",
        lambda payload: persisted_settings.update(dict(payload)),
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.settings_service,
        "load_settings",
        lambda: dict(persisted_settings),
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "probe_runtime",
        lambda *_args, **_kwargs: {
            "success": True,
            "message": "Connection successful. Discovered 3 models.",
            "discovered_models": _minimum_qwen_models(),
            "active_model_id": None,
            "device_diagnostics": {},
            "capability_matrix": narator_voice_ui_controller.voiceweaver_runtime_service.build_capability_matrix(
                _minimum_qwen_models()
            ),
        },
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **kwargs: (
            observed_timeouts.__setitem__("read_status", int(kwargs["timeout_seconds"])),
            {"active_model": None, "device_diagnostics": {}, "operation": {"status": "idle"}},
        )[1],
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "load_model",
        lambda *_args, **kwargs: (
            observed_timeouts.__setitem__("load_model", int(kwargs["timeout_seconds"])),
            {"status": "running"},
        )[1],
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "generate_voice_design",
        lambda *_args, **kwargs: (
            observed_timeouts.__setitem__("generate_voice_design", int(kwargs["timeout_seconds"])),
            {"success": True},
        )[1],
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **kwargs: (
            observed_timeouts["wait_for_terminal_operation"].append(int(kwargs["timeout_seconds"])),
            (
                {
                    "active_model": {"model_id": "qwen-designer"},
                    "operation": {"status": "completed", "progress_percent": 100, "stage": "completed"},
                    "result": {"available": False, "summary": None},
                    "device_diagnostics": {},
                }
                if len(observed_timeouts["wait_for_terminal_operation"]) == 1
                else {
                    "active_model": {"model_id": "qwen-designer"},
                    "operation": {"status": "completed", "progress_percent": 100, "stage": "completed"},
                    "result": {"available": True, "summary": "Narator voice sample ready."},
                    "device_diagnostics": {},
                }
            ),
        )[1],
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "download_generated_voice",
        lambda *_args, **kwargs: (
            observed_timeouts.__setitem__("download_generated_voice", int(kwargs["timeout_seconds"])),
            b"RIFF-generated",
        )[1],
    )

    def _start_threaded_operation(
        window,
        operation_kind,
        operation_name,
        initial_message,
        worker_callable,
        set_busy,
        success_handler,
        failure_handler,
        cancel_handler,
        cancellable=True,
    ):
        """
        @brief      Provide the start threaded operation test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        _ = operation_kind
        _ = operation_name
        _ = initial_message
        _ = set_busy
        _ = failure_handler
        _ = cancel_handler
        _ = cancellable
        success_handler(
            worker_callable(
                window._current_project_root,
                dict(window._current_manifest),
                progress_callback=lambda *_args, **_kwargs: None,
                cancel_requested=lambda: False,
            )
        )

    monkeypatch.setattr(
        narator_voice_ui_controller.operation_runner_controller,
        "start_threaded_operation",
        _start_threaded_operation,
    )

    narator_voice_ui_controller.handle_generate_sample_requested(
        window,
        window._narator_voice_inspected_profile_id,
    )
    profile_audio_path, profile_metadata_path = narrator_definition_service.profile_sample_paths(
        project_root,
        str(window._narator_voice_inspected_profile_id),
    )

    assert profile_audio_path.read_bytes() == b"RIFF-generated"
    assert "Narator voice sample ready." in profile_metadata_path.read_text(encoding="utf-8")
    assert observed_timeouts == {
        "read_status": 60,
        "load_model": 60,
        "generate_voice_design": 60,
        "wait_for_terminal_operation": [60, 60],
        "download_generated_voice": 60,
    }


def test_narator_voice_ui_controller_preview_state_change_clears_preview_flag(qtbot, tmp_path) -> None:
    """
    @brief      Verify preview-state refresh accepts the Qt playback enum without crashing and clears the preview flag.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.1
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerPreviewState")
    window = _build_window(qtbot, project_root)
    window._narator_voice_page.set_preview_active(True)
    window._narator_voice_audio_player.stop()

    narator_voice_ui_controller.handle_preview_playback_state_changed(window)

    assert window._narator_voice_page._preview_active is False  # noqa: SLF001


def test_narator_voice_progress_messages_hide_model_id(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify Narator Voice generation progress text does not disclose the concrete runtime model id.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    1.1.0
    """
    _project_root, _manifest = _create_project(tmp_path, "NarratorControllerProgressPrivacy")
    _ = qtbot
    observed_updates: list[tuple[int, str]] = []

    narator_voice_ui_controller._update_load_progress(
        lambda _current, _total, percent, message: observed_updates.append((percent, message)),
        {
            "operation": {
                "progress_percent": 40,
                "stage": "Loaded Qwen3-TTS-VoiceDesigner model qwen-designer.",
            }
        },
        "Loading voice generation model...",
    )
    narator_voice_ui_controller._update_generation_progress(
        lambda _current, _total, percent, message: observed_updates.append((percent, message)),
        {
            "operation": {
                "progress_percent": 50,
                "stage": "Generating with qwen-designer.",
            }
        },
        "Generating narator voice sample...",
    )

    assert observed_updates[0][1] == "Loading voice generation model..."
    assert observed_updates[1][1] == "Generating narator voice sample..."
    assert all("qwen" not in message.casefold() for _percent, message in observed_updates)


def _create_project(tmp_path, name: str):
    """
    @brief      Provide the create project test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-17T12:00:00+00:00",
        "size_bytes": 16,
    }
    manifest["current_stage"] = "narrator_definition_ready"
    project_workspace_service.save_manifest(manifest, project_root)
    return project_root, manifest


def _build_window(qtbot, project_root, settings_payload=None):
    """
    @brief      Provide the build window test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    window = MainWindow(settings_payload=_default_settings_payload() if settings_payload is None else settings_payload)
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    window._refresh_narator_voice_page_state(  # noqa: SLF001
        project_root,
        project_workspace_service.load_manifest(project_root),
        str(window._settings_payload.get("language", "en")),
    )
    return window


def _default_settings_payload() -> dict[str, object]:
    """
    @brief      Provide the default settings payload test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
