#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file settings_service.py
@brief Application settings lifecycle helpers for AudioMancer.
@details Builds default settings, validates persisted and in-memory payloads,
         self-heals missing or invalid values, and saves the normalized
         settings file to the application root.
@author Eng. Dan Dumitru Pasare
@date 2026-04-04
@version 0.1.6
"""

# IMPORTS

import copy
import json
from pathlib import Path
from typing import Any

from .. import config
from .logging_service import get_component_logger, trace_function

# CONSTANTS

# @brief Component logger used by settings load, validation, and save helpers.
_SETTINGS_LOGGER = get_component_logger("settings")
# @brief Default field scaffold applied to each persisted LLM profile payload.
_LLM_PROFILE_DEFAULTS = {
    "id": "",
    "label": "",
    "backend_kind": config.LLM_BACKEND_OPTIONS[0],
    "base_url": "",
    "api_key": "",
    "model_name": "",
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


def _optional_profile_id(value: object) -> str | None:
    """
    @brief      Normalize one optional persisted profile identifier.
    @param[in]  value Candidate optional profile id value.
    @return     Normalized profile id or None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    if value in (None, ""):
        return None
    return str(value)


# HELPER FUNCTIONS


def _log_settings_repair(message: str, field_name: str) -> None:
    """
    @brief      Emit a warning for one settings repair action.
    @param[in]  message Human-readable repair description.
    @param[in]  field_name Settings field or logical field path being repaired.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    _SETTINGS_LOGGER.warning(
        message,
        extra={
            "func_name": "validate_settings",
            "event": "settings-repair",
            "result": field_name,
        },
    )


def _write_settings_file(settings_payload: dict[str, Any]) -> None:
    """
    @brief      Persist one validated settings payload to the app settings file.
    @param[in]  settings_payload Validated settings payload to persist.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    settings_path = config.APP_SETTINGS_PATH
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _validate_llm_profile(
    candidate_profile: Any,
    default_profile: dict[str, Any],
    profile_index: int,
) -> dict[str, Any]:
    """
    @brief      Validate and self-heal one LLM profile payload.
    @param[in]  candidate_profile Candidate persisted profile payload.
    @param[in]  default_profile Default profile payload used for fallback.
    @param[in]  profile_index Profile index used for logging context.
    @return     Validated LLM profile payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    if not isinstance(candidate_profile, dict):
        _SETTINGS_LOGGER.warning(
            f"Replaced invalid llm_profiles[{profile_index}] with a normalized default profile shape.",
            extra={"func_name": "_validate_llm_profile", "event": "settings-repair"},
        )
        return copy.deepcopy(default_profile)

    normalized_profile = dict(candidate_profile)

    string_fields = (
        "id",
        "label",
        "backend_kind",
        "base_url",
        "api_key",
        "model_name",
        "discovered_model_name",
        "discovery_message",
    )
    integer_fields = (
        "context_window",
        "max_output_tokens",
        "request_timeout_seconds",
    )
    boolean_fields = (
        "supports_structured_output",
        "enabled",
        "discovery_succeeded",
        "user_overrode_model_name",
        "user_overrode_context_window",
    )

    for field_name in string_fields:
        if not isinstance(normalized_profile.get(field_name), str) or not normalized_profile[field_name].strip():
            _SETTINGS_LOGGER.warning(
                f"Repaired llm_profiles[{profile_index}].{field_name} using the default value.",
                extra={"func_name": "_validate_llm_profile", "event": "settings-repair"},
            )
            normalized_profile[field_name] = default_profile[field_name]

    if normalized_profile["backend_kind"] not in config.LLM_BACKEND_OPTIONS:
        _SETTINGS_LOGGER.warning(
            f"Repaired llm_profiles[{profile_index}].backend_kind using the default value.",
            extra={"func_name": "_validate_llm_profile", "event": "settings-repair"},
        )
        normalized_profile["backend_kind"] = default_profile["backend_kind"]

    for field_name in integer_fields:
        if not isinstance(normalized_profile.get(field_name), int) or normalized_profile[field_name] <= 0:
            _SETTINGS_LOGGER.warning(
                f"Repaired llm_profiles[{profile_index}].{field_name} using the default value.",
                extra={"func_name": "_validate_llm_profile", "event": "settings-repair"},
            )
            normalized_profile[field_name] = default_profile[field_name]

    if not isinstance(normalized_profile.get("temperature"), (int, float)):
        _SETTINGS_LOGGER.warning(
            f"Repaired llm_profiles[{profile_index}].temperature using the default value.",
            extra={"func_name": "_validate_llm_profile", "event": "settings-repair"},
        )
        normalized_profile["temperature"] = default_profile["temperature"]
    else:
        normalized_profile["temperature"] = float(normalized_profile["temperature"])

    for field_name in boolean_fields:
        if not isinstance(normalized_profile.get(field_name), bool):
            _SETTINGS_LOGGER.warning(
                f"Repaired llm_profiles[{profile_index}].{field_name} using the default value.",
                extra={"func_name": "_validate_llm_profile", "event": "settings-repair"},
            )
            normalized_profile[field_name] = default_profile[field_name]

    discovered_context_window = normalized_profile.get("discovered_context_window")
    if discovered_context_window is not None and (
        not isinstance(discovered_context_window, int) or discovered_context_window <= 0
    ):
        _SETTINGS_LOGGER.warning(
            f"Repaired llm_profiles[{profile_index}].discovered_context_window using the default value.",
            extra={"func_name": "_validate_llm_profile", "event": "settings-repair"},
        )
        normalized_profile["discovered_context_window"] = default_profile["discovered_context_window"]

    for field_name, field_value in default_profile.items():
        if field_name not in normalized_profile:
            _SETTINGS_LOGGER.warning(
                f"Added missing llm_profiles[{profile_index}].{field_name} using the default value.",
                extra={"func_name": "_validate_llm_profile", "event": "settings-repair"},
            )
            normalized_profile[field_name] = copy.deepcopy(field_value)

    return normalized_profile


# PUBLIC API


@trace_function(_SETTINGS_LOGGER)
def build_default_settings() -> dict[str, Any]:
    """
    @brief      Build the default application settings payload.
    @return     Default settings payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.4
    """
    return {
        "language": config.DEFAULT_LANGUAGE,
        "llm_profiles": [],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_chunking_strategy": "scene",
        "default_character_extraction_profile_id": None,
        "play_completion_beep": True,
        "ui_text_scale": config.DEFAULT_UI_TEXT_SCALE,
    }


@trace_function(_SETTINGS_LOGGER)
def validate_settings(settings_payload: dict[str, Any]) -> dict[str, Any]:
    """
    @brief      Validate and self-heal one settings payload.
    @param[in]  settings_payload Candidate settings payload.
    @return     Validated and normalized settings payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.5
    """
    defaults = build_default_settings()
    normalized_settings = dict(settings_payload) if isinstance(settings_payload, dict) else {}

    if normalized_settings is not settings_payload:
        _log_settings_repair(
            "Replaced invalid settings root payload with a normalized dict payload.",
            "<root>",
        )

    for field_name, default_value in defaults.items():
        if field_name not in normalized_settings:
            normalized_settings[field_name] = copy.deepcopy(default_value)
            _log_settings_repair(
                f"Added missing settings field '{field_name}' using the default value.",
                field_name,
            )

    if normalized_settings["language"] not in config.SUPPORTED_LANGUAGES:
        _log_settings_repair(
            "Repaired invalid 'language' using the default value.",
            "language",
        )
        normalized_settings["language"] = defaults["language"]

    if normalized_settings["ui_text_scale"] not in config.UI_TEXT_SCALE_OPTIONS:
        _log_settings_repair(
            "Repaired invalid 'ui_text_scale' using the default value.",
            "ui_text_scale",
        )
        normalized_settings["ui_text_scale"] = defaults["ui_text_scale"]

    if normalized_settings["default_ai_chunking_strategy"] not in config.AI_CHUNKING_STRATEGY_OPTIONS:
        _log_settings_repair(
            "Repaired invalid 'default_ai_chunking_strategy' using the default value.",
            "default_ai_chunking_strategy",
        )
        normalized_settings["default_ai_chunking_strategy"] = defaults["default_ai_chunking_strategy"]

    for field_name in ("play_completion_beep",):
        if not isinstance(normalized_settings[field_name], bool):
            _log_settings_repair(
                f"Repaired invalid '{field_name}' using the default value.",
                field_name,
            )
            normalized_settings[field_name] = defaults[field_name]

    candidate_profiles = normalized_settings.get("llm_profiles")
    if not isinstance(candidate_profiles, list):
        _log_settings_repair(
            "Repaired invalid 'llm_profiles' using the default value.",
            "llm_profiles",
        )
        normalized_settings["llm_profiles"] = copy.deepcopy(defaults["llm_profiles"])
    else:
        validated_profiles = []
        for index, candidate_profile in enumerate(candidate_profiles):
            validated_profiles.append(
                _validate_llm_profile(candidate_profile, _LLM_PROFILE_DEFAULTS, index)
            )
        normalized_settings["llm_profiles"] = validated_profiles

    enabled_profile_ids = {
        str(profile["id"])
        for profile in normalized_settings["llm_profiles"]
        if bool(profile.get("enabled", True)) and str(profile.get("id", "")).strip()
    }

    for field_name in (
        "default_ai_cleanup_profile_id",
        "default_ai_chunking_profile_id",
        "default_character_extraction_profile_id",
    ):
        normalized_profile_id = _optional_profile_id(
            normalized_settings.get(field_name)
        )
        if (
            normalized_profile_id is not None
            and normalized_profile_id not in enabled_profile_ids
        ):
            _log_settings_repair(
                f"Repaired invalid '{field_name}' using the default value.",
                field_name,
            )
            normalized_profile_id = defaults[field_name]
        normalized_settings[field_name] = normalized_profile_id

    return normalized_settings


@trace_function(_SETTINGS_LOGGER)
def save_settings(settings_payload: dict[str, Any]) -> None:
    """
    @brief      Validate and persist one settings payload to disk.
    @param[in]  settings_payload Candidate settings payload to persist.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.1
    """
    validated_settings = validate_settings(settings_payload)
    _write_settings_file(validated_settings)
    _SETTINGS_LOGGER.info(
        f"Saved validated settings to {config.APP_SETTINGS_PATH}.",
        extra={"func_name": "save_settings", "event": "settings-save"},
    )


@trace_function(_SETTINGS_LOGGER)
def ensure_settings_file() -> dict[str, Any]:
    """
    @brief      Ensure the app settings file exists and contains valid settings.
    @return     Validated settings payload currently persisted on disk.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.1
    """
    settings_path = config.APP_SETTINGS_PATH
    if not settings_path.exists():
        default_settings = build_default_settings()
        _write_settings_file(default_settings)
        _SETTINGS_LOGGER.info(
            f"Created missing settings file at {settings_path} using defaults.",
            extra={"func_name": "ensure_settings_file", "event": "settings-create"},
        )
        return default_settings
    return load_settings()


@trace_function(_SETTINGS_LOGGER)
def load_settings() -> dict[str, Any]:
    """
    @brief      Load, validate, and self-heal the persisted app settings.
    @return     Validated application settings payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.2
    """
    settings_path = config.APP_SETTINGS_PATH
    if not settings_path.exists():
        return ensure_settings_file()

    _SETTINGS_LOGGER.info(
        f"Loading settings from {settings_path}.",
        extra={"func_name": "load_settings", "event": "settings-load"},
    )

    try:
        persisted_payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        default_settings = build_default_settings()
        _write_settings_file(default_settings)
        _SETTINGS_LOGGER.warning(
            f"Replaced invalid JSON settings file at {settings_path} with defaults.",
            extra={"func_name": "load_settings", "event": "settings-heal"},
        )
        return default_settings

    validated_settings = validate_settings(persisted_payload)
    if validated_settings != persisted_payload:
        _write_settings_file(validated_settings)
        _SETTINGS_LOGGER.info(
            f"Detected and repaired persisted settings at {settings_path}.",
            extra={"func_name": "load_settings", "event": "settings-heal"},
        )
    else:
        _SETTINGS_LOGGER.info(
            f"Loaded settings from {settings_path} without requiring repairs.",
            extra={"func_name": "load_settings", "event": "settings-load"},
        )
    return validated_settings


# END OF FILE
