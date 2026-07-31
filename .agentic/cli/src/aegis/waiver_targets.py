#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file waiver_targets.py
@brief Discover and annotate exact run-local process waiver targets.
@details Unifies stage, invariant, gate, audit, and working-tree blockers while
         preserving failed result shapes unless an exact active waiver applies.
@details Requirement traceability and coverage audits are not waiver targets
         for quick runs because their collection stages are explicitly bypassed.
"""

# IMPORTS

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from .config import WorkflowConfig
from .gates import gate_failure_blockers
from .invariants import evaluate
from .models import Graph
from .requirements import AuditIssue, audit_coverage, audit_traceability
from .stage_forms import stage_blocker_details
from .stage_schema import run_stage_spec
from .waivers import (
    Blocker,
    active_waiver,
    current_file_digest,
    state_digests,
    waiver_metadata,
)
from .working_tree import audit_working_tree

# CONSTANTS

SHORT_MESSAGE_DIGEST_LENGTH = 12

# PUBLIC API


def audit_issue_blocker(kind: str, issue: AuditIssue) -> Blocker:
    """
    @brief Build one exact traceability or coverage waiver target.
    @param[in] kind Stable audit namespace, such as traceability or coverage.
    @param[in] issue Concrete current audit finding.
    @return Digest-pinned blocker identified by audit kind, code, and subject.
    """
    identity = {
        "code": issue.code,
        "message": issue.message,
        "req_id": issue.req_id,
        "path": issue.path,
    }
    subject = issue.req_id or issue.path or _short_message_digest(issue.message)
    selector = next(
        iter(state_digests("audit-finding-identity", identity).values())
    )[:SHORT_MESSAGE_DIGEST_LENGTH]
    blocker_id = f"{kind}:{issue.code}:{subject}:{selector}"
    return Blocker(
        id=blocker_id,
        description=issue.message,
        state_digests=state_digests(blocker_id, identity),
    )


def working_tree_blocker(
    finding: dict[str, Any],
    repo_root: Path | None = None,
) -> Blocker:
    """
    @brief Build one exact working-tree finding waiver target.
    @param[in] finding Complete current blocking-finding mapping.
    @param[in] repo_root Optional repository root; when provided, secret
               findings additionally pin the flagged file's current content so
               a NEW secret matching an already-waived pattern stales the
               waiver instead of riding it.
    @return Digest-pinned blocker whose state covers the complete finding.
    """
    code = str(finding.get("code", "unknown"))
    message = str(finding.get("message", ""))
    path = str(finding.get("path", ""))
    subject = path or _short_message_digest(message)
    payload = dict(finding)
    if code == "secret-pattern" and path and repo_root is not None:
        payload["content_sha256"] = current_file_digest(repo_root / path)
    selector = next(
        iter(
            state_digests(
                "working-tree-finding-identity",
                payload,
            ).values()
        )
    )[:SHORT_MESSAGE_DIGEST_LENGTH]
    blocker_id = f"working-tree:{code}:{subject}:{selector}"
    return Blocker(
        id=blocker_id,
        description=message or code,
        state_digests=state_digests(blocker_id, payload),
    )


def annotate_audit_issues(
    kind: str,
    issues: list[AuditIssue],
    graph: Graph,
) -> tuple[list[dict[str, Any]], list[Blocker]]:
    """
    @brief Retain every audit failure and annotate exact active waivers.
    @param[in] kind Stable audit namespace, such as traceability or coverage.
    @param[in] issues Current deterministic audit findings.
    @param[in] graph Run graph carrying human-approved waiver records.
    @return Serialized findings and the subset of blockers still unwaived.
    @details With no active waiver, serialized issue mappings retain their
             established shape without additional keys.
    """
    annotated: list[dict[str, Any]] = []
    unwaived: list[Blocker] = []
    for issue in issues:
        blocker = audit_issue_blocker(kind, issue)
        payload = issue.to_dict()
        waiver = active_waiver(graph, blocker)
        if waiver is None:
            unwaived.append(blocker)
        else:
            payload["waived"] = True
            payload["waivers"] = [waiver_metadata(waiver)]
        annotated.append(payload)
    return annotated, unwaived


def annotate_working_tree(
    report: dict[str, Any],
    graph: Graph,
    repo_root: Path | None = None,
) -> tuple[dict[str, Any], list[Blocker]]:
    """
    @brief Retain working-tree findings and annotate exact active waivers.
    @param[in] report Complete working-tree audit report.
    @param[in] graph Run graph carrying human-approved waiver records.
    @param[in] repo_root Optional repository root for content-pinned secret
               finding blockers.
    @return Copied report and the subset of finding blockers still unwaived.
    @details Entries, untracked paths, and unwaived finding shapes remain
             unchanged; waiver metadata is conditional on exact state.
    """
    annotated = dict(report)
    if "blocking_findings" not in report:
        return annotated, []

    findings: list[dict[str, Any]] = []
    unwaived: list[Blocker] = []
    for finding in report["blocking_findings"]:
        blocker = working_tree_blocker(finding, repo_root)
        payload = dict(finding)
        waiver = active_waiver(graph, blocker)
        if waiver is None:
            unwaived.append(blocker)
        else:
            payload["waived"] = True
            payload["waivers"] = [waiver_metadata(waiver)]
        findings.append(payload)
    annotated["blocking_findings"] = findings
    return annotated, unwaived


def collect_waiver_targets(
    repo_root: Path,
    graph: Graph,
    config: WorkflowConfig,
) -> list[Blocker]:
    """
    @brief Discover every currently failing human-waivable process blocker.
    @param[in] repo_root Repository root used by live audits and digest checks.
    @param[in] graph Active run graph.
    @param[in] config Validated workflow policy.
    @return Deterministically ordered blockers deduplicated by exact identity.
    @details Structural graph, schema, locking, and stale-update failures occur
             outside these process audits and therefore never become targets.
    """
    quick = bool(run_stage_spec(graph).bypassed_stages)
    blockers = list(stage_blocker_details(repo_root, graph))

    for result in evaluate(repo_root, graph, config):
        if result.holds is not False or not result.can_waive:
            continue
        digests = result.state_digests or state_digests(
            f"invariant:{result.id}",
            {"id": result.id, "message": result.message},
        )
        blockers.append(
            Blocker(
                id=result.id,
                description=result.message,
                state_digests=dict(digests),
            )
        )

    blockers.extend(gate_failure_blockers(graph, config))
    if not quick:
        blockers.extend(
            audit_issue_blocker("traceability", issue)
            for issue in audit_traceability(repo_root, config)
        )
        blockers.extend(
            audit_issue_blocker("coverage", issue)
            for issue in audit_coverage(repo_root, config)
        )
    working_tree = audit_working_tree(repo_root, config, graph)
    blockers.extend(
        working_tree_blocker(finding, repo_root)
        for finding in working_tree.get("blocking_findings", [])
    )
    return _deduplicate_blockers(blockers)


def waiver_record_statuses(
    graph: Graph,
    targets: list[Blocker],
) -> list[dict[str, Any]]:
    """
    @brief Classify every persisted waiver against current blocker state.
    @param[in] graph Run graph containing complete waiver history.
    @param[in] targets Current exact process-blocker targets.
    @return Persisted waiver fields plus active, stale, or inactive status.
    """
    targets_by_id: dict[str, list[Blocker]] = {}
    for target in targets:
        targets_by_id.setdefault(target.id, []).append(target)

    statuses: list[dict[str, Any]] = []
    for waiver in graph.waivers:
        current = targets_by_id.get(waiver.blocker_id, [])
        if any(
            target.state_digests == waiver.state_digests
            for target in current
        ):
            status = "active"
        elif current:
            status = "stale"
        else:
            status = "inactive"
        payload = asdict(waiver)
        payload["status"] = status
        statuses.append(payload)
    return statuses


# LOCAL HELPERS


def _short_message_digest(message: str) -> str:
    """
    @brief Return a compact stable subject when a finding has no named subject.
    @param[in] message Finding text whose identity needs a safe bounded form.
    @return Leading hexadecimal characters of the message SHA-256 digest.
    """
    return sha256(message.encode("utf-8")).hexdigest()[
        :SHORT_MESSAGE_DIGEST_LENGTH
    ]


def _deduplicate_blockers(blockers: list[Blocker]) -> list[Blocker]:
    """
    @brief Deterministically retain one blocker for each exact blocker ID.
    @param[in] blockers Current blockers collected from all process surfaces.
    @return Blockers ordered by ID with duplicate identities removed.
    """
    ordered = sorted(
        blockers,
        key=lambda blocker: (
            blocker.id,
            tuple(sorted(blocker.state_digests.items())),
            blocker.description,
        ),
    )
    unique: dict[str, Blocker] = {}
    for blocker in ordered:
        unique.setdefault(blocker.id, blocker)
    return list(unique.values())


# END OF FILE
