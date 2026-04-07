#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_deterministic_chunking_service.py
@brief Focused tests for the AudioMancer deterministic chunking service.
@details Verifies runtime artifact naming, paragraph chunk generation, chapter
         metadata, and resumable cancellation state for deterministic chunking.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.1.0
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import deterministic_chunking_service
from audiomancer.services import operation_runtime_service
from audiomancer.services import project_workspace_service


def test_chunking_writes_runtime_artifacts_and_detects_chapters(tmp_path) -> None:
    """
    @brief      Verify chunking writes self-contained artifacts and carries chapter labels forward.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ChunkProject", tmp_path)
    source_path = project_root / "story.pdf"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.pdf",
        "stored_relative_path": "story.pdf",
        "file_type": "pdf",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
    cleanup_root.mkdir(exist_ok=True)
    cleaned_relative_path = f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [cleaned_relative_path]
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "Chapter I\n\nParagraph one.\n\nParagraph two.\n",
        encoding="utf-8",
    )

    report_payload = deterministic_chunking_service.chunk_text(project_root, manifest)

    chunk_root = project_root / "20_chunking"
    assert (chunk_root / "input_story.pdf").is_file()
    assert (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).is_file()
    assert (chunk_root / config.CHUNKING_REPORT_FILE_NAME).is_file()
    assert (chunk_root / config.OPERATION_STATE_FILE_NAME).is_file()
    chunks = json.loads((chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))
    assert chunks[0]["chunk_id"] == "chunk-0001"
    assert chunks[1]["chapter_label"] == "Chapter I"
    assert chunks[2]["chapter_label"] == "Chapter I"
    assert chunks[2]["source_start_line"] == 5
    assert report_payload["chunk_count"] == 3
    assert report_payload["detected_chapter_count"] == 1


def test_chunking_persists_resumable_state_after_cancellation(tmp_path) -> None:
    """
    @brief      Verify one cancelled chunking run leaves resumable state on disk.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ChunkCancel", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
    cleanup_root.mkdir(exist_ok=True)
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"
    ]
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "Paragraph one.\n\nParagraph two.\n",
        encoding="utf-8",
    )
    should_cancel = {"value": False}

    def _progress_callback(*_args) -> None:
        should_cancel["value"] = True

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        deterministic_chunking_service.chunk_text(
            project_root,
            manifest,
            progress_callback=_progress_callback,
            cancel_requested=lambda: should_cancel["value"],
        )

    state_payload = json.loads(
        (project_root / "20_chunking" / config.OPERATION_STATE_FILE_NAME).read_text(encoding="utf-8")
    )
    assert state_payload["status"] == "running"
    assert state_payload["progress_current"] < state_payload["progress_total"]
    assert state_payload["resume_checkpoint"] is not None


def test_chunking_resumes_after_interruption(tmp_path) -> None:
    """
    @brief      Verify rerunning an unfinished chunking operation continues from saved progress.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ChunkResume", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
    cleanup_root.mkdir(exist_ok=True)
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"
    ]
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "Paragraph one.\n\nParagraph two.\n",
        encoding="utf-8",
    )
    chunk_root = project_root / "20_chunking"
    chunk_root.mkdir(exist_ok=True)
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps([
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "chapter_label": None,
                "text": "Paragraph one.",
                "source_start_line": 1,
                "source_end_line": 1,
                "chunking_mode": "deterministic",
                "semantic_strategy": None,
                "scene_note": None,
            }
        ], indent=2) + "\n",
        encoding="utf-8",
    )
    (chunk_root / config.OPERATION_STATE_FILE_NAME).write_text(
        json.dumps({
            "folder_relative_path": "20_chunking",
            "status": "running",
            "input_paths": [f"20_chunking/input_story.txt"],
            "output_paths": [f"20_chunking/{config.CHUNK_ARTIFACT_FILE_NAME}"],
            "artifact_paths": [],
            "progress_current": 1,
            "progress_total": 2,
            "mode": "deterministic",
            "started_at": "2026-04-07T12:00:00+00:00",
            "completed_at": None,
            "updated_at": "2026-04-07T12:01:00+00:00",
            "warning_count": 0,
            "metadata": {"warnings": [], "chunk_count": 1, "detected_chapter_count": 0},
            "resume_checkpoint": {"next_chunk_index": 1},
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    report_payload = deterministic_chunking_service.chunk_text(project_root, manifest)

    chunks = json.loads((chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))
    assert report_payload["chunk_count"] == 2
    assert len(chunks) == 2
    assert chunks[1]["chunk_id"] == "chunk-0002"


def test_chunking_rejects_empty_cleaned_text(tmp_path) -> None:
    """
    @brief      Verify empty cleaned text fails with a clear chunking error.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ChunkEmpty", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
    cleanup_root.mkdir(exist_ok=True)
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"
    ]
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text("\n\n", encoding="utf-8")

    with pytest.raises(ValueError, match="chunkable paragraphs"):
        deterministic_chunking_service.chunk_text(project_root, manifest)


# END OF FILE
