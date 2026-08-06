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
"""

# IMPORTS

import json
from pathlib import Path
import zipfile

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
    text_extraction_adapters,
    text_extraction_service,
)


def test_extract_text_writes_self_contained_artifacts_for_txt_source(tmp_path) -> None:
    """
    @brief      Verify TXT extraction writes only canonical text and authoritative metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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


@pytest.mark.parametrize(
    ("encoding", "source_text", "expected_ledger_encoding"),
    [
        ("utf-8", "Simple UTF-8 story.", "utf-8"),
        ("utf-8-sig", "BOM-marked story.", "utf-8-sig"),
        ("cp1250", "Zażółć gęślą jaźń. Příliš žluťoučký kůň.", "cp1250"),
        ("cp1251", "Привет, мир! Это проверка русского текста.", "cp1251"),
        ("cp1252", "“Café”—naïve façade. Voilà, déjà vu!", "cp1252"),
    ],
)
def test_extract_text_selects_supported_text_encoding_without_mojibake(
    tmp_path,
    encoding: str,
    source_text: str,
    expected_ledger_encoding: str,
) -> None:
    """Verify public TXT extraction selects supported encodings truthfully."""
    project_name = f"Encoding_{expected_ledger_encoding.replace('-', '_')}"
    project_root, manifest = project_workspace_service.create_project(project_name, tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_bytes(source_text.encode(encoding))
    manifest["source_document"] = _build_source_document(source_path, "txt")

    text_extraction_service.extract_text(project_root, manifest)

    canonical_text = (project_root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    ledger = source_ledger_service.load_source_ledger(project_root)
    assert canonical_text == f"{source_text}\n"
    assert ledger["source"]["encoding"] == expected_ledger_encoding


def test_extract_text_honors_rtf_code_page_declaration(tmp_path) -> None:
    """Verify an RTF code-page declaration takes priority over codec guessing."""
    project_root, manifest = project_workspace_service.create_project("RtfCp1251", tmp_path)
    source_text = "Привет из RTF."
    source_path = project_root / "story.rtf"
    source_path.write_bytes(b"{\\rtf1\\ansi\\ansicpg1251 " + source_text.encode("cp1251") + b"}")
    manifest["source_document"] = _build_source_document(source_path, "rtf")

    text_extraction_service.extract_text(project_root, manifest)

    canonical_text = (project_root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    ledger = source_ledger_service.load_source_ledger(project_root)
    assert canonical_text == f"{source_text}\n"
    assert ledger["source"]["encoding"] == "cp1251"


def test_text_decoder_uses_explicit_latin1_terminal_fallback() -> None:
    """Verify Latin-1 is used only after every Windows-code-page decoder rejects."""
    source_bytes = b"Fallback:\x98\x81"

    decoded, encoding = text_extraction_adapters._decode_bytes_with_fallback(source_bytes)

    assert decoded == source_bytes.decode("latin-1")
    assert encoding == "latin-1"


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


def test_pdf_ordering_places_centered_spanning_material_once_around_columns() -> None:
    """Verify centered headers and footers surround clear columns without duplication."""
    lines = [
        _pdf_order_line("Centered top", (292.0, 60.0, 320.0, 70.0), 0),
        *_two_column_pdf_lines(start_index=1),
        _pdf_order_line("Centered bottom", (288.0, 200.0, 324.0, 210.0), 7),
    ]

    ordered, layout_mode, reasons = text_extraction_adapters._order_pdf_lines(lines, 612.0)

    assert [line["text"] for line in ordered] == [
        "Centered top",
        "Left 1",
        "Left 2",
        "Left 3",
        "Right 1",
        "Right 2",
        "Right 3",
        "Centered bottom",
    ]
    assert layout_mode == "two_column"
    assert reasons == ["two_column_reading_order_reconstructed"]


def test_pdf_ordering_emits_vertical_threshold_overlap_once() -> None:
    """Verify one spanning line cannot belong to both vertical partitions."""
    lines = [
        _pdf_order_line("Left 1", (72.0, 100.0, 250.0, 102.0), 0),
        _pdf_order_line("Left 2", (72.0, 103.0, 250.0, 105.0), 1),
        _pdf_order_line("Left 3", (72.0, 106.0, 250.0, 108.0), 2),
        _pdf_order_line("Right 1", (360.0, 100.0, 540.0, 102.0), 3),
        _pdf_order_line("Right 2", (360.0, 103.0, 540.0, 105.0), 4),
        _pdf_order_line("Right 3", (360.0, 106.0, 540.0, 108.0), 5),
        _pdf_order_line("Threshold overlap", (250.0, 99.0, 360.0, 109.0), 6),
    ]

    ordered, layout_mode, reasons = text_extraction_adapters._order_pdf_lines(lines, 612.0)

    assert sum(line is lines[-1] for line in ordered) == 1
    assert layout_mode == "uncertain_columns"
    assert reasons == ["multi_column_reading_order_uncertain"]


def test_pdf_ordering_is_identity_permutation_for_every_layout_mode() -> None:
    """Verify every successful PDF ordering contains every input object exactly once."""
    short_lines = [
        _pdf_order_line("Short 2", (72.0, 120.0, 250.0, 130.0), 0),
        _pdf_order_line("Short 1", (72.0, 100.0, 250.0, 110.0), 1),
    ]
    single_column_lines = [
        _pdf_order_line(f"Single {index}", (72.0, 100.0 + index * 20.0, 250.0, 110.0 + index * 20.0), index)
        for index in range(6)
    ]
    two_column_lines = [
        _pdf_order_line("Top", (292.0, 60.0, 320.0, 70.0), 0),
        *_two_column_pdf_lines(start_index=1),
        _pdf_order_line("Bottom", (292.0, 200.0, 320.0, 210.0), 7),
    ]
    uncertain_lines = [
        *_two_column_pdf_lines(),
        _pdf_order_line("Ambiguous", (250.0, 130.0, 360.0, 140.0), 6),
    ]
    modes: set[str] = set()

    for lines in (short_lines, single_column_lines, two_column_lines, uncertain_lines):
        ordered, layout_mode, _reasons = text_extraction_adapters._order_pdf_lines(lines, 612.0)
        modes.add(layout_mode)
        assert len(ordered) == len(lines)
        assert {id(line) for line in ordered} == {id(line) for line in lines}

    assert modes == {"single_column", "two_column", "uncertain_columns"}


def test_pdf_ordering_preserves_uncertain_column_warning() -> None:
    """Verify a genuinely ambiguous spanning line keeps the established warning."""
    lines = [
        *_two_column_pdf_lines(),
        _pdf_order_line("Ambiguous", (250.0, 130.0, 360.0, 140.0), 6),
    ]

    ordered, layout_mode, reasons = text_extraction_adapters._order_pdf_lines(lines, 612.0)

    assert ordered == lines
    assert layout_mode == "uncertain_columns"
    assert reasons == ["multi_column_reading_order_uncertain"]


@pytest.mark.parametrize(("line_count", "page_width"), [(5, 612.0), (6, 0.0)])
def test_pdf_ordering_normalizes_early_single_column_identity(
    line_count: int,
    page_width: float,
) -> None:
    """Verify every early single-column return assigns column identity zero."""
    lines = [
        _pdf_order_line(
            f"Line {index}",
            (72.0, 100.0 + index * 20.0, 250.0, 110.0 + index * 20.0),
            index,
        )
        for index in reversed(range(line_count))
    ]

    ordered, layout_mode, reasons = text_extraction_adapters._order_pdf_lines(lines, page_width)

    assert [line["text"] for line in ordered] == [f"Line {index}" for index in range(line_count)]
    assert all(line["column"] == 0 for line in ordered)
    assert layout_mode == "single_column"
    assert reasons == []


def test_pdf_ordering_preserves_normal_single_column_top_left_order() -> None:
    """Verify normal single-column pages retain stable top-left ordering."""
    lines = [
        _pdf_order_line("Second on first row", (200.0, 100.0, 250.0, 110.0), 0),
        _pdf_order_line("First on first row", (72.0, 100.0, 150.0, 110.0), 1),
        _pdf_order_line("Line 3", (72.0, 120.0, 250.0, 130.0), 2),
        _pdf_order_line("Line 4", (72.0, 140.0, 250.0, 150.0), 3),
        _pdf_order_line("Line 5", (72.0, 160.0, 250.0, 170.0), 4),
        _pdf_order_line("Line 6", (72.0, 180.0, 250.0, 190.0), 5),
    ]

    ordered, layout_mode, reasons = text_extraction_adapters._order_pdf_lines(lines, 612.0)

    assert [line["text"] for line in ordered] == [
        "First on first row",
        "Second on first row",
        "Line 3",
        "Line 4",
        "Line 5",
        "Line 6",
    ]
    assert all(line["column"] == 0 for line in ordered)
    assert layout_mode == "single_column"
    assert reasons == []


def test_extract_text_emits_centered_pdf_text_once(tmp_path) -> None:
    """Verify public PDF extraction writes one copy of a centered physical line."""
    project_root, manifest = project_workspace_service.create_project(
        "CenteredPdfProject",
        tmp_path,
    )
    source_path = project_root / "centered.pdf"
    _write_two_column_pdf_source(source_path)
    manifest["source_document"] = _build_source_document(source_path, "pdf")

    text_extraction_service.extract_text(project_root, manifest)

    output_text = (project_root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert output_text.count("MID") == 1
    assert output_text.splitlines() == [
        "MID",
        "Left one",
        "Left two",
        "Left three",
        "Right one",
        "Right two",
        "Right three",
    ]


def test_extract_text_splits_rtf_into_multiple_progress_units(tmp_path) -> None:
    """
    @brief      Verify RTF extraction exposes paragraph-sized progress units.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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


@pytest.mark.parametrize(
    ("markup", "expected_texts"),
    [
        ("<p>Before</p><div hidden>Hidden</div><p>After</p>", ["Before", "After"]),
        ("<p>Before</p><div hidden=\"\">Hidden</div><p>After</p>", ["Before", "After"]),
        ("<p>Before</p><div hidden=\"hidden\">Hidden</div><p>After</p>", ["Before", "After"]),
        ("<p>Before</p><div hidden=\"false\">Hidden</div><p>After</p>", ["Before", "After"]),
        ("<p>Before</p><div ArIa-HiDdEn=\" TrUe \">Hidden</div><p>After</p>", ["Before", "After"]),
        ("<p>Before</p><p aria-hidden=\"false\">Visible</p><p>After</p>", ["Before", "Visible", "After"]),
        (
            "<p>Before</p><div hidden>Hidden<span>nested</span><br><img src=\"x\"></div><p>After</p>",
            ["Before", "After"],
        ),
        (
            "<p>Before</p><div hidden>Hidden<br/><img src=\"x\"/></div><p>After</p>",
            ["Before", "After"],
        ),
        ("<p>Before</p><input hidden><p>After</p>", ["Before", "After"]),
        (
            "<p>Before</p><script>Hidden</script><style>Hidden</style><nav>Hidden</nav><p>After</p>",
            ["Before", "After"],
        ),
    ],
)
def test_structured_html_extractor_omits_ignored_subtrees_without_losing_visible_text(
    markup: str,
    expected_texts: list[str],
) -> None:
    """Verify HTML hidden semantics and void tags keep ignored-state tracking balanced."""
    parser = text_extraction_adapters._StructuredHtmlExtractor(
        spine_index=0,
        item_id="chapter_1.xhtml",
    )

    parser.feed(f"<body>{markup}</body>")
    parser.close()

    assert [event.text for event in parser.events] == expected_texts


def test_extract_text_omits_hidden_epub_content_from_canonical_text_and_ledger(tmp_path) -> None:
    """Verify public EPUB extraction writes only visible blocks in source order."""
    project_root, manifest = project_workspace_service.create_project("VisibleEpub", tmp_path)
    source_path = project_root / "story.epub"
    _write_epub_source(source_path)
    document = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<p>Visible first.</p><div hidden>Hidden <span>nested</span><br><img src=\"x\"/></div>"
        "<p>Visible last.</p></body></html>"
    )
    _replace_epub_member(source_path, "chapter_1.xhtml", document.encode("utf-8"))
    manifest["source_document"] = _build_source_document(source_path, "epub")

    text_extraction_service.extract_text(project_root, manifest)

    ledger = source_ledger_service.load_source_ledger(project_root)
    assert (project_root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8") == (
        "Visible first.\n\nVisible last.\n"
    )
    canonical_text = (project_root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert [source_ledger_service.unit_text(canonical_text, unit) for unit in ledger["units"]] == [
        "Visible first.",
        "Visible last.",
    ]


@pytest.mark.parametrize(
    ("declared_encoding", "python_encoding", "source_text", "expected_encoding"),
    [
        ("utf-16", "utf-16", "UTF-16 chapter: Привет.", "utf-16"),
        ("windows-1252", "cp1252", "CP1252 chapter: Café naïve.", "cp1252"),
        ("iso-8859-1", "iso-8859-1", "Latin-1 chapter: déjà vu.", "iso8859-1"),
    ],
)
def test_extract_text_honors_uniform_epub_content_encoding(
    tmp_path,
    declared_encoding: str,
    python_encoding: str,
    source_text: str,
    expected_encoding: str,
) -> None:
    """Verify a genuine non-UTF-8 EPUB member uses its declaration or BOM."""
    project_name = f"Epub_{expected_encoding.replace('-', '_')}"
    project_root, manifest = project_workspace_service.create_project(project_name, tmp_path)
    source_path = project_root / "story.epub"
    _write_epub_source(source_path)
    document = (
        f'<?xml version="1.0" encoding="{declared_encoding}"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        f"<p>{source_text}</p></body></html>"
    )
    _replace_epub_member(source_path, "chapter_1.xhtml", document.encode(python_encoding))
    manifest["source_document"] = _build_source_document(source_path, "epub")

    text_extraction_service.extract_text(project_root, manifest)

    canonical_text = (project_root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    ledger = source_ledger_service.load_source_ledger(project_root)
    assert canonical_text == f"{source_text}\n"
    assert ledger["source"]["encoding"] == expected_encoding


def test_extract_text_preserves_mixed_encoding_epub_spine_order(tmp_path) -> None:
    """Verify mixed EPUB encodings remain ordered and are reported truthfully."""
    project_root, manifest = project_workspace_service.create_project("MixedEncodingEpub", tmp_path)
    source_path = project_root / "story.epub"
    _write_two_chapter_epub_source(source_path)
    first_text = "First UTF-8 chapter."
    second_text = "Second CP1252 chapter: Café."
    first_document = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        f"<p>{first_text}</p></body></html>"
    ).encode()
    second_document = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
        '<meta charset="windows-1252"/></head><body>'
        f"<p>{second_text}</p></body></html>"
    ).encode("cp1252")
    _replace_epub_members(
        source_path,
        {
            "chapter_1.xhtml": first_document,
            "chapter_2.xhtml": second_document,
        },
    )
    manifest["source_document"] = _build_source_document(source_path, "epub")

    text_extraction_service.extract_text(project_root, manifest)

    canonical_text = (project_root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    ledger = source_ledger_service.load_source_ledger(project_root)
    assert canonical_text == f"{first_text}\n\n{second_text}\n"
    assert "AudioMancer Navigation" not in canonical_text
    assert ledger["source"]["encoding"] == "mixed(cp1252,utf-8)"


def test_extract_text_identifies_epub_item_with_invalid_declared_encoding(tmp_path) -> None:
    """Verify an invalid EPUB declaration fails with the responsible item identity."""
    project_root, manifest = project_workspace_service.create_project("InvalidEncodingEpub", tmp_path)
    source_path = project_root / "story.epub"
    _write_epub_source(source_path)
    invalid_document = (
        b'<?xml version="1.0" encoding="not-a-codec"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Story</p></body></html>'
    )
    _replace_epub_member(source_path, "chapter_1.xhtml", invalid_document)
    manifest["source_document"] = _build_source_document(source_path, "epub")

    with pytest.raises(ValueError, match=r"chapter_0.*chapter_1\.xhtml.*not-a-codec"):
        text_extraction_service.extract_text(project_root, manifest)


def test_extract_text_identifies_epub_item_when_declared_decoding_fails(tmp_path) -> None:
    """Verify strict declared decoding failures name the responsible EPUB item."""
    project_root, manifest = project_workspace_service.create_project("FailedDecodeEpub", tmp_path)
    source_path = project_root / "story.epub"
    _write_epub_source(source_path)
    invalid_document = (
        b'<?xml version="1.0" encoding="windows-1252"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Invalid byte: \x81</p></body></html>'
    )
    _replace_epub_member(source_path, "chapter_1.xhtml", invalid_document)
    manifest["source_document"] = _build_source_document(source_path, "epub")

    with pytest.raises(ValueError, match=r"chapter_0.*chapter_1\.xhtml.*declared cp1252"):
        text_extraction_service.extract_text(project_root, manifest)


def test_extract_text_rejects_misnamed_binary_doc_with_rtf_extension(tmp_path) -> None:
    """
    @brief      Verify misnamed binary Word containers do not pass through the RTF extractor.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project(
        "MisnamedBinaryDocProject",
        tmp_path,
    )
    source_path = project_root / "misnamed-binary-doc.rtf"
    source_path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)
    manifest["source_document"] = _build_source_document(source_path, "rtf")

    with pytest.raises(ValueError, match="Word \\.doc container"):
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
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("cleanup", encoding="utf-8")
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text("[]", encoding="utf-8")
    (project_root / "operator_note.txt").write_text("keep", encoding="utf-8")

    text_extraction_service.reset_extraction_and_downstream(project_root)

    assert source_path.is_file()
    assert (project_root / "operator_note.txt").is_file()
    assert (project_root / config.EXTRACTED_TEXT_FILE_NAME).exists() is False
    assert (project_root / config.EXTRACTION_METADATA_FILE_NAME).exists() is False
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).exists() is False
    assert (project_root / config.CHUNK_ARTIFACT_FILE_NAME).exists() is False


def _build_source_document(source_path: Path, file_type: str) -> dict[str, object]:
    """
    @brief      Build one minimal manifest source-document payload for tests.
    @param[in]  source_path Project-root source path.
    @param[in]  file_type Persisted source-type token.
    @return     Source-document payload.
    @exception  None
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
    """
    path.write_text("# Story\n\nParagraph", encoding="utf-8")


def _write_rtf_source(path: Path) -> None:
    """
    @brief      Write one RTF test source file.
    @param[in]  path Target source path.
    @return     None.
    @exception  None
    """
    path.write_text(r"{\rtf1\ansi Story paragraph}", encoding="utf-8")


def _write_docx_source(path: Path, paragraphs: list[str] | None = None) -> None:
    """
    @brief      Write one DOCX test source file.
    @param[in]  path Target source path.
    @param[in]  paragraphs Optional paragraph list.
    @return     None.
    @exception  None
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


def _write_two_chapter_epub_source(path: Path) -> None:
    """Write one EPUB fixture with two ordered content documents and navigation."""
    book = epub.EpubBook()
    book.set_identifier("two-chapter-book")
    book.set_title("Two chapters")
    book.set_language("en")
    first = epub.EpubHtml(title="Chapter 1", file_name="chapter_1.xhtml", lang="en")
    first.content = "<p>Placeholder one.</p>"
    second = epub.EpubHtml(title="Chapter 2", file_name="chapter_2.xhtml", lang="en")
    second.content = "<p>Placeholder two.</p>"
    book.add_item(first)
    book.add_item(second)
    book.toc = (first, second)
    book.spine = ["nav", first, second]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book, {})


def _replace_epub_member(path: Path, file_name: str, content: bytes) -> None:
    """Replace one EPUB ZIP member selected by its trailing file name."""
    _replace_epub_members(path, {file_name: content})


def _replace_epub_members(path: Path, replacements: dict[str, bytes]) -> None:
    """Rewrite EPUB ZIP members so tests retain genuine declared source bytes."""
    replacement_path = path.with_name(f"{path.stem}_replacement.epub")
    matched_names: set[str] = set()
    with (
        zipfile.ZipFile(path, "r") as source_archive,
        zipfile.ZipFile(replacement_path, "w") as target_archive,
    ):
        for member in source_archive.infolist():
            matching_name = next(
                (name for name in replacements if member.filename.endswith(name)),
                None,
            )
            if matching_name is None:
                content = source_archive.read(member.filename)
            else:
                content = replacements[matching_name]
                matched_names.add(matching_name)
            target_archive.writestr(member, content)
    assert matched_names == set(replacements)
    replacement_path.replace(path)


def _write_pdf_source(path: Path, page_texts: list[str]) -> None:
    """
    @brief      Write one PDF test source file with one text payload per page.
    @param[in]  path Target source path.
    @param[in]  page_texts Ordered page-text payloads.
    @return     None.
    @exception  None
    """
    document = fitz.open()
    for page_text in page_texts:
        page = document.new_page()
        if page_text:
            page.insert_text((72, 72), page_text)
    document.save(path)
    document.close()


def _pdf_order_line(
    text: str,
    bbox: tuple[float, float, float, float],
    index: int,
) -> dict[str, object]:
    """Build the minimum visual-line record required by PDF ordering tests."""
    return {
        "text": text,
        "bbox": list(bbox),
        "block_index": index,
        "line_index": 0,
        "column": None,
    }


def _two_column_pdf_lines(*, start_index: int = 0) -> list[dict[str, object]]:
    """Build three clearly separated lines in each PDF column."""
    return [
        _pdf_order_line("Left 1", (72.0, 100.0, 250.0, 110.0), start_index),
        _pdf_order_line("Left 2", (72.0, 130.0, 250.0, 140.0), start_index + 1),
        _pdf_order_line("Left 3", (72.0, 160.0, 250.0, 170.0), start_index + 2),
        _pdf_order_line("Right 1", (360.0, 100.0, 540.0, 110.0), start_index + 3),
        _pdf_order_line("Right 2", (360.0, 130.0, 540.0, 140.0), start_index + 4),
        _pdf_order_line("Right 3", (360.0, 160.0, 540.0, 170.0), start_index + 5),
    ]


def _write_two_column_pdf_source(path: Path) -> None:
    """Write a clear two-column PDF page with one centered narrow header."""
    document = fitz.open()
    page = document.new_page(width=612.0, height=792.0)
    for point, text in (
        ((297.0, 50.0), "MID"),
        ((72.0, 100.0), "Left one"),
        ((72.0, 130.0), "Left two"),
        ((72.0, 160.0), "Left three"),
        ((360.0, 100.0), "Right one"),
        ((360.0, 130.0), "Right two"),
        ((360.0, 160.0), "Right three"),
    ):
        page.insert_text(point, text, fontsize=10.0)
    document.save(path)
    document.close()


# END OF FILE
