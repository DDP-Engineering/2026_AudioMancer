#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file guard_write_zone.py
@brief Pre-tool hook enforcing configured write policy.
@details Uses the canonical ``aegis.config`` model and shared path matcher;
         it contains no repository paths, patterns, or implicit write zones.
@details When stage-restricted hook behavior needs a run, missing or stale
         state denies the edit with the canonical actionable resolver error.
@details Active stage and access mode are resolved directly through the
         canonical AEGIS store API.
@author Eng. Dan Dumitru Pasare
@date 2026-07-22
@details `extract_target_paths` (0.7.0) reads the `apply_patch` envelope from
         any of the keys a host may use, not `command` alone, so a patch that
         arrives under a different key still yields paths to check.
@version 0.7.0
"""

# IMPORTS

from __future__ import annotations

import json
from pathlib import Path
import re
import sys


# @brief Argument keys that may carry an `apply_patch` envelope, in the order
#        they are read. Hosts disagree on the name: Codex sends `command`, and
#        the OpenCode adapter already probes `command`/`cmd`/`script` before
#        falling back to `patch`/`input`. Every key is read rather than only
#        the first that matches, because a host is free to send more than one
#        and missing the populated one means extracting no paths at all.
PATCH_ENVELOPE_KEYS = ("command", "cmd", "script", "patch", "input")


# PUBLIC API


def main() -> int:
    """
    @brief      Run command-line entry point workflow behavior.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.4.0
    """
    payload = json.load(sys.stdin)
    if payload.get("hook_event_name") != "PreToolUse":
        return 0
    # Accept the file-editing tool names emitted by every supported adapter:
    # Codex (`apply_patch`), Claude Code (`Edit`/`Write`/`MultiEdit`), and Qwen
    # Code (`WriteFile`, plus the raw `write_file`/`replace` tool ids). Omitting a
    # name here would silently bypass the write-zone guard for that adapter.
    if payload.get("tool_name") not in {
        "apply_patch",
        "Edit",
        "Write",
        "MultiEdit",
        "WriteFile",
        "write_file",
        "replace",
    }:
        return 0
    cwd = Path(payload.get("cwd") or ".").resolve()
    try:
        from workflow_config_bootstrap import find_repository_root, load_workflow_config

        repo_root = find_repository_root(cwd)
        config = load_workflow_config(repo_root)
        if config.write_access.mode == "unrestricted":
            stage = "unrestricted"
            zones = None
        else:
            _, stage, access_mode = read_run_state(repo_root)
            zones = None if access_mode == "repo-wide" else config.write_access.stages[stage]
    except Exception as exc:
        return deny(str(exc))
    if zones == ():
        return deny(f"Stage '{stage}' is read-only; file edits are not allowed.")
    tool_input = payload.get("tool_input", {})
    blocked = []
    escaped = []
    for path in extract_target_paths(tool_input):
        try:
            rel = normalize(path, repo_root)
        except ValueError:
            escaped.append(path)
            continue
        if is_protected_path(rel, config.protected_paths):
            blocked.append(rel)
            continue
        if zones is not None and not any(matches(rel, pattern) for pattern in zones):
            blocked.append(rel)
    if escaped:
        return deny(f"Edit escapes workspace root: {', '.join(escaped)}")
    if blocked:
        return deny(f"Edit outside '{stage}' write zone: {', '.join(blocked)}")
    return 0


# HELPER FUNCTIONS


def read_run_state(cwd: Path) -> tuple[Path, str, str]:
    """
    @brief      Load stage and access mode through the shared state API.
    @param[in]  cwd Hook working directory or a path inside the repository.
    @return     Repository root, active stage, and run-local access mode.
    @exception  RunResolutionError If no valid worktree selection exists.
    @exception  RuntimeError If the delivered AEGIS package cannot be found.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.2.0
    """
    from workflow_config_bootstrap import find_repository_root

    repo_root = find_repository_root(cwd)
    source_root = repo_root / ".agentic" / "cli" / "src"
    source_text = str(source_root)
    if source_text not in sys.path:
        sys.path.insert(0, source_text)
    from aegis.store import load_graph, resolve_run_id

    run_id = resolve_run_id(repo_root)
    graph = load_graph(repo_root, run_id)
    return repo_root, graph.stage, graph.access_mode


def extract_target_paths(tool_input: dict) -> list[str]:
    """
    @brief      Collect edited paths from a tool-use payload across agents.
    @param[in]  tool_input Mapping of the intercepted tool-use arguments.
    @return     Paths the tool intends to edit, in repo-relative or absolute form.
    @details    Supports the Codex ``apply_patch`` command envelope, the Claude
                Code ``Edit``/``Write``/``MultiEdit`` ``file_path`` argument, and
                the Qwen Code ``WriteFile``/``write_file`` ``file_path`` argument so
                the write-zone guard applies identically across every adapter.
    @details    The patch envelope is read from any of ``command``, ``cmd``,
                ``script``, ``patch``, or ``input`` (0.2.0). Hosts disagree on
                which key carries it, and this function is the shared
                implementation every adapter feeds — the OpenCode adapter
                already hedged across the same keys on its own side, which only
                helped the calls routed through it. A patch arriving under an
                unread key produced no paths at all, and a guard that extracts
                no paths finds nothing to block.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-23
    @version    0.2.0
    """
    paths: list[str] = []
    for key in PATCH_ENVELOPE_KEYS:
        candidate = tool_input.get(key)
        if isinstance(candidate, str) and candidate:
            paths.extend(extract_patch_paths(candidate))
    file_path = tool_input.get("file_path")
    if isinstance(file_path, str) and file_path:
        paths.append(file_path)
    # Two keys can carry the same patch text, so the same path can be found
    # twice; the caller checks each path against the write zone and duplicate
    # findings would report one violation more than once.
    return list(dict.fromkeys(paths))


def extract_patch_paths(command: str) -> list[str]:
    """
    @brief      Extract patch paths workflow behavior.
    @param[in]  command Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.1.0
    """
    paths = []
    for line in command.splitlines():
        match = re.match(r"\*\*\* (?:Add|Update|Delete) File: (.+)", line)
        if match:
            paths.append(match.group(1).strip())
    return paths


def normalize(path: str, cwd: Path) -> str:
    """
    @brief      Normalize workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @param[in]  cwd Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.2.0
    """
    from aegis.paths import relative_to_root

    return relative_to_root(path, cwd)


def matches(path: str, pattern: str) -> bool:
    """
    @brief      Match matches workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @param[in]  pattern Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @details    Delegates to the canonical package matcher imported by the
                shared hook bootstrap.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.3.0
    """
    from aegis.paths import matches_pattern

    return matches_pattern(path, pattern)


def is_protected_path(path: str, policy) -> bool:  # type: ignore[no-untyped-def]
    """
    @brief      Check is protected path workflow behavior.
    @param[in]  path Normalized repository-relative path.
    @param[in]  policy Validated protected-path policy.
    @return     Whether configured policy blocks a write to `path`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.3.0
    """
    return (
        policy.mode == "enforce"
        and "write" in policy.operations
        and any(matches(path, pattern) for pattern in policy.patterns)
    )


def deny(message: str) -> int:
    """
    @brief      Return deny workflow behavior.
    @param[in]  message Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
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
