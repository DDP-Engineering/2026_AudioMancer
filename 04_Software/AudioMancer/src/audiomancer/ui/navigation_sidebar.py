#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file navigation_sidebar.py
@brief Top workflow-navigation tab strip for AudioMancer.
@details Renders the workflow pages as a horizontal, tab-like strip placed under
         the main toolbar while preserving the page registration and selection
         contract used by the main-window shell.
@author Eng. Dan Dumitru Pasare
@date 2026-06-09
@version 0.4.0
"""

# IMPORTS

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListView, QListWidget, QListWidgetItem, QSizePolicy

from audiomancer.services import ui_state_service

# PUBLIC API


class NavigationSidebar(QListWidget):
    """
    @brief      Horizontal navigation tab strip that emits the selected page identifier.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.3.0
    """

    page_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the horizontal navigation tab strip.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-09
        @version    0.3.0
        """
        super().__init__(parent)
        self.setAlternatingRowColors(False)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.itemSelectionChanged.connect(self._emit_selected_page)
        self._page_labels: dict[str, str] = {}

    def add_page(self, page_id: str, label: str, enabled: bool) -> None:
        """
        @brief      Register one page entry in the navigation tab strip.
        @param[in]  page_id Internal page identifier.
        @param[in]  label Human-readable page label.
        @param[in]  enabled Initial enabled state.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-09
        @version    0.2.0
        """
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, page_id)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.addItem(item)
        self._page_labels[page_id] = label
        self.set_page_enabled(page_id, enabled)
        self._apply_strip_height()

    def set_page_label(self, page_id: str, label: str) -> None:
        """
        @brief      Update the display label for one registered page entry.
        @param[in]  page_id Target page identifier.
        @param[in]  label Human-readable page label.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        item = self._find_item(page_id)
        if item is None:
            return
        item.setText(label)
        self._page_labels[page_id] = label

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the sidebar page labels.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        for page_id in self._page_labels:
            self.set_page_label(
                page_id,
                ui_state_service.translate(f"sidebar.{page_id}", language),
            )

    def set_page_enabled(self, page_id: str, enabled: bool) -> None:
        """
        @brief      Update whether one page can be selected.
        @param[in]  page_id Target page identifier.
        @param[in]  enabled True to enable selection.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        item = self._find_item(page_id)
        if item is None:
            return
        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        item.setFlags(flags if enabled else Qt.ItemFlag.NoItemFlags)

    def set_current_page(self, page_id: str) -> None:
        """
        @brief      Select the sidebar entry for the given page.
        @param[in]  page_id Target page identifier.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        item = self._find_item(page_id)
        if item is not None:
            self.setCurrentItem(item)

    def _emit_selected_page(self) -> None:
        """
        @brief      Emit the identifier of the currently selected page.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        item = self.currentItem()
        if item is not None:
            self.page_selected.emit(str(item.data(Qt.ItemDataRole.UserRole)))

    def _find_item(self, page_id: str) -> QListWidgetItem | None:
        """
        @brief      Find a sidebar item by its page identifier.
        @param[in]  page_id Target page identifier.
        @return     Matching list item or `None`.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-05
        @version    0.1.0
        """
        for index in range(self.count()):
            item = self.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == page_id:
                return item
        return None

    def _apply_strip_height(self) -> None:
        """
        @brief      Constrain the strip to a single tab-height row.
        @details    Derives the height from the first row's size hint so the
                    strip follows the active UI font scale, and reserves room for
                    the horizontal scrollbar that appears on narrow windows.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-09
        @version    0.1.0
        """
        row_height = self.sizeHintForRow(0)
        if row_height <= 0:
            return
        frame = 2 * self.frameWidth()
        scrollbar = self.horizontalScrollBar().sizeHint().height()
        self.setFixedHeight(row_height + frame + scrollbar + 4)


# END OF FILE
