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
@version 0.5.1
"""

# IMPORTS

import pytest

from audiomancer import config
from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import text_cleanup_ui_controller
from audiomancer.ui.main_window import MainWindow

# PUBLIC API


def test_text_cleanup_ui_controller_start_operation_clears_dialog(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify direct controller-driven operations close the modal progress dialog on success.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
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
        text_cleanup_ui_controller.operation_runner_controller,
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
    assert runner_calls == ["extraction"]
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
    @date       2026-05-12
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerAiCleanupProject",
        tmp_path,
    )
    extracted_path = project_root / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text("Paragraph one.\n\nParagraph two.\n", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 10,
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

    start_calls = []
    monkeypatch.setattr(text_cleanup_ui_controller, "confirm_ai_cleanup_start", lambda *_args: True)
    monkeypatch.setattr(
        text_cleanup_ui_controller,
        "prompt_ai_cleanup_instructions",
        lambda *_args: "Keep glossary terms unchanged.",
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller, "start_operation", lambda _window, **kwargs: start_calls.append(kwargs)
    )
    cleanup_call_kwargs: list[dict[str, object]] = []
    monkeypatch.setattr(
        text_cleanup_ui_controller.ai_cleanup_service,
        "clean_text",
        lambda *_args, **kwargs: cleanup_call_kwargs.append(dict(kwargs)) or {"cleanup_mode": "ai_assisted"},
    )

    text_cleanup_ui_controller.handle_ai_cleanup_requested(window, "profile_1")

    assert len(start_calls) == 1
    assert start_calls[0]["operation_kind"] == "cleanup"
    worker_callable = start_calls[0]["worker_callable"]
    result = worker_callable(project_root, project_workspace_service.load_manifest(project_root))
    assert result["cleanup_mode"] == "ai_assisted"
    assert cleanup_call_kwargs[0]["additional_cleanup_instructions"] == "Keep glossary terms unchanged."


def test_text_cleanup_ui_controller_cancelled_optional_instructions_restore_action_state(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify AICU-001 and REQ-UX-037 restore cleanup actions after prompt cancellation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerAiCleanupPromptCancelProject",
        tmp_path,
    )
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("Paragraph one.\n", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 10,
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
    window._text_cleanup_page.set_processing_state(
        extracted_text="Paragraph one.",
        cleaned_text=None,
        notes=["Cleanup ready"],
        can_extract=True,
        can_clean=True,
        can_ai_clean=True,
    )
    window._text_cleanup_page.set_ai_profiles([("Cleanup Profile", "profile_1")], "profile_1")

    monkeypatch.setattr(text_cleanup_ui_controller, "confirm_ai_cleanup_start", lambda *_args: True)
    monkeypatch.setattr(
        text_cleanup_ui_controller,
        "start_operation",
        lambda *_args, **_kwargs: pytest.fail("must not start"),
    )

    def _cancel_prompt(*_args):
        window._text_cleanup_page.set_busy(True, "AI-Assisted Cleanup")
        return None

    monkeypatch.setattr(text_cleanup_ui_controller, "prompt_ai_cleanup_instructions", _cancel_prompt)

    text_cleanup_ui_controller.handle_ai_cleanup_requested(window, "profile_1")

    assert window._active_operation_kind is None
    assert window._text_cleanup_page._busy is False
    assert window._text_cleanup_page._ai_clean_button.isEnabled() is True


def test_text_cleanup_ui_controller_ai_cleanup_resume_skips_confirmations(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify interrupted AI cleanup resumes with the currently selected profile.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ControllerAiCleanupResumeProject",
        tmp_path,
    )
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("Paragraph one.\n", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"] = {
        "cleanup": {
            "status": "running",
            "mode": "ai_assisted",
            "metadata": {"ai_profile_id": "profile_1", "model_settings": {"model_name": "qwen3-8b"}},
        }
    }
    project_workspace_service.save_manifest(manifest, project_root)

    settings_payload = dict(default_settings_payload)
    base_profile = {
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
    selected_profile = {
        **base_profile,
        "id": "profile_2",
        "label": "Selected Cleanup Profile",
        "model_name": "qwen3-14b",
        "temperature": 0.7,
    }
    settings_payload["llm_profiles"] = [base_profile, selected_profile]
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
    cleaned_profiles: list[dict[str, object]] = []
    monkeypatch.setattr(
        text_cleanup_ui_controller.ai_cleanup_service,
        "clean_text",
        lambda _project_root, _manifest, profile, **_kwargs: (
            cleaned_profiles.append(dict(profile)) or {"cleanup_mode": "ai_assisted"}
        ),
    )

    text_cleanup_ui_controller.handle_ai_cleanup_requested(window, "profile_2")

    assert confirm_calls == []
    assert len(start_calls) == 1
    worker_callable = start_calls[0]["worker_callable"]
    worker_callable(project_root, project_workspace_service.load_manifest(project_root))
    assert cleaned_profiles[0]["id"] == "profile_2"
    assert cleaned_profiles[0]["model_name"] == "qwen3-14b"


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
    cleanup_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    cleanup_root.mkdir(exist_ok=True)
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text("Clean text\n", encoding="utf-8")
    extraction_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    extraction_root.mkdir(exist_ok=True)
    (extraction_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("Raw text\n", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-24T00:00:00+00:00",
        "size_bytes": 10,
    }
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


def test_text_cleanup_ui_controller_applies_spacing_and_refreshes_project_state(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify AISP-002/AISP-003 and REQ-FUNC-061 controller spacing application.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ControllerSpacingProject", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, manifest)
    applied_selections: list[list[str]] = []

    def _apply_spacing(_project_root, current_manifest, selected_categories):
        """Capture the spacing request and return a refreshed manifest fixture."""
        applied_selections.append(list(selected_categories))
        return {**current_manifest, "current_stage": "text_cleanup_ready"}

    monkeypatch.setattr(
        text_cleanup_ui_controller.text_cleanup_state_service,
        "apply_ai_cleanup_spacing",
        _apply_spacing,
    )
    monkeypatch.setattr(window._text_cleanup_page, "preview_scroll_state", lambda: {"cleaned": (9, 2)})
    restored_scroll_states: list[dict[str, tuple[int, int]]] = []
    monkeypatch.setattr(
        window._text_cleanup_page,
        "restore_preview_scroll_state",
        restored_scroll_states.append,
    )
    status_messages: list[str] = []
    monkeypatch.setattr(
        text_cleanup_ui_controller.misc_ui_controller,
        "show_message",
        lambda _window, message: status_messages.append(message),
    )

    text_cleanup_ui_controller.handle_apply_ai_cleanup_spacing_requested(
        window,
        ["heading", "noise", "footer"],
    )

    assert applied_selections == [["heading", "noise", "footer"]]
    assert window._current_manifest["current_stage"] == "text_cleanup_ready"
    assert restored_scroll_states == [{"cleaned": (9, 2)}]
    assert status_messages == ["AI cleanup spacing applied."]


# END OF FILE
