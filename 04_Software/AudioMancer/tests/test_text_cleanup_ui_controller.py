#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
"""Controller tests for the single Cleanup V2 command."""

from types import SimpleNamespace

from audiomancer.ui.controllers import text_cleanup_ui_controller


def test_extraction_controller_leaves_project_arguments_for_threaded_runner(monkeypatch, tmp_path) -> None:
    """The shared runner, not the controller, supplies project root and manifest."""
    captured: dict[str, object] = {}
    window = SimpleNamespace(
        _current_project_root=tmp_path,
        _current_manifest={"source_document": {"original_name": "story.txt"}},
        _settings_payload={"language": "en"},
    )
    monkeypatch.setattr(text_cleanup_ui_controller, "_completed_extraction_available", lambda _root: False)

    def _start(_window, operation_kind, _name, _message, worker, _success, _failure):
        captured["kind"] = operation_kind
        captured["worker"] = worker

    monkeypatch.setattr(text_cleanup_ui_controller, "start_operation", _start)

    text_cleanup_ui_controller.handle_extract_text_requested(window)

    assert captured == {
        "kind": "extraction",
        "worker": text_cleanup_ui_controller.text_extraction_service.extract_text,
    }


def test_cleanup_controller_passes_optional_selected_profile(monkeypatch, tmp_path) -> None:
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
        captured["kind"] = operation_kind
        captured["worker"] = worker

    monkeypatch.setattr(text_cleanup_ui_controller, "start_operation", _start)
    text_cleanup_ui_controller.handle_cleanup_requested(window, "local")

    assert captured["kind"] == "cleanup"
    assert captured["worker"].func is text_cleanup_ui_controller.text_cleanup_service.clean_text
    assert captured["worker"].keywords["ai_profile_payload"]["model_name"] == "Qwen3.6-27B"
