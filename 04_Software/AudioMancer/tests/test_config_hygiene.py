#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_config_hygiene.py
@brief Configuration hygiene tests for committed AudioMancer settings.
@details Verifies repository settings remain example-only and do not carry
         operator secrets.
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.1.0
"""

# IMPORTS

import json
from pathlib import Path

# CONSTANTS

# @brief Application subtree root used for committed configuration checks.
_APP_ROOT = Path(__file__).resolve().parents[1]


# PUBLIC API


def test_committed_settings_file_contains_only_blank_secret_fields() -> None:
    """
    @brief      Verify committed settings carry no operator-provided secret values.
    @return     None.
    @exception  AssertionError Raised when a settings secret field is populated.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    settings_path = _APP_ROOT / "settings.json"
    settings_payload = json.loads(settings_path.read_text(encoding="utf-8"))

    for profile in settings_payload.get("llm_profiles", []):
        assert profile.get("api_key", "") == ""
    assert settings_payload.get("tts_runtime_api_key", "") == ""


def test_committed_settings_file_does_not_match_common_secret_tokens() -> None:
    """
    @brief      Verify committed settings text does not include common bearer-key tokens.
    @return     None.
    @exception  AssertionError Raised when one blocked secret pattern is present.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    settings_text = (_APP_ROOT / "settings.json").read_text(encoding="utf-8")

    blocked_tokens = ("sk-", "sk-proj-", "Bearer ", "OPENAI_API_KEY")
    for blocked_token in blocked_tokens:
        assert blocked_token not in settings_text


# END OF FILE
