#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file paths.py
@brief Path resolution helpers for generated workflow scaffolds.
@details Mirrors the packaged CLI implementation shipped into generated projects.
@details ``matches_pattern`` (0.2.0, architecture-review follow-up) is now
         case-sensitive on non-Windows hosts, matching the real filesystem.
@details ``contained_relative_path`` (0.4.0) is the lenient containment check
         used by policy evaluators reading persisted data; ``relative_to_root``
         remains the strict form used at input boundaries.
@author Eng. Dan Dumitru Pasare
@date 2026-07-23
@version 0.4.0
"""

# IMPORTS

from __future__ import annotations

import os
from fnmatch import fnmatchcase
from pathlib import Path


# PUBLIC API


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


def contained_relative_path(path: str | Path, root: Path) -> str | None:
    """
    @brief      Return the repo-relative form of a path, or ``None`` when it
                escapes the workspace root.
    @param[in]  path Repository-relative or absolute candidate path.
    @param[in]  root Workspace root the candidate must stay inside.
    @return     Normalized POSIX repo-relative path, or ``None`` for an escape.
    @details    Lenient counterpart to :func:`relative_to_root`. Policy
                evaluators read persisted data that may predate validation, and
                an escaping entry there must become a reported finding rather
                than an exception that aborts the whole evaluation. Use
                :func:`relative_to_root` at input boundaries, where an escape is
                an operator error worth refusing immediately, and this function
                when classifying data already on disk.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-23
    @version    0.1.0
    """
    try:
        return relative_to_root(path, root)
    except ValueError:
        return None


def matches_pattern(path: str, pattern: str) -> bool:
    """
    @brief      Match a repo-relative path against one glob pattern.
    @param[in]  path Repo-relative path in either slash style.
    @param[in]  pattern Glob pattern in either slash style.
    @return     True when the path matches the pattern directly or as a tree
                rooted at the pattern.
    @details    Shared matcher used by scope checks, working-tree audit, and
                configured read/write hooks so every policy consumer agrees.
    @details    Case-folded only on Windows (``os.name == "nt"``), added
                0.2.0 (architecture-review follow-up): the previous
                unconditional ``.lower()`` matched Windows' own
                case-insensitive filesystem but could match/miss patterns
                inconsistently with the real, case-sensitive filesystem on
                Ubuntu/Linux. Uses ``fnmatch.fnmatchcase`` rather than
                ``fnmatch.fnmatch``: the latter applies its own OS-tied
                ``os.path.normcase`` internally (case-insensitive on
                Windows, a no-op on POSIX) *in addition to* whatever this
                function does, which would silently reintroduce
                Windows-only case-insensitivity no matter what this
                function decides — ``fnmatchcase`` never normalizes case on
                its own, so this function's own ``os.name`` check is the
                only source of case-folding.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-18
    @version    0.3.0
    """
    normalized_path = path.replace("\\", "/")
    normalized_pattern = pattern.replace("\\", "/").rstrip("/")
    if os.name == "nt":
        normalized_path = normalized_path.lower()
        normalized_pattern = normalized_pattern.lower()
    return fnmatchcase(normalized_path, normalized_pattern) or fnmatchcase(
        normalized_path, f"{normalized_pattern}/**"
    )


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


# END OF FILE
