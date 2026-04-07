#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file home_page.py
@brief Home/project dashboard page for AudioMancer.
@details Copies the DDP_Audiomancer dashboard layout so the main window uses
         the same first-page structure without implementing import behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.3.0
"""

# IMPORTS

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QSizePolicy,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from audiomancer.services import ui_state_service

# CONSTANTS

# @brief Workflow-status color palette used by the Home page stage list.
_STATUS_COLORS = {
    "not_started": QColor("#A0A0A0"),
    "in_progress": QColor("#D6A300"),
    "finished": QColor("#2E8B57"),
}


# PUBLIC API


class HomeProjectPage(QWidget):
    """
    @brief      Display the project dashboard and source-import controls.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.2.0
    """

    import_requested = Signal()

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the home/project dashboard page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.3.0
        """
        super().__init__(parent)
        self._project_active = False
        self._source_locked = False
        self._current_language = "en"
        self._current_project_name: str | None = None
        self._current_project_path: str | None = None
        self._current_stage_name: str | None = None
        self._current_source_summary: str | None = None
        self._current_locked_source_name: str | None = None
        self._stage_entries: list[dict[str, str]] = []

        layout = QVBoxLayout(self)
        self._title_label = QLabel("<h2>Home / Project</h2>")
        layout.addWidget(self._title_label)

        summary_group = QGroupBox("Project Summary", self)
        summary_layout = QGridLayout(summary_group)
        self._name_label = QLabel("Project: none")
        self._path_label = QLabel("Path: none")
        self._path_label.setWordWrap(True)
        self._stage_label = QLabel("Stage: none")
        self._source_label = QLabel("Source: none")
        self._source_label.setWordWrap(True)
        self._import_button = QPushButton("Select Source File")
        self._import_button.clicked.connect(self.import_requested.emit)
        summary_layout.addWidget(self._name_label, 0, 0)
        summary_layout.addWidget(self._import_button, 0, 1)
        summary_layout.addWidget(self._path_label, 1, 0, 1, 2)
        summary_layout.addWidget(self._stage_label, 2, 0, 1, 2)
        summary_layout.addWidget(self._source_label, 3, 0, 1, 2)
        summary_layout.addWidget(self._source_lock_label_placeholder(), 4, 0, 1, 2)
        summary_layout.setColumnStretch(0, 1)
        summary_layout.setColumnStretch(1, 0)
        layout.addWidget(summary_group)

        stage_group = QGroupBox("Workflow Progress", self)
        stage_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        stage_group.setMinimumHeight(260)
        stage_layout = QVBoxLayout(stage_group)
        self._stage_list = QListWidget(self)
        self._stage_list.setMinimumHeight(220)
        stage_layout.addWidget(self._stage_list)
        layout.addWidget(stage_group, 3)
        self._summary_group = summary_group
        self._stage_group = stage_group
        self._refresh_import_button()
        self._refresh_summary_labels()

    def set_project_state(
        self,
        display_name: str | None,
        project_path: str | None,
        stage_name: str | None,
    ) -> None:
        """
        @brief      Update the displayed project summary fields.
        @param[in]  display_name Active project display name or `None`.
        @param[in]  project_path Active project path or `None`.
        @param[in]  stage_name Active workflow stage name or `None`.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.2.0
        """
        self._current_project_name = display_name
        self._current_project_path = project_path
        self._current_stage_name = stage_name
        self._refresh_summary_labels()
        self.set_project_active(bool(project_path))

    def set_source_summary(self, summary: str | None) -> None:
        """
        @brief      Update the displayed source summary label.
        @param[in]  summary Source summary text or `None`.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.2.0
        """
        self._current_source_summary = summary
        self._refresh_summary_labels()

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Update whether the page should allow source import.
        @param[in]  is_active True when a project is active.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        self._project_active = is_active
        self._refresh_import_button()

    def set_source_locked(self, is_locked: bool, source_name: str | None) -> None:
        """
        @brief      Update the source-lock state and explanatory note.
        @param[in]  is_locked True when the project already has a source.
        @param[in]  source_name Optional source-file display name.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.2.0
        """
        self._source_locked = is_locked
        self._current_locked_source_name = source_name
        if is_locked:
            self._source_lock_label.setText(
                _build_locked_source_text(
                    self._current_language,
                    source_name,
                )
            )
        else:
            self._source_lock_label.setText(
                ui_state_service.translate("home.no_source", self._current_language)
            )
        self._refresh_import_button()

    def set_stage_statuses(self, stages: list[dict[str, str]]) -> None:
        """
        @brief      Replace the project-stage progress list.
        @param[in]  stages Ordered stage dictionaries with label, status, and note.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.2.0
        """
        self._stage_entries = [dict(stage) for stage in stages]
        self._stage_list.clear()
        for stage in self._stage_entries:
            status = stage.get("status", "not_started")
            note = stage.get("note", "")
            label = stage.get("label", "Unknown Stage")
            item = QListWidgetItem(
                f"{label} | {_status_title(status, self._current_language)}"
            )
            item.setForeground(_STATUS_COLORS.get(
                status, _STATUS_COLORS["not_started"]))
            if note:
                item.setToolTip(note)
            self._stage_list.addItem(item)

    def _refresh_import_button(self) -> None:
        """
        @brief      Apply the current button-enabled state.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        self._import_button.setEnabled(
            self._project_active and not self._source_locked
        )

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the home/project page.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.2.0
        """
        self._current_language = language
        self._title_label.setText(
            f"<h2>{ui_state_service.translate('home.title', language)}</h2>"
        )
        self._summary_group.setTitle(
            ui_state_service.translate("home.summary_group", language)
        )
        self._stage_group.setTitle(
            ui_state_service.translate("home.workflow_group", language)
        )
        self._import_button.setText(
            ui_state_service.translate("home.select_source", language)
        )
        self._refresh_summary_labels()
        if self._source_locked:
            self._source_lock_label.setText(
                _build_locked_source_text(language, self._current_locked_source_name)
            )
        else:
            self._source_lock_label.setText(
                ui_state_service.translate("home.no_source", language)
            )
        self.set_stage_statuses(self._stage_entries)

    def _refresh_summary_labels(self) -> None:
        """
        @brief      Refresh the translated project summary values.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        none_text = ui_state_service.translate("home.none", self._current_language)
        idle_text = ui_state_service.translate("status.idle", self._current_language)
        self._name_label.setText(
            _build_summary_text(
                "home.project",
                self._current_language,
                self._current_project_name or none_text,
            )
        )
        self._path_label.setText(
            _build_summary_text(
                "home.path",
                self._current_language,
                self._current_project_path or none_text,
            )
        )
        self._stage_label.setText(
            _build_summary_text(
                "home.stage",
                self._current_language,
                self._current_stage_name or idle_text,
            )
        )
        self._source_label.setText(
            _build_summary_text(
                "home.source",
                self._current_language,
                self._current_source_summary or none_text,
            )
        )
        self._source_lock_label.setText(
            _build_source_status_text(
                self._current_language,
                self._source_locked,
                self._current_locked_source_name,
            )
        )

    def _source_lock_label_placeholder(self) -> QLabel:
        """
        @brief      Build the retained source-status label used in summary.
        @return     Configured source-status label.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        self._source_lock_label = QLabel("No source imported yet.")
        self._source_lock_label.setWordWrap(True)
        locked_font = QFont(self.font())
        locked_font.setBold(True)
        self._source_lock_label.setFont(locked_font)
        self._source_lock_label.setStyleSheet("color: #7A1F1F;")
        return self._source_lock_label


def _status_title(status: str, language: str) -> str:
    """
    @brief      Convert one status token into operator-facing text.
    @param[in]  status Internal stage-status token.
    @param[in]  language Target UI language code.
    @return     Human-readable status title.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    if status == "finished":
        return ui_state_service.translate("home.status.finished", language)
    if status == "in_progress":
        return ui_state_service.translate("home.status.in_progress", language)
    return ui_state_service.translate("home.status.not_started", language)


def _build_summary_text(label_key: str, language: str, value: str) -> str:
    """
    @brief      Build one translated summary line from label and value parts.
    @param[in]  label_key Stable label translation key.
    @param[in]  language Target UI language code.
    @param[in]  value Operator-facing value text.
    @return     One `Label: value` text string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    return f"{ui_state_service.translate(label_key, language)}: {value}"


def _build_locked_source_text(language: str, source_name: str | None) -> str:
    """
    @brief      Build the translated locked-source status line.
    @param[in]  language Target UI language code.
    @param[in]  source_name Optional locked source display name.
    @return     One translated locked-source text string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    resolved_source = source_name or "selected source"
    return (
        f"{ui_state_service.translate('home.locked_source_prefix', language)}: "
        f"{resolved_source}"
        f"{ui_state_service.translate('home.locked_source_suffix', language)}"
    )


def _build_source_status_text(
    language: str,
    is_locked: bool,
    source_name: str | None,
) -> str:
    """
    @brief      Build one translated source-status text line.
    @param[in]  language Target UI language code.
    @param[in]  is_locked True when the source selection is locked.
    @param[in]  source_name Optional source display name.
    @return     One translated source-status text line.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    if is_locked:
        return _build_locked_source_text(language, source_name)
    return ui_state_service.translate("home.no_source", language)


# END OF FILE
