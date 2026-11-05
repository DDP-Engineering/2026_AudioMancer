#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file text_interaction.py
@brief Shared text context menus, editing and local Find navigation.
@details One application event filter covers existing and future text controls.
         Native Qt editing and document search retain validation, undo and Unicode
         offsets; queries remain runtime properties of individual editors.
"""

# IMPORTS

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeySequence, QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QTextEdit

from audiomancer.services import ui_state_service

# CONSTANTS / DATA MODELS

_APPLICATION_ATTRIBUTE = "_audiomancer_text_interactions"
_QUERY_PROPERTY = "_audiomancer_find_query"
TextEditor = QLineEdit | QPlainTextEdit | QTextEdit
_EDITOR_TYPES = (QLineEdit, QPlainTextEdit, QTextEdit)

# PUBLIC API


class TextInteractionController(QObject):
    """@brief Handle text commands without owning editor contents or project persistence."""

    def __init__(self, language_provider: Callable[[], str], parent: QObject) -> None:
        """@brief Keep the locale provider live while Qt owns this controller's lifetime."""
        super().__init__(parent)
        self._language_provider = language_provider
        self._prompt_open = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """@brief Intercept only eligible text context, search-shortcut and Paste events."""
        kind = event.type()
        if self._prompt_open or kind not in (
            QEvent.Type.ContextMenu,
            QEvent.Type.ShortcutOverride,
            QEvent.Type.KeyPress,
        ):
            return False
        editor = _editor_from_target(watched)
        if not _eligible(editor):
            return False
        if kind == QEvent.Type.ContextMenu:
            menu = self.build_menu(editor)
            position = event.globalPos()
            if event.reason() == event.Reason.Keyboard:
                position = editor.mapToGlobal(editor.rect().center())
            try:
                menu.exec(position)
            finally:
                menu.deleteLater()
            return True

        command = _search_command(event)
        plain_paste = event.matches(QKeySequence.StandardKey.Paste) and not editor.isReadOnly()
        if command is None and not plain_paste:
            return False
        if kind == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        if plain_paste:
            self._paste(editor)
        elif command == "find":
            self.prompt_find(editor)
        else:
            self.find_next(editor, backward=command == "previous")
        return True

    def build_menu(self, editor: TextEditor) -> QMenu | None:
        """@brief Build a localized menu from the control's current state, excluding masked fields."""
        if not _eligible(editor):
            return None
        menu = QMenu(editor)
        editable = not editor.isReadOnly()
        selected = bool(_selected_text(editor))
        text = _plain_text(editor)

        def add(name, callback, enabled=True, shortcut=None, *, mutates=False):
            """@brief Bind an action that rechecks editability before invoking native operations."""
            action = menu.addAction(self._tr(name))
            action.setObjectName("text." + name)
            action.setEnabled(enabled)
            if shortcut is not None:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(lambda _checked=False: self._invoke(editor, callback, mutates=mutates))

        if editable:
            history = editor if isinstance(editor, QLineEdit) else editor.document()
            add("undo", editor.undo, history.isUndoAvailable(), QKeySequence.StandardKey.Undo, mutates=True)
            add("redo", editor.redo, history.isRedoAvailable(), QKeySequence.StandardKey.Redo, mutates=True)
            menu.addSeparator()
            add("cut", editor.cut, selected, QKeySequence.StandardKey.Cut, mutates=True)
        add("copy", editor.copy, selected, QKeySequence.StandardKey.Copy)
        if editable:
            add(
                "paste",
                lambda: self._paste(editor),
                bool(QApplication.clipboard().text()),
                QKeySequence.StandardKey.Paste,
                mutates=True,
            )
            add("delete", lambda: _insert_text(editor, ""), selected, "Delete", mutates=True)
        add("select_all", editor.selectAll, bool(text), QKeySequence.StandardKey.SelectAll)
        menu.addSeparator()
        add("find", lambda: self.prompt_find(editor), shortcut=QKeySequence.StandardKey.Find)
        has_query = bool(editor.property(_QUERY_PROPERTY))
        add("find_next", lambda: self.find_next(editor), has_query, "F3")
        add("find_previous", lambda: self.find_next(editor, backward=True), has_query, "Shift+F3")
        return menu

    def prompt_find(self, editor: TextEditor, *, backward: bool = False) -> None:
        """@brief Ask for a query, preserving the previous query and selection on cancellation."""
        if not _eligible(editor) or self._prompt_open:
            return
        prefill = _selected_text(editor) or str(editor.property(_QUERY_PROPERTY) or "")
        self._prompt_open = True
        try:
            query, accepted = QInputDialog.getText(
                editor,
                self._tr("find_title"),
                self._tr("find_prompt"),
                text=prefill,
            )
        finally:
            self._prompt_open = False
        if accepted and query and not self.find_text(editor, query, backward=backward):
            self._not_found(editor, query)

    def find_next(self, editor: TextEditor, *, backward: bool = False) -> None:
        """@brief Repeat the editor's accepted query, prompting when no query exists."""
        if not _eligible(editor):
            return
        query = str(editor.property(_QUERY_PROPERTY) or "")
        if not query:
            self.prompt_find(editor, backward=backward)
        elif not self.find_text(editor, query, backward=backward):
            self._not_found(editor, query)

    def find_text(self, editor: TextEditor, query: str, *, backward: bool = False) -> bool:
        """
        @brief Select a literal case-insensitive match, wrapping once without editing text.
        @param[in] editor Normal enabled text control.
        @param[in] query Accepted nonempty search string, remembered on this control only.
        @param[in] backward Search before the current selection instead of after it.
        @return True on a match; a miss preserves the original cursor and selection.
        """
        if not _eligible(editor) or not query:
            return False
        editor.setProperty(_QUERY_PROPERTY, query)
        if isinstance(editor, QLineEdit):
            document = QTextDocument()
            document.setPlainText(editor.text())
            cursor = QTextCursor(document)
            if editor.hasSelectedText():
                offset = editor.selectionStart() if backward else editor.selectionEnd()
            else:
                offset = editor.cursorPosition()
            cursor.setPosition(offset)
        else:
            document = editor.document()
            cursor = editor.textCursor()
            cursor.setPosition(cursor.selectionStart() if backward else cursor.selectionEnd())
        flags = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        found = document.find(query, cursor, flags)
        if found.isNull():
            cursor.setPosition(document.characterCount() - 1 if backward else 0)
            found = document.find(query, cursor, flags)
        if found.isNull():
            return False
        if isinstance(editor, QLineEdit):
            editor.setSelection(found.selectionStart(), found.selectionEnd() - found.selectionStart())
        else:
            editor.setTextCursor(found)
            editor.ensureCursorVisible()
        return True

    def _tr(self, key: str) -> str:
        return ui_state_service.translate("text." + key, self._language_provider())

    def _invoke(self, editor: TextEditor, callback: Callable, *, mutates: bool) -> None:
        """@brief Recheck state so a menu opened before a mode change cannot mutate locked text."""
        if _eligible(editor) and (not mutates or not editor.isReadOnly()):
            callback()

    def _paste(self, editor: TextEditor) -> None:
        """@brief Insert plain clipboard text through the control's native validation/undo path."""
        if _eligible(editor) and not editor.isReadOnly():
            text = QApplication.clipboard().text()
            if text:
                _insert_text(editor, text)

    def _not_found(self, editor: TextEditor, query: str) -> None:
        """@brief Report an unsuccessful search without changing the editor's selection."""
        notice = QMessageBox(editor)
        notice.setIcon(QMessageBox.Icon.Information)
        notice.setWindowTitle(self._tr("find_title"))
        notice.setTextFormat(Qt.TextFormat.PlainText)
        notice.setText(self._tr("not_found").format(query=query))
        try:
            notice.exec()
        finally:
            notice.deleteLater()


def install_text_interactions(
    application: QApplication,
    language_provider: Callable[[], str],
) -> TextInteractionController:
    """@brief Install once per application, refreshing the provider on subsequent calls."""
    existing = getattr(application, _APPLICATION_ATTRIBUTE, None)
    if isinstance(existing, TextInteractionController):
        existing._language_provider = language_provider
        return existing
    controller = TextInteractionController(language_provider, application)
    application.installEventFilter(controller)
    setattr(application, _APPLICATION_ATTRIBUTE, controller)
    return controller


# HELPER FUNCTIONS


def _editor_from_target(target: QObject) -> TextEditor | None:
    """@brief Resolve direct control events and multiline viewport context events only."""
    if isinstance(target, _EDITOR_TYPES):
        return target
    parent = target.parent()
    if isinstance(parent, (QPlainTextEdit, QTextEdit)) and parent.viewport() is target:
        return parent
    return None


def _eligible(editor: QObject | None) -> bool:
    """@brief Protect disabled widgets and native masked/no-echo fields."""
    return (
        isinstance(editor, _EDITOR_TYPES)
        and editor.isEnabled()
        and (not isinstance(editor, QLineEdit) or editor.echoMode() == QLineEdit.EchoMode.Normal)
    )


def _plain_text(editor: TextEditor) -> str:
    return editor.text() if isinstance(editor, QLineEdit) else editor.toPlainText()


def _selected_text(editor: TextEditor) -> str:
    return editor.selectedText() if isinstance(editor, QLineEdit) else editor.textCursor().selectedText()


def _insert_text(editor: TextEditor, text: str) -> None:
    """@brief Use native insertion to replace the selection with validated, undoable plain text."""
    if isinstance(editor, QLineEdit):
        editor.insert(text)
    else:
        editor.insertPlainText(text)


def _search_command(event) -> str | None:
    """@brief Recognize platform Find bindings plus explicit F3/Shift+F3 navigation."""
    if event.matches(QKeySequence.StandardKey.Find):
        return "find"
    if event.matches(QKeySequence.StandardKey.FindPrevious):
        return "previous"
    if event.matches(QKeySequence.StandardKey.FindNext):
        return "next"
    if event.key() == Qt.Key.Key_F3:
        if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            return "previous"
        if event.modifiers() == Qt.KeyboardModifier.NoModifier:
            return "next"
    return None


# END OF FILE
