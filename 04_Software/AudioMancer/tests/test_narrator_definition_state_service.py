#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_narrator_definition_state_service.py
@brief Focused tests for the AudioMancer narrator-definition state service.
@details Verifies language display shaping, selection enablement, and bottom
         status-line composition for the simplified narrator workflow.
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import (
    narrator_definition_service,
    narrator_definition_state_service,
    project_workspace_service,
)


def test_narrator_profile_state_uses_configured_default_on_initial_load() -> None:
    """
    @brief      Verify initial Narrator Voice AI-profile state selects the configured enabled default.
    @return     None.
    @exception  None
    """
    state = narrator_definition_state_service.build_narrator_profile_generation_profile_state(
        {
            "llm_profiles": [
                {"id": "profile_a", "label": "Profile A", "enabled": True},
                {"id": "profile_b", "label": "Profile B", "enabled": True},
            ],
            "default_narrator_profile_generation_profile_id": "profile_b",
        }
    )

    assert state["selected_profile_id"] == "profile_b"


def test_narrator_profile_state_falls_back_from_invalid_or_disabled_selection() -> None:
    """
    @brief      Verify invalid live/default profiles resolve to the enabled default or first enabled profile.
    @return     None.
    @exception  None
    """
    settings_payload = {
        "llm_profiles": [
            {"id": "profile_a", "label": "Profile A", "enabled": True},
            {"id": "profile_b", "label": "Profile B", "enabled": False},
            {"id": "profile_c", "label": "Profile C", "enabled": True},
        ],
        "default_narrator_profile_generation_profile_id": "profile_a",
    }

    disabled_state = narrator_definition_state_service.build_narrator_profile_generation_profile_state(
        settings_payload,
        selected_profile_id="profile_b",
    )
    assert disabled_state["selected_profile_id"] == "profile_a"

    settings_payload["llm_profiles"][0]["enabled"] = False
    missing_default_state = narrator_definition_state_service.build_narrator_profile_generation_profile_state(
        settings_payload,
        selected_profile_id="missing_profile",
    )
    assert missing_default_state["selected_profile_id"] == "profile_c"


def test_narrator_state_service_uses_original_language_and_no_default_selection(tmp_path) -> None:
    """
    @brief      Verify narrator state resolves the original voice language and starts with no selected profile.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project(tmp_path, "NarratorStateProject")
    manifest["original_language"] = "Italian"
    project_workspace_service.save_manifest(manifest, project_root)
    translation_report_path = project_root / config.TRANSLATED_CHUNKS_FILE_NAME
    translation_report_path.parent.mkdir(parents=True, exist_ok=True)
    translation_report_path.write_text(
        json.dumps(
            {
                "target_language": "ro",
                "status": "completed",
                "token_usage": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "usage_available": False,
                },
                "budget_metadata": {},
                "additional_translation_instructions": "",
                "chunks": [{"chunk_id": "chunk-0001", "translated_text": "Text", "approved": True}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    state = narrator_definition_state_service.build_narrator_definition_state(project_root, manifest, "en")

    assert state["selected_profile_id"] is None
    assert state["effective_language"] == "it"
    assert state["selected_voice_language"] == "it"
    assert state["can_select"] is False


def test_narrator_state_service_marks_unsampled_custom_profile_selectable(tmp_path) -> None:
    """
    @brief      Verify an unsampled inspected profile can be selected when it is not already selected.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project(tmp_path, "NarratorStateCustomProject")
    custom_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "My Custom Narrator",
        "English",
        "Custom prompt.",
        "Preview text.",
    )
    state = narrator_definition_state_service.build_narrator_definition_state(
        project_root,
        manifest,
        "en",
        {
            "tts_runtime_probe_succeeded": True,
            "tts_runtime_discovered_models": _minimum_qwen_models(),
        },
        inspected_profile_id=custom_profile["profile_id"],
    )

    assert state["current_profile_id"] == custom_profile["profile_id"]
    assert state["profile_name"] == "My Custom Narrator"
    assert state["can_edit"] is True
    assert state["can_delete"] is True
    assert state["can_generate"] is True
    assert state["can_select"] is True
    assert state["preview_available"] is False


def test_narrator_state_service_keeps_generate_enabled_when_cached_runtime_is_stale(tmp_path) -> None:
    """
    @brief      Verify Generate Sample remains clickable even when cached runtime discovery is stale.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project(tmp_path, "NarratorStateStaleRuntimeProject")
    custom_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "My Narrator",
        "English",
        "Prompt.",
        "Preview text.",
    )

    state = narrator_definition_state_service.build_narrator_definition_state(
        project_root,
        manifest,
        "en",
        {
            "tts_runtime_probe_succeeded": False,
            "tts_runtime_discovered_models": [],
        },
        inspected_profile_id=custom_profile["profile_id"],
    )

    assert state["current_profile_id"] == custom_profile["profile_id"]
    assert state["can_generate"] is True


def test_narrator_state_service_status_lines_show_counts_and_qwen_readiness(tmp_path) -> None:
    """
    @brief      Verify narrator status lines summarize profile counts and Qwen readiness.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project(tmp_path, "NarratorStateStatusProject")
    profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Status Voice",
        "English",
        "Status prompt.",
        "Preview text.",
    )
    narrator_definition_service.store_profile_sample(
        project_root,
        profile,
        "Preview text.",
        {
            "generation_mode": "definition",
            "model_id": "qwen-designer",
            "source_model_id": "qwen-designer",
            "language": "en",
        },
        "Generated sample.",
        b"RIFF-preset",
    )

    state = narrator_definition_state_service.build_narrator_definition_state(
        project_root,
        manifest,
        "en",
        {
            "tts_runtime_probe_succeeded": True,
            "tts_runtime_discovered_models": _minimum_qwen_models(),
        },
        inspected_profile_id=profile["profile_id"],
    )

    assert "Profiles: 1" in state["status_lines"]
    assert "Profiles with samples: 1" in state["status_lines"]
    assert "Selected profiles: 0" in state["status_lines"]
    assert "Qwen3 TTS readiness: ready" in state["status_lines"]


def test_repeated_narrator_state_refresh_does_not_write_or_alter_document(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify repeated effective no-op state refreshes leave narrator persistence untouched.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project(tmp_path, "NarratorStateNoOpRefresh")
    narrator_definition_service.create_custom_profile(
        project_root,
        "Stable Narrator",
        "English",
        "Stable prompt.",
        "Stable authored preview.",
    )
    document_path = project_root / config.NARRATOR_VOICE_FILE_NAME
    original_bytes = document_path.read_bytes()
    write_calls: list[object] = []
    monkeypatch.setattr(
        narrator_definition_service,
        "write_narrator_voice_document",
        lambda *_args, **_kwargs: write_calls.append(object()),
    )

    narrator_definition_state_service.build_narrator_definition_state(project_root, manifest, "en")
    narrator_definition_state_service.build_narrator_definition_state(project_root, manifest, "en")

    assert write_calls == []
    assert document_path.read_bytes() == original_bytes


def _create_project(tmp_path, name: str):
    """
    @brief      Provide the create project test helper.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-17T12:00:00+00:00",
        "size_bytes": 16,
    }
    manifest["current_stage"] = "narrator_definition_ready"
    project_workspace_service.save_manifest(manifest, project_root)
    return project_root, manifest


def _minimum_qwen_models() -> list[dict[str, object]]:
    """
    @brief      Provide the minimum qwen models test helper.
    @return     None.
    @exception  None
    """
    return [
        {
            "model_id": "qwen-base",
            "backend_name": "qwen3-tts-base",
            "status": "healthy",
            "supported_generation_modes": ["clone"],
        },
        {
            "model_id": "qwen-designer",
            "backend_name": "qwen3-tts-voice-designer",
            "status": "healthy",
            "supported_generation_modes": ["voice_design"],
        },
    ]


# END OF FILE
