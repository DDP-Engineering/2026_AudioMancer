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
@details Renders schema-3 stage state, durable requirements, solution design,
         checks, evidence, verification records, and adoption baseline data.
@details Waived failures remain visibly failed and render as ``WAIVED`` with
         their human reason and timestamp.
@details Quick runs render requirement-backed state explicitly as not
         applicable without loading absent-stage storage; bypass is never
         reported as a successful check or before human intake closure.
"""

# IMPORTS

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .components import audit_local_scope, load_components
from .config import WorkflowConfig
from .gates import gate_failure_blockers
from .invariants import evaluate
from .models import Graph, Waiver
from .requirement_store import load_all_requirement_records
from .requirements import audit_coverage, audit_traceability
from .stage_forms import next_command
from .stage_schema import run_stage_spec
from .waiver_targets import (
    audit_issue_blocker,
    collect_waiver_targets,
    waiver_record_statuses,
)
from .waivers import active_waiver
from .verification import quick_bypass_committed, validation_summary_path

# PUBLIC API


def render_report(
    repo_root: Path, graph: Graph, config: WorkflowConfig
) -> str:
    """
    @brief      Render a complete Markdown report for the active workflow graph.
    @param[in]  repo_root Repository root the report reads run and component
                data from.
    @param[in]  graph Active workflow graph the report describes.
    @param[in]  config Validated workflow configuration.
    @return     Complete Markdown report text.
    @exception  CommandInputError If the adoption baseline section's component
                manifest TOML is invalid.
    """
    stage_spec = run_stage_spec(graph)
    quick = bool(stage_spec.bypassed_stages)
    bypass_committed = quick_bypass_committed(graph)
    results = evaluate(repo_root, graph, config)
    traceability_issues = [] if quick else audit_traceability(repo_root, config)
    coverage_issues = [] if quick else audit_coverage(repo_root, config)
    gate_blockers = {
        blocker.id: blocker
        for blocker in gate_failure_blockers(graph, config)
    }
    lines = [
        f"# AEGIS Report: {graph.run_id}",
        "",
        f"- Stage: `{graph.stage}`",
        f"- Access mode: `{graph.access_mode}`",
        f"- Intent: `{graph.intent.id}` {graph.intent.kind} - {graph.intent.statement}",
    ]
    if bypass_committed:
        lines.append(
            "- Quick run - stages bypassed: "
            + ", ".join(stage_spec.bypassed_stages)
        )
    lines.extend(["", "## Intent Alignment"])
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
        "## Stage Lifecycle",
    ])
    if graph.stage_records:
        for stage, record in graph.stage_records.items():
            lines.append(
                f"- `{stage}` revision {record.revision}: `{record.status}`; "
                f"retention `{record.retention}`; check execution "
                f"`{record.check_execution}`"
            )
    else:
        lines.append("- No stage records.")

    lines.extend(["", "## Requirements"])
    requirements = (
        []
        if quick
        else load_all_requirement_records(repo_root, config)
    )
    if quick:
        lines.append("- NOT APPLICABLE: Not applicable - quick run.")
    elif requirements:
        for requirement in requirements:
            lines.append(
                f"- `{requirement.id}` {requirement.status}: "
                f"{requirement.requirement}"
            )
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Solution Design"])
    if graph.design:
        design = graph.design
        lines.extend(
            [
                f"- Revision: {design.revision}",
                f"- Status: `{design.status}`",
                f"- Approval: `{design.approval}`",
                f"- Document: `{design.document_path}`",
                f"- Selected option: {design.selected_option or 'none'}",
                "- Cited requirements: "
                + (", ".join(f"`{item}`" for item in design.requirement_digests) or "none"),
                "- Open questions: "
                + ("; ".join(design.open_questions) or "none"),
            ]
        )
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Checks"])
    if graph.checks:
        for check in graph.checks:
            cites = ", ".join(check.cites_requirement)
            lines.append(
                f"- `{check.id}` {check.state}; requirements {cites}; "
                f"command `{check.command}`"
            )
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Evidence"])
    if graph.evidence:
        for item in graph.evidence:
            failure_kind = f" ({item.failure_kind})" if item.failure_kind else ""
            gate_blocker = (
                gate_blockers.get(f"gate:{item.gate_name}")
                if item.gate_name
                else None
            )
            waiver = (
                active_waiver(graph, gate_blocker)
                if item.kind == "gate"
                and item.result == "fail"
                and gate_blocker is not None
                else None
            )
            waiver_text = f"; {_waiver_text(waiver)}" if waiver else ""
            lines.append(
                f"- `{item.id}` {item.kind}/{item.result}{failure_kind}: "
                f"{item.summary}{waiver_text}"
            )
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Invariants"])
    for item in results:
        if item.status == "not-applicable":
            marker = "NOT APPLICABLE"
        elif item.holds:
            marker = "PASS"
        elif item.waived:
            marker = "WAIVED"
        else:
            marker = "FAIL"
        waiver_text = (
            " " + "; ".join(_waiver_text(waiver) for waiver in item.waivers)
            if item.waived
            else ""
        )
        lines.append(
            f"- `{item.id}` {marker} ({item.effective_policy}): "
            f"{item.message}{waiver_text}"
        )

    lines.extend(["", "## Traceability Audits"])
    if quick:
        lines.append("- NOT APPLICABLE: Not applicable - quick run.")
    elif not traceability_issues and not coverage_issues:
        lines.append("- PASS: live traceability and coverage audits have no findings.")
    for issue in traceability_issues:
        waiver = active_waiver(
            graph,
            audit_issue_blocker("traceability", issue),
        )
        marker = " WAIVED" if waiver else ""
        suffix = f" {_waiver_text(waiver)}" if waiver else ""
        lines.append(f"- `{issue.code}`{marker} {issue.message}{suffix}")
    for issue in coverage_issues:
        waiver = active_waiver(
            graph,
            audit_issue_blocker("coverage", issue),
        )
        marker = " WAIVED" if waiver else ""
        suffix = f" {_waiver_text(waiver)}" if waiver else ""
        lines.append(f"- `{issue.code}`{marker} {issue.message}{suffix}")

    validation_path = validation_summary_path(repo_root, graph)
    lines.extend(["", "## Deterministic Verification"])
    if validation_path.is_file():
        lines.append(
            f"- Validation summary: "
            f"`{validation_path.relative_to(repo_root).as_posix()}`"
        )
    else:
        lines.append("- Not yet run. Use `aegis verify run` during validation.")

    if graph.waivers:
        lines.extend(["", "## Waivers"])
        targets = collect_waiver_targets(repo_root, graph, config)
        for item in waiver_record_statuses(graph, targets):
            marker = "WAIVED" if item["status"] == "active" else item["status"].upper()
            lines.append(
                f"- `{item['blocker_id']}` {marker} by `{item['id']}` at "
                f"`{item['created_at']}`: {item['reason']}"
            )

    adoption_lines = _render_adoption_baseline(repo_root, graph, config)
    if adoption_lines:
        lines.extend(["", *adoption_lines])

    lines.extend(["", "## Handoff"])
    lines.append(f"- Next command: `{next_command(graph, repo_root)}`")
    lines.append(
        "- Delivery closure records the human handoff decision only; it does "
        "not push, publish, merge, or create a pull request."
    )
    lines.append("")
    return "\n".join(lines)


def write_report(repo_root: Path, graph: Graph, rendered: str) -> Path:
    """
    @brief      Write the rendered report to its run-local file.
    @param[in]  repo_root Repository root the run directory is under.
    @param[in]  graph Workflow graph identifying the run.
    @param[in]  rendered Complete report text rendered with the operation config.
    @return     Path of the written report file.
    @exception  OSError If the report file cannot be written.
    """
    path = repo_root / ".agentic" / "runs" / graph.run_id / "report.md"
    path.write_text(rendered, encoding="utf-8")
    return path


# HELPER FUNCTIONS


def _waiver_text(waiver: Waiver) -> str:
    """
    @brief Render the reason and timestamp for one active waiver.
    @param[in] waiver Human-approved waiver record.
    @return Concise Markdown-safe waiver description.
    """
    return (
        f"WAIVED by `{waiver.id}` at `{waiver.created_at}`: "
        f"{waiver.reason}"
    )


def _render_adoption_baseline(
    repo_root: Path, graph: Graph, config: WorkflowConfig
) -> list[str]:
    """
    @brief      Render adoption baseline details when relevant to a run.
    @param[in]  repo_root Repository root.
    @param[in]  graph Workflow graph.
    @param[in]  config Validated workflow configuration.
    @return     Markdown lines for the adoption section, or an empty list.
    @exception  CommandInputError Raised when the component manifest TOML is
                invalid.
    """
    manifest = load_components(repo_root, config.component_manifest)
    if graph.intent.kind != "adoption" and not manifest.components:
        return []

    lines = [
        "## Adoption Baseline",
        f"- Component manifest: `{config.component_manifest}`",
        "- Minimum baseline: "
        f"`{config.component_baseline_guard.minimum_completion_level}`",
        f"- Adoption report root: `{config.adoption_report_root}`",
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
        issues = audit_local_scope(
            repo_root,
            touched_paths,
            config,
            config.component_baseline_guard.minimum_completion_level,
        )
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
    """
    return sorted({path for unit in graph.change_units for path in unit.touched_paths})


# END OF FILE
