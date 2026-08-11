#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ui_scroll_service.py
@brief Focused tests for the runtime UI scroll service.
@details Verifies configured mouse-wheel steps are applied to common Qt scroll
         panes through the application-wide event filter.
"""

# IMPORTS

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QListWidget, QWidget

from audiomancer.services import ui_scroll_service

# PUBLIC API


def test_scroll_step_filter_moves_scroll_pane_by_configured_steps(qtbot) -> None:
    """
    @brief      Verify one wheel notch moves a scroll pane by the configured single-step count.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    application = QApplication.instance()
    assert application is not None
    list_widget = QListWidget()
    qtbot.addWidget(list_widget)
    for index in range(100):
        list_widget.addItem(f"Item {index:03d}")
    list_widget.resize(240, 160)
    list_widget.show()
    qtbot.wait(0)
    scroll_bar = list_widget.verticalScrollBar()
    scroll_bar.setSingleStep(1)
    scroll_bar.setValue(20)
    installed_filter = ui_scroll_service.install_global_scroll_step_filter(application, 2)

    assert installed_filter is not None
    assert installed_filter.eventFilter(list_widget.viewport(), _wheel_event(-120)) is True

    assert scroll_bar.value() == 22


def test_scroll_step_filter_ignores_non_scroll_area_widgets(qtbot) -> None:
    """
    @brief      Verify ordinary widgets are ignored by the global scroll-step filter.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    application = QApplication.instance()
    assert application is not None
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.show()
    installed_filter = ui_scroll_service.install_global_scroll_step_filter(application, 4)

    event = _wheel_event(-120)

    assert installed_filter is not None
    assert installed_filter.eventFilter(widget, event) is False


def test_scroll_step_filter_discards_destroyed_viewport_remainder(qtbot) -> None:
    """Verify destroyed viewport identities cannot retain wheel state."""
    application = QApplication.instance()
    assert application is not None
    list_widget = QListWidget()
    qtbot.addWidget(list_widget)
    installed_filter = ui_scroll_service.install_global_scroll_step_filter(application, 2)
    assert installed_filter is not None
    viewport = list_widget.viewport()
    installed_filter._vertical_angle_remainder_by_viewport[id(viewport)] = 60  # noqa: SLF001

    installed_filter.eventFilter(viewport, QEvent(QEvent.Type.Destroy))

    assert id(viewport) not in installed_filter._vertical_angle_remainder_by_viewport  # noqa: SLF001


# HELPER FUNCTIONS


def _wheel_event(angle_delta_y: int) -> QWheelEvent:
    """
    @brief      Build one vertical mouse-wheel event for scroll-service tests.
    @param[in]  angle_delta_y Vertical angle delta in Qt wheel units.
    @return     Wheel event instance.
    @exception  None
    """
    position = QPointF(8.0, 8.0)
    return QWheelEvent(
        position,
        position,
        QPoint(0, 0),
        QPoint(0, angle_delta_y),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


# END OF FILE
