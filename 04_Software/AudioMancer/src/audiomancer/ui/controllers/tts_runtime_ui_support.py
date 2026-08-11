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
         resolution, active-model extraction, and voice-design orchestration
         shared by the narrator and character voice controllers.
"""

# IMPORTS

from collections.abc import Callable
from typing import TYPE_CHECKING

from audiomancer import config
from audiomancer.services import operation_runtime_service, settings_service, voiceweaver_runtime_service

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


def run_voice_design_generation(
    settings_payload: dict[str, object],
    progress_messages: dict[str, str],
    generation_request_builder: Callable[[list[dict[str, object]]], dict[str, object]],
    prompt_text: str,
    preview_text: str,
    progress_callback,
    cancel_requested,
    *,
    before_probe: Callable[[], None] | None = None,
    default_language: str = "",
) -> dict[str, object]:
    """
    @brief      Run the shared VoiceWeaver voice-design runtime sequence.
    @param[in]  settings_payload Persisted settings snapshot.
    @param[in]  progress_messages Worker-safe progress and error messages.
    @param[in]  generation_request_builder Caller-owned request builder for discovered models.
    @param[in]  prompt_text Voice description submitted to VoiceWeaver.
    @param[in]  preview_text Text synthesized for the sample.
    @param[in]  progress_callback Optional threaded-runner progress callback.
    @param[in]  cancel_requested Optional cooperative cancellation callback.
    @param[in]  before_probe Optional caller-specific validation run after prepare progress.
    @param[in]  default_language Caller-specific fallback synthesis language.
    @return     Generation request, provider summary, and downloaded WAV bytes.
    @exception  OperationCancelledError Raised when cooperative cancellation is requested.
    @exception  RuntimeError Raised for runtime, capability, or generated-audio failures.
    """
    _emit_voice_design_progress(progress_callback, 2, progress_messages["prepare"])
    if before_probe is not None:
        before_probe()
    probe_result = probe_runtime_and_persist_cache_from_settings(settings_payload)
    if not bool(probe_result.get("success", False)):
        raise RuntimeError(str(probe_result.get("message", "")))
    operation_runtime_service.raise_if_cancelled(cancel_requested)
    capability_matrix = dict(probe_result.get("capability_matrix", {}))
    if not bool(capability_matrix.get("minimum_qwen_ready", False)):
        raise RuntimeError(
            progress_messages["qwen_capabilities_missing"].format(
                missing_capabilities=", ".join(capability_matrix.get("missing_qwen_capabilities", [])),
            )
        )
    discovered_models = list(probe_result.get("discovered_models", []))
    generation_request = generation_request_builder(discovered_models)
    if not bool(generation_request.get("can_generate", False)):
        raise RuntimeError(str(generation_request.get("unavailable_reason", "")))

    base_url = str(settings_payload.get("tts_runtime_base_url", "")).strip()
    runtime_api_key = str(settings_payload.get("tts_runtime_api_key", ""))
    timeout_seconds = preview_timeout_seconds_from_settings(settings_payload)
    model_id = str(generation_request.get("model_id", "")).strip()
    initial_status = voiceweaver_runtime_service.read_status(
        base_url,
        runtime_api_key,
        timeout_seconds=timeout_seconds,
    )
    persist_runtime_status_from_settings(settings_payload, initial_status)
    active_model_id = active_model_id_from_status(initial_status)
    _emit_voice_design_progress(progress_callback, 10, progress_messages["prepare"])
    if active_model_id != model_id:
        operation_runtime_service.raise_if_cancelled(cancel_requested)
        _emit_voice_design_progress(progress_callback, 25, progress_messages["load_model"])
        voiceweaver_runtime_service.load_model(
            base_url,
            runtime_api_key,
            model_id,
            timeout_seconds=timeout_seconds,
        )
        load_status = voiceweaver_runtime_service.wait_for_terminal_operation(
            base_url,
            runtime_api_key,
            progress_callback=lambda status_payload: _update_voice_design_load_progress(
                progress_callback,
                status_payload,
                progress_messages["load_model"],
            ),
            timeout_seconds=timeout_seconds,
            cancel_requested=cancel_requested,
        )
        persist_runtime_status_from_settings(settings_payload, load_status)
        load_operation = load_status.get("operation", {})
        if not isinstance(load_operation, dict) or str(load_operation.get("status", "")).strip().lower() != "completed":
            raise RuntimeError(voiceweaver_runtime_service.operation_failed_message(load_status))
        active_model_id = active_model_id_from_status(load_status)
        if active_model_id != model_id:
            raise RuntimeError(f"VoiceWeaver did not activate the requested model '{model_id}'.")

    operation_runtime_service.raise_if_cancelled(cancel_requested)
    _emit_voice_design_progress(progress_callback, 35, progress_messages["generate"])
    generation_options: dict[str, object] = {
        "model_parameters": (
            dict(generation_request.get("model_parameters", {}))
            if isinstance(generation_request.get("model_parameters"), dict)
            else None
        ),
        "timeout_seconds": timeout_seconds,
    }
    if "supported_languages" in generation_request:
        generation_options["supported_languages"] = (
            list(generation_request.get("supported_languages", []))
            if isinstance(generation_request.get("supported_languages"), list)
            else None
        )
    voiceweaver_runtime_service.generate_voice_design(
        base_url,
        runtime_api_key,
        str(generation_request.get("language", default_language)),
        preview_text,
        prompt_text,
        **generation_options,
    )
    final_status = voiceweaver_runtime_service.wait_for_terminal_operation(
        base_url,
        runtime_api_key,
        progress_callback=lambda status_payload: _update_voice_design_generation_progress(
            progress_callback,
            status_payload,
            progress_messages["generate"],
        ),
        timeout_seconds=timeout_seconds,
        cancel_requested=cancel_requested,
    )
    persist_runtime_status_from_settings(settings_payload, final_status)
    final_operation = final_status.get("operation", {})
    if (
        not isinstance(final_operation, dict)
        or str(final_operation.get("status", "")).strip().lower() != "completed"
    ):
        raise RuntimeError(voiceweaver_runtime_service.operation_failed_message(final_status))
    final_result = final_status.get("result", {})
    if not isinstance(final_result, dict) or not bool(final_result.get("available", False)):
        raise RuntimeError(progress_messages["generation_missing_audio"])

    operation_runtime_service.raise_if_cancelled(cancel_requested)
    _emit_voice_design_progress(progress_callback, 95, progress_messages["download"])
    audio_bytes = voiceweaver_runtime_service.download_generated_voice(
        base_url,
        runtime_api_key,
        timeout_seconds=timeout_seconds,
    )
    return {
        "generation_request": generation_request,
        "result_summary": str(final_result.get("summary", "")),
        "audio_bytes": audio_bytes,
    }


def active_model_id_from_status(status_payload: dict[str, object]) -> str | None:
    """
    @brief      Resolve the active model identifier from one runtime status payload.
    @param[in]  status_payload Runtime status payload.
    @return     Active model identifier or `None`.
    @exception  None
    """
    return voiceweaver_runtime_service._resolve_active_model_id(status_payload.get("active_model"))  # noqa: SLF001


def _update_voice_design_generation_progress(
    progress_callback,
    status_payload: dict[str, object],
    stage_text: str,
) -> None:
    """@brief Map provider generation progress into the sample-generation range."""
    operation_payload = status_payload.get("operation", {})
    if not isinstance(operation_payload, dict):
        return
    percent = int(operation_payload.get("progress_percent", 0))
    mapped_percent = 35 + int(max(0, min(percent, 100)) * 0.55)
    _emit_voice_design_progress(progress_callback, mapped_percent, stage_text)


def _update_voice_design_load_progress(
    progress_callback,
    status_payload: dict[str, object],
    stage_text: str,
) -> None:
    """@brief Map provider model-load progress into the sample-generation range."""
    operation_payload = status_payload.get("operation", {})
    if not isinstance(operation_payload, dict):
        return
    percent = int(operation_payload.get("progress_percent", 0))
    mapped_percent = 25 + int(max(0, min(percent, 100)) * 0.10)
    _emit_voice_design_progress(progress_callback, mapped_percent, stage_text)


def _emit_voice_design_progress(progress_callback, percent: int, message: str) -> None:
    """@brief Emit one sample-generation progress update when a callback exists."""
    if progress_callback is not None:
        progress_callback(0, 100, percent, message)


# END OF FILE
