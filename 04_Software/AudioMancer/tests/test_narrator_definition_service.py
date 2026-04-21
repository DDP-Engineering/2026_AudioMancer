#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_narrator_definition_service.py
@brief Focused tests for the AudioMancer narrator-definition service.
@details Verifies seeded Qwen narrator profiles, simplified TTS plan
         persistence, edit-side sample invalidation, and fixed-capability
         generation resolution.
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 3.3.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import narrator_definition_service, project_workspace_service


def test_narrator_service_seeds_builtin_qwen_profiles_without_selection(tmp_path) -> None:
    """
    @brief      Verify new projects start with the built-in Qwen presets and no selected narrator.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorSeedProject", tmp_path)

    profiles = narrator_definition_service.load_profiles(project_root)
    selected_state = narrator_definition_service.load_selected_profile_state(project_root)

    assert [profile["speaker_id"] for profile in profiles] == ["vivian", "serena", "anna"]
    assert all(
        profile["profile_kind"] == narrator_definition_service.NARRATOR_PROFILE_KIND_PRESET for profile in profiles
    )
    assert all(profile["is_selected"] is False for profile in profiles)
    assert selected_state["selected_profile_id"] is None


def test_narrator_service_begin_profile_edit_clears_sample_and_selection(tmp_path) -> None:
    """
    @brief      Verify editing a selected profile deletes its sample and clears the selected state.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorEditProject", tmp_path)
    profile = narrator_definition_service.load_profiles(project_root)[0]
    narrator_definition_service.store_profile_sample(
        project_root,
        profile,
        "Preview text.",
        {
            "generation_mode": "custom_voice",
            "model_id": "qwen-custom",
            "source_model_id": "qwen-custom",
            "speaker_id": "vivian",
            "language": "en",
        },
        "Generated sample.",
        b"RIFF-test-wav",
    )
    narrator_definition_service.select_narrator_profile(project_root, profile["profile_id"], "en")

    updated_profile = narrator_definition_service.begin_profile_edit(project_root, profile["profile_id"])

    assert narrator_definition_service.has_profile_sample(project_root, profile["profile_id"]) is False
    assert narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"] is None
    assert updated_profile["is_selected"] is False


def test_narrator_service_stores_profile_sample_and_copies_selected_narrator_sample(tmp_path) -> None:
    """
    @brief      Verify generated narrator sample artifacts persist per profile
                and copy to the selected narrator folder.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorSampleProject", tmp_path)
    profile = narrator_definition_service.load_profiles(project_root)[0]
    narrator_definition_service.store_profile_sample(
        project_root,
        profile,
        "Preview text for the narrator.",
        {
            "generation_mode": "custom_voice",
            "model_id": "qwen-custom",
            "source_model_id": "qwen-custom",
            "speaker_id": "vivian",
            "language": "en",
        },
        "Voice sample generated.",
        b"RIFF-test-wav",
    )
    narrator_definition_service.select_narrator_profile(project_root, profile["profile_id"], "en")

    copied_metadata = narrator_definition_service.copy_selected_narrator_sample(project_root, profile["profile_id"])
    profile_audio_path, profile_metadata_path = narrator_definition_service.profile_sample_paths(
        project_root,
        profile["profile_id"],
    )
    selected_audio_path, selected_metadata_path = narrator_definition_service.selected_narrator_sample_paths(
        project_root
    )

    assert profile_audio_path.read_bytes() == b"RIFF-test-wav"
    assert json.loads(profile_metadata_path.read_text(encoding="utf-8"))["preview_text"] == (
        "Preview text for the narrator."
    )
    assert copied_metadata is not None
    assert copied_metadata["selected_profile_id"] == profile["profile_id"]
    assert selected_audio_path.read_bytes() == b"RIFF-test-wav"
    assert json.loads(selected_metadata_path.read_text(encoding="utf-8"))["profile_id"] == profile["profile_id"]


def test_narrator_service_simplifies_tts_plan_to_voice_assignment_mode_only(tmp_path) -> None:
    """
    @brief      Verify project-local TTS plans persist only the voice-assignment mode.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorPlanProject", tmp_path)

    persisted_plan = narrator_definition_service.save_tts_plan(
        project_root,
        {
            "voice_assignment_mode": "narrator_and_characters",
            "custom_voice_model_id": "obsolete",
            "definition_model_id": "obsolete",
        },
    )

    assert persisted_plan == {"voice_assignment_mode": "narrator_and_characters"}
    assert narrator_definition_service.load_tts_plan(project_root) == {
        "voice_assignment_mode": "narrator_and_characters"
    }
    assert project_workspace_service.load_manifest(project_root)["voice_assignment_mode"] == "narrator_and_characters"
    assert (project_root / config.NARRATOR_DEFINITION_FOLDER_NAME / "tts_plan.json").exists() is False


def test_narrator_service_profile_generation_request_requires_minimum_qwen_capabilities(tmp_path) -> None:
    """
    @brief      Verify narrator sample generation resolves only when the minimum Qwen capability set is available.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.0.0
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorGenerationProject", tmp_path)
    preset_profile = narrator_definition_service.load_profiles(project_root)[0]
    custom_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "My Narrator",
        "English",
        "Warm and intimate.",
        "Preview text.",
    )

    missing_request = narrator_definition_service.profile_generation_request(
        preset_profile,
        {"voice_assignment_mode": config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE},
        [],
    )
    ready_models = [
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
    preset_request = narrator_definition_service.profile_generation_request(
        preset_profile,
        {"voice_assignment_mode": config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE},
        ready_models,
    )
    custom_request = narrator_definition_service.profile_generation_request(
        custom_profile,
        {"voice_assignment_mode": config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE},
        ready_models,
    )

    assert missing_request["can_generate"] is False
    assert "base" in missing_request["unavailable_reason"]
    assert preset_request["generation_mode"] == "custom_voice"
    assert preset_request["speaker_id"] == "vivian"
    assert preset_request["language"] == "en"
    assert custom_request["generation_mode"] == "definition"
    assert custom_request["model_id"] == "qwen-designer"


def test_narrator_service_normalizes_language_labels_to_runtime_codes(tmp_path) -> None:
    """
    @brief      Verify narrator profile storage normalizes legacy language labels into VoiceWeaver language codes.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorLanguageProject", tmp_path)

    created_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "My Narrator",
        "Romanian",
        "Prompt.",
        "Preview text.",
    )
    selected_state = narrator_definition_service.select_narrator_profile(
        project_root,
        created_profile["profile_id"],
        "Romanian",
    )

    assert created_profile["language"] == "ro"
    assert narrator_definition_service.load_profiles(project_root)[-1]["language"] == "ro"
    assert selected_state["selected_language"] == "ro"
    assert narrator_definition_service.narrator_language_label("ro") == "Romanian"


def test_narrator_service_restores_missing_builtin_qwen_presets_on_load(tmp_path) -> None:
    """
    @brief      Verify loading narrator profiles restores missing built-in Qwen presets.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorRepairProject", tmp_path)
    profiles_path = project_root / config.NARRATOR_DEFINITION_FOLDER_NAME / config.NARRATOR_PROFILE_FILE_NAME
    persisted_profiles = narrator_definition_service.load_profiles(project_root)
    repaired_payload = [profile for profile in persisted_profiles if profile["profile_id"] != "qwen_preset_serena"]
    profiles_path.write_text(json.dumps(repaired_payload, indent=2), encoding="utf-8")

    repaired_profiles = narrator_definition_service.load_profiles(project_root)

    assert [profile["profile_id"] for profile in repaired_profiles[:3]] == [
        "qwen_preset_vivian",
        "qwen_preset_serena",
        "qwen_preset_anna",
    ]


def test_narrator_service_runtime_qwen_presets_are_not_protected(tmp_path) -> None:
    """
    @brief      Verify runtime-synced Qwen presets stay deletable and are not normalized into protected built-ins.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorRuntimePresetProject", tmp_path)

    narrator_definition_service.sync_runtime_qwen_presets(
        project_root,
        [
            {
                "model_id": "qwen-custom",
                "backend_name": "qwen3-tts-customvoice",
                "status": "healthy",
                "supported_generation_modes": ["custom_voice"],
                "supported_presets": ["vivian", "warm_reflective"],
            }
        ],
    )

    runtime_profile = narrator_definition_service.profile_by_id(project_root, "qwen_preset_warm_reflective")

    assert runtime_profile is not None
    assert runtime_profile["profile_origin"] == narrator_definition_service.NARRATOR_PROFILE_ORIGIN_QWEN_RUNTIME
    assert runtime_profile["protected"] is False


def test_narrator_service_migrates_legacy_customvoice_seed_profiles_to_custom_profiles(tmp_path) -> None:
    """
    @brief      Verify legacy prompt-seed preset profiles are migrated into editable custom narrator profiles.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorLegacySeedProject", tmp_path)
    profiles_path = project_root / config.NARRATOR_DEFINITION_FOLDER_NAME / config.NARRATOR_PROFILE_FILE_NAME
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

    migrated_profile = narrator_definition_service.profile_by_id(
        project_root,
        "preset_qwen_customvoice_warm_reflective_narrator",
    )
    generation_request = narrator_definition_service.profile_generation_request(
        migrated_profile or {},
        {"voice_assignment_mode": config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE},
        [
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
        ],
    )

    assert migrated_profile is not None
    assert migrated_profile["profile_kind"] == narrator_definition_service.NARRATOR_PROFILE_KIND_CUSTOM
    assert (
        migrated_profile["profile_origin"]
        == narrator_definition_service.NARRATOR_PROFILE_ORIGIN_LEGACY_CUSTOMVOICE_SEED
    )
    assert (
        migrated_profile["provider_family"] == narrator_definition_service.NARRATOR_PROVIDER_FAMILY_QWEN_VOICE_DESIGNER
    )
    assert migrated_profile["editable"] is True
    assert migrated_profile["protected"] is False
    assert generation_request["can_generate"] is True
    assert generation_request["generation_mode"] == "definition"


# END OF FILE
