#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_character_discovery_service.py
@brief Focused tests for the AudioMancer character discovery service.
@details Verifies initial discovery, resumable synthesis, profile updates, and
         reset behavior for the character-discovery workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-08
@version 0.1.0
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import character_discovery_service
from audiomancer.services import project_workspace_service


def test_start_discovery_persists_outputs_and_report(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify one discovery run writes profiles, report, state, and input snapshots.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryService")
    monkeypatch.setattr(
        character_discovery_service.prompt_template_service,
        "validate_required_prompts",
        lambda _prompt_names: None,
    )
    monkeypatch.setattr(
        character_discovery_service.prompt_template_service,
        "render_prompt",
        lambda prompt_name, payload: f"{prompt_name}:{sorted(payload.keys())}",
    )
    responses = iter([
        {
            "characters": [
                {
                    "canonical_name": "Alice",
                    "aliases": ["Al"],
                    "role_summary": "Lead speaker",
                    "evidence": [
                        {
                            "chunk_id": "chunk-0001",
                            "reason": "Alice speaks in direct dialogue.",
                        }
                    ],
                }
            ]
        },
        {
            "canonical_name": "Alice",
            "aliases": ["Al"],
            "role_summary": "Lead speaker",
            "description": "Confident young woman.",
            "relationship_hints": ["Knows Bob."],
            "confidence": "high",
        },
    ])
    monkeypatch.setattr(
        character_discovery_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: next(responses),
    )

    report = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )

    assert report["character_count"] == 1
    assert report["character_profile_id_last_used"] == "profile-1"
    profiles = character_discovery_service.load_character_profiles(project_root)
    assert len(profiles) == 1
    assert profiles[0]["canonical_name"] == "Alice"
    assert profiles[0]["evidence"][0]["chunk_id"] == "chunk-0001"
    assert character_discovery_service.load_input_chunks(project_root)[0]["chunk_id"] == "chunk-0001"
    assert (project_root / config.CHARACTER_DISCOVERY_FOLDER_NAME / "input_story.json").is_file()
    assert (project_root / config.CHARACTER_DISCOVERY_FOLDER_NAME / "input_story.txt").is_file()
    state = character_discovery_service.load_operation_state(project_root)
    assert state is not None
    assert state["status"] == "completed"
    assert state["output_paths"] == [f"40_character_discovery/{config.CHARACTER_PROFILE_FILE_NAME}"]


def test_start_discovery_resumes_from_saved_synthesis_checkpoint(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify a resumable operation can skip window analysis and continue with synthesis.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryResume")
    source_chunks = json.loads(
        (project_root / "20_chunking" / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8")
    )
    fingerprint = character_discovery_service._build_input_fingerprint(source_chunks)
    resume_candidate = {
        "character_id": "alice",
        "canonical_name": "Alice",
        "aliases": ["Al"],
        "gender_hint": "",
        "age_band": "",
        "role_summary": "Lead speaker",
        "description": "",
        "temperament": "",
        "social_status": "",
        "speaking_style": "",
        "accent_or_dialect_hints": "",
        "voice_notes": "",
        "relationship_hints": [],
        "confidence": "",
        "evidence": [
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "source_excerpt": '"Hello there," said Alice.',
                "reason": "Alice speaks in dialogue.",
            }
        ],
        "has_dialogue_evidence": True,
    }
    state_path = project_root / "40_character_discovery" / config.OPERATION_STATE_FILE_NAME
    state_path.write_text(
        json.dumps(
            {
                "folder_relative_path": "40_character_discovery",
                "status": "running",
                "input_paths": [],
                "output_paths": [],
                "artifact_paths": [],
                "progress_current": 1,
                "progress_total": 2,
                "mode": character_discovery_service.CHARACTER_DISCOVERY_MODE_AI_ASSISTED,
                "started_at": "2026-04-08T12:00:00+00:00",
                "completed_at": None,
                "updated_at": "2026-04-08T12:00:00+00:00",
                "warning_count": 0,
                "metadata": {
                    "ai_profile_id": "profile-1",
                    "input_fingerprint": fingerprint,
                },
                "resume_checkpoint": {
                    "input_fingerprint": fingerprint,
                    "profile_id": "profile-1",
                    "completed_window_count": 1,
                    "total_window_count": 1,
                    "raw_candidates": [resume_candidate],
                    "merged_candidates": [resume_candidate],
                    "synthesized_profiles": [],
                    "synthesis_progress_count": 0,
                    "log_relative_path": None,
                },
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        character_discovery_service.prompt_template_service,
        "validate_required_prompts",
        lambda _prompt_names: None,
    )
    monkeypatch.setattr(
        character_discovery_service.prompt_template_service,
        "render_prompt",
        lambda prompt_name, payload: f"{prompt_name}:{sorted(payload.keys())}",
    )
    call_count = {"value": 0}

    def _fake_chat_json(*_args, **_kwargs):
        call_count["value"] += 1
        return {
            "canonical_name": "Alice",
            "description": "Resumed profile synthesis.",
            "confidence": "high",
        }

    monkeypatch.setattr(
        character_discovery_service.llm_provider_service,
        "chat_json",
        _fake_chat_json,
    )

    report = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )

    assert call_count["value"] == 1
    assert report["character_count"] == 1
    assert character_discovery_service.load_character_profiles(project_root)[0]["description"] == "Resumed profile synthesis."


def test_update_profile_and_reset_discovery(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify manual profile updates persist and reset clears character plus narrator data.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryReset")
    monkeypatch.setattr(
        character_discovery_service.prompt_template_service,
        "validate_required_prompts",
        lambda _prompt_names: None,
    )
    monkeypatch.setattr(
        character_discovery_service.prompt_template_service,
        "render_prompt",
        lambda prompt_name, payload: f"{prompt_name}:{sorted(payload.keys())}",
    )
    responses = iter([
        {
            "characters": [
                {
                    "canonical_name": "Alice",
                    "aliases": [],
                    "role_summary": "Lead speaker",
                    "evidence": [{"chunk_id": "chunk-0001"}],
                }
            ]
        },
        {"canonical_name": "Alice", "description": "Original profile."},
    ])
    monkeypatch.setattr(
        character_discovery_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: next(responses),
    )
    character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )
    narrator_root = project_root / "50_narrator_definition"
    (narrator_root / "profile.json").write_text("{}\n", encoding="utf-8")

    updated_profiles = character_discovery_service.update_character_profile(
        project_root,
        {
            "character_id": "alice",
            "canonical_name": "Alice",
            "aliases": ["Al"],
            "gender_hint": "",
            "age_band": "",
            "role_summary": "Updated role",
            "description": "Updated description",
            "temperament": "",
            "social_status": "",
            "speaking_style": "",
            "accent_or_dialect_hints": "",
            "voice_notes": "",
            "relationship_hints": ["Knows Bob."],
            "confidence": "medium",
            "evidence": [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "source_excerpt": '"Hello there," said Alice.',
                    "reason": "Alice speaks.",
                }
            ],
            "updated_at": None,
        },
    )

    assert updated_profiles[0]["role_summary"] == "Updated role"
    character_discovery_service.reset_character_discovery(project_root)

    assert list((project_root / "40_character_discovery").iterdir()) == []
    assert list((project_root / "50_narrator_definition").iterdir()) == []


def test_start_discovery_requires_chunking_input(tmp_path) -> None:
    """
    @brief      Verify discovery refuses to start when chunking artifacts are missing.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "CharacterDiscoveryMissingChunks",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-08T12:00:00+00:00",
        "size_bytes": 12,
    }
    project_workspace_service.save_manifest(manifest, project_root)

    with pytest.raises(ValueError, match="Run text chunking"):
        character_discovery_service.start_or_continue_discovery(
            project_root,
            manifest,
            _profile_payload("profile-1"),
        )


def _create_character_project(tmp_path, project_name: str):
    project_root, manifest = project_workspace_service.create_project(project_name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-08T12:00:00+00:00",
        "size_bytes": 48,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"
    ]
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [
        f"20_chunking/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    project_workspace_service.save_manifest(manifest, project_root)
    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
    chunk_root = project_root / "20_chunking"
    cleanup_root.mkdir(parents=True, exist_ok=True)
    chunk_root.mkdir(parents=True, exist_ok=True)
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        'Alice said, "Hello there."\n\nBob replied, "Hi."\n',
        encoding="utf-8",
    )
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
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
                },
                {
                    "chunk_id": "chunk-0002",
                    "sequence_index": 2,
                    "chapter_label": None,
                    "text": '"Hi," Bob replied.',
                    "source_start_line": 2,
                    "source_end_line": 2,
                    "chunking_mode": "deterministic",
                    "semantic_strategy": None,
                    "scene_note": None,
                },
            ],
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return project_root, manifest


def _profile_payload(profile_id: str) -> dict[str, object]:
    return {
        "id": profile_id,
        "label": profile_id,
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234",
        "api_key": "",
        "model_name": "qwen3-8b",
        "context_window": 4096,
        "max_output_tokens": 512,
        "request_timeout_seconds": 30,
        "temperature": 0.2,
        "supports_structured_output": False,
        "enabled": True,
    }


# END OF FILE
