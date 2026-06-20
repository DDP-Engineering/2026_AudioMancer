#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file post_tool_evidence.py
@brief Post-tool hook recording agent tool-use evidence.
@details Runs as part of the template hook layer and preserves workflow guard behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-06-20
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys


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
    if payload.get("hook_event_name") != "PostToolUse":
        return 0
    cwd = Path(payload.get("cwd") or ".").resolve()
    current = cwd / ".agentic" / "current_run"
    if not current.exists():
        return 0
    run_id = current.read_text(encoding="utf-8").strip()
    journal = cwd / ".agentic" / "runs" / run_id / "journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "time": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "event": "agentic.tool",
        "data": {
            "tool_name": payload.get("tool_name"),
            "tool_use_id": payload.get("tool_use_id"),
            "has_response": payload.get("tool_response") is not None,
        },
    }
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
