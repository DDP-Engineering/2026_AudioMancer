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
@author Eng. Dan Dumitru Pasare
@date 2026-07-24
@version 0.7.0
"""

# IMPORTS

from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
from pathlib import Path

from .components import audit_local_scope
from .config import WorkflowConfig
from .models import Graph
from .paths import contained_relative_path, matches_pattern
from .requirements import load_requirement_index
from .working_tree import MAX_SECRET_SCAN_BYTES

# DATA MODELS / TYPEDEFINITIONS


@dataclass
class InvariantResult:
    """
    @brief      Represent InvariantResult data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.2.0
    """
    id: str
    name: str
    holds: bool
    policy: str
    message: str


# PUBLIC API


def evaluate(
    repo_root: Path, graph: Graph, config: WorkflowConfig
) -> list[InvariantResult]:
    """
    @brief      Evaluate workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  config Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.3.0
    """
    return [
        _coverage(graph),
        _citation(graph),
        _red_before_green(graph),
        _no_regression(graph),
        _in_scope(repo_root, graph, config),
        _evidence(graph),
        _clean_secrets(repo_root, config),
        _green_requirements_active(repo_root, graph, config),
        _component_baseline_scope(repo_root, graph, config),
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


# HELPER FUNCTIONS


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
    requirements = load_requirement_index(repo_root, cfg).by_id
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


def _component_baseline_scope(repo_root: Path, graph: Graph, cfg: WorkflowConfig) -> InvariantResult:
    """
    @brief      Verify behavior-changing runs only touch baseline-ready components.
    @param[in]  repo_root Repository root.
    @param[in]  graph Workflow graph to evaluate.
    @param[in]  cfg Workflow configuration.
    @return     Component baseline scope invariant result.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-22
    @version    0.2.0
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
    @brief      Handle in scope workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  cfg Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @details    A recorded path that escapes the repository root is reported as
                its own finding instead of raising. Recording is validated at
                the CLI boundary, but a graph written before that validation —
                or edited by hand — must still be evaluable: an exception here
                propagates out of `evaluate` and takes `status`, `invariants`,
                `report`, and `delivery-preflight` down with it, leaving the run
                unusable until the graph is repaired by hand. An escaping path
                is never inside a configured root, so it fails the invariant.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-23
    @version    0.3.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.4.0
    """
    if cfg.secrets.mode == "disabled":
        return InvariantResult(
            "INV-7",
            "Clean secrets",
            True,
            "non-waivable",
            "Secret scanning is disabled by workflow.toml.",
        )
    patterns = cfg.secret_patterns
    if not patterns:
        return InvariantResult("INV-7", "Clean secrets", True, "non-waivable", "No secret patterns configured.")
    try:
        text = (
            _tracked_changes_text(repo_root)
            + "\n"
            + _staged_changes_text(repo_root)
            + "\n"
            + _untracked_files_text(repo_root)
        )
    except (OSError, subprocess.TimeoutExpired):
        return InvariantResult("INV-7", "Clean secrets", False, "non-waivable", "Could not inspect git diff for secrets.")
    matches = []
    for pattern in patterns:
        if re.search(pattern, text):
            matches.append(pattern)
    return InvariantResult(
        "INV-7",
        "Clean secrets",
        not matches,
        "non-waivable",
        "No configured secret pattern found in diff or untracked files." if not matches else f"Secret pattern matched: {', '.join(matches)}",
    )


def _tracked_changes_text(repo_root: Path) -> str:
    """
    @brief      Return staged and unstaged changes against HEAD as diff text.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Combined `git diff HEAD` text.
    @exception  OSError Raised when Git cannot be invoked.
    @exception  subprocess.TimeoutExpired Raised when Git does not finish in time.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-18
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.1.0
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
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Concatenated file content, best-effort.
    @details    A brand-new file has no HEAD to diff against, so its content
                would never appear in `git diff HEAD`; this reads it directly.
                Files larger than `MAX_SECRET_SCAN_BYTES` are skipped rather
                than read in full.
    @exception  OSError Raised when Git cannot be invoked.
    @exception  subprocess.TimeoutExpired Raised when Git does not finish in time.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-18
    @version    0.1.0
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


# END OF FILE
