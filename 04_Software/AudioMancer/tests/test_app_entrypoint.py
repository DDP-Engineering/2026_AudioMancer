#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
         Qt application and main window correctly, including when logging
         degraded to console-only output.
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
    """

    def __init__(self, argv) -> None:
        """
        @brief      Initialize the fake application.
        @param[in]  argv Process argument list passed by the bootstrap.
        @return     None.
        @exception  None
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
        """
        self.application_name = application_name

    def setWindowIcon(self, _window_icon) -> None:
        """
        @brief      Accept the application icon configured by the bootstrap.
        @param[in]  _window_icon Ignored Qt icon object.
        @return     None.
        @exception  None
        """
        return None

    def exec(self) -> int:
        """
        @brief      Simulate execution of the Qt event loop.
        @return     Fixed process exit code for assertions.
        @exception  None
        """
        self.exec_called = True
        return 123


class _FakeMainWindow:
    """
    @brief      Lightweight main-window fake for startup tests.
    @details    Records whether the bootstrap requests the window to be shown.
    @exception  None
    """

    def __init__(self) -> None:
        """
        @brief      Initialize the fake window.
        @return     None.
        @exception  None
        """
        self.show_called = False

    def show(self) -> None:
        """
        @brief      Record that the bootstrap requested the window to be shown.
        @return     None.
        @exception  None
        """
        self.show_called = True


# PUBLIC API


def test_main_creates_application_and_shows_window(monkeypatch) -> None:
    """
    @brief      Verify the application bootstrap creates and shows the UI shell.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    created = {}

    def _create_application(argv):
        """
        @brief      Create one fake Qt application instance.
        @param[in]  argv Process argument vector.
        @return     Fake application instance.
        @exception  None
        """
        created["application"] = _FakeApplication(argv)
        return created["application"]

    def _create_window(*args, **kwargs):
        """
        @brief      Create one fake main window and capture the input payload.
        @param[in]  args Ignored positional arguments.
        @param[in]  kwargs Window-construction keyword arguments.
        @return     Fake main window instance.
        @exception  None
        """
        created["window_settings_payload"] = kwargs.get("settings_payload")
        created["window"] = _FakeMainWindow()
        return created["window"]

    def _initialize_logging():
        """
        @brief      Record one fake logging bootstrap call.
        @return     Fake log-path marker.
        @exception  None
        """
        created["initialize_logging_called"] = True
        return "fake-log-path"

    def _shutdown_logging():
        """
        @brief      Record one fake logging shutdown call.
        @return     None.
        @exception  None
        """
        created["shutdown_logging_called"] = True

    def _get_component_logger(component_name, level_name=None):
        """
        @brief      Return one fake component logger for the bootstrap test.
        @param[in]  component_name Requested component name.
        @param[in]  level_name Optional requested level override.
        @return     Fake logger instance.
        @exception  None
        """
        created["logger_request"] = (component_name, level_name)

        class _FakeLogger:
            """
            @brief      Minimal logger fake used by the bootstrap tests.
            """

            def info(self, message, extra=None):
                """
                @brief      Record one info log event.
                @param[in]  message Logged message text.
                @param[in]  extra Optional structured extras.
                @return     None.
                @exception  None
                """
                created.setdefault("info_messages", []).append((message, extra))

            def exception(self, message, extra=None):
                """
                @brief      Record one exception log event.
                @param[in]  message Logged message text.
                @param[in]  extra Optional structured extras.
                @return     None.
                @exception  None
                """
                created.setdefault("exception_messages", []).append((message, extra))

        return _FakeLogger()

    def _load_settings():
        """
        @brief      Return one fake loaded settings payload.
        @return     Loaded settings payload.
        @exception  None
        """
        created["load_settings_called"] = True
        created["loaded_settings_payload"] = {
            "language": "en",
            "ui_scroll_steps_per_wheel_notch": 3,
        }
        return created["loaded_settings_payload"]

    monkeypatch.setattr(app_module, "initialize_logging", _initialize_logging)
    monkeypatch.setattr(app_module, "shutdown_logging", _shutdown_logging)
    monkeypatch.setattr(app_module, "get_component_logger", _get_component_logger)
    monkeypatch.setattr(app_module, "load_settings", _load_settings)
    monkeypatch.setattr(app_module, "QApplication", _create_application)
    monkeypatch.setattr(app_module, "QIcon", lambda _path: object())
    monkeypatch.setattr(app_module, "MainWindow", _create_window)
    monkeypatch.setattr(
        app_module.ui_state_service,
        "apply_theme",
        lambda application, theme_payload, scale: created.setdefault(
            "theme_application",
            (application, theme_payload, scale),
        ),
    )
    monkeypatch.setattr(
        app_module.ui_scroll_service,
        "install_global_scroll_step_filter",
        lambda application, scroll_steps: created.setdefault("scroll_filter", (application, scroll_steps)),
    )

    exit_code = app_module.main()

    assert exit_code == 123
    assert created["initialize_logging_called"] is True
    assert created["load_settings_called"] is True
    assert created["shutdown_logging_called"] is True
    assert created["logger_request"] == ("app", None)
    assert created["window_settings_payload"] == {
        "language": "en",
        "ui_scroll_steps_per_wheel_notch": 3,
    }
    assert created["scroll_filter"] == (created["application"], 3)
    assert created["application"].application_name == app_module.APPLICATION_NAME
    assert created["theme_application"][0] is created["application"]
    assert created["application"].exec_called is True
    assert created["window"].show_called is True


def test_main_logs_exception_and_shuts_down(monkeypatch) -> None:
    """
    @brief      Verify bootstrap exceptions are logged and still trigger shutdown.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    created = {}

    def _initialize_logging():
        """
        @brief      Record one fake logging bootstrap call.
        @return     Fake log-path marker.
        @exception  None
        """
        created["initialize_logging_called"] = True
        return "fake-log-path"

    def _shutdown_logging():
        """
        @brief      Record one fake logging shutdown call.
        @return     None.
        @exception  None
        """
        created["shutdown_logging_called"] = True

    def _get_component_logger(component_name, level_name=None):
        """
        @brief      Return one fake component logger for the failure path.
        @param[in]  component_name Requested component name.
        @param[in]  level_name Optional requested level override.
        @return     Fake logger instance.
        @exception  None
        """
        created["logger_request"] = (component_name, level_name)

        class _FakeLogger:
            """
            @brief      Minimal logger fake used by the failure-path test.
            """

            def info(self, message, extra=None):
                """
                @brief      Record one info log event.
                @param[in]  message Logged message text.
                @param[in]  extra Optional structured extras.
                @return     None.
                @exception  None
                """
                created.setdefault("info_messages", []).append((message, extra))

            def exception(self, message, extra=None):
                """
                @brief      Record one exception log event.
                @param[in]  message Logged message text.
                @param[in]  extra Optional structured extras.
                @return     None.
                @exception  None
                """
                created.setdefault("exception_messages", []).append((message, extra))

        return _FakeLogger()

    def _load_settings():
        """
        @brief      Return one fake loaded settings payload.
        @return     Loaded settings payload.
        @exception  None
        """
        created["load_settings_called"] = True
        created["loaded_settings_payload"] = {"language": "en"}
        return created["loaded_settings_payload"]

    def _create_application(argv):
        """
        @brief      Raise the fake bootstrap failure during app creation.
        @param[in]  argv Process argument vector.
        @return     None.
        @exception  RuntimeError Always raised for this test path.
        """
        raise RuntimeError("bootstrap failure")

    monkeypatch.setattr(app_module, "initialize_logging", _initialize_logging)
    monkeypatch.setattr(app_module, "shutdown_logging", _shutdown_logging)
    monkeypatch.setattr(app_module, "get_component_logger", _get_component_logger)
    monkeypatch.setattr(app_module, "load_settings", _load_settings)
    monkeypatch.setattr(app_module, "QApplication", _create_application)

    with pytest.raises(RuntimeError, match="bootstrap failure"):
        app_module.main()

    assert created["initialize_logging_called"] is True
    assert created["load_settings_called"] is True
    assert created["shutdown_logging_called"] is True
    assert created["logger_request"] == ("app", None)
    assert created["exception_messages"][0][1]["event"] == "fatal-bootstrap-error"


def test_main_reports_an_unavailable_log_file_when_logging_is_console_only(monkeypatch) -> None:
    """
    @brief      Verify the bootstrap survives console-only logging and reports it.
    @details    Covers REQ-NFR-d0afcd7a-79fd-4337-a2a9-713277e6411a / S-0004. A
                read-only installation directory makes initialize_logging return no
                path, which must neither crash main() nor be interpolated as None.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    created = {}

    def _initialize_logging():
        """
        @brief      Report that logging degraded to console output only.
        @return     None, matching a failed log-file creation.
        @exception  None
        """
        created["initialize_logging_called"] = True
        return None

    def _get_component_logger(component_name, level_name=None):
        """
        @brief      Return one fake component logger for the console-only path.
        @param[in]  component_name Requested component name.
        @param[in]  level_name Optional requested level override.
        @return     Fake logger instance.
        @exception  None
        """
        _ = (component_name, level_name)

        class _FakeLogger:
            """
            @brief      Minimal logger fake used by the console-only bootstrap test.
            """

            def info(self, message, extra=None):
                """
                @brief      Record one info log event.
                @param[in]  message Logged message text.
                @param[in]  extra Optional structured extras.
                @return     None.
                @exception  None
                """
                created.setdefault("info_messages", []).append((message, extra))

            def exception(self, message, extra=None):
                """
                @brief      Record one exception log event.
                @param[in]  message Logged message text.
                @param[in]  extra Optional structured extras.
                @return     None.
                @exception  None
                """
                created.setdefault("exception_messages", []).append((message, extra))

        return _FakeLogger()

    def _create_application(argv):
        """
        @brief      Raise a bootstrap failure so the log-file reference is emitted.
        @param[in]  argv Process argument vector.
        @return     None.
        @exception  RuntimeError Always raised for this test path.
        """
        _ = argv
        raise RuntimeError("bootstrap failure")

    monkeypatch.setattr(app_module, "initialize_logging", _initialize_logging)
    monkeypatch.setattr(app_module, "shutdown_logging", lambda: None)
    monkeypatch.setattr(app_module, "get_component_logger", _get_component_logger)
    monkeypatch.setattr(app_module, "load_settings", lambda: {"language": "en"})
    monkeypatch.setattr(app_module, "QApplication", _create_application)

    with pytest.raises(RuntimeError, match="bootstrap failure"):
        app_module.main()

    failure_message = created["exception_messages"][0][0]

    assert created["initialize_logging_called"] is True
    assert "None" not in failure_message
    assert "unavailable" in failure_message


# END OF FILE
