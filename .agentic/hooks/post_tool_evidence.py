#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file post_tool_evidence.py
@brief Post-tool hook recording agent tool-use evidence.
@details Resolves worktree-local state through the canonical AEGIS store and
         emits a non-destructive structured warning when no valid run exists.
"""

# IMPORTS

from __future__ import annotations

import json
from pathlib import Path
import sys

# PUBLIC API


def main() -> int:
    """
    @brief      Run command-line entry point workflow behavior.
    @return     Result produced by the workflow helper.
    @exception  None
    """
    payload = json.load(sys.stdin)
    if payload.get("hook_event_name") != "PostToolUse":
        return 0
    cwd = Path(payload.get("cwd") or ".").resolve()
    try:
        from workflow_config_bootstrap import find_repository_root

        repo_root = find_repository_root(cwd)
        source_root = repo_root / ".agentic" / "cli" / "src"
        source_text = str(source_root)
        if source_text not in sys.path:
            sys.path.insert(0, source_text)
        from aegis.store import append_journal, resolve_run_id

        run_id = resolve_run_id(repo_root)
    except Exception as exc:
        serializer = getattr(exc, "to_dict", None)
        error = serializer() if callable(serializer) else {"message": str(exc)}
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": str(exc),
                    },
                    "warning": error,
                },
                sort_keys=True,
            )
        )
        return 0
    append_journal(
        repo_root,
        run_id,
        "agentic.tool",
        {
            "tool_name": payload.get("tool_name"),
            "tool_use_id": payload.get("tool_use_id"),
            "has_response": payload.get("tool_response") is not None,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# END OF FILE
