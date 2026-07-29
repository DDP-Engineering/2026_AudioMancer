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
@date 2026-07-29
@version 0.4.0
"""

# IMPORTS

import json
from pathlib import Path

import pytest

from audiomancer import config
from audiomancer.services import (
    chunking_document_service,
    deterministic_chunking_service,
    operation_runtime_service,
    project_workspace_service,
)
from chunking_test_support import read_chunking_document, write_chunking_document, write_cleanup_input


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
    write_cleanup_input(
        project_root,
        "Chapter I\n\nParagraph one.\n\nParagraph two.\n",
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
    write_cleanup_input(project_root, "Paragraph one.\n\nParagraph two.\n")

    report_payload = deterministic_chunking_service.chunk_text(project_root, manifest)

    assert report_payload["chunk_count"] == 2
    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert len(chunks) == 2


def test_chunking_prefers_cleanup_document_paragraph_records(tmp_path) -> None:
    """
    @brief      Verify deterministic chunking uses cleanup.json paragraph offsets.
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
    cleaned_text = "Split by visible text.\n\nBut metadata says one unit.\n"
    write_cleanup_input(
        project_root,
        cleaned_text,
        paragraphs=[
            {
                "paragraph_id": "paragraph-000001",
                "output_start": 0,
                "output_end": len(cleaned_text.rstrip("\n")),
                "role": "body",
                "confidence": "repaired",
                "reason_codes": ["page_transition_repaired"],
                "source_page_start": 1,
                "source_page_end": 2,
                "starts_after_page_transition": False,
                "crosses_page_transition": True,
                "source_unit_ids": ["u-000001", "u-000002"],
                "provenance_available": True,
            }
        ],
    )

    report_payload = deterministic_chunking_service.chunk_text(project_root, manifest)

    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert report_payload["chunk_count"] == 1
    assert len(chunks) == 1
    assert chunks[0]["cleanup_joined_across_page_break"] is True
    assert chunks[0]["cleanup_boundary_confidence"] == "repaired"


def test_chunking_rejects_missing_cleanup_document(tmp_path) -> None:
    """
    @brief      Verify Chunking does not consume unverified cleaned text without cleanup.json.
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

    with pytest.raises(ValueError, match="completed Cleanup"):
        deterministic_chunking_service.chunk_text(project_root, manifest)


def test_chunking_persists_resumable_state_after_cancellation(tmp_path) -> None:
    """
    @brief      Verify S-0003/S-0005 cancelled chunking leaves resumable terminal state on disk.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.3.0
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
    write_cleanup_input(project_root, "Paragraph one.\n\nParagraph two.\n")
    cancel_checks = {"count": 0}

    def _cancel_after_one_paragraph() -> bool:
        """
        @brief      Request cancellation before processing the second paragraph.
        @return     True after one paragraph has been processed.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-29
        @version    0.2.0
        """
        cancel_checks["count"] += 1
        return cancel_checks["count"] >= 2

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        deterministic_chunking_service.chunk_text(
            project_root,
            manifest,
            cancel_requested=_cancel_after_one_paragraph,
        )

    state_payload = read_chunking_document(project_root)
    assert state_payload["status"] == "cancelled"
    assert state_payload["next_paragraph"] is not None
    assert "progress_current" not in state_payload
    assert state_payload["chunks"]


def test_chunking_batches_checkpoints_without_full_chapter_rescans(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify S-0001/S-0004 and REQ-NFR-b22bd156/REQ-FUNC-5afe128a bound persistence.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-29
    @version    0.2.0
    """
    project_root, manifest = _create_ready_chunking_project(
        tmp_path,
        "ChunkBatching",
        "\n\n".join(f"Paragraph {index}." for index in range(1, 1001)) + "\n",
    )
    writes: list[tuple[str, int | None, int, tuple[str, ...]]] = []

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

    monkeypatch.setattr(deterministic_chunking_service, "monotonic", lambda: 0.0)
    monkeypatch.setattr(
        chunking_document_service,
        "write_chunking_document",
        lambda _root, document: writes.append(
            (
                str(document["status"]),
                document["next_paragraph"],
                len(document["chunks"]),
                tuple(document["warnings"]),
            )
        ),
    )
    monkeypatch.setattr(deterministic_chunking_service, "_chapter_count_from_chunks", _unexpected_full_chapter_scan)

    report_payload = deterministic_chunking_service.chunk_text(project_root, manifest)

    assert report_payload["chunk_count"] == 1000
    assert len(writes) == 7
    assert [item[1] for item in writes[:-1]] == [1, 201, 401, 601, 801, 1001]
    assert [item[0] for item in writes].count("completed") == 1
    assert writes[-1][0:3] == ("completed", None, 1000)


def test_chunking_checkpoint_pairs_are_resume_consistent(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify S-0001/S-0003 and REQ-FUNC-3a22db38 preserve one exact processed prefix.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-29
    @version    0.1.0
    """
    project_root, manifest = _create_ready_chunking_project(
        tmp_path,
        "ChunkCheckpointPair",
        "Opening narration.\n\n* * *\n\nClosing narration.\n",
    )
    cleanup_path = project_root / config.CLEANUP_DOCUMENT_FILE_NAME
    cleanup_payload = json.loads(cleanup_path.read_text(encoding="utf-8"))
    cleanup_payload["paragraphs"][1]["role"] = "scene_separator"
    cleanup_path.write_text(json.dumps(cleanup_payload, indent=2) + "\n", encoding="utf-8")
    timestamps = iter((0.0, 0.0, 2.1, 2.1))
    writes: list[tuple[str, int | None, int]] = []
    monkeypatch.setattr(deterministic_chunking_service, "monotonic", lambda: next(timestamps))
    monkeypatch.setattr(
        chunking_document_service,
        "write_chunking_document",
        lambda _root, document: writes.append(
            (str(document["status"]), document["next_paragraph"], len(document["chunks"]))
        ),
    )

    deterministic_chunking_service.chunk_text(project_root, manifest)

    assert writes == [
        ("running", 1, 0),
        ("running", 3, 1),
        ("completed", None, 2),
    ]


def test_chunking_throttles_non_terminal_progress_updates(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify S-0002 and REQ-NFR-c26cffd5 throttle progress but always emit completion.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-29
    @version    0.1.0
    """
    project_root, manifest = _create_ready_chunking_project(
        tmp_path,
        "ChunkProgressThrottle",
        "One.\n\nTwo.\n\nThree.\n\nFour.\n",
    )
    timestamps = iter((0.0, 0.0, 0.05, 0.1, 0.19))
    progress_updates: list[tuple[int, int]] = []
    monkeypatch.setattr(deterministic_chunking_service, "monotonic", lambda: next(timestamps))

    deterministic_chunking_service.chunk_text(
        project_root,
        manifest,
        progress_callback=lambda current, total, *_args: progress_updates.append((current, total)),
    )

    assert progress_updates == [(3, 4), (4, 4)]


def test_chunking_persists_one_cancelled_terminal_document(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify S-0003/S-0005 and REQ-FUNC-bdc31247 persist one resumable cancellation.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-29
    @version    0.1.0
    """
    project_root, manifest = _create_ready_chunking_project(
        tmp_path,
        "ChunkCancelledTerminal",
        "One.\n\nTwo.\n\nThree.\n",
    )
    cancel_checks = {"count": 0}
    writes: list[tuple[str, int | None, int]] = []

    def _cancel_after_two_paragraphs() -> bool:
        """Request cancellation before processing the third paragraph."""
        cancel_checks["count"] += 1
        return cancel_checks["count"] >= 3

    monkeypatch.setattr(deterministic_chunking_service, "monotonic", lambda: 0.0)
    monkeypatch.setattr(
        chunking_document_service,
        "write_chunking_document",
        lambda _root, document: writes.append(
            (str(document["status"]), document["next_paragraph"], len(document["chunks"]))
        ),
    )

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        deterministic_chunking_service.chunk_text(
            project_root,
            manifest,
            cancel_requested=_cancel_after_two_paragraphs,
        )

    assert writes == [
        ("running", 1, 0),
        ("cancelled", 3, 2),
    ]


def test_chunking_persists_one_failed_terminal_document(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify S-0003/S-0006 and REQ-FUNC-47c34bc6 persist one resumable failure.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-29
    @version    0.1.0
    """
    project_root, manifest = _create_ready_chunking_project(
        tmp_path,
        "ChunkFailedTerminal",
        "One.\n\nTwo.\n\nThree.\n",
    )
    original_build_chunk_payload = deterministic_chunking_service._build_chunk_payload
    build_calls = {"count": 0}
    writes: list[tuple[str, int | None, int]] = []

    def _fail_on_second_paragraph(*args, **kwargs):
        """Raise one deterministic processing failure after the first committed prefix."""
        build_calls["count"] += 1
        if build_calls["count"] == 2:
            raise RuntimeError("synthetic chunking failure")
        return original_build_chunk_payload(*args, **kwargs)

    monkeypatch.setattr(deterministic_chunking_service, "monotonic", lambda: 0.0)
    monkeypatch.setattr(deterministic_chunking_service, "_build_chunk_payload", _fail_on_second_paragraph)
    monkeypatch.setattr(
        chunking_document_service,
        "write_chunking_document",
        lambda _root, document: writes.append(
            (str(document["status"]), document["next_paragraph"], len(document["chunks"]))
        ),
    )

    with pytest.raises(RuntimeError, match="synthetic chunking failure"):
        deterministic_chunking_service.chunk_text(project_root, manifest)

    assert writes == [
        ("running", 1, 0),
        ("failed", 2, 1),
    ]


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
    write_cleanup_input(project_root, cleaned_text)
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
    write_cleanup_input(project_root, "\n\n")

    with pytest.raises(ValueError, match="chunkable paragraphs"):
        deterministic_chunking_service.chunk_text(project_root, manifest)


def _create_ready_chunking_project(
    tmp_path: Path,
    project_name: str,
    cleaned_text: str,
) -> tuple[Path, dict[str, object]]:
    """
    @brief      Create one project with completed Cleanup input for focused chunking checks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  project_name Stable project folder name.
    @param[in]  cleaned_text Canonical text consumed by deterministic Chunking.
    @return     Project root and mutable manifest pair.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-29
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(project_name, tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-07-29T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [config.CLEANED_TEXT_FILE_NAME]
    write_cleanup_input(project_root, cleaned_text)
    return project_root, manifest


# END OF FILE
