#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_chunking_state_service.py
@brief Text Chunking state-service tests for AudioMancer.
@details Verifies chunking-page notes reflect running and resumable AI chunking
         states and manual selected-chunk edits correctly.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.3.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import project_workspace_service, text_chunking_state_service


def test_build_text_chunking_notes_shows_in_progress_note_for_running_ai_chunking() -> None:
    """
    @brief      Verify running AI chunking shows only the in-progress note instead of the ready note.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    notes = text_chunking_state_service.build_text_chunking_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        cleaned_text="Cleaned text",
        chunking_report_payload=None,
        chunking_operation_state={
            "status": "running",
            "mode": "ai_assisted",
            "progress_current": 1,
            "progress_total": 29,
            "metadata": {"semantic_strategy": "scene"},
        },
        has_ai_profiles=True,
        language="en",
    )

    assert any("in progress at 1/29" in note for note in notes)
    assert not any("is ready for the current cleaned text" in note for note in notes)


def test_build_text_chunking_notes_shows_resume_note_for_failed_ai_chunking() -> None:
    """
    @brief      Verify failed AI chunking shows the resume note instead of the in-progress note.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    notes = text_chunking_state_service.build_text_chunking_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        cleaned_text="Cleaned text",
        chunking_report_payload=None,
        chunking_operation_state={
            "status": "failed",
            "mode": "ai_assisted",
            "progress_current": 1,
            "progress_total": 29,
            "metadata": {"semantic_strategy": "scene"},
        },
        has_ai_profiles=True,
        language="en",
    )

    assert any("was not finalized" in note for note in notes)
    assert not any("in progress at 1/29" in note for note in notes)


def test_build_text_chunking_notes_shows_persisted_token_usage_summary() -> None:
    """
    @brief      Verify AI chunking notes include one persisted token-usage summary.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    notes = text_chunking_state_service.build_text_chunking_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        cleaned_text="Cleaned text",
        chunking_report_payload={
            "chunk_count": 4,
            "detected_chapter_count": 1,
            "chunking_mode": "ai_assisted",
            "semantic_strategy": "scene",
            "warnings": [],
            "token_usage": {
                "input_tokens": 120,
                "output_tokens": 30,
                "total_tokens": 150,
                "usage_available": True,
            },
        },
        chunking_operation_state={
            "status": "completed",
            "mode": "ai_assisted",
            "metadata": {"semantic_strategy": "scene"},
        },
        has_ai_profiles=True,
        language="en",
    )

    assert any("Input tokens: 120 | Output tokens: 30 | Total: 150" in note for note in notes)


def test_save_chunk_text_edit_persists_text_and_resets_downstream(tmp_path) -> None:
    """
    @brief      Verify selected chunk edits persist and reset only downstream workflow state.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ChunkEditProject",
        tmp_path,
    )
    chunking_root = project_root / config.CHUNKING_FOLDER_NAME
    chunking_root.mkdir(exist_ok=True)
    chunk_artifact_path = chunking_root / config.CHUNK_ARTIFACT_FILE_NAME
    chunk_artifact_path.write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "text": "Original chunk",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    translation_root = project_root / config.TRANSLATION_FOLDER_NAME
    translation_root.mkdir(exist_ok=True)
    (translation_root / "artifact.txt").write_text("stale", encoding="utf-8")
    manifest["current_stage"] = "character_discovery_ready"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["translation"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)

    updated_manifest = text_chunking_state_service.save_chunk_text_edit(
        project_root,
        manifest,
        "chunk-0001",
        "Edited chunk",
    )

    chunks = json.loads(chunk_artifact_path.read_text(encoding="utf-8"))
    assert chunks[0]["text"] == "Edited chunk"
    assert updated_manifest["current_stage"] == "translation_ready"
    assert updated_manifest["operations"]["chunking"]["status"] == "completed"
    assert updated_manifest["operations"]["translation"]["status"] == "not_started"
    assert not (translation_root / "artifact.txt").exists()


# END OF FILE
