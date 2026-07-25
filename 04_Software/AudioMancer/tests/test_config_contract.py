#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_config_contract.py
@brief Focused contract tests for the AudioMancer configuration scaffold.
@details Verifies that the adapted configuration constants, the packaged
         settings scaffold, and the frozen-bundle resource layout exist with the
         expected baseline contract.
@author Eng. Dan Dumitru Pasare
@date 2026-07-25
@version 0.10.0
"""

# IMPORTS

import importlib
import json
from pathlib import Path
import sys

from audiomancer import config
from audiomancer.services import settings_service

# PUBLIC API


def test_config_exposes_expected_identity_and_window_defaults() -> None:
    """
    @brief      Verify the adapted configuration exposes the expected identity and UI defaults.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.6
    """
    assert config.APP_NAME == "AudioMancer"
    assert config.PACKAGE_NAME == "audiomancer"
    assert config.DEFAULT_MAIN_WINDOW_WIDTH == 1040
    assert config.DEFAULT_MAIN_WINDOW_HEIGHT == 660
    assert config.DEFAULT_MAIN_WINDOW_MIN_WIDTH == 900
    assert config.DEFAULT_MAIN_WINDOW_MIN_HEIGHT == 560
    assert config.PROJECT_MANIFEST_FILE_NAME == "project.json"
    assert config.DEFAULT_WORKFLOW_STAGE == "project_created"
    assert "character_voices_ready" in config.PROJECT_WORKFLOW_STAGES
    assert "speech_blocks_ready" in config.PROJECT_WORKFLOW_STAGES
    assert "audio_blocks_ready" in config.PROJECT_WORKFLOW_STAGES
    assert "audio_assembly_ready" in config.PROJECT_WORKFLOW_STAGES
    assert config.CHARACTER_VOICES_TARGETS_FILE_NAME == "characters_voice.json"
    assert config.SUPPORTED_SOURCE_SUFFIXES[".epub"] == "epub"
    assert config.SUPPORTED_SOURCE_SUFFIXES[".docx"] == "docx"
    assert config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH == "."
    assert config.EXTRACTED_TEXT_FILE_NAME == "extracted_text.txt"
    assert config.EXTRACTION_METADATA_FILE_NAME == "extraction_metadata.json"
    assert config.CLEANED_TEXT_FILE_NAME == "clean_text.txt"
    assert config.CLEANUP_STATE_FILE_NAME == "cleanup_state.json"
    assert config.CHUNK_ARTIFACT_FILE_NAME == "chunks_text.json"
    assert not hasattr(config, "CHUNKING_REPORT_FILE_NAME")
    assert not hasattr(config, "CHUNKING_STATE_FILE_NAME")
    assert config.TRANSLATED_CHUNKS_FILE_NAME == "translated_text.json"
    assert not hasattr(config, "TRANSLATION_REPORT_FILE_NAME")
    assert not hasattr(config, "TRANSLATION_STATE_FILE_NAME")
    assert config.NARRATOR_VOICE_FILE_NAME == "narrator_voice.json"
    assert not hasattr(config, "NARRATOR_PROFILE_FILE_NAME")
    assert not hasattr(config, "NARRATOR_SELECTION_FILE_NAME")
    assert not hasattr(config, "SELECTED_NARRATOR_AUDIO_FILE_NAME")
    assert not hasattr(config, "SELECTED_NARRATOR_METADATA_FILE_NAME")
    assert config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME == "speech_blocks.json"
    assert config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME == "audio_blocks"
    assert config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT == 512
    assert config.DEFAULT_TTS_OPERATION_TIMEOUT_SECONDS == config.DEFAULT_TTS_AUDIO_GENERATION_TIMEOUT_SECONDS
    assert "ai_chunking" in config.AVAILABLE_LOG_COMPONENTS
    assert "text_extraction" in config.AVAILABLE_LOG_COMPONENTS


def test_settings_json_scaffold_matches_service_defaults(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify the bundled settings scaffold is service-readable without repair.
    @details    The scaffold is read from the bundled default path and loaded through a
                temporary active path, so the committed file is never rewritten by a
                repair pass during the test.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.2.0
    """
    scaffold_path = config.APP_DEFAULT_SETTINGS_PATH
    payload = json.loads(Path(scaffold_path).read_text(encoding="utf-8"))

    active_settings_path = tmp_path / "settings.json"
    active_settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", active_settings_path)
    loaded_payload = settings_service.load_settings()

    assert isinstance(payload, dict)
    assert isinstance(loaded_payload, dict)
    assert payload == loaded_payload
    assert scaffold_path == config.APP_ROOT / "settings.json"


def test_config_resolves_frozen_packaged_runtime_resources(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify PyInstaller resource lookup resolves files staged beside the executable.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    from audiomancer.services import prompt_template_service
    from audiomancer.ui.controllers import misc_ui_controller

    bundle_root = tmp_path / "AudioMancer"
    internal_root = bundle_root / "_internal"
    prompt_root = bundle_root / "prompts"
    help_root = bundle_root / "help" / "en"
    bundle_root.mkdir()
    internal_root.mkdir()
    prompt_root.mkdir()
    help_root.mkdir(parents=True)
    (bundle_root / "settings.json").write_text("{}\n", encoding="utf-8")
    (bundle_root / "LICENSE.txt").write_text("Main license\n", encoding="utf-8")
    (bundle_root / "LICENSE_NC.txt").write_text("NC license\n", encoding="utf-8")
    (bundle_root / "LICENSE_ro.txt").write_text("Licenta\n", encoding="utf-8")
    (bundle_root / "LICENSE_NC_ro.txt").write_text("Licenta NC\n", encoding="utf-8")
    (bundle_root / "pyproject.toml").write_text('[project]\nversion = "9.8.7"\n', encoding="utf-8")
    (prompt_root / "sample.txt").write_text("Packaged prompt", encoding="utf-8")
    (help_root / "index.html").write_text("<html></html>\n", encoding="utf-8")

    try:
        with monkeypatch.context() as frozen_patch:
            frozen_patch.setattr(sys, "frozen", True, raising=False)
            frozen_patch.setattr(sys, "_MEIPASS", str(internal_root), raising=False)
            frozen_patch.setattr(sys, "executable", str(bundle_root / "AudioMancer.exe"))
            importlib.reload(config)
            importlib.reload(prompt_template_service)
            importlib.reload(misc_ui_controller)

            assert bundle_root.resolve() == config.APP_ROOT
            assert bundle_root.resolve() / "settings.json" == config.APP_DEFAULT_SETTINGS_PATH
            assert bundle_root.resolve() / "settings.json" == config.APP_SETTINGS_PATH
            assert bundle_root.resolve() == config.APP_USER_DATA_ROOT
            assert bundle_root.resolve() / "prompts" == config.APP_PROMPTS_PATH
            assert settings_service.load_settings()["language"] == config.DEFAULT_LANGUAGE
            assert prompt_template_service.load_prompt("sample") == "Packaged prompt"
            assert misc_ui_controller.resolve_help_index_path("en") == (
                bundle_root.resolve() / "help" / "en" / "index.html"
            )
            assert misc_ui_controller.resolve_license_paths("ro") == (
                bundle_root.resolve() / "LICENSE_ro.txt",
                bundle_root.resolve() / "LICENSE_NC_ro.txt",
            )
            assert misc_ui_controller.current_application_version() == "9.8.7"
    finally:
        importlib.reload(config)
        importlib.reload(prompt_template_service)
        importlib.reload(misc_ui_controller)


def test_config_translation_languages_include_qwen3_tts_languages_with_chinese() -> None:
    """
    @brief      Verify shared language options include Qwen3 TTS languages, Romanian, and Chinese.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
    """
    language_codes = [language_code for language_code, _label in config.TRANSLATION_LANGUAGE_OPTIONS]

    assert language_codes == ["en", "ro", "ja", "ko", "zh", "de", "fr", "ru", "pt", "es", "it"]


def test_config_defines_seven_font_size_steps() -> None:
    """
    @brief      Verify the seven ordered UI font-size steps and their default.
    @details    Covers REQ-UX-7f2722c8-68e6-460b-a79a-1ee5577cadb5 / SPEC-FONT-STEPS.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    assert config.UI_FONT_SIZE_STEPS == (
        "extra_small",
        "small",
        "medium",
        "normal",
        "large",
        "very_large",
        "huge",
    )
    assert config.DEFAULT_UI_FONT_SIZE_STEP == "normal"
    assert config.DEFAULT_TEXT_FONT_SIZE_STEP == "normal"


def test_config_default_theme_is_audiomancer_dark() -> None:
    """
    @brief      Verify the default UI theme id is the AudioMancer brand dark theme.
    @details    Covers REQ-PLAT-2b9b91fe-a021-4e8e-a52b-9070926315ca / SPEC-SET-DEFAULTTHEME.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    assert config.DEFAULT_UI_THEME_ID == "audiomancer_dark"


# END OF FILE
