#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_narration_plan_service.py
@brief Focused tests for the AudioMancer narration-plan persistence helpers.
@details Verifies deterministic prompt derivation, selected voice-language
         persistence, and narrator-copy sample sync behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 1.2.0
"""

# IMPORTS

from audiomancer.services import narration_plan_service, narrator_definition_service, project_workspace_service


def test_build_character_default_prompt_uses_character_profile_fields() -> None:
    """
    @brief      Verify the default character voice prompt includes only the persisted profile facts.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    prompt_text = narration_plan_service.build_character_default_prompt(
        {
            "canonical_name": "Elizabeth",
            "gender_hint": "female",
            "age_band": "adult",
            "role_summary": "noblewoman",
            "description": "careful and observant",
            "temperament": "calm",
            "social_status": "upper class",
            "speaking_style": "measured and precise",
            "accent_or_dialect_hints": "light southern English influence",
            "voice_notes": "warm tone with restrained authority",
        }
    )

    assert "Elizabeth" in prompt_text
    assert "Gender hint: female." in prompt_text
    assert "Speaking style: measured and precise." in prompt_text
    assert "Voice notes: warm tone with restrained authority." in prompt_text
    assert "stable identity" in prompt_text


def test_build_character_default_prompt_prefers_character_owned_voice_definition_prompt() -> None:
    """
    @brief      Verify narration-plan prompt defaults prefer the character-owned voice-definition prompt.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    1.0.0
    """
    prompt_text = narration_plan_service.build_character_default_prompt(
        {
            "canonical_name": "Elizabeth",
            "role_summary": "noblewoman",
            "voice_definition_prompt": "Create a consistent spoken voice for Elizabeth. Warm mezzo tone with restrained authority.",
        }
    )

    assert prompt_text == ("Create a consistent spoken voice for Elizabeth. Warm mezzo tone with restrained authority.")


def test_selected_voice_language_persists(tmp_path) -> None:
    """
    @brief      Verify narration-plan selected voice language is persisted and normalized.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("NarrationPlanLanguage", tmp_path)

    saved_language = narration_plan_service.save_selected_voice_language(project_root, "Romanian")

    assert saved_language == "ro"
    assert narration_plan_service.load_selected_voice_language(project_root) == "ro"


def test_save_target_prompt_persists_preview_text(tmp_path) -> None:
    """
    @brief      Verify saving one narration-plan target also persists the edited preview text.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    project_root, _manifest = _create_project_with_selected_narrator(tmp_path, "NarrationPlanPreviewSave")
    voice_targets = narration_plan_service.sync_voice_plan(
        project_root,
        [{"character_id": "alice", "canonical_name": "Alice"}],
        narrator_definition_service.profile_by_id(
            project_root,
            narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"],
        ),
    )
    target_id = str(voice_targets[1]["target_id"])

    updated_target = narration_plan_service.save_target_prompt(
        project_root,
        target_id,
        "Updated prompt.",
        "First line.\nSecond line.",
    )

    assert updated_target["preview_text"] == "First line.\nSecond line."
    assert (
        narration_plan_service.voice_target_by_id(project_root, target_id)["preview_text"]
        == "First line.\nSecond line."
    )


def test_same_narrator_sync_copies_selected_narrator_sample_to_each_character(tmp_path) -> None:
    """
    @brief      Verify same-narrator mode copies the selected narrator sample into each character target slot.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    project_root, _manifest = _create_project_with_selected_narrator(tmp_path, "NarrationPlanCopy")
    character_targets = [
        {
            "target_id": "character_alice",
            "target_kind": narration_plan_service.TARGET_KIND_CHARACTER,
            "display_name": "Alice",
            "prompt_text": "Prompt one.",
        },
        {
            "target_id": "character_bob",
            "target_kind": narration_plan_service.TARGET_KIND_CHARACTER,
            "display_name": "Bob",
            "prompt_text": "Prompt two.",
        },
    ]

    narration_plan_service.sync_same_narrator_samples(project_root, character_targets, "en")

    for target_payload in character_targets:
        audio_path, metadata_path = narration_plan_service.target_sample_paths(
            project_root, target_payload["target_id"]
        )
        metadata = narration_plan_service.load_target_sample_metadata(project_root, target_payload["target_id"])
        assert audio_path.read_bytes() == b"RIFF-narrator"
        assert metadata_path.is_file()
        assert metadata["sample_source"] == narration_plan_service.SAMPLE_SOURCE_COPIED_NARRATOR
        assert metadata["copied_from_target_id"] == narration_plan_service.TARGET_ID_NARRATOR
        assert metadata["voice_language"] == "en"


def _create_project_with_selected_narrator(tmp_path, name: str):
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-20T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["current_stage"] = "narrator_definition_ready"
    project_workspace_service.save_manifest(manifest, project_root)
    narrator_profile = narrator_definition_service.load_profiles(project_root)[0]
    narrator_definition_service.store_profile_sample(
        project_root,
        narrator_profile,
        "Preview text.",
        {
            "generation_mode": "custom_voice",
            "source_model_id": "qwen-custom",
            "language": "en",
        },
        "Narrator sample ready.",
        b"RIFF-narrator",
    )
    narrator_definition_service.select_narrator_profile(project_root, narrator_profile["profile_id"], "en")
    narrator_definition_service.copy_selected_narrator_sample(project_root, narrator_profile["profile_id"])
    return project_root, manifest


# END OF FILE
