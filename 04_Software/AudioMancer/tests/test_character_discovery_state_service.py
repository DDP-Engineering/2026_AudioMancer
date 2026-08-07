#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_character_discovery_state_service.py
@brief Focused tests for the AudioMancer character discovery state service.
@details Verifies profile selector defaults and Characters page state shaping
         for completed discovery, manual-maintenance enablement, and missing AI
         profile behavior.
"""

# IMPORTS

import json
import string

import pytest

from audiomancer import config
from audiomancer.services import (
    character_discovery_service,
    character_discovery_state_service,
    project_workspace_service,
    ui_state_service,
)
from chunking_test_support import build_chunking_document


def test_profile_state_prefers_default_character_profile() -> None:
    """
    @brief      Validate profile state prefers default character profile.
    @return     None.
    @exception  None
    """
    profile_state = character_discovery_state_service.build_character_discovery_profile_state(
        {
            "llm_profiles": [
                {"id": "profile_a", "label": "Profile A", "enabled": True},
                {"id": "profile_b", "label": "Profile B", "enabled": True},
            ],
            "default_character_extraction_profile_id": "profile_b",
        }
    )

    assert profile_state["entries"] == [
        ("Profile A", "profile_a"),
        ("Profile B", "profile_b"),
    ]
    assert profile_state["selected_profile_id"] == "profile_b"


def test_build_character_state_exposes_manual_maintenance_flags(tmp_path) -> None:
    """
    @brief      Validate build character state exposes manual maintenance flags.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project(tmp_path, "CharacterDiscoveryState")

    state = character_discovery_state_service.build_character_discovery_state(
        project_root,
        manifest,
        "en",
        {
            "llm_profiles": [{"id": "profile-1", "label": "Profile One", "enabled": True}],
            "default_character_extraction_profile_id": "profile-1",
        },
    )

    assert state["selected_profile_id"] == "profile-1"
    assert state["stage_status"] == "completed"
    assert state["can_start"] is False
    assert state["can_reset"] is True
    assert state["can_add"] is True
    assert state["can_edit"] is True
    assert state["can_delete"] is True
    assert state["source_chunk_map"]["chunk-0001"] == '"Hello there," said Alice.'
    assert any("Discovered 1 speaking characters" in note for note in state["notes"])
    assert any("Input tokens: 140 | Output tokens: 35 | Total: 175" in note for note in state["notes"])
    assert any("fresh discovery rerun replaces" in note for note in state["notes"])


def test_build_character_state_uses_resolved_discovery_source(tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-013 page state avoids discovery chunk enrichment during refresh.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project(tmp_path, "CharacterDiscoveryStateNoDiscoveryEnrichment")
    state = character_discovery_state_service.build_character_discovery_state(
        project_root,
        manifest,
        "en",
        {
            "llm_profiles": [{"id": "profile-1", "label": "Profile One", "enabled": True}],
            "default_character_extraction_profile_id": "profile-1",
        },
    )

    assert state["source_chunk_map"] == {"chunk-0001": '"Hello there," said Alice.'}


def test_build_character_state_requires_ai_profile_to_start(tmp_path) -> None:
    """
    @brief      Validate build character state requires ai profile to start.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project(
        "CharacterDiscoveryNoProfile",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-08T12:00:00+00:00",
        "size_bytes": 12,
    }
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    chunk_root.mkdir(parents=True, exist_ok=True)
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            build_chunking_document(
                [
                    {
                        "chunk_id": "chunk-0001",
                        "sequence_index": 1,
                        "chapter_label": None,
                        "text": '"Hello there," said Alice.',
                        "source_start_line": 1,
                        "source_end_line": 1,
                        "chunking_mode": "deterministic",
                        "semantic_strategy": None,
                        "scene_note": None,
                    }
                ]
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    state = character_discovery_state_service.build_character_discovery_state(
        project_root,
        manifest,
        "en",
        {"llm_profiles": [], "default_character_extraction_profile_id": None},
    )

    assert state["can_start"] is False
    assert any("Enable at least one AI profile" in note for note in state["notes"])


@pytest.mark.parametrize("invalid_document", ["{", {"status": "completed"}, {"characters": [{}]}])
def test_invalid_character_documents_remain_strict_but_build_recovery_state(tmp_path, invalid_document) -> None:
    """
    @brief      Verify invalid documents are strict service errors but safe page states.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  invalid_document Invalid authoritative document test payload.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project(tmp_path, "InvalidCharacterDiscoveryState")
    document_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHARACTERS_DOCUMENT_FILE_NAME
    document_path.write_text(
        invalid_document if isinstance(invalid_document, str) else json.dumps(invalid_document),
        encoding="utf-8",
    )

    with pytest.raises(character_discovery_service.CharacterDocumentError):
        character_discovery_service.load_character_document(project_root)

    original_text = document_path.read_text(encoding="utf-8")
    localized_notes = (
        ("en", "Character Discovery data is invalid"),
        ("ro", "Datele Descoperirii Personajelor sunt nevalide"),
    )
    for language, note_fragment in localized_notes:
        state = character_discovery_state_service.build_character_discovery_state(
            project_root,
            manifest,
            language,
            {
                "llm_profiles": [{"id": "profile-1", "label": "Profile One", "enabled": True}],
                "default_character_extraction_profile_id": "profile-1",
            },
        )

        assert state["profiles"] == []
        assert state["character_count"] == 0
        assert state["source_chunk_map"] == {"chunk-0001": '"Hello there," said Alice.'}
        assert state["stage_status"] == "failed"
        assert state["selected_profile_id"] == "profile-1"
        assert state["can_reset"] is True
        disabled_flags = (
            "can_start",
            "can_add",
            "can_edit",
            "can_save",
            "can_delete",
            "edit_mode",
            "dirty",
        )
        assert all(state[flag] is False for flag in disabled_flags)
        assert any(note_fragment in note for note in state["notes"])

    assert document_path.read_text(encoding="utf-8") == original_text


def test_completed_character_notes_report_only_persisted_character_count(tmp_path) -> None:
    """
    @brief      Verify completed notes never invent an analyzed-window count.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project(tmp_path, "TruthfulCharacterSummary")

    expected_notes = (
        ("en", "Discovered 1 speaking characters."),
        ("ro", "Au fost descoperite 1 personaje vorbitoare."),
    )
    for language, expected_note in expected_notes:
        state = character_discovery_state_service.build_character_discovery_state(project_root, manifest, language)

        assert expected_note in state["notes"]
        assert not any("window" in note.casefold() or "fereastr" in note.casefold() for note in state["notes"])
        assert any("Input tokens" in note or "Tokeni intrare" in note for note in state["notes"])
        assert ui_state_service.translate("characters.note_rerun_replaces_manual", language) in state["notes"]


def test_character_recovery_and_summary_localizations_share_placeholders() -> None:
    """
    @brief      Verify paired Character Discovery localization templates have equal fields.
    @return     None.
    @exception  None
    """
    for key in ("characters.note_invalid_document", "characters.note_summary"):
        english = ui_state_service.translate(key, "en")
        romanian = ui_state_service.translate(key, "ro")

        assert _format_fields(english) == _format_fields(romanian)


def _format_fields(template: str) -> set[str]:
    """Return named Python-format fields used by one localization template."""
    return {
        field_name
        for _literal, field_name, _format_spec, _conversion in string.Formatter().parse(template)
        if field_name
    }


def _create_project(tmp_path, name: str):
    """
    @brief      Provide the create project test helper.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  name Stable name associated with the requested object.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-08T12:00:00+00:00",
        "size_bytes": 16,
    }
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    manifest["operations"]["character_discovery"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    discovery_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    chunk_root.mkdir(parents=True, exist_ok=True)
    discovery_root.mkdir(parents=True, exist_ok=True)
    chunk_payload = [
        {
            "chunk_id": "chunk-0001",
            "sequence_index": 1,
            "chapter_label": None,
            "text": '"Hello there," said Alice.',
            "source_start_line": 1,
            "source_end_line": 1,
            "chunking_mode": "deterministic",
            "semantic_strategy": None,
            "scene_note": None,
        }
    ]
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(build_chunking_document(chunk_payload), indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / "input_story.json").write_text(
        json.dumps(chunk_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.CHARACTERS_DOCUMENT_FILE_NAME).write_text(
        json.dumps(
            {
                "status": "completed",
                "source": {
                    "kind": "original",
                    "language": "en",
                    "fingerprint": "fixture",
                },
                "instructions": "",
                "token_usage": {
                    "input_tokens": 140,
                    "output_tokens": 35,
                    "total_tokens": 175,
                    "usage_available": True,
                },
                "checkpoint": None,
                "failure": None,
                "characters": [
                {
                    "character_id": "alice",
                    "canonical_name": "Alice",
                    "aliases": ["Al"],
                    "traits": {
                        "gender": {"value": "female", "confidence": "high"},
                        "age": {"value": "", "confidence": ""},
                    },
                    "voice": {
                        "definition_prompt": "A confident female voice for Alice.",
                        "preview_text": "",
                    },
                    "discovery_confidence": "high",
                    "provenance": {"origin": "ai", "edited": False},
                    "evidence": [
                        {
                            "chunk_id": "chunk-0001",
                            "sequence_index": 1,
                            "source_excerpt": '"Hello there," said Alice.',
                            "reason": "Alice speaks.",
                        }
                    ],
                }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root, manifest


# END OF FILE
