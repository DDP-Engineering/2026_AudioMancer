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
         persistence, atomic sample writes, and narrator-copy sample sync behavior.
"""

# IMPORTS

import json
from pathlib import Path
import wave

import pytest

from audiomancer import config
from audiomancer.services import (
    character_voices_service,
    narrator_definition_service,
    project_workspace_service,
    tts_budget_service,
)


def test_build_character_default_prompt_uses_compact_character_profile() -> None:
    """
    @brief      Verify the default character voice prompt uses the compact persisted profile.
    @return     None.
    @exception  None
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
    """
    project_root, _manifest = project_workspace_service.create_project("CharacterVoicesLanguage", tmp_path)

    saved_language = character_voices_service.save_selected_voice_language(project_root, "Romanian")

    assert saved_language == "ro"
    assert character_voices_service.load_selected_voice_language(project_root) == "ro"


def test_selected_voice_language_preserves_locked_manifest_language(tmp_path) -> None:
    """
    @brief      Verify a locked valid manifest rejects a different Character Voices language.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("CharacterVoicesLockedLanguage", tmp_path)
    manifest["target_language"] = "en"
    manifest["selected_voice_language"] = "en"
    manifest["project_options_locked"] = True
    project_workspace_service.save_manifest(manifest, project_root)
    manifest_path = project_root / "project.json"
    original_manifest_bytes = manifest_path.read_bytes()

    saved_language = character_voices_service.save_selected_voice_language(project_root, "Romanian")

    assert saved_language == "en"
    assert manifest_path.read_bytes() == original_manifest_bytes


def test_selected_voice_language_keeps_missing_manifest_fallback(tmp_path) -> None:
    """
    @brief      Verify a genuinely missing manifest keeps the compatible language fallback and target initialization.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "missing-manifest-project"
    project_root.mkdir()

    saved_language = character_voices_service.save_selected_voice_language(project_root, "Romanian")

    assert saved_language == "ro"
    assert (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).is_file()
    assert (project_root / "project.json").exists() is False


def test_selected_voice_language_rejects_corrupt_manifest_before_target_initialization(tmp_path) -> None:
    """
    @brief      Verify a corrupt manifest cannot report a language save or create Character Voices state.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("CharacterVoicesCorruptManifest", tmp_path)
    manifest_path = project_root / "project.json"
    corrupt_manifest_bytes = b"{corrupt project manifest"
    manifest_path.write_bytes(corrupt_manifest_bytes)
    targets_path = project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME
    assert targets_path.exists() is False

    with pytest.raises(ValueError):
        character_voices_service.save_selected_voice_language(project_root, "Romanian")

    assert manifest_path.read_bytes() == corrupt_manifest_bytes
    assert targets_path.exists() is False


@pytest.mark.parametrize("manifest_failure", [PermissionError("manifest denied"), RuntimeError("unexpected load")])
def test_selected_voice_language_does_not_swallow_manifest_failures(
    monkeypatch,
    tmp_path,
    manifest_failure: Exception,
) -> None:
    """
    @brief      Verify manifest filesystem and unexpected failures propagate before target initialization.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  manifest_failure Injected manifest load failure.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "manifest-failure-project"
    project_root.mkdir()
    targets_path = project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME

    def _raise_manifest_failure(_project_root) -> None:
        """Raise the selected manifest load failure."""
        raise manifest_failure

    monkeypatch.setattr(project_workspace_service, "load_manifest", _raise_manifest_failure)

    with pytest.raises(type(manifest_failure), match=str(manifest_failure)):
        character_voices_service.save_selected_voice_language(project_root, "Romanian")

    assert targets_path.exists() is False


def test_character_voices_targets_use_atomic_json_writer(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-014 persists Character Voices target JSON atomically.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("CharacterVoicesAtomicJson", tmp_path)
    character_voices_service.ensure_character_voices_files(project_root)
    observed_paths: list[Path] = []

    def _capture_atomic_write(target_path, payload, **_kwargs) -> None:
        """
        @brief      Capture one atomic Character Voices JSON write.
        @param[in]  target_path Candidate JSON target path.
        @param[in]  payload JSON payload.
        @return     None.
        """
        observed_paths.append(Path(target_path))
        Path(target_path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr(character_voices_service, "write_json_atomic", _capture_atomic_write, raising=False)

    character_voices_service.save_voice_targets(
        project_root,
        [
            {
                "target_id": "character_alice",
                "target_kind": character_voices_service.TARGET_KIND_CHARACTER,
                "display_name": "Alice",
            }
        ],
    )

    assert observed_paths == [project_root / "characters_voice.json"]


def test_preview_text_covers_supported_translation_targets_only() -> None:
    """
    @brief      Verify deterministic preview text exists for every supported voice language.
    @return     None.
    @exception  None
    """
    for language_code in ("en", "ro", "de", "fr", "ru", "pt", "es", "it"):
        assert character_voices_service.preview_text_for_language(language_code)
    assert all(
        language_code not in character_voices_service.DEFAULT_PREVIEW_TEXT_BY_LANGUAGE
        for language_code in ("ja", "ko", "zh")
    )


def test_save_target_prompt_persists_preview_text(tmp_path) -> None:
    """
    @brief      Verify saving one Character Voices target also persists the edited preview text.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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


def test_character_voices_readiness_rejects_empty_target_list(tmp_path) -> None:
    """
    @brief      Verify Character Voices readiness requires non-empty persisted target evidence.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project_with_selected_narrator(tmp_path, "CharacterVoicesEmptyReadiness")

    assert character_voices_service.character_voices_is_ready(project_root, []) is False


def test_character_sample_audio_uses_atomic_byte_writer(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-014 persists generated character sample WAV bytes atomically.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project_with_selected_narrator(tmp_path, "CharacterVoicesAtomicBytes")
    target_payload = character_voices_service.sync_voice_plan(
        project_root,
        [{"character_id": "alice", "canonical_name": "Alice"}],
        narrator_definition_service.profile_by_id(
            project_root,
            narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"],
        ),
    )[1]
    observed_payloads: list[bytes] = []

    def _capture_byte_write(target_path, payload) -> None:
        """
        @brief      Capture one atomic byte persistence request while writing the payload for assertions.
        @param[in]  target_path Final sample path.
        @param[in]  payload Complete WAV payload.
        @return     None.
        """
        observed_payloads.append(bytes(payload))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(payload)

    monkeypatch.setattr(character_voices_service, "write_bytes_atomic", _capture_byte_write)

    character_voices_service.store_target_sample(
        project_root,
        target_payload,
        "en",
        "Preview text.",
        {
            "generation_mode": "definition",
            "source_model_id": "qwen-designer",
        },
        "Character sample ready.",
        b"RIFF-character",
    )

    assert observed_payloads == [b"RIFF-character"]


def test_character_sample_names_follow_ids(tmp_path) -> None:
    """@brief Keep two sample pairs distinct when their names normalize identically."""
    targets = character_voices_service.sync_voice_plan(
        tmp_path,
        [
            {"character_id": "ana_one", "canonical_name": "Ana-Maria"},
            {"character_id": "ana_two", "canonical_name": "Ana Maria"},
        ],
        None,
    )
    characters = [target for target in targets if target["target_kind"] == "character"]
    for target in characters:
        target_id = str(target["target_id"])
        character_voices_service.store_target_sample(tmp_path, target, "en", target_id, {}, "", target_id.encode())

    for target in characters:
        target_id = str(target["target_id"])
        audio, _ = character_voices_service.target_sample_paths(tmp_path, target_id)
        assert target_id in audio.name
        assert audio.read_bytes() == target_id.encode()
        assert character_voices_service.load_target_sample_metadata(tmp_path, target_id)["preview_text"] == target_id


@pytest.mark.parametrize("source", ["generated", "imported"])
def test_character_sample_publication_restores_pair_on_document_failure(monkeypatch, tmp_path, source) -> None:
    """@brief Restore the old WAV and transcript if publication fails after the new WAV is installed."""
    targets = character_voices_service.sync_voice_plan(
        tmp_path, [{"character_id": "alice", "canonical_name": "Alice"}], None
    )
    target = next(target for target in targets if target["target_kind"] == "character")
    target_id = str(target["target_id"])
    character_voices_service.store_target_sample(tmp_path, target, "en", "Old transcript.", {}, "", b"RIFF-old")
    audio, document = character_voices_service.target_sample_paths(tmp_path, target_id)
    original_document = document.read_bytes()
    imported_wav = tmp_path / "imported.wav"
    _write_import_test_wav(imported_wav)
    original_replace = Path.replace

    def fail_staged_document(path, destination):
        """@brief Fail only the staged document publish, allowing the backup restore."""
        if Path(destination) == document and "-stage-" in path.parent.name:
            assert audio.read_bytes() != b"RIFF-old"
            raise OSError("document replacement failed")
        return original_replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_staged_document)
    with pytest.raises(OSError, match="document replacement failed"):
        if source == "imported":
            character_voices_service.import_target_sample(tmp_path, target, "en", "New transcript.", imported_wav)
        else:
            character_voices_service.store_target_sample(tmp_path, target, "en", "New transcript.", {}, "", b"RIFF-new")

    assert audio.read_bytes() == b"RIFF-old"
    assert document.read_bytes() == original_document


def test_sync_voice_plan_uses_character_discovery_preview_text(tmp_path) -> None:
    """
    @brief      Verify new character voice targets use discovered spoken-dialogue preview text.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project_with_selected_narrator(tmp_path, "CharacterVoicesDiscoveryPreview")
    discovered_preview_text = (
        "She weighs each answer before she gives it, and the words arrive quiet but certain. "
        "Nothing in her tone hurries, and nothing in it asks to be forgiven."
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


def test_same_narrator_sync_skips_unchanged_copied_samples(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-014 leaves unchanged same-narrator copied samples untouched.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project_with_selected_narrator(tmp_path, "CharacterVoicesCopySteady")
    character_targets = [
        {
            "target_id": "character_alice",
            "target_kind": character_voices_service.TARGET_KIND_CHARACTER,
            "display_name": "Alice",
            "prompt_text": "Prompt one.",
        }
    ]
    character_voices_service.save_voice_targets(project_root, character_targets)
    character_voices_service.sync_same_narrator_samples(project_root, character_targets, "en")

    def _fail_byte_write(*_args, **_kwargs) -> None:
        """
        @brief      Fail when an unchanged same-narrator sync rewrites WAV bytes.
        @return     None.
        @exception  AssertionError Always raised.
        """
        raise AssertionError("unchanged same-narrator sync rewrote audio")

    def _fail_json_write(*_args, **_kwargs) -> None:
        """
        @brief      Fail when an unchanged same-narrator sync rewrites target JSON.
        @return     None.
        @exception  AssertionError Always raised.
        """
        raise AssertionError("unchanged same-narrator sync rewrote metadata")

    monkeypatch.setattr(character_voices_service, "write_bytes_atomic", _fail_byte_write)
    monkeypatch.setattr(character_voices_service, "write_json_atomic", _fail_json_write, raising=False)

    character_voices_service.sync_same_narrator_samples(project_root, character_targets, "en")


def _create_project_with_selected_narrator(tmp_path, name: str):
    """
    @brief      Provide the create project with selected narrator test helper.
    @return     None.
    @exception  None
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
    return project_root, manifest


def _write_import_test_wav(path: Path) -> None:
    """
    @brief      Write one valid imported-sample WAV fixture.
    @param[in]  path Output path.
    @return     None.
    @exception  None
    """
    sample_rate = 16_000
    frame_count = int(sample_rate * 3.2)
    frame = (4000).to_bytes(2, byteorder="little", signed=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frame * frame_count)


def test_load_voice_plan_tolerates_malformed_json(tmp_path) -> None:
    """Verify a corrupt optional voice plan degrades to unavailable state."""
    (tmp_path / config.CHARACTER_VOICES_TARGETS_FILE_NAME).write_text("{not json", encoding="utf-8")
    assert character_voices_service.load_voice_plan(tmp_path) == []



def test_sync_voice_plan_falls_back_to_default_preview_when_discovery_stored_none(tmp_path) -> None:
    """
    @brief      Verify a character without discovered preview text receives the localized default.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project_with_selected_narrator(tmp_path, "CharacterVoicesDefaultPreview")

    voice_targets = character_voices_service.sync_voice_plan(
        project_root,
        [{"character_id": "alice", "canonical_name": "Alice", "preview_text": ""}],
        narrator_definition_service.profile_by_id(
            project_root,
            narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"],
        ),
    )

    assert voice_targets[1]["preview_text"] == character_voices_service.preview_text_for_language("en")


def test_character_preview_defaults_sit_inside_the_shared_word_range() -> None:
    """
    @brief      Verify every canonical character preview default is a usable voice-clone reference.
    @return     None.
    @exception  None
    """
    minimum_words, maximum_words = tts_budget_service.preview_word_bounds()

    for language_code, preview_text in character_voices_service.DEFAULT_PREVIEW_TEXT_BY_LANGUAGE.items():
        word_count = len(preview_text.split())
        assert word_count >= minimum_words, f"{language_code} default preview is too short"
        assert word_count <= maximum_words, f"{language_code} default preview is too long"


# END OF FILE
