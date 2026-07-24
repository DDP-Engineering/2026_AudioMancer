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
@brief Requirement snapshot, coverage, impact, and traceability helpers.
@details Builds all reverse mappings in memory from canonical UUID-backed TOML
         snapshots and never persists a generated registry or cache.
@author Eng. Dan Dumitru Pasare
@date 2026-07-22
@version 0.7.0
"""

# IMPORTS

from __future__ import annotations

from dataclasses import dataclass, replace
from fnmatch import fnmatchcase
from pathlib import Path
import re
from typing import Any

from .config import WorkflowConfig
from .paths import matches_pattern
from .requirement_store import (
    RequirementRecord,
    RequirementValidationError,
    create_requirement_record,
    find_requirement_record,
    load_all_requirement_records,
    manual_verification,
    normalize_linked_test,
    normalize_repository_path,
    utc_timestamp,
    validate_requirement_record,
    write_requirement_record,
)
from .working_tree import _git_status

# DATA MODELS / TYPEDEFINITIONS


@dataclass(frozen=True)
class AuditIssue:
    """
    @brief Represent one deterministic traceability or coverage finding.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.2.0
    """

    code: str
    message: str
    req_id: str | None = None
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        @brief Return a JSON-compatible finding.
        @return Finding fields in stable order.
        @author Eng. Dan Dumitru Pasare
        @date 2026-07-22
        @version 0.2.0
        """
        return {
            "code": self.code,
            "message": self.message,
            "req_id": self.req_id,
            "path": self.path,
        }


@dataclass(frozen=True)
class RequirementIndex:
    """
    @brief Hold non-persisted requirement reverse mappings.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.1.0
    """

    by_id: dict[str, RequirementRecord]
    by_test: dict[str, tuple[str, ...]]
    by_path: dict[str, tuple[str, ...]]


# PUBLIC API


def load_all_requirements(
    repo_root: Path, config: WorkflowConfig
) -> list[RequirementRecord]:
    """
    @brief Load every canonical requirement snapshot.
    @param[in] repo_root Repository root.
    @param[in] config Already validated workflow configuration.
    @return Records sorted by ID and source path.
    @exception RequirementValidationError If a snapshot is malformed.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.3.0
    """
    return load_all_requirement_records(repo_root, config)


def build_requirement_index(records: list[RequirementRecord]) -> RequirementIndex:
    """
    @brief Build deterministic in-memory ID, test, and affected-path mappings.
    @param[in] records Canonical validated requirement records.
    @return Non-persisted reverse index.
    @exception RequirementValidationError If a requirement ID is duplicated.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.1.0
    """
    by_id: dict[str, RequirementRecord] = {}
    test_sets: dict[str, set[str]] = {}
    path_sets: dict[str, set[str]] = {}
    for record in sorted(records, key=lambda item: (item.id, item.source_file or "")):
        if record.id in by_id:
            previous = by_id[record.id].source_file or "<unknown>"
            current = record.source_file or "<unknown>"
            raise RequirementValidationError(
                current,
                "id",
                f"duplicate requirement ID {record.id}; first defined at {previous}",
            )
        by_id[record.id] = record
        for selector in record.linked_tests:
            test_sets.setdefault(selector, set()).add(record.id)
        for pattern in record.affected_paths:
            path_sets.setdefault(pattern, set()).add(record.id)
    return RequirementIndex(
        by_id=dict(sorted(by_id.items())),
        by_test={key: tuple(sorted(value)) for key, value in sorted(test_sets.items())},
        by_path={key: tuple(sorted(value)) for key, value in sorted(path_sets.items())},
    )


def load_requirement_index(
    repo_root: Path, config: WorkflowConfig
) -> RequirementIndex:
    """
    @brief Load canonical records and build their process-local reverse index.
    @param[in] repo_root Repository root.
    @param[in] config Already validated workflow configuration.
    @return Deterministic in-memory index.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.2.0
    """
    return build_requirement_index(
        load_all_requirement_records(repo_root, config)
    )


def create_requirement(
    repo_root: Path,
    *,
    category: str,
    priority: str,
    requirement: str,
    rationale: str,
    verification: str,
    config: WorkflowConfig,
    affected_paths: list[str] | None = None,
    linked_tests: list[str] | None = None,
    timestamp: str | None = None,
) -> RequirementRecord:
    """
    @brief Create one independent Planned requirement snapshot.
    @return Newly persisted UUID-backed record.
    @exception ValueError If fields or linked tests are invalid.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.2.0
    """
    tests = linked_tests or []
    _require_resolvable_tests(repo_root, tests, config)
    return create_requirement_record(
        repo_root,
        config,
        category=category,
        priority=priority,
        requirement=requirement,
        rationale=rationale,
        verification=verification,
        affected_paths=affected_paths or [],
        linked_tests=tests,
        timestamp=timestamp,
    )


def show_requirement(
    repo_root: Path, requirement_id: str, config: WorkflowConfig
) -> RequirementRecord:
    """
    @brief Return one current requirement snapshot by canonical ID.
    @param[in] repo_root Repository root.
    @param[in] requirement_id Canonical UUID-backed requirement ID.
    @param[in] config Validated workflow configuration.
    @return Matching current record.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.2.0
    """
    return find_requirement_record(repo_root, requirement_id, config)


def list_requirements(
    repo_root: Path,
    *,
    config: WorkflowConfig,
    category: str | None = None,
    status: str | None = None,
) -> list[RequirementRecord]:
    """
    @brief List current snapshots with optional exact category and status filters.
    @return Matching records ordered by ID.
    @exception ValueError If a filter value is unsupported.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.2.0
    """
    records = load_all_requirement_records(repo_root, config)
    if category is not None:
        categories = {
            "functional",
            "ux",
            "non_functional",
            "security",
            "data_privacy",
            "platform",
            "release",
            "testing",
        }
        if category not in categories:
            raise ValueError(f"Unsupported requirement category: {category}")
        records = [record for record in records if record.category == category]
    if status is not None:
        if status not in {"Planned", "Active", "Retired"}:
            raise ValueError(f"Unsupported requirement status: {status}")
        records = [record for record in records if record.status == status]
    return records


def update_requirement(
    repo_root: Path,
    requirement_id: str,
    *,
    config: WorkflowConfig,
    status: str | None = None,
    priority: str | None = None,
    requirement: str | None = None,
    rationale: str | None = None,
    verification: str | None = None,
    linked_tests: list[str] | None = None,
    clear_linked_tests: bool = False,
    affected_paths: list[str] | None = None,
    clear_affected_paths: bool = False,
    timestamp: str | None = None,
) -> RequirementRecord:
    """
    @brief Atomically apply scalar patches and complete collection replacements.
    @return Resulting complete current record.
    @exception ValueError If options conflict, no update is supplied, or validation fails.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.2.0
    """
    if linked_tests is not None and clear_linked_tests:
        raise ValueError("linked_tests and clear_linked_tests are mutually exclusive")
    if affected_paths is not None and clear_affected_paths:
        raise ValueError("affected_paths and clear_affected_paths are mutually exclusive")
    supplied = any(
        value is not None
        for value in (status, priority, requirement, rationale, verification, linked_tests, affected_paths)
    ) or clear_linked_tests or clear_affected_paths
    if not supplied:
        raise ValueError("At least one requirement update option is required.")
    current = find_requirement_record(repo_root, requirement_id, config)
    new_tests = (
        tuple()
        if clear_linked_tests
        else tuple(linked_tests)
        if linked_tests is not None
        else current.linked_tests
    )
    new_paths = (
        tuple()
        if clear_affected_paths
        else tuple(affected_paths)
        if affected_paths is not None
        else current.affected_paths
    )
    candidate = replace(
        current,
        status=status if status is not None else current.status,
        priority=priority if priority is not None else current.priority,
        requirement=requirement if requirement is not None else current.requirement,
        rationale=rationale if rationale is not None else current.rationale,
        verification=verification if verification is not None else current.verification,
        linked_tests=new_tests,
        affected_paths=new_paths,
        last_updated=timestamp or utc_timestamp(),
    )
    normalized = validate_requirement_record(candidate, config)
    _require_resolvable_tests(repo_root, list(normalized.linked_tests), config)
    return write_requirement_record(repo_root, normalized, config)


def activate_requirement(
    repo_root: Path,
    req_id: str,
    linked_tests: list[str],
    verification: str,
    config: WorkflowConfig,
    *,
    timestamp: str | None = None,
) -> RequirementRecord:
    """
    @brief Activate a record while replacing its complete linked-test set.
    @return Persisted Active snapshot.
    @exception ValueError If verification or any selector is invalid.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.4.0
    """
    if not linked_tests and not manual_verification(verification.strip()):
        raise ValueError(
            "Requirement activation needs linked tests or explicit `Manual:`/`Inspection:` verification."
        )
    _require_resolvable_tests(repo_root, linked_tests, config)
    return update_requirement(
        repo_root,
        req_id,
        status="Active",
        verification=verification,
        linked_tests=linked_tests,
        config=config,
        timestamp=timestamp,
    )


def audit_traceability(
    repo_root: Path, config: WorkflowConfig
) -> list[AuditIssue]:
    """
    @brief Validate current linked tests and Active verification contracts.
    @return Deterministically ordered findings.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.3.0
    """
    index = load_requirement_index(repo_root, config)
    issues: list[AuditIssue] = []
    for record in index.by_id.values():
        unresolved: list[tuple[str, str]] = []
        for selector in record.linked_tests:
            resolved, reason = resolve_test(repo_root, selector, config)
            if not resolved:
                unresolved.append((selector, reason))
                issues.append(
                    AuditIssue(
                        "REQ-LINK-MISSING",
                        f"{record.id} linked test {selector} does not resolve: {reason}",
                        record.id,
                        record.source_file,
                    )
                )
        if record.status == "Active" and (
            (not record.linked_tests or unresolved) and not manual_verification(record.verification)
        ):
            issues.append(
                AuditIssue(
                    "REQ-NO-VERIFICATION",
                    f"{record.id} is Active without a resolvable linked-test set or explicit manual verification",
                    record.id,
                    record.source_file,
                )
            )
    return sorted(issues, key=lambda item: (item.req_id or "", item.code, item.path or ""))


def audit_coverage(
    repo_root: Path, config: WorkflowConfig
) -> list[AuditIssue]:
    """
    @brief Check configured coverable files against live current snapshots.
    @return Coverage and stale-waiver findings ordered by path.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.3.0
    """
    if config.coverage.mode == "disabled":
        return []
    records = load_all_requirement_records(repo_root, config)
    build_requirement_index(records)
    waivers = load_waivers(repo_root, config)
    coverable = iter_coverable_files(repo_root, config)
    issues: list[AuditIssue] = []
    for relative_path in coverable:
        covered = _is_covered(repo_root, records, relative_path, config)
        waived = relative_path in waivers
        if not covered and not waived:
            issues.append(
                AuditIssue(
                    "REQ-COVERAGE-MISSING",
                    f"{relative_path} has no Active test-linked requirement and is not waived",
                    path=relative_path,
                )
            )
        if covered and waived:
            issues.append(
                AuditIssue(
                    "REQ-COVERAGE-STALE-WAIVER",
                    f"{relative_path} is covered; remove stale waiver",
                    path=relative_path,
                )
            )
    for waived_path in waivers:
        if waived_path not in coverable:
            issues.append(
                AuditIssue(
                    "REQ-COVERAGE-STALE-WAIVER",
                    f"{waived_path} is waived but not coverable; remove stale waiver",
                    path=waived_path,
                )
            )
    return sorted(issues, key=lambda item: (item.path or "", item.code))


def impact(
    repo_root: Path,
    files: list[str] | None = None,
    *,
    config: WorkflowConfig,
) -> list[dict[str, Any]]:
    """
    @brief Map changed paths to live requirement snapshots and current tests.
    @return One deterministic impact object per normalized candidate path.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.3.0
    """
    records = load_all_requirement_records(repo_root, config)
    build_requirement_index(records)
    coverable = (
        set(iter_coverable_files(repo_root, config))
        if config.coverage.mode == "enforce"
        else set()
    )
    candidates = files if files is not None else _git_working_set(repo_root)
    report: list[dict[str, Any]] = []
    seen: set[str] = set()
    for file_path in candidates:
        relative_path = normalize_repository_path(file_path, allow_glob=False)
        if relative_path in seen:
            continue
        seen.add(relative_path)
        related = records_touching_file(records, relative_path)
        linked_tests = sorted({selector for record in related for selector in record.linked_tests})
        report.append(
            {
                "file": relative_path,
                "uncovered": relative_path in coverable
                and not _is_covered(repo_root, records, relative_path, config),
                "requirements": [record.to_dict() for record in related],
                "linked_tests": linked_tests,
                "full_regression_recommended": relative_path in coverable and not related,
            }
        )
    return report


def records_touching_file(
    records: list[RequirementRecord], relative_path: str
) -> list[RequirementRecord]:
    """
    @brief Match one path through the shared repository glob semantics.
    @return Matching records ordered by ID.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.1.0
    """
    normalized = normalize_repository_path(relative_path, allow_glob=False)
    return sorted(
        (
            record
            for record in records
            if any(matches_pattern(normalized, pattern) for pattern in record.affected_paths)
        ),
        key=lambda item: item.id,
    )


def resolve_test(
    repo_root: Path, test_id: str, config: WorkflowConfig
) -> tuple[bool, str]:
    """
    @brief Resolve an exact linked-test selector against current source.
    @return ``(True, "resolved")`` or an actionable failure reason.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.2.0
    """
    try:
        normalized = normalize_linked_test(test_id, config.test_roots)
    except ValueError as exc:
        return False, str(exc)
    test_path, identifier = normalized.split("::", 1)
    path = repo_root / test_path
    if not path.is_file():
        return False, f"{test_path} does not exist"
    source = path.read_text(encoding="utf-8", errors="ignore")
    language = config.traceability_language.lower()
    if language == "python":
        resolved = _resolve_python(source, identifier)
    elif language == "java":
        resolved = _resolve_java(source, identifier)
    elif language in {"c", "cpp"}:
        resolved = _resolve_cpp(source, identifier)
    else:
        resolved = identifier.split("::")[-1] in source
    return (True, "resolved") if resolved else (False, f"{identifier} not found in {test_path}")


def load_waivers(repo_root: Path, config: WorkflowConfig) -> list[str]:
    """
    @brief Load and normalize the current coverage-waiver snapshot.
    @return Sorted duplicate-free waived paths.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.2.0
    """
    values: set[str] = set()
    for root_name in config.requirement_roots:
        path = repo_root / root_name / "coverage_waivers.txt"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                values.add(normalize_repository_path(stripped, allow_glob=False))
    return sorted(values)


def iter_coverable_files(repo_root: Path, config: WorkflowConfig) -> list[str]:
    """
    @brief Enumerate configured source files subject to coverage policy.
    @return Sorted repository-relative file paths.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.2.0
    """
    if config.coverage.mode == "disabled":
        return []
    extensions = set(config.source_extensions)
    found: list[str] = []
    for root_name in config.coverable_roots:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in extensions:
                continue
            relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
            if any(
                fnmatchcase(path.name, pattern) or matches_pattern(relative, pattern)
                for pattern in config.coverable_exclude
            ):
                continue
            found.append(relative)
    return sorted(found)


# LOCAL HELPERS


def _require_resolvable_tests(
    repo_root: Path, selectors: list[str], config: WorkflowConfig
) -> None:
    """@brief Reject a write before persistence when any linked test is unresolved."""
    failures: list[str] = []
    for selector in selectors:
        resolved, reason = resolve_test(repo_root, selector, config)
        if not resolved:
            failures.append(f"{selector}: {reason}")
    if failures:
        raise ValueError(f"linked test(s) do not resolve: {'; '.join(failures)}")


def _is_covered(
    repo_root: Path,
    records: list[RequirementRecord],
    relative_path: str,
    config: WorkflowConfig,
) -> bool:
    """@brief Check for an Active matching record with a current resolvable test."""
    return any(
        record.status == "Active"
        and record.linked_tests
        and all(resolve_test(repo_root, selector, config)[0] for selector in record.linked_tests)
        for record in records_touching_file(records, relative_path)
    )


def _resolve_python(source: str, identifier: str) -> bool:
    """@brief Resolve the final Python test function segment."""
    name = identifier.split("::")[-1]
    return re.search(rf"^\s*def\s+{re.escape(name)}\s*\(", source, flags=re.MULTILINE) is not None


def _resolve_java(source: str, identifier: str) -> bool:
    """@brief Resolve a Java test method name."""
    return re.search(rf"\b{re.escape(identifier)}\s*\(", source) is not None


def _resolve_cpp(source: str, identifier: str) -> bool:
    """@brief Resolve a C or C++ test identifier."""
    return identifier.split(".")[-1] in source


def _git_working_set(repo_root: Path) -> list[str]:
    """
    @brief Return current and previous paths from the shared Git status parser.
    @details An unreadable status yields no paths here rather than a finding.
             This feeds impact analysis, which widens a result set as a
             convenience; the blocking judgement on an unreadable working tree
             belongs to `working_tree.audit_working_tree`, and duplicating it
             here would report the same problem twice.
    """
    files: list[str] = []
    entries, _status_error = _git_status(repo_root)
    for entry in entries:
        files.append(entry["path"])
        previous_path = entry.get("previous_path")
        if previous_path:
            files.append(previous_path)
    return files


# END OF FILE
