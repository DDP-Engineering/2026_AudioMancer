#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_translation_ui_controller.py
@brief Focused controller tests for monofile AI Translation.
@details Verifies resume prompting, derived manifest ownership, reset behavior,
         and retained broad downstream invalidation.
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import ai_translation_service, narrator_definition_service, project_workspace_service
from audiomancer.ui.controllers import ai_translation_ui_controller
from audiomancer.ui.main_window import MainWindow
from chunking_test_support import build_chunking_document

# PUBLIC API


@pytest.mark.parametrize(
    "status",
    [
        ai_translation_service.TRANSLATION_STATUS_RUNNING,
        ai_translation_service.TRANSLATION_STATUS_IN_PROGRESS,
        ai_translation_service.TRANSLATION_STATUS_CANCELLED,
        ai_translation_service.TRANSLATION_STATUS_FAILED,
    ],
)
def test_translation_controller_resumes_without_prompt_for_all_resumable_statuses(
    monkeypatch,
    qtbot,
    tmp_path,
    status,
) -> None:
    """
    @brief      Verify REQ-UX-003 every resumable monofile status reuses saved rules.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  qtbot Pytest-Qt fixture used to manage and interact with Qt widgets.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  status Operation status token under evaluation.
    @return     None.
    """
    project_root, _manifest = _create_project(tmp_path, f"TranslationResume{status}")
    document = _document(status)
    document["chunks"][0]["translated_text"] = "Existing"
    ai_translation_service.write_translation_document(project_root, document)
    window = _build_window(qtbot, project_root)
    prompt_calls = []
    starts = []
    monkeypatch.setattr(
        ai_translation_ui_controller,
        "prompt_ai_translation_instructions",
        lambda *_args: prompt_calls.append(True),
    )
    monkeypatch.setattr(
        ai_translation_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: starts.append(kwargs),
    )

    ai_translation_ui_controller.handle_start_translation_requested(window, "profile-1")

    assert prompt_calls == []
    assert len(starts) == 1


def test_translation_start_worker_observes_latest_pending_page_edit(monkeypatch, qtbot, tmp_path) -> None:
    """Verify page persistence completes before the mocked translation worker reads its document."""
    project_root, manifest = _create_project(tmp_path, "TranslationLatestEditBeforeWorker")
    source_chunks = [
        {"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Original one"},
        {"chunk_id": "chunk-0002", "sequence_index": 2, "text": "Original two"},
    ]
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(build_chunking_document(source_chunks), indent=2) + "\n",
        encoding="utf-8",
    )
    document = _document(ai_translation_service.TRANSLATION_STATUS_IN_PROGRESS)
    document["chunks"] = [
        {"chunk_id": "chunk-0001", "translated_text": "Earlier text", "approved": False},
        {"chunk_id": "chunk-0002", "translated_text": "", "approved": False},
    ]
    ai_translation_service.write_translation_document(project_root, document)
    window = _build_window(qtbot, project_root)
    window._current_page_id = "ai_translation"
    window._refresh_ai_translation_page_state(project_root, manifest, "en")
    observed_by_worker = []

    def observe_persisted_document(_window, **_kwargs) -> None:
        """Record the authoritative text at the operation-dispatch boundary."""
        persisted = ai_translation_service.load_translation_document(project_root)
        assert persisted is not None
        observed_by_worker.append(str(persisted["chunks"][0]["translated_text"]))

    monkeypatch.setattr(ai_translation_ui_controller, "_start_operation", observe_persisted_document)
    page = window._ai_translation_page
    page._translated_text_edit.setPlainText("Latest exact edit")
    assert page._edit_timer.isActive() is True

    page._emit_start_translation()

    persisted = ai_translation_service.load_translation_document(project_root)
    assert persisted is not None
    assert observed_by_worker == ["Latest exact edit"]
    assert persisted["chunks"][0]["translated_text"] == "Latest exact edit"
    assert page._edit_timer.isActive() is False


def test_translation_controller_syncs_derived_manifest_summary(qtbot, tmp_path) -> None:
    """
    @brief      Verify REQ-UX-003 the controller owns compact manifest synchronization.
    @param[in]  qtbot Pytest-Qt fixture used to manage and interact with Qt widgets.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, _manifest = _create_project(tmp_path, "TranslationManifestSummary")
    window = _build_window(qtbot, project_root)

    ai_translation_ui_controller._sync_manifest_after_translation(
        window,
        {
            "status": ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING,
            "translated_count": 1,
            "approved_count": 0,
            "total_count": 1,
            "warning_count": 0,
        },
    )
    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "translation_ready"
    assert window._current_manifest["operations"]["translation"] == {
        "status": ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING,
        "progress_current": 1,
        "progress_total": 1,
        "mode": "ai_assisted",
        "warning_count": 0,
    }

    ai_translation_ui_controller._sync_manifest_after_translation(
        window,
        {
            "status": ai_translation_service.TRANSLATION_STATUS_COMPLETED,
            "translated_count": 1,
            "approved_count": 1,
            "total_count": 1,
            "warning_count": 0,
        },
    )
    assert window._current_manifest["current_stage"] == "character_discovery_ready"


def test_retranslate_before_translation_start_is_inert(monkeypatch, qtbot, tmp_path) -> None:
    """Verify an impossible selected-chunk retranslation has no worker, prompt, error, or manifest effects."""
    project_root, _manifest = _create_project(tmp_path, "TranslationUnavailableRetranslate")
    window = _build_window(qtbot, project_root)
    persisted_manifest_before = project_workspace_service.load_manifest(project_root)
    prompt_calls = []
    starts = []
    warning_calls = []
    monkeypatch.setattr(
        ai_translation_ui_controller,
        "prompt_ai_translation_instructions",
        lambda *_args: prompt_calls.append(True),
    )
    monkeypatch.setattr(
        ai_translation_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: starts.append(kwargs),
    )
    monkeypatch.setattr(
        ai_translation_ui_controller.QMessageBox,
        "warning",
        lambda *args: warning_calls.append(args),
    )

    ai_translation_ui_controller.handle_retranslate_selected_requested(
        window,
        "profile-1",
        "chunk-0001",
    )

    assert prompt_calls == []
    assert starts == []
    assert warning_calls == []
    assert not (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).exists()
    assert project_workspace_service.load_manifest(project_root) == persisted_manifest_before


def test_translation_controller_keeps_broad_downstream_reset_on_approval_loss(qtbot, tmp_path) -> None:
    """
    @brief      Verify REQ-UX-003 approval loss retains the existing broad reset policy.
    @param[in]  qtbot Pytest-Qt fixture used to manage and interact with Qt widgets.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, _manifest = _create_project(tmp_path, "TranslationDownstreamReset")
    (project_root / config.CHARACTERS_DOCUMENT_FILE_NAME).write_text(
        json.dumps(_characters_document("original")) + "\n",
        encoding="utf-8",
    )
    narrator_definition_service.ensure_narrator_voice_document(project_root)
    (project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME).write_text("[]\n", encoding="utf-8")
    window = _build_window(qtbot, project_root)
    assert window._current_manifest is not None
    window._current_manifest["operations"]["narrator_definition"]["status"] = "completed"
    window._current_manifest["operations"]["character_discovery"]["status"] = "completed"
    window._current_manifest["operations"]["speech_blocks"]["status"] = "completed"

    ai_translation_ui_controller._sync_manifest_after_translation(
        window,
        {
            "status": ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING,
            "translated_count": 1,
            "approved_count": 0,
            "total_count": 1,
            "warning_count": 0,
        },
    )

    assert window._current_manifest["operations"]["narrator_definition"]["status"] == "completed"
    assert window._current_manifest["operations"]["character_discovery"]["status"] == "not_started"
    assert window._current_manifest["operations"]["speech_blocks"]["status"] == "not_started"
    assert (project_root / config.NARRATOR_VOICE_FILE_NAME).exists()
    assert not (project_root / config.CHARACTERS_DOCUMENT_FILE_NAME).exists()
    assert not (project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME).exists()


def test_translation_controller_reset_removes_monofile_and_preserves_narrator(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify reset removes Translation and downstream data but preserves narrator profiles.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  qtbot Pytest-Qt fixture used to manage and interact with Qt widgets.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, _manifest = _create_project(tmp_path, "TranslationReset")
    ai_translation_service.write_translation_document(project_root, _document("review_pending"))
    narrator_definition_service.ensure_narrator_voice_document(project_root)
    (project_root / config.CHARACTERS_DOCUMENT_FILE_NAME).write_text(
        json.dumps(_characters_document("translated")) + "\n",
        encoding="utf-8",
    )
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        ai_translation_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: ai_translation_ui_controller.QMessageBox.StandardButton.Yes,
    )

    ai_translation_ui_controller.handle_reset_translation_requested(window)

    assert not (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).exists()
    assert (project_root / config.NARRATOR_VOICE_FILE_NAME).exists()
    assert not (project_root / config.CHARACTERS_DOCUMENT_FILE_NAME).exists()


# TEST HELPERS


def _create_project(tmp_path, name: str):
    """
    @brief      Create one active project with one canonical source chunk.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  name Stable name associated with the requested object.
    @return     Created project root and manifest payload.
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-07-16T12:00:00+00:00",
        "size_bytes": 12,
    }
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["target_language"] = "ro"
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            build_chunking_document([{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Original"}]),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root, manifest


def _build_window(qtbot, project_root):
    """
    @brief      Build a main window with one enabled translation profile.
    @param[in]  qtbot Pytest-Qt fixture used to manage and interact with Qt widgets.
    @param[in]  project_root Active project root folder.
    @return     Configured main-window test double.
    """
    window = MainWindow(
        settings_payload={
            "language": "en",
            "play_completion_beep": False,
            "llm_profiles": [
                {
                    "id": "profile-1",
                    "label": "Translation Profile",
                    "backend_kind": "lmstudio",
                    "base_url": "http://127.0.0.1:1234",
                    "api_key": "",
                    "model_name": "qwen3-8b",
                    "context_window": 4096,
                    "max_output_tokens": 512,
                    "enabled": True,
                }
            ],
        }
    )
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    return window


def _document(status: str) -> dict[str, object]:
    """Build one strict monofile fixture."""
    return {
        "target_language": "ro",
        "status": status,
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "usage_available": False},
        "budget_metadata": {
            "context_window": 4096,
            "max_output_tokens": 512,
            "prompt_budget_tokens": 100,
            "text_budget_tokens": 2048,
            "safety_margin_tokens": 512,
        },
        "additional_translation_instructions": "Saved instructions",
        "chunks": [{"chunk_id": "chunk-0001", "translated_text": "", "approved": False}],
    }


def _characters_document(source_kind: str) -> dict[str, object]:
    """Build one strict Character Discovery document fixture."""
    return {
        "status": "completed",
        "source": {
            "kind": source_kind,
            "language": "ro" if source_kind == "translated" else "en",
            "fingerprint": "stale",
        },
        "instructions": "",
        "token_usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "usage_available": False,
        },
        "character_profile_id_last_used": "profile-1",
        "checkpoint": None,
        "failure": None,
        "characters": [],
    }


# END OF FILE
