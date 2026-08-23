#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_duplicate_service_consolidation.py
@brief Regression coverage for behavior-identical service helper consolidation.
@details Verifies canonical resolver edge contracts and removal of private
         delegates that carried no distinct behavior or patch seam.
"""

# IMPORTS

import pytest

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    ai_translation_state_service,
    audio_blocks_state_service,
    character_discovery_state_service,
    project_export_service,
    project_snapshot_service,
    speech_blocks_service,
    speech_blocks_state_service,
    text_chunking_state_service,
    tts_budget_service,
)

# TESTS


@pytest.mark.parametrize(
    ("settings_payload", "expected"),
    (
        (None, 486),
        ({"tts_runtime_discovered_models": "invalid"}, 486),
        (
            {
                "tts_runtime_discovered_models": [
                    None,
                    {"default_model_parameters": {"max_new_tokens": 120}},
                ]
            },
            114,
        ),
    ),
)
def test_selected_text_character_limit_preserves_settings_edges(settings_payload, expected: int) -> None:
    """Verify the shared selected-text limit preserves malformed and valid settings behavior."""
    assert tts_budget_service.selected_text_character_limit(settings_payload) == expected


@pytest.mark.parametrize(
    ("manifest", "expected"),
    (
        ({}, config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE),
        ({"voice_assignment_mode": None}, config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE),
        ({"voice_assignment_mode": " invalid "}, config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE),
        ({"voice_assignment_mode": " same_narrator "}, "same_narrator"),
    ),
)
def test_voice_assignment_mode_preserves_defaults_and_normalization(manifest, expected: str) -> None:
    """Verify the public Speech Blocks resolver keeps the former normalization contract."""
    assert speech_blocks_service.voice_assignment_mode(manifest) == expected


@pytest.mark.parametrize(
    ("manifest", "expected"),
    (
        ({}, config.DEFAULT_TRANSLATION_TARGET_LANGUAGE),
        ({"target_language": None}, config.DEFAULT_TRANSLATION_TARGET_LANGUAGE),
        ({"target_language": " invalid "}, config.DEFAULT_TRANSLATION_TARGET_LANGUAGE),
        ({"target_language": " ro "}, "ro"),
    ),
)
def test_manifest_target_language_preserves_defaults_and_normalization(manifest, expected: str) -> None:
    """Verify the shared target-language resolver keeps the former state-service contract."""
    assert ai_translation_service.manifest_target_language(manifest) == expected


def test_behaviorless_private_service_delegates_are_removed() -> None:
    """Verify former one-line service delegates no longer remain as module seams."""
    removed_helpers = (
        (speech_blocks_state_service, "_selected_text_character_limit"),
        (audio_blocks_state_service, "_selected_text_character_limit"),
        (speech_blocks_state_service, "_voice_assignment_mode"),
        (ai_translation_state_service, "_persisted_target_language"),
        (text_chunking_state_service, "_manifest_target_language"),
        (speech_blocks_state_service, "_build_token_usage_notes"),
        (text_chunking_state_service, "_build_token_usage_notes"),
        (character_discovery_state_service, "_build_token_usage_notes"),
        (project_snapshot_service, "_safe_file_stem"),
        (project_export_service, "_safe_file_stem"),
    )
    assert all(not hasattr(module, helper_name) for module, helper_name in removed_helpers)


# END OF FILE
