#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_operation_runtime_service.py
@brief Focused tests for shared operation runtime helpers.
@details Verifies percent conversion and downstream reset behavior shared by
         extraction, cleanup, and future workflow operations.
@author Eng. Dan Dumitru Pasare
@date 2026-04-22
@version 0.4.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import operation_runtime_service, project_workspace_service


def test_progress_percent_clamps_to_zero_and_hundred() -> None:
    """
    @brief      Verify shared unit-progress conversion stays inside the UI range.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
    """
    assert operation_runtime_service.progress_percent(0, 0) == 0
    assert operation_runtime_service.progress_percent(1, 4) == 25
    assert operation_runtime_service.progress_percent(99, 4) == 100


def test_reset_operation_data_clears_known_root_artifacts_only(tmp_path) -> None:
    """
    @brief      Verify one operation reset clears known flat artifacts without deleting unrelated root files.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("ResetRuntime", tmp_path)
    (project_root / "story.txt").write_text("raw", encoding="utf-8")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("raw", encoding="utf-8")
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("clean", encoding="utf-8")
    (project_root / config.CLEANUP_REPORT_FILE_NAME).write_text("{}", encoding="utf-8")
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text("[]", encoding="utf-8")
    (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text("[]", encoding="utf-8")
    (project_root / "notes.txt").write_text("keep", encoding="utf-8")

    operation_runtime_service.reset_operation_data(
        project_root,
        "cleanup",
        include_current=True,
        keep_input_snapshots=False,
    )

    assert (project_root / "story.txt").is_file()
    assert (project_root / "notes.txt").read_text(encoding="utf-8") == "keep"
    assert (project_root / config.EXTRACTED_TEXT_FILE_NAME).is_file()
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).exists() is False
    assert (project_root / config.CLEANUP_REPORT_FILE_NAME).exists() is False
    assert (project_root / config.CHUNK_ARTIFACT_FILE_NAME).exists() is False
    assert (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).exists() is False


def test_resolve_operation_path_uses_project_root_without_creating_folders(tmp_path) -> None:
    """
    @brief      Verify read-only path resolution uses the flat project root as a side effect-free operation path.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("ResolveRuntime", tmp_path)

    resolved_path = operation_runtime_service.resolve_operation_path(
        project_root,
        "translation",
        config.TRANSLATION_STATE_FILE_NAME,
    )

    assert resolved_path == project_root / config.TRANSLATION_STATE_FILE_NAME
    assert not any(
        (project_root / folder_name).exists() for folder_name in ("30_translation", "40_character_discovery")
    )


def test_ensure_default_operation_state_creates_not_started_state_only(tmp_path) -> None:
    """
    @brief      Verify default state initialization creates state metadata without reports or outputs.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("DefaultStateRuntime", tmp_path)

    state_path = operation_runtime_service.ensure_default_operation_state(project_root, "translation")
    second_state_path = operation_runtime_service.ensure_default_operation_state(project_root, "translation")

    assert state_path == project_root / config.TRANSLATION_STATE_FILE_NAME
    assert second_state_path == state_path
    assert (project_root / config.TRANSLATION_REPORT_FILE_NAME).exists() is False
    assert (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).exists() is False
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["status"] == "not_started"
    assert state_payload["input_paths"] == []
    assert state_payload["output_paths"] == []
    assert state_payload["artifact_paths"] == []
    assert state_payload["metadata"] == {}
    assert state_payload["resume_checkpoint"] is None


def test_ensure_default_operation_state_creates_zero_character_discovery_metadata(tmp_path) -> None:
    """
    @brief      Verify first Characters page access creates zero-valued discovery metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("DefaultCharacterStateRuntime", tmp_path)

    state_path = operation_runtime_service.ensure_default_operation_state(project_root, "character_discovery")

    assert state_path == project_root / config.CHARACTER_DISCOVERY_STATE_FILE_NAME
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["status"] == "not_started"
    assert state_payload["progress_current"] == 0
    assert state_payload["progress_total"] == 0
    assert state_payload["output_paths"] == []
    assert state_payload["artifact_paths"] == []
    assert state_payload["metadata"]["source_chunk_count"] == 0
    assert state_payload["metadata"]["character_count"] == 0
    assert state_payload["metadata"]["analyzed_window_count"] == 0
    assert state_payload["metadata"]["merged_candidate_count"] == 0
    assert state_payload["metadata"]["window_size"] == 0
    assert state_payload["metadata"]["window_overlap"] == 0
    assert state_payload["metadata"]["warnings"] == []
    assert state_payload["resume_checkpoint"] is None


# END OF FILE
