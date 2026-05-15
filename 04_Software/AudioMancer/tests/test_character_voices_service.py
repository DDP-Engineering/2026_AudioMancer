#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_character_voices_service.py
@brief Focused tests for the AudioMancer Character Voices persistence helpers.
@details Verifies deterministic prompt derivation, selected voice-language
         persistence, and narrator-copy sample sync behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 1.8.0
"""

# IMPORTS

from pathlib import Path
import wave

from audiomancer.services import character_voices_service, narrator_definition_service, project_workspace_service


def test_build_character_default_prompt_uses_compact_character_profile() -> None:
    """
    @brief      Verify the default character voice prompt uses the compact persisted profile.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    2.1.0
    """
    prompt_text = character_voices_service.build_character_default_prompt(
        {
            "canonical_name": "Elizabeth",
            "gender_hint": "female",
            "age_hint": "young adult",
        }
    )

    assert "Elizabeth" in prompt_text
    assert "Sex/Gender: female." in prompt_text
    assert "Age Domain: young adult." in prompt_text
    assert "stable identity" in prompt_text


def test_build_character_default_prompt_prefers_character_owned_voice_definition_prompt() -> None:
    """
    @brief      Verify Character Voices prompt defaults preserve character-owned prompts and add sex/gender.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    1.2.0
    """
    prompt_text = character_voices_service.build_character_default_prompt(
        {
            "canonical_name": "Elizabeth",
            "gender_hint": "female",
            "age_hint": "young adult",
            "voice_definition_prompt": (
                "Create a consistent spoken voice for Elizabeth. Warm mezzo tone with restrained authority."
            ),
        }
    )

    assert prompt_text.startswith(
        "Create a consistent spoken voice for Elizabeth. Warm mezzo tone with restrained authority."
    )
    assert "Sex/Gender: female." in prompt_text
    assert "Age Domain: young adult." in prompt_text


def test_build_character_default_prompt_prevents_male_default_when_gender_is_unknown() -> None:
    """
    @brief      Verify every character prompt carries explicit non-male-default guidance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    prompt_text = character_voices_service.build_character_default_prompt(
        {
            "canonical_name": "Ayla",
            "voice_definition_prompt": "Give Ayla a steady adult voice with medium pitch and clear articulation.",
        }
    )

    assert "Sex/Gender: not specified in the source." in prompt_text
    assert "do not default to a male voice" in prompt_text


def test_build_character_default_prompt_prevents_young_default_when_age_is_unknown() -> None:
    """
    @brief      Verify every character prompt carries explicit unknown-age guidance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    prompt_text = character_voices_service.build_character_default_prompt(
        {
            "canonical_name": "Ayla",
            "voice_definition_prompt": "Give Ayla a steady adult voice with medium pitch and clear articulation.",
        }
    )

    assert "Age Domain: not specified in the source." in prompt_text
    assert "do not default to a young voice" in prompt_text


def test_build_character_default_prompt_preserves_existing_age_instruction() -> None:
    """
    @brief      Verify default prompt backfill does not duplicate explicit age-domain guidance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    prompt_text = character_voices_service.build_character_default_prompt(
        {
            "canonical_name": "Mentor",
            "age_hint": "old",
            "voice_definition_prompt": "Create a consistent spoken voice. Age Domain: old. Calm and weathered.",
        }
    )

    assert prompt_text.count("Age Domain:") == 1


def test_selected_voice_language_persists(tmp_path) -> None:
    """
    @brief      Verify Character Voices selected voice language is persisted and normalized.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("CharacterVoicesLanguage", tmp_path)

    saved_language = character_voices_service.save_selected_voice_language(project_root, "Romanian")

    assert saved_language == "ro"
    assert character_voices_service.load_selected_voice_language(project_root) == "ro"


def test_preview_text_covers_qwen3_tts_languages_with_chinese() -> None:
    """
    @brief      Verify deterministic preview text exists for every supported voice language.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
    """
    for language_code in ("en", "ro", "ja", "ko", "zh", "de", "fr", "ru", "pt", "es", "it"):
        assert character_voices_service.preview_text_for_language(language_code)


def test_save_target_prompt_persists_preview_text(tmp_path) -> None:
    """
    @brief      Verify saving one Character Voices target also persists the edited preview text.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    project_root, _manifest = _create_project_with_selected_narrator(tmp_path, "CharacterVoicesPreviewSave")
    voice_targets = character_voices_service.sync_voice_plan(
        project_root,
        [{"character_id": "alice", "canonical_name": "Alice"}],
        narrator_definition_service.profile_by_id(
            project_root,
            narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"],
        ),
    )
    target_id = str(voice_targets[1]["target_id"])

    updated_target = character_voices_service.save_target_prompt(
        project_root,
        target_id,
        "Updated prompt.",
        "First line.\nSecond line.",
    )

    assert updated_target["preview_text"] == "First line.\nSecond line."
    assert (
        character_voices_service.voice_target_by_id(project_root, target_id)["preview_text"]
        == "First line.\nSecond line."
    )


def test_import_target_sample_persists_character_sample_metadata(tmp_path) -> None:
    """
    @brief      Verify imported character samples persist audio, transcript, and clone-ready metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    project_root, _manifest = _create_project_with_selected_narrator(tmp_path, "CharacterVoicesImport")
    source_sample = tmp_path / "alice_voice.wav"
    _write_import_test_wav(source_sample)
    voice_targets = character_voices_service.sync_voice_plan(
        project_root,
        [{"character_id": "alice", "canonical_name": "Alice"}],
        narrator_definition_service.profile_by_id(
            project_root,
            narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"],
        ),
    )
    target_payload = voice_targets[1]

    metadata = character_voices_service.import_target_sample(
        project_root,
        target_payload,
        "en",
        "This is the exact Alice sample text.",
        source_sample,
    )
    audio_path, _metadata_path = character_voices_service.target_sample_paths(project_root, target_payload["target_id"])

    assert audio_path.read_bytes() == source_sample.read_bytes()
    assert metadata["sample_source"] == "imported_sample"
    assert metadata["generation_mode"] == "imported_sample"
    assert metadata["source_model_id"] is None
    assert metadata["preview_text"] == "This is the exact Alice sample text."
    assert character_voices_service.has_target_sample(project_root, target_payload["target_id"]) is True
    assert character_voices_service.sample_runtime_available(metadata, []) is True


def test_sync_voice_plan_uses_character_discovery_preview_text(tmp_path) -> None:
    """
    @brief      Verify new character voice targets use discovered spoken-dialogue preview text.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    project_root, _manifest = _create_project_with_selected_narrator(tmp_path, "CharacterVoicesDiscoveryPreview")
    discovered_preview_text = (
        "Stay close to me while the storm passes over the harbor. "
        "When the lamps are lit, we will cross the square together."
    )

    voice_targets = character_voices_service.sync_voice_plan(
        project_root,
        [
            {
                "character_id": "alice",
                "canonical_name": "Alice",
                "preview_text": discovered_preview_text,
            }
        ],
        narrator_definition_service.profile_by_id(
            project_root,
            narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"],
        ),
    )

    assert voice_targets[1]["preview_text"] == discovered_preview_text


def test_sync_voice_plan_refreshes_unedited_prompt_with_explicit_gender(tmp_path) -> None:
    """
    @brief      Verify target sync backfills sex/gender guidance into existing unedited prompts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, _manifest = _create_project_with_selected_narrator(tmp_path, "CharacterVoicesGenderSync")
    old_prompt = "Give Ayla a steady adult voice with medium pitch and clear articulation."
    character_voices_service.save_voice_targets(
        project_root,
        [
            {
                "target_id": "character_ayla",
                "target_kind": character_voices_service.TARGET_KIND_CHARACTER,
                "display_name": "Ayla",
                "character_id": "ayla",
                "prompt_text": old_prompt,
                "default_prompt_text": old_prompt,
                "preview_text": "Preview.",
                "editable": True,
            }
        ],
    )

    targets = character_voices_service.sync_voice_plan(
        project_root,
        [
            {
                "character_id": "ayla",
                "canonical_name": "Ayla",
                "gender_hint": "female",
                "voice_definition_prompt": old_prompt,
            }
        ],
        None,
    )

    assert targets[0]["prompt_text"].startswith(old_prompt)
    assert "Sex/Gender: female." in str(targets[0]["prompt_text"])
    assert targets[0]["default_prompt_text"] == targets[0]["prompt_text"]


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
    project_root, _manifest = _create_project_with_selected_narrator(tmp_path, "CharacterVoicesCopy")
    character_targets = [
        {
            "target_id": "character_alice",
            "target_kind": character_voices_service.TARGET_KIND_CHARACTER,
            "display_name": "Alice",
            "prompt_text": "Prompt one.",
        },
        {
            "target_id": "character_bob",
            "target_kind": character_voices_service.TARGET_KIND_CHARACTER,
            "display_name": "Bob",
            "prompt_text": "Prompt two.",
        },
    ]

    character_voices_service.sync_same_narrator_samples(project_root, character_targets, "en")

    for target_payload in character_targets:
        audio_path, metadata_path = character_voices_service.target_sample_paths(
            project_root, target_payload["target_id"]
        )
        metadata = character_voices_service.load_target_sample_metadata(project_root, target_payload["target_id"])
        assert audio_path.read_bytes() == b"RIFF-narrator"
        assert metadata_path.is_file()
        assert metadata["sample_source"] == character_voices_service.SAMPLE_SOURCE_COPIED_NARRATOR
        assert metadata["copied_from_target_id"] == character_voices_service.TARGET_ID_NARRATOR
        assert metadata["voice_language"] == "en"


def _create_project_with_selected_narrator(tmp_path, name: str):
    """
    @brief      Provide the create project with selected narrator test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
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
    project_workspace_service.save_manifest(manifest, project_root)
    narrator_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Test Narrator",
        "English",
        "Narrator prompt.",
        "Preview text.",
    )
    narrator_definition_service.store_profile_sample(
        project_root,
        narrator_profile,
        "Preview text.",
        {
            "generation_mode": "definition",
            "source_model_id": "qwen-designer",
            "language": "en",
        },
        "Narrator sample ready.",
        b"RIFF-narrator",
    )
    narrator_definition_service.select_narrator_profile(project_root, narrator_profile["profile_id"], "en")
    narrator_definition_service.copy_selected_narrator_sample(project_root, narrator_profile["profile_id"])
    return project_root, manifest


def _write_import_test_wav(path: Path) -> None:
    """
    @brief      Write one valid imported-sample WAV fixture.
    @param[in]  path Output path.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    sample_rate = 16_000
    frame_count = int(sample_rate * 3.2)
    frame = (4000).to_bytes(2, byteorder="little", signed=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frame * frame_count)


# END OF FILE
