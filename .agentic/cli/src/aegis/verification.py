#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file verification.py
@brief Consolidated deterministic verification orchestration.
@details Runs impact selection, every enabled gate group, invariants,
         traceability, coverage, and working-tree review before producing the
         human diff-review input summary.
@details Waived failures remain present and failed in the durable summary, are
         labeled separately from passes, and no longer contribute to the
         aggregate blocking exit status.
@details Quick runs keep gates, applicable invariants, path impact, secrets,
         scope, and working-tree review real while requirement-backed analysis
         is explicit N/A and does not load absent-stage storage.
@details A quick route is reported as bypassed only after human intake closure
         commits that lifecycle decision.
"""

# IMPORTS

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import GATE_ORDER, WorkflowConfig
from .errors import CommandInputError
from .gates import gate_failure_blockers, run_gates
from .invariants import blocking_failures, evaluate
from .models import Graph, now_iso
from .persistence import atomic_write_text
from .requirements import audit_coverage, audit_traceability, impact
from .stage_schema import run_stage_spec
from .store import append_journal, load_graph, run_dir
from .waiver_targets import annotate_audit_issues, annotate_working_tree
from .waivers import active_waiver, waiver_metadata
from .working_tree import audit_working_tree

# PUBLIC API


def quick_bypass_committed(graph: Graph) -> bool:
    """
    @brief Report whether human intake closure committed a quick-stage bypass.
    @param[in] graph Active workflow graph.
    @return ``True`` only after the quick route has advanced beyond intake.
    @details A later-stage record is accepted as the durable advancement
             fallback used by run status for previously persisted graphs.
    """
    stage_spec = run_stage_spec(graph)
    if not stage_spec.bypassed_stages:
        return False
    intake = graph.stage_records.get("intake")
    return bool(
        (intake and intake.closed_at)
        or any(
            stage in graph.stage_records
            for stage in stage_spec.stages[1:]
        )
    )


def run_verification(
    repo_root: Path,
    graph: Graph,
    config: WorkflowConfig,
) -> tuple[dict[str, Any], int]:
    """
    @brief      Execute the complete deterministic verification sequence.
    @param[in]  repo_root Repository root.
    @param[in]  graph Active workflow graph.
    @param[in]  config Validated workspace configuration.
    @return     Validation summary and aggregate exit code.
    """
    stage_spec = run_stage_spec(graph)
    quick = bool(stage_spec.bypassed_stages)
    impact_report = (
        _quick_impact(graph)
        if quick
        else impact(repo_root, None, config=config)
    )
    selection = _regression_selection(impact_report)
    gate_code = run_gates(
        repo_root,
        graph.run_id,
        config,
        list(GATE_ORDER),
    )
    graph = load_graph(repo_root, graph.run_id)
    stage_spec = run_stage_spec(graph)
    quick = bool(stage_spec.bypassed_stages)
    bypass_committed = quick_bypass_committed(graph)
    invariant_results = evaluate(repo_root, graph, config)
    working_tree_report = audit_working_tree(repo_root, config, graph)
    if quick:
        traceability = _quick_audit_not_applicable()
        coverage = _quick_audit_not_applicable()
        traceability_blockers = []
        coverage_blockers = []
    else:
        traceability, traceability_blockers = annotate_audit_issues(
            "traceability",
            audit_traceability(repo_root, config),
            graph,
        )
        coverage, coverage_blockers = annotate_audit_issues(
            "coverage",
            audit_coverage(repo_root, config),
            graph,
        )
    working_tree, working_tree_blockers = annotate_working_tree(
        working_tree_report,
        graph,
        repo_root,
    )
    gate_blockers = {
        blocker.id: blocker
        for blocker in gate_failure_blockers(graph, config)
    }
    gate_status = {
        name: _gate_status(
            graph,
            config,
            name,
            gate_blockers.get(f"gate:{name}"),
        )
        for name in GATE_ORDER
    }
    summary = {
        "schema_version": 3,
        "run_id": graph.run_id,
        "generated_at": now_iso(),
        "sequence": [
            "impact",
            "gates",
            "invariants",
            "traceability",
            "coverage",
            "working-tree",
        ],
        "regression_selection": selection,
        "impact": impact_report,
        "gates": gate_status,
        "security_note": (
            "The security gate reports only explicitly configured deterministic "
            "tooling and is not an authoritative security-assurance claim."
        ),
        "invariants": [item.to_dict() for item in invariant_results],
        "traceability": traceability,
        "coverage": coverage,
        "working_tree": working_tree,
        "human_diff_review": "pending",
    }
    if quick:
        summary["run_profile"] = "quick"
        if bypass_committed:
            summary.update(
                {
                    "bypass_status": "bypassed",
                    "bypassed_stages": list(stage_spec.bypassed_stages),
                }
            )
    any_waived = bool(
        any(item.waived for item in invariant_results)
        or any(item.get("waived") for item in traceability)
        or any(item.get("waived") for item in coverage)
        or any(
            item.get("waived")
            for item in working_tree["blocking_findings"]
        )
        or any(item.get("waived") for item in gate_status.values())
    )
    if any_waived:
        summary["waived"] = True
    path = validation_summary_path(repo_root, graph)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(summary, indent=2) + "\n")
    failed = bool(
        gate_code
        or blocking_failures(invariant_results)
        or traceability_blockers
        or coverage_blockers
        or working_tree_blockers
    )
    append_journal(
        repo_root,
        graph.run_id,
        "verification.completed",
        {
            "summary": path.relative_to(repo_root).as_posix(),
            "status": "failed" if failed else ("waived" if any_waived else "ok"),
        },
    )
    return summary, 1 if failed else 0


def validation_summary_path(repo_root: Path, graph: Graph) -> Path:
    """
    @brief      Return the durable validation summary path.
    @return     Run-local JSON summary path.
    """
    return run_dir(repo_root, graph.run_id) / "validation-summary.json"


def read_validation_summary(repo_root: Path, graph: Graph) -> dict[str, Any]:
    """
    @brief      Read the most recent validation summary.
    @exception  CommandInputError If the summary is missing or malformed.
    """
    path = validation_summary_path(repo_root, graph)
    if not path.is_file():
        raise CommandInputError("no validation summary; run `aegis verify run`")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CommandInputError(
            f"cannot load validation summary {path}: {exc}"
        ) from exc


# LOCAL HELPERS


def _quick_impact(graph: Graph) -> list[dict[str, Any]]:
    """
    @brief Render path-only impact for a run without requirement collection.
    @param[in] graph Quick-run graph containing declared changed paths.
    @return Stable impact rows with requirement-backed fields left empty.
    @details Declared paths still drive real regression-selection guidance,
             while absent requirement storage is neither loaded nor trusted.
    """
    changed_paths = sorted(
        {
            path
            for change_unit in graph.change_units
            for path in change_unit.touched_paths
        }
    )
    return [
        {
            "file": path,
            "uncovered": None,
            "coverage_status": "not-applicable",
            "requirements": [],
            "linked_tests": [],
            "full_regression_recommended": False,
        }
        for path in changed_paths
    ]


def _quick_audit_not_applicable() -> list[dict[str, str]]:
    """
    @brief Render one bypassed requirement audit as an honest third state.
    @return Single list-shaped N/A record preserving the summary field type.
    """
    return [
        {
            "status": "not-applicable",
            "message": "Not applicable - quick run.",
        }
    ]


def _regression_selection(report: list[dict[str, Any]]) -> dict[str, Any]:
    """@brief Select focused or full regression from traceability impact."""
    linked = sorted(
        {
            test
            for item in report
            for test in item.get("linked_tests", [])
        }
    )
    untraced = sorted(
        item["file"]
        for item in report
        if not item.get("requirements")
    )
    full = bool(
        untraced
        or any(item.get("full_regression_recommended") for item in report)
        or len(report) > 10
    )
    reasons: list[str] = []
    if untraced:
        reasons.append("untraced changed paths")
    if len(report) > 10:
        reasons.append("cross-cutting change set")
    if any(item.get("full_regression_recommended") for item in report):
        reasons.append("coverage policy recommends full regression")
    return {
        "mode": "full" if full else "focused",
        "linked_tests_first": linked,
        "full_regression_reasons": reasons,
        "untraced_paths": untraced,
    }


def _gate_status(
    graph: Graph,
    config: WorkflowConfig,
    name: str,
    blocker: Any | None,
) -> dict[str, Any]:
    """
    @brief Render one gate status without converting a waived failure to pass.
    @param[in] graph Authoritative graph containing gate evidence and waivers.
    @param[in] config Validated gate policy.
    @param[in] name Gate group name.
    @param[in] blocker Current exact failing-gate target, when present.
    @return Stable status/commands mapping with conditional waiver metadata.
    """
    group = getattr(config.gates, name)
    status = "disabled" if group.mode == "disabled" else _gate_result(graph, name)
    payload: dict[str, Any] = {
        "status": status,
        "commands": list(group.commands),
    }
    waiver = active_waiver(graph, blocker) if blocker is not None else None
    if status == "failed" and waiver is not None:
        payload["status"] = "waived"
        payload["failure_status"] = "failed"
        payload["waived"] = True
        payload["waivers"] = [waiver_metadata(waiver)]
    return payload


def _gate_result(graph: Graph, name: str) -> str:
    """@brief Summarize active evidence for one enforced gate group."""
    evidence = [
        item
        for item in graph.evidence
        if item.kind == "gate"
        and item.gate_name == name
        and item.status == "active"
    ]
    if not evidence:
        return "not-run"
    return "failed" if any(item.result == "fail" for item in evidence) else "passed"


# END OF FILE
