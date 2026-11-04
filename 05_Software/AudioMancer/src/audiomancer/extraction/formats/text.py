#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file text.py
@brief TEXT structural extraction.
@details Part of the isolated extraction engine; no project or Qt dependencies.
"""

# IMPORTS

from __future__ import annotations

from pathlib import Path
import re

from striprtf.striprtf import rtf_to_text

from ..encoding import _decode_bytes_with_fallback, _decode_declared_bytes, _read_text_with_fallback
from ..models import ExtractionAdapterResult, SourceEvent, _emit_adapter_progress
from ..models import check_cancelled as raise_if_cancelled

_RTF_CODE_PAGE_PATTERN = re.compile(rb"\\ansicpg(\d{3,5})\b", re.IGNORECASE)

# PUBLIC API


def _extract_txt(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """@brief Extract physical text lines while preserving blank-line boundaries."""
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


def _extract_rtf(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """@brief Extract RTF text while declaring unavailable style structure."""
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


def _line_events(text: str, *, structure_origin: str) -> list[SourceEvent]:
    """@brief Convert physical lines to events while retaining blank-line strength."""
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
    """@brief Convert blank-delimited text to paragraph or line events."""
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


# END OF FILE
