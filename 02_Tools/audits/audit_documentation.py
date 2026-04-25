#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audit_documentation.py
@brief Audit documentation freshness against AudioMancer implementation files.
@details Reports documentation files that should be reviewed after source
         changes, missing component documentation candidates, and absent broad
         operator documentation files.
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

from pathlib import Path
import sys

from audit_common import AuditIssue, changed_files, main_guard, parse_changed_only, print_report, repository_root

# CONSTANTS

BROAD_DOCUMENTATION_PATHS = (
    Path("README.MD"),
    Path("04_Software/README.md"),
    Path("04_Software/AudioMancer/README.MD"),
    Path("05_SoftwareDocu/README.md"),
    Path("0_Planning/Overview.md"),
)
IMPLEMENTATION_ROOT = Path("04_Software/AudioMancer/src/audiomancer")
SERVICE_ROOT = IMPLEMENTATION_ROOT / "services"
SOFTWARE_DOC_ROOT = Path("05_SoftwareDocu")


# PUBLIC API


def run_audit(changed_only: bool = False) -> int:
    """
    @brief      Run the implementation-to-documentation freshness audit.
    @param[in]  changed_only True to focus on changed Git implementation files.
    @return     Process status code.
    @exception  RuntimeError Raised when repository discovery fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    root = repository_root()
    implementation_paths = _implementation_paths(root, changed_only)
    issues: list[AuditIssue] = []
    issues.extend(_audit_broad_docs(root, implementation_paths))
    issues.extend(_audit_service_component_docs(root, implementation_paths))
    issues.extend(_audit_how_to_tests(root))
    scope = "changed implementation files" if changed_only else "implementation files"
    return print_report(f"AudioMancer documentation audit ({scope})", issues)


# LOCAL HELPERS


def _implementation_paths(root: Path, changed_only: bool) -> list[Path]:
    """
    @brief      Resolve implementation files that should drive documentation review.
    @param[in]  root Repository root path.
    @param[in]  changed_only True to use only changed Git files.
    @return     Repository-relative implementation paths.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if changed_only:
        candidates = changed_files(root, ".py")
    else:
        candidates = [path.relative_to(root) for path in (root / IMPLEMENTATION_ROOT).rglob("*.py")]
    return [
        path
        for path in candidates
        if path.parts[: len(IMPLEMENTATION_ROOT.parts)] == IMPLEMENTATION_ROOT.parts and "tests" not in path.parts
    ]


def _audit_broad_docs(root: Path, implementation_paths: list[Path]) -> list[AuditIssue]:
    """
    @brief      Check broad project documentation files for presence and freshness.
    @param[in]  root Repository root path.
    @param[in]  implementation_paths Implementation files in audit scope.
    @return     Documentation issue list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    issues: list[AuditIssue] = []
    newest_source_time = _newest_mtime(root, implementation_paths)
    for doc_path in BROAD_DOCUMENTATION_PATHS:
        absolute_doc_path = root / doc_path
        if not absolute_doc_path.is_file():
            issues.append(AuditIssue(doc_path, None, "DOC-MISSING", "Expected broad project documentation is absent."))
            continue
        if newest_source_time is not None and absolute_doc_path.stat().st_mtime < newest_source_time:
            issues.append(
                AuditIssue(
                    doc_path,
                    None,
                    "DOC-STALE-CHECK",
                    "Implementation files are newer; review this document for stale behavior descriptions.",
                )
            )
    return issues


def _audit_service_component_docs(root: Path, implementation_paths: list[Path]) -> list[AuditIssue]:
    """
    @brief      Check service implementation files for likely component documentation.
    @param[in]  root Repository root path.
    @param[in]  implementation_paths Implementation files in audit scope.
    @return     Documentation issue list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    issues: list[AuditIssue] = []
    for source_path in implementation_paths:
        if source_path.parts[: len(SERVICE_ROOT.parts)] != SERVICE_ROOT.parts:
            continue
        doc_candidates = _component_doc_candidates(source_path)
        existing_doc = next((candidate for candidate in doc_candidates if (root / candidate).is_file()), None)
        if existing_doc is None:
            issues.append(
                AuditIssue(
                    source_path,
                    None,
                    "DOC-COMPONENT-MISSING",
                    "No matching service component document found under 05_SoftwareDocu.",
                )
            )
            continue
        if (root / existing_doc).stat().st_mtime < (root / source_path).stat().st_mtime:
            issues.append(
                AuditIssue(
                    existing_doc,
                    None,
                    "DOC-COMPONENT-STALE-CHECK",
                    f"Review against newer implementation `{source_path}`.",
                )
            )
    return issues


def _audit_how_to_tests(root: Path) -> list[AuditIssue]:
    """
    @brief      Check whether repository-level HowToTest documentation exists.
    @param[in]  root Repository root path.
    @return     Documentation issue list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    how_to_docs = list(root.glob("**/HowToTest*.md")) + list(root.glob("**/HOW_TO_TEST*.md"))
    if how_to_docs:
        return []
    return [
        AuditIssue(
            Path("HowToTest*.md"),
            None,
            "DOC-HOW-TO-TEST-MISSING",
            "No HowToTest document exists; keep validation workflow in README files or add one.",
        )
    ]


def _component_doc_candidates(source_path: Path) -> list[Path]:
    """
    @brief      Build likely component-document paths for one service module.
    @param[in]  source_path Repository-relative service source path.
    @return     Candidate component documentation paths.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    stem = source_path.stem
    title = "".join(part.title() for part in stem.split("_"))
    snake_title = "_".join(part.title() for part in stem.split("_"))
    return [
        SOFTWARE_DOC_ROOT / f"AudioMancer_{snake_title}.md",
        SOFTWARE_DOC_ROOT / f"AudioMancer_{title}.md",
    ]


def _newest_mtime(root: Path, paths: list[Path]) -> float | None:
    """
    @brief      Return the newest modification time for existing paths.
    @param[in]  root Repository root path.
    @param[in]  paths Repository-relative paths.
    @return     Newest modification timestamp or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    mtimes = [(root / path).stat().st_mtime for path in paths if (root / path).is_file()]
    return max(mtimes) if mtimes else None


def main() -> int:
    """
    @brief      Command-line entrypoint for the documentation audit.
    @return     Process status code.
    @exception  RuntimeError Raised when repository discovery fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return run_audit(changed_only=parse_changed_only(sys.argv[1:]))


if __name__ == "__main__":
    main_guard(main)


# END OF FILE
