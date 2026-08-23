#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_duplicate_controller_consolidation.py
@brief Regression coverage for shared workflow-controller helpers.
@details Verifies caller-specific stage defaults, language resolution,
         refresh ordering, profile delegation, and synchronous dialog lifecycle.
"""

# IMPORTS

from types import SimpleNamespace

import pytest

from audiomancer import config
from audiomancer.ui.controllers import (
    audio_assembly_ui_controller,
    audio_blocks_ui_controller,
    misc_ui_controller,
    speech_blocks_ui_controller,
    text_cleanup_ui_controller,
    workflow_controller_service,
)

# TESTS


def test_workflow_rank_and_language_helpers_preserve_caller_contracts() -> None:
    """Verify known stages, explicit unknown defaults, and language lookup."""
    window = SimpleNamespace(_settings_payload={"language": "ro"})

    assert workflow_controller_service.stage_rank("speech_blocks_ready") == config.PROJECT_WORKFLOW_STAGES.index(
        "speech_blocks_ready"
    )
    assert workflow_controller_service.stage_rank("unknown") == -1
    assert workflow_controller_service.stage_rank("unknown", unknown_rank=0) == 0
    assert workflow_controller_service.current_language_from_window(window) == "ro"


def test_controller_local_rank_and_language_duplicates_are_removed() -> None:
    """Verify controllers now call the canonical workflow helpers directly."""
    for controller in (
        speech_blocks_ui_controller,
        audio_blocks_ui_controller,
        audio_assembly_ui_controller,
    ):
        assert not hasattr(controller, "_stage_rank")
        assert not hasattr(controller, "current_language_from_window")


def test_refresh_and_notify_preserves_none_guard_and_event_order(monkeypatch) -> None:
    """Verify manifest load, refresh, and notification retain their exact order."""
    events: list[object] = []
    root = object()
    window = SimpleNamespace(
        _current_project_root=root,
        _settings_payload={"language": "en"},
        show_project_state=lambda project_root, manifest: events.append(("refresh", project_root, manifest)),
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller.project_workspace_service,
        "load_manifest",
        lambda project_root: events.append(("load", project_root)) or {"current_stage": "text_cleanup_ready"},
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller.misc_ui_controller,
        "show_message",
        lambda _window, message: events.append(("notify", message)),
    )

    text_cleanup_ui_controller._refresh_and_notify(window, "status.text_cleaned")

    assert events == [
        ("load", root),
        ("refresh", root, {"current_stage": "text_cleanup_ready"}),
        ("notify", "Text cleaned."),
    ]
    window._current_project_root = None
    events.clear()
    text_cleanup_ui_controller._refresh_and_notify(window, "status.operation_cancelled")
    assert events == [("notify", "Operation cancelled.")]
    with pytest.raises(AssertionError):
        text_cleanup_ui_controller.handle_cleanup_success(window, None)


def test_synchronous_progress_helper_preserves_create_and_restart_lifecycles(monkeypatch) -> None:
    """Verify create-only and restart-existing dialog paths remain independently selectable."""
    events: list[object] = []
    dialog = SimpleNamespace(
        start=lambda title, message, cancellable: events.append(("restart", title, message, cancellable))
    )
    window = SimpleNamespace(_operation_progress_dialog=dialog, _settings_payload={"language": "en"})
    def set_busy(busy: bool) -> None:
        """Capture synchronous busy-state changes."""
        events.append(("busy", busy))

    monkeypatch.setattr(
        misc_ui_controller.ui_state_service,
        "translate",
        lambda key, language: f"{language}:{key}",
    )
    monkeypatch.setattr(
        misc_ui_controller,
        "process_pending_ui_events",
        lambda: events.append("process"),
    )

    assert (
        misc_ui_controller.start_synchronous_progress(
            window,
            "en",
            True,
            set_busy,
            "title.key",
            "prepare.key",
            restart_existing=False,
        )
        is None
    )
    assert events == []

    update = misc_ui_controller.start_synchronous_progress(
        window,
        "en",
        True,
        set_busy,
        "title.key",
        "prepare.key",
        restart_existing=True,
    )
    assert events == [
        ("busy", True),
        ("restart", "en:title.key", "en:prepare.key", False),
        "process",
    ]
    monkeypatch.setattr(
        misc_ui_controller,
        "update_progress_dialog",
        lambda _window, percent, message: events.append(("update", percent, message)),
    )
    assert update is not None
    update(55, "update.key")
    assert events[-2:] == [("update", 55, "en:update.key"), "process"]


# END OF FILE
