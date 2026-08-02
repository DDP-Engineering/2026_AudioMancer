#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file check_execution.py
@brief External and managed deterministic check evidence workflows.
@details Enforces the policy captured for the current prepared stage, generates
         immutable check identities in evidence forms, and imports or executes
         a complete selected check set.
@details Managed check subprocesses (1.4.0) execute outside the run-scoped
         graph lock. A short publication transaction revalidates the captured
         stage revision, execution mode, and check definitions before evidence
         identifiers are allocated and results are recorded.
"""

# IMPORTS

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from ._form_io import load_evidence_form as _load
from ._form_io import quote_toml_string as _q
from ._form_io import read_string_field as _string
from ._form_io import retire_form as _retire_form
from .config import DEFAULT_GATE_TIMEOUT_SECONDS
from .gates import _run_command
from .models import Check, Evidence, Graph, StageRecord
from .stage_forms import StageOperationError, stage_directory
from .store import (
    GraphConflictError,
    append_journal,
    graph_transaction,
    next_evidence_id,
    relink_check_evidence,
    run_dir,
    save_graph,
    serialized_graph_mutation,
)
from .waivers import (
    Blocker,
    active_waiver,
    red_before_green_blocker,
    state_digests,
)

# CONSTANTS

EVIDENCE_SCHEMA_VERSION = 3
RESULT_KEYS = (
    "check_id",
    "command",
    "result",
    "exit_status",
    "summary",
    "output_log",
)

# PUBLIC API


@serialized_graph_mutation
def prepare_check_evidence(repo_root: Path, graph: Graph) -> Path:
    """
    @brief      Generate the external check evidence form.
    @param[in]  repo_root Repository root.
    @param[in]  graph Active workflow graph.
    @return     Path to the generated evidence TOML.
    @exception  StageOperationError If check execution mode is not external, the
                stage is not check or implementation, no checks are imported, or
                every imported check is already excused by an active waiver.
    @details    Checks whose stage evidence blocker is already covered by an
                active, exactly matching waiver receive no result row. Their
                honest absence replaces a fabricated observation.
    """
    excused = _require_external_evidence_preconditions(graph)
    path = stage_directory(repo_root, graph) / "evidence.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    expected = "fail" if graph.stage == "check" else "pass"
    lines = [
        f"schema_version = {EVIDENCE_SCHEMA_VERSION}",
        f"run_id = {_q(graph.run_id)}",
        f"stage = {_q(graph.stage)}",
        f"expected_result = {_q(expected)}",
    ]
    for check in graph.checks:
        if check.id in excused:
            continue
        lines.extend(
            [
                "",
                "[[result]]",
                f"check_id = {_q(check.id)}",
                f"command = {_q(check.command or '')}",
                'result = ""',
                "exit_status = 0",
                'summary = ""',
                'output_log = ""',
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    append_journal(
        repo_root,
        graph.run_id,
        "check.evidence.prepared",
        {
            "stage": graph.stage,
            "path": path.relative_to(repo_root).as_posix(),
            "excused_checks": sorted(excused),
        },
    )
    return path


@serialized_graph_mutation
def record_check_evidence(repo_root: Path, graph: Graph) -> list[Evidence]:
    """
    @brief      Validate and atomically import every external check result.
    @param[in]  repo_root Repository root.
    @param[in,out] graph Active workflow graph.
    @return     Imported evidence records.
    @exception  StageOperationError If preconditions are unmet, or the evidence
                form's identity, completeness, or result content fails validation.
    @details    Completeness is measured against the imported checks that are not
                excused by an active, exactly matching waiver. Every present row
                is validated unchanged, and an excused check may not carry one.
    """
    excused = _require_external_evidence_preconditions(graph)
    path = stage_directory(repo_root, graph) / "evidence.toml"
    data = _load(path)
    expected_keys = {
        "schema_version",
        "run_id",
        "stage",
        "expected_result",
        "result",
    }
    unknown = sorted(set(data) - expected_keys)
    missing = sorted(expected_keys - set(data))
    if unknown or missing:
        raise StageOperationError(
            f"{path}: "
            + (
                f"unknown key {unknown[0]}"
                if unknown
                else f"missing key {missing[0]}"
            )
        )
    expected = "fail" if graph.stage == "check" else "pass"
    identity = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "run_id": graph.run_id,
        "stage": graph.stage,
        "expected_result": expected,
    }
    for key, value in identity.items():
        if data.get(key) != value:
            raise StageOperationError(
                f"{path}: {key} must be {value!r}; received {data.get(key)!r}"
            )
    rows = data["result"]
    if not isinstance(rows, list) or len(rows) != len(graph.checks) - len(excused):
        raise StageOperationError(
            f"{path}: result collection must contain every imported check exactly once"
        )
    checks = {check.id: check for check in graph.checks}
    parsed: list[tuple[Check, str, int, str, str | None]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise StageOperationError(f"{path}: each result must be a TOML table")
        unknown_row = sorted(set(row) - set(RESULT_KEYS))
        missing_row = sorted(set(RESULT_KEYS) - set(row))
        if unknown_row or missing_row:
            raise StageOperationError(
                f"{path}: invalid result keys: "
                + ", ".join(unknown_row or missing_row)
            )
        check_id = _string(row, "check_id", path)
        if check_id in seen or check_id not in checks:
            raise StageOperationError(
                f"{path}: unknown or duplicate immutable check_id {check_id}"
            )
        if check_id in excused:
            raise StageOperationError(
                f"{path}: {check_id} is covered by an active waiver "
                "and must not carry a result"
            )
        seen.add(check_id)
        check = checks[check_id]
        if _string(row, "command", path) != (check.command or ""):
            raise StageOperationError(
                f"{path}: command for {check_id} differs from the imported check"
            )
        result = _string(row, "result", path)
        if result != expected:
            raise StageOperationError(
                f"{path}: {check_id} result must be {expected} during {graph.stage}"
            )
        exit_status = row["exit_status"]
        if type(exit_status) is not int:
            raise StageOperationError(f"{path}: exit_status must be an integer")
        if (result == "pass") != (exit_status == 0):
            raise StageOperationError(
                f"{path}: {check_id} result and exit_status are inconsistent"
            )
        summary = _string(row, "summary", path)
        if not summary:
            raise StageOperationError(f"{path}: summary must not be empty")
        output_log = _string(row, "output_log", path) or None
        parsed.append((check, result, exit_status, summary, output_log))

    imported: list[Evidence] = []
    for check, result, exit_status, summary, output_log in parsed:
        evidence = Evidence(
            id=_next_evidence_id(graph, len(imported)),
            kind="test-run",
            result=result,
            summary=summary,
            command=check.command,
            path=check.path,
            stage=graph.stage,
            check_id=check.id,
            exit_status=exit_status,
            output_log=output_log,
        )
        imported.append(evidence)
    if not imported:
        raise StageOperationError(
            f"{path}: result collection must contain every imported check exactly once"
        )
    graph.evidence.extend(imported)
    _update_check_states(graph, imported)
    save_graph(repo_root, graph)
    append_journal(
        repo_root,
        graph.run_id,
        "check.evidence.recorded",
        {"stage": graph.stage, "evidence": [item.id for item in imported]},
    )
    _retire_form(
        path,
        graph.stage_records[graph.stage].retention,
        f"check-evidence-{imported[0].id}",
    )
    return imported


def run_checks(
    repo_root: Path,
    graph: Graph,
    check_ids: list[str] | None = None,
    timeout: int = DEFAULT_GATE_TIMEOUT_SECONDS,
) -> list[Evidence]:
    """
    @brief      Execute configured checks and record managed evidence.
    @param[in]  repo_root Repository root.
    @param[in,out] graph Active workflow graph.
    @param[in]  check_ids Optional immutable check selection.
    @param[in]  timeout Per-command timeout in seconds.
    @return     Evidence created for every selected check.
    @exception  StageOperationError If policy, stage, or selection is invalid.
    @exception  GraphConflictError If execution preconditions changed while
                subprocesses were running.
    """
    with graph_transaction(repo_root, graph):
        _require_mode(graph, "managed")
        if graph.stage not in {"check", "implementation"}:
            raise StageOperationError(
                "managed checks are valid only during check or implementation"
            )
        by_id = {check.id: check for check in graph.checks}
        unknown = sorted(set(check_ids or ()) - set(by_id))
        if unknown:
            raise StageOperationError(f"unknown check ID(s): {', '.join(unknown)}")
        selected = [
            deepcopy(check)
            for check in graph.checks
            if not check_ids or check.id in check_ids
        ]
        if not selected:
            raise StageOperationError("no checks selected")
        captured_stage = graph.stage
        record = graph.stage_records[captured_stage]
        captured_revision = (record.revision, record.digest)
        captured_mode = record.check_execution
        captured_checks = _check_definition_snapshot(graph.checks)

    expected = "fail" if captured_stage == "check" else "pass"
    completed = []
    for check in selected:
        if not check.command:
            raise StageOperationError(f"{check.id} has no executable command")
        result = _run_command(repo_root, check.command, timeout)
        completed.append((check, result))

    with graph_transaction(repo_root, graph):
        current_record = graph.stage_records.get(captured_stage)
        if (
            graph.stage != captured_stage
            or current_record is None
            or (current_record.revision, current_record.digest) != captured_revision
            or current_record.check_execution != captured_mode
            or _check_definition_snapshot(graph.checks) != captured_checks
        ):
            raise GraphConflictError(graph.run_id)

        log_root = run_dir(repo_root, graph.run_id) / "evidence" / "logs"
        log_root.mkdir(parents=True, exist_ok=True)
        imported: list[Evidence] = []
        for check, result in completed:
            observed = "pass" if result.returncode == 0 else "fail"
            log_path = log_root / f"{check.id}-{captured_stage}.log"
            log_path.write_text(
                f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}\n",
                encoding="utf-8",
            )
            evidence = Evidence(
                id=_next_evidence_id(graph, len(imported)),
                kind="test-run",
                result=observed,
                summary=(
                    f"{check.id} observed {observed}; "
                    f"{'expected' if observed == expected else 'unexpected'} "
                    f"during {captured_stage}"
                ),
                command=check.command,
                path=check.path,
                stage=captured_stage,
                check_id=check.id,
                exit_status=result.returncode,
                output_log=log_path.relative_to(repo_root).as_posix(),
            )
            imported.append(evidence)
            append_journal(
                repo_root,
                graph.run_id,
                "check.output",
                {
                    "check_id": check.id,
                    "returncode": result.returncode,
                    "stdout_tail": result.stdout[-4000:],
                    "stderr_tail": result.stderr[-4000:],
                },
            )
        graph.evidence.extend(imported)
        _update_check_states(graph, imported)
        save_graph(repo_root, graph)
        return imported


# LOCAL HELPERS


def _check_definition_snapshot(checks: list[Check]) -> tuple[tuple[object, ...], ...]:
    """
    @brief Capture immutable check definitions used by managed execution.
    @param[in] checks Authoritative imported check collection.
    @return Comparable definitions excluding evidence-derived state fields.
    @details Red/green state and linked evidence may advance concurrently
             without invalidating a command result; all fields that define the
             check identity, executable, traceability, and variants must remain
             unchanged through publication.
    """
    return tuple(
        (
            check.id,
            check.level,
            tuple(check.cites_spec),
            tuple(check.cites_requirement),
            check.command,
            check.path,
            tuple(check.contract_variants),
            tuple(check.concerns),
            tuple(check.parity_targets),
        )
        for check in checks
    )


def _require_external_evidence_preconditions(graph: Graph) -> set[str]:
    """
    @brief Enforce shared preparation and recording preconditions.
    @param[in] graph Active workflow graph.
    @return Immutable identities of the checks excused by an active waiver.
    @exception StageOperationError If stage, mode, or check state is invalid, or
               no check still requires an observation this stage.
    """
    _require_mode(graph, "external")
    if graph.stage not in {"check", "implementation"}:
        raise StageOperationError(
            "check evidence is valid only during check or implementation"
        )
    if not graph.checks:
        raise StageOperationError("no imported checks are available")
    excused = _excused_check_ids(graph)
    if len(excused) == len(graph.checks):
        raise StageOperationError(
            "every imported check is covered by an active waiver; "
            "no external check evidence is required"
        )
    return excused


def _excused_check_ids(graph: Graph) -> set[str]:
    """
    @brief Identify checks whose stage evidence blocker is already waived.
    @param[in] graph Active workflow graph carrying human approval records.
    @return Immutable check identities that need no result row this stage.
    @details The blockers built here are the same objects `stage_blockers`
             evaluates, so an approval excuses a check only while it still
             covers exact current state. A stale or absent waiver excuses
             nothing, and the check still owes a truthful observation.
    """
    record = graph.stage_records.get(graph.stage)
    if record is None:
        return set()
    return {
        check.id
        for check in graph.checks
        if active_waiver(graph, _check_stage_blocker(graph, record, check.id))
        is not None
    }


def _check_stage_blocker(
    graph: Graph,
    record: StageRecord,
    check_id: str,
) -> Blocker:
    """
    @brief Rebuild the exact readiness blocker this stage's evidence answers.
    @param[in] graph Active workflow graph.
    @param[in] record Applied stage record pinning implementation approvals.
    @param[in] check_id Concrete check identity.
    @return The check stage's red-before-green or implementation's green blocker.
    @details Construction mirrors `stage_forms._specific_stage_blocker` exactly;
             any divergence would silently stop matching approved waivers.
    """
    if graph.stage == "check":
        return red_before_green_blocker(
            graph,
            check_id,
            f"{check_id} has no active red evidence",
        )
    description = f"{check_id} has no active green evidence"
    return Blocker(
        id=f"stage:implementation:{check_id}:green-evidence",
        description=description,
        state_digests=state_digests(
            "stage:implementation",
            {
                "revision": record.revision,
                "digest": record.digest,
                "description": description,
            },
        ),
    )


def _require_mode(graph: Graph, requested: str) -> None:
    """@brief Enforce the check-execution policy captured for this stage."""
    record = graph.stage_records.get(graph.stage)
    if not record:
        raise StageOperationError("prepare the current stage before handling checks")
    if record.check_execution != requested:
        correct = (
            "aegis check prepare"
            if record.check_execution == "external"
            else "aegis check run"
        )
        raise StageOperationError(
            f"check execution mode is {record.check_execution}; use `{correct}`"
        )


# @brief Stages whose fail-result records are failed green attempts, not the
#        durable check-stage red witness. Mirrors the stage set INV-4 scans.
_GREEN_ATTEMPT_STAGES = frozenset({"implementation", "validation", "delivery"})


def _update_check_states(graph: Graph, evidence: list[Evidence]) -> None:
    """
    @brief Supersede stale same-check evidence, then relink state and links.
    @param[in,out] graph Authoritative graph already extended with `evidence`.
    @param[in] evidence Freshly created records for this batch.
    @details A new record supersedes every older active record for the same
             check with the same result — a rerun of the same observation
             replaces its predecessor rather than accumulating beside it. A
             new pass additionally supersedes older fail records from the
             implementation/validation/delivery stages: those are failed
             attempts at the green observation, so a later genuine pass
             retires them and INV-4 stops reporting them as live regressions.
             Check-stage fail records are never superseded by a pass — they
             are the durable red-before-green witness, and both the
             implementation-close blocker and INV-3 continue to require an
             active red. A new fail never supersedes an older pass: keeping
             both visible is what lets INV-4 report a genuine regression
             instead of hiding that the check once passed.
    """
    new_ids = {item.id for item in evidence}
    by_id = {item.check_id: item for item in evidence}
    for check in graph.checks:
        item = by_id.get(check.id)
        if not item:
            continue
        for prior in graph.evidence:
            if (
                prior.id in new_ids
                or prior.status != "active"
                or prior.check_id != check.id
            ):
                continue
            same_result = prior.result == item.result
            failed_green_attempt = (
                item.result == "pass"
                and prior.result == "fail"
                and prior.stage in _GREEN_ATTEMPT_STAGES
            )
            if not (same_result or failed_green_attempt):
                continue
            prior.status = "superseded"
            prior.superseded_by = item.id
            prior.supersede_reason = (
                "superseded by a newer run of the same check"
            )
    relink_check_evidence(graph, set(by_id))


def _next_evidence_id(graph: Graph, offset: int) -> str:
    """
    @brief Generate the next durable sequence ID without model input.
    """
    return next_evidence_id(graph, offset)


# END OF FILE
