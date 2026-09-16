#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_settings_layout.py
@brief Keep profile defaults aligned and dialog actions reachable at different font sizes.
@details Exercises actual widget geometry and independent list/content scrolling.
"""

# IMPORTS

from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QLabel, QScrollArea
import pytest

from audiomancer.services import ui_state_service, ui_theme_service
from audiomancer.ui.pages.ai_settings_page import AiSettingsPage


@pytest.mark.parametrize("backend", ["lmstudio", "chatgpt_subscription"])
def test_normal_window_fits_single_line_defaults_and_compact_editor(qtbot, backend):
    """@brief Real theme geometry fits the reported window size without squeezing defaults or clipping fields."""
    font_path = Path("C:/Windows/Fonts/segoeui.ttf")
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))
    page = AiSettingsPage()
    qtbot.addWidget(page)
    page.setFont(QFont("Segoe UI", 12))
    theme = ui_theme_service.theme_by_id("classic_light", [])
    theme["font"].update(family="Segoe UI", point_size=12)
    page.setStyleSheet(ui_state_service.build_theme_stylesheet(theme, 12))
    page.load_settings({"llm_profiles": [
        {"id": str(i), "label": f"Profile {i}", "backend_kind": backend, "model_name": "gpt-5.6-sol"}
        for i in range(16)
    ]})
    page.resize(980, 740)
    page.show()
    qtbot.wait(50)
    scroll = page._content_scroll
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() == 0
    left = page._profile_list.parentWidget()
    right = page._label_edit.parentWidget()
    assert right.x() > left.geometry().right()
    assert left.width() == page._defaults_form.minimumSize().width()
    for row in range(page._defaults_form.rowCount()):
        label = page._defaults_form.itemAt(row, page._defaults_form.ItemRole.LabelRole).widget()
        field = page._defaults_form.itemAt(row, page._defaults_form.ItemRole.FieldRole).widget()
        assert label.width() >= label.fontMetrics().horizontalAdvance(label.text())
        assert abs(label.geometry().center().y() - field.geometry().center().y()) <= 4
    for button in (page._add_profile_button, page._remove_profile_button,
                   page._chatgpt_browser_button, page._chatgpt_device_button):
        assert button.width() <= max(button.sizeHint().width(), 210)
    assert page._profile_list.verticalScrollBar().maximum() > 0


@pytest.mark.parametrize("font_size", [10, 16, 22])
@pytest.mark.parametrize("language", ["en", "ro"])
def test_defaults_below_compact_profiles_and_actions_outside_scroll(qtbot, font_size, language):
    """@brief Resizing and larger fonts retain the footer while long lists scroll independently."""
    page = AiSettingsPage()
    qtbot.addWidget(page)
    page.setFont(QFont("Segoe UI", font_size))
    page.setStyleSheet(f"QWidget {{ font-family: Segoe UI; font-size: {font_size}pt; }}")
    page.load_settings(
        {
            "llm_profiles": [
                {"id": str(i), "label": f"Profile {i}", "backend_kind": "chatgpt_subscription", "model_name": "gpt-5.5"}
                for i in range(24)
            ]
        }
    )
    page.apply_language(language)
    page.resize(1100, 780)
    page.show()
    qtbot.wait(30)
    scrolls = page.findChildren(QScrollArea)
    assert len(scrolls) == 1, "Only the settings content should scroll, leaving actions fixed"
    scroll = scrolls[0]
    assert scroll.widget().isAncestorOf(page._profile_list)
    assert page._default_cleanup_combo.parentWidget() is page._profile_list.parentWidget()
    assert page._default_cleanup_combo.y() > page._profile_list.geometry().bottom()
    assert page._profile_list.height() < page._default_speech_blocks_combo.geometry().bottom() / 2
    assert page._profile_list.verticalScrollBar().maximum() > 0
    assert not any(
        label.isVisible() and label.text().startswith("Experimental ChatGPT") for label in page.findChildren(QLabel)
    )
    for height in (780, 480):
        page.resize(1100, height)
        qtbot.wait(20)
        before = [button.mapTo(page, QPoint()) for button in (page._cancel_button, page._save_button, page._ok_button)]
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        qtbot.wait(10)
        for index, button in enumerate((page._cancel_button, page._save_button, page._ok_button)):
            assert not scroll.isAncestorOf(button)
            assert button.mapTo(page, QPoint()) == before[index]
            assert page.rect().contains(button.mapTo(page, button.rect().bottomRight()))
            assert button.width() >= button.sizeHint().width()
        assert len({button.width() for button in (page._cancel_button, page._save_button, page._ok_button)}) == 1


def test_dialog_hosts_fixed_footer_without_an_outer_scroll(qtbot, default_settings_payload):
    """@brief The shell embeds the page directly so its footer cannot scroll out of the dialog."""
    from audiomancer.ui.main_window import MainWindow

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    dialog, page = window._ai_settings_dialog, window._ai_settings_page
    available = window.screen().availableGeometry()
    assert dialog.width() == max(640, min(800, available.width() - 32))
    assert dialog.height() == max(480, min(600, available.height() - 64))
    assert page.parentWidget() is dialog
    assert dialog.layout().itemAt(0).widget() is page
    assert len(dialog.findChildren(QScrollArea)) == 1


def test_runtime_font_changes_resize_list_and_actions_in_both_directions(qtbot):
    """@brief Increasing then decreasing control fonts recalculates geometry instead of retaining pixel caps."""
    page = AiSettingsPage()
    qtbot.addWidget(page)
    page.resize(1100, 780)
    page.show()
    sizes = []
    for points in (10, 22, 10):
        page.setFont(QFont("Segoe UI", points))
        page.setStyleSheet(f"QWidget {{ font-family: Segoe UI; font-size: {points}pt; }}")
        qtbot.wait(20)
        sizes.append((page._profile_list.height(), page._cancel_button.width()))
    assert sizes[1][0] > sizes[0][0]
    assert sizes[1][1] > sizes[0][1]
    assert sizes[2] == sizes[0]


@pytest.mark.parametrize("language", ["en", "ro"])
def test_compact_defaults_and_responsive_columns_fit_low_resolution(qtbot, language):
    """@brief Small screens scroll vertically and large screens keep equal compact default selectors."""
    page = AiSettingsPage()
    qtbot.addWidget(page)
    page.setFont(QFont("Segoe UI", 12))
    theme = ui_theme_service.theme_by_id("classic_light", [])
    theme["font"].update(family="Segoe UI", point_size=12)
    page.setStyleSheet(ui_state_service.build_theme_stylesheet(theme, 12))
    page.load_settings({"llm_profiles": [{"id": "sub", "label": "A long profile name " * 8,
                                         "backend_kind": "chatgpt_subscription", "model_name": "gpt-5.6-luna"}]})
    page.apply_language(language)
    page.resize(1400, 900)
    page.show()
    qtbot.wait(50)
    fields = [page._defaults_form.itemAt(row, page._defaults_form.ItemRole.FieldRole).widget()
              for row in range(page._defaults_form.rowCount())]
    wide_widths = [field.width() for field in fields]
    assert len(set(wide_widths)) == 1
    assert max(wide_widths) <= max(field.sizeHint().width() for field in fields)
    for width in (800, 640, 480, 1400):
        page.resize(width, 600)
        qtbot.wait(50)
        assert page.width() == width
        assert page._content_scroll.horizontalScrollBar().maximum() == 0
        assert [field.width() for field in fields] == wide_widths
        assert page.rect().contains(page._ok_button.mapTo(page, page._ok_button.rect().bottomRight()))
        left, right = page._profile_list.parentWidget(), page._label_edit.parentWidget()
        if width == 480:
            assert right.y() > left.geometry().bottom()
        elif width == 1400:
            assert right.x() > left.geometry().right()


def test_profile_selection_stays_visible_without_scrolling_the_page(qtbot):
    """@brief Rebuilding profile names retains list position and keeps the editor's selection visible."""
    page = AiSettingsPage()
    qtbot.addWidget(page)
    page.load_settings({"llm_profiles": [
        {"id": str(i), "label": f"Profile {i}", "backend_kind": "chatgpt_subscription", "model_name": "gpt-5.5"}
        for i in range(30)
    ]})
    page.resize(800, 600)
    page.show()
    qtbot.wait(30)
    page._profile_list.scrollToBottom()
    page._profile_list.setCurrentRow(22)
    qtbot.wait(20)
    listing = page._profile_list
    listing.verticalScrollBar().setValue(20)
    assert listing.viewport().rect().contains(listing.visualItemRect(listing.currentItem()))
    before = listing.verticalScrollBar().value()
    page_scroll = page._content_scroll.verticalScrollBar().value()
    page.build_current_profile_payload()
    qtbot.wait(20)
    assert listing.verticalScrollBar().value() == before
    assert page._content_scroll.verticalScrollBar().value() == page_scroll
    assert listing.currentItem().data(Qt.ItemDataRole.UserRole) == page._editor_profile_id == "22"
    assert listing.viewport().rect().contains(listing.visualItemRect(listing.currentItem()))


# END OF FILE


def test_pending_layout_refresh_is_cancelled_when_page_is_destroyed(qtbot):
    """@brief Deferred font/layout work must not access controls after their page is deleted."""
    from shiboken6 import delete

    page = AiSettingsPage()
    page.setFont(QFont("Segoe UI", 19))
    delete(page)
    qtbot.wait(1)
