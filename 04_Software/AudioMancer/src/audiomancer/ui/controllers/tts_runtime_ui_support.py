#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file tts_runtime_ui_support.py
@brief Shared VoiceWeaver runtime UI helpers for AudioMancer controllers.
@details Centralizes runtime probing, persisted runtime cache updates, timeout
         resolution, and active-model extraction shared by the narrator and
         character voice controllers.
"""

# IMPORTS

from typing import TYPE_CHECKING

from audiomancer import config
from audiomancer.services import settings_service, voiceweaver_runtime_service

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


def probe_runtime_and_persist_cache(window: "MainWindow") -> dict[str, object]:
    """
    @brief      Probe the runtime and persist the normalized discovery cache.
    @param[in]  window Main application window.
    @return     Normalized runtime probe result.
    @exception  None
    """
    probe_result = probe_runtime_and_persist_cache_from_settings(window._settings_payload)
    window._settings_payload = settings_service.load_settings()
    return probe_result


def probe_runtime_and_persist_cache_from_settings(settings_payload: dict[str, object]) -> dict[str, object]:
    """
    @brief      Probe the runtime and persist the normalized discovery cache without touching Qt objects.
    @param[in]  settings_payload Persisted settings snapshot.
    @return     Normalized runtime probe result.
    @exception  None
    """
    probe_result = voiceweaver_runtime_service.probe_runtime(
        str(settings_payload.get("tts_runtime_base_url", "")).strip(),
        str(settings_payload.get("tts_runtime_api_key", "")),
    )
    updated_settings = dict(settings_service.load_settings())
    if not updated_settings:
        updated_settings = dict(settings_payload)
    updated_settings["tts_runtime_probe_succeeded"] = bool(probe_result.get("success", False))
    updated_settings["tts_runtime_probe_message"] = str(probe_result.get("message", ""))
    updated_settings["tts_runtime_discovered_models"] = list(probe_result.get("discovered_models", []))
    updated_settings["tts_runtime_active_model_id"] = probe_result.get("active_model_id")
    updated_settings["tts_runtime_device_diagnostics"] = dict(probe_result.get("device_diagnostics", {}))
    settings_service.save_settings(updated_settings)
    return probe_result


def preview_timeout_seconds(window: "MainWindow") -> int:
    """
    @brief      Resolve the persisted preview timeout setting or its default.
    @param[in]  window Main application window.
    @return     Positive timeout value in seconds.
    @exception  None
    """
    return preview_timeout_seconds_from_settings(window._settings_payload)


def preview_timeout_seconds_from_settings(settings_payload: dict[str, object]) -> int:
    """
    @brief      Resolve the preview timeout setting from a settings snapshot.
    @param[in]  settings_payload Persisted settings snapshot.
    @return     Positive timeout value in seconds.
    @exception  None
    """
    timeout_value = settings_payload.get(
        "tts_audio_preview_timeout_seconds",
        config.DEFAULT_TTS_AUDIO_PREVIEW_TIMEOUT_SECONDS,
    )
    if isinstance(timeout_value, int) and timeout_value > 0:
        return timeout_value
    return config.DEFAULT_TTS_AUDIO_PREVIEW_TIMEOUT_SECONDS


def persist_runtime_status(window: "MainWindow", status_payload: dict[str, object]) -> None:
    """
    @brief      Persist active-model and device diagnostics from one runtime status payload.
    @param[in]  window Main application window.
    @param[in]  status_payload Runtime status payload.
    @return     None.
    @exception  None
    """
    persist_runtime_status_from_settings(window._settings_payload, status_payload)
    window._settings_payload = settings_service.load_settings()


def persist_runtime_status_from_settings(
    settings_payload: dict[str, object],
    status_payload: dict[str, object],
) -> None:
    """
    @brief      Persist active-model and device diagnostics from a runtime status without touching Qt objects.
    @param[in]  settings_payload Persisted settings snapshot.
    @param[in]  status_payload Runtime status payload.
    @return     None.
    @exception  None
    """
    updated_settings = dict(settings_service.load_settings())
    if not updated_settings:
        updated_settings = dict(settings_payload)
    updated_settings["tts_runtime_active_model_id"] = active_model_id_from_status(status_payload)
    updated_settings["tts_runtime_device_diagnostics"] = dict(status_payload.get("device_diagnostics", {}))
    settings_service.save_settings(updated_settings)


def active_model_id_from_status(status_payload: dict[str, object]) -> str | None:
    """
    @brief      Resolve the active model identifier from one runtime status payload.
    @param[in]  status_payload Runtime status payload.
    @return     Active model identifier or `None`.
    @exception  None
    """
    return voiceweaver_runtime_service._resolve_active_model_id(status_payload.get("active_model"))  # noqa: SLF001


# END OF FILE
