#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audiomancer_windows_entry.py
@brief PyInstaller launcher entrypoint for the Windows desktop bundle.
@details Imports the package-owned application bootstrap through the installed
         package path so PyInstaller can bundle the AudioMancer package without
         executing a relative-import module as a loose script.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.1.0
"""

# IMPORTS

from audiomancer.app import main

# PUBLIC API


def run() -> int:
    """
    @brief      Delegate Windows packaged startup to the application bootstrap.
    @return     Process exit code returned by the desktop application.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    return main()


if __name__ == "__main__":
    raise SystemExit(run())


# END OF FILE
