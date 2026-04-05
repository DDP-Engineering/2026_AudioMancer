#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_settings_service.py
@brief Focused tests for the AudioMancer settings service.
@details Verifies default settings generation, automatic file creation,
         persisted settings self-healing, and validated save behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-04
@version 0.1.3
"""

# IMPORTS

import copy
import json

from audiomancer import config
from audiomancer.services import settings_service


# PUBLIC API


def test_build_default_settings_matches_committed_settings_scaffold() -> None:
    """
    @brief      Verify code-owned defaults match the committed settings scaffold.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.2
    """
    committed_settings = json.loads(config.APP_SETTINGS_PATH.read_text(encoding="utf-8"))
    assert settings_service.build_default_settings() == committed_settings


def test_load_settings_creates_default_file_when_missing(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify missing settings create and return the default file.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.2
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)

    loaded_settings = settings_service.load_settings()

    assert settings_path.exists()
    assert loaded_settings == settings_service.build_default_settings()
    assert json.loads(settings_path.read_text(encoding="utf-8")) == loaded_settings


def test_load_settings_self_heals_missing_and_invalid_values(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify invalid persisted settings are healed and rewritten.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)

    invalid_settings = settings_service.build_default_settings()
    invalid_settings["language"] = "fr"
    invalid_settings["ui_text_scale"] = "gigantic"
    invalid_settings["default_ai_chunking_strategy"] = "invalid"
    invalid_settings["play_completion_beep"] = "no"
    settings_path.write_text(json.dumps(invalid_settings, indent=2), encoding="utf-8")

    loaded_settings = settings_service.load_settings()
    defaults = settings_service.build_default_settings()

    assert loaded_settings["language"] == defaults["language"]
    assert loaded_settings["ui_text_scale"] == defaults["ui_text_scale"]
    assert loaded_settings["default_ai_chunking_strategy"] == defaults["default_ai_chunking_strategy"]
    assert loaded_settings["play_completion_beep"] == defaults["play_completion_beep"]
    assert loaded_settings["llm_profiles"] == defaults["llm_profiles"]
    assert json.loads(settings_path.read_text(encoding="utf-8")) == loaded_settings
    assert "default_ai_cleanup_profile_id" not in loaded_settings
    assert "default_ai_chunking_profile_id" not in loaded_settings


def test_validate_settings_heals_invalid_llm_profiles_but_keeps_non_empty_list() -> None:
    """
    @brief      Verify invalid LLM profile fields are healed when profiles exist.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.1
    """
    candidate_settings = settings_service.build_default_settings()
    candidate_settings["llm_profiles"] = [
        {
            "id": "profile-1",
            "label": "bad profile",
            "backend_kind": "bad-backend",
            "base_url": "",
            "api_key": "",
            "model_name": "",
            "context_window": "bad",
            "max_output_tokens": -1,
            "request_timeout_seconds": 0,
            "temperature": "bad",
            "supports_structured_output": "bad",
            "enabled": "bad",
            "discovered_model_name": "",
            "discovered_context_window": "bad",
            "discovery_succeeded": "bad",
            "discovery_message": 1,
            "user_overrode_model_name": "bad",
            "user_overrode_context_window": "bad",
        }
    ]
    validated_settings = settings_service.validate_settings(candidate_settings)

    assert len(validated_settings["llm_profiles"]) == 1
    assert validated_settings["llm_profiles"][0]["id"] == "profile-1"
    assert validated_settings["llm_profiles"][0]["backend_kind"] == config.LLM_BACKEND_OPTIONS[0]
    assert validated_settings["llm_profiles"][0]["context_window"] == config.DEFAULT_LLM_CONTEXT_WINDOW
    assert validated_settings["llm_profiles"][0]["max_output_tokens"] == config.DEFAULT_LLM_MAX_OUTPUT_TOKENS
    assert validated_settings["llm_profiles"][0]["request_timeout_seconds"] == config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS
    assert validated_settings["llm_profiles"][0]["temperature"] == config.DEFAULT_LLM_TEMPERATURE
    assert "default_ai_cleanup_profile_id" not in validated_settings
    assert "default_ai_chunking_profile_id" not in validated_settings


def test_validate_settings_preserves_unknown_extra_keys() -> None:
    """
    @brief      Verify validation keeps unknown extra keys in the payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    candidate_settings = settings_service.build_default_settings()
    candidate_settings["future_key"] = {"enabled": True}

    validated_settings = settings_service.validate_settings(candidate_settings)

    assert validated_settings["future_key"] == {"enabled": True}


def test_save_settings_writes_validated_payload_to_disk(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify save_settings validates and persists the payload.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)

    candidate_settings = settings_service.build_default_settings()
    candidate_settings["language"] = "fr"

    settings_service.save_settings(candidate_settings)

    persisted_settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert persisted_settings["language"] == settings_service.build_default_settings()["language"]


def test_validate_settings_keeps_valid_persisted_payload_unchanged() -> None:
    """
    @brief      Verify a valid settings payload remains unchanged after validation.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    candidate_settings = settings_service.build_default_settings()

    assert settings_service.validate_settings(copy.deepcopy(candidate_settings)) == candidate_settings


# END OF FILE
