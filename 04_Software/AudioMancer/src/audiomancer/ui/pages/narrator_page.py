#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file narrator_page.py
@brief Static narrator profile page for AudioMancer.
@details Provides a presentational narrator-profile manager aligned to the
         Qwen3-TTS VoiceDesign and CustomVoice concepts without adding any
         connected functionality.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.2.0
"""

# IMPORTS

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

# CONSTANTS

SUPPORTED_LANGUAGES = (
    "English",
    "German",
)


# PUBLIC API


class NarratorPage(QWidget):
    """
    @brief      Render the static narrator profile manager page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.2.0
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the narrator page shell.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.2.0
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("<h2>Narrator</h2>"))
        header_row.addStretch(1)

        header_row.addWidget(QLabel("Narrator Language"))
        self._narrator_language_combo = QComboBox(self)
        self._narrator_language_combo.addItems(SUPPORTED_LANGUAGES)
        header_row.addWidget(self._narrator_language_combo)
        layout.addLayout(header_row)

        self._summary_label = QLabel(
            "Choose a narrator profile, adapt its prompt, or create a new "
            "custom narrator profile for the current language."
        )
        self._summary_label.setWordWrap(False)
        layout.addWidget(self._summary_label)

        self._main_splitter = QSplitter(self)

        profiles_group = QGroupBox("Narrator Profiles", self)
        profiles_group.setMinimumWidth(260)
        profiles_layout = QVBoxLayout(profiles_group)

        self._profile_list = QListWidget(self)
        self._profile_list.addItems((
            "Default | Studio Neutral Narrator",
            "Default | Warm Storyteller",
            "Custom | German Stage Voice",
            "Custom | Intimate Reflective Narrator",
        ))
        profiles_layout.addWidget(self._profile_list)

        profile_button_row = QHBoxLayout()
        self._new_profile_button = QPushButton("New Profile", self)
        profile_button_row.addWidget(self._new_profile_button)
        profile_button_row.addStretch(1)
        profiles_layout.addLayout(profile_button_row)

        editor_container = QWidget(self)
        editor_container_layout = QVBoxLayout(editor_container)
        editor_container_layout.setContentsMargins(0, 0, 0, 0)

        setup_group = QGroupBox("Profile Setup", self)
        setup_layout = QFormLayout(setup_group)

        self._profile_name_edit = QLineEdit(self)
        self._profile_name_edit.setText("Warm Storyteller")
        setup_layout.addRow("Profile Name", self._profile_name_edit)
        editor_container_layout.addWidget(setup_group)

        designer_group = QGroupBox("Voice Designer Prompt", self)
        designer_layout = QVBoxLayout(designer_group)

        self._designer_prompt = QPlainTextEdit(self)
        self._designer_prompt.setPlainText(
            "Create a mature theatrical narrator voice with a warm timbre, "
            "stable pacing, crisp diction, and restrained dramatic emphasis. "
            "Keep the delivery intimate and immersive rather than radio-like."
        )
        self._designer_prompt.setMinimumHeight(220)
        designer_layout.addWidget(self._designer_prompt)
        editor_container_layout.addWidget(designer_group)

        preview_text_group = QGroupBox("Preview Text", self)
        preview_text_layout = QVBoxLayout(preview_text_group)
        self._preview_text_edit = QPlainTextEdit(self)
        self._preview_text_edit.setPlainText(
            "The hall fell silent as the final lantern dimmed, and every step "
            "carried the weight of an unspoken decision."
        )
        self._preview_text_edit.setMinimumHeight(88)
        preview_text_layout.addWidget(self._preview_text_edit)

        actions_row = QHBoxLayout()
        self._create_profile_button = QPushButton("Create Profile", self)
        self._save_profile_button = QPushButton("Save Profile", self)
        self._delete_profile_button = QPushButton("Delete Profile", self)
        self._preview_toggle_button = QPushButton("Preview", self)
        actions_row.addWidget(self._create_profile_button)
        actions_row.addWidget(self._save_profile_button)
        actions_row.addWidget(self._delete_profile_button)
        actions_row.addWidget(self._preview_toggle_button)
        actions_row.addStretch(1)
        preview_text_layout.addLayout(actions_row)
        editor_container_layout.addWidget(preview_text_group)

        self._main_splitter.addWidget(profiles_group)
        self._main_splitter.addWidget(editor_container)
        self._main_splitter.setStretchFactor(0, 3)
        self._main_splitter.setStretchFactor(1, 8)
        self._main_splitter.setSizes([300, 980])
        layout.addWidget(self._main_splitter, 1)


# END OF FILE
