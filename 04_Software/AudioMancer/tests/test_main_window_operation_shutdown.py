#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_main_window_operation_shutdown.py
@brief Main-window shutdown tests for active threaded operations.
@details Verifies close handling requests cooperative cancellation and keeps the
         shell alive while a worker thread is still cleaning up.
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.1.0
"""

# IMPORTS

from threading import Event

from PySide6.QtGui import QCloseEvent

from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import operation_runner_controller
from audiomancer.ui.main_window import MainWindow


def test_main_window_close_ignores_event_while_operation_thread_is_active(
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify closing requests cancellation but keeps the window alive while a worker remains active.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Baseline application settings fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ShutdownOperationProject", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, manifest)
    window._operation_shutdown_wait_timeout_ms = 25

    worker_started = Event()
    worker_release = Event()
    success_payloads: list[object] = []

    def _blocking_worker(_project_root, _manifest, progress_callback=None, cancel_requested=None):
        """
        @brief      Provide the blocking worker test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        _ = progress_callback
        _ = cancel_requested
        worker_started.set()
        worker_release.wait(timeout=2.0)
        return {"status": "released"}

    operation_runner_controller.start_threaded_operation(
        window,
        operation_kind="chunking",
        operation_name="Blocking Operation",
        initial_message="Waiting...",
        worker_callable=_blocking_worker,
        set_busy=lambda _busy: None,
        success_handler=success_payloads.append,
        failure_handler=lambda error: (_ for _ in ()).throw(error),
        cancel_handler=lambda _message: None,
        cancellable=True,
    )

    assert worker_started.wait(timeout=1.0)
    assert not window._action_new_project.isEnabled()
    assert not window._action_open_project.isEnabled()

    close_event = QCloseEvent()
    window.closeEvent(close_event)

    assert not close_event.isAccepted()
    assert window._operation_cancel_requested is True
    assert window._operation_cancel_event is not None
    assert window._operation_cancel_event.is_set()
    assert window._active_operation_thread is not None

    worker_release.set()
    qtbot.waitUntil(lambda: window._active_operation_thread is None, timeout=1500)

    assert success_payloads == [{"status": "released"}]
    assert window._action_new_project.isEnabled()
    assert window._action_open_project.isEnabled()


# END OF FILE
