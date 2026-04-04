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
@version 0.1.1
"""

# IMPORTS

import pytest

import audiomancer.app as app_module

# DATA MODELS / TYPEDEFINITIONS


class _FakeApplication:
    """
    @brief      Lightweight QApplication fake for startup tests.
    @details    Captures bootstrap interactions without starting the real Qt
                event loop.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """

    def __init__(self, argv) -> None:
        """
        @brief      Initialize the fake application.
        @param[in]  argv Process argument list passed by the bootstrap.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-04
        @version    0.1.0
        """
        self.argv = argv
        self.application_name = None
        self.exec_called = False

    def setApplicationName(self, application_name: str) -> None:
        """
        @brief      Store the requested application name.
        @param[in]  application_name Application name set by the bootstrap.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-04
        @version    0.1.0
        """
        self.application_name = application_name

    def exec(self) -> int:
        """
        @brief      Simulate execution of the Qt event loop.
        @return     Fixed process exit code for assertions.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-04
        @version    0.1.0
        """
        self.exec_called = True
        return 123


class _FakeMainWindow:
    """
    @brief      Lightweight main-window fake for startup tests.
    @details    Records whether the bootstrap requests the window to be shown.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """

    def __init__(self) -> None:
        """
        @brief      Initialize the fake window.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-04
        @version    0.1.0
        """
        self.show_called = False

    def show(self) -> None:
        """
        @brief      Record that the bootstrap requested the window to be shown.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-04
        @version    0.1.0
        """
        self.show_called = True


# PUBLIC API


def test_main_creates_application_and_shows_window(monkeypatch) -> None:
    """
    @brief      Verify the application bootstrap creates and shows the UI shell.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.1
    """
    created = {}

    def _create_application(argv):
        created['application'] = _FakeApplication(argv)
        return created['application']

    def _create_window():
        created['window'] = _FakeMainWindow()
        return created['window']

    def _initialize_logging():
        created['initialize_logging_called'] = True
        return "fake-log-path"

    def _shutdown_logging():
        created['shutdown_logging_called'] = True

    def _get_component_logger(component_name, level_name=None):
        created['logger_request'] = (component_name, level_name)

        class _FakeLogger:
            def info(self, message, extra=None):
                created.setdefault('info_messages', []).append((message, extra))

            def exception(self, message, extra=None):
                created.setdefault('exception_messages', []).append((message, extra))

        return _FakeLogger()

    monkeypatch.setattr(app_module, 'initialize_logging', _initialize_logging)
    monkeypatch.setattr(app_module, 'shutdown_logging', _shutdown_logging)
    monkeypatch.setattr(app_module, 'get_component_logger', _get_component_logger)
    monkeypatch.setattr(app_module, 'QApplication', _create_application)
    monkeypatch.setattr(app_module, 'MainWindow', _create_window)

    exit_code = app_module.main()

    assert exit_code == 123
    assert created['initialize_logging_called'] is True
    assert created['shutdown_logging_called'] is True
    assert created['logger_request'] == ('app', None)
    assert created['application'].application_name == app_module.APPLICATION_NAME
    assert created['application'].exec_called is True
    assert created['window'].show_called is True


def test_main_logs_exception_and_shuts_down(monkeypatch) -> None:
    """
    @brief      Verify bootstrap exceptions are logged and still trigger shutdown.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.0
    """
    created = {}

    def _initialize_logging():
        created['initialize_logging_called'] = True
        return "fake-log-path"

    def _shutdown_logging():
        created['shutdown_logging_called'] = True

    def _get_component_logger(component_name, level_name=None):
        created['logger_request'] = (component_name, level_name)

        class _FakeLogger:
            def info(self, message, extra=None):
                created.setdefault('info_messages', []).append((message, extra))

            def exception(self, message, extra=None):
                created.setdefault('exception_messages', []).append((message, extra))

        return _FakeLogger()

    def _create_application(argv):
        raise RuntimeError("bootstrap failure")

    monkeypatch.setattr(app_module, 'initialize_logging', _initialize_logging)
    monkeypatch.setattr(app_module, 'shutdown_logging', _shutdown_logging)
    monkeypatch.setattr(app_module, 'get_component_logger', _get_component_logger)
    monkeypatch.setattr(app_module, 'QApplication', _create_application)

    with pytest.raises(RuntimeError, match="bootstrap failure"):
        app_module.main()

    assert created['initialize_logging_called'] is True
    assert created['shutdown_logging_called'] is True
    assert created['logger_request'] == ('app', None)
    assert created['exception_messages'][0][1]['event'] == 'fatal-bootstrap-error'


# END OF FILE
