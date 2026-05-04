#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
@version 0.7.0
"""

# IMPORTS

import json

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import (
    audio_blocks_service,
    character_discovery_service,
    character_voices_service,
    project_workspace_service,
    speech_blocks_service,
)
from audiomancer.ui.controllers import characters_ui_controller
from audiomancer.ui.main_window import MainWindow


def test_character_ui_controller_first_run_shows_info_popup(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character ui controller first run shows info popup.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
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
    monkeypatch.setattr(
        characters_ui_controller,
        "_has_previous_character_discovery_state",
        lambda _window: False,
    )

    characters_ui_controller.handle_start_discovery_requested(window, "profile-1")

    assert popup_calls
    assert len(start_calls) == 1


def test_character_ui_controller_resume_uses_current_selected_profile(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character ui controller resume uses current selected profile.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerResumeCurrentProfile")
    window = _build_window(qtbot, project_root)
    start_calls = []
    used_profiles = []
    monkeypatch.setattr(
        characters_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )
    monkeypatch.setattr(
        characters_ui_controller.character_discovery_service,
        "start_or_continue_discovery",
        lambda _project_root, _manifest, profile_payload, **_kwargs: used_profiles.append(dict(profile_payload)),
    )

    characters_ui_controller.handle_start_discovery_requested(window, "profile-2")
    start_calls[0]["worker_callable"](project_root, window._current_manifest)

    assert used_profiles[0]["id"] == "profile-2"
    assert used_profiles[0]["model_name"] == "qwen3-14b"


def test_character_ui_controller_add_flow_enters_draft_mode(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character ui controller add flow enters draft mode.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
    """
    @brief      Validate character ui controller add rejects duplicate name.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
    """
    @brief      Validate character ui controller save new character persists and selects.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerSave")
    window = _build_window(qtbot, project_root)
    _write_downstream_artifacts(project_root, window)
    window._characters_page.begin_add_mode(_manual_draft_payload("Bob"))
    monkeypatch.setattr(characters_ui_controller, "_confirm_add_character", lambda *_args, **_kwargs: True)

    characters_ui_controller.handle_save_character_requested(
        window,
        window._characters_page.current_draft_payload(),
    )

    saved_profiles = character_discovery_service.load_character_profiles(project_root)
    assert any(profile["canonical_name"] == "Bob" for profile in saved_profiles)
    assert window._characters_page.current_character_id() is not None
    assert (project_root / config.NARRATOR_PROFILE_FILE_NAME).is_file()
    voice_targets = character_voices_service.load_voice_plan(project_root)
    assert {target["display_name"] for target in voice_targets} == {"Narator Voice", "Alice", "Bob"}
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert {block["speech_block_id"] for block in speech_blocks} == {"0001-000001", "0001-000002"}
    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert {block["speech_block_id"] for block in audio_blocks} == {"0001-000001", "0001-000002"}
    assert window._current_manifest["operations"]["narrator_definition"]["status"] == "completed"
    assert window._current_manifest["operations"]["character_voices"]["status"] == "completed"
    assert window._current_manifest["operations"]["speech_blocks"]["status"] == "completed"
    assert window._current_manifest["current_stage"] == "speech_blocks_ready"
    assert window._current_manifest["narrator_profile_name"] == "Narrator"
    assert window._current_manifest["narrator_language"] == "en"


def test_character_ui_controller_delete_flow_confirms_and_removes(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character ui controller delete flow confirms and removes.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerDelete")
    window = _build_window(qtbot, project_root)
    _write_downstream_artifacts(project_root, window)
    monkeypatch.setattr(
        characters_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    characters_ui_controller.handle_delete_character_requested(window, "alice")

    assert character_discovery_service.load_character_profiles(project_root) == []
    assert (project_root / config.NARRATOR_PROFILE_FILE_NAME).is_file()
    assert character_voices_service.load_voice_plan(project_root) == []
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert len(speech_blocks) == 2
    alice_block = next(block for block in speech_blocks if block["speech_block_id"] == "0001-000001")
    assert alice_block["speaker_kind"] == speech_blocks_service.SPEAKER_KIND_NARRATOR
    assert alice_block["speaker_id"] == "narrator"
    assert alice_block["speaker_display_name"] == "Narrator"
    assert alice_block["approved"] is False
    assert audio_blocks_service.load_audio_blocks(project_root)[0]["speech_block_id"] == "0001-000002"
    assert window._current_manifest["operations"]["narrator_definition"]["status"] == "completed"
    assert window._current_manifest["operations"]["character_voices"]["status"] == "completed"
    assert window._current_manifest["operations"]["audio_assembly"]["status"] == "not_started"
    assert window._current_manifest["narrator_profile_name"] == "Narrator"
    assert window._current_manifest["narrator_language"] == "en"


def test_character_ui_controller_edit_marks_assigned_blocks_for_review(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character ui controller edit selectively invalidates assigned speech and audio blocks.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerEdit")
    window = _build_window(qtbot, project_root)
    _write_downstream_artifacts(project_root, window)
    monkeypatch.setattr(characters_ui_controller, "_confirm_edit_character", lambda *_args, **_kwargs: True)
    window._characters_page.begin_edit_mode()
    draft_payload = window._characters_page.current_draft_payload()
    draft_payload["canonical_name"] = "Alice Renamed"
    draft_payload["description"] = "Changed voice definition source"

    characters_ui_controller.handle_save_character_requested(window, draft_payload)

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    alice_block = next(block for block in speech_blocks if block["speech_block_id"] == "0001-000001")
    narrator_block = next(block for block in speech_blocks if block["speech_block_id"] == "0001-000002")
    assert alice_block["speaker_display_name"] == "Alice Renamed"
    assert alice_block["approved"] is False
    assert narrator_block["approved"] is True
    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert {block["speech_block_id"] for block in audio_blocks} == {"0001-000002"}
    voice_target = character_voices_service.voice_target_by_id(
        project_root,
        character_voices_service.character_target_id("alice"),
    )
    assert voice_target is not None
    assert voice_target["stale"] is True
    assert window._current_manifest["operations"]["audio_assembly"]["status"] == "not_started"


def test_character_ui_controller_selection_change_cancel_restores_current_row(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character ui controller selection change cancel restores current row.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerSelection")
    window = _build_window(qtbot, project_root)
    second_profile = dict(_saved_profile_payload())
    second_profile["character_id"] = "bob"
    second_profile["canonical_name"] = "Bob"
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHARACTER_PROFILE_FILE_NAME).write_text(
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


def test_character_ui_controller_regenerates_voice_definition_for_active_draft(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character ui controller regenerates voice definition for active draft.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerVoiceDefinition")
    window = _build_window(qtbot, project_root)
    message_calls = []
    monkeypatch.setattr(
        characters_ui_controller.misc_ui_controller,
        "show_message",
        lambda *_args: message_calls.append(_args),
    )
    window._characters_page.begin_edit_mode()
    window._characters_page._description_edit.setPlainText("Updated literary description")

    characters_ui_controller.handle_regenerate_voice_definition_requested(
        window,
        window._characters_page.current_draft_payload(),
    )

    regenerated_payload = window._characters_page.current_draft_payload()
    assert regenerated_payload["voice_definition_stale"] is False
    assert "Updated literary description" in regenerated_payload["voice_persona_summary"]
    assert message_calls


def _create_project(tmp_path, name: str):
    """
    @brief      Provide the create project test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    manifest["operations"]["translation"]["status"] = "completed"
    manifest["operations"]["character_discovery"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    discovery_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    chunk_root.mkdir(parents=True, exist_ok=True)
    discovery_root.mkdir(parents=True, exist_ok=True)
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": None,
                    "text": '"Hello there," said Alice.',
                    "source_start_line": 1,
                    "source_end_line": 1,
                    "chunking_mode": "deterministic",
                    "semantic_strategy": None,
                    "scene_note": None,
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (discovery_root / "input_story.json").write_text(
        json.dumps([{"chunk_id": "chunk-0001", "sequence_index": 1, "text": '"Hello there," said Alice.'}], indent=2)
        + "\n",
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
        )
        + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.CHARACTER_DISCOVERY_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
                "status": "completed",
                "input_paths": [],
                "output_paths": [f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CHARACTER_PROFILE_FILE_NAME}"],
                "artifact_paths": [
                    f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CHARACTER_DISCOVERY_REPORT_FILE_NAME}"
                ],
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
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root, manifest


def _build_window(qtbot, project_root):
    """
    @brief      Provide the build window test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
                "model_name": "qwen3-14b",
                "context_window": 8192,
                "max_output_tokens": 1024,
                "request_timeout_seconds": 30,
                "temperature": 0.4,
                "supports_structured_output": False,
                "enabled": True,
            },
        ],
        "default_character_extraction_profile_id": "profile-1",
    }
    window = MainWindow(settings_payload=settings_payload)
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    window.set_current_page("characters")
    return window


def _write_downstream_artifacts(project_root, window: MainWindow) -> None:
    """
    @brief      Create representative downstream artifacts and completed manifest entries.
    @param[in]  project_root Active temporary project root.
    @param[in]  window Main window carrying the manifest under test.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
    """
    (project_root / config.NARRATOR_PROFILE_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "profile_id": "narrator-profile",
                    "display_name": "Narrator",
                    "language": "en",
                    "preview_text": "Narrator sample.",
                    "is_selected": True,
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / config.NARRATOR_SELECTION_FILE_NAME).write_text(
        json.dumps({"selected_profile_id": "narrator-profile", "selected_language": "en"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_root / "alice_sample.wav").write_bytes(b"RIFFalice")
    (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "target_id": character_voices_service.character_target_id("alice"),
                    "target_kind": character_voices_service.TARGET_KIND_CHARACTER,
                    "display_name": "Alice",
                    "character_id": "alice",
                    "prompt_text": "Alice voice.",
                    "default_prompt_text": "Alice voice.",
                    "preview_text": "Alice preview.",
                    "editable": True,
                    "sample_mode": character_voices_service.SAMPLE_MODE_VOICE_DESIGNER,
                    "sample_audio_path": "alice_sample.wav",
                    "sample_metadata": {"target_id": character_voices_service.character_target_id("alice")},
                    "updated_at": "2026-04-08T12:02:00+00:00",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    speech_blocks = [
        {
            "speech_block_id": "0001-000001",
            "chunk_id": "chunk-0001",
            "sequence_index": 1,
            "speaker_kind": speech_blocks_service.SPEAKER_KIND_CHARACTER,
            "speaker_id": "alice",
            "speaker_display_name": "Alice",
            "content_kind": speech_blocks_service.CONTENT_KIND_DIALOGUE,
            "source_text": '"Hello there," said Alice.',
            "text": "Hello there.",
            "approved": True,
            "approved_at": "2026-04-08T12:03:00+00:00",
        },
        {
            "speech_block_id": "0001-000002",
            "chunk_id": "chunk-0001",
            "sequence_index": 2,
            "speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
            "source_text": "Narration line.",
            "text": "Narration line.",
            "approved": True,
            "approved_at": "2026-04-08T12:03:00+00:00",
        },
    ]
    (project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(speech_blocks, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_root / config.SPEECH_BLOCKS_REPORT_FILE_NAME).write_text(
        json.dumps(
            {
                "speech_block_count": 2,
                "approved_block_count": 2,
                "speech_blocks_stage_status": "completed",
                "source_language": "en",
                "source_kind": "original",
                "ai_profile_id": "profile-1",
                "token_usage": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_operation_state(project_root, config.SPEECH_BLOCKS_STATE_FILE_NAME, "completed", "speech_blocks")
    generated_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    generated_root.mkdir(parents=True, exist_ok=True)
    (generated_root / "0001-000001.wav").write_bytes(b"RIFFalice-block")
    (generated_root / "0001-000001.json").write_text("{}\n", encoding="utf-8")
    (generated_root / "0001-000002.wav").write_bytes(b"RIFFnarrator-block")
    (generated_root / "0001-000002.json").write_text("{}\n", encoding="utf-8")
    audio_blocks = [
        {
            "speech_block_id": "0001-000001",
            "sequence_index": 1,
            "chunk_id": "chunk-0001",
            "speaker_id": "alice",
            "speaker_display_name": "Alice",
            "content_kind": speech_blocks_service.CONTENT_KIND_DIALOGUE,
            "text": "Hello there.",
            "voice_target_id": character_voices_service.character_target_id("alice"),
            "voice_source_kind": "character",
            "audio_relative_path": f"{config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME}/0001-000001.wav",
            "metadata_relative_path": f"{config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME}/0001-000001.json",
            "generated": True,
            "approved": True,
            "approved_at": "2026-04-08T12:04:00+00:00",
        },
        {
            "speech_block_id": "0001-000002",
            "sequence_index": 2,
            "chunk_id": "chunk-0001",
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
            "text": "Narration line.",
            "voice_target_id": character_voices_service.TARGET_ID_NARRATOR,
            "voice_source_kind": "narrator",
            "audio_relative_path": f"{config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME}/0001-000002.wav",
            "metadata_relative_path": f"{config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME}/0001-000002.json",
            "generated": True,
            "approved": True,
            "approved_at": "2026-04-08T12:04:00+00:00",
        },
    ]
    (project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(audio_blocks, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_root / config.AUDIO_BLOCKS_REPORT_FILE_NAME).write_text(
        json.dumps({"audio_block_count": 2, "approved_block_count": 2, "voice_language": "en"}, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_operation_state(project_root, config.AUDIO_BLOCKS_STATE_FILE_NAME, "completed", "audio_blocks")
    audiobook_root = project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME
    audiobook_root.mkdir(parents=True, exist_ok=True)
    (audiobook_root / "book.wav").write_bytes(b"RIFFassembled")
    (project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME).write_text("{}\n", encoding="utf-8")
    _write_operation_state(project_root, config.AUDIO_ASSEMBLY_STATE_FILE_NAME, "completed", "audio_assembly")
    for operation_kind in (
        "narrator_definition",
        "character_voices",
        "speech_blocks",
        "audio_blocks",
        "audio_assembly",
    ):
        window._current_manifest["operations"][operation_kind]["status"] = "completed"
    window._current_manifest["current_stage"] = "speech_blocks_ready"
    window._current_manifest["narrator_profile_name"] = "Narrator"
    window._current_manifest["narrator_language"] = "en"


def _write_operation_state(project_root, file_name: str, status: str, mode: str) -> None:
    """
    @brief      Create a compact operation state fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    (project_root / file_name).write_text(
        json.dumps(
            {
                "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
                "status": status,
                "progress_current": 1,
                "progress_total": 1,
                "mode": mode,
                "started_at": "2026-04-08T12:00:00+00:00",
                "completed_at": "2026-04-08T12:05:00+00:00",
                "updated_at": "2026-04-08T12:05:00+00:00",
                "warning_count": 0,
                "metadata": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _saved_profile_payload() -> dict[str, object]:
    """
    @brief      Provide the saved profile payload test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    return character_discovery_service.regenerate_character_voice_definition(
        {
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
    )


def _manual_draft_payload(name: str) -> dict[str, object]:
    """
    @brief      Provide the manual draft payload test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    return character_discovery_service.regenerate_character_voice_definition(
        {
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
    )


# END OF FILE
