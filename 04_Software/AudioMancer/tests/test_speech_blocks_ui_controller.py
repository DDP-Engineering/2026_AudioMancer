#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_speech_blocks_ui_controller.py
@brief Speech Blocks UI controller tests for AudioMancer.
@details Verifies confirmation gating and explicit destructive reset behavior for
         the Speech Blocks workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-21
@version 0.6.3
"""

# IMPORTS

import json
from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import character_voices_service, project_workspace_service
from audiomancer.ui.controllers import speech_blocks_ui_controller
from audiomancer.ui.main_window import MainWindow


def test_speech_blocks_ui_controller_requires_confirmation_before_starting(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify Speech Blocks generation stops when the operator declines the confirmation popup.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    project_root = _create_project(tmp_path, "SpeechBlocksControllerConfirm")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "resolve_source_chunks",
        lambda *_args, **_kwargs: {
            "selected_source_language": "en",
            "source_kind": "original",
            "source_chunks": [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Narration."}],
        },
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    start_calls = []
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )

    speech_blocks_ui_controller.handle_generate_requested(window, "profile-1")

    assert start_calls == []


def test_speech_blocks_ui_controller_passes_extra_prompt_to_generation(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Speech Blocks generation asks for optional operator rules and passes them to the worker.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    project_root = _create_project(tmp_path, "SpeechBlocksControllerExtraPrompt")
    manifest = project_workspace_service.load_manifest(project_root)
    window = SimpleNamespace(
        _active_operation_kind=None,
        _settings_payload=_settings_payload(),
        _current_project_root=project_root,
        _current_manifest=manifest,
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "resolve_source_chunks",
        lambda *_args, **_kwargs: {
            "selected_source_language": "en",
            "source_kind": "original",
            "source_chunks": [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Narration."}],
        },
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(speech_blocks_ui_controller, "_is_resuming_speech_blocks_generation", lambda _window: False)
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "prompt_ai_speech_blocks_instructions",
        lambda _window, _language: "Keep whispers as separate dialogue blocks.",
    )

    def _fake_start_or_continue_generation(*_args, **kwargs):
        """
        @brief      Capture the worker keyword arguments for Speech Blocks generation.
        @param[in]  _args Ignored positional arguments.
        @param[in]  kwargs Worker keyword arguments.
        @return     Captured extra prompt payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-13
        @version    0.1.0
        """
        return {"additional": kwargs.get("additional_speech_block_instructions")}

    start_calls = []
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "start_or_continue_generation",
        _fake_start_or_continue_generation,
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )

    speech_blocks_ui_controller.handle_generate_requested(window, "profile-1")

    assert len(start_calls) == 1
    worker_result = start_calls[0]["worker_callable"](project_root, manifest)
    assert worker_result == {"additional": "Keep whispers as separate dialogue blocks."}


def test_speech_blocks_ui_controller_passes_extra_prompt_to_selected_resplit(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify selected-chunk re-splitting passes optional operator rules to the worker.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    project_root = _create_project(tmp_path, "SpeechBlocksControllerResplitExtraPrompt")
    manifest = project_workspace_service.load_manifest(project_root)
    window = SimpleNamespace(
        _active_operation_kind=None,
        _settings_payload=_settings_payload(),
        _current_project_root=project_root,
        _current_manifest=manifest,
        _speech_blocks_page=SimpleNamespace(current_profile_id=lambda: "profile-1"),
    )
    monkeypatch.setattr(speech_blocks_ui_controller, "_confirm_speech_blocks_resplit", lambda *_args: True)
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "prompt_ai_speech_blocks_instructions",
        lambda _window, _language: "Preserve ellipses in dialogue blocks.",
    )

    def _fake_regenerate_chunk_speech_blocks(*_args, **kwargs):
        """
        @brief      Capture the worker keyword arguments for selected-chunk re-splitting.
        @param[in]  _args Ignored positional arguments.
        @param[in]  kwargs Worker keyword arguments.
        @return     Captured extra prompt payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-13
        @version    0.1.0
        """
        return {"additional": kwargs.get("additional_speech_block_instructions")}

    start_calls = []
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "regenerate_chunk_speech_blocks",
        _fake_regenerate_chunk_speech_blocks,
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )

    speech_blocks_ui_controller.handle_resplit_selected_requested(window, "chunk-0001")

    assert len(start_calls) == 1
    worker_result = start_calls[0]["worker_callable"](project_root, manifest)
    assert worker_result == {"additional": "Preserve ellipses in dialogue blocks."}


def test_speech_blocks_ui_controller_edit_start_does_not_refresh_page(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify accepted block edit clears warnings and unlocks the editor without refreshing the page.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.1
    """
    project_root = tmp_path / "SpeechBlocksEditStart"
    project_root.mkdir()
    clear_calls = []
    page_calls = []
    window = SimpleNamespace(
        _settings_payload={"language": "en"},
        _current_project_root=project_root,
        _current_manifest={"current_stage": "character_voices_ready"},
        _speech_blocks_page=SimpleNamespace(begin_editing_selected_block=lambda: page_calls.append("edit")),
        show_project_state=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected refresh")),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "load_speech_blocks",
        lambda _project_root: [
            {
                "speech_block_id": "0001-000001",
                "speaker_id": "alice",
                "content_kind": "dialogue",
                "text": "Hello.",
                "warning_flags": ["speaker_fallback"],
            }
        ],
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "clear_speech_block_warning_flags",
        lambda *args: clear_calls.append(args),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_confirm_speech_block_audio_reset_if_needed",
        lambda *_args: True,
    )

    speech_blocks_ui_controller.handle_edit_started(window, "0001-000001")

    assert clear_calls == [(project_root, "0001-000001")]
    assert page_calls == ["edit"]


def test_speech_blocks_ui_controller_edit_start_skips_warning_clear_when_clean(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify edit start avoids rewriting Speech Blocks when the selected block has no warnings.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-25
    @version    0.1.0
    """
    project_root = tmp_path / "SpeechBlocksEditStartClean"
    project_root.mkdir()
    clear_calls = []
    page_calls = []
    window = SimpleNamespace(
        _settings_payload={"language": "en"},
        _current_project_root=project_root,
        _current_manifest={"current_stage": "character_voices_ready"},
        _speech_blocks_page=SimpleNamespace(begin_editing_selected_block=lambda: page_calls.append("edit")),
        show_project_state=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected refresh")),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "load_speech_blocks",
        lambda _project_root: [
            {
                "speech_block_id": "0001-000001",
                "speaker_id": "alice",
                "content_kind": "dialogue",
                "text": "Hello.",
                "warning_flags": [],
            }
        ],
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "clear_speech_block_warning_flags",
        lambda *args: clear_calls.append(args),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_confirm_speech_block_audio_reset_if_needed",
        lambda *_args: True,
    )

    speech_blocks_ui_controller.handle_edit_started(window, "0001-000001")

    assert clear_calls == []
    assert page_calls == ["edit"]


def test_speech_blocks_ui_controller_edit_decline_keeps_editor_locked(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify declining the edit impact confirmation keeps the selected Speech Block read-only.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    project_root = tmp_path / "SpeechBlocksEditDecline"
    project_root.mkdir()
    clear_calls = []
    page_calls = []
    window = SimpleNamespace(
        _settings_payload={"language": "en"},
        _current_project_root=project_root,
        _current_manifest={"current_stage": "character_voices_ready"},
        _speech_blocks_page=SimpleNamespace(begin_editing_selected_block=lambda: page_calls.append("edit")),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "load_speech_blocks",
        lambda _project_root: [
            {
                "speech_block_id": "0001-000001",
                "speaker_id": "alice",
                "content_kind": "dialogue",
                "text": "Hello.",
            }
        ],
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "clear_speech_block_warning_flags",
        lambda *args: clear_calls.append(args),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_confirm_speech_block_audio_reset_if_needed",
        lambda *_args: False,
    )

    speech_blocks_ui_controller.handle_edit_started(window, "0001-000001")

    assert clear_calls == []
    assert page_calls == []


def test_speech_blocks_ui_controller_save_restores_chunk_text_scroll(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify saving an edited block restores the selected chunk text position.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.3.3
    """
    project_root = tmp_path / "SpeechBlocksSaveScroll"
    project_root.mkdir()
    source_position = {
        "source_scroll": 37,
        "source_horizontal_scroll": 5,
        "source_cursor_position": 13,
        "source_anchor_position": 4,
    }
    restore_calls: list[dict[str, object]] = []
    window = SimpleNamespace(
        _settings_payload={"language": "en"},
        _current_project_root=project_root,
        _current_manifest={"current_stage": "speech_blocks_ready"},
        _speech_blocks_page=SimpleNamespace(
            source_text_position=lambda: dict(source_position),
            restore_source_text_position=lambda position: restore_calls.append(dict(position)),
        ),
    )
    monkeypatch.setattr(speech_blocks_ui_controller.speech_blocks_service, "update_speech_block", lambda *args: {})
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_speech_block_by_id",
        lambda *_args: {
            "speech_block_id": "0001-000001",
            "speaker_id": "narrator",
            "content_kind": "narration",
            "text": "Original text.",
        },
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_confirm_speech_block_audio_reset_if_needed",
        lambda *_args: (_ for _ in ()).throw(AssertionError("save should not ask for edit confirmation")),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.project_workspace_service,
        "load_manifest",
        lambda _project_root: {"current_stage": "speech_blocks_ready", "loaded_after_save": True},
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_reset_audio_block_after_speech_block_change",
        lambda *_args: None,
    )
    monkeypatch.setattr(speech_blocks_ui_controller.misc_ui_controller, "show_message", lambda *args, **kwargs: None)

    speech_blocks_ui_controller.handle_save_block_requested(
        window,
        "0001-000001",
        "narrator",
        "narration",
        "Edited text.",
    )

    assert restore_calls == [source_position]
    assert window._current_manifest["loaded_after_save"] is True


def test_speech_blocks_ui_controller_insert_resets_downstream_and_selects_new_block(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify insert-after delegates to service, resets assembly state, and selects edit mode.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.4.0
    """
    project_root = tmp_path / "SpeechBlocksInsertController"
    project_root.mkdir()
    page_calls: list[tuple[str, object]] = []
    window = SimpleNamespace(
        _settings_payload={"language": "en"},
        _current_project_root=project_root,
        _current_manifest={"current_stage": "audio_blocks_ready"},
        _speech_blocks_page=SimpleNamespace(
            source_text_position=lambda: {
                "source_scroll": 24,
                "source_horizontal_scroll": 3,
                "source_cursor_position": 8,
                "source_anchor_position": 2,
            },
            select_speech_block=lambda speech_block_id: page_calls.append(("select", speech_block_id)),
            begin_editing_selected_block=lambda: page_calls.append(("edit", "")),
            restore_source_text_position=lambda position: page_calls.append(("restore_source", dict(position))),
        ),
    )
    service_calls = []
    reset_calls = []
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "insert_speech_block",
        lambda *args: service_calls.append(args) or ({}, "0001-000002"),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_sync_manifest_after_speech_blocks_update",
        lambda _window: reset_calls.append("sync"),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_confirm_speech_block_sequence_change",
        lambda *_args: True,
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_reset_audio_assembly_after_speech_blocks_change",
        lambda _window: reset_calls.append("assembly"),
    )
    monkeypatch.setattr(speech_blocks_ui_controller.misc_ui_controller, "show_message", lambda *args, **kwargs: None)

    speech_blocks_ui_controller.handle_insert_block_requested(window, "chunk-0001", "0001-000001")

    assert service_calls == [(project_root, "chunk-0001", "0001-000001")]
    assert reset_calls == ["sync", "assembly"]
    assert page_calls == [
        ("select", "0001-000002"),
        ("edit", ""),
        (
            "restore_source",
            {
                "source_scroll": 24,
                "source_horizontal_scroll": 3,
                "source_cursor_position": 8,
                "source_anchor_position": 2,
            },
        ),
    ]


def test_speech_blocks_ui_controller_delete_confirms_and_resets_downstream(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify delete asks confirmation, delegates to service, restores scroll, and selects the replacement row.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.3.1
    """
    project_root = tmp_path / "SpeechBlocksDeleteController"
    project_root.mkdir()
    page_calls: list[tuple[str, object]] = []
    window = SimpleNamespace(
        _settings_payload={"language": "en"},
        _current_project_root=project_root,
        _current_manifest={"current_stage": "audio_blocks_ready"},
        _speech_blocks_page=SimpleNamespace(
            source_text_position=lambda: {
                "source_scroll": 42,
                "source_horizontal_scroll": 7,
                "source_cursor_position": 12,
                "source_anchor_position": 6,
            },
            replacement_block_id_after_delete=lambda speech_block_id: (
                page_calls.append(("replacement_for", speech_block_id)) or "0001-000002"
            ),
            select_speech_block=lambda speech_block_id: page_calls.append(("select", speech_block_id)),
            restore_source_text_position=lambda position: page_calls.append(("restore_source", dict(position))),
        ),
    )
    service_calls = []
    reset_calls = []
    monkeypatch.setattr(
        speech_blocks_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "delete_speech_block",
        lambda *args: service_calls.append(args) or {},
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_sync_manifest_after_speech_blocks_update",
        lambda _window: reset_calls.append("sync"),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_reset_audio_block_after_speech_block_change",
        lambda _window, speech_block_id: reset_calls.append(f"reset:{speech_block_id}"),
    )
    monkeypatch.setattr(speech_blocks_ui_controller.misc_ui_controller, "show_message", lambda *args, **kwargs: None)

    speech_blocks_ui_controller.handle_delete_block_requested(window, "0001-000001")

    assert service_calls == [(project_root, "0001-000001")]
    assert reset_calls == ["sync", "reset:0001-000001"]
    assert page_calls == [
        ("replacement_for", "0001-000001"),
        ("select", "0001-000002"),
        (
            "restore_source",
            {
                "source_scroll": 42,
                "source_horizontal_scroll": 7,
                "source_cursor_position": 12,
                "source_anchor_position": 6,
            },
        ),
    ]


def test_speech_blocks_ui_controller_approve_preserves_audio_blocks_and_resets_assembly(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify approving one Speech Block does not delete Audio Blocks data.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    project_root = tmp_path / "SpeechBlocksApproveController"
    project_root.mkdir()
    page_calls: list[object] = []
    window = SimpleNamespace(
        _settings_payload={"language": "en"},
        _current_project_root=project_root,
        _current_manifest={"current_stage": "audio_blocks_ready"},
        _speech_blocks_page=SimpleNamespace(
            source_text_position=lambda: {
                "source_scroll": 14,
                "source_horizontal_scroll": 2,
                "source_cursor_position": 4,
                "source_anchor_position": 1,
            },
            advance_to_next_block=lambda: page_calls.append("advance"),
            restore_source_text_position=lambda position: page_calls.append(("restore_source", dict(position))),
        ),
    )
    service_calls = []
    reset_calls = []
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "approve_speech_block",
        lambda *args: service_calls.append(args) or {},
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_sync_manifest_after_speech_blocks_update",
        lambda _window: reset_calls.append("sync"),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_reset_audio_assembly_after_speech_blocks_change",
        lambda _window: reset_calls.append("assembly"),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_reset_audio_block_after_speech_block_change",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected audio reset")),
    )
    monkeypatch.setattr(speech_blocks_ui_controller.misc_ui_controller, "show_message", lambda *args, **kwargs: None)

    speech_blocks_ui_controller.handle_approve_block_requested(window, "0001-000001")

    assert service_calls == [(project_root, "0001-000001")]
    assert reset_calls == ["sync", "assembly"]
    assert page_calls == [
        "advance",
        (
            "restore_source",
            {
                "source_scroll": 14,
                "source_horizontal_scroll": 2,
                "source_cursor_position": 4,
                "source_anchor_position": 1,
            },
        ),
    ]


def test_speech_blocks_ui_controller_approval_toggle_unapproves_without_advancing(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify pressing approval on an approved Speech Block unapproves it and keeps the row selected.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-05
    @version    0.1.0
    """
    project_root = tmp_path / "SpeechBlocksUnapproveController"
    project_root.mkdir()
    page_calls: list[object] = []
    window = SimpleNamespace(
        _settings_payload={"language": "en"},
        _current_project_root=project_root,
        _current_manifest={"current_stage": "speech_blocks_ready"},
        _speech_blocks_page=SimpleNamespace(
            source_text_position=lambda: {
                "source_scroll": 9,
                "source_horizontal_scroll": 4,
                "source_cursor_position": 3,
                "source_anchor_position": 1,
            },
            advance_to_next_block=lambda: page_calls.append("advance"),
            select_speech_block=lambda block_id: page_calls.append(f"select:{block_id}"),
            restore_source_text_position=lambda position: page_calls.append(("restore_source", dict(position))),
        ),
    )
    service_calls = []
    reset_calls = []
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_speech_block_by_id",
        lambda *_args: {"speech_block_id": "0001-000001", "approved": True},
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "unapprove_speech_block",
        lambda *args: service_calls.append(args) or {},
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "approve_speech_block",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected approve")),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_sync_manifest_after_speech_blocks_update",
        lambda _window: reset_calls.append("sync"),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_reset_audio_assembly_after_speech_blocks_change",
        lambda _window: reset_calls.append("assembly"),
    )
    monkeypatch.setattr(speech_blocks_ui_controller.misc_ui_controller, "show_message", lambda *args, **kwargs: None)

    speech_blocks_ui_controller.handle_approve_block_requested(window, "0001-000001")

    assert service_calls == [(project_root, "0001-000001")]
    assert reset_calls == ["sync", "assembly"]
    assert page_calls == [
        "select:0001-000001",
        (
            "restore_source",
            {
                "source_scroll": 9,
                "source_horizontal_scroll": 4,
                "source_cursor_position": 3,
                "source_anchor_position": 1,
            },
        ),
    ]


def test_speech_blocks_ui_controller_explicit_reset_clears_speech_blocks_and_downstream(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify explicit Speech Blocks reset clears Speech Blocks and downstream folders.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    project_root = _create_project(tmp_path, "SpeechBlocksControllerRerun")
    manifest = project_workspace_service.load_manifest(project_root)
    manifest["current_stage"] = "audio_assembly_ready"
    manifest["operations"]["speech_blocks"]["status"] = "completed"
    manifest["operations"]["audio_blocks"]["status"] = "completed"
    manifest["operations"]["audio_assembly"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    stale_artifacts = [
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME,
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME,
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME,
    ]
    stale_artifacts[0].write_text("[]\n", encoding="utf-8")
    stale_artifacts[1].write_text("[]\n", encoding="utf-8")
    stale_artifacts[2].write_text("{}\n", encoding="utf-8")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        speech_blocks_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(speech_blocks_ui_controller.misc_ui_controller, "show_message", lambda *args, **kwargs: None)

    speech_blocks_ui_controller.handle_reset_generation_requested(window)

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "character_voices_ready"
    assert window._current_manifest["operations"]["speech_blocks"]["status"] == "not_started"
    assert window._current_manifest["operations"]["audio_blocks"]["status"] == "not_started"
    assert window._current_manifest["operations"]["audio_assembly"]["status"] == "not_started"
    assert not stale_artifacts[0].exists()
    assert not stale_artifacts[1].exists()
    assert not stale_artifacts[2].exists()


def test_speech_blocks_sync_manifest_completes_only_after_full_approval(tmp_path) -> None:
    """
    @brief      Verify manifest metadata treats Speech Blocks as complete only after approval.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root = _create_project(tmp_path, "SpeechBlocksManifestApproval")
    manifest = project_workspace_service.load_manifest(project_root)
    artifacts_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    report_path = artifacts_root / config.SPEECH_BLOCKS_REPORT_FILE_NAME
    state_path = artifacts_root / config.SPEECH_BLOCKS_STATE_FILE_NAME
    state_path.write_text(
        json.dumps(
            {
                "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
                "status": "review_pending",
                "progress_current": 1,
                "progress_total": 1,
                "mode": "ai_assisted",
                "started_at": "2026-04-27T10:00:00+00:00",
                "completed_at": "2026-04-27T10:01:00+00:00",
                "updated_at": "2026-04-27T10:01:00+00:00",
                "warning_count": 0,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(
            {
                "speech_blocks_stage_status": "in_progress",
                "processed_chunk_count": 1,
                "total_chunk_count": 1,
                "speech_block_count": 1,
                "approved_block_count": 0,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    window = SimpleNamespace(_current_project_root=project_root, _current_manifest=manifest)

    def _show_project_state(_project_root, loaded_manifest):
        """
        @brief      Provide the show project state test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        window._current_manifest = loaded_manifest

    window.show_project_state = _show_project_state

    speech_blocks_ui_controller._sync_manifest_after_speech_blocks_update(window)  # noqa: SLF001

    assert window._current_manifest["current_stage"] == "character_voices_ready"
    assert window._current_manifest["operations"]["speech_blocks"]["status"] == "review_pending"

    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    report_payload["speech_blocks_stage_status"] = "completed"
    report_payload["approved_block_count"] = 1
    report_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")

    speech_blocks_ui_controller._sync_manifest_after_speech_blocks_update(window)  # noqa: SLF001

    assert window._current_manifest["current_stage"] == "speech_blocks_ready"
    assert window._current_manifest["operations"]["speech_blocks"]["status"] == "completed"


def _create_project(tmp_path, name: str):
    """
    @brief      Create one Speech Blocks controller project fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  name Project display name.
    @return     Project root path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-21T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["original_language"] = "en"
    manifest["current_stage"] = "character_voices_ready"
    manifest["operations"]["chunking"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": None,
                    "text": "Narration.",
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
    return project_root


def _build_window(qtbot, project_root):
    """
    @brief      Build a MainWindow bound to one temporary project.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  project_root Active project root folder.
    @return     Activated MainWindow test instance.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    window = MainWindow(settings_payload=_settings_payload())
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    return window


def _settings_payload() -> dict[str, object]:
    """
    @brief      Provide the settings payload test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    return {
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [
            {
                "id": "profile-1",
                "label": "Speech Blocks Profile",
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
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_translation_profile_id": None,
        "default_speech_blocks_profile_id": "profile-1",
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": None,
        "tts_runtime_base_url": "http://127.0.0.1:8059",
        "tts_runtime_api_key": "",
        "tts_runtime_probe_succeeded": False,
        "tts_runtime_probe_message": "",
        "tts_runtime_discovered_models": [],
        "tts_runtime_active_model_id": None,
        "tts_runtime_device_diagnostics": {},
        "tts_audio_preview_timeout_seconds": 60,
        "tts_audio_generation_timeout_seconds": 300,
    }


# END OF FILE
