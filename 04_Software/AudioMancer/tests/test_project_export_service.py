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
from audiomancer.services import narrator_definition_service, project_export_service, project_workspace_service
from chunking_test_support import build_chunking_document

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


def test_project_export_markdown_character_dossiers_survive_separator_and_colon_prompts(tmp_path) -> None:
    """
    @brief      Verify tricky voice prompts do not corrupt the Markdown character table.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-19
    @version    0.1.0
    """
    project_root, manifest = _build_export_project(tmp_path)
    tricky_prompt = "Whispered: intimate.\n\n----\n\nTone: warm and resonant."
    _write_json(
        project_root / config.CHARACTER_PROFILE_FILE_NAME,
        [
            {
                "character_id": "stefan",
                "canonical_name": "Ștefan",
                "gender_hint": "male",
                "age_hint": "old",
                "voice_definition_prompt": tricky_prompt,
            }
        ],
    )

    markdown = project_export_service.render_export(
        project_root,
        manifest,
        project_export_service.EXPORT_KIND_CHARACTERS,
        project_export_service.EXPORT_FORMAT_MARKDOWN,
    )
    plain = project_export_service.render_export(
        project_root,
        manifest,
        project_export_service.EXPORT_KIND_CHARACTERS,
        project_export_service.EXPORT_FORMAT_TXT,
    )

    # Exactly one character subsection: the embedded "----" must not split Ștefan into two.
    assert markdown.count("### ") == 1
    assert "### Ștefan" in markdown
    assert "### Character" not in markdown
    # The full prompt stays in one escaped table cell; no spurious "Tone" attribute row.
    assert "Whispered: intimate.<br><br>----<br><br>Tone: warm and resonant." in markdown
    assert "| **Tone** |" not in markdown
    # Plain-text export preserves the literal multi-line prompt verbatim.
    assert tricky_prompt in plain


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

    assert "Target Language: ro" in content
    assert "Context Window: 4096" in content
    assert "Maximum Output Tokens: 512" in content
    assert "Total Tokens: 18" in content
    assert "AI Profile:" not in content
    assert "AI Base URL:" not in content
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
        document = json.loads(archive.read(config.NARRATOR_VOICE_FILE_NAME).decode("utf-8"))
        profile = document["profiles"][0]
        assert sorted(archive.namelist()) == [
            f"audio_narator_{profile['profile_id']}.wav",
            config.NARRATOR_VOICE_FILE_NAME,
        ]
        assert profile["prompt_text"] == "A warm narrator definition."
        assert profile["sample"]["preview_text"] == "Narrator preview."
    with zipfile.ZipFile(character_zip) as archive:
        assert "character_voices/Stefan.wav" in archive.namelist()
        assert "Character voice definition." in archive.read("character_voices/Stefan.txt").decode("utf-8")
    with zipfile.ZipFile(assembly_zip) as archive:
        assert "audio_assembly/audiobook.wav" in archive.namelist()
        manifest_text = archive.read("audio_assembly/audio_assembly_manifest.txt").decode("utf-8")
        assert "Output Mode: whole_book" in manifest_text
        assert "Duration: 01:15" in manifest_text
        assert "Size: 14 bytes" in manifest_text


def test_project_export_archives_never_include_ai_transaction_logs(tmp_path) -> None:
    """
    @brief      Verify no archive export bundles project-local AI transaction log files.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-19
    @version    0.1.0
    """
    project_root, manifest = _build_export_project(tmp_path)
    ai_log_name = (
        f"{config.AI_TRANSACTION_LOG_FILE_PREFIX}character_discovery_20260519{config.AI_TRANSACTION_LOG_FILE_EXTENSION}"
    )
    (project_root / ai_log_name).write_text('{"exchange_event": "request"}\n', encoding="utf-8")

    archive_kinds = (
        project_export_service.EXPORT_KIND_NARRATOR_VOICE,
        project_export_service.EXPORT_KIND_CHARACTER_VOICES,
        project_export_service.EXPORT_KIND_AUDIO_ASSEMBLY,
    )
    for export_kind in archive_kinds:
        archive_path = project_export_service.create_archive_export(
            project_root,
            manifest,
            export_kind,
            tmp_path / f"{export_kind}_no_ai_log.zip",
        )
        with zipfile.ZipFile(archive_path) as archive:
            offending = [
                name
                for name in archive.namelist()
                if config.AI_TRANSACTION_LOG_FILE_PREFIX in name.rsplit("/", maxsplit=1)[-1]
            ]
        assert offending == [], f"{export_kind} archive leaked AI logs: {offending}"


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
        build_chunking_document(
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
            ]
        ),
    )
    _write_json(
        project_root / config.TRANSLATED_CHUNKS_FILE_NAME,
        {
            "target_language": "ro",
            "status": "in_progress",
            "token_usage": {
                "input_tokens": 11,
                "output_tokens": 7,
                "total_tokens": 18,
                "usage_available": True,
            },
            "budget_metadata": {
                "context_window": 4096,
                "max_output_tokens": 512,
                "prompt_budget_tokens": 100,
                "text_budget_tokens": 2048,
                "safety_margin_tokens": 512,
            },
            "additional_translation_instructions": "",
            "chunks": [
                {
                    "chunk_id": "chunk-0001",
                    "translated_text": "Traducere cu diacritice: țară și inimă.",
                    "approved": True,
                },
                {"chunk_id": "chunk-0002", "translated_text": "", "approved": False},
            ],
        },
    )
    _write_ai_log(project_root / "log_ai_translation_20260425.log")

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

    narrator_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Narator Profile",
        "en",
        "A warm narrator definition.",
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
