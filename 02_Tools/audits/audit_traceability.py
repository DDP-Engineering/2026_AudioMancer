#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audit_traceability.py
@brief Audit requirement-to-test traceability for AudioMancer registers.
@details Implements REQ-AUDIO-TEST-006. Verifies that every linked test node in
         the requirement registers resolves to a real test, and that every
         Active requirement names a resolvable automated test or an explicit
         manual verification method. Test nodes are resolved by static analysis
         by default, or by pytest collection with `--collect`.
@author Eng. Dan Dumitru Pasare
@date 2026-06-09
@version 0.2.0
"""

# IMPORTS

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from audit_common import (
    AuditIssue,
    main_guard,
    print_report,
    repository_root,
)
from requirements_lib import (
    APP_DIR,
    Requirement,
    collect_defined_test_nodes,
    linked_test_file,
    load_requirements,
)

# CONSTANTS

NODE_FILE_FLAG = "--node-file"
COLLECT_FLAG = "--collect"
PYTEST_COLLECT_COMMANDS = (
    ["uv", "run", "pytest", "--collect-only", "-q", "tests"],
    ["python", "-m", "pytest", "--collect-only", "-q", "tests"],
)

# PUBLIC API


def _parse_node_ids(text: str) -> set[str]:
    """
    @brief      Extract pytest node identifiers from collection output.
    @param[in]  text Raw `pytest --collect-only -q` output.
    @return     Set of `tests/...::node` identifiers found in the output.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    nodes: set[str] = set()
    for raw_line in text.splitlines():
        candidate = raw_line.strip()
        if "::" not in candidate or not candidate.startswith("tests/"):
            continue
        nodes.add(candidate)
        # Also register a file::function alias so class-method node IDs match
        # function-style register links.
        if candidate.count("::") >= 2:
            file_part = candidate.split("::", maxsplit=1)[0]
            last = candidate.rsplit("::", maxsplit=1)[-1]
            nodes.add(f"{file_part}::{last}")
    return nodes


def collect_pytest_nodes(app_dir: Path) -> set[str]:
    """
    @brief      Collect pytest node identifiers for the application test suite.
    @param[in]  app_dir Absolute path to the AudioMancer application directory.
    @return     Set of collected pytest node identifiers.
    @exception  RuntimeError Raised when no pytest runner can collect tests.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    last_error = "no pytest runner available"
    for command in PYTEST_COLLECT_COMMANDS:
        try:
            result = subprocess.run(
                command,
                cwd=app_dir,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError:
            continue
        nodes = _parse_node_ids(result.stdout)
        if nodes:
            return nodes
        last_error = result.stderr.strip() or result.stdout.strip() or last_error
    raise RuntimeError(f"Could not collect pytest nodes: {last_error}")


def resolve_nodes(root: Path, *, use_collect: bool, node_file: Path | None) -> set[str]:
    """
    @brief      Resolve the known-test node set used to validate links.
    @param[in]  root Repository root path.
    @param[in]  use_collect True to use pytest collection instead of static analysis.
    @param[in]  node_file Optional precollected node-id file path.
    @return     Set of known test node identifiers.
    @exception  RuntimeError Raised when pytest collection is requested but fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    if node_file is not None:
        return _parse_node_ids(node_file.read_text(encoding="utf-8"))
    if use_collect:
        return collect_pytest_nodes(root / APP_DIR)
    return collect_defined_test_nodes(root / APP_DIR)


def evaluate_requirement(
    requirement: Requirement, nodes: set[str], node_files: set[str]
) -> list[AuditIssue]:
    """
    @brief      Evaluate one requirement against the known test nodes.
    @param[in]  requirement Parsed requirement record.
    @param[in]  nodes Known test node identifiers.
    @param[in]  node_files Known test file paths.
    @return     Audit issues found for the requirement.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    issues: list[AuditIssue] = []
    for node_id in requirement.linked_tests:
        if "::" in node_id:
            if node_id not in nodes:
                issues.append(
                    AuditIssue(
                        path=requirement.source_file,
                        line=requirement.line,
                        code="REQ-LINK-MISSING",
                        message=f"{requirement.id} links unresolved test node {node_id}.",
                    )
                )
        elif node_id not in node_files:
            issues.append(
                AuditIssue(
                    path=requirement.source_file,
                    line=requirement.line,
                    code="REQ-LINK-MISSING",
                    message=f"{requirement.id} links unresolved test file {node_id}.",
                )
            )
    if requirement.is_active and not requirement.linked_tests and not requirement.has_manual_verification:
        issues.append(
            AuditIssue(
                path=requirement.source_file,
                line=requirement.line,
                code="REQ-NO-VERIFICATION",
                message=f"{requirement.id} is Active without a linked test or manual method.",
            )
        )
    return issues


def audit_issues(
    root: Path, *, use_collect: bool = False, node_file: Path | None = None
) -> list[AuditIssue]:
    """
    @brief      Gather all requirement traceability issues for the repository.
    @param[in]  root Repository root path.
    @param[in]  use_collect True to resolve nodes via pytest collection.
    @param[in]  node_file Optional precollected node-id file path.
    @return     Ordered audit issues across every register requirement.
    @exception  RuntimeError Raised when node resolution fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    requirements = load_requirements(root)
    nodes = resolve_nodes(root, use_collect=use_collect, node_file=node_file)
    node_files = {linked_test_file(node) for node in nodes}
    issues: list[AuditIssue] = []
    for requirement in requirements:
        issues.extend(evaluate_requirement(requirement, nodes, node_files))
    return issues


def run_audit(*, use_collect: bool = False, node_file: Path | None = None) -> int:
    """
    @brief      Run the requirement traceability audit and print a report.
    @param[in]  use_collect True to resolve nodes via pytest collection.
    @param[in]  node_file Optional precollected node-id file path.
    @return     Process status code.
    @exception  RuntimeError Raised when repository or node discovery fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    root = repository_root()
    issues = audit_issues(root, use_collect=use_collect, node_file=node_file)
    return print_report("Requirement Traceability Audit", issues)


def _parse_node_file_arg(argv: list[str]) -> Path | None:
    """
    @brief      Parse the optional precollected node-id file argument.
    @param[in]  argv Command-line argument list.
    @return     Node-id file path when provided, otherwise None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    if NODE_FILE_FLAG in argv:
        index = argv.index(NODE_FILE_FLAG)
        if index + 1 < len(argv):
            return Path(argv[index + 1])
    return None


def main() -> int:
    """
    @brief      Command-line entrypoint for the traceability audit.
    @return     Process status code.
    @exception  RuntimeError Raised when repository or node discovery fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    argv = sys.argv[1:]
    return run_audit(
        use_collect=COLLECT_FLAG in argv,
        node_file=_parse_node_file_arg(argv),
    )


if __name__ == "__main__":
    main_guard(main)


# END OF FILE
