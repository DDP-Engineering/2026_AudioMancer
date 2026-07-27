#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_extraction_service.py
@brief Focused tests for the AudioMancer text extraction service.
@details Verifies self-contained extraction artifacts, resumable state, and
         deterministic text extraction for the supported source formats.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.2.0
"""

# IMPORTS

import json
from pathlib import Path

from docx import Document
from ebooklib import epub
import fitz
from odf.opendocument import OpenDocumentText
from odf.text import P
import pytest

from audiomancer import config
from audiomancer.services import (
    project_workspace_service,
    source_ledger_service,
    text_extraction_service,
)


def test_extract_text_writes_self_contained_artifacts_for_txt_source(tmp_path) -> None:
    """
    @brief      Verify TXT extraction writes only canonical text and authoritative metadata.
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
    source_path = project_root / "story.txt"
    source_path.write_text("First line\r\n\r\nSecond line", encoding="utf-8")
    manifest["source_document"] = _build_source_document(source_path, "txt")

    metadata = text_extraction_service.extract_text(project_root, manifest)

    assert source_path.is_file()
    assert (project_root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8") == (
        "First line\n\nSecond line\n"
    )
    assert metadata == {
        "status": "completed",
        "progress_current": 1,
        "progress_total": 1,
        "warnings": [],
        "character_count": 23,
        "word_count": 4,
        "line_count": 3,
        "page_count": None,
    }
    assert json.loads(
        (project_root / config.EXTRACTION_METADATA_FILE_NAME).read_text(encoding="utf-8")
    ) == metadata
    generated_artifact_names = {
        path.name
        for path in project_root.iterdir()
        if path.name not in {config.PROJECT_MANIFEST_FILE_NAME, source_path.name}
    }
    assert generated_artifact_names == {
        config.EXTRACTED_TEXT_FILE_NAME,
        config.EXTRACTION_METADATA_FILE_NAME,
        config.SOURCE_LEDGER_FILE_NAME,
    }
    ledger = source_ledger_service.load_source_ledger(project_root)
    assert ledger["canonical_text"]["length_codepoints"] == 24
    assert [unit["unit_id"] for unit in ledger["units"]] == ["u-000001", "u-000002"]
    assert (project_root / "extraction_report.json").exists() is False
    assert (project_root / "extraction_state.json").exists() is False


@pytest.mark.parametrize(
    ("suffix", "file_type", "builder_name"),
    [
        (".md", "md", "markdown"),
        (".rtf", "rtf", "rtf"),
        (".docx", "docx", "docx"),
        (".odt", "odt", "odt"),
        (".epub", "epub", "epub"),
    ],
)
def test_extract_text_supports_document_formats(
    tmp_path,
    suffix: str,
    file_type: str,
    builder_name: str,
) -> None:
    """
    @brief      Verify supported document formats extract non-empty normalized text.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  suffix Source file suffix under test.
    @param[in]  file_type Persisted source-type token.
    @param[in]  builder_name Fixture-builder token for the format.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        f"Project_{file_type}",
        tmp_path,
    )
    source_path = project_root / f"story{suffix}"
    builder = {
        "markdown": _write_markdown_source,
        "rtf": _write_rtf_source,
        "docx": _write_docx_source,
        "odt": _write_odt_source,
        "epub": _write_epub_source,
    }[builder_name]
    builder(source_path)
    manifest["source_document"] = _build_source_document(source_path, file_type)

    metadata = text_extraction_service.extract_text(project_root, manifest)

    output_text = (project_root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert metadata["status"] == "completed"
    assert metadata["character_count"] > 0
    assert "Story" in output_text


def test_extract_text_reports_pdf_warnings_and_total_pages(tmp_path) -> None:
    """
    @brief      Verify PDF extraction preserves page count and empty-page warnings.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "PdfProject",
        tmp_path,
    )
    source_path = project_root / "story.pdf"
    _write_pdf_source(source_path, ["Story page one", "", "Story page three"])
    manifest["source_document"] = _build_source_document(source_path, "pdf")

    metadata = text_extraction_service.extract_text(project_root, manifest)

    assert metadata["page_count"] == 3
    assert metadata["warnings"] == ["PDF page 2 did not contain extractable text."]
    output_text = (project_root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert output_text == "Story page one\n\n\f\n\nStory page three\n"
    assert metadata["progress_total"] == 3


def test_extract_text_rejects_empty_pdf_without_ocr(tmp_path) -> None:
    """
    @brief      Verify empty-text PDFs fail with a clear OCR-related error.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "EmptyPdfProject",
        tmp_path,
    )
    source_path = project_root / "empty.pdf"
    _write_pdf_source(source_path, ["", ""])
    manifest["source_document"] = _build_source_document(source_path, "pdf")

    with pytest.raises(ValueError, match="OCR is not supported"):
        text_extraction_service.extract_text(project_root, manifest)
    metadata = text_extraction_service.load_extraction_metadata(project_root)
    assert metadata is not None
    assert metadata["status"] == "failed"
    assert metadata["progress_current"] == 2


def test_extract_text_splits_rtf_into_multiple_progress_units(tmp_path) -> None:
    """
    @brief      Verify RTF extraction exposes paragraph-sized progress units.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "RtfProgressProject",
        tmp_path,
    )
    source_path = project_root / "story.rtf"
    source_path.write_text(
        r"{\rtf1\ansi Story first paragraph.\par\par Story second paragraph.}",
        encoding="utf-8",
    )
    manifest["source_document"] = _build_source_document(source_path, "rtf")

    text_extraction_service.extract_text(project_root, manifest)

    metadata = text_extraction_service.load_extraction_metadata(project_root)
    assert metadata is not None
    assert metadata["progress_total"] >= 2


def test_extract_text_splits_epub_into_multiple_progress_units(tmp_path) -> None:
    """
    @brief      Verify EPUB extraction exposes multiple progress units when the source has multiple paragraphs.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "EpubProgressProject",
        tmp_path,
    )
    source_path = project_root / "story.epub"
    book = epub.EpubBook()
    book.set_identifier("progress-book")
    book.set_title("Story")
    book.set_language("en")
    chapter = epub.EpubHtml(title="Chapter 1", file_name="chapter_1.xhtml", lang="en")
    chapter.content = "<h1>Story</h1><p>Paragraph one.</p><p>Paragraph two.</p>"
    book.add_item(chapter)
    book.toc = (chapter,)
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(source_path), book, {})
    manifest["source_document"] = _build_source_document(source_path, "epub")

    text_extraction_service.extract_text(project_root, manifest)

    metadata = text_extraction_service.load_extraction_metadata(project_root)
    assert metadata is not None
    assert metadata["progress_total"] >= 2


def test_extract_text_rejects_misnamed_legacy_doc_with_rtf_extension(tmp_path) -> None:
    """
    @brief      Verify misnamed legacy Word containers do not pass through the RTF extractor.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "LegacyDocProject",
        tmp_path,
    )
    source_path = project_root / "legacy.rtf"
    source_path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)
    manifest["source_document"] = _build_source_document(source_path, "rtf")

    with pytest.raises(ValueError, match="legacy Word \\.doc container"):
        text_extraction_service.extract_text(project_root, manifest)
    metadata = text_extraction_service.load_extraction_metadata(project_root)
    assert metadata is not None
    assert metadata["status"] == "failed"


def test_extract_text_restarts_unfinished_docx_extraction(tmp_path) -> None:
    """
    @brief      Verify rerunning an unfinished extraction rebuilds canonical text and its ledger.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ResumeProject",
        tmp_path,
    )
    source_path = project_root / "story.docx"
    _write_docx_source(source_path, paragraphs=["Story first", "Story second"])
    manifest["source_document"] = _build_source_document(source_path, "docx")

    output_path = project_root / config.EXTRACTED_TEXT_FILE_NAME
    output_path.write_text("Story first", encoding="utf-8")
    metadata = {
        "status": "running",
        "progress_current": 1,
        "progress_total": 2,
        "warnings": [],
        "character_count": None,
        "word_count": None,
        "line_count": None,
        "page_count": None,
    }
    (project_root / config.EXTRACTION_METADATA_FILE_NAME).write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    completed_metadata = text_extraction_service.extract_text(project_root, manifest)

    assert completed_metadata["word_count"] == 4
    assert output_path.read_text(encoding="utf-8") == "Story first\n\nStory second\n"


def test_extract_text_persists_cancelled_progress_and_restarts(tmp_path) -> None:
    """
    @brief      Verify cancellation persists progress while the next run rebuilds from source.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-27
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("CancelledExtraction", tmp_path)
    source_path = project_root / "story.docx"
    _write_docx_source(source_path, paragraphs=["Story first", "Story second"])
    manifest["source_document"] = _build_source_document(source_path, "docx")
    cancellation_checks = iter((False, True))

    with pytest.raises(text_extraction_service.OperationCancelledError):
        text_extraction_service.extract_text(
            project_root,
            manifest,
            cancel_requested=lambda: next(cancellation_checks),
        )

    cancelled_metadata = text_extraction_service.load_extraction_metadata(project_root)
    assert cancelled_metadata is not None
    assert cancelled_metadata["status"] == "cancelled"
    assert cancelled_metadata["progress_current"] == 1
    assert cancelled_metadata["character_count"] is None

    completed_metadata = text_extraction_service.extract_text(project_root, manifest)

    assert completed_metadata["status"] == "completed"
    assert (project_root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8") == (
        "Story first\n\nStory second\n"
    )


@pytest.mark.parametrize(
    "payload_update",
    [
        {"unexpected": True},
        {"status": "unknown"},
        {"progress_current": 3, "progress_total": 2},
        {"word_count": 1},
    ],
)
def test_load_extraction_metadata_rejects_incompatible_schema(tmp_path, payload_update) -> None:
    """Verify exact fields, status, progress, and incomplete statistics are strict."""
    project_root, _manifest = project_workspace_service.create_project("InvalidExtraction", tmp_path)
    payload = {
        "status": "running",
        "progress_current": 0,
        "progress_total": 2,
        "warnings": [],
        "character_count": None,
        "word_count": None,
        "line_count": None,
        "page_count": None,
    }
    payload.update(payload_update)
    (project_root / config.EXTRACTION_METADATA_FILE_NAME).write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    with pytest.raises(text_extraction_service.ExtractionMetadataError, match="Reset Extraction"):
        text_extraction_service.load_extraction_metadata(project_root)


def test_load_extraction_metadata_rejects_legacy_sidecars(tmp_path) -> None:
    """Verify old report/state artifacts require a destructive extraction reset."""
    project_root, _manifest = project_workspace_service.create_project("LegacyExtraction", tmp_path)
    (project_root / "extraction_report.json").write_text("{}", encoding="utf-8")

    with pytest.raises(text_extraction_service.ExtractionMetadataError, match="Legacy extraction sidecars"):
        text_extraction_service.load_extraction_metadata(project_root)


def test_load_extraction_metadata_rejects_invalid_json(tmp_path) -> None:
    """Verify malformed metadata JSON requires a destructive extraction reset."""
    project_root, _manifest = project_workspace_service.create_project("InvalidExtractionJson", tmp_path)
    (project_root / config.EXTRACTION_METADATA_FILE_NAME).write_text("{broken", encoding="utf-8")

    with pytest.raises(text_extraction_service.ExtractionMetadataError, match="Reset Extraction"):
        text_extraction_service.load_extraction_metadata(project_root)


def test_reset_extraction_and_downstream_preserves_source_document(tmp_path) -> None:
    """
    @brief      Verify a destructive extraction reset clears known runtime data but keeps the source document.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project(
        "ResetProject",
        tmp_path,
    )
    source_path = project_root / "story.txt"
    source_path.write_text("snapshot", encoding="utf-8")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("output", encoding="utf-8")
    (project_root / config.EXTRACTION_METADATA_FILE_NAME).write_text(
        json.dumps(
            {
                "status": "completed",
                "progress_current": 1,
                "progress_total": 1,
                "warnings": [],
                "character_count": 6,
                "word_count": 1,
                "line_count": 1,
                "page_count": None,
            }
        ),
        encoding="utf-8",
    )
    (project_root / "extraction_report.json").write_text("{}", encoding="utf-8")
    (project_root / "extraction_state.json").write_text("{}", encoding="utf-8")
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("cleanup", encoding="utf-8")
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text("[]", encoding="utf-8")
    (project_root / "operator_note.txt").write_text("keep", encoding="utf-8")

    text_extraction_service.reset_extraction_and_downstream(project_root)

    assert source_path.is_file()
    assert (project_root / "operator_note.txt").is_file()
    assert (project_root / config.EXTRACTED_TEXT_FILE_NAME).exists() is False
    assert (project_root / config.EXTRACTION_METADATA_FILE_NAME).exists() is False
    assert (project_root / "extraction_report.json").exists() is False
    assert (project_root / "extraction_state.json").exists() is False
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).exists() is False
    assert (project_root / config.CHUNK_ARTIFACT_FILE_NAME).exists() is False


def _build_source_document(source_path: Path, file_type: str) -> dict[str, object]:
    """
    @brief      Build one minimal manifest source-document payload for tests.
    @param[in]  source_path Project-root source path.
    @param[in]  file_type Persisted source-type token.
    @return     Source-document payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    return {
        "original_name": source_path.name,
        "stored_relative_path": source_path.name,
        "file_type": file_type,
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }


def _write_markdown_source(path: Path) -> None:
    """
    @brief      Write one Markdown test source file.
    @param[in]  path Target source path.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    path.write_text("# Story\n\nParagraph", encoding="utf-8")


def _write_rtf_source(path: Path) -> None:
    """
    @brief      Write one RTF test source file.
    @param[in]  path Target source path.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    path.write_text(r"{\rtf1\ansi Story paragraph}", encoding="utf-8")


def _write_docx_source(path: Path, paragraphs: list[str] | None = None) -> None:
    """
    @brief      Write one DOCX test source file.
    @param[in]  path Target source path.
    @param[in]  paragraphs Optional paragraph list.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    document = Document()
    for paragraph in paragraphs or ["Story paragraph"]:
        document.add_paragraph(paragraph)
    document.save(path)


def _write_odt_source(path: Path) -> None:
    """
    @brief      Write one ODT test source file.
    @param[in]  path Target source path.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    document = OpenDocumentText()
    document.text.addElement(P(text="Story paragraph"))
    document.save(str(path))


def _write_epub_source(path: Path) -> None:
    """
    @brief      Write one EPUB test source file.
    @param[in]  path Target source path.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    book = epub.EpubBook()
    book.set_identifier("test-book")
    book.set_title("Story")
    book.set_language("en")
    chapter = epub.EpubHtml(title="Chapter 1", file_name="chapter_1.xhtml", lang="en")
    chapter.content = "<h1>Story</h1><p>Paragraph</p>"
    book.add_item(chapter)
    book.toc = (chapter,)
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book, {})


def _write_pdf_source(path: Path, page_texts: list[str]) -> None:
    """
    @brief      Write one PDF test source file with one text payload per page.
    @param[in]  path Target source path.
    @param[in]  page_texts Ordered page-text payloads.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    document = fitz.open()
    for page_text in page_texts:
        page = document.new_page()
        if page_text:
            page.insert_text((72, 72), page_text)
    document.save(path)
    document.close()


# END OF FILE
