#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
@version 1.1.5
"""

# IMPORTS

import json
from pathlib import Path

import pytest

from audiomancer import config
from audiomancer.services import project_export_service, project_workspace_service

# PUBLIC API


def test_create_project_creates_required_structure_and_manifest(tmp_path) -> None:
    """
    @brief      Verify project creation writes the required folders and manifest.
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

    assert project_root == tmp_path / "Book5_CAL_CAL"
    assert manifest["display_name"] == "Book5_CAL_CAL"
    assert manifest["current_stage"] == config.DEFAULT_WORKFLOW_STAGE
    assert manifest["source_document"] is None
    assert manifest["extraction_warning_count"] == 0
    assert manifest["operations"]["extraction"]["status"] == "not_started"
    assert "folder_relative_path" not in manifest["operations"]["cleanup"]
    assert manifest["voice_assignment_mode"] == config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE
    assert "metadata" not in manifest["operations"]["extraction"]
    assert "output_paths" not in manifest["operations"]["cleanup"]
    assert (project_root / config.PROJECT_MANIFEST_FILE_NAME).is_file()
    assert not any(path.is_dir() for path in project_root.iterdir())


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


def test_open_project_resolves_flat_project_root(tmp_path) -> None:
    """
    @brief      Verify opening succeeds when selecting the flat project root.
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

    open_result = project_workspace_service.open_project(created_root)

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


def test_open_project_rejects_legacy_numbered_layout(tmp_path) -> None:
    """
    @brief      Verify opening fails when legacy numbered workflow folders are present.
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
    (project_root / "50_narrator_definition").mkdir()

    with pytest.raises(ValueError, match="unsupported legacy numbered runtime layout"):
        project_workspace_service.open_project(project_root)


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


def test_open_project_rejects_legacy_downstream_folder_layout(
    tmp_path,
) -> None:
    """
    @brief      Verify numbered downstream folders are rejected instead of repaired.
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
    (project_root / "30_translation").mkdir()
    (project_root / "30_translation" / "artifact.txt").write_text("old-data", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported legacy numbered runtime layout"):
        project_workspace_service.open_project(project_root)


def test_open_project_accepts_current_required_folder_contract(tmp_path) -> None:
    """
    @brief      Verify project validation accepts the current required workflow-folder contract.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.0
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

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "ok"
    assert open_result["manifest"]["current_stage"] == "character_voices_ready"


def test_open_project_does_not_require_speech_blocks_folder_for_flat_layout(
    tmp_path,
) -> None:
    """
    @brief      Verify flat-layout validation does not require a Speech Blocks folder.
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

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "ok"
    assert open_result["manifest"]["current_stage"] == "character_voices_ready"
    assert (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH).is_dir()


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


@pytest.mark.parametrize("stored_relative_path", ["source/../../outside.txt", "/outside.txt"])
def test_validate_project_manifest_rejects_unsafe_source_document_paths(stored_relative_path: str) -> None:
    """
    @brief      Verify manifest validation rejects traversal and absolute source paths.
    @param[in]  stored_relative_path Candidate unsafe source-document path.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    manifest = project_workspace_service.build_project_manifest("UnsafeSource")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": stored_relative_path,
        "file_type": "txt",
        "imported_at": "2026-04-29T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["current_stage"] = "source_selected"

    with pytest.raises(ValueError, match="source_document.stored_relative_path"):
        project_workspace_service.validate_project_manifest(manifest)


def test_open_project_rejects_source_document_symlink_escape(tmp_path) -> None:
    """
    @brief      Verify project-open validation rejects source symlinks resolving outside the project.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project("SymlinkSource", tmp_path)
    outside_source = tmp_path / "outside.txt"
    outside_source.write_text("outside", encoding="utf-8")
    linked_source = project_root / "linked_source.txt"
    try:
        linked_source.symlink_to(outside_source)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Filesystem does not allow file symlink creation: {exc}")
    manifest["source_document"] = {
        "original_name": "outside.txt",
        "stored_relative_path": "linked_source.txt",
        "file_type": "txt",
        "imported_at": "2026-04-29T12:00:00+00:00",
        "size_bytes": outside_source.stat().st_size,
    }
    manifest["current_stage"] = "source_selected"
    _write_json(project_root / config.PROJECT_MANIFEST_FILE_NAME, manifest)

    with pytest.raises(ValueError, match="source_document.stored_relative_path"):
        project_workspace_service.open_project(project_root)


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
            "folder_relative_path": ".",
            "status": "running",
            "progress_current": 1,
            "progress_total": 3,
        }
    }

    validated = project_workspace_service.validate_project_manifest(manifest)

    assert validated["operations"]["extraction"]["status"] == "running"
    assert validated["operations"]["extraction"]["progress_current"] == 1
    assert "folder_relative_path" not in validated["operations"]["extraction"]
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
        "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        "status": "completed",
        "input_paths": [config.CHUNK_ARTIFACT_FILE_NAME],
        "output_paths": [config.TRANSLATED_CHUNKS_FILE_NAME],
        "artifact_paths": [config.TRANSLATION_REPORT_FILE_NAME],
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
    assert "folder_relative_path" not in translation_operation
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
        "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        "status": "completed",
        "input_paths": [config.EXTRACTED_TEXT_FILE_NAME],
        "output_paths": [config.CLEANED_TEXT_FILE_NAME],
        "artifact_paths": [config.CLEANUP_REPORT_FILE_NAME],
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


def test_open_project_heals_completed_speech_blocks_manifest_summary(tmp_path) -> None:
    """
    @brief      Verify completed Speech Blocks artifacts heal stale manifest metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("SpeechHeal", tmp_path)
    _write_json(project_root / config.SPEECH_BLOCKS_STATE_FILE_NAME, _operation_state("completed", 2, 2))
    _write_json(
        project_root / config.SPEECH_BLOCKS_REPORT_FILE_NAME,
        {
            "speech_blocks_stage_status": "completed",
            "speech_block_count": 2,
            "approved_block_count": 2,
            "total_block_count": 2,
            "warning_count": 0,
        },
    )
    _write_json(
        project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME,
        [
            {"speech_block_id": "sb-1", "speaker_name": "Narrator", "text": "One", "approved": True},
            {"speech_block_id": "sb-2", "speaker_name": "Narrator", "text": "Two", "approved": True},
        ],
    )
    manifest["current_stage"] = "speech_blocks_ready"
    manifest["operations"]["speech_blocks"]["status"] = "not_started"
    project_workspace_service.save_manifest(manifest, project_root)

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "repair_required"
    assert "speech_blocks: not_started -> completed" in open_result["changes"]
    repaired_result = project_workspace_service.repair_project(open_result)
    repaired_manifest = repaired_result["manifest"]

    assert repaired_manifest["operations"]["speech_blocks"]["status"] == "completed"
    readiness = project_export_service.build_export_states(project_root, repaired_manifest)
    speech_readiness = next(
        state for state in readiness if state["export_kind"] == project_export_service.EXPORT_KIND_SPEECH_BLOCKS
    )
    assert speech_readiness["status"] == "available"


def test_open_project_heals_audio_blocks_manifest_from_completed_report_with_stale_state(tmp_path) -> None:
    """
    @brief      Verify completed Audio Blocks report and files heal stale state metadata with a warning.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("AudioHeal", tmp_path)
    audio_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    audio_root.mkdir()
    audio_path = audio_root / "sb-1.wav"
    audio_path.write_bytes(b"RIFF")
    _write_json(
        project_root / config.AUDIO_BLOCKS_STATE_FILE_NAME,
        {
            **_operation_state("in_progress", 1, 1),
            "output_paths": [config.AUDIO_BLOCKS_OUTPUT_FILE_NAME],
            "artifact_paths": [str(Path(config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME) / "sb-1.wav")],
        },
    )
    _write_json(
        project_root / config.AUDIO_BLOCKS_REPORT_FILE_NAME,
        {
            "audio_blocks_stage_status": "completed",
            "generated_block_count": 1,
            "approved_block_count": 1,
            "total_block_count": 1,
            "warning_count": 0,
            "updated_at": "2026-04-25T12:00:00+00:00",
        },
    )
    _write_json(
        project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME,
        [
            {
                "speech_block_id": "sb-1",
                "audio_relative_path": str(Path(config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME) / "sb-1.wav"),
                "generated": True,
                "approved": True,
            }
        ],
    )
    manifest["current_stage"] = "audio_blocks_ready"
    manifest["operations"]["audio_blocks"]["status"] = "in_progress"
    project_workspace_service.save_manifest(manifest, project_root)

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "repair_required"
    assert "audio_blocks: in_progress -> completed" in open_result["changes"]
    assert any(config.AUDIO_BLOCKS_STATE_FILE_NAME in warning for warning in open_result["warnings"])
    assert open_result["normalized_manifest"]["operations"]["audio_blocks"]["status"] == "completed"


def test_open_project_does_not_require_repair_when_only_stale_state_warning_remains(tmp_path) -> None:
    """
    @brief      Verify stale operation-state warnings alone do not reopen the repair dialog.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("AudioHealAlreadyApplied", tmp_path)
    audio_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    audio_root.mkdir()
    (audio_root / "sb-1.wav").write_bytes(b"RIFF")
    _write_json(
        project_root / config.AUDIO_BLOCKS_STATE_FILE_NAME,
        {
            **_operation_state("in_progress", 1, 1),
            "output_paths": [config.AUDIO_BLOCKS_OUTPUT_FILE_NAME],
            "artifact_paths": [str(Path(config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME) / "sb-1.wav")],
        },
    )
    _write_json(
        project_root / config.AUDIO_BLOCKS_REPORT_FILE_NAME,
        {
            "audio_blocks_stage_status": "completed",
            "generated_block_count": 1,
            "approved_block_count": 1,
            "total_block_count": 1,
            "warning_count": 0,
            "updated_at": "2026-04-25T12:00:00+00:00",
        },
    )
    _write_json(
        project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME,
        [
            {
                "speech_block_id": "sb-1",
                "audio_relative_path": str(Path(config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME) / "sb-1.wav"),
                "generated": True,
                "approved": True,
            }
        ],
    )
    manifest["current_stage"] = "audio_blocks_ready"
    manifest["operations"]["audio_blocks"]["status"] = "in_progress"
    project_workspace_service.save_manifest(manifest, project_root)

    first_open_result = project_workspace_service.open_project(project_root)
    assert first_open_result["status"] == "repair_required"
    project_workspace_service.repair_project(first_open_result)

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "ok"
    assert open_result["manifest"]["operations"]["audio_blocks"]["status"] == "completed"


def test_open_project_ignores_narrator_timestamp_drift_with_noncompleted_downstream_artifacts(tmp_path) -> None:
    """
    @brief      Verify narrator timestamp drift and intentionally non-completed downstream artifacts open cleanly.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.1
    """
    project_root, manifest = project_workspace_service.create_project("NarratorTimestampDrift", tmp_path)
    profile_id = "narrator-1"
    selected_at = "2026-05-11T10:23:11+00:00"
    _write_json(
        project_root / config.NARRATOR_PROFILE_FILE_NAME,
        [
            {
                "profile_id": profile_id,
                "display_name": "Selected Narrator",
                "language": "en",
            }
        ],
    )
    _write_json(
        project_root / config.NARRATOR_SELECTION_FILE_NAME,
        {
            "selected_profile_id": profile_id,
            "display_name": "Selected Narrator",
            "selected_language": "en",
            "selected_at": selected_at,
        },
    )
    _write_json(
        project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME,
        [{"speech_block_id": "sb-1", "approved": False}],
    )
    _write_json(
        project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME,
        [{"speech_block_id": "sb-1", "generated": False}],
    )
    manifest["current_stage"] = "narrator_definition_ready"
    manifest["narrator_profile_name"] = "Selected Narrator"
    manifest["narrator_language"] = "en"
    manifest["operations"]["narrator_definition"] = project_workspace_service.project_manifest_operation_summary(
        "narrator_definition",
        {
            **_operation_state("completed", 1, 1),
            "mode": "manual",
            "started_at": "2026-05-11T10:23:10+00:00",
            "completed_at": "2026-05-11T10:23:10+00:00",
            "updated_at": "2026-05-11T10:23:10+00:00",
        },
    )
    manifest["operations"]["speech_blocks"] = {
        **manifest["operations"]["speech_blocks"],
        "status": "review_pending",
    }
    manifest["operations"]["audio_blocks"] = {
        **manifest["operations"]["audio_blocks"],
        "status": "in_progress",
    }
    project_workspace_service.save_manifest(manifest, project_root)

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "ok"
    assert open_result["manifest"]["operations"]["narrator_definition"]["status"] == "completed"
    assert open_result["manifest"]["operations"]["speech_blocks"]["status"] == "review_pending"
    assert open_result["manifest"]["operations"]["audio_blocks"]["status"] == "in_progress"


def test_open_project_heals_completed_character_voices_manifest_summary(tmp_path) -> None:
    """
    @brief      Verify Character Voices samples heal stale manifest status metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.1
    """
    project_root, manifest = project_workspace_service.create_project("CharacterVoicesHeal", tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-05-16T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["current_stage"] = "character_voices_ready"
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / "story.txt").write_text("Story.", encoding="utf-8")
    (project_root / config.SELECTED_NARRATOR_AUDIO_FILE_NAME).write_bytes(b"RIFF-narrator")
    _write_json(
        project_root / config.SELECTED_NARRATOR_METADATA_FILE_NAME,
        {
            "voice_language": "en",
            "preview_text": "Narrator preview.",
            "selected_at": "2026-05-16T12:01:00+00:00",
        },
    )
    (project_root / "audio_alice.wav").write_bytes(b"RIFF-alice")
    _write_json(
        project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME,
        [
            {
                "target_id": "narrator",
                "target_kind": "narrator",
                "display_name": "Narator Voice",
                "sample_audio_path": None,
                "sample_metadata": None,
            },
            {
                "target_id": "character_alice",
                "target_kind": "character",
                "display_name": "Alice",
                "sample_audio_path": "audio_alice.wav",
                "sample_metadata": {
                    "target_id": "character_alice",
                    "voice_language": "en",
                    "preview_text": "Alice preview.",
                    "generated_at": "2026-05-16T12:02:00+00:00",
                },
            },
        ],
    )

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "repair_required"
    operation_summary = open_result["normalized_manifest"]["operations"]["character_voices"]
    assert operation_summary["status"] == "completed"
    assert operation_summary["progress_current"] == 2
    assert operation_summary["progress_total"] == 2
    assert "updated_at" not in operation_summary


def test_open_project_does_not_heal_audio_blocks_with_traversal_audio_path(tmp_path) -> None:
    """
    @brief      Verify traversal audio paths cannot prove Audio Blocks completion.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("AudioTraversal", tmp_path)
    audio_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    audio_root.mkdir()
    outside_audio_path = tmp_path / "outside.wav"
    outside_audio_path.write_bytes(b"RIFF")
    traversal_audio_path = str(Path(config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME) / ".." / ".." / "outside.wav")
    _write_json(
        project_root / config.AUDIO_BLOCKS_STATE_FILE_NAME,
        {
            **_operation_state("in_progress", 1, 1),
            "output_paths": [config.AUDIO_BLOCKS_OUTPUT_FILE_NAME],
            "artifact_paths": [traversal_audio_path],
        },
    )
    _write_json(
        project_root / config.AUDIO_BLOCKS_REPORT_FILE_NAME,
        {
            "audio_blocks_stage_status": "completed",
            "generated_block_count": 1,
            "approved_block_count": 1,
            "total_block_count": 1,
            "warning_count": 0,
            "updated_at": "2026-04-29T12:00:00+00:00",
        },
    )
    _write_json(
        project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME,
        [
            {
                "speech_block_id": "sb-1",
                "audio_relative_path": traversal_audio_path,
                "generated": True,
                "approved": True,
            }
        ],
    )
    manifest["operations"]["audio_blocks"]["status"] = "in_progress"
    project_workspace_service.save_manifest(manifest, project_root)

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "ok"
    assert open_result["manifest"]["operations"]["audio_blocks"]["status"] == "in_progress"


def test_open_project_advances_current_stage_from_contiguous_completed_artifacts(tmp_path) -> None:
    """
    @brief      Verify current stage advances only when contiguous workflow evidence exists.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("StageHeal", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("Story", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-25T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("Story", encoding="utf-8")
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("Story", encoding="utf-8")
    _write_json(project_root / config.EXTRACTION_STATE_FILE_NAME, _operation_state("completed", 1, 1))
    _write_json(project_root / config.EXTRACTION_REPORT_FILE_NAME, {"warning_count": 0})
    _write_json(project_root / config.CLEANUP_STATE_FILE_NAME, _operation_state("completed", 1, 1))
    _write_json(project_root / config.CLEANUP_REPORT_FILE_NAME, {"warning_count": 0})

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "repair_required"
    assert "current_stage: project_created -> text_cleanup_ready" in open_result["changes"]
    assert open_result["normalized_manifest"]["current_stage"] == "text_cleanup_ready"


def test_open_project_warns_for_corrupt_speech_blocks_artifact_without_healing(tmp_path) -> None:
    """
    @brief      Verify corrupt artifacts produce warnings but no completed metadata promotion.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("CorruptSpeech", tmp_path)
    manifest["current_stage"] = "speech_blocks_ready"
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).write_text("{broken", encoding="utf-8")

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "ok"
    assert open_result["manifest"]["operations"]["speech_blocks"]["status"] == "not_started"


def _operation_state(status: str, current: int, total: int) -> dict[str, object]:
    """
    @brief      Build a compact operation-state fixture.
    @param[in]  status Operation status token.
    @param[in]  current Current progress count.
    @param[in]  total Total progress count.
    @return     Operation-state fixture payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    completed_at = "2026-04-25T12:01:00+00:00" if status == "completed" else None
    return {
        "status": status,
        "progress_current": current,
        "progress_total": total,
        "mode": "test",
        "started_at": "2026-04-25T12:00:00+00:00",
        "completed_at": completed_at,
        "updated_at": "2026-04-25T12:01:00+00:00",
        "warning_count": 0,
    }


def _write_json(path: Path, payload: object) -> None:
    """
    @brief      Write one JSON fixture file.
    @param[in]  path Target file path.
    @param[in]  payload JSON-serializable payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# END OF FILE
