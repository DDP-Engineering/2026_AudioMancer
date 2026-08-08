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
         packaged-scaffold seeding, persisted settings self-healing, and
         validated save behavior.
"""

# IMPORTS

import copy
import json
import logging
from pathlib import Path

from audiomancer import config
from audiomancer.services import settings_service, ui_theme_service

# PUBLIC API


def test_committed_settings_scaffold_matches_valid_settings_schema() -> None:
    """
    @brief      Verify the committed settings scaffold matches the valid schema.
    @return     None.
    @exception  None
    """
    committed_settings = json.loads(config.APP_DEFAULT_SETTINGS_PATH.read_text(encoding="utf-8"))
    validated_settings = settings_service.validate_settings(copy.deepcopy(committed_settings))

    assert validated_settings == committed_settings


def test_build_default_settings_uses_config_defined_factory_defaults() -> None:
    """
    @brief      Verify built-in settings derive shared factory defaults from config.
    @return     None.
    @exception  None
    """
    default_settings = settings_service.build_default_settings()

    assert default_settings["default_ai_chunking_strategy"] == config.DEFAULT_AI_CHUNKING_STRATEGY
    assert default_settings["play_completion_beep"] is config.DEFAULT_PLAY_COMPLETION_BEEP


def test_committed_settings_example_uses_config_defined_factory_defaults() -> None:
    """
    @brief      Verify the shipped settings example agrees with shared factory defaults.
    @return     None.
    @exception  None
    """
    settings_example_path = Path(__file__).resolve().parents[1] / "settings.example.json"
    committed_settings = json.loads(settings_example_path.read_text(encoding="utf-8"))

    assert committed_settings["default_ai_chunking_strategy"] == config.DEFAULT_AI_CHUNKING_STRATEGY
    assert committed_settings["play_completion_beep"] is config.DEFAULT_PLAY_COMPLETION_BEEP


def test_validate_settings_preserves_valid_explicit_scene_and_enabled_beep() -> None:
    """
    @brief      Verify valid explicit operator choices remain authoritative.
    @return     None.
    @exception  None
    """
    persisted_settings = settings_service.build_default_settings()
    persisted_settings["default_ai_chunking_strategy"] = "scene"
    persisted_settings["play_completion_beep"] = True

    validated_settings = settings_service.validate_settings(persisted_settings)

    assert validated_settings["default_ai_chunking_strategy"] == "scene"
    assert validated_settings["play_completion_beep"] is True


def test_build_default_settings_includes_theme_and_scroll_fields() -> None:
    """
    @brief      Verify default settings include theme and scroll persistence fields.
    @return     None.
    @exception  None
    """
    default_settings = settings_service.build_default_settings()

    assert default_settings["ui_theme_id"] == config.DEFAULT_UI_THEME_ID
    assert default_settings["ui_themes"] == []
    assert default_settings["ui_scroll_steps_per_wheel_notch"] == config.DEFAULT_UI_SCROLL_STEPS_PER_WHEEL_NOTCH


def test_validate_settings_repairs_invalid_chunking_context_mode() -> None:
    """
    @brief      Verify S-0001 and REQ-DATA-005 validate the chunking context mode setting.
    @return     None.
    @exception  None
    """
    default_settings = settings_service.build_default_settings()

    assert default_settings["default_ai_chunking_context_mode"] == config.AI_CHUNKING_CONTEXT_MODE_BALANCED

    valid_settings = copy.deepcopy(default_settings)
    valid_settings["default_ai_chunking_context_mode"] = config.AI_CHUNKING_CONTEXT_MODE_WIDE_SCENE
    assert (
        settings_service.validate_settings(valid_settings)["default_ai_chunking_context_mode"]
        == config.AI_CHUNKING_CONTEXT_MODE_WIDE_SCENE
    )

    invalid_settings = copy.deepcopy(default_settings)
    invalid_settings["default_ai_chunking_context_mode"] = "whole-book"
    assert (
        settings_service.validate_settings(invalid_settings)["default_ai_chunking_context_mode"]
        == config.AI_CHUNKING_CONTEXT_MODE_BALANCED
    )


def test_load_settings_creates_default_file_when_missing(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify missing settings create and return the default file.
    @details    Covers REQ-PLAT-f18086ef-3896-4be9-8afa-580b00534dbd / S-0003 for the
                case where no packaged scaffold is available to seed from. The bundled
                default path is pinned to the temporary root so the developer's own
                settings.json cannot leak into the assertion.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(config, "APP_DEFAULT_SETTINGS_PATH", tmp_path / "missing_scaffold.json")
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)

    loaded_settings = settings_service.load_settings()

    assert settings_path.exists()
    assert loaded_settings == settings_service.build_default_settings()
    assert json.loads(settings_path.read_text(encoding="utf-8")) == loaded_settings


def test_load_settings_accepts_utf8_bom_without_creating_backup(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify an optional UTF-8 BOM does not classify valid settings as corrupt.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)

    persisted_settings = settings_service.build_default_settings()
    persisted_settings["language"] = "ro"
    persisted_settings["ui_theme_id"] = "warm_reading"
    persisted_bytes = b"\xef\xbb\xbf" + json.dumps(persisted_settings, indent=2).encode("utf-8")
    settings_path.write_bytes(persisted_bytes)

    loaded_settings = settings_service.load_settings()

    assert loaded_settings == persisted_settings
    assert settings_path.read_bytes() == persisted_bytes
    assert list(tmp_path.glob("settings.corrupt*.json")) == []


def test_load_settings_backs_up_malformed_json_before_writing_defaults(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify malformed JSON bytes remain recoverable before defaults replace them.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)

    original_bytes = b'{"language": "ro", trailing-comma: true,}'
    settings_path.write_bytes(original_bytes)

    loaded_settings = settings_service.load_settings()

    assert loaded_settings == settings_service.build_default_settings()
    assert (tmp_path / "settings.corrupt.json").read_bytes() == original_bytes
    assert json.loads(settings_path.read_text(encoding="utf-8")) == loaded_settings


def test_load_settings_backs_up_invalid_utf8_and_returns_defaults(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify undecodable bytes remain recoverable and cannot escape from loading.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)

    original_bytes = b"\xff\xfe\x00invalid-settings\x80"
    settings_path.write_bytes(original_bytes)

    loaded_settings = settings_service.load_settings()

    assert loaded_settings == settings_service.build_default_settings()
    assert (tmp_path / "settings.corrupt.json").read_bytes() == original_bytes
    assert json.loads(settings_path.read_text(encoding="utf-8")) == loaded_settings


def test_load_settings_uses_distinct_backup_when_corrupt_backup_exists(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify corruption recovery never overwrites an earlier backup.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)

    previous_backup_path = tmp_path / "settings.corrupt.json"
    previous_backup_bytes = b"previous-corruption"
    previous_backup_path.write_bytes(previous_backup_bytes)
    current_bytes = b"{current-corruption"
    settings_path.write_bytes(current_bytes)

    loaded_settings = settings_service.load_settings()

    assert loaded_settings == settings_service.build_default_settings()
    assert previous_backup_path.read_bytes() == previous_backup_bytes
    assert (tmp_path / "settings.corrupt.1.json").read_bytes() == current_bytes


def test_load_settings_read_oserror_returns_defaults_without_modifying_file(
    tmp_path, monkeypatch, caplog
) -> None:
    """
    @brief      Verify a read failure returns safe defaults without touching persisted bytes.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  caplog Pytest log-capture fixture.
    @return     None.
    @exception  None
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)

    content_marker = "do-not-log-read-marker"
    original_bytes = json.dumps({"api_key": content_marker}).encode("utf-8")
    settings_path.write_bytes(original_bytes)
    original_read_bytes = type(settings_path).read_bytes

    def _raise_for_active_settings(path) -> bytes:
        if path == settings_path:
            raise PermissionError("simulated settings read failure")
        return original_read_bytes(path)

    monkeypatch.setattr(type(settings_path), "read_bytes", _raise_for_active_settings)

    with caplog.at_level(logging.WARNING, logger="settings"):
        loaded_settings = settings_service.load_settings()

    assert loaded_settings == settings_service.build_default_settings()
    with settings_path.open("rb") as settings_file:
        assert settings_file.read() == original_bytes
    assert list(tmp_path.glob("settings.corrupt*.json")) == []
    assert content_marker not in caplog.text


def test_load_settings_backup_oserror_returns_defaults_without_modifying_file(
    tmp_path, monkeypatch, caplog
) -> None:
    """
    @brief      Verify a backup failure leaves corrupt active settings untouched.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  caplog Pytest log-capture fixture.
    @return     None.
    @exception  None
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)

    content_marker = "do-not-log-backup-marker"
    original_bytes = f"{{invalid-{content_marker}".encode()
    settings_path.write_bytes(original_bytes)

    def _raise_backup_error(*_args) -> None:
        raise PermissionError("simulated settings backup failure")

    monkeypatch.setattr(settings_service, "_write_corrupt_settings_backup", _raise_backup_error)

    with caplog.at_level(logging.WARNING, logger="settings"):
        loaded_settings = settings_service.load_settings()

    assert loaded_settings == settings_service.build_default_settings()
    assert settings_path.read_bytes() == original_bytes
    assert list(tmp_path.glob("settings.corrupt*.json")) == []
    assert content_marker not in caplog.text


def test_load_settings_default_write_oserror_preserves_backup_and_returns_defaults(
    tmp_path, monkeypatch, caplog
) -> None:
    """
    @brief      Verify a failed default write leaves the completed backup recoverable.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  caplog Pytest log-capture fixture.
    @return     None.
    @exception  None
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)

    content_marker = "do-not-log-write-marker"
    original_bytes = f"{{invalid-{content_marker}".encode()
    settings_path.write_bytes(original_bytes)

    def _raise_write_error(_settings_payload) -> None:
        raise PermissionError("simulated settings defaults write failure")

    monkeypatch.setattr(settings_service, "_write_settings_file", _raise_write_error)

    with caplog.at_level(logging.WARNING, logger="settings"):
        loaded_settings = settings_service.load_settings()

    assert loaded_settings == settings_service.build_default_settings()
    assert settings_path.read_bytes() == original_bytes
    assert (tmp_path / "settings.corrupt.json").read_bytes() == original_bytes
    assert content_marker not in caplog.text


def test_load_settings_self_heals_missing_and_invalid_values(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify invalid persisted settings are healed and rewritten.
    @details    Covers S-0003 and REQ-PLAT-9fe6262f-238e-4020-aa23-5391bf9750a2.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)

    invalid_settings = settings_service.build_default_settings()
    invalid_settings["language"] = "fr"
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
    invalid_settings["ui_scroll_steps_per_wheel_notch"] = 6
    settings_path.write_text(json.dumps(invalid_settings, indent=2), encoding="utf-8")

    loaded_settings = settings_service.load_settings()
    defaults = settings_service.build_default_settings()

    assert loaded_settings["language"] == defaults["language"]
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
    assert loaded_settings["ui_scroll_steps_per_wheel_notch"] == defaults["ui_scroll_steps_per_wheel_notch"]
    assert loaded_settings["llm_profiles"] == defaults["llm_profiles"]
    assert json.loads(settings_path.read_text(encoding="utf-8")) == loaded_settings


def test_validate_settings_preserves_valid_scroll_steps() -> None:
    """
    @brief      Verify valid UI scroll-step settings survive validation.
    @return     None.
    @exception  None
    """
    for scroll_steps in range(
        config.MIN_UI_SCROLL_STEPS_PER_WHEEL_NOTCH,
        config.MAX_UI_SCROLL_STEPS_PER_WHEEL_NOTCH + 1,
    ):
        candidate_settings = settings_service.build_default_settings()
        candidate_settings["ui_scroll_steps_per_wheel_notch"] = scroll_steps

        validated_settings = settings_service.validate_settings(candidate_settings)

        assert validated_settings["ui_scroll_steps_per_wheel_notch"] == scroll_steps


def test_validate_settings_repairs_invalid_scroll_steps() -> None:
    """
    @brief      Verify invalid UI scroll-step settings repair to the default.
    @return     None.
    @exception  None
    """
    for scroll_steps in (0, 6, "three"):
        candidate_settings = settings_service.build_default_settings()
        candidate_settings["ui_scroll_steps_per_wheel_notch"] = scroll_steps

        validated_settings = settings_service.validate_settings(candidate_settings)

        assert validated_settings["ui_scroll_steps_per_wheel_notch"] == config.DEFAULT_UI_SCROLL_STEPS_PER_WHEEL_NOTCH


def test_load_settings_seeds_missing_theme_fields(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify settings missing theme fields gain current defaults.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)

    incomplete_settings = settings_service.build_default_settings()
    incomplete_settings.pop("ui_theme_id")
    incomplete_settings.pop("ui_themes")
    settings_path.write_text(json.dumps(incomplete_settings, indent=2), encoding="utf-8")

    loaded_settings = settings_service.load_settings()

    assert loaded_settings["ui_theme_id"] == config.DEFAULT_UI_THEME_ID
    assert loaded_settings["ui_themes"] == []
    assert json.loads(settings_path.read_text(encoding="utf-8")) == loaded_settings


def test_validate_settings_keeps_valid_selected_custom_theme() -> None:
    """
    @brief      Verify a valid custom theme and selected custom id survive validation.
    @return     None.
    @exception  None
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
def test_validate_settings_repairs_invalid_selected_theme_id_to_default() -> None:
    """
    @brief      Verify missing selected theme ids are repaired to the default theme.
    @return     None.
    @exception  None
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


def test_validate_settings_preserves_overnight_llm_timeout() -> None:
    """
    @brief      Verify S-0001 and REQ-UX-035 keep valid overnight LLM timeout values.
    @return     None.
    @exception  None.
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
            "request_timeout_seconds": 65535,
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

    assert validated_settings["llm_profiles"][0]["request_timeout_seconds"] == 65535


def test_validate_settings_keeps_valid_enabled_default_profile_ids() -> None:
    """
    @brief      Verify valid enabled AI default-profile ids are preserved.
    @return     None.
    @exception  None.
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
    """
    candidate_settings = settings_service.build_default_settings()
    candidate_settings["future_key"] = {"enabled": True}

    validated_settings = settings_service.validate_settings(candidate_settings)

    assert validated_settings["future_key"] == {"enabled": True}


def test_save_settings_writes_validated_payload_to_disk(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify save_settings validates and persists the payload.
    @details    Covers S-0003 and REQ-PLAT-9fe6262f-238e-4020-aa23-5391bf9750a2.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
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
    """
    candidate_settings = settings_service.build_default_settings()

    assert settings_service.validate_settings(copy.deepcopy(candidate_settings)) == candidate_settings


def test_validate_settings_keeps_empty_api_key_for_lmstudio_profile() -> None:
    """
    @brief      Verify empty API keys remain valid for LM Studio-backed profiles.
    @return     None.
    @exception  None
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
            "discovered_model_names": [],
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
            "discovered_model_names": [],
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
    assert validated_settings["scene_ambience_placement"] == "none"
    assert "scene_ambience_generation_enabled" not in validated_settings
    assert "scene_ambience_audio_generation_enabled" not in validated_settings


def test_validate_settings_repairs_invalid_urls() -> None:
    """
    @brief      Verify invalid persisted HTTP base URLs are repaired to their defaults.
    @return     None.
    @exception  None
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


def test_default_settings_include_font_size_steps() -> None:
    """
    @brief      Verify default settings carry both font-size steps at 'normal'.
    @details    Covers REQ-PLAT-0c2009a9-c691-4fd3-8e8c-e45e5e77d297 / SPEC-FONT-DEFAULTS.
    @return     None.
    @exception  None.
    """
    defaults = settings_service.build_default_settings()

    assert defaults["ui_font_size_step"] == "normal"
    assert defaults["text_font_size_step"] == "normal"


def test_validate_settings_repairs_font_size_steps() -> None:
    """
    @brief      Verify invalid font-size steps repair to normal.
    @details    Covers REQ-PLAT-46bbf1c0-5b82-45b8-a4e2-27748b1f5aeb / SPEC-FONT-VALIDATE.
    @return     None.
    @exception  None.
    """
    repaired = settings_service.validate_settings({"ui_font_size_step": "gigantic", "text_font_size_step": 5})
    assert repaired["ui_font_size_step"] == "normal"
    assert repaired["text_font_size_step"] == "normal"


def test_ensure_settings_file_seeds_from_the_bundled_default(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify a missing per-user settings file is seeded from the bundled default.
    @details    Covers REQ-PLAT-f18086ef-3896-4be9-8afa-580b00534dbd / S-0003. This is
                what carries an existing installation over to the per-user location
                instead of silently resetting the operator to factory defaults.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    bundled_settings_path = tmp_path / "install" / "settings.json"
    bundled_settings_path.parent.mkdir(parents=True)
    bundled_payload = settings_service.build_default_settings()
    bundled_payload["language"] = "ro"
    bundled_payload["play_completion_beep"] = True
    bundled_settings_path.write_text(json.dumps(bundled_payload, indent=2), encoding="utf-8")
    bundled_settings_bytes = bundled_settings_path.read_bytes()

    active_settings_path = tmp_path / "userdata" / "settings.json"
    monkeypatch.setattr(config, "APP_DEFAULT_SETTINGS_PATH", bundled_settings_path)
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", active_settings_path)

    seeded_settings = settings_service.ensure_settings_file()

    assert seeded_settings["language"] == "ro"
    assert seeded_settings["play_completion_beep"] is True
    assert json.loads(active_settings_path.read_text(encoding="utf-8")) == seeded_settings
    assert bundled_settings_path.read_bytes() == bundled_settings_bytes


def test_ensure_settings_file_falls_back_when_the_bundled_default_is_unusable(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify an unusable bundled default falls back to the built-in defaults.
    @details    Covers REQ-PLAT-f18086ef-3896-4be9-8afa-580b00534dbd / S-0003.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    bundled_settings_path = tmp_path / "install" / "settings.json"
    bundled_settings_path.parent.mkdir(parents=True)
    bundled_settings_path.write_text("{ not json", encoding="utf-8")

    active_settings_path = tmp_path / "userdata" / "settings.json"
    monkeypatch.setattr(config, "APP_DEFAULT_SETTINGS_PATH", bundled_settings_path)
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", active_settings_path)

    seeded_settings = settings_service.ensure_settings_file()

    assert seeded_settings == settings_service.build_default_settings()
    assert json.loads(active_settings_path.read_text(encoding="utf-8")) == seeded_settings


def test_ensure_settings_file_uses_defaults_when_the_active_path_is_the_bundled_path(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify the portable layout still creates a factory-default settings file.
    @details    Covers REQ-PLAT-f18086ef-3896-4be9-8afa-580b00534dbd / S-0003. When the
                application root is writable, the active and bundled paths coincide and
                there is nothing to seed from.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    portable_settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "APP_DEFAULT_SETTINGS_PATH", portable_settings_path)
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", portable_settings_path)

    created_settings = settings_service.ensure_settings_file()

    assert created_settings == settings_service.build_default_settings()
    assert json.loads(portable_settings_path.read_text(encoding="utf-8")) == created_settings


# END OF FILE
