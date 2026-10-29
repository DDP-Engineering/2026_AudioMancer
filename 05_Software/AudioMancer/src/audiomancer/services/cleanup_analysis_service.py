#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file cleanup_analysis_service.py
@brief Deterministic structural analysis for the typed Cleanup contract.
@details Resolves unit roles before classifying every source-ledger boundary,
         records conservative priors, and exposes only low/medium-confidence
         boundaries to optional LLM adjudication.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import re
import statistics

from audiomancer import config
from audiomancer.services import cleanup_text_analysis_service
from audiomancer.services.source_ledger_service import unit_text

ANALYSIS_POLICY_ID = "cleanup-typed-boundaries-2026-10-29"
UNIT_ROLES = frozenset(
    (
        "body",
        "heading",
        "scene_separator",
        "list_item",
        "verse",
        "preformatted",
        "footnote",
        "page_artifact",
    )
)
BOUNDARY_CHOICES = frozenset(
    (
        "join_with_space",
        "set_paragraph_break",
        "set_semantic_line_break",
        "dehyphenate",
        "join_preserving_hyphen",
        "document_end",
    )
)
BOUNDARY_DECISION_FIELDS = frozenset(
    (
        "boundary_id",
        "left_unit_id",
        "right_unit_id",
        "kind",
        "page_transition",
        "left_role",
        "right_role",
        "prior",
        "adjudication",
        "final",
    )
)
_PRIOR_FIELDS = frozenset(("choice", "confidence", "reason_codes"))
_ADJUDICATION_FIELDS = frozenset(
    (
        "state",
        "primary_choice",
        "verifier_choice",
        "accepted",
    )
)
_FINAL_FIELDS = frozenset(
    ("choice", "origin", "confidence", "reason_codes")
)
_CONFIDENCE_VALUES = frozenset(("strong", "medium", "low"))
_ADJUDICATION_STATES = frozenset(
    ("not_required", "pending", "completed", "fallback")
)
_FINAL_ORIGINS = frozenset(
    ("native", "deterministic", "llm", "fallback", "user")
)

_PAGE_NUMBER = re.compile(
    r"^(?:page\s+)?(\d{1,5})(?:\s*(?:/|of)\s*\d+)?[.]?$",
    re.IGNORECASE,
)
_DIALOGUE_PREFIX = re.compile(r"^\s*(?:[-\u2013\u2014]\s+|[A-Z][^:]{0,40}:\s+)")
_PARAGRAPH_KINDS = frozenset(
    ("native_paragraph", "blank_paragraph", "paragraph")
)
_LINE_KINDS = frozenset(
    ("visual_line", "physical_line", "line", "native_line_break")
)
_ROLE_BY_KIND = {
    "heading": "heading",
    "scene_separator": "scene_separator",
    "list": "list_item",
    "list_item": "list_item",
    "list_or_dialogue": "list_item",
    "blockquote": "body",
    "verse": "verse",
    "preformatted": "preformatted",
    "table": "preformatted",
    "table_or_preformatted": "preformatted",
    "footnote": "footnote",
    "paragraph": "body",
    "body": "body",
    "unknown": "body",
}


def analyze_cleanup(
    canonical_text: str,
    ledger: dict[str, object],
) -> dict[str, object]:
    """Return deterministic roles, typed boundaries, questions, and profile."""
    units = [dict(item) for item in ledger["units"]]
    boundaries = [dict(item) for item in ledger["boundaries"]]
    warnings = [str(item) for item in ledger.get("warnings", [])]
    artifact_evidence = _page_artifact_evidence(canonical_text, units)
    # Keep all artifact text on otherwise text-empty pages, such as illustrated
    # covers with just a page number. The renderer requires a surviving unit.
    pages_with_non_artifacts = {
        _page_index(unit)
        for unit in units
        if str(unit["unit_id"]) not in artifact_evidence
    }
    roles = {
        str(unit["unit_id"]): (
            "page_artifact"
            if str(unit["unit_id"]) in artifact_evidence
            else _initial_role(canonical_text, unit)
        )
        for unit in units
    }
    _apply_non_native_verse_roles(canonical_text, units, boundaries, roles)

    unit_operations: list[dict[str, object]] = []
    for unit in units:
        unit_id = str(unit["unit_id"])
        role = roles[unit_id]
        unit_operations.append(
            _unit_operation(
                "set_role",
                unit_id,
                "native_structure" if unit.get("structure_origin") == "native" else "deterministic_role",
                role=role,
            )
        )
        if (
            unit_id in artifact_evidence
            and _page_index(unit) in pages_with_non_artifacts
        ):
            unit_operations.append(
                _unit_operation(
                    "drop_page_artifact",
                    unit_id,
                    artifact_evidence[unit_id],
                    role=None,
                )
            )
    for index, operation in enumerate(unit_operations, start=1):
        operation["operation_id"] = f"op-{index:06d}"

    unit_by_id = {str(item["unit_id"]): item for item in units}
    body_widths = [
        len(unit_text(canonical_text, unit).strip())
        for unit in units
        if roles[str(unit["unit_id"])] == "body"
        and len(unit_text(canonical_text, unit).strip()) >= 20
    ]
    median_width = statistics.median(body_widths) if body_widths else 0.0
    decisions = [
        _classify_boundary(
            canonical_text,
            boundary,
            unit_by_id,
            roles,
            median_width,
        )
        for boundary in boundaries
    ]
    _apply_page_artifact_bridge_priors(
        canonical_text,
        units,
        roles,
        decisions,
        median_width,
    )
    questions = []
    for decision in decisions:
        if decision["adjudication"]["state"] != "pending":
            continue
        questions.append(
            _question_from_decision(
                canonical_text,
                decision,
                unit_by_id,
                len(questions) + 1,
            )
        )

    role_counts = Counter(roles.values())
    detected_language = cleanup_text_analysis_service.detect_language(canonical_text)
    profile = {
        "source_format": str(ledger["source"]["format"]),
        "structure_quality": str(ledger["structure_quality"]),
        "unit_count": len(units),
        "page_count": len(ledger.get("pages", [])),
        "role_counts": dict(sorted(role_counts.items())),
        "language": detected_language,
        "dominant_script": cleanup_text_analysis_service.classify_text_script(canonical_text),
    }
    warning = _unsupported_language_warning(detected_language)
    if warning is not None and warning not in warnings:
        warnings.append(warning)
    return {
        "document_profile": profile,
        "unit_operations": unit_operations,
        "boundaries": decisions,
        "questions": questions,
        "warnings": warnings,
    }


def _unsupported_language_warning(detected_language: str | None) -> str | None:
    """Return the one operator warning required for a detected unsupported source language."""
    if (
        not detected_language
        or detected_language in config.CLEANUP_SUPPORTED_SOURCE_LANGUAGES
    ):
        return None
    return (
        f"Detected source language '{detected_language}' is outside the supported Cleanup languages; "
        "review the result carefully."
    )


def validate_persisted_boundaries(decisions: object) -> None:
    """
    @brief      Validate every nested field used to reuse Cleanup decisions.
    @param[in]  decisions Candidate persisted boundary decision list.
    @return     None.
    @exception  ValueError Raised when the reusable decision shape is invalid.
    """
    if not isinstance(decisions, list):
        raise ValueError("Cleanup boundaries must be a list.")
    for decision in decisions:
        if (
            not isinstance(decision, dict)
            or set(decision) != BOUNDARY_DECISION_FIELDS
        ):
            raise ValueError("Cleanup boundary fields are invalid.")
        if (
            not isinstance(decision["boundary_id"], str)
            or not decision["boundary_id"]
        ):
            raise ValueError("Cleanup boundary ID is invalid.")
        for field in ("left_unit_id", "right_unit_id"):
            value = decision[field]
            if value is not None and not isinstance(value, str):
                raise ValueError("Cleanup boundary unit ID is invalid.")
        if not isinstance(decision["kind"], str) or not decision["kind"]:
            raise ValueError("Cleanup boundary kind is invalid.")
        if type(decision["page_transition"]) is not bool:
            raise ValueError("Cleanup page-transition flag is invalid.")
        for field in ("left_role", "right_role"):
            role = decision[field]
            if role is not None and role not in UNIT_ROLES:
                raise ValueError("Cleanup boundary role is invalid.")
        _validate_prior(decision["prior"])
        _validate_adjudication(decision["adjudication"])
        _validate_final(decision["final"])


def _validate_prior(prior: object) -> None:
    """Validate one deterministic boundary prior."""
    if not isinstance(prior, dict) or set(prior) != _PRIOR_FIELDS:
        raise ValueError("Cleanup boundary prior is invalid.")
    _validate_choice(prior["choice"], allow_none=False)
    _validate_confidence(prior["confidence"])
    _validate_reason_codes(prior["reason_codes"])


def _validate_adjudication(adjudication: object) -> None:
    """Validate one resumable boundary adjudication record."""
    if (
        not isinstance(adjudication, dict)
        or set(adjudication) != _ADJUDICATION_FIELDS
    ):
        raise ValueError("Cleanup boundary adjudication is invalid.")
    if adjudication["state"] not in _ADJUDICATION_STATES:
        raise ValueError("Cleanup boundary adjudication state is invalid.")
    _validate_choice(adjudication["primary_choice"], allow_none=True)
    _validate_choice(adjudication["verifier_choice"], allow_none=True)
    if type(adjudication["accepted"]) is not bool:
        raise ValueError("Cleanup boundary acceptance flag is invalid.")


def _validate_final(final: object) -> None:
    """Validate one final typed boundary choice."""
    if not isinstance(final, dict) or set(final) != _FINAL_FIELDS:
        raise ValueError("Cleanup boundary final record is invalid.")
    _validate_choice(final["choice"], allow_none=False)
    if final["origin"] not in _FINAL_ORIGINS:
        raise ValueError("Cleanup boundary final origin is invalid.")
    _validate_confidence(final["confidence"])
    _validate_reason_codes(final["reason_codes"])


def _validate_choice(value: object, *, allow_none: bool) -> None:
    """Validate one optional or required boundary choice."""
    if value is None and allow_none:
        return
    if not isinstance(value, str) or value not in BOUNDARY_CHOICES:
        raise ValueError("Cleanup boundary choice is invalid.")


def _validate_confidence(value: object) -> None:
    """Validate one deterministic or final confidence token."""
    if not isinstance(value, str) or value not in _CONFIDENCE_VALUES:
        raise ValueError("Cleanup boundary confidence is invalid.")


def _validate_reason_codes(value: object) -> None:
    """Validate one persisted reason-code list."""
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise ValueError("Cleanup boundary reason codes are invalid.")


def questions_from_boundaries(
    canonical_text: str,
    ledger: dict[str, object],
    decisions: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Rebuild stable pending-question payloads from persisted deterministic analysis."""
    unit_by_id = {
        str(item["unit_id"]): dict(item)
        for item in ledger["units"]
    }
    questions = []
    for decision in decisions:
        if decision["adjudication"]["state"] == "not_required":
            continue
        questions.append(
            _question_from_decision(
                canonical_text,
                decision,
                unit_by_id,
                len(questions) + 1,
            )
        )
    return questions


def _initial_role(canonical_text: str, unit: dict[str, object]) -> str:
    """Resolve one source unit role before any boundary decision."""
    text = unit_text(canonical_text, unit).strip()
    kind = str(unit.get("kind") or "unknown").casefold()
    role = _ROLE_BY_KIND.get(kind, "body")
    if cleanup_text_analysis_service.is_scene_separator_artifact(text, role):
        return "scene_separator"
    if role == "body" and cleanup_text_analysis_service.detect_chapter_label(text):
        return "heading"
    return role


def _apply_non_native_verse_roles(
    canonical_text: str,
    units: list[dict[str, object]],
    boundaries: list[dict[str, object]],
    roles: dict[str, str],
) -> None:
    """Apply the conservative three-line verse heuristic to inferred/layout runs."""
    if len(units) < 3:
        return
    boundary_by_pair = {
        (str(item.get("left_unit_id")), str(item.get("right_unit_id"))): item
        for item in boundaries
        if item.get("right_unit_id") is not None
    }
    start = 0
    while start < len(units):
        end = start
        while end + 1 < len(units):
            pair = (
                str(units[end]["unit_id"]),
                str(units[end + 1]["unit_id"]),
            )
            boundary = boundary_by_pair.get(pair)
            if boundary is None or str(boundary.get("kind")) not in _LINE_KINDS:
                break
            end += 1
        run = units[start : end + 1]
        isolated = (
            len(run) < len(units)
            or any(isinstance(item.get("layout"), dict) for item in run)
        )
        if isolated and _is_verse_run(canonical_text, run, roles):
            for unit in run:
                roles[str(unit["unit_id"])] = "verse"
        start = end + 1


def _is_verse_run(
    canonical_text: str,
    units: list[dict[str, object]],
    roles: dict[str, str],
) -> bool:
    """Return whether one isolated line run satisfies the approved verse rule."""
    if len(units) < 3:
        return False
    texts = [unit_text(canonical_text, item).strip() for item in units]
    if any(not text or len(text) > 100 for text in texts):
        return False
    excluded_roles = {"heading", "scene_separator", "list_item", "preformatted", "footnote"}
    if any(roles[str(unit["unit_id"])] in excluded_roles for unit in units):
        return False
    if any(_DIALOGUE_PREFIX.match(text) for text in texts):
        return False
    no_terminal = sum(
        not cleanup_text_analysis_service.has_sentence_terminal(text)
        for text in texts
    )
    if no_terminal / len(texts) < 2 / 3:
        return False
    x_positions = []
    for unit, text in zip(units, texts, strict=True):
        layout = unit.get("layout")
        if isinstance(layout, dict) and isinstance(layout.get("bbox"), list):
            x_positions.append(float(layout["bbox"][0]))
        else:
            x_positions.append(float(len(text) - len(text.lstrip())))
    tolerance = 4.0 if any(isinstance(item.get("layout"), dict) for item in units) else 2.0
    return max(x_positions) - min(x_positions) <= tolerance


def _classify_boundary(
    canonical_text: str,
    boundary: dict[str, object],
    unit_by_id: dict[str, dict[str, object]],
    roles: dict[str, str],
    median_width: float,
) -> dict[str, object]:
    """Resolve one source-ledger boundary to a complete typed decision."""
    boundary_id = str(boundary["boundary_id"])
    left_id = boundary.get("left_unit_id")
    right_id = boundary.get("right_unit_id")
    left = unit_by_id.get(str(left_id))
    right = unit_by_id.get(str(right_id))
    left_role = roles.get(str(left_id)) if left_id is not None else None
    right_role = roles.get(str(right_id)) if right_id is not None else None
    kind = str(boundary.get("kind") or "line")
    page_transition = _is_page_transition(kind, left, right)
    choice, confidence, reason_codes, origin = _boundary_prior(
        canonical_text,
        boundary,
        left,
        right,
        left_role,
        right_role,
        page_transition,
        median_width,
    )
    adjudication_state = "not_required" if confidence == "strong" else "pending"
    return {
        "boundary_id": boundary_id,
        "left_unit_id": left_id,
        "right_unit_id": right_id,
        "kind": kind,
        "page_transition": page_transition,
        "left_role": left_role,
        "right_role": right_role,
        "prior": {
            "choice": choice,
            "confidence": confidence,
            "reason_codes": reason_codes,
        },
        "adjudication": {
            "state": adjudication_state,
            "primary_choice": None,
            "verifier_choice": None,
            "accepted": False,
        },
        "final": {
            "choice": choice,
            "origin": origin,
            "confidence": confidence,
            "reason_codes": list(reason_codes),
        },
    }


def _boundary_prior(
    canonical_text: str,
    boundary: dict[str, object],
    left: dict[str, object] | None,
    right: dict[str, object] | None,
    left_role: str | None,
    right_role: str | None,
    page_transition: bool,
    median_width: float,
) -> tuple[str, str, list[str], str]:
    """Return choice, confidence, reason codes, and origin for one boundary."""
    kind = str(boundary.get("kind") or "line")
    if right is None or kind == "document_end":
        return "document_end", "strong", ["document_end"], "deterministic"
    assert left is not None
    left_text = unit_text(canonical_text, left)
    native = str(boundary.get("structure_origin") or "") == "native"
    if left_role == "page_artifact" or right_role == "page_artifact":
        return (
            "set_paragraph_break",
            "strong",
            ["page_artifact_safe_boundary"],
            "deterministic",
        )
    if page_transition or kind == "page":
        return _cross_page_prior(
            canonical_text,
            left,
            right,
            median_width,
        )
    if kind in _PARAGRAPH_KINDS:
        return (
            "set_paragraph_break",
            "strong",
            ["native_paragraph" if native else "paragraph_gap"],
            "native" if native else "deterministic",
        )
    if kind == "native_line_break":
        return "set_semantic_line_break", "strong", ["native_line_break"], "native"
    if left_role in {"heading", "scene_separator", "footnote"}:
        return "set_paragraph_break", "strong", [f"{left_role}_boundary"], "deterministic"
    if right_role in {"heading", "scene_separator", "footnote"}:
        return "set_paragraph_break", "strong", [f"{right_role}_boundary"], "deterministic"
    if left_role == right_role and left_role in {"verse", "preformatted", "list_item"}:
        return (
            "set_semantic_line_break",
            "strong",
            [f"{left_role}_line"],
            "deterministic",
        )
    if left_text.endswith("\u00ad"):
        return "dehyphenate", "strong", ["soft_hyphen"], "deterministic"
    if left_text.endswith("-"):
        return (
            "join_preserving_hyphen",
            "medium",
            ["visible_hyphen_line_wrap"],
            "deterministic",
        )
    geometry_choice = _geometry_prior(
        left,
        right,
        left_text,
        median_width,
    )
    if geometry_choice is not None:
        return geometry_choice
    if kind in _LINE_KINDS:
        if cleanup_text_analysis_service.has_sentence_terminal(left_text):
            return (
                "set_paragraph_break",
                "medium",
                ["sentence_terminal_line"],
                "deterministic",
            )
        if median_width and len(left_text.strip()) >= median_width * 0.85:
            return (
                "join_with_space",
                "strong",
                ["full_width_line_continuation"],
                "deterministic",
            )
        return (
            "join_with_space",
            "medium",
            ["physical_line_continuation"],
            "deterministic",
        )
    source_gap = canonical_text[int(boundary["start"]) : int(boundary["end"])]
    if source_gap.count("\n") >= 2:
        return "set_paragraph_break", "strong", ["source_blank_line"], "deterministic"
    return "join_with_space", "low", ["unknown_line_boundary"], "deterministic"


def _geometry_prior(
    left: dict[str, object],
    right: dict[str, object],
    left_text: str,
    median_width: float,
) -> tuple[str, str, list[str], str] | None:
    """Return a layout prior when both units expose comparable geometry."""
    left_layout = left.get("layout")
    right_layout = right.get("layout")
    if not isinstance(left_layout, dict) or not isinstance(right_layout, dict):
        return None
    left_box = left_layout.get("bbox")
    right_box = right_layout.get("bbox")
    if not isinstance(left_box, list) or not isinstance(right_box, list):
        return None
    same_page = _page_index(left) == _page_index(right)
    same_column = left_layout.get("column") == right_layout.get("column")
    same_font = left_layout.get("font_signature") == right_layout.get("font_signature")
    if not same_column:
        return (
            "set_paragraph_break",
            "strong",
            ["column_transition"],
            "deterministic",
        )
    line_height = max(1.0, float(left_box[3]) - float(left_box[1]))
    vertical_gap = float(right_box[1]) - float(left_box[3])
    horizontal_delta = float(right_box[0]) - float(left_box[0])
    if not same_page or not same_font:
        return None
    if vertical_gap > line_height * 1.6:
        return (
            "set_paragraph_break",
            "strong",
            ["layout_enlarged_gap"],
            "deterministic",
        )
    if horizontal_delta > 12.0:
        return (
            "set_paragraph_break",
            "strong",
            ["layout_indented_paragraph"],
            "deterministic",
        )
    if horizontal_delta < -12.0:
        return (
            "join_with_space",
            "strong",
            ["layout_dedent_continuation"],
            "deterministic",
        )
    if not cleanup_text_analysis_service.has_sentence_terminal(left_text):
        return (
            "join_with_space",
            "strong",
            ["layout_line_continuation"],
            "deterministic",
        )
    if median_width and len(left_text.strip()) >= median_width * 0.85:
        return (
            "join_with_space",
            "medium",
            ["layout_full_width_sentence_continuation"],
            "deterministic",
        )
    return (
        "set_paragraph_break",
        "medium",
        ["layout_short_terminal_line"],
        "deterministic",
    )


def _cross_page_prior(
    canonical_text: str,
    left: dict[str, object],
    right: dict[str, object],
    median_width: float,
) -> tuple[str, str, list[str], str]:
    """Classify one narrative page transition without forcing a paragraph."""
    left_text = unit_text(canonical_text, left)
    left_layout = left.get("layout")
    right_layout = right.get("layout")
    if isinstance(left_layout, dict) and isinstance(right_layout, dict):
        left_box = left_layout.get("bbox")
        right_box = right_layout.get("bbox")
        if isinstance(left_box, list) and isinstance(right_box, list):
            if left_layout.get("column") != right_layout.get("column"):
                return (
                    "set_paragraph_break",
                    "strong",
                    ["page_column_transition"],
                    "deterministic",
                )
            horizontal_delta = float(right_box[0]) - float(left_box[0])
            if horizontal_delta > 12.0:
                return (
                    "set_paragraph_break",
                    "strong",
                    ["page_indented_paragraph"],
                    "deterministic",
                )
            if horizontal_delta < -12.0:
                return (
                    "join_with_space",
                    "strong",
                    ["page_dedent_continuation"],
                    "deterministic",
                )
            if not cleanup_text_analysis_service.has_sentence_terminal(left_text):
                return (
                    "join_with_space",
                    "strong",
                    ["page_line_continuation"],
                    "deterministic",
                )
            if median_width and len(left_text.strip()) >= median_width * 0.85:
                return (
                    "join_with_space",
                    "strong",
                    ["page_full_width_sentence_continuation"],
                    "deterministic",
                )
            return (
                "set_paragraph_break",
                "strong",
                ["page_short_terminal_line"],
                "deterministic",
            )
    if cleanup_text_analysis_service.has_sentence_terminal(left_text):
        return (
            "set_paragraph_break",
            "medium",
            ["page_terminal_without_geometry"],
            "deterministic",
        )
    return (
        "join_with_space",
        "medium",
        ["page_continuation_without_geometry"],
        "deterministic",
    )


def _apply_page_artifact_bridge_priors(
    canonical_text: str,
    units: list[dict[str, object]],
    roles: dict[str, str],
    decisions: list[dict[str, object]],
    median_width: float,
) -> None:
    """Assign one effective narrative prior across each dropped-artifact run."""
    decision_by_pair = {
        (
            str(item.get("left_unit_id")),
            str(item.get("right_unit_id")),
        ): item
        for item in decisions
        if item.get("right_unit_id") is not None
    }
    index = 0
    while index < len(units):
        unit_id = str(units[index]["unit_id"])
        if roles[unit_id] != "page_artifact":
            index += 1
            continue
        run_start = index
        while (
            index + 1 < len(units)
            and roles[str(units[index + 1]["unit_id"])] == "page_artifact"
        ):
            index += 1
        run_end = index
        if run_start == 0 or run_end + 1 >= len(units):
            index += 1
            continue
        left = units[run_start - 1]
        right = units[run_end + 1]
        if (
            roles[str(left["unit_id"])] == "page_artifact"
            or roles[str(right["unit_id"])] == "page_artifact"
        ):
            index += 1
            continue
        choice, _confidence, reasons, origin = _cross_page_prior(
            canonical_text,
            left,
            right,
            median_width,
        )
        chain = units[run_start - 1 : run_end + 2]
        for chain_index in range(len(chain) - 1):
            decision = decision_by_pair.get(
                (
                    str(chain[chain_index]["unit_id"]),
                    str(chain[chain_index + 1]["unit_id"]),
                )
            )
            if decision is None:
                continue
            reason_codes = [
                *reasons,
                "page_artifact_bridge",
            ]
            decision["prior"] = {
                "choice": choice,
                "confidence": "strong",
                "reason_codes": reason_codes,
            }
            decision["adjudication"] = {
                "state": "not_required",
                "primary_choice": None,
                "verifier_choice": None,
                "accepted": False,
            }
            decision["final"] = {
                "choice": choice,
                "origin": origin,
                "confidence": "strong",
                "reason_codes": list(reason_codes),
            }
        index += 1


def _question_from_decision(
    canonical_text: str,
    decision: dict[str, object],
    unit_by_id: dict[str, dict[str, object]],
    index: int,
) -> dict[str, object]:
    """Build one bounded classification question without a strong prior."""
    left = unit_by_id.get(str(decision.get("left_unit_id")))
    right = unit_by_id.get(str(decision.get("right_unit_id")))
    left_text = "" if left is None else unit_text(canonical_text, left)
    right_text = "" if right is None else unit_text(canonical_text, right)
    prior = dict(decision["prior"])
    prior_choice = str(prior["choice"])
    if prior_choice in {"dehyphenate", "join_preserving_hyphen"}:
        choices = [
            "dehyphenate",
            "join_preserving_hyphen",
            "set_paragraph_break",
        ]
        question_type = "hyphenation"
    else:
        choices = [
            "join_with_space",
            "set_paragraph_break",
            "set_semantic_line_break",
        ]
        question_type = "line_boundary"
    return {
        "question_id": f"q-{index:06d}",
        "question_type": question_type,
        "target_id": str(decision["boundary_id"]),
        "left_text": left_text[-240:],
        "right_text": right_text[:240],
        "choices": choices,
        "prior_choice": prior_choice,
        "prior_confidence": str(prior["confidence"]),
    }


def _page_artifact_evidence(
    canonical_text: str,
    units: list[dict[str, object]],
) -> dict[str, str]:
    """Return only page artifacts supported by repetition or sequence evidence."""
    edge_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    page_numbers: list[tuple[int, dict[str, object], int]] = []
    observed_pages: set[int] = set()
    for unit in units:
        page_index = _page_index(unit)
        layout = unit.get("layout")
        if page_index is None or not isinstance(layout, dict):
            continue
        observed_pages.add(page_index)
        position = float(layout.get("relative_vertical_position", 0.5))
        if not (position <= 0.12 or position >= 0.88):
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

    evidence: dict[str, str] = {}
    page_total = max(1, len(observed_pages))
    for group in edge_groups.values():
        if len(group) >= max(3, round(page_total * 0.25)):
            for unit in group:
                evidence[str(unit["unit_id"])] = "repeated_page_edge"
    page_numbers.sort(key=lambda item: item[0])
    if len(page_numbers) >= 4 and all(
        page_numbers[index][2] == page_numbers[index - 1][2] + 1
        for index in range(1, len(page_numbers))
    ):
        for _page, unit, _number in page_numbers:
            evidence[str(unit["unit_id"])] = "sequential_page_number"
    return evidence


def _unit_operation(
    action: str,
    target_id: str,
    evidence: str,
    *,
    role: str | None,
) -> dict[str, object]:
    """Build one typed unit operation."""
    return {
        "operation_id": "",
        "action": action,
        "target_id": target_id,
        "evidence": evidence,
        "role": role,
    }


def _is_page_transition(
    kind: str,
    left: dict[str, object] | None,
    right: dict[str, object] | None,
) -> bool:
    """Return whether one boundary crosses source pages."""
    if right is None:
        return False
    if kind == "page":
        return True
    left_page = _page_index(left)
    right_page = _page_index(right)
    return left_page is not None and right_page is not None and left_page != right_page


def _page_index(unit: dict[str, object] | None) -> int | None:
    """Return a unit's optional zero-based source page."""
    if not isinstance(unit, dict):
        return None
    locator = unit.get("locator")
    if not isinstance(locator, dict) or not isinstance(locator.get("page_index"), int):
        return None
    return int(locator["page_index"])


# END OF FILE
