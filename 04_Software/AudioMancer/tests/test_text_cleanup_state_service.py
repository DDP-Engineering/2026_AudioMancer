#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
         notes, and reset payloads from manifest and artifact data.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.3.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import project_workspace_service, text_cleanup_state_service

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
        "extracted_text_relative_path": "00_extraction/output_raw_text.txt",
        "extraction_report_relative_path": "00_extraction/extraction_report.json",
        "extraction_warning_count": 0,
        "operations": {
            "extraction": {
                "folder_relative_path": config.EXTRACTION_FOLDER_NAME,
                "status": "completed",
                "output_paths": ["00_extraction/output_raw_text.txt"],
            },
            "cleanup": {
                "folder_relative_path": config.CLEANUP_FOLDER_NAME,
                "status": "completed",
                "output_paths": ["10_cleanup/output_clean_text.txt"],
            },
            "chunking": {"folder_relative_path": "20_chunking", "status": "completed"},
            "translation": {"folder_relative_path": "30_translation", "status": "completed"},
            "character_discovery": {
                "folder_relative_path": "40_character_discovery",
                "status": "completed",
            },
        },
    }

    reset_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
        manifest,
        "cleanup",
    )

    assert reset_manifest["extracted_text_relative_path"] == "00_extraction/output_raw_text.txt"
    assert reset_manifest["extraction_report_relative_path"] == "00_extraction/extraction_report.json"
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
    extraction_root = project_root / config.EXTRACTION_FOLDER_NAME
    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
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
    (cleanup_root / config.OPERATION_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": config.CLEANUP_FOLDER_NAME,
                "status": "completed",
                "input_paths": [],
                "output_paths": [f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"],
                "artifact_paths": [f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANUP_REPORT_FILE_NAME}"],
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
    manifest["extracted_text_relative_path"] = f"{config.EXTRACTION_FOLDER_NAME}/{config.EXTRACTED_TEXT_FILE_NAME}"
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"
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
    """
    @brief      Verify AI cleanup notes include one review warning when validation warnings were persisted.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "PresenterAiCleanupWarningProject",
        tmp_path,
    )
    extraction_root = project_root / config.EXTRACTION_FOLDER_NAME
    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
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
                "warnings": [
                    "AI cleanup corrected one invalid page-number label in window 1 and preserved the text for review."
                ],
                "warning_details": [
                    {
                        "kind": "invalid_page_number_label_corrected",
                        "message": "AI cleanup corrected one invalid page-number label in window 1 and preserved the text for review.",
                    }
                ],
                "paragraph_count": 3,
                "removed_line_count": 2,
                "detected_chapter_count": 1,
                "cleanup_mode": "ai_assisted",
                "ai_profile_id": "profile_1",
                "token_usage": {
                    "input_tokens": 300,
                    "output_tokens": 75,
                    "total_tokens": 375,
                    "usage_available": True,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (cleanup_root / config.OPERATION_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": config.CLEANUP_FOLDER_NAME,
                "status": "completed",
                "input_paths": [],
                "output_paths": [f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"],
                "artifact_paths": [f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANUP_REPORT_FILE_NAME}"],
                "progress_current": 1,
                "progress_total": 1,
                "mode": "ai_assisted",
                "started_at": "2026-04-07T12:00:00+00:00",
                "completed_at": "2026-04-07T12:01:00+00:00",
                "updated_at": "2026-04-07T12:01:00+00:00",
                "warning_count": 1,
                "metadata": {
                    "warnings": [],
                    "ai_profile_id": "profile_1",
                    "token_usage": {
                        "input_tokens": 300,
                        "output_tokens": 75,
                        "total_tokens": 375,
                        "usage_available": True,
                    },
                },
                "resume_checkpoint": None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest["source_document"] = {"original_name": "story.txt"}
    manifest["extracted_text_relative_path"] = f"{config.EXTRACTION_FOLDER_NAME}/{config.EXTRACTED_TEXT_FILE_NAME}"
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["mode"] = "ai_assisted"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"
    ]

    cleanup_state = text_cleanup_state_service.build_text_cleanup_state(
        project_root,
        manifest,
        "en",
    )

    assert any("completed with validation warnings" in note for note in cleanup_state["notes"])
    assert any("Input tokens: 300 | Output tokens: 75 | Total: 375" in note for note in cleanup_state["notes"])


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
        "extracted_text_relative_path": "00_extraction/output_raw_text.txt",
        "extraction_report_relative_path": "00_extraction/extraction_report.json",
        "extraction_warning_count": 0,
        "narrator_profile_name": "Warm Narrator",
        "narrator_language": "en",
        "operations": {
            "extraction": {
                "folder_relative_path": config.EXTRACTION_FOLDER_NAME,
                "status": "completed",
                "output_paths": ["00_extraction/output_raw_text.txt"],
            },
            "cleanup": {
                "folder_relative_path": config.CLEANUP_FOLDER_NAME,
                "status": "completed",
                "output_paths": ["10_cleanup/output_clean_text.txt"],
            },
            "chunking": {
                "folder_relative_path": "20_chunking",
                "status": "completed",
            },
            "translation": {
                "folder_relative_path": "30_translation",
                "status": "completed",
            },
            "character_discovery": {
                "folder_relative_path": "40_character_discovery",
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


# END OF FILE
