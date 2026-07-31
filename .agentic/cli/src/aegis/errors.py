#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file errors.py
@brief Shared public error types for expected AEGIS command failures.
@details Keeps command-input failures independent from CLI orchestration so
         lower-level readers can report actionable operator errors without
         broad exception handling or circular imports.
"""

# DATA MODELS / TYPEDEFINITIONS


class CommandInputError(ValueError):
    """
    @brief Report invalid command input discovered after argument parsing.
    @details Argparse retains responsibility for parser syntax and choices.
             This type covers validly parsed values whose referenced local
             artifact or workflow input cannot be used.
    """


# END OF FILE
