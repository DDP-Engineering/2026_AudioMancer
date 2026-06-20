#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file working_tree.py
@brief Working-tree audit helpers for delivery preflight checks.
@details Provides reusable implementation behavior for the standalone workflow template.
@author Eng. Dan Dumitru Pasare
@date 2026-06-20
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from .config import WorkflowConfig, load_config
from .paths import matches_pattern


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


def audit_working_tree(repo_root: Path, config: WorkflowConfig | None = None) -> dict[str, Any]:
    """
    @brief      Audit working tree workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  config Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    cfg = config or load_config(repo_root)
    entries = _git_status(repo_root)
    findings = []
    for entry in entries:
        path = entry["path"]
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


def _git_status(repo_root: Path) -> list[dict[str, str]]:
    """
    @brief      Handle git status workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    entries = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        status = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        entries.append({"status": status, "path": path.replace("\\", "/")})
    return entries


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
