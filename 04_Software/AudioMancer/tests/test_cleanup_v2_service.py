#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
"""Behavior tests for the source-ledger Cleanup V2 pipeline."""

from pathlib import Path

import pytest

from audiomancer import config
from audiomancer.services import (
    cleanup_ai_adjudication_service,
    cleanup_analysis_service,
    cleanup_renderer_service,
    project_workspace_service,
    source_ledger_service,
    text_cleanup_service,
    text_extraction_service,
)


def test_cleanup_without_ai_preserves_uncertain_ascii_hyphenation(tmp_path) -> None:
    """An unavailable AI profile must preserve uncertain source and still pass."""
    project_root, manifest = _project_with_text(
        tmp_path,
        "HyphenFallback",
        "This physical line ends with an uncertain hyphen-\ncontinuation remains source text.",
    )
    text_extraction_service.extract_text(project_root, manifest)

    document = text_cleanup_service.clean_text(project_root, manifest)

    cleaned_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert "hyphen-\ncontinuation" in cleaned_text
    assert document["validation_state"] == "passed_with_warnings"
    assert document["uncertainty_count"] == 1
    assert document["profile_fingerprint"] is None
    assert project_workspace_service.load_manifest(project_root)["current_stage"] == "text_chunking_ready"
    assert text_cleanup_service.load_cleanup_document(project_root) == document


def test_renderer_dehyphenates_without_accepting_replacement_text() -> None:
    """Renderer operations may only reference existing source units or boundaries."""
    builder = source_ledger_service.CanonicalDocumentBuilder(
        source_format="txt",
        source_sha256="source",
    )
    builder.add(source_ledger_service.SourceEvent("inter-", boundary_before=None))
    builder.add(source_ledger_service.SourceEvent("national", boundary_before="\n"))
    canonical_text, ledger = builder.build()
    boundary_id = ledger["boundaries"][0]["boundary_id"]

    cleaned_text, _metadata = cleanup_renderer_service.render_cleanup(
        canonical_text,
        ledger,
        [
            {
                "operation_id": "op-000001",
                "action": "dehyphenate",
                "target_id": boundary_id,
                "evidence": "test",
            }
        ],
    )

    assert cleaned_text == "international\n"
    with pytest.raises(cleanup_renderer_service.CleanupRenderError, match="Unsupported"):
        cleanup_renderer_service.render_cleanup(
            canonical_text,
            ledger,
            [
                {
                    "operation_id": "op-000001",
                    "action": "replace_text",
                    "target_id": "u-000001",
                    "replacement": "invented",
                }
            ],
        )


def test_ai_adjudication_requires_primary_and_blind_verifier_agreement(monkeypatch) -> None:
    """Only identical strict answers from both passes become Cleanup operations."""
    calls: list[dict[str, object]] = []

    def _chat_json(_profile, _system, _user, **kwargs):
        calls.append(kwargs)
        return {
            "payload": {
                "batch_id": "cleanup-batch-0001",
                "answers": [{"question_id": "q-000001", "choice": "dehyphenate"}],
            },
            "usage": {
                "input_tokens": 10,
                "output_tokens": 2,
                "total_tokens": 12,
                "usage_available": True,
            },
        }

    monkeypatch.setattr(cleanup_ai_adjudication_service.llm_provider_service, "chat_json", _chat_json)
    result = cleanup_ai_adjudication_service.adjudicate_questions(
        [
            {
                "question_id": "q-000001",
                "question_type": "hyphenation",
                "target_id": "b-000001",
                "left_text": "inter-",
                "right_text": "national",
                "choices": ["preserve", "dehyphenate"],
            }
        ],
        {
            "id": "local",
            "model_name": "Qwen3.6-27B",
            "context_window": 32_768,
            "supports_structured_output": True,
        },
    )

    assert len(calls) == 2
    assert result["operations"][0]["action"] == "dehyphenate"
    assert result["token_usage"]["total_tokens"] == 24
    assert all(call["require_response_schema"] is True for call in calls)
    assert all(call["allow_unconstrained_fallback"] is False for call in calls)
    assert all(call["allow_model_json_repair"] is False for call in calls)
    assert all(call["max_output_tokens_override"] == 512 for call in calls)


def test_ai_adjudication_reports_each_primary_and_verifier_request(monkeypatch) -> None:
    """SPEC-CLEANUP-PROGRESS-PASSES / REQ-FUNC-663fa24e-b963-4af8-9bbe-dbee3dcab956."""
    progress: list[tuple[int, int, str]] = []

    def _chat_json(_profile, _system, user_prompt, **_kwargs):
        batch_id = __import__("json").loads(user_prompt)["batch_id"]
        return {
            "payload": {
                "batch_id": batch_id,
                "answers": [{"question_id": "q-000001", "choice": "preserve"}],
            },
            "usage": {},
        }

    monkeypatch.setattr(cleanup_ai_adjudication_service.llm_provider_service, "chat_json", _chat_json)
    cleanup_ai_adjudication_service.adjudicate_questions(
        [
            {
                "question_id": "q-000001",
                "question_type": "hyphenation",
                "target_id": "b-000001",
                "left_text": "inter-",
                "right_text": "national",
                "choices": ["preserve", "dehyphenate"],
            }
        ],
        {
            "id": "local",
            "model_name": "Qwen3.6-27B",
            "context_window": 32_768,
            "supports_structured_output": True,
        },
        progress_callback=lambda current, total, message: progress.append(
            (current, total, message)
        ),
    )

    assert progress == [
        (0, 2, "AI Cleanup — Batch 1/1 — Primary request..."),
        (1, 2, "AI Cleanup — Batch 1/1 — Verifier request..."),
        (2, 2, "AI Cleanup — Batch 1/1 — Verified."),
    ]


def test_cleanup_maps_ai_work_to_monotonic_global_progress(tmp_path, monkeypatch) -> None:
    """SPEC-CLEANUP-PROGRESS-MAPPING / REQ-UX-61dacc39-d0e3-453a-8ce9-3820cd5816bf."""
    project_root, manifest = _project_with_text(
        tmp_path,
        "ProgressMapping",
        "A complete paragraph that needs no cleanup.",
    )
    text_extraction_service.extract_text(project_root, manifest)
    progress: list[tuple[int, int, int, str]] = []

    def _adjudicate(_questions, _profile, *, progress_callback, **_kwargs):
        progress_callback(0, 4, "AI Cleanup — Batch 1/2 — Primary request...")
        progress_callback(1, 4, "AI Cleanup — Batch 1/2 — Verifier request...")
        progress_callback(2, 4, "AI Cleanup — Batch 2/2 — Primary request...")
        progress_callback(3, 4, "AI Cleanup — Batch 2/2 — Verifier request...")
        progress_callback(4, 4, "AI Cleanup — Batch 2/2 — Verified.")
        return {
            "operations": [],
            "answers": [],
            "warnings": [],
            "token_usage": {},
        }

    monkeypatch.setattr(
        cleanup_ai_adjudication_service,
        "adjudicate_questions",
        _adjudicate,
    )
    text_cleanup_service.clean_text(
        project_root,
        manifest,
        ai_profile_payload={
            "id": "local",
            "model_name": "Qwen3.6-27B",
            "context_window": 32_768,
            "supports_structured_output": True,
        },
        progress_callback=lambda current, total, percent, message: progress.append(
            (current, total, percent, message)
        ),
    )

    percentages = [item[2] for item in progress]
    assert percentages == sorted(percentages)
    assert percentages[0] == 0
    assert any(0 < percent < 90 for percent in percentages)
    assert percentages[-1] == 100
    assert 100 not in percentages[:-1]
    assert any("Primary request" in item[3] for item in progress)
    assert any("Verifier request" in item[3] for item in progress)


def test_cleanup_without_ai_still_reports_phase_progress(tmp_path) -> None:
    """SPEC-CLEANUP-PROGRESS-MAPPING covers the empty AI-work boundary."""
    project_root, manifest = _project_with_text(
        tmp_path,
        "ProgressWithoutAi",
        "A complete paragraph that needs no cleanup.",
    )
    text_extraction_service.extract_text(project_root, manifest)
    progress: list[tuple[int, int, int, str]] = []

    text_cleanup_service.clean_text(
        project_root,
        manifest,
        progress_callback=lambda current, total, percent, message: progress.append(
            (current, total, percent, message)
        ),
    )

    percentages = [item[2] for item in progress]
    assert percentages == sorted(percentages)
    assert percentages[0] == 0
    assert percentages[-1] == 100
    assert any(0 < percent < 100 for percent in percentages)


def test_pdf_page_artifacts_require_repetition_or_sequence_evidence() -> None:
    """Running headers and page numbers are removed only after cross-page evidence."""
    builder = source_ledger_service.CanonicalDocumentBuilder(
        source_format="pdf",
        source_sha256="pdf-source",
        structure_quality="geometry_full",
        pages=[{"page_index": index} for index in range(6)],
    )
    for page_index in range(6):
        common_layout = {
            "bbox": [10.0, 10.0, 200.0, 20.0],
            "font_signature": "Book:10",
            "relative_vertical_position": 0.02,
            "column": 0,
        }
        builder.add(
            source_ledger_service.SourceEvent(
                "Running Title",
                structure_origin="layout",
                boundary_before="\n\n\f\n\n" if page_index else None,
                boundary_kind="page" if page_index else "visual_line",
                locator={"page_index": page_index},
                layout=common_layout,
            )
        )
        builder.add(
            source_ledger_service.SourceEvent(
                f"Body content for page {page_index + 1}.",
                structure_origin="layout",
                boundary_before="\n",
                boundary_kind="visual_line",
                locator={"page_index": page_index},
                layout={
                    **common_layout,
                    "bbox": [10.0, 100.0, 400.0, 112.0],
                    "relative_vertical_position": 0.5,
                },
            )
        )
        builder.add(
            source_ledger_service.SourceEvent(
                str(page_index + 1),
                structure_origin="layout",
                boundary_before="\n",
                boundary_kind="visual_line",
                locator={"page_index": page_index},
                layout={
                    **common_layout,
                    "bbox": [200.0, 780.0, 210.0, 790.0],
                    "relative_vertical_position": 0.98,
                },
            )
        )
    canonical_text, ledger = builder.build()

    analysis = cleanup_analysis_service.analyze_cleanup(canonical_text, ledger)
    dropped = [
        operation
        for operation in analysis["operations"]
        if operation["action"] == "drop_page_artifact"
    ]

    assert len(dropped) == 12
    assert {operation["evidence"] for operation in dropped} == {
        "repeated_page_edge",
        "sequential_page_number",
    }


def _project_with_text(tmp_path: Path, name: str, text: str):
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text(text, encoding="utf-8")
    manifest["source_document"] = {
        "original_name": source_path.name,
        "stored_relative_path": source_path.name,
        "file_type": "txt",
        "imported_at": "2026-07-27T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    project_workspace_service.save_manifest(manifest, project_root)
    return project_root, manifest
