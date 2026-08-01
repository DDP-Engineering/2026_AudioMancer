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
@details Graph mutations now reload under a repository/run-scoped OS lock,
         reject stale direct saves, publish through atomic sibling replacement,
         and serialize crash-safe journal replacement.
@details Human-approved blocker waivers are minted and journaled inside the
         same serialized graph-mutation boundary as other durable run state.
"""

# IMPORTS

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import wraps
from hashlib import sha256
import json
import os  # noqa: F401 - retained for the established fault-injection seam
from pathlib import Path
import re
from typing import Any, Callable, Concatenate, Iterator, ParamSpec, TypeVar
from uuid import uuid4

from .models import (
    AccessMode,
    Evidence,
    Graph,
    Intent,
    RunKind,
    RunProfile,
    Stage,
    Waiver,
    now_iso,
)
from .stage_schema import RUN_STAGE_SCHEMAS, StageOperationError, run_stage_spec
from .persistence import (
    PersistenceError,
    atomic_write_bytes,
    atomic_write_text,
    locked,
    scoped_lock_path,
)

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
_GRAPH_PARAMETERS = ParamSpec("_GRAPH_PARAMETERS")
_GRAPH_RESULT = TypeVar("_GRAPH_RESULT")

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
        """
        return f"{self.code}: {self.message}\n{self.remediation}"

    def to_dict(self) -> dict[str, str | None]:
        """
        @brief      Serialize the stable run-resolution fields.
        @return     JSON-compatible error mapping.
        """
        return {
            "code": self.code,
            "pointer_path": self.pointer_path,
            "run_id": self.run_id,
            "message": self.message,
            "remediation": self.remediation,
        }


class GraphConflictError(PersistenceError):
    """
    @brief Reject a stale in-memory graph before it can overwrite newer state.
    """

    code = "GRAPH-STALE-UPDATE"

    def __init__(self, run_id: str) -> None:
        """
        @brief Initialize an actionable stale-graph conflict.
        @param[in] run_id Conflicting run identity.
        """
        self.run_id = run_id
        super().__init__(
            f"{self.code}: graph {run_id} changed after it was loaded. "
            "Reload the run and retry the operation."
        )

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
    """
    if root.name == AGENTIC_DIR or AGENTIC_DIR in root.parts:
        raise SystemExit(
            f"Refusing to use '{root}' as the workflow root: it is the "
            f"'{AGENTIC_DIR}' directory itself or nested inside one. Run this "
            "command from the project root, not from inside '.agentic'."
        )


def agentic_root(repo_root: Path) -> Path:
    """
    @brief      Return the repository's `.agentic` directory path.
    @param[in]  repo_root Repository root.
    @return     `.agentic` path; not created by this call.
    @exception  None
    """
    return repo_root / AGENTIC_DIR


def runs_root(repo_root: Path) -> Path:
    """
    @brief      Return the `.agentic/runs` directory path.
    @param[in]  repo_root Repository root.
    @return     `.agentic/runs` path; not created by this call.
    @exception  None
    """
    return agentic_root(repo_root) / RUNS_DIR


def workspace_root(repo_root: Path) -> Path:
    """
    @brief      Return the ignored, worktree-local AEGIS workspace root.
    @param[in]  repo_root Repository root.
    @return     `.agentic/.workspace` path without creating it.
    """
    return agentic_root(repo_root) / WORKSPACE_DIR


def workspace_state_root(repo_root: Path) -> Path:
    """
    @brief      Return the worktree-local state directory.
    @param[in]  repo_root Repository root.
    @return     `.agentic/.workspace/state` path without creating it.
    """
    return workspace_root(repo_root) / WORKSPACE_STATE_DIR


def current_run_path(repo_root: Path) -> Path:
    """
    @brief      Return the worktree-local active-run pointer path.
    @param[in]  repo_root Repository root.
    @return     `.agentic/.workspace/state/current_run` path.
    @exception  None
    """
    return workspace_state_root(repo_root) / CURRENT_RUN


def new_run_id(kind: str) -> str:
    """
    @brief      Generate a new run ID as `<kind>-<UTC-timestamp>-<8-hex-suffix>`.
    @param[in]  kind Run kind prefix (feature/fix/change/adoption).
    @return     New run ID matching `RUN_ID_PATTERN`.
    @exception  None
    """
    return f"{kind}-{now_iso().replace(':', '').replace('+0000', 'Z')}-{uuid4().hex[:8]}"


def run_dir(repo_root: Path, run_id: str) -> Path:
    """
    @brief      Return one run's directory path.
    @param[in]  repo_root Repository root.
    @param[in]  run_id Run identity.
    @return     `.agentic/runs/<run_id>` path; not created by this call.
    @exception  None
    """
    return runs_root(repo_root) / run_id


def graph_path(repo_root: Path, run_id: str) -> Path:
    """
    @brief      Return one run's `graph.json` path.
    @param[in]  repo_root Repository root.
    @param[in]  run_id Run identity.
    @return     `.agentic/runs/<run_id>/graph.json` path; not created by this call.
    @exception  None
    """
    return run_dir(repo_root, run_id) / GRAPH_FILE


def journal_path(repo_root: Path, run_id: str) -> Path:
    """
    @brief      Return one run's `journal.jsonl` path.
    @param[in]  repo_root Repository root.
    @param[in]  run_id Run identity.
    @return     `.agentic/runs/<run_id>/journal.jsonl` path; not created by this call.
    @exception  None
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
    """
    if not _is_valid_run_id(run_id):
        raise _explicit_run_error(None, received=run_id)
    atomic_write_text(current_run_path(repo_root), f"{run_id}\n")


def resolve_run_id(repo_root: Path, explicit_run_id: str | None = None) -> str:
    """
    @brief      Resolve and validate an explicit or worktree-selected run ID.
    @param[in]  repo_root Repository root.
    @param[in]  explicit_run_id Optional run ID that takes precedence over the
                workspace pointer.
    @return     Validated run ID whose graph is readable and internally
                consistent.
    @exception  RunResolutionError If the selection or graph is invalid.
    @exception  StageOperationError If the loaded graph's kind/profile/stage
                state conflicts with its lifecycle schema.
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
            remediation=_pointer_missing_remediation(repo_root, pointer_relative),
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
    """
    return f"{AGENTIC_DIR}/{WORKSPACE_DIR}/{WORKSPACE_STATE_DIR}/{CURRENT_RUN}"


def _discoverable_runs(repo_root: Path) -> list[tuple[str, bool]]:
    """
    @brief      List the runs a lost worktree pointer could be restored to.
    @details    The pointer is worktree-local and deliberately ignored by Git,
                while `.agentic/runs/` is durable — so whenever the pointer is
                gone the runs themselves are almost always still there, and the
                operator only needs to be told which ones. Reading is
                deliberately tolerant: this feeds a diagnostic message, so an
                unreadable or malformed `graph.json` is reported as a run that
                exists rather than allowed to mask the runs beside it.
    @param[in]  repo_root Repository root.
    @return     `(run_id, complete)` pairs sorted by run ID; unreadable graphs
                are reported as incomplete. Empty when no runs are discoverable.
    @exception  None All filesystem and decoding failures are absorbed.
    """
    try:
        entries = sorted(runs_root(repo_root).iterdir())
    except OSError:
        return []
    runs: list[tuple[str, bool]] = []
    for entry in entries:
        if not _is_valid_run_id(entry.name):
            continue
        complete = False
        try:
            document = json.loads((entry / GRAPH_FILE).read_text(encoding="utf-8"))
            complete = bool(document.get("complete", False))
        except (OSError, UnicodeError, ValueError):
            complete = False
        runs.append((entry.name, complete))
    return runs


def _pointer_missing_remediation(repo_root: Path, pointer_relative: str) -> str:
    """
    @brief      Build the actionable RUN-POINTER-MISSING guidance (DPT-F08).
    @details    The deployment test lost the pointer once while the run itself
                was intact, and the message named neither the surviving run nor
                `aegis run select` — the one command that recovers it — so the
                operator had to know the run ID already. The recovery path is
                now stated: the exact command when a single incomplete run makes
                the choice unambiguous, otherwise the candidates to choose from.
    @param[in]  repo_root Repository root.
    @param[in]  pointer_relative Repository-relative pointer path.
    @return     Multi-line remediation text.
    @exception  None
    """
    runs = _discoverable_runs(repo_root)
    incomplete = [run_id for run_id, complete in runs if not complete]
    lines: list[str] = []
    if len(incomplete) == 1:
        lines.append(f"Restore it with `aegis run select {incomplete[0]}`.")
    elif runs:
        lines.append("Select one of the runs already in this repository:")
        lines.extend(
            f"  aegis run select {run_id}" + ("  (complete)" if complete else "")
            for run_id, complete in runs
        )
    lines.append(
        "Start one with `aegis run start <kind>` or rerun this command "
        "with `--run <existing-run-id>`."
    )
    lines.append(f"Expected pointer: {pointer_relative}")
    return "\n".join(lines)


def _is_valid_run_id(run_id: str) -> bool:
    """
    @brief      Validate the lexical and real-UTC run-ID contract.
    @param[in]  run_id Candidate run ID.
    @return     `True` only for a canonical supported run ID.
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
            "Start a new run or pass `--run <existing-run-id>` explicitly."
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
    @exception  StageOperationError If lifecycle kind/profile state conflicts.
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
        raw = resolved.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("graph JSON must be an object")
        graph = Graph.from_dict(payload)
        run_stage_spec(graph)
    except StageOperationError:
        raise
    except (
        AttributeError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        error.add_note(f"cause: {type(exc).__name__}: {exc}")
        raise error from exc
    if graph.run_id != run_id:
        raise error
    graph._source_digest = sha256(raw).hexdigest()
    graph._source_state_digest = sha256(_serialize_graph(graph)).hexdigest()
    return graph


def init_graph(
    repo_root: Path,
    kind: RunKind,
    statement: str,
    access_mode: AccessMode = "standard",
    scope_hint: list[str] | None = None,
    profile: RunProfile = "full",
) -> Graph:
    """
    @brief      Create, persist, and select a new run's initial graph.
    @param[in]  repo_root Repository root.
    @param[in]  kind Run kind.
    @param[in]  statement Intent statement text.
    @param[in]  access_mode Initial access mode.
    @param[in]  scope_hint Optional extra roots accepted by the scope advisory.
    @param[in]  profile Full or proportional quick lifecycle profile.
    @return     Newly persisted graph, already selected as this worktree's
                active run.
    @exception  StageOperationError If the kind/profile pair is unsupported.
    @exception  OSError If the run directory, graph, or journal cannot be
                written.
    """
    run_id = new_run_id(kind)
    try:
        lifecycle = RUN_STAGE_SCHEMAS[(kind, profile)]
    except (KeyError, TypeError):
        raise StageOperationError(
            f"run kind/profile mismatch: kind {kind!r} cannot use "
            f"profile {profile!r}"
        ) from None
    starting_stage: Stage = lifecycle.stages[0]
    graph = Graph(
        run_id=run_id,
        stage=starting_stage,
        intent=Intent(
            id=f"I-{uuid4()}",
            kind=kind,
            statement=statement,
            scope_hint=list(scope_hint or []),
        ),
        profile=profile,
        access_mode=access_mode,
    )
    run_stage_spec(graph)
    run_dir(repo_root, run_id).mkdir(parents=True, exist_ok=True)
    save_graph(repo_root, graph)
    write_current_run(repo_root, run_id)
    started = {
        "kind": kind,
        "statement": statement,
        "access_mode": access_mode,
        "scope_hint": graph.intent.scope_hint,
    }
    if profile == "quick":
        started["profile"] = profile
    append_journal(
        repo_root,
        run_id,
        "run.started",
        started,
    )
    return graph


def load_graph(repo_root: Path, run_id: str) -> Graph:
    """
    @brief      Load one already selected run graph without consulting state.
    @param[in]  repo_root Repository root.
    @param[in]  run_id Explicit, previously resolved run ID.
    @return     Parsed graph whose internal run ID matches `run_id`.
    @exception  RunResolutionError If the ID or graph is invalid.
    @exception  StageOperationError If the loaded graph's kind/profile/stage
                state conflicts with its lifecycle schema.
    @note       Call :func:`resolve_run_id` before this function when a command
                may use the workspace pointer.
    """
    if not _is_valid_run_id(run_id):
        raise _explicit_run_error(None, received=run_id)
    return _load_selected_graph(repo_root, run_id, explicit=True)


def save_graph(repo_root: Path, graph: Graph) -> None:
    """
    @brief Atomically publish a graph unless its loaded source is stale.
    @param[in] repo_root Repository root.
    @param[in,out] graph Complete graph carrying its last loaded digest.
    @return None.
    @exception GraphConflictError If a newer graph is already on disk.
    @exception OSError If persistence or replacement fails.
    """
    path = graph_path(repo_root, graph.run_id)
    content = _serialize_graph(graph)
    with locked(run_lock_path(repo_root, graph.run_id)):
        expected = getattr(graph, "_source_digest", None)
        if path.is_file() and expected is not None:
            current = sha256(path.read_bytes()).hexdigest()
            if current != expected:
                raise GraphConflictError(graph.run_id)
        atomic_write_bytes(path, content)
        graph._source_digest = sha256(content).hexdigest()
        graph._source_state_digest = sha256(content).hexdigest()


def append_journal(
    repo_root: Path,
    run_id: str,
    event: str,
    data: dict[str, Any],
) -> None:
    """
    @brief Serialize one complete UTF-8 JSON line through atomic replacement.
    @param[in] repo_root Repository root.
    @param[in] run_id Run identity selecting the journal.
    @param[in] event Stable event name.
    @param[in] data JSON-compatible event data.
    @return None.
    @exception PersistenceError If the existing journal ends in a partial line.
    @exception OSError If persistence or replacement fails.
    """
    path = journal_path(repo_root, run_id)
    with locked(journal_lock_path(repo_root, run_id)):
        existing = _read_complete_journal(path)
        atomic_write_bytes(path, existing + _journal_line(event, data))


def save_graph_with_journal_events(
    repo_root: Path,
    graph: Graph,
    events: list[tuple[str, dict[str, Any]]],
) -> None:
    """
    @brief Publish one graph transition and its journal records as one unit.
    @details The caller must hold the serialized run mutation boundary. If
             journal publication fails after graph replacement, the previous
             graph bytes are restored before the error propagates.
    @param[in] repo_root Repository root.
    @param[in,out] graph Mutated graph to publish.
    @param[in] events Ordered non-empty journal event/data pairs.
    @return None.
    @exception ValueError If an event envelope is invalid.
    @exception PersistenceError If graph or journal integrity is invalid.
    @exception OSError If durable publication fails.
    """
    if not events or any(
        not isinstance(event, str)
        or not event.strip()
        or not isinstance(data, dict)
        for event, data in events
    ):
        raise ValueError("journal events must contain names and object data")
    journal = journal_path(repo_root, graph.run_id)
    persisted = graph_path(repo_root, graph.run_id)
    with locked(journal_lock_path(repo_root, graph.run_id)):
        existing_journal = _read_complete_journal(journal)
        try:
            previous_graph = persisted.read_bytes()
        except FileNotFoundError as exc:
            raise PersistenceError(
                f"run graph is missing before journaled publication: {persisted}"
            ) from exc
        journal_content = existing_journal + b"".join(
            _journal_line(event, data) for event, data in events
        )
        intended_graph = _serialize_graph(graph)
        graph_published = False
        try:
            save_graph(repo_root, graph)
            graph_published = True
            atomic_write_bytes(journal, journal_content)
        except BaseException as original:
            try:
                graph_published = (
                    persisted.is_file()
                    and persisted.read_bytes() == intended_graph
                )
            except OSError as inspection_error:
                original.add_note(
                    "journaled graph publication could not be inspected: "
                    f"{type(inspection_error).__name__}: {inspection_error}"
                )
            journal_published = False
            try:
                journal_published = (
                    journal.is_file()
                    and journal.read_bytes() == journal_content
                )
            except OSError as inspection_error:
                original.add_note(
                    "journal event publication could not be inspected: "
                    f"{type(inspection_error).__name__}: {inspection_error}"
                )
            if graph_published and not journal_published:
                try:
                    atomic_write_bytes(persisted, previous_graph)
                except (OSError, PersistenceError) as rollback_error:
                    original.add_note(
                        "graph rollback failed after journal event publication "
                        f"failed: {type(rollback_error).__name__}: "
                        f"{rollback_error}"
                    )
            raise


def run_lock_path(repo_root: Path, run_id: str) -> Path:
    """
    @brief Return the repository/run-scoped graph mutation lock.
    @param[in] repo_root Repository root.
    @param[in] run_id Run identity.
    @return Worktree-local persistent lock path.
    """
    return scoped_lock_path(repo_root, "runs", run_id)


def journal_lock_path(repo_root: Path, run_id: str) -> Path:
    """
    @brief Return the repository/run-scoped journal append lock.
    @param[in] repo_root Repository root.
    @param[in] run_id Run identity.
    @return Worktree-local persistent lock path.
    """
    return scoped_lock_path(repo_root, "journals", run_id)


def next_evidence_id(graph: Graph, offset: int = 0) -> str:
    """
    @brief Allocate the next collision-safe monotonic evidence identifier.
    @param[in] graph Authoritative graph held by the current run transaction.
    @param[in] offset Additional identifier offset for a validated batch.
    @return Existing-compatible `E-NNNN` identifier.
    """
    numbers = [
        int(item.id[2:])
        for item in graph.evidence
        if re.fullmatch(r"E-[0-9]+", item.id)
    ]
    number = max(numbers, default=0) + offset + 1
    identifiers = {item.id for item in graph.evidence}
    candidate = f"E-{number:04d}"
    while candidate in identifiers:
        number += 1
        candidate = f"E-{number:04d}"
    return candidate


@contextmanager
def graph_transaction(repo_root: Path, graph: Graph) -> Iterator[Graph]:
    """
    @brief Reload and hold the authoritative graph for one complete mutation.
    @param[in] repo_root Repository root.
    @param[in,out] graph Caller graph refreshed in place under the run lock.
    @return Iterator yielding the refreshed graph.
    @exception RunResolutionError If the authoritative graph is invalid.
    @exception GraphConflictError If the caller's in-memory graph was already
               mutated relative to its loaded source and the on-disk graph has
               also advanced, so the conflict cannot be silently healed by a
               reload.
    """
    with locked(run_lock_path(repo_root, graph.run_id)) as lock:
        persisted = graph_path(repo_root, graph.run_id)
        if not lock.reentrant and persisted.is_file():
            current_digest = sha256(persisted.read_bytes()).hexdigest()
            expected_digest = getattr(graph, "_source_digest", None)
            if expected_digest != current_digest:
                source_state_digest = getattr(
                    graph,
                    "_source_state_digest",
                    None,
                )
                current_state_digest = sha256(
                    _serialize_graph(graph)
                ).hexdigest()
                if (
                    source_state_digest is not None
                    and current_state_digest != source_state_digest
                ):
                    raise GraphConflictError(graph.run_id)
                _replace_graph_state(
                    graph,
                    _load_selected_graph(
                        repo_root,
                        graph.run_id,
                        explicit=True,
                    ),
                )
        try:
            yield graph
        except BaseException as original:
            if not lock.reentrant:
                try:
                    _replace_graph_state(
                        graph,
                        _load_selected_graph(
                            repo_root,
                            graph.run_id,
                            explicit=True,
                        ),
                    )
                except (OSError, RunResolutionError, ValueError) as reload_error:
                    original.add_note(
                        "graph rollback reload failed; the in-memory graph may"
                        " retain the aborted mutation:"
                        f" {type(reload_error).__name__}: {reload_error}"
                    )
            raise


def serialized_graph_mutation(
    function: Callable[
        Concatenate[Path, Graph, _GRAPH_PARAMETERS],
        _GRAPH_RESULT,
    ],
) -> Callable[
    Concatenate[Path, Graph, _GRAPH_PARAMETERS],
    _GRAPH_RESULT,
]:
    """
    @brief Decorate a graph mutator with authoritative reload and run locking.
    @param[in] function Mutator whose first arguments are repository and graph.
    @return Wrapped mutator with the same public signature.
    """
    @wraps(function)
    def wrapper(
        repo_root: Path,
        graph: Graph,
        *args: _GRAPH_PARAMETERS.args,
        **kwargs: _GRAPH_PARAMETERS.kwargs,
    ) -> _GRAPH_RESULT:
        """
        @brief Run one graph mutation inside its serialized transaction.
        """
        with graph_transaction(repo_root, graph):
            return function(repo_root, graph, *args, **kwargs)

    return wrapper


@serialized_graph_mutation
def add_evidence(repo_root: Path, graph: Graph, evidence: Evidence) -> Graph:
    """
    @brief      Append one evidence record and persist it with a journal event.
    @param[in]  repo_root Repository root.
    @param[in,out] graph Active run graph refreshed under its mutation lock
                (decorator).
    @param[in]  evidence Evidence record to append; its ID must be unique on
                the graph.
    @return     Mutated graph.
    @exception  PersistenceError If the evidence ID already exists on the graph.
    @exception  GraphConflictError If the graph changed underneath this
                mutation.
    @exception  OSError If persistence fails.
    """
    if any(item.id == evidence.id for item in graph.evidence):
        raise PersistenceError(
            f"evidence identifier already exists: {evidence.id}"
        )
    graph.evidence.append(evidence)
    save_graph(repo_root, graph)
    append_journal(repo_root, graph.run_id, "evidence.recorded", asdict(evidence))
    return graph


@serialized_graph_mutation
def add_waiver(
    repo_root: Path,
    graph: Graph,
    blocker_id: str,
    reason: str,
    state_digests: dict[str, str],
    *,
    expected_source_digest: str | None = None,
) -> Waiver:
    """
    @brief Persist one human-approved waiver for exact current blocker state.
    @param[in] repo_root Repository root.
    @param[in,out] graph Active run graph refreshed under its mutation lock.
    @param[in] blocker_id Concrete named blocker identity.
    @param[in] reason Mandatory human approval reason.
    @param[in] state_digests Exact state captured when approval was given.
    @param[in] expected_source_digest Graph digest used to discover the target.
    @return Newly minted run-local waiver record.
    @exception ValueError If the blocker, reason, or digest mapping is invalid.
    @exception GraphConflictError If target discovery used an older graph.
    @exception PersistenceError If journal integrity prevents a complete record.
    @exception OSError If persistence fails.
    """
    if (
        expected_source_digest is not None
        and getattr(graph, "_source_digest", None) != expected_source_digest
    ):
        raise GraphConflictError(graph.run_id)
    if not isinstance(blocker_id, str):
        raise ValueError("blocker ID must be a string")
    if not isinstance(reason, str):
        raise ValueError("waiver reason must be a string")
    normalized_blocker_id = blocker_id.strip()
    normalized_reason = reason.strip()
    if not normalized_blocker_id:
        raise ValueError("blocker ID must be non-empty")
    if not normalized_reason:
        raise ValueError("waiver reason must be non-empty")
    if not isinstance(state_digests, dict) or any(
        not isinstance(namespace, str) or not isinstance(digest, str)
        for namespace, digest in state_digests.items()
    ):
        raise ValueError("waiver state digests must map strings to strings")
    if any(
        item.blocker_id == normalized_blocker_id
        and item.state_digests == state_digests
        for item in graph.waivers
    ):
        raise ValueError(
            f"blocker already has an active waiver: {normalized_blocker_id}"
        )
    journal = journal_path(repo_root, graph.run_id)
    with locked(journal_lock_path(repo_root, graph.run_id)):
        existing_journal = _read_complete_journal(journal)
        _validate_journal_records(journal, existing_journal)
        existing_ids = {item.id for item in graph.waivers}
        waiver_id = f"WVR-{uuid4()}"
        while waiver_id in existing_ids:
            waiver_id = f"WVR-{uuid4()}"
        waiver = Waiver(
            id=waiver_id,
            blocker_id=normalized_blocker_id,
            reason=normalized_reason,
            state_digests=dict(state_digests),
        )
        journal_content = existing_journal + _journal_line(
            "waiver.added",
            asdict(waiver),
        )
        graph.waivers.append(waiver)
        graph_published = False
        try:
            save_graph(repo_root, graph)
            graph_published = True
            atomic_write_bytes(journal, journal_content)
        except BaseException as original:
            journal_published = False
            try:
                journal_published = (
                    journal.is_file()
                    and journal.read_bytes() == journal_content
                )
            except OSError as inspection_error:
                original.add_note(
                    "waiver journal publication could not be inspected: "
                    f"{type(inspection_error).__name__}: {inspection_error}"
                )
            if graph_published and not journal_published:
                graph.waivers.pop()
                try:
                    save_graph(repo_root, graph)
                except (OSError, PersistenceError) as rollback_error:
                    original.add_note(
                        "waiver graph rollback failed after journal publication "
                        f"failed: {type(rollback_error).__name__}: "
                        f"{rollback_error}"
                    )
            raise
        return waiver


def _read_complete_journal(path: Path) -> bytes:
    """
    @brief Read a journal only when its final JSON Lines record is complete.
    @param[in] path Journal path.
    @return Existing bytes, or an empty byte string when the file is absent.
    @exception PersistenceError If the journal ends in a partial record.
    """
    existing = path.read_bytes() if path.is_file() else b""
    if existing and not existing.endswith(b"\n"):
        raise PersistenceError(
            f"journal {path} ends with an incomplete record; "
            "restore a valid journal before appending"
        )
    return existing


def _journal_line(event: str, data: dict[str, Any]) -> bytes:
    """
    @brief Serialize one timestamped journal event as a complete JSON line.
    @param[in] event Stable event name.
    @param[in] data JSON-compatible event data.
    @return Sorted UTF-8 JSON followed by one newline.
    """
    entry = {"time": now_iso(), "event": event, "data": data}
    return (json.dumps(entry, sort_keys=True) + "\n").encode("utf-8")


def _validate_journal_records(path: Path, content: bytes) -> None:
    """
    @brief Validate every existing journal line before recording a waiver.
    @param[in] path Journal path used in actionable integrity errors.
    @param[in] content Complete newline-terminated journal bytes.
    @return None.
    @exception PersistenceError If JSON or the event envelope is malformed.
    """
    for line_number, line in enumerate(content.splitlines(), start=1):
        try:
            entry = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PersistenceError(
                f"journal {path} record {line_number} is not valid JSON; "
                "restore a valid journal before adding a waiver"
            ) from exc
        if (
            not isinstance(entry, dict)
            or set(entry) != {"time", "event", "data"}
            or not isinstance(entry["time"], str)
            or not entry["time"].strip()
            or not isinstance(entry["event"], str)
            or not entry["event"].strip()
            or not isinstance(entry["data"], dict)
        ):
            raise PersistenceError(
                f"journal {path} record {line_number} has an invalid event "
                "envelope; restore a valid journal before adding a waiver"
            )


@serialized_graph_mutation
def set_stage(repo_root: Path, graph: Graph, stage: Stage) -> Graph:
    """
    @brief      Set the graph's current stage and persist it with a
                `stage.set` journal event.
    @param[in]  repo_root Repository root.
    @param[in,out] graph Active run graph refreshed under its mutation lock
                (decorator).
    @param[in]  stage New stage value.
    @return     Mutated graph.
    @exception  GraphConflictError If the graph changed underneath this
                mutation.
    @exception  OSError If persistence fails.
    """
    graph.stage = stage
    save_graph(repo_root, graph)
    append_journal(repo_root, graph.run_id, "stage.set", {"stage": stage})
    return graph


@serialized_graph_mutation
def set_access_mode(
    repo_root: Path,
    graph: Graph,
    access_mode: AccessMode,
    reason: str,
) -> Graph:
    """
    @brief      Set the graph's access mode and persist it with an
                `access_mode.set` journal event.
    @param[in]  repo_root Repository root.
    @param[in,out] graph Active run graph refreshed under its mutation lock
                (decorator).
    @param[in]  access_mode New access mode.
    @param[in]  reason Human-readable reason recorded in the journal event.
    @return     Mutated graph.
    @exception  GraphConflictError If the graph changed underneath this
                mutation.
    @exception  OSError If persistence fails.
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


def _replace_graph_state(target: Graph, source: Graph) -> None:
    """
    @brief Refresh one caller-held graph object without changing its identity.
    @param[in,out] target Graph instance retained by the caller.
    @param[in] source Newly loaded authoritative graph.
    @return None.
    """
    target.__dict__.clear()
    target.__dict__.update(source.__dict__)


def _serialize_graph(graph: Graph) -> bytes:
    """
    @brief Serialize one graph using the canonical persisted JSON format.
    @param[in] graph Complete graph state.
    @return UTF-8 bytes ending in one newline.
    """
    return (
        json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


# END OF FILE
