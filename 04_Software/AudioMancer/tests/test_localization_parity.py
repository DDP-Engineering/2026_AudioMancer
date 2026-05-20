#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_localization_parity.py
@brief Regression guard for runtime UI string catalog completeness.
@details Verifies every supported UI language exposes the exact same set of
         translation keys so operator-facing text stays language-complete.
@author Eng. Dan Dumitru Pasare
@date 2026-05-19
@version 0.1.0
"""

# IMPORTS

from audiomancer import config
from audiomancer.services import ui_state_service


def test_supported_languages_share_identical_translation_keys() -> None:
    """
    @brief      Verify each supported UI language has the same translation keys.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-19
    @version    0.1.0
    """
    reference_language = config.DEFAULT_LANGUAGE
    reference_keys = set(ui_state_service.get_ui_strings(reference_language))
    assert reference_keys, "Reference language catalog must not be empty."

    for language in config.SUPPORTED_LANGUAGES:
        language_keys = set(ui_state_service.get_ui_strings(language))
        missing = reference_keys - language_keys
        extra = language_keys - reference_keys
        assert not missing, f"Language '{language}' is missing keys: {sorted(missing)}"
        assert not extra, f"Language '{language}' has unexpected keys: {sorted(extra)}"


# END OF FILE
