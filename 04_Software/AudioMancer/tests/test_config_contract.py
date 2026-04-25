#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_config_contract.py
@brief Focused contract tests for the AudioMancer configuration scaffold.
@details Verifies that the adapted configuration constants and persisted
         settings scaffold exist with the expected baseline contract.
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 0.8.8
"""

# IMPORTS

import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import settings_service

# PUBLIC API


def test_config_exposes_expected_identity_and_window_defaults() -> None:
    """
    @brief      Verify the adapted configuration exposes the expected identity and UI defaults.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.5
    """
    assert config.APP_NAME == "AudioMancer"
    assert config.PACKAGE_NAME == "audiomancer"
    assert config.DEFAULT_MAIN_WINDOW_WIDTH == 1040
    assert config.DEFAULT_MAIN_WINDOW_HEIGHT == 660
    assert config.DEFAULT_MAIN_WINDOW_MIN_WIDTH == 900
    assert config.DEFAULT_MAIN_WINDOW_MIN_HEIGHT == 560
    assert config.PROJECT_MANIFEST_FILE_NAME == "project.json"
    assert config.DEFAULT_WORKFLOW_STAGE == "project_created"
    assert "character_voices_ready" in config.PROJECT_WORKFLOW_STAGES
    assert "speech_blocks_ready" in config.PROJECT_WORKFLOW_STAGES
    assert "audio_blocks_ready" in config.PROJECT_WORKFLOW_STAGES
    assert "audio_assembly_ready" in config.PROJECT_WORKFLOW_STAGES
    assert config.CHARACTER_VOICES_TARGETS_FILE_NAME == "characters_voice.json"
    assert config.SUPPORTED_SOURCE_SUFFIXES[".epub"] == "epub"
    assert config.SUPPORTED_SOURCE_SUFFIXES[".docx"] == "docx"
    assert config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH == "."
    assert config.EXTRACTED_TEXT_FILE_NAME == "extracted_text.txt"
    assert config.EXTRACTION_REPORT_FILE_NAME == "extraction_report.json"
    assert config.EXTRACTION_STATE_FILE_NAME == "extraction_state.json"
    assert config.CLEANED_TEXT_FILE_NAME == "clean_text.txt"
    assert config.CLEANUP_STATE_FILE_NAME == "cleanup_state.json"
    assert config.CHUNK_ARTIFACT_FILE_NAME == "chunks_text.json"
    assert config.CHUNKING_REPORT_FILE_NAME == "chunking_report.json"
    assert config.CHUNKING_STATE_FILE_NAME == "chunking_state.json"
    assert config.TRANSLATED_CHUNKS_FILE_NAME == "translated_text.json"
    assert config.TRANSLATION_STATE_FILE_NAME == "translation_state.json"
    assert config.NARRATOR_PROFILE_FILE_NAME == "audio_profiles.json"
    assert config.NARRATOR_SELECTION_FILE_NAME == "narator.json"
    assert config.SELECTED_NARRATOR_AUDIO_FILE_NAME == "narator.wav"
    assert config.SELECTED_NARRATOR_METADATA_FILE_NAME == "narator_sample.json"
    assert config.SPEECH_BLOCKS_OUTPUT_FILE_NAME == "speech_blocks.json"
    assert config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME == "audio_blocks"
    assert config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT == 512
    assert "ai_chunking" in config.AVAILABLE_LOG_COMPONENTS
    assert "text_extraction" in config.AVAILABLE_LOG_COMPONENTS


def test_settings_json_scaffold_matches_service_defaults() -> None:
    """
    @brief      Verify the persisted settings scaffold is service-readable.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.2
    """
    settings_path = config.APP_SETTINGS_PATH
    payload = json.loads(Path(settings_path).read_text(encoding="utf-8"))
    loaded_payload = settings_service.load_settings()

    assert isinstance(payload, dict)
    assert isinstance(loaded_payload, dict)
    assert payload == loaded_payload
    assert settings_path == config.APP_SETTINGS_PATH


def test_config_translation_languages_include_qwen3_tts_languages_without_chinese() -> None:
    """
    @brief      Verify shared language options include Qwen3 TTS languages, Romanian, and no Chinese entry.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    language_codes = [language_code for language_code, _label in config.TRANSLATION_LANGUAGE_OPTIONS]

    assert language_codes == ["en", "ro", "ja", "ko", "de", "fr", "ru", "pt", "es", "it"]
    assert "zh" not in language_codes


# END OF FILE
