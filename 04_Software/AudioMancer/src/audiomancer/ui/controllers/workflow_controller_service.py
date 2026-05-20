#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file workflow_controller_service.py
@brief Shared workflow UI-controller helpers.
@details Centralizes common threaded operation startup, cancellation flags,
         manifest refresh from persisted operation state, and enabled AI profile
         resolution used by workflow page controllers.
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.2.0
"""

# IMPORTS

from collections.abc import Callable
from typing import TYPE_CHECKING

from audiomancer.services import project_workspace_service, text_cleanup_state_service
from audiomancer.ui.controllers import operation_runner_controller

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow

# PUBLIC API


def start_operation(
    window: "MainWindow",
    operation_kind: str,
    operation_name: str,
    initial_message: str,
    worker_callable,
    set_busy,
    success_handler,
    failure_handler,
    cancel_handler,
) -> None:
    """
    @brief      Start one workflow operation on the shared modal worker runner.
    @param[in]  window Active main window instance.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  operation_name Operator-facing operation label.
    @param[in]  initial_message Initial progress-dialog message text.
    @param[in]  worker_callable Callable that performs the operation.
    @param[in]  set_busy Callable used to set page busy state.
    @param[in]  success_handler Callable invoked after successful completion.
    @param[in]  failure_handler Callable invoked after worker failure.
    @param[in]  cancel_handler Callable invoked after worker cancellation.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    operation_runner_controller.start_threaded_operation(
        window,
        operation_kind,
        operation_name,
        initial_message,
        worker_callable,
        set_busy=set_busy,
        success_handler=success_handler,
        failure_handler=failure_handler,
        cancel_handler=cancel_handler,
    )


def sync_manifest_operation_from_disk(
    window: "MainWindow",
    operation_kind: str,
    load_operation_state: Callable[[object], dict[str, object] | None],
    current_stage: str | None = None,
) -> None:
    """
    @brief      Reload one persisted operation state into the project manifest.
    @param[in]  window Active main window instance.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  load_operation_state Callable loading the operation state from project root.
    @param[in]  current_stage Optional manifest stage override.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operation_state = load_operation_state(window._current_project_root)
    if operation_state is not None:
        operations[operation_kind] = project_workspace_service.project_manifest_operation_summary(
            operation_kind,
            operation_state,
        )
    updated_manifest["operations"] = operations
    if current_stage is not None:
        updated_manifest["current_stage"] = current_stage
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def resolve_enabled_ai_profile(
    settings_payload: dict[str, object] | None,
    profile_id: str | None,
) -> dict[str, object] | None:
    """
    @brief      Resolve one enabled AI profile payload from settings by id.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  profile_id Requested profile identifier.
    @return     Resolved enabled profile payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    if not isinstance(settings_payload, dict) or profile_id in (None, ""):
        return None
    raw_profiles = settings_payload.get("llm_profiles", [])
    if not isinstance(raw_profiles, list):
        return None
    for profile in raw_profiles:
        if not isinstance(profile, dict) or not bool(profile.get("enabled", True)):
            continue
        if str(profile.get("id", "")).strip() == str(profile_id).strip():
            return dict(profile)
    return None


# END OF FILE
