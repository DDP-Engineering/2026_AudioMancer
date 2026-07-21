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
@version 0.15.1
"""

# IMPORTS

import json
from pathlib import Path

import pytest

from audiomancer import config
from audiomancer.services import character_discovery_service, project_workspace_service
from chunking_test_support import build_chunking_document


def test_character_discovery_prompts_request_demographic_confidence() -> None:
    """
    @brief      Verify Character Discovery prompts request demographic hints and confidence values.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.3.0
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


def test_start_discovery_persists_outputs_and_report(monkeypatch, tmp_path) -> None:
    """
    @brief      Validate start discovery persists outputs and report.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.2.0
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
    state = character_discovery_service.load_operation_state(project_root)
    assert state is not None
    assert state["status"] == "completed"
    assert state["metadata"]["phase"] == "completed"
    assert state["resume_checkpoint"] is None
    assert state["metadata"]["log_relative_path"].startswith("log_ai_characters_")
    assert (project_root / str(state["metadata"]["log_relative_path"])).is_file()
    for field_name in ("output_paths", "artifact_paths", "started_at", "completed_at", "updated_at"):
        assert field_name not in state
    manifest_operation = project_workspace_service.load_manifest(project_root)["operations"]["character_discovery"]
    assert manifest_operation["status"] == "completed"
    assert "checkpoint" not in manifest_operation
    assert "log_relative_path" not in manifest_operation
    assert report["budget_metadata"]["context_window"] == 4096
    assert report["budget_metadata"]["max_output_tokens"] == 512
    assert state["metadata"]["token_usage"] == report["token_usage"]
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
    @version    0.2.0
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
    @version    0.2.0
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
    state_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHARACTER_DISCOVERY_STATE_FILE_NAME
    state_path.write_text(
        json.dumps(
            {
                "status": "running",
                "progress_current": 1,
                "progress_total": 2,
                "mode": character_discovery_service.CHARACTER_DISCOVERY_MODE_AI_ASSISTED,
                "warning_count": 0,
                "metadata": {
                    "phase": "synthesis",
                    "ai_profile_id": "profile-1",
                    "additional_character_discovery_instructions": "",
                    "additional_character_discovery_instructions_fingerprint": (
                        character_discovery_service._compute_prompt_fingerprint("")  # noqa: SLF001
                    ),
                    "token_usage": {
                        "input_tokens": None,
                        "output_tokens": None,
                        "total_tokens": None,
                        "usage_available": False,
                    },
                    "log_relative_path": "saved_character_discovery.log",
                },
                "resume_checkpoint": {
                    "run_token": "2026-04-08T12:00:00+00:00",
                    "input_fingerprint": fingerprint,
                    "log_relative_path": "saved_character_discovery.log",
                    "additional_character_discovery_instructions_fingerprint": (
                        character_discovery_service._compute_prompt_fingerprint("")  # noqa: SLF001
                    ),
                    "completed_window_count": 1,
                    "next_discovery_start_chunk_index": len(source_chunks),
                    "raw_candidates": [resume_candidate],
                    "merged_candidates": [resume_candidate],
                    "rejected_candidates": [],
                    "synthesized_profiles": [],
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    call_profiles = []
    log_paths = []

    def _fake_chat_json(ai_profile_payload, *_args, **kwargs):
        """
        @brief      Provide the fake chat json test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
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
    assert log_paths == ["saved_character_discovery.log"]
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
    assert state["resume_checkpoint"] is None
    assert state["metadata"]["log_relative_path"] == "saved_character_discovery.log"
    resumed_profile = character_discovery_service.load_character_profiles(project_root)[0]
    assert resumed_profile["gender_hint"] == "female"
    assert "Clear and calm" in resumed_profile["voice_definition_prompt"]


def test_character_discovery_tolerates_malformed_profiles_and_report(tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-012 malformed Character Discovery artifacts degrade to missing data.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-11
    @version    0.1.0
    """
    project_root, _manifest = _create_character_project(tmp_path, "CharacterDiscoveryMalformedArtifacts")
    discovery_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    (discovery_root / config.CHARACTER_PROFILE_FILE_NAME).write_text('{"broken": ', encoding="utf-8")
    (discovery_root / config.CHARACTER_DISCOVERY_REPORT_FILE_NAME).write_text('{"broken": ', encoding="utf-8")

    assert character_discovery_service.load_character_profiles(project_root) == []
    assert character_discovery_service.load_character_discovery_report(project_root) is None


def test_start_discovery_persists_cancelled_state_and_resumes_synthesis(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-012 cancelled synthesis persists a resumable checkpoint without repeating windows.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-11
    @version    0.1.0
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryCancelledResume")
    _patch_character_discovery_prompt_rendering(monkeypatch)
    call_stages: list[str] = []

    def _cancel_during_synthesis(*_args, **kwargs):
        """
        @brief      Provide a fake model that cancels during profile synthesis.
        @return     Fake model response for discovery windows.
        @exception  OperationCancelledError Raised for the synthesis call.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-11
        @version    0.1.0
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

    cancelled_state = character_discovery_service.load_operation_state(project_root)
    assert cancelled_state is not None
    assert cancelled_state["status"] == "cancelled"
    assert cancelled_state["metadata"]["phase"] == "synthesis"
    assert cancelled_state["resume_checkpoint"]["completed_window_count"] == 1
    assert len(cancelled_state["resume_checkpoint"]["raw_candidates"]) == 1
    assert len(cancelled_state["resume_checkpoint"]["synthesized_profiles"]) == 0

    resumed_stages: list[str] = []

    def _resume_synthesis(*_args, **kwargs):
        """
        @brief      Provide a fake model that records resumed synthesis calls.
        @return     Fake synthesis payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-11
        @version    0.1.0
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
    assert report["character_count"] == 1


def test_start_discovery_persists_failed_state(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-012 synthesis failures persist a failed checkpoint.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-11
    @version    0.1.0
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryFailedState")
    _patch_character_discovery_prompt_rendering(monkeypatch)

    def _fail_during_synthesis(*_args, **kwargs):
        """
        @brief      Provide a fake model that fails during profile synthesis.
        @return     Fake model response for discovery windows.
        @exception  RuntimeError Raised for the synthesis call.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-11
        @version    0.1.0
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

    failed_state = character_discovery_service.load_operation_state(project_root)
    assert failed_state is not None
    assert failed_state["status"] == "failed"
    assert failed_state["metadata"]["phase"] == "synthesis"
    assert failed_state["resume_checkpoint"]["completed_window_count"] == 1


def test_start_discovery_builds_windows_once(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-NFR-017 discovery startup avoids duplicate full-window construction.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-11
    @version    0.1.0
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
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-11
        @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.2.0
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
                "status": "completed",
                "phase": "completed",
                "progress_current": 1,
                "progress_total": 1,
                "mode": "ai_assisted",
                "started_at": "2026-04-08T12:00:00+00:00",
                "completed_at": "2026-04-08T12:01:00+00:00",
                "updated_at": "2026-04-08T12:01:00+00:00",
                "warning_count": 0,
                "ai_profile_id": "profile-1",
                "input_fingerprint": "",
                "additional_character_discovery_instructions": "",
                "additional_character_discovery_instructions_fingerprint": "",
                "token_usage": {},
                "log_relative_path": "log_ai_characters_saved.log",
                "checkpoint": None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    narrator_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    narrator_root.mkdir(parents=True, exist_ok=True)
    (narrator_root / config.NARRATOR_PROFILE_FILE_NAME).write_text("{}\n", encoding="utf-8")

    existing_alice = character_discovery_service.load_character_profiles(project_root)[0]
    assert existing_alice["gender_confidence"] == ""
    assert existing_alice["age_confidence"] == ""

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
    updated_state = character_discovery_service.load_operation_state(project_root)
    assert updated_state is not None
    assert "metadata" not in updated_state
    assert updated_state["status"] == "completed"

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
    @version    2.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
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


def test_merge_character_candidates_keeps_strongest_demographic_confidence() -> None:
    """
    @brief      Verify merged candidates keep the strongest demographic hint/confidence pairs.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-19
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.2.0
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


def test_load_input_chunks_derives_runtime_chapter_context(tmp_path) -> None:
    """
    @brief      Verify discovery derives chapter context without persisted chunk metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  AssertionError Raised when runtime chapter context is not carried forward.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-17
    @version    0.1.0
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


def test_group_character_candidates_matches_legacy_first_match_order() -> None:
    """
    @brief      Verify REQ-NFR-017 indexed identity grouping preserves legacy first-match semantics.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-11
    @version    0.1.0
    """
    candidates = [
        {"canonical_name": "Alice", "aliases": ["A"]},
        {"canonical_name": "Beth", "aliases": ["B"]},
        {"canonical_name": "Bridge", "aliases": ["B", "A"]},
        {"canonical_name": "Beatrice", "aliases": ["B"]},
        {"canonical_name": "Cara", "aliases": ["C"]},
    ]

    legacy_groups = _legacy_group_character_candidates_by_identity(candidates)
    indexed_groups = character_discovery_service._group_character_candidates_by_identity(candidates)  # noqa: SLF001

    assert indexed_groups == legacy_groups
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


def test_resume_state_requires_current_checkpoint_boundary() -> None:
    """
    @brief      Validate resume state requires current checkpoint boundary.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.2.0
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
            "mode": character_discovery_service.CHARACTER_DISCOVERY_MODE_AI_ASSISTED,
            "input_fingerprint": "abc",
            "additional_character_discovery_instructions_fingerprint": (
                character_discovery_service._compute_prompt_fingerprint("")  # noqa: SLF001
            ),
            "log_relative_path": "log_ai_characters_saved.log",
            "checkpoint": {
                "completed_window_count": 1,
                "next_discovery_start_chunk_index": 1,
                "raw_candidates": [resume_candidate],
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
            "mode": character_discovery_service.CHARACTER_DISCOVERY_MODE_AI_ASSISTED,
            "input_fingerprint": "abc",
            "additional_character_discovery_instructions_fingerprint": (
                character_discovery_service._compute_prompt_fingerprint("")  # noqa: SLF001
            ),
            "checkpoint": {
                "completed_window_count": 1,
                "raw_candidates": [resume_candidate],
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


def _patch_character_discovery_prompt_rendering(monkeypatch) -> None:
    """
    @brief      Patch prompt rendering for focused Character Discovery service tests.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-11
    @version    0.1.0
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


def _legacy_group_character_candidates_by_identity(
    candidates: list[dict[str, object]],
) -> list[list[dict[str, object]]]:
    """
    @brief      Preserve the prior identity-grouping algorithm for equivalence tests.
    @param[in]  candidates Candidate payload list.
    @return     Identity groups from the legacy scan algorithm.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    return {
        "chunk_id": chunk_id,
        "sequence_index": sequence_index,
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
