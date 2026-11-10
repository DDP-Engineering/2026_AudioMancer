#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_workflow_controller_service.py
@brief Focused tests for shared workflow controller helpers.
@details Verifies the worker-visible cancellation path and enabled AI profile
         resolution.
"""

# IMPORTS

from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import operation_runner_controller, workflow_controller_service


def test_request_operation_cancel_sets_worker_visible_event() -> None:
    """
    @brief      Verify cancellation flips the worker-visible cancel event, not just a flag.
    @return     None.
    @exception  None
    """
    cancel_event = Event()
    window = SimpleNamespace(
        _active_operation_kind=None,
        _operation_cancel_requested=False,
        _operation_cancel_event=cancel_event,
    )

    operation_runner_controller.request_operation_cancel(window)
    assert cancel_event.is_set() is False
    assert window._operation_cancel_requested is False

    window._active_operation_kind = "translation"
    operation_runner_controller.request_operation_cancel(window)

    assert window._operation_cancel_requested is True
    assert cancel_event.is_set() is True


def test_resolve_enabled_ai_profile_ignores_disabled_or_missing_profiles() -> None:
    """
    @brief      Verify shared AI profile resolution returns only enabled matching profiles.
    @return     None.
    @exception  None
    """
    settings_payload = {
        "llm_profiles": [
            {"id": "disabled", "enabled": False},
            {"id": "enabled", "enabled": True, "model": "model-a"},
        ]
    }

    assert workflow_controller_service.resolve_enabled_ai_profile(settings_payload, "disabled") is None
    assert workflow_controller_service.resolve_enabled_ai_profile(settings_payload, "missing") is None
    assert workflow_controller_service.resolve_enabled_ai_profile(settings_payload, "enabled") == {
        "id": "enabled",
        "enabled": True,
        "model": "model-a",
    }


def test_sync_manifest_operation_from_disk_refreshes_summary_and_displays_final_manifest(tmp_path) -> None:
    """
    @brief      Verify persisted operation state becomes the active manifest summary.
    @return     None.
    @exception  None.
    """
    project_root, manifest = project_workspace_service.create_project("WorkflowSync", tmp_path)
    show_project_state = Mock()
    window = SimpleNamespace(
        _current_project_root=project_root,
        _current_manifest=manifest,
        show_project_state=show_project_state,
    )
    operation_state = {
        "status": "completed",
        "progress_current": 2,
        "progress_total": 2,
        "mode": "deterministic",
        "warning_count": 0,
        "metadata": {},
        "resume_checkpoint": None,
    }

    workflow_controller_service.sync_manifest_operation_from_disk(
        window,
        "chunking",
        lambda root: operation_state if root == project_root else None,
        current_stage="text_chunking_ready",
    )

    persisted_manifest = project_workspace_service.load_manifest(project_root)
    assert persisted_manifest["operations"]["chunking"] == {
        "status": "completed",
        "progress_current": 2,
        "progress_total": 2,
        "mode": "deterministic",
        "warning_count": 0,
    }
    assert persisted_manifest["current_stage"] == "text_chunking_ready"
    show_project_state.assert_called_once_with(project_root, persisted_manifest)


def test_sync_manifest_operation_from_disk_preserves_newer_manifest_fields(tmp_path) -> None:
    """
    @brief      Verify controller synchronization starts from the persisted manifest.
    @return     None.
    @exception  None.
    """
    project_root, stale_manifest = project_workspace_service.create_project("WorkflowFreshness", tmp_path)
    persisted_manifest = project_workspace_service.load_manifest(project_root)
    persisted_manifest["notes"] = "Written after the window snapshot."
    project_workspace_service.save_manifest(persisted_manifest, project_root)
    show_project_state = Mock()
    window = SimpleNamespace(
        _current_project_root=project_root,
        _current_manifest=stale_manifest,
        show_project_state=show_project_state,
    )

    workflow_controller_service.sync_manifest_operation_from_disk(
        window,
        "chunking",
        lambda root: {"status": "in_progress", "progress_current": 1, "progress_total": 3}
        if root == project_root
        else None,
    )

    final_manifest = project_workspace_service.load_manifest(project_root)
    assert final_manifest["notes"] == "Written after the window snapshot."
    assert final_manifest["operations"]["chunking"]["progress_current"] == 1
    show_project_state.assert_called_once_with(project_root, final_manifest)


def test_sync_manifest_operation_from_disk_ignores_regressing_stage_and_preserves_downstream_summaries(
    tmp_path,
) -> None:
    """
    @brief      Verify a controller sync cannot demote a completed project.
    @return     None.
    @exception  None.
    """
    project_root, stale_manifest = project_workspace_service.create_project("WorkflowStage", tmp_path)
    persisted_manifest = project_workspace_service.load_manifest(project_root)
    persisted_manifest["current_stage"] = "audio_assembly_ready"
    for operation_kind in ("audio_blocks", "audio_assembly"):
        persisted_manifest["operations"][operation_kind] = {
            "status": "completed",
            "progress_current": 1,
            "progress_total": 1,
            "mode": "manual",
            "warning_count": 0,
        }
    project_workspace_service.save_manifest(persisted_manifest, project_root)
    window = SimpleNamespace(
        _current_project_root=project_root,
        _current_manifest=stale_manifest,
        show_project_state=Mock(),
    )

    workflow_controller_service.sync_manifest_operation_from_disk(
        window,
        "character_discovery",
        lambda root: {"status": "in_progress", "progress_current": 1, "progress_total": 2}
        if root == project_root
        else None,
        current_stage="translation_ready",
    )

    final_manifest = project_workspace_service.load_manifest(project_root)
    assert final_manifest["current_stage"] == "audio_assembly_ready"
    assert final_manifest["operations"]["audio_blocks"]["status"] == "completed"
    assert final_manifest["operations"]["audio_assembly"]["status"] == "completed"
    assert final_manifest["operations"]["character_discovery"]["status"] == "in_progress"


def test_sync_manifest_operation_from_disk_refreshes_window_when_loader_returns_none(tmp_path) -> None:
    """
    @brief      Verify a missing persisted operation state still refreshes the window.
    @return     None.
    @exception  None.
    """
    project_root, stale_manifest = project_workspace_service.create_project("WorkflowNoState", tmp_path)
    persisted_manifest = project_workspace_service.load_manifest(project_root)
    persisted_manifest["notes"] = "Keep the persisted manifest intact."
    project_workspace_service.save_manifest(persisted_manifest, project_root)
    show_project_state = Mock()
    window = SimpleNamespace(
        _current_project_root=project_root,
        _current_manifest=stale_manifest,
        show_project_state=show_project_state,
    )

    workflow_controller_service.sync_manifest_operation_from_disk(
        window,
        "speech_blocks",
        lambda root: None,
    )

    final_manifest = project_workspace_service.load_manifest(project_root)
    assert final_manifest["notes"] == "Keep the persisted manifest intact."
    show_project_state.assert_called_once_with(project_root, final_manifest)




def test_resolve_enabled_ai_profile_fits_hidden_output_limit_to_context() -> None:
    """@brief Keep the saved output setting and fit the request to the active context."""
    profile = {
        "id": "local", "model_name": "model-a", "context_window": 32768,
        "discovered_context_model_name": "model-a", "server_context_window": 8192,
        "output_reserve_tokens": 16384,
    }
    resolved = workflow_controller_service.resolve_enabled_ai_profile({"llm_profiles": [profile]}, "local")
    assert resolved["output_reserve_tokens"] == 4096
    assert profile["output_reserve_tokens"] == 16384


# END OF FILE
