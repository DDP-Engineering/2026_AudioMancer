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
@version 0.2.2
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
    assert (project_root / config.CLEANED_TEXT_METADATA_FILE_NAME).is_file()
    assert (project_root / config.CLEANUP_REPORT_FILE_NAME).is_file()
    assert (project_root / config.CLEANUP_STATE_FILE_NAME).is_file()
    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "Book Title" not in output_text
    assert "Chapter I" in output_text
    assert "This is the first paragraph continuing on the second page." in output_text
    assert "\n\nNew paragraph.\n" in output_text
    assert report_payload["paragraph_count"] == 2
    assert report_payload["page_break_repair_count"] == 1
    assert report_payload["removed_line_count"] >= 3
    metadata_payload = json.loads((project_root / config.CLEANED_TEXT_METADATA_FILE_NAME).read_text(encoding="utf-8"))
    state_payload = json.loads((project_root / config.CLEANUP_STATE_FILE_NAME).read_text(encoding="utf-8"))
    manifest_payload = project_workspace_service.load_manifest(project_root)
    assert "text" not in metadata_payload["paragraphs"][0]
    assert state_payload["resume_checkpoint"] is None
    assert "cleaned_pages" not in state_payload["metadata"]
    assert manifest_payload["current_stage"] == "text_chunking_ready"
    assert manifest_payload["operations"]["cleanup"]["status"] == "completed"


def test_cleanup_requires_canonical_extracted_text_artifact(tmp_path) -> None:
    """
    @brief      Verify cleanup input loading requires the canonical extracted-text artifact.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    project_root, manifest = _build_cleanup_project(tmp_path, "CleanupTraversal")
    with pytest.raises(FileNotFoundError, match="Extracted text is missing"):
        deterministic_cleanup_service.clean_text(project_root, manifest)

    assert not (project_root / config.CLEANED_TEXT_FILE_NAME).exists()


def test_cleanup_repairs_uppercase_name_fragment_after_page_break(tmp_path) -> None:
    """
    @brief      Verify page-break metadata repair joins uppercase name fragments after incomplete text.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _build_cleanup_project(tmp_path, "CleanupPageBreakName")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        '"If you make sure Drenthe gets out, Drenthe will make sure this story gets out," said\n\n\f\n\nDrenthe.\n',
        encoding="utf-8",
    )

    report_payload = deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    metadata_payload = json.loads((project_root / config.CLEANED_TEXT_METADATA_FILE_NAME).read_text(encoding="utf-8"))
    assert (
        '"If you make sure Drenthe gets out, Drenthe will make sure this story gets out," said Drenthe.' in output_text
    )
    assert report_payload["page_break_repair_count"] == 1
    assert metadata_payload["paragraphs"][0]["joined_across_page_break"] is True
    assert metadata_payload["paragraphs"][0]["boundary_confidence"] == "repaired"


def test_cleanup_keeps_heading_after_page_break_separate(tmp_path) -> None:
    """
    @brief      Verify explicit headings are not joined backward across page breaks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _build_cleanup_project(tmp_path, "CleanupPageBreakHeading")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        "The previous scene ended without a hard stop\n\n\f\n\nChapter II\n\nThe next scene begins.",
        encoding="utf-8",
    )

    report_payload = deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "hard stop\n\nChapter II" in output_text
    assert report_payload["page_break_repair_count"] == 0


def test_cleanup_ignores_page_number_before_continuation_decision(tmp_path) -> None:
    """
    @brief      Verify page-number lines do not block cross-page continuation repair.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _build_cleanup_project(tmp_path, "CleanupPageNumberContinuation")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        "He looked up and whispered\n\n\f\n\nPage 13\nsoftly to the room.",
        encoding="utf-8",
    )

    report_payload = deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "He looked up and whispered softly to the room." in output_text
    assert "Page 13" not in output_text
    assert report_payload["page_break_repair_count"] == 1


def test_cleanup_preserves_complete_short_transition_after_page_break(tmp_path) -> None:
    """
    @brief      Verify complete short transition paragraphs remain separate after page breaks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _build_cleanup_project(tmp_path, "CleanupShortTransition")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        "The door closed.\n\n\f\n\nThree days.\n\nThe factory was gone.",
        encoding="utf-8",
    )

    report_payload = deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    metadata_payload = json.loads((project_root / config.CLEANED_TEXT_METADATA_FILE_NAME).read_text(encoding="utf-8"))
    assert "The door closed.\n\nThree days.\n\nThe factory was gone." in output_text
    assert report_payload["page_break_repair_count"] == 0
    assert report_payload["weak_boundary_count"] == 1
    assert metadata_payload["paragraphs"][1]["warning_flags"] == ["short_fragment_after_page_break"]


def test_cleanup_persists_resumable_state_after_cancellation(tmp_path) -> None:
    """
    @brief      Verify one cancelled cleanup run leaves resumable state on disk.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
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
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        "Header\n1\nParagraph one.\n\n\f\n\nHeader\n2\nParagraph two.",
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
        deterministic_cleanup_service.clean_text(
            project_root,
            manifest,
            progress_callback=_progress_callback,
            cancel_requested=lambda: should_cancel["value"],
        )

    state_payload = json.loads((project_root / config.CLEANUP_STATE_FILE_NAME).read_text(encoding="utf-8"))
    manifest_payload = project_workspace_service.load_manifest(project_root)
    assert state_payload["status"] == "cancelled"
    assert state_payload["progress_current"] < state_payload["progress_total"]
    assert state_payload["resume_checkpoint"] is not None
    assert manifest_payload["operations"]["cleanup"]["status"] == "cancelled"


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
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        ("- E primul schimb al gÄƒrzii de zi, Ã®i rÄƒspunse fata. GrÄƒbeÈ™te-te!\nPosteazÄƒ santinele, gÃ®ndi Paul."),
        encoding="utf-8",
    )

    deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "GrÄƒbeÈ™te-te!\nPosteazÄƒ santinele" in output_text


def test_cleanup_removes_repeated_headers_with_changing_page_numbers(tmp_path) -> None:
    """
    @brief      Verify repeated headers are matched after page-number affix normalization.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _build_cleanup_project(tmp_path, "CleanupHeaderNormalization")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        ("Chronicles of Dawn - 1\nFirst page text.\n\n\f\n\nChronicles of Dawn - 2\nSecond page text."),
        encoding="utf-8",
    )

    report_payload = deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "Chronicles of Dawn" not in output_text
    assert "First page text." in output_text
    assert "Second page text." in output_text
    assert report_payload["removed_header_footer_line_count"] == 2


def test_cleanup_counts_supported_language_chapter_markers(tmp_path) -> None:
    """
    @brief      Verify localized chapter headings are detected without being removed.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _build_cleanup_project(tmp_path, "CleanupLocalizedChapters")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        ("Kapitel 1\n\nChapitre 2\n\nCapítulo 3\n\nГлава 4\n\n第5章 はじまり\n\n제6장 시작\n"),
        encoding="utf-8",
    )

    report_payload = deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert report_payload["detected_chapter_count"] == 6
    assert "Kapitel 1" in output_text
    assert "第5章 はじまり" in output_text
    assert "제6장 시작" in output_text


def test_cleanup_merges_cjk_continuation_without_terminal_punctuation(tmp_path) -> None:
    """
    @brief      Verify CJK text can continue across a false blank-line split.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _build_cleanup_project(tmp_path, "CleanupCjkContinuation")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        "这是一个没有句号的长句\n\n继续在下一行展开。\n",
        encoding="utf-8",
    )

    deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "这是一个没有句号的长句 继续在下一行展开。" in output_text


def test_cleanup_does_not_merge_cjk_after_terminal_punctuation(tmp_path) -> None:
    """
    @brief      Verify CJK sentence punctuation prevents false continuation merging.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _build_cleanup_project(tmp_path, "CleanupCjkTerminal")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        "这是完整的一句。\n\n这是下一句。\n",
        encoding="utf-8",
    )

    deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "这是完整的一句。\n\n这是下一句。" in output_text


def test_cleanup_merges_hangul_continuation_without_lowercase_assumption(tmp_path) -> None:
    """
    @brief      Verify Hangul continuation does not depend on lowercase letters.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _build_cleanup_project(tmp_path, "CleanupHangulContinuation")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        "이 문장은 아직 끝나지 않은 긴 문장\n\n다음 줄에서 계속된다.\n",
        encoding="utf-8",
    )

    deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "이 문장은 아직 끝나지 않은 긴 문장 다음 줄에서 계속된다." in output_text


def test_cleanup_removes_expanded_page_number_forms(tmp_path) -> None:
    """
    @brief      Verify conservative page-number forms are removed across scripts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _build_cleanup_project(tmp_path, "CleanupPageNumbers")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        "- 12 -\nText one.\n\nPage 13 of 240\nText two.\n\n第 14 页\nText three.\n",
        encoding="utf-8",
    )

    report_payload = deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "- 12 -" not in output_text
    assert "Page 13 of 240" not in output_text
    assert "第 14 页" not in output_text
    assert report_payload["removed_page_number_line_count"] == 3


def test_cleanup_formats_unicode_dash_dialogue_markers(tmp_path) -> None:
    """
    @brief      Verify en dash and em dash dialogue markers are normalized onto new lines.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _build_cleanup_project(tmp_path, "CleanupUnicodeDialogue")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
        "He stopped: — Wait. She answered, – Now.\n",
        encoding="utf-8",
    )

    deterministic_cleanup_service.clean_text(project_root, manifest)

    output_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "He stopped:\n- Wait." in output_text
    assert "She answered,\n- Now." in output_text


def _build_cleanup_project(tmp_path, project_name: str):
    """
    @brief      Build one project fixture ready for deterministic cleanup.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  project_name Project name.
    @return     Tuple containing project root and manifest.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(project_name, tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-26T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    return project_root, manifest


# END OF FILE
