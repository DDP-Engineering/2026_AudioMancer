#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_project_workspace_service.py
@brief Focused tests for the AudioMancer project workspace service.
@details Verifies project creation, manifest persistence, folder-name
         validation, project-root resolution, and open validation behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.5.0
"""

# IMPORTS

import json
import shutil

import pytest

from audiomancer import config
from audiomancer.services import project_workspace_service


# PUBLIC API


def test_create_project_creates_required_structure_and_manifest(tmp_path) -> None:
    """
    @brief      Verify project creation writes the required folders and manifest.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )

    assert project_root == tmp_path / "Book5_CAL_CAL"
    assert manifest["display_name"] == "Book5_CAL_CAL"
    assert manifest["current_stage"] == config.DEFAULT_WORKFLOW_STAGE
    assert manifest["source_document"] is None
    assert manifest["extracted_text_relative_path"] is None
    assert manifest["extraction_report_relative_path"] is None
    assert manifest["extraction_warning_count"] == 0
    assert manifest["operations"]["extraction"]["status"] == "not_started"
    assert manifest["operations"]["cleanup"]["folder_relative_path"] == "10_cleanup"
    assert (
        project_root / config.PROJECT_MANIFEST_FILE_NAME
    ).is_file()
    for folder_name in config.PROJECT_REQUIRED_SUBDIRECTORIES:
        assert (project_root / folder_name).is_dir()


def test_validate_project_name_rejects_unsupported_windows_characters() -> None:
    """
    @brief      Verify unsupported Windows characters are rejected.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    with pytest.raises(ValueError, match="unsupported folder characters"):
        project_workspace_service.validate_project_name("Book:Five")


def test_validate_project_name_rejects_linux_reserved_name() -> None:
    """
    @brief      Verify Linux-reserved directory names are rejected.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    with pytest.raises(ValueError, match="cannot be '.' or '..'"):
        project_workspace_service.validate_project_name("..")


def test_validate_project_name_rejects_reserved_windows_device_name() -> None:
    """
    @brief      Verify reserved Windows device names are rejected.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    with pytest.raises(ValueError, match="reserved Windows device name"):
        project_workspace_service.validate_project_name("CON")


def test_create_project_rejects_non_empty_target_folder(tmp_path) -> None:
    """
    @brief      Verify project creation fails when the target root is not empty.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    target_root = tmp_path / "Book5_CAL_CAL"
    target_root.mkdir()
    (target_root / "existing.txt").write_text("occupied", encoding="utf-8")

    with pytest.raises(FileExistsError, match="not empty"):
        project_workspace_service.create_project("Book5_CAL_CAL", tmp_path)


def test_open_project_resolves_root_from_child_folder(tmp_path) -> None:
    """
    @brief      Verify opening succeeds when selecting one child workflow folder.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    created_root, _manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )

    open_result = project_workspace_service.open_project(
        created_root / "20_chunking"
    )

    assert open_result["status"] == "ok"
    assert open_result["project_root"] == created_root
    assert open_result["manifest"]["display_name"] == "Book5_CAL_CAL"


def test_open_project_fails_when_manifest_is_missing(tmp_path) -> None:
    """
    @brief      Verify opening fails when no manifest exists in the folder chain.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    orphan_folder = tmp_path / "orphan"
    orphan_folder.mkdir()

    with pytest.raises(FileNotFoundError, match="project.json"):
        project_workspace_service.open_project(orphan_folder)


def test_open_project_fails_when_required_folder_is_missing(tmp_path) -> None:
    """
    @brief      Verify opening fails when the required project structure is incomplete.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    (project_root / "50_narrator_definition").rmdir()

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "repair_required"
    assert open_result["corrupted_step"] == "50_narrator_definition"


def test_open_project_fails_when_required_manifest_field_is_missing(tmp_path) -> None:
    """
    @brief      Verify opening fails when minimal manifest metadata is incomplete.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    manifest_path = project_root / config.PROJECT_MANIFEST_FILE_NAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    del payload["display_name"]
    manifest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="display_name"):
        project_workspace_service.open_project(project_root)


def test_repair_project_recreates_missing_downstream_folders_and_resets_stage(
    tmp_path,
) -> None:
    """
    @brief      Verify repair recreates downstream step folders and resets metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    manifest["current_stage"] = "narrator_definition_ready"
    manifest["narrator_profile_name"] = "Warm Storyteller"
    manifest["narrator_language"] = "English"
    project_workspace_service.save_manifest(manifest, project_root)
    shutil_target = project_root / "30_translation"
    (shutil_target / "artifact.txt").write_text("old-data", encoding="utf-8")
    shutil.rmtree(shutil_target)

    open_result = project_workspace_service.open_project(project_root)
    assert open_result["status"] == "repair_required"

    repaired_result = project_workspace_service.repair_project(open_result)

    assert repaired_result["status"] == "ok"
    assert repaired_result["project_root"] == project_root
    assert repaired_result["manifest"]["current_stage"] == "project_created"
    assert repaired_result["manifest"]["narrator_profile_name"] is None
    assert repaired_result["manifest"]["narrator_language"] is None
    for folder_name in (
        "30_translation",
        "40_character_discovery",
        "50_narrator_definition",
    ):
        assert (project_root / folder_name).is_dir()
        assert list((project_root / folder_name).iterdir()) == []


def test_repair_project_fixes_invalid_current_stage_metadata_only(tmp_path) -> None:
    """
    @brief      Verify repair can fix a recoverable metadata-only stage corruption.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "source.pdf",
        "stored_relative_path": "source.pdf",
        "file_type": "pdf",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 1024,
    }
    manifest["current_stage"] = "broken_stage"
    manifest_path = project_root / config.PROJECT_MANIFEST_FILE_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "repair_required"
    assert open_result["metadata_only"] is True
    repaired_result = project_workspace_service.repair_project(open_result)

    assert repaired_result["status"] == "ok"
    assert repaired_result["project_root"] == project_root
    assert repaired_result["manifest"]["current_stage"] == "source_selected"


def test_validate_project_manifest_accepts_structured_source_document() -> None:
    """
    @brief      Verify manifest validation preserves one valid source-document payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    manifest = project_workspace_service.build_project_manifest("Book5_CAL_CAL")
    manifest["source_document"] = {
        "original_name": "story.epub",
        "stored_relative_path": "story.epub",
        "file_type": "epub",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 2048,
    }
    manifest["current_stage"] = "source_selected"

    validated = project_workspace_service.validate_project_manifest(manifest)

    assert validated["source_document"] == manifest["source_document"]
    assert validated["current_stage"] == "source_selected"


def test_validate_project_manifest_normalizes_operations_map() -> None:
    """
    @brief      Verify manifest validation fills the required per-operation state entries.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    manifest = project_workspace_service.build_project_manifest("Book5_CAL_CAL")
    manifest["operations"] = {
        "extraction": {
            "folder_relative_path": "00_extraction",
            "status": "running",
            "progress_current": 1,
            "progress_total": 3,
        }
    }

    validated = project_workspace_service.validate_project_manifest(manifest)

    assert validated["operations"]["extraction"]["status"] == "running"
    assert validated["operations"]["extraction"]["progress_current"] == 1
    assert validated["operations"]["translation"]["status"] == "not_started"


# END OF FILE
