#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_cleanup_service.py
@brief Focused orchestration checks for the approved Cleanup operation.
@details Covers progress, status-copy, source projection, and whitespace role
         realignment through deterministic Chunking.
"""

# IMPORTS

from __future__ import annotations

import json

import pytest

from audiomancer import config
from audiomancer.cleanup import render as cleanup_renderer_service
from audiomancer.services import (
    cleanup_metadata_service,
    deterministic_chunking_service,
    operation_runtime_service,
    project_workspace_service,
    text_cleanup_service,
    text_extraction_service,
)
from cleanup_test_support import build_ledger, build_project

# CONSTANTS

_DOWNSTREAM_ARTIFACT_RELATIVE_PATHS = (
    config.CHUNK_ARTIFACT_FILE_NAME,
    config.TRANSLATED_CHUNKS_FILE_NAME,
    config.CHARACTERS_DOCUMENT_FILE_NAME,
    config.NARRATOR_VOICE_FILE_NAME,
    config.CHARACTER_VOICES_TARGETS_FILE_NAME,
    config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME,
    config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME,
    config.AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME,
    config.AUDIO_ASSEMBLY_REPORT_FILE_NAME,
    config.AUDIO_ASSEMBLY_STATE_FILE_NAME,
    "audio_narator_stale.wav",
    f"{config.AI_TRANSACTION_LOG_FILE_PREFIX}chunking_stale.log",
    f"{config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME}/stale.wav",
    f"{config.AUDIOBOOK_OUTPUT_FOLDER_NAME}/stale.wav",
)
_PRESERVED_OPTION_FIELDS = (
    "project_options_locked",
    "target_language",
    "selected_voice_language",
    "voice_assignment_mode",
    "audio_assembly_settings",
    "notes",
)

# TESTS


def test_cleanup_without_ai_reports_monotonic_phase_progress(tmp_path) -> None:
    """
    @brief      Cover monotonic Cleanup progress without AI.
    """
    canonical_text, ledger = build_ledger(["A wrapped line", "continues safely."])
    project_root, manifest = build_project(tmp_path, "ProgressWithoutAi", canonical_text, ledger)
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
    assert 100 not in percentages[:-1]
    assert any("ambiguous boundaries" in item[3] for item in progress)
    assert any("estimated" in item[3] and "AI requests" in item[3] for item in progress)


def test_automatic_cleanup_publication_invalidates_downstream_state_coherently(
    tmp_path,
) -> None:
    """
    @brief      Verify automatic Cleanup publication resets downstream files and summaries together.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _build_extracted_project(
        tmp_path,
        "AutomaticCleanupInvalidation",
    )
    artifact_paths, preserved_state = _seed_completed_downstream_state(project_root)

    text_cleanup_service.clean_text(project_root, manifest)

    _assert_synchronized_cleanup_transition(
        project_root,
        artifact_paths,
        preserved_state,
    )


def test_manual_cleanup_edit_invalidates_downstream_state_coherently(tmp_path) -> None:
    """
    @brief      Verify manual cleaned-text publication resets downstream files and summaries together.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _build_extracted_project(
        tmp_path,
        "ManualCleanupInvalidation",
    )
    text_cleanup_service.clean_text(project_root, manifest)
    artifact_paths, preserved_state = _seed_completed_downstream_state(project_root)

    text_cleanup_service.save_user_cleaned_text(
        project_root,
        "Operator-edited canonical text.\n",
    )

    assert (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(
        encoding="utf-8"
    ) == "Operator-edited canonical text.\n"
    _assert_synchronized_cleanup_transition(
        project_root,
        artifact_paths,
        preserved_state,
    )


@pytest.mark.parametrize("publication_path", ["automatic", "manual"])
def test_cleanup_publication_surfaces_manifest_persistence_failure(
    tmp_path,
    monkeypatch,
    publication_path: str,
) -> None:
    """
    @brief      Verify both Cleanup publication paths surface a manifest persistence failure.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  publication_path Cleanup publication path under test.
    @return     None.
    @exception  None
    """
    project_root, manifest = _build_extracted_project(
        tmp_path,
        f"CleanupPersistenceFailure{publication_path.title()}",
    )
    if publication_path == "manual":
        text_cleanup_service.clean_text(project_root, manifest)
    _seed_completed_downstream_state(project_root)
    progress: list[int] = []

    def _raise_manifest_failure(*_args, **_kwargs) -> None:
        """@brief Inject a manifest persistence failure before publication."""
        raise OSError("injected manifest persistence failure")

    monkeypatch.setattr(
        project_workspace_service,
        "save_manifest",
        _raise_manifest_failure,
    )

    with pytest.raises(OSError, match="injected manifest persistence failure"):
        if publication_path == "automatic":
            text_cleanup_service.clean_text(
                project_root,
                manifest,
                progress_callback=lambda _current, _total, percent, _message: (
                    progress.append(percent)
                ),
            )
        else:
            text_cleanup_service.save_user_cleaned_text(
                project_root,
                "Operator-edited canonical text.\n",
            )

    assert 100 not in progress


def test_renderer_rejects_unknown_unit_actions() -> None:
    """
    @brief      Cover rejection of unknown unit actions.
    """
    canonical_text, ledger = build_ledger(["Source text."])

    with pytest.raises(cleanup_renderer_service.CleanupRenderError, match="Unsupported"):
        cleanup_renderer_service.render_cleanup(
            canonical_text,
            ledger,
            [
                {
                    "operation_id": "op-000001",
                    "action": "unsupported_action",
                    "target_id": "u-000001",
                }
            ],
            [],
        )


def test_completed_cleanup_reports_only_runtime_quality_metrics(tmp_path) -> None:
    """
    @brief      Cover the production-only Cleanup quality metric contract.
    """
    canonical_text, ledger = build_ledger(["A paragraph ends here."])
    project_root, manifest = build_project(tmp_path, "RuntimeMetrics", canonical_text, ledger)

    document = text_cleanup_service.clean_text(project_root, manifest)

    assert document["quality_report"]["introduced_fusion_count"] == 0
    assert document["quality_report"]["projection_violation_count"] == 0
    assert "f1" not in document["quality_report"]
    assert "precision" not in document["quality_report"]
    assert "recall" not in document["quality_report"]


def test_whitespace_merge_split_preserves_narratable_prose(tmp_path) -> None:
    """
    @brief      Cover issue #32 merge/split role realignment through Chunking.
    @details    Covers S-0001 through S-0006,
                REQ-FUNC-807c56f0-12b7-42e9-bd8f-0d562c903e70, and
                REQ-FUNC-376f4f7a-a9e4-4653-845b-edbba25cf170.
    """
    source_paragraphs = [
        "Opening one.",
        "Opening two.",
        "CHAPTER TWO",
        "* * *",
        "Closing one.",
        "Closing two first. Closing two second.",
    ]
    canonical_text, ledger = build_ledger(
        source_paragraphs,
        kinds=[
            "paragraph",
            "paragraph",
            "heading",
            "scene_separator",
            "paragraph",
            "paragraph",
        ],
        boundaries=[("\n\n", "native_paragraph")] * 5,
        origins=["native"] * 6,
        structure_quality="native",
    )
    project_root, manifest = build_project(
        tmp_path,
        "WhitespaceRoleRealignment",
        canonical_text,
        ledger,
    )
    text_cleanup_service.clean_text(project_root, manifest)

    edited = text_cleanup_service.save_user_cleaned_text(
        project_root,
        (
            "Opening one. Opening two.\n\n"
            "CHAPTER TWO\n\n"
            "* * *\n\n"
            "Closing one.\n\n"
            "Closing two first.\n\n"
            "Closing two second.\n"
        ),
    )

    assert [item["role"] for item in edited["paragraphs"]] == [
        "body",
        "heading",
        "scene_separator",
        "body",
        "body",
        "body",
    ]
    assert [item["provenance_available"] for item in edited["paragraphs"]] == [
        False,
        True,
        True,
        True,
        False,
        False,
    ]
    assert all(
        item["source_unit_ids"] == []
        for item in (
            edited["paragraphs"][0],
            edited["paragraphs"][4],
            edited["paragraphs"][5],
        )
    )

    deterministic_chunking_service.chunk_text(project_root, manifest)

    chunks = json.loads(
        (project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8")
    )["chunks"]
    materialized_text = "\n".join(str(item["text"]) for item in chunks)
    assert "* * *" not in materialized_text
    for prose in (
        "Opening one. Opening two.",
        "CHAPTER TWO",
        "Closing one.",
        "Closing two first.",
        "Closing two second.",
    ):
        assert prose in materialized_text


def test_whitespace_role_realign_falls_back_for_ambiguous_content(tmp_path) -> None:
    """
    @brief      Cover classifier-only fallback for ambiguous normalized content.
    @details    Covers S-0005 and
                REQ-FUNC-807c56f0-12b7-42e9-bd8f-0d562c903e70.
    """
    canonical_text, ledger = build_ledger(
        ["CHAPTER TWO", "CHAPTER TWO", "Narration."],
        kinds=["heading", "heading", "paragraph"],
        boundaries=[("\n\n", "native_paragraph")] * 2,
        origins=["native"] * 3,
        structure_quality="native",
    )
    project_root, manifest = build_project(
        tmp_path,
        "AmbiguousWhitespaceRoles",
        canonical_text,
        ledger,
    )
    text_cleanup_service.clean_text(project_root, manifest)

    edited = text_cleanup_service.save_user_cleaned_text(
        project_root,
        "CHAPTER   TWO\n\nCHAPTER TWO\n\nNarration.\n",
    )

    assert [item["role"] for item in edited["paragraphs"]] == [
        "body",
        "body",
        "body",
    ]
    assert [item["provenance_available"] for item in edited["paragraphs"]] == [
        False,
        False,
        True,
    ]
    assert edited["paragraphs"][0]["source_unit_ids"] == []
    assert edited["paragraphs"][1]["source_unit_ids"] == []


def test_whitespace_realign_carries_unique_paragraph_metadata_and_warnings(
    tmp_path,
) -> None:
    """@brief Preserve only truthful local metadata and its downstream warning flags."""
    canonical_text, ledger = build_ledger(
        ["Alpha paragraph.", "Beta paragraph.", "Gamma paragraph."],
        kinds=["heading", "paragraph", "paragraph"],
        boundaries=[("\n\n", "native_paragraph")] * 2,
        origins=["native", "native", "native"],
        structure_quality="native",
    )
    project_root, manifest = build_project(
        tmp_path,
        "WhitespaceParagraphMetadata",
        canonical_text,
        ledger,
    )
    document = text_cleanup_service.clean_text(project_root, manifest)
    unit_ids = [str(item["unit_id"]) for item in ledger["units"]]
    document["paragraphs"][0].update(
        {
            "confidence": "low",
            "reason_codes": ["deterministic_fallback", "retained_reason"],
            "source_page_start": 2,
            "source_page_end": 3,
            "starts_after_page_transition": True,
            "crosses_page_transition": True,
            "source_unit_ids": [unit_ids[0], unit_ids[0]],
            "provenance_available": True,
        }
    )
    document["paragraphs"][1].update(
        {
            "confidence": "medium",
            "reason_codes": ["unknown_line_boundary", "user_whitespace_realign"],
            "source_page_start": 5,
            "source_page_end": 5,
            "starts_after_page_transition": False,
            "crosses_page_transition": False,
            "source_unit_ids": [unit_ids[1]],
            "provenance_available": True,
        }
    )
    document["paragraphs"][2].update(
        {
            "confidence": "low",
            "reason_codes": ["retained_without_provenance"],
            "source_page_start": 8,
            "source_page_end": 9,
            "starts_after_page_transition": True,
            "crosses_page_transition": True,
            "source_unit_ids": [unit_ids[2]],
            "provenance_available": False,
        }
    )
    (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    edited = text_cleanup_service.save_user_cleaned_text(
        project_root,
        "Alpha paragraph.\n\n\nBeta paragraph.\n\n\nGamma paragraph.\n",
    )

    alpha, beta, gamma = edited["paragraphs"]
    assert alpha["source_unit_ids"] == [unit_ids[0]]
    assert beta["source_unit_ids"] == [unit_ids[1]]
    assert alpha["provenance_available"] is True
    assert beta["provenance_available"] is True
    assert (
        alpha["source_page_start"],
        alpha["source_page_end"],
        alpha["starts_after_page_transition"],
        alpha["crosses_page_transition"],
        alpha["confidence"],
    ) == (2, 3, True, True, "low")
    assert alpha["reason_codes"] == [
        "deterministic_fallback",
        "retained_reason",
        "user_whitespace_realign",
    ]
    assert beta["reason_codes"].count("user_whitespace_realign") == 1
    assert beta["confidence"] == "medium"
    assert gamma["source_unit_ids"] == []
    assert gamma["provenance_available"] is False
    assert gamma["source_page_start"] is None
    assert gamma["source_page_end"] is None
    assert gamma["starts_after_page_transition"] is False
    assert gamma["crosses_page_transition"] is False
    assert gamma["reason_codes"] == [
        "retained_without_provenance",
        "user_whitespace_realign",
    ]

    cleaned_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(
        encoding="utf-8"
    )
    runtime_records = cleanup_metadata_service.load_completed_paragraph_records(
        project_root,
        cleaned_text,
    )
    assert [item["warning_flags"] for item in runtime_records] == [
        ["deterministic_fallback"],
        ["unknown_line_boundary"],
        [],
    ]
    assert [item["text"] for item in runtime_records] == [
        "Alpha paragraph.",
        "Beta paragraph.",
        "Gamma paragraph.",
    ]


def test_whitespace_realign_failure_records_diagnostic(tmp_path, caplog) -> None:
    """
    @brief      Cover S-0001 and REQ-FUNC-1179da33-b65d-4192-a875-353a38c37ab7.
    """
    canonical_text, ledger = build_ledger(["Alpha  beta."])
    project_root, manifest = build_project(
        tmp_path,
        "WhitespaceRealignDiagnostic",
        canonical_text,
        ledger,
    )
    text_cleanup_service.clean_text(project_root, manifest)

    with caplog.at_level("WARNING"):
        edited = text_cleanup_service.save_user_cleaned_text(
            project_root,
            "Alpha beta.\n",
        )

    assert edited["warnings"].count("user_whitespace_realign_incomplete") == 1
    assert any(
        "could not realign Cleanup boundaries" in record.getMessage()
        for record in caplog.records
    )


# HELPER FUNCTIONS


def _build_extracted_project(tmp_path, name: str):
    """@brief Build one project with persisted completed Extraction and nondefault options."""
    canonical_text, ledger = build_ledger(["Canonical source paragraph."])
    project_root, manifest = build_project(
        tmp_path,
        name,
        canonical_text,
        ledger,
    )
    extraction_metadata = {
        "status": "completed",
        "progress_current": 1,
        "progress_total": 1,
        "warnings": [],
        "character_count": len(canonical_text),
        "word_count": len(canonical_text.split()),
        "line_count": len(canonical_text.splitlines()),
        "page_count": None,
    }
    text_extraction_service.write_extraction_metadata(
        project_root,
        extraction_metadata,
    )
    manifest["project_options_locked"] = True
    manifest["target_language"] = "ro"
    manifest["selected_voice_language"] = "ro"
    manifest["notes"] = "preserve this project note"
    manifest["current_stage"] = "text_cleanup_ready"
    project_workspace_service.save_manifest(manifest, project_root)
    return project_root, project_workspace_service.load_manifest(project_root)


def _seed_completed_downstream_state(project_root):
    """@brief Persist completed downstream summaries and representative owned artifacts."""
    manifest = project_workspace_service.load_manifest(project_root)
    operations = dict(manifest["operations"])
    for operation_kind in operation_runtime_service.downstream_operation_kinds(
        "chunking",
        include_current=True,
    ):
        operations[operation_kind] = (
            project_workspace_service.project_manifest_operation_summary(
                operation_kind,
                {
                    "status": "completed",
                    "progress_current": 1,
                    "progress_total": 1,
                    "mode": "test",
                    "warning_count": 0,
                },
            )
        )
    manifest["operations"] = operations
    manifest["current_stage"] = "audio_assembly_ready"
    project_workspace_service.save_manifest(manifest, project_root)

    artifact_paths = []
    for relative_path in _DOWNSTREAM_ARTIFACT_RELATIVE_PATHS:
        artifact_path = project_root / relative_path
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(b"stale downstream artifact")
        artifact_paths.append(artifact_path)

    (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).write_text("[]", encoding="utf-8")

    source_document = dict(manifest["source_document"])
    source_path = project_root / str(source_document["stored_relative_path"])
    extraction_artifacts = {
        file_name: (project_root / file_name).read_bytes()
        for file_name in (
            config.EXTRACTED_TEXT_FILE_NAME,
            config.SOURCE_LEDGER_FILE_NAME,
            config.EXTRACTION_METADATA_FILE_NAME,
        )
    }
    preserved_state = {
        "source_document": source_document,
        "source_bytes": source_path.read_bytes(),
        "extraction_artifacts": extraction_artifacts,
        "options": {
            field_name: manifest[field_name]
            for field_name in _PRESERVED_OPTION_FIELDS
        },
    }
    return artifact_paths, preserved_state


def _assert_synchronized_cleanup_transition(
    project_root,
    artifact_paths,
    preserved_state,
) -> None:
    """@brief Assert one successful Cleanup publication is coherent on disk and reopen."""
    assert all(not artifact_path.exists() for artifact_path in artifact_paths)
    manifest = project_workspace_service.load_manifest(project_root)
    default_manifest = project_workspace_service.build_project_manifest("Defaults")
    for operation_kind in operation_runtime_service.downstream_operation_kinds(
        "chunking",
        include_current=True,
    ):
        assert manifest["operations"][operation_kind] == (
            default_manifest["operations"][operation_kind]
        )
    assert manifest["operations"]["cleanup"]["status"] == "completed"
    assert manifest["current_stage"] == "text_chunking_ready"
    assert manifest["source_document"] == preserved_state["source_document"]
    source_path = project_root / str(
        preserved_state["source_document"]["stored_relative_path"]
    )
    assert source_path.read_bytes() == preserved_state["source_bytes"]
    for file_name, expected_bytes in preserved_state["extraction_artifacts"].items():
        assert (project_root / file_name).read_bytes() == expected_bytes
    assert {
        field_name: manifest[field_name]
        for field_name in _PRESERVED_OPTION_FIELDS
    } == preserved_state["options"]
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).is_file()
    assert (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).is_file()

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "ok"
    assert "recovered_operations" not in open_result


# END OF FILE
