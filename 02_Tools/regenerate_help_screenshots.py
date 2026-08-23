#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file regenerate_help_screenshots.py
@brief Refresh offline-help UI screenshots from the current AudioMancer widgets.
@details Opens the existing sample project, renders each documented page or
         settings dialog, and writes the PNG files referenced by the English
         and Romanian offline help bundles.
@author Eng. Dan Dumitru Pasare
@date 2026-06-12
@version 0.1.0
@example
    uv run python ../../02_Tools/regenerate_help_screenshots.py
"""

# IMPORTS

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys

# CONSTANTS

# @brief Repository root derived from this tool location.
REPO_ROOT = Path(__file__).resolve().parents[1]
# @brief Application source root used for direct imports without installation.
APP_SOURCE_ROOT = REPO_ROOT / "05_Software" / "AudioMancer" / "src"
# @brief Default populated sample project used by the committed help screenshots.
DEFAULT_PROJECT_ROOT = REPO_ROOT / "09_Others" / "Command Performance"
# @brief English offline help screenshot folder.
ENGLISH_SCREENSHOT_ROOT = REPO_ROOT / "06_SoftwareDocu" / "UserGuide" / "assets" / "screenshots"
# @brief Romanian offline help screenshot folder.
ROMANIAN_SCREENSHOT_ROOT = REPO_ROOT / "06_SoftwareDocu" / "UserGuide_ro" / "assets" / "screenshots"
# @brief Capture width chosen to match the historical full-window help screenshots.
CAPTURE_WIDTH = 1920
# @brief Capture height chosen to match the historical full-window help screenshots.
CAPTURE_HEIGHT = 1040
# @brief Dialog width used for settings-style screenshots.
DIALOG_WIDTH = 1280
# @brief Dialog height used for settings-style screenshots.
DIALOG_HEIGHT = 900
# @brief Main-window page screenshots referenced by the offline help.
PAGE_SCREENSHOTS = (
    ("home", "home-project.png"),
    ("text_cleanup", "text-cleanup.png"),
    ("text_chunking", "text-chunking.png"),
    ("ai_translation", "ai-translation.png"),
    ("characters", "characters.png"),
    ("narator_voice", "narator-voice.png"),
    ("character_voices", "character-voices.png"),
    ("speech_blocks", "speech-blocks.png"),
    ("audio_blocks", "audio-blocks.png"),
    ("audio_assembly", "audio-assembly.png"),
)
# @brief Dialog screenshots referenced by the offline help.
DIALOG_SCREENSHOTS = (
    ("settings", "settings-dialog.png"),
    ("ai_settings", "ai-settings-dialog.png"),
    ("tts_settings", "tts-settings-dialog.png"),
)
# @brief Sample AI profiles rendered in the AI settings dialog without secrets.
SAMPLE_LLM_PROFILES = (
    {
        "id": "profile_openai_translation",
        "label": "OpenAI Translation",
        "backend_kind": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model_name": "gpt-5.5",
        "context_window": 1000000,
        "max_output_tokens": 64000,
        "request_timeout_seconds": 180,
        "temperature": 0.2,
        "supports_structured_output": True,
        "enabled": True,
        "discovered_model_name": "",
        "discovered_context_window": None,
        "discovery_succeeded": False,
        "discovery_message": "",
        "user_overrode_model_name": False,
        "user_overrode_context_window": False,
    },
    {
        "id": "profile_lmstudio_local",
        "label": "LM Studio Local",
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234/v1",
        "api_key": "",
        "model_name": "qwen/qwen3-30b-a3b-2507",
        "context_window": 65536,
        "max_output_tokens": 32768,
        "request_timeout_seconds": 240,
        "temperature": 0.05,
        "supports_structured_output": False,
        "enabled": True,
        "discovered_model_name": "",
        "discovered_context_window": None,
        "discovery_succeeded": False,
        "discovery_message": "",
        "user_overrode_model_name": False,
        "user_overrode_context_window": False,
    },
)


# PUBLIC API


def parse_args() -> argparse.Namespace:
    """
    @brief      Parse command-line arguments for the screenshot refresh tool.
    @return     Parsed argument namespace.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-12
    @version    0.1.0
    """
    parser = argparse.ArgumentParser(description="Regenerate AudioMancer offline-help UI screenshots.")
    parser.add_argument(
        "--project-root",
        default=str(DEFAULT_PROJECT_ROOT),
        help="Populated AudioMancer project folder used for workflow-page captures.",
    )
    parser.add_argument(
        "--english-only",
        action="store_true",
        help="Write only the English screenshot folder instead of mirroring to Romanian.",
    )
    parser.add_argument(
        "--dialog",
        choices=[dialog_id for dialog_id, _file_name in DIALOG_SCREENSHOTS],
        help="Capture only one settings dialog without requiring the sample project.",
    )
    return parser.parse_args()


def main() -> int:
    """
    @brief      Regenerate the committed offline-help screenshot files.
    @return     Process exit code.
    @exception  FileNotFoundError Raised when the sample project is unavailable.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-12
    @version    0.1.0
    """
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    if args.dialog is None and not (project_root / "project.json").is_file():
        raise FileNotFoundError(f"AudioMancer sample project manifest was not found: {project_root}")

    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    if str(APP_SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(APP_SOURCE_ROOT))

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from audiomancer import config
    from audiomancer.services import project_workspace_service, settings_service, ui_state_service, ui_theme_service
    from audiomancer.ui.main_window import MainWindow

    settings_payload = build_screenshot_settings(settings_service, config)
    application = QApplication.instance() or QApplication([str(Path(__file__).name)])
    application.setApplicationName(config.APP_NAME)
    application.setWindowIcon(QIcon(str(config.APP_ICON_PATH)))
    startup_theme = ui_theme_service.theme_by_id(settings_payload["ui_theme_id"], settings_payload["ui_themes"])
    ui_state_service.apply_theme(application, startup_theme, None)

    manifest = project_workspace_service.load_manifest(project_root) if args.dialog is None else None
    window = MainWindow(settings_payload=settings_payload)
    window.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
    window.show()
    application.processEvents()

    ENGLISH_SCREENSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        for page_id, file_name in PAGE_SCREENSHOTS:
            window.set_current_page(page_id)
            window.show_project_state(project_root, manifest)
            application.processEvents()
            save_widget_screenshot(window, ENGLISH_SCREENSHOT_ROOT / file_name)

    dialog_by_id = {
        "settings": window._settings_dialog,
        "ai_settings": window._ai_settings_dialog,
        "tts_settings": window._tts_settings_dialog,
    }
    selected_dialogs = (
        DIALOG_SCREENSHOTS
        if args.dialog is None
        else tuple(entry for entry in DIALOG_SCREENSHOTS if entry[0] == args.dialog)
    )
    for dialog_id, file_name in selected_dialogs:
        dialog = dialog_by_id[dialog_id]
        dialog.resize(DIALOG_WIDTH, DIALOG_HEIGHT)
        dialog.show()
        application.processEvents()
        save_widget_screenshot(dialog, ENGLISH_SCREENSHOT_ROOT / file_name)
        dialog.hide()

    if not args.english_only:
        if args.dialog is None:
            mirror_screenshots_to_romanian()
        else:
            ROMANIAN_SCREENSHOT_ROOT.mkdir(parents=True, exist_ok=True)
            for _dialog_id, file_name in selected_dialogs:
                shutil.copy2(ENGLISH_SCREENSHOT_ROOT / file_name, ROMANIAN_SCREENSHOT_ROOT / file_name)

    window.close()
    application.processEvents()
    return 0


def build_screenshot_settings(settings_service, config) -> dict[str, object]:
    """
    @brief      Build sanitized UI settings for documentation screenshots.
    @param[in]  settings_service Imported settings service module.
    @param[in]  config Imported application configuration module.
    @return     Validated settings payload without local secrets.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-12
    @version    0.1.0
    """
    settings_payload = settings_service.build_default_settings()
    settings_payload.update(
        {
            "language": "en",
            "ui_theme_id": config.DEFAULT_UI_THEME_ID,
            "ui_themes": [],
            "play_completion_beep": False,
            "llm_profiles": [dict(profile) for profile in SAMPLE_LLM_PROFILES],
            "default_ai_cleanup_profile_id": "profile_lmstudio_local",
            "default_ai_chunking_profile_id": "profile_lmstudio_local",
            "default_ai_translation_profile_id": "profile_openai_translation",
            "default_narrator_profile_generation_profile_id": "profile_lmstudio_local",
            "default_character_extraction_profile_id": "profile_lmstudio_local",
            "default_speech_blocks_profile_id": "profile_lmstudio_local",
            "tts_runtime_base_url": config.DEFAULT_TTS_RUNTIME_BASE_URL,
            "tts_runtime_probe_succeeded": True,
            "tts_runtime_probe_message": "Documentation sample runtime profile.",
            "tts_runtime_discovered_models": [
                {
                    "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
                    "backend_name": "qwen",
                    "status": "healthy",
                    "supported_generation_modes": ["clone"],
                    "supported_languages": ["de", "en", "es", "fr", "it", "pt", "ru"],
                    "default_model_parameters": None,
                    "device_mode": "cuda",
                    "issues": None,
                },
                {
                    "model_id": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                    "backend_name": "qwen",
                    "status": "healthy",
                    "supported_generation_modes": ["voice_design"],
                    "supported_languages": ["de", "en", "es", "fr", "it", "pt", "ru"],
                    "default_model_parameters": None,
                    "device_mode": "cuda",
                    "issues": None,
                },
                {
                    "model_id": "stable-audio-open-1.0",
                    "backend_name": "stable_audio",
                    "status": "healthy",
                    "supported_generation_modes": ["sound_prompt"],
                    "supported_languages": [],
                    "default_model_parameters": None,
                    "device_mode": "cuda",
                    "issues": None,
                }
            ],
            "tts_runtime_active_model_id": "Qwen3-TTS-12Hz-1.7B-Base",
            "tts_runtime_device_diagnostics": {},
            "scene_ambience_placement": "openers_closers_and_scene_changes",
        }
    )
    return settings_service.validate_settings(settings_payload)


def save_widget_screenshot(widget, output_path: Path) -> None:
    """
    @brief      Save one widget grab as a PNG file.
    @param[in]  widget Visible Qt widget to capture.
    @param[in]  output_path Target PNG path.
    @return     None.
    @exception  RuntimeError Raised when Qt cannot save the PNG.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-12
    @version    0.1.0
    """
    pixmap = widget.grab()
    if pixmap.isNull() or not pixmap.save(str(output_path), "PNG"):
        raise RuntimeError(f"Failed to write screenshot: {output_path}")


def mirror_screenshots_to_romanian() -> None:
    """
    @brief      Copy refreshed English screenshots into the Romanian help bundle.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-12
    @version    0.1.0
    """
    ROMANIAN_SCREENSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    for _page_id, file_name in PAGE_SCREENSHOTS:
        shutil.copy2(ENGLISH_SCREENSHOT_ROOT / file_name, ROMANIAN_SCREENSHOT_ROOT / file_name)
    for _dialog_id, file_name in DIALOG_SCREENSHOTS:
        shutil.copy2(ENGLISH_SCREENSHOT_ROOT / file_name, ROMANIAN_SCREENSHOT_ROOT / file_name)


if __name__ == "__main__":
    raise SystemExit(main())


# END OF FILE
