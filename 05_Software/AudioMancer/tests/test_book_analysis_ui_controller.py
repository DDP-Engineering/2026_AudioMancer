#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009

from pathlib import Path
from types import SimpleNamespace

from audiomancer.ui.controllers import book_analysis_ui_controller


class _Page:
    def set_busy(self, _busy: bool) -> None:
        pass


def _window(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        _settings_payload={"llm_profiles": []},
        _active_operation_kind=None,
        _current_project_root=tmp_path,
        _current_manifest={"target_language": "ro"},
        _book_analysis_page=_Page(),
        _book_analysis_reset_pending=False,
    )


def test_analyze_dispatches_standard_threaded_operation(monkeypatch, tmp_path) -> None:
    window = _window(tmp_path)
    profile = {"id": "profile-a", "context_window": 16_384}
    captured: dict[str, object] = {}
    refreshed: list[bool] = []
    window.refresh_current_page_state = lambda: refreshed.append(True)
    monkeypatch.setattr(
        book_analysis_ui_controller.chunking_document_service,
        "load_chunking_document",
        lambda _root: {"status": "completed"},
    )
    monkeypatch.setattr(
        book_analysis_ui_controller.workflow_controller_service,
        "resolve_enabled_ai_profile",
        lambda *_args: profile,
    )
    monkeypatch.setattr(
        book_analysis_ui_controller.workflow_controller_service,
        "start_operation",
        lambda target, **kwargs: (
            setattr(target, "_active_operation_kind", "book_analysis"),
            captured.update(kwargs),
        ),
    )
    monkeypatch.setattr(
        book_analysis_ui_controller.project_workspace_service,
        "sync_manifest_operation_summary",
        lambda *_args, **_kwargs: dict(window._current_manifest),
    )

    book_analysis_ui_controller.handle_analyze_requested(window, "profile-a")

    assert captured["operation_kind"] == "book_analysis"
    assert captured["set_busy"] is not None
    assert refreshed == [True]
    worker = captured["worker_callable"]
    monkeypatch.setattr(
        book_analysis_ui_controller.book_analysis_service,
        "analyze_book",
        lambda project_root, profile_payload, target_language, **_kwargs: {
            "project_root": project_root,
            "profile": profile_payload,
            "language": target_language,
        },
    )
    result = worker(tmp_path, window._current_manifest)
    assert result["profile"] == profile
    assert result["language"] == "ro"


def test_running_reset_requests_cancellation_before_deleting(monkeypatch, tmp_path) -> None:
    window = _window(tmp_path)
    window._active_operation_kind = "book_analysis"
    cancelled: list[bool] = []
    reset: list[bool] = []
    monkeypatch.setattr(
        book_analysis_ui_controller.operation_runner_controller,
        "request_operation_cancel",
        lambda _window: cancelled.append(True),
    )
    monkeypatch.setattr(
        book_analysis_ui_controller.book_analysis_service,
        "reset_book_analysis",
        lambda _root: reset.append(True),
    )

    book_analysis_ui_controller.handle_reset_requested(window)

    assert window._book_analysis_reset_pending is True
    assert cancelled == [True]
    assert reset == []


def test_cancel_terminal_path_performs_pending_reset_and_clears_manifest(
    monkeypatch,
    tmp_path,
) -> None:
    window = _window(tmp_path)
    window._book_analysis_reset_pending = True
    reset: list[Path] = []
    synced: list[object] = []
    monkeypatch.setattr(
        book_analysis_ui_controller.book_analysis_service,
        "reset_book_analysis",
        lambda root: reset.append(root),
    )
    monkeypatch.setattr(
        book_analysis_ui_controller.project_workspace_service,
        "sync_manifest_operation_summary",
        lambda _root, _kind, payload, **_kwargs: synced.append(payload) or {},
    )
    monkeypatch.setattr(
        book_analysis_ui_controller.project_workspace_service,
        "load_manifest",
        lambda _root: {"target_language": "ro"},
    )
    monkeypatch.setattr(
        book_analysis_ui_controller.misc_ui_controller,
        "show_message",
        lambda *_args: None,
    )

    book_analysis_ui_controller._handle_cancelled(window, "cancelled")

    assert reset == [tmp_path]
    assert synced == [None]
    assert window._book_analysis_reset_pending is False
