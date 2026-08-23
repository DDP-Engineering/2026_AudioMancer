#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ui_localization_coverage.py
@brief Focused coverage for app-owned English and Romanian UI text bindings.
@details Verifies the localization gaps found by the complete window/page/dialog
         audit without launching the full application test suite.
"""

# IMPORTS

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from audiomancer.services import ai_translation_service, ui_scroll_service, ui_state_service
from audiomancer.ui.controllers import settings_ui_controller
from audiomancer.ui.pages.ai_settings_page import AiSettingsPage
from audiomancer.ui.pages.ai_translation_page import AiTranslationPage
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

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_UI_ROOT = _REPOSITORY_ROOT / "05_Software" / "AudioMancer" / "src" / "audiomancer" / "ui"

# PUBLIC API


def test_settings_page_localizes_all_visible_text_and_preserves_option_data(qtbot) -> None:
    """
    @brief      Verify the complete Settings surface switches to Romanian.
    @details    Covers S-0005 and REQ-UX-aa109e16-4c45-4fb8-886c-008ade7260eb.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    page.load_settings(
        {
            "language": "ro",
            "ui_theme_id": "high_contrast",
            "ui_font_size_step": "normal",
            "text_font_size_step": "very_large",
        }
    )
    page.apply_language("ro")

    assert page._ui_font_size_label.text() == "Marime font UI"
    assert page._text_font_size_label.text() == "Marime font text"
    assert page._preview_label.text() == "Text exemplu"
    assert page._preview_button.text() == "Buton exemplu"
    assert page._preview_input.toPlainText() == "Fereastra text exemplu"
    assert _combo_labels(page._language_combo) == ["Engleza", "Romana"]
    assert [page._language_combo.itemData(index) for index in range(page._language_combo.count())] == ["en", "ro"]
    assert page._language_combo.currentData() == "ro"
    assert page._theme_combo.itemText(page._theme_combo.findData("high_contrast")) == "Contrast Ridicat"
    assert page._ui_font_size_combo.itemText(page._ui_font_size_combo.findData("extra_small")) == "Foarte mica"
    assert page._ui_font_size_combo.itemText(page._ui_font_size_combo.findData("very_large")) == "Foarte mare"
    assert page._theme_combo.currentData() == "high_contrast"
    assert page._ui_font_size_combo.currentData() == "normal"
    assert page._text_font_size_combo.currentData() == "very_large"


def test_each_persistent_page_localizes_audited_visible_text(qtbot) -> None:
    """
    @brief      Verify every persistent page translates the text missed by its prior audit.
    @details    Covers S-0006 and REQ-UX-aa109e16-4c45-4fb8-886c-008ade7260eb.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    ai_settings_page = _romanian_page(qtbot, AiSettingsPage)
    assert _combo_labels(ai_settings_page._default_strategy_combo) == ["Paragraf", "Semnificatie", "Scena"]
    assert ai_settings_page._api_key_edit.placeholderText() == "optional pentru furnizor local"

    translation_page = _romanian_page(qtbot, AiTranslationPage)
    assert translation_page._profile_combo.itemText(0) == "(niciunul)"
    assert translation_page._original_language_value_label.text() == "Necunoscuta"
    assert translation_page._target_language_value_label.text() == "Engleza"
    assert translation_page._approved_progress_label.text() == "Segmente aprobate: 0/0"
    translation_page.set_translation_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Original"}],
        translated_chunks=[{"chunk_id": "chunk-0001", "translated_text": "Traducere", "approved": False}],
        notes=["Revizuieste traducerea."],
        original_language="English",
        target_language="ro",
        selected_profile_id=None,
        stage_status=ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING,
        translated_count=1,
        approved_count=0,
        total_count=1,
    )
    translation_page.apply_language("ro")
    assert translation_page._original_language_value_label.text() == "Engleza"
    assert translation_page._target_language_value_label.text() == "Romana"
    assert translation_page._approved_progress_label.text() == "Segmente aprobate: 0/1"
    assert translation_page._chunk_list.item(0).text().startswith("[Tradus]")

    home_page = _romanian_page(qtbot, HomeProjectPage)
    assert home_page._pipeline_group.title() == "Flux de Lucru"
    assert _combo_labels(home_page._target_language_combo) == [
        "Engleza",
        "Romana",
        "Germana",
        "Franceza",
        "Rusa",
        "Portugheza",
        "Spaniola",
        "Italiana",
    ]
    assert [home_page._target_language_combo.itemData(index) for index in range(8)] == [
        "en",
        "ro",
        "de",
        "fr",
        "ru",
        "pt",
        "es",
        "it",
    ]

    character_voices_page = _romanian_page(qtbot, CharacterVoicesPage)
    assert character_voices_page._title_label.text() == "<h2>Voci Personaje</h2>"
    assert character_voices_page._import_sample_button.text() == "Importa Mostra"
    assert character_voices_page._generate_sample_button.text() == "Genereaza Mostra"

    narator_voice_page = _romanian_page(qtbot, NaratorVoicePage)
    assert narator_voice_page._import_sample_button.text() == "Importa Mostra"
    assert narator_voice_page._generate_sample_button.text() == "Genereaza Mostra"

    speech_blocks_page = _romanian_page(qtbot, SpeechBlocksPage)
    assert speech_blocks_page._reset_generation_button.text() == "Reseteaza"

    chunking_page = _romanian_page(qtbot, TextChunkingPage)
    assert _combo_labels(chunking_page._strategy_combo) == ["Paragraf", "Semnificatie", "Scena"]

    cleanup_page = _romanian_page(qtbot, TextCleanupPage)
    assert cleanup_page._extracted_group.title() == "Previzualizare Text Extras"

    characters_page = _romanian_page(qtbot, CharactersPage)
    assert characters_page._title_label.text() == "<h2>Personaje</h2>"

    audio_blocks_page = _romanian_page(qtbot, AudioBlocksPage)
    assert audio_blocks_page._title_label.text() == "<h2>Blocuri Audio</h2>"

    tts_page = _romanian_page(qtbot, TtsSettingsPage)
    assert tts_page._preview_timeout_label.text() == "Timeout Preview Audio (s)"
    assert tts_page._generation_timeout_label.text() == "Timeout Generare Audio (s)"
    assert tts_page._scene_ambience_seed_spin.specialValueText() == "Aleatoriu"


def test_app_owned_dialog_calls_do_not_embed_operator_facing_literals() -> None:
    """
    @brief      Verify popup and progress APIs receive translated operator-facing text.
    @details    Covers S-0007 and REQ-UX-aa109e16-4c45-4fb8-886c-008ade7260eb.
    @return     None.
    @exception  None
    """
    findings: list[str] = []
    for source_path in sorted(_UI_ROOT.rglob("*.py")):
        source_text = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source_text)
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            findings.extend(_dialog_literal_findings(source_path, call))
            findings.extend(_operation_literal_findings(source_path, call))

    assert findings == []


def test_runtime_language_change_refreshes_current_project_page(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify applying UI settings rebuilds the visible project page in the new language.
    @details    Covers S-0008 and REQ-UX-aa109e16-4c45-4fb8-886c-008ade7260eb.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Temporary active project root.
    @return     None.
    @exception  None
    """
    refresh_current_page = Mock()
    apply_ui_settings = Mock()
    monkeypatch.setattr(ui_scroll_service, "install_global_scroll_step_filter", Mock())
    monkeypatch.setattr(ui_state_service, "apply_ui_settings", apply_ui_settings)
    manifest = {"project_id": "project-1"}
    window = SimpleNamespace(
        _settings_payload={
            "language": "ro",
            "ui_scroll_steps_per_wheel_notch": 3,
        },
        _current_project_root=tmp_path,
        _current_manifest=manifest,
        _refresh_current_page_state=refresh_current_page,
    )

    settings_ui_controller.apply_current_ui_settings(window)

    apply_ui_settings.assert_called_once()
    refresh_current_page.assert_called_once_with(tmp_path, manifest, "ro")


# TEST HELPERS


def _romanian_page(qtbot, page_type):
    """
    @brief      Build one page, register it with QtBot, and apply Romanian.
    @param[in]  qtbot Qt widget test helper.
    @param[in]  page_type Page class to instantiate.
    @return     Instantiated page using the Romanian catalog.
    @exception  None
    """
    page = page_type()
    qtbot.addWidget(page)
    page.apply_language("ro")
    return page


def _combo_labels(combo) -> list[str]:
    """Return every visible label in one combo box."""
    return [combo.itemText(index) for index in range(combo.count())]


def _dialog_literal_findings(source_path: Path, call: ast.Call) -> list[str]:
    """
    @brief      Find direct app-owned text literals passed to one Qt dialog call.
    @param[in]  source_path Path containing the parsed call.
    @param[in]  call Parsed Python call node.
    @return     Human-readable source locations and literal values.
    @exception  None
    """
    if not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name):
        return []
    owner_name = call.func.value.id
    method_name = call.func.attr
    if owner_name not in {"QMessageBox", "QInputDialog", "QFileDialog"}:
        return []
    if method_name not in {
        "critical",
        "getExistingDirectory",
        "getInt",
        "getItem",
        "getMultiLineText",
        "getOpenFileName",
        "getSaveFileName",
        "getText",
        "information",
        "question",
        "warning",
    }:
        return []
    return [
        f"{source_path.relative_to(_REPOSITORY_ROOT)}:{call.lineno}:{literal.value}"
        for literal in call.args[1:]
        if isinstance(literal, ast.Constant) and isinstance(literal.value, str) and literal.value.strip()
    ]


def _operation_literal_findings(source_path: Path, call: ast.Call) -> list[str]:
    """
    @brief      Find direct operation literals passed to start_operation.
    @param[in]  source_path Path containing the parsed call.
    @param[in]  call Parsed Python call node.
    @return     Human-readable source locations and literal values.
    @exception  None
    """
    function_name = ""
    if isinstance(call.func, ast.Name):
        function_name = call.func.id
    elif isinstance(call.func, ast.Attribute):
        function_name = call.func.attr
    if function_name != "start_operation" or len(call.args) < 4:
        return []
    return [
        f"{source_path.relative_to(_REPOSITORY_ROOT)}:{call.lineno}:{literal.value}"
        for literal in call.args[2:4]
        if isinstance(literal, ast.Constant) and isinstance(literal.value, str) and literal.value.strip()
    ]


# END OF FILE
