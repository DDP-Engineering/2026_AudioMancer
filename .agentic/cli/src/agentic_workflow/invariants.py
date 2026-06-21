#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file invariants.py
@brief Invariant checks for agentic workflow delivery readiness.
@details Provides reusable implementation behavior for the standalone workflow template.
@author Eng. Dan Dumitru Pasare
@date 2026-06-20
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
from pathlib import Path

from .config import WorkflowConfig, load_config
from .models import Graph
from .paths import is_allowed_path
from .requirements import load_all_requirements


@dataclass
class InvariantResult:
    """
    @brief      Represent InvariantResult data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    id: str
    name: str
    holds: bool
    policy: str
    message: str


def evaluate(repo_root: Path, graph: Graph, config: WorkflowConfig | None = None) -> list[InvariantResult]:
    """
    @brief      Evaluate workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  config Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    cfg = config or load_config(repo_root)
    return [
        _coverage(graph),
        _citation(graph),
        _red_before_green(graph),
        _no_regression(graph),
        _in_scope(repo_root, graph, cfg),
        _evidence(graph),
        _clean_secrets(repo_root, cfg),
        _green_requirements_active(repo_root, graph, cfg),
    ]


def blocking_failures(results: list[InvariantResult]) -> list[InvariantResult]:
    """
    @brief      Collect blocking failures workflow behavior.
    @param[in]  results Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return [item for item in results if item.policy in {"blocking", "non-waivable"} and not item.holds]


def _coverage(graph: Graph) -> InvariantResult:
    """
    @brief      Handle coverage workflow behavior.
    @param[in]  graph Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    accepted = [item for item in graph.spec_items if item.status in {"accepted", "realized"}]
    covered_ids = {spec for check in graph.checks for spec in check.cites_spec}
    missing = [item.id for item in accepted if item.id not in covered_ids]
    return InvariantResult(
        "INV-1",
        "Coverage",
        not missing,
        "blocking",
        "All accepted/realized spec items have checks." if not missing else f"Missing checks for: {', '.join(missing)}",
    )


def _citation(graph: Graph) -> InvariantResult:
    """
    @brief      Handle citation workflow behavior.
    @param[in]  graph Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    spec_ids = {item.id for item in graph.spec_items}
    bad = [
        check.id
        for check in graph.checks
        if not check.cites_spec or any(spec not in spec_ids for spec in check.cites_spec)
    ]
    return InvariantResult(
        "INV-2",
        "Citation",
        not bad,
        "blocking",
        "All checks cite existing spec items." if not bad else f"Bad check citations: {', '.join(bad)}",
    )


def _red_before_green(graph: Graph) -> InvariantResult:
    """
    @brief      Handle red before green workflow behavior.
    @param[in]  graph Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    missing = [
        check.id
        for check in graph.checks
        if check.state == "green" and not check.red_evidence
    ]
    return InvariantResult(
        "INV-3",
        "Red-before-green",
        not missing,
        "blocking",
        "Green checks have prior red evidence." if not missing else f"Missing red evidence for: {', '.join(missing)}",
    )


def _no_regression(graph: Graph) -> InvariantResult:
    """
    @brief      Handle no regression workflow behavior.
    @param[in]  graph Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    failed_gates = [
        item.id
        for item in graph.evidence
        if item.kind in {"gate", "test-run"} and item.stage in {"implementation", "validation", "delivery"} and item.result == "fail"
        and item.status != "superseded"
    ]
    return InvariantResult(
        "INV-4",
        "No regression",
        not failed_gates,
        "blocking",
        "No failing implementation/validation/delivery gate evidence." if not failed_gates else f"Failing gate evidence: {', '.join(failed_gates)}",
    )


def _green_requirements_active(repo_root: Path, graph: Graph, cfg: WorkflowConfig) -> InvariantResult:
    """
    @brief      Handle green requirements active workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  cfg Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    cited = sorted({req_id for check in graph.checks if check.state == "green" for req_id in check.cites_requirement})
    if not cited:
        return InvariantResult("INV-8", "Green requirements active", True, "blocking", "No green checks cite durable requirements.")
    rows = {row.req_id: row for row in load_all_requirements(repo_root, cfg)}
    missing = [req_id for req_id in cited if req_id not in rows]
    planned = [req_id for req_id in cited if req_id in rows and rows[req_id].status != "Active"]
    failures = [*missing, *planned]
    if not failures:
        return InvariantResult("INV-8", "Green requirements active", True, "blocking", "Green requirement-linked checks cite Active requirements.")
    parts = []
    if missing:
        parts.append(f"missing rows: {', '.join(missing)}")
    if planned:
        parts.append(f"not Active: {', '.join(planned)}")
    return InvariantResult("INV-8", "Green requirements active", False, "blocking", "; ".join(parts))


def _in_scope(repo_root: Path, graph: Graph, cfg: WorkflowConfig) -> InvariantResult:
    """
    @brief      Handle in scope workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  cfg Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    touched = [path for unit in graph.change_units for path in unit.touched_paths]
    if not touched:
        return InvariantResult("INV-5", "In scope", True, "advisory", "No change units recorded yet.")
    allowed = []
    allowed.extend(cfg.source_roots)
    allowed.extend(cfg.test_roots)
    allowed.extend(cfg.documentation_roots)
    allowed.extend(graph.intent.scope_hint)
    bad = [path for path in touched if not is_allowed_path(path, repo_root, _root_patterns(allowed))]
    return InvariantResult(
        "INV-5",
        "In scope",
        not bad,
        "advisory",
        "Touched paths are in configured scope." if not bad else f"Out-of-scope paths: {', '.join(bad)}",
    )


def _evidence(graph: Graph) -> InvariantResult:
    """
    @brief      Handle evidence workflow behavior.
    @param[in]  graph Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    has_evidence = bool(graph.evidence)
    return InvariantResult(
        "INV-6",
        "Evidence",
        has_evidence,
        "blocking",
        "Run has recorded evidence." if has_evidence else "No evidence recorded yet.",
    )


def _clean_secrets(repo_root: Path, cfg: WorkflowConfig) -> InvariantResult:
    """
    @brief      Handle clean secrets workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  cfg Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    patterns = cfg.secret_patterns
    if not patterns:
        return InvariantResult("INV-7", "Clean secrets", True, "non-waivable", "No secret patterns configured.")
    try:
        diff = subprocess.run(
            ["git", "diff", "--no-ext-diff"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return InvariantResult("INV-7", "Clean secrets", False, "non-waivable", "Could not inspect git diff for secrets.")
    matches = []
    for pattern in patterns:
        if re.search(pattern, diff):
            matches.append(pattern)
    return InvariantResult(
        "INV-7",
        "Clean secrets",
        not matches,
        "non-waivable",
        "No configured secret pattern found in diff." if not matches else f"Secret pattern matched: {', '.join(matches)}",
    )


def _root_patterns(roots: list[str]) -> list[str]:
    """
    @brief      Handle root patterns workflow behavior.
    @param[in]  roots Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    patterns = []
    for root in roots:
        normalized = root.replace("\\", "/").rstrip("/")
        if any(char in normalized for char in "*?["):
            patterns.append(normalized)
        else:
            patterns.append(f"{normalized}/**")
    return patterns
