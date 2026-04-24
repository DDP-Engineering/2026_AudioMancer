#!/usr/bin/env python3
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
@version 0.2.0
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import ai_chunking_service, operation_runtime_service, project_workspace_service


def test_ai_chunking_windows_use_configured_strategy_sizes(monkeypatch) -> None:
    """
    @brief      Verify AI chunking window sizes are read from shared configuration.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    paragraph_records = [{"unit_id": f"paragraph-{index:04d}"} for index in range(1, 6)]
    monkeypatch.setattr(
        config,
        "AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY",
        {
            "paragraph": 3,
            "meaning": 2,
            "scene": 4,
        },
    )

    windows = ai_chunking_service._build_windows(paragraph_records, "meaning")

    assert windows == [
        {"start_index": 0, "end_index": 1},
        {"start_index": 2, "end_index": 3},
        {"start_index": 4, "end_index": 4},
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
    cleaned_path = project_root / config.CLEANUP_FOLDER_NAME / config.CLEANED_TEXT_FILE_NAME
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
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"
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

    chunking_root = (
        project_root / config.CHUNK_FOLDER_NAME
        if hasattr(config, "CHUNK_FOLDER_NAME")
        else project_root / "20_chunking"
    )
    assert (chunking_root / f"{config.OPERATION_INPUT_FILE_PREFIX}story.txt").is_file()
    assert (chunking_root / config.CHUNK_ARTIFACT_FILE_NAME).is_file()
    assert (chunking_root / config.CHUNKING_REPORT_FILE_NAME).is_file()
    assert (chunking_root / config.OPERATION_STATE_FILE_NAME).is_file()
    assert any(path.name.startswith(config.AI_TRANSACTION_LOG_FILE_PREFIX) for path in chunking_root.glob("*.log"))
    assert report_payload["chunking_mode"] == "ai_assisted"
    assert report_payload["semantic_strategy"] == "meaning"
    chunks = json.loads((chunking_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))
    assert len(chunks) == 2
    assert chunks[0]["chunking_mode"] == "ai_assisted"
    assert chunks[0]["semantic_strategy"] == "meaning"
    assert chunks[0]["source_start_line"] == 1
    assert chunks[0]["source_end_line"] == 3
    assert "CHAPTER I" in chunks[0]["text"]


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
    cleaned_path = project_root / config.CLEANUP_FOLDER_NAME / config.CLEANED_TEXT_FILE_NAME
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
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"
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

    chunking_root = project_root / "20_chunking"
    chunks = json.loads((chunking_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))
    assert len(chunks) == 1
    assert "Paragraph one." in chunks[0]["text"]
    assert "Paragraph two." in chunks[0]["text"]


def test_ai_chunking_resumes_from_saved_window_checkpoint(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify interrupted AI chunking resumes from the next unfinished window.
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

    project_root, manifest = project_workspace_service.create_project("AiChunkingResumeProject", tmp_path)
    cleaned_path = project_root / config.CLEANUP_FOLDER_NAME / config.CLEANED_TEXT_FILE_NAME
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_text = "\n\n".join(f"Paragraph {index}." for index in range(1, 21)) + "\n"
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
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"
    ]

    responses = iter(
        [
            {"break_after_unit_ids": ["paragraph-0002"]},
            operation_runtime_service.OperationCancelledError("stop"),
        ]
    )

    def _chat_json(*_args, **_kwargs):
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

    state_payload = json.loads(
        (project_root / "20_chunking" / config.OPERATION_STATE_FILE_NAME).read_text(encoding="utf-8")
    )
    assert state_payload["status"] == "running"
    assert state_payload["progress_current"] == 1

    monkeypatch.setattr(
        ai_chunking_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {"break_after_unit_ids": ["paragraph-0019"]},
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
    completed_state = json.loads(
        (project_root / "20_chunking" / config.OPERATION_STATE_FILE_NAME).read_text(encoding="utf-8")
    )
    assert completed_state["status"] == "completed"
    assert completed_state["progress_current"] == 2


# END OF FILE
