#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file __init__.py
@brief Page widgets for the copied AudioMancer shell.
@details Exposes the minimal presentational pages used by the DDP-style main
         window shell in AudioMancer.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.2.0
"""

# IMPORTS

from .ai_settings_page import AiSettingsPage
from .ai_translation_page import AiTranslationPage
from .characters_page import CharactersPage
from .home_page import HomeProjectPage
from .narator_voice_page import NaratorVoicePage
from .placeholder_page import PlaceholderPage
from .settings_page import SettingsPage
from .text_chunking_page import TextChunkingPage
from .text_cleanup_page import TextCleanupPage

# PUBLIC API

__all__ = [
    "AiTranslationPage",
    "AiSettingsPage",
    "CharactersPage",
    "HomeProjectPage",
    "NaratorVoicePage",
    "PlaceholderPage",
    "SettingsPage",
    "TextChunkingPage",
    "TextCleanupPage",
]

# END OF FILE
