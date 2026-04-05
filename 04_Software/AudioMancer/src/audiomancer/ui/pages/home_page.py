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
@date 2026-04-05
@version 0.1.1
"""

# IMPORTS

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QSizePolicy,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# CONSTANTS

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
    @version    0.1.1
    """

    import_requested = Signal()

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the home/project dashboard page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.1
        """
        super().__init__(parent)
        self._project_active = False
        self._source_locked = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Home / Project</h2>"))

        summary_group = QGroupBox("Project Summary", self)
        summary_layout = QVBoxLayout(summary_group)
        self._name_label = QLabel("Project: none")
        self._path_label = QLabel("Path: none")
        self._path_label.setWordWrap(True)
        self._stage_label = QLabel("Stage: none")
        self._source_label = QLabel("Source: none")
        self._source_label.setWordWrap(True)
        for widget in (
            self._name_label,
            self._path_label,
            self._stage_label,
            self._source_label,
        ):
            summary_layout.addWidget(widget)
        layout.addWidget(summary_group)

        source_group = QGroupBox("Source Import", self)
        source_layout = QVBoxLayout(source_group)
        source_note = QLabel(
            "Each project is bound to exactly one source file. After the "
            "source is imported, the selection is locked for that project."
        )
        source_note.setWordWrap(True)
        source_layout.addWidget(source_note)
        source_row = QHBoxLayout()
        self._import_button = QPushButton("Select Source File")
        self._import_button.clicked.connect(self.import_requested.emit)
        source_row.addWidget(self._import_button)
        source_row.addStretch(1)
        source_layout.addLayout(source_row)
        self._source_lock_label = QLabel("No source imported yet.")
        self._source_lock_label.setWordWrap(True)
        locked_font = QFont(self.font())
        locked_font.setBold(True)
        self._source_lock_label.setFont(locked_font)
        self._source_lock_label.setStyleSheet("color: #7A1F1F;")
        source_layout.addWidget(self._source_lock_label)
        layout.addWidget(source_group)

        stage_group = QGroupBox("Workflow Progress", self)
        stage_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        stage_group.setMinimumHeight(340)
        stage_layout = QVBoxLayout(stage_group)
        self._stage_list = QListWidget(self)
        self._stage_list.setMinimumHeight(280)
        stage_layout.addWidget(self._stage_list)
        layout.addWidget(stage_group, 3)
        self._refresh_import_button()

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
        @version    0.1.0
        """
        self._name_label.setText(f"Project: {display_name or 'none'}")
        self._path_label.setText(f"Path: {project_path or 'none'}")
        self._stage_label.setText(f"Stage: {stage_name or 'idle'}")
        self.set_project_active(bool(project_path))

    def set_source_summary(self, summary: str | None) -> None:
        """
        @brief      Update the displayed source summary label.
        @param[in]  summary Source summary text or `None`.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        self._source_label.setText(f"Source: {summary or 'none'}")

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
        @version    0.1.0
        """
        self._source_locked = is_locked
        if is_locked:
            self._source_lock_label.setText(
                "Locked source: "
                f"{source_name or 'selected source'}. Create a new project to "
                "use another file."
            )
        else:
            self._source_lock_label.setText("No source imported yet.")
        self._refresh_import_button()

    def set_stage_statuses(self, stages: list[dict[str, str]]) -> None:
        """
        @brief      Replace the project-stage progress list.
        @param[in]  stages Ordered stage dictionaries with label, status, and note.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        self._stage_list.clear()
        for stage in stages:
            status = stage.get("status", "not_started")
            note = stage.get("note", "")
            label = stage.get("label", "Unknown Stage")
            item = QListWidgetItem(f"{_status_title(status)} | {label}")
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


def _status_title(status: str) -> str:
    """
    @brief      Convert one status token into operator-facing text.
    @param[in]  status Internal stage-status token.
    @return     Human-readable status title.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    if status == "finished":
        return "Finished"
    if status == "in_progress":
        return "In Progress"
    return "Not Started"


# END OF FILE
