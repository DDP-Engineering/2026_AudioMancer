# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.

from __future__ import annotations

from pathlib import Path

from .invariants import evaluate
from .models import Graph
from .requirements import audit_coverage, audit_registry, audit_traceability


def render_report(repo_root: Path, graph: Graph) -> str:
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
        "## Spec Items",
    ]
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
        lines.append(
            "- PASS: traceability, coverage, and registry audits have no findings."
        )
    for issue in traceability_issues:
        lines.append(f"- `{issue.code}` {issue.message}")
    for issue in coverage_issues:
        lines.append(f"- `{issue.code}` {issue.message}")
    for issue in registry_issues:
        lines.append(f"- `{issue.code}` {issue.message}")

    lines.extend(["", "## Next Prompts"])
    lines.append("- Continue the next manual gate after reviewing the report.")
    lines.append("- Ask Codex to create or update missing artifacts named above.")
    lines.append(
        "- When ready for delivery, prompt: `Create PR for this agentic workflow run`."
    )
    lines.append("")
    return "\n".join(lines)


def write_report(repo_root: Path, graph: Graph) -> Path:
    path = repo_root / ".agentic" / "runs" / graph.run_id / "report.md"
    path.write_text(render_report(repo_root, graph), encoding="utf-8")
    return path
