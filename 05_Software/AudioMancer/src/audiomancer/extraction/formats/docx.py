#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file docx.py
@brief DOCX structural extraction.
@details Part of the isolated extraction engine; no project or Qt dependencies.
"""

# IMPORTS

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from ..models import ExtractionAdapterResult, SourceEvent, _emit_adapter_progress
from ..models import check_cancelled as raise_if_cancelled

# PUBLIC API


def _extract_docx(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """@brief Extract DOCX paragraphs and tables in body order."""
    document = Document(source_path)
    events: list[SourceEvent] = []
    warnings: list[str] = []
    body_children = list(document.element.body.iterchildren())
    total = max(1, len(body_children))
    parent = document._body  # noqa: SLF001 - python-docx requires the owning body proxy.

    seen_cells = set()
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
                cells = []
                for cell in row.cells:
                    if cell._tc not in seen_cells:  # noqa: SLF001 - merged positions share one XML cell.
                        seen_cells.add(cell._tc)  # noqa: SLF001
                        cells.append(cell.text.strip())
                row_text = "\t".join(cells).strip()
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

    if document.element.xpath(".//w:txbxContent") or any(
        "footnotes" in relationship.reltype or "endnotes" in relationship.reltype
        for relationship in document.part.rels.values()
    ):
        warnings.append("DOCX contains embedded text objects or notes that are not extracted; review the source.")
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


# END OF FILE
