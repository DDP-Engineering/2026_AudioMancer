#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_translation_service.py
@brief Focused translation-service tests for AudioMancer.
@details Verifies persisted translation artifacts, resumable translation,
         review-state updates, and approval helpers.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.8.0
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import ai_translation_service, operation_runtime_service, project_workspace_service


def test_ai_translation_service_creates_translation_artifacts(monkeypatch, tmp_path) -> None:
    """
    @brief      Validate ai translation service creates translation artifacts.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationArtifactsProject")
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "validate_required_prompts",
        lambda _names: None,
    )
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    monkeypatch.setattr(
        ai_translation_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {"translated_text": "Translated text"},
            "usage": {
                "input_tokens": 100,
                "output_tokens": 25,
                "total_tokens": 125,
                "usage_available": True,
            },
        },
    )

    report = ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
    )

    translation_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    assert (translation_root / config.TRANSLATED_CHUNKS_FILE_NAME).is_file()
    assert (translation_root / config.TRANSLATION_REPORT_FILE_NAME).is_file()
    assert (translation_root / config.TRANSLATION_STATE_FILE_NAME).is_file()
    assert report["translated_chunk_count"] == 2
    assert report["translation_stage_status"] == ai_translation_service.TRANSLATION_STAGE_TRANSLATED
    assert report["token_usage"]["total_tokens"] == 250
    assert report["budget_metadata"]["context_window"] == 4096
    assert report["budget_metadata"]["max_output_tokens"] == 512
    operation_state = ai_translation_service.load_operation_state(project_root)
    assert operation_state["status"] == "translated"
    assert operation_state["metadata"]["budget_metadata"] == report["budget_metadata"]
    _assert_simplified_translation_state(operation_state)


def test_ai_translation_service_adds_operator_prompt_rules(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify operator translation instructions are appended and persisted.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.2.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationPromptRulesProject")
    captured_prompts = []
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "validate_required_prompts",
        lambda _names: None,
    )
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "load_prompt",
        lambda _name: "Translate to {target_language}:\n{source_text}",
    )
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )

    def fake_chat_json(_profile_payload, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Capture the translation prompt and return a valid fake response.
        @return     Fake translated text payload.
        @exception  None
        @version    0.1.0
        """
        captured_prompts.append(user_prompt)
        return {
            "payload": {"translated_text": "Translated with style"},
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "usage_available": True,
            },
        }

    monkeypatch.setattr(ai_translation_service.llm_provider_service, "chat_json", fake_chat_json)

    report = ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
        additional_translation_instructions="Keep the formality level consistent.",
    )

    operation_state = ai_translation_service.load_operation_state(project_root)
    assert captured_prompts
    assert "Additional operator translation instructions" in captured_prompts[0]
    assert "Keep the formality level consistent." in captured_prompts[0]
    assert report["additional_translation_instructions"] == "Keep the formality level consistent."
    assert operation_state["metadata"]["additional_translation_instructions"] == "Keep the formality level consistent."


def test_ai_translation_service_approve_and_edit_update_review_state(tmp_path) -> None:
    """
    @brief      Validate ai translation service approve and edit update review state.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "TranslationReviewProject")
    source_chunks, translated_chunks, _report = ai_translation_service.ensure_translation_records(
        project_root,
        "ro",
        "profile-1",
    )
    translated_chunks[0]["translated_text"] = "Translated one"
    translated_chunks[0]["status"] = ai_translation_service.TRANSLATED_CHUNK_STATUS_TRANSLATED
    report = ai_translation_service._rebuild_report(translated_chunks, "ro", "profile-1")
    ai_translation_service._persist_translation_state(
        project_root,
        source_chunks,
        translated_chunks,
        report,
        operation_state=ai_translation_service._build_operation_state(
            project_root,
            report,
            status="running",
            started_at="2026-04-07T12:00:00+00:00",
            completed_at=None,
            profile_id="profile-1",
            target_language="ro",
            log_path=project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / "log_ai_transactions_20260407.log",
            token_usage={
                "input_tokens": 11,
                "output_tokens": 7,
                "total_tokens": 18,
                "usage_available": True,
            },
            resume_checkpoint={"next_untranslated_chunk_id": "chunk-0002"},
        ),
    )

    report = ai_translation_service.approve_chunk(project_root, "chunk-0001", "ro", "profile-1")
    assert report["approved_chunk_count"] == 1
    assert report["translation_stage_status"] == ai_translation_service.TRANSLATION_STAGE_IN_PROGRESS
    report = ai_translation_service.update_translated_text(
        project_root, "chunk-0001", "Edited translation", "ro", "profile-1"
    )
    assert report["approved_chunk_count"] == 0
    assert ai_translation_service.load_operation_state(project_root)["metadata"]["approved_chunk_count"] == 0


def test_ai_translation_service_resume_preserves_completed_chunks(monkeypatch, tmp_path) -> None:
    """
    @brief      Validate ai translation service resume preserves completed chunks.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.2.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationResumeProject")
    source_chunks, translated_chunks, _report = ai_translation_service.ensure_translation_records(
        project_root,
        "ro",
        "profile-1",
    )
    translated_chunks[0]["translated_text"] = "Existing translation"
    translated_chunks[0]["status"] = ai_translation_service.TRANSLATED_CHUNK_STATUS_TRANSLATED
    report = ai_translation_service._rebuild_report(translated_chunks, "ro", "profile-1")
    ai_translation_service._persist_translation_state(
        project_root,
        source_chunks,
        translated_chunks,
        report,
        operation_state=ai_translation_service._build_operation_state(
            project_root,
            report,
            status="running",
            started_at="2026-04-07T12:00:00+00:00",
            completed_at=None,
            profile_id="profile-1",
            target_language="ro",
            log_path=project_root / "log_ai_translation_20260407.log",
            token_usage={
                "input_tokens": 20,
                "output_tokens": 10,
                "total_tokens": 30,
                "usage_available": True,
            },
            resume_checkpoint={"next_untranslated_chunk_id": "chunk-0002"},
        ),
    )
    existing_log_path = project_root / "log_ai_translation_20260407.log"
    existing_log_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "validate_required_prompts",
        lambda _names: None,
    )
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    calls = []

    def fake_chat_json(*_args, **kwargs):
        """
        @brief      Record the transaction log path and return a fake translation.
        @return     Fake translated text payload.
        @exception  None
        @version    0.1.0
        """
        calls.append(str(kwargs.get("log_path", "")))
        return {
            "payload": {"translated_text": "New translation"},
            "usage": {
                "input_tokens": 50,
                "output_tokens": 15,
                "total_tokens": 65,
                "usage_available": True,
            },
        }

    monkeypatch.setattr(ai_translation_service.llm_provider_service, "chat_json", fake_chat_json)

    report = ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
    )

    assert len(calls) == 1
    translated_chunks = ai_translation_service.load_translated_chunks(project_root)
    assert translated_chunks[0]["translated_text"] == "Existing translation"
    assert translated_chunks[1]["translated_text"] == "New translation"
    assert report["translated_chunk_count"] == 2
    assert report["translation_stage_status"] == ai_translation_service.TRANSLATION_STAGE_TRANSLATED
    assert report["token_usage"]["total_tokens"] == 95
    operation_state = ai_translation_service.load_operation_state(project_root)
    _assert_simplified_translation_state(operation_state)
    assert operation_state["metadata"]["log_relative_path"] == "log_ai_translation_20260407.log"
    assert calls == [str(existing_log_path)]


def test_ai_translation_service_uses_single_checkpoint_for_one_resumed_chunk(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-004 keeps one atomic chunk checkpoint during resume.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationSingleCheckpointProject")
    source_chunks, translated_chunks, _report = ai_translation_service.ensure_translation_records(
        project_root,
        "ro",
        "profile-1",
    )
    translated_chunks[0]["translated_text"] = "Existing translation"
    translated_chunks[0]["status"] = ai_translation_service.TRANSLATED_CHUNK_STATUS_TRANSLATED
    report = ai_translation_service._rebuild_report(translated_chunks, "ro", "profile-1")
    ai_translation_service._persist_translation_state(
        project_root,
        source_chunks,
        translated_chunks,
        report,
        operation_state=ai_translation_service._refresh_operation_state(
            project_root,
            source_chunks,
            translated_chunks,
            report,
            ai_translation_service.load_operation_state(project_root),
            "profile-1",
            "ro",
            {},
        ),
    )
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "validate_required_prompts",
        lambda _names: None,
    )
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    monkeypatch.setattr(
        ai_translation_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {"payload": {"translated_text": "New translation"}, "usage": {}},
    )
    original_write_json_atomic = ai_translation_service.write_json_atomic
    translated_artifact_writes = []

    def spy_write_json_atomic(path, payload, **kwargs):
        """
        @brief      Record translated artifact writes and preserve persistence.
        @return     None.
        @exception  None
        @version    0.1.0
        """
        if path.name == config.TRANSLATED_CHUNKS_FILE_NAME:
            translated_artifact_writes.append(path)
        original_write_json_atomic(path, payload, **kwargs)

    monkeypatch.setattr(ai_translation_service, "write_json_atomic", spy_write_json_atomic)

    ai_translation_service.start_or_continue_translation(project_root, manifest, _profile_payload(), "ro")

    assert len(translated_artifact_writes) == 3


def test_ai_translation_service_review_action_writes_artifact_once(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-004 review approval avoids precondition rewrite churn.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "TranslationReviewWriteCountProject")
    source_chunks, translated_chunks, _report = ai_translation_service.ensure_translation_records(
        project_root,
        "ro",
        "profile-1",
    )
    translated_chunks[0]["translated_text"] = "Translated one"
    translated_chunks[0]["status"] = ai_translation_service.TRANSLATED_CHUNK_STATUS_TRANSLATED
    report = ai_translation_service._rebuild_report(translated_chunks, "ro", "profile-1")
    ai_translation_service._persist_translation_state(
        project_root,
        source_chunks,
        translated_chunks,
        report,
        operation_state=ai_translation_service._refresh_operation_state(
            project_root,
            source_chunks,
            translated_chunks,
            report,
            ai_translation_service.load_operation_state(project_root),
            "profile-1",
            "ro",
            {},
        ),
    )
    original_write_json_atomic = ai_translation_service.write_json_atomic
    translated_artifact_writes = []

    def spy_write_json_atomic(path, payload, **kwargs):
        """
        @brief      Record translated artifact writes and preserve persistence.
        @return     None.
        @exception  None
        @version    0.1.0
        """
        if path.name == config.TRANSLATED_CHUNKS_FILE_NAME:
            translated_artifact_writes.append(path)
        original_write_json_atomic(path, payload, **kwargs)

    monkeypatch.setattr(ai_translation_service, "write_json_atomic", spy_write_json_atomic)

    ai_translation_service.approve_chunk(project_root, "chunk-0001", "ro", "profile-1")

    assert len(translated_artifact_writes) == 1


def test_ai_translation_service_tolerates_malformed_translation_json(tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-004 treats malformed translation artifacts as recoverable.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "TranslationMalformedJsonProject")
    (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text("[", encoding="utf-8")
    (project_root / config.TRANSLATION_REPORT_FILE_NAME).write_text("{", encoding="utf-8")
    (project_root / config.TRANSLATION_STATE_FILE_NAME).write_text("{", encoding="utf-8")

    source_chunks, translated_chunks, report = ai_translation_service.ensure_translation_records(
        project_root,
        "ro",
        "profile-1",
    )

    assert len(source_chunks) == 2
    assert len(translated_chunks) == 2
    assert report["translation_stage_status"] == ai_translation_service.TRANSLATION_STAGE_NOT_STARTED
    assert ai_translation_service.load_operation_state(project_root)["status"] == "not_started"


def test_ai_translation_service_persists_cancelled_state(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-004 persists cancellation terminal state.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationCancelledStateProject")
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "validate_required_prompts",
        lambda _names: None,
    )
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        ai_translation_service.start_or_continue_translation(
            project_root,
            manifest,
            _profile_payload(),
            "ro",
            cancel_requested=lambda: True,
        )

    operation_state = ai_translation_service.load_operation_state(project_root)
    assert operation_state["status"] == "cancelled"
    assert operation_state["resume_checkpoint"]["next_untranslated_chunk_id"] == "chunk-0001"


def test_ai_translation_service_persists_failed_state(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-004 persists failure terminal state.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationFailedStateProject")
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "validate_required_prompts",
        lambda _names: None,
    )
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )

    def fail_chat_json(*_args, **_kwargs):
        """
        @brief      Raise a provider failure for terminal-state assertions.
        @return     None.
        @exception  RuntimeError Always raised for this test double.
        @version    0.1.0
        """
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(ai_translation_service.llm_provider_service, "chat_json", fail_chat_json)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        ai_translation_service.start_or_continue_translation(project_root, manifest, _profile_payload(), "ro")

    operation_state = ai_translation_service.load_operation_state(project_root)
    assert operation_state["status"] == "failed"
    assert operation_state["resume_checkpoint"]["next_untranslated_chunk_id"] == "chunk-0001"


def test_ai_translation_start_same_language_uses_llm(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify start translation calls the LLM even when source and target languages match.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-19
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationStartSameLanguageProject")
    manifest["original_language"] = "en"
    calls: list[str] = []
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "validate_required_prompts",
        lambda _names: None,
    )
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )

    def fake_chat_json(_profile_payload, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Capture same-language prompts and return distinct fake text.
        @return     Fake translated text payload.
        @exception  None
        @version    0.1.0
        """
        calls.append(user_prompt)
        return {
            "payload": {"translated_text": f"LLM same-language text {len(calls)}"},
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "usage_available": True,
            },
        }

    monkeypatch.setattr(ai_translation_service.llm_provider_service, "chat_json", fake_chat_json)

    report = ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "en",
    )

    assert isinstance(report, dict)
    assert len(calls) == 2
    assert report["translation_stage_status"] == ai_translation_service.TRANSLATION_STAGE_TRANSLATED
    assert report["translated_chunk_count"] == 2
    assert report["approved_chunk_count"] == 0
    translated_chunks = ai_translation_service.load_translated_chunks(project_root)
    assert [chunk["translated_text"] for chunk in translated_chunks] == [
        "LLM same-language text 1",
        "LLM same-language text 2",
    ]
    operation_state = ai_translation_service.load_operation_state(project_root)
    assert operation_state["mode"] == "ai_assisted"
    assert "pass_through" not in operation_state["metadata"]
    _assert_simplified_translation_state(operation_state)


def test_ai_translation_service_initializes_empty_operation_metadata(tmp_path) -> None:
    """
    @brief      Verify first page access creates empty translation state from chunks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "TranslationInitialStateProject")

    _source_chunks, translated_chunks, report = ai_translation_service.ensure_translation_records(
        project_root,
        "ro",
        "profile-1",
    )

    operation_state = ai_translation_service.load_operation_state(project_root)
    assert report["translation_stage_status"] == ai_translation_service.TRANSLATION_STAGE_NOT_STARTED
    assert translated_chunks[0]["translated_text"] == ""
    assert operation_state["status"] == "not_started"
    assert operation_state["metadata"]["total_chunk_count"] == 2
    _assert_simplified_translation_state(operation_state)


def test_ai_translation_budget_metadata_reserves_max_output_tokens(monkeypatch) -> None:
    """
    @brief      Verify larger translation output budgets reduce available source-text budget.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )

    small_output_budget = ai_translation_service._build_budget_metadata(
        {
            **_profile_payload(),
            "context_window": 8192,
            "max_output_tokens": 512,
        },
        "ro",
        "system",
    )
    large_output_budget = ai_translation_service._build_budget_metadata(
        {
            **_profile_payload(),
            "context_window": 8192,
            "max_output_tokens": 4096,
        },
        "ro",
        "system",
    )

    assert large_output_budget["max_output_tokens"] == 4096
    assert large_output_budget["text_budget_tokens"] < small_output_budget["text_budget_tokens"]


def test_ai_translation_rejects_profiles_with_no_input_budget(monkeypatch) -> None:
    """
    @brief      Verify excessive output-token settings fail before translation starts.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )

    with pytest.raises(ValueError, match="too little room"):
        ai_translation_service._build_budget_metadata(
            {
                **_profile_payload(),
                "context_window": 1024,
                "max_output_tokens": 900,
            },
            "ro",
            "system",
        )


def _assert_simplified_translation_state(operation_state: dict[str, object]) -> None:
    """
    @brief      Assert translation operation state does not contain removed path metadata.
    @param[in]  operation_state Persisted translation operation state payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-17
    @version    0.1.0
    """
    for field_name in ("folder_relative_path", "input_paths", "output_paths", "artifact_paths"):
        assert field_name not in operation_state
    metadata = operation_state.get("metadata", {})
    assert isinstance(metadata, dict)
    assert "source_chunk_count" not in metadata
    assert "started_by_operator" not in metadata


def _create_chunked_project(tmp_path, name: str):
    """
    @brief      Provide the create chunked project test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 12,
    }
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [config.CHUNK_ARTIFACT_FILE_NAME]
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root
    chunk_root.mkdir(parents=True, exist_ok=True)
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": "Chapter I",
                    "text": "Original one",
                    "source_start_line": 1,
                    "source_end_line": 1,
                    "chunking_mode": "deterministic",
                    "semantic_strategy": None,
                    "scene_note": None,
                },
                {
                    "chunk_id": "chunk-0002",
                    "sequence_index": 2,
                    "chapter_label": "Chapter I",
                    "text": "Original two",
                    "source_start_line": 3,
                    "source_end_line": 3,
                    "chunking_mode": "deterministic",
                    "semantic_strategy": None,
                    "scene_note": None,
                },
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root, manifest


def _profile_payload() -> dict[str, object]:
    """
    @brief      Provide the profile payload test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    return {
        "id": "profile-1",
        "label": "Translation Profile",
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
