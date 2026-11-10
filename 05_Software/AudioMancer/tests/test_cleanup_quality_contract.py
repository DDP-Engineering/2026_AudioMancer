#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_cleanup_quality_contract.py
@brief Red-first checks for the approved Cleanup quality contract.
@details Covers the strict two-artifact contract, typed boundaries, protected
         roles, fusion safety, script eligibility, resume, and manual edits.
"""

# IMPORTS

from __future__ import annotations

import json

import pytest

from audiomancer import config
from audiomancer.cleanup import analysis as cleanup_analysis_service
from audiomancer.cleanup import render as cleanup_renderer_service
from audiomancer.cleanup import text as cleanup_text_analysis_service
from audiomancer.services import (
    cleanup_ai_adjudication_service,
    operation_runtime_service,
    project_workspace_service,
    source_ledger_service,
    text_cleanup_service,
    text_cleanup_state_service,
    token_usage_service,
)
from cleanup_test_support import (
    BOUNDARY_CHOICES,
    UNIT_ROLES,
    assert_strict_cleanup_document,
    build_ledger,
    build_project,
    make_profile,
    read_cleanup_document,
)


def _build_completed_cleanup(tmp_path):
    """@brief Build one valid completed Cleanup document for corruption checks."""
    canonical_text, ledger = build_ledger(
        ["A complete paragraph.", "A second paragraph."],
        kinds=["paragraph", "paragraph"],
        boundaries=[("\n\n", "native_paragraph")],
        origins=["native", "native"],
        structure_quality="native",
    )
    project_root, manifest = build_project(
        tmp_path,
        "CorruptCleanupDocument",
        canonical_text,
        ledger,
    )
    document = text_cleanup_service.clean_text(project_root, manifest)
    return project_root, document


def test_cleanup_persists_exactly_one_metadata_file_and_one_text_file(tmp_path) -> None:
    """@brief Cover S-0007/S-0008 and REQ-FUNC-50c48e76-aa6a-4a54-840b-ece463309faf."""
    canonical_text, ledger = build_ledger(
        ["A complete paragraph.", "A second paragraph."],
        kinds=["paragraph", "paragraph"],
        boundaries=[("\n\n", "native_paragraph")],
        origins=["native", "native"],
        structure_quality="native",
    )
    project_root, manifest = build_project(tmp_path, "StrictArtifacts", canonical_text, ledger)

    document = text_cleanup_service.clean_text(project_root, manifest)

    assert_strict_cleanup_document(document)
    assert document["status"] == "completed"
    assert document["phase"] == "done"
    assert document["output_hash"] == source_ledger_service.text_sha256(
        (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    ("field", "invalid_value", "remove_field"),
    [
        ("introduced_fusion_count", None, False),
        ("introduced_fusion_count", None, True),
        ("projection_violation_count", True, False),
        ("invalid_operation_count", "0", False),
        ("unclassified_boundary_count", 0.0, False),
        ("introduced_fusion_count", [], False),
        ("projection_violation_count", {}, False),
        ("invalid_operation_count", 1, False),
    ],
)
def test_load_cleanup_document_rejects_malformed_blocking_quality_metrics(
    tmp_path,
    field,
    invalid_value,
    remove_field,
) -> None:
    """@brief Cover S-0001 and REQ-FUNC-554ffe77-0dff-49d8-b4ad-8df145532b8a."""
    project_root, document = _build_completed_cleanup(tmp_path)
    if remove_field:
        del document["quality_report"][field]
    else:
        document["quality_report"][field] = invalid_value
    (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(text_cleanup_service.CleanupDocumentError):
        text_cleanup_service.load_cleanup_document(project_root)


@pytest.mark.parametrize(
    "case",
    [
        "missing_field",
        "extra_field",
        "boolean_counter",
        "negative_counter",
        "malformed_batch",
        "out_of_range_next_index",
    ],
)
def test_load_cleanup_document_rejects_malformed_progress(tmp_path, case) -> None:
    """@brief Cover S-0002 and REQ-FUNC-cdb7617a-5ec1-44b9-9ea5-a650e3f7f3e6."""
    project_root, document = _build_completed_cleanup(tmp_path)
    progress = document["progress"]
    if case == "missing_field":
        del progress["batch_order"]
    elif case == "extra_field":
        progress["unexpected"] = 0
    elif case == "boolean_counter":
        progress["question_count"] = True
    elif case == "negative_counter":
        progress["estimated_input_tokens"] = -1
    elif case == "malformed_batch":
        progress["batch_order"] = [["boundary-1", 2]]
    else:
        progress["next_batch_index"] = 1
    (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(text_cleanup_service.CleanupDocumentError):
        text_cleanup_service.load_cleanup_document(project_root)


@pytest.mark.parametrize(
    "case",
    [
        "missing_progress_field",
        "malformed_progress_counter",
        "invalid_batch_order",
        "missing_adjudication",
        "malformed_adjudication_object",
        "invalid_adjudication_state",
        "missing_prior",
        "missing_final",
        "non_list_boundaries",
    ],
)
def test_malformed_reuse_checkpoint_starts_fresh_analysis(
    tmp_path,
    monkeypatch,
    case,
) -> None:
    """@brief Malformed nested state is rejected strictly and never partially reused."""
    project_root, document = _build_completed_cleanup(tmp_path)
    if case == "missing_progress_field":
        del document["progress"]["completed_request_count"]
    elif case == "malformed_progress_counter":
        document["progress"]["completed_request_count"] = "1"
    elif case == "invalid_batch_order":
        document["progress"]["batch_order"] = [["unknown-boundary"]]
    elif case == "missing_adjudication":
        del document["boundaries"][0]["adjudication"]
    elif case == "malformed_adjudication_object":
        document["boundaries"][0]["adjudication"] = []
    elif case == "invalid_adjudication_state":
        document["boundaries"][0]["adjudication"]["state"] = "unknown"
    elif case == "missing_prior":
        del document["boundaries"][0]["prior"]
    elif case == "missing_final":
        del document["boundaries"][0]["final"]
    else:
        document["boundaries"] = {"unexpected": "object"}
    checkpoint_path = project_root / config.CLEANUP_DOCUMENT_FILE_NAME
    checkpoint_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(text_cleanup_service.CleanupDocumentError):
        text_cleanup_service.load_cleanup_document(project_root)

    analysis_calls = {"count": 0}
    original_analyze = cleanup_analysis_service.analyze_cleanup

    def _count_analysis(*args, **kwargs):
        """@brief Count real analysis calls to verify checkpoint reuse."""
        analysis_calls["count"] += 1
        return original_analyze(*args, **kwargs)

    monkeypatch.setattr(cleanup_analysis_service, "analyze_cleanup", _count_analysis)
    rebuilt = text_cleanup_service.clean_text(project_root, _manifest(project_root))

    assert analysis_calls["count"] == 1
    assert rebuilt["status"] == "completed"
    assert text_cleanup_service.load_cleanup_document(project_root) == rebuilt


def test_malformed_reuse_checkpoint_uses_fresh_cancellation_path(tmp_path) -> None:
    """@brief Cancellation wins before analysis instead of exposing corrupt internals."""
    project_root, document = _build_completed_cleanup(tmp_path)
    del document["progress"]["completed_request_count"]
    (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        text_cleanup_service.clean_text(
            project_root,
            _manifest(project_root),
            cancel_requested=lambda: True,
        )


def test_profile_change_cannot_reset_invalid_boundary_layer(
    tmp_path,
    monkeypatch,
) -> None:
    """@brief Profile invalidation occurs only after deterministic structure validates."""
    project_root, document = _build_completed_cleanup(tmp_path)
    del document["boundaries"][0]["adjudication"]
    (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    analysis_calls = {"count": 0}
    original_analyze = cleanup_analysis_service.analyze_cleanup

    def _count_analysis(*args, **kwargs):
        """@brief Count real analysis calls to verify checkpoint reuse."""
        analysis_calls["count"] += 1
        return original_analyze(*args, **kwargs)

    monkeypatch.setattr(cleanup_analysis_service, "analyze_cleanup", _count_analysis)
    monkeypatch.setattr(
        text_cleanup_service,
        "_reset_ai_adjudication",
        lambda *_args, **_kwargs: pytest.fail(
            "Invalid deterministic boundaries must not reach AI-only reset."
        ),
    )

    rebuilt = text_cleanup_service.clean_text(
        project_root,
        _manifest(project_root),
        ai_profile_payload=make_profile(supports_structured_output=False),
    )

    assert analysis_calls["count"] == 1
    assert rebuilt["status"] == "completed"


@pytest.mark.parametrize(
    ("status", "phase"),
    [
        ("running", "adjudication"),
        ("paused", "adjudication"),
        ("finalizing", "rendering"),
        ("completed", "done"),
    ],
)
def test_valid_checkpoint_lifecycle_states_remain_reusable(
    tmp_path,
    monkeypatch,
    status,
    phase,
) -> None:
    """@brief Strict reuse validation preserves every supported recovery branch."""
    project_root, document = _build_completed_cleanup(tmp_path)
    document["status"] = status
    document["phase"] = phase
    if status != "completed":
        document["completed_at"] = None
    (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cleanup_analysis_service,
        "analyze_cleanup",
        lambda *_args, **_kwargs: pytest.fail(
            f"A valid {status} checkpoint must reuse deterministic analysis."
        ),
    )

    recovered = text_cleanup_service.clean_text(
        project_root,
        _manifest(project_root),
    )

    assert recovered["status"] == "completed"


def test_analysis_assigns_roles_before_classifying_every_boundary() -> None:
    """@brief Cover S-0003/S-0004 and REQ-FUNC-4b0701b7-2967-4a42-aa20-a368ba13a0c0."""
    canonical_text, ledger = build_ledger(
        ["CHAPTER ONE", "Body continues", "on the next line.", "* * *"],
        kinds=["heading", "paragraph", "paragraph", "scene_separator"],
        boundaries=[
            ("\n\n", "native_paragraph"),
            ("\n", "physical_line"),
            ("\n\n", "native_paragraph"),
        ],
        origins=["native", "native", "native", "native"],
        structure_quality="native",
    )

    analysis = cleanup_analysis_service.analyze_cleanup(canonical_text, ledger)

    decisions = analysis["boundaries"]
    assert [item["boundary_id"] for item in decisions] == [
        item["boundary_id"] for item in ledger["boundaries"]
    ]
    assert {item["final"]["choice"] for item in decisions} <= BOUNDARY_CHOICES
    assert all(item["left_role"] in UNIT_ROLES for item in decisions)
    assert all(item["right_role"] in UNIT_ROLES | {None} for item in decisions)
    assert decisions[-1]["final"]["choice"] == "document_end"
    assert {item["action"] for item in analysis["unit_operations"]} <= {
        "drop_page_artifact",
        "set_role",
    }


def test_renderer_rejects_unsupported_boundary_choice() -> None:
    """@brief Cover S-0001/S-0002 and REQ-FUNC-e42171cc-9c36-4327-87ba-c0f13da05c8c."""
    canonical_text, ledger = build_ledger(["evacuation", "dropships"])
    boundary_id = str(ledger["boundaries"][0]["boundary_id"])

    with pytest.raises(cleanup_renderer_service.CleanupRenderError, match="unsupported_choice"):
        cleanup_renderer_service.render_cleanup(
            canonical_text,
            ledger,
            [],
            [
                {
                    "boundary_id": boundary_id,
                    "final": {"choice": "unsupported_choice"},
                }
            ],
        )


@pytest.mark.parametrize(
    ("left", "right", "expected_choice", "expected_text"),
    [
        ("the evacuation", "dropships arrived.", "join_with_space", "the evacuation dropships arrived.\n"),
        ("civil-", "defense unit.", "join_preserving_hyphen", "civil-defense unit.\n"),
        ("inter\u00ad", "national unit.", "dehyphenate", "international unit.\n"),
    ],
)
def test_renderer_allows_only_safe_boundary_join_forms(
    left,
    right,
    expected_choice,
    expected_text,
) -> None:
    """@brief Cover S-0001/S-0002 and REQ-FUNC-6eb73209-e81b-4413-b03e-4f183487618c."""
    canonical_text, ledger = build_ledger([left, right])
    analysis = cleanup_analysis_service.analyze_cleanup(canonical_text, ledger)
    decision = analysis["boundaries"][0]

    assert decision["final"]["choice"] == expected_choice
    cleaned_text, metadata = cleanup_renderer_service.render_cleanup(
        canonical_text,
        ledger,
        analysis["unit_operations"],
        analysis["boundaries"],
    )

    assert cleaned_text == expected_text
    assert metadata["quality_report"]["introduced_fusion_count"] == 0
    assert metadata["quality_report"]["projection_violation_count"] == 0


def test_renderer_rejects_controlled_unauthorized_empty_separator(
    monkeypatch,
) -> None:
    """@brief Reject an alphanumeric join introduced by a regressed separator renderer."""
    canonical_text, ledger = build_ledger(["alpha", "beta"])
    analysis = cleanup_analysis_service.analyze_cleanup(canonical_text, ledger)

    def _omit_separator(
        _parts,
        _spans,
        decisions,
        output_length,
        *,
        at_document_start,
    ):
        """@brief Inject an unsafe separator omission for the fusion guard."""
        del at_document_start
        return (
            output_length,
            [
                {
                    **decision,
                    "output_start": output_length,
                    "output_end": output_length,
                }
                for decision in decisions
            ],
        )

    monkeypatch.setattr(
        cleanup_renderer_service,
        "_render_boundary_group",
        _omit_separator,
    )

    with pytest.raises(
        cleanup_renderer_service.CleanupRenderError,
        match="alphanumeric source adjacency",
    ):
        cleanup_renderer_service.render_cleanup(
            canonical_text,
            ledger,
            analysis["unit_operations"],
            analysis["boundaries"],
        )


@pytest.mark.parametrize(
    ("cleaned_text", "spans", "boundaries", "expected"),
    [
        (
            "éβ",
            [
                {"unit_id": "u-left", "start": 0, "end": 1},
                {"unit_id": "u-right", "start": 1, "end": 2},
            ],
            [],
            1,
        ),
        (
            "é β",
            [
                {"unit_id": "u-left", "start": 0, "end": 1},
                {"unit_id": "u-right", "start": 2, "end": 3},
            ],
            [],
            0,
        ),
        (
            "é.β",
            [
                {"unit_id": "u-left", "start": 0, "end": 2},
                {"unit_id": "u-right", "start": 2, "end": 3},
            ],
            [],
            0,
        ),
        (
            "éβ",
            [{"unit_id": "u-left", "start": 0, "end": 2}],
            [],
            0,
        ),
        (
            "éβ",
            [
                {"unit_id": "u-left", "start": 0, "end": 1},
                {"unit_id": "u-right", "start": 1, "end": 2},
            ],
            [
                {
                    "left_unit_id": "u-left",
                    "output_start": 1,
                    "output_end": 1,
                    "dehyphenation_applied": True,
                    "final": {"choice": "dehyphenate"},
                }
            ],
            0,
        ),
        (
            "éβ",
            [
                {"unit_id": "u-left", "start": 0, "end": 1},
                {"unit_id": "u-right", "start": 1, "end": 2},
            ],
            [
                {
                    "left_unit_id": "u-dropped",
                    "output_start": 1,
                    "output_end": 1,
                    "dehyphenation_applied": True,
                    "final": {"choice": "dehyphenate"},
                }
            ],
            1,
        ),
    ],
)
def test_rendered_projection_fusion_counter_is_not_constant(
    cleaned_text,
    spans,
    boundaries,
    expected,
) -> None:
    """@brief Count only unsafe Unicode-alphanumeric joins across rendered spans."""
    assert cleanup_renderer_service._introduced_fusion_count(
        cleaned_text,
        spans,
        boundaries,
    ) == expected


@pytest.mark.parametrize(
    ("left_choice", "dropped_choice", "raises", "expected_text"),
    [
        ("join_preserving_hyphen", "dehyphenate", True, None),
        ("dehyphenate", "join_preserving_hyphen", False, "alphabeta\n"),
    ],
)
def test_renderer_scopes_dropped_chain_dehyphenation_to_retained_left_span(
    left_choice,
    dropped_choice,
    raises,
    expected_text,
) -> None:
    """@brief Authorize a dropped-chain join only from its retained left endpoint."""
    canonical_text, ledger = build_ledger(["alpha-", "artifact-", "beta"])
    analysis = cleanup_analysis_service.analyze_cleanup(canonical_text, ledger)
    unit_ids = [str(item["unit_id"]) for item in ledger["units"]]
    analysis["unit_operations"].append(
        {
            "operation_id": "op-drop-controlled",
            "action": "drop_page_artifact",
            "target_id": unit_ids[1],
        }
    )
    analysis["boundaries"][0]["final"]["choice"] = left_choice
    analysis["boundaries"][1]["final"]["choice"] = dropped_choice

    if raises:
        with pytest.raises(
            cleanup_renderer_service.CleanupRenderError,
            match="alphanumeric source adjacency",
        ):
            cleanup_renderer_service.render_cleanup(
                canonical_text,
                ledger,
                analysis["unit_operations"],
                analysis["boundaries"],
            )
        return

    cleaned_text, metadata = cleanup_renderer_service.render_cleanup(
        canonical_text,
        ledger,
        analysis["unit_operations"],
        analysis["boundaries"],
    )
    assert cleaned_text == expected_text
    assert metadata["quality_report"]["introduced_fusion_count"] == 0


@pytest.mark.parametrize(
    ("left_x", "right_x", "left", "expected_choice"),
    [
        (
            40.0,
            58.0,
            "A full source line ends at a sentence boundary after substantial "
            "narrative content.",
            "set_paragraph_break",
        ),
        (
            58.0,
            40.0,
            "A full source line ends at a sentence boundary after substantial "
            "narrative content.",
            "join_with_space",
        ),
        (
            40.0,
            40.0,
            "A full source line ends at a sentence boundary after substantial "
            "narrative content.",
            "join_with_space",
        ),
        (40.0, 40.0, "A short sentence.", "set_paragraph_break"),
    ],
)
def test_pdf_geometry_distinguishes_indent_dedent_and_full_width_lines(
    left_x,
    right_x,
    left,
    expected_choice,
) -> None:
    """@brief Cover S-0003 and the typed-boundary geometry requirements."""
    right = "The next source line provides enough text for a stable width."
    canonical_text, ledger = build_ledger(
        [left, right],
        source_format="pdf",
        kinds=["unknown", "unknown"],
        layouts=[
            {
                "bbox": [left_x, 100.0, 500.0, 114.0],
                "font_signature": "Book:11",
                "relative_vertical_position": 0.4,
                "column": 0,
            },
            {
                "bbox": [right_x, 116.0, 500.0, 130.0],
                "font_signature": "Book:11",
                "relative_vertical_position": 0.42,
                "column": 0,
            },
        ],
        locators=[{"page_index": 0}, {"page_index": 0}],
        origins=["layout", "layout"],
        structure_quality="geometry_full",
    )

    analysis = cleanup_analysis_service.analyze_cleanup(canonical_text, ledger)

    assert analysis["boundaries"][0]["final"]["choice"] == expected_choice


def test_removed_page_artifact_keeps_a_typed_safe_gap() -> None:
    """@brief Cover S-0001/S-0004 and REQ-FUNC-4d57e621-74db-40e7-b9ec-f268dadc431c."""
    edge_layout = {
        "bbox": [200.0, 780.0, 220.0, 792.0],
        "font_signature": "Book:9",
        "relative_vertical_position": 0.98,
        "column": 0,
    }
    body_layout = {
        "bbox": [40.0, 100.0, 440.0, 114.0],
        "font_signature": "Book:11",
        "relative_vertical_position": 0.5,
        "column": 0,
    }
    texts = []
    kinds = []
    boundaries = []
    layouts = []
    locators = []
    for page_index in range(4):
        if texts:
            boundaries.append(("\n\n\f\n\n", "page"))
        texts.extend([f"Narrative left {page_index}", str(page_index + 1), f"continues right {page_index}."])
        kinds.extend(["paragraph", "unknown", "paragraph"])
        layouts.extend([body_layout, edge_layout, body_layout])
        locators.extend([{"page_index": page_index}] * 3)
        boundaries.extend([("\n", "visual_line"), ("\n", "visual_line")])
    canonical_text, ledger = build_ledger(
        texts,
        source_format="pdf",
        kinds=kinds,
        boundaries=boundaries,
        layouts=layouts,
        locators=locators,
        origins=["layout"] * len(texts),
        structure_quality="geometry_full",
    )

    analysis = cleanup_analysis_service.analyze_cleanup(canonical_text, ledger)
    cleaned_text, metadata = cleanup_renderer_service.render_cleanup(
        canonical_text,
        ledger,
        analysis["unit_operations"],
        analysis["boundaries"],
    )

    assert metadata["quality_report"]["introduced_fusion_count"] == 0
    assert "0continues" not in cleaned_text
    assert "1continues" not in cleaned_text
    assert "2continues" not in cleaned_text
    assert "3continues" not in cleaned_text
    assert cleaned_text == (
        "Narrative left 0 continues right 0.\n\n"
        "Narrative left 1 continues right 1.\n\n"
        "Narrative left 2 continues right 2.\n\n"
        "Narrative left 3 continues right 3.\n"
    )


@pytest.mark.parametrize(
    ("artifact_only_page", "with_header"),
    [(0, False), (2, False), (5, False), (2, True)],
)
def test_cleanup_preserves_artifact_only_pages(
    tmp_path,
    artifact_only_page,
    with_header,
) -> None:
    """
    @brief Cover REQ-FUNC-51ecd895 through Cleanup publication and strict reload.
    @details Keep number-only and header/footer-only pages at document edges
             or between narrative pages while enforcing whole-page safety.
    @param[in] tmp_path Isolated project directory supplied by pytest.
    @param[in] artifact_only_page Page with no narrative text.
    @param[in] with_header Include a repeated header alongside each page number.
    """
    texts = []
    layouts = []
    locators = []
    protected_indexes = []
    artifact_indexes = []
    for page_index in range(6):
        page_items = []
        if with_header:
            page_items.append(("Running header", 0.05, True))
        if page_index != artifact_only_page:
            page_items.append((f"Narrative on page {page_index + 1}.", 0.5, False))
        page_items.append((str(page_index + 1), 0.98, True))
        for text, position, is_artifact in page_items:
            if is_artifact:
                artifact_indexes.append(len(texts))
            if page_index == artifact_only_page:
                protected_indexes.append(len(texts))
            texts.append(text)
            layouts.append({"relative_vertical_position": position})
            locators.append({"page_index": page_index})
    boundaries = [
        ("\n\n\f\n\n", "page")
        if left["page_index"] != right["page_index"]
        else ("\n", "visual_line")
        for left, right in zip(locators, locators[1:], strict=False)
    ]
    canonical_text, ledger = build_ledger(
        texts,
        source_format="pdf",
        boundaries=boundaries,
        layouts=layouts,
        locators=locators,
        origins=["layout"] * len(texts),
        structure_quality="geometry_full",
    )
    project_root, manifest = build_project(
        tmp_path, "ArtifactOnlyPage", canonical_text, ledger,
    )

    document = text_cleanup_service.clean_text(project_root, manifest)

    assert document["status"] == "completed"
    assert document["phase"] == "done"
    assert text_cleanup_service.load_cleanup_document(project_root) == document
    cleaned_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    protected_ids = {ledger["units"][index]["unit_id"] for index in protected_indexes}
    expected_drops = {
        ledger["units"][index]["unit_id"]
        for index in artifact_indexes
        if index not in protected_indexes
    }
    assert {
        item["target_id"] for item in document["unit_operations"]
        if item["action"] == "drop_page_artifact"
    } == expected_drops
    assert {
        item["target_id"]: item["role"]
        for item in document["unit_operations"]
        if item["action"] == "set_role" and item["target_id"] in protected_ids
    } == dict.fromkeys(protected_ids, "page_artifact")
    retained_artifact_text = (
        f"Running header {artifact_only_page + 1}"
        if with_header else str(artifact_only_page + 1)
    )
    assert retained_artifact_text in cleaned_text.splitlines()
    assert cleaned_text.count("Running header") == int(with_header)
    for page_index in range(6):
        if page_index != artifact_only_page:
            assert f"Narrative on page {page_index + 1}." in cleaned_text
            assert str(page_index + 1) not in cleaned_text.splitlines()

    # A caller-supplied deletion must still be rejected by the independent guard.
    unsafe_operations = [
        *document["unit_operations"],
        *[
            {"action": "drop_page_artifact", "target_id": target_id}
            for target_id in protected_ids
        ],
    ]
    with pytest.raises(
        cleanup_renderer_service.CleanupRenderError,
        match="may not remove every text unit on a page",
    ):
        cleanup_renderer_service.render_cleanup(
            canonical_text, ledger, unsafe_operations, document["boundaries"],
        )

    # A checkpoint written by the older policy must be rebuilt on retry.
    document["unit_operations"] = unsafe_operations
    document["status"] = "finalizing"
    document["phase"] = "rendering"
    (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).write_text(
        json.dumps(document), encoding="utf-8",
    )
    recovered = text_cleanup_service.clean_text(project_root, manifest)
    assert recovered["status"] == "completed"
    assert text_cleanup_service.load_cleanup_document(project_root) == recovered
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8") == cleaned_text


def test_non_native_verse_uses_semantic_line_breaks_and_excludes_dialogue() -> None:
    """@brief Cover S-0003/S-0004 and REQ-FUNC-8034d33d-df7f-412f-ae51-45e3dc8cb017."""
    canonical_text, ledger = build_ledger(
        [
            "The moon is low",
            "The river holds its light",
            "A quiet road",
            "— This is dialogue.",
            "— This is an answer.",
            "— This closes the exchange.",
        ],
        kinds=["unknown"] * 6,
        boundaries=[
            ("\n", "physical_line"),
            ("\n", "physical_line"),
            ("\n\n", "blank_paragraph"),
            ("\n", "physical_line"),
            ("\n", "physical_line"),
        ],
        structure_quality="text_only",
    )

    analysis = cleanup_analysis_service.analyze_cleanup(canonical_text, ledger)

    assert [item["left_role"] for item in analysis["boundaries"][:3]] == [
        "verse",
        "verse",
        "verse",
    ]
    assert [item["final"]["choice"] for item in analysis["boundaries"][:2]] == [
        "set_semantic_line_break",
        "set_semantic_line_break",
    ]
    assert all(item["left_role"] != "verse" for item in analysis["boundaries"][3:])


@pytest.mark.parametrize("text", ["这是一本中文书。" * 20, "이것은 한국어 책입니다." * 20])
def test_cleanup_rejects_predominantly_cjk_or_hangul(text, tmp_path) -> None:
    """@brief Cover S-0005 and REQ-FUNC-ff2e2c94-93ef-4e77-89e9-4bc0f69a72aa."""
    canonical_text, ledger = build_ledger([text])
    project_root, manifest = build_project(tmp_path, "UnsupportedScript", canonical_text, ledger)

    with pytest.raises(ValueError, match="Latin and Cyrillic.*CJK or Hangul"):
        text_cleanup_service.clean_text(project_root, manifest)

    assert not (project_root / config.CLEANED_TEXT_FILE_NAME).exists()


def test_cleanup_supported_languages_are_exactly_the_approved_eight() -> None:
    """
    @brief      Verify Cleanup exposes exactly the approved source-content languages.
    @details    Covers S-0001 and REQ-FUNC-b86a4cb0-a3a5-475d-aaa9-b6cb51aa1ed8.
    @return     None.
    @exception  None.
    """
    assert config.CLEANUP_SUPPORTED_SOURCE_LANGUAGES == ("en", "ro", "de", "fr", "ru", "pt", "es", "it")


@pytest.mark.parametrize(
    ("detected_language", "expected_warning"),
    [
        *((language, None) for language in config.CLEANUP_SUPPORTED_SOURCE_LANGUAGES),
        (
            "el",
            "Detected source language 'el' is outside the supported Cleanup languages; "
            "review the result carefully.",
        ),
        (None, None),
    ],
)
def test_cleanup_persists_one_warning_only_for_detected_unsupported_language(
    tmp_path,
    monkeypatch,
    detected_language: str | None,
    expected_warning: str | None,
) -> None:
    """@brief Verify supported and unavailable detection do not receive an unsupported-language warning."""
    canonical_text, ledger = build_ledger(["A reviewable paragraph."])
    project_root, manifest = build_project(tmp_path, "LanguageWarning", canonical_text, ledger)
    monkeypatch.setattr(
        cleanup_text_analysis_service,
        "detect_language",
        lambda _text: detected_language,
    )

    document = text_cleanup_service.clean_text(project_root, manifest)

    assert document["document_profile"]["language"] == detected_language
    assert document["warnings"] == ([] if expected_warning is None else [expected_warning])
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8") == (
        "A reviewable paragraph.\n"
    )
    saved_manifest = project_workspace_service.load_manifest(project_root)
    assert saved_manifest["operations"]["cleanup"]["warning_count"] == len(document["warnings"])
    state = text_cleanup_state_service.build_text_cleanup_state(project_root, saved_manifest, "en")
    assert (expected_warning in state["notes"]) if expected_warning else all(
        "outside the supported Cleanup languages" not in note for note in state["notes"]
    )


def test_cleanup_unsupported_language_warning_survives_resume_and_finalization(
    tmp_path,
    monkeypatch,
) -> None:
    """@brief Verify the warning survives cancelled AI resume and rerendering without duplication."""
    canonical_text, ledger = build_ledger(["One wrapped line", "continues safely."])
    project_root, manifest = build_project(tmp_path, "LanguageWarningRecovery", canonical_text, ledger)
    monkeypatch.setattr(cleanup_text_analysis_service, "detect_language", lambda _text: "el")
    calls: list[int] = []

    def _adjudicate(questions, profile_payload, **_kwargs):
        """@brief Return controlled adjudication records for the checkpoint fixture."""
        calls.append(len(questions))
        if len(calls) == 1:
            raise operation_runtime_service.OperationCancelledError()
        batches = cleanup_ai_adjudication_service.plan_question_batches(questions, profile_payload)
        return {
            "operations": [],
            "answers": [
                {
                    "question_id": str(question["question_id"]),
                    "primary_choice": None,
                    "verifier_choice": None,
                    "accepted": False,
                    "final_choice": str(question["prior_choice"]),
                    "state": "fallback",
                }
                for question in questions
            ],
            "warnings": [],
            "token_usage": token_usage_service.empty_token_usage(),
            "failed_batch_count": 0,
            "batch_order": [
                [str(question["target_id"]) for question in batch]
                for batch in batches
            ],
            "estimated_request_count": len(batches) * 2,
        }

    monkeypatch.setattr(cleanup_ai_adjudication_service, "adjudicate_questions", _adjudicate)
    profile = make_profile()

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        text_cleanup_service.clean_text(project_root, manifest, ai_profile_payload=profile)

    paused = read_cleanup_document(project_root)
    assert paused["warnings"] == [
        "Detected source language 'el' is outside the supported Cleanup languages; review the result carefully."
    ]

    completed = text_cleanup_service.clean_text(project_root, manifest, ai_profile_payload=profile)
    checkpoint = dict(completed)
    checkpoint["status"] = "finalizing"
    checkpoint["phase"] = "rendering"
    checkpoint["completed_at"] = None
    (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    finalized = text_cleanup_service.clean_text(project_root, manifest, ai_profile_payload=profile)

    assert completed["warnings"] == finalized["warnings"] == [
        "Detected source language 'el' is outside the supported Cleanup languages; review the result carefully."
    ]
    assert calls == [1, 1]


def test_cleanup_without_usable_ai_completes_from_deterministic_priors(tmp_path) -> None:
    """@brief Cover S-0005 and REQ-FUNC-26df5531-3acf-4c18-98ab-06d4e79112eb."""
    canonical_text, ledger = build_ledger(["One wrapped line", "continues safely."])
    project_root, manifest = build_project(tmp_path, "NoUsableAi", canonical_text, ledger)

    document = text_cleanup_service.clean_text(
        project_root,
        manifest,
        ai_profile_payload=make_profile(context_window=8_192),
    )

    assert document["status"] == "completed"
    assert document["quality_report"]["fallback_count"] >= 1
    assert document["progress"]["batch_order"] == []
    assert document["progress"]["estimated_request_count"] == 0
    assert document["quality_report"]["introduced_fusion_count"] == 0
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8") == (
        "One wrapped line continues safely.\n"
    )


@pytest.mark.parametrize("configured_context", [16_384, 65_536])
def test_mixed_type_multi_batch_plan_survives_cancel_and_resume(
    tmp_path,
    monkeypatch,
    configured_context,
) -> None:
    """@brief Checkpoint batches remain identical to runtime requests across resume."""
    canonical_text, ledger = build_ledger(
        [
            "Line-" if index % 3 == 0 else f"Line {index}"
            for index in range(14)
        ]
    )
    project_root, manifest = build_project(
        tmp_path,
        "MixedTypePlanResume",
        canonical_text,
        ledger,
    )
    captured_questions = list(
        cleanup_analysis_service.analyze_cleanup(
            canonical_text,
            ledger,
        )["questions"]
    )
    prior_by_question = {
        str(item["question_id"]): str(item["prior_choice"])
        for item in captured_questions
    }

    calls: list[tuple[str, list[str]]] = []
    cancel = {"value": False}

    def _chat_json(_profile, _system, user_prompt, **kwargs):
        """@brief Return deterministic schema answers for the test request."""
        payload = json.loads(user_prompt)
        assert kwargs["log_context"]["pass"] == "primary"
        question_ids = [
            str(item["question_id"])
            for item in payload["questions"]
        ]
        calls.append((str(payload["batch_id"]), question_ids))
        if len(calls) == 1:
            cancel["value"] = True
        return {
            "payload": {
                "batch_id": payload["batch_id"],
                "answers": [
                    {
                        "question_id": question_id,
                        "choice": prior_by_question[question_id],
                    }
                    for question_id in question_ids
                ],
            },
            "usage": {},
        }

    monkeypatch.setattr(
        "audiomancer.services.cleanup_ai_adjudication_service."
        "llm_provider_service.chat_json",
        _chat_json,
    )
    profile = make_profile(context_window=configured_context)
    profile.update(
        discovered_context_model_name=profile["model_name"],
        server_context_window=16_384,
    )
    initial_progress: list[tuple[int, int, int]] = []
    with pytest.raises(operation_runtime_service.OperationCancelledError):
        text_cleanup_service.clean_text(
            project_root,
            manifest,
            ai_profile_payload=profile,
            progress_callback=lambda current, total, percent, _message: initial_progress.append(
                (current, total, percent)
            ),
            cancel_requested=lambda: cancel["value"],
        )

    paused = read_cleanup_document(project_root)
    assert paused["profile_fingerprint"]["context_window"] == 16_384
    planned_batches = (
        cleanup_ai_adjudication_service.plan_question_batches(
            captured_questions,
            profile,
        )
    )
    planned_targets = [
        [str(item["target_id"]) for item in batch]
        for batch in planned_batches
    ]
    assert paused["progress"]["batch_order"] == planned_targets
    cancel["value"] = False
    resumed_progress: list[tuple[int, int, int]] = []

    completed = text_cleanup_service.clean_text(
        project_root,
        manifest,
        ai_profile_payload=profile,
        progress_callback=lambda current, total, percent, _message: resumed_progress.append(
            (current, total, percent)
        ),
        cancel_requested=lambda: False,
    )

    target_by_question = {
        str(item["question_id"]): str(item["target_id"])
        for item in captured_questions
    }
    runtime_targets = [
        [target_by_question[question_id] for question_id in question_ids]
        for _batch_id, question_ids in calls
    ]
    assert runtime_targets == planned_targets
    assert [batch_id for batch_id, _question_ids in calls] == [
        f"cleanup-batch-{index:04d}"
        for index in range(1, len(planned_targets) + 1)
    ]
    assert completed["progress"]["batch_order"] == planned_targets
    assert completed["progress"]["completed_request_count"] == len(calls)
    assert resumed_progress[0][2] == initial_progress[-1][2]
    combined_percentages = [
        *(item[2] for item in initial_progress),
        *(item[2] for item in resumed_progress),
    ]
    assert combined_percentages == sorted(combined_percentages)
    assert all(current <= total for current, total, _percent in resumed_progress)


def test_recursive_split_resume_expands_durable_request_total(
    tmp_path,
    monkeypatch,
) -> None:
    """@brief Split child requests are counted once across cancellation and resume."""
    canonical_text, ledger = build_ledger([f"Line {index}" for index in range(5)])
    project_root, manifest = build_project(
        tmp_path,
        "RecursiveSplitResume",
        canonical_text,
        ledger,
    )
    calls: list[str] = []
    cancel = {"value": False}

    def _ask(
        _profile,
        _batch_id,
        questions,
        *,
        verifier,
        log_path,
        cancel_requested,
        submission_callback=None,
    ):
        """@brief Inject controlled responses and cancellation or context splitting."""
        _ = verifier, log_path, cancel_requested, submission_callback
        if len(questions) > 1:
            raise cleanup_ai_adjudication_service.ContextBudgetExceededError(
                "split"
            )
        question_id = str(questions[0]["question_id"])
        calls.append(question_id)
        if len(calls) == 1:
            cancel["value"] = True
        return (
            [
                {
                    "question_id": question_id,
                    "choice": str(questions[0]["prior_choice"]),
                }
            ],
            {},
        )

    monkeypatch.setattr(cleanup_ai_adjudication_service, "_ask", _ask)
    profile = make_profile(context_window=16_384)
    initial_progress: list[tuple[int, int, int]] = []
    with pytest.raises(operation_runtime_service.OperationCancelledError):
        text_cleanup_service.clean_text(
            project_root,
            manifest,
            ai_profile_payload=profile,
            progress_callback=lambda current, total, percent, _message: initial_progress.append(
                (current, total, percent)
            ),
            cancel_requested=lambda: cancel["value"],
        )
    paused = read_cleanup_document(project_root)
    assert paused["progress"]["completed_request_count"] == 1
    assert paused["progress"]["estimated_request_count"] == 2
    cancel["value"] = False
    resumed_progress: list[tuple[int, int, int]] = []

    completed = text_cleanup_service.clean_text(
        project_root,
        manifest,
        ai_profile_payload=profile,
        progress_callback=lambda current, total, percent, _message: resumed_progress.append(
            (current, total, percent)
        ),
        cancel_requested=lambda: False,
    )

    assert calls == ["q-000001", "q-000002", "q-000003", "q-000004"]
    assert completed["progress"]["completed_request_count"] == 4
    assert completed["progress"]["estimated_request_count"] == 4
    assert resumed_progress[0][2] == initial_progress[-1][2]
    assert all(current <= total for current, total, _percent in resumed_progress)
    combined_percentages = [
        *(item[2] for item in initial_progress),
        *(item[2] for item in resumed_progress),
    ]
    assert combined_percentages == sorted(combined_percentages)
    assert resumed_progress[-1][2] == 100


def _manifest(project_root):
    """@brief Load the current project manifest for checkpoint run-path tests."""
    return project_workspace_service.load_manifest(project_root)


def test_cancel_persists_paused_checkpoint_and_exact_resume_skips_completed_requests(
    tmp_path,
    monkeypatch,
) -> None:
    """@brief Cover S-0007 and REQ-NFR-5425de7d-350c-4377-86fa-89225619be7e."""
    canonical_text, ledger = build_ledger(
        ["First ambiguous line", "continues here", "Second ambiguous line", "continues too."],
    )
    project_root, manifest = build_project(tmp_path, "ResumeSameProfile", canonical_text, ledger)
    calls: list[tuple[str, str]] = []
    initial_progress: list[tuple[int, int, int, str]] = []
    resumed_progress: list[tuple[int, int, int, str]] = []
    cancel = {"value": False}

    def _chat_json(_profile, _system, user_prompt, **kwargs):
        """@brief Return deterministic schema answers for the test request."""
        payload = json.loads(user_prompt)
        calls.append((str(payload["batch_id"]), str(kwargs["log_context"]["pass"])))
        answers = [
            {"question_id": item["question_id"], "choice": "set_paragraph_break"}
            for item in payload["questions"]
        ]
        cancel["value"] = True
        return {"payload": {"batch_id": payload["batch_id"], "answers": answers}, "usage": {}}

    monkeypatch.setattr(
        "audiomancer.services.cleanup_ai_adjudication_service.llm_provider_service.chat_json",
        _chat_json,
    )
    with pytest.raises(operation_runtime_service.OperationCancelledError):
        text_cleanup_service.clean_text(
            project_root,
            manifest,
            ai_profile_payload=make_profile(context_window=16_384),
            progress_callback=lambda current, total, percent, message: initial_progress.append(
                (current, total, percent, message)
            ),
            cancel_requested=lambda: cancel["value"],
        )

    paused = read_cleanup_document(project_root)
    assert paused["status"] == "paused"
    assert paused["progress"]["completed_request_count"] == 1
    first_call_count = len(calls)
    cancel["value"] = False

    completed = text_cleanup_service.clean_text(
        project_root,
        manifest,
        ai_profile_payload=make_profile(context_window=16_384),
        progress_callback=lambda current, total, percent, message: resumed_progress.append(
            (current, total, percent, message)
        ),
        cancel_requested=lambda: False,
    )

    assert completed["status"] == "completed"
    assert calls[0][1] == "primary"
    assert calls[first_call_count][1] == "verifier"
    assert len(calls) == completed["progress"]["completed_request_count"]
    assert resumed_progress[0][2] == initial_progress[-1][2]
    combined_percentages = [
        *(item[2] for item in initial_progress),
        *(item[2] for item in resumed_progress),
    ]
    assert combined_percentages == sorted(combined_percentages)
    assert resumed_progress[-1][2] == 100


def test_changed_model_reuses_analysis_but_restarts_all_ai_decisions(tmp_path, monkeypatch) -> None:
    """@brief Cover S-0007 and REQ-NFR-5425de7d-350c-4377-86fa-89225619be7e."""
    canonical_text, ledger = build_ledger(["One ambiguous line", "continues here."])
    project_root, manifest = build_project(tmp_path, "ResumeChangedModel", canonical_text, ledger)
    analysis_calls = {"count": 0}
    original_analyze = cleanup_analysis_service.analyze_cleanup
    requested_models: list[str] = []
    cancel = {"value": False}

    def _count_analysis(*args, **kwargs):
        """@brief Count real analysis calls to verify checkpoint reuse."""
        analysis_calls["count"] += 1
        return original_analyze(*args, **kwargs)

    def _chat_json(profile, _system, user_prompt, **_kwargs):
        """@brief Return deterministic schema answers for the test request."""
        requested_models.append(str(profile["model_name"]))
        payload = json.loads(user_prompt)
        answers = [
            {"question_id": item["question_id"], "choice": "set_paragraph_break"}
            for item in payload["questions"]
        ]
        cancel["value"] = True
        return {"payload": {"batch_id": payload["batch_id"], "answers": answers}, "usage": {}}

    monkeypatch.setattr(cleanup_analysis_service, "analyze_cleanup", _count_analysis)
    monkeypatch.setattr(
        "audiomancer.services.cleanup_ai_adjudication_service.llm_provider_service.chat_json",
        _chat_json,
    )
    with pytest.raises(operation_runtime_service.OperationCancelledError):
        text_cleanup_service.clean_text(
            project_root,
            manifest,
            ai_profile_payload=make_profile(model_name="qwen3.5-9b", context_window=16_384),
            cancel_requested=lambda: cancel["value"],
        )
    cancel["value"] = False
    text_cleanup_service.clean_text(
        project_root,
        manifest,
        ai_profile_payload=make_profile(model_name="qwen3.6-27b", context_window=32_768),
        cancel_requested=lambda: False,
    )

    assert analysis_calls["count"] == 1
    assert requested_models.count("qwen3.6-27b") >= 1
    assert all(
        item["adjudication"]["primary_choice"] is not None
        for item in read_cleanup_document(project_root)["boundaries"]
        if item["adjudication"]["state"] == "completed"
    )


def test_finalizing_recovery_renders_without_an_llm_call(tmp_path, monkeypatch) -> None:
    """@brief Cover S-0008 and REQ-FUNC-d6c69fe1-830e-4cbd-8278-26f24737b6f2."""
    canonical_text, ledger = build_ledger(["One wrapped line", "continues safely."])
    project_root, manifest = build_project(tmp_path, "FinalizingRecovery", canonical_text, ledger)
    completed = text_cleanup_service.clean_text(project_root, manifest)
    checkpoint = dict(completed)
    checkpoint["status"] = "finalizing"
    checkpoint["phase"] = "rendering"
    checkpoint["completed_at"] = None
    (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_root / config.CLEANED_TEXT_FILE_NAME).unlink()

    monkeypatch.setattr(
        "audiomancer.services.cleanup_ai_adjudication_service.llm_provider_service.chat_json",
        lambda *_args, **_kwargs: pytest.fail("Finalizing recovery must not call an LLM."),
    )
    recovered = text_cleanup_service.clean_text(
        project_root,
        manifest,
        ai_profile_payload=make_profile(),
    )

    assert recovered["status"] == "completed"
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).is_file()


@pytest.mark.parametrize("artifact_state", ["missing", "mismatched"])
def test_completed_cleanup_rerenders_when_output_missing_or_mismatched(
    tmp_path,
    monkeypatch,
    artifact_state,
) -> None:
    """@brief Cover S-0003 and REQ-FUNC-d6c69fe1-830e-4cbd-8278-26f24737b6f2."""
    canonical_text, ledger = build_ledger(["One wrapped line", "continues safely."])
    project_root, manifest = build_project(
        tmp_path,
        f"CompletedOutputRecovery-{artifact_state}",
        canonical_text,
        ledger,
    )
    completed = text_cleanup_service.clean_text(project_root, manifest)
    cleaned_path = project_root / config.CLEANED_TEXT_FILE_NAME
    expected_text = cleaned_path.read_text(encoding="utf-8")
    if artifact_state == "missing":
        cleaned_path.unlink()
    else:
        cleaned_path.write_text("stale output\n", encoding="utf-8")

    monkeypatch.setattr(
        "audiomancer.services.cleanup_ai_adjudication_service.llm_provider_service.chat_json",
        lambda *_args, **_kwargs: pytest.fail("Completed-output recovery must not call an LLM."),
    )

    recovered = text_cleanup_service.clean_text(project_root, manifest)

    assert recovered["status"] == "completed"
    assert recovered["output_hash"] == completed["output_hash"]
    assert cleaned_path.read_text(encoding="utf-8") == expected_text


def test_manual_whitespace_and_lexical_edits_keep_truthful_structure(tmp_path) -> None:
    """@brief Cover S-0009 and REQ-FUNC-807c56f0-12b7-42e9-bd8f-0d562c903e70."""
    canonical_text, ledger = build_ledger(
        ["First paragraph.", "Second paragraph."],
        kinds=["paragraph", "paragraph"],
        boundaries=[("\n\n", "native_paragraph")],
        origins=["native", "native"],
        structure_quality="native",
    )
    project_root, manifest = build_project(tmp_path, "ManualEdits", canonical_text, ledger)
    text_cleanup_service.clean_text(project_root, manifest)
    chunk_path = project_root / config.CHUNK_ARTIFACT_FILE_NAME
    chunk_path.write_text('{"status":"completed"}\n', encoding="utf-8")

    whitespace = text_cleanup_service.save_user_cleaned_text(
        project_root,
        "First paragraph.\n\n\nSecond paragraph.\n",
    )

    assert whitespace["structure_source"] == "cleanup_roles"
    assert [item["source_unit_ids"] for item in whitespace["paragraphs"]] == [
        [str(ledger["units"][0]["unit_id"])],
        [str(ledger["units"][1]["unit_id"])],
    ]
    assert not chunk_path.exists()

    lexical = text_cleanup_service.save_user_cleaned_text(
        project_root,
        "Corrected first paragraph.\n\nSecond paragraph.\n",
    )

    assert lexical["user_modified"] is True
    assert lexical["structure_source"] == "user_edited"
    assert lexical["paragraphs"][0]["source_unit_ids"] == []
    assert [item["provenance_available"] for item in lexical["paragraphs"]] == [False, True]
    assert lexical["paragraphs"][1]["source_unit_ids"] == whitespace["paragraphs"][1]["source_unit_ids"]


def test_user_edited_cleanup_reclassifies_only_explicit_scene_separators(tmp_path) -> None:
    """@brief Cover S-0015 and REQ-FUNC-ecb1e86f-7899-4734-8432-db376f8c7b99."""
    canonical_text, ledger = build_ledger(
        ["Opening narration.", "Closing narration."],
        boundaries=[("\n\n", "native_paragraph")],
    )
    project_root, manifest = build_project(tmp_path, "EditedSceneBreak", canonical_text, ledger)
    text_cleanup_service.clean_text(project_root, manifest)

    edited = text_cleanup_service.save_user_cleaned_text(
        project_root,
        "Opening narration.\n\n* * *\n\n...\n\nClosing narration.\n",
    )

    assert edited["structure_source"] == "user_edited"
    assert [item["role"] for item in edited["paragraphs"]] == [
        "body",
        "scene_separator",
        "body",
        "body",
    ]
    assert [item["provenance_available"] for item in edited["paragraphs"]] == [True, False, False, True]

    whitespace_realign = text_cleanup_service.save_user_cleaned_text(
        project_root,
        "Opening narration.\n\n\n* * *\n\n...\n\nClosing narration.\n",
    )
    assert [item["role"] for item in whitespace_realign["paragraphs"]] == [
        "body",
        "scene_separator",
        "body",
        "body",
    ]


def test_online_disclosure_metrics_do_not_persist_fragments_or_secrets(
    tmp_path,
    monkeypatch,
) -> None:
    """@brief Cover S-0007/S-0012 and the Cleanup data-privacy requirements."""
    canonical_text, ledger = build_ledger(
        ["Private line", "continues safely across a much longer source line."]
    )
    project_root, manifest = build_project(
        tmp_path,
        "OnlineDisclosure",
        canonical_text,
        ledger,
    )
    profile = make_profile()
    profile["backend_kind"] = config.ONLINE_AI_BACKEND_KIND
    profile["api_key"] = "test-api-key-must-not-persist"

    def _chat_json(_profile, _system, user_prompt, **_kwargs):
        """@brief Return deterministic schema answers for the test request."""
        request = json.loads(user_prompt)
        return {
            "payload": {
                "batch_id": request["batch_id"],
                "answers": [
                    {
                        "question_id": item["question_id"],
                        "choice": "join_with_space",
                    }
                    for item in request["questions"]
                ],
            },
            "usage": {},
        }

    monkeypatch.setattr(
        "audiomancer.services.cleanup_ai_adjudication_service."
        "llm_provider_service.chat_json",
        _chat_json,
    )

    document = text_cleanup_service.clean_text(
        project_root,
        manifest,
        ai_profile_payload=profile,
    )
    persisted = (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).read_text(
        encoding="utf-8"
    )

    assert document["quality_report"]["online_backend"] == (
        config.ONLINE_AI_BACKEND_KIND
    )
    assert document["quality_report"]["online_fragment_count"] == 1
    assert profile["api_key"] not in persisted
    assert "Private line" not in persisted
    assert "api_key" not in document["profile_fingerprint"]
    assert "base_url" not in document["profile_fingerprint"]


def test_online_disclosure_counts_failed_submission_attempts(
    tmp_path,
    monkeypatch,
) -> None:
    """@brief Cover S-0012 and the online-fragment disclosure requirement."""
    canonical_text, ledger = build_ledger(
        ["Private line", "continues safely across a much longer source line."]
    )
    project_root, manifest = build_project(
        tmp_path,
        "OnlineFailureDisclosure",
        canonical_text,
        ledger,
    )
    profile = make_profile()
    profile["backend_kind"] = config.ONLINE_AI_BACKEND_KIND
    monkeypatch.setattr(
        "audiomancer.services.cleanup_ai_adjudication_service."
        "llm_provider_service.chat_json",
        lambda *_args, **_kwargs: {
            "payload": {"invalid": True},
            "usage": {},
        },
    )

    document = text_cleanup_service.clean_text(
        project_root,
        manifest,
        ai_profile_payload=profile,
    )

    assert document["quality_report"]["failed_batch_count"] == 1
    assert document["quality_report"]["online_backend"] == (
        config.ONLINE_AI_BACKEND_KIND
    )
    assert document["quality_report"]["online_fragment_count"] == 2
    assert document["progress"]["completed_request_count"] == 0


def test_ai_reset_clears_replaced_manual_edit_provenance(tmp_path) -> None:
    """@brief Verify fresh AI adjudication no longer presents overwritten output as user-authored."""
    _project_root, document = _build_completed_cleanup(tmp_path)
    document["user_modified"] = True
    document["structure_source"] = "user_edited"

    text_cleanup_service._reset_ai_adjudication(document, None, "prompt-hash", questions=[])  # noqa: SLF001

    assert document["user_modified"] is False
    assert document["structure_source"] == "cleanup_roles"


# END OF FILE
