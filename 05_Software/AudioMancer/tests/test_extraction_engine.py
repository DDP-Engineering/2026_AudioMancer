#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_extraction_engine.py
@brief Exact-content regression tests for document extraction.
@details Verifies complete canonical outputs, standalone imports and restart/cancellation boundaries.
"""

# IMPORTS

import subprocess
import sys

from ebooklib import epub
import fitz
import pytest

from audiomancer.extraction import extract_document
from audiomancer.extraction.document import validate_source_ledger
from audiomancer.extraction.models import ExtractionCancelledError
from test_text_extraction_service import (
    _write_docx_source,
    _write_epub_source,
    _write_markdown_source,
    _write_odt_source,
    _write_rtf_source,
)

# PUBLIC API


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("txt", "First.\n\nSecond.\n"),
        ("md", "Story\n\nParagraph\n"),
        ("rtf", "Story paragraph\n"),
        ("docx", "Story paragraph\n"),
        ("odt", "Story paragraph\n"),
        ("epub", "Story\n\nParagraph\n"),
        ("pdf", "Story paragraph\n"),
    ],
)
def test_engine_complete_outputs_without_project_or_output_writes(tmp_path, kind, expected):
    """@brief Compare complete canonical content and ledger invariants for every supported format."""
    source = tmp_path / f"story.{kind}"
    if kind == "txt":
        source.write_text("First.\r\n\r\nSecond.", encoding="utf-8")
    elif kind == "pdf":
        with fitz.open() as document:
            document.new_page().insert_text((72, 72), "Story paragraph")
            document.save(source)
    else:
        {
            "md": _write_markdown_source,
            "rtf": _write_rtf_source,
            "docx": _write_docx_source,
            "odt": _write_odt_source,
            "epub": _write_epub_source,
        }[kind](source)
    before = source.read_bytes()
    progress = []
    result = extract_document(source, on_progress=lambda current, total, _message: progress.append((current, total)))
    assert result.text == expected
    validate_source_ledger(result.ledger, result.text)
    assert source.read_bytes() == before
    assert list(tmp_path.iterdir()) == [source]
    assert progress[-1] == (95, 100)
    assert all(current < total for current, total in progress)


def test_engine_can_be_imported_without_application_services_or_qt():
    """@brief The extraction engine remains independently usable outside the desktop application."""
    code = (
        "import sys; import audiomancer.extraction; "
        "assert not any(n.startswith(('PySide6', 'audiomancer.services', 'audiomancer.config')) "
        "for n in sys.modules)"
    )
    subprocess.run([sys.executable, "-B", "-c", code], check=True, timeout=30)


def test_engine_cancels_before_reading_or_writing(tmp_path):
    """@brief A cancelled request needs neither a project nor an existing source file."""
    with pytest.raises(ExtractionCancelledError):
        extract_document(tmp_path / "missing.pdf", is_cancelled=lambda: True)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("suffix", ["doc", "mobi", "azw3"])
def test_unimplemented_formats_are_not_enabled(tmp_path, suffix):
    """@brief Only the explicitly supported source formats are accepted."""
    path = tmp_path / f"story.{suffix}"
    path.write_text("<p>Story.</p>", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported source type"):
        extract_document(path)


def test_epub_auxiliary_text_is_preserved_with_diagnostic(tmp_path):
    """@brief Nonlinear EPUB content stays in spine order and is explicitly identified for review."""
    book = epub.EpubBook()
    book.set_identifier("auxiliary")
    book.set_title("Story")
    book.set_language("en")
    chapter = epub.EpubHtml(uid="chapter", file_name="chapter.xhtml", content="<p>Main.</p>")
    note = epub.EpubHtml(uid="notes", file_name="notes.xhtml", content="<p>Notes.</p>")
    book.add_item(chapter)
    book.add_item(note)
    book.spine = [(chapter, "yes"), (note, "no")]
    book.add_item(epub.EpubNcx())
    path = tmp_path / "story.epub"
    epub.write_epub(str(path), book, {})
    result = extract_document(path)
    assert result.text == "Main.\n\nNotes.\n"
    assert result.ledger["units"][-1]["native"]["linear"] is False
    assert any("auxiliary" in warning for warning in result.ledger["warnings"])

# END OF FILE
