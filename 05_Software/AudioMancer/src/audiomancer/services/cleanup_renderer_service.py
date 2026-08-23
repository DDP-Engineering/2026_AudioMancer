#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file cleanup_renderer_service.py
@brief Pure source-ledger renderer for typed Cleanup decisions.
@details Validates unit operations and every boundary, renders only source
         slices plus typed separators, and reports projection/fusion quality.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from audiomancer.services.cleanup_analysis_service import (
    BOUNDARY_CHOICES,
    UNIT_ROLES,
)
from audiomancer.services.source_ledger_service import (
    unit_text,
    validate_source_ledger,
)

ALLOWED_ACTIONS = frozenset(
    (
        "drop_page_artifact",
        "set_role",
        "join_with_space",
        "set_paragraph_break",
        "set_semantic_line_break",
        "dehyphenate",
        "join_preserving_hyphen",
        "document_end",
    )
)
_UNIT_ACTIONS = frozenset(("drop_page_artifact", "set_role"))
_CONFIDENCE_ORDER = {"strong": 2, "medium": 1, "low": 0}


class CleanupRenderError(ValueError):
    """Raised when a Cleanup decision could damage the source contract."""


def render_cleanup(
    canonical_text: str,
    ledger: dict[str, object],
    unit_operations: list[dict[str, object]],
    boundary_decisions: list[dict[str, object]],
) -> tuple[str, dict[str, object]]:
    """Render typed decisions and return clean text plus derived metadata."""
    validate_source_ledger(ledger, canonical_text)
    validate_operations(
        canonical_text,
        ledger,
        unit_operations,
        boundary_decisions,
    )
    units = {
        str(item["unit_id"]): dict(item)
        for item in ledger["units"]
    }
    boundaries = {
        str(item["boundary_id"]): dict(item)
        for item in ledger["boundaries"]
    }
    drops = {
        str(item["target_id"])
        for item in unit_operations
        if item["action"] == "drop_page_artifact"
    }
    roles = {
        str(item["target_id"]): str(item["role"])
        for item in unit_operations
        if item["action"] == "set_role"
    }
    decisions = {
        str(item["boundary_id"]): dict(item)
        for item in boundary_decisions
    }

    ordered: list[tuple[int, str, dict[str, object]]] = []
    ordered.extend((int(item["start"]), "unit", item) for item in units.values())
    ordered.extend(
        (int(item["start"]), "boundary", item)
        for item in boundaries.values()
    )
    ordered.sort(key=lambda item: item[0])
    parts: list[str] = []
    spans: list[dict[str, object]] = []
    rendered_boundaries: list[dict[str, object]] = []
    pending_boundaries: list[dict[str, object]] = []
    output_length = 0
    for _start, item_type, item in ordered:
        if item_type == "boundary":
            pending_boundaries.append(
                decisions[str(item["boundary_id"])]
            )
            continue

        unit_id = str(item["unit_id"])
        if unit_id in drops:
            continue
        if pending_boundaries:
            output_length, rendered = _render_boundary_group(
                parts,
                spans,
                pending_boundaries,
                output_length,
                at_document_start=not spans,
            )
            rendered_boundaries.extend(rendered)
            pending_boundaries = []
        text = unit_text(canonical_text, item)
        start = output_length
        parts.append(text)
        output_length += len(text)
        spans.append(
            {
                "unit_id": unit_id,
                "start": start,
                "end": output_length,
                "role": roles[unit_id],
                "source_start": int(item["start"]),
                "source_end": int(item["end"]),
                "source_page": _page_index(item),
            }
        )
    if pending_boundaries:
        output_length, rendered = _render_boundary_group(
            parts,
            spans,
            pending_boundaries,
            output_length,
            at_document_start=not spans,
        )
        rendered_boundaries.extend(rendered)

    cleaned_text = "".join(parts)
    if not cleaned_text.strip():
        raise CleanupRenderError("Cleanup cannot produce an empty document.")
    introduced_fusions = _introduced_fusion_count(
        cleaned_text,
        spans,
        rendered_boundaries,
    )
    if introduced_fusions:
        raise CleanupRenderError(
            "Cleanup would introduce alphanumeric source adjacency."
        )
    paragraphs = _paragraph_records(
        cleaned_text,
        spans,
        rendered_boundaries,
    )
    metadata = {
        "length_codepoints": len(cleaned_text),
        "spans": spans,
        "paragraphs": paragraphs,
        "quality_report": _quality_report(
            unit_operations,
            boundary_decisions,
            introduced_fusions,
        ),
    }
    return cleaned_text, metadata


def _render_boundary_group(
    parts: list[str],
    spans: list[dict[str, object]],
    decisions: list[dict[str, object]],
    output_length: int,
    *,
    at_document_start: bool,
) -> tuple[int, list[dict[str, object]]]:
    """Render one separator across direct or dropped-unit boundary chains."""
    choices = [
        str(item["final"]["choice"])
        for item in decisions
    ]
    dehyphenated_left_unit_id: str | None = None
    if at_document_start:
        separator = ""
    elif "document_end" in choices:
        separator = "\n"
    elif "set_paragraph_break" in choices:
        separator = "\n\n"
    elif "set_semantic_line_break" in choices:
        separator = "\n"
    elif "join_with_space" in choices:
        separator = " "
    else:
        separator = ""
        if "dehyphenate" in choices and parts and parts[-1].endswith(("-", "\u00ad")):
            parts[-1] = parts[-1][:-1]
            output_length -= 1
            if spans:
                spans[-1]["end"] = int(spans[-1]["end"]) - 1
                retained_left_unit_id = str(spans[-1]["unit_id"])
                if any(
                    str(item["final"]["choice"]) == "dehyphenate"
                    and str(item.get("left_unit_id")) == retained_left_unit_id
                    for item in decisions
                ):
                    dehyphenated_left_unit_id = retained_left_unit_id
    start = output_length
    if separator:
        parts.append(separator)
        output_length += len(separator)
    return (
        output_length,
        [
            {
                **decision,
                "output_start": start,
                "output_end": output_length,
                "dehyphenation_applied": (
                    dehyphenated_left_unit_id is not None
                    and str(decision["final"]["choice"]) == "dehyphenate"
                    and str(decision.get("left_unit_id"))
                    == dehyphenated_left_unit_id
                ),
            }
            for decision in decisions
        ],
    )


def validate_operations(
    canonical_text: str,
    ledger: dict[str, object],
    unit_operations: list[dict[str, object]],
    boundary_decisions: list[dict[str, object]],
) -> None:
    """Reject unknown, incomplete, duplicate, or structurally unsafe changes."""
    if not isinstance(unit_operations, list):
        raise CleanupRenderError("Cleanup unit operations must be a list.")
    if not isinstance(boundary_decisions, list):
        raise CleanupRenderError("Cleanup boundary decisions must be a list.")
    for decision in boundary_decisions:
        if not isinstance(decision, dict):
            raise CleanupRenderError(
                "Each Cleanup boundary decision must be an object."
            )
        final = decision.get("final")
        choice = (
            str(final.get("choice") or "")
            if isinstance(final, dict)
            else ""
        )
        if choice not in BOUNDARY_CHOICES:
            raise CleanupRenderError(f"Unsupported Cleanup action: {choice}")
    units = {
        str(item["unit_id"]): item
        for item in ledger["units"]
    }
    boundaries = {
        str(item["boundary_id"]): item
        for item in ledger["boundaries"]
    }
    seen_operations: set[tuple[str, str]] = set()
    dropped_by_page: Counter[int] = Counter()
    total_by_page: Counter[int] = Counter()
    roles_by_unit: dict[str, str] = {}
    for unit in units.values():
        page_index = _page_index(unit)
        if page_index is not None:
            total_by_page[page_index] += 1

    for operation in unit_operations:
        if not isinstance(operation, dict):
            raise CleanupRenderError("Each Cleanup unit operation must be an object.")
        action = str(operation.get("action") or "")
        target_id = str(operation.get("target_id") or "")
        if action not in _UNIT_ACTIONS:
            raise CleanupRenderError(f"Unsupported Cleanup action: {action}")
        if target_id not in units:
            raise CleanupRenderError(
                f"Cleanup action references unknown target: {target_id}"
            )
        operation_key = (action, target_id)
        if operation_key in seen_operations:
            raise CleanupRenderError(
                f"Duplicate Cleanup action {action} targets {target_id}."
            )
        seen_operations.add(operation_key)
        if action == "set_role":
            role = str(operation.get("role") or "")
            if role not in UNIT_ROLES:
                raise CleanupRenderError(f"Unsupported Cleanup role: {role}")
            roles_by_unit[target_id] = role
            continue
        source_slice = unit_text(canonical_text, units[target_id])
        if len(source_slice) > 160 or len(source_slice.splitlines()) > 3:
            raise CleanupRenderError(
                "Page-artifact removal exceeds the conservative size limit."
            )
        page_index = _page_index(units[target_id])
        if page_index is not None:
            dropped_by_page[page_index] += 1

    if set(roles_by_unit) != set(units):
        raise CleanupRenderError("Every source unit requires one resolved role.")
    for page_index, dropped_count in dropped_by_page.items():
        if total_by_page[page_index] and dropped_count >= total_by_page[page_index]:
            raise CleanupRenderError(
                "Cleanup may not remove every text unit on a page."
            )

    seen_boundaries: set[str] = set()
    for decision in boundary_decisions:
        final = decision.get("final")
        choice = (
            str(final.get("choice") or "")
            if isinstance(final, dict)
            else ""
        )
        boundary_id = str(decision.get("boundary_id") or "")
        if boundary_id not in boundaries:
            raise CleanupRenderError(
                f"Cleanup decision references unknown boundary: {boundary_id}"
            )
        if boundary_id in seen_boundaries:
            raise CleanupRenderError(
                f"Multiple Cleanup decisions target {boundary_id}."
            )
        seen_boundaries.add(boundary_id)
        source_boundary = boundaries[boundary_id]
        if decision.get("left_unit_id") != source_boundary.get("left_unit_id"):
            raise CleanupRenderError("Cleanup boundary left unit does not match ledger.")
        if decision.get("right_unit_id") != source_boundary.get("right_unit_id"):
            raise CleanupRenderError("Cleanup boundary right unit does not match ledger.")
        right_id = source_boundary.get("right_unit_id")
        if choice == "document_end" and right_id is not None:
            raise CleanupRenderError("document_end may only target the terminal boundary.")
        if choice != "document_end" and right_id is None:
            raise CleanupRenderError("The terminal boundary requires document_end.")
        if choice in {"dehyphenate", "join_preserving_hyphen"}:
            left_id = str(source_boundary.get("left_unit_id"))
            left_text = unit_text(canonical_text, units[left_id])
            if not left_text.endswith(("-", "\u00ad")):
                raise CleanupRenderError(
                    f"{choice} requires a source hyphen at the boundary."
                )
    if seen_boundaries != set(boundaries):
        raise CleanupRenderError("Every source boundary requires one typed decision.")


def _introduced_fusion_count(
    cleaned_text: str,
    spans: list[dict[str, object]],
    rendered_boundaries: list[dict[str, object]],
) -> int:
    """Count unsafe alphanumeric joins across separate rendered source spans."""
    count = 0
    nonempty_spans = [
        item
        for item in spans
        if int(item["end"]) > int(item["start"])
    ]
    for left_span, right_span in zip(
        nonempty_spans,
        nonempty_spans[1:],
        strict=False,
    ):
        join_offset = int(left_span["end"])
        if join_offset != int(right_span["start"]):
            continue
        if join_offset <= 0 or join_offset >= len(cleaned_text):
            continue
        if not (
            cleaned_text[join_offset - 1].isalnum()
            and cleaned_text[join_offset].isalnum()
        ):
            continue
        if any(
            item.get("dehyphenation_applied") is True
            and str(item["final"]["choice"]) == "dehyphenate"
            and str(item.get("left_unit_id")) == str(left_span["unit_id"])
            and int(item["output_start"]) == join_offset
            and int(item["output_end"]) == join_offset
            for item in rendered_boundaries
        ):
            continue
        count += 1
    return count


def _paragraph_records(
    cleaned_text: str,
    spans: list[dict[str, object]],
    boundaries: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Build non-duplicating paragraph offsets and source provenance."""
    limit = len(cleaned_text.rstrip("\n"))
    records: list[dict[str, object]] = []
    cursor = 0
    while cursor < limit:
        separator_start = cleaned_text.find("\n\n", cursor, limit)
        raw_end = limit if separator_start < 0 else separator_start
        start = cursor
        end = raw_end
        while start < end and cleaned_text[start] in "\r\n":
            start += 1
        while end > start and cleaned_text[end - 1] in "\r\n":
            end -= 1
        if start < end and cleaned_text[start:end].strip():
            records.append(
                _paragraph_record(
                    len(records) + 1,
                    start,
                    end,
                    spans,
                    boundaries,
                )
            )
        if separator_start < 0:
            break
        cursor = separator_start + 2
        while cursor < limit and cleaned_text[cursor] == "\n":
            cursor += 1
    return records


def _paragraph_record(
    index: int,
    start: int,
    end: int,
    spans: list[dict[str, object]],
    boundaries: list[dict[str, object]],
) -> dict[str, object]:
    """Build one paragraph metadata record from rendered source spans."""
    paragraph_spans = [
        item
        for item in spans
        if int(item["end"]) > start and int(item["start"]) < end
    ]
    source_unit_ids = [str(item["unit_id"]) for item in paragraph_spans]
    roles = [str(item["role"]) for item in paragraph_spans]
    role = next((item for item in roles if item != "body"), roles[0] if roles else "body")
    page_values = [
        int(item["source_page"]) + 1
        for item in paragraph_spans
        if isinstance(item.get("source_page"), int)
    ]
    relevant_boundaries = [
        item
        for item in boundaries
        if start <= int(item["output_start"]) <= end
    ]
    confidences = [
        str(item["final"]["confidence"])
        for item in relevant_boundaries
    ]
    confidence = min(
        confidences or ["strong"],
        key=lambda item: _CONFIDENCE_ORDER.get(item, 0),
    )
    reason_codes = sorted(
        {
            str(code)
            for item in relevant_boundaries
            for code in item["final"]["reason_codes"]
        }
    )
    preceding = [
        item
        for item in boundaries
        if int(item["output_end"]) <= start
    ]
    starts_after_page = bool(preceding and preceding[-1]["page_transition"])
    crosses_page = any(
        bool(item["page_transition"])
        and item["final"]["choice"] != "set_paragraph_break"
        for item in relevant_boundaries
    )
    return {
        "paragraph_id": f"paragraph-{index:06d}",
        "output_start": start,
        "output_end": end,
        "role": role,
        "confidence": confidence,
        "reason_codes": reason_codes,
        "source_page_start": min(page_values) if page_values else None,
        "source_page_end": max(page_values) if page_values else None,
        "starts_after_page_transition": starts_after_page,
        "crosses_page_transition": crosses_page,
        "source_unit_ids": source_unit_ids,
        "provenance_available": True,
    }


def _quality_report(
    unit_operations: list[dict[str, object]],
    boundaries: list[dict[str, object]],
    introduced_fusions: int,
) -> dict[str, object]:
    """Build runtime-computable Cleanup quality counters."""
    origin_counts = Counter(
        str(item["final"]["origin"])
        for item in boundaries
    )
    override_count = sum(
        bool(item["adjudication"]["accepted"])
        for item in boundaries
    )
    adjudicated_count = sum(
        item["adjudication"]["state"] == "completed"
        for item in boundaries
    )
    return {
        "introduced_fusion_count": introduced_fusions,
        "projection_violation_count": 0,
        "invalid_operation_count": 0,
        "unclassified_boundary_count": 0,
        "low_confidence_count": sum(
            item["final"]["confidence"] == "low"
            for item in boundaries
        ),
        "page_transition_count": sum(
            bool(item["page_transition"])
            for item in boundaries
        ),
        "artifact_removal_count": sum(
            item["action"] == "drop_page_artifact"
            for item in unit_operations
        ),
        "deterministic_count": origin_counts["deterministic"] + origin_counts["native"],
        "llm_count": origin_counts["llm"],
        "fallback_count": origin_counts["fallback"],
        "override_count": override_count,
        "override_rate": (
            override_count / adjudicated_count
            if adjudicated_count
            else 0.0
        ),
        "failed_batch_count": 0,
        "online_fragment_count": 0,
        "online_backend": None,
    }


def _page_index(unit: dict[str, Any]) -> int | None:
    """Return one optional source page index."""
    locator = unit.get("locator")
    if not isinstance(locator, dict) or not isinstance(locator.get("page_index"), int):
        return None
    return int(locator["page_index"])


# END OF FILE
