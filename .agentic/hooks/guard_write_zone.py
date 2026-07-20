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
@brief Pre-tool hook enforcing stage-specific write zones.
@details Runs as part of the template hook layer and preserves workflow guard behavior.
@details ``matches`` (0.2.0, architecture-review follow-up) is now
         case-sensitive on non-Windows hosts, matching the real filesystem.
@details When hooks are installed but no run has been started, non-``.agentic``
         edits remain denied and the message explains how to start a run before
         retrying.
@author Eng. Dan Dumitru Pasare
@date 2026-07-20
@version 0.3.0
"""

# IMPORTS

from __future__ import annotations

from fnmatch import fnmatchcase
import json
import os
from pathlib import Path
import re
import sys
import tomllib

# CONSTANTS

# @brief Built-in edit allowlist used when `.agentic/workflow.toml` is missing
#        or omits a stage-specific `write_zones` entry.
DEFAULT_ZONES = {
    # Intake may only create or update workflow bookkeeping.
    "intake": [".agentic/**"],

    # Intent alignment records structured understanding in workflow state.
    "alignment": [".agentic/**"],

    # Adoption intake and alignment may update adoption workflow state.
    "adoption-intake": [".agentic/**"],
    "adoption-alignment": [".agentic/**"],

    # Requirement work can update durable requirement registers.
    "requirement": [".agentic/requirements/**"],

    # Check work is limited to test roots so tests can be authored before code.
    "check": ["tests/**", "test/**"],

    # Implementation work touches product code and required component docs.
    "implementation": ["src/**", "app/**", "lib/**", ".agentic/knowledge/components/**"],

    # Validation is intentionally read-only; evidence is recorded through CLI commands.
    "validation": [],

    # Delivery may update workflow reports and final run metadata.
    "delivery": [".agentic/**"],
}

# @brief Broad-maintenance mode allowlist; protected paths still remain blocked.
REPO_WIDE_ZONES = ["**"]

# @brief Non-negotiable denylist applied even when access mode is `repo-wide`.
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


# PUBLIC API


def main() -> int:
    """
    @brief      Run command-line entry point workflow behavior.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-20
    @version    0.2.0
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
    stage, has_run = read_stage_state(cwd)
    access_mode = read_access_mode(cwd)
    zones = (
        REPO_WIDE_ZONES
        if access_mode == "repo-wide"
        else load_zones(cwd).get(stage, DEFAULT_ZONES.get(stage, []))
    )
    if not zones:
        return deny(f"Stage '{stage}' is read-only; file edits are not allowed.")
    tool_input = payload.get("tool_input", {})
    blocked = []
    escaped = []
    for path in extract_target_paths(tool_input):
        try:
            rel = normalize(path, cwd)
        except ValueError:
            escaped.append(path)
            continue
        if is_protected_path(rel):
            blocked.append(rel)
            continue
        if not any(matches(rel, pattern) for pattern in zones):
            blocked.append(rel)
    if escaped:
        return deny(f"Edit escapes workspace root: {', '.join(escaped)}")
    if blocked:
        if not has_run:
            return deny(
                "No active AEGIS run: edits outside .agentic/ are blocked. "
                "Start a run first (e.g. "
                '`.\\.agentic\\tools\\run.ps1 start --kind feature --statement "..."` / '
                '`bash .agentic/tools/run.sh start --kind feature --statement "..."`), '
                f"then retry. Blocked: {', '.join(blocked)}"
            )
        return deny(f"Edit outside '{stage}' write zone: {', '.join(blocked)}")
    return 0


# HELPER FUNCTIONS


def read_stage_state(cwd: Path) -> tuple[str, bool]:
    """
    @brief      Read the current stage and whether an active run exists.
    @param[in]  cwd Repository root the hook resolves against.
    @return     ``(stage, has_run)``; absent, missing, or invalid run state
                returns ``("intake", False)``.
    @details    Keeps stage lookup and active-run detection consistent for one
                hook decision while parsing the run graph only once.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-20
    @version    0.1.0
    """
    current = cwd / ".agentic" / "current_run"
    if not current.exists():
        return "intake", False
    graph = cwd / ".agentic" / "runs" / current.read_text(encoding="utf-8").strip() / "graph.json"
    if not graph.exists():
        return "intake", False
    try:
        stage = json.loads(graph.read_text(encoding="utf-8")).get("stage", "intake")
    except json.JSONDecodeError:
        return "intake", False
    return stage, True


def read_stage(cwd: Path) -> str:
    """
    @brief      Read the active workflow stage with an ``intake`` fallback.
    @param[in]  cwd Repository root the hook resolves against.
    @return     Active stage, or ``intake`` when no readable run exists.
    @details    Compatibility wrapper for callers that only need the stage;
                :func:`read_stage_state` also exposes active-run presence for
                actionable denial messages.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-20
    @version    0.2.0
    """
    return read_stage_state(cwd)[0]


def read_access_mode(cwd: Path) -> str:
    """
    @brief      Read access mode workflow behavior.
    @param[in]  cwd Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    current = cwd / ".agentic" / "current_run"
    if not current.exists():
        return "standard"
    graph = cwd / ".agentic" / "runs" / current.read_text(encoding="utf-8").strip() / "graph.json"
    if not graph.exists():
        return "standard"
    try:
        return json.loads(graph.read_text(encoding="utf-8")).get("access_mode", "standard")
    except json.JSONDecodeError:
        return "standard"


def load_zones(cwd: Path) -> dict[str, list[str]]:
    """
    @brief      Load zones workflow behavior.
    @param[in]  cwd Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    config = cwd / ".agentic" / "workflow.toml"
    if not config.exists():
        return DEFAULT_ZONES
    data = tomllib.loads(config.read_text(encoding="utf-8"))

    # Project configuration overrides only the stages it names; omitted stages
    # keep the conservative built-in defaults above.
    return {**DEFAULT_ZONES, **data.get("write_zones", {})}


def extract_target_paths(tool_input: dict) -> list[str]:
    """
    @brief      Collect edited paths from a tool-use payload across agents.
    @param[in]  tool_input Mapping of the intercepted tool-use arguments.
    @return     Paths the tool intends to edit, in repo-relative or absolute form.
    @details    Supports the Codex ``apply_patch`` command envelope, the Claude
                Code ``Edit``/``Write``/``MultiEdit`` ``file_path`` argument, and
                the Qwen Code ``WriteFile``/``write_file`` ``file_path`` argument so
                the write-zone guard applies identically across every adapter.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    paths: list[str] = []
    command = tool_input.get("command", "")
    if isinstance(command, str) and command:
        paths.extend(extract_patch_paths(command))
    file_path = tool_input.get("file_path")
    if isinstance(file_path, str) and file_path:
        paths.append(file_path)
    return paths


def extract_patch_paths(command: str) -> list[str]:
    """
    @brief      Extract patch paths workflow behavior.
    @param[in]  command Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
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
    @version    0.1.0
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = cwd / candidate
    try:
        return candidate.resolve().relative_to(cwd).as_posix()
    except ValueError as exc:
        raise ValueError(path) from exc


# @note Mirrors `aegis.paths.matches_pattern`. This hook runs as a
#       standalone, stdlib-only script with no package import, so the small
#       matcher is duplicated here on purpose.
def matches(path: str, pattern: str) -> bool:
    """
    @brief      Match matches workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @param[in]  pattern Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @details    Case-folded only on Windows (``os.name == "nt"``), added
                0.2.0 (architecture-review follow-up), mirroring
                ``aegis.paths.matches_pattern``: the previous unconditional
                ``.lower()`` could match/miss write-zone patterns
                inconsistently with the real, case-sensitive filesystem on
                Ubuntu/Linux. Uses ``fnmatch.fnmatchcase`` rather than
                ``fnmatch.fnmatch``: the latter applies its own OS-tied
                ``os.path.normcase`` internally, which would silently
                reintroduce Windows-only case-insensitivity regardless of
                this function's own ``os.name`` check.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-18
    @version    0.2.0
    """
    path = path.replace("\\", "/")
    pattern = pattern.replace("\\", "/").rstrip("/")
    if os.name == "nt":
        path = path.lower()
        pattern = pattern.lower()
    return fnmatchcase(path, pattern) or fnmatchcase(path, f"{pattern}/**")


def is_protected_path(path: str) -> bool:
    """
    @brief      Check is protected path workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return any(matches(path, pattern) for pattern in PROTECTED_PATH_PATTERNS)


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
