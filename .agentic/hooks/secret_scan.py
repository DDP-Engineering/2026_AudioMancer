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
@brief Pre-tool hook enforcing configured secret scanning policy.
@details Uses only patterns validated under ``guardrails.secrets`` by the
         canonical parser. Missing or invalid policy is an actionable deny;
         disabled scanning carries no dormant built-in expressions.
@details Serializes the scanned tool input with ``ensure_ascii=False`` (0.4.0,
         code-review follow-up) so a configured pattern can match a secret that
         contains non-ASCII characters instead of comparing it against
         ``\\uXXXX`` escapes.
@author Eng. Dan Dumitru Pasare
@date 2026-07-24
@version 0.4.0
"""

# IMPORTS

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# PUBLIC API


def main() -> int:
    """
    @brief      Scan pre-tool input with the active configured expressions.
    @return     Zero after allowing the input or emitting a deny decision.
    @details    Configuration errors deny the operation before its content is
                evaluated so unknown policy never becomes an implicit allow.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.3.0
    """
    payload = json.load(sys.stdin)
    if payload.get("hook_event_name") != "PreToolUse":
        return 0
    cwd = Path(payload.get("cwd") or ".").resolve()
    try:
        from workflow_config_bootstrap import load_workflow_config

        policy = load_workflow_config(cwd).secrets
    except Exception as exc:
        return deny(str(exc))
    if policy.mode == "disabled":
        return 0
    compiled_patterns = [re.compile(pattern) for pattern in policy.patterns]
    # `ensure_ascii=False` keeps non-ASCII characters literal. With the default
    # escaping a secret containing accented or non-Latin characters would be
    # serialized as `\uXXXX` escapes, and a pattern written to match the real
    # characters would never fire against that escaped text.
    text = json.dumps(payload.get("tool_input", {}), ensure_ascii=False)
    if any(pattern.search(text) for pattern in compiled_patterns):
        return deny("Possible secret detected by configured workflow policy.")
    return 0


def deny(message: str) -> int:
    """
    @brief      Emit the common pre-tool denial envelope.
    @param[in]  message Actionable policy or match reason.
    @return     Zero as required by adapter hook transports.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.2.0
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
