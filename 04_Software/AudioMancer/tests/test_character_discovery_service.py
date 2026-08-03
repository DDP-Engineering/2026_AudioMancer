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
"""

# IMPORTS

import json
from pathlib import Path

import pytest

from audiomancer import config
from audiomancer.services import character_discovery_service, narrator_definition_service, project_workspace_service
from chunking_test_support import build_chunking_document


def test_character_discovery_prompts_request_demographic_confidence() -> None:
    """
    @brief      Verify Character Discovery prompts request demographic hints and confidence values.
    @return     None.
    @exception  None
    """
    window_prompt_text = (config.APP_PROMPTS_PATH / "character_discovery_window_user.txt").read_text(encoding="utf-8")
    synthesis_prompt_text = (config.APP_PROMPTS_PATH / "character_profile_synthesis_user.txt").read_text(
        encoding="utf-8"
    )

    assert '"gender_hint": ""' in window_prompt_text
    assert '"gender_confidence": ""' in window_prompt_text
    assert '"age_hint": ""' in window_prompt_text
    assert '"age_confidence": ""' in window_prompt_text
    assert "Demographic inference rules:" in window_prompt_text
    assert "Do not infer sex/gender from occupation alone." in window_prompt_text
    assert '"gender_confidence": ""' in synthesis_prompt_text
    assert '"age_confidence": ""' in synthesis_prompt_text
    assert "Demographic synthesis rules:" in synthesis_prompt_text


def test_start_discovery_persists_one_authoritative_document(monkeypatch, tmp_path) -> None:
    """
    @brief      Validate start discovery persists outputs and report.
    @return     None.
    @exception  None
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
                            "gender_hint": "female",
                            "gender_confidence": "high",
                            "age_hint": "adult",
                            "age_confidence": "medium",
                            "confidence": "high",
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
                    "gender_confidence": "high",
                    "age_hint": "adult",
                    "age_confidence": "medium",
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

    document = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )

    assert document["status"] == "completed"
    assert document["checkpoint"] is None
    assert document["failure"] is None
    assert document["source"]["kind"] == character_discovery_service.CHARACTER_DISCOVERY_INPUT_SOURCE_ORIGINAL
    assert document["token_usage"]["total_tokens"] == 135
    assert set(document) == {
        "status",
        "source",
        "instructions",
        "token_usage",
        "checkpoint",
        "failure",
        "characters",
    }
    assert set(document["characters"][0]) == {
        "character_id",
        "canonical_name",
        "aliases",
        "traits",
        "voice",
        "discovery_confidence",
        "provenance",
        "evidence",
    }
    profiles = character_discovery_service.load_character_profiles(project_root)
    assert len(profiles) == 1
    assert profiles[0]["canonical_name"] == "Alice"
    assert profiles[0]["gender_hint"] == "female"
    assert profiles[0]["gender_confidence"] == "high"
    assert profiles[0]["age_hint"] == "adult"
    assert profiles[0]["age_confidence"] == "medium"
    assert "gentle authority" in profiles[0]["voice_definition_prompt"]
    assert "Age Domain: adult (medium confidence)." in profiles[0]["voice_definition_prompt"]
    assert profiles[0]["preview_text"] == (
        "Alice keeps her voice steady as she tells everyone to wait until the moon clears the tower."
    )
    assert profiles[0]["evidence"][0]["chunk_id"] == "chunk-0001"
    assert character_discovery_service.load_input_chunks(project_root)[0]["chunk_id"] == "chunk-0001"
    assert (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHUNK_ARTIFACT_FILE_NAME).is_file()
    assert (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME).is_file()
    document_path = (
        project_root
        / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
        / config.CHARACTERS_DOCUMENT_FILE_NAME
    )
    assert document_path.is_file()
    assert character_discovery_service.load_character_document(project_root) == document
    assert list(project_root.glob("log_ai_characters_*.log"))
    manifest_operation = project_workspace_service.load_manifest(project_root)["operations"]["character_discovery"]
    assert manifest_operation["status"] == "completed"
    assert "checkpoint" not in manifest_operation
    assert "log_relative_path" not in manifest_operation
    serialized_document = document_path.read_text(encoding="utf-8")
    assert "profile-1" not in serialized_document
    assert "qwen3-8b" not in serialized_document
    assert "temperature" not in serialized_document
    assert "max_output_tokens" not in serialized_document


def test_start_discovery_appends_and_persists_operator_character_rules(monkeypatch, tmp_path) -> None:
    """
    @brief      Validate optional operator Character Discovery rules are sent to AI prompts and persisted.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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
        """
        requested_prompts.append(str(user_prompt))
        return next(responses)

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _fake_chat_json)

    document = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        additional_character_discovery_instructions=additional_rules,
    )

    assert len(requested_prompts) == 2
    assert all("Additional operator Character Discovery instructions:" in prompt for prompt in requested_prompts)
    assert all(additional_rules in prompt for prompt in requested_prompts)
    assert document["instructions"] == additional_rules
    assert "instructions_fingerprint" not in document


def test_start_discovery_resumes_from_saved_synthesis_checkpoint(monkeypatch, tmp_path) -> None:
    """
    @brief      Validate start discovery resumes from saved synthesis checkpoint.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryResume")
    _resolved_chunks, source = character_discovery_service._resolve_discovery_input_chunks(project_root)  # noqa: SLF001
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
    resume_candidate = {
        "character_id": "alice",
        "canonical_name": "Alice",
        "aliases": ["Al"],
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
    character_discovery_service.write_character_document(
        project_root,
        _character_document(
            source,
            status="running",
            checkpoint={
                "phase": "synthesis",
                "next_candidate_index": 0,
                "candidates": [resume_candidate],
            },
        ),
    )
    call_profiles = []
    log_paths = []

    def _fake_chat_json(ai_profile_payload, *_args, **kwargs):
        """
        @brief      Provide the fake chat json test helper.
        @return     None.
        @exception  None
        """
        call_profiles.append(dict(ai_profile_payload))
        log_paths.append(Path(kwargs["log_path"]).name)
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
    assert len(log_paths) == 1
    assert log_paths[0].startswith("log_ai_characters_")
    assert call_profiles[0]["id"] == "profile-2"
    assert call_profiles[0]["model_name"] == "qwen3-14b"
    assert report["status"] == "completed"
    assert len(report["characters"]) == 1
    assert report["source"]["kind"] == character_discovery_service.CHARACTER_DISCOVERY_INPUT_SOURCE_ORIGINAL
    assert report["token_usage"]["total_tokens"] == 90
    assert report["checkpoint"] is None
    resumed_profile = character_discovery_service.load_character_profiles(project_root)[0]
    assert resumed_profile["gender_hint"] == "female"
    assert "Clear and calm" in resumed_profile["voice_definition_prompt"]


def test_character_discovery_strictly_rejects_malformed_and_invalid_root_payloads(tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-012 malformed Character Discovery artifacts degrade to missing data.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_character_project(tmp_path, "CharacterDiscoveryMalformedArtifacts")
    discovery_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    document_path = discovery_root / config.CHARACTERS_DOCUMENT_FILE_NAME
    document_path.write_text('{"broken": ', encoding="utf-8")
    with pytest.raises(character_discovery_service.CharacterDocumentError):
        character_discovery_service.load_character_document(project_root)

    document_path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(character_discovery_service.CharacterDocumentError):
        character_discovery_service.load_character_document(project_root)

    document_path.write_text(json.dumps({"status": "completed"}) + "\n", encoding="utf-8")
    with pytest.raises(character_discovery_service.CharacterDocumentError):
        character_discovery_service.load_character_document(project_root)


def test_start_discovery_persists_cancelled_state_and_resumes_synthesis(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-012 cancelled synthesis persists a resumable checkpoint without repeating windows.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryCancelledResume")
    _patch_character_discovery_prompt_rendering(monkeypatch)
    call_stages: list[str] = []

    def _cancel_during_synthesis(*_args, **kwargs):
        """
        @brief      Provide a fake model that cancels during profile synthesis.
        @return     Fake model response for discovery windows.
        @exception  OperationCancelledError Raised for the synthesis call.
        """
        stage_label = str(kwargs["log_context"]["stage_label"])
        call_stages.append(stage_label)
        if stage_label == "character_profile_synthesis":
            raise character_discovery_service.OperationCancelledError("cancelled")
        return _window_response_payload()

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _cancel_during_synthesis)

    with pytest.raises(character_discovery_service.OperationCancelledError):
        character_discovery_service.start_or_continue_discovery(
            project_root,
            manifest,
            _profile_payload("profile-1"),
            progress_callback=lambda *_args: None,
            cancel_requested=lambda: False,
        )

    cancelled_document = character_discovery_service.load_character_document(project_root)
    assert cancelled_document is not None
    assert cancelled_document["status"] == "cancelled"
    assert cancelled_document["checkpoint"]["phase"] == "synthesis"
    assert cancelled_document["checkpoint"]["next_candidate_index"] == 0
    assert len(cancelled_document["checkpoint"]["candidates"]) == 1
    assert cancelled_document["characters"] == []

    resumed_stages: list[str] = []

    def _resume_synthesis(*_args, **kwargs):
        """
        @brief      Provide a fake model that records resumed synthesis calls.
        @return     Fake synthesis payload.
        @exception  None
        """
        resumed_stages.append(str(kwargs["log_context"]["stage_label"]))
        return _synthesis_response_payload()

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _resume_synthesis)

    report = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )

    assert call_stages == ["character_discovery_window", "character_profile_synthesis"]
    assert resumed_stages == ["character_profile_synthesis"]
    assert len(report["characters"]) == 1


def test_start_discovery_persists_failed_state(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-012 synthesis failures persist a failed checkpoint.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryFailedState")
    _patch_character_discovery_prompt_rendering(monkeypatch)

    def _fail_during_synthesis(*_args, **kwargs):
        """
        @brief      Provide a fake model that fails during profile synthesis.
        @return     Fake model response for discovery windows.
        @exception  RuntimeError Raised for the synthesis call.
        """
        if str(kwargs["log_context"]["stage_label"]) == "character_profile_synthesis":
            raise RuntimeError("model failed")
        return _window_response_payload()

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _fail_during_synthesis)

    with pytest.raises(RuntimeError, match="model failed"):
        character_discovery_service.start_or_continue_discovery(
            project_root,
            manifest,
            _profile_payload("profile-1"),
            progress_callback=lambda *_args: None,
            cancel_requested=lambda: False,
        )

    failed_document = character_discovery_service.load_character_document(project_root)
    assert failed_document is not None
    assert failed_document["status"] == "failed"
    assert failed_document["checkpoint"]["phase"] == "synthesis"
    assert failed_document["checkpoint"]["next_candidate_index"] == 0
    assert failed_document["failure"]["phase"] == "synthesis"


def test_start_discovery_builds_windows_once(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-NFR-017 discovery startup avoids duplicate full-window construction.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoverySingleWindowBuild")
    _patch_character_discovery_prompt_rendering(monkeypatch)
    original_build_chunk_windows = character_discovery_service._build_chunk_windows  # noqa: SLF001
    build_call_count = 0

    def _count_build_chunk_windows(*args, **kwargs):
        """
        @brief      Count request-window construction calls.
        @return     Original window construction result.
        @exception  ValueError Propagated from original window construction.
        """
        nonlocal build_call_count
        build_call_count += 1
        return original_build_chunk_windows(*args, **kwargs)

    responses = iter([_window_response_payload(), _synthesis_response_payload()])
    monkeypatch.setattr(character_discovery_service, "_build_chunk_windows", _count_build_chunk_windows)
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

    assert build_call_count == 1


def test_manual_add_update_delete_and_reset(tmp_path) -> None:
    """
    @brief      Validate manual add update delete and reset.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_character_project(tmp_path, "CharacterDiscoveryManual")
    discovery_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    _chunks, source = character_discovery_service._resolve_discovery_input_chunks(project_root)  # noqa: SLF001
    character_discovery_service.write_character_document(
        project_root,
        _character_document(
            source,
            status="completed",
            checkpoint=None,
            characters=[_nested_saved_character()],
        ),
    )
    narrator_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    narrator_root.mkdir(parents=True, exist_ok=True)
    narrator_definition_service.ensure_narrator_voice_document(project_root)

    existing_alice = character_discovery_service.load_character_profiles(project_root)[0]
    assert existing_alice["gender_confidence"] == ""
    assert existing_alice["age_confidence"] == ""

    added_profiles = character_discovery_service.add_character_profile(project_root, "Bob")
    bob_profile = next(profile for profile in added_profiles if str(profile.get("canonical_name")) == "Bob")
    assert bob_profile["evidence"][0]["chunk_id"] == character_discovery_service.MANUAL_CHARACTER_EVIDENCE_CHUNK_ID
    assert bob_profile["review_status"] == character_discovery_service.CHARACTER_REVIEW_STATUS_MANUAL
    added_document = character_discovery_service.load_character_document(project_root)
    added_bob = next(
        item
        for item in added_document["characters"]
        if item["character_id"] == bob_profile["character_id"]
    )
    assert added_bob["provenance"] == {"origin": "manual", "edited": False}

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
    edited_document = character_discovery_service.load_character_document(project_root)
    edited_bob = next(
        item
        for item in edited_document["characters"]
        if item["character_id"] == bob_profile["character_id"]
    )
    assert edited_bob["provenance"] == {"origin": "manual", "edited": True}

    remaining_profiles = character_discovery_service.delete_character_profile(
        project_root,
        str(bob_profile["character_id"]),
    )
    assert len(remaining_profiles) == 1
    assert remaining_profiles[0]["character_id"] == "alice"
    updated_document = character_discovery_service.load_character_document(project_root)
    assert updated_document is not None
    assert updated_document["status"] == "completed"
    assert updated_document["characters"][0]["provenance"] == {"origin": "ai", "edited": False}

    character_discovery_service.reset_character_discovery(project_root)

    assert not (discovery_root / config.CHARACTERS_DOCUMENT_FILE_NAME).exists()
    assert (narrator_root / config.NARRATOR_VOICE_FILE_NAME).is_file()
    assert (discovery_root / config.CHUNK_ARTIFACT_FILE_NAME).is_file()


def test_regenerate_character_voice_definition_preserves_compact_voice_prompt() -> None:
    """
    @brief      Verify local regeneration preserves the compact final voice-definition prompt.
    @return     None.
    @exception  None
    """
    regenerated_profile = character_discovery_service.regenerate_character_voice_definition(
        {
            "character_id": "elizabeth",
            "canonical_name": "Elizabeth",
            "gender_hint": "female",
            "age_hint": "young adult",
            "voice_definition_prompt": (
                "Create a consistent spoken voice for Elizabeth. Warm tone with restrained authority."
            ),
        }
    )

    assert regenerated_profile["voice_definition_prompt"].startswith("Create a consistent spoken voice for Elizabeth.")
    assert "Sex/Gender: female." in regenerated_profile["voice_definition_prompt"]
    assert "Age Domain: young adult." in regenerated_profile["voice_definition_prompt"]


def test_regenerate_character_voice_definition_prevents_young_default_when_age_unknown() -> None:
    """
    @brief      Verify character voice prompts carry explicit unknown-age guidance.
    @return     None.
    @exception  None
    """
    regenerated_profile = character_discovery_service.regenerate_character_voice_definition(
        {
            "character_id": "ayla",
            "canonical_name": "Ayla",
            "voice_definition_prompt": "Create a consistent spoken voice for Ayla.",
        }
    )

    assert "Age Domain: not specified in the source." in regenerated_profile["voice_definition_prompt"]
    assert "do not default to a young voice" in regenerated_profile["voice_definition_prompt"]


def test_regenerate_character_voice_definition_does_not_duplicate_explicit_age_guidance() -> None:
    """
    @brief      Verify character prompt regeneration preserves one explicit age-domain instruction.
    @return     None.
    @exception  None
    """
    regenerated_profile = character_discovery_service.regenerate_character_voice_definition(
        {
            "character_id": "mentor",
            "canonical_name": "Mentor",
            "age_hint": "old",
            "voice_definition_prompt": (
                "Create a consistent spoken voice for Mentor. Age Domain: old. Weathered but controlled."
            ),
        }
    )

    assert regenerated_profile["voice_definition_prompt"].count("Age Domain:") == 1


def test_build_profile_from_synthesis_uses_dialogue_preview_fallback() -> None:
    """
    @brief      Verify character synthesis derives a six-second preview from dialogue evidence.
    @return     None.
    @exception  None
    """
    profile = character_discovery_service._build_profile_from_synthesis(  # noqa: SLF001
        {
            "canonical_name": "Alice",
            "gender_hint": "female",
            "age_hint": "adult",
            "voice_definition_prompt": "Create a consistent spoken voice for Alice. Clear and calm.",
            "preview_text": "Too short.",
            "confidence": "high",
        },
        {
            "character_id": "alice",
            "canonical_name": "Alice",
            "gender_hint": "female",
            "age_hint": "adult",
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
    assert profile["age_hint"] == "adult"
    assert "Age Domain: adult." in profile["voice_definition_prompt"]


def test_merge_character_candidates_keeps_role_speaker_candidate() -> None:
    """
    @brief      Verify merged candidates preserve deterministic role speakers as dialogue characters.
    @return     None.
    @exception  None
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


def test_merge_character_candidates_keeps_strongest_demographic_confidence() -> None:
    """
    @brief      Verify merged candidates keep the strongest demographic hint/confidence pairs.
    @return     None.
    @exception  None
    """
    merged_candidates = character_discovery_service._merge_character_candidates(  # noqa: SLF001
        [
            {
                "canonical_name": "The Pilot",
                "aliases": ["pilot"],
                "gender_hint": "male",
                "gender_confidence": "low",
                "age_hint": "adult",
                "age_confidence": "medium",
                "confidence": "high",
                "evidence": [
                    {
                        "chunk_id": "chunk-0001",
                        "sequence_index": 1,
                        "source_excerpt": '"Roger," said the military pilot.',
                        "reason": "Direct speech is attributed to a military pilot.",
                        "confidence": "high",
                    }
                ],
                "has_dialogue_evidence": True,
            },
            {
                "canonical_name": "pilot",
                "aliases": ["The Pilot"],
                "gender_hint": "female",
                "gender_confidence": "high",
                "age_hint": "middle-aged",
                "age_confidence": "low",
                "confidence": "medium",
                "evidence": [
                    {
                        "chunk_id": "chunk-0002",
                        "sequence_index": 2,
                        "source_excerpt": '"Hold formation," she said.',
                        "reason": "Pronoun evidence supports the speaker's gender.",
                        "confidence": "high",
                    }
                ],
                "has_dialogue_evidence": True,
            },
        ]
    )

    assert len(merged_candidates) == 1
    assert merged_candidates[0]["gender_hint"] == "female"
    assert merged_candidates[0]["gender_confidence"] == "high"
    assert merged_candidates[0]["age_hint"] == "adult"
    assert merged_candidates[0]["age_confidence"] == "medium"
    assert merged_candidates[0]["confidence"] == "high"


def test_window_candidate_normalization_preserves_demographic_confidence() -> None:
    """
    @brief      Verify window candidate normalization preserves current demographic fields only.
    @return     None.
    @exception  None
    """
    source_chunk = _chunk_payload("chunk-0001", 1, '"Hello," said Alice.')
    chunk_map = {"chunk-0001": source_chunk}

    assert (
        character_discovery_service._normalize_window_candidates(  # noqa: SLF001
            [
                {
                    "name": "Alice",
                    "evidence": [{"chunk_id": "chunk-0001"}],
                }
            ],
            chunk_map,
        )
        == []
    )

    normalized_candidates = character_discovery_service._normalize_window_candidates(  # noqa: SLF001
        [
            {
                "canonical_name": "Alice",
                "gender_hint": "female",
                "gender_confidence": "HIGH",
                "voice_definition_prompt": "Old discovery-pass voice prompt.",
                "age_hint": "adult",
                "age_confidence": "medium",
                "confidence": "high",
                "evidence": [{"chunk_id": "chunk-0001"}],
            }
        ],
        chunk_map,
    )

    assert normalized_candidates[0]["canonical_name"] == "Alice"
    assert normalized_candidates[0]["gender_hint"] == "female"
    assert normalized_candidates[0]["gender_confidence"] == "high"
    assert normalized_candidates[0]["age_hint"] == "adult"
    assert normalized_candidates[0]["age_confidence"] == "medium"
    assert "voice_definition_prompt" not in normalized_candidates[0]


def test_load_input_chunks_uses_fully_approved_translation(tmp_path) -> None:
    """
    @brief      Verify character discovery keeps source chunks as the authoritative discovery input.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  AssertionError Raised when translated input is selected.
    """
    project_root, _manifest = _create_character_project(tmp_path, "CharacterDiscoverySourcePreferred")
    artifact_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    (artifact_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
        json.dumps(
            {
                "target_language": "fr",
                "status": "completed",
                "token_usage": _empty_token_usage(),
                "budget_metadata": {},
                "additional_translation_instructions": "",
                "chunks": [
                {
                    "chunk_id": "chunk-0001",
                    "translated_text": "\u00abBonjour\u00bb, dit Alice.",
                    "approved": True,
                }
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    input_chunks = character_discovery_service.load_input_chunks(project_root)

    assert input_chunks[0]["text"] == "\u00abBonjour\u00bb, dit Alice."
    assert (
        input_chunks[0]["input_source"]
        == character_discovery_service.CHARACTER_DISCOVERY_INPUT_SOURCE_TRANSLATED
    )
    assert input_chunks[0]["dialogue_spans"][0]["dialogue_span_id"] == "dialogue-001"


def test_load_input_chunks_derives_runtime_chapter_context(tmp_path) -> None:
    """
    @brief      Verify discovery derives chapter context without persisted chunk metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  AssertionError Raised when runtime chapter context is not carried forward.
    """
    project_root, _manifest = _create_character_project(tmp_path, "CharacterDiscoveryRuntimeChapter")
    artifact_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    (artifact_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            build_chunking_document(
                [
                    {
                        "chunk_id": "chunk-0001",
                        "sequence_index": 1,
                        "text": "Chapter I\n\nAlice waits at the gate.",
                    },
                    {
                        "chunk_id": "chunk-0002",
                        "sequence_index": 2,
                        "text": '"Come inside," said Alice.',
                    },
                ]
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    input_chunks = character_discovery_service.load_input_chunks(project_root)

    persisted_chunks = json.loads((artifact_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))[
        "chunks"
    ]
    assert input_chunks[0]["chapter_label"] == "Chapter I"
    assert input_chunks[1]["chapter_label"] == "Chapter I"
    assert "chapter_label" not in persisted_chunks[0]


def test_load_input_chunks_uses_original_when_translation_is_not_fully_approved(tmp_path) -> None:
    """
    @brief      Verify character discovery never consumes mixed-language translation records.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  AssertionError Raised when mixed translation input is selected.
    """
    project_root, _manifest = _create_character_project(tmp_path, "CharacterDiscoveryMixedTranslation")
    artifact_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    (artifact_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            build_chunking_document(
                [
                    {
                        "chunk_id": "chunk-0001",
                        "sequence_index": 1,
                        "text": '"Hello there," said Alice.',
                    },
                    {
                        "chunk_id": "chunk-0002",
                        "sequence_index": 2,
                        "text": '"Goodbye," said Bob.',
                    },
                ]
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
        json.dumps(
            {
                "target_language": "fr",
                "status": "review_pending",
                "token_usage": _empty_token_usage(),
                "budget_metadata": {},
                "additional_translation_instructions": "",
                "chunks": [
                {
                    "chunk_id": "chunk-0001",
                    "translated_text": "\u00abBonjour\u00bb, dit Alice.",
                    "approved": True,
                },
                {
                    "chunk_id": "chunk-0002",
                    "translated_text": "\u00abAu revoir\u00bb, dit Bob.",
                    "approved": False,
                },
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    input_chunks = character_discovery_service.load_input_chunks(project_root)

    assert [chunk["input_source"] for chunk in input_chunks] == [
        character_discovery_service.CHARACTER_DISCOVERY_INPUT_SOURCE_ORIGINAL,
        character_discovery_service.CHARACTER_DISCOVERY_INPUT_SOURCE_ORIGINAL,
    ]
    assert input_chunks[0]["text"] == '"Hello there," said Alice.'


def test_merge_character_candidates_reports_rejected_non_dialogue_candidates() -> None:
    """
    @brief      Verify rejected candidate diagnostics are retained for review.
    @return     None.
    @exception  AssertionError Raised when rejection diagnostics are missing.
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


def test_group_character_candidates_preserves_first_match_order() -> None:
    """
    @brief      Verify REQ-NFR-017 indexed identity grouping preserves first-match semantics.
    @return     None.
    @exception  None
    """
    candidates = [
        {"canonical_name": "Alice", "aliases": ["A"]},
        {"canonical_name": "Beth", "aliases": ["B"]},
        {"canonical_name": "Bridge", "aliases": ["B", "A"]},
        {"canonical_name": "Beatrice", "aliases": ["B"]},
        {"canonical_name": "Cara", "aliases": ["C"]},
    ]

    reference_groups = _reference_group_character_candidates_by_identity(candidates)
    indexed_groups = character_discovery_service._group_character_candidates_by_identity(candidates)  # noqa: SLF001

    assert indexed_groups == reference_groups
    assert [[str(candidate["canonical_name"]) for candidate in group] for group in indexed_groups] == [
        ["Alice", "Bridge", "Beatrice"],
        ["Beth"],
        ["Cara"],
    ]


def test_validate_manual_character_name_rejects_duplicates_and_invalid_names() -> None:
    """
    @brief      Validate validate manual character name rejects duplicates and invalid names.
    @return     None.
    @exception  None
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


def test_resume_state_requires_current_checkpoint_boundary() -> None:
    """
    @brief      Validate resume state requires current checkpoint boundary.
    @return     None.
    @exception  None
    """
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
            "source": {"kind": "original", "language": "en", "fingerprint": "abc"},
            "characters": [],
            "checkpoint": {
                "phase": "discovery",
                "next_chunk_index": 1,
                "candidates": [resume_candidate],
            },
        },
        input_fingerprint="abc",
        source_chunks=source_chunks,
    )

    assert restored[0] == 1
    assert restored[1] == 1
    assert restored[2] == [resume_candidate]

    stale_restored = character_discovery_service._restore_resume_state(  # noqa: SLF001
        {
            "status": "running",
            "source": {"kind": "original", "language": "en", "fingerprint": "abc"},
            "characters": [],
            "checkpoint": {
                "phase": "discovery",
                "candidates": [resume_candidate],
            },
        },
        input_fingerprint="abc",
        source_chunks=source_chunks,
    )
    assert stale_restored == (0, 0, [], [], [], [], None)


def test_synthesis_candidate_payload_is_trimmed_to_budget_metadata() -> None:
    """
    @brief      Validate synthesis candidate payload is trimmed to budget metadata.
    @return     None.
    @exception  None
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


def _patch_character_discovery_prompt_rendering(monkeypatch) -> None:
    """
    @brief      Patch prompt rendering for focused Character Discovery service tests.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
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


def _window_response_payload() -> dict[str, object]:
    """
    @brief      Build a focused fake Character Discovery window response.
    @return     Fake model response payload.
    @exception  None
    """
    return {
        "payload": {
            "characters": [
                {
                    "canonical_name": "Alice",
                    "aliases": ["Al"],
                    "confidence": "high",
                    "evidence": [
                        {
                            "chunk_id": "chunk-0001",
                            "source_excerpt": '"Hello there," said Alice.',
                            "reason": "Alice speaks in direct dialogue.",
                        }
                    ],
                }
            ]
        },
        "usage": {"input_tokens": 60, "output_tokens": 15, "total_tokens": 75, "usage_available": True},
    }


def _synthesis_response_payload() -> dict[str, object]:
    """
    @brief      Build a focused fake Character Discovery synthesis response.
    @return     Fake model response payload.
    @exception  None
    """
    return {
        "payload": {
            "canonical_name": "Alice",
            "aliases": ["Al"],
            "voice_definition_prompt": "Create a consistent spoken voice for Alice. Clear and calm.",
            "preview_text": "Hello there, said Alice with a calm and friendly voice today.",
            "confidence": "high",
        },
        "usage": {"input_tokens": 40, "output_tokens": 20, "total_tokens": 60, "usage_available": True},
    }


def _reference_group_character_candidates_by_identity(
    candidates: list[dict[str, object]],
) -> list[list[dict[str, object]]]:
    """
    @brief      Provide a simple identity-grouping reference for equivalence tests.
    @param[in]  candidates Candidate payload list.
    @return     Identity groups from the reference scan algorithm.
    @exception  None
    """
    groups: list[list[dict[str, object]]] = []
    for candidate in candidates:
        alias_keys = {character_discovery_service._normalize_identity(str(candidate.get("canonical_name", "")))}  # noqa: SLF001
        alias_keys.update(
            character_discovery_service._normalize_identity(alias)  # noqa: SLF001
            for alias in list(candidate.get("aliases", []))
        )
        alias_keys.discard("")
        target_group = None
        for group in groups:
            group_alias_keys: set[str] = set()
            for group_candidate in group:
                group_alias_keys.add(
                    character_discovery_service._normalize_identity(  # noqa: SLF001
                        str(group_candidate.get("canonical_name", ""))
                    )
                )
                group_alias_keys.update(
                    character_discovery_service._normalize_identity(alias)  # noqa: SLF001
                    for alias in list(group_candidate.get("aliases", []))
                )
            if alias_keys.intersection(group_alias_keys):
                target_group = group
                break
        if target_group is None:
            groups.append([dict(candidate)])
        else:
            target_group.append(dict(candidate))
    return groups


def _create_character_project(tmp_path, project_name: str):
    """
    @brief      Provide the create character project test helper.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  project_name Unique project name used by the test fixture.
    @return     None.
    @exception  None
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
            build_chunking_document(
                [
                    {
                        "chunk_id": "chunk-0001",
                        "sequence_index": 1,
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
    return project_root, manifest


def _chunk_payload(chunk_id: str, sequence_index: int, text: str) -> dict[str, object]:
    """
    @brief      Provide the chunk payload test helper.
    @return     None.
    @exception  None
    """
    return {
        "chunk_id": chunk_id,
        "sequence_index": sequence_index,
        "input_source": character_discovery_service.CHARACTER_DISCOVERY_INPUT_SOURCE_ORIGINAL,
        "text": text,
        "dialogue_spans": [],
    }


def _profile_payload(profile_id: str) -> dict[str, object]:
    """
    @brief      Provide the profile payload test helper.
    @return     None.
    @exception  None
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


def _empty_token_usage() -> dict[str, object]:
    """Return the strict persisted token-usage shape."""
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "usage_available": False,
    }


def _character_document(
    source: dict[str, str],
    *,
    status: str,
    checkpoint: dict[str, object] | None,
    characters: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Build one strict Character Discovery test document."""
    return {
        "status": status,
        "source": dict(source),
        "instructions": "",
        "token_usage": _empty_token_usage(),
        "checkpoint": checkpoint,
        "failure": None,
        "characters": list(characters or []),
    }


def _nested_saved_character() -> dict[str, object]:
    """Return one nested character record for persistence tests."""
    return character_discovery_service._nested_character_profile(  # noqa: SLF001
        _saved_profile_payload()
    )


# END OF FILE
