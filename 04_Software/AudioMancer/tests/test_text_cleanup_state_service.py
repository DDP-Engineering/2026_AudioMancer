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
@brief Text Cleanup state-service tests for AudioMancer.
@details Verifies that the Text Cleanup page state service derives previews,
         notes, manual edit persistence, and reset payloads from manifest and
         artifact data.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.5.2
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import (
    cleanup_metadata_service,
    narrator_definition_service,
    operation_runtime_service,
    project_workspace_service,
    text_cleanup_state_service,
)

# PUBLIC API


def test_build_manifest_after_cleanup_reset_preserves_extraction_outputs() -> None:
    """
    @brief      Verify cleanup reset clears cleanup/downstream data but preserves extraction metadata.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    manifest = {
        "current_stage": "text_chunking_ready",
        "extraction_warning_count": 0,
        "operations": {
            "extraction": {
                "status": "completed",
                "output_paths": ["00_extraction/output_raw_text.txt"],
            },
            "cleanup": {
                "status": "completed",
                "output_paths": ["10_cleanup/output_clean_text.txt"],
            },
            "chunking": {"status": "completed"},
            "translation": {"status": "completed"},
            "character_discovery": {
                "status": "completed",
            },
        },
    }

    reset_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
        manifest,
        "cleanup",
    )

    assert "extracted_text_relative_path" not in reset_manifest
    assert "extraction_report_relative_path" not in reset_manifest
    assert reset_manifest["operations"]["extraction"]["status"] == "completed"
    assert reset_manifest["operations"]["cleanup"]["status"] == "not_started"
    assert reset_manifest["operations"]["chunking"]["status"] == "not_started"


def test_build_text_cleanup_state_loads_previews_and_notes(tmp_path) -> None:
    """
    @brief      Verify text-cleanup state exposes extracted and cleaned previews plus cleanup summary.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "PresenterProject",
        tmp_path,
    )
    extraction_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    cleanup_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    extraction_root.mkdir(exist_ok=True)
    cleanup_root.mkdir(exist_ok=True)
    (extraction_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        "Extracted text\n",
        encoding="utf-8",
    )
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "Cleaned text\n",
        encoding="utf-8",
    )
    (cleanup_root / config.CLEANUP_REPORT_FILE_NAME).write_text(
        json.dumps(
            {
                "warnings": [],
                "paragraph_count": 3,
                "removed_line_count": 2,
                "detected_chapter_count": 1,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (cleanup_root / config.CLEANUP_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
                "status": "completed",
                "input_paths": [],
                "output_paths": [f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}"],
                "artifact_paths": [f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANUP_REPORT_FILE_NAME}"],
                "progress_current": 1,
                "progress_total": 1,
                "mode": "deterministic",
                "started_at": "2026-04-06T12:00:00+00:00",
                "completed_at": "2026-04-06T12:01:00+00:00",
                "updated_at": "2026-04-06T12:01:00+00:00",
                "warning_count": 0,
                "metadata": {"warnings": []},
                "resume_checkpoint": None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest["source_document"] = {"original_name": "story.txt"}
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}"
    ]

    cleanup_state = text_cleanup_state_service.build_text_cleanup_state(
        project_root,
        manifest,
        "en",
    )

    assert cleanup_state["extracted_text"] == "Extracted text\n"
    assert cleanup_state["cleaned_text"] == "Cleaned text\n"
    assert any("Cleanup produced 3 paragraphs" in note for note in cleanup_state["notes"])


def test_build_text_cleanup_state_surfaces_ai_cleanup_review_warning(tmp_path) -> None:
    """Verify page state is derived from the authoritative AI Cleanup document."""
    project_root, manifest = project_workspace_service.create_project(
        "PresenterAiCleanupWarningProject",
        tmp_path,
    )
    source_text = "Extracted text\n"
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(source_text, encoding="utf-8")
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("Cleaned text\n", encoding="utf-8")
    (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).write_text(
        json.dumps(
            {
                "status": "completed",
                "mode": "ai_assisted",
                "source_fingerprint": "sha256:" + ("0" * 64),
                "instructions": "",
                "token_usage": {
                    "input_tokens": 300,
                    "output_tokens": 75,
                    "total_tokens": 375,
                    "usage_available": True,
                },
                "warnings": [{"kind": "human_review_required"}],
                "decisions": {
                    "selected_spacing_categories": ["heading", "separator"],
                    "items": [{"start": 0, "end": len(source_text), "kind": "story"}],
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest["source_document"] = {"original_name": "story.txt"}

    cleanup_state = text_cleanup_state_service.build_text_cleanup_state(
        project_root,
        manifest,
        "en",
    )

    assert cleanup_state["cleanup_mode"] == "ai_assisted"
    assert cleanup_state["cleanup_status"] == "completed"
    assert cleanup_state["can_apply_ai_spacing"] is True
    assert any("completed with validation warnings" in note for note in cleanup_state["notes"])
    assert any("Input tokens: 300 | Output tokens: 75 | Total: 375" in note for note in cleanup_state["notes"])

def test_save_cleaned_text_edit_persists_text_and_resets_downstream(tmp_path) -> None:
    """
    @brief      Verify manual cleaned-text edits persist and reset downstream workflow state only.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "CleanupEditProject",
        tmp_path,
    )
    cleanup_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    cleanup_root.mkdir(exist_ok=True)
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text("Original clean text\n", encoding="utf-8")
    chunking_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    chunking_root.mkdir(exist_ok=True)
    (chunking_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.CHARACTER_PROFILE_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.CHARACTER_DISCOVERY_REPORT_FILE_NAME).write_text("{}\n", encoding="utf-8")
    (project_root / config.CHARACTER_DISCOVERY_STATE_FILE_NAME).write_text("{}\n", encoding="utf-8")
    narrator_definition_service.ensure_narrator_voice_document(project_root)
    (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).write_text("[]\n", encoding="utf-8")
    manifest["current_stage"] = "text_chunking_ready"
    manifest["narrator_profile_name"] = "Warm Narrator"
    manifest["narrator_language"] = "fr"
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}"
    ]
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["character_discovery"]["status"] = "completed"
    manifest["operations"]["narrator_definition"]["status"] = "completed"
    manifest["operations"]["character_voices"]["status"] = "completed"
    manifest["operations"]["speech_blocks"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)

    updated_manifest = text_cleanup_state_service.save_cleaned_text_edit(
        project_root,
        manifest,
        "Edited clean text\n",
    )

    assert (cleanup_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8") == "Edited clean text\n"
    assert updated_manifest["current_stage"] == "text_cleanup_ready"
    assert updated_manifest["operations"]["cleanup"]["status"] == "completed"
    assert updated_manifest["operations"]["chunking"]["status"] == "not_started"
    assert updated_manifest["operations"]["character_discovery"]["status"] == "not_started"
    assert updated_manifest["operations"]["narrator_definition"]["status"] == "not_started"
    assert updated_manifest["operations"]["character_voices"]["status"] == "not_started"
    assert updated_manifest["operations"]["speech_blocks"]["status"] == "not_started"
    assert updated_manifest["narrator_profile_name"] is None
    assert updated_manifest["narrator_language"] is None
    assert not (chunking_root / config.CHUNK_ARTIFACT_FILE_NAME).exists()
    assert not (project_root / config.CHARACTER_PROFILE_FILE_NAME).exists()
    assert not (project_root / config.CHARACTER_DISCOVERY_REPORT_FILE_NAME).exists()
    assert not (project_root / config.CHARACTER_DISCOVERY_STATE_FILE_NAME).exists()
    assert not (project_root / config.NARRATOR_VOICE_FILE_NAME).exists()
    assert not (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).exists()
    assert not (project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).exists()
    assert not (cleanup_root / config.CLEANED_TEXT_METADATA_FILE_NAME).exists()
    assert not (cleanup_root / config.CLEANUP_STATE_FILE_NAME).exists()
    assert not (cleanup_root / config.CLEANUP_DOCUMENT_FILE_NAME).exists()
    reloaded_manifest = project_workspace_service.load_manifest(project_root)
    assert reloaded_manifest["current_stage"] == "text_cleanup_ready"
    assert reloaded_manifest["operations"]["cleanup"] == {
        "status": "completed",
        "mode": "manual_edit",
        "warning_count": 0,
    }
    loaded_records = cleanup_metadata_service.load_or_build_paragraph_records(project_root, "Edited clean text\n")
    assert loaded_records[0]["text"] == "Edited clean text"


def test_cleanup_reset_can_preserve_character_discovery_and_voice_artifacts() -> None:
    """
    @brief      Verify cleanup rerun resets generated text dependents while preserving discovered characters.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    manifest = {
        "current_stage": "speech_blocks_ready",
        "narrator_profile_name": "Warm Narrator",
        "narrator_language": "fr",
        "operations": {
            "cleanup": {"status": "completed"},
            "chunking": {"status": "completed"},
            "translation": {"status": "completed"},
            "character_discovery": {
                "status": "completed",
            },
            "narrator_definition": {
                "status": "completed",
            },
            "character_voices": {
                "status": "completed",
            },
            "speech_blocks": {
                "status": "completed",
            },
        },
    }

    reset_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
        manifest,
        "cleanup",
        preserve_operation_kinds=operation_runtime_service.TEXT_REVISION_PRESERVED_OPERATION_KINDS,
    )

    assert reset_manifest["current_stage"] == "text_cleanup_ready"
    assert reset_manifest["operations"]["chunking"]["status"] == "not_started"
    assert reset_manifest["operations"]["translation"]["status"] == "not_started"
    assert reset_manifest["operations"]["character_discovery"]["status"] == "completed"
    assert reset_manifest["operations"]["narrator_definition"]["status"] == "completed"
    assert reset_manifest["operations"]["character_voices"]["status"] == "completed"
    assert reset_manifest["operations"]["speech_blocks"]["status"] == "not_started"
    assert reset_manifest["narrator_profile_name"] == "Warm Narrator"
    assert reset_manifest["narrator_language"] == "fr"


def test_cleanup_reset_removes_stale_cleaned_text_metadata(tmp_path) -> None:
    """
    @brief      Verify cleanup reset deletes stale cleaned-text metadata with cleanup artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project(
        "CleanupMetadataResetProject",
        tmp_path,
    )
    cleanup_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    cleanup_root.mkdir(exist_ok=True)
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text("Cleaned text\n", encoding="utf-8")
    (cleanup_root / config.CLEANED_TEXT_METADATA_FILE_NAME).write_text("{}\n", encoding="utf-8")

    operation_runtime_service.reset_operation_data(project_root, "cleanup", include_current=True)

    assert not (cleanup_root / config.CLEANED_TEXT_FILE_NAME).exists()
    assert not (cleanup_root / config.CLEANED_TEXT_METADATA_FILE_NAME).exists()


def test_build_manifest_after_character_discovery_reset_returns_translation_ready() -> None:
    """
    @brief      Verify character-discovery reset preserves upstream state and returns the workflow to translation-ready.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    manifest = {
        "current_stage": "character_discovery_ready",
        "extraction_warning_count": 0,
        "narrator_profile_name": "Warm Narrator",
        "narrator_language": "en",
        "operations": {
            "extraction": {
                "status": "completed",
                "output_paths": ["00_extraction/output_raw_text.txt"],
            },
            "cleanup": {
                "status": "completed",
                "output_paths": ["10_cleanup/output_clean_text.txt"],
            },
            "chunking": {
                "status": "completed",
            },
            "translation": {
                "status": "completed",
            },
            "character_discovery": {
                "status": "completed",
            },
        },
    }

    reset_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
        manifest,
        "character_discovery",
    )

    assert reset_manifest["current_stage"] == "translation_ready"
    assert reset_manifest["operations"]["translation"]["status"] == "completed"
    assert reset_manifest["operations"]["character_discovery"]["status"] == "not_started"
    assert reset_manifest["narrator_profile_name"] is None
    assert reset_manifest["narrator_language"] is None


def test_build_manifest_after_character_discovery_reset_can_preserve_narrator_definition() -> None:
    """
    @brief      Verify character-discovery reset can keep narrator manifest state while clearing dependents.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    manifest = {
        "current_stage": "speech_blocks_ready",
        "narrator_profile_name": "Warm Narrator",
        "narrator_language": "fr",
        "operations": {
            "translation": {
                "status": "completed",
            },
            "character_discovery": {
                "status": "completed",
            },
            "narrator_definition": {
                "status": "completed",
            },
            "character_voices": {
                "status": "completed",
            },
            "speech_blocks": {
                "status": "completed",
            },
        },
    }

    reset_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
        manifest,
        "character_discovery",
        preserve_operation_kinds=operation_runtime_service.NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS,
    )

    assert reset_manifest["current_stage"] == "translation_ready"
    assert reset_manifest["operations"]["translation"]["status"] == "completed"
    assert reset_manifest["operations"]["character_discovery"]["status"] == "not_started"
    assert reset_manifest["operations"]["narrator_definition"]["status"] == "completed"
    assert reset_manifest["operations"]["character_voices"]["status"] == "not_started"
    assert reset_manifest["operations"]["speech_blocks"]["status"] == "not_started"
    assert reset_manifest["narrator_profile_name"] == "Warm Narrator"
    assert reset_manifest["narrator_language"] == "fr"


# END OF FILE
