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
@details The unused ``is_allowed_path`` convenience wrapper was removed (0.5.0,
         code-review follow-up): no production caller used it, and every policy
         consumer composes ``relative_to_root``/``contained_relative_path`` with
         ``matches_pattern`` directly.
"""

# IMPORTS

from __future__ import annotations

import os
from fnmatch import fnmatchcase
from pathlib import Path
import re


# DATA MODELS / TYPEDEFINITIONS


class RepositoryPathError(ValueError):
    """
    @brief      ValueError subtype carrying a stable reason code for
                repository path/glob normalization failures.
    @details    Lets each trust boundary that calls
                :func:`normalize_repository_path`/:func:`validate_glob`
                (currently `config.py` and `requirement_store.py`) translate
                the one canonical failure into its own typed error without
                string-matching the exception text. ``reason`` is one of
                ``"escapes-root"``, ``"has-globs"``, or ``"unbalanced-glob"``.
    """

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


# PUBLIC API


def relative_to_root(path: str | Path, root: Path) -> str:
    """
    @brief      Return the repo-relative POSIX form of a path, refusing any
                candidate that resolves outside the workspace root.
    @param[in]  path Repository-relative or absolute candidate path.
    @param[in]  root Workspace root the candidate must resolve inside.
    @return     Normalized POSIX repo-relative path.
    @exception  ValueError If the resolved candidate escapes ``root``.
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
    """
    normalized_path = path.replace("\\", "/")
    normalized_pattern = pattern.replace("\\", "/").rstrip("/")
    if os.name == "nt":
        normalized_path = normalized_path.lower()
        normalized_pattern = normalized_pattern.lower()
    return fnmatchcase(normalized_path, normalized_pattern) or fnmatchcase(
        normalized_path, f"{normalized_pattern}/**"
    )


def normalize_repository_path(value: str, *, allow_glob: bool = False) -> str:
    """
    @brief      Apply the canonical repository-relative path normalization.
    @param[in]  value Candidate repository path or glob (already known to be
                a `str`; callers validate the raw type themselves).
    @param[in]  allow_glob Whether glob metacharacters (`*?[]`) are permitted.
    @return     Normalized slash-separated repository-relative value.
    @exception  RepositoryPathError If the value is empty, escapes the
                repository root (absolute, drive-letter, `~`, or `..`
                segment), or contains glob metacharacters while
                ``allow_glob`` is False.
    @details    Shared by `config.py`'s TOML rule normalization and
                `requirement_store.py`'s requirement-record path fields, so
                both trust boundaries agree on what counts as a safe
                repository-relative path.
    """
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = re.sub(r"/{2,}", "/", normalized).rstrip("/")
    if (
        not normalized
        or normalized.startswith(("/", "~"))
        or re.match(r"^[A-Za-z]:", normalized)
        or ".." in normalized.split("/")
    ):
        raise RepositoryPathError(
            "escapes-root", "must be a repository-relative path without `..`"
        )
    if not allow_glob and any(char in normalized for char in "*?[]"):
        raise RepositoryPathError("has-globs", "must not contain glob syntax")
    return normalized


def validate_glob(value: str) -> None:
    """
    @brief      Reject glob strings with unbalanced bracket-expression syntax.
    @param[in]  value Normalized glob candidate.
    @return     None.
    @exception  RepositoryPathError If a `[`/`]` bracket expression is
                unbalanced or nested.
    """
    depth = 0
    for char in value:
        if char == "[":
            if depth:
                raise RepositoryPathError(
                    "unbalanced-glob", "glob bracket expressions must be balanced"
                )
            depth = 1
        elif char == "]":
            if not depth:
                raise RepositoryPathError(
                    "unbalanced-glob", "glob bracket expressions must be balanced"
                )
            depth = 0
    if depth:
        raise RepositoryPathError(
            "unbalanced-glob", "glob bracket expressions must be balanced"
        )


# END OF FILE
