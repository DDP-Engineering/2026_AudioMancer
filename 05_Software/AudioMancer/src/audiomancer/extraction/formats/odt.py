#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file odt.py
@brief ODT structural extraction.
@details Part of the isolated extraction engine; no project or Qt dependencies.
"""

# IMPORTS

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from odf import teletype
from odf.opendocument import load as load_odf_document

from ..models import ExtractionAdapterResult, SourceEvent, _emit_adapter_progress
from ..models import check_cancelled as raise_if_cancelled

# PUBLIC API


def _extract_odt(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """@brief Extract common ODT structural elements in document order."""
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


def _walk_odf_nodes(root) -> Iterable[tuple[object, int]]:
    """@brief Yield common ODT text/table nodes with their list nesting depth."""

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
    """@brief Return one ODF node's local tag name."""
    qname = getattr(node, "qname", None)
    if isinstance(qname, tuple) and len(qname) == 2:
        return str(qname[1])
    return ""


def _odf_attribute(node, name: str) -> str | None:
    """@brief Return one optional ODF attribute without depending on namespace prefixes."""
    for key, value in getattr(node, "attributes", {}).items():
        local_name = key[1] if isinstance(key, tuple) and len(key) == 2 else str(key)
        if str(local_name).casefold() == name.casefold():
            return str(value)
    return None


# END OF FILE
