#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_tts_runtime_ui_support.py
@brief Focused tests for shared TTS runtime UI support.
@details Verifies that runtime probing passes normalized discovery metadata to
         settings persistence without losing model range guidance.
"""

# IMPORTS

import copy

import pytest

from audiomancer.services import operation_runtime_service
from audiomancer.ui.controllers import tts_runtime_ui_support

_IN_RANGE_PREVIEW_TEXT = (
    "She weighs each answer before she gives it, and the words arrive quiet but certain. "
    "Nothing in her tone hurries, and nothing in it asks to be forgiven."
)

# PUBLIC API


def test_probe_runtime_cache_save_preserves_discovered_model_ranges(monkeypatch) -> None:
    """
    @brief      Verify the TTS Settings cache-save path retains discovered range metadata.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    probe_result = {
        "success": True,
        "message": "Connection successful.",
        "discovered_models": [
            {
                "model_id": "qwen-base",
                "generation_parameter_ranges": {"max_new_tokens": {"default": 2048}},
            }
        ],
        "active_model_id": "qwen-base",
        "device_diagnostics": {"device_mode": "cuda"},
    }
    original_probe_result = copy.deepcopy(probe_result)
    saved_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(
        tts_runtime_ui_support.voiceweaver_runtime_service,
        "probe_runtime",
        lambda *_args, **_kwargs: probe_result,
    )
    monkeypatch.setattr(
        tts_runtime_ui_support.settings_service,
        "load_settings",
        lambda: {"future_setting": {"preserved": True}},
    )
    monkeypatch.setattr(
        tts_runtime_ui_support.settings_service,
        "save_settings",
        lambda payload: saved_payloads.append(copy.deepcopy(payload)),
    )

    result = tts_runtime_ui_support.probe_runtime_and_persist_cache_from_settings(
        {"tts_runtime_base_url": "http://runtime"}
    )

    assert result == original_probe_result
    assert saved_payloads[0]["future_setting"] == {"preserved": True}
    assert saved_payloads[0]["tts_runtime_discovered_models"] == original_probe_result["discovered_models"]
    assert probe_result == original_probe_result


def test_voice_design_generation_runs_shared_success_flow(monkeypatch) -> None:
    """
    @brief      Verify the shared runtime flow loads, generates, validates, and downloads one sample.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    discovered_models = [{"model_id": "voice-designer"}]
    progress_updates: list[tuple[int, int, int, str]] = []
    status_updates: list[dict[str, object]] = []
    generated_arguments: list[tuple[tuple[object, ...], dict[str, object]]] = []
    terminal_statuses = iter(
        (
            {
                "active_model": {"model_id": "voice-designer"},
                "operation": {"status": " Completed ", "progress_percent": 50},
                "device_diagnostics": {},
            },
            {
                "active_model": {"model_id": "voice-designer"},
                "operation": {"status": " Completed ", "progress_percent": 50},
                "result": {"available": True, "summary": "Sample ready."},
                "device_diagnostics": {},
            },
        )
    )
    monkeypatch.setattr(
        tts_runtime_ui_support,
        "probe_runtime_and_persist_cache_from_settings",
        lambda _settings: {
            "success": True,
            "discovered_models": discovered_models,
            "capability_matrix": {"minimum_qwen_ready": True},
        },
    )
    monkeypatch.setattr(
        tts_runtime_ui_support,
        "persist_runtime_status_from_settings",
        lambda _settings, status: status_updates.append(status),
    )
    monkeypatch.setattr(
        tts_runtime_ui_support.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"active_model": "other-model", "device_diagnostics": {}},
    )
    monkeypatch.setattr(
        tts_runtime_ui_support.voiceweaver_runtime_service,
        "load_model",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        tts_runtime_ui_support.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **kwargs: (
            kwargs["progress_callback"]({"operation": {"progress_percent": 50}}),
            next(terminal_statuses),
        )[1],
    )
    monkeypatch.setattr(
        tts_runtime_ui_support.voiceweaver_runtime_service,
        "generate_voice_design",
        lambda *args, **kwargs: (generated_arguments.append((args, kwargs)), {"success": True})[1],
    )
    monkeypatch.setattr(
        tts_runtime_ui_support.voiceweaver_runtime_service,
        "download_generated_audio",
        lambda *_args, **_kwargs: b"RIFF-shared",
    )

    result = tts_runtime_ui_support.run_voice_design_generation(
        {
            "tts_runtime_base_url": "http://runtime",
            "tts_audio_preview_timeout_seconds": 45,
        },
        {
            "prepare": "Preparing",
            "preview_text_out_of_range": "Out of range.",
            "load_model": "Loading",
            "generate": "Generating",
            "download": "Downloading",
            "qwen_capabilities_missing": "Missing: {missing_capabilities}",
            "generation_missing_audio": "No audio",
        },
        lambda models: {
            "can_generate": models == discovered_models,
            "model_id": "voice-designer",
            "language": "en",
            "model_parameters": {"temperature": 0.4},
            "supported_languages": ["en", "ro"],
        },
        "Warm, grounded voice.",
        _IN_RANGE_PREVIEW_TEXT,
        lambda *values: progress_updates.append(values),
        lambda: False,
    )

    assert result == {
        "generation_request": {
            "can_generate": True,
            "model_id": "voice-designer",
            "language": "en",
            "model_parameters": {"temperature": 0.4},
            "supported_languages": ["en", "ro"],
        },
        "result_summary": "Sample ready.",
        "audio_bytes": b"RIFF-shared",
    }
    assert generated_arguments == [
        (
            ("http://runtime", "en", _IN_RANGE_PREVIEW_TEXT, "Warm, grounded voice."),
            {
                "model_parameters": {"temperature": 0.4},
                "timeout_seconds": 45,
                "supported_languages": ["en", "ro"],
            },
        )
    ]
    assert [update[2] for update in progress_updates] == [2, 10, 25, 30, 35, 62, 95]
    assert len(status_updates) == 3


def test_voice_design_generation_stops_after_probe_when_cancelled(monkeypatch) -> None:
    """
    @brief      Verify shared runtime orchestration preserves cooperative cancellation timing.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  OperationCancelledError Expected cancellation signal.
    """
    monkeypatch.setattr(
        tts_runtime_ui_support,
        "probe_runtime_and_persist_cache_from_settings",
        lambda _settings: {
            "success": True,
            "discovered_models": [],
            "capability_matrix": {"minimum_qwen_ready": True},
        },
    )

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        tts_runtime_ui_support.run_voice_design_generation(
            {},
            {
                "prepare": "Preparing",
                "preview_text_out_of_range": "Out of range.",
                "load_model": "Loading",
                "generate": "Generating",
                "download": "Downloading",
                "qwen_capabilities_missing": "Missing: {missing_capabilities}",
                "generation_missing_audio": "No audio",
            },
            lambda _models: pytest.fail("Request construction ran after cancellation."),
            "Prompt",
            _IN_RANGE_PREVIEW_TEXT,
            None,
            lambda: True,
        )


def test_voice_design_generation_preserves_probe_and_capability_errors(monkeypatch) -> None:
    """
    @brief      Verify provider probe and capability errors retain their caller-visible messages.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  RuntimeError Expected provider or capability error.
    """
    progress_messages = {
        "prepare": "Preparing",
        "preview_text_out_of_range": "Out of range.",
        "load_model": "Loading",
        "generate": "Generating",
        "download": "Downloading",
        "qwen_capabilities_missing": "Missing runtime capabilities: {missing_capabilities}",
        "generation_missing_audio": "No audio",
    }
    monkeypatch.setattr(
        tts_runtime_ui_support,
        "probe_runtime_and_persist_cache_from_settings",
        lambda _settings: {"success": False, "message": "Provider is unavailable."},
    )
    with pytest.raises(RuntimeError, match=r"^Provider is unavailable\.$"):
        tts_runtime_ui_support.run_voice_design_generation(
            {}, progress_messages, lambda _models: {}, "Prompt", _IN_RANGE_PREVIEW_TEXT, None, lambda: False
        )

    monkeypatch.setattr(
        tts_runtime_ui_support,
        "probe_runtime_and_persist_cache_from_settings",
        lambda _settings: {
            "success": True,
            "discovered_models": [],
            "capability_matrix": {
                "minimum_qwen_ready": False,
                "missing_qwen_capabilities": ["clone", "voice_design"],
            },
        },
    )
    with pytest.raises(RuntimeError, match=r"^Missing runtime capabilities: clone, voice_design$"):
        tts_runtime_ui_support.run_voice_design_generation(
            {}, progress_messages, lambda _models: {}, "Prompt", _IN_RANGE_PREVIEW_TEXT, None, lambda: False
        )


def test_voice_design_generation_maps_terminal_runtime_failure(monkeypatch) -> None:
    """
    @brief      Verify one failed terminal provider operation retains runtime error mapping.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  RuntimeError Expected terminal provider failure.
    """
    monkeypatch.setattr(
        tts_runtime_ui_support,
        "probe_runtime_and_persist_cache_from_settings",
        lambda _settings: {
            "success": True,
            "discovered_models": [],
            "capability_matrix": {"minimum_qwen_ready": True},
        },
    )
    monkeypatch.setattr(
        tts_runtime_ui_support,
        "persist_runtime_status_from_settings",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        tts_runtime_ui_support.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"active_model": "voice-designer", "device_diagnostics": {}},
    )
    monkeypatch.setattr(
        tts_runtime_ui_support.voiceweaver_runtime_service,
        "generate_voice_design",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        tts_runtime_ui_support.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: {"operation": {"status": "failed"}, "device_diagnostics": {}},
    )
    monkeypatch.setattr(
        tts_runtime_ui_support.voiceweaver_runtime_service,
        "operation_failed_message",
        lambda _status: "Provider rejected the request.",
    )

    with pytest.raises(RuntimeError, match=r"^Provider rejected the request\.$"):
        tts_runtime_ui_support.run_voice_design_generation(
            {},
            {
                "prepare": "Preparing",
                "preview_text_out_of_range": "Out of range.",
                "load_model": "Loading",
                "generate": "Generating",
                "download": "Downloading",
                "qwen_capabilities_missing": "Missing: {missing_capabilities}",
                "generation_missing_audio": "No audio",
            },
            lambda _models: {"can_generate": True, "model_id": "voice-designer", "language": "en"},
            "Prompt",
            _IN_RANGE_PREVIEW_TEXT,
            None,
            lambda: False,
        )



def test_voice_design_generation_refuses_out_of_range_preview_text(monkeypatch) -> None:
    """
    @brief      Verify no sample is recorded from preview text outside the accepted word range.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    monkeypatch.setattr(
        tts_runtime_ui_support,
        "probe_runtime_and_persist_cache_from_settings",
        lambda *_args, **_kwargs: pytest.fail("an out-of-range preview must be refused before the runtime is probed"),
    )

    with pytest.raises(RuntimeError, match="currently 4"):
        tts_runtime_ui_support.run_voice_design_generation(
            {},
            {
                "prepare": "Preparing",
                "preview_text_out_of_range": (
                    "Between {minimum_words} and {maximum_words} words, currently {word_count}."
                ),
            },
            lambda _models: {},
            "A mature voice with warm resonance and measured pacing throughout the book.",
            "Only five words here.",
            None,
            lambda: False,
        )


# END OF FILE
