#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_project_export_service.py
@brief Project export projection service tests for AudioMancer.
@details Verifies readiness detection and TXT/Markdown rendering for Home-page
         user-facing export artifacts.
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.4.0
"""

# IMPORTS

import json
import zipfile

from audiomancer import config
from audiomancer.services import project_export_service, project_workspace_service

# PUBLIC API


def test_project_export_service_detects_readiness_for_all_export_types(tmp_path) -> None:
    """
    @brief      Verify all export types become available from completed operations and artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    project_root, manifest = _build_export_project(tmp_path)

    states = project_export_service.build_export_states(project_root, manifest)

    assert {state["export_kind"]: state["status"] for state in states} == {
        project_export_service.EXPORT_KIND_CLEANED_TEXT: project_export_service.EXPORT_STATUS_AVAILABLE,
        project_export_service.EXPORT_KIND_TEXT_CHUNKS: project_export_service.EXPORT_STATUS_AVAILABLE,
        project_export_service.EXPORT_KIND_AI_TRANSLATION: project_export_service.EXPORT_STATUS_AVAILABLE,
        project_export_service.EXPORT_KIND_CHARACTERS: project_export_service.EXPORT_STATUS_AVAILABLE,
        project_export_service.EXPORT_KIND_NARRATOR_VOICE: project_export_service.EXPORT_STATUS_AVAILABLE,
        project_export_service.EXPORT_KIND_CHARACTER_VOICES: project_export_service.EXPORT_STATUS_AVAILABLE,
        project_export_service.EXPORT_KIND_SPEECH_BLOCKS: project_export_service.EXPORT_STATUS_AVAILABLE,
        project_export_service.EXPORT_KIND_AUDIO_ASSEMBLY: project_export_service.EXPORT_STATUS_AVAILABLE,
    }


def test_project_export_service_reports_not_ready_and_missing_artifact(tmp_path) -> None:
    """
    @brief      Verify readiness separates incomplete operations from missing artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    project_root, manifest = _build_export_project(tmp_path)
    manifest["operations"]["chunking"]["status"] = "not_started"
    (project_root / config.CLEANED_TEXT_FILE_NAME).unlink()

    states = {
        str(state["export_kind"]): str(state["status"])
        for state in project_export_service.build_export_states(project_root, manifest)
    }

    assert states[project_export_service.EXPORT_KIND_TEXT_CHUNKS] == project_export_service.EXPORT_STATUS_NOT_READY
    assert (
        states[project_export_service.EXPORT_KIND_CLEANED_TEXT] == project_export_service.EXPORT_STATUS_MISSING_ARTIFACT
    )


def test_project_export_service_preserves_utf8_and_source_header(tmp_path) -> None:
    """
    @brief      Verify exported content preserves Romanian text and source metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = _build_export_project(tmp_path)

    content = project_export_service.render_export(
        project_root,
        manifest,
        project_export_service.EXPORT_KIND_CLEANED_TEXT,
        project_export_service.EXPORT_FORMAT_TXT,
    )

    assert "poveste_șță.txt" in content
    assert "Original Extension: .txt" in content
    assert "Ștefan intră în încăpere." in content


def test_project_export_service_renders_markdown_and_hides_internal_metadata(tmp_path) -> None:
    """
    @brief      Verify Markdown rendering and hidden internal metadata in user-facing bodies.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.1
    """
    project_root, manifest = _build_export_project(tmp_path)

    chunks_content = project_export_service.render_export(
        project_root,
        manifest,
        project_export_service.EXPORT_KIND_TEXT_CHUNKS,
        project_export_service.EXPORT_FORMAT_MARKDOWN,
    )
    translation_content = project_export_service.render_export(
        project_root,
        manifest,
        project_export_service.EXPORT_KIND_AI_TRANSLATION,
        project_export_service.EXPORT_FORMAT_MARKDOWN,
    )
    speech_content = project_export_service.render_export(
        project_root,
        manifest,
        project_export_service.EXPORT_KIND_SPEECH_BLOCKS,
        project_export_service.EXPORT_FORMAT_MARKDOWN,
    )

    assert chunks_content.startswith("# AudioMancer Export")
    assert "Primul fragment curat." in chunks_content
    assert "chunk-0001" not in chunks_content
    assert "chunk_id" not in chunks_content
    assert "Traducere cu diacritice: țară și inimă." in translation_content
    assert "translated_text" not in translation_content
    assert "Speaker:" not in speech_content
    assert "Ștefan  \nVoi spune adevărul." in speech_content
    assert "speech_block_id" not in speech_content
    assert "speaker_id" not in speech_content


def test_project_export_service_renders_character_dossier_labels(tmp_path) -> None:
    """
    @brief      Verify character exports use readable dossier labels.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    project_root, manifest = _build_export_project(tmp_path)

    content = project_export_service.render_export(
        project_root,
        manifest,
        project_export_service.EXPORT_KIND_CHARACTERS,
        project_export_service.EXPORT_FORMAT_TXT,
    )

    assert "Name: Ștefan" in content
    assert "Gender Hint: male" in content
    assert "Age Hint: old" in content
    assert "Speaking Style: teatral" not in content
    assert "Voice Definition Prompt:" in content


def test_project_export_service_renders_markdown_character_dossiers_as_tables(tmp_path) -> None:
    """
    @brief      Verify Markdown character exports emphasize extracted attributes.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    project_root, manifest = _build_export_project(tmp_path)

    content = project_export_service.render_export(
        project_root,
        manifest,
        project_export_service.EXPORT_KIND_CHARACTERS,
        project_export_service.EXPORT_FORMAT_MARKDOWN,
    )

    assert "### Ștefan" in content
    assert "| Attribute | Value |" in content
    assert "| **Gender Hint** | male |" in content
    assert "| **Age Hint** | old |" in content
    assert "| **Voice Definition Prompt** |" in content
    assert "Name: Ștefan Gender Hint:" not in content


def test_project_export_service_exports_ai_request_parameters_without_prompts(tmp_path) -> None:
    """
    @brief      Verify AI exports include model request settings but not prompt bodies or secrets.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = _build_export_project(tmp_path)

    content = project_export_service.render_export(
        project_root,
        manifest,
        project_export_service.EXPORT_KIND_AI_TRANSLATION,
        project_export_service.EXPORT_FORMAT_TXT,
    )

    assert "AI Profile: profile_1" in content
    assert "AI Backend: openai_compatible" in content
    assert "AI Base URL: https://llm.example/v1" in content
    assert "AI Model: theater-model-romanian" in content
    assert "AI Temperature: 0.45" in content
    assert "AI Max Tokens: 2048" in content
    assert "system prompt should not be exported" not in content
    assert "user prompt should not be exported" not in content
    assert "sk-secret" not in content


def test_project_export_service_creates_voice_and_audio_archives(tmp_path) -> None:
    """
    @brief      Verify ZIP exports include generated audio assets and companion manifests.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    project_root, manifest = _build_export_project(tmp_path)

    narrator_zip = project_export_service.create_archive_export(
        project_root,
        manifest,
        project_export_service.EXPORT_KIND_NARRATOR_VOICE,
        tmp_path / "narrator_voice",
    )
    character_zip = project_export_service.create_archive_export(
        project_root,
        manifest,
        project_export_service.EXPORT_KIND_CHARACTER_VOICES,
        tmp_path / "character_voices.zip",
    )
    assembly_zip = project_export_service.create_archive_export(
        project_root,
        manifest,
        project_export_service.EXPORT_KIND_AUDIO_ASSEMBLY,
        tmp_path / "assembly.zip",
    )

    with zipfile.ZipFile(narrator_zip) as archive:
        assert sorted(archive.namelist()) == [
            "narator_voice/Narator_Profile.txt",
            "narator_voice/Narator_Profile.wav",
        ]
        narrator_text = archive.read("narator_voice/Narator_Profile.txt").decode("utf-8")
        assert "A warm narrator definition." in narrator_text
        assert "Narrator preview." in narrator_text
    with zipfile.ZipFile(character_zip) as archive:
        assert "character_voices/Stefan.wav" in archive.namelist()
        assert "Character voice definition." in archive.read("character_voices/Stefan.txt").decode("utf-8")
    with zipfile.ZipFile(assembly_zip) as archive:
        assert "audio_assembly/audiobook.wav" in archive.namelist()
        manifest_text = archive.read("audio_assembly/audio_assembly_manifest.txt").decode("utf-8")
        assert "Output Mode: whole_book" in manifest_text
        assert "Duration: 01:15" in manifest_text
        assert "Size: 14 bytes" in manifest_text


def test_project_export_service_detects_paths_inside_project(tmp_path) -> None:
    """
    @brief      Verify selected save paths can be checked against the active project root.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("PathProject", tmp_path)

    assert project_export_service.is_path_inside_project(project_root, project_root / "export.txt") is True
    assert project_export_service.is_path_inside_project(project_root, tmp_path / "export.txt") is False


# LOCAL HELPERS


def _build_export_project(tmp_path):
    """
    @brief      Create a project with all exportable artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     Tuple of project root and manifest.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project("ExportProject", tmp_path)
    manifest["source_document"] = {
        "original_name": "poveste_șță.txt",
        "stored_relative_path": "poveste_șță.txt",
        "file_type": "txt",
        "imported_at": "2026-04-25T10:00:00+00:00",
        "size_bytes": 64,
    }
    for operation_kind in (
        "cleanup",
        "chunking",
        "translation",
        "character_discovery",
        "narrator_definition",
        "character_voices",
        "speech_blocks",
        "audio_assembly",
    ):
        manifest["operations"][operation_kind]["status"] = "completed"

    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "Ștefan intră în încăpere.\n\nȚara întreagă tace.\n",
        encoding="utf-8",
    )
    _write_json(
        project_root / config.CLEANUP_REPORT_FILE_NAME,
        {
            "cleanup_mode": "deterministic",
            "paragraph_count": 2,
            "removed_line_count": 1,
            "detected_chapter_count": 0,
            "detected_language": "ro",
            "warnings": ["No explicit chapter headings."],
        },
    )
    _write_json(project_root / config.CLEANUP_STATE_FILE_NAME, {"status": "completed", "warning_count": 1})

    _write_json(
        project_root / config.CHUNK_ARTIFACT_FILE_NAME,
        [
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "chapter_label": None,
                "text": "Primul fragment curat.",
                "chunking_mode": "deterministic",
                "semantic_strategy": None,
            },
            {
                "chunk_id": "chunk-0002",
                "sequence_index": 2,
                "chapter_label": None,
                "text": "Al doilea fragment curat.",
                "chunking_mode": "deterministic",
                "semantic_strategy": None,
            },
        ],
    )
    _write_json(
        project_root / config.CHUNKING_REPORT_FILE_NAME,
        {"chunking_mode": "deterministic", "chunk_count": 2, "detected_chapter_count": 0},
    )
    _write_json(project_root / config.CHUNKING_STATE_FILE_NAME, {"status": "completed", "metadata": {}})

    _write_json(
        project_root / config.TRANSLATED_CHUNKS_FILE_NAME,
        [
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "source_text": "Source one",
                "translated_text": "Traducere cu diacritice: țară și inimă.",
                "approved": True,
                "target_language": "ro",
                "translation_profile_id": "profile_1",
            }
        ],
    )
    _write_json(
        project_root / config.TRANSLATION_REPORT_FILE_NAME,
        {
            "target_language": "ro",
            "translation_profile_id_last_used": "profile_1",
            "translated_chunk_count": 1,
            "approved_chunk_count": 1,
            "total_chunk_count": 1,
            "token_usage": {
                "input_tokens": 11,
                "output_tokens": 7,
                "total_tokens": 18,
                "usage_available": True,
            },
        },
    )
    _write_ai_log(project_root / "log_ai_translation_20260425.log")
    _write_json(
        project_root / config.TRANSLATION_STATE_FILE_NAME,
        {
            "status": "completed",
            "mode": "ai_assisted",
            "metadata": {"log_relative_path": "log_ai_translation_20260425.log"},
        },
    )

    _write_json(
        project_root / config.CHARACTER_PROFILE_FILE_NAME,
        [
            {
                "character_id": "stefan",
                "canonical_name": "Ștefan",
                "gender_hint": "male",
                "age_hint": "old",
                "voice_definition_prompt": "A dramatic Romanian baritone voice.",
            }
        ],
    )
    _write_json(
        project_root / config.CHARACTER_DISCOVERY_REPORT_FILE_NAME,
        {
            "character_profile_id_last_used": "profile_1",
            "analyzed_window_count": 1,
            "input_chunk_count": 2,
            "character_count": 1,
        },
    )
    _write_json(project_root / config.CHARACTER_DISCOVERY_STATE_FILE_NAME, {"status": "completed", "metadata": {}})

    narrator_audio_path = project_root / "audio_narator_profile.wav"
    narrator_audio_path.write_bytes(b"RIFF-narrator")
    _write_json(
        project_root / config.NARRATOR_PROFILE_FILE_NAME,
        [
            {
                "profile_id": "narrator-1",
                "display_name": "Narator Profile",
                "language": "en",
                "prompt_text": "A warm narrator definition.",
                "preview_text": "Narrator preview.",
                "sample_audio_path": narrator_audio_path.name,
                "sample_metadata": {
                    "display_name": "Narator Profile",
                    "prompt_text": "A warm narrator definition.",
                    "preview_text": "Narrator preview.",
                },
            }
        ],
    )
    _write_json(project_root / config.NARRATOR_SELECTION_FILE_NAME, {"selected_profile_id": "narrator-1"})

    character_audio_path = project_root / "audio_stefan.wav"
    character_audio_path.write_bytes(b"RIFF-character")
    _write_json(
        project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME,
        [
            {
                "target_id": "character_stefan",
                "target_kind": "character",
                "display_name": "Stefan",
                "character_id": "stefan",
                "prompt_text": "Character voice definition.",
                "preview_text": "Character preview.",
                "editable": True,
                "sample_audio_path": character_audio_path.name,
                "sample_metadata": {
                    "display_name": "Stefan",
                    "prompt_text": "Character voice definition.",
                    "preview_text": "Character preview.",
                },
            }
        ],
    )

    _write_json(
        project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME,
        [
            {
                "speech_block_id": "0001-000001",
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "speaker_id": "stefan",
                "speaker_display_name": "Ștefan",
                "text": "Voi spune adevărul.",
                "content_kind": "dialogue",
                "warning_flags": [],
            }
        ],
    )
    _write_json(
        project_root / config.SPEECH_BLOCKS_REPORT_FILE_NAME,
        {
            "source_language": "ro",
            "source_kind": "translated_chunks",
            "speech_blocks_profile_id_last_used": "profile_1",
            "speech_block_count": 1,
            "warning_count": 0,
        },
    )
    _write_json(project_root / config.SPEECH_BLOCKS_STATE_FILE_NAME, {"status": "completed", "metadata": {}})

    audiobook_path = project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME / "audiobook.wav"
    audiobook_path.parent.mkdir(parents=True, exist_ok=True)
    audiobook_path.write_bytes(b"RIFF-audiobook")
    _write_json(
        project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME,
        {
            "audio_assembly_stage_status": "completed",
            "settings": {
                "output_mode": "whole_book",
                "max_duration_minutes": 30,
                "output_format": "wav",
                "inter_block_silence_ms": 250,
                "inter_chunk_silence_ms": 1000,
            },
            "outputs": [
                {
                    "output_key": "whole_book",
                    "file_name": "audiobook.wav",
                    "audio_relative_path": "audiobook/audiobook.wav",
                    "block_count": 1,
                    "duration_seconds": 75.0,
                    "generated": True,
                    "output_format": "wav",
                }
            ],
        },
    )
    return project_root, manifest


def _write_json(path, payload: object) -> None:
    """
    @brief      Write one UTF-8 JSON test artifact.
    @param[in]  path Target path.
    @param[in]  payload JSON-serializable payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_ai_log(path) -> None:
    """
    @brief      Write one AI transaction-log request record for export tests.
    @param[in]  path Target log path.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    payload = {
        "timestamp": "2026-04-25T10:10:00+00:00",
        "exchange_event": "request",
        "parsed_status": "pending",
        "profile_id": "profile_1",
        "backend_kind": "openai_compatible",
        "base_url": "https://llm.example/v1",
        "api_key": "sk-secret",
        "model_name": "theater-model-romanian",
        "request_payload": {
            "model": "theater-model-romanian",
            "messages": [
                {"role": "system", "content": "system prompt should not be exported"},
                {"role": "user", "content": "user prompt should not be exported"},
            ],
            "temperature": 0.45,
            "max_tokens": 2048,
        },
        "system_prompt": "system prompt should not be exported",
        "user_prompt": "user prompt should not be exported",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


# END OF FILE
