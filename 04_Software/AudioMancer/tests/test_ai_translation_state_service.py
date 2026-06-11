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
@brief Focused tests for the AudioMancer AI translation state service.
@details Verifies translation-profile state shaping respects enabled profiles
         and the persisted default AI translation profile selection.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.4.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import ai_translation_service, ai_translation_state_service, project_workspace_service

# PUBLIC API


def test_build_ai_translation_profile_state_prefers_default_translation_profile() -> None:
    """
    @brief      Verify translation profile state prefers the configured default translation profile.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
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

    assert profile_state["entries"] == [
        ("Profile A", "profile_a"),
        ("Profile B", "profile_b"),
    ]
    assert profile_state["selected_profile_id"] == "profile_b"


def test_build_ai_translation_notes_include_persisted_token_usage() -> None:
    """
    @brief      Verify translation notes show one persisted token-usage summary.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    notes = ai_translation_state_service.build_ai_translation_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        source_chunks=[{"chunk_id": "chunk-0001"}],
        report={
            "translated_chunk_count": 1,
            "approved_chunk_count": 0,
            "warnings": [],
            "token_usage": {
                "input_tokens": 220,
                "output_tokens": 80,
                "total_tokens": 300,
                "usage_available": True,
            },
        },
        operation_state={
            "status": "completed",
            "metadata": {},
        },
        has_ai_profiles=True,
        language="en",
    )

    assert any("Input tokens: 220 | Output tokens: 80 | Total: 300" in note for note in notes)


def test_build_ai_translation_state_does_not_auto_finalize_same_language(tmp_path) -> None:
    """
    @brief      Verify same-language projects stay startable until the operator starts translation.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("SameLanguageState", tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-26T12:00:00+00:00",
        "size_bytes": 12,
    }
    manifest["original_language"] = "en"
    manifest["target_language"] = "en"
    manifest["selected_voice_language"] = "en"
    manifest["project_options_locked"] = True
    manifest["operations"]["chunking"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": None,
                    "text": "Original text.",
                    "source_start_line": 1,
                    "source_end_line": 1,
                    "chunking_mode": "deterministic",
                    "semantic_strategy": None,
                    "scene_note": None,
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    state = ai_translation_state_service.build_ai_translation_state(
        project_root,
        project_workspace_service.load_manifest(project_root),
        "en",
        {"llm_profiles": [{"id": "profile-1", "label": "GPT", "enabled": True}]},
    )

    assert state["stage_status"] == "not_started"
    assert state["translated_chunks"] == []
    assert state["translated_count"] == 0
    assert state["approved_count"] == 0


def test_build_ai_translation_state_does_not_write_unchanged_records(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-AUDIO-FUNC-005 page state build stays read-only when records are synchronized.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("TranslationStateReadOnly", tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-06-10T12:00:00+00:00",
        "size_bytes": 12,
    }
    manifest["original_language"] = "en"
    manifest["target_language"] = "ro"
    manifest["selected_voice_language"] = "ro"
    manifest["project_options_locked"] = True
    manifest["operations"]["chunking"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": None,
                    "text": "Original text.",
                    "source_start_line": 1,
                    "source_end_line": 1,
                    "chunking_mode": "deterministic",
                    "semantic_strategy": None,
                    "scene_note": None,
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ai_translation_service.ensure_translation_records(project_root, "ro", "profile-1")
    manifest = project_workspace_service.load_manifest(project_root)
    writes = []

    def fail_on_write_json_atomic(path, payload, **kwargs):
        writes.append(path)
        raise AssertionError(f"Unexpected translation write: {path}")

    monkeypatch.setattr(ai_translation_service, "write_json_atomic", fail_on_write_json_atomic)

    state = ai_translation_state_service.build_ai_translation_state(
        project_root,
        manifest,
        "en",
        {"llm_profiles": [{"id": "profile-1", "label": "GPT", "enabled": True}]},
    )

    assert state["stage_status"] == "not_started"
    assert writes == []


def _create_same_language_chunked_project(tmp_path, name: str):
    """
    @brief      Create a same-language project with one chunking artifact.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  name Project display name.
    @return     Project root and manifest payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-26T12:00:00+00:00",
        "size_bytes": 12,
    }
    manifest["original_language"] = "en"
    manifest["target_language"] = "en"
    manifest["selected_voice_language"] = "en"
    manifest["project_options_locked"] = True
    manifest["operations"]["chunking"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": None,
                    "text": "Original text.",
                    "source_start_line": 1,
                    "source_end_line": 1,
                    "chunking_mode": "deterministic",
                    "semantic_strategy": None,
                    "scene_note": None,
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root, manifest


# END OF FILE
