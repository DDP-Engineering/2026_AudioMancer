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
@brief Service package exports for AudioMancer.
@details Exposes reusable application services that support the desktop shell.
@author Eng. Dan Dumitru Pasare
@date 2026-04-04
@version 0.1.1
"""

# IMPORTS

from .logging_service import get_component_logger, initialize_logging, shutdown_logging, trace_function
from .settings_service import (
    build_default_settings,
    ensure_settings_file,
    load_settings,
    save_settings,
    validate_settings,
)

# PUBLIC API

__all__ = [
    "get_component_logger",
    "initialize_logging",
    "shutdown_logging",
    "trace_function",
    "build_default_settings",
    "ensure_settings_file",
    "load_settings",
    "save_settings",
    "validate_settings",
]

# END OF FILE
