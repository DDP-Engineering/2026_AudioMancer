#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file req_impact.py
@brief Map changed files to impacted AudioMancer requirements and tests.
@details Supports the feature-intake workflow. Given changed files, reports the
         requirement IDs and linked tests that the change touches, and flags
         changed implementation files that no requirement currently covers.
@author Eng. Dan Dumitru Pasare
@date 2026-06-09
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sys

from audit_common import changed_files, repository_root
from requirements_lib import (
    APP_DIR,
    Requirement,
    linked_test_file,
    load_requirements,
)

# CONSTANTS

JSON_FLAG = "--json"
COVERABLE_ROOTS = (
    APP_DIR / "src" / "audiomancer" / "services",
    APP_DIR / "src" / "audiomancer" / "ui" / "controllers",
)
PYTHON_SUFFIX = ".py"

# DATA MODELS / TYPEDEFINITIONS


@dataclass
class FileImpact:
    """
    @brief      Impact summary for one changed file.
    @param[in]  path Repository-relative changed file path.
    @param[in]  requirement_ids Impacted requirement identifiers.
    @param[in]  linked_tests Linked tests for the impacted requirements.
    @param[in]  uncovered True when a coverable file maps to no requirement.
    @return     Mutable per-file impact record.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """

    path: str
    requirement_ids: list[str] = field(default_factory=list)
    linked_tests: list[str] = field(default_factory=list)
    uncovered: bool = False


# PUBLIC API


def _normalize(path: Path | str) -> str:
    """
    @brief      Normalize a path to a forward-slash repository-relative string.
    @param[in]  path Candidate path value.
    @return     Normalized comparison string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    return Path(path).as_posix()


def _component_targets(requirement: Requirement) -> set[str]:
    """
    @brief      Resolve the repository-relative paths a requirement guards.
    @param[in]  requirement Parsed requirement record.
    @return     Normalized component and linked-test file paths.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    targets: set[str] = set()
    for component in requirement.related_components:
        targets.add(_normalize(component))
    for node_id in requirement.linked_tests:
        targets.add(_normalize(APP_DIR / linked_test_file(node_id)))
    return targets


def _matches(changed: str, target: str) -> bool:
    """
    @brief      Report whether a changed path falls under a requirement target.
    @param[in]  changed Normalized changed file path.
    @param[in]  target Normalized requirement target path.
    @return     True when the change touches the target file or directory.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    if changed == target:
        return True
    return changed.startswith(f"{target}/")


def _is_coverable(changed: str) -> bool:
    """
    @brief      Report whether a changed file should be covered by a requirement.
    @param[in]  changed Normalized changed file path.
    @return     True for service and UI controller Python modules.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    if not changed.endswith(PYTHON_SUFFIX) or changed.endswith("__init__.py"):
        return False
    return any(changed.startswith(f"{_normalize(root)}/") for root in COVERABLE_ROOTS)


def analyze(changed: list[Path], requirements: list[Requirement]) -> list[FileImpact]:
    """
    @brief      Build per-file impact records for changed files.
    @param[in]  changed Repository-relative changed file paths.
    @param[in]  requirements Parsed requirement records.
    @return     Ordered per-file impact records.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    targets = [(requirement, _component_targets(requirement)) for requirement in requirements]
    exact_components = {
        _normalize(component)
        for requirement in requirements
        for component in requirement.related_components
    }
    impacts: list[FileImpact] = []
    for raw_path in changed:
        changed_norm = _normalize(raw_path)
        impact = FileImpact(path=changed_norm)
        for requirement, requirement_targets in targets:
            if any(_matches(changed_norm, target) for target in requirement_targets):
                impact.requirement_ids.append(requirement.id)
                impact.linked_tests.extend(requirement.linked_tests)
        impact.requirement_ids = sorted(set(impact.requirement_ids))
        impact.linked_tests = sorted(set(impact.linked_tests))
        # Per-module coverage requires a file-level requirement, not a broad
        # directory-level one such as the cross-cutting security or platform rows.
        impact.uncovered = _is_coverable(changed_norm) and changed_norm not in exact_components
        impacts.append(impact)
    return impacts


def _render_text(impacts: list[FileImpact]) -> str:
    """
    @brief      Render the impact report as readable text.
    @param[in]  impacts Per-file impact records.
    @return     Formatted multi-line report.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    lines = ["Requirement Impact", "=================="]
    if not impacts:
        lines.append("No changed files to analyze.")
        return "\n".join(lines)
    all_requirements: set[str] = set()
    uncovered: list[str] = []
    for impact in impacts:
        lines.append(f"\n{impact.path}")
        if impact.requirement_ids:
            lines.append(f"  requirements: {', '.join(impact.requirement_ids)}")
            for node_id in impact.linked_tests:
                lines.append(f"    test: {node_id}")
            all_requirements.update(impact.requirement_ids)
        elif impact.uncovered:
            lines.append("  requirements: NONE - coverable module needs a requirement")
            uncovered.append(impact.path)
        else:
            lines.append("  requirements: none")
    lines.append("\nSummary")
    lines.append(f"  impacted requirements: {', '.join(sorted(all_requirements)) or 'none'}")
    lines.append(f"  uncovered files: {', '.join(uncovered) or 'none'}")
    return "\n".join(lines)


def _render_json(impacts: list[FileImpact]) -> str:
    """
    @brief      Render the impact report as machine-readable JSON.
    @param[in]  impacts Per-file impact records.
    @return     JSON document string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    payload = {
        "files": [
            {
                "path": impact.path,
                "requirement_ids": impact.requirement_ids,
                "linked_tests": impact.linked_tests,
                "uncovered": impact.uncovered,
            }
            for impact in impacts
        ],
        "impacted_requirements": sorted(
            {req_id for impact in impacts for req_id in impact.requirement_ids}
        ),
        "uncovered_files": [impact.path for impact in impacts if impact.uncovered],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def main() -> int:
    """
    @brief      Command-line entrypoint for the requirement impact tool.
    @return     Process status code.
    @exception  RuntimeError Raised when repository discovery fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    argv = sys.argv[1:]
    as_json = JSON_FLAG in argv
    explicit = [Path(arg) for arg in argv if arg != JSON_FLAG]
    root = repository_root()
    changed = explicit if explicit else changed_files(root)
    requirements = load_requirements(root)
    impacts = analyze(changed, requirements)
    print(_render_json(impacts) if as_json else _render_text(impacts))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Impact error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


# END OF FILE
