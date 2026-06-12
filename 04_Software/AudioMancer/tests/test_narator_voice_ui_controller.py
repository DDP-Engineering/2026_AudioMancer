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
@version 3.7.0
"""

# IMPORTS

import json

from PySide6.QtWidgets import QMessageBox
import pytest

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
    @date       2026-06-09
    @version    1.3.1
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
    updated_manifest = project_workspace_service.load_manifest(project_root)
    assert updated_manifest["narrator_profile_name"] == "My Narrator"
    assert updated_manifest["narrator_language"] == "en"
    narrator_operation = updated_manifest["operations"]["narrator_definition"]
    selected_metadata = json.loads(selected_metadata_path.read_text(encoding="utf-8"))
    assert narrator_operation["status"] == "completed"
    assert "updated_at" not in narrator_operation
    assert project_workspace_service.open_project(project_root)["status"] == "ok"
    assert selected_audio_path.read_bytes() == b"RIFF-selected"
    assert selected_metadata["profile_id"] == created_profile["profile_id"]


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
    updated_manifest = project_workspace_service.load_manifest(project_root)
    assert updated_manifest["narrator_profile_name"] == "Unsampled Narrator"
    assert updated_manifest["narrator_language"] == "en"
    assert updated_manifest["operations"]["narrator_definition"]["status"] == "completed"
    assert selected_audio_path.exists() is False
    assert selected_metadata_path.exists() is False


def test_narator_voice_select_profile_with_audio_blocks_shows_progress(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify selecting a narrator with generated audio uses synchronous progress and clears affected rows.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.2.0
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerSelectProgress")
    created_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Progress Narrator",
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
    _write_generated_audio_blocks(project_root)
    window = _build_window(qtbot, project_root)
    create_calls = []
    progress_updates = []
    process_calls = []
    original_create = narator_voice_ui_controller.misc_ui_controller.create_progress_dialog
    audio_blocks_service = narator_voice_ui_controller.audio_blocks_ui_controller.audio_blocks_service
    original_remove_audio_blocks = audio_blocks_service.remove_audio_blocks_for_speech_blocks
    monkeypatch.setattr(narator_voice_ui_controller.misc_ui_controller, "show_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        narator_voice_ui_controller.audio_blocks_ui_controller,
        "confirm_narrator_voice_invalidation",
        lambda *_args, **_kwargs: True,
    )

    def _capture_create(*args, **kwargs):
        create_calls.append(kwargs)
        return original_create(*args, **kwargs)

    def _capture_remove_audio_blocks(*args, **kwargs):
        assert window._narator_voice_page._busy is True
        assert kwargs["collect_preserved_paths"] is False
        return original_remove_audio_blocks(*args, **kwargs)

    monkeypatch.setattr(narator_voice_ui_controller.misc_ui_controller, "create_progress_dialog", _capture_create)
    monkeypatch.setattr(
        narator_voice_ui_controller.misc_ui_controller,
        "update_progress_dialog",
        lambda _window, percent, message, token_usage=None: progress_updates.append((percent, message)),
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.misc_ui_controller,
        "process_pending_ui_events",
        lambda: process_calls.append(True),
    )
    monkeypatch.setattr(
        audio_blocks_service,
        "remove_audio_blocks_for_speech_blocks",
        _capture_remove_audio_blocks,
    )

    narator_voice_ui_controller.handle_select_profile_requested(window, created_profile["profile_id"])

    output_payload = json.loads((project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME).read_text(encoding="utf-8"))
    assert create_calls[0]["cancellable"] is False
    assert any(percent == 55 for percent, _message in progress_updates)
    assert progress_updates[-1][0] == 100
    assert process_calls
    assert window._operation_progress_dialog is None
    assert window._narator_voice_page._busy is False
    assert [block["speech_block_id"] for block in output_payload] == ["0001-000001", "0001-000002"]
    narrator_block = next(block for block in output_payload if block["speech_block_id"] == "0001-000001")
    alice_block = next(block for block in output_payload if block["speech_block_id"] == "0001-000002")
    assert narrator_block["audio_relative_path"] is None
    assert narrator_block["generated"] is None
    assert alice_block["audio_relative_path"] is not None
    assert not (project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "0001-000001.wav").exists()
    assert (project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "0001-000002.wav").is_file()


def test_narator_voice_select_profile_progress_clears_after_failure(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify narrator selection progress cleanup runs when selection mutation fails.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerSelectProgressFailure")
    created_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Failing Narrator",
        "English",
        "Prompt.",
        "Preview text.",
    )
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        narator_voice_ui_controller.audio_blocks_ui_controller,
        "confirm_narrator_voice_invalidation",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        narrator_definition_service,
        "select_narrator_profile",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("selection failed")),
    )

    with pytest.raises(RuntimeError, match="selection failed"):
        narator_voice_ui_controller.handle_select_profile_requested(window, created_profile["profile_id"])

    assert window._operation_progress_dialog is None
    assert window._narator_voice_page._busy is False


def test_narator_voice_ui_controller_selection_change_refreshes_delete_state(qtbot, tmp_path) -> None:
    """
    @brief      Verify switching the inspected narrator profile refreshes delete enablement for the new profile.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.2.0
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerSelectionRefresh")
    first_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "First Narrator",
        "English",
        "Warm narrator prompt.",
        "Preview text.",
    )
    custom_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "My Narrator",
        "English",
        "Prompt.",
        "Preview text.",
    )
    narrator_definition_service.select_narrator_profile(project_root, first_profile["profile_id"], "English")
    window = _build_window(qtbot, project_root)

    assert window._narator_voice_page.current_profile_id() == first_profile["profile_id"]
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
    @version    1.2.0
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
    sample_metadata = json.loads(profile_metadata_path.read_text(encoding="utf-8"))[0]["sample"]
    assert sample_metadata["source_kind"] == narrator_definition_service.NARRATOR_SAMPLE_SOURCE_VOICE_DESIGNER
    assert sample_metadata["source_model_id"] == "qwen-designer"
    assert observed_timeouts == {
        "read_status": 60,
        "load_model": 60,
        "generate_voice_design": 60,
        "wait_for_terminal_operation": [60, 60],
        "download_generated_voice": 60,
    }


def test_narator_voice_generate_sample_passes_cancel_to_voiceweaver_waits(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-AUDIO-FUNC-024 sample generation passes cooperative cancellation to runtime polls.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-11
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerGenerateCancelWire")
    profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Generated Narrator",
        "English",
        "Generated prompt.",
        "Preview text.",
    )

    def cancel_callback() -> bool:
        """
        @brief      Return the non-cancelled state for runtime wait callback identity checks.
        @return     False.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-11
        @version    0.1.0
        """
        return False

    observed_cancel_callbacks = []
    monkeypatch.setattr(
        narator_voice_ui_controller.tts_runtime_ui_support,
        "probe_runtime_and_persist_cache_from_settings",
        lambda _settings_payload: _sample_probe_result(),
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.tts_runtime_ui_support,
        "persist_runtime_status_from_settings",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.tts_budget_service,
        "resolve_cached_tts_budget",
        lambda _models: {},
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.tts_budget_service,
        "estimated_safe_word_count",
        lambda _payload: 200,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.tts_budget_service,
        "estimated_word_count",
        lambda _text: 10,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"active_model": None, "device_diagnostics": {}, "operation": {"status": "idle"}},
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "load_model",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "generate_voice_design",
        lambda *_args, **_kwargs: {"success": True},
    )

    def _wait_for_terminal_operation(*_args, **kwargs):
        """
        @brief      Capture cancellation callbacks passed to VoiceWeaver runtime polling.
        @return     Fake terminal runtime status.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-11
        @version    0.1.0
        """
        observed_cancel_callbacks.append(kwargs.get("cancel_requested"))
        result_available = len(observed_cancel_callbacks) > 1
        return {
            "active_model": {"model_id": "qwen-designer"},
            "operation": {"status": "completed", "progress_percent": 100, "stage": "completed"},
            "result": {"available": result_available, "summary": "Narator voice sample ready."},
            "device_diagnostics": {},
        }

    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        _wait_for_terminal_operation,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "download_generated_voice",
        lambda *_args, **_kwargs: b"RIFF-generated",
    )

    narator_voice_ui_controller._generate_and_store_sample(
        project_root,
        _default_settings_payload(),
        _sample_progress_messages(),
        profile,
        "Preview text for narrator sample generation.",
        progress_callback=None,
        cancel_requested=cancel_callback,
    )

    assert observed_cancel_callbacks == [cancel_callback, cancel_callback]


def test_narator_voice_generate_sample_failure_preserves_previous_sample(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-AUDIO-FUNC-024 failed sample generation preserves the previous profile sample.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-11
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerGenerateFailurePreserves")
    profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Generated Narrator",
        "English",
        "Generated prompt.",
        "Preview text.",
    )
    narrator_definition_service.store_profile_sample(
        project_root,
        profile,
        "Previous sample text.",
        {
            "generation_mode": "definition",
            "model_id": "qwen-designer",
            "source_model_id": "qwen-designer",
            "language": "en",
        },
        "Previous generated sample.",
        b"RIFF-previous",
    )
    profile_audio_path, _metadata_path = narrator_definition_service.profile_sample_paths(
        project_root,
        profile["profile_id"],
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.tts_runtime_ui_support,
        "probe_runtime_and_persist_cache_from_settings",
        lambda _settings_payload: _sample_probe_result(),
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.tts_runtime_ui_support,
        "persist_runtime_status_from_settings",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.tts_budget_service,
        "resolve_cached_tts_budget",
        lambda _models: {},
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.tts_budget_service,
        "estimated_safe_word_count",
        lambda _payload: 200,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.tts_budget_service,
        "estimated_word_count",
        lambda _text: 10,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {
            "active_model": {"model_id": "qwen-designer"},
            "device_diagnostics": {},
            "operation": {"status": "idle"},
        },
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "generate_voice_design",
        lambda *_args, **_kwargs: {"success": True},
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: {
            "active_model": {"model_id": "qwen-designer"},
            "operation": {"status": "failed", "progress_percent": 100, "stage": "failed"},
            "result": {"available": False, "summary": None},
            "device_diagnostics": {},
        },
    )

    with pytest.raises(RuntimeError):
        narator_voice_ui_controller._generate_and_store_sample(
            project_root,
            _default_settings_payload(),
            _sample_progress_messages(),
            profile,
            "Preview text for narrator sample generation.",
            progress_callback=None,
            cancel_requested=lambda: False,
        )

    assert profile_audio_path.read_bytes() == b"RIFF-previous"
    sample_metadata = narrator_definition_service.load_profile_sample_metadata(project_root, profile["profile_id"])
    assert sample_metadata is not None
    assert sample_metadata["preview_text"] == "Previous sample text."


def test_narator_voice_generate_profiles_resolves_selected_ai_profile_and_starts_worker(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify narrator profile generation resolves the selected AI profile and count.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.1
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerGenerateProfiles")
    settings_payload = {
        **_default_settings_payload(),
        "llm_profiles": [_ai_profile_payload("profile_1")],
        "default_narrator_profile_generation_profile_id": "profile_1",
        "tts_preview_text_character_limit": 180,
    }
    window = _build_window(qtbot, project_root, settings_payload=settings_payload)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        narator_voice_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(narator_voice_ui_controller.QInputDialog, "getInt", lambda *_args, **_kwargs: (4, True))
    monkeypatch.setattr(
        narator_voice_ui_controller,
        "prompt_ai_narrator_profile_instructions",
        lambda _window, _language: "Prefer crisp theatrical-but-not-grandiose profiles.",
    )
    monkeypatch.setattr(narator_voice_ui_controller.misc_ui_controller, "show_message", lambda *args, **kwargs: None)

    def _generate_narrator_profiles(
        project_root_arg,
        _manifest,
        ai_profile,
        profile_count,
        voice_language,
        preview_limit,
        additional_profile_instructions=None,
        **_kwargs,
    ):
        """
        @brief      Capture profile generation inputs.
        @return     Fake narrator profile generation report.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-13
        @version    0.1.0
        """
        captured.update(
            {
                "project_root": project_root_arg,
                "ai_profile_id": ai_profile["id"],
                "profile_count": profile_count,
                "voice_language": voice_language,
                "preview_limit": preview_limit,
                "additional_profile_instructions": additional_profile_instructions,
            }
        )
        return {"generated_profile_ids": [], "generated_profile_count": 4}

    monkeypatch.setattr(
        narator_voice_ui_controller.narrator_profile_generation_service,
        "generate_narrator_profiles",
        _generate_narrator_profiles,
    )

    def _start_threaded_operation(
        window_arg,
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
        @brief      Run the generation worker synchronously for controller testing.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-11
        @version    0.1.0
        """
        _ = failure_handler
        _ = cancel_handler
        captured["operation_kind"] = operation_kind
        captured["operation_name"] = operation_name
        captured["initial_message"] = initial_message
        captured["set_busy"] = set_busy
        captured["cancellable"] = cancellable
        success_handler(
            worker_callable(
                window_arg._current_project_root,
                dict(window_arg._current_manifest),
                progress_callback=lambda *_args, **_kwargs: None,
                cancel_requested=lambda: False,
            )
        )

    monkeypatch.setattr(
        narator_voice_ui_controller.operation_runner_controller,
        "start_threaded_operation",
        _start_threaded_operation,
    )

    narator_voice_ui_controller.handle_generate_profiles_requested(window, "profile_1")

    assert captured["operation_kind"] == "narrator_definition"
    assert captured["operation_name"] == "Generate Narators"
    assert captured["initial_message"] == "Generating narator profiles..."
    assert captured["cancellable"] is True
    assert captured["project_root"] == project_root
    assert captured["ai_profile_id"] == "profile_1"
    assert captured["profile_count"] == 4
    assert captured["voice_language"] == "en"
    assert captured["preview_limit"] == 180
    assert captured["additional_profile_instructions"] == "Prefer crisp theatrical-but-not-grandiose profiles."


def test_narator_voice_generate_profiles_count_cancel_stops_before_worker(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify cancelling the count dialog prevents worker startup.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "NarratorControllerGenerateProfilesCancel")
    window = _build_window(
        qtbot,
        project_root,
        settings_payload={
            **_default_settings_payload(),
            "llm_profiles": [_ai_profile_payload("profile_1")],
            "default_narrator_profile_generation_profile_id": "profile_1",
        },
    )
    start_calls: list[bool] = []
    monkeypatch.setattr(
        narator_voice_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(narator_voice_ui_controller.QInputDialog, "getInt", lambda *_args, **_kwargs: (6, False))
    monkeypatch.setattr(
        narator_voice_ui_controller.operation_runner_controller,
        "start_threaded_operation",
        lambda *args, **kwargs: start_calls.append(True),
    )

    narator_voice_ui_controller.handle_generate_profiles_requested(window, "profile_1")

    assert start_calls == []


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


def _write_generated_audio_blocks(project_root) -> None:
    """
    @brief      Write generated Audio Blocks fixtures for narrator invalidation tests.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    generated_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    generated_root.mkdir(parents=True, exist_ok=True)
    (generated_root / "0001-000001.wav").write_bytes(b"RIFF-narrator")
    (generated_root / "0001-000001.json").write_text("{}\n", encoding="utf-8")
    (generated_root / "0001-000002.wav").write_bytes(b"RIFF-character")
    (generated_root / "0001-000002.json").write_text("{}\n", encoding="utf-8")
    (project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "speech_block_id": "0001-000001",
                    "sequence_index": 1,
                    "chunk_id": "chunk-0001",
                    "source_language": "en",
                    "speaker_kind": "narrator",
                    "speaker_id": "narrator",
                    "speaker_display_name": "Narrator",
                    "content_kind": "Narration",
                    "text": "Narration line.",
                    "approved": True,
                    "warning_flags": [],
                },
                {
                    "speech_block_id": "0001-000002",
                    "sequence_index": 2,
                    "chunk_id": "chunk-0001",
                    "source_language": "en",
                    "speaker_kind": "character",
                    "speaker_id": "alice",
                    "speaker_display_name": "Alice",
                    "content_kind": "Dialogue",
                    "text": "Hello.",
                    "approved": True,
                    "warning_flags": [],
                },
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "speech_block_id": "0001-000001",
                    "sequence_index": 1,
                    "chunk_id": "chunk-0001",
                    "speaker_id": "narrator",
                    "speaker_display_name": "Narrator",
                    "content_kind": "Narration",
                    "text": "Narration line.",
                    "voice_target_id": "narrator",
                    "audio_relative_path": "audio_blocks/0001-000001.wav",
                    "metadata_relative_path": "audio_blocks/0001-000001.json",
                    "generated": True,
                    "approved": True,
                    "approved_at": "2026-05-11T12:00:00+00:00",
                },
                {
                    "speech_block_id": "0001-000002",
                    "sequence_index": 2,
                    "chunk_id": "chunk-0001",
                    "speaker_id": "alice",
                    "speaker_display_name": "Alice",
                    "content_kind": "Dialogue",
                    "text": "Hello.",
                    "voice_target_id": "character_alice",
                    "audio_relative_path": "audio_blocks/0001-000002.wav",
                    "metadata_relative_path": "audio_blocks/0001-000002.json",
                    "generated": True,
                    "approved": True,
                    "approved_at": "2026-05-11T12:00:00+00:00",
                },
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / config.AUDIO_BLOCKS_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "status": "completed",
                "progress_current": 2,
                "progress_total": 2,
                "metadata": {"voice_language": "en"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / config.AUDIO_BLOCKS_REPORT_FILE_NAME).write_text(
        json.dumps({"audio_blocks_stage_status": "completed", "voice_language": "en"}, indent=2) + "\n",
        encoding="utf-8",
    )


def _sample_progress_messages() -> dict[str, str]:
    """
    @brief      Provide worker-safe sample generation progress messages for tests.
    @return     Progress message mapping.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-11
    @version    0.1.0
    """
    return {
        "prepare": "Preparing narator sample generation...",
        "qwen_capabilities_missing": "Missing capabilities: {missing_capabilities}",
        "preview_text_over_budget": "Preview text has {word_count} words; safe limit is {safe_word_count}.",
        "load_model": "Loading voice generation model...",
        "generate": "Generating narator voice sample...",
        "generation_missing_audio": "VoiceWeaver did not return downloadable audio.",
        "download": "Downloading narator voice sample...",
    }


def _sample_probe_result() -> dict[str, object]:
    """
    @brief      Provide a ready VoiceWeaver probe result for sample-generation tests.
    @return     Runtime probe payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-11
    @version    0.1.0
    """
    discovered_models = _minimum_qwen_models()
    return {
        "success": True,
        "message": "Connection successful. Discovered 2 models.",
        "discovered_models": discovered_models,
        "active_model_id": None,
        "device_diagnostics": {},
        "capability_matrix": narator_voice_ui_controller.voiceweaver_runtime_service.build_capability_matrix(
            discovered_models
        ),
    }


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
        "default_narrator_profile_generation_profile_id": None,
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
        "tts_preview_text_character_limit": config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT,
    }


def _ai_profile_payload(profile_id: str) -> dict[str, object]:
    """
    @brief      Provide an enabled AI profile payload for controller tests.
    @param[in]  profile_id Profile identifier.
    @return     AI profile payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    return {
        "id": profile_id,
        "label": "Profile One",
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234/v1",
        "api_key": "",
        "model_name": "qwen3-8b",
        "context_window": 8192,
        "max_output_tokens": 1024,
        "request_timeout_seconds": 90,
        "temperature": 0.2,
        "supports_structured_output": True,
        "enabled": True,
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
