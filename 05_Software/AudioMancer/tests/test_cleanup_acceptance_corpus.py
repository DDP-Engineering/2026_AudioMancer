#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_cleanup_acceptance_corpus.py
@brief Test-only oracle for the synthetic Cleanup acceptance corpus.
@details Measures boundary classification, output projection, page-transition
         coverage, and zero introduced fusion without exposing oracle metrics
         in runtime metadata.
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

from audiomancer.services import cleanup_analysis_service, cleanup_renderer_service
from cleanup_test_support import build_ledger

_CORPUS_PATH = Path(__file__).parent / "fixtures" / "cleanup_corpus.json"


def test_acceptance_corpus_has_required_size_and_domain_coverage() -> None:
    """Cover S-0012 and REQ-TEST-1b7844b3-7408-419e-ac14-2c9c236182d8."""
    corpus = _load_corpus()

    assert 20 <= len(corpus) <= 25
    assert {item["format"] for item in corpus} == {"txt", "md", "rtf", "docx", "odt", "epub", "pdf"}
    assert {item["language"] for item in corpus} == {"en", "ro", "de", "fr", "ru", "pt", "es", "it"}
    assert {
        "poetry",
        "native_line_break",
        "preformatted",
        "two_column",
        "degraded_geometry",
        "footnote",
        "dense_dialogue",
    } <= {item["archetype"] for item in corpus}


def test_acceptance_corpus_meets_boundary_and_projection_thresholds() -> None:
    """Cover S-0001/S-0003/S-0012 and REQ-TEST-1b7844b3-7408-419e-ac14-2c9c236182d8."""
    expected_by_tier: dict[str, list[str]] = defaultdict(list)
    actual_by_tier: dict[str, list[str]] = defaultdict(list)
    introduced_fusions = 0
    projection_violations = 0

    for case in _load_corpus():
        boundary_specs = [
            (str(item["separator"]), str(item["kind"]))
            for item in case["boundaries"]
        ]
        canonical_text, ledger = build_ledger(
            case["units"],
            source_format=str(case["format"]),
            kinds=case["kinds"],
            boundaries=boundary_specs,
            origins=case["origins"],
            layouts=case.get("layouts"),
            locators=case.get("locators"),
            structure_quality=str(case["structure_quality"]),
            warnings=case.get("warnings"),
        )
        analysis = cleanup_analysis_service.analyze_cleanup(canonical_text, ledger)
        cleaned_text, metadata = cleanup_renderer_service.render_cleanup(
            canonical_text,
            ledger,
            analysis["unit_operations"],
            analysis["boundaries"],
        )
        actual_nonterminal = [
            str(item["final"]["choice"])
            for item in analysis["boundaries"]
            if item["right_unit_id"] is not None
        ]
        expected_nonterminal = [str(item["choice"]) for item in case["boundaries"]]
        tier = str(case["tier"])
        expected_by_tier[tier].extend(expected_nonterminal)
        actual_by_tier[tier].extend(actual_nonterminal)
        assert cleaned_text == case["expected_output"], case["name"]
        introduced_fusions += int(metadata["quality_report"]["introduced_fusion_count"])
        projection_violations += int(metadata["quality_report"]["projection_violation_count"])

    all_expected = [item for values in expected_by_tier.values() for item in values]
    all_actual = [item for values in actual_by_tier.values() for item in values]
    assert _micro_f1(all_expected, all_actual) >= 0.97
    assert _micro_f1(expected_by_tier["native"], actual_by_tier["native"]) >= 0.99
    assert _micro_f1(expected_by_tier["pdf_good"], actual_by_tier["pdf_good"]) >= 0.95
    assert _micro_f1(expected_by_tier["pdf_degraded"], actual_by_tier["pdf_degraded"]) >= 0.85
    assert introduced_fusions == 0
    assert projection_violations == 0


def test_all_27_synthetic_page_transitions_receive_safe_typed_decisions() -> None:
    """Cover S-0003/S-0012 and REQ-FUNC-4b0701b7-2967-4a42-aa20-a368ba13a0c0."""
    texts = [f"Page {index + 1} narrative ends safely." for index in range(28)]
    canonical_text, ledger = build_ledger(
        texts,
        source_format="pdf",
        kinds=["paragraph"] * 28,
        boundaries=[("\n\n\f\n\n", "page")] * 27,
        origins=["layout"] * 28,
        locators=[{"page_index": index} for index in range(28)],
        structure_quality="geometry_full",
    )

    analysis = cleanup_analysis_service.analyze_cleanup(canonical_text, ledger)
    page_decisions = [item for item in analysis["boundaries"] if item["page_transition"]]

    assert len(page_decisions) == 27
    assert all(item["final"]["choice"] == "set_paragraph_break" for item in page_decisions)


def test_runtime_quality_report_excludes_oracle_only_metrics() -> None:
    """Cover S-0012 and REQ-FUNC-f9125c01-1a7a-4e84-8451-60b63f4b5dc8."""
    canonical_text, ledger = build_ledger(["One wrapped line", "continues safely."])
    analysis = cleanup_analysis_service.analyze_cleanup(canonical_text, ledger)

    _cleaned_text, metadata = cleanup_renderer_service.render_cleanup(
        canonical_text,
        ledger,
        analysis["unit_operations"],
        analysis["boundaries"],
    )

    assert "f1" not in metadata["quality_report"]
    assert "precision" not in metadata["quality_report"]
    assert "recall" not in metadata["quality_report"]


def _load_corpus() -> list[dict[str, object]]:
    """Load the immutable JSON acceptance corpus."""
    payload = json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise AssertionError("Cleanup corpus must be a list.")
    return [dict(item) for item in payload]


def _micro_f1(expected: list[str], actual: list[str]) -> float:
    """Return exact-label micro F1 for one ordered boundary sequence."""
    if len(expected) != len(actual) or not expected:
        return 0.0
    true_positive = sum(left == right for left, right in zip(expected, actual, strict=True))
    false_positive = len(actual) - true_positive
    false_negative = len(expected) - true_positive
    denominator = (2 * true_positive) + false_positive + false_negative
    return 0.0 if denominator == 0 else (2 * true_positive) / denominator


# END OF FILE
