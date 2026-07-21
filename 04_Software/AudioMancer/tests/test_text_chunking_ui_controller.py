#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_chunking_ui_controller.py
@brief Text Chunking UI controller tests for AudioMancer.
@details Verifies the Text Chunking page UI controller drives modal progress
         lifecycle, deterministic chunking dispatch, and manual chunk saves
         correctly.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.4.2
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import text_chunking_ui_controller
from audiomancer.ui.main_window import MainWindow
from chunking_test_support import write_chunking_document


def test_text_chunking_ui_controller_start_operation_clears_dialog(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify direct controller-driven chunking operations close the modal progress dialog on success.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerChunkingProject",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 10,
    }
    project_workspace_service.save_manifest(manifest, project_root)

    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": None,
            "default_ai_chunking_strategy": "paragraph",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    success_payloads = []
    runner_calls = []

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
        _ = operation_name
        _ = initial_message
        _ = failure_handler
        _ = cancel_handler
        _ = cancellable
        runner_calls.append(operation_kind)
        set_busy(True)
        result_payload = worker_callable(
            window._current_project_root,
            dict(window._current_manifest),
            progress_callback=lambda *_args, **_kwargs: None,
            cancel_requested=lambda: False,
        )
        success_handler(result_payload)
        set_busy(False)

    monkeypatch.setattr(
        text_chunking_ui_controller.operation_runner_controller,
        "start_threaded_operation",
        _start_threaded_operation,
    )

    def _worker_callable(_project_root, _manifest, progress_callback=None, cancel_requested=None):
        """
        @brief      Provide the worker callable test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        progress_callback(1, 1, 100, "Completed.")
        assert cancel_requested() is False
        return {"status": "ok"}

    text_chunking_ui_controller.start_operation(
        window,
        operation_kind="chunking",
        operation_name="Deterministic Chunking",
        initial_message="Chunking...",
        worker_callable=_worker_callable,
        success_handler=lambda payload: success_payloads.append(payload),
        failure_handler=lambda error: (_ for _ in ()).throw(error),
    )

    assert success_payloads == [{"status": "ok"}]
    assert runner_calls == ["chunking"]
    assert window._operation_progress_dialog is None
    assert window._active_operation_kind is None


def test_text_chunking_ui_controller_chunk_request_uses_controller_start(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify deterministic chunking requests dispatch through the controller start-operation helper.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerChunkDispatchProject",
        tmp_path,
    )
    source_path = project_root / "story.txt"
    source_path.write_text("Story", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [config.CLEANED_TEXT_FILE_NAME]
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("Paragraph one.\n", encoding="utf-8")
    project_workspace_service.save_manifest(manifest, project_root)

    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": None,
            "default_ai_chunking_strategy": "paragraph",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    start_calls = []
    monkeypatch.setattr(
        text_chunking_ui_controller,
        "start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )

    text_chunking_ui_controller.handle_deterministic_chunking_requested(window)

    assert len(start_calls) == 1
    assert start_calls[0]["operation_kind"] == "chunking"


def test_text_chunking_ui_controller_completed_rerun_requires_confirmation(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify completed chunking reruns stop when the operator declines destructive confirmation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerChunkRerunProject",
        tmp_path,
    )
    source_path = project_root / "story.txt"
    source_path.write_text("Story", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [config.CLEANED_TEXT_FILE_NAME]
    manifest["operations"]["chunking"]["status"] = "completed"
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("Paragraph one.\n", encoding="utf-8")
    project_workspace_service.save_manifest(manifest, project_root)

    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": None,
            "default_ai_chunking_strategy": "paragraph",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    monkeypatch.setattr(text_chunking_ui_controller, "confirm_chunking_rerun", lambda *_args: False)
    start_calls = []
    monkeypatch.setattr(
        text_chunking_ui_controller,
        "start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )

    text_chunking_ui_controller.handle_deterministic_chunking_requested(window)

    assert start_calls == []


def test_text_chunking_ui_controller_ai_chunk_request_uses_selected_profile_and_strategy(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify AI-assisted chunking dispatches through the controller helper with one selected profile.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerAiChunkDispatchProject",
        tmp_path,
    )
    source_path = project_root / "story.txt"
    source_path.write_text("Story", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [config.CLEANED_TEXT_FILE_NAME]
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("Paragraph one.\n", encoding="utf-8")
    project_workspace_service.save_manifest(manifest, project_root)

    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [
                {
                    "id": "profile_1",
                    "label": "Chunking Profile",
                    "backend_kind": "lmstudio",
                    "base_url": "http://127.0.0.1:1234",
                    "api_key": "",
                    "model_name": "qwen3-8b",
                    "context_window": 4096,
                    "max_output_tokens": 512,
                    "request_timeout_seconds": 30,
                    "temperature": 0.2,
                    "supports_structured_output": False,
                    "enabled": True,
                }
            ],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": "profile_1",
            "default_ai_chunking_strategy": "scene",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    start_calls = []
    monkeypatch.setattr(
        text_chunking_ui_controller,
        "prompt_ai_chunking_instructions",
        lambda *_args: "Keep prologues separate.",
    )
    monkeypatch.setattr(
        text_chunking_ui_controller,
        "start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )
    chunking_call_kwargs: list[dict[str, object]] = []
    monkeypatch.setattr(
        text_chunking_ui_controller.ai_chunking_service,
        "chunk_text",
        lambda *_args, **kwargs: chunking_call_kwargs.append(dict(kwargs)) or {"chunking_mode": "ai_assisted"},
    )

    text_chunking_ui_controller.handle_ai_chunking_requested(window, "profile_1", "scene")

    assert len(start_calls) == 1
    assert start_calls[0]["operation_kind"] == "chunking"
    worker_callable = start_calls[0]["worker_callable"]
    result = worker_callable(project_root, project_workspace_service.load_manifest(project_root))
    assert result["chunking_mode"] == "ai_assisted"
    assert chunking_call_kwargs[0]["additional_chunking_instructions"] == "Keep prologues separate."


def test_text_chunking_ui_controller_ai_chunk_cancelled_resume_skips_confirmation(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify REQ-FUNC-001 cancelled AI chunking resumes without rerun confirmation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerAiChunkResumeProject",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [config.CLEANED_TEXT_FILE_NAME]
    manifest["operations"]["chunking"] = {
        "status": "cancelled",
        "mode": "ai_assisted",
        "metadata": {
            "ai_profile_id": "profile_1",
            "semantic_strategy": "scene",
        },
    }
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("Paragraph one.\n", encoding="utf-8")
    project_workspace_service.save_manifest(manifest, project_root)

    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [
                {
                    "id": "profile_1",
                    "label": "Chunking Profile",
                    "backend_kind": "lmstudio",
                    "base_url": "http://127.0.0.1:1234",
                    "api_key": "",
                    "model_name": "qwen3-8b",
                    "context_window": 4096,
                    "max_output_tokens": 512,
                    "request_timeout_seconds": 30,
                    "temperature": 0.2,
                    "supports_structured_output": False,
                    "enabled": True,
                }
            ],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": "profile_1",
            "default_ai_chunking_strategy": "scene",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    confirm_calls = []
    monkeypatch.setattr(
        text_chunking_ui_controller,
        "confirm_ai_chunking_rerun",
        lambda *_args: confirm_calls.append("rerun") or True,
    )
    start_calls = []
    monkeypatch.setattr(
        text_chunking_ui_controller,
        "start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )
    monkeypatch.setattr(
        text_chunking_ui_controller.ai_chunking_service,
        "load_operation_state",
        lambda _project_root: {
            "metadata": {
                "ai_profile_id": "profile_1",
                "semantic_strategy": "scene",
            }
        },
    )

    text_chunking_ui_controller.handle_ai_chunking_requested(window, "profile_1", "scene")

    assert confirm_calls == []
    assert len(start_calls) == 1


def test_text_chunking_ui_controller_ai_chunk_resume_uses_selected_profile(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify interrupted AI chunking resumes with the currently selected AI profile.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerAiChunkSelectedProfileResumeProject",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-30T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [config.CLEANED_TEXT_FILE_NAME]
    manifest["operations"]["chunking"] = {
        "status": "running",
        "mode": "ai_assisted",
        "metadata": {
            "ai_profile_id": "profile_1",
            "semantic_strategy": "scene",
        },
    }
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("Paragraph one.\n", encoding="utf-8")
    project_workspace_service.save_manifest(manifest, project_root)

    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [
                {
                    "id": "profile_1",
                    "label": "Original Chunking Profile",
                    "backend_kind": "lmstudio",
                    "base_url": "http://127.0.0.1:1234",
                    "api_key": "",
                    "model_name": "qwen3-8b",
                    "context_window": 4096,
                    "max_output_tokens": 512,
                    "request_timeout_seconds": 30,
                    "temperature": 0.2,
                    "supports_structured_output": False,
                    "enabled": True,
                },
                {
                    "id": "profile_2",
                    "label": "Selected Chunking Profile",
                    "backend_kind": "lmstudio",
                    "base_url": "http://127.0.0.1:1234",
                    "api_key": "",
                    "model_name": "qwen3-14b",
                    "context_window": 8192,
                    "max_output_tokens": 768,
                    "request_timeout_seconds": 30,
                    "temperature": 0.4,
                    "supports_structured_output": False,
                    "enabled": True,
                },
            ],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": "profile_2",
            "default_ai_chunking_strategy": "scene",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    captured_profiles = []
    monkeypatch.setattr(
        text_chunking_ui_controller.ai_chunking_service,
        "chunk_text",
        lambda _project_root, _manifest, ai_profile, _strategy, **_kwargs: (
            captured_profiles.append(ai_profile) or {"chunking_mode": "ai_assisted"}
        ),
    )

    def _start_operation(_window, **kwargs):
        """
        @brief      Provide the start operation test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        kwargs["worker_callable"](project_root, project_workspace_service.load_manifest(project_root))

    monkeypatch.setattr(text_chunking_ui_controller, "start_operation", _start_operation)

    text_chunking_ui_controller.handle_ai_chunking_requested(window, "profile_2", "scene")

    assert len(captured_profiles) == 1
    assert captured_profiles[0]["id"] == "profile_2"
    assert captured_profiles[0]["model_name"] == "qwen3-14b"


def test_text_chunking_ui_controller_save_chunk_updates_project_state(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify manual selected-chunk save persists the edit and refreshes project state.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerChunkEditProject",
        tmp_path,
    )
    chunking_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    chunking_root.mkdir(exist_ok=True)
    chunk_artifact_path = chunking_root / config.CHUNK_ARTIFACT_FILE_NAME
    write_chunking_document(
        chunking_root,
        [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Original chunk"}],
    )
    manifest["current_stage"] = "character_discovery_ready"
    manifest["operations"]["chunking"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": None,
            "default_ai_chunking_strategy": "paragraph",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    status_messages: list[str] = []
    monkeypatch.setattr(
        text_chunking_ui_controller.misc_ui_controller,
        "show_message",
        lambda _window, message: status_messages.append(message),
    )
    restored_scroll_states: list[dict[str, int]] = []
    monkeypatch.setattr(
        window._text_chunking_page,
        "preview_scroll_state",
        lambda: {
            "cleaned_vertical": 12,
            "cleaned_horizontal": 1,
            "chunk_list_vertical": 7,
            "chunk_list_horizontal": 0,
            "chunk_list_row": 0,
        },
    )
    monkeypatch.setattr(
        window._text_chunking_page,
        "restore_preview_scroll_state",
        restored_scroll_states.append,
    )

    text_chunking_ui_controller.handle_save_chunk_requested(window, "chunk-0001", "Edited chunk")

    document = json.loads(chunk_artifact_path.read_text(encoding="utf-8"))
    assert document["chunks"][0]["text"] == "Edited chunk"
    assert document["manual_adjusted"] is True
    assert window._current_manifest["current_stage"] == "translation_ready"
    assert restored_scroll_states == [
        {
            "cleaned_vertical": 12,
            "cleaned_horizontal": 1,
            "chunk_list_vertical": 7,
            "chunk_list_horizontal": 0,
            "chunk_list_row": 0,
        }
    ]
    assert status_messages == ["Chunk saved."]


# END OF FILE
