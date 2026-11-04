#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_extraction_fidelity.py
@brief Exact-content regression tests for document extraction.
@details Verifies exact visible content, native roles, merged cells and PDF coverage diagnostics.
"""

# IMPORTS

from io import BytesIO
from unittest.mock import patch

from docx import Document
import fitz
import pytest

from audiomancer.extraction.formats import docx, html_content, markdown, pdf

# PUBLIC API


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        ("<body><p>First.</p>Tail.</body>", [("First.", "body"), ("Tail.", "body")]),
        (
            "<body><div>Before<p>Inside.</p>After</div></body>",
            [("Before", "body"), ("Inside.", "body"), ("After", "body")],
        ),
        ("<body><p>Verse one<br/>Verse two</p></body>", [("Verse one\nVerse two", "body")]),
        (
            "<body><blockquote><p>Quoted.</p>Tail.</blockquote></body>",
            [("Quoted.", "blockquote"), ("Tail.", "blockquote")],
        ),
    ],
)
def test_xhtml_preserves_all_visible_text_and_breaks(markup, expected):
    """@brief Preserve exact reader-visible content across nested XHTML blocks."""
    parser = html_content._StructuredHtmlExtractor(spine_index=0, item_id="chapter")
    parser.feed(markup)
    parser.close()
    assert [(event.text, event.kind) for event in parser.events] == expected


def test_docx_merged_cells_are_emitted_once():
    """@brief A merged cell contributes text once across rows and columns."""
    document = Document()
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).merge(table.cell(1, 1)).text = "One merged cell"
    stream = BytesIO()
    document.save(stream)
    stream.seek(0)
    result = docx._extract_docx(stream)
    assert [event.text for event in result.events] == ["One merged cell"]


def test_markdown_includes_visible_html_blocks(tmp_path):
    """@brief Embedded HTML remains part of the complete Markdown reading sequence."""
    source = tmp_path / "story.md"
    source.write_text("First.\n\n<p>HTML <em>story</em>.</p>\n\nLast.", encoding="utf-8")
    result = markdown._extract_markdown(source)
    assert [event.text for event in result.events] == ["First.", "HTML story.", "Last."]


def test_pdf_reports_image_only_pages_as_partial_coverage():
    """@brief Image-only pages require review without treating illustrations as fatal."""
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Text page.")
    page = document.new_page()
    image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), False)
    image.clear_with(255)
    page.insert_image(page.rect, stream=image.tobytes("png"))
    with patch.object(pdf.fitz, "open", return_value=document):
        result = pdf._extract_pdf(None)
    assert result.structure_quality == "geometry_partial"
    assert "image_only_page_requires_review" in result.eligibility_reason_codes
    assert "image_only_page_requires_review" in result.pages[1]["reason_codes"]
    assert any("page 2" in warning and "OCR" in warning for warning in result.warnings)

# END OF FILE
