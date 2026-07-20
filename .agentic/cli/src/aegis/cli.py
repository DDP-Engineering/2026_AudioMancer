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
@brief Command-line interface for the agentic workflow runner.
@details Provides reusable implementation behavior for the standalone AEGIS system,
including clean validation errors, duplicate-id guards, and explicit run scope hints.
@author Eng. Dan Dumitru Pasare
@date 2026-07-20
@version 0.8.0
"""

# IMPORTS

from __future__ import annotations

import argparse
from dataclasses import asdict
import fnmatch
import json
from pathlib import Path

from .components import ComponentIssue, audit_components, audit_local_scope, component_for_path, load_components
from .config import WorkflowConfig, load_config
from .gates import run_gates
from .invariants import blocking_failures, evaluate
from .models import ADOPTION_STAGES, ALL_STAGES, AccessMode, Check, ChangeUnit, Decision, Evidence, IntentAlignment, SpecItem, STAGES
from .requirements import (
    activate_requirement,
    audit_coverage,
    audit_registry,
    audit_traceability,
    impact,
    sync_registry,
)
from .report import render_report, write_report
from .store import add_evidence, append_journal, init_graph, load_graph, repo_root_from, save_graph, set_access_mode, set_stage
from .working_tree import audit_working_tree

# CONSTANTS

ALIGNMENT_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}

# PUBLIC API


def main(argv: list[str] | None = None) -> None:
    """
    @brief      Run command-line entry point workflow behavior.
    @param[in]  argv Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  SystemExit If command validation or a workflow gate fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-20
    @version    0.8.0
    """
    parser = argparse.ArgumentParser(prog="aegis")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("--kind", choices=["feature", "fix", "change", "adoption"], required=True)
    start.add_argument("--statement", required=True)
    start.add_argument("--access-mode", choices=["standard", "repo-wide"], default="standard")
    start.add_argument("--access-reason")
    start.add_argument("--scope-hint", action="append", default=[])

    sub.add_parser("status")
    sub.add_parser("next")
    sub.add_parser("invariants")
    sub.add_parser("report")
    sub.add_parser("delivery-preflight")

    stage = sub.add_parser("set-stage")
    stage.add_argument("stage", choices=ALL_STAGES)
    stage.add_argument("--reason", required=True)

    access = sub.add_parser("set-access-mode")
    access.add_argument("access_mode", choices=["standard", "repo-wide"])
    access.add_argument("--reason", required=True)

    alignment = sub.add_parser("alignment")
    alignment.add_argument("--source", required=True)
    alignment.add_argument("--understanding", required=True)
    alignment.add_argument("--scope", action="append", required=True)
    alignment.add_argument("--assumption", action="append", default=[])
    alignment.add_argument("--acceptance", action="append", required=True)
    alignment.add_argument("--question", action="append", default=[])
    alignment.add_argument("--recommended-response", action="append", default=[])
    alignment.add_argument("--risk", choices=["low", "medium", "high"], required=True)
    alignment.add_argument("--decision", choices=["proceed", "pause"], required=True)
    alignment.add_argument("--reason", required=True)
    alignment.add_argument("--planned-path", action="append", default=[])

    supersede = sub.add_parser("supersede-evidence")
    supersede.add_argument("--id", required=True)
    supersede.add_argument("--by", required=True)
    supersede.add_argument("--reason", required=True)

    audit = sub.add_parser("audit")
    audit_sub = audit.add_subparsers(dest="audit_command", required=True)
    audit_sub.add_parser("traceability")
    audit_sub.add_parser("coverage")

    impact_parser = sub.add_parser("impact")
    impact_parser.add_argument("files", nargs="*")
    impact_parser.add_argument("--json", action="store_true")

    registry = sub.add_parser("registry")
    registry_sub = registry.add_subparsers(dest="registry_command", required=True)
    registry_sub.add_parser("sync")
    registry_sub.add_parser("audit")

    requirement = sub.add_parser("requirement")
    requirement_sub = requirement.add_subparsers(dest="requirement_command", required=True)
    activate = requirement_sub.add_parser("activate")
    activate.add_argument("--id", required=True)
    activate.add_argument("--linked-test", action="append", default=[])
    activate.add_argument("--verification", required=True)

    working_tree = sub.add_parser("working-tree")
    working_tree_sub = working_tree.add_subparsers(dest="working_tree_command", required=True)
    working_tree_sub.add_parser("audit")

    adoption = sub.add_parser("adoption")
    adoption_sub = adoption.add_subparsers(dest="adoption_command", required=True)
    adoption_sub.add_parser("component-status")
    scope_check = adoption_sub.add_parser("scope-check")
    scope_check.add_argument("paths", nargs="+")
    adoption_sub.add_parser("baseline")

    gates = sub.add_parser("gates")
    gates.add_argument("action", choices=["run"])
    gates.add_argument("--name", action="append")
    gates.add_argument("--timeout", type=int, default=300)

    spec = sub.add_parser("add-spec")
    spec.add_argument("--id", required=True)
    spec.add_argument("--tag", choices=["behavior", "property"], required=True)
    spec.add_argument("--statement", required=True)
    spec.add_argument("--status", default="accepted", choices=["proposed", "accepted", "realized", "retired"])
    spec.add_argument("--example", action="append", default=[])
    spec.add_argument("--threshold")

    check = sub.add_parser("add-check")
    check.add_argument("--id", required=True)
    check.add_argument("--level", default="test")
    check.add_argument("--cites-spec", action="append", required=True)
    check.add_argument("--cites-requirement", action="append", default=[])
    check.add_argument("--command", dest="check_command")
    check.add_argument("--path")
    check.add_argument("--state", choices=["red", "green", "unknown"], default="unknown")

    ev = sub.add_parser("record-evidence")
    ev.add_argument("--kind", choices=["test-run", "diff", "scan", "gate", "decision", "note"], required=True)
    ev.add_argument("--result", choices=["pass", "fail", "info"], required=True)
    ev.add_argument("--status", choices=["active", "superseded"], default="active")
    ev.add_argument("--failure-kind")
    ev.add_argument("--summary", required=True)
    ev.add_argument("--command", dest="evidence_command")
    ev.add_argument("--path")
    ev.add_argument("--stage")
    ev.add_argument("--check-id")

    cu = sub.add_parser("record-change")
    cu.add_argument("--id", required=True)
    cu.add_argument("--path", action="append", required=True)

    args = parser.parse_args(argv)
    root = repo_root_from()

    if args.command == "start":
        if args.access_mode == "repo-wide" and not args.access_reason:
            start.error("--access-reason is required when --access-mode repo-wide")
        graph = init_graph(
            root,
            args.kind,
            args.statement,
            args.access_mode,
            scope_hint=args.scope_hint,
        )
        if args.access_mode == "repo-wide":
            _record_access_decision(graph, args.access_mode, args.access_reason)
            save_graph(root, graph)
        print(json.dumps({"run_id": graph.run_id, "stage": graph.stage, "access_mode": graph.access_mode}, indent=2))
        return

    if args.command == "status":
        graph = load_graph(root)
        print(json.dumps(_status(root, graph), indent=2))
        return

    if args.command == "next":
        graph = load_graph(root)
        next_stage = _next_stage(root, graph.stage)
        set_stage(root, graph, next_stage)
        print(json.dumps({"run_id": graph.run_id, "stage": next_stage}, indent=2))
        return

    if args.command == "set-stage":
        graph = load_graph(root)
        _record_stage_decision(graph, args.stage, args.reason)
        set_stage(root, graph, args.stage)
        save_graph(root, graph)
        print(json.dumps({"run_id": graph.run_id, "stage": args.stage}, indent=2))
        return

    if args.command == "set-access-mode":
        graph = load_graph(root)
        _record_access_decision(graph, args.access_mode, args.reason)
        set_access_mode(root, graph, args.access_mode, args.reason)
        print(json.dumps({"run_id": graph.run_id, "access_mode": args.access_mode}, indent=2))
        return

    if args.command == "alignment":
        graph = load_graph(root)
        alignment_record = _build_alignment(root, graph, args)
        graph.alignment = alignment_record
        save_graph(root, graph)
        append_journal(root, graph.run_id, "alignment.recorded", asdict(alignment_record))
        print(
            json.dumps(
                {
                    "run_id": graph.run_id,
                    "stage": graph.stage,
                    "risk": alignment_record.risk,
                    "decision": alignment_record.decision,
                    "open_question_count": len(alignment_record.open_questions),
                    "planned_path_count": len(alignment_record.planned_paths),
                },
                indent=2,
            )
        )
        return

    if args.command == "working-tree":
        report = audit_working_tree(root)
        print(json.dumps(report, indent=2))
        if report["blocking_findings"]:
            raise SystemExit(1)
        return

    if args.command == "adoption":
        _exit_if_component_manifest_invalid(root)
        if args.adoption_command == "component-status":
            print(json.dumps(_component_status(root), indent=2))
            return
        if args.adoption_command == "scope-check":
            issues = [
                *audit_local_scope(root, args.paths),
                *_unmapped_scope_issues(root, args.paths),
            ]
            _print_component_issues(issues)
            if any(issue.blocking for issue in issues):
                raise SystemExit(1)
            return
        print(_component_baseline_markdown(root))
        return

    if args.command == "invariants":
        graph = load_graph(root)
        results = evaluate(root, graph)
        print(json.dumps([item.__dict__ for item in results], indent=2))
        raise SystemExit(1 if blocking_failures(results) else 0)

    if args.command == "gates":
        exit_code = run_gates(root, args.name, args.timeout)
        if exit_code:
            raise SystemExit(exit_code)
        return

    if args.command == "audit":
        if args.audit_command == "traceability":
            issues = audit_traceability(root)
        else:
            issues = audit_coverage(root)
        _print_issues(issues)
        raise SystemExit(1 if issues else 0)

    if args.command == "impact":
        report = impact(root, args.files or None)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            _print_impact(report)
        return

    if args.command == "registry":
        if args.registry_command == "sync":
            _exit_if_component_manifest_invalid(root)
            print(json.dumps(sync_registry(root), indent=2))
            return
        issues = audit_registry(root)
        _print_issues(issues)
        raise SystemExit(1 if issues else 0)

    graph = load_graph(root)
    if args.command == "supersede-evidence":
        _supersede_evidence(graph, args.id, args.by, args.reason)
        save_graph(root, graph)
        append_journal(
            root,
            graph.run_id,
            "evidence.superseded",
            {"id": args.id, "by": args.by, "reason": args.reason},
        )
        print(json.dumps({"run_id": graph.run_id, "superseded": args.id, "by": args.by}, indent=2))
        return

    if args.command == "requirement":
        if args.requirement_command == "activate":
            try:
                row = activate_requirement(root, args.id, args.linked_test, args.verification)
            except ValueError as exc:
                raise SystemExit(str(exc)) from None
            append_journal(root, graph.run_id, "requirement.activated", row.to_dict())
            print(json.dumps(row.to_dict(), indent=2))
            return

    if args.command == "report":
        path = write_report(root, graph)
        print(render_report(root, graph))
        print(f"Report written: {path}")
        return

    if args.command == "delivery-preflight":
        results = evaluate(root, graph)
        invariant_failures = blocking_failures(results)
        traceability_issues = audit_traceability(root)
        coverage_issues = audit_coverage(root)
        registry_issues = audit_registry(root)
        component_issues = audit_components(root)
        working_tree_report = audit_working_tree(root, graph=graph)
        output = {
            "invariants": [item.__dict__ for item in results],
            "traceability_issues": [item.to_dict() for item in traceability_issues],
            "coverage_issues": [item.to_dict() for item in coverage_issues],
            "registry_issues": [item.to_dict() for item in registry_issues],
            "component_issues": [item.to_dict() for item in component_issues],
            "working_tree": working_tree_report,
        }
        print(json.dumps(output, indent=2))
        if (
            invariant_failures
            or traceability_issues
            or coverage_issues
            or registry_issues
            or component_issues
            or working_tree_report["blocking_findings"]
        ):
            raise SystemExit(1)
        print("Delivery preflight passed. Human approval is still required before PR/push.")
        return

    if args.command == "add-spec":
        if any(item.id == args.id for item in graph.spec_items):
            raise SystemExit(f"Spec id already exists: {args.id}")
        graph.spec_items.append(
            SpecItem(
                id=args.id,
                tag=args.tag,
                statement=args.statement,
                status=args.status,
                examples=args.example,
                threshold=args.threshold,
            )
        )
        save_graph(root, graph)
        print(f"Added spec {args.id}")
        return

    if args.command == "add-check":
        if any(item.id == args.id for item in graph.checks):
            raise SystemExit(f"Check id already exists: {args.id}")
        graph.checks.append(
            Check(
                id=args.id,
                level=args.level,
                cites_spec=args.cites_spec,
                cites_requirement=args.cites_requirement,
                command=args.check_command,
                path=args.path,
                state=args.state,
            )
        )
        save_graph(root, graph)
        print(f"Added check {args.id}")
        return

    if args.command == "record-evidence":
        evidence = Evidence(
            id=f"E-{len(graph.evidence) + 1:04d}",
            kind=args.kind,
            result=args.result,
            summary=args.summary,
            status=args.status,
            failure_kind=args.failure_kind,
            command=args.evidence_command,
            path=args.path,
            stage=args.stage or graph.stage,
        )
        if args.check_id:
            _link_check_evidence(graph, args.check_id, evidence)
        add_evidence(root, graph, evidence)
        print(f"Recorded evidence {evidence.id}")
        return

    if args.command == "record-change":
        graph.change_units.append(ChangeUnit(id=args.id, touched_paths=args.path))
        save_graph(root, graph)
        print(f"Recorded change unit {args.id}")
        return


# HELPER FUNCTIONS


def _status(root: Path, graph) -> dict:
    """
    @brief      Handle status workflow behavior.
    @param[in]  root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.3.0
    """
    results = evaluate(root, graph)
    return {
        "run_id": graph.run_id,
        "stage": graph.stage,
        "access_mode": graph.access_mode,
        "intent": graph.intent.__dict__,
        "alignment": asdict(graph.alignment) if graph.alignment else None,
        "spec_count": len(graph.spec_items),
        "check_count": len(graph.checks),
        "evidence_count": len(graph.evidence),
        "blocking_failures": [item.__dict__ for item in blocking_failures(results)],
    }


def _build_alignment(root: Path, graph, args) -> IntentAlignment:
    """
    @brief      Build and validate the intent-alignment record from CLI arguments.
    @param[in]  root Repository root.
    @param[in]  graph Active workflow graph.
    @param[in]  args Parsed command-line arguments.
    @return     Validated intent-alignment record.
    @exception  SystemExit Raised when policy requires a pause decision.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-03
    @version    0.2.0
    """
    if graph.stage not in {"alignment", "adoption-alignment"}:
        raise SystemExit("Intent alignment can only be recorded during alignment or adoption-alignment.")
    cfg = load_config(root)
    if not cfg.alignment_enabled:
        raise SystemExit("Intent alignment is disabled by .agentic/workflow.toml.")
    alignment_record = IntentAlignment(
        source=args.source,
        understanding=args.understanding,
        scope=args.scope,
        assumptions=args.assumption,
        acceptance=args.acceptance,
        open_questions=args.question,
        recommended_responses=args.recommended_response,
        risk=args.risk,
        decision=args.decision,
        reason=args.reason,
        planned_paths=args.planned_path,
    )
    pause_reasons = _alignment_pause_reasons(alignment_record, cfg)
    if alignment_record.decision == "proceed" and pause_reasons:
        raise SystemExit(f"Intent alignment policy requires decision pause: {'; '.join(pause_reasons)}")
    return alignment_record


def _alignment_pause_reasons(alignment_record: IntentAlignment, cfg: WorkflowConfig) -> list[str]:
    """
    @brief      Explain why an intent-alignment record must pause.
    @param[in]  alignment_record Intent-alignment record to evaluate.
    @param[in]  cfg Workflow configuration.
    @return     Human-readable pause reasons.
    @exception  SystemExit Raised when configured risk threshold is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-03
    @version    0.2.0
    """
    if cfg.alignment_risk_threshold not in ALIGNMENT_RISK_ORDER:
        raise SystemExit(
            "Invalid intent alignment risk threshold in .agentic/workflow.toml: "
            f"{cfg.alignment_risk_threshold}"
        )
    reasons = []
    unanswered_question_count = len(alignment_record.open_questions) - len(alignment_record.recommended_responses)
    if (
        cfg.alignment_pause_on_open_questions
        and alignment_record.open_questions
        and (
            not cfg.alignment_allow_recommended_responses
            or unanswered_question_count > 0
        )
    ):
        if cfg.alignment_allow_recommended_responses:
            reasons.append("open questions need recommended responses")
        else:
            reasons.append("open questions are present")
    if ALIGNMENT_RISK_ORDER[alignment_record.risk] >= ALIGNMENT_RISK_ORDER[cfg.alignment_risk_threshold]:
        reasons.append(f"risk {alignment_record.risk} meets threshold {cfg.alignment_risk_threshold}")
    protected_paths = _alignment_protected_paths(
        alignment_record.planned_paths,
        cfg.alignment_protected_scope_patterns,
    )
    if protected_paths:
        reasons.append(f"planned paths match protected scope: {', '.join(protected_paths)}")
    return reasons


def _alignment_protected_paths(planned_paths: list[str], patterns: list[str]) -> list[str]:
    """
    @brief      Collect planned paths matching configured protected-scope globs.
    @param[in]  planned_paths Planned repository-relative paths.
    @param[in]  patterns Protected path glob patterns.
    @return     Sorted matching planned paths.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-03
    @version    0.2.0
    """
    matches = set()
    normalized_patterns = [pattern.replace("\\", "/") for pattern in patterns]
    for path in planned_paths:
        normalized = path.replace("\\", "/")
        if any(fnmatch.fnmatch(normalized, pattern) for pattern in normalized_patterns):
            matches.add(path)
    return sorted(matches)


def _print_issues(issues) -> None:
    """
    @brief      Handle print issues workflow behavior.
    @param[in]  issues Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    if not issues:
        print("OK: no audit issues.")
        return
    for issue in issues:
        print(f"{issue.code}: {issue.message}")


def _print_component_issues(issues: list[ComponentIssue]) -> None:
    """
    @brief      Print component scope issues in a compact CLI format.
    @param[in]  issues Component issues to print.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-22
    @version    0.1.0
    """
    if not issues:
        print("OK: no component scope issues.")
        return
    for issue in issues:
        location = f" [{issue.path}]" if issue.path else ""
        subject = f" ({issue.name})" if issue.name else ""
        print(f"{issue.code}{subject}{location}: {issue.message}")


def _exit_if_component_manifest_invalid(root: Path) -> None:
    """
    @brief      Stop CLI commands when the component manifest is invalid.
    @param[in]  root Repository root.
    @return     None.
    @exception  SystemExit Raised when blocking manifest issues exist.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-22
    @version    0.1.0
    """
    issues = audit_components(root)
    if not any(issue.blocking for issue in issues):
        return
    _print_component_issues(issues)
    raise SystemExit(1)


def _component_status(root: Path) -> dict:
    """
    @brief      Build component and bundle status output.
    @param[in]  root Repository root.
    @return     JSON-serializable component status data.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-22
    @version    0.1.0
    """
    cfg = load_config(root)
    manifest = load_components(root, cfg.component_manifest)
    return asdict(manifest)


def _component_baseline_markdown(root: Path) -> str:
    """
    @brief      Render a concise Markdown component baseline summary.
    @param[in]  root Repository root.
    @return     Markdown baseline summary.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-22
    @version    0.1.0
    """
    status = _component_status(root)
    lines = ["# Component Baseline", "", "## Components"]
    components = status["components"]
    if not components:
        lines.append("- No components configured.")
    for name, component in sorted(components.items()):
        lines.append(f"- {name}: {component['adoption_status']} ({component['criticality']})")
    bundles = status["bundles"]
    if bundles:
        lines.extend(["", "## Bundles"])
        for name, bundle in sorted(bundles.items()):
            approved = "approved" if bundle["approved"] else "not approved"
            components_text = ", ".join(bundle["components"]) or "none"
            lines.append(f"- {name}: {bundle['adoption_status']} ({approved}; {components_text})")
    return "\n".join(lines)


def _unmapped_scope_issues(root: Path, paths: list[str]) -> list[ComponentIssue]:
    """
    @brief      Build informational issues for paths outside component patterns.
    @param[in]  root Repository root.
    @param[in]  paths Repository-relative paths to inspect.
    @return     Informational component issues.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-22
    @version    0.1.0
    """
    cfg = load_config(root)
    manifest = load_components(root, cfg.component_manifest)
    issues = []
    for path in paths:
        normalized = path.replace("\\", "/").strip()
        if component_for_path(manifest, normalized) is not None:
            continue
        issues.append(
            ComponentIssue(
                code="COMPONENT-UNMAPPED",
                message="Path is not covered by configured component patterns.",
                path=normalized,
                severity="info",
                blocking=False,
            )
        )
    return issues


def _print_impact(report) -> None:
    """
    @brief      Handle print impact workflow behavior.
    @param[in]  report Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    if not report:
        print("Impact: no changed files given and no Git working set found.")
        return
    for entry in report:
        flags = []
        if entry["uncovered"]:
            flags.append("UNCOVERED - author a requirement before coding")
        if entry["full_regression_recommended"]:
            flags.append("FULL REGRESSION RECOMMENDED")
        suffix = f" [{' ; '.join(flags)}]" if flags else ""
        print(f"{entry['file']}{suffix}")
        if not entry["requirements"]:
            print("  requirements: none")
        for row in entry["requirements"]:
            tests = ", ".join(row["linked_tests"]) or "no linked tests"
            print(f"  {row['req_id']} ({row['status']}) -> {tests}")


def _next_stage(root: Path, stage: str) -> str:
    """
    @brief      Handle next stage workflow behavior.
    @param[in]  root Repository root.
    @param[in]  stage Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.3.0
    """
    cfg = load_config(root)
    if stage == "intake" and not cfg.alignment_enabled:
        return "requirement"
    if stage == "adoption-intake" and not cfg.alignment_enabled:
        return "repo-discovery"
    stages = ADOPTION_STAGES if stage in ADOPTION_STAGES else STAGES
    index = stages.index(stage)
    if index == len(stages) - 1:
        return stage
    return stages[index + 1]


def _link_check_evidence(graph, check_id: str, evidence: Evidence) -> None:
    """
    @brief      Handle link check evidence workflow behavior.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  check_id Input value used by the workflow helper.
    @param[in]  evidence Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    for check in graph.checks:
        if check.id == check_id:
            if evidence.result == "fail":
                check.state = "red"
                check.red_evidence = evidence.id
            elif evidence.result == "pass":
                check.state = "green"
                check.green_evidence = evidence.id
            return
    raise SystemExit(f"Unknown check id: {check_id}")


def _record_access_decision(graph, access_mode: AccessMode, reason: str) -> None:
    """
    @brief      Handle record access decision workflow behavior.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  access_mode Input value used by the workflow helper.
    @param[in]  reason Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    graph.decisions.append(
        Decision(
            id=f"D-{len(graph.decisions) + 1:04d}",
            question="Workflow access mode",
            chosen=access_mode,
            rationale=reason,
        )
    )


def _record_stage_decision(graph, stage: str, reason: str) -> None:
    """
    @brief      Handle record stage decision workflow behavior.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  stage Input value used by the workflow helper.
    @param[in]  reason Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    graph.decisions.append(
        Decision(
            id=f"D-{len(graph.decisions) + 1:04d}",
            question="Workflow stage route",
            chosen=stage,
            rationale=reason,
        )
    )


def _supersede_evidence(graph, evidence_id: str, superseded_by: str, reason: str) -> None:
    """
    @brief      Handle supersede evidence workflow behavior.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  evidence_id Input value used by the workflow helper.
    @param[in]  superseded_by Input value used by the workflow helper.
    @param[in]  reason Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    evidence = {item.id: item for item in graph.evidence}
    if evidence_id not in evidence:
        raise SystemExit(f"Unknown evidence id: {evidence_id}")
    if superseded_by not in evidence:
        raise SystemExit(f"Unknown superseding evidence id: {superseded_by}")
    if evidence_id == superseded_by:
        raise SystemExit("Evidence cannot supersede itself.")
    evidence[evidence_id].status = "superseded"
    evidence[evidence_id].superseded_by = superseded_by
    evidence[evidence_id].supersede_reason = reason
    graph.decisions.append(
        Decision(
            id=f"D-{len(graph.decisions) + 1:04d}",
            question="Evidence superseded",
            chosen=f"{evidence_id} -> {superseded_by}",
            rationale=reason,
        )
    )


# END OF FILE
