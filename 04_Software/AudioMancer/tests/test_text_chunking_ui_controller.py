#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
         lifecycle and deterministic chunking dispatch correctly.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.2.0
"""

# IMPORTS

from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import text_chunking_ui_controller
from audiomancer.ui.main_window import MainWindow


def test_text_chunking_ui_controller_start_operation_clears_dialog(
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify direct controller-driven chunking operations close the modal progress dialog on success.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
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

    def _worker_callable(_project_root, _manifest, progress_callback=None, cancel_requested=None):
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
    @version    0.1.0
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
    manifest["operations"]["cleanup"]["output_paths"] = ["10_cleanup/output_clean_text.txt"]
    cleanup_root = project_root / "10_cleanup"
    cleanup_root.mkdir(exist_ok=True)
    (cleanup_root / "output_clean_text.txt").write_text("Paragraph one.\n", encoding="utf-8")
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
    @date       2026-04-07
    @version    0.1.0
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
    manifest["operations"]["cleanup"]["output_paths"] = ["10_cleanup/output_clean_text.txt"]
    manifest["operations"]["chunking"]["status"] = "completed"
    cleanup_root = project_root / "10_cleanup"
    cleanup_root.mkdir(exist_ok=True)
    (cleanup_root / "output_clean_text.txt").write_text("Paragraph one.\n", encoding="utf-8")
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
    @brief      Verify AI-assisted chunking dispatches through the controller helper with one selected profile and strategy.
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
    manifest["operations"]["cleanup"]["output_paths"] = ["10_cleanup/output_clean_text.txt"]
    cleanup_root = project_root / "10_cleanup"
    cleanup_root.mkdir(exist_ok=True)
    (cleanup_root / "output_clean_text.txt").write_text("Paragraph one.\n", encoding="utf-8")
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
        "start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )
    monkeypatch.setattr(
        text_chunking_ui_controller.ai_chunking_service,
        "chunk_text",
        lambda *_args, **_kwargs: {"chunking_mode": "ai_assisted"},
    )

    text_chunking_ui_controller.handle_ai_chunking_requested(window, "profile_1", "scene")

    assert len(start_calls) == 1
    assert start_calls[0]["operation_kind"] == "chunking"
    worker_callable = start_calls[0]["worker_callable"]
    result = worker_callable(project_root, project_workspace_service.load_manifest(project_root))
    assert result["chunking_mode"] == "ai_assisted"


def test_text_chunking_ui_controller_ai_chunk_resume_skips_confirmation(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify interrupted AI chunking resumes without rerun confirmation.
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
    manifest["operations"]["cleanup"]["output_paths"] = ["10_cleanup/output_clean_text.txt"]
    manifest["operations"]["chunking"] = {
        "folder_relative_path": "20_chunking",
        "status": "running",
        "mode": "ai_assisted",
        "metadata": {
            "ai_profile_id": "profile_1",
            "semantic_strategy": "scene",
        },
    }
    cleanup_root = project_root / "10_cleanup"
    cleanup_root.mkdir(exist_ok=True)
    (cleanup_root / "output_clean_text.txt").write_text("Paragraph one.\n", encoding="utf-8")
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


# END OF FILE
