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
@version 0.4.0
"""

# IMPORTS

from audiomancer import config
from audiomancer.services import ui_state_service

# CONSTANTS

# @brief Workflow operation rows used by persisted and active operation overlays.
_OPERATION_TO_WORKFLOW_ROW = {
    "cleanup": 0,
    "chunking": 1,
    "translation": 2,
    "character_discovery": 3,
    "speech_blocks": 6,
    "audio_blocks": 7,
    "audio_assembly": 8,
}

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
    @version    0.3.0
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
    cleanup_status = str(manifest_operation(manifest, "cleanup").get("status", "not_started"))
    if cleanup_status in {"running", "failed"} and statuses:
        statuses[0]["status"] = "in_progress"
    _apply_operation_status_overlays(statuses, manifest)
    _apply_ready_stage_overlays(statuses, str(manifest.get("current_stage", config.DEFAULT_WORKFLOW_STAGE)))
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


def apply_active_operation_status(
    statuses: list[dict[str, str]],
    operation_kind: str | None,
) -> None:
    """
    @brief      Overlay workflow rows with the currently running UI operation.
    @param[in]  statuses Mutable Home-page status rows.
    @param[in]  operation_kind Active operation kind or `None`.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    row_index = _OPERATION_TO_WORKFLOW_ROW.get(str(operation_kind or "").strip())
    if row_index is not None and row_index < len(statuses):
        statuses[row_index]["status"] = "in_progress"


def visible_workflow_stage_tokens() -> tuple[str, ...]:
    """
    @brief      Return the visible workflow stages derived from shared config.
    @return     Ordered stage tokens shown in the home workflow progress list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    return tuple(
        stage_token
        for stage_token in config.PROJECT_WORKFLOW_STAGES
        if stage_token not in {config.DEFAULT_WORKFLOW_STAGE, "source_selected"}
    )


def stage_reached_index(current_stage: str | None) -> int:
    """
    @brief      Resolve one workflow-stage token into the home progress index.
    @param[in]  current_stage Current manifest stage token.
    @return     Zero-based reached stage index.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.3.0
    """
    stage_sequence = config.PROJECT_WORKFLOW_STAGES
    if current_stage not in stage_sequence:
        return -1
    return stage_sequence.index(current_stage) - 3


def _apply_operation_status_overlays(statuses: list[dict[str, str]], manifest: dict[str, object]) -> None:
    """
    @brief      Overlay workflow rows with persisted operation status summaries.
    @param[in]  statuses Mutable Home-page status rows.
    @param[in]  manifest Active manifest payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    for operation_kind, row_index in _OPERATION_TO_WORKFLOW_ROW.items():
        if row_index >= len(statuses):
            continue
        operation_status = str(manifest_operation(manifest, operation_kind).get("status", "not_started")).strip()
        if operation_status == "completed":
            statuses[row_index]["status"] = "finished"
        elif operation_status not in {"", "not_started", "pending"}:
            statuses[row_index]["status"] = "in_progress"


def _apply_ready_stage_overlays(statuses: list[dict[str, str]], current_stage: str) -> None:
    """
    @brief      Mark later non-operation readiness stages as finished when reached.
    @param[in]  statuses Mutable Home-page status rows.
    @param[in]  current_stage Current manifest stage token.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    stage_sequence = config.PROJECT_WORKFLOW_STAGES
    if current_stage not in stage_sequence:
        return
    current_index = stage_sequence.index(current_stage)
    ready_stage_rows = {
        "narrator_definition_ready": 4,
        "character_voices_ready": 5,
        "speech_blocks_ready": 6,
        "audio_blocks_ready": 7,
        "audio_assembly_ready": 8,
    }
    for stage_token, row_index in ready_stage_rows.items():
        if row_index < len(statuses) and current_index >= stage_sequence.index(stage_token):
            statuses[row_index]["status"] = "finished"


# END OF FILE
