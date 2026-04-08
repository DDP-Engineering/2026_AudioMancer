#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_characters_ui_controller.py
@brief Character Discovery UI controller tests for AudioMancer.
@details Verifies the controller handles first-run messaging, resume profile
         selection, reset behavior, and profile-edit persistence.
@author Eng. Dan Dumitru Pasare
@date 2026-04-08
@version 0.1.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import characters_ui_controller
from audiomancer.ui.main_window import MainWindow


def test_character_ui_controller_first_run_shows_info_popup(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify the first discovery start shows the long-running AI information popup.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerFirstRun")
    window = _build_window(qtbot, project_root)
    popup_calls = []
    start_calls = []
    monkeypatch.setattr(
        characters_ui_controller.QMessageBox,
        "information",
        lambda *args: popup_calls.append(args),
    )
    monkeypatch.setattr(
        characters_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )

    characters_ui_controller.handle_start_discovery_requested(window, "profile-1")

    assert popup_calls
    assert len(start_calls) == 1


def test_character_ui_controller_resume_skips_popup_and_uses_persisted_profile(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify resumable discovery skips the first-run popup and reuses the persisted AI profile id.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    project_root, manifest = _create_project(tmp_path, "CharacterControllerResume")
    window = _build_window(qtbot, project_root)
    info_calls = []
    start_calls = []
    monkeypatch.setattr(
        characters_ui_controller.QMessageBox,
        "information",
        lambda *args: info_calls.append(args),
    )
    monkeypatch.setattr(
        characters_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )
    monkeypatch.setattr(
        characters_ui_controller.character_discovery_service,
        "load_operation_state",
        lambda _project_root: {
            "status": "running",
            "metadata": {"ai_profile_id": "profile-2"},
        },
    )
    monkeypatch.setattr(
        characters_ui_controller.character_discovery_service,
        "load_character_discovery_report",
        lambda _project_root: None,
    )
    monkeypatch.setattr(
        characters_ui_controller.character_discovery_service,
        "load_character_profiles",
        lambda _project_root: [],
    )
    monkeypatch.setattr(
        characters_ui_controller.character_discovery_service,
        "start_or_continue_discovery",
        lambda _project_root, _manifest, profile_payload, progress_callback=None, cancel_requested=None: {
            "character_profile_id_last_used": profile_payload["id"]
        },
    )

    characters_ui_controller.handle_start_discovery_requested(window, "profile-1")

    assert info_calls == []
    result = start_calls[0]["worker_callable"](
        project_root,
        dict(manifest),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )
    assert result["character_profile_id_last_used"] == "profile-2"


def test_character_ui_controller_reset_restores_translation_stage(qtbot, tmp_path) -> None:
    """
    @brief      Verify reset clears character discovery state and restores the manifest to translation-ready.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerReset")
    discovery_root = project_root / "40_character_discovery"
    (discovery_root / config.CHARACTER_PROFILE_FILE_NAME).write_text("[]\n", encoding="utf-8")
    window = _build_window(qtbot, project_root)

    characters_ui_controller.handle_reset_discovery_requested(window)

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "translation_ready"
    assert window._current_manifest["operations"]["character_discovery"]["status"] == "not_started"


def test_character_ui_controller_profile_change_persists_edit(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify one edited character profile is sent to the persistence service immediately.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerEdit")
    window = _build_window(qtbot, project_root)
    update_calls = []
    monkeypatch.setattr(
        characters_ui_controller.character_discovery_service,
        "update_character_profile",
        lambda _project_root, payload: update_calls.append(payload),
    )

    characters_ui_controller.handle_profile_changed(
        window,
        {"character_id": "alice", "canonical_name": "Alice"},
    )

    assert update_calls == [{"character_id": "alice", "canonical_name": "Alice"}]


def _create_project(tmp_path, name: str):
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-08T12:00:00+00:00",
        "size_bytes": 12,
    }
    manifest["current_stage"] = "translation_ready"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [f"20_chunking/{config.CHUNK_ARTIFACT_FILE_NAME}"]
    manifest["operations"]["translation"]["status"] = "completed"
    manifest["operations"]["character_discovery"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root / "20_chunking"
    discovery_root = project_root / "40_character_discovery"
    chunk_root.mkdir(parents=True, exist_ok=True)
    discovery_root.mkdir(parents=True, exist_ok=True)
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [{
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "chapter_label": None,
                "text": '"Hello there," said Alice.',
                "source_start_line": 1,
                "source_end_line": 1,
                "chunking_mode": "deterministic",
                "semantic_strategy": None,
                "scene_note": None,
            }],
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return project_root, manifest


def _build_window(qtbot, project_root):
    settings_payload = {
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [
            {
                "id": "profile-1",
                "label": "Profile One",
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
            },
            {
                "id": "profile-2",
                "label": "Profile Two",
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
            },
        ],
        "default_character_extraction_profile_id": "profile-1",
    }
    window = MainWindow(settings_payload=settings_payload)
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    return window


# END OF FILE
