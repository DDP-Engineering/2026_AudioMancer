#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audio_assembly_page.py
@brief Audio Assembly workflow page for AudioMancer.
@details Provides final WAV audiobook composition settings, progress display,
         generated-output inspection, and local preview playback controls.
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.1.0
"""

# IMPORTS

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from audiomancer.services import audio_assembly_service, ui_state_service


class AudioAssemblyPage(QWidget):
    """
    @brief      Display the Audio Assembly workflow surface.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """

    generate_requested = Signal(dict)
    reset_requested = Signal()
    settings_changed = Signal(dict)
    playback_toggle_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the Audio Assembly page widgets.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        super().__init__(parent)
        self._current_language = "en"
        self._project_active = False
        self._busy = False
        self._playback_active = False
        self._loading_state = False
        self._outputs: list[dict[str, object]] = []

        layout = QVBoxLayout(self)
        header_row = QHBoxLayout()
        self._title_label = QLabel("<h2>Audio Assembly</h2>", self)
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)
        self._generate_button = QPushButton("Generate Audio", self)
        self._generate_button.clicked.connect(self._emit_generate)
        header_row.addWidget(self._generate_button)
        self._playback_button = QPushButton("Play Audio", self)
        self._playback_button.clicked.connect(self._emit_playback_toggle)
        header_row.addWidget(self._playback_button)
        self._reset_button = QPushButton("Reset Audio Assembly", self)
        self._reset_button.clicked.connect(self.reset_requested.emit)
        header_row.addWidget(self._reset_button)
        layout.addLayout(header_row)

        self._settings_group = QGroupBox("Output Settings", self)
        settings_layout = QFormLayout(self._settings_group)
        self._output_mode_combo = QComboBox(self)
        self._output_mode_combo.addItem("Per text chunk", audio_assembly_service.OUTPUT_MODE_PER_CHUNK)
        self._output_mode_combo.addItem("Time limit", audio_assembly_service.OUTPUT_MODE_TIME_LIMIT)
        self._output_mode_combo.addItem("Whole audiobook", audio_assembly_service.OUTPUT_MODE_WHOLE_BOOK)
        self._output_mode_combo.currentIndexChanged.connect(self._handle_settings_changed)
        self._max_duration_spin = QSpinBox(self)
        self._max_duration_spin.setRange(1, 24 * 60)
        self._max_duration_spin.setSuffix(" min")
        self._max_duration_spin.valueChanged.connect(self._handle_settings_changed)
        self._output_format_combo = QComboBox(self)
        self._output_format_combo.addItem("WAV", audio_assembly_service.OUTPUT_FORMAT_WAV)
        self._output_format_combo.setEnabled(False)
        self._inter_block_gap_spin = QSpinBox(self)
        self._inter_block_gap_spin.setRange(0, 60_000)
        self._inter_block_gap_spin.setSuffix(" ms")
        self._inter_block_gap_spin.valueChanged.connect(self._handle_settings_changed)
        self._inter_chunk_gap_spin = QSpinBox(self)
        self._inter_chunk_gap_spin.setRange(0, 60_000)
        self._inter_chunk_gap_spin.setSuffix(" ms")
        self._inter_chunk_gap_spin.valueChanged.connect(self._handle_settings_changed)
        self._output_mode_label = QLabel("Output Mode", self)
        self._max_duration_label = QLabel("Max Duration", self)
        self._output_format_label = QLabel("Output Format", self)
        self._inter_block_gap_label = QLabel("Inter-Block Silence", self)
        self._inter_chunk_gap_label = QLabel("Inter-Chunk Silence", self)
        settings_layout.addRow(self._output_mode_label, self._output_mode_combo)
        settings_layout.addRow(self._max_duration_label, self._max_duration_spin)
        settings_layout.addRow(self._output_format_label, self._output_format_combo)
        settings_layout.addRow(self._inter_block_gap_label, self._inter_block_gap_spin)
        settings_layout.addRow(self._inter_chunk_gap_label, self._inter_chunk_gap_spin)
        layout.addWidget(self._settings_group, 0)

        progress_row = QHBoxLayout()
        self._progress_label = QLabel("0/0", self)
        progress_row.addWidget(self._progress_label)
        self._progress_bar = QProgressBar(self)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("%p%")
        progress_row.addWidget(self._progress_bar, 1)
        layout.addLayout(progress_row)

        self._outputs_group = QGroupBox("Generated Audiobook Files", self)
        outputs_layout = QVBoxLayout(self._outputs_group)
        self._output_list = QListWidget(self)
        self._output_list.currentRowChanged.connect(self._apply_control_state)
        outputs_layout.addWidget(self._output_list)
        layout.addWidget(self._outputs_group, 1)

        self._status_group = QGroupBox("Audio Assembly Status", self)
        status_layout = QVBoxLayout(self._status_group)
        self._status_edit = QPlainTextEdit(self)
        self._status_edit.setReadOnly(True)
        status_layout.addWidget(self._status_edit)
        self._status_group.setMinimumHeight(96)
        self._status_group.setMaximumHeight(132)
        layout.addWidget(self._status_group, 0)

        self.apply_language(self._current_language)
        self.set_project_active(False)
        self.set_audio_assembly_state(**_empty_page_state())

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Enable or disable page interactions based on project state.
        @param[in]  is_active True when a project is currently open.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        self._project_active = is_active
        self._apply_control_state()

    def set_busy(self, is_busy: bool) -> None:
        """
        @brief      Toggle busy-state handling while composition is active.
        @param[in]  is_busy True while one worker operation is active.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        self._busy = is_busy
        self._apply_control_state()

    def set_playback_active(self, is_active: bool) -> None:
        """
        @brief      Toggle generated-output playback state.
        @param[in]  is_active True while a generated file is playing.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        self._playback_active = is_active
        self._apply_control_state()

    def set_audio_assembly_state(
        self,
        settings: dict[str, object],
        outputs: list[dict[str, object]],
        current_output_key: str | None,
        notes: list[str],
        status_lines: list[str],
        progress_current: int,
        progress_total: int,
        progress_percent: int,
        stage_status: str,
        can_generate: bool,
        can_reset: bool,
        can_play_selected: bool,
    ) -> None:
        """
        @brief      Refresh the Audio Assembly page from controller-provided state.
        @param[in]  settings Current normalized Audio Assembly settings.
        @param[in]  outputs Generated output record list.
        @param[in]  current_output_key Preferred selected output key.
        @param[in]  notes Operator-facing note lines.
        @param[in]  status_lines Operator-facing status lines.
        @param[in]  progress_current Current generated output count.
        @param[in]  progress_total Planned output count.
        @param[in]  progress_percent Integer progress percentage.
        @param[in]  stage_status Effective Audio Assembly stage token.
        @param[in]  can_generate Controller-resolved generate enablement.
        @param[in]  can_reset Controller-resolved reset enablement.
        @param[in]  can_play_selected Controller-resolved playback enablement.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        self._loading_state = True
        self._stage_status = stage_status
        self._can_generate = can_generate
        self._can_reset = can_reset
        self._can_play_selected = can_play_selected
        self._outputs = list(outputs)
        normalized_settings = audio_assembly_service.normalize_audio_assembly_settings(settings)
        mode_index = self._output_mode_combo.findData(normalized_settings["output_mode"])
        self._output_mode_combo.setCurrentIndex(max(0, mode_index))
        self._max_duration_spin.setValue(int(normalized_settings["max_duration_minutes"]))
        self._output_format_combo.setCurrentIndex(0)
        self._inter_block_gap_spin.setValue(int(normalized_settings["inter_block_silence_ms"]))
        self._inter_chunk_gap_spin.setValue(int(normalized_settings["inter_chunk_silence_ms"]))
        self._progress_bar.setValue(max(0, min(int(progress_percent), 100)))
        self._progress_label.setText(f"{progress_current}/{progress_total}")
        self._status_edit.setPlainText("\n".join([*notes, "", *status_lines]).strip())
        self._output_list.clear()
        selected_index = 0
        for index, output in enumerate(self._outputs):
            if str(output.get("output_key", "")) == str(current_output_key or ""):
                selected_index = index
            self._output_list.addItem(_format_output_item(output))
        if self._outputs:
            self._output_list.setCurrentRow(selected_index)
        self._loading_state = False
        self._apply_control_state()

    def selected_output_key(self) -> str | None:
        """
        @brief      Return the currently selected generated-output key.
        @return     Selected output key or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        row = self._output_list.currentRow()
        if row < 0 or row >= len(self._outputs):
            return None
        return str(self._outputs[row].get("output_key", "")).strip() or None

    def current_settings_payload(self) -> dict[str, object]:
        """
        @brief      Return the settings payload currently selected in the UI.
        @return     Current Audio Assembly settings payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        return audio_assembly_service.normalize_audio_assembly_settings(
            {
                "output_mode": self._output_mode_combo.currentData(),
                "max_duration_minutes": self._max_duration_spin.value(),
                "output_format": self._output_format_combo.currentData(),
                "inter_block_silence_ms": self._inter_block_gap_spin.value(),
                "inter_chunk_silence_ms": self._inter_chunk_gap_spin.value(),
            }
        )

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply runtime UI language strings to page widgets.
        @param[in]  language Runtime UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        self._current_language = language
        self._title_label.setText(f"<h2>{ui_state_service.translate('audio_assembly.title', language)}</h2>")
        self._settings_group.setTitle(ui_state_service.translate("audio_assembly.settings_group", language))
        self._outputs_group.setTitle(ui_state_service.translate("audio_assembly.outputs_group", language))
        self._status_group.setTitle(ui_state_service.translate("audio_assembly.status_group", language))
        self._output_mode_label.setText(ui_state_service.translate("audio_assembly.output_mode", language))
        self._max_duration_label.setText(ui_state_service.translate("audio_assembly.max_duration", language))
        self._output_format_label.setText(ui_state_service.translate("audio_assembly.output_format", language))
        self._inter_block_gap_label.setText(ui_state_service.translate("audio_assembly.inter_block_silence", language))
        self._inter_chunk_gap_label.setText(ui_state_service.translate("audio_assembly.inter_chunk_silence", language))
        self._generate_button.setText(ui_state_service.translate("audio_assembly.generate", language))
        self._reset_button.setText(ui_state_service.translate("audio_assembly.reset", language))
        self._apply_control_state()

    def _emit_generate(self) -> None:
        """
        @brief      Emit the current Audio Assembly settings for generation.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        self.generate_requested.emit(self.current_settings_payload())

    def _emit_playback_toggle(self) -> None:
        """
        @brief      Emit playback toggle for the selected generated output.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        output_key = self.selected_output_key()
        if output_key:
            self.playback_toggle_requested.emit(output_key)

    def _handle_settings_changed(self) -> None:
        """
        @brief      Persist UI setting changes and refresh dependent controls.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        self._max_duration_spin.setEnabled(
            self._output_mode_combo.currentData() == audio_assembly_service.OUTPUT_MODE_TIME_LIMIT
        )
        if not self._loading_state:
            self.settings_changed.emit(self.current_settings_payload())
        self._apply_control_state()

    def _apply_control_state(self, *_args) -> None:
        """
        @brief      Update Audio Assembly button and settings enablement.
        @param[in]  *_args Optional Qt signal arguments.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        self._max_duration_spin.setEnabled(
            self._project_active
            and not self._busy
            and self._output_mode_combo.currentData() == audio_assembly_service.OUTPUT_MODE_TIME_LIMIT
        )
        self._settings_group.setEnabled(self._project_active and not self._busy)
        self._generate_button.setEnabled(
            self._project_active and not self._busy and bool(getattr(self, "_can_generate", False))
        )
        self._reset_button.setEnabled(
            self._project_active and not self._busy and bool(getattr(self, "_can_reset", False))
        )
        can_play = (
            self._project_active
            and not self._busy
            and bool(getattr(self, "_can_play_selected", False))
            and self.selected_output_key() is not None
        )
        self._playback_button.setEnabled(can_play)
        self._playback_button.setText(
            ui_state_service.translate("audio_assembly.stop_playing", self._current_language)
            if self._playback_active
            else ui_state_service.translate("audio_assembly.play_audio", self._current_language)
        )


def _empty_page_state() -> dict[str, object]:
    return {
        "settings": audio_assembly_service.default_audio_assembly_settings(),
        "outputs": [],
        "current_output_key": None,
        "notes": [],
        "status_lines": [],
        "progress_current": 0,
        "progress_total": 0,
        "progress_percent": 0,
        "stage_status": audio_assembly_service.AUDIO_ASSEMBLY_STAGE_NOT_STARTED,
        "can_generate": False,
        "can_reset": False,
        "can_play_selected": False,
    }


def _format_output_item(output: dict[str, object]) -> str:
    """
    @brief      Format one generated-output record for the output list.
    @param[in]  output Generated-output record.
    @return     Display text for the output list row.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    duration_seconds = int(float(output.get("duration_seconds", 0.0) or 0.0))
    minutes = duration_seconds // 60
    seconds = duration_seconds % 60
    return (
        f"{output.get('file_name', '')} | {minutes:02d}:{seconds:02d} | "
        f"{int(output.get('block_count', 0))} audio blocks"
    )


# END OF FILE
