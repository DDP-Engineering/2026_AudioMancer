#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file paths.py
@brief Path resolution helpers for generated workflow scaffolds.
@details Mirrors the packaged CLI implementation shipped into generated projects.
@author Eng. Dan Dumitru Pasare
@date 2026-06-20
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path


def relative_to_root(path: str | Path, root: Path) -> str:
    """
    @brief      Handle relative to root workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @param[in]  root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        rel = candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path escapes workspace root: {path}") from exc
    return rel.as_posix()


def matches_pattern(path: str, pattern: str) -> bool:
    """
    @brief      Match a repo-relative path against one glob pattern.
    @param[in]  path Repo-relative path in either slash style.
    @param[in]  pattern Glob pattern in either slash style.
    @return     True when the path matches the pattern directly or as a tree
                rooted at the pattern.
    @details    Shared matcher used by scope checks and the working-tree audit so
                they stay consistent. The standalone `guard_write_zone.py` hook
                keeps its own copy because it runs without importing this package.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    normalized_path = path.replace("\\", "/").lower()
    normalized_pattern = pattern.replace("\\", "/").rstrip("/").lower()
    return fnmatch(normalized_path, normalized_pattern) or fnmatch(normalized_path, f"{normalized_pattern}/**")


def is_allowed_path(path: str | Path, root: Path, patterns: list[str]) -> bool:
    """
    @brief      Check is allowed path workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @param[in]  root Input value used by the workflow helper.
    @param[in]  patterns Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    rel = relative_to_root(path, root)
    return any(matches_pattern(rel, pattern) for pattern in patterns)
