#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file source.py
@brief Exact source-ledger slice access.
@details Operates on caller-provided canonical text and half-open unit intervals.
"""

# IMPORTS

# Source slicing requires no runtime imports.

# PUBLIC API


def unit_text(canonical_text: str, unit: dict[str, object]) -> str:
    """@brief Return the exact canonical source slice for one unit."""
    return canonical_text[int(unit["start"]) : int(unit["end"])]


# END OF FILE
