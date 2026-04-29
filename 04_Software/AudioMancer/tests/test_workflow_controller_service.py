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
@details Verifies cancellation flag handling and enabled AI profile resolution.
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.1.0
"""

# IMPORTS

from types import SimpleNamespace

from audiomancer.ui.controllers import workflow_controller_service


def test_cancel_active_operation_only_marks_active_workflow() -> None:
    """
    @brief      Verify shared cancellation helpers only mark an active workflow.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    window = SimpleNamespace(_active_operation_kind=None, _operation_cancel_requested=False)

    workflow_controller_service.cancel_active_operation(window)

    assert workflow_controller_service.is_cancel_requested(window) is False

    window._active_operation_kind = "translation"
    workflow_controller_service.cancel_active_operation(window)

    assert workflow_controller_service.is_cancel_requested(window) is True


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


# END OF FILE
