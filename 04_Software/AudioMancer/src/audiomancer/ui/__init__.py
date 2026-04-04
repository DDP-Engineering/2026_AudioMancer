#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file __init__.py
@brief UI package for the AudioMancer application scaffold.
@details Exposes the minimal main window used by the initial desktop shell.
@author Eng. Dan Dumitru Pasare
@date 2026-04-04
@version 0.1.0
"""

# IMPORTS

from .main_window import MainWindow

# PUBLIC API

__all__ = ["MainWindow"]

# END OF FILE
