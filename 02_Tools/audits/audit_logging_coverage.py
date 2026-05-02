#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audit_logging_coverage.py
@brief Audit logging coverage candidates for principal AudioMancer functions.
@details Scans non-UI implementation modules for service-level functions that
         perform workflow, file, project-state, model, or external operations
         and reports candidates that do not appear to use the logging service.
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.1.0
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

IMPLEMENTATION_ROOT = Path("04_Software/AudioMancer/src/audiomancer")
SERVICE_ROOT = IMPLEMENTATION_ROOT / "services"
EXCLUDED_MODULES = {"logging_service.py", "__init__.py"}
IO_METHOD_NAMES = {
    "copy",
    "dump",
    "dumps",
    "load",
    "loads",
    "mkdir",
    "open",
    "read_bytes",
    "read_text",
    "rename",
    "replace",
    "resolve",
    "rmdir",
    "run",
    "save_project",
    "save_project_manifest",
    "unlink",
    "write_bytes",
    "write_text",
}
WORKFLOW_NAME_PARTS = (
    "approve",
    "continue",
    "create",
    "generate",
    "import",
    "load",
    "persist",
    "process",
    "render",
    "reset",
    "run",
    "save",
    "start",
    "translate",
    "update",
    "write",
)
PRIVATE_PRINCIPAL_PREFIXES = (
    "_call",
    "_generate",
    "_persist",
    "_request",
    "_run",
    "_save",
    "_start",
    "_stitch",
    "_write",
)
PUBLIC_PRINCIPAL_EXACT_NAMES = {"render_export"}
LOG_METHOD_NAMES = {"debug", "info", "warning", "error", "exception", "critical", "log"}


# PUBLIC API


def audit_file(path: Path, root: Path) -> list[AuditIssue]:
    """
    @brief      Audit one implementation module for likely missing logging coverage.
    @param[in]  path Repository-relative Python source path.
    @param[in]  root Repository root path.
    @return     Logging coverage issue list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if not _is_service_source(path):
        return []
    text = (root / path).read_text(encoding="utf-8")
    tree = ast.parse(text)
    module_has_logging = "logging_service" in text or "get_component_logger" in text
    issues: list[AuditIssue] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        issues.extend(_audit_node(path, node, module_has_logging))
    return issues


def run_audit(changed_only: bool = False) -> int:
    """
    @brief      Run the logging coverage audit.
    @param[in]  changed_only True to audit only changed Git Python files.
    @return     Process status code.
    @exception  RuntimeError Raised when repository discovery fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    root = repository_root()
    issues: list[AuditIssue] = []
    for path in python_files(root, changed_only=changed_only):
        issues.extend(audit_file(path, root))
    scope = "changed service files" if changed_only else "service files"
    return print_report(f"AudioMancer logging coverage audit ({scope})", issues)


# LOCAL HELPERS


def _audit_node(
    path: Path,
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    module_has_logging: bool,
) -> list[AuditIssue]:
    """
    @brief      Audit one top-level function or class for logging candidates.
    @param[in]  path Repository-relative source path.
    @param[in]  node Parsed top-level node.
    @param[in]  module_has_logging True when the module imports or names the logging service.
    @return     Logging coverage issue list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if isinstance(node, ast.ClassDef):
        issues: list[AuditIssue] = []
        for method in node.body:
            if isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef):
                issues.extend(
                    _audit_function(path, method, module_has_logging, owner=node.name)
                )
        return issues
    return _audit_function(path, node, module_has_logging, owner=None)


def _audit_function(
    path: Path,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    module_has_logging: bool,
    owner: str | None,
) -> list[AuditIssue]:
    """
    @brief      Audit one function or method for likely missing logging.
    @param[in]  path Repository-relative source path.
    @param[in]  node Parsed function node.
    @param[in]  module_has_logging True when the module imports or names the logging service.
    @param[in]  owner Optional owning class name.
    @return     Logging coverage issue list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if _skip_function(node):
        return []
    reason = _principal_reason(node)
    if reason is None:
        return []
    if module_has_logging and _function_uses_logging(node):
        return []
    qualified_name = f"{owner}.{node.name}" if owner else node.name
    message = f"`{qualified_name}` looks principal ({reason}) but does not appear to log through logging_service."
    if not module_has_logging:
        message += " Module also has no visible logging_service import/use."
    return [AuditIssue(path, node.lineno, "LOG-COVERAGE-CANDIDATE", message)]


def _is_service_source(path: Path) -> bool:
    """
    @brief      Determine whether a path is an auditable non-UI service module.
    @param[in]  path Repository-relative Python path.
    @return     True when the path is a service source module.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return (
        path.parts[: len(SERVICE_ROOT.parts)] == SERVICE_ROOT.parts
        and path.name not in EXCLUDED_MODULES
    )


def _skip_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """
    @brief      Determine whether a function is out of logging-audit scope.
    @param[in]  node Parsed function node.
    @return     True when the function should be skipped.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if node.name.startswith("__") and node.name.endswith("__"):
        return True
    if node.name.startswith("_") and len(node.body) <= 4:
        return True
    return (
        node.name.startswith(("get_", "is_", "has_", "normalize_", "format_"))
        and len(node.body) <= 6
    )


def _principal_reason(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """
    @brief      Resolve why a function looks principal enough to need logging.
    @param[in]  node Parsed function node.
    @return     Reason text or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    lowered_name = node.name.lower()
    if node.name.startswith("_") and not node.name.startswith(
        PRIVATE_PRINCIPAL_PREFIXES
    ):
        return None
    if (
        _executable_statement_count(node) <= 8
        and node.name not in PUBLIC_PRINCIPAL_EXACT_NAMES
    ):
        return None
    if node.name in PUBLIC_PRINCIPAL_EXACT_NAMES:
        return "public workflow/state operation"
    if not node.name.startswith("_") and any(
        part in lowered_name for part in WORKFLOW_NAME_PARTS
    ):
        return "public workflow/state operation"
    if _has_exception_handler(node):
        return "exception handling"
    if _has_io_or_external_call(node):
        return "file/project/external operation"
    return None


def _executable_statement_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """
    @brief      Count executable statements in one function body.
    @param[in]  node Parsed function node.
    @return     Executable statement count, excluding docstring expressions.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return sum(1 for child in node.body if not isinstance(child, ast.Expr))


def _function_uses_logging(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """
    @brief      Detect direct logger calls or logging decorators inside one function.
    @param[in]  node Parsed function node.
    @return     True when logging appears to be used.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    for decorator in node.decorator_list:
        if "trace_function" in ast.unparse(decorator):
            return True
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in LOG_METHOD_NAMES
        ):
            return True
    return False


def _has_io_or_external_call(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """
    @brief      Detect file, process, project-state, or likely external calls.
    @param[in]  node Parsed function node.
    @return     True when the function performs an operation worth logging.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name) and func.id in IO_METHOD_NAMES:
                return True
            if isinstance(func, ast.Attribute) and func.attr in IO_METHOD_NAMES:
                return True
    return False


def _has_exception_handler(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """
    @brief      Detect whether a function handles exceptions.
    @param[in]  node Parsed function node.
    @return     True when an exception handler exists.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return any(
        isinstance(child, ast.Try) and child.handlers for child in ast.walk(node)
    )


def main() -> int:
    """
    @brief      Command-line entrypoint for the logging coverage audit.
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
