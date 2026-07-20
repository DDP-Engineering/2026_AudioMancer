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
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.2.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-19
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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


def test_sync_manifest_operation_from_disk_persists_summary_and_refreshes_window(tmp_path) -> None:
    """
    @brief      Verify persisted operation state becomes the active manifest summary.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-19
    @version    0.1.0
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


# END OF FILE
