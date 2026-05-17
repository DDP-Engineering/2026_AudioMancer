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
@author Eng. Dan Dumitru Pasare
@date 2026-05-15
@version 0.8.5
"""

# IMPORTS

from .app import main

# CONSTANTS

__version__ = "1.1.2"

# PUBLIC API

__all__ = ["__version__", "main"]

# END OF FILE
