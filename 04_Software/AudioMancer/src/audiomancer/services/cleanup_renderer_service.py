#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
"""
@file cleanup_renderer_service.py
@brief Pure source-ledger renderer and validators for Cleanup V2.
@details Applies only typed, source-referenced operations. No operation can
         introduce replacement story text.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from audiomancer.services.source_ledger_service import unit_text, validate_source_ledger

ALLOWED_ACTIONS = frozenset(
    (
        "drop_page_artifact",
        "join_with_space",
        "join_without_space",
        "set_paragraph_break",
        "preserve_line_break",
        "dehyphenate",
        "set_role",
    )
)
_BOUNDARY_ACTIONS = ALLOWED_ACTIONS - {"drop_page_artifact", "set_role"}


class CleanupRenderError(ValueError):
    """Raised when a Cleanup operation could damage the source contract."""


def render_cleanup(
    canonical_text: str,
    ledger: dict[str, object],
    operations: list[dict[str, object]],
) -> tuple[str, dict[str, object]]:
    """Apply validated operations and return cleaned text plus derived spans."""
    validate_source_ledger(ledger, canonical_text)
    validate_operations(canonical_text, ledger, operations)
    units = {str(item["unit_id"]): item for item in ledger["units"]}
    boundaries = {str(item["boundary_id"]): item for item in ledger["boundaries"]}
    drops = {
        str(item["target_id"])
        for item in operations
        if item["action"] == "drop_page_artifact"
    }
    boundary_actions = {
        str(item["target_id"]): str(item["action"])
        for item in operations
        if item["action"] in _BOUNDARY_ACTIONS
    }
    role_actions = {
        str(item["target_id"]): str(item.get("role") or "unknown")
        for item in operations
        if item["action"] == "set_role"
    }

    ordered: list[tuple[int, str, dict[str, object]]] = []
    ordered.extend((int(item["start"]), "unit", item) for item in units.values())
    ordered.extend((int(item["start"]), "boundary", item) for item in boundaries.values())
    ordered.sort(key=lambda item: item[0])
    parts: list[str] = []
    spans: list[dict[str, object]] = []
    output_length = 0
    for _start, item_type, item in ordered:
        if item_type == "unit":
            unit_id = str(item["unit_id"])
            if unit_id in drops:
                continue
            text = unit_text(canonical_text, item)
            start = output_length
            parts.append(text)
            output_length += len(text)
            spans.append(
                {
                    "unit_id": unit_id,
                    "start": start,
                    "end": output_length,
                    "role": role_actions.get(unit_id, str(item.get("kind") or "unknown")),
                    "source_start": int(item["start"]),
                    "source_end": int(item["end"]),
                }
            )
            continue

        boundary_id = str(item["boundary_id"])
        left_id = item.get("left_unit_id")
        right_id = item.get("right_unit_id")
        if (left_id in drops) or (right_id in drops):
            text = ""
        else:
            action = boundary_actions.get(boundary_id)
            if action == "join_with_space":
                text = " "
            elif action in {"join_without_space", "dehyphenate"}:
                text = ""
                if action == "dehyphenate" and parts and parts[-1].endswith(("-", "\u00ad")):
                    parts[-1] = parts[-1][:-1]
                    output_length -= 1
                    if spans:
                        spans[-1]["end"] = int(spans[-1]["end"]) - 1
            elif action == "set_paragraph_break":
                text = "\n\n"
            elif action == "preserve_line_break":
                text = "\n"
            else:
                text = canonical_text[int(item["start"]) : int(item["end"])]
        parts.append(text)
        output_length += len(text)

    cleaned_text = "".join(parts)
    if not cleaned_text.strip():
        raise CleanupRenderError("Cleanup cannot produce an empty document.")
    metadata = {
        "schema_version": 1,
        "length_codepoints": len(cleaned_text),
        "spans": spans,
    }
    return cleaned_text, metadata


def validate_operations(
    canonical_text: str,
    ledger: dict[str, object],
    operations: list[dict[str, object]],
) -> None:
    """Reject unknown, duplicate, oversized, or structurally unsafe changes."""
    if not isinstance(operations, list):
        raise CleanupRenderError("Cleanup operations must be a list.")
    units = {str(item["unit_id"]): item for item in ledger["units"]}
    boundaries = {str(item["boundary_id"]): item for item in ledger["boundaries"]}
    seen_targets: set[tuple[str, str]] = set()
    dropped_by_page: Counter[int] = Counter()
    total_by_page: Counter[int] = Counter()
    for unit in units.values():
        page_index = _page_index(unit)
        if page_index is not None:
            total_by_page[page_index] += 1

    for operation in operations:
        if not isinstance(operation, dict):
            raise CleanupRenderError("Each Cleanup operation must be an object.")
        action = str(operation.get("action") or "")
        target_id = str(operation.get("target_id") or "")
        if action not in ALLOWED_ACTIONS:
            raise CleanupRenderError(f"Unsupported Cleanup action: {action}")
        expected_targets = units if action in {"drop_page_artifact", "set_role"} else boundaries
        if target_id not in expected_targets:
            raise CleanupRenderError(f"Cleanup action references unknown target: {target_id}")
        target_key = ("unit" if expected_targets is units else "boundary", target_id)
        if target_key in seen_targets:
            raise CleanupRenderError(f"Multiple Cleanup actions target {target_id}.")
        seen_targets.add(target_key)
        if action != "drop_page_artifact":
            continue
        unit = units[target_id]
        source_slice = unit_text(canonical_text, unit)
        if len(source_slice) > 160 or len(source_slice.splitlines()) > 3:
            raise CleanupRenderError("Page-artifact removal exceeds the conservative size limit.")
        page_index = _page_index(unit)
        if page_index is not None:
            dropped_by_page[page_index] += 1

    for page_index, dropped_count in dropped_by_page.items():
        if total_by_page[page_index] and dropped_count >= total_by_page[page_index]:
            raise CleanupRenderError("Cleanup may not remove every text unit on a page.")


def _page_index(unit: dict[str, Any]) -> int | None:
    """Return one optional source page index."""
    locator = unit.get("locator")
    if not isinstance(locator, dict) or not isinstance(locator.get("page_index"), int):
        return None
    return int(locator["page_index"])
