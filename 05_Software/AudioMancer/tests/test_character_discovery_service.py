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
import re

import pytest

from audiomancer import config
from audiomancer.services import (
    character_discovery_service,
    character_discovery_state_service,
    narrator_definition_service,
    project_workspace_service,
    tts_budget_service,
)
from chunking_test_support import bind_translation_source, build_chunking_document


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
                        "Alice keeps her voice steady as she tells everyone to wait until the moon clears the tower. "
                        "She counts the minutes without hurrying anyone, and no one argues with her about it."
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
        "character_profile_id_last_used",
        "rejected_candidates",
        "checkpoint",
        "failure",
        "characters",
    }
    assert document["character_profile_id_last_used"] == "profile-1"
    assert document["rejected_candidates"] == []
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
        "Alice keeps her voice steady as she tells everyone to wait until the moon clears the tower. "
        "She counts the minutes without hurrying anyone, and no one argues with her about it."
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
    assert list(project_root.glob("log_ai_character_discovery_*.log"))
    assert list(project_root.glob("log_ai_characters_*.log")) == []
    manifest_operation = project_workspace_service.load_manifest(project_root)["operations"]["character_discovery"]
    assert manifest_operation["status"] == "completed"
    assert "checkpoint" not in manifest_operation
    assert "log_relative_path" not in manifest_operation
    serialized_document = document_path.read_text(encoding="utf-8")
    assert '"character_profile_id_last_used": "profile-1"' in serialized_document
    assert "qwen3-8b" not in serialized_document
    assert "temperature" not in serialized_document
    assert "output_reserve_tokens" not in serialized_document


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
            "output_reserve_tokens": 1024,
            "temperature": 0.4,
        },
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )

    assert len(call_profiles) == 1
    assert len(log_paths) == 1
    assert log_paths[0].startswith("log_ai_character_discovery_")
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
    upstream_translation_log = project_root / "log_ai_translation_preserved.log"
    upstream_translation_log.write_text("translation log", encoding="utf-8")

    character_discovery_service.reset_character_discovery(project_root)

    assert list(project_root.glob("log_ai_character_discovery_*.log")) == []
    assert upstream_translation_log.is_file()


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


@pytest.mark.parametrize(
    "mutate_document",
    [
        lambda payload: payload.pop("character_profile_id_last_used"),
        lambda payload: payload.update({"character_profile_id_last_used": 1}),
        lambda payload: payload.pop("rejected_candidates"),
        lambda payload: payload.update(
            {"rejected_candidates": [_rejected_candidate_diagnostic("Bob", "unexpected", 0, 1)]}
        ),
        lambda payload: payload.update(
            {"rejected_candidates": [_rejected_candidate_diagnostic("", "missing_evidence", 0, 1)]}
        ),
        lambda payload: payload.update(
            {"rejected_candidates": [_rejected_candidate_diagnostic("Bob", "missing_evidence", -1, 1)]}
        ),
        lambda payload: payload.update(
            {"rejected_candidates": [_rejected_candidate_diagnostic("Bob", "missing_evidence", 0, 0)]}
        ),
        lambda payload: payload.update(
            {
                "rejected_candidates": [
                    {**_rejected_candidate_diagnostic("Bob", "missing_evidence", 0, 1), "source_excerpt": "forbidden"}
                ]
            }
        ),
        lambda payload: payload.update(
            {
                "rejected_candidates": [
                    _rejected_candidate_diagnostic("Bob", "missing_evidence", 0, 1),
                    _rejected_candidate_diagnostic("Bob", "missing_evidence", 2, 2),
                ]
            }
        ),
        lambda payload: payload.update(
            {
                "rejected_candidates": [
                    _rejected_candidate_diagnostic("Zoe", "missing_evidence", 0, 1),
                    _rejected_candidate_diagnostic("Amy", "missing_evidence", 0, 1),
                ]
            }
        ),
        lambda payload: payload.update({"unexpected": True}),
        lambda payload: payload["checkpoint"].pop("planned_window_count"),
        lambda payload: payload["checkpoint"].update({"unexpected": True}),
        lambda payload: payload["checkpoint"].update({"completed_window_count": "1"}),
        lambda payload: payload["checkpoint"].update({"planned_window_count": -1}),
    ],
)
def test_character_discovery_strictly_rejects_new_profile_and_window_contract_fields(
    tmp_path,
    mutate_document,
) -> None:
    """Verify the evolved exact root and checkpoint fields remain a hard break."""
    project_root, _manifest = _create_character_project(tmp_path, "CharacterDiscoveryStrictNewFields")
    _chunks, source = character_discovery_service._resolve_discovery_input_chunks(project_root)  # noqa: SLF001
    invalid_document = _character_document(
        source,
        status="cancelled",
        checkpoint={
            "phase": "discovery",
            "completed_window_count": 1,
            "planned_window_count": 2,
            "next_chunk_index": 8,
            "candidates": [],
        },
    )
    mutate_document(invalid_document)
    document_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHARACTERS_DOCUMENT_FILE_NAME
    document_path.write_text(json.dumps(invalid_document, indent=2) + "\n", encoding="utf-8")

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


def test_rejected_candidate_diagnostics_survive_repeated_synthesis_resume(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify rejected-candidate diagnostics stay unique through repeated synthesis resume.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  OperationCancelledError Raised by the simulated interrupted synthesis calls.
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryRejectedResume")
    _patch_character_discovery_prompt_rendering(monkeypatch)
    synthesis_attempts = 0

    def _reject_then_interrupt(*_args, **kwargs):
        """Return one accepted and one rejected candidate, then interrupt two synthesis attempts."""
        nonlocal synthesis_attempts
        if str(kwargs["log_context"]["stage_label"]) == "character_discovery_window":
            return {
                "payload": {
                    "characters": [
                        {
                            "canonical_name": "Alice",
                            "aliases": [],
                            "confidence": "high",
                            "evidence": [
                                {
                                    "chunk_id": "chunk-0001",
                                    "source_excerpt": '\"Hello there,\" said Alice.',
                                    "reason": "Alice speaks in direct dialogue.",
                                }
                            ],
                        },
                        {
                            "canonical_name": "Narrated Bob",
                            "aliases": [],
                            "confidence": "low",
                            "evidence": [],
                        },
                    ]
                },
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
            }
        synthesis_attempts += 1
        if synthesis_attempts < 3:
            raise character_discovery_service.OperationCancelledError("interrupted synthesis")
        return _synthesis_response_for_name("Alice")

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _reject_then_interrupt)
    for _attempt in range(2):
        with pytest.raises(character_discovery_service.OperationCancelledError):
            character_discovery_service.start_or_continue_discovery(
                project_root,
                manifest,
                _profile_payload("profile-1"),
                cancel_requested=lambda: False,
            )
        interrupted_document = character_discovery_service.load_character_document(project_root)
        assert interrupted_document is not None
        assert interrupted_document["rejected_candidates"] == [
            {
                "canonical_name": "Narrated Bob",
                "reason": "missing_evidence",
                "evidence_count": 0,
                "identity_merge_count": 1,
            }
        ]
        assert character_discovery_service.character_operation_summary(interrupted_document)["warning_count"] == 1

    completed_document = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        cancel_requested=lambda: False,
    )

    assert synthesis_attempts == 3
    assert completed_document["rejected_candidates"] == interrupted_document["rejected_candidates"]
    assert character_discovery_service.character_operation_summary(completed_document)["warning_count"] == 1
    persisted_manifest = project_workspace_service.load_manifest(project_root)
    assert persisted_manifest["operations"]["character_discovery"]["warning_count"] == 1


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
    assert failed_document["failure"]["message"] == "model failed"


def test_start_discovery_resumes_empty_synthesis_checkpoint(monkeypatch, tmp_path) -> None:
    """Verify an interrupted zero-candidate synthesis run can finalize without another model call."""
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryEmptySynthesis")
    _resolved_chunks, source = character_discovery_service._resolve_discovery_input_chunks(project_root)  # noqa: SLF001
    character_discovery_service.write_character_document(
        project_root,
        _character_document(
            source,
            status="running",
            checkpoint={"phase": "synthesis", "next_candidate_index": 0, "candidates": []},
        ),
    )
    _patch_character_discovery_prompt_rendering(monkeypatch)
    monkeypatch.setattr(
        character_discovery_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: pytest.fail("Empty synthesis resume must not call the provider."),
    )

    document = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
    )

    assert document["status"] == "completed"
    assert document["characters"] == []
    assert document["checkpoint"] is None


def test_discovery_resume_preserves_manual_inventory_through_checkpoints_and_recancellation(
    monkeypatch,
    tmp_path,
) -> None:
    """
    @brief      Verify resumed discovery writes preserve current durable manual records.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryManualResumeCancel")
    _set_character_project_chunks(project_root, 20)
    _patch_character_discovery_prompt_rendering(monkeypatch)
    initial_call_count = 0

    def _cancel_second_initial_window(*_args, **_kwargs):
        """Complete one discovery window and cancel the next model request."""
        nonlocal initial_call_count
        initial_call_count += 1
        if initial_call_count == 2:
            raise character_discovery_service.OperationCancelledError("cancelled")
        return _window_response_for_names(["Alice"], "chunk-0001")

    monkeypatch.setattr(
        character_discovery_service.llm_provider_service,
        "chat_json",
        _cancel_second_initial_window,
    )
    with pytest.raises(character_discovery_service.OperationCancelledError):
        character_discovery_service.start_or_continue_discovery(
            project_root,
            manifest,
            _profile_payload("profile-1"),
            progress_callback=lambda *_args: None,
            cancel_requested=lambda: False,
        )

    initial_checkpoint = character_discovery_service.load_character_document(project_root)["checkpoint"]
    character_discovery_service.add_character_profile(project_root, "Ghost")
    manual_record = character_discovery_service.load_character_document(project_root)["characters"][0]
    persisted_documents: list[dict[str, object]] = []
    original_write_json_atomic = character_discovery_service.write_json_atomic

    def _capture_character_writes(path, payload):
        """Capture authoritative document writes while preserving atomic persistence."""
        if Path(path).name == config.CHARACTERS_DOCUMENT_FILE_NAME:
            persisted_documents.append(json.loads(json.dumps(payload)))
        return original_write_json_atomic(path, payload)

    resumed_call_count = 0

    def _cancel_second_resumed_window(*_args, **_kwargs):
        """Complete one resumed window and cancel the following request."""
        nonlocal resumed_call_count
        resumed_call_count += 1
        if resumed_call_count == 2:
            raise character_discovery_service.OperationCancelledError("cancelled again")
        return _window_response_for_names(["Bob"], "chunk-0009")

    monkeypatch.setattr(character_discovery_service, "write_json_atomic", _capture_character_writes)
    monkeypatch.setattr(
        character_discovery_service.llm_provider_service,
        "chat_json",
        _cancel_second_resumed_window,
    )

    with pytest.raises(character_discovery_service.OperationCancelledError):
        character_discovery_service.start_or_continue_discovery(
            project_root,
            manifest,
            _profile_payload("profile-1"),
            progress_callback=lambda *_args: None,
            cancel_requested=lambda: False,
        )

    assert len(persisted_documents) >= 3
    assert all(document["characters"] == [manual_record] for document in persisted_documents)
    cancelled_document = character_discovery_service.load_character_document(project_root)
    assert cancelled_document["status"] == "cancelled"
    assert cancelled_document["characters"] == [manual_record]
    assert cancelled_document["checkpoint"]["completed_window_count"] == (
        initial_checkpoint["completed_window_count"] + 1
    )
    assert cancelled_document["checkpoint"]["planned_window_count"] >= (
        cancelled_document["checkpoint"]["completed_window_count"]
    )
    repeated_resume_summary = character_discovery_service.character_operation_summary(cancelled_document)
    assert repeated_resume_summary["progress_current"] == cancelled_document["checkpoint"]["completed_window_count"]
    assert repeated_resume_summary["progress_total"] == cancelled_document["checkpoint"]["planned_window_count"]


def test_discovery_resume_provider_failure_preserves_current_inventory(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify a provider failure after discovery resume preserves durable records.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryManualResumeFailure")
    _set_character_project_chunks(project_root, 20)
    _patch_character_discovery_prompt_rendering(monkeypatch)
    _chunks, source = character_discovery_service._resolve_discovery_input_chunks(project_root)  # noqa: SLF001
    manual_record = _nested_character_record(
        "manual-ghost",
        "Ghost",
        origin="manual",
        edited=True,
        sequence_index=0,
        voice_text="Operator-authored voice text.",
    )
    character_discovery_service.write_character_document(
        project_root,
        _character_document(
            source,
            status="cancelled",
            checkpoint={"phase": "discovery", "next_chunk_index": 0, "candidates": []},
            characters=[manual_record],
        ),
    )
    provider_call_count = 0

    def _complete_one_window_then_fail(*_args, **_kwargs):
        """Commit one resumed window before simulating a provider failure."""
        nonlocal provider_call_count
        provider_call_count += 1
        if provider_call_count == 1:
            return _window_response_for_names(["Alice"], "chunk-0001")
        raise RuntimeError("provider failed")

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _complete_one_window_then_fail)

    with pytest.raises(RuntimeError, match="provider failed"):
        character_discovery_service.start_or_continue_discovery(
            project_root,
            manifest,
            _profile_payload("profile-1"),
            progress_callback=lambda *_args: None,
            cancel_requested=lambda: False,
        )

    failed_document = character_discovery_service.load_character_document(project_root)
    assert failed_document["status"] == "failed"
    assert failed_document["characters"] == [manual_record]
    assert failed_document["checkpoint"]["completed_window_count"] == 1
    assert failed_document["checkpoint"]["planned_window_count"] > 1
    failed_summary = character_discovery_service.character_operation_summary(failed_document)
    assert (failed_summary["progress_current"], failed_summary["progress_total"]) == (
        failed_document["checkpoint"]["completed_window_count"],
        failed_document["checkpoint"]["planned_window_count"],
    )


def test_discovery_resume_manual_inventory_does_not_skip_synthesis_candidates(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify discovery-phase manual records do not advance synthesis progress.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryManualSynthesisBoundary")
    _set_character_project_chunks(project_root, 10)
    _patch_character_discovery_prompt_rendering(monkeypatch)
    discovery_call_count = 0

    def _cancel_second_window(*_args, **_kwargs):
        """Return three candidates before cancelling the second window."""
        nonlocal discovery_call_count
        discovery_call_count += 1
        if discovery_call_count == 2:
            raise character_discovery_service.OperationCancelledError("cancelled")
        return _window_response_for_names(["Alice", "Bob", "Carol"], "chunk-0001")

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _cancel_second_window)
    with pytest.raises(character_discovery_service.OperationCancelledError):
        character_discovery_service.start_or_continue_discovery(
            project_root,
            manifest,
            _profile_payload("profile-1"),
            progress_callback=lambda *_args: None,
            cancel_requested=lambda: False,
        )

    character_discovery_service.add_character_profile(project_root, "Manual One")
    character_discovery_service.add_character_profile(project_root, "Manual Two")
    synthesis_names = iter(["Alice", "Bob", "Carol"])
    synthesis_calls: list[str] = []

    def _finish_resumed_run(*_args, **kwargs):
        """Complete the remaining discovery window and every synthesis request."""
        stage_label = str(kwargs["log_context"]["stage_label"])
        if stage_label == "character_discovery_window":
            return _window_response_for_names([], "chunk-0009")
        name = next(synthesis_names)
        synthesis_calls.append(name)
        return _synthesis_response_for_name(name)

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _finish_resumed_run)
    completed = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )

    assert synthesis_calls == ["Alice", "Bob", "Carol"]
    assert {item["canonical_name"] for item in completed["characters"]} == {
        "Alice",
        "Bob",
        "Carol",
        "Manual One",
        "Manual Two",
    }
    assert len({item["character_id"] for item in completed["characters"]}) == 5


def test_synthesis_resume_preserves_reordered_manual_and_edited_ai_inventory(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify synthesis resume inventory is independent from root ordering.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryReorderedSynthesis")
    _patch_character_discovery_prompt_rendering(monkeypatch)
    _chunks, source = character_discovery_service._resolve_discovery_input_chunks(project_root)  # noqa: SLF001
    candidates = [
        _merged_candidate(name, index)
        for index, name in enumerate(["Alice", "Bob", "Carol", "Dave", "Eve"], 1)
    ]
    manual_before = _nested_character_record("manual-before", "Manual Before", origin="manual", sequence_index=0)
    edited_bob = _nested_character_record(
        "bob",
        "Bob Operator Edit",
        origin="ai",
        edited=True,
        sequence_index=2,
        voice_text="Keep this exact edited voice text.",
    )
    manual_between = _nested_character_record("manual-between", "Manual Between", origin="manual", sequence_index=2)
    retained_carol = _nested_character_record("carol", "Carol", origin="ai", sequence_index=3)
    manual_after = _nested_character_record("manual-after", "Manual After", origin="manual", sequence_index=99)
    current_inventory = [manual_before, edited_bob, manual_between, retained_carol, manual_after]
    character_discovery_service.write_character_document(
        project_root,
        _character_document(
            source,
            status="cancelled",
            checkpoint={"phase": "synthesis", "next_candidate_index": 3, "candidates": candidates},
            characters=current_inventory,
        ),
    )
    pending_names = iter(["Dave", "Eve"])
    requested_indexes: list[int] = []

    def _synthesize_pending(*_args, **kwargs):
        """Record the synthesis cursor and return the next pending profile."""
        requested_indexes.append(int(kwargs["log_context"]["window_index"]))
        return _synthesis_response_for_name(next(pending_names))

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _synthesize_pending)
    completed = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )

    assert requested_indexes == [4, 5]
    completed_by_id = {item["character_id"]: item for item in completed["characters"]}
    assert completed_by_id["bob"] == edited_bob
    assert completed_by_id["carol"] == retained_carol
    assert all(completed_by_id[item["character_id"]] == item for item in (manual_before, manual_between, manual_after))
    assert "alice" not in completed_by_id
    assert set(completed_by_id) == {
        "manual-before",
        "bob",
        "manual-between",
        "carol",
        "manual-after",
        "dave",
        "eve",
    }


def test_synthesis_resume_does_not_resubmit_or_restore_deleted_prefix_profiles(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify deleted completed profiles stay absent without moving the cursor.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryDeletedSynthesisPrefix")
    _patch_character_discovery_prompt_rendering(monkeypatch)
    _chunks, source = character_discovery_service._resolve_discovery_input_chunks(project_root)  # noqa: SLF001
    candidates = [
        _merged_candidate(name, index)
        for index, name in enumerate(["Alice", "Bob", "Carol", "Dave", "Eve"], 1)
    ]
    retained_bob = _nested_character_record("bob", "Bob", origin="ai", edited=True, sequence_index=2)
    character_discovery_service.write_character_document(
        project_root,
        _character_document(
            source,
            status="failed",
            checkpoint={"phase": "synthesis", "next_candidate_index": 3, "candidates": candidates},
            characters=[retained_bob],
        ),
    )
    pending_names = iter(["Dave", "Eve"])
    requested_indexes: list[int] = []

    def _synthesize_pending(*_args, **kwargs):
        """Return only candidates after the durable checkpoint boundary."""
        requested_indexes.append(int(kwargs["log_context"]["window_index"]))
        return _synthesis_response_for_name(next(pending_names))

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _synthesize_pending)
    completed = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )

    assert requested_indexes == [4, 5]
    assert {item["character_id"] for item in completed["characters"]} == {"bob", "dave", "eve"}
    assert next(item for item in completed["characters"] if item["character_id"] == "bob") == retained_bob


@pytest.mark.parametrize("interruption_kind", ["cancellation", "failure"])
def test_resumed_synthesis_interruption_preserves_truthful_inventory_and_cursor(
    monkeypatch,
    tmp_path,
    interruption_kind,
) -> None:
    """
    @brief      Verify resumed synthesis interruption retains durable inventory and cursor.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  interruption_kind Provider interruption to exercise.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_character_project(
        tmp_path,
        f"CharacterDiscoverySynthesis{interruption_kind.title()}",
    )
    _patch_character_discovery_prompt_rendering(monkeypatch)
    _chunks, source = character_discovery_service._resolve_discovery_input_chunks(project_root)  # noqa: SLF001
    candidates = [_merged_candidate(name, index) for index, name in enumerate(["Alice", "Bob", "Carol"], 1)]
    manual_record = _nested_character_record("manual-keeper", "Manual Keeper", origin="manual", sequence_index=0)
    edited_alice = _nested_character_record(
        "alice",
        "Alice Edited",
        origin="ai",
        edited=True,
        sequence_index=1,
        voice_text="Operator-edited Alice voice.",
    )
    character_discovery_service.write_character_document(
        project_root,
        _character_document(
            source,
            status="cancelled",
            checkpoint={"phase": "synthesis", "next_candidate_index": 1, "candidates": candidates},
            characters=[manual_record, edited_alice],
        ),
    )
    requested_indexes: list[int] = []

    def _interrupt_after_bob(*_args, **kwargs):
        """Synthesize Bob and interrupt Carol."""
        requested_index = int(kwargs["log_context"]["window_index"])
        requested_indexes.append(requested_index)
        if requested_index == 2:
            return _synthesis_response_for_name("Bob")
        if interruption_kind == "cancellation":
            raise character_discovery_service.OperationCancelledError("cancelled")
        raise RuntimeError("provider failed")

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _interrupt_after_bob)
    expected_error = (
        character_discovery_service.OperationCancelledError
        if interruption_kind == "cancellation"
        else RuntimeError
    )
    with pytest.raises(expected_error):
        character_discovery_service.start_or_continue_discovery(
            project_root,
            manifest,
            _profile_payload("profile-1"),
            progress_callback=lambda *_args: None,
            cancel_requested=lambda: False,
        )

    interrupted = character_discovery_service.load_character_document(project_root)
    assert interrupted["status"] == ("cancelled" if interruption_kind == "cancellation" else "failed")
    assert interrupted["checkpoint"]["next_candidate_index"] == 2
    interrupted_by_id = {item["character_id"]: item for item in interrupted["characters"]}
    assert interrupted_by_id["manual-keeper"] == manual_record
    assert interrupted_by_id["alice"] == edited_alice
    assert set(interrupted_by_id) == {"manual-keeper", "alice", "bob"}

    resumed_indexes: list[int] = []

    def _finish_carol(*_args, **kwargs):
        """Complete only the candidate remaining after the interrupted checkpoint."""
        resumed_indexes.append(int(kwargs["log_context"]["window_index"]))
        return _synthesis_response_for_name("Carol")

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _finish_carol)
    completed = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )

    assert requested_indexes == [2, 3]
    assert resumed_indexes == [3]
    assert {item["character_id"] for item in completed["characters"]} == {
        "manual-keeper",
        "alice",
        "bob",
        "carol",
    }


@pytest.mark.parametrize("restart_kind", ["source_mismatch", "force_rerun"])
def test_incompatible_or_forced_restart_retains_established_fresh_run_behavior(
    monkeypatch,
    tmp_path,
    restart_kind,
) -> None:
    """
    @brief      Verify source mismatch and force rerun still discard resumable inventory.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  restart_kind Fresh-run trigger to exercise.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_character_project(tmp_path, f"CharacterDiscoveryRestart{restart_kind.title()}")
    _patch_character_discovery_prompt_rendering(monkeypatch)
    _chunks, source = character_discovery_service._resolve_discovery_input_chunks(project_root)  # noqa: SLF001
    persisted_source = dict(source)
    if restart_kind == "source_mismatch":
        persisted_source["fingerprint"] = "stale-source-fingerprint"
    manual_record = _nested_character_record("manual-old", "Manual Old", origin="manual", sequence_index=0)
    character_discovery_service.write_character_document(
        project_root,
        _character_document(
            persisted_source,
            status="cancelled",
            checkpoint={"phase": "discovery", "next_chunk_index": 0, "candidates": []},
            characters=[manual_record],
        ),
    )
    requested_stages: list[str] = []

    def _complete_fresh_run(*_args, **kwargs):
        """Complete one fresh discovery and synthesis request."""
        stage_label = str(kwargs["log_context"]["stage_label"])
        requested_stages.append(stage_label)
        if stage_label == "character_discovery_window":
            return _window_response_for_names(["Alice"], "chunk-0001")
        return _synthesis_response_for_name("Alice")

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _complete_fresh_run)
    completed = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
        force_rerun=restart_kind == "force_rerun",
    )

    assert requested_stages == ["character_discovery_window", "character_profile_synthesis"]
    assert [item["character_id"] for item in completed["characters"]] == ["alice"]


def test_start_discovery_builds_windows_once_with_budget_metadata_parameters(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify discovery startup builds windows once with profile-derived budget parameters.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoverySingleWindowBuild")
    _patch_character_discovery_prompt_rendering(monkeypatch)
    budget_metadata = character_discovery_service._build_budget_metadata(  # noqa: SLF001
        _profile_payload("profile-1"),
        "system prompt",
    )
    budget_metadata["max_window_chunks"] = "0"
    budget_metadata["window_overlap"] = "3"
    original_build_chunk_windows = character_discovery_service._build_chunk_windows  # noqa: SLF001
    build_calls: list[tuple[int, int, bool]] = []

    def _count_build_chunk_windows(*args, **kwargs):
        """
        @brief      Count request-window construction calls.
        @return     Original window construction result.
        @exception  ValueError Propagated from original window construction.
        """
        build_calls.append((int(args[1]), int(args[2]), args[3] is budget_metadata))
        return original_build_chunk_windows(*args, **kwargs)

    responses = iter([_window_response_payload(), _synthesis_response_payload()])
    monkeypatch.setattr(character_discovery_service, "_build_budget_metadata", lambda *_args: budget_metadata)
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

    assert build_calls == [(0, 3, True)]


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


def test_build_profile_from_synthesis_keeps_composed_preview_absent_from_evidence() -> None:
    """
    @brief      Verify character synthesis keeps composed preview text that no evidence excerpt contains.
    @return     None.
    @exception  None
    """
    composed_preview_text = (
        "She weighs each answer before she gives it, and the words arrive quiet but certain. "
        "Nothing in her tone hurries, and nothing in it asks to be forgiven."
    )
    profile = character_discovery_service._build_profile_from_synthesis(  # noqa: SLF001
        {
            "canonical_name": "Alice",
            "gender_hint": "female",
            "age_hint": "adult",
            "voice_definition_prompt": "Create a consistent spoken voice for Alice. Clear and calm.",
            "preview_text": composed_preview_text,
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

    assert profile["preview_text"] == composed_preview_text
    assert profile["age_hint"] == "adult"
    assert "Age Domain: adult." in profile["voice_definition_prompt"]


@pytest.mark.parametrize("preview_word_count", (24, 45))
def test_build_profile_from_synthesis_drops_out_of_range_preview(preview_word_count: int) -> None:
    """
    @brief      Verify a composed preview outside the shared word range stores no character preview text.
    @param[in]  preview_word_count Number of words in the supplied composed preview text.
    @return     None.
    @exception  None
    """
    profile = character_discovery_service._build_profile_from_synthesis(  # noqa: SLF001
        {
            "canonical_name": "Alice",
            "gender_hint": "female",
            "age_hint": "adult",
            "voice_definition_prompt": "Create a consistent spoken voice for Alice. Clear and calm.",
            "preview_text": " ".join("word" for _index in range(preview_word_count)),
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
            ],
        },
    )

    assert profile["preview_text"] == ""


def test_normalized_character_preview_text_keeps_over_long_text() -> None:
    """
    @brief      Verify normalization never discards a long preview text to an empty string.
    @return     None.
    @exception  None
    """
    long_preview_text = " ".join("word" for _index in range(400))

    normalized_text = character_discovery_service._normalized_character_preview_text(  # noqa: SLF001
        long_preview_text
    )

    assert normalized_text == long_preview_text


def test_normalized_character_preview_text_preserves_line_breaks() -> None:
    """
    @brief      Verify normalization collapses spaces while keeping operator line breaks.
    @return     None.
    @exception  None
    """
    normalized_text = character_discovery_service._normalized_character_preview_text(  # noqa: SLF001
        "First   line.\nSecond    line."
    )

    assert normalized_text == "First line.\nSecond line."


def test_merge_character_candidates_keeps_role_speaker_candidate() -> None:
    """
    @brief      Verify merged candidates preserve deterministic role speakers as dialogue characters.
    @return     None.
    @exception  None
    """
    merged_candidates = character_discovery_service._merge_character_candidates_with_rejections(  # noqa: SLF001
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
    )[0]

    assert len(merged_candidates) == 1
    assert merged_candidates[0]["character_id"] == "his_agent"
    assert merged_candidates[0]["canonical_name"] == "His Agent"


def test_merge_character_candidates_keeps_strongest_demographic_confidence() -> None:
    """
    @brief      Verify merged candidates keep the strongest demographic hint/confidence pairs.
    @return     None.
    @exception  None
    """
    merged_candidates = character_discovery_service._merge_character_candidates_with_rejections(  # noqa: SLF001
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
    )[0]

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
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoverySourcePreferred")
    manifest["target_language"] = "fr"
    project_workspace_service.save_manifest(manifest, project_root)
    artifact_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    (artifact_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
        json.dumps(
            {
                "target_language": "fr",
                "status": "completed",
                "token_usage": _empty_token_usage(),
                "budget_metadata": {},
                "additional_translation_instructions": "",
                "chunks": bind_translation_source(project_root, [
                {
                    "chunk_id": "chunk-0001",
                    "translated_text": "\u00abBonjour\u00bb, dit Alice.",
                    "approved": True,
                }
                ]),
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


def test_manual_character_names_use_unicode_identity_keys(tmp_path) -> None:
    """
    @brief      Verify manual Unicode names persist and compare by identity key.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  AssertionError Raised when Unicode validation or persistence changes.
    """
    project_root, _manifest = _create_character_project(tmp_path, "CharacterDiscoveryUnicodeManual")
    _chunks, source = character_discovery_service._resolve_discovery_input_chunks(project_root)  # noqa: SLF001
    character_discovery_service.write_character_document(
        project_root,
        _character_document(source, status="completed", checkpoint=None, characters=[]),
    )
    names = ["Алиса", "Αλέξανδρος", "王小明", "さくら", "민준", "דוד", "ليلى"]

    for name in names:
        character_discovery_service.add_character_profile(project_root, name)

    profiles = character_discovery_service.load_character_profiles(project_root)
    assert {str(profile["canonical_name"]) for profile in profiles} == set(names)
    korean_profile = next(profile for profile in profiles if profile["canonical_name"] == "민준")
    korean_profile["aliases"] = ["민수"]
    character_discovery_service.update_character_profile(project_root, korean_profile)
    document = character_discovery_service.load_character_document(project_root)
    assert {item["canonical_name"] for item in document["characters"] if item["canonical_name"] in names} == set(names)
    assert next(item for item in document["characters"] if item["canonical_name"] == "민준")["aliases"] == ["민수"]

    existing_profiles = [
        {"character_id": "rene", "canonical_name": "René", "aliases": ["Алиса", "José"]},
    ]
    for duplicate_name in ["Rene", "Алиса", "José", "A_B"]:
        with pytest.raises(ValueError, match="duplicate_name"):
            character_discovery_service.validate_manual_character_name(
                existing_profiles + [{"character_id": "ab", "canonical_name": "AB", "aliases": []}],
                duplicate_name,
            )
    assert character_discovery_service.validate_manual_character_name(existing_profiles, "Renée") == "Renée"
    assert character_discovery_service.validate_manual_character_name(existing_profiles, "Jos") == "Jos"
    assert character_discovery_service.validate_manual_character_name(
        [{"character_id": "alice", "canonical_name": "Алиса", "aliases": []}],
        "Алиса",
        exclude_character_id="alice",
    ) == "Алиса"
    for invalid_name in ["   ", "!!!", "😀", "$", "  ́"]:
        with pytest.raises(ValueError, match="invalid_name"):
            character_discovery_service.validate_manual_character_name([], invalid_name)


def test_group_character_candidates_uses_unicode_identity_keys() -> None:
    """
    @brief      Verify Unicode candidate identity grouping preserves distinct names.
    @return     None.
    @exception  AssertionError Raised when candidate identities merge incorrectly.
    """
    candidates = [
        {"canonical_name": "Алиса", "aliases": []},
        {"canonical_name": "АЛИСА", "aliases": []},
        {"canonical_name": "Αλέξανδρος", "aliases": []},
        {"canonical_name": "Αλέξανδρος", "aliases": []},
        {"canonical_name": "王小明", "aliases": ["小明"]},
        {"canonical_name": "小明", "aliases": []},
        {"canonical_name": "שרה", "aliases": ["שָׂרָה"]},
        {"canonical_name": "سارة", "aliases": ["שָׂרָה"]},
        {"canonical_name": "René", "aliases": []},
        {"canonical_name": "Rene", "aliases": []},
        {"canonical_name": "Renée", "aliases": []},
        {"canonical_name": "José", "aliases": []},
        {"canonical_name": "Jos", "aliases": []},
        {"canonical_name": "!!!", "aliases": []},
        {"canonical_name": "😀", "aliases": []},
    ]

    groups = character_discovery_service._group_character_candidates_by_identity(candidates)  # noqa: SLF001

    assert [[item["canonical_name"] for item in group] for group in groups] == [
        ["Алиса", "АЛИСА"],
        ["Αλέξανδρος", "Αλέξανδρος"],
        ["王小明", "小明"],
        ["שרה", "سارة"],
        ["René", "Rene"],
        ["Renée"],
        ["José"],
        ["Jos"],
        ["!!!"],
        ["😀"],
    ]
    merged = character_discovery_service._merge_candidate_identity_group(groups[3])  # noqa: SLF001
    assert merged["identity_alias_keys"] == sorted(  # noqa: SLF001
        {
            character_discovery_service._normalize_identity("שרה"),  # noqa: SLF001
            character_discovery_service._normalize_identity("سارة"),  # noqa: SLF001
        }
    )


def test_discovery_synthesizes_repeated_unicode_identity_once(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify repeated Unicode discovery candidates trigger one synthesis request.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  AssertionError Raised when repeated identities synthesize more than once.
    """
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryUnicodeGrouping")
    _set_character_project_chunks(project_root, 10)
    _patch_character_discovery_prompt_rendering(monkeypatch)
    window_names = iter([("Алиса", "chunk-0001"), ("АЛИСА", "chunk-0009")])
    synthesis_requests: list[str] = []

    def _discover_then_synthesize(*_args, **kwargs):
        """Return one repeated Cyrillic mention per window and record synthesis."""
        if str(kwargs["log_context"]["stage_label"]) == "character_discovery_window":
            name, chunk_id = next(window_names)
            return _window_response_for_names([name], chunk_id)
        synthesis_requests.append("character_profile_synthesis")
        return _synthesis_response_for_name("Алиса")

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _discover_then_synthesize)
    document = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-1"),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )

    assert synthesis_requests == ["character_profile_synthesis"]
    assert [item["canonical_name"] for item in document["characters"]] == ["Алиса"]


def test_discovery_reserves_unique_ids_for_colliding_names_and_manual_profile(monkeypatch, tmp_path) -> None:
    """@brief Preserve both AI profiles and a manual profile added while synthesis is paused."""
    root, manifest = _create_character_project(tmp_path, "UniqueDiscoveryIds")
    _patch_character_discovery_prompt_rendering(monkeypatch)
    names = ["Li", "\u00c9li"]

    def interrupt_synthesis(*_args, **kwargs):
        """@brief Discover both names, then interrupt before the first profile."""
        if kwargs["log_context"]["stage_label"] == "character_discovery_window":
            return _window_response_for_names(names, "chunk-0001")
        raise character_discovery_service.OperationCancelledError("Pause synthesis.")

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", interrupt_synthesis)
    with pytest.raises(character_discovery_service.OperationCancelledError):
        character_discovery_service.start_or_continue_discovery(root, manifest, _profile_payload("profile-1"))

    character_discovery_service.add_character_profile(root, "\u0160li")
    remaining_names = iter(names)
    monkeypatch.setattr(
        character_discovery_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: _synthesis_response_for_name(next(remaining_names)),
    )
    result = character_discovery_service.start_or_continue_discovery(root, manifest, _profile_payload("profile-1"))

    assert {item["canonical_name"] for item in result["characters"]} == {*names, "\u0160li"}
    assert {item["character_id"] for item in result["characters"]} == {"li", "li_2", "li_3"}


def test_discovery_keeps_possible_speakers_when_citations_cannot_be_resolved() -> None:
    """@brief Ground Romanian dialogue and leave unresolved AI excerpts available for review."""
    text = "\u201eBun\u0103!\u201d a spus Mara."
    span = character_discovery_service._detect_dialogue_spans(text)  # noqa: SLF001
    assert len(span) == 1
    chunks = {"c1": {**_chunk_payload("c1", 1, text), "dialogue_spans": span}}
    candidates = [
        {
            "canonical_name": "Mara",
            "evidence": [{"chunk_id": "c1", "dialogue_span_id": span[0]["dialogue_span_id"],
                          "source_excerpt": "Model paraphrase"}],
        },
        {
            "canonical_name": "Dan",
            "evidence": [{"chunk_id": "c1", "dialogue_span_id": "dialogue-999",
                          "source_excerpt": '"Invented."'}],
        },
        {
            "canonical_name": "Ana",
            "evidence": [{"chunk_id": "outside-window", "source_excerpt": '"Another reply."'}],
        },
        {
            "canonical_name": "Narrated Bea",
            "evidence": [
                {
                    "chunk_id": "outside-window",
                    "source_excerpt": "Bea is mentioned by the narrator.",
                    "reason": "Narration-only reference",
                    "confidence": "high",
                }
            ],
        },
        {
            "canonical_name": "Narrated Cal",
            "evidence": [
                {"chunk_id": "outside-window", "dialogue_span_id": None, "source_excerpt": "Cal opened a door."}
            ],
        },
        {
            "canonical_name": "Narrated Eve",
            "evidence": [{"chunk_id": "outside-window", "reason": "Narration only, no dialogue."}],
        },
    ]

    normalized = character_discovery_service._normalize_window_candidates(candidates, chunks)  # noqa: SLF001
    accepted, rejected = character_discovery_service._merge_character_candidates_with_rejections(  # noqa: SLF001
        normalized
    )
    assert {item["canonical_name"] for item in rejected} == {"Narrated Bea", "Narrated Cal", "Narrated Eve"}
    assert all(item["reason"] == "missing_evidence" for item in rejected)
    by_name = {item["canonical_name"]: item for item in accepted}
    assert by_name["Mara"]["evidence"][0]["source_excerpt"] == "\u201eBun\u0103!\u201d"
    assert by_name["Dan"]["evidence"][0]["source_excerpt"] == ""
    assert by_name["Dan"]["evidence"][0]["dialogue_span_id"] == ""
    assert by_name["Ana"]["evidence"] == []

    profile = character_discovery_service._build_profile_from_synthesis(  # noqa: SLF001
        {
            "canonical_name": "",
            "evidence": [{"chunk_id": "outside-window", "source_excerpt": "Invented in synthesis."}],
        },
        by_name["Mara"],
    )
    assert profile["canonical_name"] == "Mara"
    assert profile["evidence"] == by_name["Mara"]["evidence"]


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


def test_character_discovery_online_profile_reserves_context_without_chunk_cap(monkeypatch) -> None:
    """
    @brief      Verify discovery and synthesis reserve context while keeping the online window policy.
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
        "output_reserve_tokens": 6800,
    }

    budget_metadata = character_discovery_service._build_budget_metadata(profile_payload, "system")
    source_chunks = [
        {"chunk_id": f"chunk-{index:04d}", "text": "Short character-discovery chunk."} for index in range(1, 12)
    ]

    assert budget_metadata["text_budget_tokens"] == (
        10000 - 6800 - budget_metadata["prompt_budget_tokens"] - budget_metadata["safety_margin_tokens"]
    )
    assert budget_metadata["text_budget_tokens"] < 3000
    assert budget_metadata["synthesis_payload_budget_tokens"] == (
        10000 - 6800 - budget_metadata["synthesis_prompt_budget_tokens"] - budget_metadata["safety_margin_tokens"]
    )
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
        "output_reserve_tokens": 900,
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
                "completed_window_count": 1,
                "planned_window_count": 2,
                "next_chunk_index": 1,
                "candidates": [resume_candidate],
            },
        },
        input_fingerprint="abc",
        source_chunks=source_chunks,
    )

    assert restored[0] == 1
    assert restored[1] == 2
    assert restored[2] == 1
    assert restored[3] == [resume_candidate]
    assert restored[6] == 0
    assert restored[7] == "discovery"

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
    assert stale_restored == (0, 0, 0, [], [], [], 0, None)


def test_discovery_resume_persists_real_window_progress_before_synthesis(monkeypatch, tmp_path) -> None:
    """Verify cancellation, repeated resume, manifest, page, and synthesis share real window counts."""
    project_root, manifest = _create_character_project(tmp_path, "CharacterDiscoveryWindowProgress")
    _set_character_project_chunks(project_root, 100)
    _patch_character_discovery_prompt_rendering(monkeypatch)
    budget_metadata = {
        "text_budget_tokens": 10000,
        "synthesis_payload_budget_tokens": 10000,
        "synthesis_max_evidence_items": 8,
        "max_window_chunks": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE,
        "window_overlap": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
    }
    monkeypatch.setattr(character_discovery_service, "_build_budget_metadata", lambda *_args: budget_metadata)
    source_chunks, _source = character_discovery_service._resolve_discovery_input_chunks(project_root)  # noqa: SLF001
    planned_windows = character_discovery_service._build_chunk_windows(  # noqa: SLF001
        source_chunks,
        config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE,
        config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
        budget_metadata,
    )
    completed_before_cancel = next(
        index + 1 for index, window in enumerate(planned_windows) if window[-1]["sequence_index"] >= 40
    )
    next_window = planned_windows[completed_before_cancel]
    expected_cursor = next_window[0]["sequence_index"] - 1
    resumed_planned_window_count = len(planned_windows)
    assert next_window[0] == planned_windows[completed_before_cancel - 1][-1]
    monkeypatch.setattr(
        character_discovery_service.prompt_template_service,
        "render_prompt",
        lambda prompt_name, payload: payload.get("units_block", prompt_name),
    )
    discovery_call_count = 0
    progress_updates: list[tuple[int, int]] = []

    def _cancel_near_chunk_forty(*_args, **kwargs):
        """Return real discovery responses until the planned cursor threshold is checkpointed."""
        nonlocal discovery_call_count
        if str(kwargs["log_context"]["stage_label"]) != "character_discovery_window":
            raise AssertionError("synthesis must not begin before cancellation")
        discovery_call_count += 1
        if discovery_call_count > completed_before_cancel:
            raise character_discovery_service.OperationCancelledError("cancel near chunk 40")
        names = ["Alice"] if discovery_call_count == 1 else []
        return _window_response_for_names(names, planned_windows[discovery_call_count - 1][0]["chunk_id"])

    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _cancel_near_chunk_forty)
    with pytest.raises(character_discovery_service.OperationCancelledError):
        character_discovery_service.start_or_continue_discovery(
            project_root,
            manifest,
            _profile_payload("profile-1"),
            progress_callback=lambda current, total, *_args, **_kwargs: progress_updates.append((current, total)),
            cancel_requested=lambda: False,
        )

    cancelled_document = character_discovery_service.load_character_document(project_root)
    assert cancelled_document is not None
    checkpoint = cancelled_document["checkpoint"]
    assert checkpoint == {
        "phase": "discovery",
        "completed_window_count": completed_before_cancel,
        "planned_window_count": len(planned_windows),
        "next_chunk_index": expected_cursor,
        "candidates": checkpoint["candidates"],
    }
    assert (completed_before_cancel, len(planned_windows)) in progress_updates
    summary = character_discovery_service.character_operation_summary(cancelled_document)
    assert (summary["progress_current"], summary["progress_total"]) == (completed_before_cancel, len(planned_windows))
    project_workspace_service.sync_manifest_operation_summary(project_root, "character_discovery", summary)
    manifest_progress = project_workspace_service.load_manifest(project_root)["operations"]["character_discovery"]
    assert (manifest_progress["progress_current"], manifest_progress["progress_total"]) == (
        completed_before_cancel,
        len(planned_windows),
    )
    page_state = character_discovery_state_service.build_character_discovery_state(
        project_root,
        manifest,
        "en",
        {
            "llm_profiles": [{"id": "profile-1", "label": "Profile One", "enabled": True}],
            "default_character_extraction_profile_id": "profile-1",
        },
    )
    assert any(f"{completed_before_cancel}/{len(planned_windows)}" in note for note in page_state["notes"])

    persisted_writes: list[dict[str, object]] = []
    original_write_json_atomic = character_discovery_service.write_json_atomic

    def _capture_resume_writes(path, payload):
        """Capture strict checkpoints written while the resumed run transitions to synthesis."""
        if Path(path).name == config.CHARACTERS_DOCUMENT_FILE_NAME:
            persisted_writes.append(json.loads(json.dumps(payload)))
        return original_write_json_atomic(path, payload)

    resumed_window_prompts: list[str] = []

    def _complete_resume(_profile, _system_prompt, user_prompt, **kwargs):
        """Complete remaining discovery windows and the one saved synthesis candidate."""
        if str(kwargs["log_context"]["stage_label"]) == "character_discovery_window":
            resumed_window_prompts.append(user_prompt)
            return _window_response_for_names([], "chunk-0001")
        return _synthesis_response_for_name("Alice")

    monkeypatch.setattr(character_discovery_service, "write_json_atomic", _capture_resume_writes)
    monkeypatch.setattr(character_discovery_service.llm_provider_service, "chat_json", _complete_resume)
    completed_document = character_discovery_service.start_or_continue_discovery(
        project_root,
        manifest,
        _profile_payload("profile-2"),
        progress_callback=lambda *_args, **_kwargs: None,
        cancel_requested=lambda: False,
    )

    synthesis_checkpoint = next(
        payload["checkpoint"]
        for payload in persisted_writes
        if isinstance(payload.get("checkpoint"), dict) and payload["checkpoint"].get("phase") == "synthesis"
    )
    assert resumed_window_prompts[0].startswith(f"CHUNK_ID: {next_window[0]['chunk_id']}\n")
    assert synthesis_checkpoint["completed_window_count"] == resumed_planned_window_count
    assert synthesis_checkpoint["planned_window_count"] == resumed_planned_window_count
    assert completed_document["character_profile_id_last_used"] == "profile-2"


def test_resume_state_keeps_window_counts_separate_from_chunk_cursor() -> None:
    """Verify a persisted variable-window baseline never becomes a chunk count."""
    source_chunks = [
        _chunk_payload(f"chunk-{index:04d}", index, '"Hello," said Alice.')
        for index in range(1, 101)
    ]
    checkpoint = {
        "phase": "discovery",
        "completed_window_count": 5,
        "planned_window_count": 12,
        "next_chunk_index": 40,
        "candidates": [],
    }
    restored = character_discovery_service._restore_resume_state(  # noqa: SLF001
        {
            "status": "cancelled",
            "source": {"kind": "original", "language": "en", "fingerprint": "abc"},
            "characters": [],
            "checkpoint": checkpoint,
        },
        input_fingerprint="abc",
        source_chunks=source_chunks,
    )

    summary = character_discovery_service.character_operation_summary(
        {"status": "cancelled", "checkpoint": checkpoint, "characters": []}
    )

    assert restored[0:3] == (5, 12, 40)
    assert summary["progress_current"] == 5
    assert summary["progress_total"] == 12


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


def _window_response_for_names(names: list[str], chunk_id: str) -> dict[str, object]:
    """Build one discovery response containing the requested candidate names."""
    return {
        "payload": {
            "characters": [
                {
                    "canonical_name": name,
                    "aliases": [],
                    "confidence": "high",
                    "evidence": [
                        {
                            "chunk_id": chunk_id,
                            "source_excerpt": f'"Hello," said {name}.',
                            "reason": f"{name} speaks in direct dialogue.",
                        }
                    ],
                }
                for name in names
            ]
        },
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
    }


def _synthesis_response_for_name(name: str) -> dict[str, object]:
    """Build one synthesis response for a named candidate."""
    return {
        "payload": {
            "canonical_name": name,
            "aliases": [],
            "voice_definition_prompt": f"Create a stable voice for {name}.",
            "preview_text": f"Hello there, said {name} with a clear and steady voice today.",
            "confidence": "high",
        },
        "usage": {"input_tokens": 8, "output_tokens": 4, "total_tokens": 12, "usage_available": True},
    }


def _merged_candidate(name: str, sequence_index: int) -> dict[str, object]:
    """Build one merged synthesis candidate with a stable identifier."""
    return {
        "character_id": name.casefold(),
        "canonical_name": name,
        "aliases": [],
        "confidence": "high",
        "identity_merge_count": 1,
        "evidence": [
            {
                "chunk_id": "chunk-0001",
                "sequence_index": sequence_index,
                "dialogue_span_id": "",
                "source_excerpt": f'"Hello," said {name}.',
                "reason": f"{name} speaks in direct dialogue.",
                "confidence": "high",
            }
        ],
    }


def _nested_character_record(
    character_id: str,
    canonical_name: str,
    *,
    origin: str,
    sequence_index: int,
    edited: bool = False,
    voice_text: str = "Stored voice text.",
) -> dict[str, object]:
    """Build one strict nested character record for resume-inventory tests."""
    return {
        "character_id": character_id,
        "canonical_name": canonical_name,
        "aliases": [f"{canonical_name} Alias"],
        "traits": {
            "gender": {"value": "unspecified", "confidence": "high"},
            "age": {"value": "adult", "confidence": "medium"},
        },
        "voice": {
            "definition_prompt": voice_text,
            "preview_text": f"A preserved preview line for {canonical_name} remains intact.",
        },
        "discovery_confidence": "high",
        "provenance": {"origin": origin, "edited": edited},
        "evidence": [
            {
                "chunk_id": "manual" if origin == "manual" else "chunk-0001",
                "sequence_index": sequence_index,
                "source_excerpt": f"Evidence for {canonical_name}.",
                "reason": "Preserved nested evidence.",
            }
        ],
    }


def _set_character_project_chunks(project_root: Path, chunk_count: int) -> None:
    """Replace the fixture chunk document with a requested number of chunks."""
    chunk_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHUNK_ARTIFACT_FILE_NAME
    chunk_path.write_text(
        json.dumps(
            build_chunking_document(
                [
                    {
                        "chunk_id": f"chunk-{index:04d}",
                        "sequence_index": index,
                        "text": f'"Hello from chunk {index}," said Speaker {index}.',
                        "source_start_line": index,
                        "source_end_line": index,
                        "chunking_mode": "deterministic",
                        "semantic_strategy": None,
                        "scene_note": None,
                    }
                    for index in range(1, chunk_count + 1)
                ]
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


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
        "output_reserve_tokens": 512,
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


def _rejected_candidate_diagnostic(
    canonical_name: str,
    reason: str,
    evidence_count: int,
    identity_merge_count: int,
) -> dict[str, object]:
    """Build one strict rejected-candidate diagnostic test payload."""
    return {
        "canonical_name": canonical_name,
        "reason": reason,
        "evidence_count": evidence_count,
        "identity_merge_count": identity_merge_count,
    }


def _character_document(
    source: dict[str, str],
    *,
    status: str,
    checkpoint: dict[str, object] | None,
    characters: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Build one strict Character Discovery test document."""
    persisted_checkpoint = None if checkpoint is None else dict(checkpoint)
    if isinstance(persisted_checkpoint, dict):
        persisted_checkpoint.setdefault("completed_window_count", 0)
        persisted_checkpoint.setdefault("planned_window_count", 0)
    return {
        "status": status,
        "source": dict(source),
        "instructions": "",
        "token_usage": _empty_token_usage(),
        "character_profile_id_last_used": "profile-1",
        "rejected_candidates": [],
        "checkpoint": persisted_checkpoint,
        "failure": None,
        "characters": list(characters or []),
    }


def _nested_saved_character() -> dict[str, object]:
    """Return one nested character record for persistence tests."""
    return character_discovery_service._nested_character_profile(  # noqa: SLF001
        _saved_profile_payload()
    )



def test_character_synthesis_prompt_requests_preview_inside_accepted_range() -> None:
    """
    @brief      Verify the shipped synthesis prompt asks for a preview length the validator accepts.
    @return     None.
    @exception  None
    """
    prompt_text = (config.APP_PROMPTS_PATH / "character_profile_synthesis_user.txt").read_text(encoding="utf-8")
    requested_range = re.search(r"(\d+)-(\d+) spoken words", prompt_text)
    minimum_words, maximum_words = tts_budget_service.preview_word_bounds()

    assert requested_range is not None
    assert minimum_words <= int(requested_range.group(1))
    assert int(requested_range.group(2)) <= maximum_words


# END OF FILE
