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
@version 0.11.0
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import character_discovery_service, project_workspace_service


def test_start_discovery_persists_outputs_and_report(monkeypatch, tmp_path) -> None:
    """
    @brief      Validate start discovery persists outputs and report.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
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
    responses = iter(
        [
            {
                "payload": {
                    "characters": [
                        {
                            "canonical_name": "Alice",
                            "aliases": ["Al"],
                            "evidence": [
                                {
                                    "chunk_id": "chunk-0001",
                                    "source_excerpt": (
                                        '"Alice keeps her voice steady as she tells everyone to wait until the moon '
                                        'clears the tower."'
                                    ),
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
                    "gender_hint": "female",
                    "voice_definition_prompt": (
                        "Create a consistent spoken voice for Alice. Warm mezzo voice with gentle authority."
                    ),
                    "preview_text": (
                        "Alice keeps her voice steady as she tells everyone to wait until the moon clears the tower."
                    ),
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
    assert profiles[0]["gender_hint"] == "female"
    assert "gentle authority" in profiles[0]["voice_definition_prompt"]
    assert profiles[0]["preview_text"] == (
        "Alice keeps her voice steady as she tells everyone to wait until the moon clears the tower."
    )
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
    assert report["model_settings"] == {
        "model_name": "qwen3-8b",
        "context_window": 4096,
        "max_output_tokens": 512,
        "temperature": 0.2,
    }
    assert report["model_settings_history"] == [
        {
            "profile_id": "profile-1",
            "model_name": "qwen3-8b",
            "context_window": 4096,
            "max_output_tokens": 512,
            "temperature": 0.2,
        }
    ]
    assert report["token_usage"]["total_tokens"] == 135


def test_start_discovery_appends_and_persists_operator_character_rules(monkeypatch, tmp_path) -> None:
    """
    @brief      Validate optional operator Character Discovery rules are sent to AI prompts and persisted.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryExtraPrompt")
    additional_rules = "Treat titled names like Lady Catherine as character identities."
    requested_prompts: list[str] = []
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
                            "aliases": [],
                            "evidence": [
                                {
                                    "chunk_id": "chunk-0001",
                                    "source_excerpt": '"Alice keeps watch," said Alice.',
                                    "reason": "Alice speaks in direct dialogue.",
                                }
                            ],
                        }
                    ]
                },
                "usage": {"input_tokens": 40, "output_tokens": 12, "total_tokens": 52, "usage_available": True},
            },
            {
                "payload": {
                    "canonical_name": "Alice",
                    "gender_hint": "female",
                    "voice_definition_prompt": "Create a consistent spoken voice for Alice. Sex/Gender: female.",
                    "preview_text": "Alice keeps watch.",
                    "confidence": "high",
                },
                "usage": {"input_tokens": 30, "output_tokens": 14, "total_tokens": 44, "usage_available": True},
            },
        ]
    )

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Capture rendered prompts and return fake Character Discovery responses.
        @param[in]  _profile Ignored AI profile payload.
        @param[in]  _system_prompt Ignored system prompt.
        @param[in]  user_prompt Rendered user prompt.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake Character Discovery model response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-13
        @version    0.1.0
        """
        requested_prompts.append(str(user_prompt))
        return next(responses)

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _fake_chat_json)

    report = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        additional_character_discovery_instructions=additional_rules,
    )

    state = character_discovery_service.load_operation_state(project_root)
    assert len(requested_prompts) == 2
    assert all("Additional operator Character Discovery instructions:" in prompt for prompt in requested_prompts)
    assert all(additional_rules in prompt for prompt in requested_prompts)
    assert report["additional_character_discovery_instructions"] == additional_rules
    assert report["additional_character_discovery_instructions_fingerprint"] == (
        character_discovery_service._compute_prompt_fingerprint(additional_rules)  # noqa: SLF001
    )
    assert state is not None
    assert state["metadata"]["additional_character_discovery_instructions"] == additional_rules
    assert (
        state["metadata"]["additional_character_discovery_instructions_fingerprint"]
        == report["additional_character_discovery_instructions_fingerprint"]
    )


def test_start_discovery_resumes_from_saved_synthesis_checkpoint(monkeypatch, tmp_path) -> None:
    """
    @brief      Validate start discovery resumes from saved synthesis checkpoint.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
    call_profiles = []

    def _fake_chat_json(ai_profile_payload, *_args, **_kwargs):
        """
        @brief      Provide the fake chat json test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        call_profiles.append(dict(ai_profile_payload))
        return {
            "payload": {
                "canonical_name": "Alice",
                "gender_hint": "female",
                "voice_definition_prompt": (
                    "Create a consistent spoken voice for Alice. Clear and calm. Sex/Gender: female."
                ),
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
        {
            **_profile_payload("profile-2"),
            "model_name": "qwen3-14b",
            "context_window": 8192,
            "max_output_tokens": 1024,
            "temperature": 0.4,
        },
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )

    assert len(call_profiles) == 1
    assert call_profiles[0]["id"] == "profile-2"
    assert call_profiles[0]["model_name"] == "qwen3-14b"
    assert report["character_count"] == 1
    assert report["character_profile_id_last_used"] == "profile-2"
    assert report["model_settings"] == {
        "model_name": "qwen3-14b",
        "context_window": 8192,
        "max_output_tokens": 1024,
        "temperature": 0.4,
    }
    assert report["model_settings_history"][-1] == {
        "profile_id": "profile-2",
        "model_name": "qwen3-14b",
        "context_window": 8192,
        "max_output_tokens": 1024,
        "temperature": 0.4,
    }
    assert report["input_source"] == character_discovery_service.CHARACTER_DISCOVERY_INPUT_SOURCE_CHUNKS
    assert report["token_usage"]["total_tokens"] == 90
    state = character_discovery_service.load_operation_state(project_root)
    assert state is not None
    assert state["metadata"]["model_settings"] == report["model_settings"]
    assert state["metadata"]["model_settings_history"] == report["model_settings_history"]
    resumed_profile = character_discovery_service.load_character_profiles(project_root)[0]
    assert resumed_profile["gender_hint"] == "female"
    assert "Clear and calm" in resumed_profile["voice_definition_prompt"]


def test_manual_add_update_delete_and_reset(tmp_path) -> None:
    """
    @brief      Validate manual add update delete and reset.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
            "voice_definition_prompt": "Create a consistent spoken voice for Bob. Sex/Gender: unknown.",
            "confidence": "",
            "evidence": [dict(item) for item in bob_profile["evidence"]],
            "updated_at": None,
        },
    )
    updated_bob = next(
        profile for profile in updated_profiles if str(profile.get("character_id")) == str(bob_profile["character_id"])
    )
    assert "Bob" in updated_bob["voice_definition_prompt"]
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


def test_regenerate_character_voice_definition_preserves_compact_voice_prompt() -> None:
    """
    @brief      Verify local regeneration preserves the compact final voice-definition prompt.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    2.0.0
    """
    regenerated_profile = character_discovery_service.regenerate_character_voice_definition(
        {
            "character_id": "elizabeth",
            "canonical_name": "Elizabeth",
            "gender_hint": "female",
            "voice_definition_prompt": (
                "Create a consistent spoken voice for Elizabeth. Warm tone with restrained authority."
            ),
        }
    )

    assert regenerated_profile["voice_definition_prompt"].startswith("Create a consistent spoken voice for Elizabeth.")
    assert "Sex/Gender: female." in regenerated_profile["voice_definition_prompt"]


def test_build_profile_from_synthesis_uses_dialogue_preview_fallback() -> None:
    """
    @brief      Verify character synthesis derives a six-second preview from dialogue evidence.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    profile = character_discovery_service._build_profile_from_synthesis(  # noqa: SLF001
        {
            "canonical_name": "Alice",
            "gender_hint": "female",
            "voice_definition_prompt": "Create a consistent spoken voice for Alice. Clear and calm.",
            "preview_text": "Too short.",
            "confidence": "high",
        },
        {
            "character_id": "alice",
            "canonical_name": "Alice",
            "gender_hint": "female",
            "confidence": "high",
            "evidence": [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "dialogue_span_id": "dialogue-001",
                    "source_excerpt": '"Stay close to me while the storm passes over the harbor."',
                    "reason": "Alice speaks.",
                    "confidence": "high",
                },
                {
                    "chunk_id": "chunk-0002",
                    "sequence_index": 2,
                    "dialogue_span_id": "dialogue-002",
                    "source_excerpt": '"When the lamps are lit, we will cross the square together."',
                    "reason": "Alice speaks again.",
                    "confidence": "high",
                },
            ],
        },
    )

    assert profile["preview_text"] == (
        "Stay close to me while the storm passes over the harbor. "
        "When the lamps are lit, we will cross the square together."
    )


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


def test_validate_manual_character_name_rejects_duplicates_and_invalid_names() -> None:
    """
    @brief      Validate validate manual character name rejects duplicates and invalid names.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
    """
    @brief      Validate budgeted chunk windows use eight chunks as cap.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    source_chunks = [_chunk_payload(f"chunk-{index:04d}", index, "Short dialogue text.") for index in range(1, 11)]
    windows = character_discovery_service._build_chunk_windows(  # noqa: SLF001
        source_chunks,
        window_size=8,
        overlap=1,
        budget_metadata={"text_budget_tokens": 10000},
    )

    assert [len(window) for window in windows] == [8, 3]


def test_character_discovery_online_profile_uses_direct_context_fraction_without_chunk_cap(monkeypatch) -> None:
    """
    @brief      Validate online character discovery ignores local chunk caps and output-token budget subtraction.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    monkeypatch.setattr(
        character_discovery_service.prompt_template_service,
        "render_prompt",
        lambda prompt_name, payload: f"{prompt_name}:{payload}",
    )
    profile_payload = {
        "backend_kind": config.ONLINE_AI_BACKEND_KIND,
        "context_window": 10000,
        "max_output_tokens": 9900,
    }

    budget_metadata = character_discovery_service._build_budget_metadata(profile_payload, "system")
    source_chunks = [
        {"chunk_id": f"chunk-{index:04d}", "text": "Short character-discovery chunk."} for index in range(1, 12)
    ]

    assert budget_metadata["text_budget_tokens"] == 3000
    assert budget_metadata["synthesis_payload_budget_tokens"] == 3000
    assert budget_metadata["max_window_chunks"] == 0
    assert character_discovery_service._build_chunk_windows(
        source_chunks,
        window_size=budget_metadata["max_window_chunks"],
        overlap=budget_metadata["window_overlap"],
        budget_metadata=budget_metadata,
    ) == [source_chunks]


def test_budgeted_chunk_windows_shrink_for_small_text_budget() -> None:
    """
    @brief      Validate budgeted chunk windows shrink for small text budget.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
    """
    @brief      Validate budgeted chunk windows reject oversized single chunk.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    source_chunks = [_chunk_payload("chunk-0001", 1, "Oversized text. " * 200)]

    with pytest.raises(ValueError, match="exceeds the available request input budget"):
        character_discovery_service._build_chunk_windows(  # noqa: SLF001
            source_chunks,
            window_size=8,
            overlap=1,
            budget_metadata={"text_budget_tokens": 50},
        )


def test_character_discovery_rejects_profile_with_too_little_context(monkeypatch, tmp_path) -> None:
    """
    @brief      Validate character discovery rejects profile with too little context.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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


def test_resume_state_accepts_changed_profile_and_budget_metadata() -> None:
    """
    @brief      Validate resume state accepts changed profile and budget metadata.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
    source_chunks = [
        _chunk_payload("chunk-0001", 1, '"Hello," said Alice.'),
        _chunk_payload("chunk-0002", 2, '"Hi," said Bob.'),
    ]
    resume_candidate = {
        "character_id": "alice",
        "canonical_name": "Alice",
        "evidence": [{"chunk_id": "chunk-0001", "sequence_index": 1}],
    }

    restored = character_discovery_service._restore_resume_state(  # noqa: SLF001
        {
            "status": "running",
            "mode": character_discovery_service.CHARACTER_DISCOVERY_MODE_AI_ASSISTED,
            "resume_checkpoint": {
                "input_fingerprint": "abc",
                "profile_id": "profile-1",
                "total_window_count": 2,
                "completed_window_count": 1,
                "next_discovery_start_chunk_index": 1,
                "budget_metadata": previous_budget,
                "raw_candidates": [resume_candidate],
            },
        },
        input_fingerprint="abc",
        source_chunks=source_chunks,
        budget_metadata=current_budget,
    )

    assert restored[0] == 1
    assert restored[1] == 1
    assert restored[2] == [resume_candidate]


def test_synthesis_candidate_payload_is_trimmed_to_budget_metadata() -> None:
    """
    @brief      Validate synthesis candidate payload is trimmed to budget metadata.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    candidate = {
        "character_id": "alice",
        "canonical_name": "Alice",
        "aliases": ["Al"],
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
    """
    @brief      Provide the create character project test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
    """
    @brief      Provide the chunk payload test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    return {
        "chunk_id": chunk_id,
        "sequence_index": sequence_index,
        "chapter_label": None,
        "input_source": character_discovery_service.CHARACTER_DISCOVERY_INPUT_SOURCE_CHUNKS,
        "text": text,
        "dialogue_spans": [],
    }


def _profile_payload(profile_id: str) -> dict[str, object]:
    """
    @brief      Provide the profile payload test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
    """
    @brief      Provide the saved profile payload test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    return {
        "character_id": "alice",
        "canonical_name": "Alice",
        "aliases": ["Al"],
        "gender_hint": "",
        "voice_definition_prompt": "Create a consistent spoken voice for Alice.",
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
