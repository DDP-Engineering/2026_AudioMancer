#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_cleanup_page.py
@brief Focused Qt tests for the AudioMancer text-cleanup page.
@details Verifies extraction and deterministic-cleanup button enablement plus
         preview editing and search state updates for the cleanup page.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.7.2
"""

# IMPORTS

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QGridLayout, QGroupBox, QMessageBox, QWidget

from audiomancer.services import ui_state_service
from audiomancer.ui.pages.text_cleanup_page import TextCleanupPage


def test_text_cleanup_page_enables_actions_only_with_project_inputs(qtbot) -> None:
    """
    @brief      Verify extraction and cleanup become available only when their inputs exist.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.4.0
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)

    assert page._extract_button.isEnabled() is False

    page.set_project_active(True)
    page.set_processing_state(
        extracted_text=None,
        cleaned_text=None,
        notes=["Ready"],
        can_extract=True,
        can_clean=False,
        can_ai_clean=False,
    )

    assert page._extract_button.isEnabled() is True
    assert page._clean_button.isEnabled() is False
    assert page._ai_clean_button.isEnabled() is False

    page.set_ai_profiles([("Cleanup Profile", "profile_1")], "profile_1")

    page.set_processing_state(
        extracted_text="Raw text",
        cleaned_text=None,
        notes=["Cleanup ready"],
        can_extract=True,
        can_clean=True,
        can_ai_clean=True,
    )

    assert page._clean_button.isEnabled() is True
    assert page._ai_clean_button.isEnabled() is True

    page.set_busy(True)

    assert page._extract_button.isEnabled() is False
    assert page._clean_button.isEnabled() is False
    assert page._ai_clean_button.isEnabled() is False


def test_text_cleanup_page_updates_previews_and_status(qtbot) -> None:
    """
    @brief      Verify extraction state updates the previews and status pane.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.4.0
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)

    page.set_project_active(True)
    page.set_processing_state(
        extracted_text="Raw paragraph",
        cleaned_text="Clean paragraph",
        notes=["Warning A", "Warning B"],
        can_extract=True,
        can_clean=True,
        can_ai_clean=True,
    )

    assert page._extracted_text_edit.toPlainText() == "Raw paragraph"
    assert page._cleaned_text_edit.toPlainText() == "Clean paragraph"
    assert page._status_edit.toPlainText() == "Warning A\nWarning B"
    # Status pane is an undecorated, flush, three-row container: no group-box title
    # or frame, a fixed font-aware three-row height, and its text edit fills the band
    # with zero internal margins (REQ-UX-032).
    expected_status_height = ui_state_service.operator_status_pane_height(page._status_edit)
    assert page._status_group.minimumHeight() == expected_status_height
    assert page._status_group.maximumHeight() == expected_status_height
    assert expected_status_height == ui_state_service.operator_status_pane_height(page._status_edit, 3)
    assert type(page._status_group) is QWidget
    assert not isinstance(page._status_group, QGroupBox)
    assert page._status_group.layout().contentsMargins().bottom() == 0
    assert page._status_group.layout().contentsMargins().top() == 0


def test_text_cleanup_page_allows_cleaned_text_edit_and_save(monkeypatch, qtbot) -> None:
    """
    @brief      Verify cleaned text can be edited only after pressing Edit and saved through the page signal.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    monkeypatch.setattr(
        "audiomancer.ui.pages.text_cleanup_page.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_processing_state(
        extracted_text="Raw paragraph",
        cleaned_text="Clean paragraph",
        notes=["Ready"],
        can_extract=True,
        can_clean=True,
        can_ai_clean=True,
    )
    saved_payloads: list[str] = []
    page.save_cleaned_text_requested.connect(saved_payloads.append)

    assert page._cleaned_text_edit.isReadOnly() is True
    assert page._edit_cleaned_button.isEnabled() is True
    assert page._save_cleaned_button.isEnabled() is False

    page._edit_cleaned_button.click()

    assert page._cleaned_text_edit.isReadOnly() is False
    assert page._edit_cleaned_button.isEnabled() is False
    assert page._save_cleaned_button.isEnabled() is True

    page._cleaned_text_edit.setPlainText("Edited clean paragraph")
    page._save_cleaned_button.click()

    assert saved_payloads == ["Edited clean paragraph"]
    assert page._cleaned_text_edit.isReadOnly() is True
    assert page._edit_cleaned_button.isEnabled() is True
    assert page._save_cleaned_button.isEnabled() is False


def test_text_cleanup_page_cancelled_edit_confirmation_keeps_read_only(monkeypatch, qtbot) -> None:
    """
    @brief      Verify declining cleaned-text edit impact keeps the editor locked.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-05
    @version    0.1.0
    """
    monkeypatch.setattr(
        "audiomancer.ui.pages.text_cleanup_page.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_processing_state(
        extracted_text="Raw paragraph",
        cleaned_text="Clean paragraph",
        notes=["Ready"],
        can_extract=True,
        can_clean=True,
        can_ai_clean=True,
    )

    page._edit_cleaned_button.click()

    assert page._cleaned_text_edit.isReadOnly() is True
    assert page._edit_cleaned_button.isEnabled() is True
    assert page._save_cleaned_button.isEnabled() is False


def test_text_cleanup_page_installs_preview_find_context_menus(qtbot) -> None:
    """
    @brief      Verify both text previews expose right-click custom menus for Find.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)

    assert page._extracted_text_edit.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
    assert page._cleaned_text_edit.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_text_cleanup_page_finds_preview_text_with_wrap(qtbot) -> None:
    """
    @brief      Verify preview text search selects matches and wraps from the document start.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page._extracted_text_edit.setPlainText("Alpha\nBeta\nGamma")
    cursor = page._extracted_text_edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    page._extracted_text_edit.setTextCursor(cursor)

    assert page._find_preview_text(page._extracted_text_edit, "Beta") is True
    assert page._extracted_text_edit.textCursor().selectedText() == "Beta"
    assert page._find_preview_text(page._extracted_text_edit, "Delta") is False


def test_text_cleanup_page_find_next_uses_last_preview_search(monkeypatch, qtbot) -> None:
    """
    @brief      Verify Find Next advances with the remembered search text for one preview.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page._extracted_text_edit.setPlainText("Alpha\nBeta\nBeta")
    information_messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "audiomancer.ui.pages.text_cleanup_page.QMessageBox.information",
        lambda _parent, title, message: information_messages.append((title, message)),
    )

    page._preview_find_text_by_editor_id[id(page._extracted_text_edit)] = "Beta"
    page._find_next_preview_text(page._extracted_text_edit)
    first_selection_start = page._extracted_text_edit.textCursor().selectionStart()
    page._find_next_preview_text(page._extracted_text_edit)
    second_selection_start = page._extracted_text_edit.textCursor().selectionStart()

    assert page._extracted_text_edit.textCursor().selectedText() == "Beta"
    assert second_selection_start > first_selection_start
    assert information_messages == []


def test_text_cleanup_page_find_prompt_formats_not_found_message(monkeypatch, qtbot) -> None:
    """
    @brief      Verify the Find prompt formats the not-found message without translation keyword arguments.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page._extracted_text_edit.setPlainText("Alpha")
    information_messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "audiomancer.ui.pages.text_cleanup_page.QInputDialog.getText",
        lambda *_args, **_kwargs: ("Missing", True),
    )
    monkeypatch.setattr(
        "audiomancer.ui.pages.text_cleanup_page.QMessageBox.information",
        lambda _parent, title, message: information_messages.append((title, message)),
    )

    page._prompt_preview_find(page._extracted_text_edit)

    assert information_messages == [("Find Text", "No match found for 'Missing'.")]


def test_text_cleanup_page_emits_selected_ai_profile(qtbot) -> None:
    """
    @brief      Verify AI-assisted cleanup emits the currently selected profile id.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles(
        [("Cleanup Profile", "profile_1"), ("Backup", "profile_2")],
        "profile_2",
    )
    page.set_processing_state(
        extracted_text="Raw text",
        cleaned_text=None,
        notes=["AI ready"],
        can_extract=True,
        can_clean=True,
        can_ai_clean=True,
    )

    emitted_profile_ids: list[str] = []
    page.ai_clean_requested.connect(emitted_profile_ids.append)
    page._ai_clean_button.click()

    assert emitted_profile_ids == ["profile_2"]


def test_text_cleanup_page_exposes_selectable_ai_spacing_controls(qtbot) -> None:
    """
    @brief      Verify AISP-003 and REQ-UX-036 spacing controls and multi-selection signal.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_processing_state(
        extracted_text="Raw text",
        cleaned_text="Clean text",
        notes=["AI cleanup completed"],
        can_extract=True,
        can_clean=True,
        can_ai_clean=True,
        can_apply_ai_spacing=True,
        selected_spacing_categories=["heading", "separator"],
    )

    assert list(page._spacing_checkboxes) == ["heading", "separator", "noise", "header", "footer"]
    assert "story" not in page._spacing_checkboxes
    assert page.current_spacing_categories() == ["heading", "separator"]
    assert all(page._spacing_selector_layout.indexOf(widget) >= 0 for widget in page._spacing_checkboxes.values())
    assert page._cleaned_controls_layout.indexOf(page._apply_spacing_button) >= 0
    assert page._cleaned_controls_layout.indexOf(page._edit_cleaned_button) >= 0
    assert page._cleaned_controls_layout.indexOf(page._save_cleaned_button) >= 0
    assert page._apply_spacing_button.isEnabled() is True

    emitted_selections: list[list[str]] = []
    page.apply_spacing_requested.connect(emitted_selections.append)
    page._spacing_checkboxes["noise"].setChecked(True)
    page._apply_spacing_button.click()

    assert emitted_selections == [["heading", "separator", "noise"]]
    page.set_busy(True)
    assert page._apply_spacing_button.isEnabled() is False
    assert all(checkbox.isEnabled() is False for checkbox in page._spacing_checkboxes.values())


def test_text_cleanup_page_uses_two_row_spacing_and_action_grid(qtbot) -> None:
    """
    @brief      Verify AICU-005 and REQ-UX-036 exact two-row cleaned-preview controls.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.2.0
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.resize(1040, 660)
    page.show()
    qtbot.waitUntil(page.isVisible)
    qtbot.wait(10)

    controls = page._cleaned_controls_layout

    def _position(widget) -> tuple[int, int, int, int]:
        """
        @brief      Return the grid position occupied by one cleaned-preview control.
        @param[in]  widget Control registered in the cleaned-preview grid.
        @return     Row, column, row-span, and column-span tuple.
        @exception  AssertionError Raised when the control is absent.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-15
        @version    0.1.0
        """
        index = controls.indexOf(widget)
        assert index >= 0
        return controls.getItemPosition(index)

    assert isinstance(controls, QGridLayout)
    assert controls.rowCount() == 2
    assert _position(page._spacing_label) == (0, 0, 1, 1)
    assert _position(page._spacing_checkboxes["heading"]) == (0, 1, 1, 1)
    assert _position(page._spacing_checkboxes["separator"]) == (0, 2, 1, 1)
    assert _position(page._edit_cleaned_button) == (0, 4, 1, 1)
    assert _position(page._apply_spacing_button) == (1, 0, 1, 1)
    assert _position(page._spacing_checkboxes["noise"]) == (1, 1, 1, 1)
    assert _position(page._spacing_checkboxes["header"]) == (1, 2, 1, 1)
    assert _position(page._spacing_checkboxes["footer"]) == (1, 3, 1, 1)
    assert _position(page._save_cleaned_button) == (1, 4, 1, 1)
    assert controls.minimumSize().width() <= page._cleaned_group.width()


# END OF FILE
