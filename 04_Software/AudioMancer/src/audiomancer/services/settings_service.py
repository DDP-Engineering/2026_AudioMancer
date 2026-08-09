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
         self-heals missing or invalid values, seeds a fresh settings file from
         the packaged scaffold, and saves the normalized settings file to the
         resolved writable data root.
"""

# IMPORTS

from contextlib import suppress
import copy
from functools import partial
import json
import os
from pathlib import Path
from typing import Any
from urllib import parse

from .. import config
from . import ui_theme_service, voiceweaver_runtime_service
from .logging_service import get_component_logger, trace_function
from .operation_runtime_service import optional_string as _shared_optional_string
from .persistence_service import write_json_atomic

# CONSTANTS

# @brief Component logger used by settings load, validation, and save helpers.
_SETTINGS_LOGGER = get_component_logger("settings")
_optional_string = partial(_shared_optional_string, strip=False)
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
    "discovered_model_names": [],
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
    """
    settings_path = config.APP_SETTINGS_PATH
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(settings_path, settings_payload)


def _corruption_backup_path(settings_path: Path, backup_number: int) -> Path:
    """
    @brief      Build one clearly named same-directory corruption-backup path.
    @param[in]  settings_path Active settings path.
    @param[in]  backup_number Zero-based backup sequence number.
    @return     Candidate corruption-backup path.
    @exception  None
    """
    if backup_number == 0:
        return settings_path.with_suffix(".corrupt.json")
    return settings_path.with_suffix(f".corrupt.{backup_number}.json")


def _write_corrupt_settings_backup(settings_path: Path, original_bytes: bytes) -> Path:
    """
    @brief      Preserve corrupt settings bytes without overwriting an earlier backup.
    @details    Exclusive binary creation provides collision safety, while flush and
                fsync make the backup durable before the active settings path changes.
    @param[in]  settings_path Active settings path.
    @param[in]  original_bytes Exact bytes read from the active settings file.
    @return     Path of the completed corruption backup.
    @exception  OSError Raised when a new backup cannot be written safely.
    """
    backup_number = 0
    while True:
        backup_path = _corruption_backup_path(settings_path, backup_number)
        backup_created = False
        try:
            with backup_path.open("xb") as backup_file:
                backup_created = True
                backup_file.write(original_bytes)
                backup_file.flush()
                os.fsync(backup_file.fileno())
        except FileExistsError:
            backup_number += 1
            continue
        except OSError:
            if backup_created:
                with suppress(OSError):
                    backup_path.unlink(missing_ok=True)
            raise
        return backup_path


def _seed_settings_payload() -> tuple[dict[str, Any], str]:
    """
    @brief      Build the payload used to create a missing settings file.
    @details    A fresh per-user settings file inherits the packaged scaffold when
                one is available, which carries an existing installation over to
                the per-user location instead of resetting the operator to factory
                defaults. The packaged file is only ever read.
    @return     Tuple of seed payload and a human-readable seed-source label.
    @exception  None
    """
    default_settings_path = config.APP_DEFAULT_SETTINGS_PATH
    if default_settings_path == config.APP_SETTINGS_PATH:
        return build_default_settings(), "built-in defaults"

    try:
        bundled_payload = json.loads(default_settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return build_default_settings(), "built-in defaults"

    if not isinstance(bundled_payload, dict):
        return build_default_settings(), "built-in defaults"
    return validate_settings(bundled_payload), f"packaged defaults at {default_settings_path}"


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

    discovered_model_names = normalized_profile.get("discovered_model_names")
    if not isinstance(discovered_model_names, list):
        _log_settings_repair(
            f"Repaired llm_profiles[{profile_index}].discovered_model_names using the default value.",
            f"llm_profiles[{profile_index}].discovered_model_names",
            func_name="_validate_llm_profile",
            repair_tracker=repair_tracker,
        )
        normalized_profile["discovered_model_names"] = []
    else:
        normalized_profile["discovered_model_names"] = [
            str(model_name).strip() for model_name in discovered_model_names if str(model_name).strip()
        ]

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


# @brief Maps deprecated ui_text_scale presets to the nearest new font-size step.
_LEGACY_TEXT_SCALE_TO_STEP = {
    "very_small": "extra_small",
    "small": "small",
    "normal": "normal",
    "large": "large",
    "very_large": "very_large",
}


def _validate_settings_internal(settings_payload: object) -> tuple[dict[str, Any], bool]:
    """
    @brief      Validate one settings payload and report whether any repair occurred.
    @param[in]  settings_payload Candidate settings payload.
    @return     Tuple containing the normalized settings payload and a repair flag.
    @exception  None
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

    legacy_text_scale = normalized_settings.pop("ui_text_scale", None)
    if legacy_text_scale is not None:
        migrated_step = _LEGACY_TEXT_SCALE_TO_STEP.get(str(legacy_text_scale), config.DEFAULT_UI_FONT_SIZE_STEP)
        normalized_settings.setdefault("ui_font_size_step", migrated_step)
        normalized_settings.setdefault("text_font_size_step", migrated_step)
        _log_settings_repair(
            "Migrated deprecated 'ui_text_scale' setting into the font-size step settings.",
            "ui_text_scale",
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

    for deprecated_field_name in (
        "scene_ambience_generation_enabled",
        "scene_ambience_audio_generation_enabled",
    ):
        if deprecated_field_name in normalized_settings:
            normalized_settings.pop(deprecated_field_name, None)
            _log_settings_repair(
                f"Removed deprecated '{deprecated_field_name}' setting; Scene Ambience placement now owns enablement.",
                deprecated_field_name,
                repair_tracker=repairs_made,
            )

    normalized_ui_themes = ui_theme_service.normalize_theme_collection(normalized_settings.get("ui_themes"))
    if normalized_settings.get("ui_themes") != normalized_ui_themes:
        _log_settings_repair(
            "Repaired invalid 'ui_themes' using the normalized custom theme collection.",
            "ui_themes",
            repair_tracker=repairs_made,
        )
        normalized_settings["ui_themes"] = normalized_ui_themes

    available_theme_ids = {
        str(theme_payload["theme_id"])
        for theme_payload in ui_theme_service.merged_theme_catalog(normalized_settings["ui_themes"])
    }
    if (
        not isinstance(normalized_settings.get("ui_theme_id"), str)
        or normalized_settings["ui_theme_id"].strip() not in available_theme_ids
    ):
        _log_settings_repair(
            "Repaired invalid 'ui_theme_id' using the default value.",
            "ui_theme_id",
            repair_tracker=repairs_made,
        )
        normalized_settings["ui_theme_id"] = defaults["ui_theme_id"]
    else:
        normalized_settings["ui_theme_id"] = normalized_settings["ui_theme_id"].strip()

    for step_field_name in ("ui_font_size_step", "text_font_size_step"):
        if normalized_settings.get(step_field_name) not in config.UI_FONT_SIZE_STEPS:
            _log_settings_repair(
                f"Repaired invalid '{step_field_name}' using the default value.",
                step_field_name,
                repair_tracker=repairs_made,
            )
            normalized_settings[step_field_name] = defaults[step_field_name]

    if normalized_settings["default_ai_chunking_strategy"] not in config.AI_CHUNKING_STRATEGY_OPTIONS:
        _log_settings_repair(
            "Repaired invalid 'default_ai_chunking_strategy' using the default value.",
            "default_ai_chunking_strategy",
            repair_tracker=repairs_made,
        )
        normalized_settings["default_ai_chunking_strategy"] = defaults["default_ai_chunking_strategy"]

    if normalized_settings["default_ai_chunking_context_mode"] not in config.AI_CHUNKING_CONTEXT_MODE_OPTIONS:
        _log_settings_repair(
            "Repaired invalid 'default_ai_chunking_context_mode' using the default value.",
            "default_ai_chunking_context_mode",
            repair_tracker=repairs_made,
        )
        normalized_settings["default_ai_chunking_context_mode"] = defaults["default_ai_chunking_context_mode"]

    for field_name in ("play_completion_beep",):
        if not isinstance(normalized_settings[field_name], bool):
            _log_settings_repair(
                f"Repaired invalid '{field_name}' using the default value.",
                field_name,
                repair_tracker=repairs_made,
            )
            normalized_settings[field_name] = defaults[field_name]

    if (
        not isinstance(normalized_settings["ui_scroll_steps_per_wheel_notch"], int)
        or normalized_settings["ui_scroll_steps_per_wheel_notch"] < config.MIN_UI_SCROLL_STEPS_PER_WHEEL_NOTCH
        or normalized_settings["ui_scroll_steps_per_wheel_notch"] > config.MAX_UI_SCROLL_STEPS_PER_WHEEL_NOTCH
    ):
        _log_settings_repair(
            "Repaired invalid 'ui_scroll_steps_per_wheel_notch' using the default value.",
            "ui_scroll_steps_per_wheel_notch",
            repair_tracker=repairs_made,
        )
        normalized_settings["ui_scroll_steps_per_wheel_notch"] = defaults["ui_scroll_steps_per_wheel_notch"]

    if normalized_settings["scene_ambience_placement"] not in config.SCENE_AMBIENCE_PLACEMENT_OPTIONS:
        _log_settings_repair(
            "Repaired invalid 'scene_ambience_placement' using the default value.",
            "scene_ambience_placement",
            repair_tracker=repairs_made,
        )
        normalized_settings["scene_ambience_placement"] = defaults["scene_ambience_placement"]

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
        "scene_ambience_duration_seconds",
        "scene_ambience_max_blocks_per_sequence",
        "scene_ambience_num_inference_steps",
    ):
        if not isinstance(normalized_settings[field_name], int) or normalized_settings[field_name] <= 0:
            _log_settings_repair(
                f"Repaired invalid '{field_name}' using the default value.",
                field_name,
                repair_tracker=repairs_made,
            )
            normalized_settings[field_name] = defaults[field_name]

    speech_block_target = normalized_settings["speech_block_target_audio_seconds"]
    if not isinstance(speech_block_target, int | float) or isinstance(speech_block_target, bool):
        _log_settings_repair(
            "Repaired invalid 'speech_block_target_audio_seconds' using the default value.",
            "speech_block_target_audio_seconds",
            repair_tracker=repairs_made,
        )
        normalized_settings["speech_block_target_audio_seconds"] = defaults["speech_block_target_audio_seconds"]
    elif float(speech_block_target) <= 0.0:
        # Zero and any negative value both mean "follow the TTS model budget".
        normalized_settings["speech_block_target_audio_seconds"] = 0.0
    else:
        normalized_settings["speech_block_target_audio_seconds"] = min(
            max(float(speech_block_target), float(config.SPEECH_BLOCK_TARGET_AUDIO_SECONDS_MINIMUM)),
            float(config.SPEECH_BLOCK_TARGET_AUDIO_SECONDS_MAXIMUM),
        )

    if (
        not isinstance(normalized_settings["scene_ambience_guidance_scale"], int | float)
        or float(normalized_settings["scene_ambience_guidance_scale"]) <= 0
    ):
        _log_settings_repair(
            "Repaired invalid 'scene_ambience_guidance_scale' using the default value.",
            "scene_ambience_guidance_scale",
            repair_tracker=repairs_made,
        )
        normalized_settings["scene_ambience_guidance_scale"] = defaults["scene_ambience_guidance_scale"]
    else:
        normalized_settings["scene_ambience_guidance_scale"] = float(
            normalized_settings["scene_ambience_guidance_scale"]
        )

    scene_ambience_seed = normalized_settings["scene_ambience_seed"]
    if scene_ambience_seed is not None and (not isinstance(scene_ambience_seed, int) or scene_ambience_seed < 0):
        _log_settings_repair(
            "Repaired invalid 'scene_ambience_seed' using the default value.",
            "scene_ambience_seed",
            repair_tracker=repairs_made,
        )
        normalized_settings["scene_ambience_seed"] = defaults["scene_ambience_seed"]

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
    normalized_settings["tts_runtime_device_diagnostics"] = voiceweaver_runtime_service.normalize_device_diagnostics(
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
        "default_narrator_profile_generation_profile_id",
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


def _normalize_tts_runtime_models(candidate_models: object) -> list[dict[str, object]]:
    """
    @brief      Normalize one cached VoiceWeaver discovered-model list.
    @param[in]  candidate_models Candidate discovered-model list payload.
    @return     Normalized discovered-model list.
    @exception  None
    """
    if not isinstance(candidate_models, list):
        return []
    normalized_models: list[dict[str, object]] = []
    for candidate_model in candidate_models:
        normalized_model = voiceweaver_runtime_service.normalize_model(candidate_model)
        if normalized_model is not None:
            normalized_models.append(normalized_model)
    return normalized_models


# PUBLIC API


@trace_function(_SETTINGS_LOGGER)
def build_default_settings() -> dict[str, Any]:
    """
    @brief      Build the default application settings payload.
    @return     Default settings payload.
    @exception  None
    """
    return {
        "language": config.DEFAULT_LANGUAGE,
        "llm_profiles": [],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_translation_profile_id": None,
        "default_narrator_profile_generation_profile_id": None,
        "default_speech_blocks_profile_id": None,
        "default_ai_chunking_strategy": config.DEFAULT_AI_CHUNKING_STRATEGY,
        "default_ai_chunking_context_mode": config.DEFAULT_AI_CHUNKING_CONTEXT_MODE,
        "default_character_extraction_profile_id": None,
        "play_completion_beep": config.DEFAULT_PLAY_COMPLETION_BEEP,
        "ui_scroll_steps_per_wheel_notch": config.DEFAULT_UI_SCROLL_STEPS_PER_WHEEL_NOTCH,
        "ui_font_size_step": config.DEFAULT_UI_FONT_SIZE_STEP,
        "text_font_size_step": config.DEFAULT_TEXT_FONT_SIZE_STEP,
        "ui_theme_id": config.DEFAULT_UI_THEME_ID,
        "ui_themes": [],
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
        "speech_block_target_audio_seconds": config.DEFAULT_SPEECH_BLOCK_TARGET_AUDIO_SECONDS,
        "scene_ambience_placement": config.DEFAULT_SCENE_AMBIENCE_PLACEMENT,
        "scene_ambience_duration_seconds": config.DEFAULT_SCENE_AMBIENCE_DURATION_SECONDS,
        "scene_ambience_max_blocks_per_sequence": config.DEFAULT_SCENE_AMBIENCE_MAX_BLOCKS_PER_SEQUENCE,
        "scene_ambience_guidance_scale": config.DEFAULT_SCENE_AMBIENCE_GUIDANCE_SCALE,
        "scene_ambience_num_inference_steps": config.DEFAULT_SCENE_AMBIENCE_NUM_INFERENCE_STEPS,
        "scene_ambience_seed": config.DEFAULT_SCENE_AMBIENCE_SEED,
    }


@trace_function(_SETTINGS_LOGGER)
def validate_settings(settings_payload: dict[str, Any]) -> dict[str, Any]:
    """
    @brief      Validate and self-heal one settings payload.
    @param[in]  settings_payload Candidate settings payload.
    @return     Validated and normalized settings payload.
    @exception  None
    """
    return _validate_settings_internal(settings_payload)[0]


@trace_function(_SETTINGS_LOGGER)
def save_settings(settings_payload: dict[str, Any]) -> None:
    """
    @brief      Validate and persist one settings payload to disk.
    @param[in]  settings_payload Candidate settings payload to persist.
    @return     None.
    @exception  None
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
    """
    settings_path = config.APP_SETTINGS_PATH
    if not settings_path.exists():
        seed_settings, seed_source = _seed_settings_payload()
        _write_settings_file(seed_settings)
        _SETTINGS_LOGGER.info(
            f"Created missing settings file at {settings_path} using {seed_source}.",
            extra={"func_name": "ensure_settings_file", "event": "settings-create"},
        )
        return seed_settings
    return load_settings()


@trace_function(_SETTINGS_LOGGER)
def load_settings() -> dict[str, Any]:
    """
    @brief      Load, validate, and self-heal the persisted app settings.
    @return     Validated application settings payload.
    @exception  None
    """
    settings_path = config.APP_SETTINGS_PATH
    if not settings_path.exists():
        return ensure_settings_file()

    _SETTINGS_LOGGER.info(
        f"Loading settings from {settings_path}.",
        extra={"func_name": "load_settings", "event": "settings-load"},
    )

    try:
        original_bytes = settings_path.read_bytes()
    except OSError:
        default_settings = build_default_settings()
        _SETTINGS_LOGGER.warning(
            f"Could not read settings from {settings_path}; "
            "using built-in defaults for this run without changing the file.",
            extra={"func_name": "load_settings", "event": "settings-load"},
        )
        return default_settings

    try:
        persisted_payload = json.loads(original_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        default_settings = build_default_settings()
        try:
            backup_path = _write_corrupt_settings_backup(settings_path, original_bytes)
        except OSError:
            _SETTINGS_LOGGER.warning(
                f"Could not preserve invalid settings from {settings_path}; "
                "using built-in defaults for this run without changing the active file.",
                extra={"func_name": "load_settings", "event": "settings-heal"},
            )
            return default_settings
        try:
            _write_settings_file(default_settings)
        except OSError:
            _SETTINGS_LOGGER.warning(
                f"Preserved invalid settings at {backup_path}, but could not write defaults to {settings_path}; "
                "using built-in defaults for this run.",
                extra={"func_name": "load_settings", "event": "settings-heal"},
            )
            return default_settings
        _SETTINGS_LOGGER.warning(
            f"Preserved invalid settings from {settings_path} at {backup_path} "
            "and replaced the active file with defaults.",
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
