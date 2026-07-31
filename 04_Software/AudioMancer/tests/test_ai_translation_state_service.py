#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_translation_state_service.py
@brief Focused monofile page-state tests for AI Translation.
@details Verifies profile selection, derived review state, strict load errors,
         and read-only page-state construction.
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import ai_translation_service, ai_translation_state_service, project_workspace_service
from chunking_test_support import build_chunking_document

# PUBLIC API


def test_build_ai_translation_profile_state_prefers_default_translation_profile() -> None:
    """
    @brief      Verify profile state prefers the enabled translation default.
    @return     None.
    """
    profile_state = ai_translation_state_service.build_ai_translation_profile_state(
        {
            "llm_profiles": [
                {"id": "profile_a", "label": "Profile A", "enabled": True},
                {"id": "profile_b", "label": "Profile B", "enabled": True},
            ],
            "default_ai_translation_profile_id": "profile_b",
        }
    )
    assert profile_state["entries"] == [("Profile A", "profile_a"), ("Profile B", "profile_b")]
    assert profile_state["selected_profile_id"] == "profile_b"


def test_build_ai_translation_state_is_read_only(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-005 page-state construction never persists translation data.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_project(tmp_path, "TranslationStateReadOnly")
    ai_translation_service.write_translation_document(
        project_root,
        _document(ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING),
    )
    writes = []

    def fail_on_write(*args, **kwargs):
        """
        @brief      Fail when page-state construction attempts an authoritative write.
        @param[in]  args Positional arguments forwarded to the test double.
        @param[in]  kwargs Keyword arguments forwarded to the test double.
        @return     None.
        @exception  AssertionError Raised when unexpected translation write.
        """
        writes.append((args, kwargs))
        raise AssertionError("Unexpected translation write")

    monkeypatch.setattr(ai_translation_service, "write_translation_document", fail_on_write)
    state = ai_translation_state_service.build_ai_translation_state(
        project_root,
        manifest,
        "en",
        {"llm_profiles": [{"id": "profile-1", "label": "GPT", "enabled": True}]},
    )
    assert state["stage_status"] == ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING
    assert writes == []


def test_build_ai_translation_state_derives_counts_and_status(tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-005 counts and completed status are derived, not persisted.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_project(tmp_path, "TranslationStateDerived")
    document = _document(ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING)
    document["chunks"][0]["approved"] = True
    document["chunks"][1]["approved"] = True
    ai_translation_service.write_translation_document(project_root, document)

    state = ai_translation_state_service.build_ai_translation_state(
        project_root,
        manifest,
        "en",
        {"llm_profiles": [{"id": "profile-1", "label": "GPT", "enabled": True}]},
    )
    persisted = ai_translation_service.load_translation_document(project_root)
    assert state["translated_count"] == 2
    assert state["approved_count"] == 2
    assert state["total_count"] == 2
    assert state["stage_status"] == ai_translation_service.TRANSLATION_STATUS_COMPLETED
    assert persisted is not None
    assert "translated_count" not in persisted
    assert "approved_count" not in persisted


def test_build_ai_translation_state_surfaces_incompatible_document(tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-005 incompatible persistence becomes a reset-required UI state.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_project(tmp_path, "TranslationStateInvalid")
    (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text("[]\n", encoding="utf-8")

    state = ai_translation_state_service.build_ai_translation_state(
        project_root,
        manifest,
        "en",
        {"llm_profiles": [{"id": "profile-1", "label": "GPT", "enabled": True}]},
    )
    assert state["stage_status"] == ai_translation_service.TRANSLATION_STATUS_INVALID
    assert state["translated_chunks"] == []
    assert any("Reset Translation" in note for note in state["notes"])
    assert (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).read_text(encoding="utf-8") == "[]\n"


def test_translation_summary_requires_canonical_chunk_id_alignment(tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-005 unknown document chunks cannot make canonical input complete.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, _manifest = _create_project(tmp_path, "TranslationStateAlignment")
    document = _document(ai_translation_service.TRANSLATION_STATUS_COMPLETED)
    document["chunks"][0]["approved"] = True
    document["chunks"][1] = {
        "chunk_id": "unknown-chunk",
        "translated_text": "Unknown translation",
        "approved": True,
    }
    ai_translation_service.write_translation_document(project_root, document)

    summary = ai_translation_service.load_translation_summary(project_root)

    assert summary["status"] == ai_translation_service.TRANSLATION_STATUS_IN_PROGRESS
    assert summary["translated_count"] == 1
    assert summary["approved_count"] == 1


# TEST HELPERS


def _create_project(tmp_path, name: str):
    """
    @brief      Create one project with two canonical chunks.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  name Stable name associated with the requested object.
    @return     Created project root and manifest payload.
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-07-16T12:00:00+00:00",
        "size_bytes": 12,
    }
    manifest["original_language"] = "en"
    manifest["target_language"] = "ro"
    manifest["operations"]["chunking"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            build_chunking_document(
                [
                    {"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Original one"},
                    {"chunk_id": "chunk-0002", "sequence_index": 2, "text": "Original two"},
                ]
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root, project_workspace_service.load_manifest(project_root)


def _document(status: str) -> dict[str, object]:
    """Build one strict translation document fixture."""
    return {
        "target_language": "ro",
        "status": status,
        "token_usage": {
            "input_tokens": 20,
            "output_tokens": 10,
            "total_tokens": 30,
            "usage_available": True,
        },
        "budget_metadata": {
            "context_window": 4096,
            "max_output_tokens": 512,
            "prompt_budget_tokens": 100,
            "text_budget_tokens": 2048,
            "safety_margin_tokens": 512,
        },
        "additional_translation_instructions": "",
        "chunks": [
            {"chunk_id": "chunk-0001", "translated_text": "Traducere unu", "approved": False},
            {"chunk_id": "chunk-0002", "translated_text": "Traducere doi", "approved": False},
        ],
    }


# END OF FILE
