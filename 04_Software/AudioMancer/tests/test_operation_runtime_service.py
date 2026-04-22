#!/usr/bin/env python3
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
@version 0.2.0
"""

# IMPORTS

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


def test_reset_operation_data_clears_selected_and_downstream_folders(tmp_path) -> None:
    """
    @brief      Verify one operation reset clears the selected step and all downstream folders.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("ResetRuntime", tmp_path)
    (project_root / "00_extraction" / "input_story.txt").write_text("raw", encoding="utf-8")
    (project_root / config.CLEANUP_FOLDER_NAME / config.CLEANED_TEXT_FILE_NAME).write_text(
        "clean",
        encoding="utf-8",
    )
    (project_root / "20_chunking" / config.CHUNK_ARTIFACT_FILE_NAME).write_text("[]", encoding="utf-8")
    (project_root / "30_translation" / "translation.json").write_text("{}", encoding="utf-8")

    operation_runtime_service.reset_operation_data(
        project_root,
        "cleanup",
        include_current=True,
        keep_input_snapshots=False,
    )

    assert (project_root / "00_extraction" / "input_story.txt").is_file()
    assert list((project_root / config.CLEANUP_FOLDER_NAME).iterdir()) == []
    assert list((project_root / "20_chunking").iterdir()) == []
    assert list((project_root / "30_translation").iterdir()) == []


def test_resolve_operation_path_does_not_create_missing_step_folder(tmp_path) -> None:
    """
    @brief      Verify read-only path resolution does not create workflow folders as a side effect.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("ResolveRuntime", tmp_path)
    translation_root = project_root / config.TRANSLATION_FOLDER_NAME
    operation_runtime_service.reset_operation_data(project_root, "translation", include_current=True)
    translation_root.rmdir()

    resolved_path = operation_runtime_service.resolve_operation_path(
        project_root,
        "translation",
        config.OPERATION_STATE_FILE_NAME,
    )

    assert resolved_path == translation_root / config.OPERATION_STATE_FILE_NAME
    assert translation_root.exists() is False


# END OF FILE
