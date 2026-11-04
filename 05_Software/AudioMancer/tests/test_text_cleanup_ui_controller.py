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
@brief Controller tests for the single Cleanup command.
@details Verifies threaded-runner argument ownership and optional AI profile
         forwarding from the Cleanup page controller.
"""

# IMPORTS

from types import SimpleNamespace

import pytest

from audiomancer.ui.controllers import text_cleanup_ui_controller
from audiomancer.ui.pages.text_cleanup_page import TextCleanupPage

# PUBLIC API


def test_extraction_controller_leaves_project_arguments_for_threaded_runner(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify the shared runner supplies Extraction project arguments.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    captured: dict[str, object] = {}
    window = SimpleNamespace(
        _current_project_root=tmp_path,
        _current_manifest={"source_document": {"original_name": "story.txt"}},
        _settings_payload={"language": "en"},
    )
    monkeypatch.setattr(text_cleanup_ui_controller, "_completed_extraction_available", lambda _root: False)

    def _start(_window, operation_kind, _name, _message, worker, _success, _failure):
        """
        @brief      Capture the Extraction operation and worker callable.
        @param[in]  _window Window test double unused by this helper.
        @param[in]  operation_kind Operation identifier under test.
        @param[in]  _name Operation name unused by this helper.
        @param[in]  _message Progress message unused by this helper.
        @param[in]  worker Worker callable under test.
        @param[in]  _success Success callback unused by this helper.
        @param[in]  _failure Failure callback unused by this helper.
        @return     None.
        @exception  None
        """
        captured["kind"] = operation_kind
        captured["worker"] = worker

    monkeypatch.setattr(text_cleanup_ui_controller, "start_operation", _start)

    text_cleanup_ui_controller.handle_extract_text_requested(window)

    assert captured == {
        "kind": "extraction",
        "worker": text_cleanup_ui_controller.text_extraction_service.extract_text,
    }


def test_cleanup_controller_passes_optional_selected_profile(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Cleanup forwards the optional selected AI profile.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    captured: dict[str, object] = {}
    window = SimpleNamespace(
        _current_project_root=tmp_path,
        _current_manifest={"source_document": {"original_name": "story.txt"}},
        _settings_payload={
            "language": "en",
            "llm_profiles": [
                {
                    "id": "local",
                    "enabled": True,
                    "model_name": "Qwen3.6-27B",
                    "context_window": 32768,
                    "supports_structured_output": True,
                }
            ],
        },
    )
    monkeypatch.setattr(text_cleanup_ui_controller, "_completed_extraction_available", lambda _root: True)
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_cleanup_service,
        "load_cleanup_document",
        lambda _root: None,
    )

    def _start(_window, operation_kind, _name, _message, worker, _success, _failure):
        """
        @brief      Capture the Cleanup operation and partially bound worker.
        @param[in]  _window Window test double unused by this helper.
        @param[in]  operation_kind Operation identifier under test.
        @param[in]  _name Operation name unused by this helper.
        @param[in]  _message Progress message unused by this helper.
        @param[in]  worker Partially bound Cleanup worker under test.
        @param[in]  _success Success callback unused by this helper.
        @param[in]  _failure Failure callback unused by this helper.
        @return     None.
        @exception  None
        """
        captured["kind"] = operation_kind
        captured["worker"] = worker

    monkeypatch.setattr(text_cleanup_ui_controller, "start_operation", _start)
    text_cleanup_ui_controller.handle_cleanup_requested(window, "local")

    assert captured["kind"] == "cleanup"
    assert captured["worker"].func is text_cleanup_ui_controller.text_cleanup_service.clean_text
    assert captured["worker"].keywords["ai_profile_payload"]["model_name"] == "Qwen3.6-27B"


def test_completed_cleanup_rerun_decline_keeps_manifest_and_starts_no_worker(monkeypatch, tmp_path) -> None:
    """@brief Verify declining completed Cleanup rerun leaves the active state untouched."""
    manifest = {"source_document": {"original_name": "story.txt"}, "marker": "original"}
    window = SimpleNamespace(
        _current_project_root=tmp_path,
        _current_manifest=manifest,
        _settings_payload={"language": "en"},
    )
    reset_calls: list[object] = []
    starts: list[object] = []
    monkeypatch.setattr(text_cleanup_ui_controller, "_completed_extraction_available", lambda _root: True)
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_cleanup_service,
        "load_cleanup_document",
        lambda _root: {"status": "completed"},
    )
    monkeypatch.setattr(text_cleanup_ui_controller, "_confirm", lambda *_args: False)
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_cleanup_state_service,
        "reset_cleanup",
        lambda *_args: reset_calls.append("reset"),
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller,
        "start_operation",
        lambda *_args: starts.append("started"),
    )

    text_cleanup_ui_controller.handle_cleanup_requested(window, None)

    assert window._current_manifest is manifest
    assert reset_calls == []
    assert starts == []


def test_completed_cleanup_rerun_resets_before_starting_with_reset_manifest(monkeypatch, tmp_path) -> None:
    """@brief Verify confirmed completed Cleanup rerun installs the reset manifest first."""
    original_manifest = {"source_document": {"original_name": "story.txt"}, "marker": "original"}
    reset_manifest = {"source_document": {"original_name": "story.txt"}, "marker": "reset"}
    window = SimpleNamespace(
        _current_project_root=tmp_path,
        _current_manifest=original_manifest,
        _settings_payload={"language": "en"},
    )
    events: list[str] = []
    captured: dict[str, object] = {}
    monkeypatch.setattr(text_cleanup_ui_controller, "_completed_extraction_available", lambda _root: True)
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_cleanup_service,
        "load_cleanup_document",
        lambda _root: {"status": "completed"},
    )
    monkeypatch.setattr(text_cleanup_ui_controller, "_confirm", lambda *_args: True)

    def _reset(root, manifest):
        """@brief Capture the completed Cleanup reset before worker startup."""
        assert root == tmp_path
        assert manifest is original_manifest
        events.append("reset")
        return reset_manifest

    def _start(_window, operation_kind, _name, _message, worker, _success, _failure):
        """@brief Verify the Cleanup worker receives the reset manifest."""
        assert operation_kind == "cleanup"
        assert events == ["reset"]
        assert window._current_manifest is reset_manifest
        captured["worker"] = worker

    monkeypatch.setattr(text_cleanup_ui_controller.text_cleanup_state_service, "reset_cleanup", _reset)
    monkeypatch.setattr(text_cleanup_ui_controller, "start_operation", _start)

    text_cleanup_ui_controller.handle_cleanup_requested(window, None)

    assert captured["worker"].func is text_cleanup_ui_controller.text_cleanup_service.clean_text
    assert window._current_manifest is reset_manifest


@pytest.mark.parametrize("status", ["running", "paused", "finalizing", "failed"])
def test_resumable_cleanup_starts_without_destructive_reset(monkeypatch, tmp_path, status: str) -> None:
    """@brief Verify an unfinished Cleanup document retains its checkpoint when started."""
    checkpoint = tmp_path / "cleanup.json"
    checkpoint.write_text('{"status": "paused"}', encoding="utf-8")
    window = SimpleNamespace(
        _current_project_root=tmp_path,
        _current_manifest={"source_document": {"original_name": "story.txt"}},
        _settings_payload={"language": "en"},
    )
    reset_calls: list[object] = []
    starts: list[object] = []
    monkeypatch.setattr(text_cleanup_ui_controller, "_completed_extraction_available", lambda _root: True)
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_cleanup_service,
        "load_cleanup_document",
        lambda _root: {"status": status},
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller,
        "_confirm",
        lambda *_args: (_ for _ in ()).throw(AssertionError("resumable Cleanup must not confirm rerun")),
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_cleanup_state_service,
        "reset_cleanup",
        lambda *_args: reset_calls.append("reset"),
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller,
        "start_operation",
        lambda *_args: starts.append("started"),
    )

    text_cleanup_ui_controller.handle_cleanup_requested(window, None)

    assert checkpoint.is_file()
    assert reset_calls == []
    assert starts == ["started"]


def test_completed_cleanup_rerun_reset_failure_starts_no_worker(monkeypatch, tmp_path) -> None:
    """@brief Verify a failed completed-rerun reset cannot start or report Cleanup success."""
    window = SimpleNamespace(
        _current_project_root=tmp_path,
        _current_manifest={"source_document": {"original_name": "story.txt"}},
        _settings_payload={"language": "en"},
    )
    starts: list[object] = []
    warnings: list[tuple[object, ...]] = []
    monkeypatch.setattr(text_cleanup_ui_controller, "_completed_extraction_available", lambda _root: True)
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_cleanup_service,
        "load_cleanup_document",
        lambda _root: {"status": "completed"},
    )
    monkeypatch.setattr(text_cleanup_ui_controller, "_confirm", lambda *_args: True)
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_cleanup_state_service,
        "reset_cleanup",
        lambda *_args: (_ for _ in ()).throw(OSError("reset failed")),
    )
    monkeypatch.setattr(text_cleanup_ui_controller, "start_operation", lambda *_args: starts.append("started"))
    monkeypatch.setattr(text_cleanup_ui_controller.QMessageBox, "warning", lambda *args: warnings.append(args))

    text_cleanup_ui_controller.handle_cleanup_requested(window, None)

    assert starts == []
    assert warnings[-1][2] == "reset failed"


def test_failed_cleaned_text_save_keeps_editable_draft(monkeypatch, qtbot, tmp_path) -> None:
    """@brief Verify the controller does not discard a Cleanup draft after save failure."""
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_processing_state("source", "saved", [], True, True, True, "passed", 0)
    page._edit_cleaned_button.click()
    page._cleaned_text_edit.setPlainText("draft that failed to save")
    window = SimpleNamespace(
        _current_project_root=tmp_path,
        _current_manifest={"source_document": {"original_name": "story.txt"}},
        _settings_payload={"language": "en"},
        _text_cleanup_page=page,
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_cleanup_state_service,
        "save_cleaned_text_edit",
        lambda *_args: (_ for _ in ()).throw(ValueError("save failed")),
    )
    monkeypatch.setattr(text_cleanup_ui_controller.QMessageBox, "warning", lambda *_args: None)

    text_cleanup_ui_controller.handle_save_cleaned_text_requested(window, "draft that failed to save")

    assert page._editing_cleaned_text is True
    assert page._cleaned_text_edit.isReadOnly() is False
    assert page._cleaned_text_edit.toPlainText() == "draft that failed to save"


def test_successful_cleaned_text_save_exits_edit_mode_before_refresh(monkeypatch, qtbot, tmp_path) -> None:
    """@brief Verify a persisted Cleanup correction returns the refreshed editor to read-only mode."""
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_processing_state("source", "saved before edit", [], True, True, True, "passed", 0)
    page._edit_cleaned_button.click()
    page._cleaned_text_edit.setPlainText("saved operator correction")
    updated_manifest = {"source_document": {"original_name": "story.txt"}, "current_stage": "text_chunking_ready"}
    state_updates: list[tuple[object, object]] = []
    messages: list[object] = []

    def show_project_state(project_root, manifest) -> None:
        """@brief Project the persisted correction into the page during the controller refresh."""
        state_updates.append((project_root, manifest))
        page.set_processing_state(
            "source",
            "saved operator correction",
            [],
            True,
            True,
            True,
            "passed",
            0,
        )

    window = SimpleNamespace(
        _current_project_root=tmp_path,
        _current_manifest={"source_document": {"original_name": "story.txt"}},
        _settings_payload={"language": "en"},
        _text_cleanup_page=page,
        show_project_state=show_project_state,
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_cleanup_state_service,
        "save_cleaned_text_edit",
        lambda *_args: updated_manifest,
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller.misc_ui_controller,
        "show_message",
        lambda *_args: messages.append(_args[-1]),
    )

    text_cleanup_ui_controller.handle_save_cleaned_text_requested(window, "saved operator correction")

    assert state_updates == [(tmp_path, updated_manifest)]
    assert page._editing_cleaned_text is False
    assert page._cleaned_text_edit.isReadOnly() is True
    assert page._cleaned_text_edit.toPlainText() == "saved operator correction"
    assert page._saved_cleaned_text == "saved operator correction"
    assert page._edit_cleaned_button.isEnabled() is True
    assert page._save_cleaned_button.isEnabled() is False
    assert page._cancel_edit_button.isEnabled() is False
    assert messages == ["Cleaned text saved."]


def test_extraction_rerun_defers_reset_until_worker_publication(monkeypatch, tmp_path):
    """@brief Confirmation starts the worker with original files and manifest, after pending edits settle."""
    events = []
    manifest = {"marker": "original"}
    window = SimpleNamespace(
        _current_project_root=tmp_path,
        _current_manifest=manifest,
        _settings_payload={"language": "en"},
        _ai_translation_page=SimpleNamespace(flush_pending_translation_edit=lambda: events.append("flush")),
        stop_all_audio_playback=lambda: events.append("stop"),
    )
    monkeypatch.setattr(text_cleanup_ui_controller, "_completed_extraction_available", lambda _root: True)
    monkeypatch.setattr(text_cleanup_ui_controller, "_confirm", lambda *_args: True)
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_extraction_service,
        "reset_extraction_and_downstream",
        lambda *_args: pytest.fail("Controller reset live results before extraction"),
    )
    monkeypatch.setattr(text_cleanup_ui_controller, "start_operation", lambda *_args: events.append("start"))
    text_cleanup_ui_controller.handle_extract_text_requested(window)
    assert events == ["flush", "stop", "start"]
    assert window._current_manifest is manifest


def test_busy_extraction_request_does_not_prompt_or_reset(monkeypatch, tmp_path):
    """@brief Reject direct extraction requests before any confirmation while an operation is active."""
    window = SimpleNamespace(_current_project_root=tmp_path, _current_manifest={}, _active_operation_kind="cleanup")
    monkeypatch.setattr(text_cleanup_ui_controller, "_confirm", lambda *_args: pytest.fail("Unexpected prompt"))
    monkeypatch.setattr(text_cleanup_ui_controller, "start_operation", lambda *_args: pytest.fail("Unexpected worker"))
    text_cleanup_ui_controller.handle_extract_text_requested(window)


# END OF FILE
