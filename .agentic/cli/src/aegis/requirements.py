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
@details Same-requirement updates serialize their complete read/validate/write
         transaction and publish with a source-digest precondition.
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
from .persistence import locked
from .requirement_store import (
    CATEGORY_IDENTITIES,
    VALID_STATUS,
    RequirementRecord,
    RequirementValidationError,
    create_requirement_record,
    find_requirement_record,
    load_all_requirement_records,
    manual_verification,
    normalize_linked_test,
    normalize_repository_path,
    requirement_lock_path,
    requirement_source_digest,
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
    """

    code: str
    message: str
    req_id: str | None = None
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        @brief Return a JSON-compatible finding.
        @return Finding fields in stable order.
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
    """

    by_id: dict[str, RequirementRecord]
    by_test: dict[str, tuple[str, ...]]
    by_path: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class RequirementPatch:
    """
    @brief      Scalar field patches and complete collection replacements for
                one `update_requirement` call.
    @details    `None` means "leave the current value unchanged" for every
                field. `linked_tests`/`affected_paths`/`spec_ref` each pair
                with an explicit `clear_*` flag so "replace with an empty
                collection" is distinguishable from "leave unchanged";
                supplying both a value and its `clear_*` flag is rejected.
    """

    status: str | None = None
    priority: str | None = None
    requirement: str | None = None
    rationale: str | None = None
    verification: str | None = None
    spec_ref: str | None = None
    clear_spec_ref: bool = False
    linked_tests: list[str] | None = None
    clear_linked_tests: bool = False
    affected_paths: list[str] | None = None
    clear_affected_paths: bool = False
    timestamp: str | None = None

    def __post_init__(self) -> None:
        """
        @brief      Reject a value supplied alongside its `clear_*` flag.
        @exception  ValueError If any value/`clear_*` pair conflicts.
        """
        if self.linked_tests is not None and self.clear_linked_tests:
            raise ValueError("linked_tests and clear_linked_tests are mutually exclusive")
        if self.affected_paths is not None and self.clear_affected_paths:
            raise ValueError("affected_paths and clear_affected_paths are mutually exclusive")
        if self.spec_ref is not None and self.clear_spec_ref:
            raise ValueError("spec_ref and clear_spec_ref are mutually exclusive")


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
    """
    return load_all_requirement_records(repo_root, config)


def build_requirement_index(records: list[RequirementRecord]) -> RequirementIndex:
    """
    @brief Build deterministic in-memory ID, test, and affected-path mappings.
    @param[in] records Canonical validated requirement records.
    @return Non-persisted reverse index.
    @exception RequirementValidationError If a requirement ID is duplicated.
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
    @exception RequirementValidationError If a snapshot is malformed or a
               requirement ID is duplicated.
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
    spec_ref: str = "",
    affected_paths: list[str] | None = None,
    linked_tests: list[str] | None = None,
    timestamp: str | None = None,
) -> RequirementRecord:
    """
    @brief Create one independent Planned requirement snapshot.
    @return Newly persisted UUID-backed record.
    @exception ValueError If fields, linked tests, or the spec reference are invalid.
    """
    tests = linked_tests or []
    _require_resolvable_tests(repo_root, tests, config)
    _require_existing_spec(repo_root, spec_ref)
    return create_requirement_record(
        repo_root,
        config,
        category=category,
        priority=priority,
        requirement=requirement,
        rationale=rationale,
        verification=verification,
        spec_ref=spec_ref,
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
    @exception RequirementValidationError If the ID is invalid, absent, or duplicated.
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
    """
    records = load_all_requirement_records(repo_root, config)
    if category is not None:
        if category not in CATEGORY_IDENTITIES:
            raise ValueError(f"Unsupported requirement category: {category}")
        records = [record for record in records if record.category == category]
    if status is not None:
        if status not in VALID_STATUS:
            raise ValueError(f"Unsupported requirement status: {status}")
        records = [record for record in records if record.status == status]
    return records


def update_requirement(
    repo_root: Path,
    requirement_id: str,
    *,
    config: WorkflowConfig,
    patch: RequirementPatch,
) -> RequirementRecord:
    """
    @brief Atomically apply scalar patches and complete collection replacements.
    @param[in] repo_root Repository root.
    @param[in] requirement_id Canonical UUID-backed requirement ID.
    @param[in] config Validated workflow configuration.
    @param[in] patch Scalar/collection changes to apply.
    @return Resulting complete current record.
    @exception ValueError If no update is supplied or validation fails.
    """
    supplied = any(
        value is not None
        for value in (
            patch.status,
            patch.priority,
            patch.requirement,
            patch.rationale,
            patch.verification,
            patch.spec_ref,
            patch.linked_tests,
            patch.affected_paths,
        )
    ) or patch.clear_linked_tests or patch.clear_affected_paths or patch.clear_spec_ref
    if not supplied:
        raise ValueError("At least one requirement update option is required.")
    with locked(requirement_lock_path(repo_root, requirement_id)):
        current = find_requirement_record(repo_root, requirement_id, config)
        source_digest = requirement_source_digest(repo_root, current)
        new_tests = (
            tuple()
            if patch.clear_linked_tests
            else tuple(patch.linked_tests)
            if patch.linked_tests is not None
            else current.linked_tests
        )
        new_paths = (
            tuple()
            if patch.clear_affected_paths
            else tuple(patch.affected_paths)
            if patch.affected_paths is not None
            else current.affected_paths
        )
        new_spec_ref = (
            ""
            if patch.clear_spec_ref
            else patch.spec_ref
            if patch.spec_ref is not None
            else current.spec_ref
        )
        candidate = replace(
            current,
            status=patch.status if patch.status is not None else current.status,
            priority=patch.priority if patch.priority is not None else current.priority,
            requirement=(
                patch.requirement
                if patch.requirement is not None
                else current.requirement
            ),
            rationale=(
                patch.rationale if patch.rationale is not None else current.rationale
            ),
            verification=(
                patch.verification
                if patch.verification is not None
                else current.verification
            ),
            spec_ref=new_spec_ref,
            linked_tests=new_tests,
            affected_paths=new_paths,
            last_updated=patch.timestamp or utc_timestamp(),
        )
        normalized = validate_requirement_record(candidate, config)
        _require_resolvable_tests(
            repo_root,
            list(normalized.linked_tests),
            config,
        )
        _require_existing_spec(repo_root, normalized.spec_ref)
        return write_requirement_record(
            repo_root,
            normalized,
            config,
            expected_digest=source_digest,
        )


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
    """
    if not linked_tests and not manual_verification(verification.strip()):
        raise ValueError(
            "Requirement activation needs linked tests or explicit `Manual:`/`Inspection:` verification."
        )
    _require_resolvable_tests(repo_root, linked_tests, config)
    return update_requirement(
        repo_root,
        req_id,
        config=config,
        patch=RequirementPatch(
            status="Active",
            verification=verification,
            linked_tests=linked_tests,
            timestamp=timestamp,
        ),
    )


def audit_traceability(
    repo_root: Path, config: WorkflowConfig
) -> list[AuditIssue]:
    """
    @brief Validate current linked tests and Active verification contracts.
    @return Deterministically ordered findings.
    @exception RequirementValidationError If a snapshot is malformed or a
               requirement ID is duplicated.
    """
    index = load_requirement_index(repo_root, config)
    issues: list[AuditIssue] = []
    cache: dict[str, tuple[bool, str]] = {}
    for record in index.by_id.values():
        unresolved: list[tuple[str, str]] = []
        for selector in record.linked_tests:
            resolved, reason = resolve_test(repo_root, selector, config, cache)
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
        if record.status != "Retired" and (
            (not record.linked_tests or unresolved) and not manual_verification(record.verification)
        ):
            issues.append(
                AuditIssue(
                    "REQ-NO-VERIFICATION",
                    f"{record.id} ({record.status}) has no resolvable linked-test set and no explicit manual verification",
                    record.id,
                    record.source_file,
                )
            )
        if (
            record.status != "Retired"
            and record.spec_ref
            and not (repo_root / record.spec_ref).is_file()
        ):
            issues.append(
                AuditIssue(
                    "REQ-SPEC-MISSING",
                    f"{record.id} references spec {record.spec_ref} which does not exist",
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
    @exception RequirementValidationError If a snapshot is malformed or a
               requirement ID is duplicated.
    """
    if config.coverage.mode == "disabled":
        return []
    records = load_all_requirement_records(repo_root, config)
    build_requirement_index(records)
    waivers = load_waivers(repo_root, config)
    coverable = iter_coverable_files(repo_root, config)
    issues: list[AuditIssue] = []
    cache: dict[str, tuple[bool, str]] = {}
    for relative_path in coverable:
        covered = _is_covered(repo_root, records, relative_path, config, cache)
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
    @exception RequirementValidationError If a snapshot is malformed or a
               requirement ID is duplicated.
    @exception ValueError If a candidate path is empty, escaping, absolute,
               or otherwise malformed.
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
    cache: dict[str, tuple[bool, str]] = {}
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
                and not _is_covered(repo_root, records, relative_path, config, cache),
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
    repo_root: Path,
    test_id: str,
    config: WorkflowConfig,
    cache: dict[str, tuple[bool, str]] | None = None,
) -> tuple[bool, str]:
    """
    @brief Resolve an exact linked-test selector against current source.
    @param[in] cache Optional per-invocation memo keyed by selector; audits
               pass one so repeated selectors do not re-read test files.
    @return ``(True, "resolved")`` or an actionable failure reason.
    """
    if cache is not None and test_id in cache:
        return cache[test_id]
    result = _resolve_test_uncached(repo_root, test_id, config)
    if cache is not None:
        cache[test_id] = result
    return result


def _resolve_test_uncached(
    repo_root: Path, test_id: str, config: WorkflowConfig
) -> tuple[bool, str]:
    """
    @brief Resolve one selector by reading the test file from disk.
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
    @exception ValueError If a waiver line is empty, escaping, absolute, or malformed.
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
    """
    if config.coverage.mode == "disabled":
        return []
    extensions = set(config.source_extensions)
    found: list[str] = []
    for root_name in config.coverage.coverable_roots:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in extensions:
                continue
            relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
            if any(
                fnmatchcase(path.name, pattern) or matches_pattern(relative, pattern)
                for pattern in config.coverage.exclude
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


def _require_existing_spec(repo_root: Path, spec_ref: str) -> None:
    """@brief Reject a write when a non-empty spec reference does not name an existing file."""
    if not spec_ref.strip():
        return
    normalized = normalize_repository_path(spec_ref, allow_glob=False)
    if not (repo_root / normalized).is_file():
        raise ValueError(f"spec_ref does not resolve to an existing file: {normalized}")


def _is_covered(
    repo_root: Path,
    records: list[RequirementRecord],
    relative_path: str,
    config: WorkflowConfig,
    cache: dict[str, tuple[bool, str]] | None = None,
) -> bool:
    """
    @brief Check for an Active matching record with a current resolvable test.
    """
    return any(
        record.status == "Active"
        and record.linked_tests
        and all(
            resolve_test(repo_root, selector, config, cache)[0]
            for selector in record.linked_tests
        )
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
