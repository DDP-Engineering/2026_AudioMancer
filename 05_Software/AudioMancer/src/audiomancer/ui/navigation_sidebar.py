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
@brief Sidebar navigation widget for AudioMancer.
@details Renders the workflow pages as a vertical left-hand sidebar list while
         preserving the page registration and selection contract used by the
         main-window shell.
"""

# IMPORTS

from PySide6.QtCore import QByteArray, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QSizePolicy

from audiomancer.services import ui_state_service

# CONSTANTS

# @brief Default idle icon stroke color (AudioMancer Dark text_muted), used before a theme is applied.
_ICON_STROKE_DEFAULT: str = "#98AEAC"

# @brief Rendered sidebar icon size in logical pixels.
_ICON_PIXELS: int = 18

# @brief Monoline SVG path bodies per workflow page, drawn on a 24x24 grid with currentColor stroke.
_PAGE_ICON_PATHS: dict[str, str] = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20h5v-5h4v5h5V9.5"/>',
    "text_cleanup": '<path d="m5 19 7-7"/><path d="M14 4.5 16 3l1.5 2 2 .5-1.5 2 .5 2-2-.5-2 1.5-.5-2-2-.5 1.5-2z"/>',
    "text_chunking": (
        '<rect x="4" y="4" width="16" height="4" rx="1"/>'
        '<rect x="4" y="10" width="16" height="4" rx="1"/>'
        '<rect x="4" y="16" width="10" height="4" rx="1"/>'
    ),
    "book_analysis": (
        '<path d="M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/>'
        '<path d="M8 8h7M8 11h5M8 15h3"/><path d="m15 14 1 2 2 .5-1.5 1.5.5 2-2-1-2 1 .5-2L12 16.5l2-.5z"/>'
    ),
    "ai_translation": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
    "characters": (
        '<circle cx="9" cy="8" r="3"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/>'
        '<circle cx="17" cy="8" r="2.4"/><path d="M15.5 13.6A4.6 4.6 0 0 1 21 18"/>'
    ),
    "narator_voice": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0 0 12 0M12 17v4"/>',
    "character_voices": (
        '<rect x="8" y="3" width="5" height="10" rx="2.5"/>'
        '<path d="M5.5 11a5 5 0 0 0 10 0M10.5 16v3"/><path d="M18 7v8M21 9v4"/>'
    ),
    "speech_blocks": (
        '<path d="M20 15a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2z"/><path d="M8 9h8M8 12h5"/>'
    ),
    "audio_blocks": '<path d="M4 12h2M8 7v10M12 4v16M16 8v8M20 11v2"/>',
    "audio_assembly": '<path d="M12 3 3 7l9 4 9-4-9-4z"/><path d="M3 12l9 4 9-4M3 17l9 4 9-4"/>',
}


def _render_page_icon(inner_svg: str, color: str, px: int = 32) -> QIcon:
    """
    @brief      Render one monoline page icon to a colored QIcon.
    @param[in]  inner_svg SVG path body drawn on a 24x24 grid.
    @param[in]  color Stroke color as a #RRGGBB string.
    @param[in]  px Rendered pixmap size in device pixels.
    @return     Icon with the stroked glyph on a transparent background.
    @exception  None
    """
    svg_markup = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
        f"{inner_svg}</svg>"
    )
    renderer = QSvgRenderer(QByteArray(svg_markup.encode("utf-8")))
    pixmap = QPixmap(px, px)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


# PUBLIC API


class NavigationSidebar(QListWidget):
    """
    @brief      Sidebar widget that emits the selected page identifier.
    @exception  None
    """

    page_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        """
        @brief      Initialize the sidebar widget.
        @param[in]  parent Optional parent widget.
        @return     None.
        @exception  None
        """
        super().__init__(parent)
        self.setObjectName("navigationSidebar")
        self.setAlternatingRowColors(False)
        self.setFixedWidth(160)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setIconSize(QSize(_ICON_PIXELS, _ICON_PIXELS))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.itemSelectionChanged.connect(self._emit_selected_page)
        self._page_labels: dict[str, str] = {}
        self._icon_color: str = _ICON_STROKE_DEFAULT

    def add_page(self, page_id: str, label: str, enabled: bool) -> None:
        """
        @brief      Register one page entry in the sidebar.
        @param[in]  page_id Internal page identifier.
        @param[in]  label Human-readable page label.
        @param[in]  enabled Initial enabled state.
        @return     None.
        @exception  None
        """
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, page_id)
        item.setToolTip(label)
        inner_svg = _PAGE_ICON_PATHS.get(page_id)
        if inner_svg is not None:
            item.setIcon(_render_page_icon(inner_svg, self._icon_color))
        self.addItem(item)
        self._page_labels[page_id] = label
        self.set_page_enabled(page_id, enabled)

    def apply_theme(self, theme_payload: dict[str, object]) -> None:
        """
        @brief      Recolor the workflow page icons to match the active theme.
        @param[in]  theme_payload Runtime UI theme payload.
        @return     None.
        @exception  None
        """
        colors = theme_payload.get("colors") if isinstance(theme_payload, dict) else None
        icon_color = str(colors.get("text_muted")) if isinstance(colors, dict) and colors.get("text_muted") else None
        self._icon_color = icon_color or _ICON_STROKE_DEFAULT
        for index in range(self.count()):
            item = self.item(index)
            page_id = str(item.data(Qt.ItemDataRole.UserRole))
            inner_svg = _PAGE_ICON_PATHS.get(page_id)
            if inner_svg is not None:
                item.setIcon(_render_page_icon(inner_svg, self._icon_color))

    def set_page_label(self, page_id: str, label: str) -> None:
        """
        @brief      Update the display label for one registered page entry.
        @param[in]  page_id Target page identifier.
        @param[in]  label Human-readable page label.
        @return     None.
        @exception  None
        """
        item = self._find_item(page_id)
        if item is None:
            return
        item.setText(label)
        item.setToolTip(label)
        self._page_labels[page_id] = label

    def apply_language(self, language: str) -> None:
        """
        @brief      Apply one UI language to the sidebar page labels.
        @param[in]  language Target UI language code.
        @return     None.
        @exception  None
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
        """
        item = self._find_item(page_id)
        if item is not None:
            self.setCurrentItem(item)

    def _emit_selected_page(self) -> None:
        """
        @brief      Emit the identifier of the currently selected page.
        @return     None.
        @exception  None
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
        """
        for index in range(self.count()):
            item = self.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == page_id:
                return item
        return None


# END OF FILE
