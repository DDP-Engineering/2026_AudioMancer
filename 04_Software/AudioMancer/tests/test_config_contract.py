#!/usr/bin/env python3
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
@date 2026-04-07
@version 0.8.2
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
    @version    0.2.0
    """
    assert config.APP_NAME == "AudioMancer"
    assert config.PACKAGE_NAME == "audiomancer"
    assert config.DEFAULT_MAIN_WINDOW_WIDTH == 1100
    assert config.DEFAULT_MAIN_WINDOW_HEIGHT == 700
    assert config.DEFAULT_MAIN_WINDOW_MIN_WIDTH == 960
    assert config.DEFAULT_MAIN_WINDOW_MIN_HEIGHT == 620
    assert config.PROJECT_MANIFEST_FILE_NAME == "project.json"
    assert "50_narrator_definition" in config.PROJECT_REQUIRED_SUBDIRECTORIES
    assert config.DEFAULT_WORKFLOW_STAGE == "project_created"
    assert config.SUPPORTED_SOURCE_SUFFIXES[".epub"] == "epub"
    assert config.SUPPORTED_SOURCE_SUFFIXES[".docx"] == "docx"
    assert config.EXTRACTION_FOLDER_NAME == "00_extraction"
    assert config.EXTRACTED_TEXT_FILE_NAME == "output_raw_text.txt"
    assert config.EXTRACTION_REPORT_FILE_NAME == "extraction_report.json"
    assert config.CHUNK_ARTIFACT_FILE_NAME == "output_chunks.json"
    assert config.CHUNKING_REPORT_FILE_NAME == "chunking_report.json"
    assert config.OPERATION_STATE_FILE_NAME == "state_operation.json"
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


# END OF FILE
