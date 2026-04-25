#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_deterministic_cleanup_service.py
@brief Focused tests for the AudioMancer deterministic cleanup service.
@details Verifies runtime artifact naming, conservative cleanup behavior, and
         resumable cancellation state for deterministic text cleanup.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.1.4
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import deterministic_cleanup_service, operation_runtime_service, project_workspace_service


def test_cleanup_writes_runtime_artifacts_and_preserves_structure(tmp_path) -> None:
    """
    @brief      Verify cleanup writes self-contained artifacts and keeps chapter/paragraph structure.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
    """
    project_root, manifest = project_workspace_service.create_project("CleanupProject", tmp_path)
    source_path = project_root / "story.pdf"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.pdf",
        "stored_relative_path": "story.pdf",
        "file_type": "pdf",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    extracted_relative_path = config.EXTRACTED_TEXT_FILE_NAME
    manifest["extracted_text_relative_path"] = extracted_relative_path
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        (
            "Book Title\n1\nChapter I\nThis is the first paragraph"
            "\n\n\f\n\n"
            "Book Title\n2\ncontinuing on the second page.\n\nNew paragraph."
        ),
        encoding="utf-8",
    )

    report_payload = deterministic_cleanup_service.clean_text(project_root, manifest)

    assert (project_root / config.CLEANED_TEXT_FILE_NAME).is_file()
    assert (project_root / config.CLEANUP_REPORT_FILE_NAME).is_file()
    assert (project_root / config.CLEANUP_STATE_FILE_NAME).is_file()
    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "Book Title" not in output_text
    assert "Chapter I" in output_text
    assert "This is the first paragraph continuing on the second page." in output_text
    assert "\n\nNew paragraph.\n" in output_text
    assert report_payload["paragraph_count"] == 2
    assert report_payload["removed_line_count"] >= 3


def test_cleanup_persists_resumable_state_after_cancellation(tmp_path) -> None:
    """
    @brief      Verify one cancelled cleanup run leaves resumable state on disk.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
    """
    project_root, manifest = project_workspace_service.create_project("CleanupCancel", tmp_path)
    source_path = project_root / "story.pdf"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.pdf",
        "stored_relative_path": "story.pdf",
        "file_type": "pdf",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["extracted_text_relative_path"] = config.EXTRACTED_TEXT_FILE_NAME
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        "Header\n1\nParagraph one.\n\n\f\n\nHeader\n2\nParagraph two.",
        encoding="utf-8",
    )
    should_cancel = {"value": False}

    def _progress_callback(*_args) -> None:
        should_cancel["value"] = True

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        deterministic_cleanup_service.clean_text(
            project_root,
            manifest,
            progress_callback=_progress_callback,
            cancel_requested=lambda: should_cancel["value"],
        )

    state_payload = json.loads((project_root / config.CLEANUP_STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert state_payload["status"] == "running"
    assert state_payload["progress_current"] < state_payload["progress_total"]
    assert state_payload["resume_checkpoint"] is not None


def test_cleanup_removes_separator_marks_and_heals_false_phrase_breaks(tmp_path) -> None:
    """
    @brief      Verify cleanup removes ornamental separator lines and merges false blank-line phrase breaks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("CleanupFormatting", tmp_path)
    source_path = project_root / "story.pdf"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.pdf",
        "stored_relative_path": "story.pdf",
        "file_type": "pdf",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["extracted_text_relative_path"] = config.EXTRACTED_TEXT_FILE_NAME
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        (
            '"Drenthe will shoot this industrial if\n\n'
            'you swear that Heroes of the Periphery will then be the next project,"\n\n'
            "* * *\n\n"
            "The transport liner was less than eight hours out from Korhal."
        ),
        encoding="utf-8",
    )

    report_payload = deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "* * *" not in output_text
    assert '"Drenthe will shoot this industrial if you swear that Heroes of the Periphery' in output_text
    assert report_payload["removed_separator_line_count"] == 1


def test_cleanup_displays_dialogue_markers_on_new_lines(tmp_path) -> None:
    """
    @brief      Verify cleanup keeps dialogue markers on separate display lines.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("CleanupDialogue", tmp_path)
    source_path = project_root / "story.pdf"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.pdf",
        "stored_relative_path": "story.pdf",
        "file_type": "pdf",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["extracted_text_relative_path"] = config.EXTRACTED_TEXT_FILE_NAME
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        (
            "Chani Ã®l zori, trÄƒgÃ¢ndu-l de mantie: - Mai iute. Se face luminÄƒ. "
            "- Unde s-au dus oamenii care s-au urcat pe stÃ¢nci?"
        ),
        encoding="utf-8",
    )

    deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "mantie:\n- Mai iute." in output_text
    assert "luminÄƒ.\n- Unde s-au dus oamenii" in output_text


def test_cleanup_preserves_original_newline_after_dialogue_line(tmp_path) -> None:
    """
    @brief      Verify cleanup keeps one original newline after a completed dialogue line.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("CleanupDialogueBreak", tmp_path)
    source_path = project_root / "story.pdf"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.pdf",
        "stored_relative_path": "story.pdf",
        "file_type": "pdf",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["extracted_text_relative_path"] = config.EXTRACTED_TEXT_FILE_NAME
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        ("- E primul schimb al gÄƒrzii de zi, Ã®i rÄƒspunse fata. GrÄƒbeÈ™te-te!\nPosteazÄƒ santinele, gÃ®ndi Paul."),
        encoding="utf-8",
    )

    deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "GrÄƒbeÈ™te-te!\nPosteazÄƒ santinele" in output_text


# END OF FILE
