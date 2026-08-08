#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audit_codestyle.py
@brief Audit Python code style and Doxygen headers for AudioMancer.
@details Checks repository Python files against the binding code style in
         01_Documentation/Code_Style.md: prologues, module tags, section
         markers, and callable Doxygen tags.
"""

# IMPORTS

from __future__ import annotations

import ast
from pathlib import Path
import sys

from audit_common import (
    AuditIssue,
    main_guard,
    parse_changed_only,
    print_report,
    python_files,
    repository_root,
)

# CONSTANTS

# Code_Style.md requires @file, @brief and @details in the module docstring, and
# states that no docstring carries @author, @date or @version: the file-top
# copyright banner is the sole in-file attribution and versioning is
# project-level only.
REQUIRED_MODULE_TAGS = ("@file", "@brief", "@details")
REQUIRED_CALLABLE_TAGS = ("@brief",)
FORBIDDEN_DOC_TAGS = ("@author", "@date", "@version")
REQUIRED_SECTION_MARKERS = ("# IMPORTS", "# END OF FILE")
EXPECTED_SHEBANG = "#!/usr/bin/env python3"
EXPECTED_ENCODING_PREFIX = "# -*- coding: utf-8 -*-"
EXCLUDED_PATH_PARTS = {"__pycache__", ".venv", "build", "dist"}


# PUBLIC API


def audit_file(path: Path, root: Path) -> list[AuditIssue]:
    """
    @brief      Audit one Python file for repository code-style requirements.
    @param[in]  path Repository-relative Python file path.
    @param[in]  root Repository root path.
    @return     Code-style issue list for the file.
    @exception  None
    """
    if any(part in EXCLUDED_PATH_PARTS for part in path.parts):
        return []
    absolute_path = root / path
    text = absolute_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    issues: list[AuditIssue] = []
    if not lines or lines[0] != EXPECTED_SHEBANG:
        issues.append(
            AuditIssue(path, 1, "PY-PROLOGUE", "Missing required Python shebang.")
        )
    if len(lines) < 2 or not lines[1].startswith(EXPECTED_ENCODING_PREFIX):
        issues.append(
            AuditIssue(
                path, 2, "PY-PROLOGUE", "Missing required UTF-8 encoding declaration."
            )
        )
    for marker in REQUIRED_SECTION_MARKERS:
        if marker not in text:
            issues.append(
                AuditIssue(
                    path, None, "PY-SECTION", f"Missing section marker `{marker}`."
                )
            )
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [*issues, AuditIssue(path, exc.lineno, "PY-SYNTAX", str(exc))]
    module_doc = ast.get_docstring(tree, clean=False) or ""
    for tag in REQUIRED_MODULE_TAGS:
        if tag not in module_doc:
            issues.append(
                AuditIssue(
                    path, None, "PY-MODULE-DOC", f"Missing module doc tag `{tag}`."
                )
            )
    for tag in FORBIDDEN_DOC_TAGS:
        if tag in module_doc:
            issues.append(
                AuditIssue(
                    path,
                    None,
                    "PY-MODULE-DOC",
                    f"Module doc tag `{tag}` is not allowed; attribution belongs in "
                    "the file-top copyright banner and versioning is project-level.",
                )
            )
    issues.extend(_audit_callable_docs(path, tree))
    return issues


def run_audit(changed_only: bool = False) -> int:
    """
    @brief      Run the code-style audit.
    @param[in]  changed_only True to audit only changed Git Python files.
    @return     Process status code.
    @exception  RuntimeError Raised when repository discovery fails.
    """
    root = repository_root()
    issues: list[AuditIssue] = []
    for path in python_files(root, changed_only=changed_only):
        issues.extend(audit_file(path, root))
    scope = "changed Python files" if changed_only else "repository Python files"
    return print_report(f"AudioMancer code-style audit ({scope})", issues)


# LOCAL HELPERS


def _audit_callable_docs(path: Path, tree: ast.AST) -> list[AuditIssue]:
    """
    @brief      Audit class/function docstrings in one parsed Python module.
    @param[in]  path Repository-relative Python file path.
    @param[in]  tree Parsed Python syntax tree.
    @return     Callable documentation issue list.
    @exception  None
    """
    issues: list[AuditIssue] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name.startswith("__") and node.name.endswith("__"):
            continue
        if _is_trivial_private_helper(node):
            continue
        doc = ast.get_docstring(node, clean=False)
        if doc is None:
            issues.append(
                AuditIssue(
                    path,
                    node.lineno,
                    "PY-CALLABLE-DOC",
                    f"`{node.name}` is missing a docstring.",
                )
            )
            continue
        for tag in REQUIRED_CALLABLE_TAGS:
            if tag not in doc:
                issues.append(
                    AuditIssue(
                        path,
                        node.lineno,
                        "PY-CALLABLE-DOC",
                        f"`{node.name}` is missing `{tag}`.",
                    )
                )
        for tag in FORBIDDEN_DOC_TAGS:
            if tag in doc:
                issues.append(
                    AuditIssue(
                        path,
                        node.lineno,
                        "PY-CALLABLE-DOC",
                        f"`{node.name}` carries `{tag}`, which docstrings must not use.",
                    )
                )
    return issues


def _is_trivial_private_helper(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """
    @brief      Determine whether a private helper is simple enough to omit docs.
    @param[in]  node Parsed callable or class node.
    @return     True when the node is a trivial private helper.
    @exception  None
    """
    if isinstance(node, ast.ClassDef) or not node.name.startswith("_"):
        return False
    executable_nodes = [child for child in node.body if not isinstance(child, ast.Expr)]
    if len(executable_nodes) != 1:
        return False
    return isinstance(executable_nodes[0], ast.Return)


def main() -> int:
    """
    @brief      Command-line entrypoint for the code-style audit.
    @return     Process status code.
    @exception  RuntimeError Raised when repository discovery fails.
    """
    return run_audit(changed_only=parse_changed_only(sys.argv[1:]))


if __name__ == "__main__":
    main_guard(main)


# END OF FILE
