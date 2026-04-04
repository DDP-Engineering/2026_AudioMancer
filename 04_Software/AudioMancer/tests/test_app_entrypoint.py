#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_app_entrypoint.py
@brief Startup tests for the AudioMancer application bootstrap.
@details Uses lightweight fakes to verify that the main entrypoint wires the
         Qt application and main window correctly.
@author Eng. Dan Dumitru Pasare
@date 2026-04-04
@version 0.1.0
"""

# IMPORTS

import audiomancer.app as app_module

# DATA MODELS / TYPEDEFINITIONS


class _FakeApplication:
    """@brief Lightweight QApplication fake for startup tests."""

    def __init__(self, argv) -> None:
        self.argv = argv
        self.application_name = None
        self.exec_called = False

    def setApplicationName(self, application_name: str) -> None:
        self.application_name = application_name

    def exec(self) -> int:
        self.exec_called = True
        return 123


class _FakeMainWindow:
    """@brief Lightweight main-window fake for startup tests."""

    def __init__(self) -> None:
        self.show_called = False

    def show(self) -> None:
        self.show_called = True


# PUBLIC API


def test_main_creates_application_and_shows_window(monkeypatch) -> None:
    """
    @brief Verify the application bootstrap creates and shows the UI shell.
    @param[in] monkeypatch Pytest monkeypatch fixture.
    @return None.
    @version 0.1.0
    """
    created = {}

    def _create_application(argv):
        created['application'] = _FakeApplication(argv)
        return created['application']

    def _create_window():
        created['window'] = _FakeMainWindow()
        return created['window']

    monkeypatch.setattr(app_module, 'QApplication', _create_application)
    monkeypatch.setattr(app_module, 'MainWindow', _create_window)

    exit_code = app_module.main()

    assert exit_code == 123
    assert created['application'].application_name == app_module.APPLICATION_NAME
    assert created['application'].exec_called is True
    assert created['window'].show_called is True


# END OF FILE
