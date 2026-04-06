#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_cleanup_service.py
@brief Focused tests for the AudioMancer AI cleanup service.
@details Verifies AI-assisted cleanup writes the expected cleanup artifacts,
         persists resumable state, and creates one AI transaction log file.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.1.3
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import ai_cleanup_service
from audiomancer.services import project_workspace_service


def test_ai_cleanup_writes_cleanup_artifacts_and_log(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify AI-assisted cleanup writes output, report, state, and AI log artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_cleanup_system.txt").write_text("System prompt.", encoding="utf-8")
    (prompt_root / "text_cleanup_user.txt").write_text("{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)

    project_root, manifest = project_workspace_service.create_project("AiCleanupProject", tmp_path)
    extracted_path = project_root / config.EXTRACTION_FOLDER_NAME / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.parent.mkdir(parents=True, exist_ok=True)
    extracted_path.write_text(
        "CHAPTER I\n\nStory paragraph one.\n\n***\n\nStory paragraph two.\n",
        encoding="utf-8",
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["extracted_text_relative_path"] = f"{config.EXTRACTION_FOLDER_NAME}/{config.EXTRACTED_TEXT_FILE_NAME}"

    responses = iter([
        {
            "results": [
                {"unit_id": "unit-0001", "label": "story"},
                {"unit_id": "unit-0002", "label": "story"},
                {"unit_id": "unit-0003", "label": "separator"},
                {"unit_id": "unit-0004", "label": "story"},
            ]
        }
    ])
    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: next(responses),
    )

    report_payload = ai_cleanup_service.clean_text(
        project_root,
        manifest,
        {
            "id": "profile_1",
            "label": "Cleanup Profile",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": 4096,
            "max_output_tokens": 512,
            "request_timeout_seconds": 30,
            "temperature": 0.2,
        },
    )

    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
    assert (cleanup_root / f"{config.OPERATION_INPUT_FILE_PREFIX}story.txt").is_file()
    assert (cleanup_root / config.CLEANED_TEXT_FILE_NAME).is_file()
    assert (cleanup_root / config.CLEANUP_REPORT_FILE_NAME).is_file()
    assert (cleanup_root / config.OPERATION_STATE_FILE_NAME).is_file()
    assert report_payload["cleanup_mode"] == "ai_assisted"
    assert report_payload["ai_profile_id"] == "profile_1"
    assert "Story paragraph one." in (cleanup_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert any(path.name.startswith(config.AI_TRANSACTION_LOG_FILE_PREFIX) for path in cleanup_root.glob("*.log"))
    state_payload = json.loads((cleanup_root / config.OPERATION_STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert state_payload["mode"] == "ai_assisted"
    assert state_payload["status"] == "completed"


def test_ai_cleanup_heals_soft_line_breaks_inside_one_phrase(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify AI-assisted cleanup joins soft line breaks inside one continuing sentence.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_cleanup_system.txt").write_text("System prompt.", encoding="utf-8")
    (prompt_root / "text_cleanup_user.txt").write_text("{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)

    project_root, manifest = project_workspace_service.create_project("AiCleanupSoftBreaksProject", tmp_path)
    extracted_path = project_root / config.EXTRACTION_FOLDER_NAME / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.parent.mkdir(parents=True, exist_ok=True)
    extracted_path.write_text(
        "Ottmar Drenthe was watching reviews of his latest project and fuming at\n"
        "the idiocy of the\n"
        "Dominion's reviewing elites.\n",
        encoding="utf-8",
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["extracted_text_relative_path"] = f"{config.EXTRACTION_FOLDER_NAME}/{config.EXTRACTED_TEXT_FILE_NAME}"

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "results": [
                {"unit_id": "unit-0001", "label": "story"},
            ]
        },
    )

    ai_cleanup_service.clean_text(
        project_root,
        manifest,
        {
            "id": "profile_1",
            "label": "Cleanup Profile",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": 4096,
            "max_output_tokens": 512,
            "request_timeout_seconds": 30,
            "temperature": 0.2,
        },
    )

    cleaned_text = (
        project_root / config.CLEANUP_FOLDER_NAME / config.CLEANED_TEXT_FILE_NAME
    ).read_text(encoding="utf-8")
    assert "idiocy of the Dominion's reviewing elites." in cleaned_text
    assert "idiocy of the\nDominion's reviewing elites." not in cleaned_text


def test_ai_cleanup_joins_unfinished_line_before_proper_name(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify AI-assisted cleanup joins unfinished wrapped lines before one capitalized continuation.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_cleanup_system.txt").write_text("System prompt.", encoding="utf-8")
    (prompt_root / "text_cleanup_user.txt").write_text("{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)

    project_root, manifest = project_workspace_service.create_project("AiCleanupProperNameProject", tmp_path)
    extracted_path = project_root / config.EXTRACTION_FOLDER_NAME / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.parent.mkdir(parents=True, exist_ok=True)
    extracted_path.write_text(
        '"This is below\n'
        'Drenthe."\n',
        encoding="utf-8",
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["extracted_text_relative_path"] = f"{config.EXTRACTION_FOLDER_NAME}/{config.EXTRACTED_TEXT_FILE_NAME}"

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "results": [
                {"unit_id": "unit-0001", "label": "story"},
            ]
        },
    )

    ai_cleanup_service.clean_text(
        project_root,
        manifest,
        {
            "id": "profile_1",
            "label": "Cleanup Profile",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": 4096,
            "max_output_tokens": 512,
            "request_timeout_seconds": 30,
            "temperature": 0.2,
        },
    )

    cleaned_text = (
        project_root / config.CLEANUP_FOLDER_NAME / config.CLEANED_TEXT_FILE_NAME
    ).read_text(encoding="utf-8")
    assert '"This is below Drenthe."' in cleaned_text
    assert '"This is below\nDrenthe."' not in cleaned_text


def test_ai_cleanup_merges_page_split_continuation_paragraphs(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify AI-assisted cleanup merges adjacent kept paragraphs when a page split interrupts one sentence.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_cleanup_system.txt").write_text("System prompt.", encoding="utf-8")
    (prompt_root / "text_cleanup_user.txt").write_text("{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)

    project_root, manifest = project_workspace_service.create_project("AiCleanupPageSplitProject", tmp_path)
    extracted_path = project_root / config.EXTRACTION_FOLDER_NAME / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.parent.mkdir(parents=True, exist_ok=True)
    extracted_path.write_text(
        "Drenthe will shoot this industrial if\n\n"
        "3\n\n"
        "you swear that Heroes of the Periphery will then be the next project.\n",
        encoding="utf-8",
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["extracted_text_relative_path"] = f"{config.EXTRACTION_FOLDER_NAME}/{config.EXTRACTED_TEXT_FILE_NAME}"

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "results": [
                {"unit_id": "unit-0001", "label": "story"},
                {"unit_id": "unit-0002", "label": "page_number"},
                {"unit_id": "unit-0003", "label": "story"},
            ]
        },
    )

    ai_cleanup_service.clean_text(
        project_root,
        manifest,
        {
            "id": "profile_1",
            "label": "Cleanup Profile",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": 4096,
            "max_output_tokens": 512,
            "request_timeout_seconds": 30,
            "temperature": 0.2,
        },
    )

    cleaned_text = (
        project_root / config.CLEANUP_FOLDER_NAME / config.CLEANED_TEXT_FILE_NAME
    ).read_text(encoding="utf-8")
    assert (
        "Drenthe will shoot this industrial if you swear that Heroes of the Periphery"
        in cleaned_text
    )
    assert "industrial if\n\nyou swear" not in cleaned_text


# END OF FILE
