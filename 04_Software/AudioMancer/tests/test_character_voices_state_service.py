#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_character_voices_state_service.py
@brief Focused tests for the AudioMancer Character Voices page state helpers.
@details Verifies narrator-first target ordering, translation-language
         selection rules, same-narrator shaping, and missing-sample warnings.
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 1.3.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import (
    character_discovery_service,
    character_voices_service,
    character_voices_state_service,
    narrator_definition_service,
    project_workspace_service,
)


def test_state_contains_narrator_first_and_approved_translated_language(tmp_path) -> None:
    """
    @brief      Verify narrator-first Character Voices state and approved translated language display.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    project_root, manifest = _create_project_with_narrator_and_character(tmp_path, "CharacterVoicesState")
    manifest["original_language"] = "de"
    manifest["target_language"] = "ro"
    manifest["selected_voice_language"] = "ro"
    manifest["project_options_locked"] = True
    project_workspace_service.save_manifest(manifest, project_root)
    translation_report_path = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.TRANSLATION_REPORT_FILE_NAME
    )
    translation_report_path.write_text(
        json.dumps(
            {
                "target_language": "ro",
                "total_chunk_count": 2,
                "approved_chunk_count": 2,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    state = character_voices_state_service.build_character_voices_state(
        project_root,
        project_workspace_service.load_manifest(project_root),
        "en",
        {
            "tts_runtime_probe_succeeded": True,
            "tts_runtime_discovered_models": _minimum_qwen_models(),
        },
        inspected_target_id="character_alice",
        initialize_defaults=True,
    )

    assert [target["target_kind"] for target in state["targets"][:2]] == ["narrator", "character"]
    assert state["original_language"] == "German"
    assert state["translated_language"] == "Romanian"
    assert state["language_entries"] == [("Romanian", "ro")]
    assert state["targets"][0]["can_edit_prompt"] is False
    assert state["targets"][1]["preview_text"]
    assert state["targets"][1]["preview_text"] == state["preview_text"]


def test_state_initializes_character_preview_text_from_locked_voice_language(tmp_path) -> None:
    """
    @brief      Verify first Character Voices access seeds character previews with the project voice language.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.2.0
    """
    project_root, manifest = _create_project_with_narrator_and_character(
        tmp_path,
        "CharacterVoicesFrenchPreview",
    )
    manifest["target_language"] = "fr"
    manifest["selected_voice_language"] = "fr"
    manifest["project_options_locked"] = True
    project_workspace_service.save_manifest(manifest, project_root)

    state = character_voices_state_service.build_character_voices_state(
        project_root,
        project_workspace_service.load_manifest(project_root),
        "en",
        {
            "tts_runtime_probe_succeeded": True,
            "tts_runtime_discovered_models": _minimum_qwen_models(),
        },
        inspected_target_id="character_alice",
        initialize_defaults=True,
    )

    expected_preview_text = character_voices_service.preview_text_for_language("fr")
    persisted_target = character_voices_service.voice_target_by_id(project_root, "character_alice")
    assert state["selected_voice_language"] == "fr"
    assert state["preview_text"] == expected_preview_text
    assert persisted_target is not None
    assert persisted_target["preview_text"] == expected_preview_text


def test_state_same_narrator_mode_disables_character_edit_and_generate(tmp_path) -> None:
    """
    @brief      Verify same-narrator mode disables per-character editing and auto-creates copied samples.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    project_root, manifest = _create_project_with_narrator_and_character(
        tmp_path,
        "CharacterVoicesSameNarrator",
        voice_assignment_mode="same_narrator",
    )

    state = character_voices_state_service.build_character_voices_state(
        project_root,
        manifest,
        "en",
        {
            "tts_runtime_probe_succeeded": True,
            "tts_runtime_discovered_models": _minimum_qwen_models(),
        },
        inspected_target_id="character_alice",
        initialize_defaults=True,
    )

    assert state["can_edit_prompt"] is False
    assert state["can_generate_sample"] is False
    assert state["preview_available"] is True
    assert state["preview_text"]
    assert any("same narrator voice" in note for note in state["notes"])


def test_state_missing_narrator_sample_surfaces_warning(tmp_path) -> None:
    """
    @brief      Verify missing Narator Voice samples surface a warning.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.1
    """
    project_root, manifest = _create_project_with_narrator_and_character(
        tmp_path,
        "CharacterVoicesMissingNarratorSample",
        store_narrator_sample=False,
    )

    state = character_voices_state_service.build_character_voices_state(
        project_root,
        manifest,
        "en",
        {
            "tts_runtime_probe_succeeded": True,
            "tts_runtime_discovered_models": _minimum_qwen_models(),
        },
        initialize_defaults=True,
    )

    assert state["missing_narrator_sample"] is True
    assert any("narator voice sample" in note.lower() for note in state["notes"])


def _create_project_with_narrator_and_character(
    tmp_path,
    name: str,
    voice_assignment_mode: str = "narrator_and_characters",
    store_narrator_sample: bool = True,
):
    """
    @brief      Provide the create project with narrator and character test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-20T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["current_stage"] = "narrator_definition_ready"
    manifest["voice_assignment_mode"] = voice_assignment_mode
    project_workspace_service.save_manifest(manifest, project_root)

    narrator_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Test Narrator",
        "English",
        "Warm narrator prompt.",
        "Preview text.",
    )
    if store_narrator_sample:
        narrator_definition_service.store_profile_sample(
            project_root,
            narrator_profile,
            "Preview text.",
            {
                "generation_mode": "definition",
                "source_model_id": "qwen-designer",
                "language": "en",
            },
            "Narator voice sample ready.",
            b"RIFF-narrator",
        )
    narrator_definition_service.select_narrator_profile(project_root, narrator_profile["profile_id"], "en")
    if store_narrator_sample:
        narrator_definition_service.copy_selected_narrator_sample(project_root, narrator_profile["profile_id"])

    character_discovery_service.add_character_profile(project_root, "Alice")
    alice_profile = character_discovery_service.load_character_profiles(project_root)[0]
    character_discovery_service.update_character_profile(
        project_root,
        {
            **dict(alice_profile),
            "canonical_name": "Alice",
            "gender_hint": "female",
            "voice_definition_prompt": "A gentle female voice for Alice.",
        },
    )
    return project_root, project_workspace_service.load_manifest(project_root)


def _minimum_qwen_models() -> list[dict[str, object]]:
    """
    @brief      Provide the minimum qwen models test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    return [
        {
            "model_id": "qwen-base",
            "backend_name": "qwen3-tts-base",
            "status": "healthy",
            "supported_generation_modes": ["base", "clone"],
        },
        {
            "model_id": "qwen-designer",
            "backend_name": "qwen3-tts-voice-designer",
            "status": "healthy",
            "supported_generation_modes": ["definition", "voice_designer"],
        },
    ]


# END OF FILE
