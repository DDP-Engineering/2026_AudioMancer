#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file repowise.py
@brief Validate optional RepoWise integration policy and discovery artifacts.
@details Keeps RepoWise outside the AEGIS runtime boundary. AEGIS reads only a
         strict policy, WAEGIS receipt, RepoWise state, and knowledge-graph JSON,
         then writes a normalized run-local discovery snapshot.
"""

# IMPORTS

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import subprocess
import tomllib
from typing import Any

from .persistence import atomic_write_json

# CONSTANTS

INTEGRATION_RELATIVE_PATH = (
    Path(".agentic") / "integrations" / "repowise.toml"
)
RECEIPT_RELATIVE_PATH = (
    Path(".agentic") / "integrations" / "repowise-receipt.json"
)
SUPPORTED_VERSION_SPEC = ">=0.37.0,<0.38.0"
SUPPORTED_KNOWLEDGE_GRAPH_SCHEMA = 1
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
_CONFIG_KEYS = (
    "schema_version",
    "provider",
    "mode",
    "source",
    "version_spec",
    "artifact",
    "state",
    "require_head_match",
    "require_worktree_match",
)
_RECEIPT_KEYS = (
    "schema_version",
    "provider",
    "repowise_version",
    "source",
    "profile",
    "completed",
    "head",
    "worktree_fingerprint",
    "artifact",
    "artifact_sha256",
    "state",
    "state_sha256",
    "synced_at",
)
_FINGERPRINT_EXCLUSIONS = (
    ":(exclude).agentic/**",
    ":(exclude).repowise/**",
)

# DATA MODELS / TYPEDEFINITIONS


class RepoWiseIntegrationError(ValueError):
    """
    @brief Describe an invalid RepoWise policy or unsafe artifact path.
    """


@dataclass(frozen=True)
class RepoWiseIntegration:
    """
    @brief Immutable schema-version-1 RepoWise integration policy.
    """

    schema_version: int = 1
    provider: str = "repowise"
    mode: str = "disabled"
    source: str = "none"
    version_spec: str = SUPPORTED_VERSION_SPEC
    artifact: str = ".repowise/knowledge-graph.json"
    state: str = ".repowise/state.json"
    require_head_match: bool = True
    require_worktree_match: bool = True


@dataclass(frozen=True)
class RepoWiseInspection:
    """
    @brief Stable RepoWise availability, freshness, and proposal report.
    """

    status: str
    mode: str
    source: str
    current: bool
    warnings: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    proposals: dict[str, list[str]] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    snapshot: str = ""

    def to_dict(self) -> dict[str, Any]:
        """
        @brief Serialize the inspection into stable JSON-compatible fields.
        @return Inspection mapping.
        """
        return asdict(self)


# PUBLIC API


def load_repowise_integration(repo_root: Path) -> RepoWiseIntegration:
    """
    @brief Load and strictly validate the optional RepoWise policy.
    @param[in] repo_root Repository root.
    @return Validated integration; absent files resolve to disabled policy.
    @exception RepoWiseIntegrationError If the policy is malformed or unsafe.
    """
    path = repo_root / INTEGRATION_RELATIVE_PATH
    if not path.exists():
        return RepoWiseIntegration()
    if not path.is_file():
        raise RepoWiseIntegrationError(
            f"{INTEGRATION_RELATIVE_PATH.as_posix()} is not a regular file"
        )
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise RepoWiseIntegrationError(
            f"{INTEGRATION_RELATIVE_PATH.as_posix()} is not valid UTF-8 TOML: {exc}"
        ) from exc
    _closed_keys(data, _CONFIG_KEYS, INTEGRATION_RELATIVE_PATH.as_posix())
    for key in _CONFIG_KEYS:
        if key not in data:
            raise RepoWiseIntegrationError(
                f"{INTEGRATION_RELATIVE_PATH.as_posix()} is missing {key}"
            )
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise RepoWiseIntegrationError("RepoWise integration schema_version must be 1")
    if data["provider"] != "repowise":
        raise RepoWiseIntegrationError("RepoWise integration provider must be repowise")
    if data["mode"] not in {"disabled", "advisory", "required"}:
        raise RepoWiseIntegrationError(
            "RepoWise integration mode must be disabled, advisory, or required"
        )
    if data["source"] not in {"none", "bundled", "external"}:
        raise RepoWiseIntegrationError(
            "RepoWise integration source must be none, bundled, or external"
        )
    if data["version_spec"] != SUPPORTED_VERSION_SPEC:
        raise RepoWiseIntegrationError(
            f"RepoWise version_spec must be {SUPPORTED_VERSION_SPEC}"
        )
    if data["mode"] == "disabled" and data["source"] != "none":
        raise RepoWiseIntegrationError("disabled RepoWise integration requires source none")
    if data["mode"] != "disabled" and data["source"] == "none":
        raise RepoWiseIntegrationError("enabled RepoWise integration requires a source")
    artifact = _relative_path(str(data["artifact"]), "artifact")
    state = _relative_path(str(data["state"]), "state")
    for key in ("require_head_match", "require_worktree_match"):
        if type(data[key]) is not bool:
            raise RepoWiseIntegrationError(f"RepoWise integration {key} must be boolean")
    return RepoWiseIntegration(
        schema_version=1,
        provider="repowise",
        mode=str(data["mode"]),
        source=str(data["source"]),
        version_spec=SUPPORTED_VERSION_SPEC,
        artifact=artifact,
        state=state,
        require_head_match=data["require_head_match"],
        require_worktree_match=data["require_worktree_match"],
    )


def effective_repowise_config(repo_root: Path) -> dict[str, Any]:
    """
    @brief Return the effective optional integration policy.
    @param[in] repo_root Repository root.
    @return JSON-compatible policy with its configuration path.
    @exception RepoWiseIntegrationError If the policy is malformed or unsafe.
    """
    config = load_repowise_integration(repo_root)
    return {
        **asdict(config),
        "config_path": INTEGRATION_RELATIVE_PATH.as_posix(),
        "present": (repo_root / INTEGRATION_RELATIVE_PATH).is_file(),
    }


def inspect_repowise(
    repo_root: Path,
    *,
    run_id: str | None = None,
    write_snapshot: bool = False,
) -> RepoWiseInspection:
    """
    @brief Validate configured RepoWise evidence and derive discovery proposals.
    @param[in] repo_root Repository root.
    @param[in] run_id Optional AEGIS run ID for a durable snapshot.
    @param[in] write_snapshot Whether to persist the normalized snapshot.
    @return Stable inspection with current/stale/invalid state.
    @exception RepoWiseIntegrationError If the integration policy itself is
               malformed or unsafe, or a snapshot is requested without a run ID.
    """
    config = load_repowise_integration(repo_root)
    if config.mode == "disabled":
        return RepoWiseInspection(
            status="disabled",
            mode=config.mode,
            source=config.source,
            current=False,
        )

    artifact_path = repo_root / config.artifact
    state_path = repo_root / config.state
    receipt_path = repo_root / RECEIPT_RELATIVE_PATH
    required_paths = (artifact_path, state_path, receipt_path)
    missing = [
        path.relative_to(repo_root).as_posix()
        for path in required_paths
        if not path.is_file()
    ]
    if missing:
        return _unavailable(
            config,
            "missing",
            "missing RepoWise evidence: " + ", ".join(missing),
        )
    try:
        artifact = _load_json(artifact_path, MAX_ARTIFACT_BYTES)
        state = _load_json(state_path, 8 * 1024 * 1024)
        receipt = _load_json(receipt_path, 2 * 1024 * 1024)
        _validate_knowledge_graph(artifact)
        _validate_state(state)
        _validate_receipt(receipt, config)
    except RepoWiseIntegrationError as exc:
        return _unavailable(config, "invalid", str(exc))

    warnings: list[str] = []
    artifact_digest = _sha256_file(artifact_path)
    state_digest = _sha256_file(state_path)
    if receipt["artifact"] != config.artifact:
        warnings.append("receipt artifact path does not match integration policy")
    if receipt["state"] != config.state:
        warnings.append("receipt state path does not match integration policy")
    if receipt["artifact_sha256"] != artifact_digest:
        warnings.append("RepoWise knowledge-graph digest does not match the receipt")
    if receipt["state_sha256"] != state_digest:
        warnings.append("RepoWise state digest does not match the receipt")
    head = repository_head(repo_root)
    worktree = worktree_fingerprint(repo_root)
    if config.require_head_match:
        if receipt["head"] != head:
            warnings.append("RepoWise receipt Git HEAD is stale")
        if state.get("last_sync_commit", "") != head:
            warnings.append("RepoWise state last_sync_commit is stale")
    if (
        config.require_worktree_match
        and receipt["worktree_fingerprint"] != worktree
    ):
        warnings.append("RepoWise receipt working-tree fingerprint is stale")

    proposals = _derive_proposals(artifact)
    provenance = {
        "provider": "repowise",
        "repowise_version": receipt["repowise_version"],
        "knowledge_graph_schema": artifact["schema_version"],
        "head": head,
        "worktree_fingerprint": worktree,
        "artifact_sha256": artifact_digest,
        "state_sha256": state_digest,
        "receipt": RECEIPT_RELATIVE_PATH.as_posix(),
    }
    inspection = RepoWiseInspection(
        status="stale" if warnings else "current",
        mode=config.mode,
        source=config.source,
        current=not warnings,
        warnings=tuple(sorted(set(warnings))),
        evidence=(
            config.artifact,
            config.state,
            RECEIPT_RELATIVE_PATH.as_posix(),
        ),
        proposals=proposals,
        provenance=provenance,
    )
    if not write_snapshot or not inspection.current:
        return inspection
    if not run_id:
        raise RepoWiseIntegrationError(
            "run_id is required when writing a RepoWise discovery snapshot"
        )
    snapshot_path = (
        repo_root
        / ".agentic"
        / "runs"
        / run_id
        / "discovery"
        / "repowise.json"
    )
    snapshot = {
        "schema_version": 1,
        "status": inspection.status,
        "warnings": list(inspection.warnings),
        "evidence": list(inspection.evidence),
        "provenance": inspection.provenance,
        "proposals": inspection.proposals,
    }
    _atomic_json(snapshot_path, snapshot)
    return RepoWiseInspection(
        **{
            **inspection.to_dict(),
            "snapshot": snapshot_path.relative_to(repo_root).as_posix(),
        }
    )


def repository_head(repo_root: Path) -> str:
    """
    @brief Return the current Git HEAD, or an empty string outside Git.
    @param[in] repo_root Repository root.
    @return Lowercase commit identifier or empty string.
    """
    result = _git(repo_root, "rev-parse", "--verify", "HEAD")
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8", errors="replace").strip().lower()


def worktree_fingerprint(repo_root: Path) -> str:
    """
    @brief Hash relevant dirty-state records and their current file bytes.
    @param[in] repo_root Repository root.
    @return SHA-256 fingerprint stable across AEGIS/RepoWise runtime changes.
    @details Excludes `.agentic` and `.repowise` so creating runs, receipts, or
             provider state cannot immediately invalidate a successful sync.
    """
    result = _git(
        repo_root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--",
        ".",
        *_FINGERPRINT_EXCLUSIONS,
    )
    if result.returncode != 0:
        return sha256(b"non-git").hexdigest()
    digest = sha256(result.stdout)
    records = result.stdout.split(b"\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if len(record) < 4:
            continue
        status = record[:2].decode("ascii", errors="replace")
        if "R" in status or "C" in status:
            # In `-z` mode the original path of a rename or copy arrives as
            # the following NUL-separated record with no status prefix; the
            # raw stdout already feeds the digest, so consume it whole and
            # hash only the current path below.
            index += 1
        candidate = record[3:].decode("utf-8", errors="surrogateescape")
        path = repo_root / candidate
        try:
            resolved = path.resolve()
            resolved.relative_to(repo_root.resolve())
        except (OSError, ValueError):
            continue
        if path.is_file() and not path.is_symlink():
            digest.update(candidate.encode("utf-8", errors="surrogateescape"))
            digest.update(_sha256_file(path).encode("ascii"))
    return digest.hexdigest()


# LOCAL HELPERS


def _unavailable(
    config: RepoWiseIntegration,
    status: str,
    warning: str,
) -> RepoWiseInspection:
    """@brief Build one unavailable inspection without throwing on artifacts."""
    return RepoWiseInspection(
        status=status,
        mode=config.mode,
        source=config.source,
        current=False,
        warnings=(warning,),
    )


def _closed_keys(data: dict[str, Any], keys: tuple[str, ...], label: str) -> None:
    """@brief Reject missing container shape and unknown keys."""
    if not isinstance(data, dict):
        raise RepoWiseIntegrationError(f"{label} must contain a TOML table")
    unknown = sorted(set(data) - set(keys))
    if unknown:
        raise RepoWiseIntegrationError(
            f"{label} contains unsupported key(s): {', '.join(unknown)}"
        )


def _relative_path(value: str, key: str) -> str:
    """@brief Validate one confined repository-relative POSIX path."""
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or (path.parts and ":" in path.parts[0])
    ):
        raise RepoWiseIntegrationError(
            f"RepoWise integration {key} must be a confined relative path"
        )
    return path.as_posix()


def _load_json(path: Path, maximum: int) -> dict[str, Any]:
    """@brief Load one bounded UTF-8 JSON object."""
    try:
        if path.stat().st_size > maximum:
            raise RepoWiseIntegrationError(
                f"{path.name} exceeds the {maximum}-byte validation limit"
            )
        value = json.loads(path.read_text(encoding="utf-8"))
    except RepoWiseIntegrationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepoWiseIntegrationError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RepoWiseIntegrationError(f"{path.name} must contain a JSON object")
    return value


def _validate_knowledge_graph(data: dict[str, Any]) -> None:
    """@brief Validate the stable RepoWise knowledge-graph boundary."""
    required = ("version", "schema_version", "project", "nodes", "edges", "layers")
    missing = [key for key in required if key not in data]
    if missing:
        raise RepoWiseIntegrationError(
            "knowledge-graph.json is missing: " + ", ".join(missing)
        )
    if (
        type(data["schema_version"]) is not int
        or data["schema_version"] < SUPPORTED_KNOWLEDGE_GRAPH_SCHEMA
    ):
        raise RepoWiseIntegrationError(
            "knowledge-graph.json has an unsupported schema_version"
        )
    if data["version"] != "1.0.0":
        raise RepoWiseIntegrationError(
            "knowledge-graph.json version must be 1.0.0"
        )
    if not isinstance(data["project"], dict):
        raise RepoWiseIntegrationError("knowledge-graph project must be an object")
    for key in ("nodes", "edges", "layers"):
        if not isinstance(data[key], list):
            raise RepoWiseIntegrationError(f"knowledge-graph {key} must be an array")


def _validate_state(data: dict[str, Any]) -> None:
    """@brief Validate the RepoWise state fields required for freshness."""
    value = data.get("last_sync_commit")
    if not isinstance(value, str):
        raise RepoWiseIntegrationError(
            "RepoWise state last_sync_commit must be a string"
        )


def _validate_receipt(
    data: dict[str, Any],
    config: RepoWiseIntegration,
) -> None:
    """@brief Validate the strict WAEGIS RepoWise receipt."""
    _closed_keys(data, _RECEIPT_KEYS, RECEIPT_RELATIVE_PATH.as_posix())
    missing = [key for key in _RECEIPT_KEYS if key not in data]
    if missing:
        raise RepoWiseIntegrationError(
            "RepoWise receipt is missing: " + ", ".join(missing)
        )
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise RepoWiseIntegrationError("RepoWise receipt schema_version must be 1")
    if data["provider"] != "repowise" or data["source"] != config.source:
        raise RepoWiseIntegrationError("RepoWise receipt provider/source mismatch")
    if type(data["completed"]) is not bool or not data["completed"]:
        raise RepoWiseIntegrationError("RepoWise receipt is not complete")
    if not _supported_version(data["repowise_version"]):
        raise RepoWiseIntegrationError(
            f"RepoWise receipt version must satisfy {SUPPORTED_VERSION_SPEC}"
        )
    for key in (
        "profile",
        "head",
        "worktree_fingerprint",
        "artifact",
        "artifact_sha256",
        "state",
        "state_sha256",
        "synced_at",
    ):
        if not isinstance(data[key], str):
            raise RepoWiseIntegrationError(f"RepoWise receipt {key} must be a string")


def _supported_version(value: object) -> bool:
    """@brief Accept only the validated RepoWise 0.37 release line."""
    if not isinstance(value, str):
        return False
    fields = value.split(".")
    return (
        len(fields) >= 3
        and fields[0] == "0"
        and fields[1] == "37"
        and fields[2].isdigit()
    )


def _derive_proposals(data: dict[str, Any]) -> dict[str, list[str]]:
    """@brief Normalize RepoWise graph data into adoption-form proposals."""
    nodes = [item for item in data["nodes"] if isinstance(item, dict)]
    file_nodes = [
        item
        for item in nodes
        if isinstance(item.get("filePath"), str)
        and str(item.get("id", "")).startswith("file:")
    ]
    tests = sorted(
        {
            str(item["filePath"])
            for item in file_nodes
            if "test" in item.get("tags", [])
        }
    )
    entry_points = {
        str(item["filePath"])
        for item in file_nodes
        if "entry_point" in item.get("tags", [])
    }
    project = data["project"]
    entry_points.update(
        value
        for value in project.get("entry_points", [])
        if isinstance(value, str)
    )
    source_roots = sorted(
        {
            PurePosixPath(str(item["filePath"])).parts[0]
            for item in file_nodes
            if item["filePath"]
            and "test" not in item.get("tags", [])
            and PurePosixPath(str(item["filePath"])).parts
        }
    )
    components: set[str] = set()
    for item in data.get("modules", []):
        if isinstance(item, dict):
            value = item.get("name") or item.get("id")
            if isinstance(value, str) and value:
                components.add(value)
    if not components:
        for item in data["layers"]:
            if isinstance(item, dict):
                value = item.get("name") or item.get("id")
                if isinstance(value, str) and value:
                    components.add(value)
    dependencies: set[str] = set()
    for item in project.get("tech_stack", []):
        if isinstance(item, str):
            dependencies.add(item)
        elif isinstance(item, dict):
            value = item.get("name") or item.get("technology")
            if isinstance(value, str) and value:
                dependencies.add(value)
    return {
        "source_roots": source_roots,
        "candidate_components": sorted(components),
        "external_dependencies": sorted(dependencies),
        "entry_points": sorted(entry_points),
        "existing_tests": tests,
    }


def _git(repo_root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    """@brief Run one bounded read-only Git query without a shell."""
    try:
        return subprocess.run(
            ("git", "-C", str(repo_root), *arguments),
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(arguments, 1, b"", b"")


def _sha256_file(path: Path) -> str:
    """@brief Stream one file into a SHA-256 digest."""
    digest = sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    """
    @brief Atomically write one normalized, flushed JSON document.
    """
    atomic_write_json(path, data)


# END OF FILE
