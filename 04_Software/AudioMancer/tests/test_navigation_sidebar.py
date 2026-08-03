#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_navigation_sidebar.py
@brief Focused tests for the AudioMancer navigation sidebar visuals.
@details Verifies each workflow page receives a brand icon (REQ-UX-23258764).
"""

# IMPORTS

from audiomancer.ui.navigation_sidebar import NavigationSidebar

# CONSTANTS

# @brief Ordered workflow pages registered by the main-window shell.
_WORKFLOW_PAGES = (
    ("home", "Home / Project"),
    ("text_cleanup", "Text Cleanup"),
    ("text_chunking", "Text Chunking"),
    ("ai_translation", "AI Translation"),
    ("characters", "Characters"),
    ("narator_voice", "Narator Voice"),
    ("character_voices", "Character Voices"),
    ("speech_blocks", "Speech Blocks"),
    ("audio_blocks", "Audio Blocks"),
    ("audio_assembly", "Audio Assembly"),
)

# PUBLIC API


def test_navigation_sidebar_assigns_an_icon_to_each_page(qtbot) -> None:
    """
    @brief      Verify every workflow page entry gets a non-empty icon.
    @details    Covers REQ-UX-23258764-2042-4962-8d48-94a157aaad6a / SPEC-NAV-ICONS.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    sidebar = NavigationSidebar()
    qtbot.addWidget(sidebar)

    for page_id, label in _WORKFLOW_PAGES:
        sidebar.add_page(page_id, label, enabled=True)

    assert sidebar.count() == len(_WORKFLOW_PAGES)
    for index in range(sidebar.count()):
        item = sidebar.item(index)
        assert not item.icon().isNull(), f"missing icon for page row: {item.text()}"


def test_navigation_sidebar_sets_full_label_tooltip(qtbot) -> None:
    """
    @brief      Verify each sidebar page entry carries its full label as a tooltip.
    @details    Covers REQ-UX-c0d8d572-0ed6-471c-ab33-b3ba16e55679 / SPEC-NAV-TOOLTIP.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    sidebar = NavigationSidebar()
    qtbot.addWidget(sidebar)

    for page_id, label in _WORKFLOW_PAGES:
        sidebar.add_page(page_id, label, enabled=True)

    for index, (_page_id, label) in enumerate(_WORKFLOW_PAGES):
        assert sidebar.item(index).toolTip() == label


# END OF FILE
