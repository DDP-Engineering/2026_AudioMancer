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
@version 0.1.1
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
    @date       2026-04-04
    @version    0.1.0
    """
    assert config.APP_NAME == "AudioMancer"
    assert config.PACKAGE_NAME == "audiomancer"
    assert config.DEFAULT_MAIN_WINDOW_WIDTH == 1100
    assert config.DEFAULT_MAIN_WINDOW_HEIGHT == 700
    assert config.DEFAULT_MAIN_WINDOW_MIN_WIDTH == 960
    assert config.DEFAULT_MAIN_WINDOW_MIN_HEIGHT == 620


def test_settings_json_scaffold_matches_service_defaults() -> None:
    """
    @brief      Verify the persisted settings scaffold matches code-owned service defaults.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.2
    """
    settings_path = config.APP_SETTINGS_PATH
    payload = json.loads(Path(settings_path).read_text(encoding="utf-8"))

    assert payload == settings_service.build_default_settings()
    assert settings_path == config.APP_SETTINGS_PATH


# END OF FILE
