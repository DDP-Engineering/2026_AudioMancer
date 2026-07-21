#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
         counting, and resumable cancellation state for deterministic chunking.
@author Eng. Dan Dumitru Pasare
@date 2026-04-11
@version 0.3.0
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import (
    chunking_document_service,
    deterministic_chunking_service,
    operation_runtime_service,
    project_workspace_service,
)
from chunking_test_support import read_chunking_document, write_chunking_document


def test_chunking_writes_runtime_artifacts_and_detects_chapters(tmp_path) -> None:
    """
    @brief      Verify chunking writes self-contained artifacts without persisted chapter labels.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
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
    cleaned_relative_path = config.CLEANED_TEXT_FILE_NAME
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [cleaned_relative_path]
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "Chapter I\n\nParagraph one.\n\nParagraph two.\n",
        encoding="utf-8",
    )

    report_payload = deterministic_chunking_service.chunk_text(project_root, manifest)

    assert (project_root / config.CHUNK_ARTIFACT_FILE_NAME).is_file()
    assert not (project_root / "chunking_report.json").exists()
    assert not (project_root / "chunking_state.json").exists()
    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert chunks[0]["chunk_id"] == "chunk-0001"
    assert "chapter_label" not in chunks[0]
    assert "chapter_label" not in chunks[1]
    assert "chapter_label" not in chunks[2]
    assert "source_start_line" not in chunks[2]
    assert report_payload["chunk_count"] == 3
    assert report_payload["detected_chapter_count"] == 1


def test_chunking_uses_canonical_cleanup_output_with_compact_manifest(tmp_path) -> None:
    """
    @brief      Verify chunking reads the canonical cleanup artifact with compact operation summaries.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ChunkCompactManifest",
        tmp_path,
    )
    source_path = project_root / "story.txt"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["progress_current"] = 1
    manifest["operations"]["cleanup"]["progress_total"] = 1
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "Paragraph one.\n\nParagraph two.\n",
        encoding="utf-8",
    )

    report_payload = deterministic_chunking_service.chunk_text(project_root, manifest)

    assert report_payload["chunk_count"] == 2
    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert len(chunks) == 2


def test_chunking_prefers_cleanup_metadata_paragraph_records(tmp_path) -> None:
    """
    @brief      Verify deterministic chunking uses cleanup metadata before blank-line fallback.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ChunkMetadata", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-26T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "Split by visible text.\n\nBut metadata says one unit.\n",
        encoding="utf-8",
    )
    (project_root / config.CLEANED_TEXT_METADATA_FILE_NAME).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "paragraphs": [
                    {
                        "paragraph_id": "paragraph-0001",
                        "source_start_line": 1,
                        "source_end_line": 3,
                        "source_page_start": 1,
                        "source_page_end": 2,
                        "starts_after_page_break": False,
                        "joined_across_page_break": True,
                        "boundary_confidence": "repaired",
                        "warning_flags": [],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    report_payload = deterministic_chunking_service.chunk_text(project_root, manifest)

    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert report_payload["chunk_count"] == 1
    assert len(chunks) == 1
    assert chunks[0]["cleanup_joined_across_page_break"] is True
    assert chunks[0]["cleanup_boundary_confidence"] == "repaired"


def test_chunking_falls_back_when_cleanup_metadata_is_missing(tmp_path) -> None:
    """
    @brief      Verify old projects without cleanup metadata still chunk from cleaned text.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ChunkNoMetadata", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-26T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "Paragraph one.\n\nParagraph two.\n",
        encoding="utf-8",
    )

    report_payload = deterministic_chunking_service.chunk_text(project_root, manifest)

    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert report_payload["chunk_count"] == 2
    assert len(chunks) == 2


def test_chunking_persists_resumable_state_after_cancellation(tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-017 cancelled chunking leaves resumable terminal state on disk.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
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
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [config.CLEANED_TEXT_FILE_NAME]
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "Paragraph one.\n\nParagraph two.\n",
        encoding="utf-8",
    )
    should_cancel = {"value": False}

    def _progress_callback(*_args) -> None:
        """
        @brief      Provide the progress callback test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        should_cancel["value"] = True

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        deterministic_chunking_service.chunk_text(
            project_root,
            manifest,
            progress_callback=_progress_callback,
            cancel_requested=lambda: should_cancel["value"],
        )

    state_payload = read_chunking_document(project_root)
    assert state_payload["status"] == "cancelled"
    assert state_payload["next_paragraph"] is not None
    assert "progress_current" not in state_payload
    assert state_payload["chunks"]


def test_chunking_batches_checkpoints_without_full_chapter_rescans(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify REQ-NFR-015 deterministic chunking avoids per-paragraph persistence and full rescans.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ChunkBatching", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-06-10T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "\n\n".join(f"Paragraph {index}." for index in range(1, 7)) + "\n",
        encoding="utf-8",
    )
    document_write_count = {"value": 0}
    original_write_document = chunking_document_service.write_chunking_document

    def _counting_write_document(output_root, document):
        """
        @brief      Count chunk-artifact writes while preserving real persistence.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-10
        @version    0.1.0
        """
        document_write_count["value"] += 1
        return original_write_document(output_root, document)

    def _unexpected_full_chapter_scan(_chunks):
        """
        @brief      Fail when deterministic chunking falls back to full chapter rescans.
        @return     None.
        @exception  AssertionError Always raised.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-10
        @version    0.1.0
        """
        raise AssertionError("deterministic chunking should use incremental chapter counts")

    monkeypatch.setattr(chunking_document_service, "write_chunking_document", _counting_write_document)
    monkeypatch.setattr(deterministic_chunking_service, "_chapter_count_from_chunks", _unexpected_full_chapter_scan)

    report_payload = deterministic_chunking_service.chunk_text(project_root, manifest)

    assert report_payload["chunk_count"] == 6
    assert document_write_count["value"] == 8


def test_incremental_chapter_count_matches_full_scan() -> None:
    """
    @brief      Verify REQ-NFR-015 incremental chapter counting preserves full-scan semantics.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    chunks = [
        {"text": "Chapter I\nOpening."},
        {"text": "Chapter I\nContinued."},
        {"text": "Paragraph."},
        {"text": "Scene 2\nA change."},
        {"text": "II"},
    ]

    incremental_count, last_label = deterministic_chunking_service._chapter_count_state_from_chunks(chunks)

    assert incremental_count == deterministic_chunking_service._chapter_count_from_chunks(chunks)
    assert last_label == "II"


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
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [config.CLEANED_TEXT_FILE_NAME]
    cleaned_text = "Paragraph one.\n\nParagraph two.\n"
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text(cleaned_text, encoding="utf-8")
    write_chunking_document(
        project_root,
        [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Paragraph one."}],
        source_text=cleaned_text,
        status="running",
        next_paragraph=2,
    )

    report_payload = deterministic_chunking_service.chunk_text(project_root, manifest)

    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert report_payload["chunk_count"] == 2
    assert len(chunks) == 2
    assert chunks[1]["chunk_id"] == "chunk-0002"


def test_load_chunks_returns_empty_for_malformed_artifact(tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-017 malformed chunk artifacts degrade to an empty chunk list.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("ChunkMalformed", tmp_path)
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Reset Chunking"):
        deterministic_chunking_service.load_chunks(project_root)


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
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [config.CLEANED_TEXT_FILE_NAME]
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("\n\n", encoding="utf-8")

    with pytest.raises(ValueError, match="chunkable paragraphs"):
        deterministic_chunking_service.chunk_text(project_root, manifest)


# END OF FILE
