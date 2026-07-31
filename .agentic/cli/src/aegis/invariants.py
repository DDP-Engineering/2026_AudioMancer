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
@details Provides reusable implementation behavior for the standalone AEGIS system.
@details INV-7 (0.3.0, code-review follow-up) now scans `git diff HEAD` plus
         untracked file content instead of only the unstaged `git diff`, which
         previously missed staged and newly created files.
@details INV-5 (0.6.0) reports a recorded path that escapes the repository as
         its own finding instead of raising: an exception here aborts the whole
         `evaluate` pass and with it every command that reads invariants.
@details INV-7 (0.7.0, code-review follow-up) also scans `git diff --cached`,
         closing a gap where a secret in a staged-but-never-committed file in a
         repository with no `HEAD` yet slipped past both `git diff HEAD` and the
         untracked-file listing.
@details INV-10 blocks check and later standard stages unless the authoritative
         solution design remains approved and digest-stable.
@details Blocking invariant failures can carry exact run-local waiver metadata
         while retaining ``holds = false``; structural validation and
         persistence failures occur outside invariant evaluation.
@details Quick runs render collapsed requirement, check, and design invariants
         as an explicit not-applicable state rather than a successful result,
         without loading storage owned by those absent stages.
"""

# IMPORTS

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import re
import subprocess
from pathlib import Path
from typing import Any, Literal

from .components import audit_local_scope
from .config import WorkflowConfig
from .gates import gate_failure_blockers
from .models import STAGES, Graph, Waiver
from .paths import contained_relative_path, matches_pattern
from .requirement_store import RequirementRecord
from .requirements import load_requirement_index
from .stage_schema import run_stage_spec
from .waivers import (
    Blocker,
    active_waiver,
    current_file_digest,
    red_before_green_blocker,
    state_digests,
    waiver_metadata,
)
from .working_tree import MAX_SECRET_SCAN_BYTES

# DATA MODELS / TYPEDEFINITIONS


@dataclass
class InvariantResult:
    """
    @brief      One evaluated (or not-applicable) invariant outcome, including
                any inherited waiver state.
    """
    id: str
    name: str
    holds: bool | None
    policy: str
    message: str
    status: Literal["evaluated", "not-applicable"] = field(
        default="evaluated", repr=False
    )
    state_digests: dict[str, str] = field(default_factory=dict, repr=False)
    waivers: tuple[Waiver, ...] = field(default_factory=tuple, repr=False)
    waiver_eligible: bool | None = field(default=None, repr=False)

    @property
    def can_waive(self) -> bool:
        """
        @brief Return effective process-waiver eligibility.
        @return Explicit eligibility, or the legacy blocking-policy default.
        @details The separate field preserves zero-waiver serialized policy
                 bytes while allowing legacy INV-7 failures to use the new
                 process-waiver mechanism.
        """
        if self.waiver_eligible is not None:
            return self.waiver_eligible
        return self.policy == "blocking"

    @property
    def effective_policy(self) -> str:
        """
        @brief Render a non-contradictory policy for an actively waived result.
        @return ``blocking`` for an eligible waived legacy result, else policy.
        """
        if self.waived and self.can_waive:
            return "blocking"
        return self.policy

    @property
    def waived(self) -> bool:
        """
        @brief Return whether exact active waivers neutralize this failure.
        @return ``True`` only for a failed result covered by waiver records.
        """
        return self.holds is False and bool(self.waivers)

    def to_dict(self) -> dict[str, Any]:
        """
        @brief Serialize the established result shape plus active waiver data.
        @return JSON-compatible invariant result.
        @details Ordinary results retain their byte-compatible five-key shape.
        """
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "holds": self.holds,
            "policy": self.effective_policy,
            "message": self.message,
        }
        if self.status == "not-applicable":
            payload["status"] = self.status
        if self.waived:
            payload["waived"] = True
            payload["waivers"] = [
                waiver_metadata(waiver) for waiver in self.waivers
            ]
        return payload


# PUBLIC API


def evaluate(
    repo_root: Path, graph: Graph, config: WorkflowConfig
) -> list[InvariantResult]:
    """
    @brief      Evaluate all ten AEGIS invariants against the current graph.
    @param[in]  repo_root Repository root.
    @param[in]  graph Active workflow graph to evaluate.
    @param[in]  config Validated workflow configuration.
    @return     One result per invariant, in fixed INV-1..INV-10 order, with
                any eligible failure's inherited waiver already attached.
    @exception  StageOperationError If the graph's kind/profile/stage do not
                match a declared run-stage schema.
    @exception  RequirementValidationError If a requirement snapshot is
                malformed or a requirement ID is duplicated (full runs only).
    """
    quick = bool(run_stage_spec(graph).bypassed_stages)
    # Full runs load the requirement index once for the four consumers. Quick
    # runs do not own requirement collection, so malformed or absent
    # requirement storage cannot turn their honest N/A results into a crash.
    requirements = (
        {}
        if quick
        else load_requirement_index(repo_root, config).by_id
    )
    results = [
        (
            _quick_not_applicable("INV-1", "Coverage")
            if quick
            else _coverage(requirements, graph)
        ),
        (
            _quick_not_applicable("INV-2", "Citation")
            if quick
            else _citation(requirements, graph)
        ),
        (
            _quick_not_applicable("INV-3", "Red-before-green")
            if quick
            else _red_before_green(graph)
        ),
        _no_regression(graph, config),
        _in_scope(repo_root, graph, config),
        _evidence(graph),
        _clean_secrets(repo_root, config),
        (
            _quick_not_applicable("INV-8", "Green requirements active")
            if quick
            else _green_requirements_active(requirements, graph)
        ),
        _component_baseline_scope(repo_root, graph, config),
        (
            _quick_not_applicable("INV-10", "Solution design")
            if quick
            else _solution_design(repo_root, graph, requirements)
        ),
    ]
    for result in results:
        if result.holds is not False or not result.can_waive:
            continue
        if not result.state_digests:
            result.state_digests = state_digests(
                f"invariant:{result.id}",
                {"id": result.id, "message": result.message},
            )
        if result.waivers:
            continue
        waiver = active_waiver(
            graph,
            Blocker(result.id, result.message, result.state_digests),
        )
        if waiver is not None:
            result.waivers = (waiver,)
    return results


def blocking_failures(results: list[InvariantResult]) -> list[InvariantResult]:
    """
    @brief      Select the failed, unwaived results that must block the run.
    @param[in]  results Invariant results from `evaluate`.
    @return     Results whose policy is blocking or non-waivable, that failed,
                and that carry no covering waiver.
    @exception  None
    """
    return [
        item
        for item in results
        if item.policy in {"blocking", "non-waivable"}
        and item.holds is False
        and not item.waived
    ]


# HELPER FUNCTIONS


def _quick_not_applicable(invariant_id: str, name: str) -> InvariantResult:
    """
    @brief Render one collapsed quick-run invariant as its own honest state.
    @param[in] invariant_id Stable invariant identifier.
    @param[in] name Human-readable invariant name.
    @return Non-blocking not-applicable result that is neither pass nor fail.
    """
    return InvariantResult(
        invariant_id,
        name,
        None,
        "not-applicable",
        "Not applicable - quick run.",
        status="not-applicable",
    )


def _digest_differs(path: Path, expected: str) -> bool:
    """
    @brief      Report whether a file is absent, unreadable, or digest-changed.
    @details    An unreadable file counts as changed so a permission error
                becomes a failed invariant rather than aborting the whole
                ``evaluate`` pass.
    @param[in]  path File whose content digest to compare.
    @param[in]  expected Expected SHA-256 hex digest.
    @return     ``True`` when the digest cannot be confirmed to match.
    """
    try:
        return not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected
    except OSError:
        return True


def _unique_waivers(waivers: list[Waiver]) -> tuple[Waiver, ...]:
    """
    @brief De-duplicate inherited waiver records without changing their order.
    @param[in] waivers Matching waiver records.
    @return First occurrence of each waiver identity.
    """
    seen: set[str] = set()
    unique: list[Waiver] = []
    for waiver in waivers:
        if waiver.id in seen:
            continue
        seen.add(waiver.id)
        unique.append(waiver)
    return tuple(unique)


def _solution_design_state_digests(
    repo_root: Path,
    graph: Graph,
    requirements: dict[str, RequirementRecord],
) -> dict[str, str]:
    """
    @brief Capture current design and cited-requirement content for INV-10.
    @param[in] repo_root Repository root.
    @param[in] graph Active graph with the pinned design proposal.
    @param[in] requirements Current validated requirement records.
    @return Named current digests, including stable absence/error sentinels.
    """
    design = graph.design
    digests = state_digests(
        "invariant:INV-10:approval",
        {
            "design": (
                {
                    "revision": design.revision,
                    "status": design.status,
                    "approval": design.approval,
                    "document_path": design.document_path,
                    "document_digest": design.document_digest,
                    "requirement_digests": design.requirement_digests,
                }
                if design
                else None
            )
        },
    )
    if not design:
        digests["invariant:INV-10:design-file"] = "missing-design-record"
        return digests
    digests[f"file:{design.document_path}"] = current_file_digest(
        repo_root / design.document_path
    )
    for requirement_id in sorted(design.requirement_digests):
        record = requirements.get(requirement_id)
        if record is None or record.source_file is None:
            digests[f"requirement:{requirement_id}"] = "missing"
            continue
        source = str(record.source_file)
        digests[f"requirement:{requirement_id}:{source}"] = current_file_digest(
            repo_root / source
        )
    return digests


def _coverage(
    requirements: dict[str, RequirementRecord],
    graph: Graph,
) -> InvariantResult:
    """
    @brief      INV-1: every non-Retired requirement must be cited by a check.
    @param[in]  requirements Pre-loaded requirement records by identity.
    @param[in]  graph Active workflow graph whose checks are inspected.
    @return     Pass when no non-Retired requirement is uncited.
    @exception  None
    """
    covered_ids = {
        requirement_id
        for check in graph.checks
        for requirement_id in check.cites_requirement
    }
    missing = [
        item.id
        for item in requirements.values()
        if item.status != "Retired" and item.id not in covered_ids
    ]
    return InvariantResult(
        "INV-1",
        "Coverage",
        not missing,
        "blocking",
        "All non-retired requirements have checks."
        if not missing
        else f"Missing checks for: {', '.join(missing)}",
    )


def _citation(
    requirements: dict[str, RequirementRecord],
    graph: Graph,
) -> InvariantResult:
    """
    @brief      INV-2: every check must cite at least one existing requirement.
    @param[in]  requirements Pre-loaded requirement records by identity.
    @param[in]  graph Active workflow graph whose checks are inspected.
    @return     Pass when every check cites only known requirement IDs.
    @exception  None
    """
    requirement_ids = set(requirements)
    bad = [
        check.id
        for check in graph.checks
        if not check.cites_requirement
        or any(
            requirement_id not in requirement_ids
            for requirement_id in check.cites_requirement
        )
    ]
    return InvariantResult(
        "INV-2",
        "Citation",
        not bad,
        "blocking",
        "All checks cite existing requirements."
        if not bad
        else f"Bad check citations: {', '.join(bad)}",
    )


def _red_before_green(graph: Graph) -> InvariantResult:
    """
    @brief      INV-3: every green check must have prior recorded red evidence.
    @param[in]  graph Active workflow graph whose checks are inspected.
    @return     Pass when no green check lacks red evidence, else fail with
                any matching per-check waivers already attached.
    @exception  None
    """
    missing = [
        check.id
        for check in graph.checks
        if check.state == "green" and not check.red_evidence
    ]
    blockers = [
        red_before_green_blocker(graph, check_id)
        for check_id in missing
    ]
    inherited = [
        waiver
        for blocker in blockers
        if (waiver := active_waiver(graph, blocker)) is not None
    ]
    return InvariantResult(
        "INV-3",
        "Red-before-green",
        not missing,
        "blocking",
        "Green checks have prior red evidence." if not missing else f"Missing red evidence for: {', '.join(missing)}",
        state_digests=state_digests(
            "invariant:INV-3",
            {
                "missing": missing,
                "blocker_states": [
                    blocker.state_digests for blocker in blockers
                ],
            },
        ),
        waivers=(
            _unique_waivers(inherited)
            if missing and len(inherited) == len(blockers)
            else ()
        ),
    )


def _no_regression(
    graph: Graph,
    config: WorkflowConfig,
) -> InvariantResult:
    """
    @brief      INV-4: no unwaived failing gate/test-run evidence may remain
                on implementation, validation, or delivery stage evidence.
    @param[in]  graph Active workflow graph whose evidence is inspected.
    @param[in]  config Validated gate policy.
    @return     Pass when no such failure is uncovered by an active waiver.
    @exception  None
    """
    failed_evidence = [
        item
        for item in graph.evidence
        if item.kind in {"gate", "test-run"} and item.stage in {"implementation", "validation", "delivery"} and item.result == "fail"
        and item.status != "superseded"
    ]
    gate_blockers = {
        blocker.id: blocker
        for blocker in gate_failure_blockers(graph, config)
    }
    inherited: list[Waiver] = []
    uncovered = False
    for item in failed_evidence:
        blocker = (
            gate_blockers.get(f"gate:{item.gate_name}")
            if item.kind == "gate" and item.gate_name
            else None
        )
        waiver = active_waiver(graph, blocker) if blocker else None
        if waiver is None:
            uncovered = True
        else:
            inherited.append(waiver)
    failed_gates = [item.id for item in failed_evidence]
    return InvariantResult(
        "INV-4",
        "No regression",
        not failed_gates,
        "blocking",
        "No failing implementation/validation/delivery gate evidence." if not failed_gates else f"Failing gate evidence: {', '.join(failed_gates)}",
        state_digests=state_digests(
            "invariant:INV-4",
            {
                "failures": sorted(
                    {
                        (
                            item.kind,
                            item.gate_name or "",
                            item.check_id or "",
                            item.command or "",
                            item.exit_status,
                            item.failure_kind or "",
                        )
                        for item in failed_evidence
                    },
                    key=lambda item: (
                        item[0],
                        item[1],
                        item[2],
                        item[3],
                        item[4] if item[4] is not None else -1,
                        item[5],
                    ),
                )
            },
        ),
        waivers=(
            _unique_waivers(inherited)
            if failed_evidence and not uncovered
            else ()
        ),
    )


def _green_requirements_active(
    requirements: dict[str, RequirementRecord], graph: Graph
) -> InvariantResult:
    """
    @brief      INV-8: requirements cited by a green check must exist and be
                Active, not Planned, Retired, or otherwise inactive.
    @param[in]  requirements Pre-loaded requirement records by identity.
    @param[in]  graph Active workflow graph whose checks are inspected.
    @return     Pass when every green-cited requirement exists and is Active.
    @exception  None
    """
    cited = sorted({req_id for check in graph.checks if check.state == "green" for req_id in check.cites_requirement})
    if not cited:
        return InvariantResult("INV-8", "Green requirements active", True, "blocking", "No green checks cite durable requirements.")
    missing = [req_id for req_id in cited if req_id not in requirements]
    planned = [
        req_id
        for req_id in cited
        if req_id in requirements and requirements[req_id].status != "Active"
    ]
    failures = [*missing, *planned]
    if not failures:
        return InvariantResult("INV-8", "Green requirements active", True, "blocking", "Green requirement-linked checks cite Active requirements.")
    parts = []
    if missing:
        parts.append(f"missing rows: {', '.join(missing)}")
    if planned:
        parts.append(f"not Active: {', '.join(planned)}")
    return InvariantResult("INV-8", "Green requirements active", False, "blocking", "; ".join(parts))


def _solution_design(
    repo_root: Path,
    graph: Graph,
    requirements: dict[str, RequirementRecord],
) -> InvariantResult:
    """
    @brief      Enforce approved digest-stable solution design from check onward.
    @param[in]  repo_root Repository root.
    @param[in]  graph Active workflow graph.
    @param[in]  requirements Pre-loaded requirement records by identity.
    @return     INV-10 evaluation result.
    """
    if graph.stage not in STAGES or STAGES.index(graph.stage) < STAGES.index("check"):
        return InvariantResult(
            "INV-10",
            "Solution design",
            True,
            "blocking",
            "Solution-design approval is not yet required.",
        )
    design = graph.design
    digest_state = _solution_design_state_digests(
        repo_root,
        graph,
        requirements,
    )
    if not design or design.status != "approved" or design.approval != "human":
        return InvariantResult(
            "INV-10",
            "Solution design",
            False,
            "blocking",
            "Check and later stages require explicit human design approval.",
            state_digests=digest_state,
        )
    failures: list[str] = []
    document = repo_root / design.document_path
    if _digest_differs(document, design.document_digest):
        failures.append("design.md digest changed")
    for requirement_id, digest in design.requirement_digests.items():
        record = requirements.get(requirement_id)
        path = repo_root / str(record.source_file) if record else None
        if record is None or path is None or _digest_differs(path, digest):
            failures.append(f"{requirement_id} snapshot changed")
    return InvariantResult(
        "INV-10",
        "Solution design",
        not failures,
        "blocking",
        "Approved solution design and cited requirements are digest-stable."
        if not failures
        else "; ".join(failures),
        state_digests=digest_state,
    )


def _component_baseline_scope(repo_root: Path, graph: Graph, cfg: WorkflowConfig) -> InvariantResult:
    """
    @brief      Verify behavior-changing runs only touch baseline-ready components.
    @param[in]  repo_root Repository root.
    @param[in]  graph Workflow graph to evaluate.
    @param[in]  cfg Workflow configuration.
    @return     Component baseline scope invariant result.
    @exception  CommandInputError If the component manifest TOML is invalid.
    """
    if cfg.component_baseline_guard.mode == "disabled":
        return InvariantResult(
            "INV-9",
            "Component baseline scope",
            True,
            "blocking",
            "Component baseline guard is disabled by workflow.toml.",
        )
    if graph.intent.kind == "adoption":
        return InvariantResult(
            "INV-9",
            "Component baseline scope",
            True,
            "blocking",
            "Component baseline scope does not block adoption runs.",
        )
    if graph.intent.kind not in {"feature", "fix", "change"}:
        return InvariantResult("INV-9", "Component baseline scope", True, "blocking", "Run kind does not require component baseline scope.")
    touched = [path for unit in graph.change_units for path in unit.touched_paths]
    if not touched:
        return InvariantResult("INV-9", "Component baseline scope", True, "blocking", "No change units recorded yet.")
    issues = audit_local_scope(
        repo_root, touched, cfg, cfg.adoption_default_completion_level
    )
    if not issues:
        return InvariantResult("INV-9", "Component baseline scope", True, "blocking", "Mapped component paths meet baseline scope.")
    messages = [
        f"{issue.code} {issue.name or 'component'} {issue.path or ''}".strip()
        for issue in issues
    ]
    return InvariantResult("INV-9", "Component baseline scope", False, "blocking", "; ".join(messages))


def _in_scope(repo_root: Path, graph: Graph, cfg: WorkflowConfig) -> InvariantResult:
    """
    @brief      INV-5: touched paths must fall within configured scope roots.
    @param[in]  repo_root Repository root.
    @param[in]  graph Active workflow graph whose change units are inspected.
    @param[in]  cfg Validated workflow configuration.
    @return     Pass when every touched path is inside an allowed root;
                blocking or advisory severity depending on `cfg.scope.mode`.
    @details    A recorded path that escapes the repository root is reported as
                its own finding instead of raising. Recording is validated at
                the CLI boundary, but a graph written before that validation —
                or edited by hand — must still be evaluable: an exception here
                propagates out of `evaluate` and takes `run status`,
                `verify invariants`, `delivery report`, and the outward-action
                guard down with it, leaving the run unusable until the graph is
                repaired by hand. An escaping path
                is never inside a configured root, so it fails the invariant.
    @exception  None
    """
    severity = "blocking" if cfg.scope.mode == "enforce" else "advisory"
    if cfg.scope.mode == "unrestricted":
        return InvariantResult(
            "INV-5",
            "In scope",
            True,
            severity,
            "Scope restriction is unrestricted by workflow.toml.",
        )
    touched = [path for unit in graph.change_units for path in unit.touched_paths]
    if not touched:
        return InvariantResult("INV-5", "In scope", True, severity, "No change units recorded yet.")
    patterns = _root_patterns(list(cfg.scope.allowed_roots))
    escaping: list[str] = []
    out_of_scope: list[str] = []
    for path in touched:
        relative = contained_relative_path(path, repo_root)
        if relative is None:
            escaping.append(path)
        elif not any(matches_pattern(relative, pattern) for pattern in patterns):
            out_of_scope.append(relative)
    if not escaping and not out_of_scope:
        return InvariantResult(
            "INV-5", "In scope", True, severity, "Touched paths are in configured scope."
        )
    parts = []
    if out_of_scope:
        parts.append(f"Out-of-scope paths: {', '.join(out_of_scope)}")
    if escaping:
        parts.append(
            "Paths outside the repository (re-record them relative to the repository root): "
            f"{', '.join(escaping)}"
        )
    return InvariantResult("INV-5", "In scope", False, severity, "; ".join(parts))


def _evidence(graph: Graph) -> InvariantResult:
    """
    @brief      INV-6: the run must have at least one recorded evidence item.
    @param[in]  graph Active workflow graph whose evidence is inspected.
    @return     Pass when `graph.evidence` is non-empty.
    @exception  None
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
    @brief      INV-7: no configured secret pattern may match pending changes.
    @param[in]  repo_root Repository root.
    @param[in]  cfg Validated workflow configuration.
    @return     Pass when no configured secret pattern matches; a git-access
                failure while scanning is reported as a fail, not raised.
    @details    Scans `git diff HEAD` (staged and unstaged changes against the
                last commit) plus the content of untracked files, not just the
                unstaged working-tree diff: a secret dropped into a newly
                created or already-`git add`-ed file would otherwise never
                appear in a plain `git diff`.
    @details    Also scans `git diff --cached` (0.4.0, code-review follow-up).
                In a repository with no commits yet there is no `HEAD`, so
                `git diff HEAD` fails with empty output and `git ls-files
                --others` lists only untracked files — a secret in a staged but
                never-committed file would slip through both. The cached diff
                covers exactly that gap and is a harmless superset of `git diff
                HEAD` once a `HEAD` exists.
    @exception  None
    """
    if cfg.secrets.mode == "disabled":
        return InvariantResult(
            "INV-7",
            "Clean secrets",
            True,
            "non-waivable",
            "Secret scanning is disabled by workflow.toml.",
            waiver_eligible=True,
        )
    patterns = cfg.secrets.patterns
    if not patterns:
        return InvariantResult(
            "INV-7",
            "Clean secrets",
            True,
            "non-waivable",
            "No secret patterns configured.",
            waiver_eligible=True,
        )
    try:
        text = (
            _tracked_changes_text(repo_root)
            + "\n"
            + _staged_changes_text(repo_root)
            + "\n"
            + _untracked_files_text(repo_root)
        )
    except (OSError, subprocess.TimeoutExpired):
        return InvariantResult(
            "INV-7",
            "Clean secrets",
            False,
            "non-waivable",
            "Could not inspect git diff for secrets.",
            waiver_eligible=True,
        )
    matches = []
    matched_sites: dict[str, list[str]] = {}
    for pattern in patterns:
        found = sorted(item.group(0) for item in re.finditer(pattern, text))
        if found:
            matches.append(pattern)
            matched_sites[pattern] = found
    result = InvariantResult(
        "INV-7",
        "Clean secrets",
        not matches,
        "non-waivable",
        "No configured secret pattern found in diff or untracked files." if not matches else f"Secret pattern matched: {', '.join(matches)}",
        waiver_eligible=True,
    )
    if matches:
        # Pin any waiver to the exact matched secret values, not just the
        # message text: a NEW secret matching an already-waived pattern must
        # stale the waiver rather than ride it silently, while unrelated
        # working-tree churn leaves an accepted waiver active.
        result.state_digests = state_digests(
            "invariant:INV-7",
            {"id": "INV-7", "matched_sites": matched_sites},
        )
    return result


def _tracked_changes_text(repo_root: Path) -> str:
    """
    @brief      Return staged and unstaged changes against HEAD as diff text.
    @param[in]  repo_root Repository the diff is read for.
    @return     Combined `git diff HEAD` text.
    @exception  OSError Raised when Git cannot be invoked.
    @exception  subprocess.TimeoutExpired Raised when Git does not finish in time.
    """
    return subprocess.run(
        ["git", "diff", "--no-ext-diff", "HEAD"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    ).stdout


def _staged_changes_text(repo_root: Path) -> str:
    """
    @brief      Return staged changes against the index as diff text.
    @param[in]  repo_root Repository the staged diff is read for.
    @return     `git diff --cached` text.
    @details    Unlike `git diff HEAD`, this works in a repository with no
                commits yet: with no `HEAD` to diff against, staged files show
                as additions against the empty tree. Once a `HEAD` exists this
                is a subset of `git diff HEAD`, so scanning both is redundant
                but never wrong.
    @exception  OSError Raised when Git cannot be invoked.
    @exception  subprocess.TimeoutExpired Raised when Git does not finish in time.
    """
    return subprocess.run(
        ["git", "diff", "--no-ext-diff", "--cached"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    ).stdout


def _untracked_files_text(repo_root: Path) -> str:
    """
    @brief      Return the concatenated content of untracked, non-ignored files.
    @param[in]  repo_root Repository the untracked-file listing is read for.
    @return     Concatenated file content, best-effort.
    @details    A brand-new file has no HEAD to diff against, so its content
                would never appear in `git diff HEAD`; this reads it directly.
                Files larger than `MAX_SECRET_SCAN_BYTES` are skipped rather
                than read in full.
    @exception  OSError Raised when Git cannot be invoked.
    @exception  subprocess.TimeoutExpired Raised when Git does not finish in time.
    """
    listing = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    ).stdout
    chunks = []
    for line in listing.splitlines():
        path = repo_root / line
        try:
            if path.is_file() and path.stat().st_size <= MAX_SECRET_SCAN_BYTES:
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(chunks)


def _root_patterns(roots: list[str]) -> list[str]:
    """
    @brief      Expand configured scope roots into glob patterns.
    @param[in]  roots Repository-relative roots or glob patterns.
    @return     One pattern per root: unchanged if already a glob, else
                suffixed with `/**` to match the whole subtree.
    @exception  None
    """
    patterns = []
    for root in roots:
        normalized = root.replace("\\", "/").rstrip("/")
        if any(char in normalized for char in "*?["):
            patterns.append(normalized)
        else:
            patterns.append(f"{normalized}/**")
    return patterns


# END OF FILE
