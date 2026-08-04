#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file text_extraction_adapters.py
@brief Format-specific SourceEvent adapters used by Text Extraction.
@details Preserves native structure when available and emits one common event
         stream consumed by CanonicalDocumentBuilder.
"""

from __future__ import annotations

import codecs
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
import math
from pathlib import Path
import re
import unicodedata

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
import ebooklib
from ebooklib import epub
import fitz
from markdown_it import MarkdownIt
from odf import teletype
from odf.opendocument import load as load_odf_document
from striprtf.striprtf import rtf_to_text

from audiomancer.services.operation_runtime_service import raise_if_cancelled
from audiomancer.services.source_ledger_service import SourceEvent

_PAGE_BREAK_SEPARATOR = "\n\n\f\n\n"
_LEGACY_TEXT_ENCODINGS = ("cp1250", "cp1251", "cp1252")
_LEGACY_TIE_PRIORITY = {"cp1251": 0, "cp1250": 1, "cp1252": 2}
_CENTRAL_EUROPEAN_LETTERS = frozenset(
    "\u0104\u0105\u0106\u0107\u010c\u010d\u010e\u010f\u0110\u0111\u0118\u0119\u011a\u011b"
    "\u0139\u013a\u013d\u013e\u0141\u0142\u0143\u0144\u0147\u0148\u0150\u0151\u0154\u0155"
    "\u0158\u0159\u015a\u015b\u0160\u0161\u0164\u0165\u016e\u016f\u0170\u0171\u0179\u017a"
    "\u017b\u017c\u017d\u017e"
)
_WESTERN_EUROPEAN_LETTERS = frozenset(
    "\u00c0\u00c1\u00c2\u00c3\u00c4\u00c5\u00c6\u00c7\u00c8\u00c9\u00ca\u00cb"
    "\u00cc\u00cd\u00ce\u00cf\u00d0\u00d1\u00d2\u00d3\u00d4\u00d5\u00d6\u00d8"
    "\u00d9\u00da\u00db\u00dc\u00dd\u00de\u00df\u00e0\u00e1\u00e2\u00e3\u00e4"
    "\u00e5\u00e6\u00e7\u00e8\u00e9\u00ea\u00eb\u00ec\u00ed\u00ee\u00ef\u00f0"
    "\u00f1\u00f2\u00f3\u00f4\u00f5\u00f6\u00f8\u00f9\u00fa\u00fb\u00fc\u00fd"
    "\u00fe\u00ff"
)
_WESTERN_TYPOGRAPHY = frozenset("\u2018\u2019\u201c\u201d\u2013\u2014\u2026\u20ac\u0152\u0153\u0178")
_XML_ENCODING_PATTERN = re.compile(
    r"<\?xml\b[^>]*\bencoding\s*=\s*['\"]\s*([^'\"\s]+)",
    re.IGNORECASE,
)
_META_TAG_PATTERN = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_META_CHARSET_PATTERN = re.compile(r"\bcharset\s*=\s*['\"]?\s*([^\s'\"/>;]+)", re.IGNORECASE)
_META_ATTRIBUTE_PATTERN = re.compile(
    r"([^\s=/>]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
    re.IGNORECASE,
)
_RTF_CODE_PAGE_PATTERN = re.compile(br"\\ansicpg(\d{3,5})\b", re.IGNORECASE)
_PDF_PAGE_EDGE_FRACTION = 0.12


@dataclass(frozen=True)
class ExtractionAdapterResult:
    """One adapter's canonical event stream and structural diagnostics."""

    events: list[SourceEvent]
    warnings: list[str]
    pages: list[dict[str, object]]
    structure_quality: str
    eligibility_mode: str
    eligibility_reason_codes: list[str]
    encoding: str | None
    progress_total: int
    page_count: int | None


def extract_source_events(
    source_path: Path,
    file_type: str,
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    cancel_requested=None,
) -> ExtractionAdapterResult:
    """Dispatch one source file to its structural adapter."""
    adapters = {
        "txt": _extract_txt,
        "md": _extract_markdown,
        "rtf": _extract_rtf,
        "docx": _extract_docx,
        "odt": _extract_odt,
        "epub": _extract_epub,
        "pdf": _extract_pdf,
    }
    adapter = adapters.get(str(file_type))
    if adapter is None:
        raise ValueError(f"Unsupported source type for extraction: {file_type}")
    return adapter(
        Path(source_path),
        progress_callback=progress_callback,
        cancel_requested=cancel_requested,
    )


def _extract_txt(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """Extract physical text lines while preserving blank-line boundaries."""
    raise_if_cancelled(cancel_requested)
    text, encoding = _read_text_with_fallback(source_path)
    events = _line_events(text, structure_origin="inferred")
    _emit_adapter_progress(progress_callback, 1, 1, "Text source parsed.")
    return ExtractionAdapterResult(
        events=events,
        warnings=[],
        pages=[],
        structure_quality="text_only",
        eligibility_mode="text_only",
        eligibility_reason_codes=[],
        encoding=encoding,
        progress_total=1,
        page_count=None,
    )


def _extract_markdown(
    source_path: Path,
    *,
    progress_callback=None,
    cancel_requested=None,
) -> ExtractionAdapterResult:
    """Extract reader-facing CommonMark blocks with native structural roles."""
    raise_if_cancelled(cancel_requested)
    text, encoding = _read_text_with_fallback(source_path)
    tokens = MarkdownIt("commonmark").parse(text)
    events: list[SourceEvent] = []
    stack: list[str] = []
    heading_level: int | None = None
    list_depth = 0
    blockquote_depth = 0

    for token_index, token in enumerate(tokens):
        raise_if_cancelled(cancel_requested)
        token_type = token.type
        if token_type.endswith("_open"):
            stack.append(token_type)
            if token_type == "heading_open":
                heading_level = _heading_level(token.tag)
            elif token_type in {"bullet_list_open", "ordered_list_open"}:
                list_depth += 1
            elif token_type == "blockquote_open":
                blockquote_depth += 1
            continue
        if token_type.endswith("_close"):
            if token_type == "heading_close":
                heading_level = None
            elif token_type in {"bullet_list_close", "ordered_list_close"}:
                list_depth = max(0, list_depth - 1)
            elif token_type == "blockquote_close":
                blockquote_depth = max(0, blockquote_depth - 1)
            if stack:
                stack.pop()
            continue
        if token_type == "hr":
            events.append(
                SourceEvent(
                    text="***",
                    kind="separator",
                    structure_origin="native",
                    boundary_before="\n\n",
                    boundary_kind="native_paragraph",
                    locator={"token_index": token_index},
                    native={"tag": "hr"},
                )
            )
            continue
        if token_type in {"fence", "code_block"}:
            code_text = token.content.rstrip("\n")
            if code_text:
                events.append(
                    SourceEvent(
                        text=code_text,
                        kind="table_or_preformatted",
                        structure_origin="native",
                        boundary_before="\n\n",
                        boundary_kind="native_paragraph",
                        locator={"token_index": token_index},
                        native={"tag": token.tag or token_type, "info": str(token.info or "")},
                    )
                )
            continue
        if token_type != "inline":
            continue
        visible_text = _markdown_inline_text(token)
        if not visible_text.strip():
            continue
        if heading_level is not None:
            kind = "heading"
        elif list_depth:
            kind = "list_or_dialogue"
        elif blockquote_depth:
            kind = "blockquote"
        else:
            kind = "body"
        events.append(
            SourceEvent(
                text=visible_text.strip(),
                kind=kind,
                structure_origin="native",
                boundary_before="\n\n",
                boundary_kind="native_paragraph",
                locator={"token_index": token_index, "line_map": list(token.map or [])},
                native={
                    "tag": token.tag or "inline",
                    "heading_level": heading_level,
                    "list_level": list_depth or None,
                    "blockquote_depth": blockquote_depth or None,
                },
            )
        )

    _emit_adapter_progress(progress_callback, 1, 1, "Markdown structure parsed.")
    return ExtractionAdapterResult(
        events=events,
        warnings=[],
        pages=[],
        structure_quality="native",
        eligibility_mode="native",
        eligibility_reason_codes=[],
        encoding=encoding,
        progress_total=1,
        page_count=None,
    )


def _extract_rtf(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """Extract RTF text while declaring unavailable style structure."""
    raise_if_cancelled(cancel_requested)
    source_bytes = source_path.read_bytes()
    if source_bytes.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise ValueError(
            "The selected .rtf file is actually a legacy Word .doc container. "
            "Legacy .doc extraction is not supported in this phase."
        )
    if not source_bytes.lstrip().startswith(b"{\\rtf"):
        raise ValueError("The selected .rtf file does not contain a valid RTF header.")
    code_page_match = _RTF_CODE_PAGE_PATTERN.search(source_bytes[:512])
    if code_page_match is None:
        decoded, encoding = _decode_bytes_with_fallback(source_bytes)
    else:
        declared_encoding = f"cp{code_page_match.group(1).decode('ascii')}"
        decoded, encoding = _decode_declared_bytes(
            source_bytes,
            declared_encoding,
            context=f"RTF source '{source_path.name}'",
        )
    plain_text = rtf_to_text(decoded)
    events = _paragraph_events(plain_text, structure_origin="inferred")
    _emit_adapter_progress(progress_callback, len(events), max(1, len(events)), "RTF paragraphs parsed.")
    return ExtractionAdapterResult(
        events=events,
        warnings=["RTF style and list metadata are unavailable; text structure is conservative."],
        pages=[],
        structure_quality="text_only",
        eligibility_mode="text_only",
        eligibility_reason_codes=["rtf_style_metadata_unavailable"],
        encoding=encoding,
        progress_total=max(1, len(events)),
        page_count=None,
    )


def _extract_docx(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """Extract DOCX paragraphs and tables in body order."""
    document = Document(source_path)
    events: list[SourceEvent] = []
    warnings: list[str] = []
    body_children = list(document.element.body.iterchildren())
    total = max(1, len(body_children))
    parent = document._body  # noqa: SLF001 - python-docx requires the owning body proxy.

    for body_index, child in enumerate(body_children):
        raise_if_cancelled(cancel_requested)
        tag_name = child.tag.rsplit("}", 1)[-1]
        if tag_name == "p":
            paragraph = Paragraph(child, parent)
            text = paragraph.text.strip()
            if text:
                style_name = paragraph.style.name if paragraph.style is not None else None
                numbering = paragraph._p.pPr.numPr if paragraph._p.pPr is not None else None  # noqa: SLF001
                if style_name and style_name.casefold().startswith("heading"):
                    kind = "heading"
                elif numbering is not None:
                    kind = "list_or_dialogue"
                else:
                    kind = "body"
                events.append(
                    SourceEvent(
                        text=text,
                        kind=kind,
                        structure_origin="native",
                        boundary_before="\n\n",
                        boundary_kind="native_paragraph",
                        locator={"body_index": body_index},
                        native={
                            "style_name": style_name,
                            "alignment": None if paragraph.alignment is None else int(paragraph.alignment),
                            "numbered": numbering is not None,
                        },
                    )
                )
        elif tag_name == "tbl":
            table = Table(child, parent)
            table_parent_id = f"docx-table-{body_index:04d}"
            for row_index, row in enumerate(table.rows):
                row_text = "\t".join(cell.text.strip() for cell in row.cells).strip()
                if row_text:
                    events.append(
                        SourceEvent(
                            text=row_text,
                            kind="table_or_preformatted",
                            structure_origin="native",
                            boundary_before="\n",
                            boundary_kind="table_row",
                            parent_id=table_parent_id,
                            locator={"body_index": body_index, "row_index": row_index},
                            native={"table": True},
                        )
                    )
        _emit_adapter_progress(progress_callback, body_index + 1, total, "DOCX structure parsed.")

    return ExtractionAdapterResult(
        events=events,
        warnings=warnings,
        pages=[],
        structure_quality="native_partial",
        eligibility_mode="native_partial",
        eligibility_reason_codes=["embedded_text_objects_not_enumerated"],
        encoding=None,
        progress_total=total,
        page_count=None,
    )


def _extract_odt(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """Extract common ODT structural elements in document order."""
    document = load_odf_document(str(source_path))
    events: list[SourceEvent] = []
    nodes = list(_walk_odf_nodes(document.text))
    total = max(1, len(nodes))
    for node_index, (node, list_depth) in enumerate(nodes):
        raise_if_cancelled(cancel_requested)
        local_name = _odf_local_name(node)
        text = teletype.extractText(node).strip()
        if not text:
            continue
        if local_name == "h":
            kind = "heading"
        elif local_name in {"table-cell", "covered-table-cell"}:
            kind = "table_or_preformatted"
        elif list_depth:
            kind = "list_or_dialogue"
        else:
            kind = "body"
        events.append(
            SourceEvent(
                text=text,
                kind=kind,
                structure_origin="native",
                boundary_before="\n" if kind == "table_or_preformatted" else "\n\n",
                boundary_kind="table_row" if kind == "table_or_preformatted" else "native_paragraph",
                locator={"node_index": node_index},
                native={
                    "element": local_name,
                    "style_name": _odf_attribute(node, "stylename"),
                    "outline_level": _odf_attribute(node, "outlinelevel"),
                    "list_level": list_depth or None,
                },
            )
        )
        _emit_adapter_progress(progress_callback, node_index + 1, total, "ODT structure parsed.")

    return ExtractionAdapterResult(
        events=events,
        warnings=[],
        pages=[],
        structure_quality="native_partial",
        eligibility_mode="native_partial",
        eligibility_reason_codes=["embedded_text_objects_not_enumerated"],
        encoding=None,
        progress_total=total,
        page_count=None,
    )


def _extract_epub(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """Extract visible XHTML blocks in EPUB spine order."""
    book = epub.read_epub(str(source_path), options={"ignore_ncx": False})
    events: list[SourceEvent] = []
    warnings: list[str] = []
    content_encodings: list[str] = []
    spine = list(book.spine)
    total = max(1, len(spine))
    for spine_index, spine_entry in enumerate(spine):
        raise_if_cancelled(cancel_requested)
        item_id = spine_entry[0] if isinstance(spine_entry, (tuple, list)) else spine_entry
        item = book.get_item_with_id(str(item_id))
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            _emit_adapter_progress(progress_callback, spine_index + 1, total, "EPUB spine parsed.")
            continue
        properties = {str(value).casefold() for value in getattr(item, "properties", [])}
        if "nav" in properties or str(item_id).casefold() == "nav":
            _emit_adapter_progress(progress_callback, spine_index + 1, total, "EPUB navigation skipped.")
            continue
        item_name = str(getattr(item, "file_name", "") or getattr(item, "get_name", lambda: "")())
        item_context = f"EPUB spine item '{item_id}' ({item_name or 'unnamed content document'})"
        raw_content = getattr(item, "content", None)
        content_bytes = bytes(raw_content) if isinstance(raw_content, bytes | bytearray) else item.get_content()
        decoded_content, content_encoding = _decode_epub_document_bytes(
            content_bytes,
            context=item_context,
        )
        parser = _StructuredHtmlExtractor(spine_index=spine_index, item_id=str(item_id))
        parser.feed(decoded_content)
        parser.close()
        events.extend(parser.events)
        warnings.extend(parser.warnings)
        content_encodings.append(content_encoding)
        _emit_adapter_progress(progress_callback, spine_index + 1, total, "EPUB spine parsed.")

    return ExtractionAdapterResult(
        events=events,
        warnings=warnings,
        pages=[],
        structure_quality="native",
        eligibility_mode="native",
        eligibility_reason_codes=[],
        encoding=_summarize_epub_encodings(content_encodings),
        progress_total=total,
        page_count=None,
    )


def _extract_pdf(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """Extract PDF visual lines and geometry from one TextPage representation."""
    events: list[SourceEvent] = []
    warnings: list[str] = []
    pages: list[dict[str, object]] = []
    reason_codes: set[str] = set()
    any_text = False
    any_partial = False
    with fitz.open(source_path) as document:
        total = max(1, len(document))
        for page_index, page in enumerate(document):
            raise_if_cancelled(cancel_requested)
            page_dict = page.get_text("dict", sort=False)
            page_width = float(page.rect.width)
            page_height = float(page.rect.height)
            raw_lines = _pdf_lines(page_dict, page_index, page_width, page_height)
            ordered_lines, layout_mode, page_reasons = _order_pdf_lines(raw_lines, page_width)
            reason_codes.update(page_reasons)
            if layout_mode != "single_column":
                any_partial = True
            if not ordered_lines:
                warnings.append(f"PDF page {page_index + 1} did not contain extractable text.")
            else:
                any_text = True
            image_area = _pdf_image_area(page_dict)
            pages.append(
                {
                    "page_index": page_index,
                    "mediabox": [float(value) for value in page.mediabox],
                    "cropbox": [float(value) for value in page.cropbox],
                    "rotation": int(page.rotation),
                    "width": page_width,
                    "height": page_height,
                    "image_area_ratio": 0.0
                    if page_width <= 0 or page_height <= 0
                    else min(1.0, image_area / (page_width * page_height)),
                    "text_line_count": len(ordered_lines),
                    "layout_mode": layout_mode,
                    "reason_codes": list(page_reasons),
                }
            )
            for line_position, line in enumerate(ordered_lines):
                boundary_before = (
                    _PAGE_BREAK_SEPARATOR
                    if events and line_position == 0
                    else ("\n" if events else None)
                )
                events.append(
                    SourceEvent(
                        text=str(line["text"]),
                        kind="unknown",
                        structure_origin="layout",
                        boundary_before=boundary_before,
                        boundary_kind="page" if line_position == 0 and events else "visual_line",
                        locator={
                            "page_index": page_index,
                            "block_index": int(line["block_index"]),
                            "line_index": int(line["line_index"]),
                        },
                        layout={
                            "bbox": list(line["bbox"]),
                            "direction": list(line["direction"]),
                            "dominant_font_size": float(line["dominant_font_size"]),
                            "max_font_size": float(line["max_font_size"]),
                            "bold_fraction": float(line["bold_fraction"]),
                            "font_signature": str(line["font_signature"]),
                            "relative_vertical_position": float(line["relative_vertical_position"]),
                            "column": line.get("column"),
                            "layout_mode": layout_mode,
                        },
                    )
                )
            _emit_adapter_progress(
                progress_callback,
                page_index + 1,
                total,
                f"PDF page {page_index + 1} parsed.",
            )

    if not any_text:
        raise ValueError("PDF source did not contain extractable text. OCR is not supported in this phase.")
    quality = "geometry_partial" if any_partial else "geometry_full"
    return ExtractionAdapterResult(
        events=events,
        warnings=warnings,
        pages=pages,
        structure_quality=quality,
        eligibility_mode=quality,
        eligibility_reason_codes=sorted(reason_codes),
        encoding=None,
        progress_total=len(pages),
        page_count=len(pages),
    )


class _StructuredHtmlExtractor(HTMLParser):
    """Extract visible block-level text and native roles from XHTML."""

    _BLOCK_KINDS = {
        "p": "body",
        "h1": "heading",
        "h2": "heading",
        "h3": "heading",
        "h4": "heading",
        "h5": "heading",
        "h6": "heading",
        "li": "list_or_dialogue",
        "blockquote": "blockquote",
        "pre": "table_or_preformatted",
    }

    def __init__(self, *, spine_index: int, item_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[SourceEvent] = []
        self.warnings: list[str] = []
        self._spine_index = spine_index
        self._item_id = item_id
        self._ignore_depth = 0
        self._active_tag: str | None = None
        self._active_kind: str | None = None
        self._parts: list[str] = []
        self._block_index = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_map = {str(key).casefold(): str(value) for key, value in attrs if value is not None}
        if self._ignore_depth:
            self._ignore_depth += 1
            return
        if tag in {"script", "style", "nav"} or "hidden" in attrs_map or attrs_map.get("aria-hidden") == "true":
            self._ignore_depth = 1
            return
        if tag == "hr":
            self._flush_block()
            self._append_event("***", "separator", tag)
            return
        if tag == "br":
            self._parts.append("\n")
            return
        if tag in self._BLOCK_KINDS:
            self._flush_block()
            self._active_tag = tag
            self._active_kind = self._BLOCK_KINDS[tag]

    def handle_endtag(self, tag: str) -> None:
        if self._ignore_depth:
            self._ignore_depth -= 1
            return
        if tag == self._active_tag:
            self._flush_block()

    def handle_data(self, data: str) -> None:
        if self._ignore_depth:
            return
        if self._active_tag is not None:
            self._parts.append(data)

    def close(self) -> None:
        self._flush_block()
        super().close()

    def _flush_block(self) -> None:
        if self._active_tag is None:
            self._parts.clear()
            return
        text = "".join(self._parts)
        if self._active_tag == "pre":
            normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
        else:
            normalized = " ".join(text.split())
        if normalized:
            self._append_event(normalized, self._active_kind or "body", self._active_tag)
        self._active_tag = None
        self._active_kind = None
        self._parts.clear()

    def _append_event(self, text: str, kind: str, tag: str) -> None:
        self._block_index += 1
        self.events.append(
            SourceEvent(
                text=text,
                kind=kind,
                structure_origin="native",
                boundary_before="\n\n",
                boundary_kind="native_paragraph",
                locator={
                    "spine_index": self._spine_index,
                    "item_id": self._item_id,
                    "block_index": self._block_index,
                },
                native={"tag": tag, "heading_level": _heading_level(tag)},
            )
        )


def _line_events(text: str, *, structure_origin: str) -> list[SourceEvent]:
    """Convert physical lines to events while retaining blank-line strength."""
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    events: list[SourceEvent] = []
    blank_count = 0
    for line_index, raw_line in enumerate(normalized.split("\n")):
        line = raw_line.strip()
        if not line:
            blank_count += 1
            continue
        boundary = None
        if events:
            boundary = "\n\n" if blank_count else "\n"
        events.append(
            SourceEvent(
                text=line,
                kind="unknown",
                structure_origin=structure_origin,
                boundary_before=boundary,
                boundary_kind="blank_paragraph" if blank_count else "physical_line",
                locator={
                    "line_index": line_index,
                    "leading_spaces": len(raw_line) - len(raw_line.lstrip()),
                },
            )
        )
        blank_count = 0
    return events


def _paragraph_events(text: str, *, structure_origin: str) -> list[SourceEvent]:
    """Convert blank-delimited text to paragraph or line events."""
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    events: list[SourceEvent] = []
    for paragraph_index, paragraph in enumerate(normalized.split("\n\n")):
        paragraph_text = paragraph.strip()
        if not paragraph_text:
            continue
        for line_index, line in enumerate(paragraph_text.split("\n")):
            clean_line = line.strip()
            if not clean_line:
                continue
            events.append(
                SourceEvent(
                    text=clean_line,
                    kind="unknown",
                    structure_origin=structure_origin,
                    boundary_before="\n\n" if line_index == 0 else "\n",
                    boundary_kind="paragraph" if line_index == 0 else "physical_line",
                    locator={"paragraph_index": paragraph_index, "line_index": line_index},
                )
            )
    return events


def _markdown_inline_text(token) -> str:
    """Return visible inline text without Markdown delimiters."""
    if not token.children:
        return str(token.content)
    parts: list[str] = []
    for child in token.children:
        if child.type in {"text", "code_inline"}:
            parts.append(str(child.content))
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append("\n")
        elif child.type == "image":
            parts.append(str(child.content))
    return "".join(parts)


def _read_text_with_fallback(path: Path) -> tuple[str, str]:
    """Read one text source and report the selected encoding."""
    source_bytes = path.read_bytes()
    return _decode_bytes_with_fallback(source_bytes)


def _decode_bytes_with_fallback(source_bytes: bytes) -> tuple[str, str]:
    """Decode text bytes by signature, strict UTF-8, or scored legacy evidence."""
    signature_encoding = _encoding_from_signature(source_bytes)
    if signature_encoding is not None:
        return source_bytes.decode(signature_encoding), _normalize_encoding_label(signature_encoding)

    try:
        return source_bytes.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass

    candidates: list[tuple[int, int, str, str]] = []
    for encoding in _LEGACY_TEXT_ENCODINGS:
        try:
            decoded = source_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
        candidates.append(
            (
                _legacy_text_score(decoded, encoding),
                _LEGACY_TIE_PRIORITY[encoding],
                decoded,
                encoding,
            )
        )
    if candidates:
        _score, _priority, decoded, encoding = max(candidates, key=lambda candidate: candidate[:2])
        return decoded, encoding

    return source_bytes.decode("latin-1"), "latin-1"


def _decode_epub_document_bytes(source_bytes: bytes, *, context: str) -> tuple[str, str]:
    """
    @brief      Decode one EPUB content document using signatures and declarations.
    @param[in]  source_bytes Raw content-document bytes.
    @param[in]  context Spine item identity used in actionable errors.
    @return     Decoded text and normalized encoding label.
    @exception  ValueError A declaration is unknown or strict decoding fails.
    """
    signature_encoding = _encoding_from_signature(source_bytes)
    if signature_encoding is not None:
        try:
            decoded = source_bytes.decode(signature_encoding)
        except UnicodeDecodeError as error:
            raise ValueError(f"{context} cannot be decoded as {signature_encoding}: {error}") from error
        declared_encoding = _xml_declared_encoding(decoded)
        if declared_encoding is not None:
            _resolve_encoding_label(declared_encoding, context=context)
        return decoded, _normalize_encoding_label(signature_encoding)

    header_text = source_bytes[:4096].decode("latin-1")
    declared_encoding = _xml_declared_encoding(header_text) or _html_declared_encoding(header_text)
    if declared_encoding is not None:
        return _decode_declared_bytes(source_bytes, declared_encoding, context=context)
    return _decode_bytes_with_fallback(source_bytes)


def _decode_declared_bytes(
    source_bytes: bytes,
    declared_encoding: str,
    *,
    context: str,
) -> tuple[str, str]:
    """
    @brief      Strictly decode bytes with one explicit standard-library codec.
    @param[in]  source_bytes Raw source bytes.
    @param[in]  declared_encoding Encoding name read from the source format.
    @param[in]  context Source identity used in actionable errors.
    @return     Decoded text and normalized encoding label.
    @exception  ValueError The codec is unknown or strict decoding fails.
    """
    encoding = _resolve_encoding_label(declared_encoding, context=context)
    try:
        return source_bytes.decode(encoding), encoding
    except UnicodeDecodeError as error:
        raise ValueError(f"{context} cannot be decoded as declared {encoding}: {error}") from error


def _resolve_encoding_label(declared_encoding: str, *, context: str) -> str:
    """Resolve one declared codec to its deterministic standard-library name."""
    try:
        return codecs.lookup(str(declared_encoding).strip()).name
    except LookupError as error:
        raise ValueError(f"{context} declares unsupported encoding '{declared_encoding}'.") from error


def _normalize_encoding_label(encoding: str) -> str:
    """Return the standard-library canonical name for one known codec."""
    return codecs.lookup(encoding).name


def _encoding_from_signature(source_bytes: bytes) -> str | None:
    """Return a BOM or XML byte-pattern encoding without inspecting text."""
    signatures = (
        (codecs.BOM_UTF32_BE, "utf-32"),
        (codecs.BOM_UTF32_LE, "utf-32"),
        (codecs.BOM_UTF8, "utf-8-sig"),
        (codecs.BOM_UTF16_BE, "utf-16"),
        (codecs.BOM_UTF16_LE, "utf-16"),
    )
    for signature, encoding in signatures:
        if source_bytes.startswith(signature):
            return encoding
    if source_bytes.startswith(b"\x00\x00\x00<"):
        return "utf-32-be"
    if source_bytes.startswith(b"<\x00\x00\x00"):
        return "utf-32-le"
    if source_bytes.startswith(b"\x00<\x00?"):
        return "utf-16-be"
    if source_bytes.startswith(b"<\x00?\x00"):
        return "utf-16-le"
    return None


def _xml_declared_encoding(header_text: str) -> str | None:
    """Return an XML declaration's encoding value when present."""
    match = _XML_ENCODING_PATTERN.search(header_text[:4096])
    return None if match is None else match.group(1)


def _html_declared_encoding(header_text: str) -> str | None:
    """Return an applicable HTML meta charset from the document header."""
    for match in _META_TAG_PATTERN.finditer(header_text[:4096]):
        tag = match.group(0)
        attributes = {
            attribute_match.group(1).casefold(): next(
                value for value in attribute_match.groups()[1:] if value is not None
            )
            for attribute_match in _META_ATTRIBUTE_PATTERN.finditer(tag)
        }
        if attributes.get("charset"):
            return attributes["charset"]
        if attributes.get("http-equiv", "").casefold() != "content-type":
            continue
        charset_match = _META_CHARSET_PATTERN.search(attributes.get("content", ""))
        if charset_match is not None:
            return charset_match.group(1)
    return None


def _legacy_text_score(text: str, encoding: str) -> int:
    """
    @brief      Score one legacy decode by script coherence and text quality.
    @param[in]  text Candidate Unicode text.
    @param[in]  encoding Windows code page used for the candidate.
    @return     Comparable deterministic evidence score.
    @exception  None
    """
    letters = [character for character in text if unicodedata.category(character).startswith("L")]
    latin_count = sum("LATIN" in unicodedata.name(character, "") for character in letters)
    cyrillic_count = sum("CYRILLIC" in unicodedata.name(character, "") for character in letters)
    control_count = sum(
        unicodedata.category(character).startswith("C") and character not in "\t\r\n"
        for character in text
    )
    symbol_count = sum(unicodedata.category(character).startswith("S") for character in text)
    non_ascii_latin_count = sum(
        ord(character) > 127 and "LATIN" in unicodedata.name(character, "")
        for character in letters
    )
    score = (
        (2 * max(latin_count, cyrillic_count))
        - (12 * min(latin_count, cyrillic_count))
        - (40 * control_count)
        - (4 * symbol_count)
    )
    if latin_count and non_ascii_latin_count / latin_count > 0.65:
        score -= 5 * non_ascii_latin_count
    if encoding == "cp1251":
        score += 6 * cyrillic_count
    elif encoding == "cp1250":
        score += 4 * sum(character in _CENTRAL_EUROPEAN_LETTERS for character in text)
    elif encoding == "cp1252":
        score += 4 * sum(character in _WESTERN_EUROPEAN_LETTERS for character in text)
        score += 3 * sum(character in _WESTERN_TYPOGRAPHY for character in text)
    return score


def _summarize_epub_encodings(encodings: list[str]) -> str | None:
    """Return a truthful uniform or deterministic mixed EPUB encoding token."""
    unique_encodings = sorted(set(encodings))
    if not unique_encodings:
        return None
    if len(unique_encodings) == 1:
        return unique_encodings[0]
    return f"mixed({','.join(unique_encodings)})"


def _walk_odf_nodes(root) -> Iterable[tuple[object, int]]:
    """Yield common ODT text/table nodes with their list nesting depth."""

    def walk(node, list_depth: int):
        local_name = _odf_local_name(node)
        next_depth = list_depth + 1 if local_name == "list" else list_depth
        if local_name in {"h", "p", "table-cell", "covered-table-cell"}:
            yield node, list_depth
            return
        for child in getattr(node, "childNodes", []):
            yield from walk(child, next_depth)

    yield from walk(root, 0)


def _odf_local_name(node) -> str:
    """Return one ODF node's local tag name."""
    qname = getattr(node, "qname", None)
    if isinstance(qname, tuple) and len(qname) == 2:
        return str(qname[1])
    return ""


def _odf_attribute(node, name: str) -> str | None:
    """Return one optional ODF attribute without depending on namespace prefixes."""
    for key, value in getattr(node, "attributes", {}).items():
        local_name = key[1] if isinstance(key, tuple) and len(key) == 2 else str(key)
        if str(local_name).casefold() == name.casefold():
            return str(value)
    return None


def _pdf_lines(
    page_dict: dict[str, object],
    page_index: int,
    page_width: float,
    page_height: float,
) -> list[dict[str, object]]:
    """Build visual-line records from a PyMuPDF dictionary."""
    lines: list[dict[str, object]] = []
    blocks = page_dict.get("blocks")
    if not isinstance(blocks, list):
        return lines
    for block_index, block in enumerate(blocks):
        if not isinstance(block, dict) or block.get("type") != 0:
            continue
        block_lines = block.get("lines")
        if not isinstance(block_lines, list):
            continue
        for line_index, line in enumerate(block_lines):
            if not isinstance(line, dict):
                continue
            spans = [span for span in line.get("spans", []) if isinstance(span, dict)]
            text = "".join(str(span.get("text") or "") for span in spans).strip()
            bbox = line.get("bbox")
            if not text or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            sizes = [float(span.get("size") or 0.0) for span in spans]
            weighted_size_total = sum(
                float(span.get("size") or 0.0) * max(1, len(str(span.get("text") or ""))) for span in spans
            )
            character_total = sum(max(1, len(str(span.get("text") or ""))) for span in spans)
            bold_characters = sum(
                max(1, len(str(span.get("text") or "")))
                for span in spans
                if int(span.get("flags") or 0) & 16
            )
            font_signature = "|".join(
                sorted(
                    {
                        f"{str(span.get('font') or '')}:{round(float(span.get('size') or 0.0), 1)}"
                        for span in spans
                    }
                )
            )
            direction = line.get("dir")
            if not isinstance(direction, (list, tuple)) or len(direction) != 2:
                direction = (1.0, 0.0)
            lines.append(
                {
                    "text": text,
                    "page_index": page_index,
                    "block_index": block_index,
                    "line_index": line_index,
                    "bbox": [float(value) for value in bbox],
                    "direction": [float(direction[0]), float(direction[1])],
                    "dominant_font_size": 0.0
                    if character_total == 0
                    else weighted_size_total / character_total,
                    "max_font_size": max(sizes, default=0.0),
                    "bold_fraction": 0.0 if character_total == 0 else bold_characters / character_total,
                    "font_signature": font_signature,
                    "relative_vertical_position": 0.0
                    if page_height <= 0
                    else max(0.0, min(1.0, float(bbox[1]) / page_height)),
                    "column": None,
                    "page_width": page_width,
                }
            )
    return lines


def _order_pdf_lines(
    lines: list[dict[str, object]],
    page_width: float,
) -> tuple[list[dict[str, object]], str, list[str]]:
    """Conservatively order a single-column or clearly separated two-column page."""
    if len(lines) < 6 or page_width <= 0:
        for line in lines:
            line["column"] = 0
        return sorted(lines, key=_pdf_line_sort_key), "single_column", []
    midpoint = page_width / 2.0
    margin = page_width * 0.04
    left: list[dict[str, object]] = []
    right: list[dict[str, object]] = []
    spanning: list[dict[str, object]] = []
    for line in lines:
        bbox = line["bbox"]
        satisfies_left = float(bbox[2]) <= midpoint + margin
        satisfies_right = float(bbox[0]) >= midpoint - margin
        if satisfies_left and not satisfies_right:
            left.append(line)
        elif satisfies_right and not satisfies_left:
            right.append(line)
        else:
            spanning.append(line)
    stable_two_column = (
        len(left) >= 3
        and len(right) >= 3
        and len(spanning) <= max(3, math.ceil(len(lines) * 0.2))
    )
    if not stable_two_column:
        for line in lines:
            line["column"] = 0
        return sorted(lines, key=_pdf_line_sort_key), "single_column", []

    first_column_y = min(float(line["bbox"][1]) for line in [*left, *right])
    last_column_y = max(float(line["bbox"][3]) for line in [*left, *right])
    top_spanning: list[dict[str, object]] = []
    bottom_spanning: list[dict[str, object]] = []
    ambiguous_spanning: list[dict[str, object]] = []
    for line in spanning:
        bbox = line["bbox"]
        satisfies_top = float(bbox[3]) <= first_column_y + 12.0
        satisfies_bottom = float(bbox[1]) >= last_column_y - 12.0
        if satisfies_top and not satisfies_bottom:
            top_spanning.append(line)
        elif satisfies_bottom and not satisfies_top:
            bottom_spanning.append(line)
        else:
            ambiguous_spanning.append(line)
    if ambiguous_spanning:
        for line in lines:
            line["column"] = None
        return list(lines), "uncertain_columns", ["multi_column_reading_order_uncertain"]

    for line in left:
        line["column"] = 0
    for line in right:
        line["column"] = 1
    ordered = [
        *sorted(top_spanning, key=_pdf_line_sort_key),
        *sorted(left, key=_pdf_line_sort_key),
        *sorted(right, key=_pdf_line_sort_key),
        *sorted(bottom_spanning, key=_pdf_line_sort_key),
    ]
    return ordered, "two_column", ["two_column_reading_order_reconstructed"]


def _pdf_line_sort_key(line: dict[str, object]) -> tuple[float, float, int, int]:
    """Return a stable top-left PDF line ordering key."""
    bbox = line["bbox"]
    return (
        round(float(bbox[1]), 2),
        round(float(bbox[0]), 2),
        int(line["block_index"]),
        int(line["line_index"]),
    )


def _pdf_image_area(page_dict: dict[str, object]) -> float:
    """Estimate total image-block area on a PDF page."""
    area = 0.0
    blocks = page_dict.get("blocks")
    if not isinstance(blocks, list):
        return area
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != 1:
            continue
        bbox = block.get("bbox")
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            area += max(0.0, float(bbox[2]) - float(bbox[0])) * max(
                0.0, float(bbox[3]) - float(bbox[1])
            )
    return area


def _heading_level(tag: str) -> int | None:
    """Return a numeric heading level for h1-h6 tags."""
    normalized = str(tag).casefold()
    if len(normalized) == 2 and normalized[0] == "h" and normalized[1].isdigit():
        return int(normalized[1])
    return None


def _emit_adapter_progress(callback, current: int, total: int, message: str) -> None:
    """Emit one adapter progress update when requested."""
    if callback is not None:
        callback(int(current), max(1, int(total)), str(message))


# END OF FILE
