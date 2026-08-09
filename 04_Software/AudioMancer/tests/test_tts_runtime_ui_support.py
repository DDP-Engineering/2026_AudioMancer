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

from audiomancer.ui.controllers import tts_runtime_ui_support

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
        {"tts_runtime_base_url": "http://runtime", "tts_runtime_api_key": "secret"}
    )

    assert result == original_probe_result
    assert saved_payloads[0]["future_setting"] == {"preserved": True}
    assert saved_payloads[0]["tts_runtime_discovered_models"] == original_probe_result["discovered_models"]
    assert probe_result == original_probe_result


# END OF FILE
