#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@file test_ai_translation_service.py
@brief Focused translation-service tests for AudioMancer.
@details Verifies persisted translation artifacts, resumable translation,
         review-state updates, and approval helpers.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.2.0
"""

import json

from audiomancer import config
from audiomancer.services import ai_translation_service
from audiomancer.services import project_workspace_service


def test_ai_translation_service_creates_translation_artifacts(monkeypatch, tmp_path) -> None:
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationArtifactsProject")
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "validate_required_prompts",
        lambda _names: None,
    )
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    monkeypatch.setattr(
        ai_translation_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {"translated_text": "Translated text"},
            "usage": {
                "input_tokens": 100,
                "output_tokens": 25,
                "total_tokens": 125,
                "usage_available": True,
            },
        },
    )

    report = ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
    )

    translation_root = project_root / config.TRANSLATION_FOLDER_NAME
    assert (translation_root / "input_story.json").is_file()
    assert (translation_root / config.TRANSLATED_CHUNKS_FILE_NAME).is_file()
    assert (translation_root / config.TRANSLATION_REPORT_FILE_NAME).is_file()
    assert (translation_root / config.OPERATION_STATE_FILE_NAME).is_file()
    assert report["translated_chunk_count"] == 2
    assert report["token_usage"]["total_tokens"] == 250


def test_ai_translation_service_approve_and_edit_update_review_state(tmp_path) -> None:
    project_root, _manifest = _create_chunked_project(tmp_path, "TranslationReviewProject")
    source_chunks, translated_chunks, _report = ai_translation_service.ensure_translation_records(
        project_root,
        "ro",
        "profile-1",
    )
    translated_chunks[0]["translated_text"] = "Translated one"
    translated_chunks[0]["status"] = ai_translation_service.TRANSLATED_CHUNK_STATUS_TRANSLATED
    translated_chunks[0]["translated_at"] = "2026-04-07T12:00:00+00:00"
    report = ai_translation_service._rebuild_report(translated_chunks, "ro", "profile-1")
    ai_translation_service._persist_translation_state(
        project_root,
        source_chunks,
        translated_chunks,
        report,
        operation_state=ai_translation_service._build_operation_state(
            project_root,
            source_chunks,
            translated_chunks,
            report,
            status="running",
            started_at="2026-04-07T12:00:00+00:00",
            completed_at=None,
            profile_id="profile-1",
            target_language="ro",
            log_path=project_root / config.TRANSLATION_FOLDER_NAME / "log_ai_transactions_20260407.log",
            token_usage={
                "input_tokens": 11,
                "output_tokens": 7,
                "total_tokens": 18,
                "usage_available": True,
            },
            resume_checkpoint={"next_untranslated_chunk_id": "chunk-0002"},
        ),
    )

    report = ai_translation_service.approve_chunk(project_root, "chunk-0001", "ro", "profile-1")
    assert report["approved_chunk_count"] == 1
    report = ai_translation_service.update_translated_text(project_root, "chunk-0001", "Edited translation", "ro", "profile-1")
    assert report["approved_chunk_count"] == 0


def test_ai_translation_service_resume_preserves_completed_chunks(monkeypatch, tmp_path) -> None:
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationResumeProject")
    source_chunks, translated_chunks, _report = ai_translation_service.ensure_translation_records(
        project_root,
        "ro",
        "profile-1",
    )
    translated_chunks[0]["translated_text"] = "Existing translation"
    translated_chunks[0]["status"] = ai_translation_service.TRANSLATED_CHUNK_STATUS_TRANSLATED
    translated_chunks[0]["translated_at"] = "2026-04-07T12:00:00+00:00"
    report = ai_translation_service._rebuild_report(translated_chunks, "ro", "profile-1")
    ai_translation_service._persist_translation_state(
        project_root,
        source_chunks,
        translated_chunks,
        report,
        operation_state=ai_translation_service._build_operation_state(
            project_root,
            source_chunks,
            translated_chunks,
            report,
            status="running",
            started_at="2026-04-07T12:00:00+00:00",
            completed_at=None,
            profile_id="profile-1",
            target_language="ro",
            log_path=project_root / config.TRANSLATION_FOLDER_NAME / "log_ai_transactions_20260407.log",
            token_usage={
                "input_tokens": 20,
                "output_tokens": 10,
                "total_tokens": 30,
                "usage_available": True,
            },
            resume_checkpoint={"next_untranslated_chunk_id": "chunk-0002"},
        ),
    )
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "validate_required_prompts",
        lambda _names: None,
    )
    monkeypatch.setattr(
        ai_translation_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    calls = []
    monkeypatch.setattr(
        ai_translation_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: calls.append("called") or {
            "payload": {"translated_text": "New translation"},
            "usage": {
                "input_tokens": 50,
                "output_tokens": 15,
                "total_tokens": 65,
                "usage_available": True,
            },
        },
    )

    report = ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
    )

    assert len(calls) == 1
    translated_chunks = ai_translation_service.load_translated_chunks(project_root)
    assert translated_chunks[0]["translated_text"] == "Existing translation"
    assert translated_chunks[1]["translated_text"] == "New translation"
    assert report["translated_chunk_count"] == 2
    assert report["token_usage"]["total_tokens"] == 95


def _create_chunked_project(tmp_path, name: str):
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 12,
    }
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [
        f"20_chunking/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root / "20_chunking"
    chunk_root.mkdir(parents=True, exist_ok=True)
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps([
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "chapter_label": "Chapter I",
                "text": "Original one",
                "source_start_line": 1,
                "source_end_line": 1,
                "chunking_mode": "deterministic",
                "semantic_strategy": None,
                "scene_note": None,
            },
            {
                "chunk_id": "chunk-0002",
                "sequence_index": 2,
                "chapter_label": "Chapter I",
                "text": "Original two",
                "source_start_line": 3,
                "source_end_line": 3,
                "chunking_mode": "deterministic",
                "semantic_strategy": None,
                "scene_note": None,
            },
        ], indent=2) + "\n",
        encoding="utf-8",
    )
    return project_root, manifest


def _profile_payload() -> dict[str, object]:
    return {
        "id": "profile-1",
        "label": "Translation Profile",
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234",
        "api_key": "",
        "model_name": "qwen3-8b",
        "context_window": 4096,
        "max_output_tokens": 512,
        "request_timeout_seconds": 30,
        "temperature": 0.2,
        "supports_structured_output": False,
        "enabled": True,
    }
