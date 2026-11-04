#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file __init__.py
@brief Public document extraction API.
@details Part of the isolated extraction engine; no project or Qt dependencies.
"""

# IMPORTS

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .document import CanonicalDocumentBuilder, file_sha256
from .models import ExtractedDocument, check_cancelled

# CONSTANTS

# @brief Canonical source types shared by standalone extraction, project import and file pickers.
SUPPORTED_SOURCE_SUFFIXES = {
    ".txt": "txt",
    ".pdf": "pdf",
    ".rtf": "rtf",
    ".docx": "docx",
    ".odt": "odt",
    ".md": "md",
    ".epub": "epub",
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".fb2": "fb2",
}

# PUBLIC API


def extract_document(
    source_path: str | Path,
    *,
    file_type: str | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> ExtractedDocument:
    """
    @brief Extract and validate a document without project state or output writes.
    @param[in] source_path Source document read by the selected format adapter.
    @param[in] file_type Optional format token; defaults to the file extension.
    @param[in] on_progress Callback accepting current, total and a phase message.
    @param[in] is_cancelled Cooperative cancellation predicate.
    @return Canonical text and a matching, validated provenance ledger.
    @exception ValueError The source format or content is unusable.
    @exception ExtractionCancelledError The caller cancelled extraction.
    """
    from .formats import extract_source_events

    path = Path(source_path)
    kind = file_type or SUPPORTED_SOURCE_SUFFIXES.get(path.suffix.lower(), path.suffix.lower().lstrip("."))
    check_cancelled(is_cancelled)
    source_hash = file_sha256(path)

    last_parsing_percent = -1

    def parsing_progress(current, total, message):
        """@brief Reserve the final progress range for canonical construction and publication."""
        nonlocal last_parsing_percent
        percent = min(85, int(85 * current / max(1, total)))
        if on_progress is not None and percent != last_parsing_percent:
            last_parsing_percent = percent
            on_progress(percent, 100, message)

    result = extract_source_events(path, kind, progress_callback=parsing_progress, cancel_requested=is_cancelled)
    check_cancelled(is_cancelled)
    if on_progress is not None:
        on_progress(85, 100, "Building canonical text and provenance...")
    builder = CanonicalDocumentBuilder(
        source_format=kind,
        source_sha256=source_hash,
        encoding=result.encoding,
        structure_quality=result.structure_quality,
        eligibility_mode=result.eligibility_mode,
        eligibility_reason_codes=result.eligibility_reason_codes,
        pages=result.pages,
        warnings=result.warnings,
    )
    for event in result.events:
        check_cancelled(is_cancelled)
        builder.add(event)
    canonical, ledger = builder.build()
    check_cancelled(is_cancelled)
    if on_progress is not None:
        on_progress(95, 100, "Canonical text and provenance validated.")
    return ExtractedDocument(canonical, ledger, result.page_count)


# END OF FILE
