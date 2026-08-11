#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_misc_ui_controller.py
@brief Tests for the shared shell UI helpers.
@details Verifies the operator completion-beep emitter honors the persisted
         preference without producing an audible side effect during tests.
"""

# IMPORTS

from PySide6.QtWidgets import QMessageBox, QWidget

from audiomancer import config
from audiomancer.services import ui_state_service
from audiomancer.ui.controllers import misc_ui_controller


def test_confirm_question_preserves_dialog_arguments_and_boolean_semantics(monkeypatch) -> None:
    """
    @brief      Verify the shared confirmation owns exact localization, defaults, and decisions.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    window = object()
    questions: list[tuple[object, ...]] = []
    translations: list[tuple[str, str]] = []
    decisions = iter(
        (
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
    )
    monkeypatch.setattr(
        misc_ui_controller.ui_state_service,
        "translate",
        lambda key, language: translations.append((key, language)) or f"{language}:{key}",
    )
    monkeypatch.setattr(
        misc_ui_controller.QMessageBox,
        "question",
        lambda *args: questions.append(args) or next(decisions),
    )

    outcomes = [
        misc_ui_controller.confirm_question(window, "ro", "title.key", "message.key")
        for _index in range(3)
    ]

    assert outcomes == [False, False, True]
    assert translations == [("title.key", "ro"), ("message.key", "ro")] * 3
    assert questions == [
        (
            window,
            "ro:title.key",
            "ro:message.key",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
    ] * 3


def test_confirm_question_propagates_translation_error_before_showing_dialog(monkeypatch) -> None:
    """
    @brief      Verify translation failures remain visible and do not open a partial dialog.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  RuntimeError Expected translation failure.
    """
    questions: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        misc_ui_controller.ui_state_service,
        "translate",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("translation failed")),
    )
    monkeypatch.setattr(
        misc_ui_controller.QMessageBox,
        "question",
        lambda *args: questions.append(args),
    )

    try:
        misc_ui_controller.confirm_question(object(), "en", "title.key", "message.key")
    except RuntimeError as error:
        assert str(error) == "translation failed"
    else:
        raise AssertionError("translation failure should propagate")

    assert questions == []


def test_play_completion_beep_emits_one_beep_when_enabled(monkeypatch, qtbot) -> None:
    """
    @brief      Verify an enabled completion-beep preference emits exactly one beep.
    @details    Covers REQ-FUNC-bdee3fe2-4f27-4e2e-a702-cb6abafbdd46 / S-BEEP-EMIT.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    window = _build_window(qtbot, {"play_completion_beep": True})
    beeps = _record_beeps(monkeypatch)

    misc_ui_controller.play_completion_beep(window)

    assert len(beeps) == 1


def test_play_completion_beep_stays_silent_for_disabled_or_missing_preference(monkeypatch, qtbot) -> None:
    """
    @brief      Verify a disabled, defaulted, or absent preference produces no beep.
    @details    Covers REQ-FUNC-337ba16d-5990-4f3c-be79-18964d53036f / S-BEEP-EMIT.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    assert config.DEFAULT_PLAY_COMPLETION_BEEP is False
    beeps = _record_beeps(monkeypatch)

    misc_ui_controller.play_completion_beep(_build_window(qtbot, {"play_completion_beep": False}))
    misc_ui_controller.play_completion_beep(_build_window(qtbot, {}))
    misc_ui_controller.play_completion_beep(_build_window(qtbot, None))

    window_without_settings = QWidget()
    qtbot.addWidget(window_without_settings)
    misc_ui_controller.play_completion_beep(window_without_settings)

    assert beeps == []


def test_create_progress_dialog_applies_window_language_before_start(qtbot) -> None:
    """
    @brief      Verify the shared production factory localizes before displaying progress.
    @details    Covers REQ-FUNC-84c50360 with the factory used by every production
                caller rather than a direct dialog-only language call.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    """
    window = _build_window(qtbot, {"language": "ro"})

    misc_ui_controller.create_progress_dialog(
        window,
        "Traducere",
        "Se pregateste",
        lambda: None,
    )
    dialog = window._operation_progress_dialog  # noqa: SLF001

    assert dialog is not None
    assert dialog.windowTitle() == ui_state_service.translate(
        "dialog.operation_progress_title", "ro"
    ).format(operation_name="Traducere")
    assert dialog._cancel_button.text() == ui_state_service.translate(  # noqa: SLF001
        "dialog.operation_progress_cancel", "ro"
    )

    misc_ui_controller.update_progress_dialog(
        window,
        50,
        "In lucru",
        {"input_tokens": 1200, "output_tokens": 34, "total_tokens": 1234, "usage_available": True},
    )

    assert dialog._token_usage_label.text() == ui_state_service.translate(  # noqa: SLF001
        "dialog.operation_progress_token_usage", "ro"
    ).format(input_tokens="1,200", output_tokens="34", total_tokens="1,234")

    misc_ui_controller.clear_progress_dialog(window)

    assert window._operation_progress_dialog is None  # noqa: SLF001

    window._settings_payload = {"language": "en"}  # noqa: SLF001
    misc_ui_controller.create_progress_dialog(window, "Translation", "Preparing", lambda: None)
    english_dialog = window._operation_progress_dialog  # noqa: SLF001

    assert english_dialog is not None
    assert english_dialog.windowTitle() == "Translation In Progress"
    assert english_dialog._cancel_button.text() == "Cancel Operation"  # noqa: SLF001


def test_create_progress_dialog_defaults_to_english_without_settings_payload(qtbot) -> None:
    """
    @brief      Verify incomplete window doubles retain the helper's safe language fallback.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    """
    window = QWidget()
    qtbot.addWidget(window)
    window._operation_progress_dialog = None  # noqa: SLF001

    misc_ui_controller.create_progress_dialog(window, "Translation", "Preparing", lambda: None)

    assert window._operation_progress_dialog.windowTitle() == "Translation In Progress"  # noqa: SLF001


def test_progress_update_without_usage_preserves_displayed_token_summary(qtbot) -> None:
    """Verify ordinary progress ticks do not clear a prior token-usage summary."""
    window = _build_window(qtbot, {"language": "en"})
    misc_ui_controller.create_progress_dialog(window, "Translation", "Preparing", lambda: None)
    dialog = window._operation_progress_dialog  # noqa: SLF001
    usage = {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15, "usage_available": True}
    misc_ui_controller.update_progress_dialog(window, 25, "Model work", usage)
    expected_text = dialog._token_usage_label.text()  # noqa: SLF001

    misc_ui_controller.update_progress_dialog(window, 50, "Saving")

    assert dialog._token_usage_label.text() == expected_text  # noqa: SLF001


def test_clear_progress_dialog_destroys_and_clears_the_shared_reference(qtbot) -> None:
    """
    @brief      Verify terminal runner cleanup can destroy and clear the shared dialog.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    """
    window = _build_window(qtbot, {"language": "en"})
    misc_ui_controller.create_progress_dialog(window, "Operation", "Running", lambda: None)

    misc_ui_controller.clear_progress_dialog(window)

    assert window._operation_progress_dialog is None  # noqa: SLF001


# HELPER FUNCTIONS


def _build_window(qtbot, settings_payload) -> QWidget:
    """
    @brief      Build a window-like widget exposing one settings payload.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  settings_payload Settings payload attached to the widget.
    @return     Window-like QWidget test double.
    @exception  None
    """
    window = QWidget()
    qtbot.addWidget(window)
    window._settings_payload = settings_payload  # noqa: SLF001
    return window


def _record_beeps(monkeypatch) -> list[bool]:
    """
    @brief      Replace the Qt beep call with a silent recorder.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     Recorded beep invocations.
    @exception  None
    """
    beeps: list[bool] = []
    monkeypatch.setattr(misc_ui_controller.QApplication, "beep", lambda: beeps.append(True))
    return beeps


# END OF FILE
