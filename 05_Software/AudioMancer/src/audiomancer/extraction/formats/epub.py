#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file epub.py
@brief EPUB structural extraction.
@details Part of the isolated extraction engine; no project or Qt dependencies.
"""

# IMPORTS

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import ebooklib
from ebooklib import epub

from ..encoding import _decode_markup_bytes, _summarize_epub_encodings
from ..models import ExtractionAdapterResult, SourceEvent, _emit_adapter_progress
from ..models import check_cancelled as raise_if_cancelled
from .html_content import _StructuredHtmlExtractor

# PUBLIC API


def _extract_epub(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """@brief Extract visible XHTML blocks in EPUB spine order."""
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
            raise ValueError(f"EPUB spine item {item_id!r} is missing or is not a content document.")
        properties = {str(value).casefold() for value in getattr(item, "properties", [])}
        if "nav" in properties or str(item_id).casefold() == "nav":
            _emit_adapter_progress(progress_callback, spine_index + 1, total, "EPUB navigation skipped.")
            continue
        item_name = str(getattr(item, "file_name", "") or getattr(item, "get_name", lambda: "")())
        item_context = f"EPUB spine item '{item_id}' ({item_name or 'unnamed content document'})"
        raw_content = getattr(item, "content", None)
        content_bytes = bytes(raw_content) if isinstance(raw_content, bytes | bytearray) else item.get_content()
        decoded_content, content_encoding = _decode_markup_bytes(
            content_bytes,
            context=item_context,
        )
        parser = _StructuredHtmlExtractor(spine_index=spine_index, item_id=str(item_id))
        parser.feed(decoded_content)
        parser.close()
        linear = not (
            isinstance(spine_entry, (tuple, list)) and len(spine_entry) > 1 and str(spine_entry[1]).casefold() == "no"
        )
        events.extend(replace(event, native={**event.native, "linear": linear}) for event in parser.events)
        if not linear:
            warnings.append(
                f"EPUB auxiliary item {item_id!r} was retained in spine order; review its narration placement."
            )
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


# END OF FILE
