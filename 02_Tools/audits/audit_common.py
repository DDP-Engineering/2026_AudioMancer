#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audit_common.py
@brief Shared helpers for AudioMancer repository audit scripts.
@details Provides repository-root discovery, changed-file selection, and
         report formatting helpers used by the documentation, code-style, and
         logging audit tools.
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys

# CONSTANTS

REPO_MARKER_FILE = "AGENTS.md"
PYTHON_SUFFIX = ".py"

# DATA MODELS / TYPEDEFINITIONS


@dataclass(frozen=True)
class AuditIssue:
    """
    @brief      Structured audit finding reported by one audit script.
    @param[in]  path Repository-relative path for the finding.
    @param[in]  line One-based line number when available.
    @param[in]  code Stable audit issue code.
    @param[in]  message Human-readable issue detail.
    @return     Immutable audit issue record.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """

    path: Path
    line: int | None
    code: str
    message: str


# PUBLIC API


def repository_root(start: Path | None = None) -> Path:
    """
    @brief      Resolve the repository root from a starting path.
    @param[in]  start Optional starting path.
    @return     Repository root path.
    @exception  RuntimeError Raised when no repository marker is found.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / REPO_MARKER_FILE).is_file():
            return candidate
    raise RuntimeError(f"Could not locate repository root containing {REPO_MARKER_FILE}.")


def repo_relative(path: Path, root: Path) -> Path:
    """
    @brief      Convert a path to a repository-relative path when possible.
    @param[in]  path Candidate filesystem path.
    @param[in]  root Repository root path.
    @return     Repository-relative or original path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return path


def changed_files(root: Path, suffix: str | None = None) -> list[Path]:
    """
    @brief      Read Git changed and untracked files for the repository.
    @param[in]  root Repository root path.
    @param[in]  suffix Optional filename suffix filter.
    @return     Ordered repository-relative changed file paths.
    @exception  RuntimeError Raised when Git status cannot be read.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not read git status.")
    paths: list[Path] = []
    for raw_line in result.stdout.splitlines():
        if len(raw_line) < 4:
            continue
        raw_path = raw_line[3:].strip().strip('"')
        if " -> " in raw_path:
            raw_path = raw_path.rsplit(" -> ", maxsplit=1)[-1]
        path = Path(raw_path)
        if suffix is None or path.suffix == suffix:
            paths.append(path)
    return paths


def python_files(root: Path, changed_only: bool = False) -> list[Path]:
    """
    @brief      Resolve Python files to audit.
    @param[in]  root Repository root path.
    @param[in]  changed_only True to limit the scan to changed Git files.
    @return     Ordered repository-relative Python file paths.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if changed_only:
        return [path for path in changed_files(root, PYTHON_SUFFIX) if (root / path).is_file()]
    search_roots = [root / "04_Software" / "AudioMancer", root / "02_Tools"]
    files: list[Path] = []
    for search_root in search_roots:
        if search_root.is_dir():
            files.extend(repo_relative(path, root) for path in search_root.rglob("*.py"))
    return sorted(files)


def print_report(title: str, issues: list[AuditIssue]) -> int:
    """
    @brief      Print one audit report and return a process status code.
    @param[in]  title Report title.
    @param[in]  issues Audit issue list.
    @return     Zero when no issues were found, otherwise one.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    print(title)
    print("=" * len(title))
    if not issues:
        print("No issues found.")
        return 0
    for issue in issues:
        location = str(issue.path)
        if issue.line is not None:
            location = f"{location}:{issue.line}"
        print(f"- [{issue.code}] {location} - {issue.message}")
    return 1


def parse_changed_only(argv: list[str]) -> bool:
    """
    @brief      Parse the shared changed-only command-line flag.
    @param[in]  argv Command-line argument list.
    @return     True when `--changed-only` is present.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return "--changed-only" in argv


def main_guard(callback) -> None:
    """
    @brief      Run an audit entrypoint and convert errors into process exits.
    @param[in]  callback Audit callback with no arguments.
    @return     None.
    @exception  SystemExit Raised with the audit status code.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    try:
        raise SystemExit(callback())
    except RuntimeError as exc:
        print(f"Audit error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


# END OF FILE
