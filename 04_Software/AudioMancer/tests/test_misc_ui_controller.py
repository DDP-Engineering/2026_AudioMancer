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
@author Eng. Dan Dumitru Pasare
@date 2026-07-25
@version 0.1.0
"""

# IMPORTS

from PySide6.QtWidgets import QWidget

from audiomancer import config
from audiomancer.ui.controllers import misc_ui_controller


def test_play_completion_beep_emits_one_beep_when_enabled(monkeypatch, qtbot) -> None:
    """
    @brief      Verify an enabled completion-beep preference emits exactly one beep.
    @details    Covers REQ-FUNC-bdee3fe2-4f27-4e2e-a702-cb6abafbdd46 / S-BEEP-EMIT.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
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


# HELPER FUNCTIONS


def _build_window(qtbot, settings_payload) -> QWidget:
    """
    @brief      Build a window-like widget exposing one settings payload.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  settings_payload Settings payload attached to the widget.
    @return     Window-like QWidget test double.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    beeps: list[bool] = []
    monkeypatch.setattr(misc_ui_controller.QApplication, "beep", lambda: beeps.append(True))
    return beeps


# END OF FILE
