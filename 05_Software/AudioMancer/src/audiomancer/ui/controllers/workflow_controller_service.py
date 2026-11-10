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
         canonical manifest refresh from persisted operation state, and enabled
         AI profile resolution used by workflow page controllers.
"""

# IMPORTS

from collections.abc import Callable
from typing import TYPE_CHECKING

from audiomancer import config
from audiomancer.services import ai_budget_service, project_workspace_service, ui_state_service
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
    @details    Delegates summary and stage persistence to the canonical
                Project Lifecycle writer, then displays its final disk payload.
    @param[in]  window Active main window instance.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  load_operation_state Callable loading the operation state from project root.
    @param[in]  current_stage Optional manifest stage milestone to synchronize.
    @return     None.
    @exception  None
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    operation_state = load_operation_state(window._current_project_root)
    if operation_state is not None or current_stage is not None:
        project_workspace_service.sync_manifest_operation_summary(
            window._current_project_root,
            operation_kind,
            operation_state,
            current_stage=current_stage,
        )
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
    @return     Enabled profile with output capacity fitted to its context, or None.
    @exception  None
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
            context = ai_budget_service.effective_context_window(profile)
            output_limit = max(1, context // 2)
            if ai_budget_service.output_token_limit(profile) > output_limit:
                return {**profile, "output_reserve_tokens": output_limit}
            return dict(profile)
    return None


def stage_rank(stage: str, *, unknown_rank: int = -1) -> int:
    """
    @brief      Resolve one workflow stage to its ordered rank.
    @param[in]  stage Workflow stage token.
    @param[in]  unknown_rank Caller-specific rank returned for an unknown token.
    @return     Zero-based workflow rank or the requested unknown-stage fallback.
    @exception  None
    """
    try:
        return config.PROJECT_WORKFLOW_STAGES.index(stage)
    except ValueError:
        return int(unknown_rank)


def current_language_from_window(window: "MainWindow") -> str:
    """
    @brief      Resolve the active UI language from one main window instance.
    @param[in]  window Active main window instance.
    @return     Current UI language code.
    @exception  None
    """
    return ui_state_service.current_language_from_settings(window._settings_payload)


# END OF FILE
