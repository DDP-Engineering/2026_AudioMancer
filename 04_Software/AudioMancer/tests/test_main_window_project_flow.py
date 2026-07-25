#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_main_window_project_flow.py
@brief Qt window tests for the copied AudioMancer main-window shell.
@details Validates that the DDP_Audiomancer-style toolbar, sidebar, and stacked
         pages are created without workflow functionality.
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 1.7.1
"""

# IMPORTS

import json

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QPushButton,
)

from audiomancer import config
from audiomancer.services import narrator_definition_service, project_workspace_service, speech_blocks_service
from audiomancer.ui.controllers import (
    home_ui_controller,
    text_cleanup_ui_controller,
)
import audiomancer.ui.main_window as main_window_module
from audiomancer.ui.main_window import MainWindow

# PUBLIC API


def test_main_window_creates_project_and_updates_shell(monkeypatch, qtbot, tmp_path, default_settings_payload) -> None:
    """
    @brief      Verify new-project creation activates the shell and project summary.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.2
    """

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        home_ui_controller.QInputDialog,
        "getText",
        lambda *args, **kwargs: ("Book5_CAL_CAL", True),
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)

    window._action_new_project.trigger()

    assert window._current_project_root == tmp_path / "Book5_CAL_CAL"
    assert window._current_manifest is not None
    assert window._current_manifest["display_name"] == "Book5_CAL_CAL"
    assert window._home_page._name_label.text() == "Project: Book5_CAL_CAL"
    assert window._sidebar.item(1).flags() != main_window_module.Qt.ItemFlag.NoItemFlags
    assert any(
        "Narator Voice" in window._home_page._stage_list.item(index).text()
        for index in range(window._home_page._stage_list.count())
    )
    assert any(
        "Character Voices" in window._home_page._stage_list.item(index).text()
        for index in range(window._home_page._stage_list.count())
    )


def test_main_window_opens_project_from_child_folder(monkeypatch, qtbot, tmp_path, default_settings_payload) -> None:
    """
    @brief      Verify open-project resolves the project root from a child folder.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.1
    """
    project_root, _manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    (project_root / "notes").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(project_root / "notes"),
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)

    window._action_open_project.trigger()

    assert window._current_project_root == project_root
    assert window._current_manifest is not None
    assert window._current_manifest["display_name"] == "Book5_CAL_CAL"
    assert window._home_page._path_label.text() == f"Path: {project_root}"


def test_main_window_clears_audio_players_when_switching_projects(qtbot, tmp_path, default_settings_payload) -> None:
    """
    @brief      Verify project activation releases stale playback sources and UI state.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.2.0
    """
    first_root, first_manifest = project_workspace_service.create_project("PlaybackSwitchOne", tmp_path)
    second_root, second_manifest = project_workspace_service.create_project("PlaybackSwitchTwo", tmp_path)
    first_audio_path = first_root / "preview.wav"
    first_audio_path.write_bytes(b"RIFF")

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(first_root, first_manifest)
    media_url = QUrl.fromLocalFile(str(first_audio_path))
    for player in (
        window._narator_voice_audio_player,
        window._character_voices_audio_player,
        window._audio_blocks_audio_player,
        window._audio_assembly_audio_player,
    ):
        player.setSource(media_url)
    window._narator_voice_page.set_preview_active(True)
    window._character_voices_page.set_preview_active(True)
    window._audio_blocks_playback_mode = "audiobook"
    window._audio_blocks_playback_block_ids = ["block-1"]
    window._audio_blocks_playback_index = 0
    window._audio_blocks_page.set_audiobook_playback_active(True)
    window._audio_assembly_playback_output_key = "part-0001"
    window._audio_assembly_playback_starting = True
    window._audio_assembly_page.set_playback_active(True)
    window._audio_assembly_page.set_playback_progress(250, 1000)

    window._activate_project(second_root, second_manifest)

    assert window._current_project_root == second_root
    assert window._narator_voice_audio_player.source().isEmpty()
    assert window._character_voices_audio_player.source().isEmpty()
    assert window._audio_blocks_audio_player.source().isEmpty()
    assert window._audio_assembly_audio_player.source().isEmpty()
    assert window._narator_voice_page._preview_active is False
    assert window._character_voices_page._preview_active is False
    assert window._audio_blocks_playback_mode is None
    assert window._audio_blocks_playback_block_ids == []
    assert window._audio_blocks_playback_index == -1
    assert window._audio_blocks_page._selected_playback_active is False
    assert window._audio_blocks_page._audiobook_playback_active is False
    assert window._audio_assembly_playback_output_key is None
    assert window._audio_assembly_playback_starting is False
    assert window._audio_assembly_page._playback_active is False
    assert window._audio_assembly_page._playback_position_ms == 0
    assert window._audio_assembly_page._playback_duration_ms == 0


def test_main_window_imports_source_and_locks_selection(monkeypatch, qtbot, tmp_path, default_settings_payload) -> None:
    """
    @brief      Verify source import updates the manifest, summary, and lock state.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.1
    """
    project_root, _manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    source_path = tmp_path / "story.epub"
    source_path.write_text("content", encoding="utf-8")
    replacement_source_path = tmp_path / "replacement.txt"
    replacement_source_path.write_text("replacement", encoding="utf-8")
    selected_source_path = [source_path]

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(selected_source_path[0]), ""),
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    window._home_page.import_requested.emit()

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "source_selected"
    assert window._current_manifest["source_document"]["original_name"] == "story.epub"
    assert window._home_page._source_label.text() == "Source: story.epub"
    assert window._home_page._stage_list.item(0).text() == "Text Cleanup | Not Started"
    assert window._home_page._import_button.isEnabled() is True

    selected_source_path[0] = replacement_source_path
    window._home_page.import_requested.emit()

    assert window._current_manifest["source_document"]["original_name"] == "replacement.txt"
    assert (project_root / "story.epub").exists() is False
    assert (project_root / "replacement.txt").read_text(encoding="utf-8") == "replacement"


def test_main_window_initializes_step_state_only_when_page_is_opened(qtbot, tmp_path, default_settings_payload) -> None:
    """
    @brief      Verify page activation creates only the state artifacts currently required by that page.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("PageStateProject", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)

    window._activate_project(project_root, manifest)

    assert (project_root / config.PROJECT_MANIFEST_FILE_NAME).is_file()
    assert (project_root / config.EXTRACTION_METADATA_FILE_NAME).exists() is False
    assert (project_root / config.CLEANUP_STATE_FILE_NAME).exists() is False
    assert (project_root / "chunking_state.json").exists() is False
    assert (project_root / "chunking_report.json").exists() is False
    assert (project_root / config.CHUNK_ARTIFACT_FILE_NAME).exists() is False
    assert (project_root / config.NARRATOR_VOICE_FILE_NAME).exists() is False
    assert (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).exists() is False

    window.set_current_page("text_cleanup")

    assert (project_root / config.EXTRACTION_METADATA_FILE_NAME).exists() is False
    assert (project_root / config.CLEANUP_STATE_FILE_NAME).exists() is False
    assert (project_root / config.CLEANUP_REPORT_FILE_NAME).exists() is False
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).exists() is False

    window.set_current_page("text_chunking")

    assert (project_root / "chunking_state.json").exists() is False
    assert (project_root / "chunking_report.json").exists() is False
    assert (project_root / config.CHUNK_ARTIFACT_FILE_NAME).exists() is False
    assert (project_root / config.NARRATOR_VOICE_FILE_NAME).exists() is False
    assert (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).exists() is False

    window.set_current_page("narator_voice")

    assert (project_root / config.NARRATOR_VOICE_FILE_NAME).is_file()
    assert (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).exists() is False

    window.set_current_page("character_voices")

    assert (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).is_file()


def test_main_window_restarts_completed_extraction_only_after_confirmation(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify completed extraction reruns only after operator confirmation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "RerunProject",
        tmp_path,
    )
    source_path = project_root / "story.txt"
    source_path.write_text("Story body", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    extracted_text = "Story body\n"
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(extracted_text, encoding="utf-8")
    (project_root / config.EXTRACTION_METADATA_FILE_NAME).write_text(
        json.dumps(
            {
                "status": "completed",
                "progress_current": 1,
                "progress_total": 1,
                "warnings": [],
                "character_count": len(extracted_text),
                "word_count": len(extracted_text.split()),
                "line_count": len(extracted_text.splitlines()),
                "page_count": None,
            }
        ),
        encoding="utf-8",
    )
    project_workspace_service.save_manifest(manifest, project_root)

    question_calls = []
    reset_calls = []
    extract_calls = []

    monkeypatch.setattr(
        text_cleanup_ui_controller.QMessageBox,
        "question",
        lambda *args, **kwargs: (
            question_calls.append(args),
            QMessageBox.StandardButton.No,
        )[1],
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_extraction_service,
        "reset_extraction_and_downstream",
        lambda root: reset_calls.append(root),
    )
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_extraction_service,
        "extract_text",
        lambda *args, **kwargs: extract_calls.append(args),
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    window._text_cleanup_page.extract_requested.emit()

    assert question_calls
    assert reset_calls == []
    assert extract_calls == []


def test_main_window_continues_unfinished_extraction_without_confirmation(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify unfinished extraction reruns continue directly without destructive confirmation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ResumeWindowProject",
        tmp_path,
    )
    source_path = project_root / "story.txt"
    source_path.write_text("Story body", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("Partial", encoding="utf-8")
    (project_root / config.EXTRACTION_METADATA_FILE_NAME).write_text(
        json.dumps(
            {
                "status": "failed",
                "progress_current": 1,
                "progress_total": 3,
                "warnings": [],
                "character_count": None,
                "word_count": None,
                "line_count": None,
                "page_count": None,
            }
        ),
        encoding="utf-8",
    )
    project_workspace_service.save_manifest(manifest, project_root)

    question_calls = []
    extract_calls = []

    monkeypatch.setattr(
        text_cleanup_ui_controller.QMessageBox,
        "question",
        lambda *args, **kwargs: question_calls.append(args),
    )

    def _fake_extract_text(*args, **kwargs):
        """
        @brief      Record one resumed extraction call and return a minimal report.
        @return     Final extraction metadata payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        extract_calls.append(args)
        extracted_text = "Story body\n"
        (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(extracted_text, encoding="utf-8")
        metadata = {
            "status": "completed",
            "progress_current": 1,
            "progress_total": 1,
            "warnings": [],
            "character_count": len(extracted_text),
            "word_count": len(extracted_text.split()),
            "line_count": len(extracted_text.splitlines()),
            "page_count": None,
        }
        (project_root / config.EXTRACTION_METADATA_FILE_NAME).write_text(
            json.dumps(
                metadata,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return metadata

    monkeypatch.setattr(
        text_cleanup_ui_controller.text_extraction_service,
        "extract_text",
        _fake_extract_text,
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    monkeypatch.setattr(
        text_cleanup_ui_controller,
        "start_operation",
        lambda _window, **kwargs: kwargs["success_handler"](
            kwargs["worker_callable"](
                _window._current_project_root,
                dict(_window._current_manifest),
                progress_callback=lambda *_args: None,
                cancel_requested=lambda: False,
            )
        ),
    )

    window._text_cleanup_page.extract_requested.emit()

    assert question_calls == []
    assert len(extract_calls) == 1


def test_main_window_exposes_modal_progress_dialog_and_cancel_signal(qtbot, default_settings_payload) -> None:
    """
    @brief      Verify the reusable operation-progress dialog is modal and emits cancellation.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": None,
            "default_ai_chunking_strategy": "paragraph",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)
    window._operation_progress_dialog = main_window_module.OperationProgressDialog(window)
    cancel_calls = []
    window._operation_progress_dialog.cancel_requested.connect(lambda: cancel_calls.append(True))
    window._operation_progress_dialog.start("Extract Text", "Text extraction in progress...")

    assert window._operation_progress_dialog.windowModality() == main_window_module.Qt.WindowModality.ApplicationModal
    assert window._operation_progress_dialog.isVisible() is True
    cancel_button = window._operation_progress_dialog.findChild(QPushButton)
    assert cancel_button is not None
    qtbot.mouseClick(
        cancel_button,
        main_window_module.Qt.MouseButton.LeftButton,
    )

    assert cancel_calls == [True]


def test_main_window_progress_dialog_shows_token_usage(qtbot, default_settings_payload) -> None:
    """
    @brief      Verify the shared progress dialog renders token usage when provided.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": None,
            "default_ai_chunking_strategy": "paragraph",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)
    window._operation_progress_dialog = main_window_module.OperationProgressDialog(window)
    window._operation_progress_dialog.start("Translate", "AI translation in progress...")
    window._operation_progress_dialog.update_progress(
        42,
        "AI translation in progress...",
        {
            "input_tokens": 123,
            "output_tokens": 45,
            "total_tokens": 168,
            "usage_available": True,
        },
    )

    label_texts = [widget.text() for widget in window._operation_progress_dialog.findChildren(QLabel)]
    assert any("Input tokens: 123 | Output tokens: 45 | Total: 168" in text for text in label_texts)


def test_main_window_closes_progress_dialog_after_synchronous_completion(
    qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify one synchronous modal operation closes the progress dialog after completion.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("SynchronousProgressProject", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("Story body", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    project_workspace_service.save_manifest(manifest, project_root)

    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": None,
            "default_ai_chunking_strategy": "paragraph",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    success_payloads = []

    def _worker_callable(_project_root, _manifest, progress_callback=None, cancel_requested=None):
        """
        @brief      Provide the worker callable test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        progress_callback(0, 1, 0, "Starting...")
        assert cancel_requested() is False
        progress_callback(1, 1, 100, "Completed.")
        return {"status": "ok"}

    text_cleanup_ui_controller.start_operation(
        window,
        operation_kind="extraction",
        operation_name="Extract Text",
        initial_message="Text extraction in progress...",
        worker_callable=_worker_callable,
        success_handler=lambda payload: success_payloads.append(payload),
        failure_handler=lambda error: (_ for _ in ()).throw(error),
    )

    qtbot.waitUntil(lambda: success_payloads == [{"status": "ok"}], timeout=5000)
    qtbot.waitUntil(lambda: window._operation_progress_dialog is None, timeout=5000)
    assert window._operation_progress_dialog is None
    assert window._active_operation_kind is None


def test_main_window_loads_narrator_definition_state_into_narator_voice_page(
    qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify the main window refreshes the Narator Voice page from persisted narrator-definition artifacts.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "NarratorWindowProject",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-11T12:00:00+00:00",
        "size_bytes": 4,
    }
    manifest["current_stage"] = "narrator_definition_ready"
    manifest["narrator_profile_name"] = "My Warm Narrator"
    manifest["narrator_language"] = "English"
    project_workspace_service.save_manifest(manifest, project_root)
    narrator_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "My Warm Narrator",
        "English",
        "Warm narrator prompt.",
        "Preview text.",
    )
    narrator_definition_service.select_narrator_profile(project_root, narrator_profile["profile_id"], "en")

    settings_payload = dict(default_settings_payload)
    settings_payload["tts_runtime_probe_succeeded"] = True
    settings_payload["tts_runtime_discovered_models"] = [
        {
            "model_id": "definition_model",
            "status": "healthy",
            "supported_generation_modes": ["definition"],
        },
        {
            "model_id": "clone_model",
            "status": "healthy",
            "supported_generation_modes": ["clone"],
        },
    ]
    window = MainWindow(settings_payload=settings_payload)
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    window.set_current_page("narator_voice")

    assert window._narator_voice_page._profile_list.count() == 1
    assert window._narator_voice_page.current_profile_id() == narrator_profile["profile_id"]
    assert window._narator_voice_page._profile_name_edit.text() == "My Warm Narrator"
    assert window._narator_voice_page._designer_prompt.toPlainText() == "Warm narrator prompt."
    assert window._narator_voice_page._edit_profile_button.isEnabled() is True
    assert window._narator_voice_page._delete_profile_button.isEnabled() is True


def test_main_window_prevents_reimport_when_source_is_locked(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify importing again shows an error when the source is already locked.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": 4,
    }
    manifest["current_stage"] = "source_selected"
    manifest["project_options_locked"] = True
    project_workspace_service.save_manifest(manifest, project_root)
    popup_calls = []

    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "warning",
        lambda *args, **kwargs: popup_calls.append(args),
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    window._home_page.import_requested.emit()

    assert popup_calls
    assert "already started" in popup_calls[0][2]


def test_main_window_offers_repair_and_opens_repaired_project(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify open-project offers repair for recoverable corruption.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    manifest["current_stage"] = "broken_stage"
    manifest_path = project_root / config.PROJECT_MANIFEST_FILE_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    question_calls = []

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(project_root),
    )
    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "question",
        lambda *args, **kwargs: (
            question_calls.append(args),
            QMessageBox.StandardButton.Yes,
        )[1],
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)

    window._action_open_project.trigger()

    assert question_calls
    assert window._current_project_root == project_root
    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "project_created"
    assert window._home_page._stage_list.item(0).text() == "Text Cleanup | Not Started"


def test_main_window_opens_confirmed_manifest_healing_repair(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify open-project applies confirmed manifest-healing changes.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Default settings fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("SpeechRepair", tmp_path)
    speech_blocks_service.write_speech_blocks_document(
        project_root,
        {
            "status": "completed",
            "source": {"kind": "original", "language": "en", "fingerprint": "repair-fingerprint"},
            "ai_profile_id": "profile-1",
            "instructions": "",
            "scene_ambience": {"enabled": False},
            "response_contract": "direct_blocks",
            "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "usage_available": False},
            "budget_metadata": {},
            "checkpoint": {
                "next_chunk_index": 1,
                "run_token": "2026-04-25T12:00:00+00:00",
                "log_relative_path": "log_ai_speech_blocks_20260425T120000Z.log",
                "source_snapshot_fingerprint": "repair-fingerprint",
                "source_language": "en",
                "ai_profile_id": "profile-1",
                "additional_speech_block_instructions_fingerprint": "",
                "speech_blocks_response_contract": "direct_blocks",
            },
            "failure": None,
            "blocks": [
                {
                    "speech_block_id": "sb-1",
                    "chunk_id": "chunk-0001",
                    "speaker_name": "Narrator",
                    "text": "Line",
                    "approved": True,
                }
            ],
        },
    )
    manifest["current_stage"] = "speech_blocks_ready"
    manifest["operations"]["speech_blocks"]["status"] = "not_started"
    project_workspace_service.save_manifest(manifest, project_root)
    question_calls = []

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(project_root),
    )
    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "question",
        lambda *args, **kwargs: (
            question_calls.append(args),
            QMessageBox.StandardButton.Yes,
        )[1],
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)

    window._action_open_project.trigger()

    assert question_calls
    assert "speech_blocks: not_started -> completed" in question_calls[0][2]
    assert window._current_manifest is not None
    assert window._current_manifest["operations"]["speech_blocks"]["status"] == "completed"


def test_main_window_declined_manifest_repair_leaves_project_unopened(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify declining repair keeps the project closed and leaves manifest data untouched.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Default settings fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("DeclineRepair", tmp_path)
    manifest["current_stage"] = "broken_stage"
    manifest_path = project_root / config.PROJECT_MANIFEST_FILE_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(project_root),
    )
    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)

    window._action_open_project.trigger()

    assert window._current_project_root is None
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["current_stage"] == "broken_stage"


def _operation_state(status: str, current: int, total: int) -> dict[str, object]:
    """
    @brief      Build a compact operation-state fixture.
    @param[in]  status Operation status token.
    @param[in]  current Current progress count.
    @param[in]  total Total progress count.
    @return     Operation-state fixture payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return {
        "folder_relative_path": ".",
        "status": status,
        "progress_current": current,
        "progress_total": total,
        "mode": "test",
        "started_at": "2026-04-25T12:00:00+00:00",
        "completed_at": "2026-04-25T12:01:00+00:00" if status == "completed" else None,
        "updated_at": "2026-04-25T12:01:00+00:00",
        "warning_count": 0,
    }


def _write_json(path, payload: object) -> None:
    """
    @brief      Write one JSON fixture file.
    @param[in]  path Target file path.
    @param[in]  payload JSON-serializable payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# END OF FILE
