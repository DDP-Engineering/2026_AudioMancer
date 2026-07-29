#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_cleanup_v2_quality_contract.py
@brief Red-first checks for the approved Cleanup V2 quality contract.
@details Covers the strict two-artifact contract, typed boundaries, protected
         roles, fusion safety, script eligibility, resume, and manual edits.
@author Eng. Dan Dumitru Pasare
@date 2026-07-29
@version 0.2.0
"""

from __future__ import annotations

import json

import pytest

from audiomancer import config
from audiomancer.services import (
    cleanup_analysis_service,
    cleanup_renderer_service,
    operation_runtime_service,
    source_ledger_service,
    text_cleanup_service,
)
from cleanup_v2_test_support import (
    BOUNDARY_CHOICES,
    UNIT_ROLES,
    assert_strict_cleanup_document,
    build_ledger,
    build_project,
    make_profile,
    read_cleanup_document,
)

_RETIRED_CLEANUP_CONFIG_CONSTANTS = (
    "CLEANUP_REPORT_FILE_NAME",
    "CLEANUP_STATE_FILE_NAME",
    "CLEANED_TEXT_METADATA_FILE_NAME",
)


def test_retired_cleanup_artifact_config_constants_are_gone() -> None:
    """Cover S-0007 and REQ-FUNC-50c48e76-aa6a-4a54-840b-ece463309faf."""
    for constant_name in _RETIRED_CLEANUP_CONFIG_CONSTANTS:
        assert not hasattr(config, constant_name), f"{constant_name} must be removed"


def test_cleanup_persists_exactly_one_metadata_file_and_one_text_file(tmp_path) -> None:
    """Cover S-0007/S-0008 and REQ-FUNC-50c48e76-aa6a-4a54-840b-ece463309faf."""
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
    assert not (project_root / "clean_text_metadata.json").exists()
    assert not (project_root / "cleanup_report.json").exists()
    assert not (project_root / "cleanup_state.json").exists()


def test_analysis_assigns_roles_before_classifying_every_boundary() -> None:
    """Cover S-0003/S-0004 and REQ-FUNC-4b0701b7-2967-4a42-aa20-a368ba13a0c0."""
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


def test_join_without_space_is_invalid_everywhere() -> None:
    """Cover S-0001/S-0002 and REQ-FUNC-e42171cc-9c36-4327-87ba-c0f13da05c8c."""
    canonical_text, ledger = build_ledger(["evacuation", "dropships"])
    boundary_id = str(ledger["boundaries"][0]["boundary_id"])

    assert "join_without_space" not in cleanup_renderer_service.ALLOWED_ACTIONS
    analysis = cleanup_analysis_service.analyze_cleanup(canonical_text, ledger)
    serialized = json.dumps(analysis, ensure_ascii=False)
    assert "join_without_space" not in serialized
    with pytest.raises(cleanup_renderer_service.CleanupRenderError, match="join_without_space"):
        cleanup_renderer_service.render_cleanup(
            canonical_text,
            ledger,
            [],
            [
                {
                    "boundary_id": boundary_id,
                    "final": {"choice": "join_without_space"},
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
    """Cover S-0001/S-0002 and REQ-FUNC-6eb73209-e81b-4413-b03e-4f183487618c."""
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
    """Cover S-0003 and the typed-boundary geometry requirements."""
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
    """Cover S-0001/S-0004 and REQ-FUNC-4d57e621-74db-40e7-b9ec-f268dadc431c."""
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


def test_non_native_verse_uses_semantic_line_breaks_and_excludes_dialogue() -> None:
    """Cover S-0003/S-0004 and REQ-FUNC-8034d33d-df7f-412f-ae51-45e3dc8cb017."""
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
    """Cover S-0005 and REQ-FUNC-ff2e2c94-93ef-4e77-89e9-4bc0f69a72aa."""
    canonical_text, ledger = build_ledger([text])
    project_root, manifest = build_project(tmp_path, "UnsupportedScript", canonical_text, ledger)

    with pytest.raises(ValueError, match="Latin and Cyrillic.*CJK or Hangul"):
        text_cleanup_service.clean_text(project_root, manifest)

    assert not (project_root / config.CLEANED_TEXT_FILE_NAME).exists()


def test_cleanup_supported_languages_are_exactly_the_approved_eight() -> None:
    """Cover S-0005 and REQ-FUNC-b86a4cb0-a3a5-475d-aaa9-b6cb51aa1ed8."""
    assert config.SUPPORTED_LANGUAGES == ("en", "ro", "de", "fr", "ru", "pt", "es", "it")


def test_cleanup_without_usable_ai_completes_from_deterministic_priors(tmp_path) -> None:
    """Cover S-0005 and REQ-FUNC-26df5531-3acf-4c18-98ab-06d4e79112eb."""
    canonical_text, ledger = build_ledger(["One wrapped line", "continues safely."])
    project_root, manifest = build_project(tmp_path, "NoUsableAi", canonical_text, ledger)

    document = text_cleanup_service.clean_text(
        project_root,
        manifest,
        ai_profile_payload=make_profile(context_window=8_192),
    )

    assert document["status"] == "completed"
    assert document["quality_report"]["fallback_count"] >= 1
    assert document["quality_report"]["introduced_fusion_count"] == 0
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8") == (
        "One wrapped line continues safely.\n"
    )


def test_cancel_persists_paused_checkpoint_and_exact_resume_skips_completed_requests(
    tmp_path,
    monkeypatch,
) -> None:
    """Cover S-0007 and REQ-NFR-5425de7d-350c-4377-86fa-89225619be7e."""
    canonical_text, ledger = build_ledger(
        ["First ambiguous line", "continues here", "Second ambiguous line", "continues too."],
    )
    project_root, manifest = build_project(tmp_path, "ResumeSameProfile", canonical_text, ledger)
    calls: list[tuple[str, str]] = []
    initial_progress: list[tuple[int, int, int, str]] = []
    resumed_progress: list[tuple[int, int, int, str]] = []
    cancel = {"value": False}

    def _chat_json(_profile, _system, user_prompt, **kwargs):
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
    """Cover S-0007 and REQ-NFR-5425de7d-350c-4377-86fa-89225619be7e."""
    canonical_text, ledger = build_ledger(["One ambiguous line", "continues here."])
    project_root, manifest = build_project(tmp_path, "ResumeChangedModel", canonical_text, ledger)
    analysis_calls = {"count": 0}
    original_analyze = cleanup_analysis_service.analyze_cleanup
    requested_models: list[str] = []
    cancel = {"value": False}

    def _count_analysis(*args, **kwargs):
        analysis_calls["count"] += 1
        return original_analyze(*args, **kwargs)

    def _chat_json(profile, _system, user_prompt, **_kwargs):
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
    """Cover S-0008 and REQ-FUNC-d6c69fe1-830e-4cbd-8278-26f24737b6f2."""
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


def test_manual_whitespace_and_lexical_edits_keep_truthful_structure(tmp_path) -> None:
    """Cover S-0009 and REQ-FUNC-807c56f0-12b7-42e9-bd8f-0d562c903e70."""
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
        "First paragraph.\nSecond paragraph.\n",
    )

    assert whitespace["structure_source"] == "cleanup_roles"
    assert all(item["source_unit_ids"] for item in whitespace["paragraphs"])
    assert not chunk_path.exists()

    lexical = text_cleanup_service.save_user_cleaned_text(
        project_root,
        "Corrected first paragraph.\n\nSecond paragraph.\n",
    )

    assert lexical["user_modified"] is True
    assert lexical["structure_source"] == "user_edited"
    assert all(item["source_unit_ids"] == [] for item in lexical["paragraphs"])
    assert all(item["provenance_available"] is False for item in lexical["paragraphs"])


def test_user_edited_cleanup_reclassifies_only_explicit_scene_separators(tmp_path) -> None:
    """Cover S-0015 and REQ-FUNC-ecb1e86f-7899-4734-8432-db376f8c7b99."""
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
    assert all(item["provenance_available"] is False for item in edited["paragraphs"])

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
    """Cover S-0007/S-0012 and the Cleanup data-privacy requirements."""
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
    """Cover S-0012 and the online-fragment disclosure requirement."""
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


# END OF FILE
