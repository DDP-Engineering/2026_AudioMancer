#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file delivery_preflight.py
@brief Hook entry point for delivery preflight validation.
@details Runs as part of the template hook layer and preserves workflow guard behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-06-20
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# @brief Publish-like shell command fragments that require delivery preflight.
DELIVERY_PATTERNS = ("git push", "gh pr create", "git merge")


def main() -> int:
    """
    @brief      Run command-line entry point workflow behavior.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    payload = json.load(sys.stdin)
    if payload.get("hook_event_name") != "PreToolUse":
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    normalized = " ".join(command.lower().split())
    if not any(pattern in normalized for pattern in DELIVERY_PATTERNS):
        return 0
    cwd = Path(payload.get("cwd") or ".").resolve()
    launcher = cwd / ".agentic" / "tools" / "run_aegis.py"
    if not launcher.exists():
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "Agentic workflow launcher not found. Expected .agentic/tools/run_aegis.py.",
                    }
                }
            )
        )
        return 0
    result = subprocess.run(
        [sys.executable, str(launcher), "delivery-preflight"],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "Delivery preflight failed. Resolve blocking invariants before publishing.",
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
