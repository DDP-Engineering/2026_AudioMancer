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
@details Verifies discovery persistence, resumable synthesis, manual add or
         update or delete behavior, and reset behavior for the character
         discovery workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-08
@version 0.2.0
"""

import json

import pytest

from audiomancer import config
from audiomancer.services import character_discovery_service
from audiomancer.services import project_workspace_service


def test_start_discovery_persists_outputs_and_report(monkeypatch, tmp_path) -> None:
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
    assert state["output_paths"] == [
        f"{config.CHARACTER_DISCOVERY_FOLDER_NAME}/{config.CHARACTER_PROFILE_FILE_NAME}"
    ]


def test_start_discovery_resumes_from_saved_synthesis_checkpoint(monkeypatch, tmp_path) -> None:
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryResume")
    source_chunks = json.loads(
        (project_root / config.CHUNKING_FOLDER_NAME / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8")
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
    state_path = project_root / config.CHARACTER_DISCOVERY_FOLDER_NAME / config.OPERATION_STATE_FILE_NAME
    state_path.write_text(
        json.dumps(
            {
                "folder_relative_path": config.CHARACTER_DISCOVERY_FOLDER_NAME,
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


def test_manual_add_update_delete_and_reset(tmp_path) -> None:
    project_root, _manifest = _create_character_project(tmp_path, "CharacterDiscoveryManual")
    discovery_root = project_root / config.CHARACTER_DISCOVERY_FOLDER_NAME
    (discovery_root / config.CHARACTER_PROFILE_FILE_NAME).write_text(
        json.dumps([_saved_profile_payload()], indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.OPERATION_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": config.CHARACTER_DISCOVERY_FOLDER_NAME,
                "status": "completed",
                "input_paths": [],
                "output_paths": [f"{config.CHARACTER_DISCOVERY_FOLDER_NAME}/{config.CHARACTER_PROFILE_FILE_NAME}"],
                "artifact_paths": [],
                "progress_current": 1,
                "progress_total": 1,
                "mode": "ai_assisted",
                "started_at": "2026-04-08T12:00:00+00:00",
                "completed_at": "2026-04-08T12:01:00+00:00",
                "updated_at": "2026-04-08T12:01:00+00:00",
                "warning_count": 0,
                "metadata": {"ai_profile_id": "profile-1", "character_count": 1},
                "resume_checkpoint": None,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    narrator_root = project_root / config.NARRATOR_DEFINITION_FOLDER_NAME
    narrator_root.mkdir(parents=True, exist_ok=True)
    (narrator_root / "profile.json").write_text("{}\n", encoding="utf-8")

    added_profiles = character_discovery_service.add_character_profile(project_root, "Bob")
    bob_profile = next(
        profile for profile in added_profiles if str(profile.get("canonical_name")) == "Bob"
    )
    assert bob_profile["evidence"][0]["chunk_id"] == character_discovery_service.MANUAL_CHARACTER_EVIDENCE_CHUNK_ID

    updated_profiles = character_discovery_service.update_character_profile(
        project_root,
        {
            "character_id": str(bob_profile["character_id"]),
            "canonical_name": "Bob",
            "aliases": ["Bobby"],
            "gender_hint": "",
            "age_band": "",
            "role_summary": "Manual role",
            "description": "Manual description",
            "temperament": "",
            "social_status": "",
            "speaking_style": "",
            "accent_or_dialect_hints": "",
            "voice_notes": "",
            "relationship_hints": [],
            "confidence": "",
            "evidence": [dict(item) for item in bob_profile["evidence"]],
            "updated_at": None,
        },
    )
    updated_bob = next(
        profile for profile in updated_profiles if str(profile.get("character_id")) == str(bob_profile["character_id"])
    )
    assert updated_bob["role_summary"] == "Manual role"

    remaining_profiles = character_discovery_service.delete_character_profile(
        project_root,
        str(bob_profile["character_id"]),
    )
    assert len(remaining_profiles) == 1
    assert remaining_profiles[0]["character_id"] == "alice"
    assert character_discovery_service.load_operation_state(project_root)["metadata"]["character_count"] == 1

    character_discovery_service.reset_character_discovery(project_root)

    assert list(discovery_root.iterdir()) == []
    assert list(narrator_root.iterdir()) == []


def test_validate_manual_character_name_rejects_duplicates_and_invalid_names() -> None:
    existing_profiles = [_saved_profile_payload()]

    with pytest.raises(ValueError, match="duplicate_name"):
        character_discovery_service.validate_manual_character_name(
            existing_profiles,
            "Alice",
        )
    with pytest.raises(ValueError, match="duplicate_name"):
        character_discovery_service.validate_manual_character_name(
            existing_profiles,
            "Al",
        )
    with pytest.raises(ValueError, match="invalid_name"):
        character_discovery_service.validate_manual_character_name(
            existing_profiles,
            "!!!",
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
        f"{config.CHUNKING_FOLDER_NAME}/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    project_workspace_service.save_manifest(manifest, project_root)
    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
    chunk_root = project_root / config.CHUNKING_FOLDER_NAME
    discovery_root = project_root / config.CHARACTER_DISCOVERY_FOLDER_NAME
    cleanup_root.mkdir(parents=True, exist_ok=True)
    chunk_root.mkdir(parents=True, exist_ok=True)
    discovery_root.mkdir(parents=True, exist_ok=True)
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        '"Hello there," said Alice.\n',
        encoding="utf-8",
    )
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
    return project_root, manifest


def _profile_payload(profile_id: str) -> dict[str, object]:
    return {
        "id": profile_id,
        "label": "Profile One",
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


def _saved_profile_payload() -> dict[str, object]:
    return {
        "character_id": "alice",
        "canonical_name": "Alice",
        "aliases": ["Al"],
        "gender_hint": "",
        "age_band": "",
        "role_summary": "Lead speaker",
        "description": "Original profile.",
        "temperament": "",
        "social_status": "",
        "speaking_style": "",
        "accent_or_dialect_hints": "",
        "voice_notes": "",
        "relationship_hints": [],
        "confidence": "high",
        "evidence": [
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "source_excerpt": '"Hello there," said Alice.',
                "reason": "Alice speaks.",
            }
        ],
        "updated_at": "2026-04-08T12:01:00+00:00",
    }


# END OF FILE
