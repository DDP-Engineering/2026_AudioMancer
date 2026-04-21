#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file home_presenter_service.py
@brief Home-page presenter helpers for AudioMancer.
@details Builds workflow-progress and project-summary values used by the Home
         page from manifest data without depending on Qt widgets.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.2.0
"""

# IMPORTS

from audiomancer import config
from audiomancer.services import ui_state_service

# PUBLIC API


def build_stage_statuses(
    manifest: dict[str, object] | None,
    language: str,
) -> list[dict[str, str]]:
    """
    @brief      Build the home-page workflow progress list for one manifest.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  language Current UI language code.
    @return     Ordered stage-status entries for the home page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    stage_tokens = visible_workflow_stage_tokens()
    if manifest is None:
        return [
            {
                "label": ui_state_service.translate(
                    f"home.stage_label.{token}",
                    language,
                ),
                "status": "not_started",
                "note": ui_state_service.translate(
                    f"home.stage_note.inactive.{token}",
                    language,
                ),
            }
            for token in stage_tokens
        ]

    finished_index = stage_reached_index(str(manifest.get("current_stage", config.DEFAULT_WORKFLOW_STAGE)))
    statuses: list[dict[str, str]] = []
    for index, token in enumerate(stage_tokens):
        statuses.append(
            {
                "label": ui_state_service.translate(
                    f"home.stage_label.{token}",
                    language,
                ),
                "status": "finished" if finished_index >= index else "not_started",
                "note": ui_state_service.translate(
                    f"home.stage_note.active.{token}",
                    language,
                ),
            }
        )
    extraction_status = str(manifest_operation(manifest, "extraction").get("status", "not_started"))
    if (
        source_document_name(manifest) is not None
        and extraction_status in {"running", "failed", "completed"}
        and finished_index < 1
    ):
        statuses[0]["status"] = "finished"
        statuses[1]["status"] = "in_progress"
    cleanup_status = str(manifest_operation(manifest, "cleanup").get("status", "not_started"))
    if cleanup_status in {"running", "failed"} and len(statuses) > 1:
        statuses[0]["status"] = "finished"
        statuses[1]["status"] = "in_progress"
    return statuses


def source_document_name(manifest: dict[str, object] | None) -> str | None:
    """
    @brief      Extract the display name of one persisted source document.
    @param[in]  manifest Active manifest payload or `None`.
    @return     Imported source display name or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not isinstance(manifest, dict):
        return None
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        return None
    return optional_manifest_string(source_document.get("original_name"))


def optional_manifest_string(value: object) -> str | None:
    """
    @brief      Normalize one optional manifest string used by presenter helpers.
    @param[in]  value Raw manifest field value.
    @return     Normalized string or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if value in (None, ""):
        return None
    return str(value)


def manifest_operation(
    manifest: dict[str, object] | None,
    operation_kind: str,
) -> dict[str, object]:
    """
    @brief      Return one normalized operation payload from the manifest.
    @param[in]  manifest Active manifest payload or `None`.
    @param[in]  operation_kind Operation-kind token to resolve.
    @return     Operation payload or an empty default mapping.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not isinstance(manifest, dict):
        return {}
    operations = manifest.get("operations")
    if not isinstance(operations, dict):
        return {}
    operation_payload = operations.get(operation_kind)
    return dict(operation_payload) if isinstance(operation_payload, dict) else {}


def visible_workflow_stage_tokens() -> tuple[str, ...]:
    """
    @brief      Return the visible workflow stages derived from shared config.
    @return     Ordered stage tokens shown in the home workflow progress list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    return tuple(
        stage_token for stage_token in config.PROJECT_WORKFLOW_STAGES if stage_token != config.DEFAULT_WORKFLOW_STAGE
    )


def stage_reached_index(current_stage: str | None) -> int:
    """
    @brief      Resolve one workflow-stage token into the home progress index.
    @param[in]  current_stage Current manifest stage token.
    @return     Zero-based reached stage index.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    stage_sequence = config.PROJECT_WORKFLOW_STAGES
    if current_stage not in stage_sequence:
        return -1
    if current_stage == "source_selected":
        return 0
    return stage_sequence.index(current_stage) - 2


# END OF FILE
