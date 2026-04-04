#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_package_import.py
@brief Focused smoke tests for the AudioMancer package scaffold.
@details Verifies that the package imports and exposes the expected entrypoint.
@author Eng. Dan Dumitru Pasare
@date 2026-04-04
@version 0.1.3
"""

# IMPORTS

import audiomancer

# PUBLIC API


def test_package_exposes_main() -> None:
    """
    @brief      Verify the package exports the application entrypoint.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-04
    @version    0.1.3
    """
    assert callable(audiomancer.main)
    assert audiomancer.__version__ == "0.1.4"


# END OF FILE
