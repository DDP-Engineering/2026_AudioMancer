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
@details Verifies guarded manual add or edit or save or delete flows plus
         discovery start and reset behavior for the Characters page controller.
"""

# IMPORTS

import json

from PySide6.QtWidgets import QMessageBox
import pytest

from audiomancer import config
from audiomancer.services import (
    audio_blocks_service,
    character_discovery_service,
    character_voices_service,
    narrator_definition_service,
    project_workspace_service,
    speech_blocks_service,
)
from audiomancer.ui.controllers import characters_ui_controller
from audiomancer.ui.main_window import MainWindow
from chunking_test_support import build_chunking_document


def test_character_ui_controller_first_run_shows_info_popup(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character ui controller first run shows info popup.
    @return     None.
    @exception  None
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
    monkeypatch.setattr(
        characters_ui_controller,
        "prompt_ai_character_discovery_instructions",
        lambda _window, _language: "",
    )

    characters_ui_controller.handle_start_discovery_requested(window, "profile-1")

    assert popup_calls
    assert len(start_calls) == 1


def test_character_ui_controller_resume_uses_current_selected_profile(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character ui controller resume uses current selected profile.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerResumeCurrentProfile")
    state_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHARACTERS_DOCUMENT_FILE_NAME
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    state_payload["status"] = "cancelled"
    state_payload["checkpoint"] = {
        "phase": "discovery",
        "completed_window_count": 0,
        "planned_window_count": 1,
        "next_chunk_index": 0,
        "candidates": [],
    }
    state_path.write_text(json.dumps(state_payload, indent=2) + "\n", encoding="utf-8")
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
    monkeypatch.setattr(
        characters_ui_controller,
        "prompt_ai_character_discovery_instructions",
        lambda _window, _language: "",
    )

    characters_ui_controller.handle_start_discovery_requested(window, "profile-2")
    start_calls[0]["worker_callable"](project_root, window._current_manifest)

    assert used_profiles[0]["id"] == "profile-2"
    assert used_profiles[0]["model_name"] == "qwen3-14b"


def test_character_ui_controller_cancelled_state_resumes_without_prompt(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-012 cancelled Character Discovery state is treated as resumable.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerCancelledResume")
    state_path = (
        project_root
        / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
        / config.CHARACTERS_DOCUMENT_FILE_NAME
    )
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    state_payload["status"] = "cancelled"
    state_payload["checkpoint"] = {
        "phase": "discovery",
        "completed_window_count": 1,
        "planned_window_count": 2,
        "next_chunk_index": 1,
        "candidates": [],
    }
    state_path.write_text(json.dumps(state_payload, indent=2) + "\n", encoding="utf-8")
    window = _build_window(qtbot, project_root)
    start_calls = []
    monkeypatch.setattr(
        characters_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )
    monkeypatch.setattr(
        characters_ui_controller,
        "prompt_ai_character_discovery_instructions",
        lambda _window, _language: (_ for _ in ()).throw(AssertionError("fresh prompt should not be shown")),
    )

    characters_ui_controller.handle_start_discovery_requested(window, "profile-1")

    assert len(start_calls) == 1


def test_character_ui_controller_passes_extra_prompt_to_discovery(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character discovery asks for optional operator rules and passes them to the worker.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerExtraPrompt")
    window = _build_window(qtbot, project_root)
    start_calls = []
    used_instructions = []
    monkeypatch.setattr(characters_ui_controller, "_is_resuming_character_discovery", lambda _window: False)
    monkeypatch.setattr(
        characters_ui_controller,
        "prompt_ai_character_discovery_instructions",
        lambda _window, _language: "Track honorifics as part of canonical names.",
    )
    monkeypatch.setattr(
        characters_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )
    monkeypatch.setattr(
        characters_ui_controller.character_discovery_service,
        "start_or_continue_discovery",
        lambda _project_root, _manifest, _profile_payload, **kwargs: used_instructions.append(
            kwargs.get("additional_character_discovery_instructions")
        ),
    )

    characters_ui_controller.handle_start_discovery_requested(window, "profile-1")
    start_calls[0]["worker_callable"](project_root, window._current_manifest)

    assert used_instructions == ["Track honorifics as part of canonical names."]


def test_character_ui_controller_add_flow_enters_draft_mode(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character ui controller add flow enters draft mode.
    @return     None.
    @exception  None
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


def test_character_ui_controller_edit_confirmation_cancel_keeps_view_mode(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character edit confirmation cancellation does not enter edit mode.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerEditCancel")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(characters_ui_controller, "_confirm_edit_character", lambda *_args, **_kwargs: False)

    characters_ui_controller.handle_edit_character_requested(window, "alice")

    assert window._characters_page.is_edit_mode() is False


def test_character_ui_controller_edit_confirmation_accepts_edit_mode(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character edit confirmation opens the selected profile editor.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerEditAccept")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(characters_ui_controller, "_confirm_edit_character", lambda *_args, **_kwargs: True)

    characters_ui_controller.handle_edit_character_requested(window, "alice")

    assert window._characters_page.is_edit_mode() is True


def test_character_ui_controller_save_new_character_persists_and_selects(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character ui controller save new character persists and selects.
    @return     None.
    @exception  None
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
    assert (project_root / config.NARRATOR_VOICE_FILE_NAME).is_file()
    voice_targets = character_voices_service.load_voice_plan(project_root)
    assert {target["display_name"] for target in voice_targets} == {"Narrator Voice", "Alice", "Bob"}
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
    assert (project_root / config.NARRATOR_VOICE_FILE_NAME).is_file()
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


def test_character_ui_controller_edit_preserves_speech_approval_for_voice_definition_change(
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Validate character voice-definition edits preserve Speech Blocks and clear only matching audio.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerEdit")
    window = _build_window(qtbot, project_root)
    _write_downstream_artifacts(project_root, window)
    window._characters_page.begin_edit_mode()
    draft_payload = window._characters_page.current_draft_payload()
    draft_payload["canonical_name"] = "Alice Renamed"
    draft_payload["voice_definition_prompt"] = "Create a consistent spoken voice for Alice Renamed."

    characters_ui_controller.handle_save_character_requested(window, draft_payload)

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    alice_block = next(block for block in speech_blocks if block["speech_block_id"] == "0001-000001")
    narrator_block = next(block for block in speech_blocks if block["speech_block_id"] == "0001-000002")
    assert alice_block["speaker_display_name"] == "Alice Renamed"
    assert alice_block["approved"] is True
    assert narrator_block["approved"] is True
    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert {block["speech_block_id"] for block in audio_blocks} == {"0001-000001", "0001-000002"}
    alice_audio_block = next(block for block in audio_blocks if block["speech_block_id"] == "0001-000001")
    narrator_audio_block = next(block for block in audio_blocks if block["speech_block_id"] == "0001-000002")
    assert audio_blocks_service.is_generated(alice_audio_block) is False
    assert alice_audio_block["audio_relative_path"] is None
    assert alice_audio_block["generation_fingerprint"] is None
    assert audio_blocks_service.is_generated(narrator_audio_block) is True
    voice_target = character_voices_service.voice_target_by_id(
        project_root,
        character_voices_service.character_target_id("alice"),
    )
    assert voice_target is not None
    assert (
        character_voices_service.has_target_sample(project_root, character_voices_service.character_target_id("alice"))
        is False
    )
    assert window._current_manifest["operations"]["audio_assembly"]["status"] == "not_started"


def test_character_ui_controller_save_with_progress_stays_synchronous(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate Character save progress runs on the synchronous controller path.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerEditProgress")
    window = _build_window(qtbot, project_root)
    _write_downstream_artifacts(project_root, window)
    window._characters_page.begin_edit_mode()
    draft_payload = window._characters_page.current_draft_payload()
    draft_payload["canonical_name"] = "Alice Progress"

    create_calls = []
    progress_updates = []
    process_calls = []
    original_create = characters_ui_controller.misc_ui_controller.create_progress_dialog
    original_remove_audio_blocks = audio_blocks_service.remove_audio_blocks_for_speech_blocks

    def _capture_create(*args, **kwargs):
        create_calls.append(kwargs)
        return original_create(*args, **kwargs)

    def _capture_remove_audio_blocks(*args, **kwargs):
        """
        @brief      Assert the page stays busy while downstream audio is reset.
        @return     Wrapped audio-block removal result.
        @exception  AssertionError Raised when busy-state expectations fail.
        """
        assert window._characters_page._busy is True
        assert kwargs["collect_preserved_paths"] is False
        return original_remove_audio_blocks(*args, **kwargs)

    monkeypatch.setattr(characters_ui_controller.misc_ui_controller, "create_progress_dialog", _capture_create)
    monkeypatch.setattr(
        characters_ui_controller.misc_ui_controller,
        "update_progress_dialog",
        lambda _window, percent, message, token_usage=None: progress_updates.append((percent, message)),
    )
    monkeypatch.setattr(
        characters_ui_controller.misc_ui_controller,
        "process_pending_ui_events",
        lambda: process_calls.append(True),
    )
    monkeypatch.setattr(audio_blocks_service, "remove_audio_blocks_for_speech_blocks", _capture_remove_audio_blocks)

    assert characters_ui_controller.handle_save_character_requested(window, draft_payload, show_progress=True) is True

    assert create_calls[0]["cancellable"] is False
    assert any(percent == 70 for percent, _message in progress_updates)
    assert progress_updates[-1][0] == 100
    assert process_calls
    assert window._operation_progress_dialog is None
    assert window._characters_page._busy is False


def test_character_ui_controller_save_progress_clears_after_failure(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate Character save progress cleanup runs when save mutation fails.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerEditProgressFailure")
    window = _build_window(qtbot, project_root)
    window._characters_page.begin_edit_mode()
    draft_payload = window._characters_page.current_draft_payload()
    original_update_character_profile = character_discovery_service.update_character_profile

    def _raise_after_progress(*args, **kwargs):
        """
        @brief      Raise after progress setup to verify cleanup behavior.
        @return     None.
        @exception  RuntimeError Always raised for this test double.
        """
        _ = args
        _ = kwargs
        raise RuntimeError("progress cleanup failure")

    monkeypatch.setattr(character_discovery_service, "update_character_profile", _raise_after_progress)

    with pytest.raises(RuntimeError, match="progress cleanup failure"):
        characters_ui_controller.handle_save_character_requested(window, draft_payload, show_progress=True)

    monkeypatch.setattr(character_discovery_service, "update_character_profile", original_update_character_profile)
    assert window._operation_progress_dialog is None
    assert window._characters_page._busy is False


def test_character_ui_controller_selection_change_cancel_restores_current_row(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate character ui controller selection change cancel restores current row.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project(tmp_path, "CharacterControllerSelection")
    window = _build_window(qtbot, project_root)
    second_profile = dict(_saved_profile_payload())
    second_profile["character_id"] = "bob"
    second_profile["canonical_name"] = "Bob"
    (
        project_root
        / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
        / config.CHARACTERS_DOCUMENT_FILE_NAME
    ).write_text(
        json.dumps(
            _characters_document([_saved_profile_payload(), second_profile]),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    window.show_project_state(project_root, project_workspace_service.load_manifest(project_root))
    window._characters_page.begin_edit_mode()
    window._characters_page._voice_definition_prompt_edit.setPlainText("Changed")
    monkeypatch.setattr(
        characters_ui_controller,
        "_prompt_unsaved_changes",
        lambda *_args, **_kwargs: "cancel",
    )

    characters_ui_controller.handle_selection_change_requested(window, "bob")

    assert window._characters_page.current_character_id() == "alice"
    assert window._characters_page._character_list.currentRow() == 0


def test_character_ui_controller_reset_recovers_invalid_character_document(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify reset removes an invalid document and restores ordinary page state.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project(tmp_path, "InvalidCharacterDiscoveryReset")
    document_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHARACTERS_DOCUMENT_FILE_NAME
    window = _build_window(qtbot, project_root)
    document_path.write_text("{", encoding="utf-8")
    message_calls = []
    monkeypatch.setattr(
        characters_ui_controller.misc_ui_controller,
        "show_message",
        lambda *_args: message_calls.append(True),
    )

    window._refresh_characters_page_state(project_root, window._current_manifest, "en")

    assert window._characters_page._reset_button.isEnabled() is True
    assert window._characters_page._start_button.isEnabled() is False
    characters_ui_controller.handle_reset_discovery_requested(window)

    refreshed_manifest = project_workspace_service.load_manifest(project_root)
    assert document_path.exists() is False
    assert refreshed_manifest["operations"]["character_discovery"]["status"] == "not_started"
    assert window._characters_page._reset_button.isEnabled() is False
    assert window._characters_page._start_button.isEnabled() is True
    assert message_calls == [True]


def test_character_operation_summary_does_not_reload_source_chunks(monkeypatch, tmp_path) -> None:
    """Verify manifest summary projection reads only the authoritative character document."""
    project_root, _manifest = _create_project(tmp_path, "CharacterSummaryWithoutChunkReload")
    monkeypatch.setattr(
        character_discovery_service,
        "load_input_chunks",
        lambda *_args, **_kwargs: pytest.fail("summary projection reloaded source chunks"),
    )

    summary = characters_ui_controller._character_operation_summary(project_root)  # noqa: SLF001

    assert summary is not None
    assert summary["status"] == "completed"


def _create_project(tmp_path, name: str):
    """
    @brief      Provide the create project test helper.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  name Stable name associated with the requested object.
    @return     None.
    @exception  None
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
            build_chunking_document(
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
                ]
            ),
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
    (discovery_root / config.CHARACTERS_DOCUMENT_FILE_NAME).write_text(
        json.dumps(_characters_document([_saved_profile_payload()]), indent=2)
        + "\n",
        encoding="utf-8",
    )
    return project_root, manifest


def _build_window(qtbot, project_root):
    """
    @brief      Provide the build window test helper.
    @return     None.
    @exception  None
    """
    settings_payload = {
        "language": "en",
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
    """
    narrator_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Narrator",
        "en",
        "A consistent narrator voice.",
        "Narrator sample.",
    )
    narrator_definition_service.select_narrator_profile(project_root, narrator_profile["profile_id"], "en")
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
    speech_blocks_service.write_speech_blocks_document(
        project_root,
        {
            "status": "completed",
            "source": {"kind": "original", "language": "en", "fingerprint": "chars-fixture-fingerprint"},
            "ai_profile_id": "profile-1",
            "instructions": "",
            "scene_ambience": {"enabled": False},
            "response_contract": "direct_blocks",
            "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "usage_available": False},
            "budget_metadata": {},
            "checkpoint": {
                "next_chunk_index": 1,
                "run_token": "2026-04-08T12:00:00+00:00",
                "log_relative_path": "log_ai_speech_blocks_20260408T120000Z.log",
                "source_snapshot_fingerprint": "chars-fixture-fingerprint",
                "source_language": "en",
                "ai_profile_id": "profile-1",
                "additional_speech_block_instructions_fingerprint": "",
                "speech_blocks_response_contract": "direct_blocks",
            },
            "failure": None,
            "blocks": speech_blocks,
        },
    )
    generated_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    generated_root.mkdir(parents=True, exist_ok=True)
    (generated_root / "0001-000001.wav").write_bytes(b"RIFFalice-block")
    (generated_root / "0001-000002.wav").write_bytes(b"RIFFnarrator-block")
    audio_blocks_service.write_audio_blocks_document(
        project_root,
        {
            "status": "completed",
            "voice_language": "en",
            "input_fingerprint": "characters-fixture",
            "checkpoint": None,
            "blocks": [
                {
                    "speech_block_id": "0001-000001",
                    "voice_target_id": character_voices_service.character_target_id("alice"),
                    "generated": True,
                    "approved": True,
                    "audio_can_play": True,
                    "audio_duration_seconds": None,
                    "generation_fingerprint": None,
                },
                {
                    "speech_block_id": "0001-000002",
                    "voice_target_id": character_voices_service.TARGET_ID_NARRATOR,
                    "generated": True,
                    "approved": True,
                    "audio_can_play": True,
                    "audio_duration_seconds": None,
                    "generation_fingerprint": None,
                },
            ],
        },
    )
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
    """
    return character_discovery_service.regenerate_character_voice_definition(
        {
            "character_id": "alice",
            "canonical_name": "Alice",
            "aliases": ["Al"],
            "gender_hint": "",
            "age_hint": "adult",
            "voice_definition_prompt": "Create a consistent spoken voice for Alice.",
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


def _characters_document(
    profiles: list[dict[str, object]],
) -> dict[str, object]:
    """Build one strict completed Character Discovery fixture."""
    return {
        "status": "completed",
        "source": {
            "kind": "original",
            "language": "en",
            "fingerprint": "fixture",
        },
        "instructions": "",
        "token_usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "usage_available": False,
        },
        "character_profile_id_last_used": "profile-1",
        "rejected_candidates": [],
        "checkpoint": None,
        "failure": None,
        "characters": [
            character_discovery_service._nested_character_profile(profile)  # noqa: SLF001
            for profile in profiles
        ],
    }


def _manual_draft_payload(name: str) -> dict[str, object]:
    """
    @brief      Provide the manual draft payload test helper.
    @return     None.
    @exception  None
    """
    return character_discovery_service.regenerate_character_voice_definition(
        {
            "character_id": "draft_bob",
            "canonical_name": name,
            "aliases": [],
            "gender_hint": "",
            "age_hint": "",
            "voice_definition_prompt": f"Create a consistent spoken voice for {name}.",
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
