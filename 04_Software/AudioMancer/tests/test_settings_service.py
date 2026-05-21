#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
@date 2026-04-22
@version 0.7.0
"""

# IMPORTS

import copy
import json
import logging

from audiomancer import config
from audiomancer.services import settings_service, ui_theme_service

# PUBLIC API


def test_committed_settings_scaffold_matches_valid_settings_schema() -> None:
    """
    @brief      Verify the committed settings scaffold matches the valid schema.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.3.0
    """
    committed_settings = json.loads(config.APP_SETTINGS_PATH.read_text(encoding="utf-8"))
    validated_settings = settings_service.validate_settings(copy.deepcopy(committed_settings))

    assert validated_settings == committed_settings


def test_build_default_settings_includes_theme_fields() -> None:
    """
    @brief      Verify default settings include theme persistence fields.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.2.0
    """
    default_settings = settings_service.build_default_settings()

    assert "ui_text_scale" not in default_settings
    assert default_settings["ui_theme_id"] == config.DEFAULT_UI_THEME_ID
    assert default_settings["ui_themes"] == []


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
    invalid_settings["ui_theme_id"] = "missing_theme"
    invalid_settings["ui_themes"] = [
        {
            "schema_version": config.UI_THEME_SCHEMA_VERSION,
            "theme_id": "invalid_theme",
            "display_name": "Invalid Theme",
            "built_in": False,
            "font": {},
            "colors": {"accent": "blue"},
        }
    ]
    invalid_settings["default_ai_cleanup_profile_id"] = "missing_profile"
    invalid_settings["default_ai_chunking_profile_id"] = "missing_profile"
    invalid_settings["default_ai_translation_profile_id"] = "missing_profile"
    invalid_settings["default_narrator_profile_generation_profile_id"] = "missing_profile"
    invalid_settings["default_speech_blocks_profile_id"] = "missing_profile"
    invalid_settings["default_character_extraction_profile_id"] = "missing_profile"
    invalid_settings["play_completion_beep"] = "no"
    settings_path.write_text(json.dumps(invalid_settings, indent=2), encoding="utf-8")

    loaded_settings = settings_service.load_settings()
    defaults = settings_service.build_default_settings()

    assert loaded_settings["language"] == defaults["language"]
    assert "ui_text_scale" not in loaded_settings
    assert loaded_settings["ui_theme_id"] == defaults["ui_theme_id"]
    assert loaded_settings["ui_themes"] == defaults["ui_themes"]
    assert loaded_settings["default_ai_cleanup_profile_id"] == defaults["default_ai_cleanup_profile_id"]
    assert loaded_settings["default_ai_chunking_profile_id"] == defaults["default_ai_chunking_profile_id"]
    assert loaded_settings["default_ai_translation_profile_id"] == defaults["default_ai_translation_profile_id"]
    assert (
        loaded_settings["default_narrator_profile_generation_profile_id"]
        == defaults["default_narrator_profile_generation_profile_id"]
    )
    assert loaded_settings["default_speech_blocks_profile_id"] == defaults["default_speech_blocks_profile_id"]
    assert loaded_settings["default_ai_chunking_strategy"] == defaults["default_ai_chunking_strategy"]
    assert (
        loaded_settings["default_character_extraction_profile_id"]
        == defaults["default_character_extraction_profile_id"]
    )
    assert loaded_settings["play_completion_beep"] == defaults["play_completion_beep"]
    assert loaded_settings["llm_profiles"] == defaults["llm_profiles"]
    assert json.loads(settings_path.read_text(encoding="utf-8")) == loaded_settings


def test_load_settings_migrates_missing_theme_fields_and_removes_legacy_text_scale(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify old settings gain theme fields while removing legacy ui_text_scale.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.2.0
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)

    old_settings = settings_service.build_default_settings()
    old_settings["ui_text_scale"] = "large"
    old_settings.pop("ui_theme_id")
    old_settings.pop("ui_themes")
    settings_path.write_text(json.dumps(old_settings, indent=2), encoding="utf-8")

    loaded_settings = settings_service.load_settings()

    assert "ui_text_scale" not in loaded_settings
    assert loaded_settings["ui_theme_id"] == config.DEFAULT_UI_THEME_ID
    assert loaded_settings["ui_themes"] == []
    assert json.loads(settings_path.read_text(encoding="utf-8")) == loaded_settings


def test_validate_settings_keeps_valid_selected_custom_theme() -> None:
    """
    @brief      Verify a valid custom theme and selected custom id survive validation.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    candidate_settings = settings_service.build_default_settings()
    custom_theme = ui_theme_service.import_theme_payload(
        {
            "schema_version": config.UI_THEME_SCHEMA_VERSION,
            "theme_id": "reading_theme",
            "display_name": "Reading Theme",
            "built_in": True,
            "font": {"family": "", "point_size": None, "scale": "large"},
            "colors": {"accent": "#123ABC"},
        },
        [],
    )
    candidate_settings["ui_theme_id"] = "reading_theme"
    candidate_settings["ui_themes"] = [custom_theme]

    validated_settings = settings_service.validate_settings(candidate_settings)

    assert validated_settings["ui_theme_id"] == "reading_theme"
    assert validated_settings["ui_themes"] == [custom_theme]
    assert "ui_text_scale" not in validated_settings


def test_validate_settings_repairs_invalid_selected_theme_id_to_default() -> None:
    """
    @brief      Verify missing selected theme ids are repaired to the default theme.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    candidate_settings = settings_service.build_default_settings()
    candidate_settings["ui_theme_id"] = "missing_theme"

    validated_settings = settings_service.validate_settings(candidate_settings)

    assert validated_settings["ui_theme_id"] == config.DEFAULT_UI_THEME_ID


def test_validate_settings_drops_invalid_custom_themes() -> None:
    """
    @brief      Verify invalid custom theme payloads are removed from settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    candidate_settings = settings_service.build_default_settings()
    candidate_settings["ui_themes"] = [
        {
            "schema_version": config.UI_THEME_SCHEMA_VERSION,
            "theme_id": "bad_theme",
            "display_name": "Bad Theme",
            "built_in": False,
            "font": {},
            "colors": {"accent": "#12345"},
        }
    ]

    validated_settings = settings_service.validate_settings(candidate_settings)

    assert validated_settings["ui_themes"] == []


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
    assert (
        validated_settings["llm_profiles"][0]["request_timeout_seconds"] == config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS
    )
    assert validated_settings["llm_profiles"][0]["temperature"] == config.DEFAULT_LLM_TEMPERATURE
    assert validated_settings["default_ai_cleanup_profile_id"] is None
    assert validated_settings["default_ai_chunking_profile_id"] is None


def test_validate_settings_keeps_valid_enabled_default_profile_ids() -> None:
    """
    @brief      Verify valid enabled AI default-profile ids are preserved.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    candidate_settings = settings_service.build_default_settings()
    candidate_settings["llm_profiles"] = [
        {
            "id": "profile_1",
            "label": "Profile 1",
            "backend_kind": config.LLM_BACKEND_OPTIONS[0],
            "base_url": "http://127.0.0.1:1234/v1",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": config.DEFAULT_LLM_CONTEXT_WINDOW,
            "max_output_tokens": config.DEFAULT_LLM_MAX_OUTPUT_TOKENS,
            "request_timeout_seconds": config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
            "temperature": config.DEFAULT_LLM_TEMPERATURE,
            "supports_structured_output": False,
            "enabled": True,
            "discovered_model_name": "",
            "discovered_context_window": None,
            "discovery_succeeded": False,
            "discovery_message": "",
            "user_overrode_model_name": False,
            "user_overrode_context_window": False,
        }
    ]
    candidate_settings["default_ai_cleanup_profile_id"] = "profile_1"
    candidate_settings["default_ai_chunking_profile_id"] = "profile_1"
    candidate_settings["default_ai_translation_profile_id"] = "profile_1"
    candidate_settings["default_narrator_profile_generation_profile_id"] = "profile_1"
    candidate_settings["default_speech_blocks_profile_id"] = "profile_1"
    candidate_settings["default_character_extraction_profile_id"] = "profile_1"

    validated_settings = settings_service.validate_settings(candidate_settings)

    assert validated_settings["default_ai_cleanup_profile_id"] == "profile_1"
    assert validated_settings["default_ai_chunking_profile_id"] == "profile_1"
    assert validated_settings["default_ai_translation_profile_id"] == "profile_1"
    assert validated_settings["default_narrator_profile_generation_profile_id"] == "profile_1"
    assert validated_settings["default_speech_blocks_profile_id"] == "profile_1"
    assert validated_settings["default_character_extraction_profile_id"] == "profile_1"


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


def test_validate_settings_keeps_empty_api_key_for_lmstudio_profile() -> None:
    """
    @brief      Verify empty API keys remain valid for LM Studio-backed profiles.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    candidate_settings = settings_service.build_default_settings()
    candidate_settings["llm_profiles"] = [
        {
            "id": "profile_1",
            "label": "Local LM Studio",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234/v1",
            "api_key": "",
            "model_name": "openai/gpt-oss-20b",
            "context_window": config.DEFAULT_LLM_CONTEXT_WINDOW,
            "max_output_tokens": config.DEFAULT_LLM_MAX_OUTPUT_TOKENS,
            "request_timeout_seconds": config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
            "temperature": config.DEFAULT_LLM_TEMPERATURE,
            "supports_structured_output": True,
            "enabled": True,
            "discovered_model_name": "openai/gpt-oss-20b",
            "discovered_context_window": None,
            "discovery_succeeded": True,
            "discovery_message": "Connection successful.",
            "user_overrode_model_name": True,
            "user_overrode_context_window": True,
        }
    ]

    validated_settings = settings_service.validate_settings(candidate_settings)

    assert validated_settings == candidate_settings


def test_validate_settings_does_not_log_fake_root_repair_for_valid_dict_payload(caplog) -> None:
    """
    @brief      Verify valid dictionary payloads do not emit the false root-repair warning.
    @param[in]  caplog Pytest log-capture fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    candidate_settings = settings_service.build_default_settings()

    with caplog.at_level(logging.WARNING, logger="settings"):
        validated_settings = settings_service.validate_settings(candidate_settings)

    assert validated_settings == candidate_settings
    assert "Replaced invalid settings root payload with a normalized dict payload." not in caplog.text


def test_validate_settings_normalizes_tts_runtime_discovery_cache() -> None:
    """
    @brief      Verify invalid cached VoiceWeaver discovery fields are repaired safely.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    candidate_settings = settings_service.build_default_settings()
    candidate_settings["tts_runtime_probe_succeeded"] = "yes"
    candidate_settings["tts_runtime_discovered_models"] = [
        {
            "model_id": "definition_model",
            "status": "healthy",
            "supported_generation_modes": ["definition"],
        },
        "invalid",
    ]
    candidate_settings["tts_runtime_active_model_id"] = "missing_model"
    candidate_settings["tts_runtime_device_diagnostics"] = {"status_message": "CUDA active.", "bad": []}

    validated_settings = settings_service.validate_settings(candidate_settings)

    assert validated_settings["tts_runtime_probe_succeeded"] is False
    assert len(validated_settings["tts_runtime_discovered_models"]) == 1
    assert "speaker_count" not in validated_settings["tts_runtime_discovered_models"][0]
    assert validated_settings["tts_runtime_active_model_id"] is None
    assert validated_settings["tts_runtime_device_diagnostics"] == {"status_message": "CUDA active."}


def test_load_settings_logs_repair_summary_only_when_repairs_occur(tmp_path, monkeypatch, caplog) -> None:
    """
    @brief      Verify load_settings reports either repairs or clean load, never both.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  caplog Pytest log-capture fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)

    persisted_settings = settings_service.build_default_settings()
    persisted_settings["llm_profiles"] = [
        {
            "id": "profile_1",
            "label": "Local LM Studio",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234/v1",
            "api_key": "",
            "model_name": "openai/gpt-oss-20b",
            "context_window": config.DEFAULT_LLM_CONTEXT_WINDOW,
            "max_output_tokens": config.DEFAULT_LLM_MAX_OUTPUT_TOKENS,
            "request_timeout_seconds": config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
            "temperature": config.DEFAULT_LLM_TEMPERATURE,
            "supports_structured_output": True,
            "enabled": True,
            "discovered_model_name": "openai/gpt-oss-20b",
            "discovered_context_window": None,
            "discovery_succeeded": True,
            "discovery_message": "Connection successful.",
            "user_overrode_model_name": True,
            "user_overrode_context_window": True,
        }
    ]
    settings_path.write_text(json.dumps(persisted_settings, indent=2), encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="settings"):
        loaded_settings = settings_service.load_settings()

    assert loaded_settings == persisted_settings
    assert "Detected and repaired persisted settings" not in caplog.text
    assert "Loaded settings from" in caplog.text
    assert "without requiring repairs" in caplog.text


def test_validate_settings_repairs_tts_audio_timeouts_and_preview_limit() -> None:
    """
    @brief      Verify invalid TTS audio timeout and preview-limit settings are repaired to their defaults.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.2.0
    """
    candidate_settings = settings_service.build_default_settings()
    candidate_settings["tts_audio_preview_timeout_seconds"] = 0
    candidate_settings["tts_audio_generation_timeout_seconds"] = "bad"
    candidate_settings["tts_preview_text_character_limit"] = -1
    candidate_settings["scene_ambience_guidance_scale"] = "bad"
    candidate_settings["scene_ambience_max_blocks_per_sequence"] = 0
    candidate_settings["scene_ambience_num_inference_steps"] = 0
    candidate_settings["scene_ambience_seed"] = -2
    candidate_settings["scene_ambience_generation_enabled"] = True
    candidate_settings["scene_ambience_audio_generation_enabled"] = True

    validated_settings = settings_service.validate_settings(candidate_settings)

    assert validated_settings["tts_audio_preview_timeout_seconds"] == config.DEFAULT_TTS_AUDIO_PREVIEW_TIMEOUT_SECONDS
    assert (
        validated_settings["tts_audio_generation_timeout_seconds"]
        == config.DEFAULT_TTS_AUDIO_GENERATION_TIMEOUT_SECONDS
    )
    assert validated_settings["tts_preview_text_character_limit"] == config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT
    assert validated_settings["scene_ambience_guidance_scale"] == config.DEFAULT_SCENE_AMBIENCE_GUIDANCE_SCALE
    assert (
        validated_settings["scene_ambience_max_blocks_per_sequence"]
        == config.DEFAULT_SCENE_AMBIENCE_MAX_BLOCKS_PER_SEQUENCE
    )
    assert validated_settings["scene_ambience_num_inference_steps"] == config.DEFAULT_SCENE_AMBIENCE_NUM_INFERENCE_STEPS
    assert validated_settings["scene_ambience_seed"] == config.DEFAULT_SCENE_AMBIENCE_SEED
    assert "scene_ambience_generation_enabled" not in validated_settings
    assert "scene_ambience_audio_generation_enabled" not in validated_settings


def test_validate_settings_repairs_invalid_urls() -> None:
    """
    @brief      Verify invalid persisted HTTP base URLs are repaired to their defaults.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    candidate_settings = settings_service.build_default_settings()
    candidate_settings["tts_runtime_base_url"] = "localhost:8059"
    candidate_settings["llm_profiles"] = [
        {
            "id": "profile_1",
            "label": "Broken URL",
            "backend_kind": "lmstudio",
            "base_url": "127.0.0.1:1234/v1",
            "api_key": "",
            "model_name": "qwen3-8b",
            "context_window": config.DEFAULT_LLM_CONTEXT_WINDOW,
            "max_output_tokens": config.DEFAULT_LLM_MAX_OUTPUT_TOKENS,
            "request_timeout_seconds": config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
            "temperature": config.DEFAULT_LLM_TEMPERATURE,
            "supports_structured_output": False,
            "enabled": True,
            "discovered_model_name": "",
            "discovered_context_window": None,
            "discovery_succeeded": False,
            "discovery_message": "",
            "user_overrode_model_name": False,
            "user_overrode_context_window": False,
        }
    ]

    validated_settings = settings_service.validate_settings(candidate_settings)

    assert validated_settings["tts_runtime_base_url"] == config.DEFAULT_TTS_RUNTIME_BASE_URL
    assert validated_settings["llm_profiles"][0]["base_url"] == ""


# END OF FILE
