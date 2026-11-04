#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file html.py
@brief Extract local HTML and XHTML book content.
@details Reuses the structural content parser; external resources and scripts are never loaded.
"""

# IMPORTS

from dataclasses import replace
from pathlib import Path

from ..encoding import _decode_markup_bytes
from ..models import ExtractionAdapterResult, _emit_adapter_progress, check_cancelled
from .html_content import _StructuredHtmlExtractor

# PUBLIC API


def _extract_html(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """
    @brief Read a local HTML document into visible structural text units.
    @param[in] source_path Local HTML, HTM or XHTML source file.
    @param[in] progress_callback Optional current/total/message observer.
    @param[in] cancel_requested Cooperative cancellation predicate.
    @return Text units in document order and encoding/layout diagnostics.
    @exception ValueError The declared encoding cannot decode the source.
    """
    check_cancelled(cancel_requested)
    content, encoding = _decode_markup_bytes(source_path.read_bytes(), context=f"HTML source '{source_path.name}'")
    parser = _StructuredHtmlExtractor(spine_index=0, item_id=source_path.name)
    size = 65536
    total = max(1, (len(content) + size - 1) // size)
    for index in range(total):
        check_cancelled(cancel_requested)
        parser.feed(content[index * size : (index + 1) * size])
        _emit_adapter_progress(progress_callback, index + 1, total, "HTML content parsed.")
    parser.close()
    events = [replace(event, locator={"block_index": event.locator["block_index"]}) for event in parser.events]
    warnings = []
    if parser.has_unrendered_content:
        warnings.append("HTML stylesheets and scripts are not evaluated; review content that depends on rendering.")
    return ExtractionAdapterResult(
        events=events,
        warnings=warnings,
        pages=[],
        structure_quality="native_partial",
        eligibility_mode="native_partial",
        eligibility_reason_codes=["html_rendering_not_evaluated"],
        encoding=encoding,
        progress_total=total,
        page_count=None,
    )


# END OF FILE
