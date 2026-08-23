#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_narrator_voice_single_document_contract.py
@brief Red-before-green contract tests for authoritative Narrator Voice state.
@details Verifies the strict document, canonical sample ownership, selected
         profile resolution, lifecycle cleanup, and export behavior required by
         the current Narrator Voice contracts.
"""

# IMPORTS

import json

import pytest

from audiomancer.services import (
    character_voices_service,
    narrator_definition_service,
    operation_runtime_service,
    project_export_service,
)

# CONSTANTS

_ROOT_FIELDS = {
    "status",
    "token_usage",
    "budget_metadata",
    "additional_profile_instructions",
    "selected_profile_id",
    "profiles",
    "resume",
}
def test_default_document_has_exact_contract(tmp_path) -> None:
    """
    @brief      Verify SPEC-NV-001 and REQ-FUNC-034 exact missing-document initialization.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()

    document_path = narrator_definition_service.ensure_narrator_voice_document(project_root)
    document = json.loads(document_path.read_text(encoding="utf-8"))

    assert document_path == project_root / "narrator_voice.json"
    assert set(document) == _ROOT_FIELDS
    assert document == {
        "status": "not_started",
        "token_usage": {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "usage_available": False,
        },
        "budget_metadata": {},
        "additional_profile_instructions": "",
        "selected_profile_id": None,
        "profiles": [],
        "resume": None,
    }


def test_malformed_current_document_is_preserved_and_reported(tmp_path) -> None:
    """
    @brief      Verify SPEC-NV-001 and REQ-FUNC-034 reject rather than repair current data.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    document_path = project_root / "narrator_voice.json"
    malformed_bytes = b'{"status":"completed","unknown":true}'
    document_path.write_bytes(malformed_bytes)

    with pytest.raises(narrator_definition_service.NarratorVoiceDocumentContractError):
        narrator_definition_service.load_narrator_voice_document(project_root)

    assert document_path.read_bytes() == malformed_bytes


def test_profile_sample_and_selection_use_only_document_and_canonical_wav(tmp_path) -> None:
    """
    @brief      Verify SPEC-NV-002, SPEC-NV-006, and REQ-FUNC-055 canonical no-copy selection.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Contract Narrator",
        "English",
        "Warm, measured narration.",
        "A sufficiently clear preview sentence for the selected narrator sample.",
    )
    narrator_definition_service.store_profile_sample(
        project_root,
        profile,
        "The exact transcript spoken by the selected narrator sample.",
        {
            "generation_mode": "definition",
            "model_id": "voice-model-id",
            "source_model_id": "voice-model-id",
            "language": "en",
        },
        "Generated sample.",
        b"RIFF-canonical-profile-sample",
    )
    narrator_definition_service.select_narrator_profile(project_root, profile["profile_id"], "en")

    document = narrator_definition_service.load_narrator_voice_document(project_root)
    selected_path = narrator_definition_service.selected_narrator_sample_path(project_root)
    selected_metadata = narrator_definition_service.load_selected_narrator_sample_metadata(project_root)
    expected_wav = project_root / f"audio_narator_{profile['profile_id']}.wav"

    assert set(document) == _ROOT_FIELDS
    assert document["selected_profile_id"] == profile["profile_id"]
    assert selected_path == expected_wav
    assert expected_wav.read_bytes() == b"RIFF-canonical-profile-sample"
    assert selected_metadata is not None
    assert selected_metadata["preview_text"] == "The exact transcript spoken by the selected narrator sample."


def test_character_voice_readiness_uses_selected_profile_resolution(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify SPEC-NV-004 and REQ-FUNC-057 use the current selected-profile APIs.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    selected_path = tmp_path / "audio_narator_profile_contract.wav"
    selected_path.write_bytes(b"RIFF-current-selected-profile")
    monkeypatch.setattr(
        narrator_definition_service,
        "selected_narrator_sample_path",
        lambda _project_root: selected_path,
        raising=False,
    )
    monkeypatch.setattr(
        narrator_definition_service,
        "load_selected_narrator_sample_metadata",
        lambda _project_root: {"preview_text": "Current sample transcript.", "language": "en"},
    )
    assert character_voices_service.selected_narrator_sample_exists(tmp_path) is True


def test_narrator_reset_removes_current_artifacts(tmp_path) -> None:
    """
    @brief      Verify SPEC-NV-005, REQ-FUNC-009, and REQ-FUNC-058 reset scope and log token.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    current_paths = (
        tmp_path / "narrator_voice.json",
        tmp_path / "audio_narator_profile_contract.wav",
        tmp_path / "log_ai_narrator_profiles_20260721T100000Z.log",
    )
    for current_path in current_paths:
        current_path.write_bytes(b"current")

    operation_runtime_service.reset_operation_data(tmp_path, "narrator_definition", include_current=True)

    assert all(not current_path.exists() for current_path in current_paths)


def test_narrator_export_uses_authoritative_document_and_profile_wav(tmp_path) -> None:
    """
    @brief      Verify SPEC-NV-005, REQ-FUNC-003, and REQ-FUNC-058 export current artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    profile = narrator_definition_service.create_custom_profile(
        tmp_path,
        "Export Narrator",
        "English",
        "Measured export narration.",
        "A clear export preview sentence with sufficient spoken content.",
    )
    narrator_definition_service.store_profile_sample(
        tmp_path,
        profile,
        "The exact transcript included with the exported profile sample.",
        {
            "generation_mode": "definition",
            "model_id": "voice-model-id",
            "source_model_id": "voice-model-id",
            "language": "en",
        },
        "Generated sample.",
        b"RIFF-export-profile-sample",
    )

    entries = project_export_service._build_narrator_voice_archive_entries(tmp_path)
    archive_names = {entry[0] for entry in entries}

    assert "narrator_voice.json" in archive_names
    assert f"audio_narator_{profile['profile_id']}.wav" in archive_names


# END OF FILE
