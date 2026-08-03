#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file conftest.py
@brief Global test fixtures for the AudioMancer test suite.
@details Provides shared configurations, mock profiles, and environment
         setup to reduce boilerplate across test files.
"""

# IMPORTS

from pathlib import Path

import pytest

from audiomancer import config
from audiomancer.services import project_workspace_service

# CONSTANTS

# @brief Filename fragments that identify UI-facing test modules.
_UI_TEST_FILE_TOKENS = (
    "_page.py",
    "_ui_controller.py",
    "app_entrypoint",
    "main_window",
    "operation_runner_controller",
    "ui_state",
)


def pytest_collection_modifyitems(config, items) -> None:
    """
    @brief      Add service/ui tier markers to collected tests.
    @param[in]  config Pytest configuration object.
    @param[in]  items Collected pytest items.
    @return     None.
    @exception  None
    """
    _ = config
    for item in items:
        marker_name = "ui" if _is_ui_test_item(item) else "service"
        item.add_marker(getattr(pytest.mark, marker_name))


def _is_ui_test_item(item) -> bool:
    """
    @brief      Determine whether one collected test belongs to the UI tier.
    @param[in]  item Collected pytest item.
    @return     True when the item uses Qt fixtures or a UI-facing test module.
    @exception  None
    """
    if "qtbot" in getattr(item, "fixturenames", ()):
        return True
    file_name = Path(str(item.fspath)).name
    return any(token in file_name for token in _UI_TEST_FILE_TOKENS)


@pytest.fixture
def mock_prompt_environment(tmp_path, monkeypatch):
    """
    @brief      Set up a fake prompts directory filled with minimal system/user templates.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     Path to the temporary prompt root.
    @exception  None
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir(exist_ok=True)

    # Generic stubs for tests verifying AI call generation
    (prompt_root / "text_cleanup_adjudication_primary_system.txt").write_text(
        "Primary classifier.",
        encoding="utf-8",
    )
    (prompt_root / "text_cleanup_adjudication_verifier_system.txt").write_text(
        "Independent verifier.",
        encoding="utf-8",
    )
    (prompt_root / "text_chunking_system.txt").write_text("Chunk system prompt.", encoding="utf-8")
    (prompt_root / "text_chunking_user.txt").write_text("{units_block}", encoding="utf-8")
    (prompt_root / "speech_blocks_system.txt").write_text("Speech blocks system prompt.", encoding="utf-8")
    (prompt_root / "speech_blocks_user.txt").write_text(
        "{source_language}\n{chunk_id}\n{chunk_text}\n{speaker_catalog_json}",
        encoding="utf-8",
    )

    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)
    return prompt_root


@pytest.fixture
def default_settings_payload():
    """
    @brief      Return a valid baseline application settings dictionary.
    @return     Dictionary containing global profile identifiers and UI preferences.
    @exception  None
    """
    return {
        "language": "en",
        "ui_theme_id": config.DEFAULT_UI_THEME_ID,
        "ui_themes": [],
        "play_completion_beep": False,
        "llm_profiles": [
            {
                "id": "profile_1",
                "label": "Stored Profile",
                "backend_kind": "lmstudio",
                "base_url": "http://127.0.0.1:1234/v1",
                "api_key": "",
                "model_name": "qwen3-8b",
                "context_window": 8192,
                "max_output_tokens": 1024,
                "request_timeout_seconds": 90,
                "temperature": 0.2,
                "supports_structured_output": False,
                "enabled": True,
            }
        ],
        "default_ai_cleanup_profile_id": "profile_1",
        "default_ai_chunking_profile_id": "profile_1",
        "default_ai_translation_profile_id": "profile_1",
        "default_narrator_profile_generation_profile_id": "profile_1",
        "default_speech_blocks_profile_id": "profile_1",
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": "profile_1",
        "tts_runtime_base_url": "http://127.0.0.1:8059",
        "tts_runtime_api_key": "",
        "tts_runtime_probe_succeeded": False,
        "tts_runtime_probe_message": "",
        "tts_runtime_discovered_models": [],
        "tts_runtime_active_model_id": None,
        "tts_runtime_device_diagnostics": {},
        "tts_audio_preview_timeout_seconds": 60,
        "tts_preview_text_character_limit": config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT,
        "tts_audio_generation_timeout_seconds": 300,
    }


@pytest.fixture
def mock_clean_project(tmp_path):
    """
    @brief      Generate a mocked, unmodified clean project root and manifest.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     Tuple of (project_root_path, manifest_dict).
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("MockProject", tmp_path)
    return project_root, manifest


@pytest.fixture
def mock_extracted_project(mock_clean_project):
    """
    @brief      Generate a mocked project that has finished text extraction.
    @details    Creates 'story.txt' in the extraction folder and updates the manifest.
    @param[in]  mock_clean_project Fixture yielding root and manifest.
    @return     Tuple of (project_root_path, manifest_dict).
    @exception  None
    """
    project_root, manifest = mock_clean_project

    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.parent.mkdir(parents=True, exist_ok=True)

    # Put a dummy payload, tests can overwrite if they need to
    extracted_path.write_text("Dummy Source Text\n", encoding="utf-8")

    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 10,
    }
    project_workspace_service.save_manifest(manifest, project_root)

    return project_root, manifest


# END OF FILE
