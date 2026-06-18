# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .gates import run_gates
from .invariants import blocking_failures, evaluate
from .models import AccessMode, Check, ChangeUnit, Decision, Evidence, SpecItem, STAGES
from .requirements import (
    audit_coverage,
    audit_registry,
    audit_traceability,
    impact,
    sync_registry,
)
from .report import render_report, write_report
from .store import (
    add_evidence,
    init_graph,
    load_graph,
    repo_root_from,
    save_graph,
    set_access_mode,
    set_stage,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="agentic-workflow")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("--kind", choices=["feature", "fix", "change"], required=True)
    start.add_argument("--statement", required=True)
    start.add_argument(
        "--access-mode", choices=["standard", "repo-wide"], default="standard"
    )
    start.add_argument("--access-reason")

    sub.add_parser("status")
    sub.add_parser("next")
    sub.add_parser("invariants")
    sub.add_parser("report")
    sub.add_parser("delivery-preflight")

    access = sub.add_parser("set-access-mode")
    access.add_argument("access_mode", choices=["standard", "repo-wide"])
    access.add_argument("--reason", required=True)

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

    gates = sub.add_parser("gates")
    gates.add_argument("action", choices=["run"])
    gates.add_argument("--name", action="append")
    gates.add_argument("--timeout", type=int, default=300)

    spec = sub.add_parser("add-spec")
    spec.add_argument("--id", required=True)
    spec.add_argument("--tag", choices=["behavior", "property"], required=True)
    spec.add_argument("--statement", required=True)
    spec.add_argument(
        "--status",
        default="accepted",
        choices=["proposed", "accepted", "realized", "retired"],
    )
    spec.add_argument("--example", action="append", default=[])
    spec.add_argument("--threshold")

    check = sub.add_parser("add-check")
    check.add_argument("--id", required=True)
    check.add_argument("--level", default="test")
    check.add_argument("--cites-spec", action="append", required=True)
    check.add_argument("--command", dest="check_command")
    check.add_argument("--path")
    check.add_argument(
        "--state", choices=["red", "green", "unknown"], default="unknown"
    )

    ev = sub.add_parser("record-evidence")
    ev.add_argument(
        "--kind",
        choices=["test-run", "diff", "scan", "gate", "decision", "note"],
        required=True,
    )
    ev.add_argument("--result", choices=["pass", "fail", "info"], required=True)
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
        graph = init_graph(root, args.kind, args.statement, args.access_mode)
        if args.access_mode == "repo-wide":
            _record_access_decision(graph, args.access_mode, args.access_reason)
            save_graph(root, graph)
        print(
            json.dumps(
                {
                    "run_id": graph.run_id,
                    "stage": graph.stage,
                    "access_mode": graph.access_mode,
                },
                indent=2,
            )
        )
        return

    if args.command == "status":
        graph = load_graph(root)
        print(json.dumps(_status(root, graph), indent=2))
        return

    if args.command == "next":
        graph = load_graph(root)
        next_stage = _next_stage(graph.stage)
        set_stage(root, graph, next_stage)
        print(json.dumps({"run_id": graph.run_id, "stage": next_stage}, indent=2))
        return

    if args.command == "set-access-mode":
        graph = load_graph(root)
        _record_access_decision(graph, args.access_mode, args.reason)
        set_access_mode(root, graph, args.access_mode, args.reason)
        print(
            json.dumps(
                {"run_id": graph.run_id, "access_mode": args.access_mode}, indent=2
            )
        )
        return

    if args.command == "invariants":
        graph = load_graph(root)
        results = evaluate(root, graph)
        print(json.dumps([item.__dict__ for item in results], indent=2))
        raise SystemExit(1 if blocking_failures(results) else 0)

    if args.command == "gates":
        raise SystemExit(run_gates(root, args.name, args.timeout))

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
            print(json.dumps(sync_registry(root), indent=2))
            return
        issues = audit_registry(root)
        _print_issues(issues)
        raise SystemExit(1 if issues else 0)

    graph = load_graph(root)
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
        output = {
            "invariants": [item.__dict__ for item in results],
            "traceability_issues": [item.to_dict() for item in traceability_issues],
            "coverage_issues": [item.to_dict() for item in coverage_issues],
            "registry_issues": [item.to_dict() for item in registry_issues],
        }
        print(json.dumps(output, indent=2))
        if (
            invariant_failures
            or traceability_issues
            or coverage_issues
            or registry_issues
        ):
            raise SystemExit(1)
        print(
            "Delivery preflight passed. Human approval is still required before PR/push."
        )
        return

    if args.command == "add-spec":
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
        graph.checks.append(
            Check(
                id=args.id,
                level=args.level,
                cites_spec=args.cites_spec,
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


def _status(root: Path, graph) -> dict:
    results = evaluate(root, graph)
    return {
        "run_id": graph.run_id,
        "stage": graph.stage,
        "access_mode": graph.access_mode,
        "intent": graph.intent.__dict__,
        "spec_count": len(graph.spec_items),
        "check_count": len(graph.checks),
        "evidence_count": len(graph.evidence),
        "blocking_failures": [item.__dict__ for item in blocking_failures(results)],
    }


def _print_issues(issues) -> None:
    if not issues:
        print("OK: no audit issues.")
        return
    for issue in issues:
        print(f"{issue.code}: {issue.message}")


def _print_impact(report) -> None:
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


def _next_stage(stage: str) -> str:
    index = STAGES.index(stage)
    if index == len(STAGES) - 1:
        return stage
    return STAGES[index + 1]


def _link_check_evidence(graph, check_id: str, evidence: Evidence) -> None:
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
    graph.decisions.append(
        Decision(
            id=f"D-{len(graph.decisions) + 1:04d}",
            question="Workflow access mode",
            chosen=access_mode,
            rationale=reason,
        )
    )
