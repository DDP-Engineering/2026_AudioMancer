#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file pdf.py
@brief PDF structural extraction.
@details Part of the isolated extraction engine; no project or Qt dependencies.
"""

# IMPORTS

from __future__ import annotations

import math
from pathlib import Path

import fitz

from ..models import ExtractionAdapterResult, SourceEvent, _emit_adapter_progress
from ..models import check_cancelled as raise_if_cancelled

_PAGE_BREAK_SEPARATOR = "\n\n\f\n\n"

# PUBLIC API


def _extract_pdf(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """@brief Extract PDF visual lines and geometry from one TextPage representation."""
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
            page_dict = page.get_text("dict", sort=False, flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
            page_width = float(page.rect.width)
            page_height = float(page.rect.height)
            raw_lines = _pdf_lines(page_dict, page_index, page_width, page_height)
            ordered_lines, layout_mode, page_reasons = _order_pdf_lines(raw_lines, page_width)
            reason_codes.update(page_reasons)
            if layout_mode != "single_column":
                any_partial = True
            image_area = _pdf_image_area(page.get_image_info())
            if not ordered_lines and image_area == 0:
                warnings.append(f"PDF page {page_index + 1} did not contain extractable text.")
            elif ordered_lines:
                any_text = True
            if not ordered_lines and image_area > 0:
                any_partial = True
                page_reasons.append("image_only_page_requires_review")
                reason_codes.add("image_only_page_requires_review")
                warnings.append(
                    f"PDF page {page_index + 1} contains only images; review whether OCR is needed for missing text."
                )
            if page_reasons:
                warnings.extend(
                    f"PDF page {page_index + 1}: {reason}."
                    for reason in page_reasons
                    if reason != "image_only_page_requires_review"
                )
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
                boundary_before = _PAGE_BREAK_SEPARATOR if events and line_position == 0 else ("\n" if events else None)
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


def _pdf_lines(
    page_dict: dict[str, object],
    page_index: int,
    page_width: float,
    page_height: float,
) -> list[dict[str, object]]:
    """@brief Build visual-line records from a PyMuPDF dictionary."""
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
                max(1, len(str(span.get("text") or ""))) for span in spans if int(span.get("flags") or 0) & 16
            )
            font_signature = "|".join(
                sorted({f"{str(span.get('font') or '')}:{round(float(span.get('size') or 0.0), 1)}" for span in spans})
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
                    "dominant_font_size": 0.0 if character_total == 0 else weighted_size_total / character_total,
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
    """@brief Conservatively order a single-column or clearly separated two-column page."""
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
    stable_two_column = len(left) >= 3 and len(right) >= 3 and len(spanning) <= max(3, math.ceil(len(lines) * 0.2))
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
    """@brief Return a stable top-left PDF line ordering key."""
    bbox = line["bbox"]
    return (
        round(float(bbox[1]), 2),
        round(float(bbox[0]), 2),
        int(line["block_index"]),
        int(line["line_index"]),
    )


def _pdf_image_area(images: list[dict[str, object]]) -> float:
    """@brief Estimate image coverage from display metadata without decoding image pixels."""
    area = 0.0
    for image in images:
        bbox = image.get("bbox")
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            area += max(0.0, float(bbox[2]) - float(bbox[0])) * max(0.0, float(bbox[3]) - float(bbox[1]))
    return area


# END OF FILE
