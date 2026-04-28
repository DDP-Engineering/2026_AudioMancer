#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
@version 0.6.0
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import character_discovery_service, project_workspace_service


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
    responses = iter(
        [
            {
                "payload": {
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
                "usage": {"input_tokens": 60, "output_tokens": 15, "total_tokens": 75, "usage_available": True},
            },
            {
                "payload": {
                    "canonical_name": "Alice",
                    "aliases": ["Al"],
                    "role_summary": "Lead speaker",
                    "description": "Confident young woman.",
                    "voice_persona_summary": "Young adult woman with composed presence.",
                    "voice_timbre_and_range": "Warm mezzo voice with gentle authority.",
                    "voice_definition_prompt": (
                        "Create a consistent spoken voice for Alice. Warm mezzo voice with gentle authority."
                    ),
                    "relationship_hints": ["Knows Bob."],
                    "confidence": "high",
                },
                "usage": {"input_tokens": 40, "output_tokens": 20, "total_tokens": 60, "usage_available": True},
            },
        ]
    )
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
    assert profiles[0]["voice_persona_summary"] == "Young adult woman with composed presence."
    assert "gentle authority" in profiles[0]["voice_definition_prompt"]
    assert profiles[0]["evidence"][0]["chunk_id"] == "chunk-0001"
    assert character_discovery_service.load_input_chunks(project_root)[0]["chunk_id"] == "chunk-0001"
    assert (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHUNK_ARTIFACT_FILE_NAME).is_file()
    assert (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME).is_file()
    state = character_discovery_service.load_operation_state(project_root)
    assert state is not None
    assert state["status"] == "completed"
    assert state["output_paths"] == [config.CHARACTER_PROFILE_FILE_NAME]
    assert report["budget_metadata"]["context_window"] == 4096
    assert report["budget_metadata"]["max_output_tokens"] == 512
    assert state["metadata"]["budget_metadata"] == report["budget_metadata"]
    assert report["token_usage"]["total_tokens"] == 135


def test_start_discovery_resumes_from_saved_synthesis_checkpoint(monkeypatch, tmp_path) -> None:
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryResume")
    source_chunks = character_discovery_service.load_input_chunks(project_root)
    fingerprint = character_discovery_service._build_input_fingerprint(source_chunks)
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
    budget_metadata = character_discovery_service._build_budget_metadata(  # noqa: SLF001
        _profile_payload("profile-1"),
        "character_discovery_system:[]",
    )
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
    state_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHARACTER_DISCOVERY_STATE_FILE_NAME
    state_path.write_text(
        json.dumps(
            {
                "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
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
                    "budget_metadata": budget_metadata,
                },
                "resume_checkpoint": {
                    "input_fingerprint": fingerprint,
                    "profile_id": "profile-1",
                    "completed_window_count": 1,
                    "total_window_count": 1,
                    "budget_metadata": budget_metadata,
                    "raw_candidates": [resume_candidate],
                    "merged_candidates": [resume_candidate],
                    "rejected_candidates": [],
                    "synthesized_profiles": [],
                    "synthesis_progress_count": 0,
                    "log_relative_path": None,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    call_count = {"value": 0}

    def _fake_chat_json(*_args, **_kwargs):
        call_count["value"] += 1
        return {
            "payload": {
                "canonical_name": "Alice",
                "description": "Resumed profile synthesis.",
                "confidence": "high",
            },
            "usage": {
                "input_tokens": 70,
                "output_tokens": 20,
                "total_tokens": 90,
                "usage_available": True,
            },
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
    assert report["input_source"] == character_discovery_service.CHARACTER_DISCOVERY_INPUT_SOURCE_CHUNKS
    assert report["token_usage"]["total_tokens"] == 90
    assert (
        character_discovery_service.load_character_profiles(project_root)[0]["description"]
        == "Resumed profile synthesis."
    )


def test_manual_add_update_delete_and_reset(tmp_path) -> None:
    project_root, _manifest = _create_character_project(tmp_path, "CharacterDiscoveryManual")
    discovery_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    (discovery_root / config.CHARACTER_PROFILE_FILE_NAME).write_text(
        json.dumps([_saved_profile_payload()], indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.CHARACTER_DISCOVERY_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
                "status": "completed",
                "input_paths": [],
                "output_paths": [f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CHARACTER_PROFILE_FILE_NAME}"],
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
        )
        + "\n",
        encoding="utf-8",
    )
    narrator_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    narrator_root.mkdir(parents=True, exist_ok=True)
    (narrator_root / config.NARRATOR_PROFILE_FILE_NAME).write_text("{}\n", encoding="utf-8")

    added_profiles = character_discovery_service.add_character_profile(project_root, "Bob")
    bob_profile = next(profile for profile in added_profiles if str(profile.get("canonical_name")) == "Bob")
    assert bob_profile["evidence"][0]["chunk_id"] == character_discovery_service.MANUAL_CHARACTER_EVIDENCE_CHUNK_ID
    assert bob_profile["review_status"] == character_discovery_service.CHARACTER_REVIEW_STATUS_MANUAL

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
    assert updated_bob["review_status"] == character_discovery_service.CHARACTER_REVIEW_STATUS_MANUAL

    remaining_profiles = character_discovery_service.delete_character_profile(
        project_root,
        str(bob_profile["character_id"]),
    )
    assert len(remaining_profiles) == 1
    assert remaining_profiles[0]["character_id"] == "alice"
    assert character_discovery_service.load_operation_state(project_root)["metadata"]["character_count"] == 1

    character_discovery_service.reset_character_discovery(project_root)

    assert not (discovery_root / config.CHARACTER_PROFILE_FILE_NAME).exists()
    assert not (discovery_root / config.CHARACTER_DISCOVERY_REPORT_FILE_NAME).exists()
    assert not (discovery_root / config.CHARACTER_DISCOVERY_STATE_FILE_NAME).exists()
    assert (narrator_root / config.NARRATOR_PROFILE_FILE_NAME).is_file()
    assert (discovery_root / config.CHUNK_ARTIFACT_FILE_NAME).is_file()


def test_regenerate_character_voice_definition_builds_voice_brief_and_prompt() -> None:
    """
    @brief      Verify local regeneration produces structured voice-definition fields and one final prompt.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    1.0.0
    """
    regenerated_profile = character_discovery_service.regenerate_character_voice_definition(
        {
            "character_id": "elizabeth",
            "canonical_name": "Elizabeth",
            "gender_hint": "female",
            "age_band": "adult",
            "role_summary": "noblewoman",
            "description": "careful and observant",
            "temperament": "calm",
            "social_status": "upper class",
            "speaking_style": "measured and precise",
            "accent_or_dialect_hints": "light southern English influence",
            "voice_notes": "warm tone with restrained authority",
        }
    )

    assert "restrained authority" in regenerated_profile["voice_timbre_and_range"]
    assert "measured and precise" in regenerated_profile["voice_pacing_and_rhythm"]
    assert regenerated_profile["voice_definition_prompt"].startswith("Create a consistent spoken voice for Elizabeth.")
    assert "Sex/Gender: female." in regenerated_profile["voice_definition_prompt"]
    assert regenerated_profile["voice_definition_source_signature"]
    assert regenerated_profile["voice_definition_stale"] is False


def test_merge_character_candidates_keeps_role_speaker_candidate() -> None:
    """
    @brief      Verify merged candidates preserve deterministic role speakers as dialogue characters.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    merged_candidates = character_discovery_service._merge_character_candidates(  # noqa: SLF001
        [
            {
                "canonical_name": "His Agent",
                "aliases": ["agent"],
                "role_summary": "Role-identified speaking character referred to as his agent",
                "evidence": [
                    {
                        "chunk_id": "chunk-0001",
                        "sequence_index": 1,
                        "source_excerpt": '"Sure, absolutely," his agent said.',
                        "reason": "Direct speech is attributed to his agent.",
                    }
                ],
                "has_dialogue_evidence": True,
            }
        ]
    )

    assert len(merged_candidates) == 1
    assert merged_candidates[0]["character_id"] == "his_agent"
    assert merged_candidates[0]["canonical_name"] == "His Agent"


def test_load_input_chunks_uses_source_chunks_when_translation_exists(tmp_path) -> None:
    """
    @brief      Verify character discovery keeps source chunks as the authoritative discovery input.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  AssertionError Raised when translated input is selected.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, _manifest = _create_character_project(tmp_path, "CharacterDiscoverySourcePreferred")
    artifact_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    (artifact_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "source_text": '"Hello there," said Alice.',
                    "translated_text": "\u00abBonjour\u00bb, dit Alice.",
                    "status": "approved",
                    "approved": True,
                    "target_language": "fr",
                }
            ],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    input_chunks = character_discovery_service.load_input_chunks(project_root)

    assert input_chunks[0]["text"] == '"Hello there," said Alice.'
    assert input_chunks[0]["input_source"] == character_discovery_service.CHARACTER_DISCOVERY_INPUT_SOURCE_CHUNKS
    assert input_chunks[0]["dialogue_spans"][0]["dialogue_span_id"] == "dialogue-001"


def test_load_input_chunks_ignores_mixed_translation_targets(tmp_path) -> None:
    """
    @brief      Verify character discovery never consumes mixed-language translation records.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  AssertionError Raised when mixed translation input is selected.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, _manifest = _create_character_project(tmp_path, "CharacterDiscoveryMixedTranslation")
    artifact_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    (artifact_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": None,
                    "text": '"Hello there," said Alice.',
                },
                {
                    "chunk_id": "chunk-0002",
                    "sequence_index": 2,
                    "chapter_label": None,
                    "text": '"Goodbye," said Bob.',
                },
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "source_text": '"Hello there," said Alice.',
                    "translated_text": "\u00abBonjour\u00bb, dit Alice.",
                    "status": "approved",
                    "approved": True,
                    "target_language": "fr",
                },
                {
                    "chunk_id": "chunk-0002",
                    "sequence_index": 2,
                    "source_text": '"Goodbye," said Bob.',
                    "translated_text": "\u00abAdios\u00bb, dijo Bob.",
                    "status": "approved",
                    "approved": True,
                    "target_language": "es",
                },
            ],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    input_chunks = character_discovery_service.load_input_chunks(project_root)

    assert [chunk["input_source"] for chunk in input_chunks] == [
        character_discovery_service.CHARACTER_DISCOVERY_INPUT_SOURCE_CHUNKS,
        character_discovery_service.CHARACTER_DISCOVERY_INPUT_SOURCE_CHUNKS,
    ]
    assert input_chunks[0]["text"] == '"Hello there," said Alice.'


def test_merge_character_candidates_reports_rejected_non_dialogue_candidates() -> None:
    """
    @brief      Verify rejected candidate diagnostics are retained for review.
    @return     None.
    @exception  AssertionError Raised when rejection diagnostics are missing.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    accepted, rejected = character_discovery_service._merge_character_candidates_with_rejections(  # noqa: SLF001
        [
            {
                "canonical_name": "Alice",
                "aliases": [],
                "evidence": [
                    {
                        "chunk_id": "chunk-0001",
                        "sequence_index": 1,
                        "dialogue_span_id": "dialogue-001",
                        "source_excerpt": "\u00abBonjour\u00bb",
                        "reason": "Direct speech punctuation.",
                        "confidence": "high",
                    }
                ],
            },
            {
                "canonical_name": "Narrated Bob",
                "aliases": [],
                "evidence": [
                    {
                        "chunk_id": "chunk-0001",
                        "sequence_index": 1,
                        "source_excerpt": "Bob walked into the room.",
                        "reason": "Mentioned in narration.",
                        "confidence": "low",
                    }
                ],
            },
        ]
    )

    assert [candidate["canonical_name"] for candidate in accepted] == ["Alice"]
    assert rejected == [
        {
            "canonical_name": "Narrated Bob",
            "reason": "missing_spoken_dialogue_evidence",
            "evidence_count": 1,
            "identity_merge_count": 1,
        }
    ]


def test_update_character_profile_marks_voice_definition_stale_when_facts_change(tmp_path) -> None:
    """
    @brief      Verify changing raw character facts without refreshing the voice-definition block marks the profile
                stale.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    1.0.0
    """
    project_root, _manifest = _create_character_project(tmp_path, "CharacterDiscoveryVoiceStale")
    discovery_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    persisted_profile = character_discovery_service.regenerate_character_voice_definition(_saved_profile_payload())
    (discovery_root / config.CHARACTER_PROFILE_FILE_NAME).write_text(
        json.dumps([persisted_profile], indent=2) + "\n",
        encoding="utf-8",
    )

    updated_profiles = character_discovery_service.update_character_profile(
        project_root,
        {
            **dict(persisted_profile),
            "description": "Updated literary facts without regenerating the voice definition.",
        },
    )

    updated_profile = updated_profiles[0]
    assert updated_profile["description"] == "Updated literary facts without regenerating the voice definition."
    assert updated_profile["voice_definition_stale"] is True
    assert character_discovery_service.load_character_profiles(project_root)[0]["voice_definition_stale"] is True


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


def test_budgeted_chunk_windows_use_eight_chunks_as_cap() -> None:
    source_chunks = [_chunk_payload(f"chunk-{index:04d}", index, "Short dialogue text.") for index in range(1, 11)]
    windows = character_discovery_service._build_chunk_windows(  # noqa: SLF001
        source_chunks,
        window_size=8,
        overlap=1,
        budget_metadata={"text_budget_tokens": 10000},
    )

    assert [len(window) for window in windows] == [8, 3]


def test_budgeted_chunk_windows_shrink_for_small_text_budget() -> None:
    source_chunks = [_chunk_payload(f"chunk-{index:04d}", index, '"Hello," said Alice. ' * 30) for index in range(1, 5)]
    windows = character_discovery_service._build_chunk_windows(  # noqa: SLF001
        source_chunks,
        window_size=8,
        overlap=1,
        budget_metadata={"text_budget_tokens": 260},
    )

    assert len(windows) > 1
    assert all(len(window) < 8 for window in windows)


def test_budgeted_chunk_windows_reject_oversized_single_chunk() -> None:
    source_chunks = [_chunk_payload("chunk-0001", 1, "Oversized text. " * 200)]

    with pytest.raises(ValueError, match="exceeds the available request input budget"):
        character_discovery_service._build_chunk_windows(  # noqa: SLF001
            source_chunks,
            window_size=8,
            overlap=1,
            budget_metadata={"text_budget_tokens": 50},
        )


def test_character_discovery_rejects_profile_with_too_little_context(monkeypatch, tmp_path) -> None:
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryTinyBudget")
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
    profile_payload = {
        **_profile_payload("profile-1"),
        "context_window": 1024,
        "max_output_tokens": 900,
    }

    with pytest.raises(ValueError, match="too little room for discovery input"):
        character_discovery_service.start_or_continue_discovery(
            project_root,
            manifest,
            profile_payload,
            progress_callback=lambda *_args: None,
            cancel_requested=lambda: False,
        )


def test_resume_state_rejects_changed_budget_metadata() -> None:
    current_budget = {
        "context_window": 4096,
        "max_output_tokens": 512,
        "prompt_budget_tokens": 20,
        "text_budget_tokens": 2000,
        "safety_margin_tokens": 409,
        "max_window_chunks": 8,
        "window_overlap": 1,
        "synthesis_prompt_budget_tokens": 20,
        "synthesis_payload_budget_tokens": 2000,
        "synthesis_max_evidence_items": 20,
    }
    previous_budget = {**current_budget, "max_output_tokens": 1024}

    restored = character_discovery_service._restore_resume_state(  # noqa: SLF001
        {
            "status": "running",
            "mode": character_discovery_service.CHARACTER_DISCOVERY_MODE_AI_ASSISTED,
            "resume_checkpoint": {
                "input_fingerprint": "abc",
                "profile_id": "profile-1",
                "total_window_count": 2,
                "completed_window_count": 1,
                "budget_metadata": previous_budget,
            },
        },
        input_fingerprint="abc",
        profile_id="profile-1",
        total_windows=2,
        budget_metadata=current_budget,
    )

    assert restored == (0, [], [], [], [], None)


def test_synthesis_candidate_payload_is_trimmed_to_budget_metadata() -> None:
    candidate = {
        "character_id": "alice",
        "canonical_name": "Alice",
        "aliases": ["Al"],
        "role_summary": "Lead speaker",
        "confidence": "high",
        "identity_merge_count": 1,
        "evidence": [
            {
                "chunk_id": f"chunk-{index:04d}",
                "sequence_index": index,
                "dialogue_span_id": "dialogue-001",
                "source_excerpt": '"A long line of dialogue that should be compacted."',
                "reason": "Direct dialogue evidence.",
                "confidence": "high",
            }
            for index in range(1, 40)
        ],
    }

    payload = character_discovery_service._budgeted_synthesis_candidate_payload(  # noqa: SLF001
        candidate,
        {
            "synthesis_payload_budget_tokens": 600,
            "synthesis_max_evidence_items": 12,
        },
    )

    assert len(payload["evidence"]) <= 12
    assert payload["evidence"][0]["chunk_id"] == "chunk-0001"


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
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}"
    ]
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    project_workspace_service.save_manifest(manifest, project_root)
    cleanup_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    chunk_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    discovery_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    cleanup_root.mkdir(parents=True, exist_ok=True)
    chunk_root.mkdir(parents=True, exist_ok=True)
    discovery_root.mkdir(parents=True, exist_ok=True)
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        '"Hello there," said Alice.\n',
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
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root, manifest


def _chunk_payload(chunk_id: str, sequence_index: int, text: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "sequence_index": sequence_index,
        "chapter_label": None,
        "input_source": character_discovery_service.CHARACTER_DISCOVERY_INPUT_SOURCE_CHUNKS,
        "text": text,
        "dialogue_spans": [],
    }


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
