#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_settings_page.py
@brief AI settings page for AudioMancer.
@details Renders the operator-facing AI settings dialog and exposes load/build
         helpers so the main window can coordinate persistence through the
         settings service.
"""

# IMPORTS

import copy
from uuid import uuid4

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import ai_budget_service, chatgpt_catalog_service, ui_state_service

# CONSTANTS

# @brief Characters the model selector reserves room for before it starts eliding.
_MODEL_COMBO_MINIMUM_CONTENTS_LENGTH = 12

# @brief Hard width ceiling for the model selector, so one long model id cannot widen the dialog.
# @details Kept above the width the reserved character count implies, so the ceiling never
#          contradicts the control's own minimum size hint.
_MODEL_COMBO_MAX_WIDTH_PX = 420

# @brief Default LLM profile scaffold used when the operator creates a new AI profile.
_DEFAULT_PROFILE_TEMPLATE = {
    "id": "",
    "label": "",
    "backend_kind": config.LLM_BACKEND_OPTIONS[0],
    "base_url": "",
    "api_key": "",
    "model_name": "",
    "context_window": config.DEFAULT_LLM_CONTEXT_WINDOW,
    "output_reserve_tokens": config.DEFAULT_LLM_OUTPUT_RESERVE_TOKENS,
    "request_timeout_seconds": config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
    "temperature": config.DEFAULT_LLM_TEMPERATURE,
    "supports_structured_output": False,
    "reasoning_mode": config.DEFAULT_LLM_REASONING_MODE,
    "enabled": True,
    "discovered_model_name": "",
    "discovered_model_names": [],
    "discovered_context_window": None,
    "server_context_window": None,
    "discovered_context_model_name": "",
    "discovery_succeeded": False,
    "discovery_message": "",
    "user_overrode_model_name": False,
    "user_overrode_context_window": False,
}


# PUBLIC API


class AiSettingsPage(QWidget):
    """
    @brief      Display and edit AI settings for AudioMancer.
    @exception  None
    """

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the AI settings page.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        """
        super().__init__(parent)
        self._profiles: list[dict[str, object]] = []
        self._loading_profile = False
        self._editor_profile_id: str | None = None
        self._current_language = config.DEFAULT_LANGUAGE
        self._discovered_model_options: dict[str, list[tuple[str, str]]] = {}
        self._suspend_override_tracking = False
        self._chatgpt_busy = False
        self._subscription_catalog = {"source": "builtin", "models": chatgpt_catalog_service.builtin_models()}

        layout = QVBoxLayout(self)
        self._title_label = QLabel("<h2>AI Settings</h2>")
        layout.addWidget(self._title_label)

        content = QWidget(self)
        content_row = QHBoxLayout(content)
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(12)
        self._content_scroll = QScrollArea(self)
        self._content_scroll.setWidgetResizable(True)
        self._content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content_scroll.setWidget(content)

        profile_column = QWidget(self)
        profile_column_layout = QVBoxLayout(profile_column)
        profile_column_layout.setContentsMargins(0, 0, 0, 0)

        self._profile_list = QListWidget(self)
        self._profile_list.currentRowChanged.connect(self._load_selected_profile_into_editor)
        self._profile_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        profile_column_layout.addWidget(self._profile_list)

        profile_button_row = QHBoxLayout()
        self._add_profile_button = QPushButton("Add Profile", self)
        self._remove_profile_button = QPushButton("Remove Profile", self)
        self._add_profile_button.clicked.connect(self._add_profile)
        self._remove_profile_button.clicked.connect(self._remove_selected_profile)
        profile_button_row.addWidget(self._add_profile_button)
        profile_button_row.addWidget(self._remove_profile_button)
        profile_button_row.addStretch(1)
        profile_column_layout.addLayout(profile_button_row)

        content_row.addWidget(profile_column, 6)
        self._defaults_form = QFormLayout()
        self._defaults_form.setContentsMargins(0, 0, 0, 0)
        self._defaults_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._defaults_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        profile_column_layout.addLayout(self._defaults_form)
        profile_column_layout.addStretch(1)

        editor_container = QWidget(self)
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        top_form_layout = QFormLayout()
        top_form_layout.setContentsMargins(0, 0, 0, 0)
        top_form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        top_form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        bottom_form_layout = QFormLayout()
        bottom_form_layout.setContentsMargins(0, 0, 0, 0)

        self._label_edit = QLineEdit(self)
        profile_name_row = QHBoxLayout()
        profile_name_row.addWidget(self._label_edit, 1)

        self._enabled_checkbox = QCheckBox("Profile enabled")

        self._backend_combo = QComboBox(self)
        self._backend_combo.addItems(config.LLM_BACKEND_OPTIONS)
        self._backend_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._backend_combo.setMinimumContentsLength(8)
        backend_row = QHBoxLayout()
        backend_row.addWidget(self._backend_combo, 1)

        self._connect_button = QPushButton("Connect", self)
        self._connect_button.setMinimumWidth(112)
        backend_row.addWidget(self._connect_button)

        self._base_url_edit = QLineEdit(self)

        self._api_key_edit = QLineEdit(self)
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText("optional-for-local-provider")

        self._model_combo = QComboBox(self)
        self._model_combo.setEditable(True)
        # Model identifiers can be very long. Left at the default policy the combo demands room
        # for its longest entry, which stretches the whole settings form on the X axis depending
        # on what the endpoint happens to serve. The popup list still shows full names.
        self._model_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._model_combo.setMinimumContentsLength(_MODEL_COMBO_MINIMUM_CONTENTS_LENGTH)
        self._model_combo.setMaximumWidth(_MODEL_COMBO_MAX_WIDTH_PX)
        # An editable combo only opens its list from the small arrow, so clicking the field
        # looks like the discovered models are missing. Clicking the text opens the list too.
        self._model_combo.lineEdit().installEventFilter(self)
        self._model_combo.addItems(
            (
                "qwen3-8b",
                "qwen2.5-7b-instruct",
                "llama-3.1-8b-instruct",
            )
        )

        self._context_window_spin = QSpinBox(self)
        self._context_window_spin.setRange(1, config.MAX_LLM_CONTEXT_WINDOW)

        self._temperature_spin = QDoubleSpinBox(self)
        self._temperature_spin.setRange(0.0, 2.0)
        self._temperature_spin.setDecimals(2)
        self._temperature_spin.setSingleStep(0.05)

        self._reasoning_mode_combo = QComboBox(self)

        self._profile_name_label = QLabel("Profile Name", self)
        self._backend_kind_label = QLabel("Backend Kind", self)
        self._base_url_label = QLabel("Base URL", self)
        self._api_key_label = QLabel("API Key", self)
        self._model_name_label = QLabel("Model Name", self)
        self._context_window_label = QLabel("Context Window", self)
        self._temperature_label = QLabel("Temperature", self)
        self._reasoning_mode_label = QLabel("Reasoning Level", self)

        model_name_row = QHBoxLayout()
        model_name_row.addWidget(self._model_combo, 1)
        self._chatgpt_refresh_button = QPushButton(self)
        model_name_row.addWidget(self._chatgpt_refresh_button)
        flags_row = QHBoxLayout()
        flags_row.addWidget(self._enabled_checkbox)
        flags_row.addStretch(1)

        numeric_settings_grid = QGridLayout()
        numeric_settings_grid.setContentsMargins(0, 0, 0, 0)
        numeric_settings_grid.setHorizontalSpacing(12)
        numeric_settings_grid.setVerticalSpacing(6)
        numeric_settings_grid.addWidget(self._context_window_label, 0, 0)
        numeric_settings_grid.addWidget(self._context_window_spin, 0, 1)
        numeric_settings_grid.addWidget(self._temperature_label, 1, 0)
        numeric_settings_grid.addWidget(self._temperature_spin, 1, 1)
        numeric_settings_grid.setColumnStretch(1, 1)

        top_form_layout.addRow(self._profile_name_label, profile_name_row)
        top_form_layout.addRow(self._backend_kind_label, backend_row)
        top_form_layout.addRow(self._base_url_label, self._base_url_edit)
        top_form_layout.addRow(self._api_key_label, self._api_key_edit)
        top_form_layout.addRow(self._model_name_label, model_name_row)
        top_form_layout.addRow(flags_row)
        bottom_form_layout.addRow(numeric_settings_grid)
        bottom_form_layout.addRow(self._reasoning_mode_label, self._reasoning_mode_combo)

        self._default_cleanup_combo = QComboBox(self)
        self._default_chunking_combo = QComboBox(self)
        self._default_strategy_combo = QComboBox(self)
        for strategy in config.AI_CHUNKING_STRATEGY_OPTIONS:
            self._default_strategy_combo.addItem(strategy.title(), strategy)
        self._default_context_mode_combo = QComboBox(self)
        self._reload_context_mode_combo(config.DEFAULT_LANGUAGE)

        self._default_translation_combo = QComboBox(self)
        self._default_book_analysis_combo = QComboBox(self)
        self._default_narrator_generation_combo = QComboBox(self)
        self._default_character_combo = QComboBox(self)
        self._default_speech_blocks_combo = QComboBox(self)

        self._default_cleanup_label = QLabel("Default Cleanup Profile", self)
        self._default_chunking_label = QLabel("Default Chunking Profile", self)
        self._default_strategy_label = QLabel("Default AI Chunking Strategy", self)
        self._default_context_mode_label = QLabel("Chunking Context Mode", self)
        self._default_translation_label = QLabel("Default Translation Profile", self)
        self._default_book_analysis_label = QLabel("Default Book Analysis Profile", self)
        self._default_narrator_generation_label = QLabel("Default Narrator Generation Profile", self)
        self._default_character_label = QLabel(
            "Default Character Extraction Profile",
            self,
        )
        self._default_speech_blocks_label = QLabel("Default Speech Blocks Profile", self)

        self._defaults_form.addRow(self._default_cleanup_label, self._default_cleanup_combo)
        self._defaults_form.addRow(self._default_chunking_label, self._default_chunking_combo)
        self._defaults_form.addRow(self._default_strategy_label, self._default_strategy_combo)
        self._defaults_form.addRow(self._default_context_mode_label, self._default_context_mode_combo)
        self._defaults_form.addRow(
            self._default_book_analysis_label,
            self._default_book_analysis_combo,
        )
        self._defaults_form.addRow(self._default_translation_label, self._default_translation_combo)
        self._defaults_form.addRow(self._default_narrator_generation_label, self._default_narrator_generation_combo)
        self._defaults_form.addRow(
            self._default_character_label,
            self._default_character_combo,
        )
        self._defaults_form.addRow(self._default_speech_blocks_label, self._default_speech_blocks_combo)
        for row in range(self._defaults_form.rowCount()):
            label = self._defaults_form.itemAt(row, QFormLayout.ItemRole.LabelRole).widget()
            label.setWordWrap(False)
            combo = self._defaults_form.itemAt(row, QFormLayout.ItemRole.FieldRole).widget()
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(10)
            combo.currentTextChanged.connect(combo.setToolTip)
        editor_layout.addLayout(top_form_layout)
        self._chatgpt_panel = QWidget(self)
        account_layout = QVBoxLayout(self._chatgpt_panel)
        account_layout.setContentsMargins(0, 0, 0, 0)
        self._chatgpt_status = QLabel(self)
        self._chatgpt_status.setWordWrap(True)
        self._chatgpt_status.setTextFormat(Qt.TextFormat.PlainText)
        self._chatgpt_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        account_layout.addWidget(self._chatgpt_status)
        self._chatgpt_session_only = QCheckBox(self)
        account_layout.addWidget(self._chatgpt_session_only)
        account_buttons = QGridLayout()
        self._chatgpt_browser_button = QPushButton(self)
        self._chatgpt_device_button = QPushButton(self)
        self._chatgpt_disconnect_button = QPushButton(self)
        self._chatgpt_cancel_button = QPushButton(self)
        for index, button in enumerate((self._chatgpt_browser_button, self._chatgpt_device_button,
                                        self._chatgpt_disconnect_button, self._chatgpt_cancel_button)):
            account_buttons.addWidget(button, index // 2, index % 2)
        account_buttons.setColumnStretch(0, 1)
        account_buttons.setColumnStretch(1, 1)
        account_button_row = QHBoxLayout()
        account_button_row.addLayout(account_buttons)
        account_button_row.addStretch(1)
        account_layout.addLayout(account_button_row)
        top_form_layout.addRow(self._chatgpt_panel)
        editor_layout.addLayout(bottom_form_layout)

        editor_layout.addStretch(1)
        content_row.addWidget(editor_container, 5)
        layout.addWidget(self._content_scroll, 1)

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

        self._profile_list.installEventFilter(self)
        self._content_scroll.viewport().installEventFilter(self)
        self._model_combo.currentTextChanged.connect(self._on_model_name_edited)
        self._base_url_edit.textChanged.connect(self._on_connection_edited)
        self._context_window_spin.valueChanged.connect(self._on_context_window_edited)
        self._backend_combo.currentTextChanged.connect(self._on_backend_changed)

        self.load_settings(
            {
                "llm_profiles": [],
                "default_ai_cleanup_profile_id": None,
                "default_ai_chunking_profile_id": None,
                "default_ai_translation_profile_id": None,
                "default_book_analysis_profile_id": None,
                "default_narrator_profile_generation_profile_id": None,
                "default_speech_blocks_profile_id": None,
                "default_ai_chunking_strategy": config.DEFAULT_AI_CHUNKING_STRATEGY,
                "default_ai_chunking_context_mode": config.DEFAULT_AI_CHUNKING_CONTEXT_MODE,
                "default_character_extraction_profile_id": None,
            }
        )

    def _refresh_layout_metrics(self) -> None:
        """@brief Size the compact list and equal footer actions from current font and style metrics."""
        row_height = max(self._profile_list.sizeHintForRow(0), self._profile_list.fontMetrics().height() + 8)
        self._profile_list.setFixedHeight(5 * row_height + 2 * self._profile_list.frameWidth())
        fields = [self._defaults_form.itemAt(row, QFormLayout.ItemRole.FieldRole).widget()
                  for row in range(self._defaults_form.rowCount())]
        field_width = max(field.sizeHint().width() for field in fields)
        for field in fields:
            field.setFixedWidth(field_width)
        self._profile_list.parentWidget().setFixedWidth(self._defaults_form.minimumSize().width())
        action_groups = (
            (self._cancel_button, self._save_button, self._ok_button),
            (self._add_profile_button, self._remove_profile_button),
            (self._chatgpt_browser_button, self._chatgpt_device_button,
             self._chatgpt_disconnect_button, self._chatgpt_cancel_button),
        )
        for actions in action_groups:
            width = max(button.sizeHint().width() for button in actions)
            for button in actions:
                button.setFixedWidth(width)
        self._adapt_content_columns()

    def _adapt_content_columns(self) -> None:
        """@brief Stack settings sections when both natural column widths exceed the viewport."""
        content_row = self._content_scroll.widget().layout()
        left = self._profile_list.parentWidget()
        right = self._label_edit.parentWidget()
        required_width = left.width() + right.minimumSizeHint().width() + content_row.spacing()
        direction = (QBoxLayout.Direction.LeftToRight
                     if self._content_scroll.viewport().width() >= required_width
                     else QBoxLayout.Direction.TopToBottom)
        if content_row.direction() != direction:
            content_row.setDirection(direction)
        content_row.setStretch(0, 0)
        content_row.setStretch(1, 1 if direction == QBoxLayout.Direction.LeftToRight else 0)

    def changeEvent(self, event) -> None:
        """@brief Recompute font-derived geometry after inherited UI font or style changes."""
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            QTimer.singleShot(0, self, self._refresh_layout_metrics)

    def load_settings(self, settings_payload: dict[str, object]) -> None:
        """
        @brief      Load one persisted settings payload into the page widgets.
        @param[in]  settings_payload Combined application settings payload.
        @return     None.
        @exception  None
        """
        source_profiles = settings_payload.get("llm_profiles", [])
        if not isinstance(source_profiles, list):
            source_profiles = []

        self._editor_profile_id = None
        self._discovered_model_options = {}
        self._profiles = []
        for profile in source_profiles:
            if isinstance(profile, dict):
                normalized_profile = copy.deepcopy(_DEFAULT_PROFILE_TEMPLATE)
                normalized_profile.update(profile)
                if not normalized_profile["id"]:
                    normalized_profile["id"] = self._generate_profile_id()
                self._profiles.append(normalized_profile)

        if not self._profiles:
            self._profiles = [self._create_default_profile("AI Profile 1")]

        self._reload_profile_list()
        self._reload_default_profile_combos()
        self._set_optional_combo(
            self._default_cleanup_combo,
            settings_payload.get("default_ai_cleanup_profile_id"),
        )
        self._set_optional_combo(
            self._default_chunking_combo,
            settings_payload.get("default_ai_chunking_profile_id"),
        )
        self._set_optional_combo(
            self._default_translation_combo,
            settings_payload.get("default_ai_translation_profile_id"),
        )
        self._set_optional_combo(
            self._default_book_analysis_combo,
            settings_payload.get("default_book_analysis_profile_id"),
        )
        self._set_optional_combo(
            self._default_narrator_generation_combo,
            settings_payload.get("default_narrator_profile_generation_profile_id"),
        )
        self._set_optional_combo(
            self._default_speech_blocks_combo,
            settings_payload.get("default_speech_blocks_profile_id"),
        )
        self._set_optional_combo(
            self._default_strategy_combo,
            settings_payload.get("default_ai_chunking_strategy"),
        )
        self._set_optional_combo(
            self._default_context_mode_combo,
            settings_payload.get("default_ai_chunking_context_mode", config.DEFAULT_AI_CHUNKING_CONTEXT_MODE),
        )
        self._set_optional_combo(
            self._default_character_combo,
            settings_payload.get("default_character_extraction_profile_id"),
        )
        self._profile_list.setCurrentRow(0)
        self._load_profile_into_editor(self._profiles[0])
        self.apply_language(str(settings_payload.get("language", config.DEFAULT_LANGUAGE)))

    def build_settings(
        self,
        existing_settings_payload: dict[str, object],
    ) -> dict[str, object]:
        """
        @brief      Merge the page-owned fields into one settings payload.
        @param[in]  existing_settings_payload Existing application settings.
        @return     Merged settings payload containing AI settings changes.
        @exception  None
        """
        self._sync_editor_to_owner_profile()
        merged_settings = copy.deepcopy(existing_settings_payload)
        merged_settings["llm_profiles"] = [copy.deepcopy(profile) for profile in self._profiles]
        merged_settings["default_ai_cleanup_profile_id"] = self._optional_combo_value(self._default_cleanup_combo)
        merged_settings["default_ai_chunking_profile_id"] = self._optional_combo_value(self._default_chunking_combo)
        merged_settings["default_ai_translation_profile_id"] = self._optional_combo_value(
            self._default_translation_combo
        )
        merged_settings["default_book_analysis_profile_id"] = self._optional_combo_value(
            self._default_book_analysis_combo
        )
        merged_settings["default_narrator_profile_generation_profile_id"] = self._optional_combo_value(
            self._default_narrator_generation_combo
        )
        merged_settings["default_speech_blocks_profile_id"] = self._optional_combo_value(
            self._default_speech_blocks_combo
        )
        merged_settings["default_ai_chunking_strategy"] = (
            self._optional_combo_value(self._default_strategy_combo) or config.DEFAULT_AI_CHUNKING_STRATEGY
        )
        merged_settings["default_ai_chunking_context_mode"] = (
            self._optional_combo_value(self._default_context_mode_combo) or config.DEFAULT_AI_CHUNKING_CONTEXT_MODE
        )
        merged_settings["default_character_extraction_profile_id"] = self._optional_combo_value(
            self._default_character_combo
        )
        return merged_settings

    def build_current_profile_payload(self) -> dict[str, object] | None:
        """
        @brief      Build one payload snapshot from the selected profile editor.
        @return     Copy of the selected profile payload or None.
        @exception  None
        """
        self._sync_editor_to_owner_profile()
        current_profile = self._current_profile()
        if current_profile is None:
            return None
        return copy.deepcopy(current_profile)

    def apply_probe_result(self, probe_result: dict[str, object]) -> None:
        """
        @brief      Apply one backend probe result to the selected profile.
        @param[in]  probe_result Normalized backend probe result payload.
        @return     None.
        @exception  None
        """
        current_profile = self._current_profile()
        if current_profile is None:
            return

        probe_succeeded = bool(probe_result.get("success", False))
        current_profile["discovery_succeeded"] = probe_succeeded
        current_profile["discovery_message"] = str(probe_result.get("message", ""))
        if current_profile.get("backend_kind") == config.CHATGPT_BACKEND_KIND:
            current_profile["supports_structured_output"] = bool(probe_result.get("supports_structured_output", False))
        if not probe_succeeded:
            return

        model_options = [
            (str(model.get("id", "")), str(model.get("label", "")))
            for model in probe_result.get("discovered_models", [])
            if isinstance(model, dict) and str(model.get("id", "")).strip()
        ]
        self._discovered_model_options[str(current_profile["id"])] = model_options
        # Persist the discovered ids so the selector still offers real models on the next launch
        # instead of falling back to placeholder names the endpoint may not serve at all.
        current_profile["discovered_model_names"] = [model_id for model_id, _label in model_options]

        if model_options:
            selected_model_name = str(current_profile.get("model_name", "")).strip()
            if not bool(current_profile.get("user_overrode_model_name", False)) and not bool(
                probe_result.get("selected_model_valid", False)
            ):
                selected_model_name = model_options[0][0]
                current_profile["model_name"] = selected_model_name
            if bool(probe_result.get("selected_model_valid", False)) and selected_model_name:
                current_profile["discovered_model_name"] = selected_model_name
            else:
                current_profile["discovered_model_name"] = model_options[0][0]
        else:
            current_profile["discovered_model_name"] = ""

        effective_model_name = str(current_profile.get("model_name") or "").strip()
        owner = str(probe_result.get("discovered_context_model_name") or "").strip()
        for field in ("discovered_context_window", "server_context_window"):
            value = probe_result.get(field)
            current_profile[field] = (
                value
                if owner and owner == effective_model_name and type(value) is int
                and 0 < value <= config.MAX_LLM_CONTEXT_WINDOW
                else None
            )
        model_limit = current_profile["discovered_context_window"]
        server_limit = current_profile["server_context_window"]
        current_profile["discovered_context_model_name"] = owner if model_limit or server_limit else ""
        local_backend = current_profile["backend_kind"] in {"lmstudio", "ollama"}
        detected_context = server_limit if local_backend else model_limit
        if detected_context and not current_profile.get("user_overrode_context_window"):
            current_profile["context_window"] = detected_context

        if current_profile["backend_kind"] != config.CHATGPT_BACKEND_KIND:
            current_profile["supports_structured_output"] = True
        if local_backend:
            self._apply_local_reasoning(current_profile, probe_result.get("reasoning"))

        self._load_profile_into_editor(current_profile)

    @staticmethod
    def _apply_local_reasoning(profile: dict[str, object], metadata: object) -> None:
        """@brief Keep the model's reported levels and resolve the selected effort."""
        metadata = metadata if isinstance(metadata, dict) else {}
        allowed = metadata.get("allowed_options")
        supported = {"off", "on", "none", "minimal", "low", "medium", "high", "xhigh"}
        if profile["backend_kind"] == "ollama":
            supported.update({"max", "ultra"})
        levels = list(dict.fromkeys(
            level for level in allowed if isinstance(level, str) and level in supported
        )) if isinstance(allowed, list) else []
        if "on" in levels and any(level not in {"off", "none", "on"} for level in levels):
            levels.remove("on")
        profile["discovered_reasoning_levels"] = levels
        if not levels:
            profile.pop("reasoning_effort", None)
            return
        selected = profile.get("reasoning_effort") or {
            "disabled": "off" if "off" in levels else "none",
            "enabled": "on" if "on" in levels else "medium",
        }.get(profile.get("reasoning_mode"))
        if selected not in levels:
            default = metadata.get("default")
            selected = default if default in levels else levels[0]
        profile["reasoning_effort"] = selected
        profile["reasoning_mode"] = "disabled" if selected in {"off", "none"} else "enabled"

    def apply_subscription_catalog(self, result: dict) -> None:
        """@brief Replace account model hints while preserving every unsaved profile/editor choice."""
        self._sync_editor_to_owner_profile()
        self._subscription_catalog = copy.deepcopy(result)
        current = self._current_profile()
        if current is not None and current.get("backend_kind") == config.CHATGPT_BACKEND_KIND:
            self._load_model_options_for_profile(current)
            self._reload_reasoning_mode_combo(self._current_language, chatgpt_catalog_service.requested_effort(current))
            self._apply_subscription_context()
        self._update_catalog_status()

    def _update_catalog_status(self) -> None:
        """@brief Distinguish live, cached and candidate metadata without implying inference verification."""
        source = self._subscription_catalog.get("source", "builtin")
        self._chatgpt_refresh_button.setToolTip(
            ui_state_service.translate("ai_settings.catalog_" + source, self._current_language)
        )

    def set_subscription_status(self, text: str, *, visible: bool = True) -> None:
        """@brief Reserve status rows for active progress or errors, keeping idle details in tooltips."""
        self._chatgpt_status.setText(text)
        self._chatgpt_status.setVisible(visible and bool(text))
        self._chatgpt_browser_button.setToolTip(text)

    # LOCAL HELPERS

    def _create_default_profile(self, label: str) -> dict[str, object]:
        """
        @brief      Build a new default AI profile payload for the editor.
        @param[in]  label Initial operator-facing profile label.
        @return     Default profile payload ready for insertion.
        @exception  None
        """
        profile = copy.deepcopy(_DEFAULT_PROFILE_TEMPLATE)
        profile["id"] = self._generate_profile_id()
        profile["label"] = label
        profile["backend_kind"] = config.LLM_BACKEND_OPTIONS[0]
        profile["base_url"] = "http://127.0.0.1:1234/v1"
        profile["model_name"] = "qwen3-8b"
        return profile

    def _generate_profile_id(self) -> str:
        """
        @brief      Generate one stable-looking unique profile identifier.
        @return     Generated profile identifier string.
        @exception  None
        """
        return f"llm_profile_{uuid4().hex[:12]}"

    def _load_model_options_for_profile(self, profile: dict[str, object]) -> None:
        """
        @brief      Reload the model selector choices for one profile.
        @details    Prefers models discovered in this session, then the ones persisted by the
                    last successful probe. The built-in names are only a last resort for a
                    profile that has never been probed, because they are guesses that a given
                    endpoint may not serve.
        @param[in]  profile Target profile payload.
        @return     None.
        @exception  None
        """
        selected_model_name = str(profile.get("model_name", "")).strip()
        discovered_options = self._discovered_model_options.get(str(profile["id"]), [])
        if profile.get("backend_kind") == config.CHATGPT_BACKEND_KIND:
            # Candidate labels stay separate from the actual model identifier.
            discovered_options = [(model["id"], model["id"]) for model in self._subscription_catalog["models"]]
        if not discovered_options:
            discovered_options = [
                (str(model_name).strip(), str(model_name).strip())
                for model_name in profile.get("discovered_model_names", [])
                if str(model_name).strip()
            ]
        self._suspend_override_tracking = True
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        if discovered_options:
            for model_id, label in discovered_options:
                self._model_combo.addItem(label, model_id)
        else:
            self._model_combo.addItems(
                (
                    "qwen3-8b",
                    "qwen2.5-7b-instruct",
                    "llama-3.1-8b-instruct",
                )
            )
        self._model_combo.setCurrentText(selected_model_name)
        self._model_combo.blockSignals(False)
        self._suspend_override_tracking = False

    def _reload_profile_list(self) -> None:
        """
        @brief      Rebuild the profile-list widget from the in-memory payload.
        @return     None.
        @exception  None
        """
        current_profile_id = self._current_profile_id()
        scroll_position = self._profile_list.verticalScrollBar().value()
        self._profile_list.blockSignals(True)
        self._profile_list.clear()
        current_row = 0
        for index, profile in enumerate(self._profiles):
            item = QListWidgetItem(str(profile["label"]) or f"AI Profile {index + 1}")
            item.setData(Qt.ItemDataRole.UserRole, profile["id"])
            self._profile_list.addItem(item)
            if profile["id"] == current_profile_id:
                current_row = index
        if self._profiles:
            self._profile_list.setCurrentRow(current_row)
            self._profile_list.doItemsLayout()
            self._profile_list.verticalScrollBar().setValue(scroll_position)
            self._profile_list.scrollToItem(self._profile_list.currentItem())
        self._profile_list.blockSignals(False)

    def _reload_default_profile_combos(self) -> None:
        """
        @brief      Rebuild the default-profile selectors from enabled profiles.
        @return     None.
        @exception  None
        """
        current_cleanup = self._optional_combo_value(self._default_cleanup_combo)
        current_chunking = self._optional_combo_value(self._default_chunking_combo)
        current_translation = self._optional_combo_value(self._default_translation_combo)
        current_book_analysis = self._optional_combo_value(self._default_book_analysis_combo)
        current_narrator_generation = self._optional_combo_value(self._default_narrator_generation_combo)
        current_speech_blocks = self._optional_combo_value(self._default_speech_blocks_combo)
        current_character = self._optional_combo_value(self._default_character_combo)

        for combo in (
            self._default_cleanup_combo,
            self._default_chunking_combo,
            self._default_translation_combo,
            self._default_book_analysis_combo,
            self._default_narrator_generation_combo,
            self._default_speech_blocks_combo,
            self._default_character_combo,
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(none)", None)
            for profile in self._profiles:
                if bool(profile.get("enabled", True)):
                    combo.addItem(str(profile["label"]), profile["id"])
            combo.blockSignals(False)

        self._set_optional_combo(self._default_cleanup_combo, current_cleanup)
        self._set_optional_combo(self._default_chunking_combo, current_chunking)
        self._set_optional_combo(self._default_translation_combo, current_translation)
        self._set_optional_combo(self._default_book_analysis_combo, current_book_analysis)
        self._set_optional_combo(self._default_narrator_generation_combo, current_narrator_generation)
        self._set_optional_combo(self._default_speech_blocks_combo, current_speech_blocks)
        self._set_optional_combo(self._default_character_combo, current_character)

    def _load_selected_profile_into_editor(self, row: int) -> None:
        """
        @brief      Load the selected list-row profile into the editor widgets.
        @param[in]  row Selected profile-list row index.
        @return     None.
        @exception  None
        """
        if self._loading_profile:
            return
        if row < 0 or row >= len(self._profiles):
            return
        self._sync_editor_to_owner_profile()
        self._load_profile_into_editor(self._profiles[row])

    def _load_profile_into_editor(self, profile: dict[str, object]) -> None:
        """
        @brief      Populate the editor widgets from one profile payload.
        @param[in]  profile Source profile payload.
        @return     None.
        @exception  None
        """
        self._loading_profile = True
        self._editor_profile_id = str(profile["id"])
        self._load_model_options_for_profile(profile)
        self._label_edit.setText(str(profile["label"]))
        self._enabled_checkbox.setChecked(bool(profile["enabled"]))
        self._backend_combo.setCurrentText(str(profile["backend_kind"]))
        self._editor_backend_kind = str(profile["backend_kind"])
        self._base_url_edit.setText(str(profile["base_url"]))
        self._api_key_edit.setText(str(profile["api_key"]))
        self._model_combo.setCurrentText(str(profile["model_name"]))
        self._refresh_context_limit()
        self._context_window_spin.setValue(int(profile["context_window"]))
        self._temperature_spin.setValue(float(profile["temperature"]))
        selected_reasoning = (
            chatgpt_catalog_service.requested_effort(profile)
            if profile["backend_kind"] == config.CHATGPT_BACKEND_KIND
            else profile.get("reasoning_effort")
        )
        self._reload_reasoning_mode_combo(self._current_language, selected_reasoning)
        self._loading_profile = False
        self._apply_subscription_context()
        self._update_subscription_controls()
        self.set_subscription_status("", visible=False)

    def _sync_editor_to_owner_profile(self) -> None:
        """
        @brief      Copy the editor state back into the stable profile that owns it.
        @return     None.
        @exception  None
        """
        owner_profile = self._editor_profile()
        if owner_profile is None or self._loading_profile:
            return
        owner_profile["label"] = self._label_edit.text().strip() or "Unnamed Profile"
        owner_profile["enabled"] = self._enabled_checkbox.isChecked()
        backend, base_url, model_name = self._editor_connection()
        previous_backend, previous_url, previous_model = self._profile_connection(owner_profile)
        if backend != config.CHATGPT_BACKEND_KIND and (backend, base_url) != (previous_backend, previous_url):
            owner_profile.update(discovered_context_window=None, discovered_context_model_name="")
        if (backend, base_url, model_name) != (previous_backend, previous_url, previous_model):
            owner_profile["server_context_window"] = None
            owner_profile.pop("discovered_reasoning_levels", None)
            if backend != config.CHATGPT_BACKEND_KIND:
                owner_profile.pop("reasoning_effort", None)
                owner_profile["reasoning_mode"] = config.DEFAULT_LLM_REASONING_MODE
        owner_profile["backend_kind"] = backend
        owner_profile["base_url"] = base_url
        owner_profile["api_key"] = self._api_key_edit.text()
        owner_profile["model_name"] = model_name
        if owner_profile["backend_kind"] == config.CHATGPT_BACKEND_KIND:
            owner_profile["base_url"] = config.CHATGPT_BASE_URL
            owner_profile["api_key"] = ""
            owner_profile["credential_ref"] = config.CHATGPT_CREDENTIAL_REF
        owner_profile["context_window"] = self._context_window_spin.value()
        owner_profile["temperature"] = self._temperature_spin.value()
        effort = self._optional_combo_value(self._reasoning_mode_combo)
        if backend == config.CHATGPT_BACKEND_KIND:
            owner_profile["reasoning_effort"] = effort or config.DEFAULT_LLM_REASONING_MODE
            owner_profile["reasoning_mode"] = chatgpt_catalog_service.reasoning_mode(owner_profile["reasoning_effort"])
        else:
            levels = owner_profile.get("discovered_reasoning_levels")
            if isinstance(levels, list) and effort is not None and effort in levels:
                owner_profile["reasoning_effort"] = effort
                owner_profile["reasoning_mode"] = "disabled" if effort in {"off", "none"} else "enabled"
        self._reload_profile_list()
        self._reload_default_profile_combos()

    def _on_model_name_edited(self, _value: str) -> None:
        """
        @brief      Mark the selected model name as manually overridden.
        @param[in]  _value Ignored current model text.
        @return     None.
        @exception  None
        """
        if self._loading_profile or self._suspend_override_tracking:
            return
        owner_profile = self._editor_profile()
        if owner_profile is not None:
            owner_profile["user_overrode_model_name"] = True
            if self._backend_combo.currentText() == config.CHATGPT_BACKEND_KIND:
                self._apply_subscription_context(reset_override=True)
                self._reload_reasoning_mode_combo(self._current_language)
                owner_profile["supports_structured_output"] = False
                self.set_subscription_status("", visible=False)
        self._on_connection_edited()

    def _on_connection_edited(self, _value: str = "") -> None:
        """@brief Refresh bounds and local options for the edited connection."""
        if self._loading_profile:
            return
        self._refresh_context_limit()
        if self._backend_combo.currentText() != config.CHATGPT_BACKEND_KIND:
            self._reload_reasoning_mode_combo(self._current_language)

    def _on_backend_changed(self, _value: str) -> None:
        """@brief Refresh subscription-specific controls and defaults on an explicit backend change."""
        if self._loading_profile:
            return
        owner_profile = self._editor_profile()
        if self._editor_backend_kind == config.CHATGPT_BACKEND_KIND and owner_profile is not None:
            owner_profile["reasoning_effort"] = self._optional_combo_value(self._reasoning_mode_combo)
        self._editor_backend_kind = self._backend_combo.currentText()
        subscription = self._backend_combo.currentText() == config.CHATGPT_BACKEND_KIND
        if subscription:
            selected = self._model_combo.currentText()
            self._model_combo.blockSignals(True)
            self._model_combo.clear()
            self._model_combo.addItems([model["id"] for model in self._subscription_catalog["models"]])
            self._model_combo.setCurrentText(selected)
            self._model_combo.blockSignals(False)
            if owner_profile is not None:
                owner_profile["supports_structured_output"] = False
        selected_effort = (
            owner_profile.get("reasoning_effort", "provider_default")
            if subscription and owner_profile and owner_profile["backend_kind"] == config.CHATGPT_BACKEND_KIND
            else "provider_default"
        )
        self._reload_reasoning_mode_combo(self._current_language, selected_effort)
        if subscription:
            self._apply_subscription_context(reset_override=True)
        self._update_subscription_controls()

    def _apply_subscription_context(self, *, reset_override: bool = False) -> None:
        """@brief Apply model default context while retaining manual edits until the model changes."""
        if self._backend_combo.currentText() != config.CHATGPT_BACKEND_KIND:
            return
        profile = self._editor_profile()
        if profile is None:
            return
        if reset_override:
            profile["user_overrode_context_window"] = False
        model_name = self._model_combo.currentText().strip()
        model = next((item for item in self._subscription_catalog["models"] if item["id"] == model_name), {})
        context = model.get("context_window")
        if type(context) is not int or not 0 < context <= 2_147_483_647:
            profile["discovered_context_window"] = None
            profile["discovered_context_model_name"] = ""
            return
        profile["discovered_context_window"] = context
        profile["discovered_context_model_name"] = model_name
        if profile.get("user_overrode_context_window", False):
            return
        self._context_window_spin.blockSignals(True)
        self._context_window_spin.setValue(context)
        self._context_window_spin.blockSignals(False)
        profile["context_window"] = context

    def _update_subscription_controls(self) -> None:
        """@brief Show account controls and disable fields the subscription transport does not use."""
        subscription = self._backend_combo.currentText() == config.CHATGPT_BACKEND_KIND
        self._chatgpt_panel.setVisible(subscription)
        self._chatgpt_refresh_button.setVisible(subscription)
        self._chatgpt_refresh_button.setEnabled(not self._chatgpt_busy)
        self._api_key_label.setVisible(not subscription)
        self._api_key_edit.setVisible(not subscription)
        self._base_url_edit.setReadOnly(subscription)
        self._temperature_spin.setEnabled(not subscription)
        if subscription:
            self._base_url_edit.setText(config.CHATGPT_BASE_URL)
            self._api_key_edit.clear()
        self._refresh_context_limit()
        self._connect_button.setText(ui_state_service.translate(
            "ai_settings.chatgpt_test" if subscription else "ai_settings.connect", self._current_language))
        self._connect_button.setEnabled(not (subscription and self._chatgpt_busy))
        self._chatgpt_browser_button.setEnabled(not self._chatgpt_busy)
        self._chatgpt_device_button.setEnabled(not self._chatgpt_busy)
        self._chatgpt_session_only.setEnabled(not self._chatgpt_busy)
        self._chatgpt_cancel_button.setEnabled(self._chatgpt_busy)

    def set_subscription_busy(self, busy: bool) -> None:
        """@brief Update account worker controls without blocking other profile editing."""
        self._chatgpt_busy = busy
        self._update_subscription_controls()

    def _on_context_window_edited(self, _value: int) -> None:
        """
        @brief      Mark the selected context window as manually overridden.
        @param[in]  _value Ignored current numeric value.
        @return     None.
        @exception  None
        """
        if self._loading_profile or self._suspend_override_tracking:
            return
        owner_profile = self._editor_profile()
        if owner_profile is not None:
            owner_profile["user_overrode_context_window"] = True

    def _editor_connection(self) -> tuple[str, str, str]:
        """@brief Return the current backend, endpoint and model from the editor."""
        return (
            self._backend_combo.currentText(),
            self._base_url_edit.text().strip(),
            self._model_combo.currentText().strip(),
        )

    @staticmethod
    def _profile_connection(profile: dict[str, object]) -> tuple[str, str, str]:
        """@brief Identify the connection that owns the profile's discovered limits."""
        return (str(profile["backend_kind"]), str(profile["base_url"]), str(profile["model_name"]))

    def _refresh_context_limit(self) -> None:
        """@brief Enforce the last reported limit for the current connection."""
        profile = self._editor_profile()
        limit = None
        if profile is not None and self._editor_connection() == self._profile_connection(profile):
            limit = ai_budget_service.context_window_limit(profile)
        blocked = self._context_window_spin.blockSignals(True)
        self._context_window_spin.setMaximum(limit or config.MAX_LLM_CONTEXT_WINDOW)
        self._context_window_spin.blockSignals(blocked)

    def _editor_profile(self) -> dict[str, object] | None:
        """
        @brief      Return the stable profile currently represented by the editor.
        @return     Editor-owner profile or `None`.
        @exception  None
        """
        if self._editor_profile_id is None:
            return None
        for profile in self._profiles:
            if str(profile.get("id", "")) == self._editor_profile_id:
                return profile
        return None

    def _current_profile(self) -> dict[str, object] | None:
        """
        @brief      Return the currently selected profile payload when available.
        @return     Selected profile payload or `None`.
        @exception  None
        """
        row = self._profile_list.currentRow()
        if row < 0 or row >= len(self._profiles):
            return None
        return self._profiles[row]

    def _current_profile_id(self) -> str | None:
        """
        @brief      Return the identifier of the selected profile-list item.
        @return     Selected profile identifier or `None`.
        @exception  None
        """
        current_item = self._profile_list.currentItem()
        if current_item is None:
            return None
        value = current_item.data(Qt.ItemDataRole.UserRole)
        return None if value in (None, "") else str(value)

    def _set_optional_combo(self, combo: QComboBox, value: object) -> None:
        """
        @brief      Select one optional combo-box value with fallback to `(none)`.
        @param[in]  combo Target combo box.
        @param[in]  value Desired stored value.
        @return     None.
        @exception  None
        """
        index = combo.findData(value)
        combo.setCurrentIndex(0 if index < 0 else index)

    def _optional_combo_value(self, combo: QComboBox) -> str | None:
        """
        @brief      Read one optional combo-box value normalized for persistence.
        @param[in]  combo Source combo box.
        @return     Selected string value or `None`.
        @exception  None
        """
        value = combo.currentData()
        return None if value in (None, "") else str(value)

    def _reload_context_mode_combo(self, language: str) -> None:
        """
        @brief      Rebuild the chunking context-mode selector labels for one language.
        @param[in]  language Active UI language.
        @return     None.
        @exception  None
        """
        current_mode = self._optional_combo_value(self._default_context_mode_combo)
        self._default_context_mode_combo.blockSignals(True)
        self._default_context_mode_combo.clear()
        self._default_context_mode_combo.addItem(
            ui_state_service.translate("ai_settings.context_mode_balanced", language),
            config.AI_CHUNKING_CONTEXT_MODE_BALANCED,
        )
        self._default_context_mode_combo.addItem(
            ui_state_service.translate("ai_settings.context_mode_wide_scene", language),
            config.AI_CHUNKING_CONTEXT_MODE_WIDE_SCENE,
        )
        self._default_context_mode_combo.addItem(
            ui_state_service.translate("ai_settings.context_mode_maximum", language),
            config.AI_CHUNKING_CONTEXT_MODE_MAXIMUM,
        )
        self._default_context_mode_combo.blockSignals(False)
        self._set_optional_combo(
            self._default_context_mode_combo,
            current_mode or config.DEFAULT_AI_CHUNKING_CONTEXT_MODE,
        )

    def _reload_reasoning_mode_combo(self, language: str, selected: str | None = None) -> None:
        """
        @brief      Rebuild reasoning-mode labels while preserving the stable value.
        @param[in]  language Active UI language code.
        @return     None.
        @exception  None
        """
        current_mode = selected if selected is not None else self._optional_combo_value(self._reasoning_mode_combo)
        subscription = self._backend_combo.currentText() == config.CHATGPT_BACKEND_KIND
        current_mode = current_mode or config.DEFAULT_LLM_REASONING_MODE
        self._reasoning_mode_combo.blockSignals(True)
        self._reasoning_mode_combo.clear()
        if subscription:
            self._reasoning_mode_combo.setVisible(True)
            self._reasoning_mode_label.setVisible(True)
            current_mode = {"enabled": "medium", "disabled": "none"}.get(current_mode, current_mode)
            model = next((item for item in self._subscription_catalog["models"]
                          if item["id"] == self._model_combo.currentText()), {})
            default = ui_state_service.translate("ai_settings.reasoning_mode.provider_default", language)
            if model.get("default_effort"):
                default += " (" + model["default_effort"] + ")"
            self._reasoning_mode_combo.addItem(default, "provider_default")
            for effort in model.get("efforts", []):
                self._reasoning_mode_combo.addItem(self._effort_label(effort, language), effort)
            if self._reasoning_mode_combo.findData(current_mode) < 0:
                label = self._effort_label(current_mode, language)
                unavailable = ui_state_service.translate("ai_settings.effort_unavailable", language)
                self._reasoning_mode_combo.addItem(f"{label} ({unavailable})", current_mode)
            self._reasoning_mode_combo.setCurrentIndex(self._reasoning_mode_combo.findData(current_mode))
            self._reasoning_mode_combo.blockSignals(False)
            if hasattr(self, "_reasoning_mode_label"):
                self._reasoning_mode_label.setText(ui_state_service.translate("ai_settings.reasoning_effort", language))
            return
        profile = self._editor_profile()
        levels = (
            profile.get("discovered_reasoning_levels", [])
            if profile is not None and self._editor_connection() == self._profile_connection(profile)
            and profile["backend_kind"] in {"lmstudio", "ollama"}
            else []
        )
        levels = [level for level in levels if isinstance(level, str)] if isinstance(levels, list) else []
        supports_reasoning = any(level not in {"off", "none"} for level in levels)
        self._reasoning_mode_combo.setVisible(supports_reasoning)
        self._reasoning_mode_label.setVisible(supports_reasoning)
        for effort in levels:
            self._reasoning_mode_combo.addItem(self._effort_label(effort, language), effort)
        self._set_optional_combo(self._reasoning_mode_combo, current_mode)
        self._reasoning_mode_combo.blockSignals(False)
        self._reasoning_mode_label.setText(ui_state_service.translate("ai_settings.reasoning_effort", language))

    def _effort_label(self, effort: str, language: str) -> str:
        """@brief Localize known effort names and display future provider identifiers verbatim."""
        label = {"off": "none"}.get(effort, effort)
        known = {"none", "on", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
        return ui_state_service.translate("ai_settings.effort_" + label, language) if label in known else effort

    def _add_profile(self) -> None:
        """
        @brief      Append one new editable profile to the in-memory list.
        @return     None.
        @exception  None
        """
        self._sync_editor_to_owner_profile()
        self._profiles.append(self._create_default_profile(f"AI Profile {len(self._profiles) + 1}"))
        self._reload_profile_list()
        self._reload_default_profile_combos()
        self._profile_list.setCurrentRow(len(self._profiles) - 1)

    def _remove_selected_profile(self) -> None:
        """
        @brief      Remove the selected profile and repair dependent selectors.
        @return     None.
        @exception  None
        """
        self._sync_editor_to_owner_profile()
        row = self._profile_list.currentRow()
        if row < 0 or len(self._profiles) <= 1:
            return
        removed_profile = self._profiles.pop(row)
        removed_profile_id = str(removed_profile["id"])
        for combo in (
            self._default_cleanup_combo,
            self._default_chunking_combo,
            self._default_translation_combo,
            self._default_narrator_generation_combo,
            self._default_speech_blocks_combo,
            self._default_character_combo,
        ):
            if self._optional_combo_value(combo) == removed_profile_id:
                combo.setCurrentIndex(0)
        self._reload_profile_list()
        self._reload_default_profile_combos()
        target_row = max(0, row - 1)
        self._profile_list.setCurrentRow(target_row)
        self._load_profile_into_editor(self._profiles[target_row])

    def eventFilter(self, watched: object, event: object) -> bool:
        """
        @brief      Open the model list when the operator clicks the editable model field.
        @details    An editable combo box normally only drops down from its arrow, so clicking
                    the field reads as "the discovered models are not there". The field stays
                    editable, so a model name that was never advertised can still be typed.
                    The popup opens on button release, and only once the current event has been
                    delivered: opening it during the press makes the popup grab the mouse, and
                    the release that follows immediately dismisses it again.
        @param[in]  watched Object receiving the event.
        @param[in]  event Event delivered to the object.
        @return     True when the event was handled locally.
        @exception  None
        """
        if (
            watched is self._model_combo.lineEdit()
            and event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
            and self._model_combo.isEnabled()
            and self._model_combo.count() > 0
            and not self._model_combo.view().isVisible()
        ):
            QTimer.singleShot(0, self, self._show_model_popup)
        if watched is self._profile_list and event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            QTimer.singleShot(0, self, self._refresh_layout_metrics)
        if watched is self._content_scroll.viewport() and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self, self._adapt_content_columns)
        return super().eventFilter(watched, event)

    def _show_model_popup(self) -> None:
        """
        @brief      Drop down the model list unless it is already open.
        @return     None.
        @exception  None
        """
        if self._model_combo.isEnabled() and not self._model_combo.view().isVisible():
            self._model_combo.showPopup()

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the AI settings page labels.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        """
        self._current_language = language
        self._title_label.setText(f"<h2>{ui_state_service.translate('ai_settings.title', language)}</h2>")
        self._profile_name_label.setText(ui_state_service.translate("ai_settings.profile_name", language))
        self._enabled_checkbox.setText(ui_state_service.translate("ai_settings.profile_enabled", language))
        self._backend_kind_label.setText(ui_state_service.translate("ai_settings.backend_kind", language))
        self._base_url_label.setText(ui_state_service.translate("ai_settings.base_url", language))
        self._api_key_label.setText(ui_state_service.translate("ai_settings.api_key", language))
        self._api_key_edit.setPlaceholderText(ui_state_service.translate("ai_settings.api_key_placeholder", language))
        self._model_name_label.setText(ui_state_service.translate("ai_settings.model_name", language))
        self._context_window_label.setText(ui_state_service.translate("ai_settings.context_window", language))
        self._temperature_label.setText(ui_state_service.translate("ai_settings.temperature", language))
        self._reload_reasoning_mode_combo(language)
        self._default_cleanup_label.setText(ui_state_service.translate("ai_settings.default_cleanup", language))
        self._default_chunking_label.setText(ui_state_service.translate("ai_settings.default_chunking", language))
        self._default_translation_label.setText(ui_state_service.translate("ai_settings.default_translation", language))
        self._default_book_analysis_label.setText(
            ui_state_service.translate("ai_settings.default_book_analysis", language)
        )
        self._default_narrator_generation_label.setText(
            ui_state_service.translate("ai_settings.default_narrator_generation", language)
        )
        self._default_speech_blocks_label.setText(
            ui_state_service.translate("ai_settings.default_speech_blocks", language)
        )
        self._default_strategy_label.setText(ui_state_service.translate("ai_settings.default_strategy", language))
        for index in range(self._default_strategy_combo.count()):
            strategy = str(self._default_strategy_combo.itemData(index) or "")
            self._default_strategy_combo.setItemText(
                index,
                ui_state_service.translate(f"chunking.strategy.{strategy}", language),
            )
        self._default_context_mode_label.setText(
            ui_state_service.translate("ai_settings.default_context_mode", language)
        )
        self._reload_context_mode_combo(language)
        self._default_character_label.setText(ui_state_service.translate("ai_settings.default_character", language))
        self._add_profile_button.setText(ui_state_service.translate("ai_settings.add_profile", language))
        self._remove_profile_button.setText(ui_state_service.translate("ai_settings.remove_profile", language))
        self._connect_button.setText(ui_state_service.translate("ai_settings.connect", language))
        for widget, key in (
            (self._chatgpt_browser_button, "chatgpt_sign_in"),
            (self._chatgpt_device_button, "chatgpt_device"),
            (self._chatgpt_disconnect_button, "chatgpt_disconnect"),
            (self._chatgpt_cancel_button, "chatgpt_cancel"),
            (self._chatgpt_session_only, "chatgpt_session"),
        ):
            widget.setText(ui_state_service.translate("ai_settings." + key, language))
        self._chatgpt_session_only.setToolTip(ui_state_service.translate("ai_settings.chatgpt_session_hint", language))
        self._chatgpt_refresh_button.setText(ui_state_service.translate("ai_settings.refresh_models", language))
        self._update_catalog_status()
        self._update_subscription_controls()
        self._cancel_button.setText(ui_state_service.translate("ai_settings.cancel", language))
        self._save_button.setText(ui_state_service.translate("settings.apply", language))
        self._ok_button.setText(ui_state_service.translate("ai_settings.ok", language))
        self._refresh_layout_metrics()
        for combo in (
            self._default_cleanup_combo,
            self._default_chunking_combo,
            self._default_translation_combo,
            self._default_book_analysis_combo,
            self._default_narrator_generation_combo,
            self._default_speech_blocks_combo,
            self._default_character_combo,
        ):
            if combo.count() > 0:
                combo.setItemText(
                    0,
                    ui_state_service.translate("ai_settings.none", language),
                )


# END OF FILE
