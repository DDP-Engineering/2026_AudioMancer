#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_controller_cancellation_wiring.py
@brief Tests that workflow controllers hand their cancellation handler to the runner.
@details The Text Chunking and Text Cleanup controllers delegate progress and
         terminal outcomes to the shared operation runner but keep their own
         cancellation handler, which syncs the manifest and refreshes project
         state. The existing controller tests accept `cancel_handler` and discard
         it, so this module is what proves the handler is actually connected.
@author Eng. Dan Dumitru Pasare
@date 2026-07-25
@version 0.1.0
"""

# IMPORTS

import pytest

from audiomancer.ui.controllers import text_chunking_ui_controller, text_cleanup_ui_controller

# CONSTANTS

# @brief Controller modules that delegate operations to the shared runner.
_DELEGATING_CONTROLLERS = (
    text_chunking_ui_controller,
    text_cleanup_ui_controller,
)


@pytest.mark.parametrize("controller_module", _DELEGATING_CONTROLLERS, ids=lambda module: module.__name__)
def test_controllers_pass_their_cancellation_handler_to_the_runner(monkeypatch, controller_module) -> None:
    """
    @brief      Verify start_operation wires the module's cancellation handler.
    @details    The cancellation handler performs manifest sync and project-state
                refresh that the shared runner does not, so losing the wiring would
                silently leave a cancelled run's manifest stale.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  controller_module Controller module under test.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    captured_cancel_handlers: list = []
    cancelled_messages: list[str] = []

    def _capture_start(window, operation_kind, operation_name, initial_message, worker_callable, **runner_callbacks):
        """
        @brief      Capture the cancel handler the controller hands to the runner.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-25
        @version    0.1.0
        """
        _ = (window, operation_kind, operation_name, initial_message, worker_callable)
        captured_cancel_handlers.append(runner_callbacks["cancel_handler"])

    monkeypatch.setattr(
        controller_module.operation_runner_controller,
        "start_threaded_operation",
        _capture_start,
    )
    monkeypatch.setattr(
        controller_module,
        "handle_operation_cancelled",
        lambda window, message: cancelled_messages.append(message),
    )

    controller_module.start_operation(
        _StubWindow(),
        operation_kind="kind",
        operation_name="Name",
        initial_message="starting",
        worker_callable=lambda *_args, **_kwargs: None,
        success_handler=lambda payload: None,
        failure_handler=lambda error: None,
    )

    assert len(captured_cancel_handlers) == 1
    captured_cancel_handlers[0]("cancelled")
    assert cancelled_messages == ["cancelled"]


# HELPER FUNCTIONS


class _StubWindow:
    """
    @brief      Minimal window double exposing the page attributes start_operation touches.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """

    def __init__(self) -> None:
        """
        @brief      Provide busy-capable page doubles for both controllers.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-25
        @version    0.1.0
        """
        self._text_chunking_page = _StubPage()
        self._text_cleanup_page = _StubPage()


class _StubPage:
    """
    @brief      Page double that accepts busy-state changes.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """

    def set_busy(self, is_busy: bool, operation_name: str | None = None) -> None:
        """
        @brief      Accept one busy-state change without rendering UI.
        @param[in]  is_busy True while an operation runs.
        @param[in]  operation_name Optional operator-facing operation name.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-25
        @version    0.1.0
        """
        _ = (is_busy, operation_name)


# END OF FILE
