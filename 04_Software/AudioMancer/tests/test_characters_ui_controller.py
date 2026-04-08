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
@details Verifies guarded manual add or save or delete flows plus discovery
         start and reset behavior for the Characters page controller.
@author Eng. Dan Dumitru Pasare
@date 2026-04-08
@version 0.2.0
"""

import json

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import character_discovery_service
from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import characters_ui_controller
from audiomancer.ui.main_window import MainWindow


def test_character_ui_controller_first_run_shows_info_popup(monkeypatch, qtbot, tmp_path) -> None:
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
    monkeypatch.setattr(
        characters_ui_controller,
        "_has_previous_character_discovery_state",
        lambda _window: False,
    )

    characters_ui_controller.handle_start_discovery_requested(window, "profile-1")

    assert popup_calls
    assert len(start_calls) == 1


def test_character_ui_controller_add_flow_enters_draft_mode(monkeypatch, qtbot, tmp_path) -> None:
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerAdd")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        characters_ui_controller.QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("Bob", True),
    )

    characters_ui_controller.handle_add_character_requested(window)

    assert window._characters_page.is_add_mode() is True
    assert window._characters_page.current_draft_payload()["canonical_name"] == "Bob"
    assert window._characters_page._save_character_button.isEnabled() is True


def test_character_ui_controller_add_rejects_duplicate_name(monkeypatch, qtbot, tmp_path) -> None:
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerDuplicate")
    window = _build_window(qtbot, project_root)
    warning_calls = []
    monkeypatch.setattr(
        characters_ui_controller.QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("Alice", True),
    )
    monkeypatch.setattr(
        characters_ui_controller.QMessageBox,
        "warning",
        lambda *args: warning_calls.append(args),
    )

    characters_ui_controller.handle_add_character_requested(window)

    assert warning_calls
    assert window._characters_page.is_add_mode() is False


def test_character_ui_controller_save_new_character_persists_and_selects(monkeypatch, qtbot, tmp_path) -> None:
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerSave")
    window = _build_window(qtbot, project_root)
    window._characters_page.begin_add_mode(_manual_draft_payload("Bob"))

    characters_ui_controller.handle_save_character_requested(
        window,
        window._characters_page.current_draft_payload(),
    )

    saved_profiles = character_discovery_service.load_character_profiles(project_root)
    assert any(profile["canonical_name"] == "Bob" for profile in saved_profiles)
    assert window._characters_page.current_character_id() is not None


def test_character_ui_controller_delete_flow_confirms_and_removes(monkeypatch, qtbot, tmp_path) -> None:
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerDelete")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        characters_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    characters_ui_controller.handle_delete_character_requested(window, "alice")

    assert character_discovery_service.load_character_profiles(project_root) == []


def test_character_ui_controller_selection_change_cancel_restores_current_row(monkeypatch, qtbot, tmp_path) -> None:
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerSelection")
    window = _build_window(qtbot, project_root)
    second_profile = dict(_saved_profile_payload())
    second_profile["character_id"] = "bob"
    second_profile["canonical_name"] = "Bob"
    (project_root / config.CHARACTER_DISCOVERY_FOLDER_NAME / config.CHARACTER_PROFILE_FILE_NAME).write_text(
        json.dumps([_saved_profile_payload(), second_profile], indent=2) + "\n",
        encoding="utf-8",
    )
    window.show_project_state(project_root, project_workspace_service.load_manifest(project_root))
    window._characters_page.begin_edit_mode()
    window._characters_page._description_edit.setPlainText("Changed")
    monkeypatch.setattr(
        characters_ui_controller,
        "_prompt_unsaved_changes",
        lambda *_args, **_kwargs: "cancel",
    )

    characters_ui_controller.handle_selection_change_requested(window, "bob")

    assert window._characters_page.current_character_id() == "alice"
    assert window._characters_page._character_list.currentRow() == 0


def _create_project(tmp_path, name: str):
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-08T12:00:00+00:00",
        "size_bytes": 12,
    }
    manifest["current_stage"] = "character_discovery_ready"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [
        f"{config.CHUNKING_FOLDER_NAME}/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    manifest["operations"]["translation"]["status"] = "completed"
    manifest["operations"]["character_discovery"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root / config.CHUNKING_FOLDER_NAME
    discovery_root = project_root / config.CHARACTER_DISCOVERY_FOLDER_NAME
    chunk_root.mkdir(parents=True, exist_ok=True)
    discovery_root.mkdir(parents=True, exist_ok=True)
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [ {
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
    (discovery_root / "input_story.json").write_text(
        json.dumps([{"chunk_id": "chunk-0001", "sequence_index": 1, "text": '"Hello there," said Alice.'}], indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.CHARACTER_PROFILE_FILE_NAME).write_text(
        json.dumps([_saved_profile_payload()], indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.CHARACTER_DISCOVERY_REPORT_FILE_NAME).write_text(
        json.dumps(
            {
                "input_chunk_count": 1,
                "analyzed_window_count": 1,
                "merged_candidate_count": 1,
                "character_count": 1,
                "character_discovery_mode": "ai_assisted",
                "character_profile_id_last_used": "profile-1",
                "window_size": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE,
                "window_overlap": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
                "warning_count": 0,
                "warnings": [],
                "generated_at": "2026-04-08T12:01:00+00:00",
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.OPERATION_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": config.CHARACTER_DISCOVERY_FOLDER_NAME,
                "status": "completed",
                "input_paths": [],
                "output_paths": [f"{config.CHARACTER_DISCOVERY_FOLDER_NAME}/{config.CHARACTER_PROFILE_FILE_NAME}"],
                "artifact_paths": [f"{config.CHARACTER_DISCOVERY_FOLDER_NAME}/{config.CHARACTER_DISCOVERY_REPORT_FILE_NAME}"],
                "progress_current": 1,
                "progress_total": 1,
                "mode": "ai_assisted",
                "started_at": "2026-04-08T12:00:00+00:00",
                "completed_at": "2026-04-08T12:01:00+00:00",
                "updated_at": "2026-04-08T12:01:00+00:00",
                "warning_count": 0,
                "metadata": {"ai_profile_id": "profile-1", "character_count": 1},
                "resume_checkpoint": None,
            },
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
            }
        ],
        "default_character_extraction_profile_id": "profile-1",
    }
    window = MainWindow(settings_payload=settings_payload)
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    return window


def _saved_profile_payload() -> dict[str, object]:
    return {
        "character_id": "alice",
        "canonical_name": "Alice",
        "aliases": ["Al"],
        "gender_hint": "",
        "age_band": "",
        "role_summary": "Lead speaker",
        "description": "Original description",
        "temperament": "",
        "social_status": "",
        "speaking_style": "",
        "accent_or_dialect_hints": "",
        "voice_notes": "",
        "relationship_hints": ["Knows Bob."],
        "confidence": "high",
        "evidence": [
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "source_excerpt": '"Hello there," said Alice.',
                "reason": "Alice speaks.",
            }
        ],
        "updated_at": "2026-04-08T12:01:00+00:00",
    }


def _manual_draft_payload(name: str) -> dict[str, object]:
    return {
        "character_id": "draft_bob",
        "canonical_name": name,
        "aliases": [],
        "gender_hint": "",
        "age_band": "",
        "role_summary": "",
        "description": "",
        "temperament": "",
        "social_status": "",
        "speaking_style": "",
        "accent_or_dialect_hints": "",
        "voice_notes": "",
        "relationship_hints": [],
        "confidence": "",
        "evidence": [
            {
                "chunk_id": character_discovery_service.MANUAL_CHARACTER_EVIDENCE_CHUNK_ID,
                "sequence_index": 0,
                "source_excerpt": character_discovery_service.MANUAL_CHARACTER_EVIDENCE_NOTE,
                "reason": character_discovery_service.MANUAL_CHARACTER_EVIDENCE_NOTE,
            }
        ],
        "updated_at": None,
    }


# END OF FILE
