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
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import ai_chunking_service, operation_runtime_service, project_workspace_service
from chunking_test_support import read_chunking_document, write_chunking_document, write_cleanup_input


def test_ai_chunking_windows_use_configured_strategy_caps(monkeypatch) -> None:
    """
    @brief      Verify AI chunking paragraph caps are read from shared configuration.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
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

    windows = ai_chunking_service._build_windows(paragraph_records, budget_metadata)

    assert windows == [{"start_index": 0, "end_index": 19}]
    assert windows[0]["end_index"] > 9


def test_ai_chunking_small_context_limits_paragraph_windows(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify small AI contexts reduce the paragraph count per AI request.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
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

    windows = ai_chunking_service._build_windows(paragraph_records, budget_metadata)

    assert len(windows) > 1
    assert windows[0]["end_index"] < len(paragraph_records) - 1


def test_ai_chunking_rejects_profiles_with_no_input_budget(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify excessive output-token settings fail before AI chunking starts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
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
    assert ai_chunking_service._build_windows(paragraph_records, budget_metadata) == [
        {"start_index": 0, "end_index": 4}
    ]


def test_ai_chunking_context_modes_control_paragraph_caps(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify S-0002 and REQ-FUNC-039 map chunking context modes to prompt-window caps.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)
    paragraph_records = [
        {"unit_id": f"paragraph-{index:04d}", "text": "Short scene paragraph."} for index in range(1, 301)
    ]
    profile_payload = {
        "context_window": 262144,
        "max_output_tokens": 512,
    }

    balanced_metadata = ai_chunking_service._build_budget_metadata(
        profile_payload,
        "scene",
        "scene",
        "",
        chunking_context_mode=config.AI_CHUNKING_CONTEXT_MODE_BALANCED,
    )
    wide_metadata = ai_chunking_service._build_budget_metadata(
        profile_payload,
        "scene",
        "scene",
        "",
        chunking_context_mode=config.AI_CHUNKING_CONTEXT_MODE_WIDE_SCENE,
    )
    maximum_metadata = ai_chunking_service._build_budget_metadata(
        profile_payload,
        "scene",
        "scene",
        "",
        chunking_context_mode=config.AI_CHUNKING_CONTEXT_MODE_MAXIMUM,
    )

    assert balanced_metadata["strategy_paragraph_cap"] == 128
    assert wide_metadata["strategy_paragraph_cap"] == 256
    assert maximum_metadata["strategy_paragraph_cap"] == 0
    assert ai_chunking_service._build_windows(paragraph_records, balanced_metadata)[0]["end_index"] == 127
    assert ai_chunking_service._build_windows(paragraph_records, wide_metadata)[0]["end_index"] == 255
    assert ai_chunking_service._build_windows(paragraph_records, maximum_metadata) == [
        {"start_index": 0, "end_index": 299}
    ]


def test_ai_chunking_keeps_oversized_paragraphs_whole() -> None:
    """
    @brief      Verify budgeted windows never split a single oversized paragraph.
    @return     None.
    @exception  None
    """
    paragraph_records = [
        {"unit_id": "paragraph-0001", "text": "x" * 3000},
        {"unit_id": "paragraph-0002", "text": "Short follow-up."},
    ]

    windows = ai_chunking_service._build_windows(
        paragraph_records,
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
    write_cleanup_input(project_root, cleaned_path.read_text(encoding="utf-8"))
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
            "payload": {
                "chunks": [
                    {
                        "start_paragraph": 1,
                        "start_text": "CHAPTER I",
                        "break_after_paragraph": 2,
                    }
                ]
            },
            "usage": {"input_tokens": 25, "output_tokens": 5, "total_tokens": 30, "usage_available": True},
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
        "meaning",
    )

    chunking_root = project_root
    assert (chunking_root / config.CHUNK_ARTIFACT_FILE_NAME).is_file()
    assert any(path.name.startswith(config.AI_TRANSACTION_LOG_FILE_PREFIX) for path in chunking_root.glob("*.log"))
    document = read_chunking_document(chunking_root)
    assert document["mode"] == "ai_assisted"
    assert document["semantic_strategy"] == "meaning"
    assert "budget_metadata" not in document
    chunks = document["chunks"]
    assert len(chunks) == 2
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
    write_cleanup_input(project_root, cleaned_path.read_text(encoding="utf-8"))
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
        """
        captured_user_prompts.append(user_prompt)
        return {
            "payload": {
                "chunks": [
                    {
                        "start_paragraph": 1,
                        "start_text": "Paragraph one.",
                        "break_after_paragraph": 1,
                    }
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14, "usage_available": True},
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
        "scene",
        additional_chunking_instructions="Keep all chapter prologues in separate chunks.",
    )

    assert captured_user_prompts
    assert "Additional operator chunking instructions:" in captured_user_prompts[0]
    assert "Keep all chapter prologues in separate chunks." in captured_user_prompts[0]
    document = read_chunking_document(project_root)
    assert document["additional_chunking_instructions"] == "Keep all chapter prologues in separate chunks."
    assert "additional_chunking_instructions_fingerprint" not in document


def test_ai_chunking_ignores_invalid_boundaries_and_closes_last_chunk(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify invalid AI boundary ids do not corrupt output and the last chunk closes automatically.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
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
    write_cleanup_input(project_root, cleaned_path.read_text(encoding="utf-8"))
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
            "payload": {
                "chunks": [
                    {
                        "start_paragraph": 1,
                        "start_text": "wrong anchor",
                        "break_after_paragraph": 1,
                    }
                ]
            },
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
    chunks = json.loads((chunking_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert len(chunks) == 1
    assert "Paragraph one." in chunks[0]["text"]
    assert "Paragraph two." in chunks[0]["text"]


def test_ai_chunking_uses_absolute_numbers_and_preserves_cleanup_metadata(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify AI chunking sends absolute numbers while preserving cleanup provenance.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_system.txt").write_text("{strategy}", encoding="utf-8")
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)

    project_root, manifest = project_workspace_service.create_project("AiChunkingMetadataIds", tmp_path)
    cleaned_text = "Visible first.\n\nVisible second.\n"
    write_cleanup_input(
        project_root,
        cleaned_text,
        paragraphs=[
            {
                "paragraph_id": "paragraph-0042",
                "output_start": 0,
                "output_end": len(cleaned_text.rstrip("\n")),
                "role": "body",
                "confidence": "repaired",
                "reason_codes": ["page_transition_repaired"],
                "source_page_start": 1,
                "source_page_end": 2,
                "starts_after_page_transition": False,
                "crosses_page_transition": True,
                "source_unit_ids": ["u-000001", "u-000002"],
                "provenance_available": True,
            }
        ],
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
        """
        captured_prompt["text"] = user_prompt
        return {
            "payload": {
                "chunks": [
                    {
                        "start_paragraph": 1,
                        "start_text": "Visible first. Visible second.",
                        "break_after_paragraph": 1,
                    }
                ]
            },
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

    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert "Paragraph 1\n" in captured_prompt["text"]
    assert "paragraph-0042" not in captured_prompt["text"]
    assert chunks[0]["cleanup_joined_across_page_break"] is True


def test_ai_chunking_resumes_from_saved_window_checkpoint(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify REQ-FUNC-001 interrupted AI chunking resumes from the next unfinished window.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
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
    write_cleanup_input(project_root, cleaned_text)
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
            {
                "chunks": [
                    {
                        "start_paragraph": 1,
                        "start_text": "Paragraph 1.",
                        "break_after_paragraph": 20,
                    }
                ]
            },
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

    window_build_starts: list[int] = []
    original_window_builder = ai_chunking_service._build_windows_from_index  # noqa: SLF001

    def counting_window_builder(paragraph_records, start_index, budget_metadata):
        """Record each remaining-window rebuild before delegating to the real builder."""
        window_build_starts.append(start_index)
        return original_window_builder(paragraph_records, start_index, budget_metadata)

    monkeypatch.setattr(ai_chunking_service, "_build_windows_from_index", counting_window_builder)
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

    state_payload = read_chunking_document(project_root)
    assert state_payload["status"] == "cancelled"
    assert state_payload["next_paragraph"] == 21
    assert "progress_current" not in state_payload

    monkeypatch.setattr(
        ai_chunking_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {
                "chunks": [
                    {
                        "start_paragraph": 21,
                        "start_text": "Paragraph 21.",
                        "break_after_paragraph": 39,
                    }
                ]
            },
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
    completed_state = read_chunking_document(project_root)
    assert completed_state["status"] == "completed"
    assert completed_state["next_paragraph"] is None
    assert window_build_starts == [0, 20, 20, 40]


def test_ai_running_state_reuses_prebuilt_chunks(tmp_path) -> None:
    """
    @brief      Verify REQ-NFR-015 AI checkpoint state does not rebuild already prepared chunks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("AiChunkPrebuiltState", tmp_path)
    input_path = project_root / config.CLEANED_TEXT_FILE_NAME
    source_text = "Chapter I\n\nParagraph one.\n"
    input_path.write_text(source_text, encoding="utf-8")
    chunks = [
        {
            "chunk_id": "chunk-0001",
            "sequence_index": 1,
            "text": "Chapter I\n\nParagraph one.",
        }
    ]
    write_chunking_document(
        project_root,
        chunks,
        mode="ai_assisted",
        semantic_strategy="paragraph",
        source_text=source_text,
        status="running",
        next_paragraph=2,
    )

    state_payload = read_chunking_document(project_root)
    assert len(state_payload["chunks"]) == 1
    assert state_payload["next_paragraph"] == 2


def test_ai_chunking_rejects_checkpoint_with_unknown_fields(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify an incompatible AI Chunking document is rejected.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
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

    project_root, manifest = project_workspace_service.create_project("AiChunkingInvalidCheckpointProject", tmp_path)
    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_path.write_text("\n\n".join(f"Paragraph {index}." for index in range(1, 41)) + "\n", encoding="utf-8")
    write_cleanup_input(project_root, cleaned_path.read_text(encoding="utf-8"))
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
            {
                "chunks": [
                    {
                        "start_paragraph": 1,
                        "start_text": "Paragraph 1.",
                        "break_after_paragraph": 20,
                    }
                ]
            },
            operation_runtime_service.OperationCancelledError("stop"),
        ]
    )

    def _first_chat_json(*_args, **_kwargs):
        """
        @brief      Return one response and then cancel to create an interrupted checkpoint.
        @return     Fake provider payload with one chunking boundary.
        @exception  OperationCancelledError Raised by queued cancellation response.
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

    document_path = project_root / config.CHUNK_ARTIFACT_FILE_NAME
    state_payload = read_chunking_document(project_root)
    state_payload["unexpected_checkpoint_field"] = "paragraph-0020"
    document_path.write_text(json.dumps(state_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    captured_prompts: list[str] = []

    def _second_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Capture prompts for restart verification.
        @return     Fake provider payload with one chunking boundary.
        @exception  None
        """
        captured_prompts.append(user_prompt)
        return {
            "payload": {"chunks": []},
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
        }

    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _second_chat_json)

    with pytest.raises(ValueError, match="Reset Chunking"):
        ai_chunking_service.chunk_text(project_root, manifest, profile, "paragraph")

    assert not captured_prompts


def test_ai_chunking_continues_resume_when_budget_metadata_changes(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify resume continues from the next paragraph when the selected profile budget changes.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
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
    write_cleanup_input(project_root, cleaned_path.read_text(encoding="utf-8"))
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
            {
                "chunks": [
                    {
                        "start_paragraph": 1,
                        "start_text": "Paragraph 1.",
                        "break_after_paragraph": 20,
                    }
                ]
            },
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
        """
        captured_prompts.append(user_prompt)
        return {
            "payload": {
                "chunks": [
                    {
                        "start_paragraph": 21,
                        "start_text": "Paragraph 21.",
                        "break_after_paragraph": 39,
                    }
                ]
            },
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

    ai_chunking_service.chunk_text(project_root, manifest, second_profile, "paragraph")

    assert captured_prompts
    assert "Paragraph 1\n" not in captured_prompts[0]
    assert "Paragraph 21\n" in captured_prompts[0]
    completed_state = read_chunking_document(project_root)
    assert completed_state["status"] == "completed"
    assert completed_state["next_paragraph"] is None
    assert completed_state["token_usage"]["total_tokens"] == 24
    assert "ai_profile_id" not in completed_state
    assert "model_name" not in completed_state
    assert "budget_metadata" not in completed_state


# END OF FILE
