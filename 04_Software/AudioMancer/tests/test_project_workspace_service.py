#!/usr/bin/env python3
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
@date 2026-04-20
@version 0.9.0
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
    assert manifest["voice_assignment_mode"] == config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE
    assert "metadata" not in manifest["operations"]["extraction"]
    assert "output_paths" not in manifest["operations"]["cleanup"]
    assert (project_root / config.PROJECT_MANIFEST_FILE_NAME).is_file()
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

    open_result = project_workspace_service.open_project(created_root / "20_chunking")

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
    @version    0.2.0
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
    assert repaired_result["manifest"]["current_stage"] == "text_chunking_ready"
    assert repaired_result["manifest"]["narrator_profile_name"] is None
    assert repaired_result["manifest"]["narrator_language"] is None
    for folder_name in (
        "30_translation",
        "40_character_discovery",
        "50_narrator_definition",
        "60_character_voices",
        "70_speech_blocks",
        "80_audio_blocks",
        "90_audio_assembly",
    ):
        assert (project_root / folder_name).is_dir()
        assert list((project_root / folder_name).iterdir()) == []


def test_repair_project_recreates_missing_support_folder_without_resetting_stage(tmp_path) -> None:
    """
    @brief      Verify repair recreates one missing support folder without resetting the workflow stage.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-21T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["current_stage"] = "character_voices_ready"
    project_workspace_service.save_manifest(manifest, project_root)
    shutil.rmtree(project_root / config.PROJECT_AUDIO_SAMPLES_FOLDER_NAME)

    open_result = project_workspace_service.open_project(project_root)
    repaired_result = project_workspace_service.repair_project(open_result)

    assert open_result["status"] == "repair_required"
    assert open_result["corrupted_step"] == config.PROJECT_AUDIO_SAMPLES_FOLDER_NAME
    assert repaired_result["status"] == "ok"
    assert repaired_result["manifest"]["current_stage"] == "character_voices_ready"
    assert (project_root / config.PROJECT_AUDIO_SAMPLES_FOLDER_NAME).is_dir()


def test_repair_project_recreates_missing_speech_blocks_folder_without_resetting_character_voices_stage(
    tmp_path,
) -> None:
    """
    @brief      Verify repair recreates one missing Speech Blocks folder without resetting the trusted Character Voices stage.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-21T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["current_stage"] = "character_voices_ready"
    project_workspace_service.save_manifest(manifest, project_root)
    shutil.rmtree(project_root / config.SPEECH_BLOCKS_FOLDER_NAME)

    open_result = project_workspace_service.open_project(project_root)
    repaired_result = project_workspace_service.repair_project(open_result)

    assert open_result["status"] == "repair_required"
    assert open_result["corrupted_step"] == config.SPEECH_BLOCKS_FOLDER_NAME
    assert repaired_result["status"] == "ok"
    assert repaired_result["manifest"]["current_stage"] == "character_voices_ready"
    assert (project_root / config.SPEECH_BLOCKS_FOLDER_NAME).is_dir()


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
    assert validated["voice_assignment_mode"] == config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE


def test_validate_project_manifest_normalizes_voice_assignment_mode() -> None:
    """
    @brief      Verify manifest validation normalizes unsupported voice-assignment values to the default.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    manifest = project_workspace_service.build_project_manifest("Book5_CAL_CAL")
    manifest["voice_assignment_mode"] = "unsupported_mode"

    validated = project_workspace_service.validate_project_manifest(manifest)

    assert validated["voice_assignment_mode"] == config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE


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
    assert "metadata" not in validated["operations"]["extraction"]
    assert "output_paths" not in validated["operations"]["translation"]


def test_save_manifest_projects_detailed_operation_state_to_compact_summary(tmp_path) -> None:
    """
    @brief      Verify saving the manifest strips duplicated detailed operation payload fields.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "CompactManifestProject",
        tmp_path,
    )
    manifest["operations"]["translation"] = {
        "folder_relative_path": config.TRANSLATION_FOLDER_NAME,
        "status": "completed",
        "input_paths": [f"{config.TRANSLATION_FOLDER_NAME}/input_story.json"],
        "output_paths": [f"{config.TRANSLATION_FOLDER_NAME}/{config.TRANSLATED_CHUNKS_FILE_NAME}"],
        "artifact_paths": [f"{config.TRANSLATION_FOLDER_NAME}/{config.TRANSLATION_REPORT_FILE_NAME}"],
        "progress_current": 8,
        "progress_total": 8,
        "mode": "ai_assisted",
        "started_at": "2026-04-11T10:00:00+00:00",
        "completed_at": "2026-04-11T10:10:00+00:00",
        "updated_at": "2026-04-11T10:10:00+00:00",
        "warning_count": 2,
        "metadata": {
            "translated_chunks": [
                {"chunk_id": "chunk-0001", "translated_text": "..."},
            ],
            "warnings": ["warning"],
        },
        "resume_checkpoint": {"next_untranslated_chunk_id": None},
    }

    project_workspace_service.save_manifest(manifest, project_root)

    saved_payload = json.loads((project_root / config.PROJECT_MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
    translation_operation = saved_payload["operations"]["translation"]
    assert translation_operation["status"] == "completed"
    assert translation_operation["progress_current"] == 8
    assert translation_operation["warning_count"] == 2
    assert "input_paths" not in translation_operation
    assert "output_paths" not in translation_operation
    assert "artifact_paths" not in translation_operation
    assert "metadata" not in translation_operation
    assert "resume_checkpoint" not in translation_operation


def test_validate_project_manifest_accepts_legacy_detailed_operation_payloads() -> None:
    """
    @brief      Verify legacy manifests with detailed operation payloads still validate successfully.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    manifest = project_workspace_service.build_project_manifest("LegacyManifest")
    manifest["operations"]["cleanup"] = {
        "folder_relative_path": config.CLEANUP_FOLDER_NAME,
        "status": "completed",
        "input_paths": [f"{config.CLEANUP_FOLDER_NAME}/input_story.txt"],
        "output_paths": [f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"],
        "artifact_paths": [f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANUP_REPORT_FILE_NAME}"],
        "progress_current": 3,
        "progress_total": 3,
        "mode": "ai_assisted",
        "started_at": "2026-04-11T10:00:00+00:00",
        "completed_at": "2026-04-11T10:10:00+00:00",
        "updated_at": "2026-04-11T10:10:00+00:00",
        "warning_count": 1,
        "metadata": {"warning_details": [{"kind": "detail"}]},
        "resume_checkpoint": {"completed_window_count": 3},
    }

    validated = project_workspace_service.validate_project_manifest(manifest)

    assert validated["operations"]["cleanup"]["status"] == "completed"
    assert validated["operations"]["cleanup"]["mode"] == "ai_assisted"
    assert validated["operations"]["cleanup"]["warning_count"] == 1
    assert "metadata" not in validated["operations"]["cleanup"]


def test_repair_manifest_preserves_character_discovery_for_narrator_stage() -> None:
    """
    @brief      Verify repaired narrator-stage manifests keep character discovery data intact.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    manifest = project_workspace_service.build_project_manifest("Book5_CAL_CAL")
    manifest["current_stage"] = "narrator_definition_ready"
    manifest["operations"]["extraction"]["status"] = "completed"
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["translation"]["status"] = "completed"
    manifest["operations"]["character_discovery"]["status"] = "completed"

    repaired_manifest = project_workspace_service._build_repaired_manifest(
        manifest,
        "narrator_definition_ready",
    )

    assert repaired_manifest["operations"]["translation"]["status"] == "completed"
    assert repaired_manifest["operations"]["character_discovery"]["status"] == "completed"


def test_repair_manifest_preserves_character_discovery_for_character_voices_stage() -> None:
    """
    @brief      Verify repaired character-voices-stage manifests keep character discovery data intact.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    manifest = project_workspace_service.build_project_manifest("Book5_CAL_CAL")
    manifest["current_stage"] = "character_voices_ready"
    manifest["operations"]["extraction"]["status"] = "completed"
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["translation"]["status"] = "completed"
    manifest["operations"]["character_discovery"]["status"] = "completed"

    repaired_manifest = project_workspace_service._build_repaired_manifest(
        manifest,
        "character_voices_ready",
    )

    assert repaired_manifest["operations"]["translation"]["status"] == "completed"
    assert repaired_manifest["operations"]["character_discovery"]["status"] == "completed"


# END OF FILE
