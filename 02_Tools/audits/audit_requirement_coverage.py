#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audit_requirement_coverage.py
@brief Audit per-module requirement coverage for AudioMancer.
@details Implements REQ-TEST-007. Every module under `services/` and
         `ui/controllers/` must be named by at least one requirement that links
         an automated test, or be listed in the coverage waiver file. The waiver
         file records pre-existing gaps so the gate passes today while preventing
         new untested modules from being added.
@author Eng. Dan Dumitru Pasare
@date 2026-06-09
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

from pathlib import Path

from audit_common import (
    AuditIssue,
    main_guard,
    print_report,
    repository_root,
)
from requirements_lib import APP_DIR, load_requirements

# CONSTANTS

WAIVER_FILE = Path(".agentic/requirements/coverage_waivers.txt")
COVERABLE_ROOTS = (
    APP_DIR / "src" / "audiomancer" / "services",
    APP_DIR / "src" / "audiomancer" / "ui" / "controllers",
)
INIT_FILE = "__init__.py"
COMMENT_PREFIX = "#"

# PUBLIC API


def load_waivers(root: Path) -> set[str]:
    """
    @brief      Load the recorded coverage waiver module paths.
    @param[in]  root Repository root path.
    @return     Set of repository-relative waived module paths.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    waiver_path = root / WAIVER_FILE
    if not waiver_path.is_file():
        return set()
    waivers: set[str] = set()
    for raw_line in waiver_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(COMMENT_PREFIX):
            continue
        waivers.add(Path(line).as_posix())
    return waivers


def covered_module_paths(root: Path) -> set[str]:
    """
    @brief      Resolve module paths that a test-linked requirement covers.
    @param[in]  root Repository root path.
    @return     Set of repository-relative module paths with test coverage.
    @exception  RuntimeError Raised when the register directory is missing.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    covered: set[str] = set()
    for requirement in load_requirements(root):
        if not requirement.linked_tests:
            continue
        for component in requirement.related_components:
            covered.add(Path(component).as_posix())
    return covered


def coverable_modules(root: Path) -> list[str]:
    """
    @brief      Resolve service and controller modules that require coverage.
    @param[in]  root Repository root path.
    @return     Ordered repository-relative coverable module paths.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    modules: list[str] = []
    for coverable_root in COVERABLE_ROOTS:
        absolute_root = root / coverable_root
        if not absolute_root.is_dir():
            continue
        for path in sorted(absolute_root.glob("*.py")):
            if path.name == INIT_FILE:
                continue
            modules.append(path.relative_to(root).as_posix())
    return modules


def coverage_issues(root: Path) -> list[AuditIssue]:
    """
    @brief      Gather requirement coverage issues for coverable modules.
    @param[in]  root Repository root path.
    @return     Audit issues for uncovered, unwaived modules and stale waivers.
    @exception  RuntimeError Raised when the register directory is missing.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    covered = covered_module_paths(root)
    waivers = load_waivers(root)
    modules = coverable_modules(root)
    issues: list[AuditIssue] = []
    used_waivers: set[str] = set()
    for module in modules:
        if module in covered:
            continue
        if module in waivers:
            used_waivers.add(module)
            continue
        issues.append(
            AuditIssue(
                path=Path(module),
                line=None,
                code="REQ-COVERAGE-MISSING",
                message=f"{module} has no requirement with a linked test and no waiver.",
            )
        )
    for stale in sorted(waivers - used_waivers):
        issues.append(
            AuditIssue(
                path=WAIVER_FILE,
                line=None,
                code="REQ-COVERAGE-STALE-WAIVER",
                message=f"Waiver for {stale} is no longer needed; remove it.",
            )
        )
    return issues


def run_audit() -> int:
    """
    @brief      Run the requirement coverage audit and print a report.
    @return     Process status code.
    @exception  RuntimeError Raised when repository discovery fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    root = repository_root()
    return print_report("Requirement Coverage Audit", coverage_issues(root))


def main() -> int:
    """
    @brief      Command-line entrypoint for the requirement coverage audit.
    @return     Process status code.
    @exception  RuntimeError Raised when repository discovery fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    return run_audit()


if __name__ == "__main__":
    main_guard(main)


# END OF FILE
