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
@details ``init_graph`` (0.3.0) persists optional scope hints in the run intent
         and initial journal event so INV-5 can honor explicit extra roots.
@author Eng. Dan Dumitru Pasare
@date 2026-07-20
@version 0.5.0
"""

# IMPORTS

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .models import ADOPTION_STAGES, AccessMode, Evidence, Graph, Intent, RunKind, Stage, now_iso

# CONSTANTS

AGENTIC_DIR = ".agentic"
RUNS_DIR = "runs"
CURRENT_RUN = "current_run"
GRAPH_FILE = "graph.json"
JOURNAL_FILE = "journal.jsonl"

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


def current_run_path(repo_root: Path) -> Path:
    """
    @brief      Resolve current run path workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return agentic_root(repo_root) / CURRENT_RUN


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
    @brief      Write current run workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  run_id Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    agentic_root(repo_root).mkdir(parents=True, exist_ok=True)
    current_run_path(repo_root).write_text(run_id, encoding="utf-8")


def read_current_run(repo_root: Path) -> str:
    """
    @brief      Read current run workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    path = current_run_path(repo_root)
    if not path.exists():
        raise SystemExit("No active agentic run. Start one with: aegis start")
    return path.read_text(encoding="utf-8").strip()


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
    @version    0.3.0
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


def load_graph(repo_root: Path, run_id: str | None = None) -> Graph:
    """
    @brief      Load graph workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  run_id Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    active_id = run_id or read_current_run(repo_root)
    path = graph_path(repo_root, active_id)
    if not path.exists():
        raise SystemExit(f"Graph not found for run {active_id}")
    return Graph.from_dict(json.loads(path.read_text(encoding="utf-8")))


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
