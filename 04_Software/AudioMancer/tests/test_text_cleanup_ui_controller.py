#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_cleanup_ui_controller.py
@brief Text Cleanup UI controller tests for AudioMancer.
@details Verifies the Text Cleanup page UI controller still drives modal
         progress lifecycle, extraction dispatch, and manual cleaned-text
         save dispatch and preview scroll preservation correctly.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.5.0
"""

# IMPORTS

from audiomancer import config
from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import text_cleanup_ui_controller
from audiomancer.ui.main_window import MainWindow

# PUBLIC API


def test_text_cleanup_ui_controller_start_operation_clears_dialog(
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify direct controller-driven operations close the modal progress dialog on success.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerOperationProject",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 10,
    }
    project_workspace_service.save_manifest(manifest, project_root)

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    success_payloads = []

    def _worker_callable(_project_root, _manifest, progress_callback=None, cancel_requested=None):
        progress_callback(1, 1, 100, "Completed.")
        assert cancel_requested() is False
        return {"status": "ok"}

    text_cleanup_ui_controller.start_operation(
        window,
        operation_kind="extraction",
        operation_name="Extract Text",
        initial_message="Extracting...",
        worker_callable=_worker_callable,
        success_handler=lambda payload: success_payloads.append(payload),
        failure_handler=lambda error: (_ for _ in ()).throw(error),
    )

    assert success_payloads == [{"status": "ok"}]
    assert window._operation_progress_dialog is None
    assert window._active_operation_kind is None


def test_text_cleanup_ui_controller_extract_request_uses_controller_start(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify extraction requests dispatch through the controller start-operation helper.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerDispatchProject",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 10,
    }
    project_workspace_service.save_manifest(manifest, project_root)

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    start_calls = []
    monkeypatch.setattr(
        text_cleanup_ui_controller,
        "start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )

    text_cleanup_ui_controller.handle_extract_text_requested(window)

    assert len(start_calls) == 1
    assert start_calls[0]["operation_kind"] == "extraction"


def test_text_cleanup_ui_controller_ai_cleanup_request_uses_selected_profile(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify AI-assisted cleanup dispatches through the controller helper with one selected profile.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerAiCleanupProject",
        tmp_path,
    )
    extracted_path = project_root / "00_extraction" / "output_raw_text.txt"
    extracted_path.parent.mkdir(parents=True, exist_ok=True)
    extracted_path.write_text("Paragraph one.\n\nParagraph two.\n", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["extracted_text_relative_path"] = "00_extraction/output_raw_text.txt"
    project_workspace_service.save_manifest(manifest, project_root)

    settings_payload = dict(default_settings_payload)
    settings_payload["llm_profiles"] = [
        {
            "id": "profile_1",
            "label": "Cleanup Profile",
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
            "discovered_model_name": "",
            "discovered_context_window": None,
            "discovery_succeeded": False,
            "discovery_message": "",
            "user_overrode_model_name": False,
            "user_overrode_context_window": False,
        }
    ]
    settings_payload["default_ai_cleanup_profile_id"] = "profile_1"

    window = MainWindow(settings_payload=settings_payload)
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    start_calls = []
    monkeypatch.setattr(text_cleanup_ui_controller, "confirm_ai_cleanup_start", lambda *_args: True)
    monkeypatch.setattr(
        text_cleanup_ui_controller, "start_operation", lambda _window, **kwargs: start_calls.append(kwargs)
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller.ai_cleanup_service,
        "clean_text",
        lambda *_args, **_kwargs: {"cleanup_mode": "ai_assisted"},
    )

    text_cleanup_ui_controller.handle_ai_cleanup_requested(window, "profile_1")

    assert len(start_calls) == 1
    assert start_calls[0]["operation_kind"] == "cleanup"
    worker_callable = start_calls[0]["worker_callable"]
    result = worker_callable(project_root, project_workspace_service.load_manifest(project_root))
    assert result["cleanup_mode"] == "ai_assisted"


def test_text_cleanup_ui_controller_ai_cleanup_resume_skips_confirmations(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify interrupted AI cleanup resumes without start or rerun confirmations.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerAiCleanupResumeProject",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["extracted_text_relative_path"] = "00_extraction/output_raw_text.txt"
    manifest["operations"] = {
        "cleanup": {
            "folder_relative_path": "10_cleanup",
            "status": "running",
            "mode": "ai_assisted",
            "metadata": {"ai_profile_id": "profile_1"},
        }
    }
    project_workspace_service.save_manifest(manifest, project_root)

    settings_payload = dict(default_settings_payload)
    settings_payload["llm_profiles"] = [
        {
            "id": "profile_1",
            "label": "Cleanup Profile",
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
            "discovered_model_name": "",
            "discovered_context_window": None,
            "discovery_succeeded": False,
            "discovery_message": "",
            "user_overrode_model_name": False,
            "user_overrode_context_window": False,
        }
    ]
    settings_payload["default_ai_cleanup_profile_id"] = "profile_1"

    window = MainWindow(settings_payload=settings_payload)
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    confirm_calls: list[str] = []
    monkeypatch.setattr(
        text_cleanup_ui_controller, "confirm_ai_cleanup_start", lambda *_args: confirm_calls.append("start") or True
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller, "confirm_ai_cleanup_rerun", lambda *_args: confirm_calls.append("rerun") or True
    )
    start_calls = []
    monkeypatch.setattr(
        text_cleanup_ui_controller, "start_operation", lambda _window, **kwargs: start_calls.append(kwargs)
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller.ai_cleanup_service,
        "load_operation_state",
        lambda _project_root: {"metadata": {"ai_profile_id": "profile_1"}},
    )

    text_cleanup_ui_controller.handle_ai_cleanup_requested(window, "profile_1")

    assert confirm_calls == []
    assert len(start_calls) == 1


def test_text_cleanup_ui_controller_save_cleaned_text_updates_project_state(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify manual cleaned-text save persists the edit and refreshes project state.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerCleanupEditProject",
        tmp_path,
    )
    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
    cleanup_root.mkdir(exist_ok=True)
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text("Clean text\n", encoding="utf-8")
    extraction_root = project_root / config.EXTRACTION_FOLDER_NAME
    extraction_root.mkdir(exist_ok=True)
    (extraction_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("Raw text\n", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": f"{config.EXTRACTION_FOLDER_NAME}/story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-24T00:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["extracted_text_relative_path"] = f"{config.EXTRACTION_FOLDER_NAME}/{config.EXTRACTED_TEXT_FILE_NAME}"
    manifest["current_stage"] = "text_chunking_ready"
    manifest["operations"]["cleanup"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    status_messages: list[str] = []
    monkeypatch.setattr(
        text_cleanup_ui_controller.misc_ui_controller,
        "show_message",
        lambda _window, message: status_messages.append(message),
    )
    restored_scroll_states: list[dict[str, tuple[int, int]]] = []
    monkeypatch.setattr(
        window._text_cleanup_page,
        "preview_scroll_state",
        lambda: {"extracted": (42, 3), "cleaned": (7, 1)},
    )
    monkeypatch.setattr(
        window._text_cleanup_page,
        "restore_preview_scroll_state",
        restored_scroll_states.append,
    )

    text_cleanup_ui_controller.handle_save_cleaned_text_requested(window, "Edited clean text\n")

    assert (cleanup_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8") == "Edited clean text\n"
    assert window._current_manifest["current_stage"] == "text_cleanup_ready"
    assert restored_scroll_states == [{"extracted": (42, 3), "cleaned": (7, 1)}]
    assert status_messages == ["Cleaned text saved."]


# END OF FILE
