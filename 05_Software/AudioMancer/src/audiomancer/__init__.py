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
@brief Package definition for the AudioMancer application scaffold.
@details Exposes the package version for the desktop application shell.
"""

# IMPORTS


# CONSTANTS

__version__ = "2.2.1"

# PUBLIC API


def main() -> int:
    """@brief Load the desktop bootstrap only when the application is actually started."""
    from .app import main as run_application

    return run_application()


__all__ = ["__version__", "main"]

# END OF FILE
