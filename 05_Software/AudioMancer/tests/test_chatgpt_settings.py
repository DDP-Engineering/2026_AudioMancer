#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_chatgpt_settings.py
@brief Subscription profile persistence and remote workflow boundaries.
@details Exercises isolated protocol, lifecycle and workflow fixtures without live credentials.
"""

# IMPORTS

import pytest

from audiomancer.services import settings_service


def test_subscription_profile_round_trip_excludes_secrets():
    """@brief Verify subscription profile round trip excludes secrets."""
    settings = settings_service.build_default_settings()
    settings["llm_profiles"] = [
        {
            "id": "subscription",
            "label": "ChatGPT",
            "backend_kind": "chatgpt_subscription",
            "base_url": "https://untrusted.example",
            "api_key": "sentinel-key",
            "credential_ref": "../../credential",
            "access_token": "sentinel-access",
            "refresh_token": "sentinel-refresh",
            "id_token": "sentinel-id",
            "model_name": "gpt-5.4",
            "supports_structured_output": True,
        }
    ]
    profile = settings_service.validate_settings(settings)["llm_profiles"][0]
    assert profile["backend_kind"] == "chatgpt_subscription"
    assert profile["credential_ref"] == "chatgpt-default"
    assert profile["base_url"] == "https://chatgpt.com/backend-api"
    assert profile["api_key"] == ""
    assert not {"access_token", "refresh_token", "id_token"} & profile.keys()
    assert "sentinel" not in str(profile)
    assert settings_service.validate_settings({**settings, "llm_profiles": [profile]})["llm_profiles"][0] == profile


@pytest.mark.parametrize(
    "old_mode,effort", [("enabled", "medium"), ("disabled", "none"), ("provider_default", "provider_default")]
)
def test_legacy_subscription_reasoning_migrates_without_affecting_local_profiles(old_mode, effort):
    """@brief Old subscription choices have explicit equivalents; local profile semantics stay intact."""
    payload = settings_service.build_default_settings()
    payload["llm_profiles"] = [
        {
            "id": "sub",
            "label": "Sub",
            "backend_kind": "chatgpt_subscription",
            "reasoning_mode": old_mode,
            "model_name": "gpt-5.6-luna",
        }
    ]
    profile = settings_service.validate_settings(payload)["llm_profiles"][0]
    assert profile["reasoning_effort"] == effort
    profile["reasoning_effort"] = "high"
    profile = settings_service.validate_settings({**payload, "llm_profiles": [profile]})["llm_profiles"][0]
    assert profile["reasoning_effort"] == "high"
    assert profile["reasoning_mode"] == "enabled"
    profile.update(backend_kind="lmstudio", reasoning_mode="disabled")
    assert (
        settings_service.validate_settings({**payload, "llm_profiles": [profile]})["llm_profiles"][0]["reasoning_mode"]
        == "disabled"
    )


# END OF FILE
