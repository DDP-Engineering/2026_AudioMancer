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
from .models import Check, Evidence, Graph
from .stage_forms import StageOperationError, stage_directory
from .store import (
    GraphConflictError,
    append_journal,
    graph_transaction,
    next_evidence_id,
    run_dir,
    save_graph,
    serialized_graph_mutation,
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
                stage is not check or implementation, or no checks are imported.
    """
    _require_external_evidence_preconditions(graph)
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
        {"stage": graph.stage, "path": path.relative_to(repo_root).as_posix()},
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
    """
    _require_external_evidence_preconditions(graph)
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
    if not isinstance(rows, list) or len(rows) != len(graph.checks):
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


def _require_external_evidence_preconditions(graph: Graph) -> None:
    """
    @brief Enforce shared preparation and recording preconditions.
    @param[in] graph Active workflow graph.
    @return None.
    @exception StageOperationError If stage, mode, or check state is invalid.
    """
    _require_mode(graph, "external")
    if graph.stage not in {"check", "implementation"}:
        raise StageOperationError(
            "check evidence is valid only during check or implementation"
        )
    if not graph.checks:
        raise StageOperationError("no imported checks are available")


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


def _update_check_states(graph: Graph, evidence: list[Evidence]) -> None:
    """@brief Link evidence and update red/green state after atomic creation."""
    by_id = {item.check_id: item for item in evidence}
    for check in graph.checks:
        item = by_id.get(check.id)
        if not item:
            continue
        if item.result == "fail":
            check.state = "red"
            check.red_evidence = item.id
        elif item.result == "pass":
            check.state = "green"
            check.green_evidence = item.id


def _next_evidence_id(graph: Graph, offset: int) -> str:
    """
    @brief Generate the next durable sequence ID without model input.
    """
    return next_evidence_id(graph, offset)


# END OF FILE
