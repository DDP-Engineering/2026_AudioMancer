#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_duplicate_model_activation_consolidation.py
@brief Regression coverage for shared Audio Blocks model activation.
@details Verifies the exact load, wait, terminal-status, active-model, and
         cancellation contracts shared by clone and sound model flows.
"""

# IMPORTS

import pytest

from audiomancer.services import audio_blocks_service

# TESTS


def test_ensure_model_active_loads_waits_and_returns_terminal_status(monkeypatch) -> None:
    """Verify the shared tail preserves runtime arguments, cancellation, and final status."""
    calls: list[tuple[object, ...]] = []
    final_status = {
        "active_model": {"model_id": "model-a"},
        "operation": {"status": "completed"},
    }
    def cancel_requested() -> bool:
        """Keep the shared wait path active."""
        return False

    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "load_model",
        lambda *args, **kwargs: calls.append(("load", args, kwargs)),
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *args, **kwargs: calls.append(("wait", args, kwargs)) or final_status,
    )

    result = audio_blocks_service._ensure_model_active(
        {"base_url": "http://runtime", "runtime_api_key": "secret", "timeout_seconds": 17},
        "model-a",
        "model",
        cancel_requested=cancel_requested,
    )

    assert result is final_status
    assert calls == [
        (
            "load",
            ("http://runtime", "secret", "model-a"),
            {"timeout_seconds": 17},
        ),
        (
            "wait",
            ("http://runtime", "secret"),
            {"timeout_seconds": 17, "cancel_requested": cancel_requested},
        ),
    ]


def test_ensure_model_active_preserves_failure_and_wrong_model_errors(monkeypatch) -> None:
    """Verify terminal failure mapping and active-model verification remain distinct."""
    monkeypatch.setattr(audio_blocks_service.voiceweaver_runtime_service, "load_model", lambda *_a, **_k: None)
    statuses = iter(
        (
            {"operation": {"status": "failed"}},
            {"operation": {"status": "completed"}, "active_model": {"model_id": "other"}},
        )
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: next(statuses),
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "operation_failed_message",
        lambda _status: "mapped failure",
    )

    with pytest.raises(RuntimeError, match="mapped failure"):
        audio_blocks_service._ensure_model_active({}, "model-a", "model")
    with pytest.raises(RuntimeError, match="requested sound model 'model-a'"):
        audio_blocks_service._ensure_model_active({}, "model-a", "sound model")


# END OF FILE
