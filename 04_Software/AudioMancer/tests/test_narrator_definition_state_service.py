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
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 3.4.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import (
    narrator_definition_service,
    narrator_definition_state_service,
    project_workspace_service,
)


def test_narrator_state_service_exposes_project_languages_and_no_default_selection(tmp_path) -> None:
    """
    @brief      Verify narrator state shows original and translated languages and starts with no selected profile.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.2.0
    """
    project_root, manifest = _create_project(tmp_path, "NarratorStateProject")
    manifest["original_language"] = "Italian"
    project_workspace_service.save_manifest(manifest, project_root)
    translation_report_path = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.TRANSLATION_REPORT_FILE_NAME
    )
    translation_report_path.parent.mkdir(parents=True, exist_ok=True)
    translation_report_path.write_text(
        json.dumps({"target_language": "ro", "total_chunk_count": 1, "approved_chunk_count": 1}, indent=2) + "\n",
        encoding="utf-8",
    )

    state = narrator_definition_state_service.build_narrator_definition_state(project_root, manifest, "en")

    assert state["selected_profile_id"] is None
    assert state["original_language"] == "Italian"
    assert state["translated_language"] == "Romanian"
    assert state["effective_language"] == "it"
    assert state["selected_voice_language"] == "it"
    assert state["language_entries"] == [("Italian", "it"), ("Romanian", "ro")]
    assert state["can_select"] is False


def test_narrator_state_service_uses_cleanup_detected_original_language_when_manifest_is_empty(tmp_path) -> None:
    """
    @brief      Verify narrator state falls back to cleanup-detected language when manifest language is empty.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
    """
    project_root, manifest = _create_project(tmp_path, "NarratorStateCleanupLanguageProject")
    cleanup_report_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANUP_REPORT_FILE_NAME
    cleanup_report_path.parent.mkdir(parents=True, exist_ok=True)
    cleanup_report_path.write_text(
        json.dumps({"detected_language": "it"}, indent=2) + "\n",
        encoding="utf-8",
    )

    state = narrator_definition_state_service.build_narrator_definition_state(project_root, manifest, "en")

    assert state["original_language"] == "Italian"
    assert state["effective_language"] == "it"
    assert state["selected_voice_language"] == "it"


def test_narrator_state_service_marks_sampled_custom_profile_selectable(tmp_path) -> None:
    """
    @brief      Verify a sampled inspected profile can be selected when it is not already selected.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    project_root, manifest = _create_project(tmp_path, "NarratorStateCustomProject")
    custom_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "My Custom Narrator",
        "English",
        "Custom prompt.",
        "Preview text.",
    )
    narrator_definition_service.store_profile_sample(
        project_root,
        custom_profile,
        "Preview text.",
        {
            "generation_mode": "definition",
            "model_id": "qwen-designer",
            "source_model_id": "qwen-designer",
            "speaker_id": None,
            "language": "en",
        },
        "Generated custom sample.",
        b"RIFF-custom",
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
    assert state["preview_available"] is True


def test_narrator_state_service_status_lines_show_counts_and_qwen_readiness(tmp_path) -> None:
    """
    @brief      Verify narrator status lines summarize profile counts and Qwen readiness.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    project_root, manifest = _create_project(tmp_path, "NarratorStateStatusProject")
    profiles = narrator_definition_service.load_profiles(project_root)
    narrator_definition_service.store_profile_sample(
        project_root,
        profiles[0],
        "Preview text.",
        {
            "generation_mode": "custom_voice",
            "model_id": "qwen-custom",
            "source_model_id": "qwen-custom",
            "speaker_id": "vivian",
            "language": "en",
        },
        "Generated preset sample.",
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
        inspected_profile_id=profiles[0]["profile_id"],
    )

    assert "Profiles: 3" in state["status_lines"]
    assert "Profiles with samples: 1" in state["status_lines"]
    assert "Selected profiles: 0" in state["status_lines"]
    assert "Qwen3 TTS readiness: ready" in state["status_lines"]


def test_narrator_state_service_syncs_all_runtime_qwen_presets(tmp_path) -> None:
    """
    @brief      Verify narrator state adds all runtime-reported Qwen CustomVoice presets to the project profile list.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    project_root, manifest = _create_project(tmp_path, "NarratorStateRuntimePresetProject")

    state = narrator_definition_state_service.build_narrator_definition_state(
        project_root,
        manifest,
        "en",
        {
            "tts_runtime_probe_succeeded": True,
            "tts_runtime_discovered_models": _runtime_qwen_models_with_extended_presets(),
        },
    )

    assert len(state["profiles"]) == 5
    assert [profile["speaker_id"] for profile in state["profiles"][:5]] == [
        "vivian",
        "serena",
        "anna",
        "aiden",
        "uncle_fu",
    ]


def test_narrator_state_service_legacy_default_custom_profile_is_deletable(tmp_path) -> None:
    """
    @brief      Verify legacy non-Qwen protected custom profiles are normalized into deletable custom profiles.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    project_root, manifest = _create_project(tmp_path, "NarratorStateLegacyDefaultProject")
    profiles_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.NARRATOR_PROFILE_FILE_NAME
    profiles_path.write_text(
        json.dumps(
            [
                {
                    "profile_id": "default_narrator_profile",
                    "display_name": "Default1",
                    "language": "en",
                    "prompt_text": "Warm narrator prompt.",
                    "profile_kind": "custom",
                    "profile_origin": "default_custom",
                    "provider_family": "project_default",
                    "editable": True,
                    "protected": True,
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    state = narrator_definition_state_service.build_narrator_definition_state(
        project_root,
        manifest,
        "en",
        inspected_profile_id="default_narrator_profile",
    )

    assert state["current_profile_id"] == "default_narrator_profile"
    assert state["can_delete"] is True


def test_narrator_state_service_legacy_customvoice_seed_profile_is_deletable_and_generatable(tmp_path) -> None:
    """
    @brief      Verify legacy prompt-seed narrator profiles are exposed as
                deletable custom profiles with sample generation enabled.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    project_root, manifest = _create_project(tmp_path, "NarratorStateLegacySeedProject")
    profiles_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.NARRATOR_PROFILE_FILE_NAME
    profiles_path.write_text(
        json.dumps(
            [
                {
                    "profile_id": "preset_qwen_customvoice_warm_reflective_narrator",
                    "display_name": "Warm Reflective Narrator",
                    "language": "en",
                    "prompt_text": "Warm reflective narrator prompt.",
                    "profile_kind": "preset",
                    "profile_origin": "qwen_builtin_preset",
                    "provider_family": "qwen3_tts_customvoice_seed",
                    "editable": False,
                    "protected": True,
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    state = narrator_definition_state_service.build_narrator_definition_state(
        project_root,
        manifest,
        "en",
        {
            "tts_runtime_probe_succeeded": True,
            "tts_runtime_discovered_models": _minimum_qwen_models(),
        },
        inspected_profile_id="preset_qwen_customvoice_warm_reflective_narrator",
    )

    assert state["current_profile_id"] == "preset_qwen_customvoice_warm_reflective_narrator"
    assert state["is_preset"] is False
    assert state["can_edit"] is True
    assert state["can_delete"] is True
    assert state["can_generate"] is True


def _create_project(tmp_path, name: str):
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
    return [
        {
            "model_id": "qwen-base",
            "backend_name": "qwen3-tts-base",
            "status": "healthy",
            "supported_generation_modes": ["clone"],
            "supported_presets": [],
        },
        {
            "model_id": "qwen-designer",
            "backend_name": "qwen3-tts-voice-designer",
            "status": "healthy",
            "supported_generation_modes": ["definition"],
            "supported_presets": [],
        },
        {
            "model_id": "qwen-custom",
            "backend_name": "qwen3-tts-customvoice",
            "status": "healthy",
            "supported_generation_modes": ["custom_voice"],
            "supported_presets": ["vivian", "serena", "anna"],
        },
    ]


def _runtime_qwen_models_with_extended_presets() -> list[dict[str, object]]:
    models = _minimum_qwen_models()
    models[2]["supported_presets"] = ["vivian", "serena", "anna", "aiden", "uncle_fu"]
    return models


# END OF FILE
