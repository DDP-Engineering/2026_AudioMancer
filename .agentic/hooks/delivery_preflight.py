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
@brief Pre-tool hook enforcing deterministic verification and closed delivery.
@details Command fragments come only from validated
         ``guardrails.delivery.command_patterns``. Disabled policy has no
         implicit publish commands, and configuration errors deny pre-tool use.
"""

# IMPORTS

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# PUBLIC API


def main() -> int:
    """
    @brief      Run command-line entry point workflow behavior.
    @return     Result produced by the workflow helper.
    @exception  None
    """
    payload = json.load(sys.stdin)
    if payload.get("hook_event_name") != "PreToolUse":
        return 0
    if payload.get("tool_name") not in {"Bash", "run_shell_command"}:
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    if not isinstance(command, str):
        command = ""
    normalized = " ".join(command.lower().split())
    cwd = Path(payload.get("cwd") or ".").resolve()
    try:
        from workflow_config_bootstrap import find_repository_root, load_workflow_config

        repo_root = find_repository_root(cwd)
        policy = load_workflow_config(repo_root).delivery
    except Exception as exc:
        return deny(str(exc))
    if policy.mode == "disabled":
        return 0
    if not any(pattern in normalized for pattern in policy.command_patterns):
        return 0
    launcher = repo_root / ".agentic" / "tools" / "run_aegis.py"
    if not launcher.exists():
        return deny(
            "Agentic workflow launcher not found. Expected .agentic/tools/run_aegis.py."
        )
    verification = _run_aegis(repo_root, launcher, "verify", "run", "--json")
    if verification.returncode != 0:
        detail = (verification.stderr or verification.stdout).strip()
        reason = (
            "Deterministic verification failed. Resolve every blocking result "
            "before publishing."
        )
        if detail:
            reason = f"{reason}\n{detail}"
        return deny(reason)
    delivery = _run_aegis(repo_root, launcher, "delivery", "show", "--json")
    try:
        state = json.loads(delivery.stdout)
    except json.JSONDecodeError:
        state = {}
    if delivery.returncode != 0 or state.get("complete") is not True:
        detail = (delivery.stderr or delivery.stdout).strip()
        reason = "AEGIS delivery is not closed. Complete the delivery stage before publishing."
        if detail:
            reason = f"{reason}\n{detail}"
        return deny(reason)
    return 0


def _run_aegis(
    repo_root: Path,
    launcher: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    """
    @brief Run one grouped AEGIS command for the outward-action guard.
    @param[in] repo_root Repository root.
    @param[in] launcher Project-local AEGIS launcher.
    @param[in] args Grouped AEGIS arguments.
    @return Captured process result.
    """
    return subprocess.run(
        [sys.executable, str(launcher), *args],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def deny(message: str) -> int:
    """
    @brief      Emit the common pre-tool denial envelope.
    @param[in]  message Actionable policy or preflight reason.
    @return     Zero as required by adapter hook transports.
    """
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": message,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# END OF FILE
