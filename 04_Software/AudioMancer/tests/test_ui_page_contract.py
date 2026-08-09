#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ui_page_contract.py
@brief Structural contract tests for supported AudioMancer workflow page APIs.
@details Verifies retired page methods stay absent while controller-owned
         selection reads and full-state application paths remain available.
"""

# IMPORTS

from audiomancer.ui.pages.character_voices_page import CharacterVoicesPage
from audiomancer.ui.pages.narator_voice_page import NaratorVoicePage
from audiomancer.ui.pages.speech_blocks_page import SpeechBlocksPage

# PUBLIC API


def test_workflow_pages_omit_retired_methods_and_keep_live_state_interfaces() -> None:
    """
    @brief      Verify stale page APIs are absent and live state APIs remain callable.
    @return     None.
    @exception  None
    """
    page_contracts = (
        (
            SpeechBlocksPage,
            ("insert_speech_block_item", "remove_speech_block_item"),
            ("current_profile_id", "set_speech_blocks_state", "update_speech_block_item"),
        ),
        (
            CharacterVoicesPage,
            ("apply_selected_target",),
            ("current_target_id", "set_character_voices_state"),
        ),
        (
            NaratorVoicePage,
            ("apply_selected_profile",),
            ("current_profile_id", "set_narator_voice_state"),
        ),
    )

    for page_class, retired_method_names, live_method_names in page_contracts:
        for method_name in retired_method_names:
            assert not hasattr(page_class, method_name)
        for method_name in live_method_names:
            assert callable(getattr(page_class, method_name, None))


# END OF FILE
