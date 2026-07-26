#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file tts_settings_page.py
@brief TTS settings page for AudioMancer.
@details Renders the operator-facing TTS Settings dialog and exposes load or
         build helpers so the main window can coordinate runtime persistence.
@author Eng. Dan Dumitru Pasare
@date 2026-05-23
@version 1.6.4
"""

# IMPORTS

import copy

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QStyleOptionSpinBox,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import ui_state_service, voiceweaver_runtime_service

# CONSTANTS

_RUNTIME_LIMIT_LABEL_MIN_WIDTH_PX = 200
_RUNTIME_LIMIT_FORM_FIELD_SPACING_PX = 16
_RUNTIME_LIMIT_COLUMN_SPACING_PX = 44
_AMBIENCE_LIMITS_LEFT_MARGIN_PX = 12
# @brief Compact width for runtime limit controls.
# @details Wide enough for the word-valued controls ("Random", "Auto") to render with their
#          arrow box instead of eliding, while still not stretching across the dialog.
_RUNTIME_LIMIT_CONTROL_MAX_WIDTH_PX = 120
_RUNTIME_LIMIT_CONTROL_MIN_WIDTH_PX = 96
_SCENE_AMBIENCE_PLACEMENT_MAX_WIDTH_PX = 420


class TtsSettingsPage(QWidget):
    """
    @brief      Display and edit global TTS runtime settings.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.4.1
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the TTS settings page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-23
        @version    1.4.2
        """
        super().__init__(parent)
        self._current_language = config.DEFAULT_LANGUAGE
        self._project_active = False
        self._discovered_models: list[dict[str, object]] = []
        self._device_diagnostics: dict[str, object] = {}
        self._capability_matrix: dict[str, object] = voiceweaver_runtime_service.build_capability_matrix([])
        self._probe_succeeded = False
        self._probe_message = ""
        self._active_model_id: str | None = None

        layout = QVBoxLayout(self)

        self._runtime_group = QGroupBox("VoiceWeaver Runtime", self)
        runtime_layout = QVBoxLayout(self._runtime_group)
        runtime_row = QHBoxLayout()
        runtime_row.setSpacing(16)

        left_column = QWidget(self)
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._base_url_label = QLabel("Base URL", self)
        self._base_url_edit = QLineEdit(self)
        self._base_url_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._api_key_label = QLabel("API Key", self)
        self._api_key_edit = QLineEdit(self)
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        left_layout.addWidget(self._base_url_label)
        left_layout.addWidget(self._base_url_edit)
        left_layout.addWidget(self._api_key_label)
        left_layout.addWidget(self._api_key_edit)
        self._test_connection_button = QPushButton("Test Connection", self)
        left_layout.addWidget(self._test_connection_button)
        self._runtime_status_label = QLabel("", self)
        self._runtime_status_label.setWordWrap(True)
        left_layout.addWidget(self._runtime_status_label)
        left_column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        runtime_row.addWidget(left_column, 1)

        self._models_group = QGroupBox("Discovered Models", self)
        models_layout = QVBoxLayout(self._models_group)
        self._model_list = QListWidget(self)
        self._model_list.setMinimumHeight(148)
        self._model_list.setMaximumHeight(148)
        models_layout.addWidget(self._model_list)
        self._models_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        runtime_row.addWidget(self._models_group, 1)
        runtime_layout.addLayout(runtime_row)
        self._runtime_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._runtime_group)

        self._planning_group = QGroupBox("Runtime Audio Limits", self)
        planning_layout = QVBoxLayout(self._planning_group)
        self._planning_status_label = QLabel("", self)
        self._planning_status_label.setWordWrap(True)
        planning_layout.addWidget(self._planning_status_label)

        self._planning_columns_layout = QHBoxLayout()
        self._planning_columns_layout.setSpacing(_RUNTIME_LIMIT_COLUMN_SPACING_PX)
        self._numeric_limits_column = QWidget(self)
        numeric_limits_form = QFormLayout(self._numeric_limits_column)
        numeric_limits_form.setContentsMargins(0, 0, 0, 0)
        numeric_limits_form.setHorizontalSpacing(_RUNTIME_LIMIT_FORM_FIELD_SPACING_PX)
        numeric_limits_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        numeric_limits_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self._ambience_limits_column = QWidget(self)
        ambience_limits_form = QFormLayout(self._ambience_limits_column)
        ambience_limits_form.setContentsMargins(_AMBIENCE_LIMITS_LEFT_MARGIN_PX, 0, 0, 0)
        ambience_limits_form.setHorizontalSpacing(_RUNTIME_LIMIT_FORM_FIELD_SPACING_PX)
        ambience_limits_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        ambience_limits_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self._preview_timeout_label = QLabel("Audio Preview Timeout (s)", self)
        self._configure_runtime_limit_label(self._preview_timeout_label)
        self._preview_timeout_spin = QSpinBox(self)
        self._preview_timeout_spin.setRange(10, 3600)
        self._preview_timeout_spin.setValue(config.DEFAULT_TTS_AUDIO_PREVIEW_TIMEOUT_SECONDS)
        self._configure_limit_spinbox(self._preview_timeout_spin)
        numeric_limits_form.addRow(self._preview_timeout_label, self._preview_timeout_spin)
        self._generation_timeout_label = QLabel("Audio Generation Timeout (s)", self)
        self._configure_runtime_limit_label(self._generation_timeout_label)
        self._generation_timeout_spin = QSpinBox(self)
        self._generation_timeout_spin.setRange(30, 7200)
        self._generation_timeout_spin.setValue(config.DEFAULT_TTS_AUDIO_GENERATION_TIMEOUT_SECONDS)
        self._configure_limit_spinbox(self._generation_timeout_spin)
        numeric_limits_form.addRow(self._generation_timeout_label, self._generation_timeout_spin)
        self._preview_text_limit_label = QLabel("Preview Text Limit (chars)", self)
        self._configure_runtime_limit_label(self._preview_text_limit_label)
        self._preview_text_limit_spin = QSpinBox(self)
        self._preview_text_limit_spin.setRange(64, 8192)
        self._preview_text_limit_spin.setValue(config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT)
        self._configure_limit_spinbox(self._preview_text_limit_spin)
        numeric_limits_form.addRow(self._preview_text_limit_label, self._preview_text_limit_spin)
        self._speech_block_target_label = QLabel("Narration Block Target (s)", self)
        self._configure_runtime_limit_label(self._speech_block_target_label)
        self._speech_block_target_spin = QDoubleSpinBox(self)
        self._speech_block_target_spin.setRange(0.0, config.SPEECH_BLOCK_TARGET_AUDIO_SECONDS_MAXIMUM)
        self._speech_block_target_spin.setSingleStep(5.0)
        self._speech_block_target_spin.setDecimals(0)
        # The minimum doubles as "no operator preference", so the model budget decides.
        # Kept short because this column is narrow; the tooltip carries the explanation.
        self._speech_block_target_spin.setSpecialValueText("Auto")
        self._speech_block_target_spin.setValue(config.DEFAULT_SPEECH_BLOCK_TARGET_AUDIO_SECONDS)
        self._speech_block_target_spin.setToolTip(
            "Preferred spoken length of one same-narrator block. "
            "The TTS model budget always stays the hard limit, so this can only shorten blocks."
        )
        self._configure_limit_spinbox(self._speech_block_target_spin)
        numeric_limits_form.addRow(self._speech_block_target_label, self._speech_block_target_spin)
        self._scene_ambience_placement_label = QLabel("Scene Ambience Placement", self)
        self._scene_ambience_placement_combo = QComboBox(self)
        self._scene_ambience_placement_combo.setMinimumWidth(140)
        self._scene_ambience_placement_combo.setMaximumWidth(_SCENE_AMBIENCE_PLACEMENT_MAX_WIDTH_PX)
        self._scene_ambience_placement_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for placement in config.SCENE_AMBIENCE_PLACEMENT_OPTIONS:
            self._scene_ambience_placement_combo.addItem(placement, placement)
        ambience_limits_form.addRow(self._scene_ambience_placement_label, self._scene_ambience_placement_combo)
        self._scene_ambience_duration_label = QLabel("Scene Ambience Duration (s)", self)
        self._scene_ambience_duration_spin = QSpinBox(self)
        self._scene_ambience_duration_spin.setRange(1, 120)
        self._scene_ambience_duration_spin.setValue(config.DEFAULT_SCENE_AMBIENCE_DURATION_SECONDS)
        self._configure_limit_spinbox(self._scene_ambience_duration_spin)
        ambience_limits_form.addRow(self._scene_ambience_duration_label, self._scene_ambience_duration_spin)
        self._scene_ambience_max_blocks_label = QLabel("Scene Ambience Max Blocks", self)
        self._scene_ambience_max_blocks_spin = QSpinBox(self)
        self._scene_ambience_max_blocks_spin.setRange(1, 24)
        self._scene_ambience_max_blocks_spin.setValue(config.DEFAULT_SCENE_AMBIENCE_MAX_BLOCKS_PER_SEQUENCE)
        self._configure_limit_spinbox(self._scene_ambience_max_blocks_spin)
        ambience_limits_form.addRow(self._scene_ambience_max_blocks_label, self._scene_ambience_max_blocks_spin)
        self._scene_ambience_guidance_label = QLabel("Scene Ambience Guidance", self)
        self._scene_ambience_guidance_spin = QDoubleSpinBox(self)
        self._scene_ambience_guidance_spin.setRange(0.1, 30.0)
        self._scene_ambience_guidance_spin.setSingleStep(0.5)
        self._scene_ambience_guidance_spin.setDecimals(1)
        self._scene_ambience_guidance_spin.setValue(config.DEFAULT_SCENE_AMBIENCE_GUIDANCE_SCALE)
        self._configure_limit_spinbox(self._scene_ambience_guidance_spin)
        ambience_limits_form.addRow(self._scene_ambience_guidance_label, self._scene_ambience_guidance_spin)
        self._scene_ambience_steps_label = QLabel("Scene Ambience Steps", self)
        self._scene_ambience_steps_spin = QSpinBox(self)
        self._scene_ambience_steps_spin.setRange(1, 300)
        self._scene_ambience_steps_spin.setValue(config.DEFAULT_SCENE_AMBIENCE_NUM_INFERENCE_STEPS)
        self._configure_limit_spinbox(self._scene_ambience_steps_spin)
        ambience_limits_form.addRow(self._scene_ambience_steps_label, self._scene_ambience_steps_spin)
        self._scene_ambience_seed_label = QLabel("Scene Ambience Seed", self)
        self._scene_ambience_seed_spin = QSpinBox(self)
        self._scene_ambience_seed_spin.setRange(-1, 2_147_483_647)
        self._scene_ambience_seed_spin.setSpecialValueText("Random")
        self._scene_ambience_seed_spin.setValue(-1)
        self._configure_limit_spinbox(self._scene_ambience_seed_spin)
        ambience_limits_form.addRow(self._scene_ambience_seed_label, self._scene_ambience_seed_spin)
        self._numeric_limits_column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._ambience_limits_column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._planning_columns_layout.addWidget(self._numeric_limits_column, 1)
        self._planning_columns_layout.addWidget(self._ambience_limits_column, 1)
        planning_layout.addLayout(self._planning_columns_layout)
        self._planning_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._planning_group)
        layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._cancel_button = QPushButton("Cancel", self)
        self._save_button = QPushButton("Save", self)
        self._ok_button = QPushButton("OK", self)
        button_row.addWidget(self._cancel_button)
        button_row.addWidget(self._save_button)
        button_row.addWidget(self._ok_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

    def load_state(
        self,
        settings_payload: dict[str, object],
        project_plan_payload: dict[str, object] | None,
        project_active: bool,
    ) -> None:
        """
        @brief      Load one runtime TTS state into the page.
        @param[in]  settings_payload Current application settings payload.
        @param[in]  project_plan_payload Optional normalized project TTS plan payload.
        @param[in]  project_active True when one project is currently open.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-23
        @version    1.5.0
        """
        self._project_active = project_active
        self._base_url_edit.setText(
            str(settings_payload.get("tts_runtime_base_url", config.DEFAULT_TTS_RUNTIME_BASE_URL))
        )
        self._api_key_edit.setText(str(settings_payload.get("tts_runtime_api_key", "")))
        # Dialog always opens with a fresh "Not connected" state — the operator must
        # re-run Test Connection in each session so the displayed status reflects the
        # live runtime and not a stale flag persisted from a previous session.
        self._probe_succeeded = False
        self._probe_message = ""
        self._preview_timeout_spin.setValue(
            int(
                settings_payload.get(
                    "tts_audio_preview_timeout_seconds",
                    config.DEFAULT_TTS_AUDIO_PREVIEW_TIMEOUT_SECONDS,
                )
            )
        )
        self._generation_timeout_spin.setValue(
            int(
                settings_payload.get(
                    "tts_audio_generation_timeout_seconds",
                    config.DEFAULT_TTS_AUDIO_GENERATION_TIMEOUT_SECONDS,
                )
            )
        )
        self._preview_text_limit_spin.setValue(
            int(
                settings_payload.get(
                    "tts_preview_text_character_limit",
                    config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT,
                )
            )
        )
        self._speech_block_target_spin.setValue(
            float(
                settings_payload.get(
                    "speech_block_target_audio_seconds",
                    config.DEFAULT_SPEECH_BLOCK_TARGET_AUDIO_SECONDS,
                )
                or 0.0
            )
        )
        scene_ambience_placement = str(
            settings_payload.get(
                "scene_ambience_placement",
                config.DEFAULT_SCENE_AMBIENCE_PLACEMENT,
            )
        ).strip()
        if scene_ambience_placement not in config.SCENE_AMBIENCE_PLACEMENT_OPTIONS:
            scene_ambience_placement = config.DEFAULT_SCENE_AMBIENCE_PLACEMENT
        self._set_combo_value(self._scene_ambience_placement_combo, scene_ambience_placement)
        self._scene_ambience_duration_spin.setValue(
            int(
                settings_payload.get(
                    "scene_ambience_duration_seconds",
                    config.DEFAULT_SCENE_AMBIENCE_DURATION_SECONDS,
                )
            )
        )
        self._scene_ambience_max_blocks_spin.setValue(
            int(
                settings_payload.get(
                    "scene_ambience_max_blocks_per_sequence",
                    config.DEFAULT_SCENE_AMBIENCE_MAX_BLOCKS_PER_SEQUENCE,
                )
            )
        )
        self._scene_ambience_guidance_spin.setValue(
            float(
                settings_payload.get(
                    "scene_ambience_guidance_scale",
                    config.DEFAULT_SCENE_AMBIENCE_GUIDANCE_SCALE,
                )
            )
        )
        self._scene_ambience_steps_spin.setValue(
            int(
                settings_payload.get(
                    "scene_ambience_num_inference_steps",
                    config.DEFAULT_SCENE_AMBIENCE_NUM_INFERENCE_STEPS,
                )
            )
        )
        scene_ambience_seed = settings_payload.get("scene_ambience_seed", config.DEFAULT_SCENE_AMBIENCE_SEED)
        self._scene_ambience_seed_spin.setValue(-1 if scene_ambience_seed is None else int(scene_ambience_seed))
        self._active_model_id = (
            None
            if settings_payload.get("tts_runtime_active_model_id") in (None, "")
            else str(settings_payload.get("tts_runtime_active_model_id"))
        )
        self._discovered_models = [
            dict(model)
            for model in settings_payload.get("tts_runtime_discovered_models", [])
            if isinstance(model, dict)
        ]
        self._device_diagnostics = (
            dict(settings_payload.get("tts_runtime_device_diagnostics", {}))
            if isinstance(settings_payload.get("tts_runtime_device_diagnostics"), dict)
            else {}
        )
        self._capability_matrix = voiceweaver_runtime_service.build_capability_matrix(self._discovered_models)
        self._rebuild_model_list()
        self._runtime_status_label.setText(self._build_runtime_status_text())
        self._load_project_plan(project_plan_payload or {})
        self.apply_language(str(settings_payload.get("language", config.DEFAULT_LANGUAGE)))

    def apply_probe_result(self, probe_result: dict[str, object]) -> None:
        """
        @brief      Apply one VoiceWeaver probe result to the current page state.
        @param[in]  probe_result Normalized VoiceWeaver probe result payload.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-18
        @version    1.1.0
        """
        self._probe_succeeded = bool(probe_result.get("success", False))
        self._probe_message = str(probe_result.get("message", ""))
        self._active_model_id = (
            None if probe_result.get("active_model_id") in (None, "") else str(probe_result.get("active_model_id"))
        )
        self._discovered_models = [
            dict(model) for model in probe_result.get("discovered_models", []) if isinstance(model, dict)
        ]
        self._device_diagnostics = (
            dict(probe_result.get("device_diagnostics", {}))
            if isinstance(probe_result.get("device_diagnostics"), dict)
            else {}
        )
        self._capability_matrix = voiceweaver_runtime_service.build_capability_matrix(self._discovered_models)
        self._rebuild_model_list()
        self._runtime_status_label.setText(self._build_runtime_status_text())
        self._apply_planning_state()

    def build_settings(self, existing_settings_payload: dict[str, object]) -> dict[str, object]:
        """
        @brief      Merge the page-owned runtime settings into one settings payload.
        @param[in]  existing_settings_payload Existing application settings payload.
        @return     Merged settings payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.2.0
        """
        merged_settings = copy.deepcopy(existing_settings_payload)
        merged_settings["tts_runtime_base_url"] = self._base_url_edit.text().strip()
        merged_settings["tts_runtime_api_key"] = self._api_key_edit.text()
        merged_settings["tts_runtime_probe_succeeded"] = self._probe_succeeded
        merged_settings["tts_runtime_probe_message"] = self._probe_message
        merged_settings["tts_runtime_discovered_models"] = [dict(model) for model in self._discovered_models]
        merged_settings["tts_runtime_active_model_id"] = self._active_model_id
        merged_settings["tts_runtime_device_diagnostics"] = dict(self._device_diagnostics)
        merged_settings["tts_audio_preview_timeout_seconds"] = self._preview_timeout_spin.value()
        merged_settings["tts_audio_generation_timeout_seconds"] = self._generation_timeout_spin.value()
        merged_settings["tts_preview_text_character_limit"] = self._preview_text_limit_spin.value()
        speech_block_target = float(self._speech_block_target_spin.value())
        merged_settings["speech_block_target_audio_seconds"] = (
            0.0
            if speech_block_target <= 0.0
            else max(speech_block_target, float(config.SPEECH_BLOCK_TARGET_AUDIO_SECONDS_MINIMUM))
        )
        merged_settings.pop("scene_ambience_generation_enabled", None)
        merged_settings.pop("scene_ambience_audio_generation_enabled", None)
        merged_settings["scene_ambience_placement"] = str(
            self._scene_ambience_placement_combo.currentData() or config.DEFAULT_SCENE_AMBIENCE_PLACEMENT
        )
        merged_settings["scene_ambience_duration_seconds"] = self._scene_ambience_duration_spin.value()
        merged_settings["scene_ambience_max_blocks_per_sequence"] = self._scene_ambience_max_blocks_spin.value()
        merged_settings["scene_ambience_guidance_scale"] = self._scene_ambience_guidance_spin.value()
        merged_settings["scene_ambience_num_inference_steps"] = self._scene_ambience_steps_spin.value()
        seed_value = self._scene_ambience_seed_spin.value()
        merged_settings["scene_ambience_seed"] = None if seed_value < 0 else seed_value
        return merged_settings

    def build_tts_plan_payload(self) -> dict[str, object] | None:
        """
        @brief      Return no project-local TTS plan because project options are locked on Home.
        @return     Project-local TTS plan payload or None when no project is active.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-18
        @version    1.2.0
        """
        return None

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the TTS settings page labels.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-17
        @version    1.2.0
        """
        self._current_language = language
        self._runtime_group.setTitle(ui_state_service.translate("tts_settings.runtime_group", language))
        self._base_url_label.setText(ui_state_service.translate("tts_settings.base_url", language))
        self._api_key_label.setText(ui_state_service.translate("tts_settings.api_key", language))
        self._test_connection_button.setText(ui_state_service.translate("tts_settings.test_connection", language))
        self._models_group.setTitle(ui_state_service.translate("tts_settings.models_group", language))
        self._planning_group.setTitle(ui_state_service.translate("tts_settings.plan_group", language))
        self._preview_timeout_label.setText(ui_state_service.translate("tts_settings.preview_timeout", language))
        self._generation_timeout_label.setText(ui_state_service.translate("tts_settings.generation_timeout", language))
        self._preview_text_limit_label.setText(ui_state_service.translate("tts_settings.preview_text_limit", language))
        self._scene_ambience_placement_label.setText(
            ui_state_service.translate("tts_settings.scene_ambience_placement", language)
        )
        self._scene_ambience_duration_label.setText(
            ui_state_service.translate("tts_settings.scene_ambience_duration", language)
        )
        self._scene_ambience_max_blocks_label.setText(
            ui_state_service.translate("tts_settings.scene_ambience_max_blocks", language)
        )
        self._scene_ambience_guidance_label.setText(
            ui_state_service.translate("tts_settings.scene_ambience_guidance", language)
        )
        self._scene_ambience_steps_label.setText(
            ui_state_service.translate("tts_settings.scene_ambience_steps", language)
        )
        self._scene_ambience_seed_label.setText(
            ui_state_service.translate("tts_settings.scene_ambience_seed", language)
        )
        self._refresh_scene_ambience_placement_labels()
        self._cancel_button.setText(ui_state_service.translate("tts_settings.cancel", language))
        self._save_button.setText(ui_state_service.translate("tts_settings.save", language))
        self._ok_button.setText(ui_state_service.translate("tts_settings.ok", language))
        self._runtime_status_label.setText(self._build_runtime_status_text())
        self._rebuild_model_list()
        self._apply_planning_state()

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        """
        @brief      Select one combo-box item by stored data.
        @param[in]  combo Target combo box.
        @param[in]  value Stored item value.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-20
        @version    0.1.0
        """
        for index in range(combo.count()):
            if str(combo.itemData(index)) == value:
                combo.setCurrentIndex(index)
                return

    def _configure_limit_spinbox(self, spinbox: QAbstractSpinBox) -> None:
        """
        @brief      Configure compact numeric controls for runtime limits.
        @param[in]  spinbox Target spin box.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-23
        @version    0.2.1
        """
        spinbox.setMinimumWidth(_RUNTIME_LIMIT_CONTROL_MIN_WIDTH_PX)
        spinbox.setMaximumWidth(_RUNTIME_LIMIT_CONTROL_MAX_WIDTH_PX)
        spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        spinbox.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        spinbox.installEventFilter(self)

    def eventFilter(self, watched: object, event: object) -> bool:
        """
        @brief      Keep compact spin-box arrow clicks aligned to the real Qt arrow boxes.
        @param[in]  watched Object receiving the event.
        @param[in]  event Event delivered to the object.
        @return     True when the event was handled locally.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-23
        @version    0.3.0
        """
        if isinstance(watched, QAbstractSpinBox) and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() != Qt.MouseButton.LeftButton or not watched.isEnabled():
                return False
            click_position = event.position().toPoint()
            style_option = QStyleOptionSpinBox()
            watched.initStyleOption(style_option)
            up_button_rect = watched.style().subControlRect(
                QStyle.ComplexControl.CC_SpinBox,
                style_option,
                QStyle.SubControl.SC_SpinBoxUp,
                watched,
            )
            down_button_rect = watched.style().subControlRect(
                QStyle.ComplexControl.CC_SpinBox,
                style_option,
                QStyle.SubControl.SC_SpinBoxDown,
                watched,
            )
            if up_button_rect.contains(click_position):
                watched.stepBy(1)
                watched.selectAll()
                return True
            if down_button_rect.contains(click_position):
                watched.stepBy(-1)
                watched.selectAll()
                return True
        return super().eventFilter(watched, event)

    def _configure_runtime_limit_label(self, label: QLabel) -> None:
        """
        @brief      Reserve label width so larger fonts do not crowd numeric fields.
        @param[in]  label Target label.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-20
        @version    0.1.0
        """
        label.setMinimumWidth(_RUNTIME_LIMIT_LABEL_MIN_WIDTH_PX)

    def _refresh_scene_ambience_placement_labels(self) -> None:
        """
        @brief      Refresh localized Scene Ambience placement combo labels.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-20
        @version    0.1.0
        """
        current_value = str(
            self._scene_ambience_placement_combo.currentData() or config.DEFAULT_SCENE_AMBIENCE_PLACEMENT
        )
        self._scene_ambience_placement_combo.blockSignals(True)
        self._scene_ambience_placement_combo.clear()
        for placement in config.SCENE_AMBIENCE_PLACEMENT_OPTIONS:
            placement_label = ui_state_service.translate(
                f"tts_settings.scene_ambience_placement_{placement}",
                self._current_language,
            )
            self._scene_ambience_placement_combo.addItem(
                placement_label,
                placement,
            )
        self._set_combo_value(self._scene_ambience_placement_combo, current_value)
        self._scene_ambience_placement_combo.blockSignals(False)

    def _load_project_plan(self, project_plan_payload: dict[str, object]) -> None:
        """
        @brief      Load the project plan.
        @param[in]  project_plan_payload Payload for `project_plan_payload`.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.2.0
        """
        _ = project_plan_payload
        self._apply_planning_state()

    def _rebuild_model_list(self) -> None:
        """
        @brief      Execute the rebuild model list helper.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        self._model_list.clear()
        if not self._discovered_models:
            self._model_list.addItem(ui_state_service.translate("tts_settings.no_models", self._current_language))
            return
        for model in self._discovered_models:
            model_id = str(model.get("model_id", "")).strip()
            status = str(model.get("status", "")).strip() or "-"
            generation_modes = ", ".join(
                str(mode).strip() for mode in model.get("supported_generation_modes", []) if str(mode).strip()
            )
            active_suffix = (
                f" | {ui_state_service.translate('tts_settings.active_model_marker', self._current_language)}"
                if model_id and model_id == self._active_model_id
                else ""
            )
            self._model_list.addItem(f"{model_id} | {status} | {generation_modes or '-'}{active_suffix}")

    def _build_runtime_status_text(self) -> str:
        """
        @brief      Build the runtime status text.
        @return     Derived helper result.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.1.0
        """
        if self._probe_succeeded:
            return ui_state_service.translate("tts_settings.connected", self._current_language)
        if self._probe_message.strip():
            return ui_state_service.translate("tts_settings.connection_failed", self._current_language)
        return ui_state_service.translate("tts_settings.not_connected", self._current_language)

    def _apply_planning_state(self) -> None:
        """
        @brief      Apply the planning state.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-21
        @version    0.2.0
        """
        minimum_qwen_ready = bool(self._capability_matrix.get("minimum_qwen_ready", False))
        self._planning_group.setEnabled(True)
        if not self._probe_succeeded:
            self._planning_status_label.setText(
                ui_state_service.translate("tts_settings.plan_probe_required", self._current_language)
            )
            return
        if not minimum_qwen_ready:
            self._planning_status_label.setText(
                ui_state_service.translate("tts_settings.plan_missing_qwen", self._current_language).format(
                    missing_capabilities=", ".join(self._capability_matrix.get("missing_qwen_capabilities", [])),
                )
            )
            return
        self._planning_status_label.setText(
            ui_state_service.translate("tts_settings.plan_ready", self._current_language)
        )


# END OF FILE
