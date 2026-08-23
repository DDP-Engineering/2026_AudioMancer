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
@brief Service package exports for AudioMancer.
@details Exposes reusable application services that support the desktop shell.
"""

# IMPORTS

from .logging_service import get_component_logger, initialize_logging, shutdown_logging, trace_function
from .project_workspace_service import (
    create_project,
    load_manifest,
    open_project,
    resolve_project_root,
    save_manifest,
    validate_project,
    validate_project_name,
)
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
    "create_project",
    "load_manifest",
    "open_project",
    "resolve_project_root",
    "save_manifest",
    "validate_project",
    "validate_project_name",
]

# END OF FILE
