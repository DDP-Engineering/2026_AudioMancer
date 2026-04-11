#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file placeholder_page.py
@brief Generic placeholder workflow page for AudioMancer.
@details Renders title and explanatory text for copied shell pages that have
         not been implemented functionally in AudioMancer yet.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.1.0
"""

# IMPORTS

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from audiomancer.services import ui_state_service

# PUBLIC API


class PlaceholderPage(QWidget):
    """
    @brief      Render one not-yet-implemented workflow placeholder page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """

    def __init__(self, title: str, note: str, parent=None) -> None:
        """
        @brief      Initialize the placeholder page.
        @param[in]  title Page title.
        @param[in]  note Operator-facing explanatory note.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        super().__init__(parent)
        self._title = title
        layout = QVBoxLayout(self)
        self._title_label = QLabel(f"<h2>{title}</h2>")
        self._note_label = QLabel(note)
        self._note_label.setWordWrap(True)
        layout.addWidget(self._title_label)
        layout.addWidget(self._note_label)
        layout.addStretch(1)

    def set_note(self, note: str) -> None:
        """
        @brief      Replace the placeholder explanatory note.
        @param[in]  note Operator-facing placeholder text.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        self._note_label.setText(note)

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the placeholder page.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        key_base = self._title.lower().replace(" ", "_")
        self._title_label.setText(f"<h2>{ui_state_service.translate(f'placeholder.{key_base}.title', language)}</h2>")
        self._note_label.setText(ui_state_service.translate(f"placeholder.{key_base}.note", language))


# END OF FILE
