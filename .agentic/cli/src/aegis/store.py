#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file store.py
@brief Persistence helpers for agentic workflow run state.
@details Mirrors the packaged CLI implementation shipped into generated projects.
@details ``repo_root_from`` (0.3.0, code-review follow-up) now refuses a
         resolved root that is itself named ``.agentic`` or nested inside one:
         previously, invoking the CLI with the process working directory
         mistakenly set to a project's own ``.agentic`` folder (or a
         previously self-nested copy of it) silently created another
         ``.agentic/.agentic/...`` layer instead of failing, since
         ``agentic_root()``/``write_current_run()``/``init_graph()`` all
         ``mkdir(parents=True, exist_ok=True)`` unconditionally.
@details ``repo_root_from`` (0.4.0, analysis-review follow-up) resolves the
         workflow root by upward discovery instead of trusting the working
         directory verbatim: the nearest ancestor containing an ``.agentic``
         directory wins, then the nearest ancestor containing ``.git``, then
         the candidate itself (legacy greenfield behavior). Previously, any
         command run from a repository subdirectory treated that subdirectory
         as the root, so ``status`` reported "No active agentic run" and
         following its advice scaffolded a nested ``src/.agentic/`` silently;
         a working directory inside ``.agentic`` itself now heals to the
         surrounding project root instead of exiting.
@details ``init_graph`` (0.4.0) publishes the active-run selector atomically
         below ignored, worktree-local workspace state only after the initial
         graph has been saved successfully.
@details ``resolve_run_id`` and ``load_graph`` (0.1.0) implement the strict
         explicit-first active-run contract with typed, actionable failures.
@author Eng. Dan Dumitru Pasare
@date 2026-07-20
@version 0.6.0
"""

# IMPORTS

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from .models import ADOPTION_STAGES, AccessMode, Evidence, Graph, Intent, RunKind, Stage, now_iso

# CONSTANTS

AGENTIC_DIR = ".agentic"
RUNS_DIR = "runs"
WORKSPACE_DIR = ".workspace"
WORKSPACE_STATE_DIR = "state"
CURRENT_RUN = "current_run"
GRAPH_FILE = "graph.json"
JOURNAL_FILE = "journal.jsonl"
RUN_ID_PATTERN = re.compile(
    r"^(feature|fix|change|adoption)-"
    r"(?P<timestamp>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z)-"
    r"[0-9a-f]{8}$"
)

# DATA MODELS / TYPEDEFINITIONS


@dataclass
class RunResolutionError(Exception):
    """
    @brief      Describe one stable active-run resolution failure.
    @param[in]  code Stable machine-readable error code.
    @param[in]  pointer_path Repository-relative pointer path, when applicable.
    @param[in]  run_id Valid-shaped candidate run ID, when available.
    @param[in]  message Human-readable failure description.
    @param[in]  remediation Concrete corrective action for an agent.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.2.0
    """

    code: str
    pointer_path: str | None
    run_id: str | None
    message: str
    remediation: str

    def __str__(self) -> str:
        """
        @brief      Render the stable text error contract.
        @return     Error code, message, and remediation.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-22
        @version    0.1.0
        """
        return f"{self.code}: {self.message}\n{self.remediation}"

    def to_dict(self) -> dict[str, str | None]:
        """
        @brief      Serialize the stable run-resolution fields.
        @return     JSON-compatible error mapping.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-22
        @version    0.1.0
        """
        return {
            "code": self.code,
            "pointer_path": self.pointer_path,
            "run_id": self.run_id,
            "message": self.message,
            "remediation": self.remediation,
        }

# PUBLIC API


def repo_root_from(path: Path | None = None) -> Path:
    """
    @brief      Resolve the workflow root by upward marker discovery.
    @param[in]  path Optional starting directory; defaults to the process
                working directory.
    @return     Resolved workflow root.
    @details    Discovery order: the nearest ancestor (starting with the
                candidate itself) that contains an ``.agentic`` directory,
                else the nearest ancestor that contains ``.git``, else the
                candidate itself. This makes every CLI command safe to run
                from any repository subdirectory — including from inside
                ``.agentic`` itself, which previously exited — and prevents
                ``start`` from scaffolding a second ``.agentic/`` below an
                existing install.
    @exception  SystemExit Raised by the safety-net guard when the resolved
                root is itself named ``.agentic`` or nested inside one (only
                reachable for paths that do not exist on disk).
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-20
    @version    0.3.0
    """
    candidate = (path or Path.cwd()).resolve()
    root = _discover_root(candidate)
    _reject_nested_agentic_root(root)
    return root


def _discover_root(candidate: Path) -> Path:
    """
    @brief      Walk upward from a candidate directory to the workflow root.
    @param[in]  candidate Resolved starting directory.
    @return     The discovered workflow root, or the candidate itself.
    @details    Two full passes, not one nearest-marker pass: ``.agentic`` is
                the authoritative AEGIS marker and must win even when a
                vendored checkout puts a ``.git`` closer to the candidate —
                a nearest-marker rule would resolve into the vendored
                repository and reintroduce the nested-scaffold defect there.
                ``.git`` is checked with ``exists()`` rather than ``is_dir()``
                because linked worktrees mark their root with a ``.git``
                file. With no marker anywhere upward the candidate itself is
                returned, preserving the greenfield ``start`` behavior.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-20
    @version    0.1.0
    """
    directories = (candidate, *candidate.parents)
    for directory in directories:
        if (directory / AGENTIC_DIR).is_dir():
            return directory
    for directory in directories:
        if (directory / ".git").exists():
            return directory
    return candidate


def _reject_nested_agentic_root(root: Path) -> None:
    """
    @brief      Refuse a workflow root that is itself named ``.agentic`` or
                nested inside one.
    @param[in]  root Resolved candidate workflow root.
    @return     None
    @details    Safety net behind :func:`_discover_root`. For any path that
                exists on disk discovery heals this case first (the parent
                containing ``.agentic`` always wins), so the guard only fires
                for nonexistent-path fallbacks — where the unchecked
                ``mkdir(parents=True, exist_ok=True)`` write paths
                (``write_current_run``, ``init_graph``) could still grow an
                ``.agentic/.agentic/...`` layer.
    @exception  SystemExit Raised when ``root`` matches or contains an
                ``.agentic`` path segment.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-20
    @version    0.2.0
    """
    if root.name == AGENTIC_DIR or AGENTIC_DIR in root.parts:
        raise SystemExit(
            f"Refusing to use '{root}' as the workflow root: it is the "
            f"'{AGENTIC_DIR}' directory itself or nested inside one. Run this "
            "command from the project root, not from inside '.agentic'."
        )


def agentic_root(repo_root: Path) -> Path:
    """
    @brief      Resolve agentic root workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return repo_root / AGENTIC_DIR


def runs_root(repo_root: Path) -> Path:
    """
    @brief      Handle runs root workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return agentic_root(repo_root) / RUNS_DIR


def workspace_root(repo_root: Path) -> Path:
    """
    @brief      Return the ignored, worktree-local AEGIS workspace root.
    @param[in]  repo_root Repository root.
    @return     `.agentic/.workspace` path without creating it.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.1.0
    """
    return agentic_root(repo_root) / WORKSPACE_DIR


def workspace_state_root(repo_root: Path) -> Path:
    """
    @brief      Return the worktree-local state directory.
    @param[in]  repo_root Repository root.
    @return     `.agentic/.workspace/state` path without creating it.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.1.0
    """
    return workspace_root(repo_root) / WORKSPACE_STATE_DIR


def current_run_path(repo_root: Path) -> Path:
    """
    @brief      Return the worktree-local active-run pointer path.
    @param[in]  repo_root Repository root.
    @return     `.agentic/.workspace/state/current_run` path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.2.0
    """
    return workspace_state_root(repo_root) / CURRENT_RUN


def new_run_id(kind: str) -> str:
    """
    @brief      Create new run id workflow behavior.
    @param[in]  kind Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return f"{kind}-{now_iso().replace(':', '').replace('+0000', 'Z')}-{uuid4().hex[:8]}"


def run_dir(repo_root: Path, run_id: str) -> Path:
    """
    @brief      Run dir workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  run_id Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return runs_root(repo_root) / run_id


def graph_path(repo_root: Path, run_id: str) -> Path:
    """
    @brief      Resolve graph path workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  run_id Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return run_dir(repo_root, run_id) / GRAPH_FILE


def journal_path(repo_root: Path, run_id: str) -> Path:
    """
    @brief      Resolve journal path workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  run_id Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return run_dir(repo_root, run_id) / JOURNAL_FILE


def write_current_run(repo_root: Path, run_id: str) -> None:
    """
    @brief      Atomically publish the worktree-local active-run pointer.
    @param[in]  repo_root Repository root.
    @param[in]  run_id Valid run ID to publish.
    @return     None.
    @exception  RunResolutionError If `run_id` is malformed.
    @exception  OSError If the state directory or pointer cannot be written.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.2.0
    """
    if not _is_valid_run_id(run_id):
        raise _explicit_run_error(None, received=run_id)
    state_root = workspace_state_root(repo_root)
    state_root.mkdir(parents=True, exist_ok=True)
    destination = current_run_path(repo_root)
    temporary = destination.with_name(f".{CURRENT_RUN}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(f"{run_id}\n".encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def resolve_run_id(repo_root: Path, explicit_run_id: str | None = None) -> str:
    """
    @brief      Resolve and validate an explicit or worktree-selected run ID.
    @param[in]  repo_root Repository root.
    @param[in]  explicit_run_id Optional run ID that takes precedence over the
                workspace pointer.
    @return     Validated run ID whose graph is readable and internally
                consistent.
    @exception  RunResolutionError If the selection or graph is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.1.0
    """
    if explicit_run_id is not None:
        if not _is_valid_run_id(explicit_run_id):
            raise _explicit_run_error(None, received=explicit_run_id)
        _load_selected_graph(repo_root, explicit_run_id, explicit=True)
        return explicit_run_id

    pointer = current_run_path(repo_root)
    pointer_relative = _pointer_relative_path()
    if not pointer.exists():
        raise RunResolutionError(
            code="RUN-POINTER-MISSING",
            pointer_path=pointer_relative,
            run_id=None,
            message="No active AEGIS run is selected for this worktree.",
            remediation=(
                "Start one with `aegis start ...` or rerun this command with "
                "`--run-id <existing-run-id>`.\n"
                f"Expected pointer: {pointer_relative}"
            ),
        )
    try:
        raw = pointer.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError):
        raise _invalid_pointer_error() from None
    if not text.endswith("\n") or text.count("\n") != 1:
        raise _invalid_pointer_error()
    run_id = text[:-1]
    if not _is_valid_run_id(run_id):
        raise _invalid_pointer_error()
    _load_selected_graph(repo_root, run_id, explicit=False)
    return run_id


# LOCAL HELPERS


def _pointer_relative_path() -> str:
    """
    @brief      Return the stable repository-relative pointer path.
    @return     POSIX-form pointer path used in errors and JSON.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.1.0
    """
    return f"{AGENTIC_DIR}/{WORKSPACE_DIR}/{WORKSPACE_STATE_DIR}/{CURRENT_RUN}"


def _is_valid_run_id(run_id: str) -> bool:
    """
    @brief      Validate the lexical and real-UTC run-ID contract.
    @param[in]  run_id Candidate run ID.
    @return     `True` only for a canonical supported run ID.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.1.0
    """
    match = RUN_ID_PATTERN.fullmatch(run_id)
    if match is None:
        return False
    try:
        datetime.strptime(match.group("timestamp"), "%Y-%m-%dT%H%M%SZ")
    except ValueError:
        return False
    return True


def _invalid_pointer_error() -> RunResolutionError:
    """
    @brief      Build the stable malformed-pointer error.
    @return     `RUN-POINTER-INVALID` error.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.1.0
    """
    pointer_relative = _pointer_relative_path()
    return RunResolutionError(
        code="RUN-POINTER-INVALID",
        pointer_path=pointer_relative,
        run_id=None,
        message=f"{pointer_relative} does not contain a valid run ID.",
        remediation=(
            "Start a new run or replace the pointer by starting/selecting a valid run; "
            "do not edit run graphs by guessing an ID."
        ),
    )


def _explicit_run_error(
    run_id: str | None,
    *,
    received: str | None = None,
) -> RunResolutionError:
    """
    @brief      Build the stable explicit-selection error.
    @param[in]  run_id Valid-shaped candidate, when available.
    @param[in]  received Original malformed value, when no valid candidate is
                available for the serialized `run_id` field.
    @return     `RUN-ID-NOT-FOUND` error.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.2.0
    """
    display = run_id if run_id is not None else (received or "<invalid-run-id>")
    return RunResolutionError(
        code="RUN-ID-NOT-FOUND",
        pointer_path=None,
        run_id=run_id,
        message=(
            f"Explicit run {display} does not resolve to a valid graph under "
            f"{AGENTIC_DIR}/{RUNS_DIR}/."
        ),
        remediation=(
            "List the available run directories or start a new run, then retry "
            "with the exact ID."
        ),
    )


def _stale_pointer_error(run_id: str) -> RunResolutionError:
    """
    @brief      Build the stable stale-pointer error.
    @param[in]  run_id Valid-shaped workspace selection.
    @return     `RUN-POINTER-STALE` error.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.1.0
    """
    return RunResolutionError(
        code="RUN-POINTER-STALE",
        pointer_path=_pointer_relative_path(),
        run_id=run_id,
        message=(
            f"This worktree selects {run_id}, but {AGENTIC_DIR}/{RUNS_DIR}/"
            f"{run_id}/{GRAPH_FILE} is missing or invalid."
        ),
        remediation=(
            "Start a new run or pass `--run-id <existing-run-id>` explicitly."
        ),
    )


def _load_selected_graph(repo_root: Path, run_id: str, *, explicit: bool) -> Graph:
    """
    @brief      Validate containment and parse one selected graph.
    @param[in]  repo_root Repository root.
    @param[in]  run_id Canonical run ID.
    @param[in]  explicit Whether failures use the explicit-selection contract.
    @return     Parsed, internally consistent graph.
    @exception  RunResolutionError If containment, I/O, JSON, model parsing,
                or graph identity validation fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.2.0
    """
    error = _explicit_run_error(run_id) if explicit else _stale_pointer_error(run_id)
    root = runs_root(repo_root).resolve()
    path = graph_path(repo_root, run_id)
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        raise error from None
    if not resolved.is_file():
        raise error
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("graph JSON must be an object")
        graph = Graph.from_dict(payload)
    except (
        AttributeError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        raise error from None
    if graph.run_id != run_id:
        raise error
    return graph


def init_graph(
    repo_root: Path,
    kind: RunKind,
    statement: str,
    access_mode: AccessMode = "standard",
    scope_hint: list[str] | None = None,
) -> Graph:
    """
    @brief      Handle init graph workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  kind Input value used by the workflow helper.
    @param[in]  statement Input value used by the workflow helper.
    @param[in]  access_mode Input value used by the workflow helper.
    @param[in]  scope_hint Optional extra roots accepted by the scope advisory.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-20
    @version    0.4.0
    """
    run_id = new_run_id(kind)
    starting_stage: Stage = ADOPTION_STAGES[0] if kind == "adoption" else "intake"
    graph = Graph(
        run_id=run_id,
        stage=starting_stage,
        intent=Intent(
            id="I-0001",
            kind=kind,
            statement=statement,
            scope_hint=list(scope_hint or []),
        ),
        access_mode=access_mode,
    )
    run_dir(repo_root, run_id).mkdir(parents=True, exist_ok=True)
    save_graph(repo_root, graph)
    write_current_run(repo_root, run_id)
    append_journal(
        repo_root,
        run_id,
        "run.started",
        {
            "kind": kind,
            "statement": statement,
            "access_mode": access_mode,
            "scope_hint": graph.intent.scope_hint,
        },
    )
    return graph


def load_graph(repo_root: Path, run_id: str) -> Graph:
    """
    @brief      Load one already selected run graph without consulting state.
    @param[in]  repo_root Repository root.
    @param[in]  run_id Explicit, previously resolved run ID.
    @return     Parsed graph whose internal run ID matches `run_id`.
    @exception  RunResolutionError If the ID or graph is invalid.
    @note       Call :func:`resolve_run_id` before this function when a command
                may use the workspace pointer.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.2.0
    """
    if not _is_valid_run_id(run_id):
        raise _explicit_run_error(None, received=run_id)
    return _load_selected_graph(repo_root, run_id, explicit=True)


def save_graph(repo_root: Path, graph: Graph) -> None:
    """
    @brief      Save graph workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    path = graph_path(repo_root, graph.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def append_journal(repo_root: Path, run_id: str, event: str, data: dict) -> None:
    """
    @brief      Append journal workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  run_id Input value used by the workflow helper.
    @param[in]  event Input value used by the workflow helper.
    @param[in]  data Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    path = journal_path(repo_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"time": now_iso(), "event": event, "data": data}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def add_evidence(repo_root: Path, graph: Graph, evidence: Evidence) -> Graph:
    """
    @brief      Add evidence workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  evidence Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    graph.evidence.append(evidence)
    save_graph(repo_root, graph)
    append_journal(repo_root, graph.run_id, "evidence.recorded", evidence.__dict__)
    return graph


def set_stage(repo_root: Path, graph: Graph, stage: Stage) -> Graph:
    """
    @brief      Set stage workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  stage Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    graph.stage = stage
    save_graph(repo_root, graph)
    append_journal(repo_root, graph.run_id, "stage.set", {"stage": stage})
    return graph


def set_access_mode(
    repo_root: Path,
    graph: Graph,
    access_mode: AccessMode,
    reason: str,
) -> Graph:
    """
    @brief      Set access mode workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  access_mode Input value used by the workflow helper.
    @param[in]  reason Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    graph.access_mode = access_mode
    save_graph(repo_root, graph)
    append_journal(
        repo_root,
        graph.run_id,
        "access_mode.set",
        {"access_mode": access_mode, "reason": reason},
    )
    return graph


# END OF FILE
