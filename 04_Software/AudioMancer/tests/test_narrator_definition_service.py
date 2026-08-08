#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_narrator_definition_service.py
@brief Focused tests for the AudioMancer narrator-definition service.
@details Verifies custom Qwen Voice Designer narrator profiles, simplified TTS plan
         persistence, edit-side sample invalidation, and fixed-capability
         generation resolution.
"""

# IMPORTS

import json
from pathlib import Path
import wave

import pytest

from audiomancer import config
from audiomancer.services import narrator_definition_service, project_workspace_service


def test_narrator_service_starts_without_predefined_profiles(tmp_path) -> None:
    """
    @brief      Verify new projects start with no predefined narrator profiles and no selected narrator.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorSeedProject", tmp_path)

    profiles = narrator_definition_service.load_profiles(project_root)
    selected_state = narrator_definition_service.load_selected_profile_state(project_root)

    assert profiles == []
    assert selected_state["selected_profile_id"] is None


def test_narrator_service_rejects_torn_authoritative_document_without_replacing_it(tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-034 reports malformed current narrator data without replacement.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorTornProfileProject", tmp_path)
    document_path = project_root / config.NARRATOR_VOICE_FILE_NAME
    document_path.write_text("[", encoding="utf-8")

    with pytest.raises(narrator_definition_service.NarratorVoiceDocumentContractError):
        narrator_definition_service.load_profiles(project_root)

    assert document_path.read_text(encoding="utf-8") == "["


def test_narrator_service_begin_profile_edit_clears_sample_and_selection(tmp_path) -> None:
    """
    @brief      Verify editing a selected profile deletes its sample and clears the selected state.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorEditProject", tmp_path)
    profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Edit Voice",
        "English",
        "Warm prompt.",
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
        b"RIFF-test-wav",
    )
    narrator_definition_service.select_narrator_profile(project_root, profile["profile_id"], "en")

    updated_profile = narrator_definition_service.begin_profile_edit(project_root, profile["profile_id"])

    assert narrator_definition_service.has_profile_sample(project_root, profile["profile_id"]) is False
    assert narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"] is None
    assert "is_selected" not in updated_profile
    assert updated_profile["sample"] is None


def test_narrator_service_stores_single_profile_sample_and_marks_selected_metadata(tmp_path) -> None:
    """
    @brief      Verify generated narrator sample artifacts persist once per profile
                and selected state is recorded in that profile JSON.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorSampleProject", tmp_path)
    profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Sample Voice",
        "English",
        "Warm prompt.",
        "Preview text.",
    )
    narrator_definition_service.store_profile_sample(
        project_root,
        profile,
        "Preview text for the narrator.",
        {
            "generation_mode": "definition",
            "model_id": "qwen-designer",
            "source_model_id": "qwen-designer",
            "language": "en",
        },
        "Voice sample generated.",
        b"RIFF-test-wav",
    )
    narrator_definition_service.select_narrator_profile(project_root, profile["profile_id"], "en")
    profile_audio_path, profile_metadata_path = narrator_definition_service.profile_sample_paths(
        project_root,
        profile["profile_id"],
    )
    selected_audio_path = narrator_definition_service.selected_narrator_sample_path(project_root)
    selected_metadata = narrator_definition_service.load_selected_narrator_sample_metadata(project_root)

    assert profile_audio_path.read_bytes() == b"RIFF-test-wav"
    assert narrator_definition_service.load_profile_sample_metadata(project_root, profile["profile_id"])[
        "preview_text"
    ] == ("Preview text for the narrator.")
    assert selected_metadata is not None
    assert selected_metadata["profile_id"] == profile["profile_id"]
    assert selected_metadata["source_kind"] == narrator_definition_service.NARRATOR_SAMPLE_SOURCE_VOICE_DESIGNER
    assert "selected_at" not in selected_metadata
    assert selected_audio_path == profile_audio_path
    assert profile_metadata_path == project_root / config.NARRATOR_VOICE_FILE_NAME
    assert selected_audio_path.read_bytes() == b"RIFF-test-wav"
    document_payload = json.loads(profile_metadata_path.read_text(encoding="utf-8"))
    profile_payload = document_payload["profiles"][0]
    assert "sample_metadata" not in profile_payload
    assert profile_payload["sample"]["source_model_id"] == "qwen-designer"
    assert document_payload["selected_profile_id"] == profile["profile_id"]
    assert not list(project_root.glob("audio_narator_*.json"))


def test_narrator_service_imports_profile_sample_and_marks_selected_metadata(tmp_path) -> None:
    """
    @brief      Verify imported narrator samples persist audio, transcript, and selected metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorImportedSampleProject", tmp_path)
    source_sample = tmp_path / "source_voice.wav"
    _write_import_test_wav(source_sample)
    profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Imported Voice",
        "English",
        "Warm prompt.",
        "Preview text.",
    )
    narrator_definition_service.select_narrator_profile(project_root, profile["profile_id"], "en")

    metadata = narrator_definition_service.import_profile_sample(
        project_root,
        profile,
        "This is the exact imported sample text.",
        source_sample,
    )
    profile_audio_path, _profile_metadata_path = narrator_definition_service.profile_sample_paths(
        project_root,
        profile["profile_id"],
    )
    selected_audio_path = narrator_definition_service.selected_narrator_sample_path(project_root)
    selected_metadata = narrator_definition_service.load_selected_narrator_sample_metadata(project_root)

    assert profile_audio_path.read_bytes() == source_sample.read_bytes()
    assert selected_audio_path.read_bytes() == source_sample.read_bytes()
    assert metadata["source_kind"] == "imported"
    assert metadata["source_model_id"] is None
    assert metadata["preview_text"] == "This is the exact imported sample text."
    assert "audio_validation" not in metadata
    assert selected_metadata is not None
    assert selected_metadata["source_kind"] == "imported"
    assert narrator_definition_service.sample_runtime_available(metadata, []) is True


def test_narrator_service_reports_selected_sample_metadata_when_canonical_wav_is_missing(tmp_path) -> None:
    """
    @brief      Verify selected metadata remains authoritative while readiness detects a missing WAV.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorTornSelectedSampleProject", tmp_path)
    profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Sample Voice",
        "English",
        "Warm prompt.",
        "Preview text.",
    )
    narrator_definition_service.store_profile_sample(
        project_root,
        profile,
        "Profile sample text.",
        {
            "generation_mode": "definition",
            "model_id": "qwen-designer",
            "source_model_id": "qwen-designer",
            "language": "en",
        },
        "Generated sample.",
        b"RIFF-profile",
    )
    narrator_definition_service.select_narrator_profile(project_root, profile["profile_id"], "en")
    selected_audio_path = narrator_definition_service.selected_narrator_sample_path(project_root)
    assert selected_audio_path is not None
    selected_audio_path.unlink()

    selected_metadata = narrator_definition_service.load_selected_narrator_sample_metadata(project_root)

    assert selected_metadata is not None
    assert selected_metadata["profile_id"] == profile["profile_id"]
    assert selected_metadata["preview_text"] == "Profile sample text."
    assert selected_audio_path.is_file() is False


def test_narrator_service_store_profile_sample_preserves_other_profile_samples(tmp_path) -> None:
    """
    @brief      Verify storing one new narrator sample preserves samples generated for other profiles.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorMultiSampleProject", tmp_path)
    first_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "First Voice",
        "English",
        "First prompt.",
        "First preview text.",
    )
    second_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Second Voice",
        "English",
        "Second prompt.",
        "Second preview text.",
    )
    narrator_definition_service.store_profile_sample(
        project_root,
        first_profile,
        "First preview text.",
        {
            "generation_mode": "definition",
            "model_id": "qwen-designer",
            "source_model_id": "qwen-designer",
            "language": "en",
        },
        "First generated sample.",
        b"RIFF-first",
    )

    narrator_definition_service.store_profile_sample(
        project_root,
        second_profile,
        "Second preview text.",
        {
            "generation_mode": "definition",
            "model_id": "qwen-designer",
            "source_model_id": "qwen-designer",
            "language": "en",
        },
        "Second generated sample.",
        b"RIFF-second",
    )

    second_audio_path, second_metadata_path = narrator_definition_service.profile_sample_paths(
        project_root,
        second_profile["profile_id"],
    )
    first_audio_path, first_metadata_path = narrator_definition_service.profile_sample_paths(
        project_root,
        first_profile["profile_id"],
    )
    assert second_audio_path.read_bytes() == b"RIFF-second"
    assert (
        narrator_definition_service.load_profile_sample_metadata(project_root, second_profile["profile_id"])[
            "preview_text"
        ]
        == "Second preview text."
    )
    assert first_audio_path.read_bytes() == b"RIFF-first"
    assert first_metadata_path == project_root / config.NARRATOR_VOICE_FILE_NAME
    assert second_metadata_path == project_root / config.NARRATOR_VOICE_FILE_NAME
    assert (
        narrator_definition_service.load_profile_sample_metadata(project_root, first_profile["profile_id"])[
            "preview_text"
        ]
        == "First preview text."
    )
    assert sorted(path.name for path in project_root.glob("audio_narator_*")) == sorted(
        [first_audio_path.name, second_audio_path.name]
    )


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


def test_narrator_service_profile_sample_path_uses_stored_audio_path_after_rename(tmp_path) -> None:
    """
    @brief      Verify stored narrator samples remain previewable after a profile display-name edit.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorRenamedSampleProject", tmp_path)
    profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Original Voice",
        "English",
        "Warm prompt.",
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
        b"RIFF-renamed",
    )
    original_audio_path, _metadata_path = narrator_definition_service.profile_sample_paths(
        project_root,
        profile["profile_id"],
    )

    narrator_definition_service.update_custom_profile(
        project_root,
        {
            **dict(profile),
            "display_name": "Renamed Voice",
        },
    )

    renamed_audio_path, _metadata_path = narrator_definition_service.profile_sample_paths(
        project_root,
        profile["profile_id"],
    )
    assert renamed_audio_path == original_audio_path
    assert narrator_definition_service.has_profile_sample(project_root, profile["profile_id"]) is True
    assert renamed_audio_path.read_bytes() == b"RIFF-renamed"


def test_narrator_service_simplifies_tts_plan_to_voice_assignment_mode_only(tmp_path) -> None:
    """
    @brief      Verify project-local TTS plans persist only the voice-assignment mode.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorPlanProject", tmp_path)

    persisted_plan = narrator_definition_service.save_tts_plan(
        project_root,
        {
            "voice_assignment_mode": "narrator_and_characters",
            "definition_model_id": "unsupported-extra-field",
        },
    )

    assert persisted_plan == {"voice_assignment_mode": "narrator_and_characters"}
    assert narrator_definition_service.load_tts_plan(project_root) == {
        "voice_assignment_mode": "narrator_and_characters"
    }
    assert project_workspace_service.load_manifest(project_root)["voice_assignment_mode"] == "narrator_and_characters"


def test_narrator_service_profile_generation_request_requires_minimum_qwen_capabilities(tmp_path) -> None:
    """
    @brief      Verify narrator sample generation resolves only when the minimum Qwen capability set is available.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorGenerationProject", tmp_path)
    custom_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "My Narrator",
        "English",
        "Warm and intimate.",
        "Preview text.",
    )

    missing_request = narrator_definition_service.profile_generation_request(
        custom_profile,
        {"voice_assignment_mode": config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE},
        [],
    )
    ready_models = [
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
            "supported_generation_modes": ["definition"],
        },
    ]
    custom_request = narrator_definition_service.profile_generation_request(
        custom_profile,
        {"voice_assignment_mode": config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE},
        ready_models,
    )

    assert missing_request["can_generate"] is False
    assert "base" in missing_request["unavailable_reason"]
    assert custom_request["generation_mode"] == "definition"
    assert custom_request["model_id"] == "qwen-designer"


def test_narrator_service_normalizes_language_labels_to_runtime_codes(tmp_path) -> None:
    """
    @brief      Verify narrator profile storage normalizes language labels into VoiceWeaver language codes.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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


def test_narrator_language_migration_preserves_operator_authored_preview(tmp_path) -> None:
    """
    @brief      Verify a language migration preserves exact operator-authored narrator preview text.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorAuthoredPreview", tmp_path)
    profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Operator Narrator",
        "English",
        "Operator prompt.",
        "An exact operator-authored preview that must survive.",
    )

    narrator_definition_service.apply_voice_language_to_profiles(project_root, "ro")

    migrated = narrator_definition_service.profile_by_id(project_root, profile["profile_id"])
    assert migrated is not None
    assert migrated["language"] == "ro"
    assert migrated["preview_text"] == "An exact operator-authored preview that must survive."


def test_narrator_language_migration_preserves_ai_authored_preview(tmp_path) -> None:
    """
    @brief      Verify a language migration preserves exact AI-authored narrator preview text.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorAiPreview", tmp_path)
    generated = narrator_definition_service.append_ai_generated_profiles(
        project_root,
        [
            {
                "display_name": "AI Narrator",
                "language": "en",
                "prompt_text": "AI-authored prompt.",
                "preview_text": "An exact AI-authored preview that must survive.",
            }
        ],
        {},
    )[0]

    narrator_definition_service.apply_voice_language_to_profiles(project_root, "de")

    migrated = narrator_definition_service.profile_by_id(project_root, generated["profile_id"])
    assert migrated is not None
    assert migrated["language"] == "de"
    assert migrated["preview_text"] == "An exact AI-authored preview that must survive."


def test_narrator_language_migration_localizes_prior_canonical_default(tmp_path) -> None:
    """
    @brief      Verify a prior-language canonical preview is replaced by the new localized default.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorDefaultPreview", tmp_path)
    profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Default Narrator",
        "English",
        "Default prompt.",
        narrator_definition_service.preview_text_for_language("en"),
    )

    narrator_definition_service.apply_voice_language_to_profiles(project_root, "fr")

    migrated = narrator_definition_service.profile_by_id(project_root, profile["profile_id"])
    assert migrated is not None
    assert migrated["language"] == "fr"
    assert migrated["preview_text"] == narrator_definition_service.preview_text_for_language("fr")


def test_narrator_language_migration_handles_mixed_profiles_and_preserves_sample_metadata(tmp_path) -> None:
    """
    @brief      Verify mixed authored/default profiles migrate independently without changing sample provenance.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorMixedPreviews", tmp_path)
    operator_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Operator Narrator",
        "English",
        "Operator prompt.",
        "Operator-authored preview.",
    )
    default_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Default Narrator",
        "English",
        "Default prompt.",
        narrator_definition_service.preview_text_for_language("en"),
    )
    ai_profile = narrator_definition_service.append_ai_generated_profiles(
        project_root,
        [
            {
                "display_name": "AI Narrator",
                "language": "en",
                "prompt_text": "AI prompt.",
                "preview_text": "AI-authored preview.",
            }
        ],
        {},
    )[0]
    narrator_definition_service.store_profile_sample(
        project_root,
        operator_profile,
        "Recorded sample transcript.",
        {"language": "en", "model_id": "qwen-designer", "source_model_id": "qwen-designer"},
        "Generated.",
        b"RIFF-sample",
    )
    original_sample = narrator_definition_service.load_profile_sample_metadata(
        project_root,
        operator_profile["profile_id"],
    )

    narrator_definition_service.apply_voice_language_to_profiles(project_root, "ro")

    migrated_by_id = {
        profile["profile_id"]: profile for profile in narrator_definition_service.load_profiles(project_root)
    }
    assert {profile["language"] for profile in migrated_by_id.values()} == {"ro"}
    assert migrated_by_id[operator_profile["profile_id"]]["preview_text"] == "Operator-authored preview."
    assert migrated_by_id[ai_profile["profile_id"]]["preview_text"] == "AI-authored preview."
    assert migrated_by_id[default_profile["profile_id"]][
        "preview_text"
    ] == narrator_definition_service.preview_text_for_language("ro")
    assert migrated_by_id[operator_profile["profile_id"]]["sample"] == original_sample


def test_narrator_language_application_skips_unchanged_document_write(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify applying an unchanged language does not invoke the strict atomic document writer.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("NarratorNoOpLanguage", tmp_path)
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

    narrator_definition_service.apply_voice_language_to_profiles(project_root, "en")

    assert write_calls == []
    assert document_path.read_bytes() == original_bytes


# END OF FILE
