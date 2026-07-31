#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ui_scroll_service.py
@brief Runtime mouse-wheel scroll-step helpers for AudioMancer.
@details Installs one application-wide Qt event filter that applies the
         settings-backed mouse-wheel step count to common scroll panes.
"""

# IMPORTS

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QScrollBar, QWidget

from audiomancer import config

# CONSTANTS

# @brief Qt mouse-wheel angle delta units for one physical wheel notch.
_WHEEL_ANGLE_UNITS_PER_NOTCH = 120

# @brief Dynamic QApplication attribute that keeps the installed filter alive.
_APPLICATION_SCROLL_FILTER_ATTRIBUTE = "_audiomancer_scroll_step_filter"


# PUBLIC API


class ScrollStepEventFilter(QObject):
    """
    @brief      Apply a configured wheel-scroll step count to scroll-area viewports.
    @exception  None
    """

    def __init__(self, scroll_steps_per_notch: int, parent: QObject | None = None) -> None:
        """
        @brief      Initialize the scroll-step event filter.
        @param[in]  scroll_steps_per_notch Number of scrollbar single-steps per wheel notch.
        @param[in]  parent Optional Qt parent object.
        @return     None.
        @exception  None
        """
        super().__init__(parent)
        self._scroll_steps_per_notch = config.DEFAULT_UI_SCROLL_STEPS_PER_WHEEL_NOTCH
        self._vertical_angle_remainder_by_viewport: dict[int, int] = {}
        self.set_scroll_steps_per_notch(scroll_steps_per_notch)

    def set_scroll_steps_per_notch(self, scroll_steps_per_notch: int) -> None:
        """
        @brief      Update the configured wheel-scroll step count.
        @param[in]  scroll_steps_per_notch Number of scrollbar single-steps per wheel notch.
        @return     None.
        @exception  None
        """
        if not isinstance(scroll_steps_per_notch, int):
            scroll_steps_per_notch = config.DEFAULT_UI_SCROLL_STEPS_PER_WHEEL_NOTCH
        self._scroll_steps_per_notch = max(
            config.MIN_UI_SCROLL_STEPS_PER_WHEEL_NOTCH,
            min(scroll_steps_per_notch, config.MAX_UI_SCROLL_STEPS_PER_WHEEL_NOTCH),
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """
        @brief      Apply configured one-notch scroll steps to scroll-area wheel events.
        @param[in]  watched Qt object receiving the event.
        @param[in]  event Qt event payload.
        @return     True when the wheel event was handled.
        @exception  None
        """
        if event.type() != QEvent.Type.Wheel or not isinstance(watched, QWidget):
            return super().eventFilter(watched, event)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return super().eventFilter(watched, event)
        scroll_area = _scroll_area_from_viewport(watched)
        if scroll_area is None:
            return super().eventFilter(watched, event)
        angle_delta = event.angleDelta().y()
        if angle_delta == 0:
            return super().eventFilter(watched, event)
        viewport_key = id(watched)
        accumulated_delta = self._vertical_angle_remainder_by_viewport.get(viewport_key, 0) + int(angle_delta)
        notch_count = int(accumulated_delta / _WHEEL_ANGLE_UNITS_PER_NOTCH)
        self._vertical_angle_remainder_by_viewport[viewport_key] = accumulated_delta - (
            notch_count * _WHEEL_ANGLE_UNITS_PER_NOTCH
        )
        if notch_count == 0:
            return True
        _scroll_by_notches(scroll_area.verticalScrollBar(), notch_count, self._scroll_steps_per_notch)
        return True


def install_global_scroll_step_filter(
    application: QApplication | None,
    scroll_steps_per_notch: int,
) -> ScrollStepEventFilter | None:
    """
    @brief      Install or reconfigure the application-wide scroll-step event filter.
    @param[in]  application Running Qt application instance.
    @param[in]  scroll_steps_per_notch Number of scrollbar single-steps per wheel notch.
    @return     Installed event filter or `None` when no application exists.
    @exception  None
    """
    if application is None:
        return None
    installed_filter = getattr(application, _APPLICATION_SCROLL_FILTER_ATTRIBUTE, None)
    if isinstance(installed_filter, ScrollStepEventFilter):
        installed_filter.set_scroll_steps_per_notch(scroll_steps_per_notch)
        return installed_filter
    installed_filter = ScrollStepEventFilter(scroll_steps_per_notch, application)
    application.installEventFilter(installed_filter)
    setattr(application, _APPLICATION_SCROLL_FILTER_ATTRIBUTE, installed_filter)
    return installed_filter


# HELPER FUNCTIONS


def _scroll_area_from_viewport(widget: QWidget) -> QAbstractScrollArea | None:
    """
    @brief      Resolve a scroll area from one watched viewport widget.
    @param[in]  widget Candidate event target widget.
    @return     Owning scroll area or `None`.
    @exception  None
    """
    parent_widget = widget.parentWidget()
    if isinstance(parent_widget, QAbstractScrollArea) and parent_widget.viewport() is widget:
        return parent_widget
    return None


def _scroll_by_notches(scroll_bar: QScrollBar, notch_count: int, scroll_steps_per_notch: int) -> None:
    """
    @brief      Move one scrollbar by configured wheel notches.
    @param[in]  scroll_bar Target scrollbar.
    @param[in]  notch_count Signed wheel-notch count.
    @param[in]  scroll_steps_per_notch Number of single-steps per wheel notch.
    @return     None.
    @exception  None
    """
    step_size = max(1, int(scroll_bar.singleStep())) * max(
        config.MIN_UI_SCROLL_STEPS_PER_WHEEL_NOTCH,
        min(int(scroll_steps_per_notch), config.MAX_UI_SCROLL_STEPS_PER_WHEEL_NOTCH),
    )
    scroll_bar.setValue(scroll_bar.value() - (notch_count * step_size))


# END OF FILE
