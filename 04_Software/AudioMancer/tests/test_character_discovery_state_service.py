#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
@author Eng. Dan Dumitru Pasare
@date 2026-04-08
@version 0.3.0
"""

import json

from audiomancer import config
from audiomancer.services import character_discovery_state_service
from audiomancer.services import project_workspace_service


def test_profile_state_prefers_default_character_profile() -> None:
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


def test_build_character_state_requires_ai_profile_to_start(tmp_path) -> None:
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
        f"{config.CHUNKING_FOLDER_NAME}/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root / config.CHUNKING_FOLDER_NAME
    chunk_root.mkdir(parents=True, exist_ok=True)
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [{
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "chapter_label": None,
                "text": '"Hello there," said Alice.',
                "source_start_line": 1,
                "source_end_line": 1,
                "chunking_mode": "deterministic",
                "semantic_strategy": None,
                "scene_note": None,
            }],
            indent=2,
        ) + "\n",
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


def _create_project(tmp_path, name: str):
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
        f"{config.CHUNKING_FOLDER_NAME}/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    manifest["operations"]["character_discovery"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root / config.CHUNKING_FOLDER_NAME
    discovery_root = project_root / config.CHARACTER_DISCOVERY_FOLDER_NAME
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
        json.dumps(chunk_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / "input_story.json").write_text(
        json.dumps(chunk_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.CHARACTER_PROFILE_FILE_NAME).write_text(
        json.dumps(
            [{
                "character_id": "alice",
                "canonical_name": "Alice",
                "aliases": ["Al"],
                "gender_hint": "",
                "age_band": "",
                "role_summary": "Lead speaker",
                "description": "Confident.",
                "temperament": "",
                "social_status": "",
                "speaking_style": "",
                "accent_or_dialect_hints": "",
                "voice_notes": "",
                "relationship_hints": [],
                "confidence": "high",
                "evidence": [{
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "source_excerpt": '"Hello there," said Alice.',
                    "reason": "Alice speaks.",
                }],
                "updated_at": "2026-04-08T12:01:00+00:00",
            }],
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.CHARACTER_DISCOVERY_REPORT_FILE_NAME).write_text(
        json.dumps(
            {
                "input_chunk_count": 1,
                "analyzed_window_count": 1,
                "merged_candidate_count": 1,
                "character_count": 1,
                "character_discovery_mode": "ai_assisted",
                "character_profile_id_last_used": "profile-1",
                "window_size": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE,
                "window_overlap": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
                "warning_count": 0,
                "warnings": [],
                "generated_at": "2026-04-08T12:01:00+00:00",
                "token_usage": {
                    "input_tokens": 140,
                    "output_tokens": 35,
                    "total_tokens": 175,
                    "usage_available": True,
                },
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.OPERATION_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": config.CHARACTER_DISCOVERY_FOLDER_NAME,
                "status": "completed",
                "input_paths": [],
                "output_paths": [f"{config.CHARACTER_DISCOVERY_FOLDER_NAME}/{config.CHARACTER_PROFILE_FILE_NAME}"],
                "artifact_paths": [f"{config.CHARACTER_DISCOVERY_FOLDER_NAME}/{config.CHARACTER_DISCOVERY_REPORT_FILE_NAME}"],
                "progress_current": 1,
                "progress_total": 1,
                "mode": "ai_assisted",
                "started_at": "2026-04-08T12:00:00+00:00",
                "completed_at": "2026-04-08T12:01:00+00:00",
                "updated_at": "2026-04-08T12:01:00+00:00",
                "warning_count": 0,
                "metadata": {
                    "ai_profile_id": "profile-1",
                    "character_count": 1,
                    "token_usage": {
                        "input_tokens": 140,
                        "output_tokens": 35,
                        "total_tokens": 175,
                        "usage_available": True,
                    },
                },
                "resume_checkpoint": None,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return project_root, manifest


# END OF FILE
