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
@author Eng. Dan Dumitru Pasare
@date 2026-07-27
@version 0.1.0
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
import math
from pathlib import Path

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
_TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp1250", "cp1252", "latin-1")
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
    decoded, encoding = _decode_bytes_with_fallback(source_bytes)
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
        parser = _StructuredHtmlExtractor(spine_index=spine_index, item_id=str(item_id))
        parser.feed(item.get_content().decode("utf-8", errors="strict"))
        parser.close()
        events.extend(parser.events)
        warnings.extend(parser.warnings)
        _emit_adapter_progress(progress_callback, spine_index + 1, total, "EPUB spine parsed.")

    return ExtractionAdapterResult(
        events=events,
        warnings=warnings,
        pages=[],
        structure_quality="native",
        eligibility_mode="native",
        eligibility_reason_codes=[],
        encoding="utf-8",
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
    """Decode text bytes with the application's supported fallback order."""
    for encoding in _TEXT_ENCODINGS:
        try:
            return source_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("text", source_bytes, 0, 1, "Unable to decode text source.")


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
        return sorted(lines, key=_pdf_line_sort_key), "single_column", []
    midpoint = page_width / 2.0
    margin = page_width * 0.04
    left = [line for line in lines if float(line["bbox"][2]) <= midpoint + margin]
    right = [line for line in lines if float(line["bbox"][0]) >= midpoint - margin]
    spanning = [line for line in lines if line not in left and line not in right]
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
    top_spanning = [line for line in spanning if float(line["bbox"][3]) <= first_column_y + 12.0]
    bottom_spanning = [line for line in spanning if float(line["bbox"][1]) >= last_column_y - 12.0]
    ambiguous_spanning = [line for line in spanning if line not in top_spanning and line not in bottom_spanning]
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
