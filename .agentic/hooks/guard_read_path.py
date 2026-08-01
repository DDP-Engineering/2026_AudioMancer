#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file guard_read_path.py
@brief Pre-tool hook enforcing configured protected-read policy.
@details Loads the canonical schema-version-3 workflow model and applies only
         ``guardrails.protected_paths`` patterns configured for ``read``.
         The hook contains no native repository denylist or fallback policy.
@details Covers the search and listing tools as well as the single-file read
         tool (0.2.0). A policy that only inspected the canonical read tool was
         bypassable by asking the same host for the same bytes through its grep
         tool, so every adapter now routes its content-reading *and*
         path-enumerating tools here.
@details **Known limitation.** An unscoped repository-wide search carries no
         path argument to inspect, so it is allowed and may still surface lines
         from a protected file in its results. This hook blocks a protected path
         from being *targeted*; it cannot redact a result set, because no
         supported host lets a pre-tool hook rewrite tool output. Treat
         ``protected_paths`` read policy as a guard against direct access, and
         keep genuine secrets out of the working tree.
"""

# IMPORTS

from __future__ import annotations

import json
from pathlib import Path
import sys


# @brief Tools that read the contents of one named file. A payload carrying no
#        path is a malformed read, so it is denied rather than allowed: these
#        tools cannot operate without a target.
CONTENT_READ_TOOLS = frozenset(
    {
        # Claude Code / generic
        "Read",
        "read",
        "ReadFile",
        # Qwen Code canonical + display + legacy aliases
        "read_file",
        "ReadFileTool",
        "read_many_files",
        "ReadManyFiles",
        "ReadManyFilesTool",
    }
)

# @brief Tools that search file content or enumerate paths. Their scope
#        argument is optional — an unscoped call means "the whole repository" —
#        so a payload with no path is allowed rather than denied. Denying every
#        unscoped search would make the policy unusable, and an unscoped search
#        is the documented residual limitation above. Any path they *do* carry
#        is still checked.
SEARCH_TOOLS = frozenset(
    {
        # Claude Code
        "Grep",
        "Glob",
        # Qwen Code canonical + display + legacy aliases
        "grep_search",
        "GrepTool",
        "search_file_content",
        "SearchFiles",
        "glob",
        "GlobTool",
        "FindFiles",
        "list_directory",
        "ListFiles",
        "ListFilesTool",
        "ReadFolder",
        # OpenCode
        "grep",
        "list",
        # Pi
        "find",
        "ls",
    }
)

# @brief Keys whose value is a single concrete path.
PATH_KEYS = ("file_path", "filePath", "path", "filename", "absolute_path", "dir", "directory")

# @brief Keys whose value is a list of paths or path globs.
PATH_LIST_KEYS = ("paths", "filenames", "include", "includes")

# @brief Tools whose ``pattern`` argument is a *path* glob rather than a content
#        regex. `Grep`'s `pattern` matches file contents and must never be read
#        as a path; `Glob`'s names the paths themselves.
GLOB_PATTERN_TOOLS = frozenset({"Glob", "glob", "GlobTool", "FindFiles", "find"})


# PUBLIC API


def main() -> int:
    """
    @brief      Evaluate one adapter read against validated repository policy.
    @return     Zero after allowing the read or emitting a deny decision.
    @exception  None Configuration and path failures become hook denials.
    @details    A tool this hook does not recognize is treated as a content read
                (0.2.0): an unknown tool wired to this hook by an adapter is far
                more likely to be a read under a name not yet listed than a
                search, and the strict branch is the safe way to be wrong.
    """
    payload = json.load(sys.stdin)
    if payload.get("hook_event_name") != "PreToolUse":
        return 0
    cwd = Path(payload.get("cwd") or ".").resolve()
    try:
        from workflow_config_bootstrap import find_repository_root, load_workflow_config

        repo_root = find_repository_root(cwd)
        config = load_workflow_config(repo_root)
        policy = config.protected_paths
        if policy.mode == "disabled" or "read" not in policy.operations:
            return 0

        tool_name = payload.get("tool_name")
        tool_name = tool_name if isinstance(tool_name, str) else ""
        targets = extract_target_paths(payload.get("tool_input", {}), tool_name)
        if not targets:
            # A search with no scope argument means the whole repository. It is
            # allowed, per the documented limitation in the module docstring.
            # Anything else reaching here is a read that named no file.
            if tool_name in SEARCH_TOOLS:
                return 0
            return deny("Protected-read policy could not determine the requested path.")

        from aegis.paths import matches_pattern, relative_to_root

        for target in targets:
            relative_path = relative_to_root(target, repo_root)
            if any(matches_pattern(relative_path, pattern) for pattern in policy.patterns):
                return deny(f"Reading configured protected path is blocked: {relative_path}")
    except Exception as exc:
        return deny(str(exc))
    return 0


def extract_target_paths(tool_input: object, tool_name: str = "") -> list[str]:
    """
    @brief      Extract every read target from supported adapter argument shapes.
    @param[in]  tool_input Adapter tool input mapping.
    @param[in]  tool_name Tool the payload belongs to; selects how ``pattern``
                is interpreted.
    @return     Non-empty path strings, in discovery order, without duplicates.
    @details    Returns every path the call names rather than the first one
                (0.2.0), because the multi-file read and search tools scope
                themselves with a *list* of paths or globs and checking only the
                first would let the rest through unexamined.
    @details    ``pattern`` is read only for the glob-style tools in
                :data:`GLOB_PATTERN_TOOLS`. For a grep-style tool the same key
                holds a content regex, and treating that as a path would compare
                arbitrary regex text against the protected patterns — producing
                both false blocks and a misleading denial message.
    @exception  None
    """
    if not isinstance(tool_input, dict):
        return []
    found: list[str] = []

    def add(value: object) -> None:
        """@brief Record one non-empty string path, ignoring anything else."""
        if isinstance(value, str) and value and value not in found:
            found.append(value)

    for key in PATH_KEYS:
        add(tool_input.get(key))
    for key in PATH_LIST_KEYS:
        value = tool_input.get(key)
        if isinstance(value, (list, tuple)):
            for item in value:
                add(item)
        else:
            add(value)
    if tool_name in GLOB_PATTERN_TOOLS:
        add(tool_input.get("pattern"))
    return found


def deny(message: str) -> int:
    """
    @brief      Emit the common pre-tool denial envelope.
    @param[in]  message Actionable reason shown to the agent.
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
