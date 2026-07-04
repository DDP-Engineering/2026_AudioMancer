#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file report.py
@brief Markdown report rendering for workflow runs.
@details Mirrors the packaged CLI implementation shipped into generated projects.
@author Eng. Dan Dumitru Pasare
@date 2026-06-20
@version 0.4.0
"""

# IMPORTS

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .components import audit_local_scope, load_components
from .config import load_config
from .invariants import evaluate
from .models import Graph
from .requirements import audit_coverage, audit_registry, audit_traceability


def render_report(repo_root: Path, graph: Graph) -> str:
    """
    @brief      Render render report workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.4.0
    """
    results = evaluate(repo_root, graph)
    traceability_issues = audit_traceability(repo_root)
    coverage_issues = audit_coverage(repo_root)
    registry_issues = audit_registry(repo_root)
    lines = [
        f"# Agentic Workflow Report: {graph.run_id}",
        "",
        f"- Stage: `{graph.stage}`",
        f"- Access mode: `{graph.access_mode}`",
        f"- Intent: `{graph.intent.id}` {graph.intent.kind} - {graph.intent.statement}",
        "",
        "## Intent Alignment",
    ]
    if graph.alignment:
        alignment = graph.alignment
        lines.append(f"- Source: {alignment.source}")
        lines.append(f"- Understanding: {alignment.understanding}")
        lines.append(f"- Risk: `{alignment.risk}`")
        lines.append(f"- Decision: `{alignment.decision}` - {alignment.reason}")
        lines.append(f"- Scope: {'; '.join(alignment.scope)}")
        lines.append(f"- Acceptance: {'; '.join(alignment.acceptance)}")
        lines.append(f"- Assumptions: {'; '.join(alignment.assumptions) if alignment.assumptions else 'none'}")
        lines.append(f"- Open questions: {'; '.join(alignment.open_questions) if alignment.open_questions else 'none'}")
        lines.append(
            "- Recommended responses: "
            f"{'; '.join(alignment.recommended_responses) if alignment.recommended_responses else 'none'}"
        )
        if alignment.planned_paths:
            lines.append(f"- Planned paths: {', '.join(alignment.planned_paths)}")
    else:
        lines.append("- None recorded.")

    lines.extend([
        "",
        "## Spec Items",
    ])
    if graph.spec_items:
        for item in graph.spec_items:
            lines.append(f"- `{item.id}` [{item.tag}] {item.status}: {item.statement}")
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Checks"])
    if graph.checks:
        for check in graph.checks:
            cites = ", ".join(check.cites_spec)
            lines.append(f"- `{check.id}` {check.state}; cites {cites}")
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Evidence"])
    if graph.evidence:
        for item in graph.evidence:
            lines.append(f"- `{item.id}` {item.kind}/{item.result}: {item.summary}")
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Invariants"])
    for item in results:
        marker = "PASS" if item.holds else "FAIL"
        lines.append(f"- `{item.id}` {marker} ({item.policy}): {item.message}")

    lines.extend(["", "## Traceability Audits"])
    if not traceability_issues and not coverage_issues and not registry_issues:
        lines.append("- PASS: traceability, coverage, and registry audits have no findings.")
    for issue in traceability_issues:
        lines.append(f"- `{issue.code}` {issue.message}")
    for issue in coverage_issues:
        lines.append(f"- `{issue.code}` {issue.message}")
    for issue in registry_issues:
        lines.append(f"- `{issue.code}` {issue.message}")

    adoption_lines = _render_adoption_baseline(repo_root, graph)
    if adoption_lines:
        lines.extend(["", *adoption_lines])

    lines.extend(["", "## Next Prompts"])
    lines.append("- Continue the next manual gate after reviewing the report.")
    lines.append("- Ask the agent to create or update missing artifacts named above.")
    lines.append("- When ready for delivery, prompt: `Create PR for this agentic workflow run`.")
    lines.append("")
    return "\n".join(lines)


def write_report(repo_root: Path, graph: Graph) -> Path:
    """
    @brief      Write report workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    path = repo_root / ".agentic" / "runs" / graph.run_id / "report.md"
    path.write_text(render_report(repo_root, graph), encoding="utf-8")
    return path


def _render_adoption_baseline(repo_root: Path, graph: Graph) -> list[str]:
    """
    @brief      Render adoption baseline details when relevant to a run.
    @param[in]  repo_root Repository root.
    @param[in]  graph Workflow graph.
    @return     Markdown lines for the adoption section, or an empty list.
    @exception  tomllib.TOMLDecodeError Raised when component TOML is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-22
    @version    0.1.0
    """
    cfg = load_config(repo_root)
    manifest = load_components(repo_root, cfg.component_manifest)
    if graph.intent.kind != "adoption" and not manifest.components:
        return []

    lines = [
        "## Adoption Baseline",
        f"- Component manifest: `{cfg.component_manifest}`",
        f"- Minimum baseline: `{cfg.adoption_default_completion_level}`",
        f"- Adoption report root: `{cfg.adoption_report_root}`",
        "",
        "### Component Status Counts",
    ]
    if manifest.components:
        counts = Counter(component.adoption_status for component in manifest.components.values())
        for status, count in sorted(counts.items()):
            lines.append(f"- `{status}`: {count}")
    else:
        lines.append("- No components configured.")

    lines.extend(["", "### Components"])
    if manifest.components:
        for name, component in sorted(manifest.components.items()):
            tests = ", ".join(component.tests) if component.tests else "no tests mapped"
            lines.append(f"- `{name}`: {component.adoption_status}; paths {', '.join(component.paths) or 'none'}; tests {tests}")
    else:
        lines.append("- No components configured.")

    touched_paths = _touched_paths(graph)
    if touched_paths:
        lines.extend(["", "### Local Scope Findings"])
        issues = audit_local_scope(repo_root, touched_paths, cfg.adoption_default_completion_level)
        if issues:
            for issue in issues:
                location = f" [{issue.path}]" if issue.path else ""
                subject = f" ({issue.name})" if issue.name else ""
                lines.append(f"- `{issue.code}`{subject}{location}: {issue.message}")
        else:
            lines.append("- No local-scope findings for touched paths.")
    return lines


def _touched_paths(graph: Graph) -> list[str]:
    """
    @brief      Collect touched paths from change units.
    @param[in]  graph Workflow graph.
    @return     Sorted unique repository-relative paths.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-22
    @version    0.1.0
    """
    return sorted({path for unit in graph.change_units for path in unit.touched_paths})
