#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_operation_runner_controller.py
@brief Tests for the shared threaded modal-operation runner.
@details Verifies success, failure, cancellation, progress delivery, and active
         operation cleanup without showing real modal progress dialogs.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.2.0
"""

# IMPORTS

from threading import Event
from time import sleep

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QWidget

from audiomancer.services import operation_runtime_service
from audiomancer.ui.controllers import operation_runner_controller


class _FakeProgressDialog:
    """
    @brief      Minimal progress-dialog double used by runner tests.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """

    def __init__(self, message: str) -> None:
        """
        @brief      Store the initial status message.
        @param[in]  message Initial progress status message.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        self._message = message

    def status_message(self) -> str:
        """
        @brief      Return the current status message.
        @return     Current status message.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        return self._message

    def set_status_message(self, message: str) -> None:
        """
        @brief      Store a new status message.
        @param[in]  message New progress status message.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        self._message = message


def test_threaded_operation_success_reports_progress_and_cleans_up(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify successful worker execution updates progress and clears runner state.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Temporary project root fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    window = _build_runner_window(qtbot, tmp_path)
    events = _patch_progress_dialog(monkeypatch)
    busy_states: list[bool] = []
    results: list[object] = []

    def worker(project_root, manifest, progress_callback=None, cancel_requested=None):
        """
        @brief      Provide the worker test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        assert QThread.currentThread() != window.thread()
        assert project_root == tmp_path
        assert manifest == {"project": "test"}
        assert cancel_requested is not None
        progress_callback(1, 2, 50, "half")
        return {"ok": True}

    operation_runner_controller.start_threaded_operation(
        window,
        "kind",
        "Name",
        "starting",
        worker,
        set_busy=busy_states.append,
        success_handler=lambda result: _append_on_ui_thread(window, results, result),
        failure_handler=lambda error: None,
        cancel_handler=lambda message: None,
    )

    qtbot.waitUntil(lambda: window._active_operation_kind is None, timeout=3000)

    assert busy_states == [True, False]
    assert results == [{"ok": True}]
    assert ("update", 50, "half") in events
    assert ("finish",) in events
    _assert_runner_state_cleared(window)


def test_threaded_operation_failure_calls_failure_handler_and_cleans_up(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify failed worker execution calls the failure handler and clears runner state.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Temporary project root fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    window = _build_runner_window(qtbot, tmp_path)
    events = _patch_progress_dialog(monkeypatch)
    failures: list[str] = []

    def worker(project_root, manifest, progress_callback=None, cancel_requested=None):
        """
        @brief      Provide the worker test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        assert QThread.currentThread() != window.thread()
        _ = project_root
        _ = manifest
        _ = progress_callback
        _ = cancel_requested
        raise RuntimeError("boom")

    operation_runner_controller.start_threaded_operation(
        window,
        "kind",
        "Name",
        "starting",
        worker,
        set_busy=lambda is_busy: None,
        success_handler=lambda result: None,
        failure_handler=lambda error: _append_on_ui_thread(window, failures, str(error)),
        cancel_handler=lambda message: None,
    )

    qtbot.waitUntil(lambda: window._active_operation_kind is None, timeout=3000)

    assert failures == ["boom"]
    assert ("fail", "boom") in events
    _assert_runner_state_cleared(window)


def test_threaded_operation_cancel_sets_event_and_calls_cancel_handler(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify cancellation sets the event observed by the worker and clears runner state.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Temporary project root fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    window = _build_runner_window(qtbot, tmp_path)
    events = _patch_progress_dialog(monkeypatch)
    worker_started = Event()
    cancellations: list[str] = []

    def worker(project_root, manifest, progress_callback=None, cancel_requested=None):
        """
        @brief      Provide the worker test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        assert QThread.currentThread() != window.thread()
        _ = project_root
        _ = manifest
        _ = progress_callback
        assert cancel_requested is not None
        worker_started.set()
        for _index in range(200):
            if cancel_requested():
                raise operation_runtime_service.OperationCancelledError("cancelled")
            sleep(0.005)
        raise AssertionError("worker did not observe cancellation")

    operation_runner_controller.start_threaded_operation(
        window,
        "kind",
        "Name",
        "starting",
        worker,
        set_busy=lambda is_busy: None,
        success_handler=lambda result: None,
        failure_handler=lambda error: None,
        cancel_handler=lambda message: _append_on_ui_thread(window, cancellations, message),
    )

    qtbot.waitUntil(worker_started.is_set, timeout=3000)
    operation_runner_controller.request_operation_cancel(window)
    qtbot.waitUntil(lambda: window._active_operation_kind is None, timeout=3000)

    assert cancellations == ["cancelled"]
    assert ("fail", "cancelled") in events
    _assert_runner_state_cleared(window)


def test_threaded_operation_does_not_start_when_operation_is_active(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify runner preserves single active-operation behavior.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Temporary project root fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    window = _build_runner_window(qtbot, tmp_path)
    _patch_progress_dialog(monkeypatch)
    window._active_operation_kind = "busy"
    calls: list[bool] = []

    operation_runner_controller.start_threaded_operation(
        window,
        "kind",
        "Name",
        "starting",
        lambda project_root, manifest, progress_callback=None, cancel_requested=None: calls.append(True),
        set_busy=lambda is_busy: calls.append(is_busy),
        success_handler=lambda result: None,
        failure_handler=lambda error: None,
        cancel_handler=lambda message: None,
    )

    assert calls == []
    assert window._active_operation_kind == "busy"


def _build_runner_window(qtbot, project_root) -> QWidget:
    """
    @brief      Build a QWidget with the operation attributes used by the runner.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  project_root Active project root path.
    @return     Window-like QWidget test double.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    window = QWidget()
    qtbot.addWidget(window)
    window._current_project_root = project_root  # noqa: SLF001
    window._current_manifest = {"project": "test"}  # noqa: SLF001
    window._active_operation_kind = None  # noqa: SLF001
    window._active_operation_name = None  # noqa: SLF001
    window._operation_cancel_requested = False  # noqa: SLF001
    window._operation_cancel_event = None  # noqa: SLF001
    window._active_operation_thread = None  # noqa: SLF001
    window._active_operation_worker = None  # noqa: SLF001
    window._active_operation_ui_bridge = None  # noqa: SLF001
    window._operation_progress_dialog = None  # noqa: SLF001
    return window


def _patch_progress_dialog(monkeypatch) -> list[tuple]:
    """
    @brief      Replace progress-dialog helpers with recording test doubles.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     Recorded progress-dialog events.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    events: list[tuple] = []
    misc_ui_controller = operation_runner_controller.misc_ui_controller

    def create_progress_dialog(window, operation_name, initial_message, cancel_callback, cancellable=True):
        """
        @brief      Provide the create progress dialog test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        assert QThread.currentThread() == window.thread()
        _ = operation_name
        _ = cancel_callback
        _ = cancellable
        window._operation_progress_dialog = _FakeProgressDialog(initial_message)  # noqa: SLF001
        events.append(("create", initial_message))

    def update_progress_dialog(window, percent, message, token_usage=None):
        """
        @brief      Provide the update progress dialog test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        assert QThread.currentThread() == window.thread()
        _ = token_usage
        if window._operation_progress_dialog is not None:  # noqa: SLF001
            window._operation_progress_dialog.set_status_message(message)  # noqa: SLF001
        events.append(("update", percent, message))

    def finish_progress_dialog(window):
        """
        @brief      Provide the finish progress dialog test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        assert QThread.currentThread() == window.thread()
        _ = window
        events.append(("finish",))

    def fail_progress_dialog(window, message):
        """
        @brief      Provide the fail progress dialog test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        assert QThread.currentThread() == window.thread()
        _ = window
        events.append(("fail", message))

    def clear_progress_dialog(window):
        """
        @brief      Provide the clear progress dialog test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        assert QThread.currentThread() == window.thread()
        window._operation_progress_dialog = None  # noqa: SLF001
        events.append(("clear",))

    monkeypatch.setattr(misc_ui_controller, "create_progress_dialog", create_progress_dialog)
    monkeypatch.setattr(misc_ui_controller, "update_progress_dialog", update_progress_dialog)
    monkeypatch.setattr(misc_ui_controller, "finish_progress_dialog", finish_progress_dialog)
    monkeypatch.setattr(misc_ui_controller, "fail_progress_dialog", fail_progress_dialog)
    monkeypatch.setattr(misc_ui_controller, "clear_progress_dialog", clear_progress_dialog)
    return events


def _assert_runner_state_cleared(window: QWidget) -> None:
    """
    @brief      Assert active operation fields are cleared after thread finish.
    @param[in]  window Window-like QWidget test double.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    assert window._active_operation_kind is None  # noqa: SLF001
    assert window._active_operation_name is None  # noqa: SLF001
    assert window._operation_cancel_requested is False  # noqa: SLF001
    assert window._operation_cancel_event is None  # noqa: SLF001
    assert window._active_operation_thread is None  # noqa: SLF001
    assert window._active_operation_worker is None  # noqa: SLF001
    assert window._active_operation_ui_bridge is None  # noqa: SLF001
    assert window._operation_progress_dialog is None  # noqa: SLF001


def _append_on_ui_thread(window: QWidget, target: list, value: object) -> None:
    """
    @brief      Append one value only after verifying UI-thread execution.
    @param[in]  window Window-like QWidget test double.
    @param[in]  target Target list.
    @param[in]  value Value to append.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    assert QThread.currentThread() == window.thread()
    target.append(value)


# END OF FILE
