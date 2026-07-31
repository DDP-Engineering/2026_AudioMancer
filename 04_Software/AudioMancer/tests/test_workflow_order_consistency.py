#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_workflow_order_consistency.py
@brief Regression guard for the single-source workflow operation order.
@details Verifies the runtime, impact, and workspace layers all derive the
         canonical workflow operation order and operation-stage map from the
         shared config definition.
"""

# IMPORTS

from audiomancer import config
from audiomancer.services import operation_runtime_service, project_workspace_service, workflow_impact_service


def test_operation_order_is_single_sourced_from_config() -> None:
    """
    @brief      Verify every layer uses the canonical config operation order.
    @return     None.
    @exception  None
    """
    canonical = config.WORKFLOW_OPERATION_ORDER
    assert canonical == operation_runtime_service._OPERATION_ORDER
    assert canonical == workflow_impact_service.WORKFLOW_OPERATION_ORDER
    assert canonical == project_workspace_service._HEALABLE_OPERATION_ORDER


def test_operation_stage_map_is_single_sourced_from_config() -> None:
    """
    @brief      Verify every layer uses the canonical config operation-stage map.
    @return     None.
    @exception  None
    """
    canonical = config.OPERATION_STAGE_BY_KIND
    assert canonical == workflow_impact_service.OPERATION_STAGE_BY_KIND
    assert canonical == project_workspace_service._OPERATION_STAGE_BY_KIND


def test_operation_stage_map_targets_are_valid_workflow_stages() -> None:
    """
    @brief      Verify each promoted stage token is a known workflow stage.
    @return     None.
    @exception  None
    """
    for operation_kind, stage in config.OPERATION_STAGE_BY_KIND.items():
        assert operation_kind in config.WORKFLOW_OPERATION_ORDER
        assert stage in config.PROJECT_WORKFLOW_STAGES


# END OF FILE
