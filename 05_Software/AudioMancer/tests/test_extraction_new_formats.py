#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_extraction_new_formats.py
@brief Complete-content and import integration tests for HTML and FictionBook.
@details Verifies complete content, encodings, XML constraints and project integration for HTML and FB2.
"""

# IMPORTS

import socket

import pytest

from audiomancer import config
from audiomancer.extraction import extract_document
from audiomancer.extraction.document import validate_source_ledger
from audiomancer.extraction.models import ExtractionCancelledError
from audiomancer.services import (
    project_options_service,
    project_workspace_service,
    text_extraction_service,
    ui_state_service,
)

# CONSTANTS

FB2_NAMESPACE = "http://www.gribuser.ru/xml/fictionbook/2.0"

# PUBLIC API


@pytest.mark.parametrize("suffix", ["html", "htm", "xhtml"])
def test_local_html_preserves_reading_order_and_avoids_external_resources(tmp_path, monkeypatch, suffix):
    """@brief Preserve all visible HTML text, explicit breaks and structure without network access."""
    source = tmp_path / f"story.{suffix}"
    source.write_text(
        '<!DOCTYPE html><html><head><title>Metadata</title><link rel="stylesheet" href="https://example.invalid/style.css"></head>'
        "<body><nav>Navigation</nav><h1>Chapter</h1><p>First <em>story</em>.</p>Tail."
        '<p hidden>Hidden</p><div style="DISPLAY : none !important">CSS hidden</div>'
        "<blockquote><p>Quoted.</p></blockquote><p>Line one<br>Line two</p>"
        '<script src="https://example.invalid/script.js">Forbidden script text</script></body></html>',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        socket, "create_connection", lambda *_args, **_kwargs: pytest.fail("External resource requested")
    )
    result = extract_document(source)
    assert result.text == "Chapter\n\nFirst story.\n\nTail.\n\nQuoted.\n\nLine one\nLine two\n"
    assert result.ledger["source"]["format"] == "html"
    assert result.ledger["units"][0]["kind"] == "heading"
    assert result.ledger["units"][3]["kind"] == "blockquote"
    assert all(
        "block_index" in unit["locator"] and "spine_index" not in unit["locator"] for unit in result.ledger["units"]
    )
    validate_source_ledger(result.ledger, result.text)


def test_prefixed_xhtml_blocks_keep_native_structure(tmp_path):
    """@brief Prefixed XHTML uses the same paragraph and heading semantics as ordinary HTML."""
    source = tmp_path / "story.xhtml"
    source.write_text(
        '<h:html xmlns:h="http://www.w3.org/1999/xhtml"><h:head><h:title>Ignore</h:title></h:head>'
        "<h:body><h:h2>Heading</h:h2><h:p>Paragraph.</h:p></h:body></h:html>",
        encoding="utf-8",
    )
    result = extract_document(source)
    assert result.text == "Heading\n\nParagraph.\n"
    assert result.ledger["units"][0]["native"]["heading_level"] == 2


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "cp1251"])
def test_html_and_fb2_honor_declared_encoding(tmp_path, encoding):
    """@brief Preserve Unicode content and report the actual encoding for both markup formats."""
    text = "\u041f\u0440\u0438\u0432\u0435\u0442, \u043a\u043d\u0438\u0433\u0430!"
    for suffix, markup in (
        ("html", f'<html><head><meta charset="{encoding}"></head><body><p>{text}</p></body></html>'),
        (
            "fb2",
            f'<?xml version="1.0" encoding="{encoding}"?>'
            f'<FictionBook xmlns="{FB2_NAMESPACE}"><body><section><p>{text}</p>'
            "</section></body></FictionBook>",
        ),
    ):
        source = tmp_path / f"story.{suffix}"
        source.write_bytes(markup.encode(encoding))
        result = extract_document(source)
        assert result.text == text + "\n"
        assert result.ledger["source"]["encoding"] == encoding


def test_fb2_extracts_body_poetry_tables_and_notes_without_metadata(tmp_path):
    """@brief Keep body content once, with semantic roles, excluding metadata and binary payloads."""
    source = tmp_path / "story.fb2"
    source.write_text(
        f'<FictionBook xmlns="{FB2_NAMESPACE}">'
        "<description><title-info><book-title>Metadata title</book-title>"
        "<annotation><p>Metadata annotation</p></annotation></title-info></description>"
        '<body><title><p>Book</p></title><section id="chapter"><title><p>Chapter</p></title>'
        '<p>First <strong>paragraph</strong> <a href="#n1">[1]</a>.</p>'
        "<cite><p>Quoted.</p></cite><poem><stanza><v>Verse one</v><v>Verse two</v></stanza>"
        "<stanza><v>Last verse</v></stanza></poem><table><tr><td>A</td><td>B</td></tr></table></section></body>"
        '<body name="notes"><section id="n1"><title><p>Note 1</p></title><p>Note content.</p></section></body>'
        '<binary id="cover" content-type="image/png">Not narrative</binary></FictionBook>',
        encoding="utf-8",
    )
    result = extract_document(source)
    assert (
        result.text == "Book\n\nChapter\n\nFirst paragraph [1].\n\nQuoted.\n\n"
        "Verse one\nVerse two\n\nLast verse\nA\tB\n\nNote 1\n\nNote content.\n"
    )
    assert [unit["kind"] for unit in result.ledger["units"]] == [
        "heading",
        "heading",
        "body",
        "blockquote",
        "verse",
        "verse",
        "table_or_preformatted",
        "heading",
        "footnote",
    ]
    assert result.ledger["units"][-1]["locator"]["body_index"] == 1
    assert result.ledger["units"][-1]["native"]["body_name"] == "notes"
    assert any("notes" in warning for warning in result.ledger["warnings"])
    validate_source_ledger(result.ledger, result.text)


@pytest.mark.parametrize(
    "content",
    [
        "<html><body>Wrong format</body></html>",
        f'<FictionBook xmlns="{FB2_NAMESPACE}"><description/></FictionBook>',
        f'<FictionBook xmlns="{FB2_NAMESPACE}"><body><section><p>Broken</section></body></FictionBook>',
        '<FictionBook xmlns="urn:wrong"><body><section><p>Wrong namespace</p></section></body></FictionBook>',
        '<!DOCTYPE FictionBook [<!ENTITY injected "Forbidden">]>'
        f'<FictionBook xmlns="{FB2_NAMESPACE}"><body><section><p>&injected;</p>'
        "</section></body></FictionBook>",
    ],
)
def test_fb2_rejects_unusable_or_unsafe_xml(tmp_path, content):
    """@brief Reject malformed FictionBook and DTD/entity payloads with a format-specific error."""
    source = tmp_path / "invalid.fb2"
    source.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="FB2"):
        extract_document(source)
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize(
    ("suffix", "kind", "content"),
    [
        ("html", "html", "<html><body><p>Story.</p></body></html>"),
        ("htm", "html", "<p>Story.</p>"),
        ("xhtml", "html", '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Story.</p></body></html>'),
        (
            "fb2",
            "fb2",
            f'<FictionBook xmlns="{FB2_NAMESPACE}"><body><section><p>Story.</p></section></body></FictionBook>',
        ),
    ],
)
def test_new_formats_work_through_project_creation_and_extraction(tmp_path, suffix, kind, content):
    """@brief Import, persist, reopen and extract the new formats through the existing project workflow."""
    source = tmp_path / f"book.{suffix}"
    source.write_text(content, encoding="utf-8")
    root, manifest = project_options_service.create_project_with_source("New source", tmp_path, source)
    assert manifest["source_document"]["file_type"] == kind
    reopened = project_workspace_service.load_manifest(root)
    metadata = text_extraction_service.extract_text(root, reopened)
    assert metadata["status"] == "completed"
    assert (root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8") == "Story.\n"
    for language in ("en", "ro"):
        assert f"*.{suffix}" in ui_state_service.translate("dialog.select_source_filter", language)


@pytest.mark.parametrize("kind", ["html", "fb2"])
def test_cancel_new_adapters_without_output_files(tmp_path, kind):
    """@brief Honour cancellation after real parsing progress without producing project artifacts."""
    source = tmp_path / f"book.{kind}"
    body = "".join(f"<p>Paragraph {index}.</p>" for index in range(3000))
    markup = (
        f"<body>{body}</body>"
        if kind == "html"
        else f'<FictionBook xmlns="{FB2_NAMESPACE}"><body><section>{body}</section></body></FictionBook>'
    )
    source.write_text(markup, encoding="utf-8")
    progress = []
    with pytest.raises(ExtractionCancelledError):
        extract_document(
            source,
            on_progress=lambda current, *_args: progress.append(current),
            is_cancelled=lambda: any(value > 0 for value in progress),
        )
    assert source.read_text(encoding="utf-8") == markup
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize("kind", ["html", "fb2"])
def test_failed_new_format_rerun_keeps_previous_results(tmp_path, kind):
    """@brief New-format parse errors retain the previous extraction and every downstream byte."""
    source = tmp_path / f"book.{kind}"
    content = (
        "<body><p>Story.</p></body>"
        if kind == "html"
        else f'<FictionBook xmlns="{FB2_NAMESPACE}"><body><section><p>Story.</p></section></body></FictionBook>'
    )
    source.write_text(content, encoding="utf-8")
    root, manifest = project_options_service.create_project_with_source("Preserve results", tmp_path, source)
    text_extraction_service.extract_text(root, manifest)
    (root / config.CLEANED_TEXT_FILE_NAME).write_text("Approved cleanup", encoding="utf-8")
    stored_source = root / manifest["source_document"]["stored_relative_path"]
    invalid = '<meta charset="invalid-codec"><p>Story</p>' if kind == "html" else "<FictionBook>Broken XML"
    stored_source.write_text(invalid, encoding="utf-8")
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    with pytest.raises(ValueError):
        text_extraction_service.extract_text(root, manifest)
    after = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert after == before


def test_fb2_poetry_survives_cleanup(tmp_path):
    """@brief Verse structure from the new adapter remains protected by the existing Cleanup consumer."""
    from audiomancer.services import text_cleanup_service

    source = tmp_path / "poem.fb2"
    source.write_text(
        f'<FictionBook xmlns="{FB2_NAMESPACE}"><body><section><poem><stanza>'
        "<v>First verse</v><v>Second verse</v></stanza></poem></section></body></FictionBook>",
        encoding="utf-8",
    )
    root, manifest = project_options_service.create_project_with_source("Poem", tmp_path, source)
    text_extraction_service.extract_text(root, manifest)
    text_cleanup_service.clean_text(root, project_workspace_service.load_manifest(root))
    assert "First verse\nSecond verse" in (root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")


def test_picker_and_import_registry_are_identical_in_both_languages():
    """@brief Every accepted extension is visible in the book picker, including all HTML aliases."""
    for language in ("en", "ro"):
        picker = ui_state_service.translate("dialog.select_source_filter", language)
        patterns = picker.split("(", 1)[1].rstrip(")").split()
        assert set(patterns) == {f"*{suffix}" for suffix in config.SUPPORTED_SOURCE_SUFFIXES}


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        ("<html><head><title>Metadata</title><body><p>Story.</p></body></html>", "Story.\n"),
        ("<title>Metadata</title><p>Story.</p>", "Story.\n"),
        ("<ul><li>First<li>Second</ul><p>After.</p>", "First\n\nSecond\n\nAfter.\n"),
    ],
)
def test_html_optional_end_tags_preserve_content_and_roles(tmp_path, markup, expected):
    """@brief Accept ordinary HTML with optional head/list end tags, retaining list semantics."""
    source = tmp_path / "optional.html"
    source.write_text(markup, encoding="utf-8")
    result = extract_document(source)
    assert result.text == expected
    if markup.startswith("<ul>"):
        assert [unit["kind"] for unit in result.ledger["units"]] == ["list_or_dialogue", "list_or_dialogue", "body"]


# END OF FILE
