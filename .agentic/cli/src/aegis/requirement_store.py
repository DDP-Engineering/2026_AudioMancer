#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file requirement_store.py
@brief Canonical TOML persistence for durable requirement snapshots.
@details Validates the hard-break UUID identity and complete schema before
         exposing records to traceability consumers. Stage imports validate a
         complete collection before publishing any snapshot.
@details Existing-record updates use per-requirement locks and digest
         preconditions so stale snapshots cannot silently replace newer files.
"""

# IMPORTS

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tomllib
import uuid
from typing import Any, Callable

from .config import WorkflowConfig
from .persistence import (
    atomic_write_text,
    create_temporary_text,
    locked,
    replace_temporary,
    scoped_lock_path,
    sync_directory,
)

# CONSTANTS

SCHEMA_VERSION = 1
CATEGORY_IDENTITIES = {
    "functional": ("functional", "FUNC"),
    "ux": ("ux", "UX"),
    "non_functional": ("non_functional", "NFR"),
    "security": ("security", "SEC"),
    "data_privacy": ("data_privacy", "DATA"),
    "platform": ("platform", "PLAT"),
    "release": ("release", "REL"),
    "testing": ("testing", "TEST"),
}
CATEGORY_BY_CODE = {code: category for category, (_, code) in CATEGORY_IDENTITIES.items()}
VALID_STATUS = ("Planned", "Active", "Retired")
VALID_PRIORITY = ("Must", "Should", "Could")
REQUIREMENT_ID_RETRY_LIMIT = 5
REQUIREMENT_KEYS = (
    "schema_version",
    "id",
    "category",
    "status",
    "priority",
    "requirement",
    "rationale",
    "verification",
    "spec_ref",
    "affected_paths",
    "linked_tests",
    "created_on",
    "last_updated",
)
ID_PATTERN = re.compile(
    r"^REQ-(FUNC|UX|NFR|SEC|DATA|PLAT|REL|TEST)-"
    r"([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$"
)
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# DATA MODELS / TYPEDEFINITIONS


class RequirementValidationError(ValueError):
    """
    @brief Describe one invalid canonical requirement snapshot.
    """

    def __init__(self, path: str, key: str, message: str) -> None:
        """
        @brief Initialize an actionable requirement validation error.
        @param[in] path Repository-relative source path or target location.
        @param[in] key Offending schema key or identity property.
        @param[in] message Concrete validation failure.
        """
        self.path = path
        self.key = key
        self.message = message
        super().__init__(f"{path}: {key}: {message}")


class RequirementConflictError(RequirementValidationError):
    """
    @brief Report a stale requirement update without overwriting newer content.
    """

    code = "REQUIREMENT-STALE-UPDATE"

    def __init__(
        self,
        path: str,
        expected_digest: str,
        actual_digest: str,
    ) -> None:
        """
        @brief Initialize one typed optimistic-concurrency conflict.
        @param[in] path Repository-relative requirement path.
        @param[in] expected_digest Digest captured when the record was loaded.
        @param[in] actual_digest Digest present immediately before publication.
        """
        self.expected_digest = expected_digest
        self.actual_digest = actual_digest
        super().__init__(
            path,
            "stale_update",
            f"{self.code}: requirement changed after it was loaded; "
            "reload it and retry the update",
        )


@dataclass(frozen=True)
class RequirementRecord:
    """
    @brief Represent one complete current requirement snapshot.
    @details source_file is diagnostic metadata and is never serialized.
    """

    schema_version: int
    id: str
    category: str
    status: str
    priority: str
    requirement: str
    rationale: str
    verification: str
    affected_paths: tuple[str, ...]
    linked_tests: tuple[str, ...]
    created_on: str
    last_updated: str
    spec_ref: str = ""
    source_file: str | None = field(default=None, compare=False)

    @property
    def req_id(self) -> str:
        """@brief Return the canonical ID for transitional Python consumers."""
        return self.id

    def to_dict(self) -> dict[str, Any]:
        """
        @brief Return the complete persisted record in normative key order.
        @return JSON-compatible snapshot without diagnostic source metadata.
        """
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "category": self.category,
            "status": self.status,
            "priority": self.priority,
            "requirement": self.requirement,
            "rationale": self.rationale,
            "verification": self.verification,
            "spec_ref": self.spec_ref,
            "affected_paths": list(self.affected_paths),
            "linked_tests": list(self.linked_tests),
            "created_on": self.created_on,
            "last_updated": self.last_updated,
        }


# PUBLIC API


def requirement_id_category(requirement_id: str) -> str:
    """
    @brief Validate one requirement ID and return its category.
    @param[in] requirement_id Candidate hard-break requirement ID.
    @return Ratified category value encoded by the ID.
    @exception RequirementValidationError If syntax or UUIDv4 identity is invalid.
    """
    match = ID_PATTERN.fullmatch(requirement_id)
    if not match:
        raise RequirementValidationError(
            "<requirement-id>",
            "id",
            "expected REQ-<CATEGORY-CODE>-<lowercase canonical UUIDv4>",
        )
    uuid_text = match.group(2)
    try:
        parsed = uuid.UUID(uuid_text)
    except ValueError as exc:
        raise RequirementValidationError(
            "<requirement-id>", "id", "UUID portion is invalid"
        ) from exc
    if parsed.version != 4 or str(parsed) != uuid_text:
        raise RequirementValidationError(
            "<requirement-id>", "id", "UUID portion must be canonical lowercase UUIDv4"
        )
    return CATEGORY_BY_CODE[match.group(1)]


def normalize_repository_path(value: str, *, allow_glob: bool) -> str:
    """
    @brief Apply the ratified repository-relative path normalization.
    @param[in] value Candidate repository path or glob.
    @param[in] allow_glob Whether supported glob metacharacters are permitted.
    @return Normalized slash-separated repository-relative value.
    @exception ValueError If the value is empty, escaping, absolute, or malformed.
    """
    if not isinstance(value, str):
        raise ValueError("must be a string")
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = re.sub(r"/{2,}", "/", normalized).rstrip("/")
    if (
        not normalized
        or normalized.startswith(("/", "~"))
        or re.match(r"^[A-Za-z]:", normalized)
        or ".." in normalized.split("/")
    ):
        raise ValueError("must be a repository-relative path without `..`")
    if not allow_glob and any(char in normalized for char in "*?[]"):
        raise ValueError("must not contain glob syntax")
    if allow_glob:
        _validate_glob(normalized)
    return normalized


def normalize_linked_test(value: str, test_roots: tuple[str, ...]) -> str:
    """
    @brief Normalize and validate an exact linked-test selector.
    @param[in] value Candidate path and identifier separated by ``::``.
    @param[in] test_roots Configured repository test roots.
    @return Normalized exact selector.
    @exception ValueError If the selector shape or root is invalid.
    """
    if not isinstance(value, str) or "::" not in value:
        raise ValueError("must use <repo-relative-test-path>::<identifier>")
    test_path, identifier = value.split("::", 1)
    normalized_path = normalize_repository_path(test_path, allow_glob=False)
    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        raise ValueError("must contain a non-empty test identifier after `::`")
    if not any(
        normalized_path == root or normalized_path.startswith(f"{root}/")
        for root in test_roots
    ):
        raise ValueError(
            f"test path must be under a configured test root: {', '.join(test_roots)}"
        )
    return f"{normalized_path}::{normalized_identifier}"


def load_requirement_file(
    path: Path,
    repo_root: Path,
    requirement_root: str,
    config: WorkflowConfig,
) -> RequirementRecord:
    """
    @brief Parse and validate one canonical TOML requirement file.
    @param[in] path Requirement TOML path.
    @param[in] repo_root Repository root.
    @param[in] requirement_root Configured requirement root containing path.
    @param[in] config Validated workflow configuration.
    @return Complete validated requirement record.
    @exception RequirementValidationError If TOML, schema, or identity is invalid.
    """
    source = _relative(path, repo_root)
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RequirementValidationError(source, "TOML", str(exc)) from exc
    if not isinstance(data, dict):
        raise RequirementValidationError(source, "TOML", "top-level value must be a table")
    unknown = sorted(set(data) - set(REQUIREMENT_KEYS))
    missing = [key for key in REQUIREMENT_KEYS if key not in data]
    if unknown:
        raise RequirementValidationError(source, unknown[0], "unknown key")
    if missing:
        raise RequirementValidationError(source, missing[0], "required key is missing")
    record = _record_from_mapping(data, source, config)
    _validate_file_identity(record, path, repo_root, requirement_root)
    return record


def load_all_requirement_records(
    repo_root: Path, config: WorkflowConfig
) -> list[RequirementRecord]:
    """
    @brief Load all canonical requirement files from configured roots.
    @param[in] repo_root Repository root.
    @param[in] config Validated workflow configuration.
    @return Records sorted deterministically by ID and source path.
    @exception RequirementValidationError If any record is invalid.
    """
    records: list[RequirementRecord] = []
    for root_name in config.requirement_roots:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.toml")):
            records.append(load_requirement_file(path, repo_root, root_name, config))
    return sorted(records, key=lambda item: (item.id, item.source_file or ""))


def find_requirement_record(
    repo_root: Path, requirement_id: str, config: WorkflowConfig
) -> RequirementRecord:
    """
    @brief Locate exactly one canonical requirement by ID.
    @param[in] repo_root Repository root.
    @param[in] requirement_id Canonical requirement ID.
    @param[in] config Validated workflow configuration.
    @return Matching current requirement snapshot.
    @exception RequirementValidationError If the ID is invalid, absent, or duplicated.
    """
    category = requirement_id_category(requirement_id)
    directory = CATEGORY_IDENTITIES[category][0]
    matches: list[RequirementRecord] = []
    for root_name in config.requirement_roots:
        path = repo_root / root_name / directory / f"{requirement_id}.toml"
        if path.exists():
            matches.append(load_requirement_file(path, repo_root, root_name, config))
    if not matches:
        raise RequirementValidationError(
            "<requirements>", "id", f"requirement not found: {requirement_id}"
        )
    if len(matches) > 1:
        locations = ", ".join(item.source_file or "<unknown>" for item in matches)
        raise RequirementValidationError(
            "<requirements>", "id", f"duplicate requirement ID at {locations}"
        )
    return matches[0]


def create_requirement_record(
    repo_root: Path,
    config: WorkflowConfig,
    *,
    category: str,
    priority: str,
    requirement: str,
    rationale: str,
    verification: str,
    spec_ref: str = "",
    affected_paths: list[str] | tuple[str, ...] = (),
    linked_tests: list[str] | tuple[str, ...] = (),
    timestamp: str | None = None,
    uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4,
) -> RequirementRecord:
    """
    @brief Create one Planned snapshot with exclusive collision-safe publication.
    @return Newly persisted requirement record.
    @exception RequirementValidationError If a field is invalid or no unique
               identifier can be allocated within the bounded retry limit.
    """
    if category not in CATEGORY_IDENTITIES:
        raise RequirementValidationError(
            "<new-requirement>", "category", f"expected one of {', '.join(CATEGORY_IDENTITIES)}"
        )
    now = timestamp or utc_timestamp()
    directory, code = CATEGORY_IDENTITIES[category]
    target_root = repo_root / config.requirement_roots[0] / directory
    target_root.mkdir(parents=True, exist_ok=True)
    for _attempt in range(REQUIREMENT_ID_RETRY_LIMIT):
        candidate_uuid = uuid_factory()
        requirement_id = f"REQ-{code}-{candidate_uuid}"
        source = _relative(target_root / f"{requirement_id}.toml", repo_root)
        record = validate_requirement_record(
            RequirementRecord(
                schema_version=SCHEMA_VERSION,
                id=requirement_id,
                category=category,
                status="Planned",
                priority=priority,
                requirement=requirement,
                rationale=rationale,
                verification=verification,
                spec_ref=spec_ref,
                affected_paths=tuple(affected_paths),
                linked_tests=tuple(linked_tests),
                created_on=now,
                last_updated=now,
                source_file=source,
            ),
            config,
        )
        target = repo_root / source
        if _publish_exclusive(target, render_requirement_toml(record)):
            return record
    raise RequirementValidationError(
        "<new-requirement>",
        "id",
        "could not allocate a unique requirement ID after "
        f"{REQUIREMENT_ID_RETRY_LIMIT} attempts",
    )


def write_requirement_record(
    repo_root: Path,
    record: RequirementRecord,
    config: WorkflowConfig,
    *,
    expected_digest: str | None = None,
) -> RequirementRecord:
    """
    @brief Validate and atomically replace one existing requirement snapshot.
    @param[in] repo_root Repository root.
    @param[in] record Complete replacement snapshot.
    @param[in] config Validated workflow configuration.
    @param[in] expected_digest Optional digest captured when the source loaded.
    @return Normalized record persisted to its immutable source path.
    @exception RequirementValidationError If the record or target identity is invalid.
    @exception RequirementConflictError If the source changed before publish.
    """
    normalized = validate_requirement_record(record, config)
    if not normalized.source_file:
        raise RequirementValidationError("<requirements>", "source_file", "source path is required for update")
    target = repo_root / normalized.source_file
    matching_root = next(
        (
            root_name
            for root_name in config.requirement_roots
            if target.is_relative_to(repo_root / root_name)
        ),
        None,
    )
    if matching_root is None:
        raise RequirementValidationError(normalized.source_file, "path", "file is outside configured requirement roots")
    _validate_file_identity(normalized, target, repo_root, matching_root)
    with locked(requirement_lock_path(repo_root, normalized.id)):
        if not target.is_file():
            raise RequirementValidationError(
                normalized.source_file,
                "path",
                "existing requirement file is missing",
            )
        if expected_digest is not None:
            actual_digest = _file_digest(target)
            if actual_digest != expected_digest:
                raise RequirementConflictError(
                    normalized.source_file,
                    expected_digest,
                    actual_digest,
                )
        _atomic_replace(target, render_requirement_toml(normalized))
    return normalized


def publish_requirement_records(
    repo_root: Path,
    records: list[RequirementRecord],
    config: WorkflowConfig,
) -> list[RequirementRecord]:
    """
    @brief      Validate and publish a complete requirement-stage collection.
    @param[in]  repo_root Repository root.
    @param[in]  records Candidate snapshots carrying CLI-generated IDs.
    @param[in]  config Validated workspace configuration.
    @return     Normalized records in deterministic ID order.
    @exception  RequirementValidationError If any record or identity is invalid,
                or if an OSError occurs during publication (wrapped).
    @exception  RequirementConflictError If any target file changed underneath
                the held locks between the pre-write digest check and publish.
    @details    Every record is validated before temporary files are created.
                Existing snapshots are restored if publication fails.
    """
    normalized_records: list[RequirementRecord] = []
    seen: set[str] = set()
    for candidate in records:
        if candidate.id in seen:
            raise RequirementValidationError(
                "<requirement-stage>", "id", f"duplicate requirement ID {candidate.id}"
            )
        seen.add(candidate.id)
        normalized = validate_requirement_record(candidate, config)
        directory = CATEGORY_IDENTITIES[normalized.category][0]
        source = (
            Path(config.requirement_roots[0])
            / directory
            / f"{normalized.id}.toml"
        ).as_posix()
        normalized_records.append(
            RequirementRecord(
                **{
                    **normalized.to_dict(),
                    "affected_paths": normalized.affected_paths,
                    "linked_tests": normalized.linked_tests,
                    "source_file": source,
                }
            )
        )

    targets: list[tuple[Path, Path, str | None, str | None]] = []
    try:
        with ExitStack() as locks:
            for record in sorted(normalized_records, key=lambda item: item.id):
                locks.enter_context(
                    locked(requirement_lock_path(repo_root, record.id))
                )
            for record in sorted(normalized_records, key=lambda item: item.id):
                target = repo_root / str(record.source_file)
                target.parent.mkdir(parents=True, exist_ok=True)
                previous = (
                    target.read_text(encoding="utf-8")
                    if target.is_file()
                    else None
                )
                previous_digest = (
                    _file_digest(target) if target.is_file() else None
                )
                temporary = _write_temporary(
                    target,
                    render_requirement_toml(record),
                )
                targets.append(
                    (target, temporary, previous, previous_digest)
                )
            for target, _temporary, _previous, previous_digest in targets:
                actual_digest = (
                    _file_digest(target) if target.is_file() else None
                )
                if actual_digest != previous_digest:
                    raise RequirementConflictError(
                        _relative(target, repo_root),
                        previous_digest or "<absent>",
                        actual_digest or "<absent>",
                    )
            for target, temporary, _previous, _digest in targets:
                replace_temporary(temporary, target)
    except RequirementConflictError:
        for _target, temporary, _previous, _digest in targets:
            temporary.unlink(missing_ok=True)
        raise
    except OSError as exc:
        unrestored: list[str] = []
        for target, temporary, previous, _digest in reversed(targets):
            try:
                temporary.unlink(missing_ok=True)
                if previous is None:
                    if target.exists():
                        target.unlink()
                        sync_directory(target.parent)
                else:
                    _atomic_replace(target, previous)
            except OSError as restore_error:
                unrestored.append(
                    f"{_relative(target, repo_root)} ({restore_error})"
                )
        message = f"atomic import failed: {exc}"
        if unrestored:
            message += (
                "; rollback could not restore: " + ", ".join(unrestored)
            )
        raise RequirementValidationError(
            "<requirement-stage>", "publish", message
        ) from exc
    return sorted(normalized_records, key=lambda item: item.id)


def requirement_lock_path(repo_root: Path, requirement_id: str) -> Path:
    """
    @brief Return the repository/requirement-scoped update lock.
    @param[in] repo_root Repository root.
    @param[in] requirement_id Canonical requirement identity.
    @return Worktree-local persistent lock path.
    """
    return scoped_lock_path(repo_root, "requirements", requirement_id)


def requirement_source_digest(
    repo_root: Path,
    record: RequirementRecord,
) -> str:
    """
    @brief Digest the exact source bytes for an already loaded requirement.
    @param[in] repo_root Repository root.
    @param[in] record Loaded record carrying diagnostic source_file metadata.
    @return Lowercase SHA-256 digest.
    @exception RequirementValidationError If the source is unavailable.
    """
    if not record.source_file:
        raise RequirementValidationError(
            "<requirements>",
            "source_file",
            "source path is required for a freshness check",
        )
    path = repo_root / record.source_file
    try:
        return _file_digest(path)
    except OSError as exc:
        raise RequirementValidationError(
            record.source_file,
            "source_file",
            f"cannot read source for freshness check: {exc}",
        ) from exc


def validate_requirement_record(
    record: RequirementRecord, config: WorkflowConfig
) -> RequirementRecord:
    """
    @brief Validate and normalize all fields in a requirement snapshot.
    @param[in] record Candidate record.
    @param[in] config Validated workflow configuration.
    @return Normalized immutable record.
    @exception RequirementValidationError If any field violates the schema.
    """
    source = record.source_file or "<requirement>"
    if type(record.schema_version) is not int or record.schema_version != SCHEMA_VERSION:
        raise RequirementValidationError(source, "schema_version", "expected integer 1")
    if not isinstance(record.id, str):
        raise RequirementValidationError(source, "id", "must be a string")
    try:
        id_category = requirement_id_category(record.id)
    except RequirementValidationError as exc:
        raise RequirementValidationError(source, "id", exc.message) from exc
    if record.category not in CATEGORY_IDENTITIES:
        raise RequirementValidationError(source, "category", f"expected one of {', '.join(CATEGORY_IDENTITIES)}")
    if record.category != id_category:
        raise RequirementValidationError(source, "category", "does not match the category code in id")
    if record.status not in VALID_STATUS:
        raise RequirementValidationError(source, "status", f"expected one of {', '.join(VALID_STATUS)}")
    if record.priority not in VALID_PRIORITY:
        raise RequirementValidationError(source, "priority", f"expected one of {', '.join(VALID_PRIORITY)}")
    scalars = {
        "requirement": record.requirement,
        "rationale": record.rationale,
        "verification": record.verification,
    }
    normalized_scalars: dict[str, str] = {}
    for key, value in scalars.items():
        if not isinstance(value, str) or not value.strip():
            raise RequirementValidationError(source, key, "must be a non-empty string")
        normalized_scalars[key] = value.strip()
    if not isinstance(record.spec_ref, str):
        raise RequirementValidationError(source, "spec_ref", "must be a string")
    spec_ref = record.spec_ref.strip()
    if spec_ref:
        try:
            spec_ref = normalize_repository_path(spec_ref, allow_glob=False)
        except ValueError as exc:
            raise RequirementValidationError(source, "spec_ref", str(exc)) from exc
    affected = _normalize_set(
        record.affected_paths,
        source,
        "affected_paths",
        lambda item: normalize_repository_path(item, allow_glob=True),
    )
    linked = _normalize_set(
        record.linked_tests,
        source,
        "linked_tests",
        lambda item: normalize_linked_test(item, config.test_roots),
    )
    created = _parse_timestamp(record.created_on, source, "created_on")
    updated = _parse_timestamp(record.last_updated, source, "last_updated")
    if updated < created:
        raise RequirementValidationError(source, "last_updated", "must not be earlier than created_on")
    if record.status == "Active" and not linked and not manual_verification(normalized_scalars["verification"]):
        raise RequirementValidationError(
            source,
            "verification",
            "Active requirements need linked tests or `Manual:`/`Inspection:` method text",
        )
    return RequirementRecord(
        schema_version=SCHEMA_VERSION,
        id=record.id,
        category=record.category,
        status=record.status,
        priority=record.priority,
        requirement=normalized_scalars["requirement"],
        rationale=normalized_scalars["rationale"],
        verification=normalized_scalars["verification"],
        spec_ref=spec_ref,
        affected_paths=affected,
        linked_tests=linked,
        created_on=record.created_on,
        last_updated=record.last_updated,
        source_file=record.source_file,
    )


def render_requirement_toml(record: RequirementRecord) -> str:
    """
    @brief Render a requirement snapshot in normative deterministic TOML order.
    @param[in] record Validated requirement record.
    @return UTF-8 text with LF-compatible line endings and final newline.
    """
    lines = [
        f"schema_version = {record.schema_version}",
        f"id = {_toml_string(record.id)}",
        f"category = {_toml_string(record.category)}",
        f"status = {_toml_string(record.status)}",
        f"priority = {_toml_string(record.priority)}",
        f"requirement = {_toml_string(record.requirement)}",
        f"rationale = {_toml_string(record.rationale)}",
        f"verification = {_toml_string(record.verification)}",
        f"spec_ref = {_toml_string(record.spec_ref)}",
        "",
        *_render_array("affected_paths", record.affected_paths),
        "",
        *_render_array("linked_tests", record.linked_tests),
        "",
        f"created_on = {_toml_string(record.created_on)}",
        f"last_updated = {_toml_string(record.last_updated)}",
    ]
    return "\n".join(lines) + "\n"


def utc_timestamp() -> str:
    """@brief Return the current UTC time in the ratified second-precision form."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def manual_verification(value: str) -> bool:
    """
    @brief Return whether text is an explicit non-empty manual method.
    """
    return any(
        value.startswith(prefix) and bool(value[len(prefix) :].strip())
        for prefix in ("Manual:", "Inspection:")
    )


# LOCAL HELPERS


def _record_from_mapping(
    data: dict[str, Any], source: str, config: WorkflowConfig
) -> RequirementRecord:
    """@brief Convert a closed TOML mapping into a validated record."""
    if type(data["schema_version"]) is not int:
        raise RequirementValidationError(source, "schema_version", "must be integer 1")
    scalar_keys = (
        "id",
        "category",
        "status",
        "priority",
        "requirement",
        "rationale",
        "verification",
        "spec_ref",
        "created_on",
        "last_updated",
    )
    for key in scalar_keys:
        if not isinstance(data[key], str):
            raise RequirementValidationError(source, key, "must be a string")
    for key in ("affected_paths", "linked_tests"):
        value = data[key]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise RequirementValidationError(source, key, "must be an array of strings")
    return validate_requirement_record(
        RequirementRecord(
            schema_version=data["schema_version"],
            id=data["id"],
            category=data["category"],
            status=data["status"],
            priority=data["priority"],
            requirement=data["requirement"],
            rationale=data["rationale"],
            verification=data["verification"],
            spec_ref=data["spec_ref"],
            affected_paths=tuple(data["affected_paths"]),
            linked_tests=tuple(data["linked_tests"]),
            created_on=data["created_on"],
            last_updated=data["last_updated"],
            source_file=source,
        ),
        config,
    )


def _validate_file_identity(
    record: RequirementRecord, path: Path, repo_root: Path, requirement_root: str
) -> None:
    """@brief Enforce the category, directory, ID, and filename identity tuple."""
    expected_directory = CATEGORY_IDENTITIES[record.category][0]
    expected = repo_root / requirement_root / expected_directory / f"{record.id}.toml"
    if path.resolve() != expected.resolve():
        raise RequirementValidationError(
            _relative(path, repo_root),
            "path",
            f"identity requires {_relative(expected, repo_root)}",
        )


def _normalize_set(
    values: tuple[str, ...] | list[str],
    source: str,
    key: str,
    normalizer: Callable[[str], str],
) -> tuple[str, ...]:
    """@brief Normalize, reject duplicates, and sort one set-like array."""
    if not isinstance(values, (tuple, list)):
        raise RequirementValidationError(source, key, "must be an array of strings")
    normalized: list[str] = []
    for item in values:
        try:
            value = normalizer(item)
        except ValueError as exc:
            raise RequirementValidationError(source, key, f"invalid value {item!r}: {exc}") from exc
        if value in normalized:
            raise RequirementValidationError(source, key, f"duplicate normalized value: {value}")
        normalized.append(value)
    return tuple(sorted(normalized))


def _parse_timestamp(value: str, source: str, key: str) -> datetime:
    """@brief Parse one exact RFC 3339 UTC timestamp."""
    if not isinstance(value, str) or not TIMESTAMP_PATTERN.fullmatch(value):
        raise RequirementValidationError(source, key, "expected YYYY-MM-DDTHH:MM:SSZ")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise RequirementValidationError(source, key, f"invalid UTC calendar timestamp: {value}") from exc


def _validate_glob(value: str) -> None:
    """@brief Reject nested or unbalanced glob bracket expressions."""
    depth = 0
    for char in value:
        if char == "[":
            if depth:
                raise ValueError("glob bracket expressions must be balanced")
            depth = 1
        elif char == "]":
            if not depth:
                raise ValueError("glob bracket expressions must be balanced")
            depth = 0
    if depth:
        raise ValueError("glob bracket expressions must be balanced")


def _render_array(name: str, values: tuple[str, ...]) -> list[str]:
    """@brief Render a deterministic TOML string array with one item per line."""
    if not values:
        return [f"{name} = []"]
    return [f"{name} = [", *(f"  {_toml_string(value)}," for value in values), "]"]


def _toml_string(value: str) -> str:
    """@brief Encode a Python string as a TOML-compatible basic string."""
    return json.dumps(value, ensure_ascii=False)


def _publish_exclusive(path: Path, content: str) -> bool:
    """
    @brief Atomically publish content only when the destination is absent.
    """
    temporary = _write_temporary(path, content)
    try:
        os.link(temporary, path)
        sync_directory(path.parent)
    except FileExistsError:
        return False
    finally:
        temporary.unlink(missing_ok=True)
    return True


def _atomic_replace(path: Path, content: str) -> None:
    """
    @brief Atomically replace one sibling file after complete serialization.
    """
    atomic_write_text(path, content)


def _write_temporary(path: Path, content: str) -> Path:
    """
    @brief Persist and flush a temporary sibling for atomic publication.
    """
    return create_temporary_text(path, content)


def _file_digest(path: Path) -> str:
    """
    @brief Return the SHA-256 digest of one file's exact bytes.
    """
    return sha256(path.read_bytes()).hexdigest()


def _relative(path: Path, repo_root: Path) -> str:
    """@brief Return one repository-relative path with forward slashes."""
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise RequirementValidationError(str(path), "path", "path escapes repository root") from exc


# END OF FILE
