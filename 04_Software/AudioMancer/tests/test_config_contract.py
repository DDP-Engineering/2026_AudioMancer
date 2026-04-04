#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
@date 2026-04-04
@version 0.1.0
"""

# IMPORTS

import json
from pathlib import Path

from audiomancer import config

# PUBLIC API


def test_config_exposes_expected_identity_and_window_defaults() -> None:
    """
    @brief      Verify the adapted configuration exposes the expected identity and UI defaults.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    assert config.APP_NAME == "AudioMancer"
    assert config.PACKAGE_NAME == "audiomancer"
    assert config.DEFAULT_MAIN_WINDOW_WIDTH == 1100
    assert config.DEFAULT_MAIN_WINDOW_HEIGHT == 700
    assert config.DEFAULT_MAIN_WINDOW_MIN_WIDTH == 960
    assert config.DEFAULT_MAIN_WINDOW_MIN_HEIGHT == 620


def test_settings_json_scaffold_contains_expected_keys() -> None:
    """
    @brief      Verify the persisted settings scaffold contains the expected adapted keys and defaults.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.1
    """
    settings_path = config.APP_SETTINGS_PATH
    payload = json.loads(Path(settings_path).read_text(encoding="utf-8"))

    assert payload["language"] == config.DEFAULT_LANGUAGE
    assert payload["ui_text_scale"] == config.DEFAULT_UI_TEXT_SCALE
    assert payload["default_ai_chunking_strategy"] == "scene"
    assert payload["default_analysis_provider"] == "local_analysis_placeholder"
    assert len(payload["llm_profiles"]) == 3
    assert payload["default_ai_cleanup_profile_id"] == "llm-profile-d02b1cea-6028-4048-9662-9d11a67c47a6"


# END OF FILE