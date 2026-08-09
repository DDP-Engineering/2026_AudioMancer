#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_project_workspace_service.py
@brief Focused tests for the AudioMancer project workspace service.
@details Verifies project creation, manifest persistence, folder-name
         validation, project-root resolution, and open validation behavior.
"""

# IMPORTS

import json
from pathlib import Path
import subprocess
import sys

import pytest

from audiomancer import config
from audiomancer.services import (
    audio_assembly_service,
    audio_blocks_service,
    chunking_document_service,
    narrator_definition_service,
    project_export_service,
    project_workspace_service,
    speech_blocks_service,
    text_cleanup_service,
    text_extraction_service,
)
from chunking_test_support import write_cleanup_input


def _write_audio_blocks_document_fixture(project_root, *, status="completed", speech_block_id="sb-1"):
    """
    @brief      Persist a single-block Audio Blocks document fixture.
    @param[in]  project_root Active project root folder.
    @param[in]  status Document lifecycle status.
    @param[in]  speech_block_id Source Speech Blocks identifier.
    @return     None.
    """
    audio_blocks_service.write_audio_blocks_document(
        project_root,
        {
            "status": status,
            "voice_language": "en",
            "input_fingerprint": "ws-fixture-fingerprint",
            "checkpoint": None,
            "blocks": [
                {
                    "speech_block_id": speech_block_id,
                    "voice_target_id": "narrator",
                    "generated": True,
                    "approved": True,
                    "audio_can_play": True,
                    "audio_duration_seconds": None,
                    "generation_fingerprint": None,
                }
            ],
        },
    )


def _write_speech_blocks_document(project_root, blocks, *, status="completed", kind="original", language="en"):
    """
    @brief      Persist a valid single Speech Blocks document fixture.
    @param[in]  project_root Active project root folder.
    @param[in]  blocks Speech block payloads.
    @param[in]  status Document lifecycle status.
    @param[in]  kind Source-kind token.
    @param[in]  language Source language code.
    @return     None.
    """
    speech_blocks_service.write_speech_blocks_document(
        project_root,
        {
            "status": status,
            "source": {"kind": kind, "language": language, "fingerprint": "ws-fixture-fingerprint"},
            "ai_profile_id": "profile-1",
            "instructions": "",
            "scene_ambience": {"enabled": False},
            "response_contract": "direct_blocks",
            "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "usage_available": False},
            "budget_metadata": {},
            "checkpoint": {
                "next_chunk_index": 0,
                "run_token": "2026-04-25T12:00:00+00:00",
                "log_relative_path": "log_ai_speech_blocks_20260425T120000Z.log",
                "source_snapshot_fingerprint": "ws-fixture-fingerprint",
                "source_language": language,
                "ai_profile_id": "profile-1",
                "additional_speech_block_instructions_fingerprint": "",
                "speech_blocks_response_contract": "direct_blocks",
            },
            "failure": None,
            "blocks": list(blocks),
        },
    )

# PUBLIC API


def test_create_project_creates_required_structure_and_manifest(tmp_path) -> None:
    """
    @brief      Verify project creation writes the required folders and manifest.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )

    assert project_root == tmp_path / "Book5_CAL_CAL"
    assert manifest["display_name"] == "Book5_CAL_CAL"
    assert manifest["current_stage"] == config.DEFAULT_WORKFLOW_STAGE
    assert manifest["source_document"] is None
    assert "extraction_warning_count" not in manifest
    assert "extraction" not in manifest["operations"]
    assert "folder_relative_path" not in manifest["operations"]["cleanup"]
    assert manifest["voice_assignment_mode"] == config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE
    assert "output_paths" not in manifest["operations"]["cleanup"]
    assert (project_root / config.PROJECT_MANIFEST_FILE_NAME).is_file()
    assert not any(path.is_dir() for path in project_root.iterdir())


def test_validate_project_name_rejects_unsupported_windows_characters() -> None:
    """
    @brief      Verify unsupported Windows characters are rejected.
    @return     None.
    @exception  None
    """
    with pytest.raises(ValueError, match="unsupported folder characters"):
        project_workspace_service.validate_project_name("Book:Five")


def test_validate_project_name_rejects_linux_reserved_name() -> None:
    """
    @brief      Verify Linux-reserved directory names are rejected.
    @return     None.
    @exception  None
    """
    with pytest.raises(ValueError, match="cannot be '.' or '..'"):
        project_workspace_service.validate_project_name("..")


def test_validate_project_name_rejects_reserved_windows_device_name() -> None:
    """
    @brief      Verify reserved Windows device names are rejected.
    @return     None.
    @exception  None
    """
    with pytest.raises(ValueError, match="reserved Windows device name"):
        project_workspace_service.validate_project_name("CON")


def test_create_project_rejects_non_empty_target_folder(tmp_path) -> None:
    """
    @brief      Verify project creation fails when the target root is not empty.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    target_root = tmp_path / "Book5_CAL_CAL"
    target_root.mkdir()
    (target_root / "existing.txt").write_text("occupied", encoding="utf-8")

    with pytest.raises(FileExistsError, match="not empty"):
        project_workspace_service.create_project("Book5_CAL_CAL", tmp_path)


def test_create_project_rejects_existing_file_target(tmp_path) -> None:
    """Cover S-0004 and REQ-FUNC-c593854d-38a1-44f3-aff1-33ede63b8dde."""
    target_path = tmp_path / "ExistingProjectFile"
    target_path.write_bytes(b"existing project bytes")

    with pytest.raises(
        FileExistsError,
        match="Project path already exists as a file",
    ):
        project_workspace_service.create_project("ExistingProjectFile", tmp_path)

    assert target_path.is_file()
    assert target_path.read_bytes() == b"existing project bytes"


def test_open_project_resolves_flat_project_root(tmp_path) -> None:
    """
    @brief      Verify opening succeeds when selecting the flat project root.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    created_root, _manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )

    open_result = project_workspace_service.open_project(created_root)

    assert open_result["status"] == "ok"
    assert open_result["project_root"] == created_root
    assert open_result["manifest"]["display_name"] == "Book5_CAL_CAL"


def test_open_project_requires_repair_for_malformed_cleanup_quality_metric(
    tmp_path,
) -> None:
    """
    @brief      Verify invalid Cleanup completion does not abort project open.
    @details    Covers corrected S-0005 and
                REQ-FUNC-c3211661-3717-46cc-9817-da4e2524b18b.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project(
        "CorruptCleanupRepair",
        tmp_path,
    )
    source_path = project_root / "story.txt"
    source_path.write_text("Story source.", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-07-29T20:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    text_extraction_service.extract_text(project_root, manifest)
    document = text_cleanup_service.clean_text(project_root, manifest)
    document["quality_report"]["introduced_fusion_count"] = None
    (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] in {"ok", "repair_required"}


def test_open_project_self_heals_incompatible_chunking_and_downstream(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify S-0001 through S-0003 and scoped Chunking self-heal.
    @details    Covers REQ-FUNC-03bed2a0-5150-4cd4-a5be-a1f23ff94db2 and
                REQ-FUNC-25286e0a-41af-4f78-89ba-0920d87dc03c.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("ChunkingSelfHeal", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("Story source.", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-07-29T07:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    text_extraction_service.extract_text(project_root, manifest)
    extracted_path = project_root / config.EXTRACTED_TEXT_FILE_NAME
    extraction_metadata_path = project_root / config.EXTRACTION_METADATA_FILE_NAME
    extracted_before = extracted_path.read_bytes()
    extraction_metadata_before = extraction_metadata_path.read_bytes()
    cleanup_document_path = write_cleanup_input(project_root, "Cleaned story.")
    cleaned_path = project_root / config.CLEANED_TEXT_FILE_NAME
    cleanup_document_before = cleanup_document_path.read_bytes()
    cleaned_before = cleaned_path.read_bytes()
    manifest["current_stage"] = "audio_assembly_ready"
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["mode"] = "manual_edit"
    for operation_kind in config.WORKFLOW_OPERATION_ORDER[2:]:
        manifest["operations"][operation_kind]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)

    reset_file_names = (
        config.CHUNK_ARTIFACT_FILE_NAME,
        config.TRANSLATED_CHUNKS_FILE_NAME,
        config.CHARACTERS_DOCUMENT_FILE_NAME,
        config.NARRATOR_VOICE_FILE_NAME,
        config.CHARACTER_VOICES_TARGETS_FILE_NAME,
        config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME,
        config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME,
        config.AUDIO_ASSEMBLY_REPORT_FILE_NAME,
        config.AUDIO_ASSEMBLY_STATE_FILE_NAME,
    )
    for file_name in reset_file_names:
        (project_root / file_name).write_text("{}\n", encoding="utf-8")
    chunking_log_path = project_root / f"{config.AI_TRANSACTION_LOG_FILE_PREFIX}chunking_fixture.log"
    chunking_log_path.write_text("log", encoding="utf-8")

    original_validate_project = project_workspace_service.validate_project
    validation_calls = []

    def _tracked_validate_project(candidate_root):
        """Track project-validation attempts for the bounded retry assertion."""
        validation_calls.append(Path(candidate_root))
        return original_validate_project(candidate_root)

    monkeypatch.setattr(project_workspace_service, "validate_project", _tracked_validate_project)

    open_result = project_workspace_service.open_project(project_root)

    assert validation_calls == [project_root, project_root]
    assert open_result["status"] == "ok"
    assert open_result["recovered_operations"] == ["chunking"]
    assert open_result["manifest"]["current_stage"] == "text_chunking_ready"
    assert open_result["manifest"]["operations"]["cleanup"]["status"] == "completed"
    for operation_kind in config.WORKFLOW_OPERATION_ORDER[2:]:
        assert open_result["manifest"]["operations"][operation_kind]["status"] == "not_started"
    assert source_path.read_text(encoding="utf-8") == "Story source."
    assert extracted_path.read_bytes() == extracted_before
    assert extraction_metadata_path.read_bytes() == extraction_metadata_before
    assert cleanup_document_path.read_bytes() == cleanup_document_before
    assert cleaned_path.read_bytes() == cleaned_before
    assert all(not (project_root / file_name).exists() for file_name in reset_file_names)
    assert not chunking_log_path.exists()


def test_open_project_propagates_chunking_io_error_without_reset(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify S-0004 and REQ-FUNC-810d9787-dc4d-4ed6-8b7e-e746fefdf658.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("ChunkingIoFailure", tmp_path)
    chunking_path = project_root / config.CHUNK_ARTIFACT_FILE_NAME
    chunking_path.write_text("{}\n", encoding="utf-8")
    downstream_path = project_root / config.TRANSLATED_CHUNKS_FILE_NAME
    downstream_path.write_text("{}\n", encoding="utf-8")

    def _raise_permission_error(_project_root):
        """
        @brief      Raise the compatibility wrapper with an operating-system cause.
        """
        try:
            raise PermissionError("chunking read denied")
        except PermissionError as error:
            raise chunking_document_service.IncompatibleChunkingDocumentError(
                "Chunking data is incompatible."
            ) from error

    monkeypatch.setattr(chunking_document_service, "load_chunking_document", _raise_permission_error)

    with pytest.raises(PermissionError, match="chunking read denied"):
        project_workspace_service.open_project(project_root)

    assert chunking_path.is_file()
    assert downstream_path.is_file()


def test_open_project_fails_when_manifest_is_missing(tmp_path) -> None:
    """
    @brief      Verify opening fails when no manifest exists in the folder chain.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    orphan_folder = tmp_path / "orphan"
    orphan_folder.mkdir()

    with pytest.raises(FileNotFoundError, match="project.json"):
        project_workspace_service.open_project(orphan_folder)


def test_open_project_fails_when_required_manifest_field_is_missing(tmp_path) -> None:
    """
    @brief      Verify opening fails when minimal manifest metadata is incomplete.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    manifest_path = project_root / config.PROJECT_MANIFEST_FILE_NAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    del payload["display_name"]
    manifest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="display_name"):
        project_workspace_service.open_project(project_root)


def test_open_project_accepts_current_required_folder_contract(tmp_path) -> None:
    """
    @brief      Verify project validation accepts the current required workflow-folder contract.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-21T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["current_stage"] = "character_voices_ready"
    project_workspace_service.save_manifest(manifest, project_root)

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "ok"
    assert open_result["manifest"]["current_stage"] == "character_voices_ready"


def test_open_project_does_not_require_speech_blocks_folder_for_flat_layout(
    tmp_path,
) -> None:
    """
    @brief      Verify flat-layout validation does not require a Speech Blocks folder.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-21T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["current_stage"] = "character_voices_ready"
    project_workspace_service.save_manifest(manifest, project_root)

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "ok"
    assert open_result["manifest"]["current_stage"] == "character_voices_ready"
    assert (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH).is_dir()


def test_repair_project_fixes_invalid_current_stage_metadata_only(tmp_path) -> None:
    """
    @brief      Verify repair can fix a recoverable metadata-only stage corruption.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "source.pdf",
        "stored_relative_path": "source.pdf",
        "file_type": "pdf",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 1024,
    }
    manifest["current_stage"] = "broken_stage"
    manifest_path = project_root / config.PROJECT_MANIFEST_FILE_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "repair_required"
    assert open_result["metadata_only"] is True
    repaired_result = project_workspace_service.repair_project(open_result)

    assert repaired_result["status"] == "ok"
    assert repaired_result["project_root"] == project_root
    assert repaired_result["manifest"]["current_stage"] == "source_selected"


def test_validate_project_manifest_accepts_structured_source_document() -> None:
    """
    @brief      Verify manifest validation preserves one valid source-document payload.
    @return     None.
    @exception  None
    """
    manifest = project_workspace_service.build_project_manifest("Book5_CAL_CAL")
    manifest["source_document"] = {
        "original_name": "story.epub",
        "stored_relative_path": "story.epub",
        "file_type": "epub",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 2048,
    }
    manifest["current_stage"] = "source_selected"

    validated = project_workspace_service.validate_project_manifest(manifest)

    assert validated["source_document"] == manifest["source_document"]
    assert validated["current_stage"] == "source_selected"
    assert validated["voice_assignment_mode"] == config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE


@pytest.mark.parametrize("stored_relative_path", ["source/../../outside.txt", "/outside.txt"])
def test_validate_project_manifest_rejects_unsafe_source_document_paths(stored_relative_path: str) -> None:
    """
    @brief      Verify manifest validation rejects traversal and absolute source paths.
    @param[in]  stored_relative_path Candidate unsafe source-document path.
    @return     None.
    @exception  None
    """
    manifest = project_workspace_service.build_project_manifest("UnsafeSource")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": stored_relative_path,
        "file_type": "txt",
        "imported_at": "2026-04-29T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["current_stage"] = "source_selected"

    with pytest.raises(ValueError, match="source_document.stored_relative_path"):
        project_workspace_service.validate_project_manifest(manifest)


def test_open_project_rejects_source_document_symlink_escape(tmp_path) -> None:
    """
    @brief      Verify project-open validation rejects source symlinks resolving outside the project.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("SymlinkSource", tmp_path)
    outside_source = tmp_path / "outside.txt"
    outside_source.write_text("outside", encoding="utf-8")
    linked_source = project_root / "linked_source.txt"
    try:
        linked_source.symlink_to(outside_source)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Filesystem does not allow file symlink creation: {exc}")
    manifest["source_document"] = {
        "original_name": "outside.txt",
        "stored_relative_path": "linked_source.txt",
        "file_type": "txt",
        "imported_at": "2026-04-29T12:00:00+00:00",
        "size_bytes": outside_source.stat().st_size,
    }
    manifest["current_stage"] = "source_selected"
    _write_json(project_root / config.PROJECT_MANIFEST_FILE_NAME, manifest)

    with pytest.raises(ValueError, match="source_document.stored_relative_path"):
        project_workspace_service.open_project(project_root)


def test_validate_project_manifest_normalizes_voice_assignment_mode() -> None:
    """
    @brief      Verify manifest validation normalizes unsupported voice-assignment values to the default.
    @return     None.
    @exception  None
    """
    manifest = project_workspace_service.build_project_manifest("Book5_CAL_CAL")
    manifest["voice_assignment_mode"] = "unsupported_mode"

    validated = project_workspace_service.validate_project_manifest(manifest)

    assert validated["voice_assignment_mode"] == config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE


def test_project_workspace_calls_audio_assembly_settings_contract(monkeypatch) -> None:
    """
    @brief      Verify project manifest defaults and normalization call the domain-owned public API.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    domain_defaults = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "max_duration_minutes": 37,
    }
    domain_normalized = {
        **domain_defaults,
        "max_duration_minutes": 91,
        "inter_block_silence_ms": 654,
    }
    calls: list[tuple[str, object]] = []

    def _default_settings() -> dict[str, object]:
        """
        @brief      Return an observable domain default payload.
        @return     Domain-owned settings defaults.
        """
        calls.append(("default", None))
        return dict(domain_defaults)

    def _normalize_settings(value: object) -> dict[str, object]:
        """
        @brief      Return an observable domain normalization payload.
        @param[in]  value Candidate manifest settings.
        @return     Domain-owned normalized settings.
        """
        calls.append(("normalize", value))
        return dict(domain_normalized)

    monkeypatch.setattr(audio_assembly_service, "default_audio_assembly_settings", _default_settings)
    monkeypatch.setattr(audio_assembly_service, "normalize_audio_assembly_settings", _normalize_settings)

    manifest = project_workspace_service.build_project_manifest("AssemblyContract")
    assert manifest["audio_assembly_settings"] == domain_defaults

    candidate = {"max_duration_minutes": "88"}
    manifest["audio_assembly_settings"] = candidate
    validated = project_workspace_service.validate_project_manifest(manifest)

    assert validated["audio_assembly_settings"] == domain_normalized
    assert calls == [("default", None), ("normalize", candidate)]


def test_project_manifest_settings_match_domain_bounds_and_preserve_save_load(tmp_path) -> None:
    """
    @brief      Verify manifest settings exactly match domain defaults, bounds, and invalid-input rules.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    assert project_workspace_service.build_project_manifest("AssemblyDefaults")[
        "audio_assembly_settings"
    ] == audio_assembly_service.default_audio_assembly_settings()
    candidates = (
        None,
        ["invalid"],
        {
            "output_mode": "unsupported",
            "max_duration_minutes": -4,
            "output_format": "MP3",
            "inter_block_silence_ms": 60_001,
            "inter_chunk_silence_ms": "invalid",
            "include_scene_ambience": 0,
            "unknown_field": "discarded",
        },
        {
            "output_mode": "time_limit",
            "max_duration_minutes": 99_999,
            "output_format": "WAV",
            "inter_block_silence_ms": -1,
            "inter_chunk_silence_ms": 60_001,
            "include_scene_ambience": True,
        },
    )
    for candidate in candidates:
        manifest = project_workspace_service.build_project_manifest("AssemblyBounds")
        manifest["audio_assembly_settings"] = candidate

        assert project_workspace_service.validate_project_manifest(manifest)[
            "audio_assembly_settings"
        ] == audio_assembly_service.normalize_audio_assembly_settings(candidate)

    project_root, manifest = project_workspace_service.create_project("AssemblyRoundTrip", tmp_path)
    saved_candidate = candidates[-1]
    manifest["audio_assembly_settings"] = saved_candidate
    project_workspace_service.save_manifest(manifest, project_root)

    assert project_workspace_service.load_manifest(project_root)[
        "audio_assembly_settings"
    ] == audio_assembly_service.normalize_audio_assembly_settings(saved_candidate)


def test_audio_assembly_and_project_workspace_import_without_cycle() -> None:
    """
    @brief      Verify both service import orders and settings calls succeed in fresh interpreters.
    @return     None.
    @exception  None
    """
    scripts = (
        (
            "from audiomancer.services import project_workspace_service\n"
            "project_workspace_service.build_project_manifest('WorkspaceFirst')\n"
            "from audiomancer.services import audio_assembly_service\n"
            "audio_assembly_service.default_audio_assembly_settings()\n"
        ),
        (
            "from audiomancer.services import audio_assembly_service\n"
            "audio_assembly_service.default_audio_assembly_settings()\n"
            "from audiomancer.services import project_workspace_service\n"
            "project_workspace_service.build_project_manifest('AssemblyFirst')\n"
        ),
    )

    for script in scripts:
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_validate_project_manifest_normalizes_operations_map() -> None:
    """
    @brief      Verify manifest validation fills the required per-operation state entries.
    @return     None.
    @exception  None
    """
    manifest = project_workspace_service.build_project_manifest("Book5_CAL_CAL")
    manifest["operations"] = {
        "extraction": {
            "folder_relative_path": ".",
            "status": "running",
            "progress_current": 1,
            "progress_total": 3,
        }
    }

    validated = project_workspace_service.validate_project_manifest(manifest)

    assert "extraction" not in validated["operations"]
    assert validated["operations"]["translation"]["status"] == "not_started"
    assert "output_paths" not in validated["operations"]["translation"]


def test_save_manifest_projects_detailed_operation_state_to_compact_summary(tmp_path) -> None:
    """
    @brief      Verify saving the manifest strips duplicated detailed operation payload fields.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project(
        "CompactManifestProject",
        tmp_path,
    )
    manifest["operations"]["translation"] = {
        "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        "status": "completed",
        "input_paths": [config.CHUNK_ARTIFACT_FILE_NAME],
        "output_paths": [config.TRANSLATED_CHUNKS_FILE_NAME],
        "artifact_paths": [config.TRANSLATED_CHUNKS_FILE_NAME],
        "progress_current": 8,
        "progress_total": 8,
        "mode": "ai_assisted",
        "started_at": "2026-04-11T10:00:00+00:00",
        "completed_at": "2026-04-11T10:10:00+00:00",
        "updated_at": "2026-04-11T10:10:00+00:00",
        "warning_count": 2,
        "metadata": {
            "translated_chunks": [
                {"chunk_id": "chunk-0001", "translated_text": "..."},
            ],
            "warnings": ["warning"],
        },
        "resume_checkpoint": {"next_untranslated_chunk_id": None},
    }

    project_workspace_service.save_manifest(manifest, project_root)

    saved_payload = json.loads((project_root / config.PROJECT_MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
    translation_operation = saved_payload["operations"]["translation"]
    assert translation_operation["status"] == "completed"
    assert translation_operation["progress_current"] == 8
    assert translation_operation["warning_count"] == 2
    assert "input_paths" not in translation_operation
    assert "output_paths" not in translation_operation
    assert "artifact_paths" not in translation_operation
    assert "folder_relative_path" not in translation_operation
    assert "metadata" not in translation_operation
    assert "resume_checkpoint" not in translation_operation


def test_repair_manifest_preserves_character_discovery_for_narrator_stage() -> None:
    """
    @brief      Verify repaired narrator-stage manifests keep character discovery data intact.
    @return     None.
    @exception  None
    """
    manifest = project_workspace_service.build_project_manifest("Book5_CAL_CAL")
    manifest["current_stage"] = "narrator_definition_ready"
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["translation"]["status"] = "completed"
    manifest["operations"]["character_discovery"]["status"] = "completed"

    repaired_manifest = project_workspace_service._build_repaired_manifest(
        manifest,
        "narrator_definition_ready",
    )

    assert repaired_manifest["operations"]["translation"]["status"] == "completed"
    assert repaired_manifest["operations"]["character_discovery"]["status"] == "completed"


def test_repair_manifest_preserves_character_discovery_for_character_voices_stage() -> None:
    """
    @brief      Verify repaired character-voices-stage manifests keep character discovery data intact.
    @return     None.
    @exception  None
    """
    manifest = project_workspace_service.build_project_manifest("Book5_CAL_CAL")
    manifest["current_stage"] = "character_voices_ready"
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["translation"]["status"] = "completed"
    manifest["operations"]["character_discovery"]["status"] = "completed"

    repaired_manifest = project_workspace_service._build_repaired_manifest(
        manifest,
        "character_voices_ready",
    )

    assert repaired_manifest["operations"]["translation"]["status"] == "completed"
    assert repaired_manifest["operations"]["character_discovery"]["status"] == "completed"


def test_open_project_heals_completed_speech_blocks_manifest_summary(tmp_path) -> None:
    """
    @brief      Verify completed Speech Blocks artifacts heal stale manifest metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("SpeechHeal", tmp_path)
    _write_speech_blocks_document(
        project_root,
        [
            {"speech_block_id": "sb-1", "chunk_id": "chunk-0001", "speaker_name": "Narrator", "text": "One", "approved": True},  # noqa: E501
            {"speech_block_id": "sb-2", "chunk_id": "chunk-0001", "speaker_name": "Narrator", "text": "Two", "approved": True},  # noqa: E501
        ],
    )
    manifest["current_stage"] = "speech_blocks_ready"
    manifest["operations"]["speech_blocks"]["status"] = "not_started"
    project_workspace_service.save_manifest(manifest, project_root)

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "repair_required"
    assert "speech_blocks: not_started -> completed" in open_result["changes"]
    repaired_result = project_workspace_service.repair_project(open_result)
    repaired_manifest = repaired_result["manifest"]

    assert repaired_manifest["operations"]["speech_blocks"]["status"] == "completed"
    readiness = project_export_service.build_export_states(project_root, repaired_manifest)
    speech_readiness = next(
        state for state in readiness if state["export_kind"] == project_export_service.EXPORT_KIND_SPEECH_BLOCKS
    )
    assert speech_readiness["status"] == "available"


def test_open_project_heals_audio_blocks_manifest_from_completed_report_with_stale_state(tmp_path) -> None:
    """
    @brief      Verify completed Audio Blocks report and files heal stale state metadata with a warning.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("AudioHeal", tmp_path)
    audio_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    audio_root.mkdir()
    (audio_root / "sb-1.wav").write_bytes(b"RIFF")
    _write_audio_blocks_document_fixture(project_root, status="in_progress")
    manifest["current_stage"] = "audio_blocks_ready"
    manifest["operations"]["audio_blocks"]["status"] = "in_progress"
    project_workspace_service.save_manifest(manifest, project_root)

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "repair_required"
    assert "audio_blocks: in_progress -> completed" in open_result["changes"]
    assert any(config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME in warning for warning in open_result["warnings"])
    assert open_result["normalized_manifest"]["operations"]["audio_blocks"]["status"] == "completed"


def test_open_project_does_not_require_repair_when_only_stale_state_warning_remains(tmp_path) -> None:
    """
    @brief      Verify stale operation-state warnings alone do not reopen the repair dialog.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("AudioHealAlreadyApplied", tmp_path)
    audio_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    audio_root.mkdir()
    (audio_root / "sb-1.wav").write_bytes(b"RIFF")
    _write_audio_blocks_document_fixture(project_root, status="in_progress")
    manifest["current_stage"] = "audio_blocks_ready"
    manifest["operations"]["audio_blocks"]["status"] = "in_progress"
    project_workspace_service.save_manifest(manifest, project_root)

    first_open_result = project_workspace_service.open_project(project_root)
    assert first_open_result["status"] == "repair_required"
    project_workspace_service.repair_project(first_open_result)

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "ok"
    assert open_result["manifest"]["operations"]["audio_blocks"]["status"] == "completed"


def test_open_project_ignores_narrator_timestamp_drift_with_noncompleted_downstream_artifacts(tmp_path) -> None:
    """
    @brief      Verify narrator timestamp drift and intentionally non-completed downstream artifacts open cleanly.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("NarratorTimestampDrift", tmp_path)
    narrator_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Selected Narrator",
        "en",
        "A steady narrator voice.",
        "A selected narrator preview sentence.",
    )
    narrator_definition_service.select_narrator_profile(project_root, narrator_profile["profile_id"], "en")
    _write_speech_blocks_document(
        project_root,
        [{"speech_block_id": "sb-1", "chunk_id": "chunk-0001", "approved": False}],
        status="review_pending",
    )
    _write_json(
        project_root / config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME,
        [{"speech_block_id": "sb-1", "generated": False}],
    )
    manifest["current_stage"] = "narrator_definition_ready"
    manifest["narrator_profile_name"] = "Selected Narrator"
    manifest["narrator_language"] = "en"
    manifest["operations"]["narrator_definition"] = project_workspace_service.project_manifest_operation_summary(
        "narrator_definition",
        {
            **_operation_state("completed", 1, 1),
            "mode": "manual",
            "started_at": "2026-05-11T10:23:10+00:00",
            "completed_at": "2026-05-11T10:23:10+00:00",
            "updated_at": "2026-05-11T10:23:10+00:00",
        },
    )
    manifest["operations"]["speech_blocks"] = {
        **manifest["operations"]["speech_blocks"],
        "status": "review_pending",
    }
    manifest["operations"]["audio_blocks"] = {
        **manifest["operations"]["audio_blocks"],
        "status": "in_progress",
    }
    project_workspace_service.save_manifest(manifest, project_root)

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "ok"
    assert open_result["manifest"]["operations"]["narrator_definition"]["status"] == "completed"
    assert open_result["manifest"]["operations"]["speech_blocks"]["status"] == "review_pending"
    assert open_result["manifest"]["operations"]["audio_blocks"]["status"] == "in_progress"


def test_open_project_heals_completed_character_voices_manifest_summary(tmp_path) -> None:
    """
    @brief      Verify Character Voices samples heal stale manifest status metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("CharacterVoicesHeal", tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-05-16T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["current_stage"] = "character_voices_ready"
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / "story.txt").write_text("Story.", encoding="utf-8")
    narrator_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Narator Voice",
        "en",
        "A warm narrator voice.",
        "Narrator preview.",
    )
    narrator_definition_service.store_profile_sample(
        project_root,
        narrator_profile,
        "Narrator preview.",
        {"generation_mode": "definition", "source_model_id": "qwen-designer", "language": "en"},
        "Narrator sample ready.",
        b"RIFF-narrator",
    )
    narrator_definition_service.select_narrator_profile(project_root, narrator_profile["profile_id"], "en")
    (project_root / "audio_alice.wav").write_bytes(b"RIFF-alice")
    _write_json(
        project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME,
        [
            {
                "target_id": "narrator",
                "target_kind": "narrator",
                "display_name": "Narator Voice",
                "sample_audio_path": None,
                "sample_metadata": None,
            },
            {
                "target_id": "character_alice",
                "target_kind": "character",
                "display_name": "Alice",
                "sample_audio_path": "audio_alice.wav",
                "sample_metadata": {
                    "target_id": "character_alice",
                    "voice_language": "en",
                    "preview_text": "Alice preview.",
                    "generated_at": "2026-05-16T12:02:00+00:00",
                },
            },
        ],
    )

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "repair_required"
    operation_summary = open_result["normalized_manifest"]["operations"]["character_voices"]
    assert operation_summary["status"] == "completed"
    assert operation_summary["progress_current"] == 2
    assert operation_summary["progress_total"] == 2
    assert "updated_at" not in operation_summary


def test_open_project_does_not_heal_audio_blocks_with_missing_derived_audio(tmp_path) -> None:
    """
    @brief      Verify a missing derived WAV cannot prove Audio Blocks completion.
    @details    Generated audio paths derive from `speech_block_id`; completion
                still requires the claimed audio to exist on disk.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("AudioMissingDerived", tmp_path)
    (project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME).mkdir()
    outside_audio_path = tmp_path / "outside.wav"
    outside_audio_path.write_bytes(b"RIFF")
    _write_audio_blocks_document_fixture(project_root, status="in_progress")
    manifest["operations"]["audio_blocks"]["status"] = "in_progress"
    project_workspace_service.save_manifest(manifest, project_root)

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "ok"
    assert open_result["manifest"]["operations"]["audio_blocks"]["status"] == "in_progress"
    assert outside_audio_path.is_file()


def test_open_project_advances_current_stage_from_contiguous_completed_artifacts(tmp_path) -> None:
    """
    @brief      Verify current stage advances only when contiguous workflow evidence exists.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("StageHeal", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("Story", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-25T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("Story", encoding="utf-8")
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("Story", encoding="utf-8")
    _write_json(
        project_root / config.EXTRACTION_METADATA_FILE_NAME,
        {
            "status": "completed",
            "progress_current": 1,
            "progress_total": 1,
            "warnings": [],
            "character_count": 5,
            "word_count": 1,
            "line_count": 1,
            "page_count": None,
        },
    )
    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "repair_required"
    assert open_result["corrupted_step"] == "extraction"
    assert open_result["changes"] == []


def test_open_project_warns_for_corrupt_speech_blocks_artifact_without_healing(tmp_path) -> None:
    """
    @brief      Verify corrupt artifacts produce warnings but no completed metadata promotion.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("CorruptSpeech", tmp_path)
    manifest["current_stage"] = "speech_blocks_ready"
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME).write_text("{broken", encoding="utf-8")

    open_result = project_workspace_service.open_project(project_root)

    assert open_result["status"] == "ok"
    assert open_result["manifest"]["operations"]["speech_blocks"]["status"] == "not_started"


def _operation_state(status: str, current: int, total: int) -> dict[str, object]:
    """
    @brief      Build a compact operation-state fixture.
    @param[in]  status Operation status token.
    @param[in]  current Current progress count.
    @param[in]  total Total progress count.
    @return     Operation-state fixture payload.
    @exception  None
    """
    completed_at = "2026-04-25T12:01:00+00:00" if status == "completed" else None
    return {
        "status": status,
        "progress_current": current,
        "progress_total": total,
        "mode": "test",
        "started_at": "2026-04-25T12:00:00+00:00",
        "completed_at": completed_at,
        "updated_at": "2026-04-25T12:01:00+00:00",
        "warning_count": 0,
    }


def _write_json(path: Path, payload: object) -> None:
    """
    @brief      Write one JSON fixture file.
    @param[in]  path Target file path.
    @param[in]  payload JSON-serializable payload.
    @return     None.
    @exception  None
    """
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# END OF FILE
