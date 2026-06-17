# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.

from __future__ import annotations

from fnmatch import fnmatch
import json
from pathlib import Path
import re
import sys
import tomllib

DEFAULT_ZONES = {
    "intake": [".agentic/**"],
    "requirement": [".agentic/specs/**", "spec/**", "docs/spec/**"],
    "check": ["tests/**", "test/**"],
    "implementation": ["src/**", "app/**", "lib/**", "05_SoftwareDocu/**"],
    "validation": [],
    "delivery": [".agentic/**"],
}


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("hook_event_name") != "PreToolUse":
        return 0
    if payload.get("tool_name") not in {"apply_patch", "Edit", "Write"}:
        return 0
    cwd = Path(payload.get("cwd") or ".").resolve()
    stage = read_stage(cwd)
    zones = load_zones(cwd).get(stage, DEFAULT_ZONES.get(stage, []))
    if not zones:
        return deny(f"Stage '{stage}' is read-only; file edits are not allowed.")
    command = payload.get("tool_input", {}).get("command", "")
    blocked = []
    escaped = []
    for path in extract_patch_paths(command):
        try:
            rel = normalize(path, cwd)
        except ValueError:
            escaped.append(path)
            continue
        if not any(matches(rel, pattern) for pattern in zones):
            blocked.append(rel)
    if escaped:
        return deny(f"Edit escapes workspace root: {', '.join(escaped)}")
    if blocked:
        return deny(f"Edit outside '{stage}' write zone: {', '.join(blocked)}")
    return 0


def read_stage(cwd: Path) -> str:
    current = cwd / ".agentic" / "current_run"
    if not current.exists():
        return "intake"
    graph = cwd / ".agentic" / "runs" / current.read_text(encoding="utf-8").strip() / "graph.json"
    if not graph.exists():
        return "intake"
    try:
        return json.loads(graph.read_text(encoding="utf-8")).get("stage", "intake")
    except json.JSONDecodeError:
        return "intake"


def load_zones(cwd: Path) -> dict[str, list[str]]:
    config = cwd / ".agentic" / "workflow.toml"
    if not config.exists():
        return DEFAULT_ZONES
    data = tomllib.loads(config.read_text(encoding="utf-8"))
    return {**DEFAULT_ZONES, **data.get("write_zones", {})}


def extract_patch_paths(command: str) -> list[str]:
    paths = []
    for line in command.splitlines():
        match = re.match(r"\*\*\* (?:Add|Update|Delete) File: (.+)", line)
        if match:
            paths.append(match.group(1).strip())
    return paths


def normalize(path: str, cwd: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = cwd / candidate
    try:
        return candidate.resolve().relative_to(cwd).as_posix()
    except ValueError as exc:
        raise ValueError(path) from exc


def matches(path: str, pattern: str) -> bool:
    pattern = pattern.replace("\\", "/").rstrip("/")
    return fnmatch(path.lower(), pattern.lower()) or fnmatch(path.lower(), f"{pattern.lower()}/**")


def deny(message: str) -> int:
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
