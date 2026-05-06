#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_chunking_page.py
@brief Focused Qt tests for the AudioMancer text-chunking page.
@details Verifies chunking-page button enablement, chunk list rendering, and
         selected chunk preview editing and search behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.4.2
"""

# IMPORTS

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QMessageBox

from audiomancer.ui.pages.text_chunking_page import TextChunkingPage


def test_text_chunking_page_renders_chunks_and_selected_preview(qtbot) -> None:
    """
    @brief      Verify chunking-page state renders chunk lists and selected preview text.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    page = TextChunkingPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_processing_state(
        cleaned_text="clean text",
        chunks=[
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "chapter_label": None,
                "text": "Paragraph text",
                "source_start_line": 1,
                "source_end_line": 1,
                "chunking_mode": "deterministic",
                "semantic_strategy": None,
                "scene_note": None,
            }
        ],
        notes=["Chunk artifact contains 1 chunks."],
        can_chunk=True,
    )

    assert page._chunk_button.isEnabled() is True
    assert page._chunk_list.count() == 1
    assert page._chunk_list.currentRow() == 0
    assert page._chunk_text_edit.toPlainText() == "Paragraph text"
    assert page._insert_chunk_button.isEnabled() is True
    assert page._delete_chunk_button.isEnabled() is False
    assert page._edit_chunk_button.isEnabled() is True
    assert "Chunk artifact contains 1 chunks." in page._notes_edit.toPlainText()
    assert page.current_ai_strategy() == "paragraph"
    assert page._notes_group.maximumHeight() == 112
    assert page._chunk_list.minimumHeight() == 132


def test_text_chunking_page_keeps_selectors_readable_while_busy(qtbot) -> None:
    """
    @brief      Verify AI selectors stay readable while chunking actions are busy.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    page = TextChunkingPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_processing_state(
        cleaned_text="clean text",
        chunks=[],
        notes=["busy"],
        can_chunk=True,
    )

    page.set_busy(True)

    assert page._chunk_button.isEnabled() is False
    assert page._ai_chunk_button.isEnabled() is False
    assert page._profile_combo.isEnabled() is True
    assert page._strategy_combo.isEnabled() is True


def test_text_chunking_page_enables_ai_button_when_profiles_exist(qtbot) -> None:
    """
    @brief      Verify AI-assisted chunking is enabled only when a profile is selected and AI chunking is allowed.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    page = TextChunkingPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_processing_state(
        cleaned_text="clean text",
        chunks=[],
        notes=["ready"],
        can_chunk=True,
        can_ai_chunk=True,
    )

    assert page._chunk_button.isEnabled() is True
    assert page._ai_chunk_button.isEnabled() is True


def test_text_chunking_page_allows_selected_chunk_edit_and_save(monkeypatch, qtbot) -> None:
    """
    @brief      Verify selected chunk text can be edited and saved through the page signal.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    monkeypatch.setattr(
        "audiomancer.ui.pages.text_chunking_page.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    page = TextChunkingPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_processing_state(
        cleaned_text="clean text",
        chunks=[
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "text": "Paragraph text",
            }
        ],
        notes=["ready"],
        can_chunk=True,
    )
    saved_payloads: list[tuple[str, str]] = []
    page.save_chunk_requested.connect(lambda chunk_id, text: saved_payloads.append((chunk_id, text)))

    assert page._chunk_text_edit.isReadOnly() is True
    assert page._edit_chunk_button.isEnabled() is True
    assert page._save_chunk_button.isEnabled() is False

    page._edit_chunk_button.click()

    assert page._chunk_text_edit.isReadOnly() is False
    assert page._edit_chunk_button.isEnabled() is False
    assert page._save_chunk_button.isEnabled() is True

    page._chunk_text_edit.setPlainText("Edited paragraph")
    page._save_chunk_button.click()

    assert saved_payloads == [("chunk-0001", "Edited paragraph")]
    assert page._chunk_text_edit.isReadOnly() is True
    assert page._chunk_list.item(0).text() == "chunk-0001 | Edited paragraph"
    assert page._edit_chunk_button.isEnabled() is True
    assert page._save_chunk_button.isEnabled() is False


def test_text_chunking_page_cancelled_edit_confirmation_keeps_read_only(monkeypatch, qtbot) -> None:
    """
    @brief      Verify declining selected chunk edit impact keeps the editor locked.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-05
    @version    0.1.0
    """
    monkeypatch.setattr(
        "audiomancer.ui.pages.text_chunking_page.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    page = TextChunkingPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_processing_state(
        cleaned_text="clean text",
        chunks=[
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "text": "Paragraph text",
            }
        ],
        notes=["ready"],
        can_chunk=True,
    )

    page._edit_chunk_button.click()

    assert page._chunk_text_edit.isReadOnly() is True
    assert page._edit_chunk_button.isEnabled() is True
    assert page._save_chunk_button.isEnabled() is False


def test_text_chunking_page_emits_insert_and_delete_requests(qtbot) -> None:
    """
    @brief      Verify selected chunk insert and delete buttons emit chunk ids.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    page = TextChunkingPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_processing_state(
        cleaned_text="clean text",
        chunks=[
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "text": "Paragraph one",
            },
            {
                "chunk_id": "chunk-0002",
                "sequence_index": 2,
                "text": "Paragraph two",
            },
        ],
        notes=["ready"],
        can_chunk=True,
    )
    inserted_ids: list[str] = []
    deleted_ids: list[str] = []
    page.insert_chunk_requested.connect(inserted_ids.append)
    page.delete_chunk_requested.connect(deleted_ids.append)

    page._insert_chunk_button.click()
    page._delete_chunk_button.click()

    assert inserted_ids == ["chunk-0001"]
    assert deleted_ids == ["chunk-0001"]


def test_text_chunking_page_installs_preview_find_context_menus(qtbot) -> None:
    """
    @brief      Verify both text previews expose right-click custom menus for Find.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    page = TextChunkingPage()
    qtbot.addWidget(page)

    assert page._cleaned_text_edit.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
    assert page._chunk_text_edit.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_text_chunking_page_find_next_uses_last_preview_search(monkeypatch, qtbot) -> None:
    """
    @brief      Verify Find Next advances with the remembered search text for one preview.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    page = TextChunkingPage()
    qtbot.addWidget(page)
    page._chunk_text_edit.setPlainText("Alpha\nBeta\nBeta")
    cursor = page._chunk_text_edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    page._chunk_text_edit.setTextCursor(cursor)
    information_messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "audiomancer.ui.pages.text_chunking_page.QMessageBox.information",
        lambda _parent, title, message: information_messages.append((title, message)),
    )

    page._preview_find_text_by_editor_id[id(page._chunk_text_edit)] = "Beta"
    page._find_next_preview_text(page._chunk_text_edit)
    first_selection_start = page._chunk_text_edit.textCursor().selectionStart()
    page._find_next_preview_text(page._chunk_text_edit)
    second_selection_start = page._chunk_text_edit.textCursor().selectionStart()

    assert page._chunk_text_edit.textCursor().selectedText() == "Beta"
    assert second_selection_start > first_selection_start
    assert information_messages == []


# END OF FILE
