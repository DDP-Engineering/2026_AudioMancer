#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_project_stage_consistency.py
@brief Tests that the persisted workflow stage is a monotonic high-water mark.
@details Reproduces the Repair Project drift observed on a real finished project,
         where re-running Speech Blocks regressed current_stage while audio_blocks
         and audio_assembly stayed completed.
"""

# IMPORTS

from audiomancer.services import project_workspace_service


def test_operation_summary_advances_the_stage(tmp_path) -> None:
    """
    @brief      Verify a higher requested stage still moves the project forward.
    @details    Covers REQ-FUNC-e45d3577-3260-4db1-83e9-e6d99bcf5967 / S-STAGE-MONOTONIC.
    @param[in]  tmp_path Temporary project root fixture.
    @return     None.
    @exception  None
    """
    project_root = _project_at_stage(tmp_path, "AdvanceProject", "character_voices_ready")

    manifest = project_workspace_service.sync_manifest_operation_summary(
        project_root,
        "speech_blocks",
        {"status": "completed", "progress_current": 7, "progress_total": 7},
        current_stage="speech_blocks_ready",
    )

    assert manifest["current_stage"] == "speech_blocks_ready"
    assert manifest["operations"]["speech_blocks"]["status"] == "completed"


def test_operation_summary_never_moves_the_stage_backwards(tmp_path) -> None:
    """
    @brief      Verify a lower requested stage is ignored instead of regressing the project.
    @details    Covers REQ-FUNC-e45d3577-3260-4db1-83e9-e6d99bcf5967 / S-STAGE-MONOTONIC. This
                is the Speech Blocks re-run write that produced the drifted manifest on disk.
    @param[in]  tmp_path Temporary project root fixture.
    @return     None.
    @exception  None
    """
    project_root = _finished_project(tmp_path, "RegressProject")

    manifest = project_workspace_service.sync_manifest_operation_summary(
        project_root,
        "speech_blocks",
        {"status": "review_pending", "progress_current": 3, "progress_total": 7},
        current_stage="character_voices_ready",
    )

    assert manifest["current_stage"] == "audio_assembly_ready"
    assert manifest["operations"]["speech_blocks"]["status"] == "review_pending"
    assert manifest["operations"]["speech_blocks"]["progress_current"] == 3


def test_lower_requested_stage_does_not_destroy_completed_downstream_work(tmp_path) -> None:
    """
    @brief      Verify a summary sync never discards operation summaries it was not given.
    @details    Covers REQ-FUNC-e45d3577-3260-4db1-83e9-e6d99bcf5967 / S-STAGE-NODESTROY.
                Invalidating downstream work is owned by the explicit reset path, which
                clears artifacts and summaries together; a summary sync must not silently
                throw away a completed audio render.
    @param[in]  tmp_path Temporary project root fixture.
    @return     None.
    @exception  None
    """
    project_root = _finished_project(tmp_path, "PreserveProject")

    manifest = project_workspace_service.sync_manifest_operation_summary(
        project_root,
        "speech_blocks",
        {"status": "review_pending", "progress_current": 3, "progress_total": 7},
        current_stage="character_voices_ready",
    )

    assert manifest["operations"]["audio_blocks"]["status"] == "completed"
    assert manifest["operations"]["audio_assembly"]["status"] == "completed"


def test_finished_manifest_claims_no_completed_work_above_its_stage(tmp_path) -> None:
    """
    @brief      Verify the persisted manifest stays self-consistent after a regressing write.
    @details    Covers REQ-FUNC-e45d3577-3260-4db1-83e9-e6d99bcf5967 / S-STAGE-MONOTONIC. The
                Repair Project prompt fires when the stage derived from local artifacts
                outranks the stored stage, so the property that prevents it is that no
                operation above the stored stage still claims completion. That invariant is
                asserted directly; asserting it through `open_project` would need fabricated
                artifacts for all ten evidence builders and would otherwise pass for the
                wrong reason on a project that simply has no artifacts on disk.
    @param[in]  tmp_path Temporary project root fixture.
    @return     None.
    @exception  None
    """
    project_root = _finished_project(tmp_path, "ConsistentProject")
    project_workspace_service.sync_manifest_operation_summary(
        project_root,
        "speech_blocks",
        {"status": "review_pending", "progress_current": 3, "progress_total": 7},
        current_stage="character_voices_ready",
    )

    manifest = project_workspace_service.load_manifest(project_root)
    justified_operations = project_workspace_service._allowed_operations_for_stage(  # noqa: SLF001
        str(manifest["current_stage"])
    )
    completed_operations = {
        operation_kind
        for operation_kind, summary in manifest["operations"].items()
        if str(summary.get("status")) == "completed"
    }

    assert completed_operations <= justified_operations


# HELPER FUNCTIONS


def _project_at_stage(tmp_path, display_name: str, stage: str):
    """
    @brief      Create a project pinned to one workflow stage.
    @param[in]  tmp_path Temporary project root fixture.
    @param[in]  display_name Project display name.
    @param[in]  stage Stage token to persist.
    @return     Active project root path.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project(display_name, tmp_path)
    manifest["source_document"] = {
        "original_name": "book.pdf",
        "stored_relative_path": "book.pdf",
        "file_type": "pdf",
        "imported_at": "2026-07-24T06:40:27+00:00",
        "size_bytes": 224602,
    }
    (project_root / "book.pdf").write_bytes(b"%PDF-1.4 test")
    manifest["current_stage"] = stage
    project_workspace_service.save_manifest(manifest, project_root)
    return project_root


def _finished_project(tmp_path, display_name: str):
    """
    @brief      Create a project whose whole workflow is recorded as completed.
    @details    Mirrors the shape of the real drifted manifest: every operation
                completed, with the stage at audio_assembly_ready.
    @param[in]  tmp_path Temporary project root fixture.
    @param[in]  display_name Project display name.
    @return     Active project root path.
    @exception  None
    """
    project_root = _project_at_stage(tmp_path, display_name, "audio_assembly_ready")
    manifest = project_workspace_service.load_manifest(project_root)
    operations = dict(manifest["operations"])
    for operation_kind in operations:
        operations[operation_kind] = {
            "status": "completed",
            "progress_current": 1,
            "progress_total": 1,
            "mode": "manual",
            "warning_count": 0,
        }
    manifest["operations"] = operations
    manifest["current_stage"] = "audio_assembly_ready"
    project_workspace_service.save_manifest(manifest, project_root)
    return project_root


# END OF FILE
