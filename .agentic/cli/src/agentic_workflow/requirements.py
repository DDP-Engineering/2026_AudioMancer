#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file requirements.py
@brief Requirement registry, coverage, and traceability helpers.
@details Provides reusable implementation behavior for the standalone workflow template.
@author Eng. Dan Dumitru Pasare
@date 2026-06-20
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .config import WorkflowConfig, load_config


REGISTER_HEADER = [
    "ID",
    "Status",
    "Priority",
    "Requirement",
    "Rationale",
    "Related Components",
    "Verification Method",
    "Linked Tests",
    "Created On",
    "Last Updated",
]

VALID_STATUS = {"Planned", "Active", "Retired"}
VALID_PRIORITY = {"Must", "Should", "Could"}
ID_PATTERN = re.compile(r"^REQ-[A-Z]+-\d{3,}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
MANUAL_MARKERS = ("manual", "inspection")


@dataclass
class RequirementRow:
    """
    @brief      Represent RequirementRow data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    req_id: str
    status: str
    priority: str
    requirement: str
    rationale: str
    related_components: list[str]
    verification: str
    linked_tests: list[str]
    created_on: str
    last_updated: str
    source_file: str
    line_number: int

    def file_components(self) -> list[str]:
        """
        @brief      Handle file components workflow behavior.
        @return     Result produced by the workflow helper.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-20
        @version    0.1.0
        """
        return [item for item in self.related_components if _looks_like_file(item)]

    def directory_components(self) -> list[str]:
        """
        @brief      Handle directory components workflow behavior.
        @return     Result produced by the workflow helper.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-20
        @version    0.1.0
        """
        return [item for item in self.related_components if not _looks_like_file(item)]

    def to_dict(self) -> dict[str, Any]:
        """
        @brief      Handle to dict workflow behavior.
        @return     Result produced by the workflow helper.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-20
        @version    0.1.0
        """
        return asdict(self)


@dataclass
class AuditIssue:
    """
    @brief      Represent AuditIssue data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    code: str
    message: str
    req_id: str | None = None
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        @brief      Handle to dict workflow behavior.
        @return     Result produced by the workflow helper.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-20
        @version    0.1.0
        """
        return asdict(self)


def load_all_requirements(repo_root: Path, config: WorkflowConfig | None = None) -> list[RequirementRow]:
    """
    @brief      Load all requirements workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  config Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    cfg = config or load_config(repo_root)
    rows: list[RequirementRow] = []
    for root_name in cfg.requirement_roots:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in sorted(root.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            rows.extend(parse_register_file(path, repo_root))
    return rows


def parse_register_file(path: Path, repo_root: Path | None = None) -> list[RequirementRow]:
    """
    @brief      Parse register file workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    header_index = _find_header(lines)
    if header_index is None:
        return []
    rows: list[RequirementRow] = []
    source = _relative(path, repo_root) if repo_root else path.as_posix()
    for index, line in enumerate(lines[header_index + 2 :], start=header_index + 3):
        if not line.strip().startswith("|"):
            continue
        cells = _split_markdown_row(line)
        if len(cells) != len(REGISTER_HEADER):
            continue
        rows.append(
            RequirementRow(
                req_id=cells[0],
                status=cells[1],
                priority=cells[2],
                requirement=cells[3],
                rationale=cells[4],
                related_components=_split_cell(cells[5]),
                verification=cells[6],
                linked_tests=_split_cell(cells[7]),
                created_on=cells[8],
                last_updated=cells[9],
                source_file=source,
                line_number=index,
            )
        )
    return rows


def validate_rows(rows: list[RequirementRow]) -> list[AuditIssue]:
    """
    @brief      Validate rows workflow behavior.
    @param[in]  rows Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    issues: list[AuditIssue] = []
    seen: set[str] = set()
    for row in rows:
        location = f"{row.source_file}:{row.line_number}"
        if row.req_id in seen:
            issues.append(AuditIssue("REQ-DUPLICATE-ID", f"{row.req_id} is duplicated at {location}", row.req_id))
        seen.add(row.req_id)
        if not ID_PATTERN.match(row.req_id):
            issues.append(AuditIssue("REQ-BAD-ID", f"{row.req_id} has invalid ID format at {location}", row.req_id))
        if row.status not in VALID_STATUS:
            issues.append(AuditIssue("REQ-BAD-STATUS", f"{row.req_id} has invalid status {row.status}", row.req_id))
        if row.priority not in VALID_PRIORITY:
            issues.append(AuditIssue("REQ-BAD-PRIORITY", f"{row.req_id} has invalid priority {row.priority}", row.req_id))
        if row.created_on and not DATE_PATTERN.match(row.created_on):
            issues.append(AuditIssue("REQ-BAD-CREATED-ON", f"{row.req_id} has invalid Created On timestamp", row.req_id))
        if row.last_updated and not DATE_PATTERN.match(row.last_updated):
            issues.append(AuditIssue("REQ-BAD-LAST-UPDATED", f"{row.req_id} has invalid Last Updated timestamp", row.req_id))
    return issues


def audit_traceability(repo_root: Path, config: WorkflowConfig | None = None) -> list[AuditIssue]:
    """
    @brief      Audit traceability workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  config Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    cfg = config or load_config(repo_root)
    rows = load_all_requirements(repo_root, cfg)
    issues = validate_rows(rows)
    for row in rows:
        unresolved = []
        for test_id in row.linked_tests:
            resolves, reason = resolve_test(repo_root, test_id, cfg)
            if not resolves:
                unresolved.append((test_id, reason))
                issues.append(AuditIssue("REQ-LINK-MISSING", f"{row.req_id} linked test {test_id} does not resolve: {reason}", row.req_id))
        if row.status == "Active":
            has_automated = bool(row.linked_tests) and not unresolved
            has_manual = any(marker in row.verification.lower() for marker in MANUAL_MARKERS)
            if not has_automated and not has_manual:
                issues.append(AuditIssue("REQ-NO-VERIFICATION", f"{row.req_id} is Active without a resolvable linked test or manual verification", row.req_id))
    return issues


def audit_coverage(repo_root: Path, config: WorkflowConfig | None = None) -> list[AuditIssue]:
    """
    @brief      Audit coverage workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  config Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    cfg = config or load_config(repo_root)
    rows = load_all_requirements(repo_root, cfg)
    waivers = load_waivers(repo_root, cfg)
    coverable = iter_coverable_files(repo_root, cfg)
    issues: list[AuditIssue] = []
    for relative_path in coverable:
        covered = _is_covered(repo_root, rows, relative_path, cfg)
        waived = relative_path in waivers
        if not covered and not waived:
            issues.append(AuditIssue("REQ-COVERAGE-MISSING", f"{relative_path} has no file-level test-linked requirement and is not waived", path=relative_path))
        if covered and waived:
            issues.append(AuditIssue("REQ-COVERAGE-STALE-WAIVER", f"{relative_path} is covered; remove stale waiver", path=relative_path))
    for waived_path in waivers:
        if waived_path not in coverable:
            issues.append(AuditIssue("REQ-COVERAGE-STALE-WAIVER", f"{waived_path} is waived but not coverable; remove stale waiver", path=waived_path))
    return issues


def activate_requirement(
    repo_root: Path,
    req_id: str,
    linked_tests: list[str],
    verification: str,
    config: WorkflowConfig | None = None,
) -> RequirementRow:
    """
    @brief      Activate requirement workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  req_id Input value used by the workflow helper.
    @param[in]  linked_tests Input value used by the workflow helper.
    @param[in]  verification Input value used by the workflow helper.
    @param[in]  config Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    cfg = config or load_config(repo_root)
    if not linked_tests and not any(marker in verification.lower() for marker in MANUAL_MARKERS):
        raise ValueError("Requirement activation needs at least one linked test or manual verification text.")
    for root_name in cfg.requirement_roots:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in sorted(root.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            updated = _activate_requirement_in_file(path, repo_root, req_id, linked_tests, verification)
            if updated:
                return updated
    raise ValueError(f"Requirement not found: {req_id}")


def impact(repo_root: Path, files: list[str] | None = None, config: WorkflowConfig | None = None) -> list[dict[str, Any]]:
    """
    @brief      Build impact workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  files Input value used by the workflow helper.
    @param[in]  config Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    cfg = config or load_config(repo_root)
    rows = load_all_requirements(repo_root, cfg)
    coverable = set(iter_coverable_files(repo_root, cfg))
    candidates = files or _git_working_set(repo_root)
    report = []
    for file_path in candidates:
        relative_path = _normalize_relative(file_path)
        related = rows_touching_file(rows, relative_path)
        linked_tests = sorted({test for row in related for test in row.linked_tests})
        report.append(
            {
                "file": relative_path,
                "uncovered": relative_path in coverable and not rows_covering_file(rows, relative_path),
                "requirements": [row.to_dict() for row in related],
                "linked_tests": linked_tests,
                "full_regression_recommended": relative_path in coverable and not related,
            }
        )
    return report


def sync_registry(repo_root: Path) -> dict[str, int]:
    """
    @brief      Synchronize sync registry workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    rows = load_all_requirements(repo_root)
    registry = repo_root / ".agentic" / "registry"
    registry.mkdir(parents=True, exist_ok=True)
    specs = {row.req_id: row.to_dict() for row in rows}
    checks = {}
    for row in rows:
        for test_id in row.linked_tests:
            checks[test_id] = {
                "id": test_id,
                "requirement_ids": sorted({*(checks.get(test_id, {}).get("requirement_ids", [])), row.req_id}),
            }
    features = _load_active_feature(repo_root)
    registry.joinpath("requirements.json").write_text(json.dumps(specs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    registry.joinpath("checks.json").write_text(json.dumps(checks, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    registry.joinpath("features.json").write_text(json.dumps(features, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"requirement_count": len(specs), "check_count": len(checks), "feature_count": len(features)}


def audit_registry(repo_root: Path) -> list[AuditIssue]:
    """
    @brief      Audit registry workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    registry = repo_root / ".agentic" / "registry"
    requirements_path = registry / "requirements.json"
    checks_path = registry / "checks.json"
    features_path = registry / "features.json"
    issues: list[AuditIssue] = []
    if not requirements_path.exists():
        issues.append(AuditIssue("REGISTRY-MISSING", "requirements registry cache is missing; run registry sync"))
    if not checks_path.exists():
        issues.append(AuditIssue("REGISTRY-MISSING", "checks registry cache is missing; run registry sync"))
    if not features_path.exists():
        issues.append(AuditIssue("REGISTRY-MISSING", "features registry cache is missing; run registry sync"))
    if issues:
        return issues
    try:
        json.loads(requirements_path.read_text(encoding="utf-8"))
        json.loads(checks_path.read_text(encoding="utf-8"))
        json.loads(features_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(AuditIssue("REGISTRY-BAD-JSON", str(exc)))
    return issues


def _load_active_feature(repo_root: Path) -> dict[str, Any]:
    """
    @brief      Load active feature workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    current = repo_root / ".agentic" / "current_run"
    if not current.exists():
        return {}
    run_id = current.read_text(encoding="utf-8").strip()
    graph_path = repo_root / ".agentic" / "runs" / run_id / "graph.json"
    if not graph_path.exists():
        return {}
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    return {
        run_id: {
            "run_id": run_id,
            "stage": data.get("stage"),
            "intent": data.get("intent", {}),
            "spec_ids": [item.get("id") for item in data.get("spec_items", [])],
            "check_ids": [item.get("id") for item in data.get("checks", [])],
            "touched_paths": sorted({path for unit in data.get("change_units", []) for path in unit.get("touched_paths", [])}),
            "report_path": f".agentic/runs/{run_id}/report.md",
        }
    }


def load_waivers(repo_root: Path, config: WorkflowConfig) -> list[str]:
    """
    @brief      Load waivers workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  config Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    for root_name in config.requirement_roots:
        path = repo_root / root_name / "coverage_waivers.txt"
        if path.exists():
            return [
                line.strip().replace("\\", "/")
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
    return []


def iter_coverable_files(repo_root: Path, config: WorkflowConfig) -> list[str]:
    """
    @brief      Iterate iter coverable files workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  config Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    extensions = set(config.source_extensions)
    found: list[str] = []
    for root_name in config.coverable_roots:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in extensions:
                continue
            rel = _relative(path, repo_root)
            if any(fnmatch(path.name, pattern) or fnmatch(rel, pattern.replace("\\", "/")) for pattern in config.coverable_exclude):
                continue
            found.append(rel)
    return sorted(found)


def rows_covering_file(rows: list[RequirementRow], relative_path: str) -> list[RequirementRow]:
    """
    @brief      Collect rows covering file workflow behavior.
    @param[in]  rows Input value used by the workflow helper.
    @param[in]  relative_path Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    normalized = _normalize_relative(relative_path)
    return [row for row in rows if normalized in row.file_components()]


def rows_touching_file(rows: list[RequirementRow], relative_path: str) -> list[RequirementRow]:
    """
    @brief      Collect rows touching file workflow behavior.
    @param[in]  rows Input value used by the workflow helper.
    @param[in]  relative_path Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    normalized = _normalize_relative(relative_path)
    matches = rows_covering_file(rows, normalized)
    matches.extend(
        row
        for row in rows
        if row not in matches and any(normalized.startswith(directory.rstrip("/") + "/") for directory in row.directory_components())
    )
    return matches


def resolve_test(repo_root: Path, test_id: str, config: WorkflowConfig) -> tuple[bool, str]:
    """
    @brief      Resolve test workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  test_id Input value used by the workflow helper.
    @param[in]  config Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    try:
        test_path, ident = _split_test_id(test_id)
    except ValueError as exc:
        return False, str(exc)
    path = repo_root / test_path
    if not path.exists():
        return False, f"{test_path} does not exist"
    source = path.read_text(encoding="utf-8", errors="ignore")
    language = config.traceability_language.lower()
    if language == "python":
        resolved = _resolve_python(source, ident)
    elif language == "java":
        resolved = _resolve_java(source, ident)
    elif language in {"c", "cpp"}:
        resolved = _resolve_cpp(source, ident)
    else:
        resolved = ident.split("::")[-1].split("#")[-1] in source
    return (True, "resolved") if resolved else (False, f"{ident} not found in {test_path}")


def _activate_requirement_in_file(
    path: Path,
    repo_root: Path,
    req_id: str,
    linked_tests: list[str],
    verification: str,
) -> RequirementRow | None:
    """
    @brief      Activate requirement in file workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  req_id Input value used by the workflow helper.
    @param[in]  linked_tests Input value used by the workflow helper.
    @param[in]  verification Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    header_index = _find_header(lines)
    if header_index is None:
        return None
    for index, line in enumerate(lines[header_index + 2 :], start=header_index + 2):
        if not line.strip().startswith("|"):
            continue
        cells = _split_markdown_row(line)
        if len(cells) != len(REGISTER_HEADER) or cells[0] != req_id:
            continue
        existing_tests = _split_cell(cells[7])
        merged_tests = _merge_unique(existing_tests, [_normalize_relative(item) for item in linked_tests])
        cells[1] = "Active"
        cells[6] = verification
        cells[7] = _format_list_cell(merged_tests)
        cells[9] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        lines[index] = "| " + " | ".join(cells) + " |"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        # Re-parse and locate the updated row by ID instead of by line offset so
        # activation stays correct even when the register has blank or malformed
        # lines between the header and this row.
        for updated_row in parse_register_file(path, repo_root):
            if updated_row.req_id == req_id:
                return updated_row
        return None
    return None


def _is_covered(repo_root: Path, rows: list[RequirementRow], relative_path: str, config: WorkflowConfig) -> bool:
    """
    @brief      Check is covered workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  rows Input value used by the workflow helper.
    @param[in]  relative_path Input value used by the workflow helper.
    @param[in]  config Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    for row in rows_covering_file(rows, relative_path):
        if row.status not in {"Active", "Planned"}:
            continue
        if any(resolve_test(repo_root, test_id, config)[0] for test_id in row.linked_tests):
            return True
    return False


def _find_header(lines: list[str]) -> int | None:
    """
    @brief      Handle find header workflow behavior.
    @param[in]  lines Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    expected = "| " + " | ".join(REGISTER_HEADER) + " |"
    for index, line in enumerate(lines):
        if line.strip() == expected:
            return index
    return None


def _split_markdown_row(line: str) -> list[str]:
    """
    @brief      Handle split markdown row workflow behavior.
    @param[in]  line Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _split_cell(cell: str) -> list[str]:
    """
    @brief      Handle split cell workflow behavior.
    @param[in]  cell Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    values = re.findall(r"`([^`]+)`", cell)
    if values:
        return [_normalize_relative(value) for value in values]
    if not cell.strip() or cell.strip() in {"-", "None", "N/A"}:
        return []
    return [_normalize_relative(part.strip()) for part in cell.split(";") if part.strip()]


def _format_list_cell(values: list[str]) -> str:
    """
    @brief      Handle format list cell workflow behavior.
    @param[in]  values Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return "; ".join(f"`{value}`" for value in values) if values else "-"


def _merge_unique(existing: list[str], new_items: list[str]) -> list[str]:
    """
    @brief      Handle merge unique workflow behavior.
    @param[in]  existing Input value used by the workflow helper.
    @param[in]  new_items Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    merged: list[str] = []
    for item in [*existing, *new_items]:
        if item and item not in {"-", "None", "N/A"} and item not in merged:
            merged.append(item)
    return merged


def _split_test_id(test_id: str) -> tuple[str, str]:
    """
    @brief      Handle split test id workflow behavior.
    @param[in]  test_id Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    if "#" in test_id:
        path, ident = test_id.split("#", 1)
        return _normalize_relative(path), ident
    if "::" in test_id:
        path, ident = test_id.split("::", 1)
        return _normalize_relative(path), ident
    raise ValueError(f"Linked test id must contain '::' or '#': {test_id}")


def _resolve_python(source: str, ident: str) -> bool:
    """
    @brief      Resolve python workflow behavior.
    @param[in]  source Input value used by the workflow helper.
    @param[in]  ident Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    name = ident.split("::")[-1]
    return re.search(rf"^\s*def\s+{re.escape(name)}\s*\(", source, flags=re.MULTILINE) is not None


def _resolve_java(source: str, ident: str) -> bool:
    """
    @brief      Resolve java workflow behavior.
    @param[in]  source Input value used by the workflow helper.
    @param[in]  ident Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return re.search(rf"\b{re.escape(ident)}\s*\(", source) is not None


def _resolve_cpp(source: str, ident: str) -> bool:
    """
    @brief      Resolve cpp workflow behavior.
    @param[in]  source Input value used by the workflow helper.
    @param[in]  ident Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    test_name = ident.split(".")[-1]
    return test_name in source


def _looks_like_file(path: str) -> bool:
    """
    @brief      Handle looks like file workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return bool(Path(path).suffix)


def _relative(path: Path, repo_root: Path) -> str:
    """
    @brief      Handle relative workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _normalize_relative(path: str) -> str:
    """
    @brief      Normalize relative workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return path.replace("\\", "/").strip().strip("`")


def _git_working_set(repo_root: Path) -> list[str]:
    """
    @brief      Handle git working set workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    files = []
    for line in result.stdout.splitlines():
        if len(line) > 3:
            files.append(_normalize_relative(line[3:]))
    return files
