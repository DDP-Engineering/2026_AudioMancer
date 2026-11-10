#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
"""

# IMPORTS

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import project_export_service, ui_state_service, ui_theme_service

# CONSTANTS

# @brief Ordered visible workflow stage tokens used by the Home progress grid.
_WORKFLOW_STAGE_TOKENS = tuple(
    stage_token
    for stage_token in config.PROJECT_WORKFLOW_STAGES
    if stage_token not in {config.DEFAULT_WORKFLOW_STAGE, "source_selected"}
)
# @brief Export-capable workflow stages mapped to the matching Home export kind.
_EXPORT_KIND_BY_STAGE_TOKEN = {
    "text_cleanup_ready": project_export_service.EXPORT_KIND_CLEANED_TEXT,
    "text_chunking_ready": project_export_service.EXPORT_KIND_TEXT_CHUNKS,
    "translation_ready": project_export_service.EXPORT_KIND_AI_TRANSLATION,
    "character_discovery_ready": project_export_service.EXPORT_KIND_CHARACTERS,
    "narrator_definition_ready": project_export_service.EXPORT_KIND_NARRATOR_VOICE,
    "character_voices_ready": project_export_service.EXPORT_KIND_CHARACTER_VOICES,
    "speech_blocks_ready": project_export_service.EXPORT_KIND_SPEECH_BLOCKS,
    "audio_assembly_ready": project_export_service.EXPORT_KIND_AUDIO_ASSEMBLY,
}
# @brief Stable compact height for correlated workflow and export rows.
_WORKFLOW_ROW_MIN_HEIGHT = 28

# @brief Home page fallback theme roles derived from the default built-in theme.
_DEFAULT_THEME_COLORS = ui_theme_service.theme_by_id(ui_theme_service.default_theme_id(), [])["colors"]

# @brief Stage status tokens mapped to theme color roles.
_STATUS_COLOR_ROLES = {
    "not_started": "disabled",
    "in_progress": "warning",
    "finished": "success",
}

# @brief Smallest bead inset from the stepper edge, in pixels.
_STEPPER_MIN_MARGIN_PX: float = 26.0


def _stepper_bead_layout(width: float, count: int) -> tuple[float, float]:
    """
    @brief      Resolve the bead inset and spacing for one stepper width.
    @details    Every caption is centred on its bead and drawn one bead spacing
                wide, so the outermost captions overhang the widget unless the
                inset is at least half a spacing. Deriving the inset from the
                width and the stage count makes the first and last captions land
                exactly on the edges; the minimum inset wins only at widths where
                it is already the larger of the two, so nothing moves there.
    @param[in]  width Stepper width in pixels.
    @param[in]  count Number of stages to draw.
    @return     Tuple of bead inset and spacing between bead centres, in pixels.
    @exception  None
    """
    if count <= 1:
        return width / 2.0, 0.0
    margin_x = max(_STEPPER_MIN_MARGIN_PX, width / (2.0 * count))
    return margin_x, max(width - 2.0 * margin_x, 1.0) / (count - 1)


class _WorkflowStepper(QWidget):
    """
    @brief      Horizontal workflow stepper that renders one status bead per stage.
    @details    Draws a connected row of stage beads (finished / in_progress / not_started)
                with captions, using the active Home theme color roles.
    @exception  None
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize an empty workflow stepper.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        """
        super().__init__(parent)
        self._steps: list[tuple[str, str]] = []
        self._colors = _normalize_home_theme_colors(None)
        self.setMinimumHeight(66)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_steps(self, stages: list[dict[str, str]]) -> None:
        """
        @brief      Replace the rendered stage set.
        @param[in]  stages Ordered stage dictionaries with label and status.
        @return     None.
        @exception  None
        """
        self._steps = [(str(stage.get("label", "")), str(stage.get("status", "not_started"))) for stage in stages]
        self.update()

    def apply_theme(self, theme_colors: dict[str, str] | None) -> None:
        """
        @brief      Apply the active Home theme color roles to the stepper.
        @param[in]  theme_colors Home theme color-role mapping.
        @return     None.
        @exception  None
        """
        payload = {"colors": theme_colors} if isinstance(theme_colors, dict) else None
        self._colors = _normalize_home_theme_colors(payload)
        self.update()

    def step_count(self) -> int:
        """
        @brief      Return the number of rendered steps.
        @return     Step count.
        @exception  None
        """
        return len(self._steps)

    def statuses(self) -> list[str]:
        """
        @brief      Return the ordered stage status tokens.
        @return     Status token list.
        @exception  None
        """
        return [status for _label, status in self._steps]

    def paintEvent(self, event) -> None:  # noqa: N802
        """
        @brief      Paint the stepper beads, connectors, and captions.
        @param[in]  event Qt paint event.
        @return     None.
        @exception  None
        """
        del event
        if not self._steps:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            self._paint_stepper(painter)
        finally:
            painter.end()

    def _paint_stepper(self, painter: QPainter) -> None:
        """
        @brief      Render every stage bead, connector, and caption.
        @param[in]  painter Active painter bound to this widget.
        @return     None.
        @exception  None
        """
        colors = self._colors
        count = len(self._steps)
        bead_radius = 11.0
        bead_center_y = 20.0
        width = float(self.width())
        margin_x, gap = _stepper_bead_layout(width, count)
        centers = [(width / 2.0 if count == 1 else margin_x + index * gap) for index in range(count)]

        border = QColor(colors.get("border", "#D7DDE5"))
        muted = QColor(colors.get("text_muted", "#5F6368"))
        text_primary = QColor(colors.get("text_primary", "#202124"))
        panel = QColor(colors.get("panel_background", "#FFFFFF"))
        finished_color = QColor(colors.get(_STATUS_COLOR_ROLES["finished"], "#2E8B57"))

        for index in range(count - 1):
            done = self._steps[index][1] == "finished"
            connector_pen = QPen(finished_color if done else border)
            connector_pen.setWidthF(2.0)
            painter.setPen(connector_pen)
            painter.drawLine(
                QPointF(centers[index] + bead_radius + 2.0, bead_center_y),
                QPointF(centers[index + 1] - bead_radius - 2.0, bead_center_y),
            )

        caption_font = QFont(self.font())
        caption_font.setPointSizeF(max(caption_font.pointSizeF() - 1.5, 6.5))
        caption_flags = (
            int(Qt.AlignmentFlag.AlignHCenter) | int(Qt.AlignmentFlag.AlignTop) | int(Qt.TextFlag.TextWordWrap)
        )

        for index, (label, status) in enumerate(self._steps):
            role = _STATUS_COLOR_ROLES.get(status, _STATUS_COLOR_ROLES["not_started"])
            status_color = QColor(colors.get(role, "#A0A0A0"))
            center_x = centers[index]
            bead_rect = QRectF(
                center_x - bead_radius,
                bead_center_y - bead_radius,
                bead_radius * 2.0,
                bead_radius * 2.0,
            )
            if status == "not_started":
                painter.setBrush(QBrush(panel))
                outline_pen = QPen(status_color)
                outline_pen.setWidthF(2.0)
                painter.setPen(outline_pen)
                painter.drawEllipse(bead_rect)
            else:
                painter.setBrush(QBrush(status_color))
                painter.setPen(QPen(status_color, 0))
                painter.drawEllipse(bead_rect)

            if status == "finished":
                check_pen = QPen(panel)
                check_pen.setWidthF(2.0)
                check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(check_pen)
                painter.drawPolyline(
                    [
                        QPointF(center_x - 4.5, bead_center_y),
                        QPointF(center_x - 1.5, bead_center_y + 3.0),
                        QPointF(center_x + 4.5, bead_center_y - 3.5),
                    ]
                )
            elif status == "in_progress":
                painter.setBrush(QBrush(panel))
                painter.setPen(QPen(panel, 0))
                painter.drawEllipse(QRectF(center_x - 3.0, bead_center_y - 3.0, 6.0, 6.0))

            caption_width = gap if gap else 88.0
            caption_rect = QRectF(
                center_x - caption_width / 2.0,
                bead_center_y + bead_radius + 5.0,
                caption_width,
                32.0,
            )
            painter.setFont(caption_font)
            painter.setPen(QPen(text_primary if status != "not_started" else muted))
            painter.drawText(caption_rect, caption_flags, label)


# PUBLIC API


class HomeProjectPage(QWidget):
    """
    @brief      Display the project dashboard, audiobook options and exports.
    @exception  None
    """

    project_snapshot_requested = Signal()
    export_requested = Signal(str, str)
    project_options_change_requested = Signal(str, str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the home/project dashboard page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        """
        super().__init__(parent)
        self._project_active = False
        self._operation_busy = False
        self._target_language = config.DEFAULT_TRANSLATION_TARGET_LANGUAGE
        self._voice_assignment_mode = config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE
        self._current_language = "en"
        self._current_project_name: str | None = None
        self._current_project_path: str | None = None
        self._current_stage_name: str | None = None
        self._current_source_summary: str | None = None
        self._stage_entries: list[dict[str, str]] = []
        self._stage_rows: list[QLineEdit] = []
        self._export_states: dict[str, dict[str, object]] = {}
        self._export_rows: dict[str, dict[str, object]] = {}
        self._export_spacers: list[QWidget] = []
        self._theme_colors = _normalize_home_theme_colors(None)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 4, 8, 4)
        root_layout.setSpacing(3)

        summary_group = QGroupBox("Project Summary", self)
        summary_layout = QGridLayout(summary_group)
        summary_layout.setContentsMargins(8, 6, 8, 6)
        summary_layout.setHorizontalSpacing(10)
        summary_layout.setVerticalSpacing(3)
        self._name_label = QLabel("Project: none")
        project_name_font = QFont(self.font())
        project_name_font.setFamily("Georgia")
        project_name_font.setBold(True)
        project_name_font.setPointSizeF(max(project_name_font.pointSizeF(), 1.0) * 1.3)
        self._name_label.setFont(project_name_font)
        self._path_label = QLabel("Path: none")
        self._path_label.setWordWrap(True)
        self._source_label = QLabel("Source: none")
        self._source_label.setWordWrap(True)
        self._target_language_caption = QLabel("Translation language")
        self._narration_mode_caption = QLabel("Audio output style")
        self._target_language_combo = QComboBox(self)
        for language_code, language_label in config.TRANSLATION_LANGUAGE_OPTIONS:
            self._target_language_combo.addItem(language_label, language_code)
        self._narration_mode_combo = QComboBox(self)
        self._narration_mode_combo.addItem("Same narrator for whole book", "same_narrator")
        self._narration_mode_combo.addItem("Narrator + character voices", "narrator_and_characters")
        self._target_language_combo.activated.connect(self._emit_project_options_change)
        self._narration_mode_combo.activated.connect(self._emit_project_options_change)
        self._snapshot_button = QPushButton("Export Project ZIP")
        self._snapshot_button.clicked.connect(self.project_snapshot_requested.emit)
        summary_action_layout = QVBoxLayout()
        summary_action_layout.setContentsMargins(0, 0, 0, 0)
        summary_action_layout.setSpacing(3)
        summary_action_layout.addWidget(self._target_language_caption)
        summary_action_layout.addWidget(self._target_language_combo)
        summary_action_layout.addWidget(self._narration_mode_caption)
        summary_action_layout.addWidget(self._narration_mode_combo)
        summary_action_layout.addWidget(self._snapshot_button)
        summary_layout.addWidget(self._name_label, 0, 0)
        summary_layout.addLayout(summary_action_layout, 0, 1, 3, 1)
        summary_layout.addWidget(self._path_label, 1, 0)
        summary_layout.addWidget(self._source_label, 2, 0)
        summary_layout.setColumnStretch(0, 1)
        summary_layout.setColumnStretch(1, 0)
        root_layout.addWidget(summary_group)

        self._workflow_stepper = _WorkflowStepper(self)
        pipeline_group = QGroupBox("Workflow Pipeline", self)
        pipeline_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        pipeline_layout = QVBoxLayout(pipeline_group)
        pipeline_layout.setContentsMargins(8, 6, 8, 4)
        pipeline_layout.addWidget(self._workflow_stepper)
        self._pipeline_group = pipeline_group
        root_layout.addWidget(pipeline_group)

        lower_layout = QHBoxLayout()
        lower_layout.setSpacing(6)
        stage_group = QGroupBox("Workflow Progress", self)
        stage_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        stage_layout = QVBoxLayout(stage_group)
        stage_layout.setContentsMargins(8, 8, 8, 8)
        stage_layout.setSpacing(4)
        for _stage_token in _WORKFLOW_STAGE_TOKENS:
            stage_row = QLineEdit(self)
            stage_row.setReadOnly(True)
            stage_row.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            stage_row.setMinimumHeight(_WORKFLOW_ROW_MIN_HEIGHT)
            stage_layout.addWidget(stage_row)
            self._stage_rows.append(stage_row)
        self._stage_list = _StageRowListProxy(self._stage_rows)
        stage_layout.addStretch(1)
        lower_layout.addWidget(stage_group, 1)

        exports_group = QGroupBox("Exports", self)
        exports_group.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )
        exports_group.setMinimumWidth(280)
        exports_layout = QGridLayout(exports_group)
        exports_layout.setContentsMargins(8, 8, 8, 8)
        exports_layout.setHorizontalSpacing(8)
        exports_layout.setVerticalSpacing(4)
        exports_layout.setColumnStretch(0, 1)
        exports_layout.setColumnStretch(1, 0)
        self._exports_layout = exports_layout
        for row_index, stage_token in enumerate(_WORKFLOW_STAGE_TOKENS):
            export_kind = _EXPORT_KIND_BY_STAGE_TOKEN.get(stage_token)
            if export_kind is None:
                spacer = QWidget(self)
                spacer.setMinimumHeight(_WORKFLOW_ROW_MIN_HEIGHT)
                spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                exports_layout.addWidget(spacer, row_index, 0, 1, 2)
                self._export_spacers.append(spacer)
                continue
            format_combo = QComboBox(self)
            format_combo.setMinimumWidth(120)
            format_combo.setMinimumHeight(_WORKFLOW_ROW_MIN_HEIGHT)
            export_button = QPushButton("", self)
            export_button.setMinimumWidth(92)
            export_button.setMinimumHeight(_WORKFLOW_ROW_MIN_HEIGHT)
            export_button.clicked.connect(
                lambda _checked=False, kind=export_kind, combo=format_combo: self.export_requested.emit(
                    kind,
                    str(combo.currentData()),
                )
            )
            exports_layout.addWidget(format_combo, row_index, 0)
            exports_layout.addWidget(export_button, row_index, 1)
            self._export_rows[export_kind] = {
                "format": format_combo,
                "button": export_button,
            }
        exports_layout.addItem(
            QSpacerItem(1, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding),
            len(_WORKFLOW_STAGE_TOKENS),
            0,
            1,
            2,
        )
        lower_layout.addWidget(exports_group)
        root_layout.addLayout(lower_layout, 1)
        self._summary_group = summary_group
        self._exports_group = exports_group
        self._stage_group = stage_group
        self._apply_workflow_row_heights()
        self._refresh_summary_actions()
        self._refresh_project_options_controls()
        self._refresh_summary_labels()
        self.set_export_states(project_export_service.build_export_states(None, None))

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
        """
        self._current_source_summary = summary
        self._refresh_summary_labels()

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Update whether the page should allow project actions.
        @param[in]  is_active True when a project is active.
        @return     None.
        @exception  None
        """
        self._project_active = is_active
        self._refresh_summary_actions()
        self._refresh_project_options_controls()

    def set_operation_busy(self, is_busy: bool) -> None:
        """
        @brief      Update summary controls that are disabled during active operations.
        @param[in]  is_busy True when a long-running workflow operation is active.
        @return     None.
        @exception  None
        """
        self._operation_busy = is_busy
        self._refresh_summary_actions()
        self._refresh_project_options_controls()

    def set_project_options(
        self,
        project_options_locked: bool,
        target_language: str,
        voice_assignment_mode: str,
    ) -> None:
        """
        @brief      Update the displayed and editable project-level audiobook options.
        @param[in]  project_options_locked Legacy flag retained for manifest compatibility.
        @param[in]  target_language Selected audiobook target language code.
        @param[in]  voice_assignment_mode Selected narration mode.
        @return     None.
        @exception  None
        """
        self._target_language = _normalize_language_code(target_language)
        self._voice_assignment_mode = _normalize_voice_assignment_mode(voice_assignment_mode)
        target_index = self._target_language_combo.findData(self._target_language)
        if target_index >= 0:
            self._target_language_combo.setCurrentIndex(target_index)
        mode_index = self._narration_mode_combo.findData(self._voice_assignment_mode)
        if mode_index >= 0:
            self._narration_mode_combo.setCurrentIndex(mode_index)
        self._refresh_summary_labels()
        self._refresh_project_options_controls()
        self._refresh_summary_actions()

    def selected_project_options(self) -> tuple[str, str]:
        """
        @brief      Return the currently displayed project options.
        @return     Tuple of target language and voice-assignment mode tokens.
        @exception  None
        """
        return (
            str(self._target_language_combo.currentData() or config.DEFAULT_TRANSLATION_TARGET_LANGUAGE),
            str(self._narration_mode_combo.currentData() or config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE),
        )

    def set_stage_statuses(self, stages: list[dict[str, str]]) -> None:
        """
        @brief      Replace the project-stage progress list.
        @param[in]  stages Ordered stage dictionaries with label, status, and note.
        @return     None.
        @exception  None
        """
        self._stage_entries = [dict(stage) for stage in stages]
        for row_index, stage_row in enumerate(self._stage_rows):
            if row_index >= len(self._stage_entries):
                stage_row.clear()
                stage_row.setToolTip("")
                stage_row.setStyleSheet(_stage_row_style("not_started", self._theme_colors))
                continue
            stage = self._stage_entries[row_index]
            status = stage.get("status", "not_started")
            note = stage.get("note", "")
            label = stage.get("label", "Unknown Stage")
            stage_row.setText(f"{label} | {_status_title(status, self._current_language)}")
            stage_row.setToolTip(note)
            stage_row.setStyleSheet(_stage_row_style(status, self._theme_colors))
        self._workflow_stepper.set_steps(self._stage_entries)

    def set_export_states(self, export_states: list[dict[str, object]]) -> None:
        """
        @brief      Replace the Home export readiness rows.
        @param[in]  export_states Ordered export readiness dictionaries.
        @return     None.
        @exception  None
        """
        self._export_states = {
            str(state.get("export_kind", "")): dict(state)
            for state in export_states
            if str(state.get("export_kind", "")) in project_export_service.EXPORT_KIND_OPTIONS
        }
        self._refresh_export_rows()

    def _refresh_summary_actions(self) -> None:
        """
        @brief      Apply the current summary button-enabled state.
        @return     None.
        @exception  None
        """
        self._snapshot_button.setEnabled(self._project_active and not self._operation_busy)

    def _refresh_project_options_controls(self) -> None:
        """
        @brief      Apply project option selector enabled state.
        @return     None.
        @exception  None
        """
        can_edit_options = self._project_active and not self._operation_busy
        self._target_language_combo.setEnabled(can_edit_options)
        self._narration_mode_combo.setEnabled(can_edit_options)

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the home/project page.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        """
        self._current_language = language
        self._summary_group.setTitle(ui_state_service.translate("home.summary_group", language))
        self._pipeline_group.setTitle(ui_state_service.translate("home.pipeline_group", language))
        self._exports_group.setTitle(ui_state_service.translate("home.exports_group", language))
        self._stage_group.setTitle(ui_state_service.translate("home.workflow_group", language))
        self._target_language_caption.setText(ui_state_service.translate("home.translation_language", language))
        self._narration_mode_caption.setText(ui_state_service.translate("home.audio_output_style", language))
        self._snapshot_button.setText(ui_state_service.translate("home.export_project_zip", language))
        for index in range(self._target_language_combo.count()):
            language_code = str(self._target_language_combo.itemData(index) or "")
            self._target_language_combo.setItemText(
                index,
                ui_state_service.localized_language_label(language_code, language),
            )
        self._narration_mode_combo.setItemText(
            0,
            ui_state_service.translate("home.mode_same_narrator", language),
        )
        self._narration_mode_combo.setItemText(
            1,
            ui_state_service.translate("home.mode_narrator_and_characters", language),
        )
        self._refresh_summary_labels()
        self.set_stage_statuses(self._stage_entries)
        self._refresh_export_rows()
        self._refresh_project_options_controls()
        self._apply_workflow_row_heights()

    def apply_theme(self, theme_payload: dict[str, object]) -> None:
        """
        @brief      Apply one runtime UI theme to Home page status visuals.
        @param[in]  theme_payload Runtime UI theme payload.
        @return     None.
        @exception  None
        """
        self._theme_colors = _normalize_home_theme_colors(theme_payload)
        self._workflow_stepper.apply_theme(self._theme_colors)
        self.set_stage_statuses(self._stage_entries)
        self._refresh_summary_labels()
        self._apply_workflow_row_heights()

    def _refresh_export_rows(self) -> None:
        """
        @brief      Refresh translated export row labels and readiness controls.
        @return     None.
        @exception  None
        """
        for export_kind, widgets in self._export_rows.items():
            state = self._export_states.get(
                export_kind,
                {
                    "export_kind": export_kind,
                    "status": project_export_service.EXPORT_STATUS_NOT_READY,
                    "can_export": False,
                },
            )
            status = str(state.get("status", project_export_service.EXPORT_STATUS_NOT_READY))
            format_combo = widgets["format"]
            export_button = widgets["button"]
            export_label = ui_state_service.translate(f"home.export.{export_kind}", self._current_language)
            export_status = ui_state_service.translate(f"home.export_status.{status}", self._current_language)
            if isinstance(format_combo, QComboBox):
                current_format = str(format_combo.currentData() or project_export_service.EXPORT_FORMAT_TXT)
                supported_formats = project_export_service.export_formats_for_kind(export_kind)
                format_combo.blockSignals(True)
                format_combo.clear()
                for export_format in supported_formats:
                    format_combo.addItem(
                        ui_state_service.translate(f"home.export_format.{export_format}", self._current_language),
                        export_format,
                    )
                restored_index = format_combo.findData(current_format)
                format_combo.setCurrentIndex(max(restored_index, 0))
                format_combo.blockSignals(False)
                format_combo.setEnabled(bool(state.get("can_export", False)))
                format_combo.setToolTip(f"{export_label}: {export_status}")
            if isinstance(export_button, QPushButton):
                button_key = (
                    "home.export_partial_button"
                    if status == project_export_service.EXPORT_STATUS_PARTIAL
                    else "home.export_button"
                )
                export_button.setText(ui_state_service.translate(button_key, self._current_language))
                export_button.setEnabled(bool(state.get("can_export", False)))
                export_button.setToolTip(f"{export_label}: {export_status}")
        self._apply_workflow_row_heights()

    def _apply_workflow_row_heights(self) -> None:
        """
        @brief      Keep workflow rows and matching export controls on identical fixed-height bands.
        @return     None.
        @exception  None
        """
        candidate_heights = [max(_WORKFLOW_ROW_MIN_HEIGHT, self.fontMetrics().height() + 12)]
        candidate_heights.extend(stage_row.sizeHint().height() for stage_row in self._stage_rows)
        for widgets in self._export_rows.values():
            format_combo = widgets["format"]
            export_button = widgets["button"]
            if isinstance(format_combo, QComboBox):
                candidate_heights.append(format_combo.sizeHint().height())
            if isinstance(export_button, QPushButton):
                candidate_heights.append(export_button.sizeHint().height())
        row_height = max(candidate_heights)
        for stage_row in self._stage_rows:
            stage_row.setMinimumHeight(row_height)
            stage_row.setMaximumHeight(row_height)
        for widgets in self._export_rows.values():
            format_combo = widgets["format"]
            export_button = widgets["button"]
            if isinstance(format_combo, QComboBox):
                format_combo.setMinimumHeight(row_height)
                format_combo.setMaximumHeight(row_height)
            if isinstance(export_button, QPushButton):
                export_button.setMinimumHeight(row_height)
                export_button.setMaximumHeight(row_height)
        for spacer in self._export_spacers:
            spacer.setMinimumHeight(row_height)
            spacer.setMaximumHeight(row_height)
        for row_index in range(len(_WORKFLOW_STAGE_TOKENS)):
            self._exports_layout.setRowMinimumHeight(row_index, row_height)
            self._exports_layout.setRowStretch(row_index, 0)

    def _refresh_summary_labels(self) -> None:
        """
        @brief      Refresh the translated project summary values.
        @return     None.
        @exception  None
        """
        none_text = ui_state_service.translate("home.none", self._current_language)
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
        self._source_label.setText(
            _build_summary_text(
                "home.source",
                self._current_language,
                self._current_source_summary or none_text,
            )
        )

    def _emit_project_options_change(self, _index: int = -1) -> None:
        """
        @brief      Request saving options after a deliberate operator selection.
        @return     None.
        @exception  None
        """
        self.project_options_change_requested.emit(*self.selected_project_options())


def _status_title(status: str, language: str) -> str:
    """
    @brief      Convert one status token into operator-facing text.
    @param[in]  status Internal stage-status token.
    @param[in]  language Target UI language code.
    @return     Human-readable status title.
    @exception  None
    """
    if status == "finished":
        return ui_state_service.translate("home.status.finished", language)
    if status == "in_progress":
        return ui_state_service.translate("home.status.in_progress", language)
    return ui_state_service.translate("home.status.not_started", language)


def _stage_row_style(status: str, theme_colors: dict[str, str] | None = None) -> str:
    """
    @brief      Build the read-only workflow row stylesheet for one status.
    @param[in]  status Internal stage-status token.
    @param[in]  theme_colors Active Home page theme color roles.
    @return     Qt stylesheet for one row box.
    @exception  None
    """
    colors = _normalize_home_theme_colors({"colors": theme_colors} if theme_colors is not None else None)
    status_role = _STATUS_COLOR_ROLES.get(status, _STATUS_COLOR_ROLES["not_started"])
    status_color = colors[status_role]
    return (
        "QLineEdit {"
        f"background: {colors['panel_background']};"
        f"border: 1px solid {colors['border']};"
        "border-radius: 4px;"
        "padding: 4px 8px;"
        f"color: {status_color};"
        "}"
    )


def _normalize_home_theme_colors(theme_payload: object) -> dict[str, str]:
    """
    @brief      Resolve a complete Home page theme color map.
    @param[in]  theme_payload Candidate runtime theme payload or colors-only mapping.
    @return     Complete color-role mapping with classic-light fallback values.
    @exception  None
    """
    default_colors = dict(_DEFAULT_THEME_COLORS) if isinstance(_DEFAULT_THEME_COLORS, dict) else {}
    if not isinstance(theme_payload, dict):
        return default_colors
    colors_payload = theme_payload.get("colors", theme_payload)
    if not isinstance(colors_payload, dict):
        return default_colors
    resolved_colors = dict(default_colors)
    for role_name, color_value in colors_payload.items():
        normalized_role = str(role_name)
        normalized_color = str(color_value).strip()
        if QColor(normalized_color).isValid():
            resolved_colors[normalized_role] = QColor(normalized_color).name().upper()
    return resolved_colors


def _build_summary_text(label_key: str, language: str, value: str) -> str:
    """
    @brief      Build one translated summary line from label and value parts.
    @param[in]  label_key Stable label translation key.
    @param[in]  language Target UI language code.
    @param[in]  value Operator-facing value text.
    @return     One `Label: value` text string.
    @exception  None
    """
    return f"{ui_state_service.translate(label_key, language)}: {value}"


def _normalize_language_code(value: object) -> str:
    """
    @brief      Normalize one translation-language code for Home-page display.
    @param[in]  value Candidate language code.
    @return     Supported language code.
    @exception  None
    """
    normalized_value = str(value or "").strip()
    if normalized_value in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
        return normalized_value
    return config.DEFAULT_TRANSLATION_TARGET_LANGUAGE


def _language_label(value: object) -> str:
    """
    @brief      Resolve one translation-language label.
    @param[in]  value Candidate language code.
    @return     Operator-facing language label.
    @exception  None
    """
    language_code = _normalize_language_code(value)
    return str(dict(config.TRANSLATION_LANGUAGE_OPTIONS).get(language_code, language_code))


def _normalize_voice_assignment_mode(value: object) -> str:
    """
    @brief      Normalize one voice-assignment mode.
    @param[in]  value Candidate mode.
    @return     Supported voice-assignment mode.
    @exception  None
    """
    normalized_value = str(value or "").strip()
    if normalized_value in config.TTS_VOICE_ASSIGNMENT_MODE_OPTIONS:
        return normalized_value
    return config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE


class _StageRowListProxy:
    """
    @brief      Backward-compatible read-only adapter for stage-row tests.
    @exception  None
    """

    def __init__(self, rows: list[QLineEdit]) -> None:
        """
        @brief      Initialize the proxy with workflow row widgets.
        @param[in]  rows Ordered stage row widgets.
        @return     None.
        @exception  None
        """
        self._rows = rows

    def count(self) -> int:
        """
        @brief      Return the number of workflow rows.
        @return     Workflow row count.
        @exception  None
        """
        return len(self._rows)

    def item(self, index: int) -> QLineEdit:
        """
        @brief      Return one workflow row by index.
        @param[in]  index Zero-based row index.
        @return     Workflow row widget.
        @exception  IndexError Raised when the index is invalid.
        """
        return self._rows[index]


# END OF FILE
