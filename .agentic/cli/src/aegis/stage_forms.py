#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file stage_forms.py
@brief File-first stage preparation, import, readiness, and closure.
@details Implements strict schema-3 TOML forms, policy capture, collection
         imports, solution-design integrity, explicit closure approval, and
         deterministic routing for standard and adoption workflows.
"""

# IMPORTS

from __future__ import annotations

import copy
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import tomllib
import uuid
from typing import Any

from ._form_io import read_string_field as _string
from .config import GATE_ORDER, WorkflowConfig, load_config
from .models import (
    STAGES,
    ChangeUnit,
    Check,
    Graph,
    IntentAlignment,
    SolutionDesign,
    Stage,
    StageRecord,
    now_iso,
)
from .paths import relative_to_root
from .requirement_store import (
    CATEGORY_IDENTITIES,
    RequirementRecord,
    find_requirement_record,
    load_all_requirement_records,
    publish_requirement_records,
    utc_timestamp,
)
from .requirements import RequirementPatch, update_requirement
from .repowise import inspect_repowise
from .store import (
    append_journal,
    relink_check_evidence,
    run_dir,
    save_graph,
    save_graph_with_journal_events,
    serialized_graph_mutation,
    set_access_mode,
)
from .stage_schema import (
    REQUIRED_STAGE_VALUE,
    STAGE_FIELD_SPECS,
    StageOperationError,
    StageFieldSpec,
    run_stage_spec,
)
from .waivers import (
    Blocker,
    active_waiver,
    blocker_to_dict,
    current_file_digest,
    red_before_green_blocker,
    state_digests,
)

# CONSTANTS

FORM_SCHEMA_VERSION = 3
COLLECTION_STAGES = ("requirement", "check")
BLOCKER_SLUG_LIMIT = 72
COMMON_CONTROL_KEYS = (
    "requested_access_mode",
    "access_rationale",
    "route_to",
    "route_rationale",
    "summary",
    "unresolved_questions",
)
REQUIREMENT_FORM_KEYS = (
    "schema_version",
    "run_id",
    "stage",
    "revision",
    "id",
    "category",
    "priority",
    "requirement",
    "rationale",
    "verification",
    "spec_ref",
    "affected_paths",
    "linked_tests",
)
CHECK_FORM_KEYS = (
    "schema_version",
    "run_id",
    "stage",
    "revision",
    "id",
    "level",
    "cites_requirement",
    "cites_spec",
    "command",
    "path",
    "contract_variants",
    "concerns",
    "parity_targets",
)

# PUBLIC API


def bypassed_stages(graph: Graph) -> list[Stage]:
    """
    @brief Return explicit lifecycle stages bypassed by the selected run type.
    @param[in] graph Valid run graph.
    @return Bypassed stages in standard lifecycle order.
    @exception StageOperationError If the graph conflicts with its run profile.
    """
    return list(run_stage_spec(graph).bypassed_stages)


def quick_scope_advisory(
    graph: Graph,
    config: WorkflowConfig,
) -> dict[str, Any] | None:
    """
    @brief Build the optional non-blocking quick-run changed-path advisory.
    @param[in] graph Quick or full run graph after implementation import.
    @param[in] config Validated workflow policy.
    @return Advisory metadata above the configured limit, otherwise ``None``.
    @exception StageOperationError If the graph conflicts with its run profile.
    """
    run_stage_spec(graph)
    policy = config.quick_changed_paths
    if graph.profile != "quick" or policy.mode == "disabled":
        return None
    changed_paths = sorted(
        {path for unit in graph.change_units for path in unit.touched_paths}
    )
    if len(changed_paths) <= policy.max_paths:
        return None
    restart = f"aegis run start {graph.intent.kind}"
    return {
        "code": "QUICK-SCOPE-ADVISORY",
        "status": "advisory",
        "changed_path_count": len(changed_paths),
        "max_paths": policy.max_paths,
        "message": (
            f"Quick run touches {len(changed_paths)} changed paths, above the "
            f"configured maximum of {policy.max_paths}. Quick runs cannot route "
            "into bypassed stages; restart as a full run and carry the recorded "
            f"context forward with `{restart}`."
        ),
        "restart_command": restart,
    }


def stage_directory(repo_root: Path, graph: Graph) -> Path:
    """
    @brief      Return the run-local working-form directory for the current stage.
    @param[in]  repo_root Repository root.
    @param[in]  graph Active workflow graph.
    @return     `.agentic/runs/<run-id>/stages/<stage>`.
    """
    return run_dir(repo_root, graph.run_id) / "stages" / graph.stage


@serialized_graph_mutation
def prepare_stage(
    repo_root: Path,
    graph: Graph,
    config: WorkflowConfig,
) -> Path:
    """
    @brief      Generate or rehydrate the current stage form.
    @param[in]  repo_root Repository root.
    @param[in,out] graph Active workflow graph.
    @param[in]  config Validated workspace policy.
    @return     Primary working artifact path.
    @exception  StageOperationError If the run is already complete.
    @details    Interface policy is captured only when a new prepared revision
                is created. Repeated calls for an unimported revision preserve
                that captured policy.
    """
    run_stage_spec(graph)
    if graph.complete:
        raise StageOperationError("run is complete; no stage can be prepared")
    current = graph.stage_records.get(graph.stage)
    directory = stage_directory(repo_root, graph)
    primary = _primary_form(directory, graph.stage)
    if current and current.status == "prepared" and primary.is_file():
        return _artifact_path(repo_root, graph, directory, primary)

    record = _prepare_stage_record(
        repo_root,
        graph,
        config,
        current,
        directory,
    )
    graph.stage_records[graph.stage] = record

    primary = _write_prepared_stage_forms(repo_root, graph, record, directory)
    record.artifact = primary.relative_to(repo_root).as_posix()
    save_graph(repo_root, graph)
    append_journal(
        repo_root,
        graph.run_id,
        "stage.prepared",
        {
            "stage": graph.stage,
            "revision": record.revision,
            "retention": record.retention,
            "check_execution": record.check_execution,
            "artifact": record.artifact,
        },
    )
    return _artifact_path(repo_root, graph, directory, primary)


@serialized_graph_mutation
def add_stage_item(repo_root: Path, graph: Graph) -> Path:
    """
    @brief      Generate another CLI-identified requirement or check form.
    @param[in]  repo_root Repository root.
    @param[in,out] graph Active workflow graph.
    @return     Newly generated item form.
    @exception  StageOperationError If the stage is not a requirement/check
                collection stage, is not yet prepared, or the next numbered
                form path already exists.
    """
    run_stage_spec(graph)
    if graph.stage not in COLLECTION_STAGES:
        raise StageOperationError(
            "stage add is valid only during requirement or check"
        )
    record = graph.stage_records.get(graph.stage)
    if not record or record.status != "prepared":
        raise StageOperationError("run `aegis stage prepare` before stage add")
    directory = stage_directory(repo_root, graph)
    existing = sorted(directory.glob(f"{graph.stage}-*.toml"))
    numbers = [
        int(item.stem.rsplit("-", 1)[-1])
        for item in existing
        if item.stem.rsplit("-", 1)[-1].isdigit()
    ]
    number = max(numbers, default=0) + 1
    path = directory / f"{graph.stage}-{number:03d}.toml"
    if path.exists():
        raise StageOperationError(
            f"refusing to overwrite existing form {path.name}"
        )
    if graph.stage == "requirement":
        requirement_id = _new_requirement_id("functional")
        spec_path = (
            run_dir(repo_root, graph.run_id)
            / "requirements"
            / f"{requirement_id}.md"
        )
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        if not spec_path.exists():
            spec_path.write_text(
                _companion_spec_template(requirement_id),
                encoding="utf-8",
            )
        path.write_text(
            _requirement_form(
                graph,
                record,
                requirement_id,
                spec_path.relative_to(repo_root).as_posix(),
            ),
            encoding="utf-8",
        )
    else:
        path.write_text(
            _check_form(graph, record, f"CHK-{uuid.uuid4()}"),
            encoding="utf-8",
        )
    append_journal(
        repo_root,
        graph.run_id,
        "stage.item.generated",
        {"stage": graph.stage, "path": path.relative_to(repo_root).as_posix()},
    )
    return path


def show_stage(repo_root: Path, graph: Graph) -> dict[str, Any]:
    """
    @brief      Report current form files, imported revision, and blockers.
    @param[in]  repo_root Repository root.
    @param[in]  graph Active workflow graph.
    @return     Stable JSON-compatible stage status.
    @exception  StageOperationError If the graph conflicts with its run profile.
    """
    run_stage_spec(graph)
    directory = stage_directory(repo_root, graph)
    record = graph.stage_records.get(graph.stage)
    files = (
        [
            path.relative_to(repo_root).as_posix()
            for path in sorted(directory.rglob("*"))
            if path.is_file()
        ]
        if directory.exists()
        else []
    )
    blockers = stage_blockers(repo_root, graph)
    waived_blockers = [
        blocker_to_dict(blocker, graph)
        for blocker in stage_blocker_details(repo_root, graph)
        if active_waiver(graph, blocker) is not None
    ]
    warnings: list[str] = []
    if graph.stage == "repo-discovery":
        inspection = inspect_repowise(repo_root)
        if inspection.mode == "advisory":
            warnings.extend(inspection.warnings)
    shown = {
        "run_id": graph.run_id,
        "stage": graph.stage,
        "revision": record.revision if record else 0,
        "imported_revision": (
            record.revision if record and record.status in {"applied", "closed"} else 0
        ),
        "state": record.status if record else "not-prepared",
        "files": files,
        "ready": not blockers,
        "blockers": blockers,
        "warnings": sorted(set(warnings)),
        "artifact": record.artifact if record else "",
    }
    if waived_blockers:
        shown["waived_blockers"] = waived_blockers
    return shown


@serialized_graph_mutation
def apply_stage(
    repo_root: Path,
    graph: Graph,
    config: WorkflowConfig,
) -> StageRecord:
    """
    @brief      Validate and atomically import all current-stage forms.
    @param[in]  repo_root Repository root.
    @param[in,out] graph Active workflow graph.
    @param[in]  config Validated workspace configuration.
    @return     Updated authoritative stage record.
    @exception  StageOperationError If forms are absent, stale, or invalid.
    """
    run_stage_spec(graph)
    record = graph.stage_records.get(graph.stage)
    if not record or record.status != "prepared":
        raise StageOperationError("run `aegis stage prepare` before stage apply")
    directory = stage_directory(repo_root, graph)
    if not directory.is_dir():
        raise StageOperationError("prepared stage directory is missing")

    payload: dict[str, Any]
    if graph.stage == "requirement":
        control = _load_control(directory / "stage.toml", graph, record)
        payload = _apply_requirements(repo_root, graph, config, directory, record)
    elif graph.stage == "check":
        control = _load_control(directory / "stage.toml", graph, record)
        payload = _apply_checks(graph, directory, record)
    else:
        form_path = _primary_form(directory, graph.stage)
        payload = _load_single_stage_form(form_path, graph, record)
        _import_single_stage(repo_root, graph, config, payload)
        control = payload["control"]

    _validate_control(graph, control)
    payload["control"] = control
    digest = _stage_digest(directory)
    record.status = "applied"
    record.digest = digest
    record.summary = control["summary"]
    record.unresolved_questions = control["unresolved_questions"]
    record.requested_access_mode = control["requested_access_mode"]
    record.access_rationale = control["access_rationale"]
    record.route_to = control["route_to"]
    record.route_rationale = control["route_rationale"]
    record.payload = payload
    record.applied_at = now_iso()
    save_graph(repo_root, graph)
    append_journal(
        repo_root,
        graph.run_id,
        "stage.applied",
        {
            "stage": graph.stage,
            "revision": record.revision,
            "digest": record.digest,
        },
    )
    _apply_retention(repo_root, graph, record, directory)
    return record


@serialized_graph_mutation
def close_stage(
    repo_root: Path,
    graph: Graph,
    config: WorkflowConfig,
) -> tuple[Graph, Path | None]:
    """
    @brief      Journal human approval, close the stage, and prepare its successor.
    @param[in]  repo_root Repository root.
    @param[in,out] graph Active workflow graph.
    @param[in]  config Current workspace configuration.
    @return     Updated graph and next prepared artifact, or `None` on completion.
    @exception  StageOperationError If the stage has not been applied yet or
                authoritative readiness blockers remain.
    @note       Invoking this command is the explicit human approval action.
    """
    run_stage_spec(graph)
    record = graph.stage_records.get(graph.stage)
    if not record or record.status != "applied":
        raise StageOperationError("run `aegis stage apply` before stage close")
    blockers = stage_blockers(repo_root, graph)
    if blockers:
        raise StageOperationError("; ".join(blockers))
    closing_stage, deferred_events = _approve_stage(
        repo_root,
        graph,
        config,
        record,
    )
    if _advance_stage(repo_root, graph, record, closing_stage):
        return graph, None
    if deferred_events:
        save_graph_with_journal_events(repo_root, graph, deferred_events)
    else:
        save_graph(repo_root, graph)
    return graph, prepare_stage(repo_root, graph, config)


def stage_blockers(repo_root: Path, graph: Graph) -> list[str]:
    """
    @brief      Evaluate lifecycle and stage-specific readiness blockers.
    @param[in]  repo_root Repository root.
    @param[in]  graph Active workflow graph.
    @return     Deterministically ordered actionable blocker text.
    @exception  StageOperationError If the graph conflicts with its run profile.
    """
    run_stage_spec(graph)
    record = graph.stage_records.get(graph.stage)
    if not record:
        return ["stage is not prepared; run `aegis stage prepare`"]
    if record.status == "prepared":
        return ["stage forms are not imported; run `aegis stage apply`"]
    descriptions = _stage_readiness_descriptions(repo_root, graph, record)
    if record.status != "applied":
        return descriptions
    details = {
        blocker.description: blocker
        for blocker in _stage_blocker_details(
            repo_root,
            graph,
            record,
            descriptions,
        )
    }
    return [
        description
        for description in descriptions
        if description not in details
        or active_waiver(graph, details[description]) is None
    ]


def stage_blocker_details(repo_root: Path, graph: Graph) -> list[Blocker]:
    """
    @brief      Return exact waiver targets for applied-stage readiness failures.
    @param[in]  repo_root Repository root.
    @param[in]  graph Active workflow graph.
    @return     Deterministically ordered structured, human-waivable blockers.
    @exception  StageOperationError If the graph conflicts with its run profile.
    @note       Lifecycle guidance and structural integrity failures are omitted.
    """
    run_stage_spec(graph)
    record = graph.stage_records.get(graph.stage)
    if not record or record.status != "applied":
        return []
    return _stage_blocker_details(
        repo_root,
        graph,
        record,
        _stage_readiness_descriptions(repo_root, graph, record),
    )


def next_command(graph: Graph, repo_root: Path | None = None) -> str:
    """
    @brief      Return the exact next lifecycle command for a graph.
    @param[in]  graph Active workflow graph.
    @param[in]  repo_root Optional repository root for waiver-aware readiness.
    @return     One command without explanatory prose.
    @exception  StageOperationError If the graph conflicts with its run profile.
    """
    run_stage_spec(graph)
    if graph.complete:
        return "none"
    record = graph.stage_records.get(graph.stage)
    if not record:
        return "aegis stage prepare"
    if record.status == "prepared":
        if (
            graph.profile == "quick"
            and graph.stage == "implementation"
            and not any(
                item.status == "active" and item.stage == "implementation"
                for item in graph.evidence
            )
        ):
            return "aegis evidence prepare add"
        return "aegis stage apply"
    if record.status == "applied":
        if repo_root is not None and not stage_blockers(repo_root, graph):
            return "aegis stage close"
        if graph.profile == "quick" and graph.stage == "implementation":
            linked = record.payload.get("linked_check_evidence")
            active_ids = {
                item.id
                for item in graph.evidence
                if item.status == "active" and item.stage == "implementation"
            }
            if (
                not isinstance(linked, list)
                or not linked
                or any(item not in active_ids for item in linked)
            ):
                return "aegis evidence prepare add"
        elif graph.stage in {"check", "implementation"}:
            if graph.stage == "check":
                missing_evidence = any(
                    not _has_check_evidence(graph, check.id, "fail")
                    for check in graph.checks
                )
            else:
                missing_evidence = any(
                    not _has_check_evidence(graph, check.id, "fail")
                    or not _has_check_evidence(graph, check.id, "pass")
                    for check in graph.checks
                )
            if missing_evidence:
                return (
                    "aegis check prepare"
                    if record.check_execution == "external"
                    else "aegis check run"
                )
        if (
            graph.stage == "validation"
            and not record.payload.get("deterministic_verification")
        ):
            return "aegis verify run"
        return "aegis stage close"
    return "aegis stage prepare"


# LOCAL HELPERS


def _stage_readiness_descriptions(
    repo_root: Path,
    graph: Graph,
    record: StageRecord,
) -> list[str]:
    """
    @brief Collect deterministic applied-record readiness descriptions.
    @return Existing human-facing blocker text in stable order.
    """
    descriptions = list(record.unresolved_questions)
    descriptions.extend(_standard_stage_blockers(repo_root, graph, record))
    descriptions.extend(_evidence_stage_blockers(graph, record))
    descriptions.extend(_adoption_stage_blockers(repo_root, graph, record))
    return sorted(set(descriptions))


def _stage_blocker_details(
    repo_root: Path,
    graph: Graph,
    record: StageRecord,
    descriptions: list[str],
) -> list[Blocker]:
    """
    @brief Convert readiness text into exact digest-pinned waiver targets.
    @return Waivable blockers in the same deterministic order as descriptions.
    """
    specific: dict[str, Blocker] = {}
    generic_ids: dict[str, str] = {}
    for description in descriptions:
        if _is_non_waivable_stage_blocker(repo_root, graph, description):
            continue
        blocker = _specific_stage_blocker(graph, record, description)
        if blocker is not None:
            specific[description] = blocker
            continue
        generic_ids[description] = _generic_stage_blocker_id(
            graph.stage,
            description,
        )

    id_counts: dict[str, int] = {}
    for blocker_id in generic_ids.values():
        id_counts[blocker_id] = id_counts.get(blocker_id, 0) + 1

    blockers: list[Blocker] = []
    for description in descriptions:
        if description in specific:
            blockers.append(specific[description])
            continue
        blocker_id = generic_ids.get(description)
        if blocker_id is None:
            continue
        if id_counts[blocker_id] > 1:
            blocker_id = (
                f"{blocker_id}-{sha256(description.encode('utf-8')).hexdigest()[:8]}"
            )
        blockers.append(
            Blocker(
                id=blocker_id,
                description=description,
                state_digests=_stage_blocker_state_digests(
                    repo_root,
                    graph,
                    record,
                    description,
                ),
            )
        )
    return blockers


def _specific_stage_blocker(
    graph: Graph,
    record: StageRecord,
    description: str,
) -> Blocker | None:
    """
    @brief Build shared red-before-green or exact green-evidence blockers.
    @return A specialized blocker, or ``None`` for generic stage readiness.
    """
    for check in graph.checks:
        if description in {
            f"{check.id} has no active red evidence",
            f"{check.id} is missing prior red evidence",
        }:
            return red_before_green_blocker(
                graph,
                check.id,
                description,
            )
        if description == f"{check.id} has no active green evidence":
            return Blocker(
                id=f"stage:implementation:{check.id}:green-evidence",
                description=description,
                state_digests=state_digests(
                    "stage:implementation",
                    {
                        "revision": record.revision,
                        "digest": record.digest,
                        "description": description,
                    },
                ),
            )
    return None


def _stage_blocker_state_digests(
    repo_root: Path,
    graph: Graph,
    record: StageRecord,
    description: str,
) -> dict[str, str]:
    """
    @brief Pin a generic blocker to its applied stage and durable drift state.
    @return Namespace-to-digest mapping used for exact waiver matching.
    """
    digests = state_digests(
        f"stage:{graph.stage}",
        {
            "revision": record.revision,
            "digest": record.digest,
            "description": description,
        },
    )
    if graph.stage != "design" or graph.design is None:
        return digests

    design = graph.design
    if description == "design.md changed after stage apply":
        digests["design:document"] = current_file_digest(
            repo_root / design.document_path
        )
        return digests

    suffix = " changed after design apply"
    if not description.endswith(suffix):
        return digests
    requirement_id = description.removesuffix(suffix)
    if requirement_id not in design.requirement_digests:
        return digests
    try:
        config = load_config(repo_root)
        requirement = find_requirement_record(repo_root, requirement_id, config)
    except (OSError, ValueError):
        return digests
    digests[f"design:requirement:{requirement_id}"] = current_file_digest(
        repo_root / str(requirement.source_file)
    )
    return digests


def _generic_stage_blocker_id(stage: Stage, description: str) -> str:
    """
    @brief Mint a stable exact stage-blocker ID from readable readiness text.
    @return ``stage:<stage>:<readable-slug>`` with a hash only when needed.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", description.casefold()).strip("-")
    short_hash = sha256(description.encode("utf-8")).hexdigest()[:8]
    if not slug:
        slug = f"blocker-{short_hash}"
    elif len(slug) > BLOCKER_SLUG_LIMIT:
        prefix = slug[: BLOCKER_SLUG_LIMIT - len(short_hash) - 1].rstrip("-")
        slug = f"{prefix}-{short_hash}"
    return f"stage:{stage}:{slug}"


def _is_non_waivable_stage_blocker(
    repo_root: Path,
    graph: Graph,
    description: str,
) -> bool:
    """
    @brief Identify structural integrity failures outside process waivers.
    @return True for design or required-integration schema corruption.
    """
    if description.startswith(
        "cited requirement integrity cannot be verified:"
    ):
        return True
    if (
        graph.stage == "repo-discovery"
        and description.startswith(
            "required RepoWise discovery is not current:"
        )
    ):
        inspection = inspect_repowise(repo_root)
        return (
            inspection.mode == "required"
            and inspection.status == "invalid"
        )
    return False


def _prepare_stage_record(
    repo_root: Path,
    graph: Graph,
    config: WorkflowConfig,
    current: StageRecord | None,
    directory: Path,
) -> StageRecord:
    """
    @brief Create a prepared record while preserving imported payload state.
    """
    revision = (current.revision + 1) if current else 1
    if directory.exists():
        for path in directory.iterdir():
            if path.name != "revisions" and path.is_file():
                path.unlink()
    directory.mkdir(parents=True, exist_ok=True)
    record = StageRecord(
        stage=graph.stage,
        revision=revision,
        status="prepared",
        retention=config.interface.stage_form_retention,
        check_execution=config.interface.check_execution,
        artifact="",
        payload=copy.deepcopy(current.payload) if current and current.payload else {},
    )
    if graph.stage == "repo-discovery":
        if not record.payload:
            record.payload = {
                "source_roots": list(config.source_roots),
                "test_roots": list(config.test_roots),
                "requirement_roots": list(config.requirement_roots),
                "documentation_roots": list(config.documentation_roots),
                "gate_commands": [
                    f"{name}: {command}"
                    for name in GATE_ORDER
                    for command in getattr(config.gates, name).commands
                ],
            }
        _merge_repowise_discovery(repo_root, graph, record)
    return record


def _write_prepared_stage_forms(
    repo_root: Path,
    graph: Graph,
    record: StageRecord,
    directory: Path,
) -> Path:
    """
    @brief Write or rehydrate the form set for one prepared stage.
    """
    if graph.stage == "requirement":
        _write_control_form(directory / "stage.toml", graph, record)
        return _rehydrate_requirement_forms(repo_root, graph, record)
    if graph.stage == "check":
        _write_control_form(directory / "stage.toml", graph, record)
        return _rehydrate_check_forms(repo_root, graph, record)
    return _write_single_stage_form(repo_root, graph, record)


def _approve_stage(
    repo_root: Path,
    graph: Graph,
    config: WorkflowConfig,
    record: StageRecord,
) -> tuple[Stage, list[tuple[str, dict[str, Any]]]]:
    """
    @brief Apply approval-side mutations and journal the approval.
    @return Closing stage and any events deferred for graph-coupled publication.
    """
    closing_stage = graph.stage
    spec = run_stage_spec(graph)
    defer_events = closing_stage == "intake" and bool(spec.bypassed_stages)
    journal_events: list[tuple[str, dict[str, Any]]] = []
    record.status = "closed"
    record.closed_at = now_iso()
    if record.requested_access_mode:
        if defer_events:
            graph.access_mode = record.requested_access_mode  # type: ignore[assignment]
            journal_events.append(
                (
                    "access_mode.set",
                    {
                        "access_mode": record.requested_access_mode,
                        "reason": record.access_rationale,
                    },
                )
            )
        else:
            set_access_mode(
                repo_root,
                graph,
                record.requested_access_mode,  # type: ignore[arg-type]
                record.access_rationale,
            )
    if closing_stage == "design" and graph.design:
        graph.design.status = "approved"
        graph.design.approval = "human"
        graph.design.approved_at = now_iso()
    if closing_stage == "validation" and graph.profile != "quick":
        _activate_green_requirements(repo_root, graph, config)
    approval_data = {
        "stage": closing_stage,
        "revision": record.revision,
        "approver": "human",
    }
    if defer_events:
        journal_events.append(("stage.approved", approval_data))
    else:
        append_journal(
            repo_root,
            graph.run_id,
            "stage.approved",
            approval_data,
        )
    if (
        closing_stage == "intake"
        and spec.bypassed_stages
        and not any(stage in graph.stage_records for stage in spec.stages[1:])
    ):
        journal_events.append(
            (
                "run.stages_bypassed",
                {
                    "profile": graph.profile,
                    "status": "bypassed",
                    "stages": list(spec.bypassed_stages),
                    "reason": "quick run type",
                    "approver": "human",
                    "intake_revision": record.revision,
                },
            )
        )
    return closing_stage, journal_events


def _advance_stage(
    repo_root: Path,
    graph: Graph,
    record: StageRecord,
    closing_stage: Stage,
) -> bool:
    """
    @brief Apply routing or advance to the next configured lifecycle stage.
    @return True when the run completed.
    """
    route = record.route_to
    if route:
        graph.stage = route  # type: ignore[assignment]
        if graph.design and _standard_index(route) <= _standard_index("design"):
            graph.design.status = "stale"
            graph.design.approval = "stale"
        append_journal(
            repo_root,
            graph.run_id,
            "stage.routed",
            {
                "from": closing_stage,
                "to": route,
                "reason": record.route_rationale,
            },
        )
        return False
    stages = run_stage_spec(graph).stages
    position = stages.index(closing_stage)
    if position < len(stages) - 1:
        graph.stage = stages[position + 1]
        return False
    graph.complete = True
    save_graph(repo_root, graph)
    append_journal(
        repo_root,
        graph.run_id,
        "run.completed",
        {"stage": closing_stage, "outward_action": "none"},
    )
    return True


def _standard_stage_blockers(
    repo_root: Path,
    graph: Graph,
    record: StageRecord,
) -> list[str]:
    """
    @brief Return non-evidence blockers for standard workflow stages.
    """
    blockers: list[str] = []
    if graph.stage == "intake" and not graph.intent.statement.strip():
        blockers.append("intake statement is empty")
    if graph.stage == "alignment":
        if not graph.alignment:
            blockers.append("alignment is not imported")
        elif graph.alignment.decision != "proceed":
            blockers.append("alignment decision is not proceed")
    if graph.stage == "requirement" and not record.payload.get("requirements"):
        blockers.append("at least one atomic requirement is required")
    if graph.stage == "design":
        blockers.extend(_design_blockers(repo_root, graph))
    if graph.stage in {"delivery", "adoption-delivery"}:
        if record.payload.get("decision") != "approved":
            blockers.append("final human handoff decision is not approved")
    return blockers


def _evidence_stage_blockers(
    graph: Graph,
    record: StageRecord,
) -> list[str]:
    """
    @brief Return check, implementation, and validation evidence blockers.
    """
    blockers: list[str] = []
    if graph.stage == "check":
        if not graph.checks:
            blockers.append("at least one deterministic check is required")
        for check in graph.checks:
            if not _has_check_evidence(graph, check.id, "fail"):
                blockers.append(f"{check.id} has no active red evidence")
    if graph.stage == "implementation":
        if graph.profile == "quick":
            linked = record.payload.get("linked_check_evidence")
            linked_ids = (
                linked
                if isinstance(linked, list)
                and all(isinstance(item, str) and item for item in linked)
                else []
            )
            if not linked_ids:
                blockers.append(
                    "quick implementation requires linked active evidence"
                )
            active_ids = {
                item.id
                for item in graph.evidence
                if item.status == "active" and item.stage == "implementation"
            }
            for evidence_id in linked_ids:
                if evidence_id not in active_ids:
                    blockers.append(
                        f"{evidence_id} is not active implementation evidence"
                    )
        else:
            for check in graph.checks:
                if not _has_check_evidence(graph, check.id, "fail"):
                    blockers.append(f"{check.id} is missing prior red evidence")
                if not _has_check_evidence(graph, check.id, "pass"):
                    blockers.append(f"{check.id} has no active green evidence")
    if graph.stage == "validation":
        if not record.payload.get("deterministic_verification"):
            blockers.append("deterministic verification references are required")
        for key in ("diff_review", "documentation_review", "style_review"):
            if record.payload.get(key) not in {"pass", "not-applicable"}:
                blockers.append(f"{key.replace('_', ' ')} is not complete")
    return blockers


def _adoption_stage_blockers(
    repo_root: Path,
    graph: Graph,
    record: StageRecord,
) -> list[str]:
    """
    @brief Return readiness blockers specific to adoption workflow stages.
    """
    blockers: list[str] = []
    data = record.payload
    if graph.stage == "adoption-intake":
        if not graph.intent.statement.strip():
            blockers.append("adoption statement is empty")
        if not data.get("adoption_slice"):
            blockers.append("adoption slice is empty")
    if graph.stage == "adoption-alignment":
        if not graph.alignment:
            blockers.append("adoption alignment is not imported")
        elif graph.alignment.decision != "proceed":
            blockers.append("adoption alignment decision is not proceed")
    if graph.stage == "repo-discovery":
        if not data.get("candidate_components"):
            blockers.append("repository discovery has no candidate components")
        inspection = inspect_repowise(repo_root)
        if inspection.mode == "required" and not inspection.current:
            detail = "; ".join(inspection.warnings) or inspection.status
            blockers.append(f"required RepoWise discovery is not current: {detail}")
    if graph.stage == "component-map":
        if not data.get("components"):
            blockers.append("component map has no components")
        if not data.get("approved_slice"):
            blockers.append("component map has no approved adoption slice")
        if data.get("approval_decision") != "approved":
            blockers.append("component map approval decision is not approved")
    if graph.stage == "component-adoption":
        if not data.get("adopted_components"):
            blockers.append("no components were adopted")
        if data.get("behavior_changed"):
            blockers.append("adoption cannot include runtime behavior changes")
    if graph.stage == "baseline-review":
        if not data.get("reviewed_components"):
            blockers.append("baseline review has no reviewed components")
        if data.get("blocking_gaps"):
            blockers.append("baseline review has blocking gaps")
        if data.get("decision") != "approved":
            blockers.append("baseline review decision is not approved")
    return blockers


def _write_single_stage_form(
    repo_root: Path,
    graph: Graph,
    record: StageRecord,
) -> Path:
    """@brief Generate one stage-specific form and any durable Markdown."""
    directory = stage_directory(repo_root, graph)
    path = _primary_form(directory, graph.stage)
    values = _rehydrated_values(graph, record)
    if graph.stage == "design":
        design_path = run_dir(repo_root, graph.run_id) / "design.md"
        if not design_path.exists():
            design_path.write_text(_design_template(graph), encoding="utf-8")
        values["document"] = design_path.relative_to(repo_root).as_posix()
    path.write_text(
        _single_form_text(graph, record, values),
        encoding="utf-8",
    )
    return path


def _primary_form(directory: Path, stage: str) -> Path:
    """@brief Return the primary TOML path for one stage directory."""
    return directory / ("stage.toml" if stage in COLLECTION_STAGES else f"{stage}.toml")


def _artifact_path(
    repo_root: Path,
    graph: Graph,
    directory: Path,
    primary: Path,
) -> Path:
    """@brief Prefer the authoritative design document as its active artifact."""
    if graph.stage == "design":
        return run_dir(repo_root, graph.run_id) / "design.md"
    return primary


def _base_lines(graph: Graph, record: StageRecord) -> list[str]:
    """@brief Render strict shared schema and identity keys."""
    return [
        f"schema_version = {FORM_SCHEMA_VERSION}",
        f"run_id = {_q(graph.run_id)}",
        f"stage = {_q(graph.stage)}",
        f"revision = {record.revision}",
    ]


def _control_lines(values: dict[str, Any] | None = None) -> list[str]:
    """@brief Render the common control table for every stage form."""
    data = {
        "requested_access_mode": "",
        "access_rationale": "",
        "route_to": "",
        "route_rationale": "",
        "summary": "",
        "unresolved_questions": [],
        **(values or {}),
    }
    return [
        "",
        "[control]",
        f"requested_access_mode = {_q(data['requested_access_mode'])}",
        f"access_rationale = {_q(data['access_rationale'])}",
        f"route_to = {_q(data['route_to'])}",
        f"route_rationale = {_q(data['route_rationale'])}",
        f"summary = {_q(data['summary'])}",
        f"unresolved_questions = {_array(data['unresolved_questions'])}",
    ]


def _write_control_form(path: Path, graph: Graph, record: StageRecord) -> None:
    """@brief Write the collection-stage control form."""
    values = record.payload.get("control", {}) if record.payload else {}
    path.write_text(
        "\n".join([*_base_lines(graph, record), *_control_lines(values)]) + "\n",
        encoding="utf-8",
    )


def _rehydrate_requirement_forms(
    repo_root: Path,
    graph: Graph,
    record: StageRecord,
) -> Path:
    """
    @brief Reconstruct requirement forms from authoritative imported snapshots.
    @return First reconstructed form, or a newly generated empty form.
    """
    snapshots = record.payload.get("requirements", [])
    if not snapshots:
        return add_stage_item(repo_root, graph)
    directory = stage_directory(repo_root, graph)
    first: Path | None = None
    for number, snapshot in enumerate(snapshots, start=1):
        if not isinstance(snapshot, dict):
            raise StageOperationError(
                "authoritative requirement payload is not reconstructable"
            )
        path = directory / f"requirement-{number:03d}.toml"
        path.write_text(
            _requirement_form_from_snapshot(graph, record, snapshot),
            encoding="utf-8",
        )
        first = first or path
    if first is None:
        raise StageOperationError("authoritative requirement payload is empty")
    return first


def _rehydrate_check_forms(
    repo_root: Path,
    graph: Graph,
    record: StageRecord,
) -> Path:
    """
    @brief Reconstruct check forms from authoritative graph records.
    @return First reconstructed form, or a newly generated empty form.
    """
    if not graph.checks:
        return add_stage_item(repo_root, graph)
    directory = stage_directory(repo_root, graph)
    first: Path | None = None
    for number, check in enumerate(graph.checks, start=1):
        path = directory / f"check-{number:03d}.toml"
        path.write_text(
            _check_form_from_record(graph, record, check),
            encoding="utf-8",
        )
        first = first or path
    if first is None:
        raise StageOperationError("authoritative check payload is empty")
    return first


def _requirement_form(
    graph: Graph,
    record: StageRecord,
    requirement_id: str,
    spec_ref: str,
) -> str:
    """@brief Render one atomic requirement input form."""
    lines = [
        *_base_lines(graph, record),
        f"id = {_q(requirement_id)}",
        'category = "functional"',
        'priority = "Must"',
        'requirement = ""',
        'rationale = ""',
        'verification = ""',
        f"spec_ref = {_q(spec_ref)}",
        "affected_paths = []",
        "linked_tests = []",
    ]
    return "\n".join(lines) + "\n"


def _requirement_form_from_snapshot(
    graph: Graph,
    record: StageRecord,
    snapshot: dict[str, Any],
) -> str:
    """
    @brief Render one editable requirement form from an imported snapshot.
    """
    required = (
        "id",
        "category",
        "priority",
        "requirement",
        "rationale",
        "verification",
        "spec_ref",
        "affected_paths",
        "linked_tests",
    )
    if any(key not in snapshot for key in required):
        raise StageOperationError(
            "authoritative requirement payload is missing reconstruction fields"
        )
    return (
        "\n".join(
            [
                *_base_lines(graph, record),
                f"id = {_q(snapshot['id'])}",
                f"category = {_q(snapshot['category'])}",
                f"priority = {_q(snapshot['priority'])}",
                f"requirement = {_q(snapshot['requirement'])}",
                f"rationale = {_q(snapshot['rationale'])}",
                f"verification = {_q(snapshot['verification'])}",
                f"spec_ref = {_q(snapshot['spec_ref'])}",
                f"affected_paths = {_array(snapshot['affected_paths'])}",
                f"linked_tests = {_array(snapshot['linked_tests'])}",
            ]
        )
        + "\n"
    )


def _check_form(graph: Graph, record: StageRecord, check_id: str) -> str:
    """@brief Render one deterministic check input form."""
    return (
        "\n".join(
            [
                *_base_lines(graph, record),
                f"id = {_q(check_id)}",
                'level = "test"',
                "cites_requirement = []",
                "cites_spec = []",
                'command = ""',
                'path = ""',
                "contract_variants = []",
                "concerns = []",
                "parity_targets = []",
            ]
        )
        + "\n"
    )


def _check_form_from_record(
    graph: Graph,
    record: StageRecord,
    check: Check,
) -> str:
    """
    @brief Render one editable check form from an authoritative check.
    """
    return (
        "\n".join(
            [
                *_base_lines(graph, record),
                f"id = {_q(check.id)}",
                f"level = {_q(check.level)}",
                f"cites_requirement = {_array(check.cites_requirement)}",
                f"cites_spec = {_array(check.cites_spec)}",
                f"command = {_q(check.command)}",
                f"path = {_q(check.path or '')}",
                f"contract_variants = {_array(check.contract_variants)}",
                f"concerns = {_array(check.concerns)}",
                f"parity_targets = {_array(check.parity_targets)}",
            ]
        )
        + "\n"
    )


def _single_form_text(
    graph: Graph,
    record: StageRecord,
    values: dict[str, Any],
) -> str:
    """
    @brief Render the current single-artifact stage form from its field schema.
    """
    lines = _base_lines(graph, record)
    for field in _stage_field_specs(graph.stage):
        default = _stage_field_default(field, graph)
        value = values[field.name] if default is REQUIRED_STAGE_VALUE else values.get(
            field.name,
            default,
        )
        lines.append(f"{field.name} = {_render_stage_field(field, value)}")
    lines.extend(_control_lines(values.get("control", {})))
    return "\n".join(lines) + "\n"


def _load_control(path: Path, graph: Graph, record: StageRecord) -> dict[str, Any]:
    """@brief Parse and validate a collection-stage control form."""
    data = _load_toml(path)
    _closed_keys(
        data,
        ("schema_version", "run_id", "stage", "revision", "control"),
        path,
    )
    _validate_identity(data, graph, record, path)
    return _control(data.get("control"), path)


def _load_single_stage_form(
    path: Path,
    graph: Graph,
    record: StageRecord,
) -> dict[str, Any]:
    """
    @brief Parse one strict stage-specific TOML form from its field schema.
    """
    data = _load_toml(path)
    fields = _stage_field_specs(graph.stage)
    stage_keys = tuple(field.name for field in fields)
    expected = (
        "schema_version",
        "run_id",
        "stage",
        "revision",
        *stage_keys,
        "control",
    )
    _closed_keys(data, expected, path)
    _validate_identity(data, graph, record, path)
    # Every schema field is required; optionality would need support in the
    # value validator too, so the schema deliberately has no per-field flag.
    for field in fields:
        if field.name not in data:
            raise StageOperationError(
                f"{path}: missing required key {field.name}"
            )
    _validate_stage_values(data, graph.stage, path)
    data["control"] = _control(data.get("control"), path)
    return data


def _apply_requirements(
    repo_root: Path,
    graph: Graph,
    config: WorkflowConfig,
    directory: Path,
    record: StageRecord,
) -> dict[str, Any]:
    """@brief Validate all requirement forms before durable publication."""
    forms = sorted(directory.glob("requirement-*.toml"))
    if not forms:
        raise StageOperationError("requirement stage has no item forms")
    timestamp = utc_timestamp()
    records: list[RequirementRecord] = []
    for path in forms:
        data = _load_toml(path)
        _closed_keys(data, REQUIREMENT_FORM_KEYS, path)
        _validate_identity(data, graph, record, path)
        for key in REQUIREMENT_FORM_KEYS:
            if key not in data:
                raise StageOperationError(f"{path}: missing required key {key}")
        spec_path = repo_root / _string(data, "spec_ref", path)
        if not spec_path.is_file():
            raise StageOperationError(f"{path}: companion specification is missing")
        records.append(
            RequirementRecord(
                schema_version=1,
                id=_string(data, "id", path),
                category=_string(data, "category", path),
                status="Planned",
                priority=_string(data, "priority", path),
                requirement=_nonempty(data, "requirement", path),
                rationale=_nonempty(data, "rationale", path),
                verification=_nonempty(data, "verification", path),
                spec_ref=_string(data, "spec_ref", path),
                affected_paths=tuple(_strings(data, "affected_paths", path)),
                linked_tests=tuple(_strings(data, "linked_tests", path)),
                created_on=timestamp,
                last_updated=timestamp,
            )
        )
    imported = publish_requirement_records(repo_root, records, config)
    return {"requirements": [item.to_dict() for item in imported]}


def _apply_checks(
    graph: Graph,
    directory: Path,
    record: StageRecord,
) -> dict[str, Any]:
    """@brief Validate a complete check collection before updating the graph."""
    forms = sorted(directory.glob("check-*.toml"))
    if not forms:
        raise StageOperationError("check stage has no item forms")
    checks: list[Check] = []
    seen: set[str] = set()
    for path in forms:
        data = _load_toml(path)
        _closed_keys(data, CHECK_FORM_KEYS, path)
        _validate_identity(data, graph, record, path)
        for key in CHECK_FORM_KEYS:
            if key not in data:
                raise StageOperationError(f"{path}: missing required key {key}")
        check_id = _nonempty(data, "id", path)
        if check_id in seen:
            raise StageOperationError(f"{path}: duplicate check ID {check_id}")
        seen.add(check_id)
        cites = _strings(data, "cites_requirement", path)
        if not cites:
            raise StageOperationError(f"{path}: cites_requirement must not be empty")
        command = _nonempty(data, "command", path)
        checks.append(
            Check(
                id=check_id,
                level=_nonempty(data, "level", path),
                cites_spec=_strings(data, "cites_spec", path),
                cites_requirement=cites,
                command=command,
                path=_string(data, "path", path) or None,
                contract_variants=_strings(data, "contract_variants", path),
                concerns=_strings(data, "concerns", path),
                parity_targets=_strings(data, "parity_targets", path),
            )
        )
    # Reapplying the collection must not orphan evidence already recorded for
    # a check whose observable definition is unchanged: a same-id, same-command
    # check keeps its red/green links, re-derived from the active evidence the
    # graph still holds. A changed command means the old evidence no longer
    # proves anything about the new definition, so that check starts unknown.
    previous = {check.id: check for check in graph.checks}
    unchanged = {
        check.id
        for check in checks
        if check.id in previous and previous[check.id].command == check.command
    }
    graph.checks = checks
    relink_check_evidence(graph, unchanged)
    return {"checks": [asdict(item) for item in checks]}


def _import_single_stage(
    repo_root: Path,
    graph: Graph,
    config: WorkflowConfig,
    data: dict[str, Any],
) -> None:
    """
    @brief Import stage-specific authoritative fields into the graph.
    @details Accepted keys and value kinds were validated from STAGE_FIELD_SPECS.
    """
    if graph.stage == "intake":
        _import_intake(graph, data)
    elif graph.stage in {"alignment", "adoption-alignment"}:
        _import_alignment(graph, data)
    elif graph.stage == "adoption-intake":
        _import_adoption_intake(graph, config, data)
    elif graph.stage == "design":
        _import_design(repo_root, graph, config, data)
    elif graph.stage == "implementation":
        _import_implementation(repo_root, graph, data)
    elif graph.stage == "component-adoption":
        _import_component_adoption(repo_root, graph, data)
    elif graph.stage == "component-map":
        _validate_import_decision(
            data,
            "component-map",
            "approval_decision",
            "component-map approval_decision must be pending or approved",
        )
    elif graph.stage == "baseline-review":
        _validate_import_decision(
            data,
            "baseline-review",
            "decision",
            "baseline-review decision must be pending or approved",
        )


def _import_intake(graph: Graph, data: dict[str, Any]) -> None:
    """
    @brief Import the standard intake form.
    """
    path = Path("intake.toml")
    graph.intent.statement = _nonempty(data, "statement", path)
    graph.intent.scope_hint = _strings(data, "scope_hints", path)
    mode = _string(data, "access_mode", path)
    if mode not in {"standard", "repo-wide"}:
        raise StageOperationError(
            "intake access_mode must be standard or repo-wide"
        )
    graph.access_mode = mode  # type: ignore[assignment]
    graph.intent.status = "accepted"


def _import_alignment(graph: Graph, data: dict[str, Any]) -> None:
    """
    @brief Import standard or adoption alignment fields.
    """
    path = Path("alignment.toml")
    understanding = _nonempty(data, "understanding", path)
    in_scope = _strings(data, "in_scope", path)
    acceptance = _strings(data, "acceptance_criteria", path)
    if not in_scope or not acceptance:
        raise StageOperationError(
            "alignment in_scope and acceptance_criteria must not be empty"
        )
    risk = _string(data, "risk", path)
    decision = _string(data, "decision", path)
    if risk not in {"low", "medium", "high"}:
        raise StageOperationError("alignment risk must be low, medium, or high")
    if decision not in {"proceed", "pause"}:
        raise StageOperationError("alignment decision must be proceed or pause")
    graph.alignment = IntentAlignment(
        source="stage-form",
        understanding=understanding,
        scope=[
            *[f"in: {item}" for item in in_scope],
            *[f"out: {item}" for item in _strings(data, "out_of_scope", path)],
        ],
        assumptions=_strings(data, "assumptions", path),
        acceptance=acceptance,
        open_questions=_strings(data, "questions", path),
        recommended_responses=_strings(data, "recommended_answers", path),
        risk=risk,  # type: ignore[arg-type]
        decision=decision,  # type: ignore[arg-type]
        reason=data["control"]["summary"] or "Imported alignment decision.",
        planned_paths=_strings(data, "planned_paths", path),
    )


def _import_adoption_intake(
    graph: Graph,
    config: WorkflowConfig,
    data: dict[str, Any],
) -> None:
    """
    @brief Import adoption scope, bundle, and access fields.
    """
    path = Path("adoption-intake.toml")
    graph.intent.statement = _nonempty(data, "statement", path)
    adoption_slice = _nonempty(data, "adoption_slice", path)
    bundle = _strings(data, "bundle_components", path)
    if len(bundle) > 1:
        if not config.adoption_allow_component_bundles:
            raise StageOperationError(
                "workspace policy does not permit component bundles"
            )
        if len(bundle) > config.adoption_max_bundle_components:
            raise StageOperationError(
                "component bundle exceeds the configured maximum"
            )
        if not _string(data, "bundle_rationale", path):
            raise StageOperationError(
                "bundle_rationale is required for multiple components"
            )
    mode = _string(data, "access_mode", path)
    if mode not in {"standard", "repo-wide"}:
        raise StageOperationError(
            "adoption-intake access_mode must be standard or repo-wide"
        )
    graph.intent.scope_hint = [adoption_slice, *bundle]
    graph.intent.status = "accepted"
    graph.access_mode = mode  # type: ignore[assignment]


def _import_implementation(
    repo_root: Path,
    graph: Graph,
    data: dict[str, Any],
) -> None:
    """
    @brief Import implementation changed paths as one change unit.
    """
    path = Path("implementation.toml")
    changed = _normalized_changed_paths(
        repo_root,
        _strings(data, "changed_paths", path),
    )
    if not changed:
        raise StageOperationError(
            "implementation changed_paths must not be empty"
        )
    linked_evidence = _strings(data, "linked_check_evidence", path)
    if graph.profile == "quick":
        if not linked_evidence:
            raise StageOperationError(
                "quick implementation linked_check_evidence must not be empty"
            )
        if len(set(linked_evidence)) != len(linked_evidence):
            raise StageOperationError(
                "quick implementation linked_check_evidence contains duplicates"
            )
        active_ids = {
            item.id
            for item in graph.evidence
            if item.status == "active" and item.stage == "implementation"
        }
        unknown = sorted(set(linked_evidence) - active_ids)
        if unknown:
            raise StageOperationError(
                "quick implementation evidence must name active evidence "
                f"recorded during implementation: {', '.join(unknown)}"
            )
    graph.change_units = [
        ChangeUnit(
            id=_nonempty(data, "change_unit_id", path),
            touched_paths=changed,
        )
    ]


def _import_component_adoption(
    repo_root: Path,
    graph: Graph,
    data: dict[str, Any],
) -> None:
    """
    @brief Import component-adoption changed paths as one change unit.
    """
    if type(data["behavior_changed"]) is not bool:
        raise StageOperationError(
            "component-adoption behavior_changed must be a boolean"
        )
    graph.change_units = [
        ChangeUnit(
            id=f"CU-{uuid.uuid4()}",
            touched_paths=_normalized_changed_paths(
                repo_root,
                _strings(
                    data,
                    "changed_paths",
                    Path("component-adoption.toml"),
                ),
            ),
        )
    ]


def _validate_import_decision(
    data: dict[str, Any],
    stage: str,
    key: str,
    message: str,
) -> None:
    """
    @brief Validate one imported pending-or-approved decision.
    """
    decision = _string(data, key, Path(f"{stage}.toml"))
    if decision not in {"pending", "approved"}:
        raise StageOperationError(message)


def _normalized_changed_paths(
    repo_root: Path,
    values: list[str],
) -> list[str]:
    """
    @brief Normalize, contain, and de-duplicate stage-recorded changed paths.
    @param[in] repo_root Repository root used as the containment boundary.
    @param[in] values Paths supplied by the current stage form.
    @return Repository-relative paths in first-seen order.
    @exception StageOperationError If a path is outside the repository.
    """
    normalized: list[str] = []
    for value in values:
        try:
            path = relative_to_root(value, repo_root)
        except ValueError as exc:
            raise StageOperationError(
                f"changed path is outside the repository: {value}"
            ) from exc
        if path not in normalized:
            normalized.append(path)
    return normalized


def _import_design(
    repo_root: Path,
    graph: Graph,
    config: WorkflowConfig,
    data: dict[str, Any],
) -> None:
    """@brief Record one design proposal with requirement and document digests."""
    document = _nonempty(data, "document", Path("design.toml"))
    expected = (run_dir(repo_root, graph.run_id) / "design.md").resolve()
    actual = (repo_root / document).resolve()
    if actual != expected or not actual.is_file():
        raise StageOperationError(
            "design document must be the run-local authoritative design.md"
        )
    cited = _strings(data, "cited_requirement_ids", Path("design.toml"))
    if not cited:
        raise StageOperationError("design must cite at least one requirement ID")
    requirement_digests: dict[str, str] = {}
    for requirement_id in cited:
        requirement = find_requirement_record(repo_root, requirement_id, config)
        requirement_digests[requirement_id] = _file_digest(
            repo_root / str(requirement.source_file)
        )
    previous_revision = graph.design.revision if graph.design else 0
    graph.design = SolutionDesign(
        revision=previous_revision + 1,
        status="proposed",
        document_path=document,
        document_digest=_file_digest(actual),
        requirement_digests=requirement_digests,
        selected_option=_string(data, "selected_option", Path("design.toml")),
        open_questions=data["control"]["unresolved_questions"],
    )


def _design_blockers(repo_root: Path, graph: Graph) -> list[str]:
    """@brief Validate authoritative design and cited requirement integrity."""
    if not graph.design:
        return ["solution design is not imported"]
    design = graph.design
    blockers: list[str] = []
    if not design.selected_option.strip():
        blockers.append("design selected_option is empty")
    if design.open_questions:
        blockers.extend(design.open_questions)
    document = repo_root / design.document_path
    if not document.is_file() or _file_digest(document) != design.document_digest:
        blockers.append("design.md changed after stage apply")
    try:
        config = load_config(repo_root)
        for requirement_id, digest in design.requirement_digests.items():
            requirement = find_requirement_record(repo_root, requirement_id, config)
            if _file_digest(repo_root / str(requirement.source_file)) != digest:
                blockers.append(f"{requirement_id} changed after design apply")
    except (OSError, ValueError) as exc:
        blockers.append(f"cited requirement integrity cannot be verified: {exc}")
    return blockers


def _activate_green_requirements(
    repo_root: Path,
    graph: Graph,
    config: WorkflowConfig,
) -> None:
    """
    @brief Activate cited green requirements through serialized stale-safe updates.
    """
    for requirement in load_all_requirement_records(repo_root, config):
        if requirement.status != "Planned":
            continue
        cited = [
            check for check in graph.checks if requirement.id in check.cites_requirement
        ]
        if not cited or any(
            not _has_check_evidence(graph, check.id, "pass") for check in cited
        ):
            continue
        update_requirement(
            repo_root,
            requirement.id,
            config=config,
            patch=RequirementPatch(status="Active", timestamp=utc_timestamp()),
        )
        append_journal(
            repo_root,
            graph.run_id,
            "requirement.activated",
            {"requirement_id": requirement.id, "source": "validation-close"},
        )


def _has_check_evidence(graph: Graph, check_id: str, result: str) -> bool:
    """@brief Return whether active check evidence has the requested result."""
    return any(
        item.status == "active"
        and item.check_id == check_id
        and item.result == result
        for item in graph.evidence
    )


def _validate_control(graph: Graph, control: dict[str, Any]) -> None:
    """
    @brief Validate access and earlier-stage routing requests.
    """
    mode = control["requested_access_mode"]
    if mode and mode not in {"standard", "repo-wide"}:
        raise StageOperationError(
            "control.requested_access_mode must be empty, standard, or repo-wide"
        )
    if mode and not control["access_rationale"].strip():
        raise StageOperationError(
            "control.access_rationale is required for an access-mode change"
        )
    route = control["route_to"]
    if route:
        stages = run_stage_spec(graph).stages
        if route not in stages or stages.index(route) >= stages.index(graph.stage):
            raise StageOperationError(
                "control.route_to must name an earlier stage in this workflow"
            )
        if not control["route_rationale"].strip():
            raise StageOperationError(
                "control.route_rationale is required for earlier-stage routing"
            )


def _control(value: Any, path: Path) -> dict[str, Any]:
    """@brief Validate and normalize a common control table."""
    if not isinstance(value, dict):
        raise StageOperationError(f"{path}: [control] table is required")
    _closed_keys(value, COMMON_CONTROL_KEYS, path)
    for key in COMMON_CONTROL_KEYS:
        if key not in value:
            raise StageOperationError(f"{path}: control.{key} is required")
    return {
        "requested_access_mode": _string(value, "requested_access_mode", path),
        "access_rationale": _string(value, "access_rationale", path),
        "route_to": _string(value, "route_to", path),
        "route_rationale": _string(value, "route_rationale", path),
        "summary": _string(value, "summary", path),
        "unresolved_questions": _strings(
            value, "unresolved_questions", path
        ),
    }


def _validate_stage_values(
    data: dict[str, Any],
    stage: Stage,
    path: Path,
) -> None:
    """
    @brief Validate and normalize every stage-specific scalar and array.
    """
    for field in _stage_field_specs(stage):
        if field.kind == "array":
            data[field.name] = _strings(data, field.name, path)
        elif field.kind == "string":
            data[field.name] = _string(data, field.name, path)
        elif field.kind == "bool" and type(data[field.name]) is not bool:
            raise StageOperationError(
                f"{path}: {field.name} must be a boolean"
            )


def _merge_repowise_discovery(
    repo_root: Path,
    graph: Graph,
    record: StageRecord,
) -> None:
    """
    @brief Merge validated RepoWise proposals without replacing existing values.
    @param[in] repo_root Repository root.
    @param[in] graph Active adoption graph.
    @param[in,out] record Prepared repo-discovery record.
    @return None.
    """
    inspection = inspect_repowise(
        repo_root,
        run_id=graph.run_id,
        write_snapshot=True,
    )
    for key in (
        "source_roots",
        "candidate_components",
        "external_dependencies",
        "entry_points",
        "existing_tests",
    ):
        existing = record.payload.get(key, [])
        if not isinstance(existing, list):
            existing = []
        additions = inspection.proposals.get(key, []) if inspection.current else []
        record.payload[key] = sorted(
            {
                item
                for item in [*existing, *additions]
                if isinstance(item, str) and item
            }
        )
    for key in (
        "test_roots",
        "requirement_roots",
        "documentation_roots",
        "gate_commands",
    ):
        record.payload.setdefault(key, [])
    evidence = [
        item
        for item in record.payload.get("discovery_evidence", [])
        if isinstance(item, str) and item
    ]
    if inspection.snapshot:
        evidence.append(inspection.snapshot)
    record.payload["discovery_evidence"] = sorted(set(evidence))
    record.payload["repowise_warnings"] = list(inspection.warnings)
    record.payload["repowise_status"] = inspection.status


def _validate_identity(
    data: dict[str, Any],
    graph: Graph,
    record: StageRecord,
    path: Path,
) -> None:
    """@brief Reject stale, foreign, or non-schema-3 forms."""
    expected = {
        "schema_version": FORM_SCHEMA_VERSION,
        "run_id": graph.run_id,
        "stage": graph.stage,
        "revision": record.revision,
    }
    for key, value in expected.items():
        if data.get(key) != value:
            raise StageOperationError(
                f"{path}: {key} must be {value!r}; received {data.get(key)!r}"
            )


def _apply_retention(
    repo_root: Path,
    graph: Graph,
    record: StageRecord,
    directory: Path,
) -> None:
    """
    @brief Apply the captured transient stage-form retention policy.
    """
    if record.retention == "versioned":
        revision_dir = directory / "revisions" / f"{record.revision:04d}"
        revision_dir.mkdir(parents=True, exist_ok=True)
        for path in directory.iterdir():
            if path.is_file():
                shutil.copy2(path, revision_dir / path.name)
        (revision_dir / "digest.json").write_text(
            json.dumps({"sha256": record.digest}, indent=2) + "\n",
            encoding="utf-8",
        )
    elif record.retention == "discard":
        for path in directory.iterdir():
            if path.is_file():
                path.unlink()


def _stage_digest(directory: Path) -> str:
    """@brief Digest every current transient form in deterministic order."""
    digest = sha256()
    for path in sorted(item for item in directory.iterdir() if item.is_file()):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _file_digest(path: Path) -> str:
    """@brief Return the SHA-256 digest of one durable artifact."""
    return sha256(path.read_bytes()).hexdigest()


def _load_toml(path: Path) -> dict[str, Any]:
    """@brief Load one UTF-8 TOML table with an actionable error."""
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise StageOperationError(f"{path}: cannot load form: {exc}") from exc
    if not isinstance(data, dict):
        raise StageOperationError(f"{path}: top-level TOML value must be a table")
    return data


def _closed_keys(data: dict[str, Any], expected: tuple[str, ...], path: Path) -> None:
    """@brief Enforce exact key sets for strict schema-3 stage forms."""
    unknown = sorted(set(data) - set(expected))
    if unknown:
        raise StageOperationError(f"{path}: unknown key {unknown[0]}")


def _stage_field_specs(stage: Stage) -> tuple[StageFieldSpec, ...]:
    """
    @brief Return the declarative field sequence for one single-form stage.
    @exception StageOperationError If the stage uses no supported single form.
    """
    try:
        return STAGE_FIELD_SPECS[stage]
    except KeyError as exc:
        raise StageOperationError(f"unsupported stage form: {stage}") from exc


def _stage_field_default(field: StageFieldSpec, graph: Graph) -> Any:
    """
    @brief Resolve one static or graph-aware field default.
    """
    return field.default(graph) if callable(field.default) else field.default


def _render_stage_field(field: StageFieldSpec, value: Any) -> str:
    """
    @brief Render one schema-typed TOML field value.
    """
    if field.kind == "array":
        return _array(value)
    if field.kind == "bool":
        return "true" if value else "false"
    return _q(value)


def _nonempty(data: dict[str, Any], key: str, path: Path) -> str:
    """@brief Read one required non-empty string field."""
    value = _string(data, key, path)
    if not value:
        raise StageOperationError(f"{path}: {key} must not be empty")
    return value


def _strings(data: dict[str, Any], key: str, path: Path) -> list[str]:
    """
    @brief Read one list of non-empty strings.
    """
    value = data.get(key)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise StageOperationError(
            f"{path}: {key} must be an array of non-empty strings"
        )
    return [item.strip() for item in value]


def _new_requirement_id(category: str) -> str:
    """@brief Generate a durable canonical requirement ID."""
    code = CATEGORY_IDENTITIES[category][1]
    return f"REQ-{code}-{uuid.uuid4()}"


def _rehydrated_values(graph: Graph, record: StageRecord) -> dict[str, Any]:
    """
    @brief Recover a new editable form from authoritative imported state.
    @details The legacy per-stage mappings below cover graphs persisted before
             payload snapshots existed; :func:`_with_schema_defaults` then
             fills any schema field the hand-written mapping does not name, so
             adding a field to the schema table can never silently drop it on
             rehydration.
    """
    if record.payload:
        return dict(record.payload)
    return _with_schema_defaults(graph, _legacy_rehydrated_values(graph))


def _with_schema_defaults(graph: Graph, values: dict[str, Any]) -> dict[str, Any]:
    """
    @brief Fill schema fields absent from a legacy rehydration mapping.
    """
    if not values:
        return values
    for field in _stage_field_specs(graph.stage):
        default = _stage_field_default(field, graph)
        if default is REQUIRED_STAGE_VALUE:
            # Populated by the caller (design.document); never a form default.
            continue
        values.setdefault(field.name, default)
    return values


def _legacy_rehydrated_values(graph: Graph) -> dict[str, Any]:
    """
    @brief Map pre-payload graph state onto the current form fields.
    """
    if graph.stage == "intake":
        return {
            "statement": graph.intent.statement,
            "scope_hints": graph.intent.scope_hint,
            "access_mode": graph.access_mode,
        }
    if graph.stage == "alignment" and graph.alignment:
        return {
            "understanding": graph.alignment.understanding,
            "in_scope": [
                item.removeprefix("in: ")
                for item in graph.alignment.scope
                if item.startswith("in: ")
            ],
            "out_of_scope": [
                item.removeprefix("out: ")
                for item in graph.alignment.scope
                if item.startswith("out: ")
            ],
            "assumptions": graph.alignment.assumptions,
            "acceptance_criteria": graph.alignment.acceptance,
            "questions": graph.alignment.open_questions,
            "recommended_answers": graph.alignment.recommended_responses,
            "planned_paths": graph.alignment.planned_paths,
            "risk": graph.alignment.risk,
            "decision": graph.alignment.decision,
        }
    if graph.stage == "design" and graph.design:
        return {
            "cited_requirement_ids": list(graph.design.requirement_digests),
            "selected_option": graph.design.selected_option,
            "control": {"unresolved_questions": graph.design.open_questions},
        }
    return {}


def _companion_spec_template(requirement_id: str) -> str:
    """@brief Render a durable externally observable companion specification."""
    return f"""# Companion Specification: {requirement_id}

## Observable Contract

Describe externally observable behavior, state transitions, formats, errors,
user-facing text, and non-functional constraints.

## Acceptance Examples

- Add representative success, boundary, and failure examples.

## Variants

Identify applicable production/mock/sandbox, feature-flag, role, platform, and
persistence-adapter variants. State which variants promise parity.
"""


def _design_template(graph: Graph) -> str:
    """@brief Render the authoritative solution-design document outline."""
    return f"""# Solution Design: {graph.run_id}

## Requirement Summary and Cited IDs

## Relevant Existing Architecture

## Constraints

## Alternatives and Trade-offs

## Selected Design and Rationale

## Affected Components

## Internal Interfaces and Data

## Compatibility Implications

## Implementation Sequence

## Validation Approach

## Risks and Open Decisions
"""


def _q(value: Any) -> str:
    """@brief Quote a scalar as a TOML basic string."""
    return json.dumps(str(value), ensure_ascii=False)


def _array(values: Any) -> str:
    """@brief Render a TOML string array."""
    return "[" + ", ".join(_q(item) for item in values) + "]"


def _standard_index(stage: str) -> int:
    """@brief Return standard-stage order, treating adoption stages as earlier."""
    return STAGES.index(stage) if stage in STAGES else -1


# END OF FILE
