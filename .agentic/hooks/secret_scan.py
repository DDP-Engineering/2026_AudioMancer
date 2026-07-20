#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file secret_scan.py
@brief Hook entry point for secret scanning checks.
@details Scans the union of built-in secret formats and repository-configured
         ``[secrets].patterns`` while treating unreadable configuration and
         invalid user regexes as non-blocking.
@author Eng. Dan Dumitru Pasare
@date 2026-07-20
@version 0.2.0
"""

# IMPORTS

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

# CONSTANTS

PATTERNS = [
    r"sk-[A-Za-z0-9_-]{20,}",
    r"ghp_[A-Za-z0-9_]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
]

# PUBLIC API


def main() -> int:
    """
    @brief      Scan pre-tool input for built-in and configured secret patterns.
    @return     Zero after allowing the input or emitting a deny decision.
    @details    Invalid configured regexes are skipped individually; a missing,
                unreadable, or invalid ``workflow.toml`` contributes no custom
                patterns and never crashes or blocks the hook by itself.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-20
    @version    0.2.0
    """
    payload = json.load(sys.stdin)
    if payload.get("hook_event_name") != "PreToolUse":
        return 0
    cwd = Path(payload.get("cwd") or ".").resolve()
    compiled_patterns = []
    for pattern in dict.fromkeys([*PATTERNS, *load_configured_patterns(cwd)]):
        try:
            compiled_patterns.append(re.compile(pattern))
        except re.error:
            continue
    text = json.dumps(payload.get("tool_input", {}))
    if any(pattern.search(text) for pattern in compiled_patterns):
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "Possible secret detected in tool input.",
                    }
                }
            )
        )
    return 0


# HELPER FUNCTIONS


def load_configured_patterns(cwd: Path) -> list[str]:
    """
    @brief      Read repository-configured secret patterns for the hook.
    @param[in]  cwd Repository root supplied by the tool payload.
    @return     String regex entries from ``[secrets].patterns``, or an empty
                list when configuration is absent, unreadable, malformed, or
                has the wrong shape.
    @details    The hook is a protective convenience layer and must never brick
                tool use because a project configuration cannot be loaded.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-20
    @version    0.1.0
    """
    try:
        config_path = cwd / ".agentic" / "workflow.toml"
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        patterns = data.get("secrets", {}).get("patterns", [])
        if not isinstance(patterns, list):
            return []
        return [pattern for pattern in patterns if isinstance(pattern, str)]
    except Exception:
        return []


if __name__ == "__main__":
    raise SystemExit(main())

# END OF FILE
