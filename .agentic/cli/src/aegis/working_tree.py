#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file working_tree.py
@brief Working-tree audit helpers for delivery preflight checks.
@details Provides reusable implementation behavior for the standalone AEGIS system.
@details `_git_status` (0.3.0, code-review follow-up) now runs with
         `-c core.quotepath=false` and unquotes any remaining C-style-quoted
         path, so a protected/blocked/secret path pattern can no longer be
         dodged by a non-ASCII filename that Git would otherwise report as an
         escaped, quoted string.
@author Eng. Dan Dumitru Pasare
@date 2026-07-18
@version 0.3.0
"""

# IMPORTS

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from .config import WorkflowConfig, load_config
from .paths import matches_pattern

# CONSTANTS

PROTECTED_PATH_PATTERNS = [
    ".git/**",
    ".env",
    ".env.*",
    "**/*.env",
    "**/*.pem",
    "**/*.key",
    "**/*.p12",
    "**/*.pfx",
    "**/*_rsa",
    "**/*_rsa.pub",
    "**/id_rsa",
    "**/id_rsa.pub",
    "**/id_ed25519",
    "**/id_ed25519.pub",
]

MAX_SECRET_SCAN_BYTES = 1_000_000

# PUBLIC API


def audit_working_tree(
    repo_root: Path,
    config: WorkflowConfig | None = None,
    graph: Any | None = None,
) -> dict[str, Any]:
    """
    @brief      Audit working tree workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  config Input value used by the workflow helper.
    @param[in]  graph Active workflow graph when delivery preflight needs
                run-kind-specific checks.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.2.0
    """
    cfg = config or load_config(repo_root)
    entries = _git_status(repo_root)
    findings = []
    for entry in entries:
        path = entry["path"]
        entry_paths = _entry_paths(entry)
        blocked_adoption_path = next(
            (candidate for candidate in entry_paths if _is_blocked_adoption_source_change(candidate, cfg, graph)),
            None,
        )
        if blocked_adoption_path:
            findings.append(
                _finding(
                    "ADOPTION-SOURCE-CHANGE",
                    blocked_adoption_path,
                    "Adoption delivery cannot include application source changes.",
                )
            )
        if _matches_any(path, PROTECTED_PATH_PATTERNS):
            findings.append(_finding("protected-path", path, "Protected path is present in the working tree."))
        if _matches_any(path, cfg.working_tree_blocked_patterns):
            findings.append(_finding("blocked-pattern", path, "Path matches a configured working-tree blocker."))
        secret = _secret_match(repo_root / path, cfg.secret_patterns)
        if secret:
            findings.append(_finding("secret-pattern", path, f"Configured secret pattern matched: {secret}"))
    return {
        "entries": entries,
        "untracked": [entry for entry in entries if entry["status"] == "??"],
        "blocking_findings": findings,
    }


# HELPER FUNCTIONS


def _git_status(repo_root: Path) -> list[dict[str, str]]:
    """
    @brief      Handle git status workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.2
    """
    result = subprocess.run(
        # `-c core.quotepath=false` stops Git from C-style-quoting and
        # octal-escaping paths containing non-ASCII bytes (its default
        # `core.quotePath=true` behavior); without it, a file such as
        # `café.txt` is reported as the literal string `"caf\303\251.txt"`,
        # which none of the protected/blocked/secret path patterns below
        # would ever match.
        ["git", "-c", "core.quotepath=false", "status", "--porcelain", "-uall"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    entries = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        status = line[:2]
        path = line[3:]
        previous_path = None
        if " -> " in path:
            previous_path, path = path.split(" -> ", 1)
        entry = {"status": status, "path": _unquote_git_path(path).replace("\\", "/")}
        if previous_path:
            entry["previous_path"] = _unquote_git_path(previous_path).replace("\\", "/")
        entries.append(entry)
    return entries


_GIT_QUOTE_ESCAPES = {"\\": "\\", '"': '"', "n": "\n", "t": "\t", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


def _unquote_git_path(path: str) -> str:
    """
    @brief      Undo Git's C-style quoting of a porcelain status path.
    @param[in]  path Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @details    `-c core.quotepath=false` (set on the `git status` call above)
                covers the common non-ASCII-filename case, but Git still
                quotes paths containing a literal double quote or backslash
                regardless of that setting, so this remains a second,
                defense-in-depth layer for those remaining cases.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-18
    @version    0.1.0
    """
    if len(path) < 2 or path[0] != '"' or path[-1] != '"':
        return path
    inner = path[1:-1]
    raw = bytearray()
    index = 0
    while index < len(inner):
        char = inner[index]
        if char != "\\" or index + 1 >= len(inner):
            raw.extend(char.encode("utf-8"))
            index += 1
            continue
        nxt = inner[index + 1]
        if nxt in "01234567":
            octal = inner[index + 1 : index + 4]
            try:
                raw.append(int(octal, 8))
                index += 4
                continue
            except ValueError:
                pass
        raw.extend(_GIT_QUOTE_ESCAPES.get(nxt, nxt).encode("utf-8"))
        index += 2
    return raw.decode("utf-8", errors="replace")


def _secret_match(path: Path, patterns: list[str]) -> str | None:
    """
    @brief      Handle secret match workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @param[in]  patterns Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    if not patterns or not path.exists() or not path.is_file():
        return None
    try:
        if path.stat().st_size > MAX_SECRET_SCAN_BYTES:
            return None
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    for pattern in patterns:
        if re.search(pattern, text):
            return pattern
    return None


def _finding(code: str, path: str, message: str) -> dict[str, str]:
    """
    @brief      Handle finding workflow behavior.
    @param[in]  code Input value used by the workflow helper.
    @param[in]  path Input value used by the workflow helper.
    @param[in]  message Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return {"code": code, "path": path, "message": message}


def _matches_any(path: str, patterns: list[str]) -> bool:
    """
    @brief      Match matches any workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @param[in]  patterns Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return any(matches_pattern(path, pattern) for pattern in patterns)


def _is_blocked_adoption_source_change(path: str, config: WorkflowConfig, graph: Any | None) -> bool:
    """
    @brief      Detect source changes that are not allowed during adoption.
    @param[in]  path Repository-relative Git status path.
    @param[in]  config Workflow configuration.
    @param[in]  graph Active workflow graph when available.
    @return     True when an adoption run touches application source.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-22
    @version    0.1.0
    """
    if graph is None or getattr(getattr(graph, "intent", None), "kind", None) != "adoption":
        return False
    if config.adoption_behavior_changes_allowed:
        return False
    normalized = path.replace("\\", "/").strip("/")
    return any(_path_is_under_root(normalized, root) for root in config.source_roots)


def _entry_paths(entry: dict[str, str]) -> list[str]:
    """
    @brief      Return current and previous Git paths for a status entry.
    @param[in]  entry Git status entry.
    @return     Paths that should be checked for policy findings.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-22
    @version    0.1.0
    """
    paths = [entry["path"]]
    previous_path = entry.get("previous_path")
    if previous_path:
        paths.append(previous_path)
    return paths


def _path_is_under_root(path: str, root: str) -> bool:
    """
    @brief      Check whether a Git status path is at or below a root path.
    @param[in]  path Repository-relative path.
    @param[in]  root Repository-relative root.
    @return     True when the path belongs to the root tree.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-22
    @version    0.1.0
    """
    normalized_root = root.replace("\\", "/").strip("/")
    return path == normalized_root or path.startswith(f"{normalized_root}/")


# END OF FILE
