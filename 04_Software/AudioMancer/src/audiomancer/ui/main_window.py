#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file main_window.py
@brief Main window shell copied from DDP_Audiomancer for AudioMancer.
@details Implements the sidebar-driven Qt shell while delegating page/window
         behavior to dedicated UI controllers and page-specific state services
         so the window remains a thin coordinator.
"""

# IMPORTS

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from audiomancer import config
from audiomancer.services import (
    ai_translation_state_service,
    audio_assembly_state_service,
    audio_blocks_state_service,
    character_discovery_state_service,
    character_voices_state_service,
    home_presenter_service,
    narrator_definition_state_service,
    operation_runtime_service,
    project_export_service,
    settings_service,
    speech_blocks_state_service,
    text_chunking_state_service,
    text_cleanup_state_service,
    ui_state_service,
)
from audiomancer.ui.controllers import (
    ai_settings_ui_controller,
    ai_translation_ui_controller,
    audio_assembly_ui_controller,
    audio_blocks_ui_controller,
    character_voices_ui_controller,
    characters_ui_controller,
    home_ui_controller,
    misc_ui_controller,
    narator_voice_ui_controller,
    operation_runner_controller,
    settings_ui_controller,
    speech_blocks_ui_controller,
    text_chunking_ui_controller,
    text_cleanup_ui_controller,
    tts_settings_ui_controller,
)
from audiomancer.ui.navigation_sidebar import NavigationSidebar
from audiomancer.ui.operation_progress_dialog import OperationProgressDialog
from audiomancer.ui.operation_status_dialog import OperationStatusDialog
from audiomancer.ui.pages.ai_settings_page import AiSettingsPage
from audiomancer.ui.pages.ai_translation_page import AiTranslationPage
from audiomancer.ui.pages.audio_assembly_page import AudioAssemblyPage
from audiomancer.ui.pages.audio_blocks_page import AudioBlocksPage
from audiomancer.ui.pages.character_voices_page import CharacterVoicesPage
from audiomancer.ui.pages.characters_page import CharactersPage
from audiomancer.ui.pages.home_page import HomeProjectPage
from audiomancer.ui.pages.narator_voice_page import NaratorVoicePage
from audiomancer.ui.pages.settings_page import SettingsPage
from audiomancer.ui.pages.speech_blocks_page import SpeechBlocksPage
from audiomancer.ui.pages.text_chunking_page import TextChunkingPage
from audiomancer.ui.pages.text_cleanup_page import TextCleanupPage
from audiomancer.ui.pages.tts_settings_page import TtsSettingsPage

# CONSTANTS

# @brief Default initial main-window width used at shell startup.
WINDOW_WIDTH = config.DEFAULT_MAIN_WINDOW_WIDTH
# @brief Default initial main-window height used at shell startup.
WINDOW_HEIGHT = config.DEFAULT_MAIN_WINDOW_HEIGHT
# @brief Minimum allowed main-window width.
WINDOW_MIN_WIDTH = config.DEFAULT_MAIN_WINDOW_MIN_WIDTH
# @brief Minimum allowed main-window height.
WINDOW_MIN_HEIGHT = config.DEFAULT_MAIN_WINDOW_MIN_HEIGHT

# @brief Page-to-operation-state mapping initialized only when a workflow page is opened.
_PAGE_OPERATION_STATE_KINDS = {
    "text_cleanup": ("extraction",),
    "text_chunking": ("chunking",),
    "ai_translation": ("translation",),
    "characters": ("character_discovery",),
    "speech_blocks": ("speech_blocks",),
    "audio_blocks": ("audio_blocks",),
    "audio_assembly": ("audio_assembly",),
}


# PUBLIC API


class MainWindow(QMainWindow):
    """
    @brief      Render the sidebar-driven AudioMancer desktop shell.
    @details    Owns the visible Qt shell and delegates page/window behavior to
                dedicated UI controllers plus page-specific state services.
    @return     None.
    @exception  None
    """

    PAGE_ORDER = (
        ("home", "Home / Project"),
        ("text_cleanup", "Text Cleanup"),
        ("text_chunking", "Text Chunking"),
        ("ai_translation", "AI Translation"),
        ("characters", "Characters"),
        ("narator_voice", "Narrator Voice"),
        ("character_voices", "Character Voices"),
        ("speech_blocks", "Speech Blocks"),
        ("audio_blocks", "Audio Blocks"),
        ("audio_assembly", "Audio Assembly"),
    )

    # @brief Workflow operation each page reports status for. Home carries no single
    #        operation of its own, so it is absent and its status button stays dead.
    PAGE_OPERATION_KIND = {
        "text_cleanup": "cleanup",
        "text_chunking": "chunking",
        "ai_translation": "translation",
        "characters": "character_discovery",
        "narator_voice": "narrator_definition",
        "character_voices": "character_voices",
        "speech_blocks": "speech_blocks",
        "audio_blocks": "audio_blocks",
        "audio_assembly": "audio_assembly",
    }

    def __init__(
        self,
        settings_payload: dict[str, object] | None = None,
        parent=None,
    ) -> None:
        """
        @brief      Initialize the copied main-window shell.
        @param[in]  settings_payload Optional preloaded application settings.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        """
        super().__init__(parent)
        self.setWindowTitle(misc_ui_controller.build_window_title())
        self.setWindowIcon(QIcon(str(config.APP_ICON_PATH)))
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self._page_registry: dict[str, QWidget] = {}
        self._page_containers: dict[str, QScrollArea] = {}
        self._current_page_id = "home"
        self._current_manifest: dict[str, object] | None = None
        self._current_project_root: Path | None = None
        self._operation_progress_dialog: OperationProgressDialog | None = None
        self._active_operation_kind: str | None = None
        self._active_operation_name: str | None = None
        self._operation_cancel_requested = False
        self._active_operation_thread = None
        self._active_operation_worker = None
        self._active_operation_ui_bridge = None
        self._operation_cancel_event = None
        self._operation_shutdown_wait_timeout_ms = 3000
        self._narator_voice_preview_generation = 0
        self._narator_voice_inspected_profile_id: str | None = None
        self._character_voices_inspected_target_id: str | None = None
        self._character_voices_missing_narrator_popup_shown = False
        self._settings_payload = (
            dict(settings_payload) if isinstance(settings_payload, dict) else settings_service.load_settings()
        )
        self._narator_voice_audio_output = QAudioOutput(self)
        self._narator_voice_audio_player = QMediaPlayer(self)
        self._narator_voice_audio_player.setAudioOutput(self._narator_voice_audio_output)
        self._narator_voice_audio_player.playbackStateChanged.connect(
            lambda _state: narator_voice_ui_controller.handle_preview_playback_state_changed(self)
        )
        self._character_voices_audio_output = QAudioOutput(self)
        self._character_voices_audio_player = QMediaPlayer(self)
        self._character_voices_audio_player.setAudioOutput(self._character_voices_audio_output)
        self._character_voices_audio_player.playbackStateChanged.connect(
            lambda _state: character_voices_ui_controller.handle_preview_playback_state_changed(self)
        )
        self._audio_blocks_audio_output = QAudioOutput(self)
        self._audio_blocks_audio_player = QMediaPlayer(self)
        self._audio_blocks_audio_player.setAudioOutput(self._audio_blocks_audio_output)
        self._audio_blocks_audio_player.playbackStateChanged.connect(
            lambda _state: audio_blocks_ui_controller.handle_playback_state_changed(self)
        )
        self._audio_blocks_audio_player.mediaStatusChanged.connect(
            lambda status: audio_blocks_ui_controller.handle_media_status_changed(self, status)
        )
        self._audio_blocks_playback_mode: str | None = None
        self._audio_blocks_playback_block_ids: list[str] = []
        self._audio_blocks_playback_index = -1
        self._audio_assembly_audio_output = QAudioOutput(self)
        self._audio_assembly_audio_player = QMediaPlayer(self)
        self._audio_assembly_audio_player.setAudioOutput(self._audio_assembly_audio_output)
        self._audio_assembly_audio_player.playbackStateChanged.connect(
            lambda _state: audio_assembly_ui_controller.handle_playback_state_changed(self)
        )
        self._audio_assembly_audio_player.positionChanged.connect(
            lambda position_ms: audio_assembly_ui_controller.handle_playback_position_changed(self, position_ms)
        )
        self._audio_assembly_audio_player.durationChanged.connect(
            lambda duration_ms: audio_assembly_ui_controller.handle_playback_duration_changed(self, duration_ms)
        )
        self._audio_assembly_playback_output_key: str | None = None

        self._toolbar = self._build_toolbar()
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._toolbar)
        self._sidebar = NavigationSidebar(self)
        self._operation_status_button = QPushButton(self)
        self._operation_status_button.setObjectName("operationStatusButton")
        self._operation_status_button.setText(ui_state_service.translate("sidebar.operation_status", "en"))
        self._operation_status_button.setFixedWidth(self._sidebar.width())
        self._operation_status_button.setEnabled(False)
        self._operation_status_button.clicked.connect(self._show_operation_status_dialog)
        self._operation_status_dialog = OperationStatusDialog(self)
        self._stack = QStackedWidget(self)

        self._build_pages()
        self._build_dialogs()

        central_widget = QWidget(self)
        central_layout = QHBoxLayout(central_widget)
        # The sidebar is itself the QListWidget whose rows are the workflow pages,
        # so the operation-status button cannot live inside it without posing as an
        # eleventh page. A column wrapper keeps the button beside the list instead.
        navigation_column = QWidget(central_widget)
        navigation_layout = QVBoxLayout(navigation_column)
        navigation_layout.setContentsMargins(0, 0, 0, 0)
        navigation_layout.addWidget(self._sidebar, 1)
        navigation_layout.addWidget(self._operation_status_button, 0)
        central_layout.addWidget(navigation_column)
        central_layout.addWidget(self._stack, 1)
        self.setCentralWidget(central_widget)

        self._sidebar.page_selected.connect(self.set_current_page)
        self._sidebar.set_current_page("home")
        self.set_current_page("home")
        self._apply_current_ui_settings()
        self.set_project_active(False)
        self.show_project_state(None, None)

    def set_current_page(self, page_id: str) -> None:
        """
        @brief      Switch the shell to the requested placeholder page.
        @param[in]  page_id Registered page identifier.
        @return     None.
        @exception  None
        """
        page = self._page_registry.get(page_id)
        if page is None:
            return
        self._ensure_page_default_metadata(page_id)
        self._current_page_id = page_id
        self._stack.setCurrentWidget(self._page_containers[page_id])
        was_blocked = self._sidebar.blockSignals(True)
        self._sidebar.set_current_page(page_id)
        self._sidebar.blockSignals(was_blocked)
        if self._current_project_root is not None and self._current_manifest is not None:
            self.show_project_state(self._current_project_root, self._current_manifest)
        if page_id == "character_voices":
            self._character_voices_missing_narrator_popup_shown = False
            character_voices_ui_controller.handle_page_activated(self)

    def set_project_active(self, is_active: bool) -> None:
        """
        @brief      Enable or disable workflow pages based on project availability.
        @param[in]  is_active True when a project is open.
        @return     None.
        @exception  None
        """
        for page_id, _label in self.PAGE_ORDER:
            enabled = is_active or page_id == "home"
            self._sidebar.set_page_enabled(page_id, enabled)
        if not is_active:
            self._sidebar.set_current_page("home")
            self.set_current_page("home")
        for widget in self._page_registry.values():
            if hasattr(widget, "set_project_active"):
                widget.set_project_active(is_active)

    def show_project_state(
        self,
        project_root: Path | None,
        manifest: dict[str, object] | None,
    ) -> None:
        """
        @brief      Refresh shell-level project labels and workflow status state.
        @param[in]  project_root Active project root or `None`.
        @param[in]  manifest Active project manifest or `None`.
        @return     None.
        @exception  None
        """
        current_language = self.refresh_project_summary(project_root, manifest)
        self._refresh_current_page_state(project_root, manifest, current_language)
        self._refresh_operation_status_control(manifest)

    def refresh_project_summary(
        self,
        project_root: Path | None,
        manifest: dict[str, object] | None,
    ) -> str:
        """
        @brief      Refresh shell-level project labels and Home workflow status state only.
        @param[in]  project_root Active project root or `None`.
        @param[in]  manifest Active project manifest or `None`.
        @return     Current UI language code.
        @exception  None
        """
        self._current_project_root = project_root
        self._current_manifest = manifest
        current_language = ui_state_service.current_language_from_settings(self._settings_payload)
        display_name = None if manifest is None else str(manifest.get("display_name") or "")
        stage_name = None if manifest is None else str(manifest.get("current_stage") or "")
        source_name = home_presenter_service.source_document_name(manifest)
        self._home_page.set_project_state(
            display_name,
            None if project_root is None else str(project_root),
            stage_name,
        )
        self._home_page.set_source_summary(source_name)
        self._home_page.set_source_locked(source_name is not None, source_name)
        manifest_payload = {} if manifest is None else manifest
        self._home_page.set_project_options(
            bool(manifest_payload.get("project_options_locked", False)),
            str(manifest_payload.get("target_language", config.DEFAULT_TRANSLATION_TARGET_LANGUAGE)),
            str(
                manifest_payload.get(
                    "voice_assignment_mode",
                    config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
                )
            ),
        )
        self._home_page.set_stage_statuses(
            home_presenter_service.build_stage_statuses(
                manifest,
                current_language,
            )
        )
        self._home_page.set_export_states(project_export_service.build_export_states(project_root, manifest))
        return current_language

    def _refresh_operation_status_control(self, manifest: dict[str, object] | None) -> None:
        """
        @brief      Match the operation-status button to the current page's operation.
        @details    The button offers the result of an operation, so it stays dead
                    until one has been recorded. An absent, empty or not-started
                    status all mean the same thing to the operator - the operation
                    has not run - and none of them has a result worth opening.
        @param[in]  manifest Active project manifest or `None`.
        @return     None.
        @exception  None
        """
        status_text = self._current_operation_status_text(manifest)
        self._operation_status_button.setEnabled(status_text is not None)
        # The dialog is modeless, so one left open must follow the operator to
        # whichever page they navigate to rather than freezing on a stale page.
        if self._operation_status_dialog.isVisible():
            self._operation_status_dialog.set_status_text(status_text or "")

    def _show_operation_status_dialog(self) -> None:
        """
        @brief      Show the current page's operation status in the modeless dialog.
        @return     None.
        @exception  None
        """
        self._operation_status_dialog.set_status_text(
            self._current_operation_status_text(self._current_manifest) or ""
        )
        self._operation_status_dialog.show()
        self._operation_status_dialog.raise_()

    def _current_operation_status_text(self, manifest: dict[str, object] | None) -> str | None:
        """
        @brief      Resolve the status text of the current page's operation.
        @param[in]  manifest Active project manifest or `None`.
        @return     Status text, or `None` when the operation has not run.
        @exception  None
        """
        operation_kind = self.PAGE_OPERATION_KIND.get(self._current_page_id or "")
        if manifest is None or operation_kind is None:
            return None
        status = str(home_presenter_service.manifest_operation(manifest, operation_kind).get("status", "")).strip()
        if status in {"", "not_started"}:
            return None
        page = self._page_registry.get(self._current_page_id or "")
        reader = getattr(page, "operation_status_text", None)
        return reader() if callable(reader) else ""

    def _refresh_current_page_state(
        self,
        project_root: Path | None,
        manifest: dict[str, object] | None,
        current_language: str,
    ) -> None:
        """
        @brief      Refresh only the currently visible workflow page.
        @param[in]  project_root Active project root or `None`.
        @param[in]  manifest Active project manifest or `None`.
        @param[in]  current_language Current UI language code.
        @return     None.
        @exception  None
        """
        if self._current_page_id == "text_cleanup":
            self._text_cleanup_page.set_project_active(project_root is not None)
            self._text_cleanup_page.set_ai_profiles(
                **text_cleanup_state_service.build_ai_cleanup_profile_state(self._settings_payload)
            )
            self._text_cleanup_page.set_processing_state(
                **text_cleanup_state_service.build_text_cleanup_state(
                    project_root,
                    manifest,
                    current_language,
                )
            )
            return
        if self._current_page_id == "text_chunking":
            self._refresh_text_chunking_page_state(project_root, manifest, current_language)
            return
        if self._current_page_id == "ai_translation":
            self._refresh_ai_translation_page_state(project_root, manifest, current_language)
            return
        if self._current_page_id == "characters":
            self._refresh_characters_page_state(project_root, manifest, current_language)
            return
        if self._current_page_id == "narator_voice":
            self._refresh_narator_voice_page_state(project_root, manifest, current_language)
            return
        if self._current_page_id == "character_voices":
            self._refresh_character_voices_page_state(project_root, manifest, current_language)
            return
        if self._current_page_id == "speech_blocks":
            self._refresh_speech_blocks_page_state(project_root, manifest, current_language)
            return
        if self._current_page_id == "audio_blocks":
            self._refresh_audio_blocks_page_state(project_root, manifest, current_language)
            return
        if self._current_page_id == "audio_assembly":
            self._refresh_audio_assembly_page_state(project_root, manifest, current_language)

    def _refresh_text_chunking_page_state(
        self,
        project_root: Path | None,
        manifest: dict[str, object] | None,
        current_language: str,
    ) -> None:
        """
        @brief      Refresh the Text Chunking page state.
        @param[in]  project_root Active project root or `None`.
        @param[in]  manifest Active project manifest or `None`.
        @param[in]  current_language Current UI language code.
        @return     None.
        @exception  None
        """
        self._text_chunking_page.set_project_active(project_root is not None)
        self._text_chunking_page.set_ai_profiles(
            **text_chunking_state_service.build_ai_chunking_profile_state(self._settings_payload)
        )
        self._text_chunking_page.set_processing_state(
            **text_chunking_state_service.build_text_chunking_state(
                project_root,
                manifest,
                current_language,
                self._settings_payload,
            )
        )

    def _refresh_ai_translation_page_state(
        self,
        project_root: Path | None,
        manifest: dict[str, object] | None,
        current_language: str,
    ) -> None:
        """
        @brief      Refresh the AI Translation page state.
        @param[in]  project_root Active project root or `None`.
        @param[in]  manifest Active project manifest or `None`.
        @param[in]  current_language Current UI language code.
        @return     None.
        @exception  None
        """
        selected_profile_id = self._ai_translation_page.current_profile_id()
        self._ai_translation_page.set_project_active(project_root is not None)
        translation_state = ai_translation_state_service.build_ai_translation_state(
            project_root,
            manifest,
            current_language,
            self._settings_payload,
            selected_profile_id,
        )
        self._ai_translation_page.set_ai_profiles(
            **ai_translation_state_service.build_ai_translation_profile_state(
                self._settings_payload,
                selected_profile_id,
            )
        )
        self._ai_translation_page.set_translation_state(**translation_state)

    def _refresh_characters_page_state(
        self,
        project_root: Path | None,
        manifest: dict[str, object] | None,
        current_language: str,
    ) -> None:
        """
        @brief      Refresh the Characters page state.
        @param[in]  project_root Active project root or `None`.
        @param[in]  manifest Active project manifest or `None`.
        @param[in]  current_language Current UI language code.
        @return     None.
        @exception  None
        """
        self._characters_page.set_project_active(project_root is not None)
        selected_profile_id = self._characters_page.current_profile_id()
        character_state = character_discovery_state_service.build_character_discovery_state(
            project_root,
            manifest,
            current_language,
            self._settings_payload,
            selected_profile_id,
        )
        self._characters_page.set_ai_profiles(
            **character_discovery_state_service.build_character_discovery_profile_state(
                self._settings_payload,
                character_state.get("selected_profile_id"),
            )
        )
        self._characters_page.set_character_state(**character_state)

    def _refresh_narator_voice_page_state(
        self,
        project_root: Path | None,
        manifest: dict[str, object] | None,
        current_language: str,
    ) -> None:
        """
        @brief      Refresh the Narrator Voice page state.
        @param[in]  project_root Active project root or `None`.
        @param[in]  manifest Active project manifest or `None`.
        @param[in]  current_language Current UI language code.
        @return     None.
        @exception  None
        """
        self._narator_voice_page.set_project_active(project_root is not None)
        self._narator_voice_page.set_ai_profiles(
            **narrator_definition_state_service.build_narrator_profile_generation_profile_state(
                self._settings_payload,
                project_root,
                self._narator_voice_page.current_ai_profile_id(),
            )
        )
        self._narator_voice_page.set_narator_voice_state(
            **narrator_definition_state_service.build_narrator_definition_state(
                project_root,
                manifest,
                current_language,
                self._settings_payload,
                self._narator_voice_inspected_profile_id,
            )
        )

    def _refresh_character_voices_page_state(
        self,
        project_root: Path | None,
        manifest: dict[str, object] | None,
        current_language: str,
    ) -> None:
        """
        @brief      Refresh the Character Voices page state.
        @param[in]  project_root Active project root or `None`.
        @param[in]  manifest Active project manifest or `None`.
        @param[in]  current_language Current UI language code.
        @return     None.
        @exception  None
        """
        self._character_voices_page.set_project_active(project_root is not None)
        self._character_voices_page.set_character_voices_state(
            **character_voices_state_service.build_character_voices_state(
                project_root,
                manifest,
                current_language,
                self._settings_payload,
                self._character_voices_inspected_target_id,
                initialize_defaults=self._current_page_id == "character_voices",
            )
        )

    def _refresh_speech_blocks_page_state(
        self,
        project_root: Path | None,
        manifest: dict[str, object] | None,
        current_language: str,
    ) -> None:
        """
        @brief      Refresh the Speech Blocks page state.
        @param[in]  project_root Active project root or `None`.
        @param[in]  manifest Active project manifest or `None`.
        @param[in]  current_language Current UI language code.
        @return     None.
        @exception  None
        """
        self._speech_blocks_page.set_project_active(project_root is not None)
        speech_blocks_state = speech_blocks_state_service.build_speech_blocks_state(
            project_root,
            manifest,
            current_language,
            self._settings_payload,
        )
        self._speech_blocks_page.set_ai_profiles(
            **speech_blocks_state_service.build_speech_blocks_profile_state(
                self._settings_payload,
                speech_blocks_state.get("selected_profile_id"),
            )
        )
        self._speech_blocks_page.set_speech_blocks_state(**speech_blocks_state)

    def _refresh_audio_blocks_page_state(
        self,
        project_root: Path | None,
        manifest: dict[str, object] | None,
        current_language: str,
    ) -> None:
        """
        @brief      Refresh the Audio Blocks page state.
        @param[in]  project_root Active project root or `None`.
        @param[in]  manifest Active project manifest or `None`.
        @param[in]  current_language Current UI language code.
        @return     None.
        @exception  None
        """
        self._audio_blocks_page.set_project_active(project_root is not None)
        self._audio_blocks_page.set_audio_blocks_state(
            **audio_blocks_state_service.build_audio_blocks_state(
                project_root,
                manifest,
                current_language,
                self._settings_payload,
            )
        )

    def _refresh_audio_assembly_page_state(
        self,
        project_root: Path | None,
        manifest: dict[str, object] | None,
        current_language: str,
    ) -> None:
        """
        @brief      Refresh the Audio Assembly page state.
        @param[in]  project_root Active project root or `None`.
        @param[in]  manifest Active project manifest or `None`.
        @param[in]  current_language Current UI language code.
        @return     None.
        @exception  None
        """
        self._audio_assembly_page.set_project_active(project_root is not None)
        self._audio_assembly_page.set_audio_assembly_state(
            **audio_assembly_state_service.build_audio_assembly_state(
                project_root,
                manifest,
                current_language,
            )
        )

    def refresh_audio_assembly_page_state(self) -> None:
        """
        @brief      Refresh the Audio Assembly page alone from the current project state.
        @details    Narrower than `show_project_state`, which also rebuilds the
                    project summary and its Home export readiness rows by
                    reading every export artifact. A caller that changed
                    nothing outside the Audio Assembly page uses this instead.
        @return     None.
        @exception  None
        """
        self._refresh_audio_assembly_page_state(
            self._current_project_root,
            self._current_manifest,
            ui_state_service.current_language_from_settings(self._settings_payload),
        )

    def refresh_current_page_state(self) -> None:
        """
        @brief      Refresh the visible workflow page alone from the current project state.
        @details    Narrower than `show_project_state`, which also rebuilds the
                    project summary and its Home export readiness rows by
                    reading every export artifact, and narrower than
                    `apply_current_ui_settings`, which reapplies the
                    application-wide theme, font, and language. A caller that
                    changed only settings the visible page consumes uses this
                    instead.
        @return     None.
        @exception  None
        """
        self._refresh_current_page_state(
            self._current_project_root,
            self._current_manifest,
            ui_state_service.current_language_from_settings(self._settings_payload),
        )

    def show_settings_dialog(self) -> None:
        """
        @brief      Show the static settings dialog.
        @return     None.
        @exception  None
        """
        settings_ui_controller.show_settings_dialog(self)

    def show_ai_settings_dialog(self) -> None:
        """
        @brief      Show the static AI settings dialog.
        @return     None.
        @exception  None
        """
        ai_settings_ui_controller.show_ai_settings_dialog(self)

    def show_tts_settings_dialog(self) -> None:
        """
        @brief      Show the static TTS settings dialog.
        @return     None.
        @exception  None
        """
        tts_settings_ui_controller.show_tts_settings_dialog(self)

    def show_about_dialog(self) -> None:
        """
        @brief      Build and show the About dialog.
        @return     None.
        @exception  None
        """
        misc_ui_controller.show_about_dialog(self)

    def show_message(self, message: str, timeout_ms: int = 5000) -> None:
        """
        @brief      Accept one transient shell message without rendering a status bar.
        @param[in]  message Operator-facing message text.
        @param[in]  timeout_ms Legacy timeout in milliseconds.
        @return     None.
        @exception  None
        """
        misc_ui_controller.show_message(self, message, timeout_ms)

    # LOCAL HELPERS

    def _wordmark_html(self, accent: str) -> str:
        """
        @brief      Build the rich-text markup for the AudioMancer toolbar wordmark.
        @param[in]  accent Accent color for the "Mancer" half.
        @return     Rich-text HTML string.
        @exception  None
        """
        return (
            "<span style=\"font-family:Georgia,'Times New Roman',serif; font-size:13pt; font-weight:600;\">"
            f'Audio<span style="color:{accent}; font-style:italic;">Mancer</span></span>'
        )

    def _build_toolbar(self) -> QToolBar:
        """
        @brief      Build the source-matched main toolbar.
        @return     Configured Qt toolbar.
        @exception  None
        """
        toolbar = QToolBar("Main Toolbar", self)
        self._app_wordmark = QLabel(self)
        self._app_wordmark.setObjectName("appWordmark")
        self._app_wordmark.setTextFormat(Qt.TextFormat.RichText)
        self._app_wordmark.setContentsMargins(10, 0, 12, 0)
        self._app_wordmark.setText(self._wordmark_html("#E3AC52"))
        toolbar.addWidget(self._app_wordmark)
        toolbar.addSeparator()
        self._action_new_project = toolbar.addAction("New Project")
        self._action_open_project = toolbar.addAction("Open Project")
        toolbar.addSeparator()
        self._action_settings = toolbar.addAction("Settings")
        self._action_ai_settings = toolbar.addAction("AI Settings")
        self._action_tts_settings = toolbar.addAction("TTS Settings")
        toolbar.addSeparator()
        self._action_help = toolbar.addAction("Help")
        self._action_about = toolbar.addAction("About")
        self._action_settings.triggered.connect(
            lambda _checked=False: settings_ui_controller.show_settings_dialog(self)
        )
        self._action_ai_settings.triggered.connect(
            lambda _checked=False: ai_settings_ui_controller.show_ai_settings_dialog(self)
        )
        self._action_tts_settings.triggered.connect(
            lambda _checked=False: tts_settings_ui_controller.show_tts_settings_dialog(self)
        )
        self._action_new_project.triggered.connect(
            lambda _checked=False: home_ui_controller.handle_new_project_requested(self)
        )
        self._action_open_project.triggered.connect(
            lambda _checked=False: home_ui_controller.handle_open_project_requested(self)
        )
        self._action_help.triggered.connect(lambda _checked=False: misc_ui_controller.show_help(self))
        self._action_about.triggered.connect(lambda _checked=False: misc_ui_controller.show_about_dialog(self))
        return toolbar

    def _build_scrollable_container(self, page: QWidget) -> QScrollArea:
        """
        @brief      Wrap one page in a frameless, resizable scroll area.
        @details    Lets oversized page content scroll instead of clipping at large font
                    sizes or the minimum window resolution, without altering the page itself.
        @param[in]  page Page widget to wrap.
        @return     Scroll area hosting the page.
        @exception  None
        """
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(page)
        return scroll_area

    def _build_pages(self) -> None:
        """
        @brief      Build and register the stacked shell pages.
        @return     None.
        @exception  None
        """
        current_language = ui_state_service.current_language_from_settings(self._settings_payload)
        home_page = HomeProjectPage(self)
        self._home_page = home_page
        home_page.set_project_state(
            display_name=None,
            project_path=None,
            stage_name=None,
        )
        home_page.set_source_summary(None)
        home_page.set_source_locked(False, None)
        home_page.set_project_options(
            False,
            config.DEFAULT_TRANSLATION_TARGET_LANGUAGE,
            config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
        )
        home_page.set_stage_statuses(home_presenter_service.build_stage_statuses(None, current_language))
        home_page.set_export_states(project_export_service.build_export_states(None, None))
        home_page.import_requested.connect(lambda: home_ui_controller.handle_import_source_requested(self))
        home_page.project_snapshot_requested.connect(lambda: home_ui_controller.handle_project_snapshot_requested(self))
        home_page.project_options_lock_requested.connect(
            lambda target_language, voice_assignment_mode: home_ui_controller.handle_project_options_lock_requested(
                self,
                target_language,
                voice_assignment_mode,
            )
        )
        home_page.export_requested.connect(
            lambda export_kind, export_format: home_ui_controller.handle_export_requested(
                self,
                export_kind,
                export_format,
            )
        )

        self._text_cleanup_page = TextCleanupPage(self)
        self._text_cleanup_page.extract_requested.connect(
            lambda: text_cleanup_ui_controller.handle_extract_text_requested(self)
        )
        self._text_cleanup_page.cleanup_requested.connect(
            lambda profile_id: text_cleanup_ui_controller.handle_cleanup_requested(self, profile_id)
        )
        self._text_cleanup_page.reset_cleanup_requested.connect(
            lambda: text_cleanup_ui_controller.handle_reset_cleanup_requested(self)
        )
        self._text_cleanup_page.save_cleaned_text_requested.connect(
            lambda cleaned_text: text_cleanup_ui_controller.handle_save_cleaned_text_requested(self, cleaned_text)
        )
        self._text_chunking_page = TextChunkingPage(self)
        self._text_chunking_page.chunk_requested.connect(
            lambda: text_chunking_ui_controller.handle_deterministic_chunking_requested(self)
        )
        self._text_chunking_page.ai_chunk_requested.connect(
            lambda profile_id, strategy: text_chunking_ui_controller.handle_ai_chunking_requested(
                self,
                profile_id,
                strategy,
            )
        )
        self._text_chunking_page.save_chunk_requested.connect(
            lambda chunk_id, chunk_text: text_chunking_ui_controller.handle_save_chunk_requested(
                self,
                chunk_id,
                chunk_text,
            )
        )
        self._text_chunking_page.insert_chunk_requested.connect(
            lambda chunk_id: text_chunking_ui_controller.handle_insert_chunk_requested(self, chunk_id)
        )
        self._text_chunking_page.delete_chunk_requested.connect(
            lambda chunk_id: text_chunking_ui_controller.handle_delete_chunk_requested(self, chunk_id)
        )
        self._ai_translation_page = AiTranslationPage(self)
        self._ai_translation_page.start_translation_requested.connect(
            lambda profile_id: ai_translation_ui_controller.handle_start_translation_requested(
                self,
                profile_id,
            )
        )
        self._ai_translation_page.reset_translation_requested.connect(
            lambda: ai_translation_ui_controller.handle_reset_translation_requested(self)
        )
        self._ai_translation_page.approve_all_requested.connect(
            lambda: ai_translation_ui_controller.handle_approve_all_requested(self)
        )
        self._ai_translation_page.approve_selected_requested.connect(
            lambda chunk_id: ai_translation_ui_controller.handle_approve_selected_requested(
                self,
                chunk_id,
            )
        )
        self._ai_translation_page.retranslate_selected_requested.connect(
            lambda profile_id, chunk_id: ai_translation_ui_controller.handle_retranslate_selected_requested(
                self,
                profile_id,
                chunk_id,
            )
        )
        self._ai_translation_page.translated_text_changed.connect(
            lambda chunk_id, translated_text: ai_translation_ui_controller.handle_translated_text_changed(
                self,
                chunk_id,
                translated_text,
            )
        )
        self._characters_page = CharactersPage(self)
        self._characters_page.start_discovery_requested.connect(
            lambda profile_id: characters_ui_controller.handle_start_discovery_requested(
                self,
                profile_id,
            )
        )
        self._characters_page.reset_discovery_requested.connect(
            lambda: characters_ui_controller.handle_reset_discovery_requested(self)
        )
        self._characters_page.add_character_requested.connect(
            lambda: characters_ui_controller.handle_add_character_requested(self)
        )
        self._characters_page.edit_character_requested.connect(
            lambda character_id: characters_ui_controller.handle_edit_character_requested(
                self,
                character_id,
            )
        )
        self._characters_page.save_character_requested.connect(
            lambda profile_payload: characters_ui_controller.handle_save_character_requested(
                self,
                profile_payload,
                show_progress=True,
            )
        )
        self._characters_page.delete_character_requested.connect(
            lambda character_id: characters_ui_controller.handle_delete_character_requested(
                self,
                character_id,
            )
        )
        self._characters_page.selection_change_requested.connect(
            lambda character_id: characters_ui_controller.handle_selection_change_requested(
                self,
                character_id,
            )
        )
        self._narator_voice_page = NaratorVoicePage(self)
        self._narator_voice_page.create_profile_requested.connect(
            lambda profile_payload: narator_voice_ui_controller.handle_create_profile_requested(
                self,
                profile_payload,
            )
        )
        self._narator_voice_page.edit_profile_requested.connect(
            lambda profile_id: narator_voice_ui_controller.handle_edit_profile_requested(
                self,
                profile_id,
            )
        )
        self._narator_voice_page.save_profile_requested.connect(
            lambda profile_payload: narator_voice_ui_controller.handle_save_profile_requested(
                self,
                profile_payload,
            )
        )
        self._narator_voice_page.delete_profile_requested.connect(
            lambda profile_id: narator_voice_ui_controller.handle_delete_profile_requested(
                self,
                profile_id,
            )
        )
        self._narator_voice_page.selection_change_requested.connect(
            lambda profile_id: narator_voice_ui_controller.handle_selection_change_requested(
                self,
                profile_id,
            )
        )
        self._narator_voice_page.generate_sample_requested.connect(
            lambda profile_id: narator_voice_ui_controller.handle_generate_sample_requested(
                self,
                profile_id,
            )
        )
        self._narator_voice_page.import_sample_requested.connect(
            lambda profile_id: narator_voice_ui_controller.handle_import_sample_requested(
                self,
                profile_id,
            )
        )
        self._narator_voice_page.generate_profiles_requested.connect(
            lambda profile_id: narator_voice_ui_controller.handle_generate_profiles_requested(
                self,
                profile_id,
            )
        )
        self._narator_voice_page.select_profile_requested.connect(
            lambda profile_id: narator_voice_ui_controller.handle_select_profile_requested(
                self,
                profile_id,
            )
        )
        self._narator_voice_page.preview_toggle_requested.connect(
            lambda: narator_voice_ui_controller.handle_preview_toggle_requested(self)
        )
        self._character_voices_page = CharacterVoicesPage(self)
        self._character_voices_page.selection_change_requested.connect(
            lambda target_id: character_voices_ui_controller.handle_selection_change_requested(
                self,
                target_id,
            )
        )
        self._character_voices_page.import_sample_requested.connect(
            lambda target_id: character_voices_ui_controller.handle_import_sample_requested(
                self,
                target_id,
            )
        )
        self._character_voices_page.edit_prompt_requested.connect(
            lambda target_id: character_voices_ui_controller.handle_edit_prompt_requested(
                self,
                target_id,
            )
        )
        self._character_voices_page.save_prompt_requested.connect(
            lambda target_payload: character_voices_ui_controller.handle_save_prompt_requested(
                self,
                target_payload,
            )
        )
        self._character_voices_page.generate_sample_requested.connect(
            lambda target_id: character_voices_ui_controller.handle_generate_sample_requested(
                self,
                target_id,
            )
        )
        self._character_voices_page.generate_missing_samples_requested.connect(
            lambda: character_voices_ui_controller.handle_generate_missing_samples_requested(self)
        )
        self._character_voices_page.preview_toggle_requested.connect(
            lambda: character_voices_ui_controller.handle_preview_toggle_requested(self)
        )
        self._speech_blocks_page = SpeechBlocksPage(self)
        self._speech_blocks_page.generate_requested.connect(
            lambda profile_id: speech_blocks_ui_controller.handle_generate_requested(
                self,
                profile_id,
            )
        )
        self._speech_blocks_page.reset_generation_requested.connect(
            lambda: speech_blocks_ui_controller.handle_reset_generation_requested(self)
        )
        self._speech_blocks_page.approve_all_requested.connect(
            lambda: speech_blocks_ui_controller.handle_approve_all_requested(self)
        )
        self._speech_blocks_page.resplit_selected_requested.connect(
            lambda chunk_id: speech_blocks_ui_controller.handle_resplit_selected_requested(self, chunk_id)
        )
        self._speech_blocks_page.insert_block_requested.connect(
            lambda chunk_id, after_speech_block_id: speech_blocks_ui_controller.handle_insert_block_requested(
                self,
                chunk_id,
                after_speech_block_id,
            )
        )
        self._speech_blocks_page.delete_block_requested.connect(
            lambda speech_block_id: speech_blocks_ui_controller.handle_delete_block_requested(self, speech_block_id)
        )
        self._speech_blocks_page.edit_started.connect(
            lambda speech_block_id: speech_blocks_ui_controller.handle_edit_started(self, speech_block_id)
        )
        self._speech_blocks_page.save_block_requested.connect(
            lambda speech_block_id, speaker_id, content_kind, edit_payload: (
                speech_blocks_ui_controller.handle_save_block_requested(
                    self,
                    speech_block_id,
                    speaker_id,
                    content_kind,
                    edit_payload,
                )
            )
        )
        self._speech_blocks_page.approve_block_requested.connect(
            lambda speech_block_id: speech_blocks_ui_controller.handle_approve_block_requested(self, speech_block_id)
        )
        self._speech_blocks_page.generate_audio_selected_requested.connect(
            lambda speech_block_id: audio_blocks_ui_controller.handle_regenerate_selected_requested(
                self,
                speech_block_id,
            )
        )
        self._speech_blocks_page.selected_audio_playback_toggle_requested.connect(
            lambda speech_block_id: audio_blocks_ui_controller.handle_selected_playback_toggle_requested(
                self,
                speech_block_id,
            )
        )
        self._audio_blocks_page = AudioBlocksPage(self)
        self._audio_blocks_page.start_generation_requested.connect(
            lambda: audio_blocks_ui_controller.handle_start_generation_requested(self)
        )
        self._audio_blocks_page.reset_generation_requested.connect(
            lambda: audio_blocks_ui_controller.handle_reset_generation_requested(self)
        )
        self._audio_blocks_page.approve_all_requested.connect(
            lambda: audio_blocks_ui_controller.handle_approve_all_requested(self)
        )
        self._audio_blocks_page.audiobook_playback_toggle_requested.connect(
            lambda: audio_blocks_ui_controller.handle_audiobook_playback_toggle_requested(self)
        )
        self._audio_blocks_page.regenerate_selected_requested.connect(
            lambda speech_block_id: audio_blocks_ui_controller.handle_regenerate_selected_requested(
                self,
                speech_block_id,
            )
        )
        self._audio_blocks_page.approve_selected_requested.connect(
            lambda speech_block_id: audio_blocks_ui_controller.handle_approve_selected_requested(
                self,
                speech_block_id,
            )
        )
        self._audio_blocks_page.selected_playback_toggle_requested.connect(
            lambda speech_block_id: audio_blocks_ui_controller.handle_selected_playback_toggle_requested(
                self,
                speech_block_id,
            )
        )
        self._audio_assembly_page = AudioAssemblyPage(self)
        self._audio_assembly_page.settings_changed.connect(
            lambda settings: audio_assembly_ui_controller.handle_settings_changed(self, settings)
        )
        self._audio_assembly_page.generate_requested.connect(
            lambda settings: audio_assembly_ui_controller.handle_generate_requested(self, settings)
        )
        self._audio_assembly_page.reset_requested.connect(
            lambda: audio_assembly_ui_controller.handle_reset_requested(self)
        )
        self._audio_assembly_page.playback_toggle_requested.connect(
            lambda output_key: audio_assembly_ui_controller.handle_playback_toggle_requested(self, output_key)
        )
        self._audio_assembly_page.playback_restart_requested.connect(
            lambda output_key: audio_assembly_ui_controller.handle_playback_restart_requested(self, output_key)
        )
        self._audio_assembly_page.playback_seek_requested.connect(
            lambda position_ms: audio_assembly_ui_controller.handle_playback_seek_requested(self, position_ms)
        )
        self._audio_assembly_page.playback_skip_requested.connect(
            lambda delta_ms: audio_assembly_ui_controller.handle_playback_skip_requested(self, delta_ms)
        )
        self._audio_assembly_page.scene_mix_generate_requested.connect(
            lambda group_key: audio_assembly_ui_controller.handle_scene_mix_generate_requested(self, group_key)
        )
        self._audio_assembly_page.scene_mix_playback_toggle_requested.connect(
            lambda group_key: audio_assembly_ui_controller.handle_scene_mix_playback_toggle_requested(self, group_key)
        )

        pages = {
            "home": home_page,
            "text_cleanup": self._text_cleanup_page,
            "text_chunking": self._text_chunking_page,
            "ai_translation": self._ai_translation_page,
            "characters": self._characters_page,
            "narator_voice": self._narator_voice_page,
            "character_voices": self._character_voices_page,
            "speech_blocks": self._speech_blocks_page,
            "audio_blocks": self._audio_blocks_page,
            "audio_assembly": self._audio_assembly_page,
        }

        for page_id, label in self.PAGE_ORDER:
            page = pages[page_id]
            self._page_registry[page_id] = page
            container = self._build_scrollable_container(page)
            self._page_containers[page_id] = container
            self._stack.addWidget(container)
            self._sidebar.add_page(page_id, label, enabled=page_id == "home")

    def _build_dialogs(self) -> None:
        """
        @brief      Build static shell dialogs for the copied window.
        @return     None.
        @exception  None
        """
        current_language = ui_state_service.current_language_from_settings(self._settings_payload)

        self._settings_dialog = QDialog(self)
        self._settings_dialog.setWindowTitle(ui_state_service.translate("dialog.settings_title", current_language))
        self._settings_dialog.setMinimumSize(640, 480)
        self._settings_dialog.resize(800, 600)
        settings_layout = QVBoxLayout(self._settings_dialog)
        self._settings_page = SettingsPage(self._settings_dialog)
        self._settings_page._cancel_button.clicked.connect(self._settings_dialog.close)
        self._settings_page._apply_button.clicked.connect(
            lambda _checked=False: settings_ui_controller.apply_settings_from_dialog(self)
        )
        self._settings_page._ok_button.clicked.connect(
            lambda _checked=False: settings_ui_controller.save_settings_from_dialog(self)
        )
        self._settings_page.load_settings(self._settings_payload)
        settings_layout.addWidget(self._build_scrollable_container(self._settings_page))

        self._ai_settings_dialog = QDialog(self)
        self._ai_settings_dialog.setWindowTitle(
            ui_state_service.translate("dialog.ai_settings_title", current_language)
        )
        self._ai_settings_dialog.setMinimumSize(640, 480)
        self._ai_settings_dialog.resize(800, 600)
        ai_layout = QVBoxLayout(self._ai_settings_dialog)
        self._ai_settings_page = AiSettingsPage(self._ai_settings_dialog)
        self._ai_settings_page._connect_button.clicked.connect(
            lambda _checked=False: ai_settings_ui_controller.connect_ai_profile_from_dialog(self)
        )
        self._ai_settings_page._cancel_button.clicked.connect(self._ai_settings_dialog.close)
        self._ai_settings_page._save_button.clicked.connect(
            lambda _checked=False: ai_settings_ui_controller.apply_ai_settings_from_dialog(self)
        )
        self._ai_settings_page._ok_button.clicked.connect(
            lambda _checked=False: ai_settings_ui_controller.save_ai_settings_from_dialog(self)
        )
        self._ai_settings_page.load_settings(self._settings_payload)
        ai_layout.addWidget(self._build_scrollable_container(self._ai_settings_page))

        self._tts_settings_dialog = QDialog(self)
        self._tts_settings_dialog.setWindowTitle(
            ui_state_service.translate("dialog.tts_settings_title", current_language)
        )
        self._tts_settings_dialog.setMinimumSize(640, 480)
        self._tts_settings_dialog.resize(800, 600)
        tts_layout = QVBoxLayout(self._tts_settings_dialog)
        self._tts_settings_page = TtsSettingsPage(self._tts_settings_dialog)
        self._tts_settings_page._test_connection_button.clicked.connect(
            lambda _checked=False: tts_settings_ui_controller.test_runtime_connection_from_dialog(self)
        )
        self._tts_settings_page._cancel_button.clicked.connect(self._tts_settings_dialog.close)
        self._tts_settings_page._save_button.clicked.connect(
            lambda _checked=False: tts_settings_ui_controller.apply_tts_settings_from_dialog(self)
        )
        self._tts_settings_page._ok_button.clicked.connect(
            lambda _checked=False: tts_settings_ui_controller.save_tts_settings_from_dialog(self)
        )
        self._tts_settings_page.load_state(self._settings_payload, None, False)
        tts_layout.addWidget(self._build_scrollable_container(self._tts_settings_page))

    def _apply_current_ui_settings(self) -> None:
        """
        @brief      Apply persisted runtime UI settings to the current shell.
        @return     None.
        @exception  None
        """
        settings_ui_controller.apply_current_ui_settings(self)

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language across the visible shell widgets.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        """
        settings_ui_controller.apply_language(self, language)

    def apply_theme(self, theme_payload: dict[str, object]) -> None:
        """
        @brief      Apply one UI theme across theme-aware shell pages.
        @param[in]  theme_payload Runtime UI theme payload.
        @return     None.
        @exception  None
        """
        for widget in self._page_registry.values():
            if hasattr(widget, "apply_theme"):
                widget.apply_theme(theme_payload)
        if hasattr(self, "_sidebar") and hasattr(self._sidebar, "apply_theme"):
            self._sidebar.apply_theme(theme_payload)
        if hasattr(self, "_app_wordmark"):
            colors = theme_payload.get("colors") if isinstance(theme_payload, dict) else None
            accent = str(colors.get("accent")) if isinstance(colors, dict) and colors.get("accent") else "#E3AC52"
            self._app_wordmark.setText(self._wordmark_html(accent))

    def _activate_project(
        self,
        project_root: Path,
        manifest: dict[str, object],
    ) -> None:
        """
        @brief      Apply one active project into the current shell state.
        @param[in]  project_root Resolved active project root.
        @param[in]  manifest Loaded active project manifest.
        @return     None.
        @exception  None
        """
        home_ui_controller.activate_project(self, project_root, manifest)

    def stop_all_audio_playback(self) -> None:
        """
        @brief      Stop every project-local preview/player and clear loaded media sources.
        @details    Project switches must release old project media files and reset
                    playback UI state before the next manifest is displayed.
        @return     None.
        @exception  None
        """
        for attr_name in (
            "_narator_voice_audio_player",
            "_character_voices_audio_player",
            "_audio_blocks_audio_player",
            "_audio_assembly_audio_player",
        ):
            player = getattr(self, attr_name, None)
            if player is not None:
                player.stop()
                player.setSource(QUrl())

        if hasattr(self, "_narator_voice_page"):
            self._narator_voice_page.set_preview_active(False)
        if hasattr(self, "_character_voices_page"):
            self._character_voices_page.set_preview_active(False)
        if hasattr(self, "_audio_blocks_page"):
            self._audio_blocks_page.set_selected_playback_active(False)
            self._audio_blocks_page.set_audiobook_playback_active(False)
        if hasattr(self, "_speech_blocks_page"):
            self._speech_blocks_page.set_selected_audio_playback_active(False)
        if hasattr(self, "_audio_assembly_page"):
            self._audio_assembly_page.set_playback_active(False)
            self._audio_assembly_page.set_playback_progress(0, 0)

        self._audio_blocks_playback_mode = None
        self._audio_blocks_playback_block_ids = []
        self._audio_blocks_playback_index = -1
        self._audio_assembly_playback_output_key = None
        self._audio_assembly_playback_starting = False

    def _ensure_page_default_metadata(self, page_id: str) -> None:
        """
        @brief      Persist default operation-state metadata for the opened workflow page.
        @param[in]  page_id Registered page identifier.
        @return     None.
        @exception  None
        """
        if self._current_project_root is None or self._current_manifest is None:
            return
        for operation_kind in _PAGE_OPERATION_STATE_KINDS.get(page_id, ()):
            operation_runtime_service.ensure_default_operation_state(self._current_project_root, operation_kind)

    def _build_about_dialog(self) -> QDialog:
        """
        @brief      Build the About dialog for the AudioMancer shell.
        @return     Configured Qt dialog instance.
        @exception  None
        """
        return misc_ui_controller.build_about_dialog(self)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """
        @brief      Handle window close for the static shell.
        @param[in]  event Qt close event.
        @return     None.
        @exception  None
        """
        if not operation_runner_controller.cancel_active_operation_for_shutdown(
            self,
            self._operation_shutdown_wait_timeout_ms,
        ):
            event.ignore()
            return
        self._ai_translation_page.flush_pending_translation_edit()
        self.stop_all_audio_playback()
        super().closeEvent(event)


# END OF FILE
