#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_chunking_service.py
@brief Focused tests for the AudioMancer AI chunking service.
@details Verifies AI-assisted chunking writes canonical chunk artifacts,
         persists resumable state, and rebuilds chunk spans from AI boundaries.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.5.2
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import ai_chunking_service, operation_runtime_service, project_workspace_service


def test_ai_chunking_windows_use_configured_strategy_caps(monkeypatch) -> None:
    """
    @brief      Verify AI chunking paragraph caps are read from shared configuration.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.2.0
    """
    paragraph_records = [{"unit_id": f"paragraph-{index:04d}", "text": "Short paragraph."} for index in range(1, 6)]
    monkeypatch.setattr(
        config,
        "AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY",
        {
            "paragraph": 3,
            "meaning": 2,
            "scene": 4,
        },
    )

    windows = ai_chunking_service._build_windows(
        paragraph_records,
        "meaning",
        {
            "context_window": 4096,
            "max_output_tokens": 512,
            "prompt_budget_tokens": 20,
            "text_budget_tokens": 2000,
            "safety_margin_tokens": 409,
            "strategy_paragraph_cap": config.AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY["meaning"],
        },
    )

    assert windows == [
        {"start_index": 0, "end_index": 1},
        {"start_index": 2, "end_index": 3},
        {"start_index": 4, "end_index": 4},
    ]


def test_ai_chunking_large_context_allows_larger_scene_windows(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify large AI contexts can feed more than the old scene paragraph window.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)
    paragraph_records = [
        {"unit_id": f"paragraph-{index:04d}", "text": "Short scene paragraph."} for index in range(1, 21)
    ]
    budget_metadata = ai_chunking_service._build_budget_metadata(
        {
            "context_window": 16384,
            "max_output_tokens": 512,
        },
        "scene",
        "scene",
        "",
    )

    windows = ai_chunking_service._build_windows(paragraph_records, "scene", budget_metadata)

    assert windows == [{"start_index": 0, "end_index": 19}]
    assert windows[0]["end_index"] > 9


def test_ai_chunking_small_context_limits_paragraph_windows(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify small AI contexts reduce the paragraph count per AI request.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)
    paragraph_records = [{"unit_id": f"paragraph-{index:04d}", "text": "x" * 500} for index in range(1, 13)]
    budget_metadata = ai_chunking_service._build_budget_metadata(
        {
            "context_window": 2048,
            "max_output_tokens": 512,
        },
        "scene",
        "scene",
        "",
    )

    windows = ai_chunking_service._build_windows(paragraph_records, "scene", budget_metadata)

    assert len(windows) > 1
    assert windows[0]["end_index"] < len(paragraph_records) - 1


def test_ai_chunking_rejects_profiles_with_no_input_budget(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify excessive output-token settings fail before AI chunking starts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)

    with pytest.raises(ValueError, match="too little room"):
        ai_chunking_service._build_budget_metadata(
            {
                "context_window": 1024,
                "max_output_tokens": 900,
            },
            "scene",
            "scene",
            "",
        )


def test_ai_chunking_online_profile_uses_direct_context_fraction_without_paragraph_cap(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify online AI chunking ignores local paragraph caps and output-token budget subtraction.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)
    monkeypatch.setattr(config, "AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY", {"scene": 1})
    paragraph_records = [{"unit_id": f"paragraph-{index:04d}", "text": "Short paragraph."} for index in range(1, 6)]

    budget_metadata = ai_chunking_service._build_budget_metadata(
        {
            "backend_kind": config.ONLINE_AI_BACKEND_KIND,
            "context_window": 10000,
            "max_output_tokens": 9900,
        },
        "scene",
        "scene",
        "",
    )

    assert budget_metadata["text_budget_tokens"] == 3000
    assert budget_metadata["strategy_paragraph_cap"] == 0
    assert ai_chunking_service._build_windows(paragraph_records, "scene", budget_metadata) == [
        {"start_index": 0, "end_index": 4}
    ]


def test_ai_chunking_keeps_oversized_paragraphs_whole() -> None:
    """
    @brief      Verify budgeted windows never split a single oversized paragraph.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    paragraph_records = [
        {"unit_id": "paragraph-0001", "text": "x" * 3000},
        {"unit_id": "paragraph-0002", "text": "Short follow-up."},
    ]

    windows = ai_chunking_service._build_windows(
        paragraph_records,
        "scene",
        {
            "context_window": 2048,
            "max_output_tokens": 512,
            "prompt_budget_tokens": 20,
            "text_budget_tokens": 512,
            "safety_margin_tokens": 256,
            "strategy_paragraph_cap": 64,
        },
    )

    assert windows == [
        {"start_index": 0, "end_index": 0},
        {"start_index": 1, "end_index": 1},
    ]


def test_ai_chunking_writes_chunking_artifacts_and_log(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify AI-assisted chunking writes canonical output, report, state, and AI log artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_system.txt").write_text("{strategy}", encoding="utf-8")
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)

    project_root, manifest = project_workspace_service.create_project("AiChunkingProject", tmp_path)
    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_path.write_text(
        "CHAPTER I\n\nParagraph one.\n\nParagraph two.\n\nParagraph three.\n",
        encoding="utf-8",
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}"
    ]

    monkeypatch.setattr(
        ai_chunking_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {"break_after_unit_ids": ["paragraph-0002"]},
            "usage": {"input_tokens": 25, "output_tokens": 5, "total_tokens": 30, "usage_available": True},
        },
    )

    report_payload = ai_chunking_service.chunk_text(
        project_root,
        manifest,
        {
            "id": "profile_1",
            "label": "Chunking Profile",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": 4096,
            "max_output_tokens": 512,
            "request_timeout_seconds": 30,
            "temperature": 0.2,
        },
        "meaning",
    )

    chunking_root = project_root
    assert (chunking_root / config.CHUNK_ARTIFACT_FILE_NAME).is_file()
    assert (chunking_root / config.CHUNKING_REPORT_FILE_NAME).is_file()
    assert (chunking_root / config.CHUNKING_STATE_FILE_NAME).is_file()
    assert any(path.name.startswith(config.AI_TRANSACTION_LOG_FILE_PREFIX) for path in chunking_root.glob("*.log"))
    assert report_payload["chunking_mode"] == "ai_assisted"
    assert report_payload["semantic_strategy"] == "meaning"
    assert report_payload["budget_metadata"]["context_window"] == 4096
    assert report_payload["budget_metadata"]["max_output_tokens"] == 512
    assert report_payload["budget_metadata"]["strategy_paragraph_cap"] == config.DEFAULT_AI_CHUNKING_MEANING_WINDOW_SIZE
    state_payload = json.loads((chunking_root / config.CHUNKING_STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert state_payload["metadata"]["budget_metadata"] == report_payload["budget_metadata"]
    chunks = json.loads((chunking_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))
    assert len(chunks) == 2
    assert chunks[0]["chunking_mode"] == "ai_assisted"
    assert chunks[0]["semantic_strategy"] == "meaning"
    assert chunks[0]["source_start_line"] == 1
    assert chunks[0]["source_end_line"] == 3
    assert "CHAPTER I" in chunks[0]["text"]
    assert "chapter_label" not in chunks[0]
    assert "chapter_label" not in chunks[1]


def test_ai_chunking_appends_operator_instructions_to_prompt_and_state(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify AI-assisted chunking appends operator rules and persists them with operation state.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_system.txt").write_text("{strategy}", encoding="utf-8")
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)

    project_root, manifest = project_workspace_service.create_project("AiChunkingExtraPromptProject", tmp_path)
    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_path.write_text("Paragraph one.\n\nParagraph two.\n", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-05-12T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}"
    ]
    captured_user_prompts: list[str] = []

    def _chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Provide the fake chat json test helper.
        @return     Fake AI chunking response payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-12
        @version    0.1.0
        """
        captured_user_prompts.append(user_prompt)
        return {
            "payload": {"break_after_unit_ids": ["paragraph-0001"]},
            "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14, "usage_available": True},
        }

    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _chat_json)

    report_payload = ai_chunking_service.chunk_text(
        project_root,
        manifest,
        {
            "id": "profile_1",
            "label": "Chunking Profile",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": 4096,
            "max_output_tokens": 512,
            "request_timeout_seconds": 30,
            "temperature": 0.2,
        },
        "scene",
        additional_chunking_instructions="Keep all chapter prologues in separate chunks.",
    )

    assert captured_user_prompts
    assert "Additional operator chunking instructions:" in captured_user_prompts[0]
    assert "Keep all chapter prologues in separate chunks." in captured_user_prompts[0]
    assert report_payload["additional_chunking_instructions"] == "Keep all chapter prologues in separate chunks."
    assert report_payload["additional_chunking_instructions_fingerprint"]
    state_payload = json.loads((project_root / config.CHUNKING_STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert state_payload["resume_checkpoint"] is None
    assert "additional_chunking_instructions" not in state_payload["metadata"]


def test_ai_chunking_ignores_invalid_boundaries_and_closes_last_chunk(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify invalid AI boundary ids do not corrupt output and the last chunk closes automatically.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_system.txt").write_text("{strategy}", encoding="utf-8")
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)

    project_root, manifest = project_workspace_service.create_project("AiChunkingInvalidBreaksProject", tmp_path)
    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_path.write_text("Paragraph one.\n\nParagraph two.\n", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}"
    ]

    monkeypatch.setattr(
        ai_chunking_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {"break_after_unit_ids": ["paragraph-9999"]},
            "usage": {"input_tokens": 15, "output_tokens": 4, "total_tokens": 19, "usage_available": True},
        },
    )

    ai_chunking_service.chunk_text(
        project_root,
        manifest,
        {
            "id": "profile_1",
            "label": "Chunking Profile",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": 4096,
            "max_output_tokens": 512,
            "request_timeout_seconds": 30,
            "temperature": 0.2,
        },
        "paragraph",
    )

    chunking_root = project_root
    chunks = json.loads((chunking_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))
    assert len(chunks) == 1
    assert "Paragraph one." in chunks[0]["text"]
    assert "Paragraph two." in chunks[0]["text"]


def test_ai_chunking_uses_cleanup_metadata_paragraph_ids(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify AI chunking sends stable metadata paragraph ids to the model.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_system.txt").write_text("{strategy}", encoding="utf-8")
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)

    project_root, manifest = project_workspace_service.create_project("AiChunkingMetadataIds", tmp_path)
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "Visible first.\n\nVisible second.\n",
        encoding="utf-8",
    )
    (project_root / config.CLEANED_TEXT_METADATA_FILE_NAME).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "paragraphs": [
                    {
                        "paragraph_id": "paragraph-0042",
                        "text": "Visible first.\n\nVisible second.",
                        "source_start_line": 1,
                        "source_end_line": 3,
                        "source_page_start": 1,
                        "source_page_end": 2,
                        "starts_after_page_break": False,
                        "joined_across_page_break": True,
                        "boundary_confidence": "repaired",
                        "warning_flags": [],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-26T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    captured_prompt = {"text": ""}

    def _chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Capture the generated AI chunking prompt and return one boundary.
        @param[in]  _profile Ignored profile payload.
        @param[in]  _system_prompt Ignored system prompt.
        @param[in]  user_prompt Rendered user prompt.
        @return     Fake provider payload with one chunk boundary and token usage.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
        """
        captured_prompt["text"] = user_prompt
        return {
            "payload": {"break_after_unit_ids": ["paragraph-0042"]},
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
        }

    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _chat_json)

    ai_chunking_service.chunk_text(
        project_root,
        manifest,
        {
            "id": "profile_1",
            "label": "Chunking Profile",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": 4096,
            "max_output_tokens": 512,
            "request_timeout_seconds": 30,
            "temperature": 0.2,
        },
        "paragraph",
    )

    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))
    assert "paragraph-0042" in captured_prompt["text"]
    assert chunks[0]["cleanup_joined_across_page_break"] is True


def test_ai_chunking_resumes_from_saved_window_checkpoint(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify interrupted AI chunking resumes from the next unfinished window.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.1
    """
    monkeypatch.setattr(
        config,
        "AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY",
        {
            **config.AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY,
            "paragraph": 20,
        },
    )
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_system.txt").write_text("{strategy}", encoding="utf-8")
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)

    project_root, manifest = project_workspace_service.create_project("AiChunkingResumeProject", tmp_path)
    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_text = "\n\n".join(f"Paragraph {index}." for index in range(1, 41)) + "\n"
    cleaned_path.write_text(cleaned_text, encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}"
    ]

    responses = iter(
        [
            {"break_after_unit_ids": ["paragraph-0002"]},
            operation_runtime_service.OperationCancelledError("stop"),
        ]
    )

    def _chat_json(*_args, **_kwargs):
        """
        @brief      Return queued chunking responses for resume coverage.
        @param[in]  _args Ignored positional provider arguments.
        @param[in]  _kwargs Ignored keyword provider arguments.
        @return     Fake provider payload with chunking boundaries and token usage.
        @exception  OperationCancelledError Raised by queued cancellation response.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
        """
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return {
            "payload": response,
            "usage": {
                "input_tokens": 40,
                "output_tokens": 10,
                "total_tokens": 50,
                "usage_available": True,
            },
        }

    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _chat_json)

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        ai_chunking_service.chunk_text(
            project_root,
            manifest,
            {
                "id": "profile_1",
                "label": "Chunking Profile",
                "backend_kind": "lmstudio",
                "base_url": "http://127.0.0.1:1234",
                "api_key": "",
                "model_name": "qwen3-8b",
                "context_window": 4096,
                "max_output_tokens": 512,
                "request_timeout_seconds": 30,
                "temperature": 0.2,
            },
            "paragraph",
        )

    state_payload = json.loads((project_root / config.CHUNKING_STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert state_payload["status"] == "running"
    assert state_payload["progress_current"] == 1

    monkeypatch.setattr(
        ai_chunking_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {"break_after_unit_ids": ["paragraph-0039"]},
            "usage": {
                "input_tokens": 30,
                "output_tokens": 5,
                "total_tokens": 35,
                "usage_available": True,
            },
        },
    )

    report_payload = ai_chunking_service.chunk_text(
        project_root,
        manifest,
        {
            "id": "profile_1",
            "label": "Chunking Profile",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": 4096,
            "max_output_tokens": 512,
            "request_timeout_seconds": 30,
            "temperature": 0.2,
        },
        "paragraph",
    )

    assert report_payload["chunk_count"] == 3
    assert report_payload["token_usage"]["total_tokens"] == 85
    completed_state = json.loads((project_root / config.CHUNKING_STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert completed_state["status"] == "completed"
    assert completed_state["progress_current"] == 2


def test_ai_chunking_restarts_when_checkpoint_lacks_completed_unit_count(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify old AI chunking checkpoints without completed-unit counts are not resumed.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    monkeypatch.setattr(
        config,
        "AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY",
        {
            **config.AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY,
            "paragraph": 20,
        },
    )
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_system.txt").write_text("{strategy}", encoding="utf-8")
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)

    project_root, manifest = project_workspace_service.create_project("AiChunkingOldCheckpointProject", tmp_path)
    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_path.write_text("\n\n".join(f"Paragraph {index}." for index in range(1, 41)) + "\n", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}"
    ]
    profile = {
        "id": "profile_1",
        "label": "Chunking Profile",
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234",
        "api_key": "",
        "model_name": "qwen3-8b",
        "context_window": 4096,
        "max_output_tokens": 512,
        "request_timeout_seconds": 30,
        "temperature": 0.2,
    }
    responses = iter(
        [
            {"break_after_unit_ids": ["paragraph-0002"]},
            operation_runtime_service.OperationCancelledError("stop"),
        ]
    )

    def _first_chat_json(*_args, **_kwargs):
        """
        @brief      Return one response and then cancel to create an interrupted checkpoint.
        @return     Fake provider payload with one chunking boundary.
        @exception  OperationCancelledError Raised by queued cancellation response.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-15
        @version    0.1.0
        """
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return {
            "payload": response,
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
        }

    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _first_chat_json)
    with pytest.raises(operation_runtime_service.OperationCancelledError):
        ai_chunking_service.chunk_text(project_root, manifest, profile, "paragraph")

    state_path = project_root / config.CHUNKING_STATE_FILE_NAME
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    checkpoint = dict(state_payload["resume_checkpoint"])
    checkpoint.pop("completed_unit_count", None)
    checkpoint["completed_last_unit_id"] = "paragraph-0020"
    checkpoint["budget_metadata"] = dict(state_payload["metadata"]["budget_metadata"])
    state_payload["resume_checkpoint"] = checkpoint
    state_path.write_text(json.dumps(state_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    captured_prompts: list[str] = []

    def _second_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Capture prompts for restart verification.
        @return     Fake provider payload with one chunking boundary.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-15
        @version    0.1.0
        """
        captured_prompts.append(user_prompt)
        return {
            "payload": {"break_after_unit_ids": ["paragraph-0039"]},
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
        }

    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _second_chat_json)

    ai_chunking_service.chunk_text(project_root, manifest, profile, "paragraph")

    assert captured_prompts
    assert "paragraph-0001" in captured_prompts[0]
    assert "paragraph-0021" not in captured_prompts[0]


def test_ai_chunking_continues_resume_when_budget_metadata_changes(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify resume continues from the next paragraph when the selected profile budget changes.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.2.0
    """
    monkeypatch.setattr(
        config,
        "AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY",
        {
            **config.AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY,
            "paragraph": 20,
        },
    )
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_system.txt").write_text("{strategy}", encoding="utf-8")
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)

    project_root, manifest = project_workspace_service.create_project("AiChunkingBudgetRestartProject", tmp_path)
    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_path.write_text("\n\n".join(f"Paragraph {index}." for index in range(1, 41)) + "\n", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}"
    ]
    first_profile = {
        "id": "profile_1",
        "label": "Chunking Profile",
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234",
        "api_key": "",
        "model_name": "qwen3-8b",
        "context_window": 4096,
        "max_output_tokens": 512,
        "request_timeout_seconds": 30,
        "temperature": 0.2,
    }
    responses = iter(
        [
            {"break_after_unit_ids": ["paragraph-0002"]},
            operation_runtime_service.OperationCancelledError("stop"),
        ]
    )

    def _first_chat_json(*_args, **_kwargs):
        """
        @brief      Return the first queued chunking response before cancellation.
        @param[in]  _args Ignored positional provider arguments.
        @param[in]  _kwargs Ignored keyword provider arguments.
        @return     Fake provider payload with one chunking boundary.
        @exception  OperationCancelledError Raised by queued cancellation response.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
        """
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return {
            "payload": response,
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
        }

    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _first_chat_json)
    with pytest.raises(operation_runtime_service.OperationCancelledError):
        ai_chunking_service.chunk_text(project_root, manifest, first_profile, "paragraph")

    captured_prompts: list[str] = []

    def _second_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Provide the second chat json test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        captured_prompts.append(user_prompt)
        return {
            "payload": {"break_after_unit_ids": ["paragraph-0039"]},
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
        }

    second_profile = {
        **first_profile,
        "id": "profile_2",
        "model_name": "qwen3-14b",
        "context_window": 8192,
        "max_output_tokens": 768,
        "temperature": 0.4,
    }
    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _second_chat_json)

    report_payload = ai_chunking_service.chunk_text(project_root, manifest, second_profile, "paragraph")

    assert captured_prompts
    assert "paragraph-0001" not in captured_prompts[0]
    assert "paragraph-0021" in captured_prompts[0]
    assert report_payload["ai_profile_id"] == "profile_2"
    assert report_payload["model_name"] == "qwen3-14b"
    assert report_payload["context_window"] == 8192
    assert report_payload["max_output_tokens"] == 768
    assert report_payload["temperature"] == 0.4
    assert len(report_payload["profile_usage_history"]) == 2
    completed_state = json.loads((project_root / config.CHUNKING_STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert completed_state["resume_checkpoint"] is None
    assert "completed_unit_count" not in completed_state["metadata"]
    assert completed_state["metadata"]["model_name"] == "qwen3-14b"


# END OF FILE
