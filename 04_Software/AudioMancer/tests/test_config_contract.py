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
    assert config.CLEANUP_DOCUMENT_FILE_NAME == "cleanup.json"
    assert config.CHUNK_ARTIFACT_FILE_NAME == "chunks_text.json"
    assert config.TRANSLATED_CHUNKS_FILE_NAME == "translated_text.json"
    assert config.NARRATOR_VOICE_FILE_NAME == "narrator_voice.json"
    assert config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME == "speech_blocks.json"
    assert config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME == "audio_blocks"
    assert config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT == 512
    assert config.DEFAULT_TTS_OPERATION_TIMEOUT_SECONDS == config.DEFAULT_TTS_AUDIO_GENERATION_TIMEOUT_SECONDS


def test_config_omits_retired_scene_ambience_enablement_switch() -> None:
    """
    @brief      Verify configuration omits the retired global Scene Ambience switch.
    @details    Scene Ambience placement remains the authoritative configured policy.
    @return     None.
    @exception  None
    """
    assert not hasattr(config, "DEFAULT_SCENE_AMBIENCE_GENERATION_ENABLED")
    assert config.DEFAULT_SCENE_AMBIENCE_PLACEMENT in config.SCENE_AMBIENCE_PLACEMENT_OPTIONS


def test_config_omits_retired_component_logging_overrides() -> None:
    """
    @brief      Verify configuration omits the inert per-component logging surface.
    @details    The global default remains a supported logging level.
    @return     None.
    @exception  None
    """
    assert not hasattr(config, "DEFAULT_LOG_LEVEL_OVERRIDES")
    assert not hasattr(config, "AVAILABLE_LOG_COMPONENTS")
    assert config.DEFAULT_LOG_LEVEL in config.LOG_LEVEL_OPTIONS


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


def test_config_module_initializes_from_one_level_frozen_runtime_root(monkeypatch) -> None:
    """
    @brief      Verify a shallow frozen runtime cannot exhaust available parents at import.
    @details    Executes the real configuration module initializer with a synthetic
                one-level application root, matching portable layouts such as
                `D:\\AudioMancer` or `/AudioMancer` without requiring root access.
                Covers REQ-PLAT-7cd89b15.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    """
    config_source_path = Path(config.__file__).resolve()
    shallow_runtime_root = Path(config_source_path.anchor) / "AudioMancer"
    shallow_config_path = shallow_runtime_root / "_internal" / config.PACKAGE_NAME / "config.py"
    module_globals = {
        "__file__": str(shallow_config_path),
        "__name__": "audiomancer._shallow_config_probe",
        "__package__": "audiomancer",
    }
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(shallow_runtime_root / "_internal"), raising=False)
    monkeypatch.setattr(sys, "executable", str(shallow_runtime_root / "AudioMancer.exe"))
    monkeypatch.setenv("AUDIOMANCER_DATA_DIR", str(shallow_runtime_root / "data"))

    exec(compile(config_source_path.read_bytes(), str(shallow_config_path), "exec"), module_globals)

    assert module_globals["APP_ROOT"] == shallow_runtime_root
    assert module_globals["APP_HELP_INDEX_RELATIVE_PATHS"] == {
        "en": Path("help") / "en" / "index.html",
        "ro": Path("help") / "ro" / "index.html",
    }


def test_config_preserves_source_tree_help_paths() -> None:
    """
    @brief      Verify source-checkout Help paths retain their English and Romanian locations.
    @details    Covers REQ-PLAT-7cd89b15.
    @return     None.
    @exception  None.
    """
    source_root = config._source_tree_root_from_package(config.APP_PACKAGE_ROOT)

    assert source_root is not None
    documentation_root = source_root.parent.parent / "05_SoftwareDocu"
    expected_source_paths = {
        "en": documentation_root / "UserGuide" / "index.html",
        "ro": documentation_root / "UserGuide_ro" / "index.html",
    }
    assert expected_source_paths == config.APP_HELP_SOURCE_INDEX_PATHS
    assert expected_source_paths["en"] == config.APP_HELP_SOURCE_INDEX_PATH


def test_config_resolves_frozen_packaged_runtime_resources(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify PyInstaller resource lookup resolves files staged beside the executable.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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
    """
    language_codes = [language_code for language_code, _label in config.TRANSLATION_LANGUAGE_OPTIONS]

    assert language_codes == ["en", "ro", "ja", "ko", "zh", "de", "fr", "ru", "pt", "es", "it"]


def test_config_defines_seven_font_size_steps() -> None:
    """
    @brief      Verify the seven ordered UI font-size steps and their default.
    @details    Covers REQ-UX-7f2722c8-68e6-460b-a79a-1ee5577cadb5 / SPEC-FONT-STEPS.
    @return     None.
    @exception  None.
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


def test_config_resolves_user_documents_root_across_platforms(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify the documents root prefers the home documents folder and falls back to home.
    @details    Covers REQ-PLAT-b463cefd-a2a7-4f53-8450-7411960f44b2 / SPEC-DOCS-ROOT.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    """
    home_root = tmp_path / "home"
    documents_root = home_root / "Documents"
    documents_root.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home_root))
    monkeypatch.setenv("USERPROFILE", str(home_root))
    monkeypatch.delenv("XDG_DOCUMENTS_DIR", raising=False)

    for platform_name in ("win32", "darwin", "linux"):
        monkeypatch.setattr(config.sys, "platform", platform_name)
        assert config.resolve_user_documents_root() == documents_root.resolve()

    documents_root.rmdir()

    for platform_name in ("win32", "darwin", "linux"):
        monkeypatch.setattr(config.sys, "platform", platform_name)
        assert config.resolve_user_documents_root() == home_root.resolve()


def test_config_user_documents_root_honours_xdg_documents_dir_on_posix_only(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify XDG_DOCUMENTS_DIR wins on POSIX only, and only when it names an existing folder.
    @details    Covers REQ-PLAT-b463cefd-a2a7-4f53-8450-7411960f44b2 / SPEC-DOCS-ROOT.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    """
    home_root = tmp_path / "home"
    documents_root = home_root / "Documents"
    xdg_root = tmp_path / "xdg_documents"
    documents_root.mkdir(parents=True)
    xdg_root.mkdir()
    monkeypatch.setenv("HOME", str(home_root))
    monkeypatch.setenv("USERPROFILE", str(home_root))
    monkeypatch.setenv("XDG_DOCUMENTS_DIR", str(xdg_root))

    monkeypatch.setattr(config.sys, "platform", "linux")
    assert config.resolve_user_documents_root() == xdg_root.resolve()

    for ignoring_platform_name in ("win32", "darwin"):
        monkeypatch.setattr(config.sys, "platform", ignoring_platform_name)
        assert config.resolve_user_documents_root() == documents_root.resolve()

    monkeypatch.setattr(config.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DOCUMENTS_DIR", "   ")
    assert config.resolve_user_documents_root() == documents_root.resolve()

    monkeypatch.setenv("XDG_DOCUMENTS_DIR", str(tmp_path / "missing_documents"))
    assert config.resolve_user_documents_root() == documents_root.resolve()


def test_config_default_theme_is_audiomancer_dark() -> None:
    """
    @brief      Verify the default UI theme id is the AudioMancer brand dark theme.
    @details    Covers REQ-PLAT-2b9b91fe-a021-4e8e-a52b-9070926315ca / SPEC-SET-DEFAULTTHEME.
    @return     None.
    @exception  None.
    """
    assert config.DEFAULT_UI_THEME_ID == "audiomancer_dark"


# END OF FILE
