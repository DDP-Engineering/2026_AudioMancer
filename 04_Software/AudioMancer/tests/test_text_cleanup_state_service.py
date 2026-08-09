#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_cleanup_state_service.py
@brief State projection tests for the unified Cleanup page.
@details Verifies structural-extraction readiness, completed Cleanup state,
         manual edits, and optional compatible AI profiles.
"""

# IMPORTS

from audiomancer import config
from audiomancer.services import (
    project_workspace_service,
    text_cleanup_service,
    text_cleanup_state_service,
    text_extraction_service,
)

# PUBLIC API


def test_cleanup_state_requires_structural_extraction(tmp_path) -> None:
    """
    @brief      Verify structural Extraction enables Cleanup state.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _extracted_project(tmp_path, "StateProject")

    state = text_cleanup_state_service.build_text_cleanup_state(project_root, manifest, "en")

    assert state["can_clean"] is True
    assert state["extracted_text"] == "First line-\ncontinues here.\n"
    assert state["cleaned_text"] is None
    assert state["validation_state"] == "not_started"


def test_cleanup_state_exposes_runtime_quality_and_manual_save(tmp_path) -> None:
    """
    @brief      Verify completed Cleanup exposes runtime quality and persists manual edits.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _extracted_project(tmp_path, "CompletedState")
    document = text_cleanup_service.clean_text(project_root, manifest)

    state = text_cleanup_state_service.build_text_cleanup_state(project_root, manifest, "en")
    assert state["validation_state"] == "passed"
    assert state["uncertainty_count"] == document["quality_report"]["low_confidence_count"]
    assert state["can_reset_cleanup"] is True

    text_cleanup_state_service.save_cleaned_text_edit(project_root, "Operator correction.\n")
    updated = text_cleanup_service.load_cleanup_document(project_root)
    assert updated is not None
    assert updated["user_modified"] is True
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8") == "Operator correction.\n"


def test_cleanup_reset_removes_artifacts_and_forces_fresh_analysis(tmp_path) -> None:
    """Verify Cleanup reset removes completed artifacts before a fresh run starts."""
    project_root, manifest = _extracted_project(tmp_path, "ResetCleanup")
    text_cleanup_service.clean_text(project_root, manifest)
    downstream_artifact = project_root / config.CHUNK_ARTIFACT_FILE_NAME
    downstream_artifact.write_text("[]\n", encoding="utf-8")

    reset_manifest = text_cleanup_state_service.reset_cleanup(project_root, manifest)

    assert not (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).exists()
    assert not (project_root / config.CLEANED_TEXT_FILE_NAME).exists()
    assert not downstream_artifact.exists()
    assert reset_manifest["operations"]["cleanup"]["status"] == "not_started"
    assert reset_manifest["operations"]["chunking"]["status"] == "not_started"

    progress: list[str] = []
    text_cleanup_service.clean_text(
        project_root,
        reset_manifest,
        progress_callback=lambda _current, _total, _percent, message: progress.append(message),
    )

    assert any(message.startswith("Analyzing structural cleanup evidence") for message in progress)
    assert "Cleanup completed." not in progress


def test_ai_profile_state_keeps_profile_optional() -> None:
    """
    @brief      Verify Cleanup profile state keeps AI optional and excludes disabled profiles.
    @return     None.
    @exception  None
    """
    state = text_cleanup_state_service.build_ai_cleanup_profile_state(
        {
            "default_ai_cleanup_profile_id": "local",
            "llm_profiles": [
                {"id": "local", "label": "Local Qwen", "enabled": True},
                {"id": "disabled", "label": "Disabled", "enabled": False},
            ],
        }
    )
    assert state == {
        "entries": [("Local Qwen", "local")],
        "selected_profile_id": "local",
    }


def test_ai_cleanup_profile_state_preserves_nonempty_whitespace_label() -> None:
    """
    @brief      Verify Cleanup retains its distinct nonempty whitespace-label behavior.
    @return     None.
    @exception  None
    """
    state = text_cleanup_state_service.build_ai_cleanup_profile_state(
        {
            "default_ai_cleanup_profile_id": "local",
            "llm_profiles": [{"id": "local", "label": "   ", "enabled": True}],
        }
    )

    assert state == {
        "entries": [("   ", "local")],
        "selected_profile_id": "local",
    }

# LOCAL HELPERS


def _extracted_project(tmp_path, name):
    """
    @brief      Create a structurally extracted project fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  name Project display name.
    @return     Project-root and manifest tuple.
    @exception  OSError Raised when fixture files cannot be written.
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("First line-\ncontinues here.", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": source_path.name,
        "stored_relative_path": source_path.name,
        "file_type": "txt",
        "imported_at": "2026-07-27T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    project_workspace_service.save_manifest(manifest, project_root)
    text_extraction_service.extract_text(project_root, manifest)
    return project_root, manifest


# END OF FILE
