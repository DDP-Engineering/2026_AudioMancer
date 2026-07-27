#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
"""
@file cleanup_analysis_service.py
@brief Conservative deterministic evidence pass for Cleanup V2.
@details Produces verified operations where structural evidence is strong and
         typed residual questions everywhere else. Uncertainty preserves text.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import re
import statistics

from audiomancer.services import cleanup_text_analysis_service
from audiomancer.services.source_ledger_service import unit_text

_PAGE_NUMBER = re.compile(r"^(?:page\s+)?(\d{1,5})(?:\s*(?:/|of)\s*\d+)?[.]?$", re.IGNORECASE)
_PROTECTED_KINDS = frozenset(("heading", "list_or_dialogue", "blockquote", "table_or_preformatted"))


def analyze_cleanup(
    canonical_text: str,
    ledger: dict[str, object],
) -> dict[str, object]:
    """Return document profile, conservative operations, and residual questions."""
    units = list(ledger["units"])
    boundaries = list(ledger["boundaries"])
    operations: list[dict[str, object]] = []
    questions: list[dict[str, object]] = []
    warnings = [str(item) for item in ledger.get("warnings", [])]
    role_counts: Counter[str] = Counter()
    for unit in units:
        kind = str(unit.get("kind") or "unknown")
        role_counts[kind] += 1

    page_artifacts, artifact_questions = _page_artifact_evidence(canonical_text, units)
    operations.extend(page_artifacts)
    questions.extend(artifact_questions)
    dropped_ids = {str(item["target_id"]) for item in page_artifacts}

    unit_by_id = {str(item["unit_id"]): item for item in units}
    body_widths = [
        len(unit_text(canonical_text, item).strip())
        for item in units
        if str(item.get("kind") or "unknown") not in _PROTECTED_KINDS
        and len(unit_text(canonical_text, item).strip()) >= 20
    ]
    median_width = statistics.median(body_widths) if body_widths else 0
    for boundary in boundaries:
        left_id = boundary.get("left_unit_id")
        right_id = boundary.get("right_unit_id")
        if left_id not in unit_by_id or right_id not in unit_by_id:
            continue
        if left_id in dropped_ids or right_id in dropped_ids:
            continue
        left = unit_by_id[str(left_id)]
        right = unit_by_id[str(right_id)]
        left_text = unit_text(canonical_text, left)
        right_text = unit_text(canonical_text, right)
        boundary_id = str(boundary["boundary_id"])
        kind = str(boundary.get("kind") or "")
        if "\u00ad" in left_text[-1:]:
            operations.append(_operation("dehyphenate", boundary_id, "soft_hyphen"))
            continue
        if kind in {"native_paragraph", "blank_paragraph", "paragraph", "page", "document_end"}:
            continue
        if _protected(left) or _protected(right):
            continue
        if left_text.endswith("-"):
            questions.append(
                _question(
                    "hyphenation",
                    boundary_id,
                    left_text,
                    right_text,
                    ["preserve", "dehyphenate"],
                )
            )
            continue
        if _high_confidence_line_join(left, right, left_text, right_text, median_width):
            action = "join_without_space" if _no_space_script_boundary(left_text, right_text) else "join_with_space"
            operations.append(_operation(action, boundary_id, "layout_line_continuation"))
        elif kind in {"visual_line", "physical_line"}:
            questions.append(
                _question(
                    "line_boundary",
                    boundary_id,
                    left_text,
                    right_text,
                    ["preserve", "join_with_space", "join_without_space", "paragraph_break"],
                )
            )

    profile = {
        "source_format": str(ledger["source"]["format"]),
        "structure_quality": str(ledger["structure_quality"]),
        "unit_count": len(units),
        "page_count": len(ledger.get("pages", [])),
        "role_counts": dict(sorted(role_counts.items())),
        "language": cleanup_text_analysis_service.detect_language(canonical_text),
    }
    return {
        "document_profile": profile,
        "operations": operations,
        "questions": questions,
        "warnings": warnings,
    }


def operation_from_answer(question: dict[str, object], choice: str, *, verifier: bool) -> dict[str, object] | None:
    """Map one accepted typed answer to a source-referenced operation."""
    question_type = str(question["question_type"])
    target_id = str(question["target_id"])
    mapping = {
        ("running_artifact", "remove"): "drop_page_artifact",
        ("block_role", "heading"): "set_role",
        ("block_role", "body"): "set_role",
        ("line_boundary", "join_with_space"): "join_with_space",
        ("line_boundary", "join_without_space"): "join_without_space",
        ("line_boundary", "paragraph_break"): "set_paragraph_break",
        ("hyphenation", "dehyphenate"): "dehyphenate",
    }
    action = mapping.get((question_type, choice))
    if action is None:
        return None
    kwargs = {"role": choice} if action == "set_role" else {}
    return _operation(
        action,
        target_id,
        "ai_adjudication",
        verified_by="blind_verifier" if verifier else "primary",
        **kwargs,
    )


def _page_artifact_evidence(
    canonical_text: str,
    units: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    edge_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    page_numbers: list[tuple[int, dict[str, object], int]] = []
    for unit in units:
        locator = unit.get("locator")
        layout = unit.get("layout")
        if not isinstance(locator, dict) or not isinstance(layout, dict):
            continue
        page_index = locator.get("page_index")
        position = float(layout.get("relative_vertical_position", 0.5))
        if not isinstance(page_index, int) or not (position <= 0.12 or position >= 0.88):
            continue
        text = unit_text(canonical_text, unit).strip()
        if not text or len(text) > 160:
            continue
        number_match = _PAGE_NUMBER.fullmatch(text)
        if number_match:
            page_numbers.append((page_index, unit, int(number_match.group(1))))
            continue
        key = cleanup_text_analysis_service.normalized_header_footer_key(text)
        if key:
            parity = page_index % 2
            edge = "top" if position <= 0.12 else "bottom"
            edge_groups[f"{edge}:{parity}:{key}"].append(unit)

    operations: list[dict[str, object]] = []
    questions: list[dict[str, object]] = []
    observed_pages = {unit.get("locator", {}).get("page_index") for unit in units}
    page_total = max(1, len({item[0] for item in page_numbers}) or len(observed_pages))
    for group in edge_groups.values():
        if len(group) >= max(3, round(page_total * 0.25)):
            operations.extend(
                _operation("drop_page_artifact", str(unit["unit_id"]), "repeated_page_edge")
                for unit in group
            )
        elif len(group) >= 2:
            questions.extend(
                _question(
                    "running_artifact",
                    str(unit["unit_id"]),
                    unit_text(canonical_text, unit),
                    "",
                    ["preserve", "remove"],
                )
                for unit in group
            )
    page_numbers.sort(key=lambda item: item[0])
    if len(page_numbers) >= 4 and all(
        page_numbers[index][2] == page_numbers[index - 1][2] + 1
        for index in range(1, len(page_numbers))
    ):
        operations.extend(
            _operation("drop_page_artifact", str(unit["unit_id"]), "sequential_page_number")
            for _page, unit, _number in page_numbers
        )
    else:
        questions.extend(
            _question(
                "running_artifact",
                str(unit["unit_id"]),
                unit_text(canonical_text, unit),
                "",
                ["preserve", "remove"],
            )
            for _page, unit, _number in page_numbers
        )
    return operations, questions


def _high_confidence_line_join(
    left: dict[str, object],
    right: dict[str, object],
    left_text: str,
    right_text: str,
    median_width: float,
) -> bool:
    if cleanup_text_analysis_service.has_sentence_terminal(left_text):
        return False
    if not left_text.strip() or not right_text.strip():
        return False
    left_layout = left.get("layout")
    right_layout = right.get("layout")
    if isinstance(left_layout, dict) and isinstance(right_layout, dict):
        same_page = left.get("locator", {}).get("page_index") == right.get("locator", {}).get("page_index")
        same_column = left_layout.get("column") == right_layout.get("column")
        same_font = left_layout.get("font_signature") == right_layout.get("font_signature")
        left_box = left_layout.get("bbox")
        right_box = right_layout.get("bbox")
        if same_page and same_column and same_font and isinstance(left_box, list) and isinstance(right_box, list):
            line_height = max(1.0, float(left_box[3]) - float(left_box[1]))
            vertical_gap = float(right_box[1]) - float(left_box[3])
            return vertical_gap <= line_height * 1.3 and abs(float(left_box[0]) - float(right_box[0])) <= 12.0
        return False
    return median_width >= 30 and len(left_text.strip()) >= median_width * 0.85


def _protected(unit: dict[str, object]) -> bool:
    return str(unit.get("kind") or "unknown") in _PROTECTED_KINDS


def _no_space_script_boundary(left: str, right: str) -> bool:
    sample = f"{left[-8:]}{right[:8]}"
    return cleanup_text_analysis_service.classify_text_script(sample) in {"cjk", "hangul"}


def _operation(action: str, target_id: str, evidence: str, **extra: object) -> dict[str, object]:
    return {
        "operation_id": "",
        "action": action,
        "target_id": target_id,
        "evidence": evidence,
        **extra,
    }


def _question(
    question_type: str,
    target_id: str,
    left_text: str,
    right_text: str,
    choices: list[str],
) -> dict[str, object]:
    return {
        "question_id": "",
        "question_type": question_type,
        "target_id": target_id,
        "left_text": left_text[-240:],
        "right_text": right_text[:240],
        "choices": choices,
    }
