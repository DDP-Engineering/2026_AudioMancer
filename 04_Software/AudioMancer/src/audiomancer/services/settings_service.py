#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
@date 2026-04-22
@version 0.7.1
"""

# IMPORTS

import copy
import json
from typing import Any
from urllib import parse

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

# @brief Default persisted VoiceWeaver runtime discovery cache payload.
_TTS_RUNTIME_MODEL_DEFAULTS = {
    "model_id": "",
    "backend_name": "",
    "status": "unhealthy",
    "supported_generation_modes": [],
    "supported_languages": [],
    "supported_presets": [],
    "speaker_count": 0,
    "default_model_parameters": None,
    "device_mode": "",
    "issues": None,
}


def _optional_profile_id(value: object) -> str | None:
    """
    @brief      Normalize one optional persisted profile identifier.
    @param[in]  value Candidate optional profile id value.
    @return     Normalized profile id or None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.1
    """
    if value in (None, ""):
        return None
    return str(value)


def _optional_string(value: object) -> str | None:
    """
    @brief      Normalize one optional persisted string field.
    @param[in]  value Candidate persisted string value.
    @return     Normalized string or None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    if value in (None, ""):
        return None
    return str(value)


def _is_valid_http_url(value: str) -> bool:
    """
    @brief      Determine whether one string is a valid absolute HTTP or HTTPS URL.
    @param[in]  value Candidate URL string.
    @return     True when the string exposes an HTTP(S) scheme and network location.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    parsed_value = parse.urlparse(str(value).strip())
    return parsed_value.scheme in {"http", "https"} and bool(parsed_value.netloc)


# HELPER FUNCTIONS


def _log_settings_repair(
    message: str,
    field_name: str,
    *,
    func_name: str = "validate_settings",
    repair_tracker: list[bool] | None = None,
) -> None:
    """
    @brief      Emit a warning for one settings repair action.
    @param[in]  message Human-readable repair description.
    @param[in]  field_name Settings field or logical field path being repaired.
    @param[in]  func_name Logical function name emitted in the log entry.
    @param[in]  repair_tracker Optional mutable repair tracker toggled when one repair occurs.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.3.0
    """
    if repair_tracker is not None:
        repair_tracker.append(True)
    _SETTINGS_LOGGER.warning(
        message,
        extra={
            "func_name": func_name,
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
    repair_tracker: list[bool] | None = None,
) -> dict[str, Any]:
    """
    @brief      Validate and self-heal one LLM profile payload.
    @param[in]  candidate_profile Candidate persisted profile payload.
    @param[in]  default_profile Default profile payload used for fallback.
    @param[in]  profile_index Profile index used for logging context.
    @param[in]  repair_tracker Optional mutable repair tracker toggled when one repair occurs.
    @return     Validated LLM profile payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.2.0
    """
    if not isinstance(candidate_profile, dict):
        _log_settings_repair(
            f"Replaced invalid llm_profiles[{profile_index}] with a normalized default profile shape.",
            f"llm_profiles[{profile_index}]",
            func_name="_validate_llm_profile",
            repair_tracker=repair_tracker,
        )
        return copy.deepcopy(default_profile)

    normalized_profile = dict(candidate_profile)

    required_string_fields = (
        "id",
        "label",
        "backend_kind",
    )
    optional_string_fields = (
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

    for field_name in required_string_fields:
        if not isinstance(normalized_profile.get(field_name), str) or not normalized_profile[field_name].strip():
            _log_settings_repair(
                f"Repaired llm_profiles[{profile_index}].{field_name} using the default value.",
                f"llm_profiles[{profile_index}].{field_name}",
                func_name="_validate_llm_profile",
                repair_tracker=repair_tracker,
            )
            normalized_profile[field_name] = default_profile[field_name]
        else:
            normalized_profile[field_name] = normalized_profile[field_name].strip()

    for field_name in optional_string_fields:
        if not isinstance(normalized_profile.get(field_name), str):
            _log_settings_repair(
                f"Repaired llm_profiles[{profile_index}].{field_name} using the default value.",
                f"llm_profiles[{profile_index}].{field_name}",
                func_name="_validate_llm_profile",
                repair_tracker=repair_tracker,
            )
            normalized_profile[field_name] = default_profile[field_name]

    if normalized_profile["backend_kind"] not in config.LLM_BACKEND_OPTIONS:
        _log_settings_repair(
            f"Repaired llm_profiles[{profile_index}].backend_kind using the default value.",
            f"llm_profiles[{profile_index}].backend_kind",
            func_name="_validate_llm_profile",
            repair_tracker=repair_tracker,
        )
        normalized_profile["backend_kind"] = default_profile["backend_kind"]

    if normalized_profile["base_url"] and not _is_valid_http_url(normalized_profile["base_url"]):
        _log_settings_repair(
            f"Repaired llm_profiles[{profile_index}].base_url using the default value.",
            f"llm_profiles[{profile_index}].base_url",
            func_name="_validate_llm_profile",
            repair_tracker=repair_tracker,
        )
        normalized_profile["base_url"] = default_profile["base_url"]

    for field_name in integer_fields:
        if not isinstance(normalized_profile.get(field_name), int) or normalized_profile[field_name] <= 0:
            _log_settings_repair(
                f"Repaired llm_profiles[{profile_index}].{field_name} using the default value.",
                f"llm_profiles[{profile_index}].{field_name}",
                func_name="_validate_llm_profile",
                repair_tracker=repair_tracker,
            )
            normalized_profile[field_name] = default_profile[field_name]

    if not isinstance(normalized_profile.get("temperature"), (int, float)):
        _log_settings_repair(
            f"Repaired llm_profiles[{profile_index}].temperature using the default value.",
            f"llm_profiles[{profile_index}].temperature",
            func_name="_validate_llm_profile",
            repair_tracker=repair_tracker,
        )
        normalized_profile["temperature"] = default_profile["temperature"]
    else:
        normalized_profile["temperature"] = float(normalized_profile["temperature"])

    for field_name in boolean_fields:
        if not isinstance(normalized_profile.get(field_name), bool):
            _log_settings_repair(
                f"Repaired llm_profiles[{profile_index}].{field_name} using the default value.",
                f"llm_profiles[{profile_index}].{field_name}",
                func_name="_validate_llm_profile",
                repair_tracker=repair_tracker,
            )
            normalized_profile[field_name] = default_profile[field_name]

    discovered_context_window = normalized_profile.get("discovered_context_window")
    if discovered_context_window is not None and (
        not isinstance(discovered_context_window, int) or discovered_context_window <= 0
    ):
        _log_settings_repair(
            f"Repaired llm_profiles[{profile_index}].discovered_context_window using the default value.",
            f"llm_profiles[{profile_index}].discovered_context_window",
            func_name="_validate_llm_profile",
            repair_tracker=repair_tracker,
        )
        normalized_profile["discovered_context_window"] = default_profile["discovered_context_window"]

    for field_name, field_value in default_profile.items():
        if field_name not in normalized_profile:
            _log_settings_repair(
                f"Added missing llm_profiles[{profile_index}].{field_name} using the default value.",
                f"llm_profiles[{profile_index}].{field_name}",
                func_name="_validate_llm_profile",
                repair_tracker=repair_tracker,
            )
            normalized_profile[field_name] = copy.deepcopy(field_value)

    return normalized_profile


def _validate_settings_internal(settings_payload: object) -> tuple[dict[str, Any], bool]:
    """
    @brief      Validate one settings payload and report whether any repair occurred.
    @param[in]  settings_payload Candidate settings payload.
    @return     Tuple containing the normalized settings payload and a repair flag.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    repairs_made: list[bool] = []
    defaults = build_default_settings()
    normalized_settings = dict(settings_payload) if isinstance(settings_payload, dict) else {}

    if not isinstance(settings_payload, dict):
        _log_settings_repair(
            "Replaced invalid settings root payload with a normalized dict payload.",
            "<root>",
            repair_tracker=repairs_made,
        )

    for field_name, default_value in defaults.items():
        if field_name not in normalized_settings:
            normalized_settings[field_name] = copy.deepcopy(default_value)
            _log_settings_repair(
                f"Added missing settings field '{field_name}' using the default value.",
                field_name,
                repair_tracker=repairs_made,
            )

    if normalized_settings["language"] not in config.SUPPORTED_LANGUAGES:
        _log_settings_repair(
            "Repaired invalid 'language' using the default value.",
            "language",
            repair_tracker=repairs_made,
        )
        normalized_settings["language"] = defaults["language"]

    if normalized_settings["ui_text_scale"] not in config.UI_TEXT_SCALE_OPTIONS:
        _log_settings_repair(
            "Repaired invalid 'ui_text_scale' using the default value.",
            "ui_text_scale",
            repair_tracker=repairs_made,
        )
        normalized_settings["ui_text_scale"] = defaults["ui_text_scale"]

    if normalized_settings["default_ai_chunking_strategy"] not in config.AI_CHUNKING_STRATEGY_OPTIONS:
        _log_settings_repair(
            "Repaired invalid 'default_ai_chunking_strategy' using the default value.",
            "default_ai_chunking_strategy",
            repair_tracker=repairs_made,
        )
        normalized_settings["default_ai_chunking_strategy"] = defaults["default_ai_chunking_strategy"]

    for field_name in ("play_completion_beep",):
        if not isinstance(normalized_settings[field_name], bool):
            _log_settings_repair(
                f"Repaired invalid '{field_name}' using the default value.",
                field_name,
                repair_tracker=repairs_made,
            )
            normalized_settings[field_name] = defaults[field_name]

    for field_name in (
        "tts_runtime_base_url",
        "tts_runtime_api_key",
        "tts_runtime_probe_message",
    ):
        if not isinstance(normalized_settings[field_name], str):
            _log_settings_repair(
                f"Repaired invalid '{field_name}' using the default value.",
                field_name,
                repair_tracker=repairs_made,
            )
            normalized_settings[field_name] = defaults[field_name]

    if normalized_settings["tts_runtime_base_url"] and not _is_valid_http_url(
        normalized_settings["tts_runtime_base_url"]
    ):
        _log_settings_repair(
            "Repaired invalid 'tts_runtime_base_url' using the default value.",
            "tts_runtime_base_url",
            repair_tracker=repairs_made,
        )
        normalized_settings["tts_runtime_base_url"] = defaults["tts_runtime_base_url"]

    if not isinstance(normalized_settings["tts_runtime_probe_succeeded"], bool):
        _log_settings_repair(
            "Repaired invalid 'tts_runtime_probe_succeeded' using the default value.",
            "tts_runtime_probe_succeeded",
            repair_tracker=repairs_made,
        )
        normalized_settings["tts_runtime_probe_succeeded"] = defaults["tts_runtime_probe_succeeded"]

    for field_name in (
        "tts_audio_preview_timeout_seconds",
        "tts_audio_generation_timeout_seconds",
        "tts_preview_text_character_limit",
    ):
        if not isinstance(normalized_settings[field_name], int) or normalized_settings[field_name] <= 0:
            _log_settings_repair(
                f"Repaired invalid '{field_name}' using the default value.",
                field_name,
                repair_tracker=repairs_made,
            )
            normalized_settings[field_name] = defaults[field_name]

    normalized_settings["tts_runtime_discovered_models"] = _normalize_tts_runtime_models(
        normalized_settings.get("tts_runtime_discovered_models")
    )
    normalized_settings["tts_runtime_active_model_id"] = _optional_string(
        normalized_settings.get("tts_runtime_active_model_id")
    )
    discovered_model_ids = {
        str(model.get("model_id", "")).strip()
        for model in normalized_settings["tts_runtime_discovered_models"]
        if isinstance(model, dict)
    }
    if (
        normalized_settings["tts_runtime_active_model_id"] is not None
        and normalized_settings["tts_runtime_active_model_id"] not in discovered_model_ids
    ):
        _log_settings_repair(
            "Repaired invalid 'tts_runtime_active_model_id' using the default value.",
            "tts_runtime_active_model_id",
            repair_tracker=repairs_made,
        )
        normalized_settings["tts_runtime_active_model_id"] = defaults["tts_runtime_active_model_id"]
    normalized_settings["tts_runtime_device_diagnostics"] = _normalize_tts_device_diagnostics(
        normalized_settings.get("tts_runtime_device_diagnostics")
    )

    candidate_profiles = normalized_settings.get("llm_profiles")
    if not isinstance(candidate_profiles, list):
        _log_settings_repair(
            "Repaired invalid 'llm_profiles' using the default value.",
            "llm_profiles",
            repair_tracker=repairs_made,
        )
        normalized_settings["llm_profiles"] = copy.deepcopy(defaults["llm_profiles"])
    else:
        validated_profiles = []
        for index, candidate_profile in enumerate(candidate_profiles):
            validated_profiles.append(
                _validate_llm_profile(candidate_profile, _LLM_PROFILE_DEFAULTS, index, repair_tracker=repairs_made)
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
        "default_ai_translation_profile_id",
        "default_speech_blocks_profile_id",
        "default_character_extraction_profile_id",
    ):
        normalized_profile_id = _optional_profile_id(normalized_settings.get(field_name))
        if normalized_profile_id is not None and normalized_profile_id not in enabled_profile_ids:
            _log_settings_repair(
                f"Repaired invalid '{field_name}' using the default value.",
                field_name,
                repair_tracker=repairs_made,
            )
            normalized_profile_id = defaults[field_name]
        normalized_settings[field_name] = normalized_profile_id

    return normalized_settings, bool(repairs_made)


def _normalize_string_list(value: object) -> list[str]:
    """
    @brief      Normalize one list-like payload into a list of non-empty strings.
    @param[in]  value Candidate list payload.
    @return     Normalized string list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_tts_generation_modes(value: object) -> list[str]:
    """
    @brief      Normalize cached VoiceWeaver generation modes and fold legacy aliases into the current REST contract.
    @param[in]  value Candidate generation-mode list payload.
    @return     Normalized generation-mode list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    mode_aliases = {
        "base": "clone",
        "voice_designer": "definition",
    }
    normalized_modes: list[str] = []
    for mode in _normalize_string_list(value):
        normalized_mode = mode_aliases.get(mode, mode)
        if normalized_mode not in normalized_modes:
            normalized_modes.append(normalized_mode)
    return normalized_modes


def _normalize_tts_runtime_model(candidate_model: object) -> dict[str, object] | None:
    """
    @brief      Normalize one cached VoiceWeaver discovered-model payload.
    @param[in]  candidate_model Candidate discovered-model payload.
    @return     Normalized model payload or None when invalid.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    0.2.0
    """
    if not isinstance(candidate_model, dict):
        return None
    model_id = str(candidate_model.get("model_id", "")).strip()
    if not model_id:
        return None
    try:
        speaker_count = int(candidate_model.get("speaker_count", 0))
    except (TypeError, ValueError):
        speaker_count = 0
    issues = candidate_model.get("issues")
    return {
        "model_id": model_id,
        "backend_name": str(candidate_model.get("backend_name", "")).strip(),
        "status": str(candidate_model.get("status", _TTS_RUNTIME_MODEL_DEFAULTS["status"])).strip()
        or _TTS_RUNTIME_MODEL_DEFAULTS["status"],
        "supported_generation_modes": _normalize_tts_generation_modes(
            candidate_model.get("supported_generation_modes")
        ),
        "supported_languages": _normalize_string_list(candidate_model.get("supported_languages")),
        "supported_presets": _normalize_string_list(candidate_model.get("supported_presets")),
        "speaker_count": max(speaker_count, 0),
        "default_model_parameters": (
            dict(candidate_model.get("default_model_parameters"))
            if isinstance(candidate_model.get("default_model_parameters"), dict)
            else None
        ),
        "device_mode": str(candidate_model.get("device_mode", "")).strip(),
        "issues": issues if isinstance(issues, (list, type(None))) else None,
    }


def _normalize_tts_runtime_models(candidate_models: object) -> list[dict[str, object]]:
    """
    @brief      Normalize one cached VoiceWeaver discovered-model list.
    @param[in]  candidate_models Candidate discovered-model list payload.
    @return     Normalized discovered-model list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    if not isinstance(candidate_models, list):
        return []
    normalized_models: list[dict[str, object]] = []
    for candidate_model in candidate_models:
        normalized_model = _normalize_tts_runtime_model(candidate_model)
        if normalized_model is not None:
            normalized_models.append(normalized_model)
    return normalized_models


def _normalize_tts_device_diagnostics(candidate_payload: object) -> dict[str, object]:
    """
    @brief      Normalize one cached VoiceWeaver device-diagnostics payload.
    @param[in]  candidate_payload Candidate device-diagnostics payload.
    @return     Normalized diagnostics payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    if not isinstance(candidate_payload, dict):
        return {}
    normalized_payload: dict[str, object] = {}
    for key, value in candidate_payload.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        if value is None or isinstance(value, (bool, int, float, str)):
            normalized_payload[normalized_key] = value
    return normalized_payload


# PUBLIC API


@trace_function(_SETTINGS_LOGGER)
def build_default_settings() -> dict[str, Any]:
    """
    @brief      Build the default application settings payload.
    @return     Default settings payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.5.1
    """
    return {
        "language": config.DEFAULT_LANGUAGE,
        "llm_profiles": [],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_translation_profile_id": None,
        "default_speech_blocks_profile_id": None,
        "default_ai_chunking_strategy": "scene",
        "default_character_extraction_profile_id": None,
        "play_completion_beep": True,
        "ui_text_scale": config.DEFAULT_UI_TEXT_SCALE,
        "tts_runtime_base_url": config.DEFAULT_TTS_RUNTIME_BASE_URL,
        "tts_runtime_api_key": config.DEFAULT_TTS_RUNTIME_API_KEY,
        "tts_runtime_probe_succeeded": False,
        "tts_runtime_probe_message": "",
        "tts_runtime_discovered_models": [],
        "tts_runtime_active_model_id": None,
        "tts_runtime_device_diagnostics": {},
        "tts_audio_preview_timeout_seconds": config.DEFAULT_TTS_AUDIO_PREVIEW_TIMEOUT_SECONDS,
        "tts_audio_generation_timeout_seconds": config.DEFAULT_TTS_AUDIO_GENERATION_TIMEOUT_SECONDS,
        "tts_preview_text_character_limit": config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT,
    }


@trace_function(_SETTINGS_LOGGER)
def validate_settings(settings_payload: dict[str, Any]) -> dict[str, Any]:
    """
    @brief      Validate and self-heal one settings payload.
    @param[in]  settings_payload Candidate settings payload.
    @return     Validated and normalized settings payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.6.0
    """
    return _validate_settings_internal(settings_payload)[0]


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
    @version    0.2.0
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

    validated_settings, repairs_made = _validate_settings_internal(persisted_payload)
    if repairs_made:
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
