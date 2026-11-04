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
@brief Explicit dispatch for the supported source formats.
@details Part of the isolated extraction engine; no project or Qt dependencies.
"""

# IMPORTS

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..models import ExtractionAdapterResult
from . import docx, epub, fb2, html, markdown, odt, pdf, text

# PUBLIC API


def extract_source_events(
    source_path: Path,
    file_type: str,
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    cancel_requested=None,
) -> ExtractionAdapterResult:
    """@brief Dispatch one source file to its structural adapter."""
    adapters = {
        "txt": text._extract_txt,
        "md": markdown._extract_markdown,
        "rtf": text._extract_rtf,
        "docx": docx._extract_docx,
        "odt": odt._extract_odt,
        "epub": epub._extract_epub,
        "pdf": pdf._extract_pdf,
        "html": html._extract_html,
        "fb2": fb2._extract_fb2,
    }
    adapter = adapters.get(str(file_type))
    if adapter is None:
        raise ValueError(f"Unsupported source type for extraction: {file_type}")
    return adapter(
        Path(source_path),
        progress_callback=progress_callback,
        cancel_requested=cancel_requested,
    )


# END OF FILE
