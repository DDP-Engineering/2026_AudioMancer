#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_interaction.py
@brief Shared text-menu and search contracts for actual Qt controls.
@details Exercises edit-state transitions, clipboard, Unicode search, keyboard
         routing, dynamic dialogs and localization without project operations.
"""

# IMPORTS

from PySide6.QtCore import QMimeData, QPoint, Qt
from PySide6.QtGui import QAction, QContextMenuEvent, QIntValidator, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QTextEdit,
    QVBoxLayout,
)
import pytest

from audiomancer.ui import text_interaction
from audiomancer.ui.operation_status_dialog import OperationStatusDialog

# FIXTURES / HELPERS


@pytest.fixture
def interactions(qapp, monkeypatch):
    """@brief Install a scoped controller and restore the operator's clipboard afterwards."""
    language = {"value": "en"}
    clipboard = qapp.clipboard()
    saved = QMimeData()
    mime = clipboard.mimeData()
    if mime is not None:
        for fmt in mime.formats():
            saved.setData(fmt, mime.data(fmt))
    controller = text_interaction.install_text_interactions(qapp, lambda: language["value"])
    notices = []
    class InformationDialog(QMessageBox):
        """@brief Capture actual plain-text notice dialogs without a modal test loop."""

        def exec(self):
            """@brief Record the visible message contract, including literal query rendering."""
            assert self.textFormat() == Qt.TextFormat.PlainText
            notices.append((self.parent(), self.windowTitle(), self.text()))
            return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(text_interaction, "QMessageBox", InformationDialog)
    yield controller, language, notices
    qapp.removeEventFilter(controller)
    qapp._audiomancer_text_interactions = None
    controller.deleteLater()
    if qapp.platformName() == "offscreen":
        # The isolated platform has no operator clipboard to restore. Release
        # MIME ownership before the QApplication is destroyed on Windows.
        clipboard.clear()
    else:
        clipboard.setMimeData(saved)


def _editor(qtbot, cls, text="Alpha beta Alpha"):
    """@brief Create an actual editor with plain test content."""
    editor = cls()
    qtbot.addWidget(editor)
    if isinstance(editor, QLineEdit):
        editor.setText(text)
        editor.setCursorPosition(0)
    else:
        editor.setPlainText(text)
        editor.moveCursor(QTextCursor.MoveOperation.Start)
    return editor


def _text(editor):
    return editor.text() if isinstance(editor, QLineEdit) else editor.toPlainText()


def _selection(editor):
    return editor.selectedText() if isinstance(editor, QLineEdit) else editor.textCursor().selectedText()


def _action(menu, name):
    return next(action for action in menu.actions() if action.objectName() == "text." + name)


@pytest.mark.parametrize("cls", [QLineEdit, QPlainTextEdit, QTextEdit])
def test_context_menu_tracks_live_editability_selection_and_clipboard(interactions, qapp, qtbot, cls):
    """@brief Read-only text exposes navigation; editing adds state-aware native operations."""
    controller, _, _ = interactions
    editor = _editor(qtbot, cls)
    editor.setReadOnly(True)
    editor.selectAll()
    menu = controller.build_menu(editor)
    assert _action(menu, "copy").isEnabled()
    assert _action(menu, "find").isEnabled()
    assert not _action(menu, "find_next").isEnabled()
    assert not any(a.objectName() == "text.cut" for a in menu.actions())
    _action(menu, "copy").trigger()
    assert qapp.clipboard().text() == "Alpha beta Alpha"
    editor.setReadOnly(False)
    menu = controller.build_menu(editor)
    assert _action(menu, "cut").isEnabled()
    assert _action(menu, "paste").isEnabled()
    assert _action(menu, "delete").isEnabled()
    editor.setReadOnly(True)
    _action(menu, "delete").trigger()
    assert _text(editor) == "Alpha beta Alpha"


@pytest.mark.parametrize("cls", [QLineEdit, QPlainTextEdit, QTextEdit])
def test_clipboard_plain_paste_cut_delete_and_native_undo(interactions, qapp, qtbot, cls):
    """@brief Menu edits retain native undo and insert plain text from rich clipboard data."""
    controller, _, _ = interactions
    editor = _editor(qtbot, cls, "Original")
    editor.selectAll()
    mime = QMimeData()
    mime.setText("Replacement")
    mime.setHtml("<b>Replacement</b>")
    qapp.clipboard().setMimeData(mime)
    _action(controller.build_menu(editor), "paste").trigger()
    assert _text(editor) == "Replacement"
    if isinstance(editor, QTextEdit):
        assert editor.currentCharFormat().fontWeight() < 700
    _action(controller.build_menu(editor), "undo").trigger()
    assert _text(editor) == "Original"
    _action(controller.build_menu(editor), "redo").trigger()
    assert _text(editor) == "Replacement"
    editor.selectAll()
    _action(controller.build_menu(editor), "cut").trigger()
    assert _text(editor) == ""
    assert qapp.clipboard().text() == "Replacement"
    _action(controller.build_menu(editor), "undo").trigger()
    editor.selectAll()
    _action(controller.build_menu(editor), "delete").trigger()
    assert _text(editor) == ""


@pytest.mark.parametrize("cls", [QLineEdit, QPlainTextEdit, QTextEdit])
def test_find_wraps_both_directions_and_keeps_control_local_queries(interactions, qtbot, cls):
    """@brief Repeat search wraps case-insensitively without modifying editor contents."""
    controller, _, _ = interactions
    editor = _editor(qtbot, cls, "Alpha beta ALPHA")
    editor.setReadOnly(True)
    other = _editor(qtbot, cls, "A separate beta")
    assert controller.find_text(editor, "alpha")
    assert _selection(editor) == "Alpha"
    controller.find_next(editor)
    assert _selection(editor) == "ALPHA"
    controller.find_next(editor)
    assert _selection(editor) == "Alpha"
    controller.find_next(editor, backward=True)
    assert _selection(editor) == "ALPHA"
    assert controller.find_text(other, "beta")
    controller.find_next(editor)
    assert _selection(editor) == "Alpha"
    assert _text(editor) == "Alpha beta ALPHA"


@pytest.mark.parametrize("cls", [QLineEdit, QPlainTextEdit, QTextEdit])
def test_find_handles_literal_unicode_and_no_match_selection(interactions, qtbot, cls):
    """@brief Astral characters do not corrupt Qt selection offsets and regex syntax stays literal."""
    controller, _, notices = interactions
    editor = _editor(qtbot, cls, "😀 carte [A]. și CARTE [A].")
    assert controller.find_text(editor, "carte")
    assert _selection(editor) == "carte"
    controller.find_next(editor)
    assert _selection(editor) == "CARTE"
    assert controller.find_text(editor, "[A].")
    assert _selection(editor) == "[A]."
    assert not controller.find_text(editor, "absent")
    assert _selection(editor) == "[A]."
    controller.find_next(editor)
    assert notices
    assert _selection(editor) == "[A]."


@pytest.mark.parametrize("cls", [QLineEdit, QPlainTextEdit, QTextEdit])
def test_find_prompt_prefills_selection_and_cancel_keeps_accepted_query(interactions, qtbot, monkeypatch, cls):
    """@brief Cancelled search leaves the prior query, selection and text untouched."""
    controller, _, _ = interactions
    editor = _editor(qtbot, cls)
    controller.find_text(editor, "Alpha")
    captured = []

    def cancel(*args, **kwargs):
        """@brief Capture Find prefill while cancelling the new query."""
        captured.append(kwargs["text"])
        return "beta", False

    monkeypatch.setattr(QInputDialog, "getText", cancel)
    controller.prompt_find(editor)
    assert captured == ["Alpha"]
    assert _selection(editor) == "Alpha"
    controller.find_next(editor)
    assert _selection(editor) == "Alpha"
    if isinstance(editor, QLineEdit):
        assert editor.selectionStart() == 11
    else:
        assert editor.textCursor().selectionStart() == 11


@pytest.mark.parametrize("cls", [QLineEdit, QPlainTextEdit, QTextEdit])
def test_keyboard_find_next_previous_and_plain_paste_target_focused_editor(interactions, qapp, qtbot, monkeypatch, cls):
    """@brief Search keys consume parent shortcuts and Paste follows the plain-text path."""
    controller, _, _ = interactions
    parent = QDialog()
    qtbot.addWidget(parent)
    layout = QVBoxLayout(parent)
    editor = cls("Alpha beta Alpha", parent)
    if isinstance(editor, QLineEdit):
        editor.setCursorPosition(0)
    layout.addWidget(editor)
    parent_calls = []
    action = QAction(parent)
    action.setShortcut(QKeySequence("Ctrl+F"))
    action.triggered.connect(lambda: parent_calls.append(True))
    parent.addAction(action)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Alpha", True))
    parent.show()
    parent.activateWindow()
    editor.setFocus()
    qtbot.keyClick(editor, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert _selection(editor) == "Alpha"
    assert parent_calls == []
    qtbot.keyClick(editor, Qt.Key.Key_F3)
    assert (editor.selectionStart() if isinstance(editor, QLineEdit) else editor.textCursor().selectionStart()) == 11
    qtbot.keyClick(editor, Qt.Key.Key_F3, Qt.KeyboardModifier.ShiftModifier)
    assert (editor.selectionStart() if isinstance(editor, QLineEdit) else editor.textCursor().selectionStart()) == 0
    mime = QMimeData()
    mime.setText("Plain")
    mime.setHtml("<b>Plain</b>")
    qapp.clipboard().setMimeData(mime)
    qtbot.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert _text(editor) == "Plain beta Alpha"


def test_context_dispatch_covers_late_dialogs_and_runtime_locale(interactions, qapp, qtbot, monkeypatch):
    """@brief Future dialogs and multiline viewport events receive one localized menu."""
    controller, language, _ = interactions
    assert text_interaction.install_text_interactions(qapp, lambda: language["value"]) is controller
    editor = _editor(qtbot, QPlainTextEdit)
    captured = []
    original_build = controller.build_menu

    def capture_menu(target):
        """@brief Replace the instance's native modal exec while retaining actual Qt actions."""
        menu = original_build(target)
        menu.exec = lambda *_args: captured.append(menu)
        return menu

    monkeypatch.setattr(controller, "build_menu", capture_menu)
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(2, 2), QPoint(20, 20))
    qapp.sendEvent(editor.viewport(), event)
    assert len(captured) == 1
    assert _action(captured[-1], "find").text() == "Find…"
    language["value"] = "ro"
    assert _action(controller.build_menu(editor), "find").text() == "Caută…"
    assert _action(controller.build_menu(editor), "copy").text() == "Copiază"


@pytest.mark.parametrize(
    "mode", [QLineEdit.EchoMode.Password, QLineEdit.EchoMode.PasswordEchoOnEdit, QLineEdit.EchoMode.NoEcho]
)
def test_masked_fields_keep_native_behavior(interactions, qtbot, monkeypatch, mode):
    """@brief Protected field contents never enter shared menus or Find prompts."""
    controller, _, _ = interactions
    editor = _editor(qtbot, QLineEdit, "synthetic-secret")
    editor.setEchoMode(mode)
    editor.selectAll()
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: pytest.fail("Masked Find opened"))
    assert controller.build_menu(editor) is None
    controller.prompt_find(editor)
    qtbot.keyClick(editor, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert _text(editor) == "synthetic-secret"


def test_plain_paste_preserves_line_validator_and_readonly_keyboard_guard(interactions, qapp, qtbot):
    """@brief Native line validation rejects invalid clipboard data; locked text ignores Paste."""
    controller, _, _ = interactions
    editor = _editor(qtbot, QLineEdit, "12")
    editor.setValidator(QIntValidator(0, 99, editor))
    editor.selectAll()
    qapp.clipboard().setText("invalid")
    _action(controller.build_menu(editor), "paste").trigger()
    assert editor.text() == "12"
    qapp.clipboard().setText("34")
    qtbot.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert editor.text() == "34"
    editor.setReadOnly(True)
    editor.selectAll()
    qapp.clipboard().setText("56")
    qtbot.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert editor.text() == "34"


def test_empty_disabled_controls_and_find_prompt_reentrancy(interactions, qapp, qtbot, monkeypatch):
    """@brief Empty action states and nested Find prevention follow current control state."""
    controller, _, _ = interactions
    editor = _editor(qtbot, QPlainTextEdit, "")
    qapp.clipboard().clear()
    menu = controller.build_menu(editor)
    for name in ("copy", "cut", "delete", "undo", "redo", "select_all", "paste"):
        assert not _action(menu, name).isEnabled()
    calls = []

    def find_dialog(*_args, **_kwargs):
        """@brief A query dialog cannot recursively spawn another shared query dialog."""
        calls.append(1)
        controller.prompt_find(editor)
        return "", False

    monkeypatch.setattr(QInputDialog, "getText", find_dialog)
    controller.find_next(editor, backward=True)
    assert calls == [1]
    assert not controller._prompt_open
    editor.setEnabled(False)
    assert controller.build_menu(editor) is None
    controller.prompt_find(editor)
    assert calls == [1]


def test_dynamic_dialog_line_editor_gets_shared_context_menu(interactions, qapp, qtbot, monkeypatch):
    """@brief Direct line-editor events in a newly created dialog use the same menu."""
    controller, _, _ = interactions
    dialog = QDialog()
    qtbot.addWidget(dialog)
    editor = QLineEdit("Dialog text", dialog)
    captured = []
    original_build = controller.build_menu

    def record(target):
        """@brief Capture the actual dialog menu without entering a modal event loop."""
        menu = original_build(target)
        menu.exec = lambda *_args: captured.append(menu)
        return menu

    monkeypatch.setattr(controller, "build_menu", record)
    qapp.sendEvent(editor, QContextMenuEvent(QContextMenuEvent.Reason.Keyboard, QPoint(), QPoint()))
    assert len(captured) == 1
    assert _action(captured[0], "find_previous") is not None


def test_operation_status_uses_readonly_search_and_localized_not_found(interactions, qtbot, monkeypatch):
    """@brief The actual status dialog supports repeat search while preserving its text."""
    controller, language, notices = interactions
    dialog = OperationStatusDialog()
    qtbot.addWidget(dialog)
    dialog.set_status_text("First warning. Second warning.")
    editor = dialog._status_edit
    assert controller.find_text(editor, "warning")
    controller.find_next(editor)
    assert _selection(editor) == "warning"
    assert not any(a.objectName() == "text.paste" for a in controller.build_menu(editor).actions())
    language["value"] = "ro"
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("absent", True))
    controller.prompt_find(editor)
    assert notices[-1][1] == "Caută text"
    assert notices[-1][2] == "Textul nu a fost găsit: absent"
    assert dialog.status_text() == "First warning. Second warning."


# END OF FILE
