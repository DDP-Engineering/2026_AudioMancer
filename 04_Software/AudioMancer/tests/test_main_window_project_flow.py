#!/usr/bin/env python3
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
@version 1.5.1
"""

# IMPORTS

import json

from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QPushButton,
)

from audiomancer import config
from audiomancer.services import deterministic_chunking_service, project_workspace_service
from audiomancer.ui.controllers import (
    ai_translation_ui_controller,
    home_ui_controller,
    text_chunking_ui_controller,
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
    @version    0.2.1
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
        "Narration Plan" in window._home_page._stage_list.item(index).text()
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
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(project_root / "40_character_discovery"),
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)

    window._action_open_project.trigger()

    assert window._current_project_root == project_root
    assert window._current_manifest is not None
    assert window._current_manifest["display_name"] == "Book5_CAL_CAL"
    assert window._home_page._path_label.text() == f"Path: {project_root}"


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
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    source_path = tmp_path / "story.epub"
    source_path.write_text("content", encoding="utf-8")

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(source_path), ""),
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    window._home_page.import_requested.emit()

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "source_selected"
    assert window._current_manifest["source_document"]["original_name"] == "story.epub"
    assert window._home_page._source_label.text() == "Source: story.epub"
    assert window._home_page._stage_list.item(0).text() == "Source Selected | Finished"
    assert window._home_page._import_button.isEnabled() is False


def test_main_window_extracts_text_and_updates_cleanup_page(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify extraction updates the manifest, preview, and completed extraction state.
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
        "ExtractProject",
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
    project_workspace_service.save_manifest(manifest, project_root)

    extraction_state = {
        "folder_relative_path": "00_extraction",
        "status": "completed",
        "input_paths": ["00_extraction/input_story.txt"],
        "output_paths": [f"00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}"],
        "artifact_paths": [f"00_extraction/{config.EXTRACTION_REPORT_FILE_NAME}"],
        "progress_current": 1,
        "progress_total": 1,
        "mode": "deterministic",
        "started_at": "2026-04-06T12:00:00+00:00",
        "completed_at": "2026-04-06T12:01:00+00:00",
        "updated_at": "2026-04-06T12:01:00+00:00",
        "warning_count": 0,
        "metadata": {"warnings": [], "source_type": "txt"},
        "resume_checkpoint": None,
    }

    def _fake_extract_text(*args, **kwargs):
        """
        @brief      Persist fake extraction artifacts for the main-window test.
        @return     Fake extraction report payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        extraction_root = project_root / "00_extraction"
        extraction_root.mkdir(exist_ok=True)
        (extraction_root / "input_story.txt").write_text("Story body", encoding="utf-8")
        (extraction_root / config.EXTRACTED_TEXT_FILE_NAME).write_text(
            "Story body\n",
            encoding="utf-8",
        )
        (extraction_root / config.EXTRACTION_REPORT_FILE_NAME).write_text(
            (
                "{\n"
                '  "source_relative_path": "00_extraction/input_story.txt",\n'
                '  "source_type": "txt",\n'
                f'  "extracted_text_relative_path": "00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}",\n'
                '  "extracted_at": "2026-04-06T12:01:00+00:00",\n'
                '  "page_count": null,\n'
                '  "warnings": [],\n'
                '  "character_count": 10,\n'
                '  "word_count": 2,\n'
                '  "line_count": 1\n'
                "}\n"
            ),
            encoding="utf-8",
        )
        (extraction_root / config.OPERATION_STATE_FILE_NAME).write_text(
            json.dumps(extraction_state, indent=2) + "\n",
            encoding="utf-8",
        )
        return {
            "source_relative_path": "00_extraction/input_story.txt",
            "source_type": "txt",
            "extracted_text_relative_path": f"00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}",
            "extracted_at": "2026-04-06T12:01:00+00:00",
            "page_count": None,
            "warnings": [],
            "character_count": 10,
            "word_count": 2,
            "line_count": 1,
        }

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

    assert window._current_manifest is not None
    assert window._current_manifest["extracted_text_relative_path"] == (
        f"00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}"
    )
    assert window._current_manifest["operations"]["extraction"]["status"] == "completed"
    assert window._home_page._stage_list.item(1).text() == "Text Cleanup | In Progress"
    assert window._text_cleanup_page._extracted_text_edit.toPlainText() == "Story body\n"
    assert "Extracted 2 words across 1 lines." in window._text_cleanup_page._notes_edit.toPlainText()


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
    manifest["extracted_text_relative_path"] = f"00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}"
    manifest["extraction_report_relative_path"] = f"00_extraction/{config.EXTRACTION_REPORT_FILE_NAME}"
    manifest["operations"]["extraction"]["status"] = "completed"
    manifest["operations"]["cleanup"]["status"] = "completed"
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
    manifest["operations"]["extraction"]["status"] = "failed"
    manifest["operations"]["extraction"]["progress_current"] = 1
    manifest["operations"]["extraction"]["progress_total"] = 3
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
        @return     Minimal extraction report payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        extract_calls.append(args)
        extraction_root = project_root / "00_extraction"
        extraction_root.mkdir(exist_ok=True)
        (extraction_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("Story body\n", encoding="utf-8")
        (extraction_root / config.EXTRACTION_REPORT_FILE_NAME).write_text(
            "{}\n",
            encoding="utf-8",
        )
        (extraction_root / config.OPERATION_STATE_FILE_NAME).write_text(
            json.dumps(
                {
                    "folder_relative_path": "00_extraction",
                    "status": "completed",
                    "input_paths": [],
                    "output_paths": [f"00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}"],
                    "artifact_paths": [f"00_extraction/{config.EXTRACTION_REPORT_FILE_NAME}"],
                    "progress_current": 1,
                    "progress_total": 1,
                    "mode": "deterministic",
                    "started_at": "2026-04-06T12:00:00+00:00",
                    "completed_at": "2026-04-06T12:01:00+00:00",
                    "updated_at": "2026-04-06T12:01:00+00:00",
                    "warning_count": 0,
                    "metadata": {"warnings": []},
                    "resume_checkpoint": None,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "source_relative_path": "00_extraction/input_story.txt",
            "source_type": "txt",
            "extracted_text_relative_path": f"00_extraction/{config.EXTRACTED_TEXT_FILE_NAME}",
            "extracted_at": "2026-04-06T12:01:00+00:00",
            "page_count": None,
            "warnings": [],
            "character_count": 10,
            "word_count": 2,
            "line_count": 1,
        }

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

    assert success_payloads == [{"status": "ok"}]
    assert window._operation_progress_dialog is None
    assert window._active_operation_kind is None


def test_main_window_runs_deterministic_cleanup_and_updates_preview(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify deterministic cleanup updates the manifest-facing UI state and cleaned preview.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("CleanupWindowProject", tmp_path)
    source_path = project_root / "story.pdf"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.pdf",
        "stored_relative_path": "story.pdf",
        "file_type": "pdf",
        "imported_at": "2026-04-06T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["extracted_text_relative_path"] = "00_extraction/output_raw_text.txt"
    manifest["operations"]["extraction"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    extraction_root = project_root / "00_extraction"
    extraction_root.mkdir(exist_ok=True)
    (extraction_root / "output_raw_text.txt").write_text("Chapter I\n\nParagraph one.", encoding="utf-8")

    def _fake_clean_text(*_args, progress_callback=None, cancel_requested=None, **_kwargs):
        progress_callback(1, 1, 100, "Deterministic cleanup completed.")
        cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
        cleanup_root.mkdir(exist_ok=True)
        (cleanup_root / "input_story.pdf").write_text("Chapter I\n\nParagraph one.", encoding="utf-8")
        (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text("Chapter I\n\nParagraph one.\n", encoding="utf-8")
        (cleanup_root / config.CLEANUP_REPORT_FILE_NAME).write_text(
            json.dumps(
                {
                    "input_relative_path": f"{config.CLEANUP_FOLDER_NAME}/input_story.pdf",
                    "cleaned_text_relative_path": f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}",
                    "cleaned_at": "2026-04-06T12:02:00+00:00",
                    "detected_language": "en",
                    "warnings": [],
                    "paragraph_count": 2,
                    "removed_line_count": 0,
                    "removed_header_footer_line_count": 0,
                    "removed_page_number_line_count": 0,
                    "detected_chapter_count": 1,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (cleanup_root / "state_operation.json").write_text(
            json.dumps(
                {
                    "folder_relative_path": config.CLEANUP_FOLDER_NAME,
                    "status": "completed",
                    "input_paths": [f"{config.CLEANUP_FOLDER_NAME}/input_story.pdf"],
                    "output_paths": [f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"],
                    "artifact_paths": [f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANUP_REPORT_FILE_NAME}"],
                    "progress_current": 1,
                    "progress_total": 1,
                    "mode": "deterministic",
                    "started_at": "2026-04-06T12:00:00+00:00",
                    "completed_at": "2026-04-06T12:02:00+00:00",
                    "updated_at": "2026-04-06T12:02:00+00:00",
                    "warning_count": 0,
                    "metadata": {"warnings": []},
                    "resume_checkpoint": None,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        assert cancel_requested() is False
        return {"paragraph_count": 2}

    monkeypatch.setattr(text_cleanup_ui_controller.deterministic_cleanup_service, "clean_text", _fake_clean_text)

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

    window._text_cleanup_page.clean_requested.emit()

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "text_chunking_ready"
    assert window._text_cleanup_page._cleaned_text_edit.toPlainText() == "Chapter I\n\nParagraph one.\n"
    assert "Cleanup produced 2 paragraphs" in window._text_cleanup_page._notes_edit.toPlainText()


def test_main_window_runs_deterministic_chunking_and_updates_preview(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify deterministic chunking updates the manifest-facing UI state and chunk preview.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ChunkWindowProject", tmp_path)
    source_path = project_root / "story.pdf"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.pdf",
        "stored_relative_path": "story.pdf",
        "file_type": "pdf",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"
    ]
    project_workspace_service.save_manifest(manifest, project_root)
    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
    cleanup_root.mkdir(exist_ok=True)
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text("Chapter I\n\nParagraph one.\n", encoding="utf-8")

    def _fake_chunk_text(*_args, progress_callback=None, cancel_requested=None, **_kwargs):
        progress_callback(1, 1, 100, "Deterministic chunking completed.")
        chunk_root = project_root / "20_chunking"
        chunk_root.mkdir(exist_ok=True)
        (chunk_root / "input_story.pdf").write_text("Chapter I\n\nParagraph one.\n", encoding="utf-8")
        (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
            json.dumps(
                [
                    {
                        "chunk_id": "chunk-0001",
                        "sequence_index": 1,
                        "chapter_label": "Chapter I",
                        "text": "Chapter I",
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
                        "text": "Paragraph one.",
                        "source_start_line": 3,
                        "source_end_line": 3,
                        "chunking_mode": "deterministic",
                        "semantic_strategy": None,
                        "scene_note": None,
                    },
                ],
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (chunk_root / config.CHUNKING_REPORT_FILE_NAME).write_text(
            json.dumps(
                {
                    "input_relative_path": "20_chunking/input_story.pdf",
                    "chunk_artifact_relative_path": f"20_chunking/{config.CHUNK_ARTIFACT_FILE_NAME}",
                    "chunked_at": "2026-04-07T12:02:00+00:00",
                    "warnings": [],
                    "chunk_count": 2,
                    "detected_chapter_count": 1,
                    "chunking_mode": "deterministic",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (chunk_root / config.OPERATION_STATE_FILE_NAME).write_text(
            json.dumps(
                {
                    "folder_relative_path": "20_chunking",
                    "status": "completed",
                    "input_paths": ["20_chunking/input_story.pdf"],
                    "output_paths": [f"20_chunking/{config.CHUNK_ARTIFACT_FILE_NAME}"],
                    "artifact_paths": [f"20_chunking/{config.CHUNKING_REPORT_FILE_NAME}"],
                    "progress_current": 2,
                    "progress_total": 2,
                    "mode": "deterministic",
                    "started_at": "2026-04-07T12:00:00+00:00",
                    "completed_at": "2026-04-07T12:02:00+00:00",
                    "updated_at": "2026-04-07T12:02:00+00:00",
                    "warning_count": 0,
                    "metadata": {"warnings": [], "chunk_count": 2, "detected_chapter_count": 1},
                    "resume_checkpoint": None,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        assert cancel_requested() is False
        return {"chunk_count": 2}

    monkeypatch.setattr(text_chunking_ui_controller.deterministic_chunking_service, "chunk_text", _fake_chunk_text)

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    monkeypatch.setattr(
        text_chunking_ui_controller,
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

    window._text_chunking_page.chunk_requested.emit()

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "translation_ready"
    assert window._text_chunking_page._chunk_list.count() >= 2
    assert window._text_chunking_page._chunk_text_edit.toPlainText() == "Chapter I"
    assert "Chunking produced 2 chunks" in window._text_chunking_page._notes_edit.toPlainText()


def test_main_window_runs_ai_chunking_and_updates_preview(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify the main window wires AI-assisted chunking and refreshes the chunk preview after success.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
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
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 4,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}"
    ]
    cleanup_root = project_root / config.CLEANUP_FOLDER_NAME
    cleanup_root.mkdir(parents=True, exist_ok=True)
    (cleanup_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "Chapter I\n\nParagraph one.\n\nParagraph two.\n",
        encoding="utf-8",
    )
    project_workspace_service.save_manifest(manifest, project_root)

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    monkeypatch.setattr(
        text_chunking_ui_controller,
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
    monkeypatch.setattr(
        text_chunking_ui_controller.ai_chunking_service,
        "chunk_text",
        lambda project_root, manifest, _profile, _strategy, progress_callback=None, cancel_requested=None: (
            deterministic_chunking_service.chunk_text(
                project_root,
                manifest,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
            | {
                "chunking_mode": "ai_assisted",
                "semantic_strategy": "scene",
            }
        ),
    )

    window._text_chunking_page.ai_chunk_requested.emit("profile_1", "scene")

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "translation_ready"
    assert window._text_chunking_page._chunk_list.count() >= 2
    assert window._text_chunking_page._ai_chunk_button.isEnabled() is True


def test_main_window_runs_ai_translation_and_updates_preview(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify the main window wires AI translation and refreshes the translated preview after success.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "TranslationWindowProject",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 4,
    }
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [f"20_chunking/{config.CHUNK_ARTIFACT_FILE_NAME}"]
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root / "20_chunking"
    chunk_root.mkdir(parents=True, exist_ok=True)
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": None,
                    "text": "Original one",
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

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    monkeypatch.setattr(
        ai_translation_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: ai_translation_ui_controller._sync_manifest_after_translation(
            _window,
            kwargs["worker_callable"](
                _window._current_project_root,
                dict(_window._current_manifest),
                progress_callback=lambda *_args: None,
                cancel_requested=lambda: False,
            ),
        ),
    )
    monkeypatch.setattr(
        ai_translation_ui_controller.ai_translation_service,
        "start_or_continue_translation",
        lambda project_root, _manifest, _profile, target_language, progress_callback=None, cancel_requested=None: (
            (project_root / config.TRANSLATION_FOLDER_NAME).mkdir(parents=True, exist_ok=True),
            (project_root / config.TRANSLATION_FOLDER_NAME / "input_story.json").write_text("[]\n", encoding="utf-8"),
            (project_root / config.TRANSLATION_FOLDER_NAME / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
                json.dumps(
                    [
                        {
                            "chunk_id": "chunk-0001",
                            "sequence_index": 1,
                            "source_text": "Original one",
                            "translated_text": "Tradus unu",
                            "approved": False,
                            "approved_at": None,
                            "translated_at": "2026-04-07T12:01:00+00:00",
                            "translation_profile_id": "profile_1",
                            "target_language": target_language,
                            "status": "translated",
                        }
                    ],
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            ),
            (project_root / config.TRANSLATION_FOLDER_NAME / config.TRANSLATION_REPORT_FILE_NAME).write_text(
                json.dumps(
                    {
                        "target_language": target_language,
                        "translation_profile_id_last_used": "profile_1",
                        "translation_stage_status": "completed",
                        "translated_chunk_count": 1,
                        "approved_chunk_count": 0,
                        "total_chunk_count": 1,
                        "updated_at": "2026-04-07T12:02:00+00:00",
                        "warnings": [],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            ),
            (project_root / config.TRANSLATION_FOLDER_NAME / config.OPERATION_STATE_FILE_NAME).write_text(
                json.dumps(
                    {
                        "folder_relative_path": config.TRANSLATION_FOLDER_NAME,
                        "status": "completed",
                        "input_paths": [f"{config.TRANSLATION_FOLDER_NAME}/input_story.json"],
                        "output_paths": [f"{config.TRANSLATION_FOLDER_NAME}/{config.TRANSLATED_CHUNKS_FILE_NAME}"],
                        "artifact_paths": [f"{config.TRANSLATION_FOLDER_NAME}/{config.TRANSLATION_REPORT_FILE_NAME}"],
                        "progress_current": 1,
                        "progress_total": 1,
                        "mode": "ai_assisted",
                        "started_at": "2026-04-07T12:00:00+00:00",
                        "completed_at": "2026-04-07T12:02:00+00:00",
                        "updated_at": "2026-04-07T12:02:00+00:00",
                        "warning_count": 0,
                        "metadata": {
                            "target_language": target_language,
                            "translation_profile_id": "profile_1",
                            "translated_chunk_count": 1,
                            "approved_chunk_count": 0,
                            "total_chunk_count": 1,
                            "warnings": [],
                            "translated_chunks": [],
                            "source_chunk_count": 1,
                            "log_relative_path": None,
                        },
                        "resume_checkpoint": None,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            ),
            {
                "target_language": target_language,
                "translation_profile_id_last_used": "profile_1",
                "translation_stage_status": "completed",
                "translated_chunk_count": 1,
                "approved_chunk_count": 0,
                "total_chunk_count": 1,
                "updated_at": "2026-04-07T12:02:00+00:00",
                "warnings": [],
            },
        )[-1],
    )

    window._ai_translation_page.start_translation_requested.emit("profile_1", "ro")
    window.show_project_state(project_root, project_workspace_service.load_manifest(project_root))

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "translation_ready"
    assert window._ai_translation_page._chunk_list.count() == 1
    assert window._ai_translation_page._translated_text_edit.toPlainText() == "Tradus unu"


def test_main_window_loads_character_discovery_state_into_characters_page(
    qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify the main window refreshes the Characters page from persisted discovery artifacts.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "CharactersWindowProject",
        tmp_path,
    )
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-08T12:00:00+00:00",
        "size_bytes": 4,
    }
    manifest["current_stage"] = "character_discovery_ready"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [f"20_chunking/{config.CHUNK_ARTIFACT_FILE_NAME}"]
    manifest["operations"]["character_discovery"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root / "20_chunking"
    discovery_root = project_root / "40_character_discovery"
    chunk_root.mkdir(parents=True, exist_ok=True)
    discovery_root.mkdir(parents=True, exist_ok=True)
    chunk_payload = [
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
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(chunk_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / f"input_{config.CHUNK_ARTIFACT_FILE_NAME}").write_text(
        json.dumps(chunk_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (discovery_root / config.CHARACTER_PROFILE_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "character_id": "alice",
                    "canonical_name": "Alice",
                    "aliases": ["Al"],
                    "gender_hint": "",
                    "age_band": "",
                    "role_summary": "Lead speaker",
                    "description": "Confident.",
                    "temperament": "",
                    "social_status": "",
                    "speaking_style": "",
                    "accent_or_dialect_hints": "",
                    "voice_notes": "",
                    "relationship_hints": [],
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
            ],
            indent=2,
        )
        + "\n",
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
                "character_profile_id_last_used": "profile_1",
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
    (discovery_root / config.OPERATION_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": "40_character_discovery",
                "status": "completed",
                "input_paths": [],
                "output_paths": [f"40_character_discovery/{config.CHARACTER_PROFILE_FILE_NAME}"],
                "artifact_paths": [f"40_character_discovery/{config.CHARACTER_DISCOVERY_REPORT_FILE_NAME}"],
                "progress_current": 1,
                "progress_total": 1,
                "mode": "ai_assisted",
                "started_at": "2026-04-08T12:00:00+00:00",
                "completed_at": "2026-04-08T12:01:00+00:00",
                "updated_at": "2026-04-08T12:01:00+00:00",
                "warning_count": 0,
                "metadata": {"ai_profile_id": "profile_1"},
                "resume_checkpoint": None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    assert window._characters_page._character_list.count() == 1
    assert window._characters_page._start_button.isEnabled() is False
    assert window._characters_page._reset_button.isEnabled() is True
    assert window._characters_page._evidence_preview.toPlainText() == '"Hello there," said Alice.'


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
    narrator_root = project_root / config.NARRATOR_DEFINITION_FOLDER_NAME
    narrator_root.mkdir(parents=True, exist_ok=True)
    (narrator_root / config.NARRATOR_PROFILE_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "profile_id": "preset_1",
                    "speaker_id": "vivian",
                    "display_name": "CustomVoice | Neutral Story Guide",
                    "language": "en",
                    "prompt_text": "Preset prompt.",
                    "profile_kind": "preset",
                    "provider_family": "qwen3_tts_customvoice_seed",
                    "editable": False,
                    "updated_at": None,
                },
                {
                    "profile_id": "custom_1",
                    "display_name": "My Warm Narrator",
                    "language": "en",
                    "prompt_text": "Warm narrator prompt.",
                    "profile_kind": "custom",
                    "provider_family": "project_custom",
                    "editable": True,
                    "updated_at": "2026-04-11T12:01:00+00:00",
                },
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (narrator_root / config.NARRATOR_SELECTION_FILE_NAME).write_text(
        json.dumps(
            {
                "selected_profile_id": "custom_1",
                "selected_language": "en",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    settings_payload = dict(default_settings_payload)
    settings_payload["tts_runtime_probe_succeeded"] = True
    settings_payload["tts_runtime_discovered_models"] = [
        {
            "model_id": "custom_model",
            "status": "healthy",
            "supported_generation_modes": ["custom_voice"],
            "supported_presets": ["vivian"],
            "speaker_count": 1,
        },
        {
            "model_id": "definition_model",
            "status": "healthy",
            "supported_generation_modes": ["definition"],
            "supported_presets": [],
            "speaker_count": 0,
        },
        {
            "model_id": "clone_model",
            "status": "healthy",
            "supported_generation_modes": ["clone"],
            "supported_presets": [],
            "speaker_count": 0,
        },
    ]
    window = MainWindow(settings_payload=settings_payload)
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    assert window._narator_voice_page._profile_list.count() == 5
    assert window._narator_voice_page.current_profile_id() == "custom_1"
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
    assert "locked source file" in popup_calls[0][2]


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
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project(
        "Book5_CAL_CAL",
        tmp_path,
    )
    (project_root / "40_character_discovery").rmdir()
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
    assert (project_root / "40_character_discovery").is_dir()
    assert window._current_manifest["current_stage"] == "project_created"
    assert window._home_page._stage_list.item(0).text() == "Source Selected | Not Started"


# END OF FILE
