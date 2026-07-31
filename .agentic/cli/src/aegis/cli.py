#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file cli.py
@brief Stage-oriented, file-first AEGIS 2.1 command-line interface.
@details Exposes only ten grouped command families, two global options, stable
         concise/JSON response fields, and no AEGIS 1.x aliases or mutation
         flags.
"""

# IMPORTS

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any

from .check_execution import (
    prepare_check_evidence,
    record_check_evidence,
    run_checks,
)
from .components import (
    audit_local_scope,
    load_components,
)
from .config import (
    ConfigurationError,
    GATE_ORDER,
    WorkflowConfig,
    effective_config_dict,
    load_config,
)
from .evidence_forms import (
    apply_evidence_form,
    prepare_evidence_form,
    show_evidence,
)
from .errors import CommandInputError
from .gates import gate_failure_blockers, run_gates
from .invariants import blocking_failures, evaluate
from .models import Graph
from .persistence import PersistenceError
from .report import render_report, write_report
from .requirements import (
    audit_coverage,
    audit_traceability,
    impact,
    list_requirements,
    show_requirement,
)
from .repowise import (
    RepoWiseIntegrationError,
    effective_repowise_config,
    inspect_repowise,
)
from .requirement_store import (
    RequirementValidationError,
    normalize_repository_path,
)
from .stage_forms import (
    StageOperationError,
    add_stage_item,
    apply_stage,
    bypassed_stages,
    close_stage,
    next_command,
    prepare_stage,
    quick_scope_advisory,
    show_stage,
)
from .store import (
    RunResolutionError,
    add_waiver,
    init_graph,
    load_graph,
    repo_root_from,
    resolve_run_id,
    write_current_run,
)
from .waiver_targets import (
    annotate_audit_issues,
    annotate_working_tree,
    collect_waiver_targets,
    waiver_record_statuses,
)
from .waivers import active_waiver, blocker_to_dict
from .verification import (
    quick_bypass_committed,
    read_validation_summary,
    run_verification,
    validation_summary_path,
)
from .working_tree import audit_working_tree

# CONSTANTS

TOP_LEVEL_COMMANDS = (
    "run",
    "stage",
    "requirement",
    "check",
    "evidence",
    "waive",
    "verify",
    "delivery",
    "adoption",
    "config",
)

# PUBLIC API


def main(argv: list[str] | None = None) -> None:
    """
    @brief      Run the AEGIS 2.1 grouped CLI.
    @param[in]  argv Optional argument vector for tests and embedding.
    @return     None.
    @exception  SystemExit For parser, policy, validation, or command failures.
    @exception  OSError If persistence or file I/O fails outside the handled
                policy exceptions.
    """
    normalized = _normalize_global_options(list(argv) if argv is not None else sys.argv[1:])
    parser = _build_parser()
    args = parser.parse_args(normalized)
    root = repo_root_from()
    graph: Graph | None = None
    try:
        if args.group == "config":
            payload = _config_command(root, args)
            _respond(payload, args.json)
            return

        config = load_config(root)
        if args.group == "run" and args.action == "start":
            profile = "quick" if args.quick else "full"
            graph = init_graph(root, args.kind, "", profile=profile)
            artifact = prepare_stage(root, graph, config)
            details: dict[str, Any] = {
                "run_id": graph.run_id,
                "kind": graph.intent.kind,
            }
            if graph.profile == "quick":
                details["run_profile"] = graph.profile
            _respond(
                _payload(
                    graph,
                    artifact.relative_to(root).as_posix(),
                    next_command(graph, root),
                    **details,
                ),
                args.json,
            )
            return

        if args.group == "run" and args.action == "select":
            run_id = resolve_run_id(root, args.run_id)
            graph = load_graph(root, run_id)
            write_current_run(root, run_id)
            _respond(_run_status(root, graph), args.json)
            return

        graph = _load_active_graph(root, args.run)
        payload, exit_code = _dispatch(root, graph, config, args)
        if exit_code and payload.get("status") == "ok":
            payload["status"] = "failed"
        _respond(payload, args.json)
        if exit_code:
            raise SystemExit(exit_code)
    except (
        CommandInputError,
        ConfigurationError,
        PersistenceError,
        RepoWiseIntegrationError,
        RequirementValidationError,
        RunResolutionError,
        StageOperationError,
    ) as exc:
        stage = graph.stage if graph else "none"
        artifact = _active_artifact(graph)
        payload = {
            "status": "blocked",
            "stage": stage,
            "artifact": artifact,
            "next": next_command(graph, root) if graph else "aegis config validate",
            "error": str(exc),
        }
        if isinstance(exc, ConfigurationError):
            payload.update(exc.to_dict())
        _respond(payload, args.json)
        raise SystemExit(1) from None


# CLI CONSTRUCTION


def _build_parser() -> argparse.ArgumentParser:
    """
    @brief Build the complete hard-break AEGIS 2 parser.
    """
    parser = argparse.ArgumentParser(prog="aegis")
    parser.add_argument("--run", help="explicit run ID; selected run is the default")
    parser.add_argument("--json", action="store_true", help="emit stable JSON")
    groups = parser.add_subparsers(dest="group", required=True)

    run = groups.add_parser("run", help="create and navigate runs")
    run_sub = run.add_subparsers(dest="action", required=True)
    start = run_sub.add_parser("start")
    start.add_argument("kind", choices=("feature", "fix", "change", "adoption"))
    start.add_argument(
        "--quick",
        action="store_true",
        help="use the proportional four-stage profile for fix/change runs",
    )
    run_sub.add_parser("status")
    run_sub.add_parser("resume")
    select = run_sub.add_parser("select")
    select.add_argument("run_id")

    stage = groups.add_parser("stage", help="operate the current stage forms")
    stage_sub = stage.add_subparsers(dest="action", required=True)
    for action in ("prepare", "add", "show", "apply", "close"):
        stage_sub.add_parser(action)

    requirement = groups.add_parser("requirement", help="read durable requirements")
    requirement_sub = requirement.add_subparsers(dest="action", required=True)
    requirement_sub.add_parser("list")
    requirement_show = requirement_sub.add_parser("show")
    requirement_show.add_argument("id")

    check = groups.add_parser("check", help="record deterministic check evidence")
    check_sub = check.add_subparsers(dest="action", required=True)
    check_sub.add_parser("prepare")
    check_sub.add_parser("record")
    check_run = check_sub.add_parser("run")
    check_run.add_argument("check_ids", nargs="*")

    evidence = groups.add_parser("evidence", help="manage manual evidence forms")
    evidence_sub = evidence.add_subparsers(dest="action", required=True)
    evidence_prepare = evidence_sub.add_parser("prepare")
    evidence_prepare.add_argument("evidence_action", choices=("add", "supersede"))
    evidence_sub.add_parser("apply")
    evidence_sub.add_parser("show")

    waive = groups.add_parser("waive", help="record exact run-local waivers")
    waive_sub = waive.add_subparsers(dest="action", required=True)
    waive_add = waive_sub.add_parser("add")
    waive_add.add_argument("blocker_id")
    waive_add.add_argument("--reason", required=True)
    waive_sub.add_parser("list")

    verify = groups.add_parser("verify", help="run deterministic verification")
    verify_sub = verify.add_subparsers(dest="action", required=True)
    verify_sub.add_parser("run")
    verify_sub.add_parser("status")
    gates = verify_sub.add_parser("gates")
    gates.add_argument("gate_names", nargs="*", choices=GATE_ORDER)
    verify_sub.add_parser("invariants")
    verify_sub.add_parser("traceability")
    verify_sub.add_parser("coverage")
    verify_impact = verify_sub.add_parser("impact")
    verify_impact.add_argument("paths_file", nargs="?")
    verify_sub.add_parser("working-tree")

    delivery = groups.add_parser("delivery", help="inspect delivery handoff")
    delivery_sub = delivery.add_subparsers(dest="action", required=True)
    delivery_sub.add_parser("show")
    delivery_sub.add_parser("report")

    adoption = groups.add_parser("adoption", help="inspect adoption state")
    adoption_sub = adoption.add_subparsers(dest="action", required=True)
    adoption_sub.add_parser("component-status")
    scope = adoption_sub.add_parser("scope-check")
    scope.add_argument("paths", nargs="+")
    adoption_sub.add_parser("baseline")

    config = groups.add_parser("config", help="inspect workspace policy")
    config_sub = config.add_subparsers(dest="action", required=True)
    config_sub.add_parser("validate")
    config_sub.add_parser("show")
    return parser


# COMMAND ORCHESTRATION


def _dispatch(
    root: Path,
    graph: Graph,
    config: WorkflowConfig,
    args: argparse.Namespace,
) -> tuple[dict[str, Any], int]:
    """
    @brief Dispatch one parsed grouped command.
    """
    if args.group == "run":
        return _run_status(root, graph), 0
    if args.group == "stage":
        return _stage_command(root, graph, config, args), 0
    if args.group == "requirement":
        records = (
            [show_requirement(root, args.id, config)]
            if args.action == "show"
            else list_requirements(root, config=config)
        )
        artifact = (
            records[0].source_file
            if args.action == "show"
            else config.requirement_roots[0]
        )
        return (
            _payload(
                graph,
                artifact or "none",
                next_command(graph, root),
                requirements=[item.to_dict() for item in records],
            ),
            0,
        )
    if args.group == "check":
        return _check_command(root, graph, args), 0
    if args.group == "evidence":
        return _evidence_command(root, graph, args), 0
    if args.group == "waive":
        return _waive_command(root, graph, config, args), 0
    if args.group == "verify":
        return _verify_command(root, graph, config, args)
    if args.group == "delivery":
        if args.action == "report":
            path = write_report(root, graph, render_report(root, graph, config))
            return (
                _payload(
                    graph,
                    path.relative_to(root).as_posix(),
                    next_command(graph, root),
                    report=path.relative_to(root).as_posix(),
                ),
                0,
            )
        return _run_status(root, graph), 0
    return _adoption_command(root, graph, config, args)


def _stage_command(
    root: Path,
    graph: Graph,
    config: WorkflowConfig,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """
    @brief Execute one stage lifecycle action.
    """
    if args.action == "prepare":
        artifact = prepare_stage(root, graph, config)
        return _payload(
            graph,
            artifact.relative_to(root).as_posix(),
            next_command(graph, root),
        )
    if args.action == "add":
        artifact = add_stage_item(root, graph)
        return _payload(
            graph,
            artifact.relative_to(root).as_posix(),
            "aegis stage apply",
        )
    if args.action == "show":
        shown = show_stage(root, graph)
        return _payload(
            graph,
            shown.get("artifact") or "none",
            next_command(graph, root),
            **shown,
        )
    if args.action == "apply":
        record = apply_stage(root, graph, config)
        return _payload(
            graph,
            record.artifact or "none",
            next_command(graph, root),
            revision=record.revision,
            digest=record.digest,
        )
    closing_stage = graph.stage
    graph, artifact = close_stage(root, graph, config)
    details: dict[str, Any] = {
        "complete": graph.complete,
        **_quick_run_details(graph),
    }
    if closing_stage == "implementation":
        advisory = quick_scope_advisory(graph, config)
        if advisory is not None:
            details["advisories"] = [advisory]
    return _payload(
        graph,
        artifact.relative_to(root).as_posix() if artifact else "none",
        next_command(graph, root),
        **details,
    )


def _check_command(
    root: Path,
    graph: Graph,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """
    @brief Execute one external or managed check command.
    """
    if args.action == "prepare":
        path = prepare_check_evidence(root, graph)
        return _payload(
            graph,
            path.relative_to(root).as_posix(),
            "aegis check record",
        )
    if args.action == "record":
        evidence = record_check_evidence(root, graph)
    else:
        evidence = run_checks(root, graph, args.check_ids)
    return _payload(
        graph,
        "none",
        next_command(graph, root),
        evidence=[asdict(item) for item in evidence],
    )


def _evidence_command(
    root: Path,
    graph: Graph,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """
    @brief Execute one manual evidence form action.
    """
    if args.action == "prepare":
        path = prepare_evidence_form(root, graph, args.evidence_action)
        return _payload(
            graph,
            path.relative_to(root).as_posix(),
            "aegis evidence apply",
        )
    if args.action == "apply":
        result = apply_evidence_form(root, graph)
        return _payload(graph, "none", next_command(graph, root), result=result)
    result = show_evidence(root, graph)
    return _payload(
        graph,
        result["form"] or "none",
        next_command(graph, root),
        **result,
    )


def _waive_command(
    root: Path,
    graph: Graph,
    config: WorkflowConfig,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """
    @brief List or record one exact human-approved run-local waiver.
    @param[in] root Repository root.
    @param[in,out] graph Active graph that owns the waiver record.
    @param[in] config Validated workflow policy used to discover blockers.
    @param[in] args Parsed waiver action and values.
    @return Stable waiver response payload.
    @exception CommandInputError If the reason/target is invalid or inactive.
    @exception ValueError If the target already gained an active waiver of the
               same state underneath this call.
    @exception GraphConflictError If the graph changed underneath this call.
    @exception PersistenceError If journal integrity prevents a complete record.
    @exception OSError If persistence fails.
    """
    expected_source_digest = getattr(graph, "_source_digest", None)
    targets = collect_waiver_targets(root, graph, config)
    if args.action == "list":
        history = waiver_record_statuses(graph, targets)
        return _payload(
            graph,
            "none",
            next_command(graph, root),
            active_waivers=[
                item for item in history if item["status"] == "active"
            ],
            waiver_history=history,
            eligible_blockers=[
                blocker_to_dict(blocker, graph) for blocker in targets
            ],
        )

    reason = args.reason.strip()
    if not reason:
        raise CommandInputError("waiver reason must not be empty")
    blocker_id = args.blocker_id.strip()
    if not blocker_id:
        raise CommandInputError("waiver blocker ID must be one exact non-empty ID")
    target = next(
        (item for item in targets if item.id == blocker_id),
        None,
    )
    if target is None:
        raise CommandInputError(
            "blocker is not currently active or is not waivable: "
            f"{blocker_id}"
        )
    if active_waiver(graph, target) is not None:
        raise CommandInputError(
            f"blocker already has an active waiver: {blocker_id}"
        )
    waiver = add_waiver(
        root,
        graph,
        target.id,
        reason,
        target.state_digests,
        expected_source_digest=expected_source_digest,
    )
    return _payload(
        graph,
        "none",
        next_command(graph, root),
        waiver=asdict(waiver),
        blocker=blocker_to_dict(target, graph),
    )


def _verify_command(
    root: Path,
    graph: Graph,
    config: WorkflowConfig,
    args: argparse.Namespace,
) -> tuple[dict[str, Any], int]:
    """
    @brief Execute one deterministic verification action.
    """
    if args.action == "run":
        summary, code = run_verification(root, graph, config)
        return (
            _payload(
                graph,
                validation_summary_path(root, graph).relative_to(root).as_posix(),
                next_command(graph, root),
                verification=summary,
            ),
            code,
        )
    if args.action == "status":
        summary = read_validation_summary(root, graph)
        return (
            _payload(
                graph,
                validation_summary_path(root, graph).relative_to(root).as_posix(),
                next_command(graph, root),
                verification=summary,
            ),
            0,
        )
    if args.action == "gates":
        code = run_gates(root, graph.run_id, config, args.gate_names or None)
        graph = load_graph(root, graph.run_id)
        modes = {
            name: getattr(config.gates, name).mode
            for name in (args.gate_names or GATE_ORDER)
        }
        waived_gates = [
            blocker_to_dict(blocker, graph)
            for blocker in gate_failure_blockers(
                graph,
                config,
                args.gate_names or None,
            )
            if active_waiver(graph, blocker) is not None
        ]
        details: dict[str, Any] = {"gates": modes}
        if waived_gates:
            details["waived_gates"] = waived_gates
        return (
            _payload(graph, "none", next_command(graph, root), **details),
            1 if code else 0,
        )
    if args.action == "invariants":
        results = evaluate(root, graph, config)
        return (
            _payload(
                graph,
                "none",
                next_command(graph, root),
                invariants=[item.to_dict() for item in results],
            ),
            1 if blocking_failures(results) else 0,
        )
    if args.action in {"traceability", "coverage"}:
        if graph.profile == "quick":
            return (
                _payload(
                    graph,
                    "none",
                    next_command(graph, root),
                    audit_status="not-applicable",
                    issues=[
                        {
                            "status": "not-applicable",
                            "message": "Not applicable - quick run.",
                        }
                    ],
                ),
                0,
            )
        issues = (
            audit_traceability(root, config)
            if args.action == "traceability"
            else audit_coverage(root, config)
        )
        serialized, blockers = annotate_audit_issues(
            args.action,
            issues,
            graph,
        )
        return (
            _payload(
                graph,
                "none",
                next_command(graph, root),
                issues=serialized,
            ),
            1 if blockers else 0,
        )
    if args.action == "impact":
        paths = _read_paths_file(root, args.paths_file) if args.paths_file else None
        report = impact(root, paths, config=config)
        return _payload(graph, "none", next_command(graph, root), impact=report), 0
    report, blockers = annotate_working_tree(
        audit_working_tree(root, config, graph),
        graph,
        root,
    )
    return (
        _payload(graph, "none", next_command(graph, root), working_tree=report),
        1 if blockers else 0,
    )


def _adoption_command(
    root: Path,
    graph: Graph,
    config: WorkflowConfig,
    args: argparse.Namespace,
) -> tuple[dict[str, Any], int]:
    """
    @brief Preserve adoption inspection commands under the grouped surface.
    """
    manifest = load_components(root, config.component_manifest)
    if args.action == "component-status":
        components = {
            name: asdict(component)
            for name, component in sorted(manifest.components.items())
        }
        return (
            _payload(
                graph,
                config.component_manifest,
                next_command(graph, root),
                components=components,
            ),
            0,
        )
    if args.action == "scope-check":
        issues = audit_local_scope(root, args.paths, config)
        return (
            _payload(
                graph,
                config.component_manifest,
                next_command(graph, root),
                issues=[asdict(item) for item in issues],
            ),
            1 if any(item.blocking for item in issues) else 0,
        )
    baseline = {
        "minimum_completion_level": (
            config.component_baseline_guard.minimum_completion_level
        ),
        "component_count": len(manifest.components),
        "report_root": config.adoption_report_root,
    }
    return (
        _payload(
            graph,
            config.component_manifest,
            next_command(graph, root),
            baseline=baseline,
        ),
        0,
    )


def _config_command(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    """@brief Validate schema-3 policy and optional integration configuration."""
    config = load_config(root)
    data = effective_config_dict(config)
    integration = effective_repowise_config(root)
    inspection = inspect_repowise(root)
    return {
        "status": "ok",
        "stage": "none",
        "artifact": ".agentic/workflow.toml",
        "next": "aegis run start feature",
        **(
            {
                "config": data,
                "integrations": {
                    "repowise": {
                        **integration,
                        "status": inspection.status,
                        "warnings": list(inspection.warnings),
                    }
                },
            }
            if args.action == "show"
            else {
                "schema_version": 3,
                "integration_schema_versions": {"repowise": 1},
            }
        ),
    }


# LOCAL HELPERS


def _run_status(root: Path, graph: Graph) -> dict[str, Any]:
    """
    @brief Build status/resume output from authoritative run state.
    """
    shown = show_stage(root, graph) if not graph.complete else {}
    evidence = [
        {
            "id": item.id,
            "kind": item.kind,
            "result": item.result,
            "status": item.status,
            "check_id": item.check_id,
        }
        for item in graph.evidence
    ]
    return _payload(
        graph,
        shown.get("artifact") or "none",
        next_command(graph, root),
        run_id=graph.run_id,
        complete=graph.complete,
        readiness=shown,
        evidence=evidence,
        **_quick_run_details(graph),
    )


def _quick_run_details(graph: Graph) -> dict[str, Any]:
    """
    @brief Build quick-only status fields after human intake approval.
    @param[in] graph Active run graph.
    @return Empty mapping for full runs, otherwise profile and bypass state.
    """
    if graph.profile != "quick":
        return {}
    details: dict[str, Any] = {"run_profile": "quick"}
    if quick_bypass_committed(graph):
        details.update(
            {
                "bypass_status": "bypassed",
                "bypassed_stages": bypassed_stages(graph),
            }
        )
    return details


def _load_active_graph(root: Path, explicit: str | None) -> Graph:
    """@brief Resolve and load either the explicit or selected run."""
    run_id = resolve_run_id(root, explicit)
    return load_graph(root, run_id)


def _payload(
    graph: Graph,
    artifact: str,
    exact_next: str,
    **details: Any,
) -> dict[str, Any]:
    """@brief Construct the stable command-response envelope."""
    return {
        "status": "ok",
        "stage": graph.stage,
        "artifact": artifact or "none",
        "next": exact_next,
        **details,
    }


def _respond(payload: dict[str, Any], json_output: bool) -> None:
    """@brief Emit stable JSON or concise line-oriented text."""
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    for key in ("status", "stage", "artifact", "next"):
        print(f"{key}: {payload.get(key, 'none')}")
    for key, value in payload.items():
        if key in {"status", "stage", "artifact", "next"}:
            continue
        rendered = (
            value
            if isinstance(value, (str, int, float, bool)) or value is None
            else json.dumps(value, ensure_ascii=False, sort_keys=True)
        )
        print(f"{key}: {rendered}")


def _normalize_global_options(argv: list[str]) -> list[str]:
    """
    @brief      Accept the two global options before or after grouped commands.
    @param[in]  argv Raw argument vector.
    @return     Equivalent vector with global options moved before the group.
    """
    globals_: list[str] = []
    command: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--json":
            globals_.append(token)
        elif token == "--run":
            if index + 1 >= len(argv):
                command.append(token)
            else:
                globals_.extend((token, argv[index + 1]))
                index += 1
        elif token.startswith("--run="):
            globals_.append(token)
        else:
            command.append(token)
        index += 1
    return [*globals_, *command]


def _read_paths_file(root: Path, value: str) -> list[str]:
    """
    @brief Read newline-delimited impact paths from a repository file.
    @param[in] root Repository root.
    @param[in] value Parsed repository-relative paths-file value.
    @return Non-comment, non-empty paths from the referenced file.
    @exception CommandInputError If the file or one of its paths is invalid.
    @exception OSError If the paths file cannot be read.
    """
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        raise CommandInputError(
            "paths file must be repository-relative"
        ) from None
    if not path.is_file():
        raise CommandInputError(f"paths file does not exist: {value}")
    paths: list[str] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            paths.append(
                normalize_repository_path(stripped, allow_glob=False)
            )
        except ValueError as exc:
            raise CommandInputError(
                f"invalid path in {value} at line {line_number}: {exc}"
            ) from exc
    return paths


def _active_artifact(graph: Graph | None) -> str:
    """@brief Return the graph's currently recorded artifact for errors."""
    if not graph:
        return "none"
    record = graph.stage_records.get(graph.stage)
    return record.artifact if record and record.artifact else "none"


# END OF FILE
