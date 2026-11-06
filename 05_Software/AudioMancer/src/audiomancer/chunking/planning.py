#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file planning.py
@brief Cursor-based budgeted paragraph windows.
@details Paragraph costs are precomputed by the caller; selecting a window only visits its source span.
"""

# IMPORTS

# No external dependencies.

# PUBLIC API


def next_window(costs: list[int], start_index: int, text_budget: int, paragraph_cap: int) -> dict[str, int]:
    """@brief Return the next inclusive source range, admitting an oversized paragraph alone.
    @exception ValueError The cursor or budget is invalid.
    """
    if not 0 <= start_index < len(costs) or text_budget <= 0:
        raise ValueError("Invalid Chunking window cursor or text budget.")
    end = start_index
    tokens = costs[start_index]
    while end + 1 < len(costs) and (paragraph_cap <= 0 or end - start_index + 1 < paragraph_cap):
        if tokens + costs[end + 1] > text_budget:
            break
        end += 1
        tokens += costs[end]
    return {"start_index": start_index, "end_index": end}


# END OF FILE
