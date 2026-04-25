#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file operation_runner_controller.py
@brief Shared threaded modal-operation runner for AudioMancer UI controllers.
@details Runs long workflow service calls on a QThread while the Qt UI thread
         owns progress dialogs, cancellation requests, page busy state, and
         operation finalization callbacks.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.2.1
"""

# IMPORTS

from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal, Slot

from audiomancer.services import operation_runtime_service
from audiomancer.ui.controllers import misc_ui_controller

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


# PUBLIC API


class ThreadedOperationWorker(QObject):
    """
    @brief      Execute one long-running workflow operation on a worker thread.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """

    progress = Signal(object)
    succeeded = Signal(object)
    cancelled = Signal(str)
    failed = Signal(object)
    finished = Signal()

    def __init__(
        self,
        project_root: Path,
        manifest: dict[str, object],
        worker_callable,
        cancel_event: Event,
        parent=None,
    ) -> None:
        """
        @brief      Initialize the worker with immutable operation inputs.
        @param[in]  project_root Active project root.
        @param[in]  manifest Manifest snapshot passed to the service callable.
        @param[in]  worker_callable Callable that performs the operation.
        @param[in]  cancel_event Thread-safe cooperative cancellation flag.
        @param[in]  parent Optional parent object.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        super().__init__(parent)
        self._project_root = project_root
        self._manifest = dict(manifest)
        self._worker_callable = worker_callable
        self._cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        """
        @brief      Execute the service callable and emit terminal status.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        try:
            result_payload = self._worker_callable(
                self._project_root,
                dict(self._manifest),
                progress_callback=self._emit_progress,
                cancel_requested=self._cancel_event.is_set,
            )
        except operation_runtime_service.OperationCancelledError as error:
            self.cancelled.emit(str(error))
        except Exception as error:  # noqa: BLE001
            self.failed.emit(error)
        else:
            self.succeeded.emit(result_payload)
        finally:
            self.finished.emit()

    def _emit_progress(
        self,
        progress_current: int,
        progress_total: int,
        percent: int,
        message: str,
        token_usage=None,
    ) -> None:
        """
        @brief      Emit one UI-thread-safe progress payload.
        @param[in]  progress_current Completed work units.
        @param[in]  progress_total Total work units.
        @param[in]  percent Current progress percentage.
        @param[in]  message Operator-facing status message.
        @param[in]  token_usage Optional token usage payload.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-24
        @version    0.1.0
        """
        self.progress.emit(
            {
                "progress_current": progress_current,
                "progress_total": progress_total,
                "percent": percent,
                "message": message,
                "token_usage": token_usage,
            }
        )


class ThreadedOperationUiBridge(QObject):
    """
    @brief      Apply worker-thread operation signals on the Qt UI thread.
    @details    Owns the signal receiver slots in the main-window thread so
                progress and terminal callbacks never update widgets from the
                worker thread.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """

    def __init__(
        self,
        window: "MainWindow",
        set_busy,
        success_handler,
        failure_handler,
        cancel_handler,
        parent=None,
    ) -> None:
        """
        @brief      Initialize the UI-thread bridge callbacks.
        @param[in]  window Active main window.
        @param[in]  set_busy Callback accepting one boolean busy state.
        @param[in]  success_handler UI-thread callback for successful worker result.
        @param[in]  failure_handler UI-thread callback for raised exceptions.
        @param[in]  cancel_handler UI-thread callback for cooperative cancellation.
        @param[in]  parent Optional parent object.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        super().__init__(parent)
        self._window = window
        self._set_busy = set_busy
        self._success_handler = success_handler
        self._failure_handler = failure_handler
        self._cancel_handler = cancel_handler

    @Slot(object)
    def handle_progress(self, payload: object) -> None:
        """
        @brief      Apply one worker progress payload on the UI thread.
        @param[in]  payload Progress payload emitted by the worker.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        _handle_operation_progress(self._window, payload)

    @Slot(object)
    def handle_success(self, result_payload: object) -> None:
        """
        @brief      Finalize one successful worker operation on the UI thread.
        @param[in]  result_payload Worker result payload.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        _handle_operation_success(self._window, self._success_handler, result_payload)

    @Slot(object)
    def handle_failure(self, error: object) -> None:
        """
        @brief      Finalize one failed worker operation on the UI thread.
        @param[in]  error Raised operation exception.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        _handle_operation_failure(self._window, self._failure_handler, error)

    @Slot(str)
    def handle_cancelled(self, message: str) -> None:
        """
        @brief      Finalize one cancelled worker operation on the UI thread.
        @param[in]  message Operator-facing cancellation message.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        _handle_operation_cancelled(self._window, self._cancel_handler, message)

    @Slot()
    def handle_finished(self) -> None:
        """
        @brief      Clear operation state after the worker thread stops.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        _clear_threaded_operation(self._window, self._set_busy)


def start_threaded_operation(
    window: "MainWindow",
    operation_kind: str,
    operation_name: str,
    initial_message: str,
    worker_callable,
    set_busy,
    success_handler,
    failure_handler,
    cancel_handler,
    cancellable: bool = True,
) -> None:
    """
    @brief      Start one modal workflow operation on a dedicated QThread.
    @param[in]  window Active main window.
    @param[in]  operation_kind Stable operation kind token.
    @param[in]  operation_name Operator-facing operation name.
    @param[in]  initial_message Initial progress-dialog message.
    @param[in]  worker_callable Service callable run on the worker thread.
    @param[in]  set_busy Callback accepting one boolean busy state.
    @param[in]  success_handler UI-thread callback for successful worker result.
    @param[in]  failure_handler UI-thread callback for raised exceptions.
    @param[in]  cancel_handler UI-thread callback for cooperative cancellation.
    @param[in]  cancellable True when the progress dialog should expose Cancel.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.1
    """
    if window._active_operation_kind is not None:
        return
    assert window._current_project_root is not None
    assert window._current_manifest is not None

    cancel_event = Event()
    operation_thread = QThread(window)
    worker = ThreadedOperationWorker(
        Path(window._current_project_root),
        dict(window._current_manifest),
        worker_callable,
        cancel_event,
    )
    ui_bridge = ThreadedOperationUiBridge(
        window,
        set_busy,
        success_handler,
        failure_handler,
        cancel_handler,
        parent=window,
    )
    worker.moveToThread(operation_thread)

    set_busy(True)
    home_page = getattr(window, "_home_page", None)
    if home_page is not None:
        home_page.set_operation_busy(True)
    window._active_operation_kind = operation_kind
    window._active_operation_name = operation_name
    window._operation_cancel_requested = False
    window._operation_cancel_event = cancel_event
    window._active_operation_thread = operation_thread
    window._active_operation_worker = worker
    window._active_operation_ui_bridge = ui_bridge

    misc_ui_controller.create_progress_dialog(
        window,
        operation_name,
        initial_message,
        lambda: request_operation_cancel(window),
        cancellable=cancellable,
    )

    operation_thread.started.connect(worker.run)
    worker.progress.connect(ui_bridge.handle_progress)
    worker.succeeded.connect(ui_bridge.handle_success)
    worker.failed.connect(ui_bridge.handle_failure)
    worker.cancelled.connect(ui_bridge.handle_cancelled)
    worker.finished.connect(operation_thread.quit)
    worker.finished.connect(worker.deleteLater)
    operation_thread.finished.connect(operation_thread.deleteLater)
    operation_thread.finished.connect(ui_bridge.handle_finished)
    operation_thread.start()


def request_operation_cancel(window: "MainWindow") -> None:
    """
    @brief      Request cooperative cancellation for the active threaded operation.
    @param[in]  window Active main window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.1
    """
    if window._active_operation_kind is None:
        return
    window._operation_cancel_requested = True
    if window._operation_cancel_event is not None:
        window._operation_cancel_event.set()


# LOCAL HELPERS


def _handle_operation_progress(window: "MainWindow", payload: object) -> None:
    """
    @brief      Apply one worker progress payload to the modal progress dialog.
    @param[in]  window Active main window.
    @param[in]  payload Progress payload emitted by the worker.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    if not isinstance(payload, dict):
        return
    misc_ui_controller.update_progress_dialog(
        window,
        int(payload.get("percent", 0)),
        str(payload.get("message", "")),
        payload.get("token_usage"),
    )


def _handle_operation_success(window: "MainWindow", success_handler, result_payload: object) -> None:
    """
    @brief      Finalize one successful worker operation on the UI thread.
    @param[in]  window Active main window.
    @param[in]  success_handler Callback invoked with the worker result payload.
    @param[in]  result_payload Worker result payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    if window._operation_progress_dialog is not None:
        misc_ui_controller.update_progress_dialog(
            window,
            100,
            window._operation_progress_dialog.status_message(),
        )
    misc_ui_controller.finish_progress_dialog(window)
    success_handler(result_payload)


def _handle_operation_failure(window: "MainWindow", failure_handler, error: object) -> None:
    """
    @brief      Finalize one failed worker operation on the UI thread.
    @param[in]  window Active main window.
    @param[in]  failure_handler Callback invoked with the raised exception.
    @param[in]  error Raised operation exception.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    misc_ui_controller.update_progress_dialog(window, 100, str(error))
    misc_ui_controller.fail_progress_dialog(window, str(error))
    failure_handler(error if isinstance(error, Exception) else RuntimeError(str(error)))


def _handle_operation_cancelled(window: "MainWindow", cancel_handler, message: str) -> None:
    """
    @brief      Finalize one cancelled worker operation on the UI thread.
    @param[in]  window Active main window.
    @param[in]  cancel_handler Callback invoked with the cancellation message.
    @param[in]  message Operator-facing cancellation message.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    misc_ui_controller.update_progress_dialog(window, 100, message)
    misc_ui_controller.fail_progress_dialog(window, message)
    cancel_handler(message)


def _clear_threaded_operation(window: "MainWindow", set_busy) -> None:
    """
    @brief      Clear UI operation bookkeeping after the worker thread stops.
    @param[in]  window Active main window.
    @param[in]  set_busy Callback accepting one boolean busy state.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.1
    """
    set_busy(False)
    home_page = getattr(window, "_home_page", None)
    if home_page is not None:
        home_page.set_operation_busy(False)
    misc_ui_controller.clear_progress_dialog(window)
    window._active_operation_kind = None
    window._active_operation_name = None
    window._operation_cancel_requested = False
    window._operation_cancel_event = None
    window._active_operation_thread = None
    window._active_operation_worker = None
    window._active_operation_ui_bridge = None


# END OF FILE
